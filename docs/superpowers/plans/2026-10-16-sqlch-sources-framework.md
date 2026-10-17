# sqlch sources framework + Local source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a source registry, a generic docked source pane, daemon playback of source items with a seek bar in Now Playing, and the Local (files on disk) source as the first working source.

**Architecture:** A source is a module in `sqlch/sources/` exposing `search/browse/resolve`. The GUI builds one lazily-created `SourcePane` docked window per registered source (reusing the docked-window system), listed in a SOURCES popover on the nav row. Clicking an item sends `play_item` to the daemon, which resolves it and hands the result to mpv through the existing `_spawn_mpv`. Now Playing renders item metadata and a seek bar from `position`/`duration` in `status`.

**Tech Stack:** Python 3.11+, GTK4/PyGObject, gtk4-layer-shell, mpv IPC, `unittest`.

Spec: `docs/superpowers/specs/2026-10-16-sqlch-sources-design.md` (sections 1-5). Radio timeshift (section 6) and Jellyfin/YouTube/video/Spotify are separate cycles. The niri window rule for `sqlch-video` lives in the nixos repo and ships with the first video source, not here; only the mpv flags land in this plan.

## Global Constraints

- Repo/worktree: `/home/prepko/sqlch-sources`, branch `sources-framework` (verify with `git rev-parse --show-toplevel` before any commit). Tests: `python -m unittest tests.<module> -v`. The 3 errors in `tests/test_header.py::TestPreviousTracksReserveSpace` are pre-existing on main: ignore them.
- Do NOT launch the GUI (it opens on the user's live desktop); the controller/user does live checks.
- No new third-party dependencies. The GUI's Python env only has PyGObject; `sqlch.sources` modules may import only the stdlib and `sqlch.core.config`/`sqlch.core.paths`.
- Colors only through `palette`/`_build_css` tokens (`{rest}`, `{score}`, `{mono}`...). Comments only where the WHY is non-obvious.
- Item shape (dict): `source, id, title, artist, album, art, duration, kind, path`; `kind` is one of `track`, `video`, `folder`; folder items must carry `path`.
- Target: `Target(url, video=False, meta=None)` (NamedTuple). Daemon commands: `{"cmd":"play_item","item":{...}}` and `{"cmd":"seek","pos":<seconds>}`; `status` adds `position` and `duration` only when `current.type == "item"`.
- Source module contract: `NAME`, `TITLE` (uppercase strip title), `LABEL`, `HINT` (setup hint shown when unavailable), `available()`, `search(query)`, `browse(path)`, `resolve(item)`.
- Reserved window names a source may not use: `library`, `discover`, `np`.
- Source network/disk work never runs on the GTK main thread; results return through `GLib.idle_add`.
- Commits: lowercase one-liner `sqlch: what` (GUI-only changes `sqlch-gui: what`), then blank line + `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

---

### Task 1: Source types, registry, config helper

**Files:**
- Create: `sqlch/sources/__init__.py`, `sqlch/sources/base.py`
- Test: `tests/test_sources.py`

**Interfaces:**
- Produces in `base.py`: `KINDS = ("track", "video", "folder")`; `class Target(NamedTuple): url: str; video: bool = False; meta: dict | None = None`; `make_item(source, id, title, *, kind="track", artist=None, album=None, art=None, duration=None, path=None) -> dict` (raises `ValueError` for unknown kind, or a folder with no `path`).
- Produces in `__init__.py`: `RESERVED = ("library", "discover", "np")`; `_load(names=_MODULES, package=__name__) -> dict[str, module]` (skips and logs any module that fails to import, lacks `NAME`, collides with a reserved name or a name already loaded); `REGISTRY = _load()` (defined last in the file); `source_config(name) -> dict` reading `config.load().get("sources", {}).get(name, {})`.

- [ ] **Step 1: Write the failing tests** in `tests/test_sources.py`:

```python
import unittest
from unittest import mock

from sqlch import sources
from sqlch.sources.base import Target, make_item


class TestMakeItem(unittest.TestCase):
    def test_defaults(self):
        item = make_item("local", "a/b.mp3", "B")
        self.assertEqual(item, {
            "source": "local", "id": "a/b.mp3", "title": "B", "artist": None,
            "album": None, "art": None, "duration": None, "kind": "track",
            "path": None})

    def test_folder_requires_path(self):
        with self.assertRaises(ValueError):
            make_item("local", "a", "A", kind="folder")
        self.assertEqual(
            make_item("local", "a", "A", kind="folder", path="a")["path"], "a")

    def test_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):
            make_item("local", "x", "X", kind="podcast")


class TestTarget(unittest.TestCase):
    def test_defaults(self):
        t = Target("file:///x.mp3")
        self.assertFalse(t.video)
        self.assertIsNone(t.meta)


class TestRegistry(unittest.TestCase):
    def test_failing_and_nameless_modules_are_skipped(self):
        # "nope" does not exist; "base" imports fine but has no NAME.
        self.assertEqual(sources._load(("nope", "base")), {})

    def test_reserved_name_is_skipped(self):
        fake = mock.Mock(NAME="library")
        with mock.patch("importlib.import_module", return_value=fake):
            self.assertEqual(sources._load(("x",)), {})

    def test_duplicate_name_keeps_first(self):
        a, b = mock.Mock(NAME="dup"), mock.Mock(NAME="dup")
        with mock.patch("importlib.import_module", side_effect=[a, b]):
            self.assertEqual(sources._load(("x", "y")), {"dup": a})

    def test_source_config(self):
        cfg = {"sources": {"local": {"library_root": "/m"}}}
        with mock.patch("sqlch.core.config.load", return_value=cfg):
            self.assertEqual(sources.source_config("local"), {"library_root": "/m"})
            self.assertEqual(sources.source_config("other"), {})
        with mock.patch("sqlch.core.config.load", return_value={}):
            self.assertEqual(sources.source_config("local"), {})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify fail:** `python -m unittest tests.test_sources -v` → ImportError.
