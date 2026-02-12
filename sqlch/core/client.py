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
import os
import socket
from pathlib import Path
from typing import Any

def runtime_dir() -> Path:
    base = os.environ.get('XDG_RUNTIME_DIR') or '/tmp'
    return Path(base) / 'sqlch'
CONTROL_SOCK = runtime_dir() / 'control.sock'

def daemon_available() -> bool:
    return CONTROL_SOCK.exists()

def send(msg: dict[str, Any], timeout: float=1.5) -> dict[str, Any]:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(str(CONTROL_SOCK))
    s.sendall((json.dumps(msg) + '\n').encode())
    data = b''
    while not data.endswith(b'\n'):
        chunk = s.recv(4096)
        if not chunk:
            break
        data += chunk
    s.close()
    if not data:
        return {'ok': False, 'error': 'no response'}
    return json.loads(data.decode('utf-8', errors='replace'))