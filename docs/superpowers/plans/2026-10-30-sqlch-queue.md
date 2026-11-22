# sqlch queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A daemon-owned, persistent, cross-source play queue with auto-advance, a RADIO/MEDIA mode that decides what next/prev do, resume-by-statefile for parked media, and a dockable Playlist pane with drag and drop.

**Architecture:** `sqlch/core/playqueue.py` is pure persistent state (`queue.json`, daemon-only writer, atomic replace, same pattern as `follows.py`). `sqlch/core/transport.py` drives `player` with that state: advance, mode flips, parking, prev/next. The daemon gets `queue_*` and `set_mode` commands plus a 1 s tick that detects end of playback. The CLI, MPRIS and the GUI Playlist pane all go through the daemon.

**Tech Stack:** Python 3.11+, `unittest` (no pytest in this repo), GTK4/PyGObject for the pane, mpv JSON IPC.

Spec: `docs/superpowers/specs/2026-10-30-sqlch-queue-design.md`. Task 9 appends an "Implementation notes" section to it recording where this plan refines the spec.

## Global Constraints

- Run tests with `python -m unittest` (e.g. `python -m unittest tests.test_playqueue -v`). There is no pytest.
- The daemon is the only writer of `queue.json`; the GUI and CLI `queue` listing only read it. Every write replaces the file atomically.
- A corrupt `queue.json` is moved aside (`.bad`) and the queue starts empty.
- Default mode is `radio`, so a fresh install behaves exactly as today (`next`/`prev` cycle stations).
- Stations are queue entries; items are queue entries. Radio never "ends".
- 3 consecutive unplayable entries stop advance.
- `prev` in media mode restarts the item when it is more than 3 seconds in, otherwise steps back through `history` (max 20).
- A drop plays immediately only when the queue is empty and nothing is playing; otherwise it queues.
- RADIO→MEDIA plays the saved `resume` entry from its saved position (replacing the station). MEDIA→RADIO parks the playing item, then starts `library.last_played_station()`.
- Comments follow the surrounding code: short, say why, never restate the code.
- Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Work on branch `unstable`; never push `main`.

## File Structure

| File | Responsibility |
|---|---|
| `sqlch/core/playqueue.py` (new) | `queue.json` state: entries, mode, now, context, history, resume. No playback knowledge. |
| `sqlch/core/transport.py` (new) | Advance, next/prev, mode flips, parking, tick. Drives `player`. |
| `sqlch/core/player.py` (modify) | `playback_ended()` |
| `sqlch/core/daemon.py` (modify) | Route play/next/prev/stop through `transport`, new commands, tick loop, status fields |
| `sqlch/cli/main.py` (modify) | `sqlch queue ...`, `sqlch mode` |
| `sqlch/core/mpris_daemon.py` (modify) | `Next`/`Previous`, dynamic `CanGoNext`/`CanGoPrevious` |
| `sqlch/sources/__init__.py` (modify) | Reserve the `playlist` window name |
| `sqlch_gui/ui/playlist_math.py` (new) | Pure drop-index and reorder math |
| `sqlch_gui/ui/dnd.py` (new) | Drag payload encode/decode, drag source helper, queue message builders |
| `sqlch_gui/ui/playlist_pane.py` (new) | The Playlist pane |
| `sqlch_gui/ui/dock_state.py`, `dock_manager.py`, `controls.py`, `window.py` (modify) | Register the pane, add a PLAYLIST tab |
| `sqlch_gui/ui/station_list.py`, `source_pane.py` (modify) | Drag sources, "Add to queue" / "Play next" |
| `tests/__init__.py` (modify) | Isolate `XDG_DATA_HOME` so no test touches the real data dir |
| `tests/test_playqueue.py`, `test_transport.py`, `test_daemon_queue.py`, `test_cli_queue.py`, `test_mpris_queue.py`, `test_playlist_math.py`, `test_dnd.py`, `test_playlist_pane.py` (new) | Tests |

---

### Task 1: Queue state module

**Files:**
- Modify: `tests/__init__.py`
- Create: `sqlch/core/playqueue.py`
- Test: `tests/test_playqueue.py`

**Interfaces:**
- Produces (all in `sqlch.core.playqueue`):
  - constants `FILE = "queue.json"`, `MODES = ("radio", "media")`, `HISTORY_MAX = 20`
  - `path() -> Path`
  - `read() -> dict`: read-only view, never writes; state shape `{"mode": str, "entries": [entry], "now": entry|None, "context": {"items": [item], "index": int}|None, "history": [entry], "resume": {"entry": entry, "pos": float, "dur": float|None}|None}`
  - `make_entry(kind: str, payload: dict) -> dict` → `{"uid": str, "kind": "item", "item": {...}}` or `{"uid": str, "kind": "station", "station": {"id","name","url"}}`; raises `ValueError`
  - `entry_title(entry) -> str`, `entry_subtitle(entry) -> str`, `entry_label(entry) -> str`
  - `add(entry, at=None, play_next=False) -> int` (index inserted at)
  - `remove(uid) -> bool`, `move(uid, to) -> bool`, `take(uid) -> dict|None` (removes it and everything before it), `pop_head() -> dict|None`, `clear() -> None`
  - `set_mode(mode)`, `set_now(entry|None)`, `set_context(items|None, current_id|None)`, `next_in_context() -> dict|None`
  - `push_history(entry)`, `pop_history() -> dict|None`
  - `set_resume(entry, pos, dur)`, `clear_resume()`

- [ ] **Step 1: Isolate the data dir for every test**

Replace the (empty) contents of `tests/__init__.py` with:

```python
import os
import tempfile

# The daemon code under test writes small state files (queue.json, ...) into
# data_dir(); keep every test run out of the real ~/.local/share/sqlch.
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="sqlch-tests-")
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_playqueue.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlch.core import playqueue

TRACK = {"source": "local", "id": "a", "title": "Song A", "artist": "Band", "kind": "track"}
TRACK_B = {"source": "local", "id": "b", "title": "Song B", "kind": "track"}
STATION = {"id": "kexp", "name": "KEXP", "url": "http://kexp.example/stream", "extra": "dropped"}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        p = mock.patch.object(playqueue, "data_dir", lambda: self.dir)
        p.start()
        self.addCleanup(p.stop)

    def item(self, it=TRACK):
        return playqueue.make_entry("item", it)

    def station(self):
        return playqueue.make_entry("station", STATION)

    def uids(self):
        return [e["uid"] for e in playqueue.read()["entries"]]


class TestEntries(Base):
    def test_item_entry_keeps_the_whole_item(self):
        e = self.item()
        self.assertEqual((e["kind"], e["item"]), ("item", TRACK))
        self.assertTrue(e["uid"])

    def test_station_entry_keeps_only_id_name_url(self):
        e = self.station()
        self.assertEqual(e["station"], {"id": "kexp", "name": "KEXP",
                                        "url": "http://kexp.example/stream"})

    def test_uids_are_unique(self):
        self.assertNotEqual(self.item()["uid"], self.item()["uid"])

    def test_bad_entries_raise(self):
        for kind, payload in (("item", {}), ("item", {"source": "x"}),
                              ("station", {"name": "no url"}), ("nope", TRACK),
                              ("item", None)):
            with self.assertRaises(ValueError):
                playqueue.make_entry(kind, payload)

    def test_labels(self):
        self.assertEqual(playqueue.entry_title(self.item()), "Song A")
        self.assertEqual(playqueue.entry_label(self.item()), "Song A — Band")
        self.assertEqual(playqueue.entry_label(self.item(TRACK_B)), "Song B")
        self.assertEqual(playqueue.entry_title(self.station()), "KEXP")
        self.assertEqual(playqueue.entry_subtitle(self.station()), "radio")
        self.assertEqual(playqueue.entry_subtitle(self.item()), "Band")


class TestState(Base):
    def test_empty_default(self):
        s = playqueue.read()
        self.assertEqual(s, {"mode": "radio", "entries": [], "now": None,
                             "context": None, "history": [], "resume": None})

    def test_add_orders_and_returns_index(self):
        a, b, c = self.item(), self.item(TRACK_B), self.station()
        self.assertEqual(playqueue.add(a), 0)
        self.assertEqual(playqueue.add(b), 1)
        self.assertEqual(playqueue.add(c, at=1), 1)
        self.assertEqual(self.uids(), [a["uid"], c["uid"], b["uid"]])

    def test_add_play_next_goes_first(self):
        a, b = self.item(), self.item(TRACK_B)
        playqueue.add(a)
        playqueue.add(b, play_next=True)
        self.assertEqual(self.uids(), [b["uid"], a["uid"]])

    def test_add_clamps_at(self):
        a, b = self.item(), self.item(TRACK_B)
        playqueue.add(a, at=99)
        playqueue.add(b, at=-5)
        self.assertEqual(self.uids(), [b["uid"], a["uid"]])

    def test_remove(self):
        a = self.item()
        playqueue.add(a)
        self.assertTrue(playqueue.remove(a["uid"]))
        self.assertFalse(playqueue.remove(a["uid"]))
        self.assertEqual(self.uids(), [])

    def test_move_counts_the_target_after_removal(self):
        a, b, c = self.item(), self.item(TRACK_B), self.station()
        for e in (a, b, c):
            playqueue.add(e)
        self.assertTrue(playqueue.move(a["uid"], 2))
        self.assertEqual(self.uids(), [b["uid"], c["uid"], a["uid"]])
        self.assertTrue(playqueue.move(a["uid"], 0))
        self.assertEqual(self.uids(), [a["uid"], b["uid"], c["uid"]])
        self.assertFalse(playqueue.move("nope", 0))

    def test_take_drops_everything_before(self):
        a, b, c = self.item(), self.item(TRACK_B), self.station()
        for e in (a, b, c):
            playqueue.add(e)
        self.assertEqual(playqueue.take(b["uid"])["uid"], b["uid"])
        self.assertEqual(self.uids(), [c["uid"]])
        self.assertIsNone(playqueue.take("nope"))
        self.assertEqual(self.uids(), [c["uid"]])

    def test_pop_head_and_clear(self):
        a, b = self.item(), self.item(TRACK_B)
        playqueue.add(a)
        playqueue.add(b)
        self.assertEqual(playqueue.pop_head()["uid"], a["uid"])
        playqueue.clear()
        self.assertIsNone(playqueue.pop_head())

    def test_clear_keeps_resume(self):
        a = self.item()
        playqueue.add(self.item(TRACK_B))
        playqueue.set_resume(a, 90.0, 300.0)
        playqueue.clear()
        self.assertEqual(playqueue.read()["resume"]["entry"]["uid"], a["uid"])

    def test_mode_now_resume(self):
        a = self.item()
        playqueue.set_mode("media")
        playqueue.set_now(a)
        playqueue.set_resume(a, 12.5, None)
        s = playqueue.read()
        self.assertEqual((s["mode"], s["now"]["uid"]), ("media", a["uid"]))
        self.assertEqual((s["resume"]["pos"], s["resume"]["dur"]), (12.5, None))
        playqueue.clear_resume()
        playqueue.set_now(None)
        s = playqueue.read()
        self.assertEqual((s["now"], s["resume"]), (None, None))

    def test_unknown_mode_raises(self):
        with self.assertRaises(ValueError):
            playqueue.set_mode("shuffle")

    def test_history_is_capped_and_pops_newest_first(self):
        entries = [self.item({**TRACK, "id": str(i)}) for i in range(playqueue.HISTORY_MAX + 5)]
        for e in entries:
            playqueue.push_history(e)
        self.assertEqual(len(playqueue.read()["history"]), playqueue.HISTORY_MAX)
        self.assertEqual(playqueue.pop_history()["uid"], entries[-1]["uid"])
        self.assertEqual(len(playqueue.read()["history"]), playqueue.HISTORY_MAX - 1)

    def test_pop_history_empty(self):
        self.assertIsNone(playqueue.pop_history())


class TestContext(Base):
    ITEMS = [{**TRACK, "id": str(i)} for i in range(3)]

    def test_next_in_context_walks_the_list(self):
        playqueue.set_context(self.ITEMS, "0")
        self.assertEqual(playqueue.next_in_context()["id"], "1")
        self.assertEqual(playqueue.next_in_context()["id"], "2")
        self.assertIsNone(playqueue.next_in_context())

    def test_context_starts_at_the_playing_item(self):
        playqueue.set_context(self.ITEMS, "1")
        self.assertEqual(playqueue.next_in_context()["id"], "2")

    def test_unknown_current_id_means_no_context(self):
        playqueue.set_context(self.ITEMS, "zzz")
        self.assertIsNone(playqueue.read()["context"])

    def test_none_clears_and_folders_are_dropped(self):
        folder = {"source": "local", "id": "d", "kind": "folder"}
        playqueue.set_context([folder, *self.ITEMS], "0")
        self.assertEqual([i["id"] for i in playqueue.read()["context"]["items"]],
                         ["0", "1", "2"])
        playqueue.set_context(None, None)
        self.assertIsNone(playqueue.read()["context"])


class TestPersistence(Base):
    def test_round_trip_and_no_temp_files(self):
        a = self.item()
        playqueue.add(a)
        playqueue.set_mode("media")
        self.assertEqual(playqueue.read()["entries"][0]["item"], TRACK)
        self.assertEqual([p.name for p in self.dir.iterdir()], ["queue.json"])

    def test_corrupt_file_is_quarantined_by_a_write(self):
        (self.dir / "queue.json").write_text("{not json")
        self.assertEqual(playqueue.read()["entries"], [])  # reading never renames
        self.assertTrue((self.dir / "queue.json").exists())
        playqueue.add(self.item())
        bad = [p for p in self.dir.iterdir() if p.name.endswith(".bad")]
        self.assertEqual(len(bad), 1)
        self.assertEqual(len(playqueue.read()["entries"]), 1)

    def test_non_dict_payload_counts_as_corrupt(self):
        (self.dir / "queue.json").write_text("[1, 2]")
        playqueue.set_mode("media")
        self.assertEqual(len([p for p in self.dir.iterdir() if p.name.endswith(".bad")]), 1)

    def test_malformed_entries_are_dropped_on_read(self):
        good = self.item()
        (self.dir / "queue.json").write_text(json.dumps({
            "mode": "media",
            "entries": [good, {"uid": "x", "kind": "item"}, "junk", {"kind": "station"}],
        }))
        s = playqueue.read()
        self.assertEqual([e["uid"] for e in s["entries"]], [good["uid"]])
        self.assertEqual((s["now"], s["history"], s["resume"]), (None, [], None))

    def test_unknown_mode_falls_back_to_radio(self):
        (self.dir / "queue.json").write_text(json.dumps({"mode": "weird"}))
        self.assertEqual(playqueue.read()["mode"], "radio")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m unittest tests.test_playqueue -v`
