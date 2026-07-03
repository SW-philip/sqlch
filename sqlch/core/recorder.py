"""Stream recording via mpv stream-record: session state + finalize pipeline.

The daemon owns at most one recording at a time. mpv dumps the raw stream
bytes (bit-perfect, no re-encode) into <recordings_dir>/.incoming/; on
finalize each dump is remuxed losslessly (ffmpeg -c copy) into a tagged
file under <recordings_dir>/<Station>/.

Import-cycle note: player.py calls into this module, so mpv access here goes
through the lazy _mpv() accessor instead of a top-level import.
"""

from __future__ import annotations

import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlch.core import config, notify

_CODEC_EXT = {
    "aac": ".m4a",
    "mp3": ".mp3",
    "vorbis": ".ogg",
    "opus": ".opus",
}
_FALLBACK_EXT = ".mka"

_lock = threading.Lock()
_session: dict[str, Any] | None = None


def _mpv():
    from sqlch.core import player
    return player


# ------------------------------------------------------------
# Paths + naming
# ------------------------------------------------------------

def recordings_dir() -> Path:
    d = config.load().get("recordings_dir")
    p = Path(d).expanduser() if d else Path.home() / "Music" / "radio"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _staging_dir() -> Path:
    p = recordings_dir() / ".incoming"
    p.mkdir(parents=True, exist_ok=True)
    return p


def sanitize_filename(name: str) -> str:
    """Make a station/track string safe as a single path component."""
    name = "".join(c for c in name if c.isprintable())
    for sep in ("/", "\\", ":"):
        name = name.replace(sep, "-")
    name = " ".join(name.split())
    name = name.strip("-. ")
    return name[:120] or "untitled"


def ext_for_codec(codec: str | None) -> str:
    return _CODEC_EXT.get((codec or "").lower(), _FALLBACK_EXT)


def unique_path(dest: Path) -> Path:
    if not dest.exists():
        return dest
    for i in range(2, 1000):
        cand = dest.with_name(f"{dest.stem} ({i}){dest.suffix}")
        if not cand.exists():
            return cand
    return dest.with_name(f"{dest.stem} ({int(time.time())}){dest.suffix}")


def format_tracklist(entries: list[tuple[float, str | None, str | None]]) -> str:
    lines = []
    for elapsed, artist, title in entries:
        m, s = divmod(int(elapsed), 60)
        who = f"{artist} - {title}" if artist else (title or "Unknown")
        lines.append(f"[{m:02d}:{s:02d}] {who}")
    return "\n".join(lines) + ("\n" if lines else "")


# ------------------------------------------------------------
# Finalize: raw dump -> tagged file
# ------------------------------------------------------------

def _probe_codec(path: Path) -> str | None:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        out = r.stdout.strip().splitlines()
        return out[0].strip() or None if out else None
    except Exception:
        return None


def _remux(raw: Path, dest: Path, tags: dict[str, str]) -> bool:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-i", str(raw), "-map", "0:a", "-c", "copy"]
    for k, v in tags.items():
        if v:
            cmd += ["-metadata", f"{k}={v}"]
    cmd.append(str(dest))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return r.returncode == 0 and dest.exists() and dest.stat().st_size > 0
    except Exception:
        return False


def _finalize(
    raw: Path,
    station_name: str,
    tags: dict[str, str],
    stem: str,
    partial: bool = False,
) -> Path | None:
    """Remux one closed raw dump into its tagged final file.

    Returns the final path, or None (failure keeps the raw for salvage;
    empty raws are discarded silently).
    """
    try:
        if not raw.exists() or raw.stat().st_size == 0:
            raw.unlink(missing_ok=True)
            return None
        codec = _probe_codec(raw)
        if partial:
            stem += " (partial)"
        dest_dir = recordings_dir() / sanitize_filename(station_name)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = unique_path(dest_dir / (sanitize_filename(stem) + ext_for_codec(codec)))
        if _remux(raw, dest, tags):
            raw.unlink(missing_ok=True)
            return dest
        notify.notify("sqlch record",
                      f"Could not finalize '{stem}' — raw kept in {raw.parent}")
        return None
    except Exception:
        notify.notify("sqlch record", f"Finalize error for '{stem}'")
        return None


# ------------------------------------------------------------
# Session state machine (daemon-side singleton)
# ------------------------------------------------------------

_finalizers: list[threading.Thread] = []


def _spawn_finalizer(target, *args) -> None:
    t = threading.Thread(target=target, args=args, daemon=True)
    _finalizers.append(t)
    t.start()


def _join_finalizers(timeout: float = 10.0) -> None:
    """Test hook: wait for background finalize threads."""
    for t in list(_finalizers):
        t.join(timeout)
    _finalizers.clear()


def _raw_path(started_at: datetime, seq: int) -> Path:
    return _staging_dir() / f"rec-{started_at:%Y%m%d-%H%M%S}-{seq}.dump"