- [ ] **Step 3: Implement.**

`sqlch/sources/base.py`:

```python
from typing import NamedTuple

KINDS = ("track", "video", "folder")


class Target(NamedTuple):
    url: str
    video: bool = False
    meta: dict | None = None


def make_item(source, id, title, *, kind="track", artist=None, album=None,
              art=None, duration=None, path=None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"unknown item kind: {kind}")
    if kind == "folder" and path is None:
        raise ValueError("folder items need a path")
    return {"source": source, "id": id, "title": title, "artist": artist,
            "album": album, "art": art, "duration": duration, "kind": kind,
            "path": path}
```

`sqlch/sources/__init__.py`:

```python
"""Media source registry. Each source module is listed explicitly (no
filesystem scan) and imported defensively so one broken source cannot take
down the others."""

import importlib
import logging

log = logging.getLogger(__name__)

RESERVED = ("library", "discover", "np")
_MODULES = ("local",)


def source_config(name: str) -> dict:
    from sqlch.core import config
    return (config.load().get("sources") or {}).get(name) or {}


def _load(names=_MODULES, package=__name__) -> dict:
    registry = {}
    for n in names:
        try:
            mod = importlib.import_module(f"{package}.{n}")
            name = mod.NAME
        except Exception:
            log.exception("source %s failed to load", n)
            continue
        if name in RESERVED or name in registry:
            log.error("source %s: name %r is reserved or duplicated", n, name)
            continue
        registry[name] = mod
    return registry


# Last: source modules import source_config from this package while loading.
REGISTRY = _load()
```

- [ ] **Step 4: Run to verify pass:** `python -m unittest tests.test_sources -v`.
- [ ] **Step 5: Commit** `sqlch: source registry with item and target types`.

---

### Task 2: Local source

**Files:**
- Create: `sqlch/sources/local.py`
- Test: `tests/test_source_local.py`
- Modify: `docs/superpowers/specs/2026-10-16-sqlch-sources-design.md` (Local note: replace "`search` filters an on-disk index cached under `cache_dir()`. Tags via `mutagen`" with "`search` walks the tree (capped at 200 hits) and matches every query word against the relative path. Artist/album/title come from the `Artist/Album/NN - Title.ext` path layout; tag reading is deferred so the GUI needs no new dependency.")

**Interfaces:**
- Consumes: `make_item`, `Target` from `sqlch.sources.base`; `source_config` from `sqlch.sources`.
- Produces: module-level `NAME="local"`, `TITLE="LOCAL"`, `LABEL="Local Library"`, `HINT` (text telling the user to set `"sources": {"local": {"library_root": "/path"}}` in `~/.config/sqlch/sqlch.json`), `available()`, `search(query)`, `browse(path=None)`, `resolve(item)`. Item `id` is the file's path relative to the root in POSIX form; folder `path` is the same for directories. `library_root` defaults to `~/Music`.

Behavior: `browse` lists directories first then audio files, both case-insensitive sorted, skipping names starting with `.`. Audio extensions: `.mp3 .flac .ogg .opus .m4a .aac .wav .wma`. Title = filename stem with a leading track number (`^\d+\s*[-._)]*\s*`) stripped (fall back to the stem if that empties it). With `parts` = directories between root and the file: album = `parts[-1]` if any, artist = `parts[-2]` if at least two. Art = first file in the track's directory whose lowercased name is `cover|folder|front|album` + `.jpg|.jpeg|.png` (cache the directory listing per call). `search`: all query words (lowercased, whitespace split) must appear in the lowercased relative path; walk with sorted traversal, skip hidden dirs, stop at 200 results; empty query returns `[]`. Path safety: `_safe(root, rel)` raises `ValueError` if `rel` is absolute or has a `..` part (do not `resolve()`: symlinked album folders must keep working). `resolve` returns `Target(str(path), False, {"title","artist","album","art"})` and raises `FileNotFoundError` if the file is missing.

- [ ] **Step 1: Write failing tests** in `tests/test_source_local.py`. Build a temp tree in `setUp`:

```
Artist/Album/01 - First Song.mp3   Artist/Album/02 - Second.flac
Artist/Album/cover.jpg             Artist/Album/notes.txt
Solo/loose.ogg                     .hidden/secret.mp3
```