Expected: ERROR `ImportError: cannot import name 'playqueue' from 'sqlch.core'`

- [ ] **Step 4: Write the module**

Create `sqlch/core/playqueue.py`:

```python
"""The play queue: one small JSON file in data_dir().

Same ownership rules as follows.py: the daemon is the only writer and the
only one that quarantines a corrupt file; the gui only reads. Every write
replaces the file atomically. This module is pure state; what plays next is
decided in transport.py."""

import json
import logging
import os
import tempfile
import threading
import time
import uuid

from sqlch.core.paths import data_dir

log = logging.getLogger(__name__)

FILE = "queue.json"
MODES = ("radio", "media")
HISTORY_MAX = 20

# RLock: the mutators nest (add -> _update).
_lock = threading.RLock()


def path():
    return data_dir() / FILE


def _empty() -> dict:
    return {"mode": "radio", "entries": [], "now": None, "context": None,
            "history": [], "resume": None}


def _entry_ok(e) -> bool:
    if not isinstance(e, dict) or not isinstance(e.get("uid"), str):
        return False
    if e.get("kind") == "item":
        it = e.get("item")
        return isinstance(it, dict) and bool(it.get("source")) and bool(it.get("id"))
    if e.get("kind") == "station":
        st = e.get("station")
        return isinstance(st, dict) and bool(st.get("url"))
    return False


def _context_ok(c) -> bool:
    return (isinstance(c, dict) and isinstance(c.get("items"), list)
            and isinstance(c.get("index"), int))


def _resume_ok(r) -> bool:
    return (isinstance(r, dict) and _entry_ok(r.get("entry"))
            and isinstance(r.get("pos"), (int, float)))


def _clean(data) -> dict:
    """Normalize a parsed payload. A non-dict raises ValueError; bad rows
    inside a dict are dropped rather than failing the whole queue."""
    if not isinstance(data, dict):
        raise ValueError(f"{FILE} does not hold an object")
    out = _empty()
    if data.get("mode") in MODES:
        out["mode"] = data["mode"]
    entries = data.get("entries")
    out["entries"] = [e for e in entries if _entry_ok(e)] if isinstance(entries, list) else []
    history = data.get("history")
    out["history"] = [e for e in history if _entry_ok(e)] if isinstance(history, list) else []
    if _entry_ok(data.get("now")):
        out["now"] = data["now"]
    if _context_ok(data.get("context")):
        out["context"] = data["context"]
    if _resume_ok(data.get("resume")):
        r = data["resume"]
        out["resume"] = {"entry": r["entry"], "pos": float(r["pos"]),
                         "dur": r["dur"] if isinstance(r.get("dur"), (int, float)) else None}
    return out


def _load() -> dict:
    """FileNotFoundError -> empty; bad content raises ValueError."""
    try:
        data = json.loads(path().read_text())
    except FileNotFoundError:
        return _empty()
    return _clean(data)


def read() -> dict:
    """Read-only view for any process: never renames or writes."""
    try:
        return _load()
    except (OSError, ValueError) as e:
        log.error("can't read %s: %s", path(), e)
        return _empty()


def _read_for_write() -> dict:
    """Daemon-side read under _lock. Corrupt content is moved aside under a
    unique name; other I/O errors raise rather than looking like an empty queue."""
    p = path()
    try:
        return _load()
    except ValueError as e:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        bad = p.with_name(f"{p.name}.{stamp}.bad")
        n = 1
        while bad.exists():
            bad = p.with_name(f"{p.name}.{stamp}-{n}.bad")
            n += 1
        log.error("%s is unreadable (%s); moving it to %s", p, e, bad.name)
        os.replace(p, bad)
        return _empty()


def _write(state: dict) -> None:
    p = path()
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=FILE + ".")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _update(fn):
    with _lock:
        state = _read_for_write()
        out = fn(state)
        _write(state)
        return out


# ---- entries ----

def make_entry(kind: str, payload) -> dict:
    uid = uuid.uuid4().hex[:8]
    if kind == "item":
        if not (isinstance(payload, dict) and payload.get("source") and payload.get("id")):
            raise ValueError("an item entry needs a source and an id")
        return {"uid": uid, "kind": "item", "item": payload}
    if kind == "station":
        if not (isinstance(payload, dict) and payload.get("url")):
            raise ValueError("a station entry needs a url")
        return {"uid": uid, "kind": "station",
                "station": {k: payload.get(k) for k in ("id", "name", "url")}}
    raise ValueError(f"unknown entry kind: {kind}")


def entry_title(entry: dict) -> str:
    if entry["kind"] == "station":
        st = entry["station"]
        return st.get("name") or st.get("url") or ""
    return entry["item"].get("title") or entry["item"].get("id") or ""


def entry_subtitle(entry: dict) -> str:
    if entry["kind"] == "station":
        return "radio"
    it = entry["item"]
    return " · ".join(x for x in (it.get("artist"), it.get("album")) if x)


def entry_label(entry: dict) -> str:
    artist = entry["item"].get("artist") if entry["kind"] == "item" else None
    title = entry_title(entry)
    return f"{title} — {artist}" if artist else title


# ---- queue edits ----

def add(entry: dict, at: int | None = None, play_next: bool = False) -> int:
    def go(state):
        entries = state["entries"]
        if play_next:
            i = 0
        elif at is None:
            i = len(entries)
        else:
            i = max(0, min(int(at), len(entries)))
        entries.insert(i, entry)
        return i
    return _update(go)


def remove(uid: str) -> bool:
    def go(state):
        before = len(state["entries"])
        state["entries"] = [e for e in state["entries"] if e["uid"] != uid]
        return len(state["entries"]) != before
    return _update(go)


def move(uid: str, to: int) -> bool:
    """`to` is the index in the list after the entry has been taken out."""
    def go(state):
        entries = state["entries"]
        for i, e in enumerate(entries):
            if e["uid"] == uid:
                entries.pop(i)
                entries.insert(max(0, min(int(to), len(entries))), e)
                return True
        return False
    return _update(go)


def take(uid: str) -> dict | None:
    """Remove an entry and everything queued before it; return the entry."""
    def go(state):
        for i, e in enumerate(state["entries"]):
            if e["uid"] == uid:
                del state["entries"][:i + 1]
                return e
        return None
    return _update(go)


def pop_head() -> dict | None:
    if not read()["entries"]:
        return None  # advance polls this; don't rewrite the file for nothing

    def go(state):
        return state["entries"].pop(0) if state["entries"] else None
    return _update(go)


def clear() -> None:
    _update(lambda state: state.update(entries=[]))


# ---- mode, now, context, history, resume ----

def set_mode(mode: str) -> None:
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode}")
    _update(lambda state: state.update(mode=mode))


def set_now(entry: dict | None) -> None:
    _update(lambda state: state.update(now=entry))


def set_context(items: list | None, current_id: str | None) -> None:
    """The list the playing item came from. Folders are dropped; no match for
    current_id means there is no list to walk."""
    def go(state):
        state["context"] = None
        if not items:
            return
        playable = [i for i in items if isinstance(i, dict) and i.get("kind") != "folder"]
        for n, i in enumerate(playable):
            if i.get("id") == current_id:
                state["context"] = {"items": playable, "index": n}
                return
    _update(go)


def next_in_context() -> dict | None:
    ctx = read()["context"]
    if not ctx or ctx["index"] + 1 >= len(ctx["items"]):
        return None

    def go(state):
        c = state["context"]
        if not c or c["index"] + 1 >= len(c["items"]):
            return None
        c["index"] += 1
        return c["items"][c["index"]]
    return _update(go)


def push_history(entry: dict) -> None:
    def go(state):
        state["history"].append(entry)
        del state["history"][:-HISTORY_MAX]
    _update(go)


def pop_history() -> dict | None:
    def go(state):
        return state["history"].pop() if state["history"] else None
    return _update(go)


def set_resume(entry: dict, pos: float, dur: float | None) -> None:
    _update(lambda state: state.update(
        resume={"entry": entry, "pos": float(pos), "dur": dur}))


def clear_resume() -> None:
    _update(lambda state: state.update(resume=None))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m unittest tests.test_playqueue -v`
Expected: all PASS.

- [ ] **Step 6: Run the whole suite to check the `tests/__init__.py` change broke nothing**

Run: `python -m unittest discover -s tests -t . 2>&1 | tail -5`
Expected: `OK` (same count as before plus the new tests; some GUI tests may skip without a display, as they did before).

- [ ] **Step 7: Commit**

```bash
git add tests/__init__.py tests/test_playqueue.py sqlch/core/playqueue.py
git commit -m "sqlch: playqueue store (entries, mode, now, context, history, resume)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: End-of-playback detection

**Files:**
- Modify: `sqlch/core/player.py` (after `item_progress`, near line 441)
- Test: `tests/test_player_items.py`

mpv is spawned with `--keep-open=yes`, so at end of file it parks with `eof-reached` true instead of exiting, and no `end-file` event reaches us (the daemon only does request/response IPC). End detection is therefore a poll of `eof-reached`. An external player (Spotify handoff) is judged by its progress.

**Interfaces:**
- Produces: `player.playback_ended() -> bool`; constant `HANDOFF_END_MARGIN = 1.0`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_player_items.py`, after `TestMpvArgs`/before `TestDaemonItems` (any class position works; this is a new class):

```python
class TestPlaybackEnded(unittest.TestCase):
    def test_mpv_parked_at_eof(self):
        with mock.patch.object(player, "_current", {"type": "item"}), \
             mock.patch.object(player, "mpv_get", return_value=True) as get:
            self.assertTrue(player.playback_ended())
        get.assert_called_once_with("eof-reached")

    def test_mpv_still_playing_or_not_loaded(self):
        for val in (False, None):
            with mock.patch.object(player, "_current", {"type": "item"}), \
                 mock.patch.object(player, "mpv_get", return_value=val):
                self.assertFalse(player.playback_ended())

    def test_handoff_ends_at_the_last_second(self):
        cur = {"type": "item", "handoff": "spotify"}
        for prog, ended in (((299.5, 300.0), True), ((120.0, 300.0), False),
                            ((None, None), False), ((10.0, 0), False)):
            with mock.patch.object(player, "_current", cur), \
                 mock.patch.object(player.handoff, "progress", return_value=prog):
                self.assertEqual(player.playback_ended(), ended, prog)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m unittest tests.test_player_items.TestPlaybackEnded -v`
Expected: FAIL `AttributeError: module 'sqlch.core.player' has no attribute 'playback_ended'`

- [ ] **Step 3: Implement**

In `sqlch/core/player.py`, add the constant next to the other module constants (search for `LIVE_MARGIN` / `TIMESHIFT_SECS` and put it beside them), then the function directly after `item_progress`:

```python
HANDOFF_END_MARGIN = 1.0  # an external player this close to the end counts as finished
```

```python
def playback_ended() -> bool:
    """True once the playing item has reached its end. mpv runs with
    keep-open, so it parks at EOF rather than exiting; an external player
    is judged by its progress."""
    if _current and _current.get("handoff"):
        pos, dur = handoff.progress(_current["handoff"])
        return (isinstance(pos, (int, float)) and isinstance(dur, (int, float))
                and dur > 0 and pos >= dur - HANDOFF_END_MARGIN)
    return mpv_get("eof-reached") is True
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m unittest tests.test_player_items -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add sqlch/core/player.py tests/test_player_items.py
git commit -m "sqlch: player.playback_ended polls eof-reached (keep-open) or handoff progress

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Transport (advance, next/prev, mode flips, parking)

**Files:**
- Create: `sqlch/core/transport.py`
- Test: `tests/test_transport.py`

**Interfaces:**
- Consumes: everything produced by Task 1 (`playqueue.*`), `player.play_target(target, item, start=None)`, `player.play_station(station)`, `player.current()`, `player.item_progress() -> (pos, dur)`, `player.seek(pos)`, `player.stop(notify_user=True)`, `player.playback_ended()`, `library.last_played_station()`, `library.list_stations()`, `library.next_station(id)`, `library.prev_station(id)`, `progress.get(source, id)`, `progress.resume_point(row)`, `progress.MIN_RESUME_SECS`, `sources.REGISTRY`.
- Produces (in `sqlch.core.transport`):
  - `class PlayError(Exception)`
  - `start_item(item: dict, *, context: list | None = None, resume: bool = False) -> None` (raises `PlayError`)
  - `start_station(station: dict) -> None`
  - `play_entry(entry: dict) -> bool` (parks, starts, clears context; for drops and `queue_play`)
  - `advance() -> bool`, `next_cmd() -> None`, `prev_cmd() -> None`
  - `set_mode(mode: str) -> None` (raises `ValueError`)
  - `park() -> None`, `stop() -> None`, `tick() -> None`
  - `can_go_next() -> bool`, `can_go_previous() -> bool`
  - constants `RESTART_AFTER = 3.0`, `NEAR_END = 10.0`, `MAX_FAILS = 3`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_transport.py`:

