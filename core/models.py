"""Lead data model shared by every scraper, the GUI and the exporter."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, fields
from urllib.parse import urlparse

# Links that are a social profile / link page rather than the business's own website.
SOCIAL_DOMAINS = (
    "facebook.com", "fb.com", "fb.me", "instagram.com", "instagr.am", "wa.me", "whatsapp.com",
    "tiktok.com", "twitter.com", "x.com", "linkedin.com", "youtube.com", "pinterest.com",
    "linktr.ee", "linkin.bio", "beacons.ai", "foodpanda.pk", "foodpanda.com", "ubereats.com",
    "doordash.com", "grubhub.com", "yelp.com", "business.site", "sites.google.com",
    "g.page", "goo.gl", "maps.app.goo.gl",
)

WEBSITE_NONE = "No website"
WEBSITE_SOCIAL = "Social only"
WEBSITE_REAL = "Has website"


def classify_website(url: str) -> str:
    """'' -> No website, facebook/instagram/etc. -> Social only, anything else -> Has website."""
    url = (url or "").strip()
    if not url:
        return WEBSITE_NONE
    host = urlparse(url if "://" in url else f"http://{url}").netloc.lower().split(":")[0]
    host = host.removeprefix("www.").removeprefix("m.")
    if any(host == domain or host.endswith("." + domain) for domain in SOCIAL_DOMAINS):
        return WEBSITE_SOCIAL
    return WEBSITE_REAL


@dataclass
class Lead:
    """One business lead. Every field is a plain string so missing data is simply ""."""

    source: str
    name: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    website_status: str = ""
    address: str = ""
    city: str = ""
    country: str = ""
    rating: str = ""
    review_count: str = ""
    category: str = ""
    search_query: str = ""
    listing_url: str = ""

    def key(self) -> tuple[str, str]:
        """Normalized identity used to drop duplicates (same name + same phone/address/URL)."""
        name = re.sub(r"\W+", "", self.name.lower())
        phone = re.sub(r"\D+", "", self.phone)
        address = re.sub(r"\W+", "", self.address.lower())
        return name, phone or address or self.listing_url.lower()

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


# Column order used by the results table and the exported files.
COLUMNS: list[str] = [f.name for f in fields(Lead)]

COLUMN_TITLES: dict[str, str] = {
    "source": "Source",
    "name": "Business Name",
    "phone": "Phone",
    "email": "Email",
    "website": "Website",
    "website_status": "Website Status",
    "address": "Address",
    "city": "City",
    "country": "Country",
    "rating": "Rating",
    "review_count": "Reviews",
    "category": "Category",
    "search_query": "Search Query",
    "listing_url": "Listing URL",
}
