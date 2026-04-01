# Code Review Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Apply all findings from the three-agent code review: consolidate duplicates, fix bugs, clean up dead code, and tighten syntax/idioms.

**Architecture:** Changes are grouped by dependency order. Tasks 1–3 restructure shared infrastructure (IPC, ICY parser, last-played helper). Tasks 4–7 fix correctness bugs. Tasks 8–10 are mechanical cleanups with no logical dependencies.

**Tech Stack:** Python 3.10+, mpv IPC (Unix socket), Textual TUI, pydbus/GLib MPRIS2, Spotify/MusicBrainz REST

---

## Task 1: Replace socat-based MPV IPC with raw Unix socket

The socat subprocess approach in `player.py` is slower, adds a system dependency, and is inferior to the raw socket version already in `mpris_daemon.py`. Consolidate on the socket version in `player.py`; `mpris_daemon.py` will then import from `player`.

**Files:**
- Modify: `sqlch/core/player.py` (lines 51–68: `_mpv_ipc`)
- Modify: `sqlch/core/mpris_daemon.py` (lines 143–176: remove `_mpv_ipc`, `mpv_get`, `mpv_cmd`; add imports)

**Step 1: Replace `_mpv_ipc` in `player.py`**

In `player.py`, add `import socket` to the imports at the top, then replace lines 51–68 with:

```python
def _mpv_ipc(cmd: dict[str, Any], timeout: float = 0.5) -> dict[str, Any] | None:
    sock = mpv_socket()
    if not sock.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(str(sock))
            s.sendall((json.dumps(cmd) + "\n").encode())
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
        if buf.strip():
            return json.loads(buf.decode())
    except Exception:
        return None
    return None
```

Also remove `subprocess` from imports in `player.py` only if it's no longer used elsewhere — it IS still used by `_kill_existing` and `_spawn_mpv`, so keep it. Add `socket` to imports.

**Step 2: Remove duplicate IPC helpers from `mpris_daemon.py`**

In `mpris_daemon.py`:
- Remove the `_mpv_ipc` function (lines 143–163)
- Remove the `mpv_get` function (lines 166–171)
- Remove the `mpv_cmd` function (lines 174–176)
- Update the import from `player.py` to also import `mpv_get` and `mpv_command`:

```python
from sqlch.core.player import mpv_socket, mpv_get, mpv_command
```

- Everywhere in `mpris_daemon.py` that calls `mpv_cmd(...)`, replace with `mpv_command(...)` (same signature, already in `player.py` as `mpv_command(*parts)`)
  - `mpris_daemon.py:289`: `mpv_cmd("set_property", "volume", ...)` → `mpv_command(...)`
  - `mpris_daemon.py:300`: `mpv_cmd("set_property", "pause", "no")` → `mpv_command(...)`
  - `mpris_daemon.py:304`: `mpv_cmd("set_property", "pause", "yes")` → `mpv_command(...)`
  - `mpris_daemon.py:308`: `mpv_cmd("quit")` → `mpv_command(...)`
  - `mpris_daemon.py:312`: `mpv_cmd("cycle", "pause")` → `mpv_command(...)`

**Step 3: Verify no remaining `socat` references**

Run: `grep -r socat sqlch/`
Expected: no output

**Step 4: Commit**

```bash
git add sqlch/core/player.py sqlch/core/mpris_daemon.py
git commit -m "refactor: consolidate MPV IPC on raw Unix socket, drop socat dependency"
```

---

## Task 2: Consolidate ICY title parser

`player.py:_parse_icy` and `mpris_daemon.py:parse_icy_title` are two parsers that handle the same input differently. The `mpris_daemon.py` version is correct (handles bare titles). Promote it to `player.py` and import it in `mpris_daemon.py`.

**Files:**
- Modify: `sqlch/core/player.py` (lines 126–130)
- Modify: `sqlch/core/mpris_daemon.py` (lines 183–196)

**Step 1: Replace `_parse_icy` in `player.py`**

Replace lines 126–130 with the better implementation, keeping the private name:

```python
def _parse_icy(title: str) -> tuple[str | None, str | None]:
    if not title:
        return None, None
    if " - " in title:
        artist, track = title.split(" - ", 1)
    elif "-" in title:
        artist, track = title.split("-", 1)
    else:
        return None, title.strip()
    return artist.strip() or None, track.strip() or None
```

**Step 2: Remove `parse_icy_title` from `mpris_daemon.py` and import from player**

