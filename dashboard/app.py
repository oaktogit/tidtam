from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from db.database import get_all_vehicles
import json
import os

app = FastAPI(title="Tidtam GPS Dashboard")

BASE_DIR = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/vehicles")
async def vehicles():
    return get_all_vehicles()


@app.get("/api/summary")
async def summary():
    vehicles = get_all_vehicles()
    return {
        "total": len(vehicles),
        "by_source": {
            src: len([v for v in vehicles if v["source"] == src])
            for src in set(v["source"] for v in vehicles)
        },
        "moving": len([v for v in vehicles if v.get("status") in ("moving", "กำลังวิ่ง")]),
        "stopped": len([v for v in vehicles if v.get("status") in ("stopped", "จอด", "idle")]),
    }