def start(mode: str, station: dict[str, Any] | None) -> dict[str, Any]:
    global _session
    if mode not in ("full", "track"):
        return {"ok": False, "error": f"unknown mode: {mode}"}
    p = _mpv()
    with _lock:
        if _session:
            return {"ok": False, "error": "already recording",
                    "recording": _status_locked()}
        if not p.mpv_socket().exists() or p.mpv_get("pid") is None:
            return {"ok": False, "error": "nothing playing"}

        station = station or {}
        started_at = datetime.now()
        raw = _raw_path(started_at, 0)
        p.mpv_command("set_property", "stream-record", str(raw))

        artist = title = None
        meta = p.mpv_get("metadata") or {}
        icy = meta.get("icy-title") or meta.get("title")
        if icy:
            artist, title = p._parse_icy(icy)
        fmeta = p.mpv_get("filtered-metadata") or {}
        genre = fmeta.get("icy-genre") or fmeta.get("genre")

        _session = {
            "mode": mode,
            "station": station,
            "started": time.monotonic(),
            "started_at": started_at,
            "raw": raw,
            "seq": 0,
            "tracklist": [],
            "current_track": (artist, title),
            "first_file": True,
            "icy_genre": genre,
        }
        if title:
            _session["tracklist"].append((0.0, artist, title))
    notify.notify("sqlch record",
                  f"Recording ({mode})\n{station.get('name', 'station')}")
    return {"ok": True, "recording": status()}


def on_track_change(artist: str | None, title: str | None) -> None:
    """Called by the daemon's metadata watcher on every ICY title change."""
    with _lock:
        if not _session:
            return
        elapsed = time.monotonic() - _session["started"]
        prev_track = _session["current_track"]
        _session["current_track"] = (artist, title)
        _session["tracklist"].append((elapsed, artist, title))
        if _session["mode"] != "track":
            return
        p = _mpv()
        _session["seq"] += 1
        new_raw = _raw_path(_session["started_at"], _session["seq"])
        old_raw = _session["raw"]
        p.mpv_command("set_property", "stream-record", str(new_raw))
        _session["raw"] = new_raw
        partial = _session["first_file"]
        _session["first_file"] = False
        station_name = _session["station"].get("name", "Station")
    _spawn_finalizer(_finalize_track, old_raw, station_name, prev_track, partial)


def stop() -> dict[str, Any]:
    global _session
    with _lock:
        if not _session:
            return {"ok": False, "error": "not recording"}
        sess = _session
        _session = None
    p = _mpv()
    if p.mpv_socket().exists():
        p.mpv_command("set_property", "stream-record", "")
        time.sleep(0.2)  # give mpv a beat to flush + close the dump

    station_name = sess["station"].get("name", "Station")
    if sess["mode"] == "track":
        last_partial = True  # stop always cuts the playing song short
        _spawn_finalizer(_finalize_track, sess["raw"], station_name,
                         sess["current_track"], last_partial)
    else:
        _spawn_finalizer(_finalize_session, sess, station_name)
    notify.notify("sqlch record", "Recording stopped")
    return {"ok": True}


def status() -> dict[str, Any]:
    with _lock:
        return _status_locked()


def _status_locked() -> dict[str, Any]:
    if not _session:
        return {"active": False}
    return {
        "active": True,
        "mode": _session["mode"],
        "elapsed": int(time.monotonic() - _session["started"]),
        "file": str(_session["raw"]),
        "station": _session["station"].get("name"),
    }


# ------------------------------------------------------------
# Per-mode finalize wrappers (run on background threads)
# ------------------------------------------------------------

def _finalize_track(
    raw: Path,
    station_name: str,
    track: tuple[str | None, str | None],
    partial: bool,
) -> None:
    artist, title = track
    stem = f"{artist} - {title}" if artist and title else (title or raw.stem)
    tags = {
        "artist": artist or "",
        "title": title or "",
        "album": station_name,
        "comment": f"Recorded from {station_name} by sqlch",
    }
    if artist and title:
        try:
            from sqlch.core import enrich
            meta = enrich.enrich_track(artist, title)
            if meta.get("album"):
                tags["album"] = meta["album"]
            if meta.get("year"):
                tags["date"] = str(meta["year"])
            if meta.get("genres"):
                tags["genre"] = ", ".join(meta["genres"])
        except Exception:
            pass
    _finalize(raw, station_name, tags, stem, partial=partial)


def _finalize_session(sess: dict[str, Any], station_name: str) -> None:
    stamp = f"{sess['started_at']:%Y-%m-%d %H%M}"
    stem = f"{station_name} - {stamp}"
    tags = {
        "title": stem,
        "artist": station_name,
        "album": station_name,
        "date": f"{sess['started_at']:%Y-%m-%d}",
        "genre": sess.get("icy_genre") or "",
        "comment": "Recorded by sqlch",
    }
    dest = _finalize(sess["raw"], station_name, tags, stem)
    if dest and sess["tracklist"]:
        try:
            dest.with_suffix(".tracklist.txt").write_text(
                format_tracklist(sess["tracklist"])
            )
        except Exception:
            pass