- Delete the `parse_icy_title` function from `mpris_daemon.py` (lines 183–196)
- Update the import from `player.py`:

```python
from sqlch.core.player import mpv_socket, mpv_get, mpv_command, _parse_icy
```

- Update `mpris_daemon.py:339`: `parse_icy_title(icy_title)` → `_parse_icy(icy_title)`

**Step 3: Commit**

```bash
git add sqlch/core/player.py sqlch/core/mpris_daemon.py
git commit -m "refactor: unify ICY title parser in player.py, fix bare-title handling"
```

---

## Task 3: Add `library.last_played_station()` and use it everywhere

The "find the most recently played station" pattern is written out in full in three places. Extract it to `library.py`.

**Files:**
- Modify: `sqlch/core/library.py` (add function after `prev_station`)
- Modify: `sqlch/core/daemon.py` (lines 38–43)
- Modify: `sqlch/cli/main.py` (lines 89–95)
- Modify: `sqlch/core/player.py` (lines 359–364)

**Step 1: Add `last_played_station` to `library.py`**

After the `prev_station` function (after line 85), add:

```python
def last_played_station() -> dict | None:
    stations = list_stations()
    played = [s for s in stations if s.get("last_played")]
    return max(played, key=lambda s: s["last_played"]) if played else None
```

**Step 2: Update `daemon.py` `__last__` branch (lines 38–43)**

Replace:
```python
        if q == '__last__':
            stations = library.list_stations()
            played = [s for s in stations if s.get('last_played')]
            if not played:
                return {'ok': False, 'error': 'no last played station'}
            st = max(played, key=lambda s: s['last_played'])
            player.play_station(st)
            return {'ok': True}
```
With:
```python
        if q == '__last__':
            st = library.last_played_station()
            if not st:
                return {'ok': False, 'error': 'no last played station'}
            player.play_station(st)
            return {'ok': True}
```

**Step 3: Update `main.py` `play-last` branch (lines 89–95)**

Replace:
```python
            stations = library.list_stations()
            played = [s for s in stations if s.get('last_played')]
            if played:
                st = max(played, key=lambda s: s['last_played'])
                player.play_station(st)
            else:
                print('sqlch: no last played station', file=sys.stderr)
```
With:
```python
            st = library.last_played_station()
            if st:
                player.play_station(st)
            else:
                print('sqlch: no last played station', file=sys.stderr)
```

**Step 4: Update `player.py` `now_playing_info` fallback (lines 359–364)**

Replace:
```python
    if not station_name:
        stations = library.list_stations()
        played = [s for s in stations if s.get("last_played")]
        if played:
            st = max(played, key=lambda s: s["last_played"])
            station_name = st.get("name")
```
With:
```python
    if not station_name:
        st = library.last_played_station()
        if st:
            station_name = st.get("name")
```

**Step 5: Commit**

```bash
git add sqlch/core/library.py sqlch/core/daemon.py sqlch/cli/main.py sqlch/core/player.py
git commit -m "refactor: extract last_played_station() to library, remove 3x duplicate pattern"
```

---

## Task 4: Fix TUI `action_play` bug (raw discover dict → library station)

`action_play` passes a raw RadioBrowser result dict directly to `player.play_station`. Those dicts have `stationuuid`, not `id`, so `record_play` is silently called with `None` and the station is never tracked. Fix: run it through `library.add_discovered_station` first.

**Files:**
- Modify: `sqlch/tui/app.py` (lines 288–292)

**Step 1: Update `action_play`**

Replace:
```python
    def action_play(self) -> None:
        self._with_selected_station(
            lambda url, st: player.play_station(st),
            "Playing",
        )
```
With:
```python
    def action_play(self) -> None:
        self._with_selected_station(
            lambda url, st: player.play_station(library.add_discovered_station(st)),
            "Playing",
        )
```

**Step 2: Commit**

```bash
git add sqlch/tui/app.py
git commit -m "fix: action_play now adds discover result to library before playing, fixes silent record_play(None)"
```

---

## Task 5: Fix `pause()` protocol inconsistency in `player.py`

`pause()` sends raw socat text `b"cycle pause\n"` while every other call uses the JSON IPC. After Task 1, socat is gone entirely. Replace with `mpv_command`.

**Files:**
- Modify: `sqlch/core/player.py` (lines 261–275)

**Step 1: Replace `pause()`**

Replace the entire `pause()` function with:
```python
def pause() -> None:
    if not mpv_socket().exists():
        return
    mpv_command("cycle", "pause")
```

