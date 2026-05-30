from playwright.async_api import Page
from scrapers.base import BaseScraper
from scrapers.geocode import reverse_geocode


class GeniusTracksScraper(BaseScraper):
    source_name = "geniustracks"

    async def login(self, page: Page) -> bool:
        await page.goto(self.url)
        await page.wait_for_load_state("load")

        await page.fill('input[name="username"], input[type="email"]', self.username)
        await page.fill('input[name="password"], input[type="password"]', self.password)
        # expect_navigation around the click avoids the race where the URL
        # check runs before the JS-driven navigation kicks in. See
        # `feedback-click-nav-race` memory.
        async with page.expect_navigation(wait_until="load", timeout=30000):
            await page.click('button[type="submit"], input[type="submit"]')

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

        def captured_count() -> int:
            return len(captured.get("data", {}).get("data", []))

        page.on("response", handle_response)
        await page.goto("https://track3.geniustracks.com/mapGenius", wait_until="domcontentloaded")

        # wait for initial data load — explicit instead of fragile networkidle
        try:
            await page.wait_for_event(
                "response",
                predicate=lambda r: "getRealTimeData" in r.url and r.status == 200,
                timeout=20000,
            )
        except Exception as e:
            print(f"[geniustracks] initial getRealTimeData wait timed out: {e}")
        await page.wait_for_timeout(300)  # listener flush — async handler finishes quickly

        # เลือก "ทั้งหมด" — retry สูงสุด 3 ครั้ง ถ้ายังจับข้อมูลไม่ได้
        for attempt in range(1, 4):
            try:
                await page.click(".select2-selection, [class*='group'] .select2, .select2-container", timeout=5000)
                await page.wait_for_timeout(400)
                await page.click("li:has-text('ทั้งหมด')", timeout=5000)
                # รอ getRealTimeData ของ group change
                try:
                    await page.wait_for_event(
                        "response",
                        predicate=lambda r: "getRealTimeData" in r.url and r.status == 200,
                        timeout=10000,
                    )
                except Exception:
                    pass
                await page.wait_for_timeout(1500)  # buffer for slow getRealTimeData responses
            except Exception as e:
                print(f"[geniustracks] dropdown attempt {attempt} failed: {e}")

            if captured_count() > 0:
                print(f"[geniustracks] captured {captured_count()} vehicles on attempt {attempt}")
                break
            print(f"[geniustracks] attempt {attempt}: still 0 vehicles, retrying...")

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

            try:
                heading = float(d.get("car_rotation") or 0)
            except (TypeError, ValueError):
                heading = 0.0
            try:
                # mileage is cumulative; mile (per-trip) as fallback. Either
                # works for Park detection — delta=0 while stopped.
                odometer = float(d.get("mileage") or d.get("mile") or 0) or None
            except (TypeError, ValueError):
                odometer = None

            lat = float(d.get("lat", 0))
            lng = float(d.get("lng", 0))
            poi_obj = d.get("nearest_poi")
            poi_name = (
                (poi_obj.get("name") if isinstance(poi_obj, dict) else None)
                or d.get("near")
                or ""
            ).strip()
            admin = (d.get("address") or "").strip()
            if poi_name and admin:
                address = f"{poi_name}\n{admin}"
            elif poi_name or admin:
                address = poi_name or admin
            else:
                address = await reverse_geocode(lat, lng) if lat and lng else ""

            vehicles.append({
                "vehicle_id": str(d.get("id")),
                "name": d.get("name", ""),
                "plate": d.get("number", ""),
                "lat": lat,
                "lng": lng,
                "speed": speed,
                "status": status,
                "address": address,
                "heading": heading,
                "odometer": odometer,
                "engine_on": bool(engine_on),
                "extra": {
                    "over_4h": bool(d.get("isDrivingOverFourHours")),
                },
            })

        return vehicles
