from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from sqlch.core import enrich, library, notify
from sqlch.core.paths import runtime_dir


# ------------------------------------------------------------
# Runtime + mpv plumbing
# ------------------------------------------------------------

def mpv_socket() -> Path:
    return runtime_dir() / "mpv.sock"


def mpv_bin() -> str:
    return os.environ.get("MPV_BIN", "mpv")


def mpris_plugin() -> str | None:
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
# MPV IPC helpers
# ------------------------------------------------------------

def _mpv_ipc(cmd: dict[str, Any], timeout: float = 0.5) -> dict[str, Any] | None:
    sock = mpv_socket()
    if not sock.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(str(sock))
            s.sendall((json.dumps(cmd) + "\n").encode())
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
        if buf.strip():
            return json.loads(buf.decode())
    except Exception:
        return None
    return None


def mpv_get(prop: str) -> Any:
    resp = _mpv_ipc({"command": ["get_property", prop]})
    if resp and resp.get("error") == "success":
        return resp.get("data")
    return None


def mpv_command(*parts: Any) -> None:
    _mpv_ipc({"command": list(parts)})


def mpv_set_userdata(key: str, value: Any) -> None:
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
# Volume fade
# ------------------------------------------------------------

def _fade_volume(target: int, steps: int = 20, duration: float = 1.0) -> None:
    """Gradually fade the main mpv volume to target over duration seconds."""
    current_vol = mpv_get("volume")
    if current_vol is None:
        return
    current_vol = float(current_vol)
    step_size = (target - current_vol) / steps
    delay = duration / steps
    for _ in range(steps):
        current_vol += step_size
        mpv_command("set_property", "volume", max(0, min(100, int(current_vol))))
        time.sleep(delay)


# ------------------------------------------------------------
# Metadata / enrichment
# ------------------------------------------------------------

def mpv_set_metadata(key: str, value: Any) -> None:
    if value is None:
        return
    mpv_command("set_property_string", f"metadata/{key}", str(value))


def _parse_icy(title: str) -> tuple[str | None, str | None]:
    if not title:
        return None, None
    if " - " in title:
        artist, track = title.split(" - ", 1)
    elif "-" in title:
        artist, track = title.split("-", 1)
    else:
        return None, title.strip()
    return artist.strip() or None, track.strip() or None


def _apply_enrichment_now(artist: str | None, track: str, station_name: str) -> None:
    meta = enrich.enrich_track(artist or "", track)
    album = meta.get("album") or station_name
    year = meta.get("year")
    genres = meta.get("genres")

    mpv_set_metadata("title", track)
    if artist:
        mpv_set_metadata("artist", artist)
    mpv_set_metadata("album", album)
    if year:
        mpv_set_metadata("date", year)
    if genres:
        mpv_set_metadata("genre", ", ".join(genres))

    mpv_set_userdata("title", track)
    if artist:
        mpv_set_userdata("artist", artist)
    mpv_set_userdata("album", album)
    if year:
        mpv_set_userdata("date", year)
    if genres:
        mpv_set_userdata("genre", ", ".join(genres))


def _watch_metadata(station_name: str) -> None:
    _metadata_stop.clear()
    last_seen: str | None = None
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
                    pass
        time.sleep(0.5)


# ------------------------------------------------------------
# Process lifecycle
# ------------------------------------------------------------

def _send_quit() -> None:
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
    mpris = _need_env("SQLCH_MPRIS_PLUGIN", mpris_plugin())
    sock = mpv_socket()
    sock.parent.mkdir(parents=True, exist_ok=True)

    args: list[str] = [
        mpv_bin(),
        f"--input-ipc-server={sock}",
        f"--script={mpris}",
        "--idle=yes",
        "--keep-open=yes",
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
    if not mpv_socket().exists():
        return
    mpv_command("cycle", "pause")


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


def preview(url: str, duration: int = 10) -> None:
    global _preview_timer

    if _preview_timer:
        _preview_timer.cancel()
        _preview_timer = None

    was_playing = _current is not None and mpv_socket().exists()

    if was_playing:
        def _ducked_preview() -> None:
            _fade_volume(20, steps=20, duration=1.0)

            proc = subprocess.Popen(
                [
                    "ffplay",
                    "-nodisp",
                    "-autoexit",
                    "-loglevel", "quiet",
                    "-t", str(duration),
                    url,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            proc.wait()
            _fade_volume(100, steps=20, duration=1.0)

        threading.Thread(target=_ducked_preview, daemon=True).start()

    else:
        stop()
        _spawn_mpv(url, preview=True)

        def _end_preview() -> None:
            stop()

        _preview_timer = threading.Timer(duration, _end_preview)
        _preview_timer.daemon = True
        _preview_timer.start()


def current() -> dict[str, Any] | None:
    return _current


def now_playing_info() -> dict:
    """Return structured now-playing info pulled from live MPV ICY metadata."""
    if not mpv_socket().exists():
        return {"status": "stopped"}

    station_name = None
    if _current:
        station_name = _current.get("item", {}).get("name")
    if not station_name:
        st = library.last_played_station()
        if st:
            station_name = st.get("name")

    meta = mpv_get("metadata") or {}
    icy = meta.get("icy-title") or meta.get("title")

    info: dict = {"status": "playing", "station": station_name}
    if icy:
        artist, track = _parse_icy(icy)
        info["artist"] = artist
        info["track"] = track
    return info


def status_string() -> str:
    info = now_playing_info()
    if info["status"] == "stopped":
        return "Not playing"
    lines = []
    if info.get("station"):
        lines.append(f"\u266b {info['station']}")
    if info.get("track"):
        artist = info.get("artist")
        track = info["track"]
        lines.append(f"  {artist} \u2014 {track}" if artist else f"  {track}")
    return "\n".join(lines) if lines else "Playing"
