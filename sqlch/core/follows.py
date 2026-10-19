"""Favorites and followed YouTube channels: small JSON files in data_dir().

The daemon is the only writer. Every write replaces the file atomically, so
the gui can read these files directly without a lock."""

import json
import logging
import os
import tempfile
import threading

from sqlch.core.paths import data_dir

log = logging.getLogger(__name__)

FAVORITES = "favorites.json"
FOLLOWS = "youtube_follows.json"

_lock = threading.Lock()  # serializes read-modify-write between daemon threads


def _path(name: str):
    return data_dir() / name


def _quarantine(path) -> None:
    log.error("%s is unreadable; moving it to %s.bad", path, path.name)
    try:
        os.replace(path, path.with_name(path.name + ".bad"))
    except OSError:
        pass


def _read(name: str) -> list:
    path = _path(name)
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        _quarantine(path)
        return []
    if not isinstance(data, list):
        _quarantine(path)
        return []
    return data


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
        rows = _read(FAVORITES)
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
        rows = _read(FOLLOWS)
        if any(isinstance(r, dict) and r.get("channel_id") == channel_id for r in rows):
            return
        rows.append({"channel_id": channel_id, "name": name,
                     "last_video_id": None, "last_checked": None})
        _write(FOLLOWS, rows)


def unfollow(channel_id: str) -> None:
    with _lock:
        rows = _read(FOLLOWS)
        kept = [r for r in rows
                if not (isinstance(r, dict) and r.get("channel_id") == channel_id)]
        if len(kept) != len(rows):
            _write(FOLLOWS, kept)


def record_seen(channel_id: str, video_id: str | None, checked: float) -> None:
    with _lock:
        rows = _read(FOLLOWS)
        for r in rows:
            if isinstance(r, dict) and r.get("channel_id") == channel_id:
                r["last_video_id"] = video_id
                r["last_checked"] = checked
                _write(FOLLOWS, rows)
                return
