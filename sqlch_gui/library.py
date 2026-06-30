"""Station library CRUD, frequency pool management, and station list."""

import json
import re
import subprocess
from pathlib import Path

from . import FREQ_CACHE_JSON, LIBRARY_JSON

_KNOWN_FREQUENCIES: dict[str, float] = {
    "wxpn": 88.5,
    "wrti": 90.1,
    "whyy": 90.9,
    "wmmr": 93.3,
    "wip": 94.1,
    "wusl": 98.9,
    "wmgk": 102.9,
    "wnrw": 105.7,
}

_PHILLY_FREQ_POOL: list[float] = [
    88.1,
    88.5,
    88.9,
    89.3,
    89.7,
    90.1,
    90.5,
    90.9,
    91.3,
    91.7,
    92.1,
    92.5,
    92.9,
    93.3,
    93.7,
    94.1,
    94.5,
    94.9,
    95.3,
    95.7,
    96.1,
    96.5,
    96.9,
    97.3,
    97.7,
    98.1,
    98.5,
    98.9,
    99.3,
    99.7,
    100.1,
    100.5,
    100.9,
    101.1,
    101.5,
    101.9,
    102.1,
    102.5,
    102.9,
    103.3,
    103.9,
    104.5,
    105.3,
    106.1,
    106.5,
    107.1,
    107.9,
]


def _load_library() -> dict:
    if not LIBRARY_JSON.exists():
        return {"stations": []}
    try:
        return json.loads(LIBRARY_JSON.read_text())
    except Exception:
        return {"stations": []}


def _save_library(data: dict):
    LIBRARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    LIBRARY_JSON.write_text(json.dumps(data, indent=2))


def _load_freq_cache() -> dict[str, float]:
    if not FREQ_CACHE_JSON.exists():
        return {}
    try:
        return json.loads(FREQ_CACHE_JSON.read_text())
    except Exception:
        return {}


def _save_freq_cache(cache: dict[str, float]):
    FREQ_CACHE_JSON.parent.mkdir(parents=True, exist_ok=True)
    FREQ_CACHE_JSON.write_text(json.dumps(cache, indent=2))


def _assign_frequency(station_id: str) -> float | None:
    for k, v in _KNOWN_FREQUENCIES.items():
        if k in station_id.lower():
            return v

    cache = _load_freq_cache()
    if station_id in cache:
        return cache[station_id]

    lib = _load_library()
    used = {s.get("frequency") for s in lib.get("stations", []) if s.get("frequency")}

    for f in _PHILLY_FREQ_POOL:
        if f not in used:
            cache[station_id] = f
            _save_freq_cache(cache)
            return f

    import random

    f = round(random.uniform(87.5, 108.0), 1)
    cache[station_id] = f
    _save_freq_cache(cache)
    return f


def get_station_list() -> list[dict]:
    """Return the list of all library stations with populated frequencies and fallback metrics."""
    lib = _load_library()
    stations = lib.get("stations", [])
    for s in stations:
        if not s.get("frequency"):
            s["frequency"] = _assign_frequency(s["id"])
        if "group" not in s:
            s["group"] = "Unsorted"
        if "bitrate" not in s:
            s["bitrate"] = None
        if "channels" not in s:
            s["channels"] = None
    return stations


def add_url(name: str, url: str) -> str | None:
    """Add a new station by tracking its unique normalized ID. Returns an error string or None."""
    if not name or not url:
        return "Name and URL are required"
    station_id = re.sub(r"[^a-z0-9_-]", "", name.lower().replace(" ", "_"))
    if not station_id:
        station_id = "station_" + str(abs(hash(url)) % 10000)

    lib = _load_library()
    if any(s["id"] == station_id for s in lib["stations"]):
        return f"Station '{name}' already exists"

    freq = _assign_frequency(station_id)
    new_station = {
        "id": station_id,
        "name": name,
        "url": url,
        "frequency": freq,
        "group": "Unsorted",
    }
    lib["stations"].append(new_station)
    _save_library(lib)
    return None


def update(station_id: str, name: str, url: str) -> bool:
    """Modify details for an existing station ID."""
    lib = _load_library()
    for s in lib["stations"]:
        if s["id"] == station_id:
            s["name"] = name
            s["url"] = url
            _save_library(lib)
            return True
    return False


def remove(station_id: str) -> bool:
    """Delete a station from the library storage array."""
    lib = _load_library()
    orig_len = len(lib["stations"])
    lib["stations"] = [s for s in lib["stations"] if s["id"] != station_id]
    if len(lib["stations"]) != orig_len:
        _save_library(lib)
        return True
    return False


def set_frequency(station_id: str, new_freq: float) -> bool:
    """Override the frequency value for a specific station."""
    lib = _load_library()
    for s in lib["stations"]:
        if s["id"] == station_id:
            s["frequency"] = round(float(new_freq), 1)
            _save_library(lib)
            cache = _load_freq_cache()
            cache[station_id] = s["frequency"]
            _save_freq_cache(cache)
            return True
    return False


def set_group(station_id: str, group: str) -> bool:
    """Assign a station to a specific display group categorization header."""
    lib = _load_library()
    for s in lib["stations"]:
        if s["id"] == station_id:
            s["group"] = group.strip() if group.strip() else "Unsorted"
            _save_library(lib)
            return True
    return False


def backfill_freqs():
    """Assign frequencies to any library stations that lack one (runs on every startup)."""
    lib = _load_library()
    changed = False
    for station in lib["stations"]:
        if station.get("frequency") is None:
            freq = _assign_frequency(station["id"])
            if freq is not None:
                station["frequency"] = freq
                changed = True
    if changed:
        _save_library(lib)