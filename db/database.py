import sqlite3
from datetime import datetime
from config import DB_PATH


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vehicles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                vehicle_id TEXT NOT NULL,
                name TEXT,
                plate TEXT,
                lat REAL,
                lng REAL,
                speed REAL,
                status TEXT,
                address TEXT,
                updated_at TEXT NOT NULL,
                raw_data TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_source_vehicle
            ON vehicles (source, vehicle_id)
        """)
        # migrate: add address column if not exists
        try:
            conn.execute("ALTER TABLE vehicles ADD COLUMN address TEXT")
        except Exception:
            pass
        conn.commit()


def upsert_vehicle(source: str, vehicle_id: str, data: dict):
    now = datetime.now().isoformat()
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM vehicles WHERE source=? AND vehicle_id=?",
            (source, vehicle_id)
        ).fetchone()

        if existing:
            conn.execute("""
                UPDATE vehicles SET
                    name=?, plate=?, lat=?, lng=?, speed=?, status=?, address=?, updated_at=?, raw_data=?
                WHERE source=? AND vehicle_id=?
            """, (
                data.get("name"), data.get("plate"),
                data.get("lat"), data.get("lng"),
                data.get("speed"), data.get("status"),
                data.get("address", ""),
                now, str(data),
                source, vehicle_id
            ))
        else:
            conn.execute("""
                INSERT INTO vehicles (source, vehicle_id, name, plate, lat, lng, speed, status, address, updated_at, raw_data)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                source, vehicle_id,
                data.get("name"), data.get("plate"),
                data.get("lat"), data.get("lng"),
                data.get("speed"), data.get("status"),
                data.get("address", ""),
                now, str(data)
            ))
        conn.commit()


def get_all_vehicles():
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM vehicles ORDER BY source, name
        """).fetchall()
        return [dict(r) for r in rows]
