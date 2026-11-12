"""Find a business's public contact email.

Google Maps / Search listings never include email addresses, so two lookups are used:

1. find_emails(): for leads with a real website - fetch the homepage (plus up to a few
   contact/about pages) and pull out mailto: links, plain-text addresses (also HTML-entity /
   %40 encoded) and Cloudflare-protected addresses.
2. search_business_email(): for leads WITHOUT a website (or when the site shows none) -
   one web search for '"Business Name" City email'. Business directories (hamariweb, cybo,
   eatoye, ...) often list the owner's email in their snippets. An address is only accepted
   from a result that names the business, and a directory's own address is rejected.

Only raw HTML is downloaded (no page rendering), so both are quick.
"""
from __future__ import annotations

import asyncio
import html
import re
from urllib.parse import quote_plus, unquote, urljoin, urlparse

from playwright.async_api import APIRequestContext
from playwright.async_api import Error as PlaywrightError

from core.locations import city_names, parse_location

EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,24}(?![\w-])")
_CF_EMAIL_RE = re.compile(r'data-cfemail="([0-9a-fA-F]+)"|/cdn-cgi/l/email-protection#([0-9a-fA-F]+)')
_HREF_RE = re.compile(r"""href\s*=\s*["']([^"'#]+)["']""", re.I)
_CONTACT_HINT_RE = re.compile(r"contact|about|reach|get-in-touch|support|impressum", re.I)

# Things that look like emails but are not contact addresses.
_JUNK_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js", ".ico", ".avif")
_JUNK_DOMAINS = (
    "example.com", "example.org", "domain.com", "yourdomain.com", "email.com", "mail.com",
    "sentry.io", "wixpress.com", "sentry-next.wixpress.com", "sentry.wixpress.com",
    "yoursite.com", "website.com", "company.com", "godaddy.com", "schema.org",
)
_JUNK_LOCAL_PARTS = ("user", "username", "name", "email", "your", "yourname", "youremail", "john", "john.doe",
                     "johndoe", "jane", "jane.doe", "janedoe", "test", "example", "someone", "firstname.lastname",
                     "first.last", "noreply", "no-reply", "donotreply")

MAX_PAGES = 4          # homepage + up to 3 contact/about pages
MAX_EMAILS = 3
REQUEST_TIMEOUT_MS = 12_000
WEBSITE_TIMEOUT_MS = 8_000  # business websites: slow ones are rarely worth the wait


def _decode_cfemail(encoded: str) -> str:
    """Cloudflare stores emails XOR-ed with the first byte as key."""
    try:
        key = int(encoded[:2], 16)
        return "".join(chr(int(encoded[i:i + 2], 16) ^ key) for i in range(2, len(encoded), 2))
    except ValueError:
        return ""


def extract_emails(page_html: str) -> list[str]:
    """All plausible contact emails in a page, in order of appearance, de-duplicated."""
    text = unquote(html.unescape(page_html or ""))
    found = [m.group(0) for m in EMAIL_RE.finditer(text)]
    for match in _CF_EMAIL_RE.finditer(page_html or ""):
        found.append(_decode_cfemail(match.group(1) or match.group(2)))

    emails: list[str] = []
    for email in found:
        email = email.strip(".").lower()
        local, _, domain = email.partition("@")
        if not domain or email.endswith(_JUNK_SUFFIXES) or local in _JUNK_LOCAL_PARTS:
            continue
        if any(domain == junk or domain.endswith("." + junk) for junk in _JUNK_DOMAINS):
            continue
        if re.search(r"@\d+x\.", email):  # retina image names like logo@2x.png
            continue
        if email not in emails:
            emails.append(email)
    return emails


def _contact_links(page_html: str, base_url: str) -> list[str]:
    """Same-site links that look like contact/about pages."""
    site = urlparse(base_url).netloc.lower().removeprefix("www.")
    links: list[str] = []
    for href in _HREF_RE.findall(page_html or ""):
        if not _CONTACT_HINT_RE.search(href):
            continue
        url = urljoin(base_url, href)
        host = urlparse(url).netloc.lower().removeprefix("www.")
        if url.startswith("http") and host == site and url not in links:
            links.append(url)
    return links


def _rank(emails: list[str], website: str) -> list[str]:
    """Keep only emails on the business's own domain (info@theirsite.com) when there are any.

    Otherwise return everything found (small businesses often use gmail etc.). This drops
    addresses of web agencies / partners that also appear on the page.
    """
    return _own_domain(emails, website) or emails


def _own_domain(emails: list[str], website: str) -> list[str]:
    site = urlparse(website).netloc.lower().removeprefix("www.")
    return [e for e in emails if site and (e.endswith("@" + site) or e.endswith("." + site))]


async def _fetch(request: APIRequestContext, url: str, timeout: int = REQUEST_TIMEOUT_MS) -> str:
    try:
        response = await request.get(url, timeout=timeout, fail_on_status_code=False)
        if not response.ok or "html" not in response.headers.get("content-type", "html"):
            return ""
        return await response.text()
    except (PlaywrightError, UnicodeDecodeError):
        return ""


