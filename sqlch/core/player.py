import os
import time
import json
import threading
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from sqlch.core import config, notify, enrich, library

# ------------------------------------------------------------
# Constants / globals
# ------------------------------------------------------------

SOCKET = Path("/tmp/sqlch-mpv.sock")
MPV_BIN = os.environ.get("MPV_BIN", "mpv")

MPRIS_PLUGIN = (
    "/nix/store/jh3yklrqbzi8lv0765g332cs11wp91pm-mpv-mpris-1.1"
    "/share/mpv/scripts/mpris.so"
)

_current = None
_preview_timer = None

_metadata_thread: Optional[threading.Thread] = None
_metadata_stop = threading.Event()

# ------------------------------------------------------------
# IPC helpers
# ------------------------------------------------------------

def _mpv_ipc(cmd: dict, timeout: float = 0.4) -> Optional[dict]:
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


def _wait_for_ipc(timeout: float = 2.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if SOCKET.exists():
            if _mpv_ipc({"command": ["get_property", "pid"]}):
                return True
        time.sleep(0.05)
    return False


# ------------------------------------------------------------
# Metadata parsing
# ------------------------------------------------------------

def _parse_icy
