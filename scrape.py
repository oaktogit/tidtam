"""
Production entry point — รัน scrape ครั้งเดียวแล้วจบ
ใช้สำหรับ GitHub Actions (ไม่มี scheduler, ไม่มี dashboard)
"""
import asyncio
import os
import random
import time
from playwright.async_api import async_playwright
from db.database import init_db, get_known_addresses, cleanup_old_positions
from scrapers.geocode import warm_cache_from
from scrapers.skytek import SkytekScraper
from scrapers.geniustracks import GeniusTracksScraper
from scrapers.legacy import LegacyScraper


def build_scrapers():
    return [
        SkytekScraper(
            url=os.environ.get("SKYTEK_URL", "https://skytekgpsdee.com/login.aspx"),
            username=os.environ.get("SKYTEK_USERNAME", ""),
            password=os.environ.get("SKYTEK_PASSWORD", ""),
        ),
        GeniusTracksScraper(
            url=os.environ.get("GENIUSTRACKS_URL", "https://track3.geniustracks.com/login"),
            username=os.environ.get("GENIUSTRACKS_USERNAME", ""),
            password=os.environ.get("GENIUSTRACKS_PASSWORD", ""),
        ),
        LegacyScraper(
            url=os.environ.get("LEGACY_URL", "http://103.246.17.121/login.jsp"),
            account=os.environ.get("LEGACY_ACCOUNT", ""),
            username=os.environ.get("LEGACY_USERNAME", ""),
            password=os.environ.get("LEGACY_PASSWORD", ""),
        ),
    ]


async def scrape_all():
    print("=== เริ่มดึงข้อมูล GPS ===")
    warmed = warm_cache_from(get_known_addresses())
    print(f"[geocode] warmed cache with {warmed} known addresses")
    scrapers = build_scrapers()
    # แชร์ 1 chromium ให้ 3 scrapers (context แยกกัน คุกกี้ไม่ปน)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            await asyncio.gather(*[s.run(browser) for s in scrapers])
        finally:
            await browser.close()
    try:
        deleted = cleanup_old_positions(days=90)
        if deleted:
            print(f"[positions] retention: deleted {deleted} rows older than 90 days")
    except Exception as e:
        print(f"[positions] retention cleanup failed: {e}")
    print("=== ดึงข้อมูลเสร็จ ===")


if __name__ == "__main__":
    init_db()
    # หน่วง 0-60 วินาทีสุ่ม กลบ pattern login เป๊ะนาทีจาก cron */15
    jitter = random.uniform(0, 60)
    print(f"[jitter] sleeping {jitter:.1f}s before scraping")
    time.sleep(jitter)
    asyncio.run(scrape_all())
