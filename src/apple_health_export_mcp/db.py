"""SQLite store: schema + connection. See docs/adr.md (ADR-0002, 0004, 0009)."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

# Apple writes timestamps in local time with the offset appended
# ("2026-06-18 23:13:35 +0300"), so the local calendar day is just the
# first 10 chars — no timezone conversion needed (ADR-0009).
SCHEMA = """
CREATE TABLE IF NOT EXISTS record (
    key        BLOB PRIMARY KEY,   -- content hash, idempotent (ADR-0005)
    type       TEXT NOT NULL,      -- HK*TypeIdentifier*, locale-independent
    source     TEXT,               -- sourceName, may be localized/personal
    unit       TEXT,
    value      TEXT,               -- TEXT: quantity=number, category=enum string
    start      TEXT NOT NULL,      -- raw, with offset
    end        TEXT,
    created    TEXT,
    local_date TEXT NOT NULL       -- substr(start,1,10): local day, for bucketing
);
CREATE INDEX IF NOT EXISTS ix_record_type_date ON record(type, local_date);

CREATE TABLE IF NOT EXISTS workout (
    key          BLOB PRIMARY KEY,
    activity     TEXT NOT NULL,    -- workoutActivityType
    duration     REAL,
    duration_unit TEXT,
    source       TEXT,
    start        TEXT NOT NULL,
    end          TEXT,
    created      TEXT,
    local_date   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_workout_date ON workout(local_date);

CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def db_path() -> Path:
    """Resolve the DB path from config/env (ADR-0007). No hard-coded location."""
    env = os.environ.get("AH_DB_PATH")
    if env:
        return Path(env).expanduser()
    # Fallback: XDG data dir.
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "apple-health-export-mcp" / "health.db"


def connect(path: Path | None = None, *, create: bool = True) -> sqlite3.Connection:
    p = path or db_path()
    if create:
        p.parent.mkdir(parents=True, exist_ok=True)
    elif not p.exists():
        raise FileNotFoundError(
            f"No database at {p}. Run `apple-health-export-mcp ingest <export.zip>` first "
            f"(set AH_DB_PATH to control the location)."
        )
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
