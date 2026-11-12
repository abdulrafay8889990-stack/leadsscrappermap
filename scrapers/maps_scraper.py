"""Google Maps scraper.

1. Opens the Maps search for "<keyword> in <location>" (or the keyword at a map position).
2. Scrolls the left results sidebar (an infinite-scroll feed) to collect place URLs.
3. Opens the places in several tabs at once (default 3) and reads name, phone, website,
   address, rating, review count and category from each details panel in one call.
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import quote_plus

from playwright.async_api import BrowserContext, Page
from playwright.async_api import Error as PlaywrightError

from core.geo import TILE_ZOOM
from core.history import place_id
from core.models import Lead
from scrapers.base import BaseScraper, clean_text, digits_only, find_phone, is_browser_closed

# Google changes class names often; data-item-id / aria attributes are the most stable hooks.
# Update this dict if extraction starts returning blanks.
SELECTORS = {
    "feed": 'div[role="feed"]',
    "place_link": 'div[role="feed"] a[href*="/maps/place/"]',
    "end_of_list": re.compile(r"reached the end of the list", re.I),
    "name": ("h1.DUwDvf", 'div[role="main"] h1', "h1"),
    "rating": ('div.F7nice span[aria-hidden="true"]', 'span[role="img"][aria-label*="star"]'),
    "reviews": ('div.F7nice span[aria-label*="review"]', 'button[aria-label*="review"]'),
    "address": 'button[data-item-id="address"]',
    "website": 'a[data-item-id="authority"]',
    "phone": 'button[data-item-id^="phone:tel:"]',
    "category": ("button.DkEaL", 'button[jsaction*="category"]'),
    # any of the info rows (address / phone / website): shows the details panel has rendered
    "info_rows": 'button[data-item-id="address"], button[data-item-id^="phone:tel:"], a[data-item-id="authority"]',
}

DEFAULT_TABS = 3  # places opened at the same time
MAX_TABS = 4  # more tabs got slower in tests (CPU + network contention)

# Runs in the page: for every place link in the feed, return its URL, name and the
# href of the card's "Website" button (null if the card has none we can see).
CARD_JS = """els => els.map(a => {
    const card = a.parentElement;  // the result card (link + rating + buttons)
    const site = card ? card.querySelector('a[data-value="Website"], a[aria-label*="website" i]') : null;
    return {href: a.href, name: a.getAttribute('aria-label') || '', website: site ? site.href : null};
})"""

# Runs in the place page: read every field in one call. `sel` maps field -> list of selectors.
EXTRACT_FIELDS = ("name", "rating", "reviews", "address", "website", "phone", "category")
EXTRACT_JS = """sel => {
    const read = (list, attr) => {
        for (const s of list) {
            const el = document.querySelector(s);
            if (!el) continue;
            const value = attr ? el.getAttribute(attr) : el.innerText;
            if (value && value.trim()) return value;
        }
        return "";
    };
    return {
        name: read(sel.name), rating: read(sel.rating),
        reviews_label: read(sel.reviews, "aria-label"), reviews_text: read(sel.reviews),
        address: read(sel.address, "aria-label"), website: read(sel.website, "href"),
        phone: read(sel.phone, "aria-label"), phone_id: read(sel.phone, "data-item-id"),
        category: read(sel.category),
    };
}"""

_LABEL_PREFIX_RE = re.compile(r"^\s*(Address|Phone|Website|Open website)\s*:\s*", re.I)


class MapsScraper(BaseScraper):
    SOURCE = "Google Maps"
    PROFILE = "google"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Places are opened in several tabs at once (with their email lookups running alongside).
        self.parallel_tabs = max(1, min(int(self.options.get("parallel_tabs", DEFAULT_TABS)), MAX_TABS))
        self._detail_pages: list[Page] = []
        self._visited: set[str] = set()  # place ids already seen, across all searches

    async def scrape(self, context: BrowserContext, page: Page) -> None:
        if self.coords:  # map-tile search: the keyword at a map position (zoom 14 view)
            lat, lng = self.coords
            url = f"https://www.google.com/maps/search/{quote_plus(self.keyword)}/@{lat},{lng},{TILE_ZOOM}z?hl=en"
        else:
            url = f"https://www.google.com/maps/search/{quote_plus(self.keyword + ' in ' + self.location)}?hl=en"
        self.status("Opening Google Maps...")
        self.log("Opening Google Maps search...")
        if not await self.goto(page, url):
            self.log("Could not open Google Maps.", "error")
            return

        self._detail_pages = [p for p in self._detail_pages if not p.is_closed()]
        while len(self._detail_pages) < self.parallel_tabs:
            self._detail_pages.append(await context.new_page())

        await self.process_places(page, self._detail_pages)
        if not self.search_full:
            self.log("No more new listings for this search.")

    async def process_places(self, feed_page: Page, pages: list[Page]) -> None:
        """A pipeline that runs until the target is reached or the results list is used up:

        * one task scrolls the results list and queues new places (a few ahead of the tabs);
        * every tab opens the next queued place as soon as it is free;
        * filtering + the email lookup of a place (add_lead) run in the background, so a tab
          moves on to the next place straight away instead of waiting for the lookup.
        """
        queue: list[tuple[int, str]] = []
        found = 0
        listing_done = False
        new_places = asyncio.Event()
        lookups: set[asyncio.Task] = set()
        lookup_slots = asyncio.Semaphore(len(pages) * 2)  # don't flood websites / web search
        buffer = len(pages) * 3

        async def collector() -> None:
            nonlocal found, listing_done
            exhausted = False
            try:
                while not self.search_full and not exhausted:
                    if len(queue) >= buffer:  # enough queued; scrolling further may be wasted
                        await asyncio.sleep(0.3)
                        continue
                    urls, exhausted = await self.collect_place_urls(feed_page, batch=buffer)
                    for url in urls:
                        found += 1
                        queue.append((found, url))
                    new_places.set()
            finally:
                listing_done = True
                new_places.set()

        async def finish(lead: Lead) -> None:
            async with lookup_slots:
                await self.add_lead(lead)

        async def worker(tab: Page) -> None:
            while not self.search_full:
                # Leads still in their lookup may complete the target: don't open more places
                # than are still missing; wait for a lookup to finish and look again.
                while lookups and len(self.leads) + len(lookups) >= self._search_target and not self.search_full:
                    await asyncio.wait(set(lookups), return_when=asyncio.FIRST_COMPLETED)
                if self.search_full:
                    return
                if not queue:
                    if listing_done:
                        return
                    new_places.clear()
                    await new_places.wait()
                    continue
                index, place_url = queue.pop(0)
                self.status(f"Google Maps: listing {index}/{found} | {len(self.leads)}/{self.max_results} leads"
                            f" · {self.city}")
                try:
                    lead = await self.extract_place(tab, place_url)
                except PlaywrightError as exc:
                    if is_browser_closed(exc):
                        raise
                    self.log(f"Listing {index} failed: {str(exc).splitlines()[0]}", "warning")
                    continue
                if lead:
                    task = asyncio.create_task(finish(lead))
                    lookups.add(task)
                    task.add_done_callback(lookups.discard)
                await self.human_delay(0.4, 1.0)

        tasks = [asyncio.create_task(collector())] + [asyncio.create_task(worker(tab)) for tab in pages]
        try:
            await asyncio.gather(*tasks)
            while lookups:  # let the last lookups finish
                await asyncio.gather(*set(lookups))
        except BaseException:
            # One tab failed hard (browser closed, CAPTCHA not solved, Stop): stop everything.
            for task in [*tasks, *lookups]:
                task.cancel()
            await asyncio.gather(*tasks, *lookups, return_exceptions=True)
            raise

    # ------------------------------------------------------------- sidebar
    async def collect_place_urls(self, page: Page, batch: int = 0) -> tuple[list[str], bool]:
        """Scroll the results feed until there are `batch` new candidate places (default: enough
        for the leads still missing).

        Returns (place URLs to open, True if the results list has nothing more to load).
        Places already handled in this run are ignored, so repeated calls continue where
        the previous one stopped. Result cards show a "Website" button when a place has one,
        so places whose website fails the filter are skipped without opening them.
        """
        try:
            await page.wait_for_selector(SELECTORS["feed"], timeout=15_000)
        except PlaywrightError:
            # A very specific query jumps straight to a single place page with no feed.
            ident = place_id(page.url) or page.url
            if "/maps/place/" in page.url and ident not in self._visited:
                self._visited.add(ident)
                self.log("Search opened a single place directly.")
                return [page.url], True
            return [], True

        feed = page.locator(SELECTORS["feed"]).first
        # Some opened places get filtered out later (e.g. no phone), so gather a few extra.
        needed = self._search_target - len(self.leads)
        wanted = batch or int(needed * 1.3) + 5
        urls: list[str] = []
        seen: set[str] = set()
        stale_rounds = 0
        scroll_round = 0
        exhausted = False

        while not self.stopped and len(urls) < wanted:
            scroll_round += 1
            cards = await page.locator(SELECTORS["place_link"]).evaluate_all(CARD_JS)
            new_links = 0
            for card in cards:
                href = card["href"].split("?")[0]
                # The same place can appear under slightly different URLs in different searches.
                ident = place_id(href) or href
                if ident in seen:
                    continue
                seen.add(ident)
                new_links += 1
                if ident in self._visited:
                    continue
                self._visited.add(ident)
                if self.skip_known and self.history.has_place(href):
                    self.skip(card["name"], "already collected in an earlier run")
                    continue
                # card["website"] is None when no Website button was found: check on the details page.
                if card["website"] and not self.website_allowed(card["website"]):
                    self.skip(card["name"], "has website")
                    continue
                urls.append(href)

            if not self.leads:
                self.status(f"Scrolling Google Maps results (round {scroll_round})...")

            if len(urls) >= wanted:
                break
            if await page.get_by_text(SELECTORS["end_of_list"]).count():
                self.log("Reached the end of the Google Maps results list.")
                exhausted = True
                break
            stale_rounds = 0 if new_links else stale_rounds + 1
            if stale_rounds >= 4:
                self.log("No new listings are loading; moving on.")
                exhausted = True
                break

            # Wheel-scroll over the sidebar, then make sure it actually reached the bottom
            # so Maps fires its "load more" request.
            try:
                await feed.hover()
                await self.human_scroll(page, steps=(2, 4))
                await feed.evaluate("el => el.scrollTo(0, el.scrollHeight)")
            except PlaywrightError:
                pass
            await self.human_delay(1.2, 2.6)

        if urls:
            self.log(f"{len(urls)} new listings queued ({len(self._visited)} seen so far)")
        return urls, exhausted

    # -------------------------------------------------------------- details
    async def extract_place(self, page: Page, url: str) -> Lead | None:
        if not await self.goto(page, url):
            return None
        try:
            await page.locator(", ".join(SELECTORS["name"])).first.wait_for(timeout=12_000)
        except PlaywrightError:
            self.log("Place panel did not load; skipping.", "warning")
            return None
        try:  # the address/phone/website rows render just after the name
            await page.locator(SELECTORS["info_rows"]).first.wait_for(timeout=2_500)
        except PlaywrightError:
            pass  # some places have none of them; read what is there
        await self.human_delay(0.1, 0.3)

        # One round-trip for every field instead of one per field.
        try:
            data = await page.evaluate(EXTRACT_JS, {k: list(v) if isinstance(v, tuple) else [v]
                                                    for k, v in SELECTORS.items() if k in EXTRACT_FIELDS})
        except PlaywrightError as exc:
            if is_browser_closed(exc):
                raise
            return None
        data = {key: clean_text(value) for key, value in data.items()}
        rating_match = re.search(r"\d+(?:[.,]\d)?", data["rating"])
        phone = data["phone"] or data["phone_id"].replace("phone:tel:", "")  # "phone:tel:+13125550100"
        return Lead(
            source=self.SOURCE,
            name=data["name"],
            phone=find_phone(phone) or _LABEL_PREFIX_RE.sub("", phone),
            website=data["website"],
            address=_LABEL_PREFIX_RE.sub("", data["address"]),
            rating=rating_match.group(0).replace(",", ".") if rating_match else "",
            review_count=digits_only(data["reviews_label"] or data["reviews_text"]),
            category=data["category"],
            listing_url=page.url,
        )
