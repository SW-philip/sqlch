# ------------------------------------------------------------
# Lazy cache resolution (Nix-safe)
# ------------------------------------------------------------

_CACHE_DIR = None

def _cache_dir():
    global _CACHE_DIR
    if _CACHE_DIR is None:
        import os
        from pathlib import Path
        base = os.environ.get("XDG_CACHE_HOME")
        if not base:
            base = str(Path.home() / ".cache")
        p = Path(base) / "sqlch"
        p.mkdir(parents=True, exist_ok=True)
        _CACHE_DIR = p
    return _CACHE_DIR

import json
import subprocess

def _mpv_ipc(cmd: dict, timeout: float=0.3):
    """
    Send a JSON IPC command to mpv and return parsed response.
    Returns None on failure.
    """
    if not SOCKET.exists():
        return None
    try:
        proc = subprocess.run(['socat', '-', str(SOCKET)], input=(json.dumps(cmd) + '\n').encode(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout)
        if not proc.stdout:
            return None
        return json.loads(proc.stdout.decode())
    except Exception:
        return None