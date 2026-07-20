"""Persistence layer for station curation: schema and connection helper.

SQLite connections aren't safe to share across threads, so this module never
caches or holds one at module scope — `connect()` is a plain factory, and
every other function in this package (see later curation tasks) takes an
explicit `conn` parameter and lets the caller own its lifecycle.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlch.core.paths import data_dir

_SCHEMA = """
CREATE TABLE IF NOT EXISTS heard_tracks (
    station_id TEXT NOT NULL,
    artist TEXT,
    title TEXT,
    first_heard_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS candidate_probes (
    station_id TEXT NOT NULL,
    artist TEXT,
    title TEXT,
    observed_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS stations_curation (
    station_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    probation_started_at INTEGER NOT NULL,
    probation_ends_at INTEGER NOT NULL,
    score REAL,
    gate_passed INTEGER
);
"""


def db_path() -> Path:
    return data_dir() / "curation.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or db_path()))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn
