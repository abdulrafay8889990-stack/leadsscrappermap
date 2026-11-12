"""Shared Playwright plumbing for every scraper.

BaseScraper owns the browser lifecycle, human-paced delays, defensive DOM helpers
(which return "" instead of raising when an element is missing), Google consent
handling and CAPTCHA detection. Subclasses only implement ``scrape()``.
"""
from __future__ import annotations

import asyncio
import json
from collections import deque
from dataclasses import dataclass
import random
import re
import threading
from abc import ABC, abstractmethod
from typing import Any, Callable, Iterable

from playwright.async_api import BrowserContext, Locator, Page, Playwright, async_playwright
from playwright.async_api import Error as PlaywrightError

from core.email_finder import SearchBlocked, find_emails, search_business_email
from core.history import LeadHistory
from core.geo import geocode, spiral_tiles
from core.locations import COUNTRIES, parse_location
from core.models import WEBSITE_NONE, WEBSITE_REAL, Lead, classify_website
from core.paths import PROFILES_DIR

EmitFn = Callable[[str, Any], None]

# Business photos, map tiles, Street View and web fonts: large and useless for lead data.
HEAVY_RESOURCES_RE = re.compile(
    r"googleusercontent\.com/|/maps/vt[/?]|/kh/v=|streetviewpixels|/maps/api/staticmap|fonts\.gstatic\.com"
    r"|\.(?:jpe?g|png|gif|webp|avif|woff2?|ttf|mp4)(?:\?|$)",
    re.I,
)

# North-American style numbers with an optional +country code, e.g. (312) 555-0100, +1 312-555-0100.
PHONE_RE = re.compile(r"(?<!\d)(?:\+\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")

# Google Maps renders icons with Private-Use-Area glyphs that leak into inner_text.
_ICON_GLYPHS_RE = re.compile(r"[-]")

# Pages that mean "you've been flagged as a bot".
_BLOCK_URL_MARKERS = ("/sorry/", "captcha", "/blocked")
_BLOCK_SELECTORS = (
    "form#captcha-form",
    'iframe[src*="recaptcha"]',
    'iframe[src*="captcha-delivery"]',  # DataDome
    "#px-captcha",
)
_HARD_BLOCK_RE = re.compile(r"you have been blocked|access denied|your ip .* (has been )?blocked", re.I)


@dataclass
class SearchItem:
    """One search in the run queue. Expansions carry `target`: the total lead count their
    group must reach (the shortfall of the search they came from)."""

    keyword: str
    location: str
    coords: tuple[float, float] | None = None
    target: int | None = None
    level: str = "top"  # top (user's) | city (from a country) | tile (map tile / area)
    tile: str = ""


class ScrapeAborted(Exception):
    """Raised to end a run cleanly (user stop, unsolved CAPTCHA). Not treated as a crash."""


BROWSER_CLOSED_MESSAGE = "The browser window was closed, so the run stopped. Leads found so far are kept."


def is_browser_closed(exc: Exception) -> bool:
    text = str(exc)
    return "has been closed" in text or "Target closed" in text or "Browser closed" in text


def clean_text(value: str | None) -> str:
    """Strip icon glyphs and collapse whitespace."""
    if not value:
        return ""
    value = _ICON_GLYPHS_RE.sub("", value)
    return re.sub(r"\s+", " ", value).strip()


def find_phone(text: str) -> str:
    match = PHONE_RE.search(text or "")
    return match.group(0).strip() if match else ""


def digits_only(text: str) -> str:
    """'(1,234 reviews)' -> '1234'. Also expands '1.2K' -> '1200'."""
    text = (text or "").strip()
    k_match = re.search(r"(\d+(?:\.\d+)?)\s*[kK]\b", text)
    if k_match:
        return str(int(float(k_match.group(1)) * 1000))
    return re.sub(r"\D", "", text)


