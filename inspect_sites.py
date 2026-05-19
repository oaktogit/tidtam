"""
รัน: python inspect_sites.py [skytek|geniustracks|legacy]

Script นี้จะ:
1. เปิด browser จริง (มีหน้าต่าง)
2. Login ให้อัตโนมัติ
3. ดัก network request ทุกอัน และ print JSON ที่ดูเหมือนข้อมูลรถ
4. หยุดรอให้กด Enter ก่อนปิด (เพื่อ inspect เพิ่มได้)
"""
import asyncio
import json
import sys
from playwright.async_api import async_playwright
from config import SITES


GPS_KEYWORDS = ["lat", "lng", "latitude", "longitude", "speed", "vehicle", "device", "position", "gps"]


def looks_like_gps(data) -> bool:
    text = json.dumps(data).lower()
    return sum(1 for k in GPS_KEYWORDS if k in text) >= 2


async def inspect(site_key: str):
    cfg = SITES[site_key]
    print(f"\n{'='*60}")
    print(f"  Inspecting: {site_key}")
    print(f"  URL: {cfg['url']}")
    print(f"{'='*60}\n")

    captured = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        context = await browser.new_context()
        page = await context.new_page()

        async def handle_response(response):
            ct = response.headers.get("content-type", "")
            is_json = "json" in ct
            is_xml = "xml" in ct or "text" in ct
            if not (is_json or is_xml):
                return
            try:
                if is_json:
                    data = await response.json()
                    text = json.dumps(data)
                else:
                    text = await response.text()
                    data = text

                if any(k in text.lower() for k in GPS_KEYWORDS):
                    # ดัก request ที่ส่งไปด้วย
                    req = response.request
                    post_data = req.post_data or ""
                    print(f"\n[GPS DATA FOUND] {response.url}")
                    print(f"  Method: {req.method}")
                    if post_data:
                        print(f"  Body: {post_data[:500]}")
                    print(f"  Response: {text[:2000]}")
                    print("..." if len(text) > 2000 else "")
                    captured.append({"url": response.url, "method": req.method, "body": post_data, "data": data})
                else:
                    print(f"[{ct[:20]}] {response.url}")
            except Exception:
                pass

        # ดัก WebSocket frames ด้วย
        async def handle_websocket(ws):
            print(f"\n[WebSocket] {ws.url}")
            async def on_frame(payload):
                text = payload if isinstance(payload, str) else payload.decode("utf-8", errors="ignore")
                if any(k in text.lower() for k in GPS_KEYWORDS):
                    print(f"[WS GPS FRAME] {text[:2000]}")
                    captured.append({"url": ws.url, "data": text})
            ws.on("framereceived", on_frame)

        page.on("response", handle_response)
        page.on("websocket", handle_websocket)

        # --- Login ---
        await page.goto(cfg["url"])
        await page.wait_for_load_state("networkidle")

        if site_key == "skytek":
            await page.click('input[name="rbl"][value="เลขทะเบียน"]')
            await page.fill('input[name="tbUserName"]', cfg["username"])
            await page.fill('input[name="tbPwd"]', cfg["password"])
            await page.click('input[id="btnLogin"]')
            await page.wait_for_load_state("networkidle")

            # print ลิงก์ทั้งหมดในหน้า เพื่อหา selector ที่ถูกต้อง
            print("\n[Skytek] ลิงก์ทั้งหมดในหน้า:")
            links = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a, input[type=button], button'))
                    .map(el => ({tag: el.tagName, text: el.innerText || el.value || '', href: el.href || ''}))
                    .filter(el => el.text.trim())
            }""")
            for l in links:
                print(f"  [{l['tag']}] '{l['text'].strip()}' → {l['href']}")

            print("\n[Skytek] กด Enter หลังจาก navigate ไปหน้าติดตามด้วยตัวเองแล้ว...")
            input()
            await page.wait_for_timeout(4000)

        elif site_key == "geniustracks":
            await page.fill('input[name="username"], input[type="email"], input[placeholder*="user" i]', cfg["username"])
            await page.fill('input[name="password"], input[type="password"]', cfg["password"])
            await page.click('button[type="submit"], input[type="submit"]')

        elif site_key == "legacy":
            await page.fill('input[name="account"]', cfg.get("account", ""))
            await page.fill('input[name="username"]', cfg["username"])
            await page.fill('input[name="j_password"]', cfg["password"])
            await page.click('input[id="login-btn"]')

        await page.wait_for_load_state("networkidle")
        print(f"\n[URL หลัง login] {page.url}")

        # รอให้ JS โหลดข้อมูลเพิ่ม
        await page.wait_for_timeout(3000)

        print(f"\n{'='*60}")
        print(f"  พบ GPS response: {len(captured)} อัน")
        print(f"  กด Enter เพื่อปิด browser...")
        print(f"{'='*60}")
        input()

        await browser.close()

    if not captured:
        print("\n[ไม่พบ JSON ที่ดูเหมือน GPS] ลองดูใน browser แล้วส่ง screenshot มาครับ")
    else:
        out_file = f"inspect_{site_key}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(captured, f, indent=2, ensure_ascii=False)
        print(f"\n[บันทึกผลที่] {out_file}")


if __name__ == "__main__":
    site = sys.argv[1] if len(sys.argv) > 1 else "legacy"
    if site not in SITES:
        print(f"ใช้: python inspect_sites.py [{'|'.join(SITES.keys())}]")
        sys.exit(1)
    asyncio.run(inspect(site))
