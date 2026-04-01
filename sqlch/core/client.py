import json
import socket
from pathlib import Path
from typing import Any

from sqlch.core.paths import runtime_dir


def _control_sock() -> Path:
    return runtime_dir() / 'control.sock'


def daemon_available() -> bool:
    return _control_sock().exists()


def send(msg: dict[str, Any], timeout: float = 1.5) -> dict[str, Any]:
    sock = _control_sock()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(str(sock))
        s.sendall((json.dumps(msg) + '\n').encode())
        data = b''
        while not data.endswith(b'\n'):
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
    if not data:
        return {'ok': False, 'error': 'no response'}
    return json.loads(data.decode('utf-8', errors='replace'))
