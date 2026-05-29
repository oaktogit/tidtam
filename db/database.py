import json
import os
import sqlite3
from datetime import datetime, timedelta

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
            extra TEXT,
            updated_at TEXT NOT NULL,
            raw_data TEXT
        )
    """)
    _exec(conn, """
        CREATE INDEX IF NOT EXISTS idx_source_vehicle
        ON vehicles (source, vehicle_id)
    """)
    # Append-only position history. Every scrape that yields a valid GPS fix
    # inserts one row here; cleanup_old_positions trims rows older than N days.
    _exec(conn, f"""
        CREATE TABLE IF NOT EXISTS positions (
            {pk},
            source TEXT NOT NULL,
            vehicle_id TEXT NOT NULL,
            lat REAL,
            lng REAL,
            speed REAL,
            status TEXT,
            heading REAL,
            recorded_at TEXT NOT NULL
        )
    """)
    _exec(conn, """
        CREATE INDEX IF NOT EXISTS idx_pos_vehicle_time
        ON positions (source, vehicle_id, recorded_at)
    """)
    # Additive migrations for tables that pre-date these columns.
    # SQLite has no IF NOT EXISTS for ALTER, so we try/except.
    # Postgres supports IF NOT EXISTS — safe to run every startup.
    if DATABASE_URL:
        for col_sql in (
            "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS address TEXT",
            "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS heading REAL",
            "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS extra TEXT",
        ):
            try:
                _exec(conn, col_sql)
            except Exception:
                pass
    else:
        for col_sql in (
            "ALTER TABLE vehicles ADD COLUMN address TEXT",
            "ALTER TABLE vehicles ADD COLUMN heading REAL",
            "ALTER TABLE vehicles ADD COLUMN extra TEXT",
        ):
            try:
                conn.execute(col_sql)
            except Exception:
                pass
    conn.commit()
    conn.close()


def _insert_position(conn, source: str, vehicle_id: str, data: dict, now: str):
    """Append one position snapshot. Skip rows with no valid GPS fix."""
    lat = data.get("lat")
    lng = data.get("lng")
    try:
        if not float(lat or 0) or not float(lng or 0):
            return
    except (TypeError, ValueError):
        return
    _exec(conn, """
        INSERT INTO positions (source, vehicle_id, lat, lng, speed, status, heading, recorded_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        source, vehicle_id,
        data.get("lat"), data.get("lng"),
        data.get("speed"), data.get("status"),
        data.get("heading"),
        now,
    ))


def upsert_vehicle(source: str, vehicle_id: str, data: dict):
    now = datetime.now().isoformat()
    extra_json = json.dumps(data.get("extra") or {}, ensure_ascii=False)
    conn = _get_conn()
    existing = _exec(conn,
        "SELECT id FROM vehicles WHERE source=? AND vehicle_id=?",
        (source, vehicle_id)
    ).fetchone()

    if existing:
        _exec(conn, """
            UPDATE vehicles SET
                name=?, plate=?, lat=?, lng=?, speed=?, status=?, address=?, heading=?, extra=?, updated_at=?, raw_data=?
            WHERE source=? AND vehicle_id=?
        """, (
            data.get("name"), data.get("plate"),
            data.get("lat"), data.get("lng"),
            data.get("speed"), data.get("status"),
            data.get("address", ""),
            data.get("heading"),
            extra_json,
            now, str(data),
            source, vehicle_id
        ))
    else:
        _exec(conn, """
            INSERT INTO vehicles (source, vehicle_id, name, plate, lat, lng, speed, status, address, heading, extra, updated_at, raw_data)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            source, vehicle_id,
            data.get("name"), data.get("plate"),
            data.get("lat"), data.get("lng"),
            data.get("speed"), data.get("status"),
            data.get("address", ""),
            data.get("heading"),
            extra_json,
            now, str(data)
        ))
    _insert_position(conn, source, vehicle_id, data, now)
    conn.commit()
    conn.close()


def cleanup_old_positions(days: int = 90) -> int:
    """Delete position rows older than N days. Returns count deleted."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = _get_conn()
    cur = _exec(conn, "DELETE FROM positions WHERE recorded_at < ?", (cutoff,))
    deleted = cur.rowcount if hasattr(cur, "rowcount") else 0
    conn.commit()
    conn.close()
    return deleted


def get_positions(source: str, vehicle_id: str, hours: int = 24) -> list[dict]:
    """Return positions for one vehicle within the last N hours, oldest first."""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    conn = _get_conn()
    if DATABASE_URL:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT lat, lng, speed, status, heading, recorded_at FROM positions "
            "WHERE source=%s AND vehicle_id=%s AND recorded_at >= %s "
            "ORDER BY recorded_at ASC",
            (source, vehicle_id, cutoff),
        )
        rows = [dict(r) for r in cur.fetchall()]
    else:
        rows = [dict(r) for r in conn.execute(
            "SELECT lat, lng, speed, status, heading, recorded_at FROM positions "
            "WHERE source=? AND vehicle_id=? AND recorded_at >= ? "
            "ORDER BY recorded_at ASC",
            (source, vehicle_id, cutoff),
        ).fetchall()]
    conn.close()
    return rows


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
    # Deserialize extra JSON so the API returns a real object, not a string.
    for r in rows:
        raw = r.get("extra")
        if isinstance(raw, str) and raw:
            try:
                r["extra"] = json.loads(raw)
            except Exception:
                r["extra"] = {}
        elif raw is None:
            r["extra"] = {}
    return rows


def get_known_addresses() -> list[tuple]:
    """Return [(lat, lng, address), ...] for warming the geocode cache so
    repeat positions skip Nominatim on the next scrape."""
    conn = _get_conn()
    sql = "SELECT lat, lng, address FROM vehicles WHERE address IS NOT NULL AND address != ''"
    if DATABASE_URL:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
    else:
        rows = conn.execute(sql).fetchall()
    conn.close()
    return [(r[0], r[1], r[2]) for r in rows]
