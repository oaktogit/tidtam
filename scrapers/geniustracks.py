from playwright.async_api import Page
from scrapers.base import BaseScraper


class GeniusTracksScraper(BaseScraper):
    source_name = "geniustracks"

    async def login(self, page: Page) -> bool:
        await page.goto(self.url)
        await page.wait_for_load_state("networkidle")

        await page.fill('input[name="username"], input[type="email"]', self.username)
        await page.fill('input[name="password"], input[type="password"]', self.password)
        await page.click('button[type="submit"], input[type="submit"]')
        await page.wait_for_load_state("networkidle")

        return "login" not in page.url.lower()

    async def get_vehicles(self, page: Page) -> list[dict]:
        captured = {}

        async def handle_response(response):
            if "getRealTimeData" in response.url:
                try:
                    data = await response.json()
                    # เก็บอันที่มีรถมากที่สุด
                    if len(data.get("data", [])) > len(captured.get("data", {}).get("data", [])):
                        captured["data"] = data
                except Exception:
                    pass

        page.on("response", handle_response)
        await page.goto("https://track3.geniustracks.com/mapGenius")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(3000)

        # คลิก dropdown กลุ่ม แล้วเลือก "ทั้งหมด"
        try:
            await page.click(".select2-selection, [class*='group'] .select2, .select2-container", timeout=5000)
            await page.wait_for_timeout(500)
            await page.click("li:has-text('ทั้งหมด')", timeout=5000)
            await page.wait_for_timeout(4000)  # รอ API โหลดรถใหม่ครบ
        except Exception:
            pass

        data = captured.get("data", {})

        vehicles = []
        for d in data.get("data", []):
            online = d.get("statusonline", 0) == 1
            engine_on = d.get("isEngineOn", False)
            speed = float(d.get("speed", 0))

            if not online:
                status = "OFFLINE"
            elif engine_on or speed > 0:
                status = "moving"
            else:
                status = "stopped"

            vehicles.append({
                "vehicle_id": str(d.get("id")),
                "name": d.get("name", ""),
                "plate": d.get("number", ""),
                "lat": float(d.get("lat", 0)),
                "lng": float(d.get("lng", 0)),
                "speed": speed,
                "status": status,
                "address": d.get("address", ""),
            })

        return vehicles
