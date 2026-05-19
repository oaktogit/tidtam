from abc import ABC, abstractmethod
from playwright.async_api import async_playwright, Page
from db.database import upsert_vehicle
import traceback


class BaseScraper(ABC):
    source_name: str = ""

    def __init__(self, url: str, username: str, password: str, **kwargs):
        self.url = url
        self.username = username
        self.password = password
        self.extra = kwargs  # เก็บ field พิเศษ เช่น account

    @abstractmethod
    async def login(self, page: Page) -> bool:
        pass

    @abstractmethod
    async def get_vehicles(self, page: Page) -> list[dict]:
        """Return list of dicts with keys: vehicle_id, name, plate, lat, lng, speed, status"""
        pass

    async def run(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            try:
                logged_in = await self.login(page)
                if not logged_in:
                    print(f"[{self.source_name}] Login failed")
                    return []

                vehicles = await self.get_vehicles(page)
                for v in vehicles:
                    upsert_vehicle(self.source_name, v["vehicle_id"], v)
                print(f"[{self.source_name}] Updated {len(vehicles)} vehicles")
                return vehicles
            except Exception:
                print(f"[{self.source_name}] Error:\n{traceback.format_exc()}")
                return []
            finally:
                await browser.close()