and patch `local.source_config` to return `{"library_root": str(root)}` (`mock.patch.object(local, "source_config", ...)`). Tests: (a) `browse(None)` returns exactly folders `Artist`, `Solo` in that order (`.hidden` skipped), each `kind == "folder"` with `path == id`; (b) `browse("Artist/Album")` returns two tracks titled `First Song` and `Second`, artist `Artist`, album `Album`, `art` ending `cover.jpg`, first `id == "Artist/Album/01 - First Song.mp3"`, `notes.txt` ignored; (c) `browse("Solo")` track has `artist is None`, `album == "Solo"`, `art is None`; (d) `browse("../x")` and `browse("/etc")` raise `ValueError`; (e) `search("second artist")` returns one item, `search("secret")` and `search("")` return `[]`, and a tree with >200 matching files returns 200 (create 205 empty `.mp3` files under `Many/`); (f) `resolve` returns `Target` with `url == str(root/"Artist/Album/02 - Second.flac")`, `video is False`, `meta["title"] == "Second"`; resolving a missing id raises `FileNotFoundError`; (g) `available()` true for the temp root, false for `library_root` pointing at a missing dir; (h) `from sqlch.sources import REGISTRY; "local" in REGISTRY` and `REGISTRY["local"] is local`.
- [ ] **Step 2: Run to verify fail:** `python -m unittest tests.test_source_local -v`.
- [ ] **Step 3: Implement `local.py`** per the behavior above. Skeleton for the parts that are easy to get wrong:

```python
import os
import re
from pathlib import Path, PurePosixPath

from sqlch.sources import source_config
from sqlch.sources.base import Target, make_item

NAME = "local"
TITLE = "LOCAL"
LABEL = "Local Library"
HINT = ('Set "sources": {"local": {"library_root": "/path/to/music"}} '
        "in ~/.config/sqlch/sqlch.json")

AUDIO_EXT = {".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".wav", ".wma"}
COVER_STEMS = ("cover", "folder", "front", "album")
COVER_EXT = (".jpg", ".jpeg", ".png")
SEARCH_LIMIT = 200


def _root() -> Path:
    return Path(source_config(NAME).get("library_root") or "~/Music").expanduser()


def _safe(root: Path, rel: str | None) -> Path:
    if not rel:
        return root
    p = PurePosixPath(rel)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError("path outside library")
    return root / rel


def _title_from(stem: str) -> str:
    return re.sub(r"^\d+\s*[-._)]*\s*", "", stem) or stem


def _cover(directory: Path, cache: dict) -> str | None:
    if directory not in cache:
        names = {c.name.lower(): c for c in directory.iterdir() if c.is_file()}
        cache[directory] = next(
            (str(names[s + e]) for s in COVER_STEMS for e in COVER_EXT
             if s + e in names), None)
    return cache[directory]


def _track(root: Path, f: Path, covers: dict) -> dict:
    rel = f.relative_to(root)
    parts = rel.parts[:-1]
    return make_item(
        NAME, rel.as_posix(), _title_from(f.stem),
        artist=parts[-2] if len(parts) >= 2 else None,
        album=parts[-1] if parts else None,
        art=_cover(f.parent, covers))
```

`browse`, `search` (use `os.walk(root, followlinks=True)`; prune `dirs[:] = sorted(d for d in dirs if not d.startswith("."))`; iterate `sorted(files)`), `resolve`, `available` follow the behavior description.
- [ ] **Step 4: Run to verify pass:** `python -m unittest tests.test_source_local tests.test_sources -v`.
- [ ] **Step 5: Commit** `sqlch: local files source`.

---

### Task 3: Playback backend (mpv args, play_target, seek, daemon commands)

**Files:**
- Modify: `sqlch/core/player.py`, `sqlch/core/daemon.py`
- Test: `tests/test_player_items.py`

**Interfaces:**
- Consumes: `sqlch.sources.REGISTRY`, `Target`.
- Produces in `player.py`: `_mpv_args(url, *, video=False, preview=False) -> list[str]` (extracted from `_spawn_mpv`, same arguments in the same order for audio; for `video=True` the `--force-window=no` entry becomes `--force-window=yes`, `--wayland-app-id=sqlch-video` is added and `--no-video` is omitted); `play_target(target: Target, item: dict) -> None`; `seek(pos: float) -> None`; `item_progress() -> tuple[float | None, float | None]` (mpv `time-pos`, `duration`).
- Produces in `daemon.py`: `play_item` and `seek` commands; `status` includes `position`/`duration` for item playback.

- [ ] **Step 1: Write failing tests** in `tests/test_player_items.py`:

