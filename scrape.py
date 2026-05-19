"""
Production entry point — รัน scrape ครั้งเดียวแล้วจบ
ใช้สำหรับ GitHub Actions (ไม่มี scheduler, ไม่มี dashboard)
"""
import asyncio
import os
from db.database import init_db
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
    scrapers = build_scrapers()
    await asyncio.gather(*[s.run() for s in scrapers])
    print("=== ดึงข้อมูลเสร็จ ===")


if __name__ == "__main__":
    init_db()
    asyncio.run(scrape_all())