```python
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlch.core import playqueue, transport

A = {"source": "fake", "id": "a", "title": "A", "kind": "track"}
B = {"source": "fake", "id": "b", "title": "B", "kind": "track"}
C = {"source": "fake", "id": "c", "title": "C", "kind": "track"}
KEXP = {"id": "kexp", "name": "KEXP", "url": "http://kexp.example/s"}
WXPN = {"id": "wxpn", "name": "WXPN", "url": "http://wxpn.example/s"}


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.patch(mock.patch.object(playqueue, "data_dir", lambda: Path(tmp.name)))
        self.player = self.patch(mock.patch.object(transport, "player"))
        self.player.current.return_value = None
        self.player.item_progress.return_value = (None, None)
        self.library = self.patch(mock.patch.object(transport, "library"))
        self.notify = self.patch(mock.patch.object(transport, "notify"))
        self.src = mock.Mock()
        self.src.resolve.side_effect = lambda item: f"target:{item['id']}"
        self.patch(mock.patch.dict("sqlch.sources.REGISTRY", {"fake": self.src}))
        transport._fails = 0

    def patch(self, p):
        m = p.start()
        self.addCleanup(p.stop)
        return m

    def item(self, it=A):
        return playqueue.make_entry("item", it)

    def station(self, st=KEXP):
        return playqueue.make_entry("station", st)

    def playing(self, entry, mode="media"):
        playqueue.set_mode(mode)
        playqueue.set_now(entry)

    def played_ids(self):
        return [c.args[1]["id"] for c in self.player.play_target.call_args_list]

    def state(self):
        return playqueue.read()


class TestStartItem(Base):
    def test_plays_sets_media_now_and_context(self):
        transport.start_item(B, context=[A, B, C])
        self.player.play_target.assert_called_once_with("target:b", B, start=None)
        s = self.state()
        self.assertEqual((s["mode"], s["now"]["item"]), ("media", B))
        self.assertEqual(s["context"]["index"], 1)

    def test_no_context_clears_the_old_one(self):
        transport.start_item(A, context=[A, B])
        transport.start_item(B)
        self.assertIsNone(self.state()["context"])

    def test_resume_uses_the_saved_point(self):
        with mock.patch.object(transport.progress, "get", return_value={"position": 300}), \
             mock.patch.object(transport.progress, "resume_point", return_value=300.0):
            transport.start_item(A, resume=True)
        self.player.play_target.assert_called_once_with("target:a", A, start=300.0)

    def test_unknown_source_and_resolve_errors(self):
        with self.assertRaisesRegex(transport.PlayError, "unknown source: nope"):
            transport.start_item({"source": "nope", "id": "x"})
        self.src.resolve.side_effect = FileNotFoundError("gone")
        with self.assertRaisesRegex(transport.PlayError, "resolve failed: gone"):
            transport.start_item(A)
        self.player.play_target.assert_not_called()

    def test_item_without_id_still_plays_but_is_not_recorded(self):
        transport.start_item({"source": "fake", "title": "t"})
        self.player.play_target.assert_called_once()
        self.assertIsNone(self.state()["now"])


class TestStartStation(Base):
    def test_sets_radio_and_now(self):
        self.player.current.return_value = {"type": "station"}
        transport.start_station(KEXP)
        self.player.play_station.assert_called_once_with(KEXP)
        s = self.state()
        self.assertEqual((s["mode"], s["now"]["station"]["id"]), ("radio", "kexp"))

    def test_parks_the_playing_item_first(self):
        self.player.current.return_value = {"type": "item", "item": A}
        self.player.item_progress.return_value = (120.0, 300.0)
        transport.start_station(KEXP)
        r = self.state()["resume"]
        self.assertEqual((r["entry"]["item"]["id"], r["pos"], r["dur"]), ("a", 120.0, 300.0))

    def test_station_that_would_not_start_changes_nothing(self):
        self.player.current.return_value = None
        transport.start_station(KEXP)
        self.assertEqual(self.state()["mode"], "radio")
        self.assertIsNone(self.state()["now"])


class TestPark(Base):
    def test_ignores_radio_idle_and_unloaded(self):
        for cur in (None, {"type": "station", "item": KEXP}):
            self.player.current.return_value = cur
            transport.park()
        self.player.current.return_value = {"type": "item", "item": A}
        self.player.item_progress.return_value = (0, None)
        transport.park()
        self.assertIsNone(self.state()["resume"])


class TestAdvance(Base):
    def test_plays_the_head_and_files_the_finished_one(self):
        a, b = self.item(A), self.item(B)
        self.playing(a)
        playqueue.add(b)
        self.assertTrue(transport.advance())
        self.assertEqual(self.played_ids(), ["b"])
        s = self.state()
        self.assertEqual((s["entries"], s["now"]["uid"], s["mode"]), ([], b["uid"], "media"))
        self.assertEqual([h["uid"] for h in s["history"]], [a["uid"]])

    def test_falls_back_to_the_context(self):
        playqueue.set_context([A, B, C], "a")
        self.playing(self.item(A))
        self.assertTrue(transport.advance())
        self.assertEqual(self.played_ids(), ["b"])
        self.assertTrue(transport.advance())
        self.assertEqual(self.played_ids(), ["b", "c"])
        self.assertFalse(transport.advance())

    def test_explicit_queue_beats_the_context(self):
        playqueue.set_context([A, B], "a")
        self.playing(self.item(A))
        playqueue.add(self.item(C))
        transport.advance()
        self.assertEqual(self.played_ids(), ["c"])

    def test_nothing_left(self):
        self.playing(self.item(A))
        self.assertFalse(transport.advance())
        self.player.play_target.assert_not_called()

    def test_station_entry_flips_to_radio_and_keeps_the_rest(self):
        self.playing(self.item(A))
        st, b = self.station(), self.item(B)
        playqueue.add(st)
        playqueue.add(b)
        self.player.current.return_value = {"type": "station"}
        self.assertTrue(transport.advance())
        self.player.play_station.assert_called_once_with(st["station"])
        s = self.state()
        self.assertEqual((s["mode"], s["now"]["uid"]), ("radio", st["uid"]))
        self.assertEqual([e["uid"] for e in s["entries"]], [b["uid"]])
        self.assertEqual((s["resume"]["entry"]["uid"], s["resume"]["pos"]), (b["uid"], 0.0))

    def test_station_entry_with_nothing_after_clears_resume(self):
        playqueue.set_resume(self.item(A), 50.0, 100.0)
        playqueue.add(self.station())
        self.player.current.return_value = {"type": "station"}
        transport.advance()
        self.assertIsNone(self.state()["resume"])

    def test_unplayable_entries_are_skipped_with_a_notice(self):
        self.playing(self.item(A))
        bad = self.item({"source": "fake", "id": "bad"})
        good = self.item(C)
        self.src.resolve.side_effect = (
            lambda item: (_ for _ in ()).throw(OSError("nope")) if item["id"] == "bad"
            else f"target:{item['id']}")
        playqueue.add(bad)
        playqueue.add(good)
        self.assertTrue(transport.advance())
        self.assertEqual(self.played_ids(), ["c"])
        self.notify.notify.assert_called_once()

    def test_three_failures_in_a_row_stop_advance(self):
        self.playing(self.item(A))
        self.src.resolve.side_effect = OSError("nope")
        for i in range(4):
            playqueue.add(self.item({"source": "fake", "id": f"x{i}"}))
        self.assertFalse(transport.advance())
        self.assertEqual(len(self.state()["entries"]), 1)  # the fourth was never tried
        self.assertEqual(transport._fails, 0)  # reset so the next press tries again


class TestNextPrev(Base):
    def test_radio_next_and_prev_cycle_stations(self):
        self.player.current.return_value = {"type": "station", "item": KEXP}
        self.library.next_station.return_value = WXPN
        transport.next_cmd()
        self.library.next_station.assert_called_once_with("kexp")
        self.player.play_station.assert_called_with(WXPN)
        self.library.prev_station.return_value = KEXP
        transport.prev_cmd()
        self.library.prev_station.assert_called_once_with("kexp")

    def test_radio_next_when_idle_starts_the_first_station(self):
        self.library.list_stations.return_value = [KEXP, WXPN]
        transport.next_cmd()
        self.player.play_station.assert_called_once_with(KEXP)
        self.player.play_station.reset_mock()
        transport.prev_cmd()
        self.player.play_station.assert_called_once_with(WXPN)

    def test_media_next_advances(self):
        self.playing(self.item(A))
        playqueue.add(self.item(B))
        transport.next_cmd()
        self.assertEqual(self.played_ids(), ["b"])

    def test_media_prev_restarts_when_more_than_three_seconds_in(self):
        self.playing(self.item(A))
        playqueue.push_history(self.item(B))
        self.player.current.return_value = {"type": "item", "item": A}
        self.player.item_progress.return_value = (3.5, 100.0)
        transport.prev_cmd()
        self.player.seek.assert_called_once_with(0.0)
        self.player.play_target.assert_not_called()

    def test_media_prev_steps_back_and_requeues_the_current(self):
        a, b = self.item(A), self.item(B)
        self.playing(a)
        playqueue.push_history(b)
        self.player.current.return_value = {"type": "item", "item": A}
        self.player.item_progress.return_value = (2.0, 100.0)
        transport.prev_cmd()
        self.assertEqual(self.played_ids(), ["b"])
        s = self.state()
        self.assertEqual(s["now"]["uid"], b["uid"])
        self.assertEqual([e["uid"] for e in s["entries"]], [a["uid"]])
        self.assertEqual(s["history"], [])

    def test_media_prev_with_no_history_restarts(self):
        self.playing(self.item(A))
        self.player.current.return_value = {"type": "item", "item": A}
        self.player.item_progress.return_value = (1.0, 100.0)
        transport.prev_cmd()
        self.player.seek.assert_called_once_with(0.0)

    def test_media_prev_when_idle_does_nothing(self):
        self.playing(None)
        transport.prev_cmd()
        self.player.seek.assert_not_called()


class TestSetMode(Base):
    def test_to_media_resumes_at_the_saved_point(self):
        a = self.item(A)
        playqueue.set_resume(a, 100.0, 300.0)
        playqueue.add(a)  # as after a station entry: the head is also the resume entry
        transport.set_mode("media")
        self.player.play_target.assert_called_once_with("target:a", A, start=100.0)
        s = self.state()
        self.assertEqual((s["mode"], s["entries"], s["resume"]), ("media", [], None))

    def test_resume_near_the_end_starts_over(self):
        playqueue.set_resume(self.item(A), 295.0, 300.0)
        transport.set_mode("media")
        self.player.play_target.assert_called_once_with("target:a", A, start=None)

    def test_resume_before_the_minimum_starts_over(self):
        playqueue.set_resume(self.item(A), 5.0, 300.0)
        transport.set_mode("media")
        self.player.play_target.assert_called_once_with("target:a", A, start=None)

    def test_to_media_without_resume_plays_the_head(self):
        playqueue.add(self.item(B))
        transport.set_mode("media")
        self.assertEqual(self.played_ids(), ["b"])

    def test_to_media_with_nothing_only_flips_the_mode(self):
        transport.set_mode("media")
        self.player.play_target.assert_not_called()
        self.assertEqual(self.state()["mode"], "media")

    def test_to_radio_parks_then_starts_the_last_station(self):
        self.playing(self.item(A))
        self.player.current.return_value = {"type": "item", "item": A}
        self.player.item_progress.return_value = (60.0, 200.0)
        self.library.last_played_station.return_value = KEXP

        def started(st):
            self.player.current.return_value = {"type": "station"}
        self.player.play_station.side_effect = started
        transport.set_mode("radio")
        self.player.play_station.assert_called_once_with(KEXP)
        s = self.state()
        self.assertEqual((s["mode"], s["resume"]["pos"]), ("radio", 60.0))

    def test_to_radio_without_a_last_station_only_flips(self):
        self.playing(self.item(A))
        self.library.last_played_station.return_value = None
        transport.set_mode("radio")
        self.player.play_station.assert_not_called()
        self.assertEqual(self.state()["mode"], "radio")

    def test_same_mode_is_a_no_op(self):
        transport.set_mode("radio")
        self.player.play_station.assert_not_called()

    def test_unknown_mode_raises(self):
        with self.assertRaises(ValueError):
            transport.set_mode("shuffle")


class TestPlayEntry(Base):
    def test_item_entry_plays_and_drops_the_context(self):
        playqueue.set_context([A, B], "a")
        self.assertTrue(transport.play_entry(self.item(C)))
        self.assertEqual(self.played_ids(), ["c"])
        self.assertIsNone(self.state()["context"])

    def test_failed_entry_returns_false(self):
        self.src.resolve.side_effect = OSError("nope")
        self.assertFalse(transport.play_entry(self.item(C)))


class TestTick(Base):
    def setUp(self):
        super().setUp()
        self.player.current.return_value = {"type": "item", "item": A}

    def test_not_ended_does_nothing(self):
        self.player.playback_ended.return_value = False
        playqueue.add(self.item(B))
        transport.tick()
        self.player.play_target.assert_not_called()

    def test_radio_and_idle_do_nothing(self):
        self.player.playback_ended.return_value = True
        for cur in (None, {"type": "station", "item": KEXP}):
            self.player.current.return_value = cur
            transport.tick()
        self.player.play_target.assert_not_called()
        self.player.stop.assert_not_called()

    def test_ended_advances(self):
        self.player.playback_ended.return_value = True
        playqueue.add(self.item(B))
        transport.tick()
        self.assertEqual(self.played_ids(), ["b"])

    def test_ended_with_nothing_left_stops_and_clears(self):
        self.player.playback_ended.return_value = True
        self.playing(self.item(A))
        playqueue.set_resume(self.item(A), 299.0, 300.0)
        transport.tick()
        self.player.stop.assert_called_once_with(notify_user=False)
        s = self.state()
        self.assertEqual((s["now"], s["resume"]), (None, None))

    def test_ended_handoff_is_left_to_autoplay(self):
        self.player.current.return_value = {"type": "item", "item": A, "handoff": "spotify"}
        self.player.playback_ended.return_value = True
        transport.tick()
        self.player.stop.assert_not_called()


class TestStop(Base):
    def test_parks_stops_and_clears_now(self):
        self.playing(self.item(A))
        self.player.current.return_value = {"type": "item", "item": A}
        self.player.item_progress.return_value = (80.0, 200.0)
        transport.stop()
        self.player.stop.assert_called_once_with()
        s = self.state()
        self.assertEqual((s["now"], s["resume"]["pos"]), (None, 80.0))


class TestCanGo(Base):
    def test_radio_needs_stations(self):
        self.library.list_stations.return_value = []
        self.assertFalse(transport.can_go_next())
        self.assertFalse(transport.can_go_previous())
        self.library.list_stations.return_value = [KEXP]
        self.assertTrue(transport.can_go_next())
        self.assertTrue(transport.can_go_previous())

    def test_media_next_needs_entries_or_context(self):
        playqueue.set_mode("media")
        self.assertFalse(transport.can_go_next())
        playqueue.add(self.item(B))
        self.assertTrue(transport.can_go_next())
        playqueue.clear()
        playqueue.set_context([A, B], "a")
        self.assertTrue(transport.can_go_next())

    def test_media_previous_needs_history_or_something_playing(self):
        playqueue.set_mode("media")
        self.assertFalse(transport.can_go_previous())
        playqueue.push_history(self.item(B))
        self.assertTrue(transport.can_go_previous())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m unittest tests.test_transport -v`
Expected: ERROR `ImportError: cannot import name 'transport'`

- [ ] **Step 3: Write the module**

Create `sqlch/core/transport.py`:

