"""Persistence layer for station curation: schema and connection helper.

SQLite connections aren't safe to share across threads, so this module never
caches or holds one at module scope — `connect()` is a plain factory, and
every other function in this package (see later curation tasks) takes an
explicit `conn` parameter and lets the caller own its lifecycle.
"""

from __future__ import annotations

import sqlite3
import time
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


def record_heard_track(
    conn: sqlite3.Connection,
    station_id: str,
    artist: str | None,
    title: str | None,
    *,
    when: int | None = None,
) -> None:
    conn.execute(
        "INSERT INTO heard_tracks (station_id, artist, title, first_heard_at) "
        "VALUES (?, ?, ?, ?)",
        (station_id, artist, title, when if when is not None else int(time.time())),
    )
    conn.commit()


def has_heard(conn: sqlite3.Connection, artist: str, title: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM heard_tracks WHERE artist = ? AND title = ? LIMIT 1",
        (artist, title),
    ).fetchone()
    return row is not None


def heard_pairs(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    rows = conn.execute(
        "SELECT artist, title FROM heard_tracks "
        "WHERE artist IS NOT NULL AND title IS NOT NULL"
    ).fetchall()
    return {(r["artist"], r["title"]) for r in rows}


def record_candidate_probe(
    conn: sqlite3.Connection,
    station_id: str,
    artist: str | None,
    title: str | None,
    *,
    when: int | None = None,
) -> None:
    last = conn.execute(
        "SELECT artist, title FROM candidate_probes "
        "WHERE station_id = ? ORDER BY observed_at DESC LIMIT 1",
        (station_id,),
    ).fetchone()
    if last is not None and last["artist"] == artist and last["title"] == title:
        return
    conn.execute(
        "INSERT INTO candidate_probes (station_id, artist, title, observed_at) "
        "VALUES (?, ?, ?, ?)",
        (station_id, artist, title, when if when is not None else int(time.time())),
    )
    conn.commit()


def get_probes(conn: sqlite3.Connection, station_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT artist, title, observed_at FROM candidate_probes "
        "WHERE station_id = ? ORDER BY observed_at ASC",
        (station_id,),
    ).fetchall()
    return [dict(r) for r in rows]
