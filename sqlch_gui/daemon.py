"""sqlch control socket + MPV IPC queries."""

import json
import socket
import subprocess

from . import CONTROL_SOCK, MPV_SOCK


def send(msg: dict) -> dict | None:
    """Send a command JSON message to the main sqlch UNIX domain control socket."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.settimeout(1.5)
        s.connect(str(CONTROL_SOCK))
        s.sendall((json.dumps(msg) + "\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        return json.loads(data.decode("utf-8", errors="replace"))
    except Exception:
        return None
    finally:
        s.close()


def get_vol_state() -> tuple[float, bool]:
    """Return (volume_float, muted) from wpctl. Falls back to (0.0, False) on error."""
    try:
        r = subprocess.run(
            ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        line = r.stdout.strip()
        parts = line.split()
        vol = float(parts[1]) if len(parts) >= 2 else 0.0
        muted = "[MUTED]" in line or "[BAR]" in line
        return vol, muted
    except Exception:
        return 0.0, False


def get_bt_active() -> bool:
    """Return True if any bluez_output sink node exists in PipeWire."""
    try:
        r = subprocess.run(["pw-dump"], capture_output=True, text=True, timeout=1)
        return "bluez_output" in r.stdout
    except Exception:
        return False


def _mpv_get_property(prop: str):
    if not MPV_SOCK.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(str(MPV_SOCK))
            s.sendall((json.dumps({"command": ["get_property", prop]}) + "\n").encode())
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
        if buf.strip():
            resp = json.loads(buf.decode())
            if resp.get("error") == "success":
                return resp.get("data")
    except Exception:
        pass
    return None


def get_stream_bitrate() -> int | None:
    """Return stream bitrate in kbps from MPV audio-bitrate property, or None."""
    val = _mpv_get_property("audio-bitrate")
    if val is not None:
        try:
            v = int(float(val))
            return v // 1000 if v > 1000 else v
        except (ValueError, TypeError):
            pass
    return None


def get_stream_channels() -> int | None:
    """Return channel count from MPV (1 = mono, 2 = stereo), or None."""
    val = _mpv_get_property("audio-params/channel-count")
    if val is not None:
        try:
            return int(val)
        except (ValueError, TypeError):
            pass
    return None


def get_stream_format() -> str | None:
    """Return the short audio codec name (e.g. 'mp3', 'aac') from MPV, or None."""
    val = _mpv_get_property("audio-codec-name")
    if val:
        return str(val).upper()
    return None