```python
"""What plays next: queue advance, the radio/media mode, and parking media.

playqueue.py holds the state and knows nothing about playback; this module
drives player with it. Public functions take one lock because the daemon's
request thread and its end-of-playback tick both call in."""

import functools
import logging
import threading

from sqlch import sources
from sqlch.core import library, notify, player, playqueue, progress

log = logging.getLogger(__name__)

RESTART_AFTER = 3.0   # prev restarts the playing item when it is further in than this
NEAR_END = 10.0       # a parked item this close to its end starts over
MAX_FAILS = 3         # consecutive unplayable entries before advance gives up

_lock = threading.RLock()
_fails = 0


class PlayError(Exception):
    """An item could not be resolved or started; the message is user-facing."""


def _locked(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _lock:
            return fn(*args, **kwargs)
    return wrapper


def _resume_start(pos, dur) -> float | None:
    """Where a parked item restarts, or None to start it from the top."""
    if not isinstance(pos, (int, float)) or pos < progress.MIN_RESUME_SECS:
        return None
    if isinstance(dur, (int, float)) and dur > 0 and pos >= dur - NEAR_END:
        return None
    return float(pos)


def _play_item(item: dict, start: float | None = None) -> None:
    src = sources.REGISTRY.get(item.get("source"))
    if src is None:
        raise PlayError(f"unknown source: {item.get('source')}")
    try:
        target = src.resolve(item)
    except Exception as e:
        raise PlayError(f"resolve failed: {e}") from e
    player.play_target(target, item, start=start)


def _start_entry(entry: dict, start: float | None = None) -> bool:
    """Play one queue entry and record it as now playing. A failure is
    counted, announced and reported as False."""
    global _fails
    try:
        if entry["kind"] == "station":
            player.play_station(entry["station"])
            if player.current() is None:
                raise PlayError("station would not start")
            mode = "radio"
        else:
            _play_item(entry["item"], start)
            mode = "media"
    except Exception as e:
        _fails += 1
        notify.notify("sqlch error", f"Skipped {playqueue.entry_title(entry)}: {e}")
        return False
    _fails = 0
    playqueue.set_mode(mode)
    playqueue.set_now(entry)
    if mode == "radio":
        # a radio entry never ends, so the next queued item is what media picks up
        waiting = [e for e in playqueue.read()["entries"] if e["kind"] == "item"]
        if waiting:
            playqueue.set_resume(waiting[0], 0.0, None)
        else:
            playqueue.clear_resume()
    return True


# ---- starting things ----

@_locked
def start_item(item: dict, *, context: list | None = None, resume: bool = False) -> None:
    start = None
    if resume:
        start = progress.resume_point(progress.get(item.get("source"), item.get("id")))
    _play_item(item, start)
    global _fails
    _fails = 0
    playqueue.set_mode("media")
    if item.get("id"):
        playqueue.set_now(playqueue.make_entry("item", item))
        playqueue.set_context(context, item["id"])


@_locked
def start_station(station: dict) -> None:
    park()
    player.play_station(station)
    if player.current() is None:
        return  # play_station refused (missing or bad url); it already said so
    playqueue.set_mode("radio")
    try:
        playqueue.set_now(playqueue.make_entry("station", station))
    except ValueError:
        playqueue.set_now(None)


@_locked
def play_entry(entry: dict) -> bool:
    """Play an entry the user picked (a drop on an idle player, a jump in the
    playlist). It starts a fresh run, so the old context no longer applies."""
    park()
    if not _start_entry(entry):
        return False
    playqueue.set_context(None, None)
    return True


@_locked
def stop() -> None:
    park()
    player.stop()
    playqueue.set_now(None)


# ---- parking ----

@_locked
def park() -> None:
    """Save where the playing item is, so flipping back to media (or a
    restart) can pick it up. Cheap enough to call every few seconds."""
    cur = player.current()
    if not cur or cur.get("type") != "item":
        return
    pos, dur = player.item_progress()
    # mpv reports nothing or 0 until the file is loaded
    if not isinstance(pos, (int, float)) or pos < 1:
        return
    try:
        entry = playqueue.make_entry("item", cur["item"])
    except ValueError:
        return
    playqueue.set_resume(entry, pos, dur)


# ---- moving on ----

@_locked
def advance() -> bool:
    """Play the next queue entry, else the next item of the list the playing
    item came from. False when nothing is left or too many entries failed."""
    global _fails
    finished = playqueue.read()["now"]
    while _fails < MAX_FAILS:
        entry = playqueue.pop_head()
        if entry is None:
            item = playqueue.next_in_context()
            if item is None:
                return False
            entry = playqueue.make_entry("item", item)
        if _start_entry(entry):
            if finished:
                playqueue.push_history(finished)
            return True
    _fails = 0
    notify.notify("sqlch", "Queue stopped: too many entries failed to play")
    return False


def _cycle_station(forward: bool) -> None:
    cur = player.current()
    if cur:
        sid = (cur.get("item") or {}).get("id")
        st = (library.next_station if forward else library.prev_station)(sid)
    else:
        stations = library.list_stations()
        st = (stations[0] if forward else stations[-1]) if stations else None
    if st:
        start_station(st)


@_locked
def next_cmd() -> None:
    if playqueue.read()["mode"] == "radio":
        _cycle_station(True)
    else:
        advance()


@_locked
def prev_cmd() -> None:
    state = playqueue.read()
    if state["mode"] == "radio":
        _cycle_station(False)
        return
    if player.current() is None:
        return
    pos, _ = player.item_progress()
    if (isinstance(pos, (int, float)) and pos > RESTART_AFTER) or not state["history"]:
        player.seek(0.0)
        return
    entry = playqueue.pop_history()
    if state["now"]:
        playqueue.add(state["now"], play_next=True)  # next goes forward again
    _start_entry(entry)


@_locked
def set_mode(mode: str) -> None:
    if mode not in playqueue.MODES:
        raise ValueError(f"unknown mode: {mode}")
    state = playqueue.read()
    if mode == state["mode"]:
        return
    if mode == "radio":
        st = library.last_played_station()
        if st:
            start_station(st)
        else:
            park()
            playqueue.set_mode("radio")
        return
    playqueue.set_mode("media")  # even if nothing starts, next/prev now follow the queue
    resume = state["resume"]
    if resume:
        entry = resume["entry"]
        playqueue.remove(entry["uid"])  # it may also sit at the head of the queue
        playqueue.clear_resume()
        if _start_entry(entry, start=_resume_start(resume["pos"], resume["dur"])):
            return
    advance()


@_locked
def tick() -> None:
    """About once a second: move on when the playing item has ended."""
    cur = player.current()
    if not cur or cur.get("type") != "item" or not player.playback_ended():
        return
    if advance():
        return
    if cur.get("handoff"):
        return  # the external player may carry on by itself (autoplay)
    player.stop(notify_user=False)
    playqueue.set_now(None)
    playqueue.clear_resume()


# ---- for MPRIS ----

def can_go_next() -> bool:
    s = playqueue.read()
    if s["mode"] == "radio":
        return bool(library.list_stations())
    ctx = s["context"]
    return bool(s["entries"]) or bool(ctx and ctx["index"] + 1 < len(ctx["items"]))


def can_go_previous() -> bool:
    s = playqueue.read()
    if s["mode"] == "radio":
        return bool(library.list_stations())
    return bool(s["history"]) or s["now"] is not None
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m unittest tests.test_transport -v`
Expected: all PASS. If a test fails because of ordering inside `start_item` (the `global _fails` statement must precede first use in the function in Python ≥3.12 style checkers), move the `global _fails` line to the top of `start_item`.

- [ ] **Step 5: Commit**

```bash
git add sqlch/core/transport.py tests/test_transport.py
git commit -m "sqlch: transport (advance, next/prev, radio/media mode, parking)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Daemon wiring

**Files:**
- Modify: `sqlch/core/daemon.py`
- Modify: `sqlch/sources/__init__.py:12` (`RESERVED`)
- Test: `tests/test_daemon_queue.py`; existing `tests/test_player_items.py`, `tests/test_daemon_progress.py` must keep passing

**Interfaces:**
- Consumes: Task 3 `transport.*`, Task 1 `playqueue.*`, `player.current()`
- Produces: daemon commands
  - `queue_add` `{kind, payload, at?, play_next?}` → `{ok, uid, index, played}`
  - `queue_remove` `{uid}`, `queue_move` `{uid, to}`, `queue_clear`, `queue_play` `{uid}`, `set_mode` `{mode}`
  - `play_item` gains optional `context: [item]`
  - `status` gains `mode`, `queue_len`
  - `daemon.TICK_EVERY = 1`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_daemon_queue.py`:

```python
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlch.core import daemon, playqueue

TRACK = {"source": "fake", "id": "a", "title": "A", "kind": "track"}
KEXP = {"id": "kexp", "name": "KEXP", "url": "http://kexp.example/s"}


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = mock.patch.object(playqueue, "data_dir", lambda: Path(tmp.name))
        p.start()
        self.addCleanup(p.stop)
        self.transport = mock.patch.object(daemon, "transport").start()
        self.addCleanup(mock.patch.stopall)
        self.player = mock.patch.object(daemon, "player").start()
        self.player.current.return_value = None
        self.transport.play_entry.return_value = True

    def call(self, **msg):
        return daemon._handle(msg)

    def uids(self):
        return [e["uid"] for e in playqueue.read()["entries"]]


class TestQueueAdd(Base):
    def test_queues_when_something_is_waiting(self):
        playqueue.add(playqueue.make_entry("item", TRACK))
        r = self.call(cmd="queue_add", kind="station", payload=KEXP)
        self.assertEqual((r["ok"], r["played"], r["index"]), (True, False, 1))
        self.assertEqual(len(self.uids()), 2)
        self.transport.play_entry.assert_not_called()

    def test_queues_when_something_is_playing(self):
        self.player.current.return_value = {"type": "item", "item": TRACK}
        r = self.call(cmd="queue_add", kind="station", payload=KEXP)
        self.assertFalse(r["played"])
        self.assertEqual(len(self.uids()), 1)

    def test_plays_at_once_when_idle_and_empty(self):
        r = self.call(cmd="queue_add", kind="station", payload=KEXP)
        self.assertEqual((r["ok"], r["played"]), (True, True))
        self.assertEqual(self.uids(), [])
        (entry,), _ = self.transport.play_entry.call_args
        self.assertEqual(entry["station"]["id"], "kexp")

    def test_idle_play_failure_is_reported(self):
        self.transport.play_entry.return_value = False
        r = self.call(cmd="queue_add", kind="station", payload=KEXP)
        self.assertFalse(r["ok"])
        self.assertIn("error", r)

    def test_at_and_play_next(self):
        a = playqueue.make_entry("item", TRACK)
        playqueue.add(a)
        self.call(cmd="queue_add", kind="station", payload=KEXP, at=0)
        self.assertEqual(playqueue.read()["entries"][0]["kind"], "station")
        self.call(cmd="queue_add", kind="item", payload={**TRACK, "id": "z"}, play_next=True)
        self.assertEqual(playqueue.read()["entries"][0]["item"]["id"], "z")

    def test_bad_payload(self):
        self.assertFalse(self.call(cmd="queue_add", kind="item", payload={})["ok"])
        self.assertFalse(self.call(cmd="queue_add")["ok"])


class TestQueueEdits(Base):
    def setUp(self):
        super().setUp()
        self.a = playqueue.make_entry("item", TRACK)
        self.b = playqueue.make_entry("station", KEXP)
        playqueue.add(self.a)
        playqueue.add(self.b)

    def test_remove(self):
        self.assertTrue(self.call(cmd="queue_remove", uid=self.a["uid"])["ok"])
        self.assertEqual(self.uids(), [self.b["uid"]])
        self.assertFalse(self.call(cmd="queue_remove", uid="nope")["ok"])

    def test_move(self):
        self.assertTrue(self.call(cmd="queue_move", uid=self.a["uid"], to=1)["ok"])
        self.assertEqual(self.uids(), [self.b["uid"], self.a["uid"]])
        self.assertFalse(self.call(cmd="queue_move", uid="nope", to=0)["ok"])
        self.assertFalse(self.call(cmd="queue_move", uid=self.a["uid"])["ok"])
        self.assertFalse(self.call(cmd="queue_move", uid=self.a["uid"], to="1")["ok"])

    def test_clear(self):
        self.assertTrue(self.call(cmd="queue_clear")["ok"])
        self.assertEqual(self.uids(), [])

    def test_play_jumps_and_drops_the_ones_before(self):
        self.assertTrue(self.call(cmd="queue_play", uid=self.b["uid"])["ok"])
        (entry,), _ = self.transport.play_entry.call_args
        self.assertEqual(entry["uid"], self.b["uid"])
        self.assertEqual(self.uids(), [])
        self.assertFalse(self.call(cmd="queue_play", uid="nope")["ok"])


class TestSetModeAndStatus(Base):
    def test_set_mode(self):
        self.assertEqual(self.call(cmd="set_mode", mode="media"), {"ok": True})
        self.transport.set_mode.assert_called_once_with("media")

    def test_set_mode_rejects_unknown(self):
        self.transport.set_mode.side_effect = ValueError("unknown mode: x")
        r = self.call(cmd="set_mode", mode="x")
        self.assertEqual((r["ok"], r["error"]), (False, "unknown mode: x"))

    def test_status_reports_mode_and_queue_length(self):
        playqueue.set_mode("media")
        playqueue.add(playqueue.make_entry("item", TRACK))
        rec = mock.Mock(status=mock.Mock(return_value={"active": False}))
        self.player.status_string.return_value = "s"
        with mock.patch.dict("sys.modules", {"sqlch.core.recorder": rec}):
            r = self.call(cmd="status")
        self.assertEqual((r["mode"], r["queue_len"]), ("media", 1))


class TestRouting(Base):
    def test_next_prev_stop_go_through_transport(self):
        with mock.patch.object(daemon, "track_once"):
            self.call(cmd="next")
            self.transport.next_cmd.assert_called_once_with()
            self.call(cmd="prev")
            self.transport.prev_cmd.assert_called_once_with()
            self.call(cmd="stop")
            self.transport.stop.assert_called_once_with()

    def test_play_station_goes_through_transport(self):
        with mock.patch.object(daemon, "track_once"), \
             mock.patch.object(daemon.library, "find_station", return_value=KEXP):
            r = self.call(cmd="play", query="kexp")
        self.assertTrue(r["ok"])
        self.transport.start_station.assert_called_once_with(KEXP)

    def test_play_item_passes_context_and_resume(self):
        with mock.patch.object(daemon, "track_once"):
            r = self.call(cmd="play_item", item=TRACK, context=[TRACK], resume=True)
        self.assertEqual(r, {"ok": True})
        self.transport.start_item.assert_called_once_with(TRACK, context=[TRACK], resume=True)

    def test_play_item_ignores_a_non_list_context(self):
        with mock.patch.object(daemon, "track_once"):
            self.call(cmd="play_item", item=TRACK, context="junk")
        self.transport.start_item.assert_called_once_with(TRACK, context=None, resume=False)

    def test_play_item_error_is_returned(self):
        self.transport.PlayError = Exception
        self.transport.start_item.side_effect = Exception("resolve failed: x")
        with mock.patch.object(daemon, "track_once"):
            r = self.call(cmd="play_item", item=TRACK)
        self.assertEqual((r["ok"], r["error"]), (False, "resolve failed: x"))


class TestLoops(Base):
    def test_track_loop_body_parks_and_swallows_errors(self):
        with mock.patch.object(daemon, "track_once", side_effect=RuntimeError("x")):
            daemon.sample_once()
        self.transport.park.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m unittest tests.test_daemon_queue -v`
