import os
import time
import json
import threading
import subprocess
from pathlib import Path

from sqlch.core import config, notify, enrich, library

SOCKET = Path("/tmp/sqlch-mpv.sock")
MPV_BIN = os.environ.get("MPV_BIN", "mpv")
_preview_timer = None

MPRIS_PLUGIN = (
    "/nix/store/jh3yklrqbzi8lv0765g332cs11wp91pm-mpv-mpris-1.1"
    "/share/mpv/scripts/mpris.so"
)

_current = None


# ------------------------------------------------------------
# IPC helpers
# ------------------------------------------------------------

def _mpv_ipc(cmd: dict, timeout: float = 0.3):
    if not SOCKET.exists():
        return None
    try:
        proc = subprocess.run(
            ["socat", "-", str(SOCKET)],
            input=(json.dumps(cmd) + "\n").encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
        if proc.stdout:
            return json.loads(proc.stdout.decode())
    except Exception:
        pass
    return None


def mpv_get(prop: str):
    resp = _mpv_ipc({"command": ["get_property", prop]})
    if resp and resp.get("error") == "success":
        return resp.get("data")
    return None


def mpv_set(prop: str, value):
    if value is None:
        return
    _mpv_ipc({
        "command": ["set_property", f"metadata/{prop}", value]
    })


def _wait_for_ipc(timeout=2.0):
    start = time.time()
    while time.time() - start < timeout:
        if SOCKET.exists():
            if _mpv_ipc({"command": ["get_property", "pid"]}):
                return True
        time.sleep(0.05)
    return False


# ------------------------------------------------------------
# Metadata helpers
# ------------------------------------------------------------

def _parse_icy(title: str):
    if not title or "-" not in title:
        return None, None
    artist, track = title.split("-", 1)
    return artist.strip() or None, track.strip() or None


def apply_enrichment(station_name: str):
    raw = mpv_get("media-title")
    if not raw:
        return

    artist, track = _parse_icy(raw)
    if not track:
        return

    meta = enrich.enrich_track(artist or "", track)

    mpv_set("title", track)
    if artist:
        mpv_set("artist", artist)

    mpv_set("album", meta.get("album") or station_name)

    if meta.get("year"):
        mpv_set("date", meta["year"])
    if meta.get("genres"):
        mpv_set("genre", ", ".join(meta["genres"]))


# ------------------------------------------------------------
# mpv lifecycle
# ------------------------------------------------------------

def _kill_existing():
    if SOCKET.exists():
        try:
            subprocess.run(
                ["socat", "-", str(SOCKET)],
                input=b"quit\n",
                timeout=0.3,
            )
        except Exception:
            pass
        try:
            SOCKET.unlink()
        except Exception:
            pass

    subprocess.run(
        ["pkill", "-f", f"mpv.*{SOCKET}"],
        stderr=subprocess.DEVNULL,
    )


def _spawn_mpv(url, *, video=False, preview=False):
    args = [
        MPV_BIN,
        f"--input-ipc-server={SOCKET}",
        "--script=" + MPRIS_PLUGIN,
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

def stop():
    global _current, _preview_timer
    if _preview_timer:
        _preview_timer.cancel()
        _preview_timer = None

    _kill_existing()
    _current = None
    notify.notify("sqlch", "Playback stopped")


def pause():
    if SOCKET.exists():
        subprocess.run(
            ["socat", "-", str(SOCKET)],
            input=b"cycle pause\n",
            timeout=0.2,
            stderr=subprocess.DEVNULL,
        )


def play_station(station):
    global _current

    if not station.get("url"):
        notify.notify("sqlch error", "Station missing URL")
        return

    stop()
    notify.notify("Now Playing", station["name"])
    _spawn_mpv(station["url"])

    _current = {"type": "station", "item": station}
    library.record_play(station["id"])

    if _wait_for_ipc():
        apply_enrichment(station["name"])

def preview(url, duration=12):
    global _preview_timer

    stop()

    _spawn_mpv(url, preview=True)

    def _end_preview():
        stop()

    _preview_timer = threading.Timer(duration, _end_preview)
    _preview_timer.daemon = True
    _preview_timer.start()

def current():
    return _current


def status_string():
    if SOCKET.exists():
        d = config.load()
        lp = d.get("last_played")
        if lp:
            return f"Now playing: {lp.get('name')}"
        return "Now playing"
    return "sqlch: Not Playing"
