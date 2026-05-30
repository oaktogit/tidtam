"""Reverse-geocode lat/lng via Nominatim (OpenStreetMap). Free, no API key.

Output format: "POI name\nต. อ. จ." — UI splits on \n for 2-line display.
Falls back to admin-only line if no nearby POI is found via Overpass.
"""
import asyncio
import json
import math
import urllib.parse
import urllib.request


_cache: dict[tuple[float, float], str] = {}


# Tag categories ranked by how useful the name is as a "where is this car"
# label. Higher score wins. Specific businesses outrank generic structures;
# highway/place are last-resort context (most roadside parking in Thailand
# has no nearby POI tagged in OSM).
_TAG_PRIORITY = {
    "amenity": 6,
    "shop": 6,
    "office": 5,
    "tourism": 5,
    "industrial": 4,
    "craft": 4,
    "healthcare": 4,
    "leisure": 3,
    "landuse": 2,
    "building": 1,
    "highway": 1,
    "place": 1,
}


def _prefix(value: str, prefix: str, *strip_words: str) -> str:
    v = value.strip()
    for w in strip_words:
        if v.startswith(w):
            v = v[len(w):].strip()
            break
    return prefix + v


def _format_thai(addr: dict) -> str:
    parts: list[str] = []

    tambon = (
        addr.get("suburb")
        or addr.get("village")
        or addr.get("neighbourhood")
        or addr.get("hamlet")
        or addr.get("town")
    )
    if tambon:
        parts.append(_prefix(tambon, "ต.", "ต.", "ตำบล", "แขวง"))

    amphoe = (
        addr.get("city_district")
        or addr.get("district")
        or addr.get("county")
    )
    if amphoe:
        parts.append(_prefix(amphoe, "อ.", "อ.", "อำเภอ", "เขต"))

    province = (
        addr.get("province")
        or addr.get("state")
        or addr.get("city")
    )
    if province:
        parts.append(_prefix(province, "จ.", "จ.", "จังหวัด"))

    return " ".join(parts)


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _fetch_overpass_poi(lat: float, lng: float, radius_m: int = 150) -> str:
    """Return the name of the most prominent named OSM feature within
    `radius_m` of (lat, lng), preferring Thai names. Empty string if none.
    """
    query = (
        "[out:json][timeout:5];"
        f"nwr(around:{radius_m},{lat:.6f},{lng:.6f})[name];"
        "out center 25;"
    )
    data = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=data,
        headers={"User-Agent": "TidtamGPS/1.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        result = json.loads(r.read())

    best_score = (-1, 0.0)  # (priority, -distance)
    best_name = ""
    for el in result.get("elements", []):
        tags = el.get("tags", {})
        priority = max(
            (_TAG_PRIORITY[k] for k in _TAG_PRIORITY if k in tags),
            default=0,
        )
        if priority == 0:
            continue
        # building=yes is generic; only keep it if nothing better exists
        if tags.get("building") == "yes" and priority == 1:
            priority = 0.5
        el_lat = el.get("lat") or el.get("center", {}).get("lat")
        el_lng = el.get("lon") or el.get("center", {}).get("lon")
        if el_lat is None or el_lng is None:
            continue
        dist = _haversine_m(lat, lng, el_lat, el_lng)
        score = (priority, -dist)
        if score > best_score:
            best_score = score
            best_name = tags.get("name:th") or tags.get("name", "")
    return best_name


def _fetch_sync(lat: float, lng: float) -> str:
    qs = urllib.parse.urlencode({
        "format": "json",
        "lat": f"{lat:.6f}",
        "lon": f"{lng:.6f}",
        "zoom": "14",
        "accept-language": "th",
        "addressdetails": "1",
    })
    url = "https://nominatim.openstreetmap.org/reverse?" + qs
    req = urllib.request.Request(url, headers={"User-Agent": "TidtamGPS/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
    admin = _format_thai(data.get("address", {})) or data.get("display_name", "")

    try:
        poi = _fetch_overpass_poi(lat, lng)
    except Exception:
        poi = ""

    if poi and admin:
        return f"{poi}\n{admin}"
    return poi or admin


async def reverse_geocode(lat: float, lng: float) -> str:
    if not lat or not lng:
        return ""
    key = (round(lat, 4), round(lng, 4))  # ~11m precision
    if key in _cache:
        return _cache[key]
    try:
        addr = await asyncio.to_thread(_fetch_sync, lat, lng)
    except Exception:
        addr = ""
    _cache[key] = addr
    return addr


def warm_cache_from(rows) -> int:
    """Pre-populate _cache from an iterable of (lat, lng, address) tuples.
    Saves serial Nominatim calls (rate-limited 1 req/s) for vehicles whose
    rounded position hasn't moved since the previous scrape.

    Only warms entries already in 2-line "POI\\nadmin" format — pre-POI
    addresses are skipped so the next scrape re-fetches them through the
    new Overpass path."""
    n = 0
    for lat, lng, addr in rows:
        if lat and lng and addr and "\n" in addr:
            _cache[(round(lat, 4), round(lng, 4))] = addr
            n += 1
    return n