Expected: FAIL/ERROR (`daemon` has no attribute `transport`).

- [ ] **Step 3: Reserve the window name**

In `sqlch/sources/__init__.py` change line 12:

```python
RESERVED = ("library", "discover", "np", "radio", "playlist")
```

(`radio` was already a docked window name that no source may take; reserving both here keeps the list authoritative. If `tests/test_sources.py` asserts the exact `RESERVED` tuple, update that assertion to match.)

- [ ] **Step 4: Wire the daemon**

In `sqlch/core/daemon.py`:

1. Imports: change the `from sqlch.core import ...` line to
   `from sqlch.core import discover, follows, library, notify, player, playqueue, progress, transport, watcher`.

2. Constants and loops. Replace the block from `TRACK_EVERY = 5` through `_track_loop` with:

```python
TRACK_EVERY = 5  # seconds between playhead samples
TICK_EVERY = 1   # seconds between end-of-playback checks
_FLUSH_BEFORE = {'stop', 'play', 'play_item', 'next', 'prev', 'queue_play', 'set_mode'}


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


def sample_once() -> None:
    """One playhead sample: the video's watch progress, and the parked
    position the queue resumes from."""
    for sample in (track_once, transport.park):
        try:
            sample()
        except Exception:
            pass


def _track_loop() -> None:
    while True:
        time.sleep(TRACK_EVERY)
        sample_once()


def _tick_loop() -> None:
    while True:
        time.sleep(TICK_EVERY)
        try:
            transport.tick()
        except Exception:
            pass
```

3. In `_handle`, status branch: just before `return resp` in the `status` command add
   `state = playqueue.read()` and
   `resp['mode'], resp['queue_len'] = state['mode'], len(state['entries'])`.

4. `stop`: replace `player.stop()` in the `if cmd == 'stop':` branch with `transport.stop()`.

5. `play`: replace the three `player.play_station(st)` calls inside `if cmd == 'play':` with `transport.start_station(st)`.

6. `play_item`: replace the whole branch with:

```python
    if cmd == 'play_item':
        item = msg.get('item')
        if not isinstance(item, dict):
            return {'ok': False, 'error': 'missing item'}
        context = msg.get('context')
        try:
            transport.start_item(item, context=context if isinstance(context, list) else None,
                                 resume=bool(msg.get('resume')))
        except transport.PlayError as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True}
```

7. `next` / `prev`: replace each branch body (everything between `if cmd == 'next':` and the following `return {'ok': True}`) with `transport.next_cmd()` / `transport.prev_cmd()` followed by `return {'ok': True}`.

8. New commands, inserted just before `if cmd == 'drain_notices':`:

```python
    if cmd == 'queue_add':
        try:
            entry = playqueue.make_entry(msg.get('kind'), msg.get('payload'))
        except ValueError as e:
            return {'ok': False, 'error': str(e)}
        if not playqueue.read()['entries'] and player.current() is None:
            # nothing waiting and nothing playing: a drop starts right away
            ok = transport.play_entry(entry)
            resp = {'ok': ok, 'uid': entry['uid'], 'played': True}
            if not ok:
                resp['error'] = 'could not play it'
            return resp
        at = msg.get('at')
        index = playqueue.add(entry, at=at if isinstance(at, int) else None,
                              play_next=bool(msg.get('play_next')))
        return {'ok': True, 'uid': entry['uid'], 'index': index, 'played': False}
    if cmd == 'queue_remove':
        if playqueue.remove(str(msg.get('uid'))):
            return {'ok': True}
        return {'ok': False, 'error': 'unknown uid'}
    if cmd == 'queue_move':
        to = msg.get('to')
        if not isinstance(to, int) or isinstance(to, bool):
            return {'ok': False, 'error': 'missing to'}
        if playqueue.move(str(msg.get('uid')), to):
            return {'ok': True}
        return {'ok': False, 'error': 'unknown uid'}
    if cmd == 'queue_clear':
        playqueue.clear()
        return {'ok': True}
    if cmd == 'queue_play':
        entry = playqueue.take(str(msg.get('uid')))
        if entry is None:
            return {'ok': False, 'error': 'unknown uid'}
        if transport.play_entry(entry):
            return {'ok': True}
        return {'ok': False, 'error': 'could not play it'}
    if cmd == 'set_mode':
        try:
            transport.set_mode(msg.get('mode'))
        except ValueError as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True}
```

9. `run_daemon`: after the `threading.Thread(target=_track_loop, ...)` line add
   `threading.Thread(target=_tick_loop, daemon=True, name="queue-tick").start()`.

- [ ] **Step 5: Run the new and the existing daemon tests**

Run: `python -m unittest tests.test_daemon_queue tests.test_daemon_progress tests.test_player_items tests.test_daemon_follows tests.test_sources -v 2>&1 | tail -30`
Expected: all PASS. `test_daemon_progress.TestPlayItemResume` and `test_player_items.TestDaemonItems` exercise the real `transport.start_item` through `daemon._handle` (they patch `sources.REGISTRY`, `progress.get`, `player.play_target`, which `transport` reads through the same module objects); `tests/__init__.py` keeps their `queue.json` writes in a temp dir.

- [ ] **Step 6: Commit**

```bash
git add sqlch/core/daemon.py sqlch/sources/__init__.py tests/test_daemon_queue.py
git commit -m "sqlch: daemon queue commands, mode, end-of-playback tick, status fields

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: CLI

**Files:**
- Modify: `sqlch/cli/main.py` (help text near line 39, dispatch before `if cmd == 'status':` near line 139, new functions after `spotify_login_cmd`)
- Test: `tests/test_cli_queue.py`

**Interfaces:**
- Consumes: `playqueue.read()`, `playqueue.entry_label()`, `library.find_station(query)`, `is_stream_url(url)`, `daemon_call(payload)`
- Produces: `main.queue_cmd(args: list[str]) -> None`, `main.mode_cmd(args: list[str]) -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_queue.py`:

```python
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from sqlch.cli import main
from sqlch.core import playqueue

KEXP = {"id": "kexp", "name": "KEXP", "url": "http://kexp.example/s", "group": "x"}


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = mock.patch.object(playqueue, "data_dir", lambda: Path(tmp.name))
        p.start()
        self.addCleanup(p.stop)

    def run_cmd(self, fn, args, call=None):
        with mock.patch.object(main, "daemon_call", call or mock.Mock(return_value={"ok": True})) as dc, \
                redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            try:
                fn(args)
                code = None
            except SystemExit as e:
                code = e.code
        return dc, code, out.getvalue(), err.getvalue()


class TestQueueList(Base):
    def test_empty(self):
        _, code, out, _ = self.run_cmd(main.queue_cmd, [])
        self.assertIsNone(code)
        self.assertEqual(out.strip(), "mode: radio")

    def test_lists_now_and_entries(self):
        playqueue.set_mode("media")
        playqueue.set_now(playqueue.make_entry("item", {"source": "x", "id": "1", "title": "Now", "artist": "Me"}))
        playqueue.add(playqueue.make_entry("station", KEXP))
        playqueue.add(playqueue.make_entry("item", {"source": "x", "id": "2", "title": "Later"}))
        _, _, out, _ = self.run_cmd(main.queue_cmd, ["list"])
        self.assertEqual(out.splitlines(), ["mode: media", "now:  Now — Me",
                                            "  1. KEXP", "  2. Later"])


class TestQueueAdd(Base):
    def test_adds_a_known_station(self):
        with mock.patch.object(main.library, "find_station", return_value=KEXP):
            dc, code, _, _ = self.run_cmd(main.queue_cmd, ["add", "kexp"])
        self.assertIsNone(code)
        dc.assert_called_once_with({"cmd": "queue_add", "kind": "station",
                                    "payload": {"id": "kexp", "name": "KEXP",
                                                "url": "http://kexp.example/s"}})

    def test_adds_a_bare_stream_url(self):
        with mock.patch.object(main.library, "find_station", return_value=None):
            dc, _, _, _ = self.run_cmd(main.queue_cmd, ["add", "http://x.example/live"])
        payload = dc.call_args.args[0]["payload"]
        self.assertEqual((payload["name"], payload["url"]),
                         ("http://x.example/live", "http://x.example/live"))

    def test_unknown_station_exits_nonzero(self):
        with mock.patch.object(main.library, "find_station", return_value=None):
            dc, code, _, err = self.run_cmd(main.queue_cmd, ["add", "nonsense"])
        self.assertEqual(code, 1)
        dc.assert_not_called()
        self.assertIn("nonsense", err)

    def test_add_needs_an_argument(self):
        _, code, _, err = self.run_cmd(main.queue_cmd, ["add"])
        self.assertEqual(code, 2)
        self.assertIn("usage", err)

    def test_daemon_down(self):
        with mock.patch.object(main.library, "find_station", return_value=KEXP):
            _, code, _, err = self.run_cmd(main.queue_cmd, ["add", "kexp"],
                                           call=mock.Mock(return_value=None))
        self.assertEqual(code, 1)
        self.assertIn("daemon", err)

    def test_daemon_error_is_shown(self):
        with mock.patch.object(main.library, "find_station", return_value=KEXP):
            _, code, _, err = self.run_cmd(main.queue_cmd, ["add", "kexp"],
                                           call=mock.Mock(return_value={"ok": False, "error": "boom"}))
        self.assertEqual(code, 1)
        self.assertIn("boom", err)


class TestQueueClear(Base):
    def test_clear(self):
        dc, code, _, _ = self.run_cmd(main.queue_cmd, ["clear"])
        self.assertIsNone(code)
        dc.assert_called_once_with({"cmd": "queue_clear"})

    def test_unknown_subcommand(self):
        _, code, _, err = self.run_cmd(main.queue_cmd, ["shuffle"])
        self.assertEqual(code, 2)
        self.assertIn("usage", err)


class TestMode(Base):
    def test_shows_the_mode(self):
        playqueue.set_mode("media")
        dc, _, out, _ = self.run_cmd(main.mode_cmd, [])
        self.assertEqual(out.strip(), "media")
        dc.assert_not_called()

    def test_sets_the_mode(self):
        dc, code, _, _ = self.run_cmd(main.mode_cmd, ["radio"])
        self.assertIsNone(code)
        dc.assert_called_once_with({"cmd": "set_mode", "mode": "radio"})

    def test_rejects_unknown_mode(self):
        dc, code, _, err = self.run_cmd(main.mode_cmd, ["shuffle"])
        self.assertEqual(code, 2)
        dc.assert_not_called()
        self.assertIn("usage", err)

    def test_daemon_down(self):
        _, code, _, err = self.run_cmd(main.mode_cmd, ["media"], call=mock.Mock(return_value=None))
        self.assertEqual(code, 1)
        self.assertIn("daemon", err)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m unittest tests.test_cli_queue -v`
Expected: FAIL `AttributeError: module 'sqlch.cli.main' has no attribute 'queue_cmd'`

- [ ] **Step 3: Implement**

In `sqlch/cli/main.py`:

1. Imports: change `from sqlch.core import player, library, discover` to
   `from sqlch.core import player, library, discover, playqueue` and add
   `from sqlch.core.urlcheck import is_stream_url` below the `client` import.

2. Help text: append, after the `'Spotify:\n'` block (keep the closing paren):

```python
    '\n'
    'Queue:\n'
    '  sqlch queue                      (list entries and the mode)\n'
    '  sqlch queue add <id|name|url>    (add a station)\n'
    '  sqlch queue clear\n'
    '  sqlch mode [radio|media]         (what next/prev walk)\n'
```

3. Dispatch: insert before `if cmd == 'status':`:

```python
    if cmd == 'queue':
        queue_cmd(args)
        return
    if cmd == 'mode':
        mode_cmd(args)
        return
```

4. Functions, after `spotify_login_cmd`/its usage constants (anywhere at module level above `main`'s use is fine since they resolve at call time):

```python
QUEUE_USAGE = 'usage: sqlch queue [list | add <id|name|url> | clear]'
MODE_USAGE = 'usage: sqlch mode [radio|media]'


def _queue_call(payload: dict) -> None:
    resp = daemon_call(payload)
    if resp is None:
        print('sqlch: daemon not running', file=sys.stderr)
        sys.exit(1)
    if not resp.get('ok', True):
        print(f"sqlch: {resp.get('error') or 'daemon refused'}", file=sys.stderr)
        sys.exit(1)


def queue_cmd(args: list[str]) -> None:
    sub = args[0] if args else 'list'
    if sub == 'list':
        state = playqueue.read()
        print(f"mode: {state['mode']}")
        if state['now']:
            print(f"now:  {playqueue.entry_label(state['now'])}")
        for i, entry in enumerate(state['entries'], 1):
            print(f"{i:>3}. {playqueue.entry_label(entry)}")
        return
    if sub == 'clear':
        _queue_call({'cmd': 'queue_clear'})
        return
    if sub == 'add':
        query = ' '.join(args[1:]).strip()
        if not query:
            print(QUEUE_USAGE, file=sys.stderr)
            sys.exit(2)
        st = library.find_station(query)
        if st is None and is_stream_url(query):
            st = {'name': query, 'url': query}
        if st is None:
            print(f'sqlch: no station or stream called {query!r}', file=sys.stderr)
            sys.exit(1)
        _queue_call({'cmd': 'queue_add', 'kind': 'station',
                     'payload': {'id': st.get('id'), 'name': st.get('name'),
                                 'url': st.get('url')}})
        return
    print(QUEUE_USAGE, file=sys.stderr)
    sys.exit(2)


def mode_cmd(args: list[str]) -> None:
    if not args:
        print(playqueue.read()['mode'])
        return
    if len(args) != 1 or args[0] not in playqueue.MODES:
        print(MODE_USAGE, file=sys.stderr)
        sys.exit(2)
    _queue_call({'cmd': 'set_mode', 'mode': args[0]})
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m unittest tests.test_cli_queue tests.test_cli_spotify -v 2>&1 | tail -5`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add sqlch/cli/main.py tests/test_cli_queue.py
git commit -m "sqlch: queue and mode commands

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: MPRIS Next/Previous

**Files:**
- Modify: `sqlch/core/mpris_daemon.py` (XML near line 68, class attrs near line 163, methods near line 99)
- Test: `tests/test_mpris_queue.py`

**Interfaces:**
- Consumes: `transport.next_cmd()`, `transport.prev_cmd()`, `transport.can_go_next()`, `transport.can_go_previous()`
- Produces: D-Bus `Next` / `Previous` methods, dynamic `CanGoNext` / `CanGoPrevious`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mpris_queue.py`:

