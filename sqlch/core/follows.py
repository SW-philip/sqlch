"""Favorites and followed YouTube channels: small JSON files in data_dir().

The daemon is the only writer and the only one that quarantines a corrupt
file; the gui only reads. Every write replaces the file atomically, so
the gui can read these files directly without a lock."""

import json
import logging
import os
import tempfile
import threading
import time

from sqlch.core.paths import data_dir

log = logging.getLogger(__name__)

FAVORITES = "favorites.json"
FOLLOWS = "youtube_follows.json"

_lock = threading.Lock()  # serializes read-modify-write between daemon threads


def _path(name: str):
    return data_dir() / name


def _load(path) -> list:
    """Parse the store. FileNotFoundError -> []; a bad payload raises
    ValueError; any other OSError propagates."""
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return []
    if not isinstance(data, list):
        raise ValueError(f"{path.name} does not hold a list")
    return data


def _read(name: str) -> list:
    """Read-only view for any process: never renames or writes."""
    path = _path(name)
    try:
        return _load(path)
    except (OSError, ValueError) as e:
        log.error("can't read %s: %s", path, e)
        return []


def _read_for_write(name: str) -> list:
    """Daemon-side read under _lock. Corrupt content is moved aside under a
    unique name; other I/O errors raise rather than looking like an empty store."""
    path = _path(name)
    try:
        return _load(path)
    except ValueError as e:
        bad = path.with_name(f"{path.name}.{time.strftime('%Y%m%d-%H%M%S')}.bad")
        n = 1
        while bad.exists():
            bad = path.with_name(f"{path.name}.{time.strftime('%Y%m%d-%H%M%S')}-{n}.bad")
            n += 1
        log.error("%s is unreadable (%s); moving it to %s", path, e, bad.name)
        os.replace(path, bad)
        return []


def _write(name: str, rows: list) -> None:
    path = _path(name)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=name + ".")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(rows, f, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---- favorites ----

def list_favorites(source: str) -> list[dict]:
    return [r for r in _read(FAVORITES)
            if isinstance(r, dict) and r.get("source") == source]


def favorite_ids(source: str) -> set[str]:
    return {r.get("id") for r in list_favorites(source)}


def toggle_favorite(item: dict) -> bool:
    key = (item.get("source"), item.get("id"))
    if not all(key):
        raise ValueError("a favorite needs a source and an id")
    with _lock:
        rows = _read_for_write(FAVORITES)
        kept = [r for r in rows
                if not (isinstance(r, dict) and (r.get("source"), r.get("id")) == key)]
        added = len(kept) == len(rows)
        if added:
            kept.append(item)
        _write(FAVORITES, kept)
    return added


# ---- followed youtube channels ----

def list_follows() -> list[dict]:
    return [r for r in _read(FOLLOWS) if isinstance(r, dict) and r.get("channel_id")]


def followed_ids() -> set[str]:
    return {r["channel_id"] for r in list_follows()}


def follow(channel_id: str, name: str) -> None:
    with _lock:
        rows = _read_for_write(FOLLOWS)
        if any(isinstance(r, dict) and r.get("channel_id") == channel_id for r in rows):
            return
        rows.append({"channel_id": channel_id, "name": name,
                     "last_video_id": None, "last_checked": None})
        _write(FOLLOWS, rows)


def unfollow(channel_id: str) -> None:
    with _lock:
        rows = _read_for_write(FOLLOWS)
        kept = [r for r in rows
                if not (isinstance(r, dict) and r.get("channel_id") == channel_id)]
        if len(kept) != len(rows):
            _write(FOLLOWS, kept)


def record_seen(channel_id: str, video_id: str | None, checked: float) -> None:
    with _lock:
        rows = _read_for_write(FOLLOWS)
        for r in rows:
            if isinstance(r, dict) and r.get("channel_id") == channel_id:
                r["last_video_id"] = video_id
                r["last_checked"] = checked
                _write(FOLLOWS, rows)
                return
