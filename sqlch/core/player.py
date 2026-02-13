from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from sqlch.core import config, enrich, library, notify

# ------------------------------------------------------------
# Lazy cache resolution (Nix-safe)
# ------------------------------------------------------------

_CACHE_DIR: Path | None = None


def _cache_dir() -> Path:
    global _CACHE_DIR
    if _CACHE_DIR is None:
        base = os.environ.get("XDG_CACHE_HOME")
        if not base:
            base = str(Path.home() / ".cache")
        p = Path(base) / "sqlch"
        p.mkdir(parents=True, exist_ok=True)
        _CACHE_DIR = p
    return _CACHE_DIR


# ------------------------------------------------------------
# Runtime + mpv plumbing
# ------------------------------------------------------------

def runtime_dir() -> Path:
    """
    Per-user runtime directory.

    Prefer XDG_RUNTIME_DIR (systemd user session),
    fall back to /tmp for non-systemd shells.
    """
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    p = Path(base) / "sqlch"
    p.mkdir(parents=True, exist_ok=True)
    return p


def mpv_socket() -> Path:
    return runtime_dir() / "mpv.sock"


def mpv_bin() -> str:
    # Nix wrapper can export MPV_BIN; otherwise rely on PATH.
    return os.environ.get("MPV_BIN", "mpv")


def mpris_plugin() -> str | None:
    # Expect Nix wrapper to export this.
    return os.environ.get("SQLCH_MPRIS_PLUGIN")


def _need_env(name: str, value: str | None) -> str:
    if not value:
        raise RuntimeError(f"{name} is not set. (Expected Nix wrapper to export it.)")
    return value


# ------------------------------------------------------------
# State
# ------------------------------------------------------------

_current: dict[str, Any] | None = None
_preview_timer: threading.Timer | None = None
_metadata_thread: threading.Thread | None = None
_metadata_stop = threading.Event()


# ------------------------------------------------------------
# MPV IPC helpers (uses socat)
# ------------------------------------------------------------