SEARCH_URL = "https://www.bing.com/search?q={query}&setlang=en"
LITE_PAGE_BYTES = 200_000
_RESULT_SPLIT_RE = re.compile(r'<li class="b_algo"')
_RESULT_URL_RE = re.compile(r'<cite[^>]*>(.*?)</cite>', re.S)
FREE_MAIL = ("gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "live.com", "icloud.com", "aol.com",
             "ymail.com", "proton.me", "protonmail.com", "msn.com", "yahoo.co.uk", "gmx.com", "zoho.com")
# Words that say nothing about which business it is.
_GENERIC_WORDS = {
    "the", "and", "of", "cafe", "café", "coffee", "restaurant", "restaurants", "bakery", "bakers", "shop", "store",
    "salon", "studio", "center", "centre", "house", "point", "co", "pvt", "ltd", "llc", "inc", "company",
    "services", "service", "branch", "official", "new", "best",
}
# City names inside business names ("Cafe Karachi", "Pizza London") don't identify the business.
_CITY_WORDS = {word for city in city_names() for word in re.findall(r"[a-z0-9]+", city)}


class SearchBlocked(Exception):
    """The search engine answered with a CAPTCHA / block page."""


def _significant_words(name: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", name.lower())
    return [w for w in words if w not in _GENERIC_WORDS and w not in _CITY_WORDS and len(w) > 1]


def _result_blocks(page_html: str) -> list[tuple[str, str]]:
    """Bing result page -> [(result host, plain text of the result)]."""
    blocks = []
    for part in _RESULT_SPLIT_RE.split(page_html)[1:]:
        cite = _RESULT_URL_RE.search(part)
        host_text = html.unescape(re.sub(r"<[^>]+>", "", cite.group(1))) if cite else ""
        host = urlparse(host_text if "://" in host_text else "https://" + host_text).netloc.lower()
        text = html.unescape(re.sub(r"<[^>]+>", " ", part))
        blocks.append((host.removeprefix("www."), re.sub(r"\s+", " ", text)))
    return blocks


def pick_business_emails(page_html: str, name: str) -> list[str]:
    """Emails from search results that are about this business, most frequent first."""
    words = _significant_words(name) or re.findall(r"[a-z0-9]+", name.lower())
    initials = "".join(w[0] for w in re.findall(r"[a-z0-9]+", name.lower()) if w != "the")
    votes: dict[str, int] = {}
    for host, text in _result_blocks(page_html):
        names_business = all(re.search(rf"\b{re.escape(w)}\b", text, re.I) for w in words)
        name_positions = [m.start() for m in re.finditer(rf"\b{re.escape(words[0])}\b", text, re.I)] if words else []
        lowered = text.lower()
        for email in extract_emails(text):
            domain = email.split("@")[1]
            if host and (domain == host or host.endswith("." + domain) or domain.endswith("." + host)):
                continue  # the directory's own address (info@tripako.com on tripako.com)
            local = email.split("@")[0]
            name_in_email = any(len(w) >= 3 and (w in local or w in domain) for w in words) or (
                len(initials) >= 2 and local.startswith(initials))
            # On list pages with many businesses, only trust an address written near the name.
            position = lowered.find(email)
            near_name = any(abs(position - p) <= 250 for p in name_positions) if position >= 0 else False
            if name_in_email or (names_business and near_name and domain in FREE_MAIL):
                votes[email] = votes.get(email, 0) + (2 if name_in_email else 1)
    return sorted(votes, key=votes.get, reverse=True)


async def search_business_email(request: APIRequestContext, name: str, location: str) -> list[str]:
    """One web search for the business's email. Raises SearchBlocked on a CAPTCHA page."""
    if not name:
        return []
    city = parse_location(location)[0] if location else ""
    query = f'"{name}" {city} email'.strip()
    for _attempt in range(3):
        try:
            response = await request.get(SEARCH_URL.format(query=quote_plus(query)), timeout=REQUEST_TIMEOUT_MS,
                                         fail_on_status_code=False)
            page = await response.text()
        except (PlaywrightError, UnicodeDecodeError):
            return []
        if response.status in (403, 429) or ("b_algo" not in page and "captcha" in page.lower()):
            raise SearchBlocked(f"web search returned HTTP {response.status} / CAPTCHA")
        emails = pick_business_emails(page, name)
        # Bing randomly serves a "lite" page (~120 KB) without the rich directory snippets
        # that usually hold the email; only a full page is a reliable "no email" answer.
        if emails or len(page) >= LITE_PAGE_BYTES:
            return emails[:2]
    return []


async def find_emails(request: APIRequestContext, website: str) -> list[str]:
    """Visit a website's homepage and contact pages; return up to MAX_EMAILS emails."""
    if not website:
        return []
    if "://" not in website:
        website = "http://" + website

    homepage = await _fetch(request, website, WEBSITE_TIMEOUT_MS)
    emails = extract_emails(homepage)
    # An address on the business's own domain in the homepage (usually the footer) is the best
    # answer already; only otherwise look at the contact/about pages - all at the same time.
    own = _own_domain(emails, website)
    if own:
        return own[:MAX_EMAILS]

    candidates = _contact_links(homepage, website)
    if not candidates and homepage:
        candidates = [urljoin(website, path) for path in ("/contact", "/contact-us")]
    pages = await asyncio.gather(*(_fetch(request, url, WEBSITE_TIMEOUT_MS) for url in candidates[:MAX_PAGES - 1]))
    for page in pages:
        for email in extract_emails(page):
            if email not in emails:
                emails.append(email)

    return _rank(emails, website)[:MAX_EMAILS]