```python
import unittest
from pathlib import Path
from unittest import mock

from sqlch.core import daemon, player
from sqlch.sources.base import Target


class TestMpvArgs(unittest.TestCase):
    def _args(self, mpris=None, **kw):
        with mock.patch.object(player, "mpv_bin", return_value="mpv"), \
             mock.patch.object(player, "mpv_socket", return_value=Path("/r/mpv.sock")), \
             mock.patch.object(player, "mpris_plugin", return_value=mpris):
            return player._mpv_args("URL", **kw)

    def test_audio_default(self):
        a = self._args()
        self.assertEqual(a[0], "mpv")
        self.assertIn("--input-ipc-server=/r/mpv.sock", a)
        self.assertIn("--force-window=no", a)
        self.assertIn("--no-video", a)
        self.assertNotIn("--wayland-app-id=sqlch-video", a)
        self.assertEqual(a[-1], "URL")

    def test_mpris_script_inserted_at_index_two(self):
        self.assertEqual(self._args(mpris="/p/mpris.so")[2], "--script=/p/mpris.so")

    def test_video_shows_a_tagged_window(self):
        a = self._args(video=True)
        self.assertIn("--force-window=yes", a)
        self.assertNotIn("--force-window=no", a)
        self.assertIn("--wayland-app-id=sqlch-video", a)
        self.assertNotIn("--no-video", a)

    def test_preview_volume(self):
        self.assertIn("--volume=60", self._args(preview=True))


class TestPlayTarget(unittest.TestCase):
    def test_spawns_and_records_current_item(self):
        item = {"source": "local", "id": "a.mp3", "title": "A"}
        with mock.patch.object(player, "stop"), \
             mock.patch.object(player.notify, "notify"), \
             mock.patch.object(player, "_spawn_mpv") as spawn:
            player.play_target(Target("/m/a.mp3", False, {"title": "A"}), item)
        spawn.assert_called_once_with("/m/a.mp3", video=False)
        self.assertEqual(player.current(), {"type": "item", "item": item})

    def test_seek_is_absolute(self):
        with mock.patch.object(player, "mpv_command") as cmd:
            player.seek(42)
        cmd.assert_called_once_with("seek", 42.0, "absolute")

    def test_item_progress(self):
        with mock.patch.object(player, "mpv_get", side_effect=[12.5, 200.0]):
            self.assertEqual(player.item_progress(), (12.5, 200.0))


class TestDaemonItems(unittest.TestCase):
    def setUp(self):
        self.src = mock.Mock()
        self.src.resolve.return_value = Target("/m/a.mp3")
        patch = mock.patch.dict("sqlch.sources.REGISTRY", {"fake": self.src})
        patch.start()
        self.addCleanup(patch.stop)

    def test_play_item_resolves_and_plays(self):
        item = {"source": "fake", "id": "1", "title": "T"}
        with mock.patch.object(player, "play_target") as play:
            resp = daemon._handle({"cmd": "play_item", "item": item})
        self.assertEqual(resp, {"ok": True})
        play.assert_called_once_with(Target("/m/a.mp3"), item)

    def test_play_item_errors(self):
        self.assertFalse(daemon._handle({"cmd": "play_item"})["ok"])
        r = daemon._handle({"cmd": "play_item", "item": {"source": "nope"}})
        self.assertFalse(r["ok"])
        self.src.resolve.side_effect = FileNotFoundError("gone")
        r = daemon._handle({"cmd": "play_item", "item": {"source": "fake"}})
        self.assertFalse(r["ok"])
        self.assertIn("gone", r["error"])

    def test_seek(self):
        with mock.patch.object(player, "seek") as seek:
            self.assertEqual(daemon._handle({"cmd": "seek", "pos": 30}), {"ok": True})
        seek.assert_called_once_with(30.0)
        self.assertFalse(daemon._handle({"cmd": "seek"})["ok"])

    def test_status_reports_progress_only_for_items(self):
        rec = mock.Mock(status=mock.Mock(return_value={"active": False}))
        with mock.patch.object(player, "status_string", return_value="s"), \
             mock.patch.dict("sys.modules", {"sqlch.core.recorder": rec}), \
             mock.patch.object(player, "item_progress", return_value=(5.0, 90.0)):
            with mock.patch.object(player, "current",
                                   return_value={"type": "item", "item": {}}):
                r = daemon._handle({"cmd": "status"})
            self.assertEqual((r["position"], r["duration"]), (5.0, 90.0))
            with mock.patch.object(player, "current",
                                   return_value={"type": "station", "item": {}}):
                r = daemon._handle({"cmd": "status"})
            self.assertNotIn("position", r)


if __name__ == "__main__":
    unittest.main()
```

(`status` does `from sqlch.core import recorder` inside the handler; if patching `sys.modules` does not satisfy that import form, patch `sqlch.core.recorder.status` instead. Keep the assertions.)
- [ ] **Step 2: Run to verify fail:** `python -m unittest tests.test_player_items -v`.
- [ ] **Step 3: Implement.** In `player.py` replace the argument-building half of `_spawn_mpv` with `_mpv_args` (keep the `sock.parent.mkdir`, `Popen`, and `proc.wait` thread in `_spawn_mpv`, now `args = _mpv_args(url, video=video, preview=preview)`):

```python
def _mpv_args(url: str, *, video: bool = False, preview: bool = False) -> list[str]:
    args: list[str] = [
        mpv_bin(),
        f"--input-ipc-server={mpv_socket()}",
        "--idle=yes",
        "--keep-open=yes",
        "--force-window=yes" if video else "--force-window=no",
        "--no-terminal",
        "--cache=yes",
    ]
    mpris = mpris_plugin()
    if mpris:
        args.insert(2, f"--script={mpris}")
    if video:
        args.append("--wayland-app-id=sqlch-video")
    else:
        args.append("--no-video")
    if preview:
        args.append("--volume=60")
    args.append(url)
    return args
```

Add after `play_station`:

```python
def play_target(target, item: dict[str, Any]) -> None:
    global _current
    stop(notify_user=False)
    meta = target.meta or {}
    notify.notify("sqlch", f"NOW PLAYING\n{meta.get('title') or item.get('title', '')}")
    _spawn_mpv(target.url, video=target.video)
    _current = {"type": "item", "item": item}


def seek(pos: float) -> None:
    mpv_command("seek", float(pos), "absolute")


def item_progress() -> tuple[float | None, float | None]:
    return mpv_get("time-pos"), mpv_get("duration")
```

In `daemon.py`: `from sqlch import sources` next to the other imports; add `play_item` and `seek` branches before `preview`:

