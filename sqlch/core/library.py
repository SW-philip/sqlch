from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import List, Optional

from sqlch.core.paths import data_dir

APP_NAME = "sqlch"
LIBRARY_VERSION = 1


def _library_path() -> Path:
    return data_dir() / "library.json"


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def _now() -> int:
    return int(time.time())


def _atomic_write(path: Path, data: dict):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    tmp.replace(path)


def _normalize_id(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    return s.strip("-")


def _default_library() -> dict:
    return {"version": LIBRARY_VERSION, "stations": []}


def _normalize_station(st: dict) -> dict:
    st = dict(st)
    st.setdefault("id", _normalize_id(st.get("name", "unknown")))
    st.setdefault("name", "Unknown")
    st.setdefault("category", None)
    st.setdefault("url", None)
    st.setdefault("tags", [])
    st.setdefault("notes", None)
    st.setdefault("added_at", _now())
    st.setdefault("last_played", None)
    st.setdefault("play_count", 0)
    st.setdefault("rb_uuid", None)
    st.setdefault("source", {"type": "manual", "origin": "user"})
    st.setdefault(
        "stream",
        {
            "codec": None,
            "bitrate": None,
            "country": None,
            "validated": False,
            "last_checked": None,
        },
    )
    return st


def next_station(current_id: str) -> Optional[dict]:
    stations = list_stations()
    ids = [s["id"] for s in stations]
    if current_id not in ids:
        return stations[0] if stations else None
    idx = (ids.index(current_id) + 1) % len(stations)
    return stations[idx]


def prev_station(current_id: str) -> Optional[dict]:
    stations = list_stations()
    ids = [s["id"] for s in stations]
    if current_id not in ids:
        return stations[-1] if stations else None
    idx = (ids.index(current_id) - 1) % len(stations)
    return stations[idx]


# ------------------------------------------------------------
# Public API
# ------------------------------------------------------------

def load() -> dict:
    path = _library_path()

    if not path.exists():
        lib = _default_library()
        _atomic_write(path, lib)
        return lib

    try:
        lib = json.loads(path.read_text())
    except Exception:
        lib = _default_library()

    lib.setdefault("version", LIBRARY_VERSION)
    lib.setdefault("stations", [])
    lib["stations"] = [_normalize_station(st) for st in lib["stations"]]

    return lib


def save(lib: dict):
    _atomic_write(_library_path(), lib)


def list_stations(category: Optional[str] = None) -> List[dict]:
    lib = load()
    stations = lib["stations"]
    if category:
        stations = [st for st in stations if st.get("category") == category]
    return stations


def find_station(query: str) -> Optional[dict]:
    q = query.lower()
    lib = load()

    for st in lib["stations"]:
        if st["id"] == q or st["name"].lower() == q:
            return st

    for st in lib["stations"]:
        if q in st["name"].lower():
            return st

    return None


def add_station(
    *,
    name: str,
    url: str,
    category: Optional[str] = None,
    tags: Optional[List[str]] = None,
    stream: Optional[dict] = None,
    source: Optional[dict] = None,
    allow_existing: bool = False,
) -> dict:
    lib = load()
    station_id = _normalize_id(name)

    existing = next((s for s in lib["stations"] if s["id"] == station_id), None)
    if existing:
        if allow_existing:
            return existing
        raise ValueError(
            f"Station ID collision: '{station_id}'. Rename the station or edit the existing one."
        )

    st = _normalize_station(
        {
            "id": station_id,
            "name": name,
            "url": url,
            "category": category,
            "tags": tags or [],
            "stream": stream or {},
            "source": source or {"type": "manual", "origin": "user"},
            "added_at": _now(),
        }
    )

    lib["stations"].append(st)
    save(lib)
    return st


def update_station(station_id: str, updates: dict) -> dict:
    lib = load()

    for i, st in enumerate(lib["stations"]):
        if st["id"] == station_id:
            updates = dict(updates)
            updates.pop("id", None)
            st.update(updates)
            lib["stations"][i] = _normalize_station(st)
            save(lib)
            return lib["stations"][i]

    raise KeyError(f"Station '{station_id}' not found")


def remove_station(station_id: str) -> bool:
    lib = load()
    before = len(lib["stations"])
    lib["stations"] = [st for st in lib["stations"] if st["id"] != station_id]

    if len(lib["stations"]) == before:
        return False

    save(lib)
    return True


def record_play(station_id: str):
    lib = load()

    for st in lib["stations"]:
        if st["id"] == station_id:
            st["last_played"] = _now()
            st["play_count"] += 1
            save(lib)
            return


def add_discovered_station(st: dict) -> dict:
    """Add a station dict returned by RadioBrowser discovery to the library."""
    tags = st.get("tags") or ""
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    return add_station(
        name=st.get("name") or "Unknown",
        url=st["url"],
        tags=tags,
        stream={
            "codec": st.get("codec"),
            "bitrate": st.get("bitrate"),
            "country": st.get("country"),
            "validated": False,
            "last_checked": None,
        },
        source={"type": "radiobrowser", "origin": st.get("stationuuid")},
        allow_existing=True,
    )
