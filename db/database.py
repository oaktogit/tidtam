import os
import sqlite3
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL")

try:
    from config import DB_PATH
except ImportError:
    DB_PATH = "tidtam.db"


def _get_conn():
    if DATABASE_URL:
        import psycopg2
        return psycopg2.connect(DATABASE_URL)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _exec(conn, sql: str, params=()):
    """Unified execute: handles ? (SQLite) vs %s (PostgreSQL) placeholders."""
    if DATABASE_URL:
        sql = sql.replace("?", "%s")
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur
    return conn.execute(sql, params)


def init_db():
    pk = "id SERIAL PRIMARY KEY" if DATABASE_URL else "id INTEGER PRIMARY KEY AUTOINCREMENT"
    conn = _get_conn()
    _exec(conn, f"""
        CREATE TABLE IF NOT EXISTS vehicles (
            {pk},
            source TEXT NOT NULL,
            vehicle_id TEXT NOT NULL,
            name TEXT,
            plate TEXT,
            lat REAL,
            lng REAL,
            speed REAL,
            status TEXT,
            address TEXT,
            heading REAL,
            updated_at TEXT NOT NULL,
            raw_data TEXT
        )
    """)
    _exec(conn, """
        CREATE INDEX IF NOT EXISTS idx_source_vehicle
        ON vehicles (source, vehicle_id)
    """)
    if not DATABASE_URL:
        # SQLite only: migrate legacy databases without these columns
        for col_sql in (
            "ALTER TABLE vehicles ADD COLUMN address TEXT",
            "ALTER TABLE vehicles ADD COLUMN heading REAL",
        ):
            try:
                conn.execute(col_sql)
            except Exception:
                pass
    conn.commit()
    conn.close()


def upsert_vehicle(source: str, vehicle_id: str, data: dict):
    now = datetime.now().isoformat()
    conn = _get_conn()
    existing = _exec(conn,
        "SELECT id FROM vehicles WHERE source=? AND vehicle_id=?",
        (source, vehicle_id)
    ).fetchone()

    if existing:
        _exec(conn, """
            UPDATE vehicles SET
                name=?, plate=?, lat=?, lng=?, speed=?, status=?, address=?, heading=?, updated_at=?, raw_data=?
            WHERE source=? AND vehicle_id=?
        """, (
            data.get("name"), data.get("plate"),
            data.get("lat"), data.get("lng"),
            data.get("speed"), data.get("status"),
            data.get("address", ""),
            data.get("heading"),
            now, str(data),
            source, vehicle_id
        ))
    else:
        _exec(conn, """
            INSERT INTO vehicles (source, vehicle_id, name, plate, lat, lng, speed, status, address, heading, updated_at, raw_data)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            source, vehicle_id,
            data.get("name"), data.get("plate"),
            data.get("lat"), data.get("lng"),
            data.get("speed"), data.get("status"),
            data.get("address", ""),
            data.get("heading"),
            now, str(data)
        ))
    conn.commit()
    conn.close()


def get_all_vehicles():
    conn = _get_conn()
    if DATABASE_URL:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM vehicles ORDER BY source, name")
        rows = [dict(r) for r in cur.fetchall()]
    else:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM vehicles ORDER BY source, name"
        ).fetchall()]
    conn.close()
    return rows
