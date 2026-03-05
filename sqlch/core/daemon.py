import json
import os
import socket
import threading
from pathlib import Path
from typing import Any

from sqlch.core import library, notify, player, discover, config
from sqlch.core.paths import runtime_dir


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
        if q == '__last__':
            stations = library.list_stations()
            played = [s for s in stations if s.get('last_played')]
            if not played:
                return {'ok': False, 'error': 'no last played station'}
            st = max(played, key=lambda s: s['last_played'])
            player.play_station(st)
            return {'ok': True}
        st = library.find_station(q)
        if not st:
            results = discover.search(q)
            if len(results) == 1:
                st = library.add_station(
                    name=results[0].get('name') or 'unknown',
                    url=results[0].get('url'),
                    allow_existing=True,
                )
            else:
                return {
                    'ok': False,
                    'error': f'could not resolve: {q}',
                    'results': results[:10],
                }
        player.play_station(st)
        return {'ok': True, 'station': {'id': st.get('id'), 'name': st.get('name')}}
    if cmd == 'preview':
        url = (msg.get('url') or '').strip()
        if not url:
            return {'ok': False, 'error': 'missing url'}
        dur = int(msg.get('duration') or 12)
        player.preview(url, duration=dur)
        return {'ok': True}
    if cmd == 'next':
        current = player.current()
        if current:
            sid = current.get('item', {}).get('id')
            st = library.next_station(sid)
        else:
            stations = library.list_stations()
            st = stations[0] if stations else None
        if st:
            player.play_station(st)
        return {'ok': True}
    if cmd == 'prev':
        current = player.current()
        if current:
            sid = current.get('item', {}).get('id')
            st = library.prev_station(sid)
        else:
            stations = library.list_stations()
            st = stations[-1] if stations else None
        if st:
            player.play_station(st)
        return {'ok': True}
    return {'ok': False, 'error': f'unknown cmd: {cmd}'}


def run_daemon():
    sock = control_sock()
    print("RUN_DAEMON ENTERED", sock, flush=True)

    # Start MPRIS daemon in background thread
    from sqlch.core import mpris_daemon
    threading.Thread(target=mpris_daemon.main, daemon=True, name="mpris").start()

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