**Step 2: Commit**

```bash
git add sqlch/core/player.py
git commit -m "fix: pause() now uses JSON IPC instead of raw socat text command"
```

---

## Task 6: Make MPRIS plugin optional in `_spawn_mpv` (fix preview crash without Nix env)

`_spawn_mpv` unconditionally calls `_need_env("SQLCH_MPRIS_PLUGIN", ...)` which raises when the env var is absent. This crashes `preview()` in non-Nix environments. The MPRIS plugin is not needed for audio preview.

**Files:**
- Modify: `sqlch/core/player.py` (lines 217–244)

**Step 1: Make `--script` conditional**

Replace:
```python
def _spawn_mpv(url: str, *, video: bool = False, preview: bool = False) -> None:
    mpris = _need_env("SQLCH_MPRIS_PLUGIN", mpris_plugin())
    sock = mpv_socket()
    sock.parent.mkdir(parents=True, exist_ok=True)

    args: list[str] = [
        mpv_bin(),
        f"--input-ipc-server={sock}",
        f"--script={mpris}",
        ...
    ]
```
With:
```python
def _spawn_mpv(url: str, *, video: bool = False, preview: bool = False) -> None:
    sock = mpv_socket()
    sock.parent.mkdir(parents=True, exist_ok=True)

    args: list[str] = [
        mpv_bin(),
        f"--input-ipc-server={sock}",
        "--idle=yes",
        "--keep-open=yes",
        "--force-window=no",
        "--no-terminal",
        "--cache=yes",
    ]
    mpris = mpris_plugin()
    if mpris:
        args.insert(2, f"--script={mpris}")
    if not video:
        args.append("--no-video")
    if preview:
        args.append("--volume=60")
    args.append(url)

    subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
```

Note: `_need_env` and `mpris_plugin` functions stay in the file — they are still referenced/exported.

**Step 2: Commit**

```bash
git add sqlch/core/player.py
git commit -m "fix: _spawn_mpv no longer crashes when SQLCH_MPRIS_PLUGIN is unset"
```

---

## Task 7: Add TTL to Spotify track cache

`spoti.py` writes `cached_at` but never checks it, so entries are cached forever. `enrich.py` has a 30-day TTL. Make them consistent.

**Files:**
- Modify: `sqlch/core/spoti.py`

**Step 1: Add `CACHE_TTL` constant and stale check in `enrich()`**

At the top of `spoti.py`, after the imports, add:

```python
CACHE_TTL = 60 * 60 * 24 * 30  # 30 days
```

In the `enrich()` function, replace:
```python
    if k in cache:
        return cache[k]
```
With:
```python
    if k in cache:
        entry = cache[k]
        if (_now() - entry.get('cached_at', 0)) < CACHE_TTL:
            return entry
```

**Step 2: Commit**

```bash
git add sqlch/core/spoti.py
git commit -m "fix: add 30-day TTL to Spotify track cache, consistent with enrich.py"
```

---

## Task 8: Dead code and import cleanup

**Files:**
- Modify: `sqlch/core/daemon.py` (line 96 debug print; line 8 unused `config` import)
- Modify: `sqlch/core/config.py` (line 2 unused `os` import; line 7 duplicate `APP_NAME`)
- Modify: `sqlch/cli/main.py` (line 151–153 missing `.strip()` on tag split)

**Step 1: Remove debug print from `daemon.py`**

Remove line 96: `print("RUN_DAEMON ENTERED", sock, flush=True)`

**Step 2: Remove unused `config` import from `daemon.py`**

Change line 8:
```python
from sqlch.core import library, notify, player, discover, config
```
To:
```python
from sqlch.core import library, notify, player, discover
```

**Step 3: Remove unused `os` import and duplicate `APP_NAME` from `config.py`**

Remove `import os` from line 2.
Remove `APP_NAME = 'sqlch'` from line 7.

**Step 4: Fix missing `.strip()` on tag split in `main.py` (line 151–153)**

Replace:
```python
        tags = st.get('tags') or []
        if isinstance(tags, str):
            tags = [t for t in tags.split(',') if t]
```
With:
```python
        tags = st.get('tags') or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(',') if t.strip()]
```

**Step 5: Commit**

```bash
git add sqlch/core/daemon.py sqlch/core/config.py sqlch/cli/main.py
git commit -m "chore: remove debug print, dead imports, duplicate constant; fix tag strip bug"
```

---

## Task 9: Syntax and idiom fixes

