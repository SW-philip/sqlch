"""Watch progress for video items: one small JSON file in data_dir().

Same ownership rules as follows.py: the daemon is the only writer, the gui
reads the file directly, every write replaces it atomically."""

import json
import logging
import os
import tempfile
import threading
import time

from sqlch.core.paths import data_dir

log = logging.getLogger(__name__)

FILE = "watch_progress.json"
WATCHED_FRACTION = 0.9
MIN_RESUME_SECS = 15  # earlier than this "continue" isn't worth offering

_lock = threading.Lock()


def key(source: str, id: str) -> str:
    return f"{source}:{id}"


def _path():
    return data_dir() / FILE


def read_all() -> dict:
    """Read-only view for any process: never renames or writes."""
    try:
        data = json.loads(_path().read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        log.error("can't read %s: %s", FILE, e)
        return {}
    return data if isinstance(data, dict) else {}


def _write(rows: dict) -> None:
    path = _path()
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=FILE + ".")
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


def get(source: str, id: str) -> dict | None:
    row = read_all().get(key(source, id))
    return row if isinstance(row, dict) else None


def resume_point(row: dict | None) -> float | None:
    """Where to continue from, or None when there is nothing to resume."""
    if not row or row.get("watched"):
        return None
    pos = row.get("position")
    if not isinstance(pos, (int, float)) or pos < MIN_RESUME_SECS:
        return None
    return float(pos)


def fraction(row: dict | None) -> float:
    if not row:
        return 0.0
    if row.get("watched"):
        return 1.0
    pos, dur = row.get("position"), row.get("duration")
    if not isinstance(pos, (int, float)) or not isinstance(dur, (int, float)) or dur <= 0:
        return 0.0
    return max(0.0, min(1.0, pos / dur))


def record(source: str, id: str, position: float, duration: float | None) -> None:
    """Store the playhead. Crossing WATCHED_FRACTION marks the video watched;
    that flag is sticky so re-watching the intro never un-watches it."""
    if not isinstance(position, (int, float)) or position < 0:
        return
    with _lock:
        rows = read_all()
        row = rows.get(key(source, id))
        row = row if isinstance(row, dict) else {}
        if row.get("watched"):
            return
        dur = duration if isinstance(duration, (int, float)) and duration > 0 \
            else row.get("duration")
        watched = bool(dur and position >= dur * WATCHED_FRACTION)
        rows[key(source, id)] = {"position": 0 if watched else float(position),
                                 "duration": dur, "watched": watched,
                                 "updated": time.time()}
        _write(rows)


def mark(source: str, id: str, watched: bool) -> None:
    with _lock:
        rows = read_all()
        row = rows.get(key(source, id))
        row = row if isinstance(row, dict) else {}
        rows[key(source, id)] = {"position": 0, "duration": row.get("duration"),
                                 "watched": watched, "updated": time.time()}
        _write(rows)
