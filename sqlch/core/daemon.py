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
import threading
from pathlib import Path
from typing import Any
from sqlch.core import library, notify, player, discover, config

def runtime_dir() -> Path:
    base = os.environ.get('XDG_RUNTIME_DIR') or '/tmp'
    p = Path(base) / 'sqlch'
    p.mkdir(parents=True, exist_ok=True)
    return p

def control_sock() -> Path:
    return runtime_dir() / "control.sock"

def _reply(conn: socket.socket, obj: dict[str, Any]):
    data = (json.dumps(obj) + '\n').encode()
    conn.sendall(data)

def _handle(msg: dict[str, Any]) -> dict[str, Any]:
    cmd = msg.get('cmd')
    if cmd == 'ping':
        return {'ok': True, 'msg': 'pong'}
    if cmd == 'status':
        return {'ok': True, 'status': player.status_string(), 'current': player.current()}
    if cmd == 'stop':
        player.stop()
        return {'ok': True}
    if cmd == 'pause':
        player.pause()
        return {'ok': True}
    if cmd == 'play':
        q = (msg.get('query') or '').strip()
        if not q:
            return {'ok': False, 'error': 'missing query'}
        st = library.resolve_station(q)
        if not st:
            results = discover.search(q)
            if len(results) == 1:
                st = library.add_station(results[0])
            else:
                return {'ok': False, 'error': f'could not resolve: {q}', 'results': results[:10]}
        player.play_station(st)
        return {'ok': True, 'station': {'id': st.get('id'), 'name': st.get('name')}}
    if cmd == 'preview':
        url = (msg.get('url') or '').strip()
        if not url:
            return {'ok': False, 'error': 'missing url'}
        dur = int(msg.get('duration') or 12)
        player.preview(url, duration=dur)
        return {'ok': True}
    return {'ok': False, 'error': f'unknown cmd: {cmd}'}

def run_daemon():
    sock = control_sock()
    print("RUN_DAEMON ENTERED", sock, flush=True)

    try:
        if sock.exists():
            sock.unlink()
    except Exception:
        pass

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(sock))
    os.chmod(sock, 0o600)
    srv.listen(16)

    while True:
        conn, _ = srv.accept()
        try:
            buf = b''
            while not buf.endswith(b'\n'):
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
            if not buf:
                _reply(conn, {'ok': False, 'error': 'empty request'})
                continue
            msg = json.loads(buf.decode('utf-8', errors='replace'))
            resp = _handle(msg)
            _reply(conn, resp)
        except Exception as e:
            _reply(conn, {'ok': False, 'error': str(e)})
        finally:
            try:
                conn.close()
            except Exception:
                pass
