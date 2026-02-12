_CACHE_DIR = None

def _cache_dir():
    global _CACHE_DIR
    if _CACHE_DIR is None:
        import os
        from pathlib import Path
        base = os.environ.get('XDG_CACHE_HOME')
        if not base:
            base = str(Path.home() / '.cache')
        p = Path(base) / 'sqlch'
        p.mkdir(parents=True, exist_ok=True)
        _CACHE_DIR = p
    return _CACHE_DIR
import os
import sys
import json
import tempfile
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from sqlch.core import player, library, discover
from sqlch.core import client
from sqlch.core.daemon import run_daemon
HELP = 'sqlch — radio + metadata orchestrator\n\nUsage:\n  sqlch daemon\n  sqlch status\n  sqlch play <id|name|index|url>\n  sqlch play-last\n  sqlch pause\n  sqlch stop\n  sqlch tui\n\nLibrary:\n  sqlch list\n  sqlch info <id>\n  sqlch add <url>\n  sqlch edit <id>\n  sqlch rm <id>\n\nDiscovery:\n  sqlch search <query>\n  sqlch preview <index|url>\n'

def main():
    argv = sys.argv[1:]
    if not argv:
        print(status())
        return
    if argv[0] in ('-h', '--help', 'help'):
        print(HELP)
        return
    cmd, *args = argv
    if cmd == 'daemon':
        run_daemon()
        return
    if cmd == 'tui':
        from sqlch.tui.app import main as tui_main
        tui_main()
        return
    dispatch_command(cmd, args)

def daemon_call(payload: dict):
    """
    Send command to daemon if available.
    Returns response dict or None if daemon not running.
    """
    if not client.daemon_available():
        return None
    return client.send(payload)

def status():
    resp = daemon_call({'cmd': 'status'})
    if resp:
        return resp.get('status', 'sqlch: unknown')
    return player.status_string()

def dispatch_command(cmd: str, args: list[str]) -> None:
    if cmd == 'status':
        print(status())
        return
    if cmd == 'stop':
        if daemon_call({'cmd': 'stop'}) is None:
            player.stop()
        return
    if cmd == 'pause':
        if daemon_call({'cmd': 'pause'}) is None:
            player.pause()
        return
    if cmd == 'play-last':
        if daemon_call({'cmd': 'play', 'query': '__last__'}) is None:
            player.start_last()
        return
    if cmd == 'play':
        play_cmd(args)
        return
    if cmd == 'list':
        list_cmd()
        return
    if cmd == 'info':
        info_cmd(args)
        return
    if cmd == 'add':
        add_cmd(args)
        return
    if cmd == 'edit':
        edit_cmd(args)
        return
    if cmd == 'rm':
        rm_cmd(args)
        return
    if cmd == 'search':
        search_cmd(args)
        return
    if cmd == 'preview':
        preview_cmd(args)
        return
    print(f'Unknown command: {cmd}', file=sys.stderr)
    sys.exit(1)

def play_cmd(args: list[str]) -> None:
    if not args:
        print('Usage: sqlch play <id|name|index|url>', file=sys.stderr)
        sys.exit(1)
    arg = args[0]
    resp = daemon_call({'cmd': 'play', 'query': arg})
    if resp:
        if not resp.get('ok'):
            print(resp.get('error', 'play failed'), file=sys.stderr)
            sys.exit(1)
        return
    if arg.isdigit():
        results = discover.load_last_search()
        idx = int(arg) - 1
        if not results or idx < 0 or idx >= len(results):
            print('Play index out of range.', file=sys.stderr)
            sys.exit(1)
        st = results[idx]
        station = library.add_station(name=st.get('name') or 'unknown', url=st.get('url'), tags=(st.get('tags') or '').split(',') if isinstance(st.get('tags'), str) else st.get('tags') or [], allow_existing=True)
        player.play_station(station)
        return
    station = library.find_station(arg)
    if station:
        player.play_station(station)
        return
    if '://' in arg:
        station = library.add_station(name=urlparse(arg).netloc or arg, url=arg, allow_existing=True)
        player.play_station(station)
        return
    print(f'Could not resolve station: {arg}', file=sys.stderr)
    sys.exit(1)