```python
    if cmd == 'play_item':
        item = msg.get('item')
        if not isinstance(item, dict):
            return {'ok': False, 'error': 'missing item'}
        src = sources.REGISTRY.get(item.get('source'))
        if src is None:
            return {'ok': False, 'error': f"unknown source: {item.get('source')}"}
        try:
            target = src.resolve(item)
        except Exception as e:
            return {'ok': False, 'error': f'resolve failed: {e}'}
        player.play_target(target, item)
        return {'ok': True}
    if cmd == 'seek':
        try:
            pos = float(msg['pos'])
        except (KeyError, TypeError, ValueError):
            return {'ok': False, 'error': 'missing pos'}
        player.seek(pos)
        return {'ok': True}
```

and extend `status`:

```python
        cur = player.current()
        resp = {'ok': True, 'status': player.status_string(), 'current': cur,
                'recording': recorder.status()}
        if cur and cur.get('type') == 'item':
            resp['position'], resp['duration'] = player.item_progress()
        return resp
```
- [ ] **Step 4: Run to verify pass:** `python -m unittest tests.test_player_items tests.test_sources tests.test_source_local -v`, then `python -m unittest discover tests` once (only the 3 known errors).
- [ ] **Step 5: Commit** `sqlch: play source items and seek through the daemon`.

---

### Task 4: Registry-driven docked windows with lazy panes

**Files:**
- Modify: `sqlch_gui/ui/dock_state.py`, `sqlch_gui/ui/dock_window.py`, `sqlch_gui/ui/dock_manager.py`
- Test: `tests/test_dock_state.py`

**Interfaces:**
- Produces: `dock_state.default_state(names=NAMES)` and `dock_state.load(path=STATE_PATH, names=NAMES)`; `save` unchanged. Existing callers keep working.
- Produces: `DockedWindow(manager, name, title, panel=None)` gains `.panel` and `.set_panel(widget)`.
- Produces: `DockManager(np_win, panels, nav, on_shown, on_hidden, titles=None)`: `panels` values are a widget or a zero-arg callable returning one (created on first open); `self.names` = `dock_state.NAMES` + any extra panel names; `self.titles` merges `_TITLES` with `titles`; `on_shown`/`on_hidden` dicts may omit a name, in which case the manager calls `panel.on_shown()` / `panel.on_hidden()` if the panel defines them.

- [ ] **Step 1: Write failing tests** appended to `tests/test_dock_state.py` (match its existing tempdir style): (a) `load(path, names=NAMES + ("local",))` with no file → `state["local"] == {"open": False, "placed": None}`; (b) save then load with the extra name round-trips `{"open": True, "placed": {"mode": "free", "x": 5, "y": 6}}`; (c) a file containing a `"ghost"` entry loads without a `"ghost"` key; (d) `load(path)` with default names ignores a saved `"local"` entry.
- [ ] **Step 2: Run to verify fail:** `python -m unittest tests.test_dock_state -v`.
- [ ] **Step 3: Implement.** `dock_state.py`: add the `names=NAMES` parameter to `default_state` and `load` and use it in the two comprehension/loop sites. `dock_window.py`: keep the scroll in `self._scroll`, add `self.panel = None`, `set_panel(self, panel)` (`self.panel = panel; self._scroll.set_child(panel)`), and call `set_panel` in `__init__` only when `panel is not None`. `dock_manager.py`:
  - In `__init__`: 

```python
        self.names = dock_state.NAMES + tuple(n for n in panels if n not in dock_state.NAMES)
        self.titles = {**_TITLES, **(titles or {})}
        self._factories = {n: p for n, p in panels.items() if callable(p)}
        self.state = dock_state.load(names=self.names)
        self.windows = {
            n: DockedWindow(self, n, self.titles[n],
                            None if n in self._factories else panels[n])
            for n in self.names
        }
```

  - Replace the two other `dock_state.NAMES` uses (`nav.set_open` loop in `__init__`, `_open_names`) with `self.names`.
  - Add `_call_hook(self, hooks, name, attr)` (`hook = hooks.get(name) or getattr(self.windows[name].panel, attr, None); if hook: hook()`), use it for `_on_shown` in `_fade_in` and `_on_hidden` in `toggle`'s `closed()`; and at the top of `_fade_in`: `if win.panel is None: win.set_panel(self._factories[name]())`.
- [ ] **Step 4: Verify** — `python -m unittest tests.test_dock_state tests.test_dock tests.test_overlay_card -v`, `python -c "import sqlch_gui.ui.window"`, `nix run nixpkgs#ruff -- check sqlch_gui/ui/dock_state.py sqlch_gui/ui/dock_window.py sqlch_gui/ui/dock_manager.py` (ignore E402).
- [ ] **Step 5: Commit** `sqlch-gui: registry-driven docked windows with lazily built panes`.

---

### Task 5: SOURCES tab and popover in the nav row

**Files:**
- Modify: `sqlch_gui/ui/controls.py` (`NavColumn`), `sqlch_gui/ui/common.py` (CSS)
- Test: `tests/test_nav_column.py`, `tests/test_gui_style.py`

**Interfaces:**
- Produces: `NavColumn.set_sources(entries: list[dict])` where each entry is `{"name", "label", "available": bool, "hint"}`; builds one popover row per entry (open-dot label `○`/`●`, label text) and shows the SOURCES tab only when `entries` is non-empty. Clicking a row pops the popover down and emits `nav-toggled(name)`. `set_open(name, bool)` additionally handles source names: updates that row's dot and sets class `active` on the SOURCES tab while any source is open.
- The SOURCES tab is a plain `Gtk.Button` with class `sq-tab` (a `Gtk.MenuButton` would not pick up `.sq-tab` styling) plus a `Gtk.Popover` parented to it; attributes `_sources_btn`, `_pop`, `_rows` (`name -> (button, dot_label)`).
- CSS: `.sq-source-row` (mono font, `0.7em`, letter-spacing `0.1em`, color `{lyric}`), `.sq-source-row:hover` (color `{score}`), `.sq-source-off` (`opacity: 0.55`).

