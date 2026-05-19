# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Tidtam aggregates vehicle/GPS data from three third-party Thai GPS tracking websites (skytek, geniustracks, legacy) by driving their web UIs with Playwright, normalizing the results, and serving them through a FastAPI dashboard. Site credentials and tuning live in `config.py` (gitignored).

## Common commands

```bash
# First-time setup
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium     # required — scrapers use headless Chromium

# Run the whole app (scrape immediately, then every SCRAPE_INTERVAL_MINUTES,
# while serving the dashboard on :8000)
python main.py

# Inspect one site interactively in a visible browser, capturing network
# traffic that looks like GPS payloads — used when adapting a scraper to a
# site change.
python inspect_sites.py skytek          # or geniustracks | legacy
```

There is no test suite, linter, or build step configured.

## Architecture

Three layers, wired together in `main.py`:

1. **Scrapers** (`scrapers/`) — one module per source, all subclassing
   `BaseScraper` (`scrapers/base.py`). The base class owns the Playwright
   lifecycle (`run()` launches headless Chromium, calls `login()` then
   `get_vehicles()`, and upserts each result). Subclasses only implement those
   two methods and set `source_name`. Constructor accepts arbitrary `**kwargs`
   stored on `self.extra` — that's how `LegacyScraper` reads its `account`
   field from `config.SITES["legacy"]` without changing the base signature.
   `get_vehicles()` must return dicts with keys
   `vehicle_id, name, plate, lat, lng, speed, status` (and optionally
   `address`). Site-specific scrapers typically log in via the UI, then
   call internal AJAX endpoints through `page.evaluate(fetch(...))` so they
   inherit the session cookies — see `SkytekScraper._post` for the pattern.

2. **Storage** (`db/database.py`) — single SQLite file `tidtam.db`, one
   `vehicles` table keyed by `(source, vehicle_id)`. `upsert_vehicle` does
   read-then-update-or-insert; `init_db()` is idempotent and includes an
   inline `ALTER TABLE ADD COLUMN address` migration guarded by try/except
   (the established pattern here for additive schema changes).

3. **Dashboard** (`dashboard/app.py`) — FastAPI with two JSON endpoints
   (`/api/vehicles`, `/api/summary`) plus `index.html`. It reads the DB
   only — it never triggers scraping. The scheduler in `main.py`
   (`AsyncIOScheduler`) is what keeps the data fresh, running alongside
   the uvicorn server in the same event loop.

`scrapers/geocode.py` provides async reverse-geocoding via Nominatim with
an in-process `_cache` keyed by lat/lng rounded to 4 decimal places (~11m).
No API key; respect Nominatim's usage policy when increasing call volume.

## Conventions worth knowing

- Status values are not normalized across sources — both English (`moving`,
  `stopped`, `idle`) and Thai (`กำลังวิ่ง`, `จอด`) appear, and
  `/api/summary` matches on both. New scrapers should keep the source's
  native strings rather than translating.
- `config.py` is gitignored; when adding a new site, add its entry to
  `SITES`, wire it into `build_scrapers()` in `main.py`, and document
  required keys in the scraper module.
- `inspect_*.json` files in the repo root are captured network dumps from
  `inspect_sites.py` runs, kept as references for the AJAX shapes each
  site returns.
