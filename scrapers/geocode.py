"""Reverse-geocode lat/lng via Nominatim (OpenStreetMap). Free, no API key."""
import asyncio
import json
import urllib.parse
import urllib.request


_cache: dict[tuple[float, float], str] = {}


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
    short = _format_thai(data.get("address", {}))
    return short or data.get("display_name", "")


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
    rounded position hasn't moved since the previous scrape."""
    n = 0
    for lat, lng, addr in rows:
        if lat and lng and addr:
            _cache[(round(lat, 4), round(lng, 4))] = addr
            n += 1
    return n
