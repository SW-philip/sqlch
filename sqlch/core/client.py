# sqlch/core/client.py
import json
import os
import socket
from pathlib import Path
from typing import Any

def runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return Path(base) / "sqlch"

CONTROL_SOCK = runtime_dir() / "control.sock"

def daemon_available() -> bool:
    return CONTROL_SOCK.exists()

def send(msg: dict[str, Any], timeout: float = 1.5) -> dict[str, Any]:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(str(CONTROL_SOCK))
    s.sendall((json.dumps(msg) + "\n").encode())
    data = b""
    while not data.endswith(b"\n"):
        chunk = s.recv(4096)
        if not chunk:
            break
        data += chunk
    s.close()
    if not data:
        return {"ok": False, "error": "no response"}
    return json.loads(data.decode("utf-8", errors="replace"))