def _mpv_ipc(cmd: dict[str, Any], timeout: float = 0.4) -> dict[str, Any] | None:
    """
    Send a JSON IPC command to mpv via its UNIX socket.
    Returns parsed JSON response (if any) or None.
    """
    sock = mpv_socket()
    if not sock.exists():
        return None

    try:
        proc = subprocess.run(
            ["socat", "-", str(sock)],
            input=(json.dumps(cmd) + "\n").encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
        if not proc.stdout:
            return None
        return json.loads(proc.stdout.decode("utf-8", errors="replace"))
    except Exception:
        return None


def mpv_get(prop: str) -> Any:
    resp = _mpv_ipc({"command": ["get_property", prop]})
    if resp and resp.get("error") == "success":
        return resp.get("data")
    return None


def mpv_command(*parts: Any) -> None:
    _mpv_ipc({"command": list(parts)})


def mpv_set_userdata(key: str, value: Any) -> None:
    """
    Store metadata into mpv user-data namespace. mpv-mpris reads user-data/*.
    """
    if value is None:
        return
    mpv_command("set_property_string", f"user-data/{key}", str(value))


def _wait_for_ipc(timeout: float = 2.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if mpv_socket().exists():
            if _mpv_ipc({"command": ["get_property", "pid"]}):
                return True
        time.sleep(0.05)
    return False


# ------------------------------------------------------------
# Metadata / enrichment
# ------------------------------------------------------------

def _parse_icy(title: str) -> tuple[str | None, str | None]:
    if not title or "-" not in title:
        return (None, None)
    artist, track = title.split("-", 1)
    artist = artist.strip() or None
    track = track.strip() or None
    return (artist, track)


def _apply_enrichment_now(artist: str | None, track: str, station_name: str) -> None:
    meta = enrich.enrich_track(artist or "", track)

    mpv_set_userdata("title", track)
    if artist:
        mpv_set_userdata("artist", artist)

    mpv_set_userdata("album", meta.get("album") or station_name)

    year = meta.get("year")
    if year:
        mpv_set_userdata("date", year)

    genres = meta.get("genres")
    if genres:
        mpv_set_userdata("genre", ", ".join(genres))


def _watch_metadata(station_name: str) -> None:
    """
    Poll MPV metadata and re-apply enrichment whenever icy-title changes.
    """
    _metadata_stop.clear()
    last_seen: str | None = None

    # Ask mpv to start tracking; harmless if it ignores.
    _mpv_ipc({"command": ["observe_property", 1, "metadata"]})

    while not _metadata_stop.is_set():
        meta = mpv_get("metadata")
        if not meta:
            time.sleep(0.5)
            continue

        icy = meta.get("icy-title") or meta.get("title")
        if icy and icy != last_seen:
            last_seen = icy
            artist, track = _parse_icy(icy)
            if track:
                try:
                    _apply_enrichment_now(artist, track, station_name)
                except Exception:
                    # never kill metadata thread
                    pass

        time.sleep(0.5)


# ------------------------------------------------------------
# Process lifecycle
# ------------------------------------------------------------

def _send_quit() -> None:
    # Important: mpv_socket() is a function.
    if not mpv_socket().exists():
        return
    try:
        _mpv_ipc({"command": ["quit"]}, timeout=0.3)
    except Exception:
        pass


def _cleanup_socket() -> None:
    sock = mpv_socket()
    try:
        if sock.exists():
            sock.unlink()
    except Exception:
        pass


def _kill_existing() -> None:
    """
    Try to gracefully quit mpv via IPC, then clean up stale socket,
    then pkill any mpv process still holding that socket path.
    """
    global _metadata_thread

    _metadata_stop.set()
    _send_quit()
    _cleanup_socket()

    sock = mpv_socket()
    subprocess.run(
        ["pkill", "-f", f"mpv.*{sock}"],
        stderr=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        check=False,
    )
    _metadata_thread = None


def _spawn_mpv(url: str, *, video: bool = False, preview: bool = False) -> None:
    """
    Start mpv detached, with IPC enabled and MPRIS plugin loaded.
    """
    mpris = _need_env("SQLCH_MPRIS_PLUGIN", mpris_plugin())

    sock = mpv_socket()
    sock.parent.mkdir(parents=True, exist_ok=True)

    args: list[str] = [
        mpv_bin(),
        f"--input-ipc-server={sock}",
        f"--script={mpris}",
        "--idle=yes",
        "--force-window=no",
        "--no-terminal",
        "--cache=yes",
    ]

    if not video:
        args.append("--no-video")
    if preview:
        args.append("--volume=60")

    args.append(url)

    subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


# ------------------------------------------------------------
# Public API
# ------------------------------------------------------------

def stop() -> None:
    global _current, _preview_timer

    if _preview_timer:
        _preview_timer.cancel()
        _preview_timer = None

    _kill_existing()
    _current = None
    notify.notify("sqlch", "Playback stopped")


def pause() -> None:
    sock = mpv_socket()
    if not sock.exists():
        return

    # mpv also accepts command mode text over IPC; this is fine.
    try:
        subprocess.run(
            ["socat", "-", str(sock)],
            input=b"cycle pause\n",
            timeout=0.2,
            stderr=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            check=False,
        )
    except Exception:
        pass


def play_station(station: dict[str, Any]) -> None:
    global _current, _metadata_thread

    url = station.get("url")
    if not url:
        notify.notify("sqlch error", "Station missing URL")
        return

    stop()
    notify.notify("Now Playing", station.get("name", "Unknown Station"))

    _spawn_mpv(url)
    _current = {"type": "station", "item": station}

    sid = station.get("id")
    if sid is not None:
        library.record_play(sid)

    if _wait_for_ipc():
        _metadata_thread = threading.Thread(
            target=_watch_metadata,
            args=(station.get("name", "Station"),),
            daemon=True,
        )
        _metadata_thread.start()


def preview(url: str, duration: int = 12) -> None:
    global _preview_timer

    stop()
    _spawn_mpv(url, preview=True)

    def _end_preview() -> None:
        stop()

    _preview_timer = threading.Timer(duration, _end_preview)
    _preview_timer.daemon = True
    _preview_timer.start()


def current() -> dict[str, Any] | None:
    return _current


def status_string() -> str:
    if mpv_socket().exists():
        d = config.load()
        lp = d.get("last_played")
        if lp:
            return f"Now playing: {lp.get('name')}"
        return "Now playing"
    return "sqlch: Not Playing"