- [ ] **Step 1: Write failing tests.** In `tests/test_nav_column.py` add: (a) before `set_sources`, `nav._sources_btn.get_visible()` is False; after `set_sources([...two entries...])` it is True; (b) `nav._rows["local"][0].emit("clicked")` emits `nav-toggled` with `"local"` and does not change the dot; (c) `set_open("local", True)` makes `nav._rows["local"][1].get_text() == "●"` and gives `nav._sources_btn` class `active`; `set_open("local", False)` reverts both; with two sources open, closing one keeps the tab active; (d) an entry with `available: False` has class `sq-source-off` on its row and keeps its hint as tooltip; (e) `set_open("library", True)` still works and does not touch the SOURCES tab. In `tests/test_gui_style.py` extend the CSS test to assert `.sq-source-row` and `.sq-source-off` appear in `_build_css(...)`.
- [ ] **Step 2: Run to verify fail:** `python -m unittest tests.test_nav_column tests.test_gui_style -v`.
- [ ] **Step 3: Implement** in `NavColumn.__init__` after the tab loop:

```python
        self._rows = {}
        self._open_sources = set()
        self._sources_btn = Gtk.Button(label="SOURCES")
        self._sources_btn.add_css_class("sq-tab")
        self._sources_btn.set_tooltip_text("Media sources")
        self._sources_btn.set_visible(False)
        self._pop = Gtk.Popover()
        self._pop.set_parent(self._sources_btn)
        self._sources_btn.connect("clicked", lambda _b: self._pop.popup())
        # A popover parented to a widget must be unparented before it dies.
        self.connect("destroy", lambda _w: self._pop.unparent())
        self.append(self._sources_btn)
```

and:

```python
    def set_sources(self, entries):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for e in entries:
            dot = Gtk.Label(label="○")
            text = Gtk.Label(label=e["label"], xalign=0.0)
            inner = Gtk.Box(spacing=8)
            inner.append(dot)
            inner.append(text)
            btn = Gtk.Button()
            btn.set_child(inner)
            btn.add_css_class("flat")
            btn.add_css_class("sq-source-row")
            if not e["available"]:
                btn.add_css_class("sq-source-off")
                btn.set_tooltip_text(e["hint"])
            btn.connect("clicked", lambda _b, n=e["name"]: self._pick(n))
            box.append(btn)
            self._rows[e["name"]] = (btn, dot)
        self._pop.set_child(box)
        self._sources_btn.set_visible(bool(entries))

    def _pick(self, name):
        self._pop.popdown()
        self.emit("nav-toggled", name)
```

and extend `set_open` with an `elif name in self._rows:` branch (update the dot text, add/discard `name` in `_open_sources`, toggle `active` on `_sources_btn` by `bool(self._open_sources)`). Keep the existing library/discover branch first; guard it with `if name in self._buttons:`.
- [ ] **Step 4: Verify** — both test modules, `tests.test_header` (only the 3 known errors), `python -c "import sqlch_gui.ui.window"`, ruff on `controls.py common.py`.
- [ ] **Step 5: Commit** `sqlch-gui: sources tab with popover in the nav row`.

---

### Task 6: Generic SourcePane

**Files:**
- Create: `sqlch_gui/ui/timefmt.py`, `sqlch_gui/ui/source_pane.py`
- Modify: `sqlch_gui/ui/common.py` (only if a missing CSS class is needed; prefer reusing `station-row`, `station-live`, `list-plate`, `field-entry`, `search-btn`, `meta-genre`, `control-btn`)
- Test: `tests/test_source_pane.py`

