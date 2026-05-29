import json
import re
from playwright.async_api import Page
from scrapers.base import BaseScraper
from scrapers.geocode import reverse_geocode


ASHX = "/ajax/VehicleMonitor,App_Web_vehiclemonitor.aspx.cdcab7d2.hyutbdl4.ashx"
EPOCH_CURTIME = "1900-01-01 00:00:00"


class SkytekScraper(BaseScraper):
    source_name = "skytek"

    async def login(self, page: Page) -> bool:
        await page.goto(self.url, wait_until="domcontentloaded")

        await page.click('input[name="rbl"][value="เลขทะเบียน"]')
        await page.fill('input[name="tbUserName"]', self.username)
        if self.password:
            await page.fill('input[name="tbPwd"]', self.password)
        await page.click('input[id="btnLogin"]')
        # รอ URL เปลี่ยนตรงๆ — กัน race ที่ click คืนก่อน navigation
        # (wait_for_load_state รอ state ของ "หน้าปัจจุบัน" ซึ่งอาจยังเป็น login)
        await page.wait_for_url("**/VehicleMonitor.aspx", timeout=60000)
        print(f"[skytek] after login URL: {page.url}")

        return page.url.lower().endswith("vehiclemonitor.aspx")

    async def _post(self, page: Page, method: str, body: str = "") -> str:
        raw = await page.evaluate(
            """async ({url, body}) => {
                const r = await fetch(url, {
                    method: 'POST',
                    body: body,
                    headers: {'Content-Type': 'application/x-www-form-urlencoded'}
                });
                return await r.text();
            }""",
            {"url": f"{ASHX}?_method={method}&_session=r", "body": body},
        )
        # ASHX wraps payload in literal single quotes — strip them
        raw = raw.strip()
        if len(raw) >= 2 and raw.startswith("'") and raw.endswith("'"):
            raw = raw[1:-1]
        return raw

    async def get_vehicles(self, page: Page) -> list[dict]:
        # 1) รายชื่อรถ: SystemNo|Plate per record (delimiter '#')
        veh_raw = await self._post(page, "GetVehJson")
        plate_by_sysno: dict[str, str] = {}
        for chunk in re.split(r"[#\r\n]+", veh_raw):
            chunk = chunk.strip()
            if not chunk or "|" not in chunk:
                continue
            parts = chunk.split("|")
            sysno = parts[0].strip()
            plate = parts[1].strip() if len(parts) > 1 else ""
            if sysno:
                plate_by_sysno[sysno] = plate

        # 2) เก็บ metadata เพิ่ม (CompanyName, McName) จาก GetGridHtml
        grid_html = await self._post(
            page, "GetGridHtml", "strpageindex=0\r\nstrpagesize=1000"
        )
        meta_by_sysno: dict[str, dict] = {}
        # tip attribute uses either {'k':'v'} or {"k":"v"} depending on encoding
        for tip in re.finditer(r"tip=[\"']?(\{[^\"'\\]*(?:\\.[^\"'\\]*)*\})", grid_html):
            try:
                tip_json = tip.group(1).replace("\\'", "'").replace("'", '"')
                t = json.loads(tip_json)
                sysno = t.get("SystemNo")
                if sysno:
                    meta_by_sysno[sysno] = {
                        "company": t.get("CompanyName", ""),
                        "fleet": t.get("McName", ""),
                        "sim": t.get("SimID", ""),
                    }
            except Exception:
                pass

        # 3) ตำแหน่งล่าสุดของทุกคัน
        loc_raw = await self._post(page, "GetLocationData", f"curtime={EPOCH_CURTIME}")
        positions: dict[str, dict] = {}
        for chunk in loc_raw.split("#"):
            chunk = chunk.strip()
            if not chunk.startswith("{"):
                continue
            try:
                pos = json.loads(chunk)
                # SimID ที่นี่จริงๆ คือ SystemNo (จาก response จริง)
                key = pos.get("SimID") or pos.get("SystemNo")
                if key:
                    positions[str(key)] = pos
            except Exception:
                continue

        vehicles: list[dict] = []
        for sysno, plate in plate_by_sysno.items():
            pos = positions.get(sysno, {})
            meta = meta_by_sysno.get(sysno, {})

            try:
                lat = float(pos.get("Latitude") or 0)
                lng = float(pos.get("Longitude") or 0)
            except (TypeError, ValueError):
                lat, lng = 0.0, 0.0

            try:
                speed = float(pos.get("Velocity") or 0)
            except (TypeError, ValueError):
                speed = 0.0

            try:
                heading = float(pos.get("Direction") or pos.get("Heading") or 0)
            except (TypeError, ValueError):
                heading = 0.0

            acc_on = (pos.get("AccStatus") or "").upper() == "ON"
            locate_ok = (pos.get("LocateStatus") or "").lower() == "locate"

            if not pos:
                status = "ไม่เชื่อมต่อ"
            elif acc_on or speed > 0:
                status = "moving"
            elif locate_ok:
                status = "stopped"
            else:
                status = "ไม่เชื่อมต่อ"

            address = await reverse_geocode(lat, lng) if lat and lng else ""

            vehicles.append({
                "vehicle_id": sysno,
                "name": f"{plate} {meta.get('fleet', '')}".strip(),
                "plate": plate,
                "lat": lat,
                "lng": lng,
                "speed": speed,
                "status": status,
                "address": address,
                "heading": heading,
            })

        return vehicles
