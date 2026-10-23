import json
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any

from sqlch import sources
from sqlch.core import discover, follows, library, notify, player, progress, watcher
from sqlch.sources import youtube
from sqlch.core.paths import runtime_dir


def control_sock() -> Path:
    return runtime_dir() / "control.sock"


def _reply(conn: socket.socket, obj: dict[str, Any]):
    data = (json.dumps(obj) + '\n').encode()
    conn.sendall(data)


TRACK_EVERY = 5  # seconds between playhead samples
_FLUSH_BEFORE = {'stop', 'play', 'play_item', 'next', 'prev'}


def track_once() -> None:
    """Save the playhead of the playing video so it can be resumed or marked watched."""
    cur = player.current()
    if not cur or cur.get('type') != 'item':
        return
    item = cur.get('item') or {}
    if item.get('kind') != 'video' or not item.get('source') or not item.get('id'):
        return
    pos, dur = player.item_progress()
    # mpv reports nothing or 0 until the file is loaded; recording that would
    # wipe a saved resume point.
    if not isinstance(pos, (int, float)) or pos < 1:
        return
    progress.record(item['source'], item['id'], pos, dur)


def _track_loop() -> None:
    while True:
        time.sleep(TRACK_EVERY)
        try:
            track_once()
        except Exception:
            pass


def _handle(msg: dict[str, Any]) -> dict[str, Any]:
    cmd = msg.get('cmd')
    if cmd in _FLUSH_BEFORE:
        try:
            track_once()
        except Exception:
            pass
    if cmd == 'ping':
        return {'ok': True, 'msg': 'pong'}
    if cmd == 'status':
        from sqlch.core import recorder
        cur = player.current()
        resp = {'ok': True, 'status': player.status_string(), 'current': cur,
                'recording': recorder.status()}
        if cur and cur.get('type') == 'item':
            resp['position'], resp['duration'] = player.item_progress()
            resp['can_skip'] = player.can_skip()
        elif cur:
            resp['timeshift'] = player.timeshift()
            shown = player.displayed_title()
            if shown:
                resp['displayed_icy'] = shown
        return resp
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
            st = library.last_played_station()
            if not st:
                return {'ok': False, 'error': 'no last played station'}
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
    if cmd == 'play_item':
        item = msg.get('item')
        if not isinstance(item, dict):
            return {'ok': False, 'error': 'missing item'}
        src = sources.REGISTRY.get(item.get('source'))
        if src is None:
            return {'ok': False, 'error': f"unknown source: {item.get('source')}"}
        mode = msg.get('mode')
        if mode is not None and mode not in dict(getattr(src, 'PLAY_MODES', ())).values():
            return {'ok': False, 'error': f'unknown play mode: {mode}'}
        try:
            target = src.resolve(item, mode=mode) if mode else src.resolve(item)
        except Exception as e:
            return {'ok': False, 'error': f'resolve failed: {e}'}
        start = None
        if msg.get('resume'):
            start = progress.resume_point(progress.get(item['source'], item['id']))
        player.play_target(target, item, start=start)
        return {'ok': True}
    if cmd == 'seek':
        try:
            pos = float(msg['pos'])
        except (KeyError, TypeError, ValueError):
            return {'ok': False, 'error': 'missing pos'}
        player.seek(pos)
        return {'ok': True}
    if cmd == 'seek_rel':
        try:
            delta = float(msg['delta'])
        except (KeyError, TypeError, ValueError):
            return {'ok': False, 'error': 'missing delta'}
        player.seek_relative(delta)
        return {'ok': True}
    if cmd == 'go_live':
        player.go_live()
        return {'ok': True}
    if cmd == 'preview':
        url = (msg.get('url') or '').strip()
        if not url:
            return {'ok': False, 'error': 'missing url'}
        dur = int(msg.get('duration') or 12)
        player.preview(url, duration=dur)
        return {'ok': True}
    if cmd == 'next':
        if player.can_skip():
            player.skip(True)
            return {'ok': True}
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
        if player.can_skip():
            player.skip(False)
            return {'ok': True}
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
    if cmd == 'record':
        from sqlch.core import recorder
        action = msg.get('action') or 'toggle'
        mode = msg.get('mode') or 'full'
        if action == 'status':
            return {'ok': True, 'recording': recorder.status()}
        if action == 'stop':
            return recorder.stop()
        if action == 'start':
            cur = player.current() or {}
            return recorder.start(mode, cur.get('item'))
        if action == 'toggle':
            if recorder.status()['active']:
                return recorder.stop()
            cur = player.current() or {}
            return recorder.start(mode, cur.get('item'))
        return {'ok': False, 'error': f'unknown record action: {action}'}
    if cmd == 'toggle_favorite':
        item = msg.get('item')
        if not isinstance(item, dict):
            return {'ok': False, 'error': 'missing item'}
        try:
            return {'ok': True, 'favorite': follows.toggle_favorite(item)}
        except ValueError as e:
            return {'ok': False, 'error': str(e)}
    if cmd == 'follow':
        cid = msg.get('channel_id')
        if not isinstance(cid, str) or not youtube.valid_channel_id(cid):
            return {'ok': False, 'error': 'bad channel id'}
        name = msg.get('name')
        follows.follow(cid, name if isinstance(name, str) and name else cid)
        return {'ok': True}
    if cmd == 'unfollow':
        cid = msg.get('channel_id')
        if not isinstance(cid, str):
            return {'ok': False, 'error': 'bad channel id'}
        follows.unfollow(cid)
        return {'ok': True}
    if cmd == 'podcast_follow':
        item = msg.get('item')
        feed = item.get('feed_url') if isinstance(item, dict) else None
        if not (isinstance(feed, str) and feed.startswith(('http://', 'https://'))):
            return {'ok': False, 'error': 'bad feed url'}
        follows.follow_podcast(item)
        return {'ok': True}
    if cmd == 'podcast_unfollow':
        feed = msg.get('feed_url')
        if not (isinstance(feed, str) and feed.startswith(('http://', 'https://'))):
            return {'ok': False, 'error': 'bad feed url'}
        follows.unfollow_podcast(feed)
        return {'ok': True}
    if cmd == 'mark_watched':
        item = msg.get('item')
        if not isinstance(item, dict) or not item.get('source') or not item.get('id'):
            return {'ok': False, 'error': 'missing item'}
        progress.mark(item['source'], item['id'], bool(msg.get('watched', True)))
        return {'ok': True}
    if cmd == 'drain_notices':
        return {'ok': True, 'notices': watcher.drain()}
    return {'ok': False, 'error': f'unknown cmd: {cmd}'}


def run_daemon():
    sock = control_sock()
    # Start MPRIS daemon in background thread
    from sqlch.core import mpris_daemon
    threading.Thread(target=mpris_daemon.main, daemon=True, name="mpris").start()
    watcher.start(youtube.fetch_feed, youtube.poll_seconds)
    threading.Thread(target=_track_loop, daemon=True, name="progress").start()

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