```python
import unittest
from unittest import mock

from sqlch.core import mpris_daemon


class TestMprisTransport(unittest.TestCase):
    def setUp(self):
        self.t = mock.patch.object(mpris_daemon, "transport").start()
        self.addCleanup(mock.patch.stopall)
        self.m = mpris_daemon.SQLCHMPRIS()

    def test_next_and_previous_call_the_transport(self):
        self.m.Next()
        self.t.next_cmd.assert_called_once_with()
        self.m.Previous()
        self.t.prev_cmd.assert_called_once_with()

    def test_can_go_follows_the_transport(self):
        self.t.can_go_next.return_value = True
        self.t.can_go_previous.return_value = False
        self.assertTrue(self.m.CanGoNext)
        self.assertFalse(self.m.CanGoPrevious)

    def test_get_all_reports_them(self):
        self.t.can_go_next.return_value = True
        self.t.can_go_previous.return_value = True
        props = self.m.GetAll("org.mpris.MediaPlayer2.Player")
        self.assertTrue(props["CanGoNext"].get_boolean())

    def test_introspection_lists_the_methods(self):
        self.assertIn('<method name="Next"/>', mpris_daemon.MPRIS_XML)
        self.assertIn('<method name="Previous"/>', mpris_daemon.MPRIS_XML)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m unittest tests.test_mpris_queue -v`
Expected: FAIL (`mpris_daemon` has no `transport`).

- [ ] **Step 3: Implement**

In `sqlch/core/mpris_daemon.py`:

1. Import (next to `from sqlch.core import enrich`): `from sqlch.core import enrich, transport`.
2. In `MPRIS_XML`, in the `org.mpris.MediaPlayer2.Player` interface, after `<method name="Stop"/>` add:
```xml
    <method name="Next"/>
    <method name="Previous"/>
```
3. Delete the two class attributes `CanGoNext = False` and `CanGoPrevious = False`, and add these properties next to `Position`:

```python
    @property
    def CanGoNext(self) -> bool:
        return transport.can_go_next()

    @property
    def CanGoPrevious(self) -> bool:
        return transport.can_go_previous()
```
4. Add the methods after `PlayPause`:

```python
    def Next(self) -> None:
        transport.next_cmd()

    def Previous(self) -> None:
        transport.prev_cmd()
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m unittest tests.test_mpris_queue -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add sqlch/core/mpris_daemon.py tests/test_mpris_queue.py
git commit -m "sqlch: MPRIS Next/Previous follow the radio/media mode

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Playlist pane (GUI) and window registration

**Files:**
- Create: `sqlch_gui/ui/playlist_math.py`, `sqlch_gui/ui/dnd.py`, `sqlch_gui/ui/playlist_pane.py`
- Modify: `sqlch_gui/ui/dock_state.py:9` (`NAMES`), `sqlch_gui/ui/dock_manager.py:14` (`_TITLES`), `sqlch_gui/ui/controls.py` (`NavColumn._TABS`), `sqlch_gui/ui/window.py:94-98` (panels)
- Test: `tests/test_playlist_math.py`, `tests/test_dnd.py`, `tests/test_playlist_pane.py`; existing `tests/test_dock_state.py`, `tests/test_nav_column.py`, `tests/test_dock.py` must still pass

**Interfaces:**
- Consumes: `playqueue.read()`, `playqueue.path()`, `playqueue.entry_title/entry_subtitle`, `daemon.send`, `source_pane._thread_run`, `timefmt.format_duration`, daemon commands from Task 4
- Produces:
  - `playlist_math.insert_index(mids: list[float], y: float) -> int`, `playlist_math.move_target(src: int, drop: int) -> int`
  - `dnd.PREFIX`, `dnd.encode(payload: dict) -> str`, `dnd.decode(text) -> dict | None`, `dnd.station_payload(station: dict) -> dict`, `dnd.queue_msg(kind: str, payload: dict, play_next: bool = False) -> dict`, `dnd.attach_drag(widget, payload: dict) -> None`
  - `PlaylistPane(parent_window, read=playqueue.read, send=None, run_async=_thread_run, watch=True)` with `.refresh() -> bool`, `.on_shown()`, `._on_drop(target, value, x, y) -> bool`, `._midpoints() -> list[float]`

- [ ] **Step 1: Write the failing tests for the pure helpers**

Create `tests/test_playlist_math.py`:

```python
import unittest

from sqlch_gui.ui.playlist_math import insert_index, move_target


class TestInsertIndex(unittest.TestCase):
    MIDS = [10.0, 30.0, 50.0]

    def test_above_between_below(self):
        self.assertEqual(insert_index(self.MIDS, 0), 0)
        self.assertEqual(insert_index(self.MIDS, 10), 1)  # on a midpoint: after that row
        self.assertEqual(insert_index(self.MIDS, 29.9), 1)
        self.assertEqual(insert_index(self.MIDS, 40), 2)
        self.assertEqual(insert_index(self.MIDS, 999), 3)

    def test_empty_list(self):
        self.assertEqual(insert_index([], 12), 0)


class TestMoveTarget(unittest.TestCase):
    def test_moving_down_counts_after_removal(self):
        self.assertEqual(move_target(0, 3), 2)   # A to the very end of [A, B, C]
        self.assertEqual(move_target(0, 2), 1)

    def test_moving_up(self):
        self.assertEqual(move_target(2, 0), 0)
        self.assertEqual(move_target(2, 1), 1)

    def test_dropping_next_to_itself_is_a_no_op(self):
        self.assertEqual(move_target(1, 1), 1)
        self.assertEqual(move_target(1, 2), 1)


if __name__ == "__main__":
    unittest.main()
```

Create `tests/test_dnd.py`:

```python
import json
import unittest

from sqlch_gui.ui import dnd

KEXP = {"id": "kexp", "name": "KEXP", "url": "http://kexp.example/s", "group": "x"}
TRACK = {"source": "local", "id": "a", "title": "A"}