**Interfaces:**
- Produces: `timefmt.format_duration(seconds) -> str` (`""` for `None`/non-positive; `m:ss`; `h:mm:ss` from one hour).
- Produces: `SourcePane(parent_window, source, run_async=_thread_run, play=None)` — a `Gtk.Box`. `run_async(work, done)` runs `work()` off-thread and calls `done(result, error_str_or_None)` on the main thread (default uses a daemon thread + `GLib.idle_add`; tests pass a synchronous one). `play(item)` defaults to sending `{"cmd":"play_item","item":item}` to the daemon through `run_async`. Public: `on_shown()` (first call loads the root or shows the source's `HINT` when `available()` is false; later calls do nothing), `on_hidden()` (invalidates in-flight loads). Test-visible state: `_items` (items currently listed), `_stack` (list of `(path, title)` for browse breadcrumbs), `_searching` (bool), `status` (a `Gtk.Label` for hint/error/empty text), `entry` (`Gtk.Entry`), `_activate(item)`, `back()`, `_search(query)`.

Behavior: search entry + search button on top (Enter or button → `_search(text)`; empty text leaves search and reloads the current browse folder). A nav row with a back button and a breadcrumb label (hidden at the root and not searching). `_activate(item)`: folder → push `(item["path"], item["title"])` and browse that path; otherwise call `play(item)`. `back()`: when searching, clear the entry and reload the current folder; else pop the stack and reload. Each load increments `_gen`; `_show` ignores results whose gen is stale. Rows: `station-row` box with a title label (ellipsized), a `station-live` sub label (artist · album, hidden when empty) in a vertical body, and a right-aligned duration label from `format_duration(item["duration"])`; folder rows get a `›` suffix instead of a duration. A `GestureClick` (primary button, `released`) on each row calls `_activate`. `status` shows `HINT` when unavailable, `Nothing here` for an empty list, `Couldn't load: <error>` on error; hidden when the list has rows. The list lives in its own `Gtk.ScrolledWindow` (`vexpand`, policy NEVER/AUTOMATIC) like `DiscoverPanel`.

- [ ] **Step 1: Write failing tests** in `tests/test_source_pane.py` using a fake source object (`NAME="fake"`, `HINT="set it up"`, `available()`, `browse(path)`, `search(q)`, recording calls) and a synchronous `run_async`:

```python
def sync(work, done):
    try:
        result, err = work(), None
    except Exception as e:
        result, err = None, str(e)
    done(result, err)
```

Cases: (a) `format_duration`: `None`/`0`/`-3` → `""`, `75` → `"1:15"`, `3725` → `"1:02:05"`; (b) `on_shown` loads `browse(None)` once and lists its items (`pane._items`); a second `on_shown` does not call `browse` again; (c) `_activate(folder)` pushes the stack and calls `browse(folder["path"])`; `back()` returns to the root listing and empties the stack; (d) `_activate(track)` calls the injected `play` with the item and does not touch the stack; (e) `_search("x")` lists `search("x")` results, sets `_searching`; `back()` clears the entry text and returns to the folder listing; empty-query `_search("")` does the same as back; (f) unavailable source: `on_shown` never calls `browse`, `status` text equals `HINT` and is visible; (g) a source whose `browse` raises shows `Couldn't load: ...` in `status`; (h) an empty result shows `Nothing here`; (i) a stale result (increment `_gen` between starting a load with an async runner that holds `done` and then calling it) does not replace the list; (j) `on_hidden()` invalidates an in-flight load the same way.
- [ ] **Step 2: Run to verify fail:** `python -m unittest tests.test_source_pane -v`.
- [ ] **Step 3: Implement** both files per the interface and behavior above. `_thread_run`:

```python
def _thread_run(work, done):
    def run():
        try:
            result, err = work(), None
        except Exception as e:
            result, err = None, str(e)
        GLib.idle_add(done, result, err)   # returns False via done's own return
    threading.Thread(target=run, daemon=True).start()
```

`done` callbacks that run through `GLib.idle_add` must return `False`; make `_show` return `False`.
- [ ] **Step 4: Verify** — `python -m unittest tests.test_source_pane -v`, `python -c "import sqlch_gui.ui.source_pane"`, ruff on the two new files.
- [ ] **Step 5: Commit** `sqlch-gui: generic source pane`.

---

### Task 7: Wire sources into the window

**Files:**
- Modify: `sqlch_gui/ui/window.py`

**Interfaces:**
- Consumes: `sqlch.sources.REGISTRY`, `SourcePane`, `NavColumn.set_sources`, `DockManager(..., titles=)`.

- [ ] **Step 1: Implement** in `SqlchPopupWindow.__init__` (replace the existing `DockManager(...)` construction and the `nav` hookup around it):

```python
from sqlch.sources import REGISTRY as SOURCES
from .source_pane import SourcePane
...
        panels = {"library": self.station_list, "discover": self.discover}
        titles = {}
        for name, src in SOURCES.items():
            panels[name] = lambda s=src: SourcePane(self, s)
            titles[name] = src.TITLE
        self.now_playing.nav_column.set_sources([
            {"name": n, "label": s.LABEL, "available": s.available(), "hint": s.HINT}
            for n, s in SOURCES.items()])

        self.docks = DockManager(
            self, panels=panels, titles=titles,
            nav=self.now_playing.nav_column,
            on_shown={"library": self.station_list.on_shown, "discover": lambda: None},
            on_hidden={"library": self.station_list.abort_probes, "discover": lambda: None},
        )
```

Keep everything else (the `nav-toggled` connection, `show_saved` on map) unchanged.
- [ ] **Step 2: Verify** — `python -c "import sqlch_gui.ui.window"`, the dock/nav/source tests, full suite once (only the 3 known errors), ruff on `window.py`. No GUI launch.
- [ ] **Step 3: Commit** `sqlch-gui: dock a pane per registered source`.

---

### Task 8: Now Playing shows source items with a seek bar

**Files:**
- Modify: `sqlch_gui/ui/controls.py` (`SeekBar`), `sqlch_gui/ui/now_playing.py`, `sqlch_gui/ui/common.py` (CSS)
- Test: `tests/test_seek_bar.py`, `tests/test_gui_style.py`

**Interfaces:**
- Consumes: `timefmt.format_duration`; daemon `status` fields `position`, `duration`, `current.type == "item"`.
- Produces: `SeekBar(Gtk.Box)` in `controls.py`: hidden until it has a positive duration; `set_state(position, duration)`; emits `seek-requested(float seconds)` when the user moves the scale; while the user is interacting (and for 1.5 s after the last user change) `set_state` does not move the scale, so the 1 Hz poll cannot fight a drag. Attributes for tests: `_scale` (`Gtk.Scale`), `_time` (`Gtk.Label`), `_hold_until` (monotonic seconds), `_on_change_value(scale, scroll, value)`.
- CSS (`_build_css`, palette tokens): `.seek-bar scale trough` (`{wing}` fill, small radius, `min-height: 4px`), `.seek-bar scale highlight` (`{score}`), `.seek-bar scale slider` (`{score}`, `min-width: 10px`, `min-height: 10px`), `.seek-time` (`{mono}`, `0.65em`, `{rest}`). Extend the CSS test to assert `.seek-bar` and `.seek-time`.
- Now Playing: `self.seek_bar` is appended to the card between `info_scroll` and `control_row`; its `seek-requested` handler sends `{"cmd": "seek", "pos": pos}` through `daemon.send` on a background thread. In `update()`, after `_set_stale(False)`: if `curr.get("type") == "item"` call `self._update_item(item, resp)` and return; otherwise `self.seek_bar.set_state(None, None)` and continue as today. When playback stops (the early-return stale branch) also call `self.seek_bar.set_state(None, None)`.

`_update_item(item, resp)`: hides the LIVE tag; sets `_cur_station_id = None`, `_cur_frequency = None`; track line `<b>Artist — Title</b>` (just the title when there is no artist, all HTML-escaped); station line `<b>SOURCE</b>  Album` (source name uppercased; album omitted when empty); when the item identity (`f"{source}:{id}"`) differs from `self._hist_station_id`: store it there, clear `_history`, set `_cur_artist`/`_cur_title` to the item's artist/title (empty string for a missing artist), re-render the previous-tracks rows, and set the cover — if `item["art"]` is an existing local file `GLib.idle_add(self._apply_cover_path, art, artist, title)`, else `self.clear_cover()`; finally `self.seek_bar.set_state(resp.get("position"), resp.get("duration"))`. Remote art URLs are out of scope here (later sources fetch to the covers cache first).

- [ ] **Step 1: Write failing tests** in `tests/test_seek_bar.py`: (a) hidden at construction; `set_state(None, None)`, `set_state(5, 0)`, `set_state(None, 90)` keep it hidden; (b) `set_state(10, 100)` shows it, `_scale.get_value() == 10`, `_scale.get_adjustment().get_upper() == 100`, `_time.get_text() == "0:10 / 1:40"`; (c) `_on_change_value(None, None, 42.0)` emits `seek-requested` with `42.0` and returns `False`; (d) right after that, `set_state(60, 100)` leaves the scale value where it was and sets `_hold_until` in the future; after `bar._hold_until = 0`, `set_state(60, 100)` moves it to 60; (e) a later `set_state(None, None)` hides it even during the hold. Plus the CSS assertions above.
- [ ] **Step 2: Run to verify fail:** `python -m unittest tests.test_seek_bar tests.test_gui_style -v`.
- [ ] **Step 3: Implement.**

```python
class SeekBar(Gtk.Box):
    """Position scale for items with a known duration. The user's own moves
    are not overwritten by the 1 Hz status poll for HOLD seconds."""

    __gsignals__ = {
        'seek-requested': (GObject.SignalFlags.RUN_LAST, None, (float,)),
    }
    HOLD = 1.5

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.add_css_class("seek-bar")
        self._hold_until = 0.0
        self._scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 1)
        self._scale.set_draw_value(False)
        self._scale.set_hexpand(True)
        self._scale.connect("change-value", self._on_change_value)
        self._time = Gtk.Label(label="")
        self._time.add_css_class("seek-time")
        self.append(self._scale)
        self.append(self._time)
        self.set_visible(False)

    def _on_change_value(self, _scale, _scroll, value):
        self._hold_until = time.monotonic() + self.HOLD
        self.emit("seek-requested", float(value))
        return False

    def set_state(self, position, duration):
        if not duration or duration <= 0 or position is None:
            self.set_visible(False)
            return
        self.set_visible(True)
        self._time.set_text(
            f"{format_duration(position) or '0:00'} / {format_duration(duration)}")
        if time.monotonic() < self._hold_until:
            return
        self._scale.set_range(0, duration)
        self._scale.set_value(min(position, duration))
```

(`controls.py` needs `import time` and `from .timefmt import format_duration`.) Note `format_duration(0)` is `""`, hence the `or '0:00'` for a position of 0; do not change `format_duration`'s contract. In `now_playing.py` add `SeekBar` to the `controls` import, create and append `self.seek_bar` before `control_row`, add the `update()` branch and `_update_item` as specified.
- [ ] **Step 4: Verify** — `python -m unittest tests.test_seek_bar tests.test_gui_style tests.test_header -v` (only the 3 known errors), `python -c "import sqlch_gui.ui.window"`, full suite once, ruff on `controls.py now_playing.py common.py`.
- [ ] **Step 5: Commit** `sqlch-gui: now playing shows source items with a seek bar`.

---

### Final verification (controller, after the whole-branch review)

- Re-point the dev wrapper (`scratchpad/sqlch-gui-dev`, `PYTHONPATH`) at `~/sqlch-sources`, set `sources.local.library_root` in `~/.config/sqlch/sqlch.json`, restart the sqlch daemon from the worktree (the daemon must run the new code for `play_item`), then run live checks with the user: SOURCES tab lists Local; opening it docks a pane that magnets like the others; browse folders and back; search; play a track (Now Playing shows `LOCAL`, album, art if a cover file exists, a working seek bar); stop; start a radio station (seek bar disappears, live display unchanged); restart restores the open Local pane.
