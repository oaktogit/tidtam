import asyncio
import json as json_lib
import re
import urllib.request
from playwright.async_api import Page
from scrapers.base import BaseScraper
from scrapers.geocode import reverse_geocode
from urllib.parse import urlparse


_LEGACY_DIST_PREFIX = re.compile(r"^\s*\(\s*[\d.]+\s*m\s*\)\s*")
_LEGACY_ADMIN_START = re.compile(r"\s*(?:ต\.|แขวง\s|ตำบล\s)")
_TRAILING_POSTAL = re.compile(r"\s*\d{5}\s*$")


def _split_legacy_address(s: str) -> tuple[str, str]:
    """Parse legacy provider's '( 233.49 m) ครัวร้อยเอ็ด  ต.บางนอน อ.เมืองระนอง  จ.ระนอง 85000'
    into (poi, admin). Either side may be empty if not present."""
    s = (s or "").strip()
    if not s:
        return "", ""
    rest = _LEGACY_DIST_PREFIX.sub("", s)
    m = _LEGACY_ADMIN_START.search(rest)
    if not m:
        return "", _TRAILING_POSTAL.sub("", rest).strip()
    poi = rest[: m.start()].strip()
    admin = _TRAILING_POSTAL.sub("", rest[m.start():]).strip()
    return poi, admin


class LegacyScraper(BaseScraper):
    source_name = "legacy"

    async def login(self, page: Page) -> bool:
        await page.goto(self.url, timeout=90000, wait_until="domcontentloaded")

        await page.fill('input[name="account"]', self.extra.get("account", ""))
        await page.fill('input[name="username"]', self.username)
        await page.fill('input[name="j_password"]', self.password)
        await page.click('input[id="login-btn"]')
        await page.wait_for_function("() => !window.location.href.includes('login')", timeout=60000)

        return "login" not in page.url.lower()

    async def get_vehicles(self, page: Page) -> list[dict]:
        base = f"{urlparse(self.url).scheme}://{urlparse(self.url).netloc}"
        api_url = f"{base}/ajax/devices-state.html?state=0"

        # ดึง cookie จาก Playwright context แล้วยิง request ผ่าน urllib
        # หลีกเลี่ยง round-trip page.evaluate(fetch) ผ่าน browser
        cookies = await page.context.cookies(api_url)
        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

        def _fetch():
            req = urllib.request.Request(api_url, headers={"Cookie": cookie_header})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json_lib.loads(r.read())

        data = await asyncio.to_thread(_fetch)

        vehicles = []
        for d in data.get("devices", []):
            name = d.get("deviceName", "").strip()
            # deviceName มักมีรูปแบบ "70-5177 เพชรบุรี" — แยก plate กับชื่อ
            parts = name.split(" ", 1)
            plate = parts[0] if parts else name
            label = parts[1].strip() if len(parts) > 1 else ""

            ignition = d.get("iginition", "false") == "true"
            speed = float(d.get("speed", 0))
            connected = d.get("connectionState", "0") == "1"
            try:
                heading = float(d.get("heading", 0))
            except (TypeError, ValueError):
                heading = 0.0
            try:
                odometer = float(d.get("odometer") or 0) or None
            except (TypeError, ValueError):
                odometer = None

            if not connected:
                status = "ไม่เชื่อมต่อ"
            elif ignition or speed > 0:
                status = "moving"
            else:
                status = "stopped"

            lat = float(d.get("latitude", 0))
            lng = float(d.get("longitude", 0))
            poi, admin = _split_legacy_address(d.get("address", ""))
            if poi and admin:
                address = f"{poi}\n{admin}"
            elif poi or admin:
                address = poi or admin
            else:
                address = await reverse_geocode(lat, lng) if lat and lng else ""

            vehicles.append({
                "vehicle_id": str(d.get("id")),
                "name": name,
                "plate": plate,
                "lat": lat,
                "lng": lng,
                "speed": speed,
                "status": status,
                "address": address,
                "heading": heading,
                "odometer": odometer,
                "engine_on": ignition,
            })

        return vehicles