class TestPayload(unittest.TestCase):
    def test_round_trip(self):
        for p in ({"kind": "station", "payload": dnd.station_payload(KEXP)},
                  {"kind": "item", "payload": TRACK},
                  {"move": "abc123"}):
            self.assertEqual(dnd.decode(dnd.encode(p)), p)

    def test_station_payload_keeps_id_name_url(self):
        self.assertEqual(dnd.station_payload(KEXP),
                         {"id": "kexp", "name": "KEXP", "url": "http://kexp.example/s"})

    def test_decode_rejects_strangers(self):
        for text in (None, 5, "hello", "sqlch-queue:", "sqlch-queue:[1]",
                     "sqlch-queue:{bad", dnd.PREFIX + json.dumps({"kind": "nope", "payload": {}}),
                     dnd.PREFIX + json.dumps({"kind": "item", "payload": "x"}),
                     dnd.PREFIX + json.dumps({"move": 3})):
            self.assertIsNone(dnd.decode(text), text)

    def test_queue_msg(self):
        self.assertEqual(dnd.queue_msg("item", TRACK),
                         {"cmd": "queue_add", "kind": "item", "payload": TRACK,
                          "play_next": False})
        self.assertTrue(dnd.queue_msg("item", TRACK, play_next=True)["play_next"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m unittest tests.test_playlist_math tests.test_dnd -v`
Expected: ERROR `ModuleNotFoundError`.

- [ ] **Step 3: Write the helpers**

Create `sqlch_gui/ui/playlist_math.py`:

```python
"""Drop-position arithmetic for the Playlist pane, kept free of GTK."""


def insert_index(mids: list[float], y: float) -> int:
    """Which gap a drop at y lands in, among rows with vertical midpoints
    `mids` (gap 0 is above the first row)."""
    for i, mid in enumerate(mids):
        if y < mid:
            return i
    return len(mids)


def move_target(src: int, drop: int) -> int:
    """The `to` for playqueue.move when dragging row `src` into gap `drop`.
    Gaps are numbered with the dragged row still in the list, move() counts
    after it has been taken out."""
    return drop - 1 if drop > src else drop
```

Create `sqlch_gui/ui/dnd.py`:

```python
"""Drag payloads between panes. A tagged JSON string, so a stray text drop
onto the Playlist is ignored instead of queued."""

import json

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GObject, Gtk

PREFIX = "sqlch-queue:"


def encode(payload: dict) -> str:
    return PREFIX + json.dumps(payload)


def decode(text) -> dict | None:
    """A {"move": uid} reorder, or {"kind": "item"|"station", "payload": {...}}."""
    if not isinstance(text, str) or not text.startswith(PREFIX):
        return None
    try:
        data = json.loads(text[len(PREFIX):])
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    if "move" in data:
        return data if isinstance(data["move"], str) else None
    if data.get("kind") in ("item", "station") and isinstance(data.get("payload"), dict):
        return data
    return None


def station_payload(station: dict) -> dict:
    return {"id": station.get("id"), "name": station.get("name"), "url": station.get("url")}


def queue_msg(kind: str, payload: dict, play_next: bool = False) -> dict:
    return {"cmd": "queue_add", "kind": kind, "payload": payload, "play_next": play_next}


def attach_drag(widget, payload: dict) -> None:
    """Make `widget` a drag source carrying `payload`."""
    value = GObject.Value()
    value.init(GObject.TYPE_STRING)
    value.set_string(encode(payload))
    source = Gtk.DragSource()
    source.set_actions(Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
    source.connect("prepare", lambda _s, _x, _y: Gdk.ContentProvider.new_for_value(value))
    widget.add_controller(source)
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m unittest tests.test_playlist_math tests.test_dnd -v`
Expected: all PASS.

- [ ] **Step 5: Write the failing pane tests**

Create `tests/test_playlist_pane.py`:

```python
import unittest
from unittest import mock

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from sqlch.core import playqueue
from sqlch_gui.ui import dnd
from sqlch_gui.ui.playlist_pane import PlaylistPane

A = {"source": "fake", "id": "a", "title": "Song A", "artist": "Band", "kind": "track"}
B = {"source": "fake", "id": "b", "title": "Song B", "kind": "track"}
KEXP = {"id": "kexp", "name": "KEXP", "url": "http://kexp.example/s"}


def sync(work, done):
    try:
        result, err = work(), None
    except Exception as e:
        result, err = None, str(e)
    done(result, err)


def state(**kw):
    s = {"mode": "media", "entries": [], "now": None, "context": None,
         "history": [], "resume": None}
    s.update(kw)
    return s


def entry(kind, payload):
    return playqueue.make_entry(kind, payload)


def labels(widget, acc=None):
    acc = [] if acc is None else acc
    child = widget.get_first_child()
    while child:
        if isinstance(child, Gtk.Label):
            acc.append(child.get_text())
        labels(child, acc)
        child = child.get_next_sibling()
    return acc


def make(st, sent=None):
    box = {"state": st}
    pane = PlaylistPane(None, read=lambda: box["state"],
                        send=(lambda m: (sent.append(m), {"ok": True})[1]) if sent is not None
                        else (lambda m: {"ok": True}),
                        run_async=sync, watch=False)
    return pane, box


class TestRows(unittest.TestCase):
    def test_now_row_then_entries(self):
        now, a, k = entry("item", A), entry("item", A), entry("station", KEXP)
        pane, _ = make(state(now=now, entries=[a, k]))
        texts = labels(pane.list)
        self.assertEqual(texts[0], "▶")  # the now marker
        self.assertIn("KEXP", texts)
        self.assertIn("radio", texts)
        self.assertEqual(len(pane._entries), 2)
        self.assertEqual(len(pane._row_widgets), 2)

    def test_empty_queue_has_no_rows(self):
        pane, _ = make(state())
        self.assertEqual(pane._entries, [])
        self.assertIsNone(pane.list.get_row_at_index(0))

    def test_refresh_is_a_no_op_when_nothing_changed(self):
        pane, box = make(state(entries=[entry("item", A)]))
        before = pane._row_widgets[0]
        self.assertFalse(pane.refresh())
        self.assertIs(pane._row_widgets[0], before)
        box["state"] = state(entries=[entry("item", A), entry("item", B)])
        pane.refresh()
        self.assertEqual(len(pane._entries), 2)

    def test_refresh_ignores_a_moving_resume_position_in_media_mode(self):
        a = entry("item", A)
        pane, box = make(state(mode="media", resume={"entry": a, "pos": 10.0, "dur": 90.0}))
        before = pane._sig
        box["state"] = state(mode="media", resume={"entry": a, "pos": 15.0, "dur": 90.0})
        pane.refresh()
        self.assertEqual(pane._sig, before)


class TestModeToggle(unittest.TestCase):
    def test_follows_the_state(self):
        pane, box = make(state(mode="media"))
        self.assertTrue(pane.btn_media.get_active())
        box["state"] = state(mode="radio")
        pane.refresh()
        self.assertTrue(pane.btn_radio.get_active())

    def test_click_sends_set_mode(self):
        sent = []
        pane, _ = make(state(mode="media"), sent)
        pane.btn_radio.emit("clicked")
        self.assertEqual(sent, [{"cmd": "set_mode", "mode": "radio"}])

    def test_syncing_the_toggle_from_state_sends_nothing(self):
        sent = []
        pane, box = make(state(mode="media"), sent)
        box["state"] = state(mode="radio")
        pane.refresh()
        self.assertEqual(sent, [])


class TestResumeLine(unittest.TestCase):
    def test_shown_only_while_parked(self):
        a = entry("item", A)
        r = {"entry": a, "pos": 412.0, "dur": 900.0}
        pane, box = make(state(mode="radio", resume=r))
        self.assertTrue(pane.status.get_visible())
        self.assertEqual(pane.status.get_text(), "resume: Song A, 6:52")
        box["state"] = state(mode="media", resume=r)
        pane.refresh()
        self.assertFalse(pane.status.get_visible())


class TestActions(unittest.TestCase):
    def test_remove_button_sends_queue_remove(self):
        a = entry("item", A)
        sent = []
        pane, _ = make(state(entries=[a]), sent)
        pane._remove_buttons[a["uid"]].emit("clicked")
        self.assertEqual(sent, [{"cmd": "queue_remove", "uid": a["uid"]}])

    def test_clear_button(self):
        sent = []
        pane, _ = make(state(entries=[entry("item", A)]), sent)
        pane.btn_clear.emit("clicked")
        self.assertEqual(sent, [{"cmd": "queue_clear"}])

    def test_play_row(self):
        a = entry("item", A)
        sent = []
        pane, _ = make(state(entries=[a]), sent)
        pane._play(a)
        self.assertEqual(sent, [{"cmd": "queue_play", "uid": a["uid"]}])

    def test_error_shows_in_the_status_line(self):
        pane = PlaylistPane(None, read=lambda: state(), run_async=sync, watch=False,
                            send=lambda m: {"ok": False, "error": "boom"})
        pane.btn_clear.emit("clicked")
        self.assertIn("boom", pane.status.get_text())
        self.assertTrue(pane.status.get_visible())


class TestDrop(unittest.TestCase):
    def setUp(self):
        self.a, self.b, self.c = entry("item", A), entry("item", B), entry("station", KEXP)
        self.sent = []
        self.pane, _ = make(state(entries=[self.a, self.b, self.c]), self.sent)
        self.pane._midpoints = lambda: [10.0, 30.0, 50.0]

    def test_a_new_station_inserts_at_the_gap(self):
        ok = self.pane._on_drop(None, dnd.encode(
            {"kind": "station", "payload": dnd.station_payload(KEXP)}), 5, 40)
        self.assertTrue(ok)
        self.assertEqual(self.sent, [{"cmd": "queue_add", "kind": "station",
                                      "payload": dnd.station_payload(KEXP), "at": 2}])

    def test_reorder_down(self):
        self.pane._on_drop(None, dnd.encode({"move": self.a["uid"]}), 5, 999)
        self.assertEqual(self.sent, [{"cmd": "queue_move", "uid": self.a["uid"], "to": 2}])

    def test_reorder_up(self):
        self.pane._on_drop(None, dnd.encode({"move": self.c["uid"]}), 5, 0)
        self.assertEqual(self.sent, [{"cmd": "queue_move", "uid": self.c["uid"], "to": 0}])

    def test_strangers_and_unknown_moves_are_refused(self):
        self.assertFalse(self.pane._on_drop(None, "just text", 5, 5))
        self.assertFalse(self.pane._on_drop(None, dnd.encode({"move": "nope"}), 5, 5))
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 6: Run to verify failure**

Run: `python -m unittest tests.test_playlist_pane -v`
Expected: ERROR `ModuleNotFoundError: No module named 'sqlch_gui.ui.playlist_pane'`

- [ ] **Step 7: Write the pane**

Create `sqlch_gui/ui/playlist_pane.py`:

```python
"""Playlist pane: the queue, the RADIO / MEDIA toggle, drag in and reorder.

Reads queue.json directly (the daemon is the only writer) and sends every
change as a daemon command."""

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, GObject, Gtk

from sqlch.core import playqueue

from .. import daemon
from . import dnd
from .playlist_math import insert_index, move_target
from .source_pane import _thread_run
from .timefmt import format_duration


class PlaylistPane(Gtk.Box):
    def __init__(self, parent_window, read=playqueue.read, send=None,
                 run_async=_thread_run, watch=True):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_start(6)
        self.set_margin_end(6)
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.win = parent_window
        self._read = read
        self._send = send or (lambda msg: daemon.send(msg))
        self._run = run_async
        self._sig = None
        self._entries: list[dict] = []        # the entries behind the list rows, in order
        self._row_widgets: list[Gtk.Widget] = []
        self._remove_buttons: dict[str, Gtk.Button] = {}

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.btn_radio = Gtk.ToggleButton(label="RADIO")
        self.btn_media = Gtk.ToggleButton(label="MEDIA")
        self.btn_media.set_group(self.btn_radio)
        for mode, button in (("radio", self.btn_radio), ("media", self.btn_media)):
            button.add_css_class("section-pill")
            button.set_tooltip_text("What next/prev and the media keys walk")
            # clicked, not toggled: syncing the buttons from the file must not send
            button.connect("clicked", lambda _b, m=mode: self._pick_mode(m))
            head.append(button)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        head.append(spacer)
        self.btn_clear = Gtk.Button(label="Clear")
        self.btn_clear.add_css_class("row-btn")
        self.btn_clear.connect("clicked", lambda _b: self._call({"cmd": "queue_clear"}))
        head.append(self.btn_clear)
        self.append(head)

        self.status = Gtk.Label(xalign=0.0)
        self.status.add_css_class("meta-genre")
        self.status.set_wrap(True)
        self.status.set_visible(False)
        self.append(self.status)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.list = Gtk.ListBox()
        self.list.add_css_class("list-plate")
        self.list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list.set_vexpand(True)
        hint = Gtk.Label(label="Drag stations or tracks here")
        hint.add_css_class("meta-genre")
        self.list.set_placeholder(hint)
        drop = Gtk.DropTarget.new(GObject.TYPE_STRING,
                                  Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        drop.connect("drop", self._on_drop)
        self.list.add_controller(drop)
        scroll.set_child(self.list)
        self.append(scroll)

        self._monitor = None
        if watch:
            f = Gio.File.new_for_path(str(playqueue.path()))
            self._monitor = f.monitor_file(Gio.FileMonitorFlags.NONE, None)
            self._monitor.connect("changed", lambda *_: GLib.idle_add(self.refresh))
        self.refresh()

    def on_shown(self):
        self.refresh()

    # --- state -> widgets ---

    def refresh(self) -> bool:
        state = self._read()
        # While media plays the resume position moves every few seconds;
        # it only shows (and only matters here) while parked.
        parked = state["resume"] if state["mode"] == "radio" else None
        now = state["now"]
        sig = (state["mode"], now and now["uid"],
               tuple(e["uid"] for e in state["entries"]),
               parked and (parked["entry"]["uid"], int(parked["pos"])))
        if sig == self._sig:
            return False
        self._sig = sig
        (self.btn_radio if state["mode"] == "radio" else self.btn_media).set_active(True)
        self._fill(state)
        self._show_resume(parked)
        return False

    def _fill(self, state):
        while row := self.list.get_first_child():
            self.list.remove(row)
        self._entries = list(state["entries"])
        self._row_widgets = []
        self._remove_buttons = {}
        if state["now"]:
            self.list.append(self._build_row(state["now"], now=True))
        for e in self._entries:
            row = self._build_row(e)
            self._row_widgets.append(row)
            self.list.append(row)

    def _show_resume(self, parked):
        if parked is None:
            self.status.set_visible(False)
            return
        title = playqueue.entry_title(parked["entry"])
        self.status.set_text(f"resume: {title}, {format_duration(parked['pos'])}")
        self.status.set_visible(True)

    def _build_row(self, entry, now=False):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.add_css_class("station-row")
        mark = Gtk.Label(label="▶" if now else ("◉" if entry["kind"] == "station" else ""))
        mark.add_css_class("meta-genre")
        mark.set_width_chars(2)
        row.append(mark)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        body.set_hexpand(True)
        title = Gtk.Label(label=playqueue.entry_title(entry), xalign=0.0)
        title.set_ellipsize(3)
        body.append(title)
        sub_text = playqueue.entry_subtitle(entry)
        sub = Gtk.Label(label=sub_text, xalign=0.0)
        sub.add_css_class("station-live")
        sub.set_ellipsize(3)
        sub.set_visible(bool(sub_text))
        body.append(sub)
        row.append(body)
        if not now:
            remove = Gtk.Button(label="✕")
            remove.add_css_class("row-btn")
            remove.set_valign(Gtk.Align.CENTER)
            remove.set_tooltip_text("Remove from the playlist")
            remove.connect("clicked", lambda _b, e=entry: self._call(
                {"cmd": "queue_remove", "uid": e["uid"]}))
            row.append(remove)
            self._remove_buttons[entry["uid"]] = remove
            click = Gtk.GestureClick()
            click.set_button(Gdk.BUTTON_PRIMARY)
            click.connect("released", lambda _g, _n, _x, _y, e=entry: self._play(e))
            row.add_controller(click)
            dnd.attach_drag(row, {"move": entry["uid"]})
        return row

    # --- commands ---

    def _call(self, msg):
        self._run(lambda: self._send(msg), self._done)

    def _done(self, resp, err):
        problem = err if err is not None else (
            "daemon not running" if resp is None
            else None if resp.get("ok", True) else resp.get("error") or "daemon refused")
        if problem is not None:
            self.status.set_text(f"Couldn't do that: {problem}")
            self.status.set_visible(True)
        else:
            GLib.idle_add(self.refresh)
        return False

    def _pick_mode(self, mode):
        self._call({"cmd": "set_mode", "mode": mode})

    def _play(self, entry):
        self._call({"cmd": "queue_play", "uid": entry["uid"]})

    # --- drag and drop ---

    def _midpoints(self) -> list[float]:
        mids = []
        for widget in self._row_widgets:
            ok, rect = widget.compute_bounds(self.list)
            if ok:
                mids.append(rect.get_y() + rect.get_height() / 2)
        return mids

    def _on_drop(self, _target, value, _x, y) -> bool:
        data = dnd.decode(value)
        if data is None:
            return False
        drop = insert_index(self._midpoints(), y)
        if "move" in data:
            uids = [e["uid"] for e in self._entries]
            if data["move"] not in uids:
                return False
            msg = {"cmd": "queue_move", "uid": data["move"],
                   "to": move_target(uids.index(data["move"]), drop)}
        else:
            msg = {"cmd": "queue_add", "kind": data["kind"],
                   "payload": data["payload"], "at": drop}
        self._call(msg)
        return True
```

- [ ] **Step 8: Run to verify the pane tests pass**

Run: `python -m unittest tests.test_playlist_pane -v`
Expected: all PASS. (Needs a GTK-capable environment like the other GUI tests; they run headless in this repo.) If `test_refresh_ignores_a_moving_resume_position_in_media_mode` fails, the signature is leaking the resume position outside radio mode; fix `parked` in `refresh`.

- [ ] **Step 9: Register the window and the tab**

1. `sqlch_gui/ui/dock_state.py:9`: `NAMES = ("radio", "playlist")`
2. `sqlch_gui/ui/dock_manager.py:14`: `_TITLES = {"radio": "RADIO", "playlist": "PLAYLIST"}`
3. `sqlch_gui/ui/controls.py` `NavColumn._TABS`:

```python
    _TABS = (
        ("radio", "RADIO", "Radio: station library and discover"),
        ("playlist", "PLAYLIST", "Playlist: the queue and the radio/media mode"),
    )
```
4. `sqlch_gui/ui/window.py`: add `from .playlist_pane import PlaylistPane` beside the other pane imports, and change

```python
        panels = {"radio": self.radio}
        titles = {}
```
to
```python
        panels = {"radio": self.radio, "playlist": lambda: PlaylistPane(self)}
        titles = {}
```
(the `titles` dict stays; `_TITLES` supplies the PLAYLIST title.)

- [ ] **Step 10: Run the dock, nav and state tests and the whole GUI suite**

Run: `python -m unittest tests.test_dock_state tests.test_nav_column tests.test_dock tests.test_radio_pane tests.test_header -v 2>&1 | tail -15`
Expected: all PASS. If a test counts the nav tabs or the default state's names, update that assertion to include `playlist` (the production change is intended).

- [ ] **Step 11: Commit**

```bash
git add sqlch_gui/ui/playlist_math.py sqlch_gui/ui/dnd.py sqlch_gui/ui/playlist_pane.py \
  sqlch_gui/ui/dock_state.py sqlch_gui/ui/dock_manager.py sqlch_gui/ui/controls.py sqlch_gui/ui/window.py \
  tests/test_playlist_math.py tests/test_dnd.py tests/test_playlist_pane.py
git commit -m "sqlch-gui: Playlist pane with RADIO/MEDIA toggle, reorder and drop

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

(Include any test file you had to adjust in Step 10 in the same commit.)

---

### Task 8: Drag sources, row menus, and play context

**Files:**
- Modify: `sqlch_gui/ui/station_list.py` (`_build_station_row` ~line 188, `show_context_menu` ~line 252)
- Modify: `sqlch_gui/ui/source_pane.py` (`_daemon_play` line 140, `_activate` line 458, `_open_menu` line 470, `_build_row` line 349)
- Test: `tests/test_source_pane.py`, `tests/test_station_list.py`

**Interfaces:**
- Consumes: Task 7 `dnd.attach_drag`, `dnd.queue_msg`, `dnd.station_payload`; daemon `queue_add`, `play_item` with `context`
- Produces: `SourcePane._queue(item, play_next, pop)`; `play_item` messages from `SourcePane` carry `context` (the pane's playable items)

- [ ] **Step 1: Write the failing source-pane tests**

Append to `tests/test_source_pane.py` (before the `if __name__ == "__main__":` line near the end; keep the existing trailing class as is). These reuse the file's `make`, `Fake`, `TRACK`, `FOLDER`, `rows_titled`, `button_labels`:

```python
class TestQueueActions(unittest.TestCase):
    def test_track_menu_offers_the_queue_actions(self):
        p = make(Fake())
        p.on_shown()
        with mock.patch.object(Gtk.Popover, "popup"):
            p._open_menu(TRACK, p.list)
        pop = p.list.get_last_child()
        while not isinstance(pop, Gtk.Popover):
            pop = pop.get_prev_sibling()
        self.assertEqual(button_labels(pop.get_child()), ["Add to queue", "Play next"])

    def test_queue_sends_the_item(self):
        sent = []
        p = make(Fake(), send=lambda m: (sent.append(m), {"ok": True})[1])
        pop = mock.Mock()
        p._queue(TRACK, True, pop)
        pop.popdown.assert_called_once_with()
        self.assertEqual(sent, [{"cmd": "queue_add", "kind": "item", "payload": TRACK,
                                 "play_next": True}])

    def test_queue_failure_shows_in_the_status_line(self):
        p = make(Fake(), send=lambda m: {"ok": False, "error": "boom"})
        p._queue(TRACK, False, mock.Mock())
        self.assertIn("boom", p.status.get_text())

    def test_folders_get_no_queue_actions(self):
        s = MenuFake()
        p = make(s)
        p.on_shown()
        with mock.patch.object(Gtk.Popover, "popup"):
            p._open_menu(FOLDER, p.list)
        pop = p.list.get_last_child()
        while not isinstance(pop, Gtk.Popover):
            pop = pop.get_prev_sibling()
        self.assertEqual(button_labels(pop.get_child()), ["Go to E", "Save"])


class TestPlayContext(unittest.TestCase):
    def test_play_sends_the_playable_items_as_context(self):
        sent = []
        p = make(Fake(tree={None: [FOLDER, TRACK, {**TRACK, "id": "t2"}]}),
                 send=lambda m: (sent.append(m), {"ok": True})[1])
        p._play = lambda item, resume=False: p._daemon_play_with_context(item, resume)
        p.on_shown()
        with mock.patch.object(type(p), "_send_play", create=True):
            pass
        p._daemon_play_with_context(TRACK, False)
        msg = sent[-1]
        self.assertEqual(msg["cmd"], "play_item")
        self.assertEqual([i["id"] for i in msg["context"]], ["t", "t2"])
```

> The last test is awkward because `_daemon_play` is currently a `@staticmethod` that calls the module-level `daemon.send`. Step 3 turns it into an instance method that uses `self._send`; once it does, replace the body of `test_play_sends_the_playable_items_as_context` with the simpler form below and delete the `p._play = ...` / `with mock.patch.object(type(p), "_send_play", ...)` scaffolding:

```python
    def test_play_sends_the_playable_items_as_context(self):
        sent = []
        p = make(Fake(tree={None: [FOLDER, TRACK, {**TRACK, "id": "t2"}]}),
                 play=None, send=lambda m: (sent.append(m), {"ok": True})[1])
        p.on_shown()
        p._daemon_play(TRACK)
        msg = sent[-1]
        self.assertEqual(msg["cmd"], "play_item")
        self.assertEqual([i["id"] for i in msg["context"]], ["t", "t2"])
```

Write the simpler form directly (skip the awkward draft).

- [ ] **Step 2: Run to verify failure**

Run: `python -m unittest tests.test_source_pane.TestQueueActions tests.test_source_pane.TestPlayContext -v`
Expected: FAIL (`_queue` missing; menu buttons missing; `_daemon_play` doesn't send context).

- [ ] **Step 3: Implement in `source_pane.py`**

1. Imports: add `from . import dnd` next to the other relative imports.

2. Replace the static `_daemon_play` with an instance method that sends the pane's playable items as the context:

```python
    def _daemon_play(self, item, resume=False):
        context = [i for i in self._items if i.get("kind") != "folder"]
        resp = self._send({"cmd": "play_item", "item": item, "resume": resume,
                           "context": context})
        if resp is None:
            raise RuntimeError("daemon not running")
        if not resp.get("ok", True):
            raise RuntimeError(resp.get("error") or "daemon refused")
```
   `self._play = play or self._daemon_play` in `__init__` already binds the method, so it keeps working. `_items` is the list the pane is showing (set in `_show`); search results and sections are therefore their own context. Update any existing test that calls `SourcePane._daemon_play(item)` as a static method to use an instance (`grep -n "_daemon_play" tests/`).

3. `_open_menu`: change the top and the tail:

```python
    def _open_menu(self, item, anchor):
        """The source's actions for an item: go to (path/title), copy (text to
        the clipboard) or action (an id for source.act, run off the main thread);
        playable items also get the queue actions."""
        menu = getattr(self.source, "menu", None)
        queueable = item.get("kind") != "folder"
        if menu is None and not queueable:
            return
```
   and, inside `done`, after the `for entry in entries or []:` loop and before `return False`:

```python
            if queueable:
                for label, play_next in (("Add to queue", False), ("Play next", True)):
                    btn = Gtk.Button(label=label)
                    btn.add_css_class("menu-btn")
                    btn.connect("clicked", lambda b, n=play_next: self._queue(item, n, pop))
                    box.append(btn)
```
   and change the final line `self._run(lambda: menu(item), done)` to
   `self._run(lambda: menu(item) if menu else [], done)`.

4. New method after `_menu_pick`:

```python
    def _queue(self, item, play_next, pop):
        pop.popdown()

        def done(resp, err):
            problem = err if err is not None else (
                "daemon not running" if resp is None
                else None if resp.get("ok", True) else resp.get("error") or "daemon refused")
            self._set_status(f"Couldn't queue it: {problem}" if problem is not None
                             else "Playing" if resp.get("played") else "Queued")
            return False
        self._run(lambda: self._send(dnd.queue_msg("item", item, play_next)), done)
```

5. Drag source in `_build_row`, directly before `row.set_tooltip_text(...)` at the end:

```python
        if item.get("kind") != "folder":
            dnd.attach_drag(row, {"kind": "item", "payload": item})
```

- [ ] **Step 4: Station list: drag source and menu actions**

In `sqlch_gui/ui/station_list.py`:

1. Add `from . import dnd` to the imports.
2. In `_build_station_row`, directly before `row._station = s`:

```python
        dnd.attach_drag(row, {"kind": "station", "payload": dnd.station_payload(s)})
```
3. In `show_context_menu`, build two buttons ahead of the edit fields. After `vbox = Gtk.Box(...)` add:

```python
        for label, play_next in (("Add to queue", False), ("Play next", True)):
            btn_q = Gtk.Button(label=label)
            btn_q.add_css_class("menu-btn")
            btn_q.connect("clicked", lambda b, n=play_next: self._queue_station(popover, station, n))
            vbox.append(btn_q)
        vbox.append(Gtk.Separator())
```
   and add the method beside `on_delete_station`:

```python
    def _queue_station(self, popover, station, play_next):
        popover.popdown()
        daemon.send(dnd.queue_msg("station", dnd.station_payload(station), play_next))
```
   (`daemon` is already imported in this module; it's used by `on_row_clicked`.)

- [ ] **Step 5: Add a station-list test**

Append to `tests/test_station_list.py`, using its `_LibraryBackedTestCase` and `_make_panel`:

```python
class TestStationQueueActions(_LibraryBackedTestCase):
    def test_queue_station_sends_the_station(self):
        library.add_url("Test Station", "http://example.com/stream")
        station = library.get_station_list()[0]
        panel = _make_panel()
        popover = Mock()
        with patch("sqlch_gui.ui.station_list.daemon.send") as send:
            panel._queue_station(popover, station, True)
        popover.popdown.assert_called_once_with()
        send.assert_called_once_with({
            "cmd": "queue_add", "kind": "station", "play_next": True,
            "payload": {"id": station["id"], "name": "Test Station",
                        "url": "http://example.com/stream"}})
```
   and add `Mock` to the file's `from unittest.mock import patch` import (`from unittest.mock import Mock, patch`).

- [ ] **Step 6: Run to verify pass**

Run: `python -m unittest tests.test_source_pane tests.test_station_list -v 2>&1 | tail -15`
Expected: all PASS, including the pre-existing menu tests (`test_menu_entries_navigate_and_act` uses a FOLDER item so it sees no queue buttons; `test_sources_without_a_menu_open_nothing` uses a FOLDER and still opens nothing).

- [ ] **Step 7: Commit**

```bash
git add sqlch_gui/ui/source_pane.py sqlch_gui/ui/station_list.py tests/test_source_pane.py tests/test_station_list.py
git commit -m "sqlch-gui: drag rows into the playlist, Add to queue / Play next, play context

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: README, spec notes, full suite, smoke test

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-10-30-sqlch-queue-design.md` (append a section)

- [ ] **Step 1: Append the implementation notes to the spec**

Append to `docs/superpowers/specs/2026-10-30-sqlch-queue-design.md`:

```markdown

## 8. Implementation notes

Where the implementation plan (`docs/superpowers/plans/2026-10-30-sqlch-queue.md`)
refines the sections above:

- **Modules.** State is `sqlch/core/playqueue.py` (not `queue.py`, which would
  shadow the stdlib module for anyone running from `sqlch/core`). Playback
  logic is `sqlch/core/transport.py`.
- **End detection polls, it does not hook `end-file`.** mpv runs with
  `--keep-open=yes`, so it parks at EOF instead of exiting and the daemon has
  only request/response IPC. A 1 s daemon tick reads `eof-reached`
  (`player.playback_ended()`); Spotify handoff counts as ended within 1 s of
  the end. When nothing is left to play, an mpv item is stopped; a handoff item
  is left to the external player's own autoplay.
- **`now`.** `queue.json` also stores `now` (the playing entry). The playing
  entry is popped from `entries` when it starts, so `play_next` inserts at
  index 0 and the pane shows `now` as its first row.
- **`context` carries the sibling items** (`{"items": [...], "index": n}`), sent
  by the pane with `play_item`, instead of a path to re-browse. It works for
  search results and podcast feeds, and advancing needs no network call.
- **`resume` also stores `dur`**, so the near-end rule (within 10 s of the end
  restarts from the top; before 15 s in, also from the top) needs no lookup.
- **Wire format.** `queue_add` takes `{kind, payload, at?, play_next?}`; the
  daemon builds the entry and its `uid`.
- **Default mode is `radio`**, so behavior before first use is unchanged.
- **Playlist rows have no art thumbnails**; they are text rows like the Library
  pane. Thumbnails are a follow-up.
- Stopping (`stop` command) parks the playing item and clears `now`.
```

- [ ] **Step 2: Document the queue in the README**

In `README.md`:

1. In the "What sqlch is" bullet list, after the **Radio timeshift** bullet add:

```markdown
- A **queue** — drag stations and tracks from any source into the Playlist pane (or use *Add to queue* / *Play next* in a row's menu); finished items advance to the next entry or the next item in the list you started from, and a RADIO / MEDIA toggle decides what next/prev and your media keys walk
```

2. In "Usage", after the "### Spotify" subsection and before "### Library", add:

```markdown
### Queue

```bash
sqlch queue                      # list entries and the mode
sqlch queue add <id|name|url>    # queue a station
sqlch queue clear
sqlch mode [radio|media]         # show or set what next/prev walk
```

Items from the GUI sources are queued from the Playlist pane or a row's menu.
A queued station starts when the item before it finishes and flips the mode to
RADIO; flip back to MEDIA and the interrupted item resumes where it left off.
Dropping onto an empty, idle playlist plays right away.
```

3. In the architecture tree, under `core/`, add after `handoff.py`:

```
│   ├── playqueue.py     # Persistent queue: entries, mode, resume point
│   ├── transport.py     # Advance, next/prev, radio/media mode, parking
```
   and under `sqlch_gui/ui/`, after `source_pane.py`:

```
    ├── playlist_pane.py  # Queue pane: RADIO/MEDIA toggle, drag in and reorder
```

- [ ] **Step 3: Run the whole suite**

Run: `python -m unittest discover -s tests -t . 2>&1 | tail -8`
Expected: `OK`. Fix any failure before continuing; do not skip a failing test.

- [ ] **Step 4: Manual smoke test (needs a Wayland session, mpv and a configured source)**

Using the project's wrapper env (see the `sqlch-gui dev launch` memory note), start the daemon and GUI from the working tree, then check each of these and note the result:

1. `sqlch mode` prints `radio`; `sqlch queue` prints `mode: radio` and nothing else.
2. Play a short local track from the Local pane. Right-click another track → *Add to queue*. Open PLAYLIST: the first track is the `▶` row and the second is listed below it.
3. Let the first track end: the second starts on its own within ~1 s and `mode` is `media`.
4. Drag a station from the Library pane onto the Playlist while a track plays: it queues. When the track ends the station starts and the toggle shows RADIO. The status line reads `resume: …` when a track was queued behind it.
5. Click MEDIA: the station is replaced and the parked track continues from its saved position.
6. Click RADIO while media plays: the last station starts. Press your media-key next: it cycles stations; flip to MEDIA and it walks the queue.
7. With an empty playlist and nothing playing, drop a station: it plays at once.
8. Drag-reorder two rows; remove one with ✕; Clear empties the list.
9. `kill` the daemon mid-track, restart it: `sqlch queue` still lists the entries.

Record anything that fails as a follow-up; if the PLAYLIST tab text is clipped in the 290 px nav row, shorten the label to `LIST` in `NavColumn._TABS`.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/superpowers/specs/2026-10-30-sqlch-queue-design.md
git commit -m "docs: queue in the README, spec implementation notes

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage**

| Spec requirement | Task |
|---|---|
| Explicit queue + context fallback (§Decisions, §2) | 1 (`context`, `next_in_context`), 3 (`advance`), 8 (pane sends `context`) |
| Persistent `queue.json`, atomic, quarantine (§1) | 1 |
| Station entries flip to RADIO and the queue waits (§2) | 3 (`_start_entry`, `test_station_entry_flips_to_radio_and_keeps_the_rest`) |
| RADIO/MEDIA toggle, follows play, manual override sticks (§2) | 3 (`_start_entry`/`start_station` set the mode; `set_mode`), 7 (pane toggle) |
| `prev` restart > 3 s else history (§2) | 3 (`prev_cmd`) |
| 3 consecutive failures stop advance; toast (§2, §6) | 3 (`advance`, `notify`) |
| Resume by statefile; periodic save; near-end rule (§3) | 3 (`park`, `_resume_start`), 4 (`sample_once` every 5 s) |
| RADIO→MEDIA resumes, MEDIA→RADIO starts last station (§3) | 3 (`set_mode`) |
| `queue_*`, `set_mode`, `status` fields (§4) | 4 |
| Drop plays only when empty and idle (§4, confirmed with you) | 4 (`queue_add`), 7 (drop sends `queue_add`) |
| CLI `queue`, `queue add`, `queue clear`, `mode` (§4) | 5 |
| MPRIS Next/Previous, CanGoNext (§4) | 6 |
| Playlist pane: toggle, rows, reorder, drop target, clear, resume line (§5) | 7 |
| Row menu "Add to queue" / "Play next", drag sources (§5) | 8 |
| Errors: skip, quarantine, unknown uid (§6) | 1, 3, 4 |
| Tests (§7) | every task |
| Spec said "hook `end-file`" | Deviation: polling `eof-reached`, recorded in Task 9's spec notes and justified in Task 2 |
| Spec said rows show art | Deviation: text rows only, recorded in Task 9's spec notes |

**Placeholder scan:** no TBD/TODO steps; every code step has the code. Task 8 Step 1 contains one deliberately-superseded draft test followed by the version to write; the instruction there is to write only the simpler form.

**Type consistency:** `make_entry(kind, payload)`, `entry_title/subtitle/label`, `add(entry, at, play_next)`, `take`, `pop_head`, `set_resume(entry, pos, dur)` and the state keys (`mode`, `entries`, `now`, `context`, `history`, `resume` with `entry/pos/dur`) are used identically in Tasks 1, 3, 4, 5, 7. `transport.start_item(item, *, context, resume)`, `start_station(station)`, `play_entry(entry) -> bool`, `set_mode(mode)`, `next_cmd/prev_cmd`, `tick`, `park`, `stop` match their call sites in Tasks 4 and 6. `dnd.queue_msg(kind, payload, play_next)` matches the daemon's `queue_add` fields (`kind`, `payload`, `at`, `play_next`).
