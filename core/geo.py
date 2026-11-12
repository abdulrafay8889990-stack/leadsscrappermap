"""Geocoding + map grid, so a city can be searched tile by tile.

Google Maps returns at most ~120 places for one search. Searching the same keyword at many
map positions ("dentist" @lat,lng,14z) returns different places each time, so a city can be
covered completely. Tiles spiral outwards from the city centre, so the busiest parts come first.

City centres come from OpenStreetMap's Nominatim geocoder (free; max 1 request/second and a
real User-Agent are required by its usage policy - we make one request per city).
"""
from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "LeadScraperDesktop/1.0 (business lead research tool)"
TILE_ZOOM = 14
# Size of one zoom-14 Google Maps view in a 1366x768 window, a bit smaller so tiles overlap.
TILE_LNG_DEG = 0.10
TILE_LAT_DEG = 0.055

_cache: dict[str, tuple[float, float, float] | None] = {}
_last_request = 0.0


def geocode(place: str) -> tuple[float, float, float] | None:
    """'Muscat, Oman' -> (lat, lng, size_deg) or None. size_deg = larger side of the bounding box."""
    global _last_request
    key = place.strip().lower()
    if key in _cache:
        return _cache[key]
    wait = 1.1 - (time.time() - _last_request)  # Nominatim: at most one request per second
    if wait > 0:
        time.sleep(wait)
    _last_request = time.time()
    url = NOMINATIM_URL + "?" + urllib.parse.urlencode({"q": place, "format": "json", "limit": 1})
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            results = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None  # not cached: try again next time
    if not results:
        _cache[key] = None
        return None
    top = results[0]
    south, north, west, east = map(float, top["boundingbox"])
    result = (float(top["lat"]), float(top["lon"]), max(north - south, east - west))
    _cache[key] = result
    return result


def spiral_tiles(lat: float, lng: float, size_deg: float = 0.0, min_rings: int = 4, max_rings: int = 9):
    """Tile centres in square rings around (lat, lng): ring 0 = centre, ring 1 = the 8 around it, ...

    The number of rings follows the city's size (at least `min_rings`, so cities whose
    geocoded box is only the old town still get their suburbs)."""
    rings = max(min_rings, min(max_rings, math.ceil(size_deg / (2 * TILE_LAT_DEG)) + 1))
    lng_step = TILE_LNG_DEG
    tiles = [(round(lat, 5), round(lng, 5))]
    for ring in range(1, rings + 1):
        for dx in range(-ring, ring + 1):
            for dy in range(-ring, ring + 1):
                if max(abs(dx), abs(dy)) == ring:
                    tiles.append((round(lat + dy * TILE_LAT_DEG, 5), round(lng + dx * lng_step, 5)))
    return tiles