def list_cmd() -> None:
    stations = library.list_stations()
    if not stations:
        print('No stations saved.')
        return
    for st in stations:
        print(f"{st['id']:20} {st['name']}")

def info_cmd(args: list[str]) -> None:
    if not args:
        print('Usage: sqlch info <station-id>', file=sys.stderr)
        sys.exit(1)
    st = library.find_station(args[0])
    if not st:
        print('Station not found.', file=sys.stderr)
        sys.exit(1)
    print(json.dumps(st, indent=2))

def add_cmd(args):
    from sqlch.core import library, discover

    if not args:
        print("Usage: sqlch add <number|name>")
        return

    query = " ".join(args)

    results = discover.load_last_search()
    if not results:
        print("No recent search results found. Run `sqlch search` first.")
        return

    # -------------------------------------------------
    # 1. Numeric selection
    # -------------------------------------------------
    if query.isdigit():
        idx = int(query) - 1
        if idx < 0 or idx >= len(results):
            print("Invalid selection number.")
            return
        chosen = results[idx]

    # -------------------------------------------------
    # 2. Fuzzy name match
    # -------------------------------------------------
    else:
        q = query.lower()
        matches = [
            r for r in results
            if q in (r.get("name") or "").lower()
        ]

        if not matches:
            print(f"No match found for '{query}'.")
            return

        if len(matches) > 1:
            print("Multiple matches found:")
            for i, m in enumerate(matches, 1):
                print(f"  {i}. {m['name']}")
            print("Be more specific.")
            return

        chosen = matches[0]

    name = chosen.get("name")
    url = chosen.get("url")

    if not url:
        print("Selected station has no valid URL.")
        return

    st = library.add_station(name=name, url=url)
    print(f"Added: {st['name']}")

def edit_cmd(args: list[str]) -> None:
    if not args:
        print('Usage: sqlch edit <station-id>', file=sys.stderr)
        sys.exit(1)
    st = library.find_station(args[0])
    if not st:
        print('Station not found.', file=sys.stderr)
        sys.exit(1)
    editor = os.environ.get('EDITOR') or os.environ.get('VISUAL') or 'nano'
    with tempfile.NamedTemporaryFile('w+', suffix='.json', delete=False) as tf:
        json.dump(st, tf, indent=2)
        tf.flush()
        subprocess.call([editor, tf.name])
    edited = json.loads(Path(tf.name).read_text())
    edited['id'] = st['id']
    library.update_station(st['id'], edited)
    print(f"Updated station: {st['id']}")

def rm_cmd(args: list[str]) -> None:
    if not args:
        print('Usage: sqlch rm <station-id>', file=sys.stderr)
        sys.exit(1)
    if library.remove_station(args[0]):
        print('Removed.')
    else:
        print('Station not found.', file=sys.stderr)
        sys.exit(1)

def search_cmd(args: list[str]) -> None:
    if not args:
        print('Usage: sqlch search <query>', file=sys.stderr)
        sys.exit(1)
    results = discover.search(' '.join(args))
    discover.save_last_search(results)
    if not results:
        print('No results.')
        return
    for i, st in enumerate(results, 1):
        print(f"[{i:2}] {st.get('name', 'Unknown')}\n     {st.get('country', '-')} | {st.get('codec', '-')} {st.get('bitrate', '-')}kbps\n     url: {st.get('url', '-')}\n")

def preview_cmd(args: list[str]) -> None:
    if not args:
        print('Usage: sqlch preview <index|url>', file=sys.stderr)
        sys.exit(1)
    arg = args[0]
    resp = daemon_call({'cmd': 'preview', 'url': arg})
    if resp:
        return
    if arg.isdigit():
        results = discover.load_last_search()
        idx = int(arg) - 1
        if not results or idx < 0 or idx >= len(results):
            print('Preview index out of range.', file=sys.stderr)
            sys.exit(1)
        player.preview(results[idx]['url'])
    else:
        player.preview(arg)