class BaseScraper(ABC):
    SOURCE = "Base"
    PROFILE = "default"  # browser profile folder name; sites that share cookies share a profile
    SEARCH_PAUSE = (3.0, 6.0)  # seconds to wait between two searches

    def __init__(
        self,
        keywords: list[str],
        locations: list[str],
        max_results: int,
        headless: bool,
        stop_event: threading.Event,
        emit: EmitFn,
        options: dict[str, Any] | None = None,
    ) -> None:
        self.keywords = [k.strip() for k in keywords if k.strip()]
        self.locations = [loc.strip() for loc in locations if loc.strip()] or [""]
        # The search currently being scraped; run() moves through every keyword x location pair.
        self.keyword = self.keywords[0]
        self.location = self.locations[0]
        self.max_results = max_results
        self.headless = headless
        self.stop_event = stop_event
        self.emit = emit
        self.options = options or {}
        # "all" | "no_real_website" (social-only pages allowed) | "no_website"
        self.website_filter: str = self.options.get("website_filter", "all")
        self.require_phone: bool = bool(self.options.get("require_phone", False))
        # Every lead is recorded in the history; skip_known also drops leads from earlier runs.
        self.skip_known: bool = bool(self.options.get("skip_known", True))
        self.find_emails: bool = bool(self.options.get("find_emails", True))
        self.require_email: bool = bool(self.options.get("require_email", False))
        self._search_emails_ok = True  # turned off for the run if the search engine blocks us
        # Split the lead target evenly over all searches, so one city can't take every lead.
        self.spread_evenly: bool = bool(self.options.get("spread_evenly", True))
        self._search_target = max_results
        self.city, self.country = "", ""
        # When a search's results run out: country -> cities -> map tiles, until the target is met.
        self.auto_expand: bool = bool(self.options.get("auto_expand", True))
        self._expanded: set[tuple[str, str, str]] = set()
        self.coords: tuple[float, float] | None = None  # set for map-tile searches
        self._tile_label = ""
        self.history = LeadHistory()
        self.leads: list[Lead] = []
        self.skipped = 0
        self._seen: set[tuple[str, str]] = set()
        self._nav_failures = 0  # consecutive pages that could not be loaded at all
        self._pw: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    # ------------------------------------------------------------------ state
    @property
    def query(self) -> str:
        base = f"{self.keyword} in {self.location}" if self.location else self.keyword
        return f"{base} · map area {self._tile_label}" if self.coords else base

    @property
    def stopped(self) -> bool:
        return self.stop_event.is_set()

    @property
    def finished(self) -> bool:
        """True when the user pressed Stop or we already have enough leads."""
        return self.stopped or len(self.leads) >= self.max_results

    @property
    def search_full(self) -> bool:
        """True when the current search (one keyword x location) has its share of leads."""
        return self.finished or len(self.leads) >= self._search_target

    def log(self, message: str, level: str = "info") -> None:
        self.emit("log", (level, message))

    def status(self, message: str) -> None:
        self.emit("status", message)

    def website_allowed(self, website: str) -> bool:
        """Does a business with this website pass the user's website filter?"""
        status = classify_website(website)
        if self.website_filter == "no_website":
            return status == WEBSITE_NONE
        if self.website_filter == "no_real_website":
            return status != WEBSITE_REAL
        return True

    def skip(self, name: str, reason: str) -> None:
        self.skipped += 1
        self.log(f"Skipped {name or 'listing'} ({reason})", "skip")
        self.emit("skipped", self.skipped)

    async def add_lead(self, lead: Lead) -> bool:
        """Filter, de-duplicate, look up the email, then store a lead. True if it was added.

        The cheap checks run first so the (slower) email lookup only happens for leads
        that will actually be kept.
        """
        if not lead.name or self.search_full:
            return False
        lead.website_status = classify_website(lead.website)
        lead.search_query = lead.search_query or self.query
        lead.city = lead.city or self.city
        lead.country = lead.country or self.country
        if not self.website_allowed(lead.website):
            self.skip(lead.name, lead.website_status.lower())
            return False
        if self.require_phone and not lead.phone:
            self.skip(lead.name, "no phone")
            return False
        key = lead.key()
        if key in self._seen:
            return False
        self._seen.add(key)
        if self.skip_known and self.history.has_lead(lead):
            self.skip(lead.name, "already collected in an earlier run")
            return False

        if self.find_emails and not lead.email and self.context:
            await self.lookup_email(lead)
            if self.search_full:  # other tabs filled the target while this lookup was running
                return False
        if self.require_email and not lead.email:
            self.skip(lead.name, "no email found")
            return False

        self.history.add(lead)
        self.leads.append(lead)
        self.emit("lead", lead)
        self.emit("progress", (len(self.leads), self.max_results))
        self.log(f"[{len(self.leads)}] {lead.name} | {lead.phone or 'no phone'} | "
                 f"{lead.email or 'no email'} | {lead.website or 'no website'}")
        return True

    async def lookup_email(self, lead: Lead) -> None:
        """Listings never show emails: try the business's own website, then a web search
        (business directories often list the owner's email - this is how businesses
        WITHOUT a website still get one)."""
        if lead.website_status == WEBSITE_REAL:
            self.status(f"Looking for an email on {lead.website[:60]}...")
            lead.email = ", ".join(await find_emails(self.context.request, lead.website))
        if lead.email or not self._search_emails_ok:
            return
        self.status(f"Searching the web for {lead.name}'s email...")
        try:
            lead.email = ", ".join(await search_business_email(self.context.request, lead.name, self.location))
        except SearchBlocked as exc:
            self._search_emails_ok = False  # don't hammer a search engine that is blocking us
            self.log(f"Email web search paused for this run ({exc}). Website emails still work.", "warning")

    # -------------------------------------------------------------- lifecycle
    async def run(self) -> list[Lead]:
        """Open the session, scrape every keyword x location search, always close the session."""
        queue = deque(SearchItem(k, loc) for k in self.keywords for loc in self.locations)
        self.log(f"Starting {self.SOURCE}: {len(queue)} search(es), target {self.max_results} leads")
        aborted = False
        number = 0
        try:
            await self.open()
            while queue and not self.finished:
                item = queue.popleft()
                if item.target is not None and len(self.leads) >= item.target:
                    continue  # this expansion group already delivered what was missing
                number += 1
                self.keyword, self.location, self.coords = item.keyword, item.location, item.coords
                self._tile_label = item.tile
                self.city, self.country = parse_location(self.location)
                if item.target is not None:
                    self._search_target = min(item.target, self.max_results)
                elif self.spread_evenly:
                    # Share what is still needed over the user's searches that are left, so a
                    # search that comes up short hands its unused share to the next ones.
                    searches_left = 1 + sum(1 for queued in queue if queued.target is None)
                    remaining = self.max_results - len(self.leads)
                    self._search_target = len(self.leads) + -(-remaining // searches_left)
                else:
                    self._search_target = self.max_results
                left = self._search_target - len(self.leads)
                self.log(f"=== Search {number} ({len(queue)} queued): '{self.query}' (up to {left} leads) ===")
                await self.scrape(self.context, self.page)

                if self.auto_expand and not self.finished and len(self.leads) < self._search_target:
                    # The results list ran out before this search got its leads: keep going with
                    # the cities of a country, or the map tiles of a city.
                    expansions = await self.expand(item, self._search_target)
                    queue.extendleft(reversed(expansions))
                if queue and not self.finished:
                    await self.human_delay(*self.SEARCH_PAUSE)
        except ScrapeAborted as exc:
            aborted = True
            self.log(str(exc), "warning")
        except PlaywrightError as exc:
            if not is_browser_closed(exc):
                raise
            # The Chromium window was closed (by hand or by a crash): end cleanly, keep the leads.
            aborted = True
            self.log(BROWSER_CLOSED_MESSAGE, "warning")
        finally:
            await self.close()

        summary = f"{len(self.leads)} leads collected, {self.skipped} skipped (filters or already collected)."
        if self.stopped:
            self.log(f"Stopped by user. {summary}", "warning")
        elif aborted:
            self.log(f"{self.SOURCE} run ended early. {summary}", "warning")
        else:
            self.log(f"Finished {self.SOURCE}: {summary}", "success")
        return self.leads

    async def expand(self, item: SearchItem, target: int) -> list[SearchItem]:
        """Follow-up searches for a search whose results ran out:
        country -> its cities; city -> map grid tiles around the city centre."""
        if item.level == "tile":
            return []
        city, country = parse_location(item.location)
        missing = target - len(self.leads)
        if not city and country in COUNTRIES and item.level == "top":
            cities = [f"{name}, {country}" for name in COUNTRIES[country]]
            self.log(f"'{item.location}' ran out with {missing} leads still needed - searching its "
                     f"{len(cities)} cities one by one.", "success")
            return [SearchItem(item.keyword, loc, target=target, level="city") for loc in cities]
        if not city:
            return []
        group = (item.keyword.lower(), city.lower(), country.lower())
        if group in self._expanded:
            return []
        self._expanded.add(group)
        place = f"{city}, {country}" if country else city
        point = await asyncio.to_thread(geocode, place)
        if not point:
            self.log(f"Could not find {place} on the map, so it can't be searched area by area.", "warning")
            return []
        tiles = spiral_tiles(*point)
        self.log(f"{city} ran out with {missing} leads still needed - now searching the map area by area "
                 f"({len(tiles)} map tiles, centre first). Places already checked are skipped instantly.",
                 "success")
        return [SearchItem(item.keyword, item.location, coords=(lat, lng), target=target, level="tile",
                           tile=f"{index}/{len(tiles)}") for index, (lat, lng) in enumerate(tiles, start=1)]

    async def open(self) -> None:
        """Start Chromium with this site's saved profile (cookies survive between runs).

        Keeping the profile means a CAPTCHA you solve once stays solved for later runs,
        instead of every run starting as a brand-new, unknown browser.
        """
        self.status(f"Launching browser for {self.SOURCE}...")
        self._pw = await async_playwright().start()
        profile_dir = PROFILES_DIR / self.PROFILE
        profile_dir.mkdir(parents=True, exist_ok=True)
        launch_args: dict[str, Any] = {
            "headless": self.headless,
            "locale": "en-US",
            "viewport": {"width": 1366, "height": 768},
        }
        if self.headless:
            # Headless Chromium advertises "HeadlessChrome" in its user agent, which Google
            # rejects outright. Report the same Chrome version as a normal desktop build.
            probe = await self._pw.chromium.launch(headless=True)
            major = probe.version.split(".")[0]
            await probe.close()
            launch_args["user_agent"] = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
            )
        try:
            self.context = await self._pw.chromium.launch_persistent_context(str(profile_dir), **launch_args)
        except PlaywrightError as exc:
            if "ProcessSingleton" in str(exc) or "user data directory is already in use" in str(exc):
                raise ScrapeAborted("The scraper's browser profile is still open. Close that browser window and try again.")
            raise
        self.context.set_default_timeout(15_000)
        # Speed: photos, map tiles and web fonts are never needed for text data. Only these URLs
        # are intercepted (everything else bypasses Python), and CAPTCHA images are not touched.
        await self.context.route(HEAVY_RESOURCES_RE, lambda route: route.continue_()
                                 if "captcha" in route.request.url else route.abort())
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

    async def close(self) -> None:
        try:
            if self.context:
                await self.context.close()
        except PlaywrightError:
            pass
        try:
            if self._pw:
                await self._pw.stop()
        except PlaywrightError:
            pass

    @abstractmethod
    async def scrape(self, context: BrowserContext, page: Page) -> None:
        """Collect leads for the current self.query with self.add_lead() until self.finished."""

    # ------------------------------------------------------------ human pace
    async def human_delay(self, low: float = 1.2, high: float = 3.5) -> None:
        """Sleep a random time, in small slices so the Stop button reacts within ~0.25s."""
        remaining = random.uniform(low, high)
        while remaining > 0 and not self.stopped:
            step = min(0.25, remaining)
            await asyncio.sleep(step)
            remaining -= step

    async def human_scroll(self, page: Page, steps: tuple[int, int] = (3, 6)) -> None:
        """Mouse-wheel scroll in uneven increments, like a person skimming a page."""
        for _ in range(random.randint(*steps)):
            if self.stopped:
                return
            await page.mouse.wheel(0, random.randint(250, 650))
            await asyncio.sleep(random.uniform(0.15, 0.5))

    # -------------------------------------------------------------- navigation
    async def goto(self, page: Page, url: str, attempts: int = 3) -> bool:
        """Navigate with retries, then deal with consent and CAPTCHA pages. False on failure.

        If several pages in a row cannot be reached at all, the site is refusing this
        connection (rate limit / network block), so the run stops instead of failing every page.
        """
        for attempt in range(1, attempts + 1):
            if self.stopped:
                return False
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                self._nav_failures = 0
                await self.handle_consent(page)
                await self.check_blocked(page)
                return True
            except ScrapeAborted:
                raise
            except PlaywrightError as exc:
                if is_browser_closed(exc):
                    raise ScrapeAborted(BROWSER_CLOSED_MESSAGE) from exc
                self.log(f"Navigation failed (attempt {attempt}/{attempts}): {str(exc).splitlines()[0]}", "warning")
                await self.human_delay(4 * attempt, 8 * attempt)  # back off a bit more each time

        self._nav_failures += 1
        if self._nav_failures >= 3:
            raise ScrapeAborted(
                f"{self.SOURCE} is not reachable from this connection (pages keep timing out or being reset). "
                "The site is probably rate-limiting your IP. Wait a few hours or try another network."
            )
        return False

    async def handle_consent(self, page: Page) -> None:
        """Dismiss Google's EU cookie consent interstitial if it appears."""
        if "consent." not in page.url:
            return
        for label in ("Accept all", "Reject all", "I agree"):
            button = page.get_by_role("button", name=label).first
            try:
                if await button.count():
                    await button.click()
                    await page.wait_for_load_state("domcontentloaded")
                    self.log("Accepted Google consent dialog.")
                    return
            except PlaywrightError:
                continue

    async def is_blocked(self, page: Page) -> bool:
        url = page.url.lower()
        if any(marker in url for marker in _BLOCK_URL_MARKERS):
            return True
        try:
            for selector in _BLOCK_SELECTORS:
                if await page.locator(selector).count():
                    return True
        except PlaywrightError:
            pass  # page navigated mid-check; treat as not blocked
        return False

    async def is_hard_blocked(self, page: Page) -> bool:
        """'You have been blocked' pages (no puzzle to solve), including inside the DataDome iframe."""
        try:
            for frame in page.frames:
                if await frame.get_by_text(_HARD_BLOCK_RE).count():
                    return True
        except PlaywrightError:
            pass
        return False

    async def raise_if_hard_blocked(self, page: Page) -> None:
        if await self.is_hard_blocked(page):
            raise ScrapeAborted(
                f"{self.SOURCE} has blocked this IP address (no CAPTCHA offered). "
                "Scraping cannot continue from this connection right now - wait several hours or use another network."
            )

    async def check_blocked(self, page: Page) -> None:
        """If a CAPTCHA is showing, let the user solve it (visible mode) or abort (headless)."""
        if not await self.is_blocked(page):
            return
        await self.raise_if_hard_blocked(page)
        if self.headless:
            raise ScrapeAborted(
                f"{self.SOURCE} is showing a CAPTCHA / bot check. "
                "Turn off 'Run headless' and start again so you can solve it in the browser window."
            )
        self.log("CAPTCHA detected - please solve it in the browser window (waiting up to 2 minutes)...", "warning")
        self.status("Waiting for CAPTCHA to be solved...")
        for _ in range(240):
            if self.stopped:
                raise ScrapeAborted("Stopped while waiting for CAPTCHA.")
            await asyncio.sleep(0.5)
            await self.raise_if_hard_blocked(page)  # a failed puzzle can turn into a hard block
            if not await self.is_blocked(page):
                self.log("CAPTCHA cleared, continuing.", "success")
                await self.human_delay(1.5, 3)
                return
        raise ScrapeAborted("CAPTCHA was not solved within 2 minutes; stopping.")

    # ------------------------------------------------------------- safe DOM
    async def safe_text(
        self,
        root: Page | Locator,
        selectors: str | Iterable[str],
        attr: str | None = None,
        timeout: int = 1500,
    ) -> str:
        """Return text (or an attribute) of the first selector that matches, or "".

        Never raises: missing elements, detached nodes and timeouts all yield "".
        """
        if isinstance(selectors, str):
            selectors = (selectors,)
        for selector in selectors:
            try:
                locator = root.locator(selector).first
                if not await locator.count():
                    continue
                if attr:
                    value = await locator.get_attribute(attr, timeout=timeout)
                else:
                    value = await locator.inner_text(timeout=timeout)
                value = clean_text(value)
                if value:
                    return value
            except PlaywrightError:
                continue
        return ""

    async def read_json_ld(self, page: Page) -> list[dict[str, Any]]:
        """Parse every <script type="application/ld+json"> block on the page (schema.org data)."""
        items: list[dict[str, Any]] = []
        try:
            raw_blocks = await page.locator('script[type="application/ld+json"]').all_inner_texts()
        except PlaywrightError:
            return items
        for raw in raw_blocks:
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            stack = data if isinstance(data, list) else [data]
            while stack:
                item = stack.pop()
                if isinstance(item, dict):
                    items.append(item)
                    stack.extend(v for v in item.get("@graph", []) if isinstance(v, dict))
                elif isinstance(item, list):
                    stack.extend(item)
        return items
