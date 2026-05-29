import asyncio
import json as json_lib
import urllib.request
from playwright.async_api import Page
from scrapers.base import BaseScraper
from urllib.parse import urlparse


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

            if not connected:
                status = "ไม่เชื่อมต่อ"
            elif ignition or speed > 0:
                status = "moving"
            else:
                status = "stopped"

            vehicles.append({
                "vehicle_id": str(d.get("id")),
                "name": name,
                "plate": plate,
                "lat": float(d.get("latitude", 0)),
                "lng": float(d.get("longitude", 0)),
                "speed": speed,
                "status": status,
                "address": d.get("address", ""),
                "heading": heading,
            })

        return vehicles
