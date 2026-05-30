import asyncio
import sys
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from db.database import init_db, cleanup_old_positions
from scrapers.skytek import SkytekScraper
from scrapers.geniustracks import GeniusTracksScraper
from scrapers.legacy import LegacyScraper
from config import SITES, SCRAPE_INTERVAL_MINUTES
import uvicorn
from dashboard.app import app


def build_scrapers():
    return [
        SkytekScraper(**SITES["skytek"]),
        GeniusTracksScraper(**SITES["geniustracks"]),
        LegacyScraper(**SITES["legacy"]),
    ]


_scrape_lock = asyncio.Lock()


async def scrape_all():
    # Lock prevents the dashboard's manual /api/scrape from racing the
    # AsyncIOScheduler job (or itself, if the user spams the refresh button).
    if _scrape_lock.locked():
        print("[scrape] already running — skipping concurrent request")
        return
    async with _scrape_lock:
        print("=== เริ่มดึงข้อมูล GPS ===")
        scrapers = build_scrapers()
        await asyncio.gather(*[s.run() for s in scrapers])
        try:
            deleted = cleanup_old_positions(days=90)
            if deleted:
                print(f"[positions] retention: deleted {deleted} rows older than 90 days")
        except Exception as e:
            print(f"[positions] retention cleanup failed: {e}")
        print("=== ดึงข้อมูลเสร็จ ===")


async def main():
    init_db()

    # ดึงข้อมูลครั้งแรกทันที
    await scrape_all()

    # ตั้ง scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(scrape_all, "interval", minutes=SCRAPE_INTERVAL_MINUTES)
    scheduler.start()

    # รัน dashboard
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