**Files:**
- Modify: `sqlch/core/client.py` (socket context manager)
- Modify: `sqlch/core/enrich.py` (redundant check; inline import)
- Modify: `sqlch/core/mpris_daemon.py` (double return None)
- Modify: `sqlch/cli/main.py` (missing annotation on `add_cmd`)
- Modify: `sqlch/core/paths.py` (import order)

**Step 1: Fix socket leak in `client.py`**

`send()` currently:
```python
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(str(sock))
    s.sendall((json.dumps(msg) + '\n').encode())
    data = b''
    while not data.endswith(b'\n'):
        chunk = s.recv(4096)
        if not chunk:
            break
        data += chunk
    s.close()
```
Replace with:
```python
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
```

**Step 2: Simplify redundant check in `enrich.py` line 55**

Replace: `if v and v != [] and v != '':`
With: `if v:`

**Step 3: Move `import os` to top of `enrich.py`**

Add `import os` to the top-level imports block (after `import time`).
Remove the local `import os` inside `_mb_base_url()` (line 116).

**Step 4: Fix double `return None` in `mpris_daemon.py`**

The `_mpv_ipc` function in `mpris_daemon.py` will be deleted in Task 1, so this is already handled. Skip if Task 1 is done.

**Step 5: Add annotation to `add_cmd` in `main.py`**

Change line 198:
```python
def add_cmd(args):
```
To:
```python
def add_cmd(args: list[str]) -> None:
```

**Step 6: Fix import order in `paths.py`**

Change:
```python
from pathlib import Path
import os
```
To:
```python
import os
from pathlib import Path
```

**Step 7: Commit**

```bash
git add sqlch/core/client.py sqlch/core/enrich.py sqlch/cli/main.py sqlch/core/paths.py
git commit -m "fix: socket context manager in client, simplify enrich check, annotation, import order"
```

---

## Task 10: Replace legacy `typing` imports with native Python 3.10+ types

Five files use `typing.List`, `typing.Dict`, `typing.Optional`, `typing.Tuple` despite having `from __future__ import annotations`. Replace throughout.

**Files:**
- Modify: `sqlch/core/discover.py`
- Modify: `sqlch/core/enrich.py`
- Modify: `sqlch/core/library.py`
- Modify: `sqlch/core/mpris_daemon.py`
- Modify: `sqlch/core/spoti.py`

**Substitutions in each file:**
- `List[X]` → `list[X]`
- `Dict[K, V]` → `dict[K, V]`
- `Optional[X]` → `X | None`
- `Tuple[X, Y]` → `tuple[X, Y]`
- Remove the `from typing import ...` line entirely (or keep only what's still needed)

**`discover.py`**: Remove `from typing import List, Dict`. Update signatures:
- `search(...)` → returns `list[dict]`
- `save_last_search(results: list[dict])` and `load_last_search() -> list[dict]`
- Internal `results: list[dict] = []`

**`enrich.py`**: Remove `from typing import Dict, Any, Optional`. Keep only if `Any` is still used in annotations. Check: `Any` is used in `dict[str, Any]` throughout — `Any` still needs importing from `typing`. Change to `from typing import Any` only.

**`library.py`**: Remove `from typing import List, Optional`. Update:
- `list_stations(category: str | None = None) -> list[dict]`
- `find_station(...) -> dict | None`
- `add_station(... tags: list[str] | None, ...) -> dict`
- `next_station(...) -> dict | None`
- `prev_station(...) -> dict | None`
- `last_played_station() -> dict | None` (already native from Task 3)

**`mpris_daemon.py`**: Remove `from typing import Any, Dict, Optional, Tuple`. Keep `from typing import Any`. Update all `Dict[str, Any]` → `dict[str, Any]`, `Optional[str]` → `str | None`, `Tuple[...]` → `tuple[...]`.

**`spoti.py`**: Remove `from typing import Optional, Dict, Any`. Keep `from typing import Any`. Update all signatures accordingly.

**Step 1: Update each file's imports and annotations**

Go file by file making the substitutions above.

**Step 2: Verify no `typing.List/Dict/Optional/Tuple` remain**

Run: `grep -r "from typing import" sqlch/`
Expected: only `from typing import Any` lines remain.

**Step 3: Commit**

```bash
git add sqlch/core/discover.py sqlch/core/enrich.py sqlch/core/library.py sqlch/core/mpris_daemon.py sqlch/core/spoti.py
git commit -m "chore: replace legacy typing.List/Dict/Optional with native Python 3.10+ types"
```
