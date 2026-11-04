# Source Pane Sections, Favorites, and YouTube Follows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every source pane a section menu (source-defined sections plus a universal FAVORITES), a star on every row, and let YouTube channels be followed with an in-window toast when a followed channel uploads.

**Architecture:** Sources may define `sections()`; `sources.sections_for()` adds BROWSE (when a source has none) and FAVORITES. Favorites and follows are small JSON files owned by a new `sqlch/core/follows.py` (daemon writes, GUI reads directly because writes are atomic renames). A daemon watcher thread polls YouTube RSS feeds and queues notices; the GUI's existing 1 s monitor loop drains them and shows each in a toast overlaid on the cover art.

**Tech Stack:** Python 3.11, GTK4 (PyGObject), stdlib `unittest` (`python3 -m unittest`), yt-dlp (existing), stdlib `urllib` + `xml.etree`.

## Global Constraints

- Tests are `unittest`, run from the repo root: `python3 -m unittest tests.test_x -v`. Whole suite: `python3 -m unittest discover -s tests -t .`. No pytest.
- The GUI process has no `requests`; use stdlib `urllib` (see `sqlch/sources/jellyfin.py`).
- The daemon is the only writer of `favorites.json` and `youtube_follows.json`. The GUI reads them through `sqlch.core.follows` read functions and writes through daemon commands.
- Notices live in daemon memory, newest 20 kept. Toast is inside the sqlch window (label overlaid on the cover art), never `notify-send`.
- First poll after following records the newest video and queues nothing.
- More than 3 new videos from one channel in one poll queue one summary notice `"<Channel>: N new videos"`. After 10 consecutive failures for a channel, queue one `"Can't reach <Channel>"` notice.
- `sources.youtube.poll_minutes` defaults to 30, minimum 1.
- Colors in CSS come from the palette variables already used in `sqlch_gui/ui/common.py` (`{root}`, `{outline}`, `{hairline}`, `{mono}`, `{dim}`); no literals.
- Commit trailer on every commit: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Commit and push to `main` directly.

## File Structure

- Create `sqlch/core/follows.py` — favorites + follows JSON store.
- Create `sqlch/core/watcher.py` — feed polling and notice queue.
- Create `sqlch_gui/ui/toast.py` — toast label.
- Modify `sqlch/sources/base.py` — `make_item` gains `channel_id`.
- Modify `sqlch/sources/__init__.py` — `BROWSE`, `FAVORITES`, `sections_for`.
- Modify `sqlch/sources/youtube.py` — channel ids, `sections()`, CHANNELS, feed fetch/parse, `poll_seconds`.
- Modify `sqlch/sources/jellyfin.py`, `sqlch/sources/spotify.py` — `sections()` and `section:` browse.
- Modify `sqlch/core/daemon.py` — new commands, start watcher.
- Modify `sqlch_gui/ui/now_playing.py`, `sqlch_gui/ui/window.py`, `sqlch_gui/ui/common.py` — toast overlay, notice drain, CSS.
- Modify `sqlch_gui/ui/source_pane.py` — section row, star, follow.
- Tests: `tests/test_follows.py`, `tests/test_watcher.py`, `tests/test_toast.py`, `tests/test_daemon_follows.py` (new); extend `tests/test_sources.py`, `tests/test_source_youtube.py`, `tests/test_source_jellyfin.py`, `tests/test_source_spotify.py`, `tests/test_source_pane.py`.

---

### Task 1: Favorites and follows store

**Files:**
- Create: `sqlch/core/follows.py`
- Test: `tests/test_follows.py`

**Interfaces:**
- Produces (all in `sqlch.core.follows`):
  - `list_favorites(source: str) -> list[dict]`
  - `favorite_ids(source: str) -> set[str]`
  - `toggle_favorite(item: dict) -> bool` (True = now a favorite; raises `ValueError` without `source`/`id`)
  - `list_follows() -> list[dict]` (`{channel_id, name, last_video_id, last_checked}`)
  - `followed_ids() -> set[str]`
  - `follow(channel_id: str, name: str) -> None` (idempotent)
  - `unfollow(channel_id: str) -> None`
  - `record_seen(channel_id: str, video_id: str | None, checked: float) -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_follows.py`:

```python
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlch.core import follows

ITEM = {"source": "youtube", "id": "abc", "title": "Song", "kind": "video"}
OTHER = {"source": "jellyfin", "id": "abc", "title": "Same id", "kind": "track"}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        p = mock.patch.object(follows, "data_dir", lambda: self.dir)
        p.start()
        self.addCleanup(p.stop)


class TestFavorites(Base):
    def test_empty(self):
        self.assertEqual(follows.list_favorites("youtube"), [])
        self.assertEqual(follows.favorite_ids("youtube"), set())

    def test_toggle_adds_then_removes(self):
        self.assertTrue(follows.toggle_favorite(ITEM))
        self.assertEqual(follows.list_favorites("youtube"), [ITEM])
        self.assertEqual(follows.favorite_ids("youtube"), {"abc"})
        self.assertFalse(follows.toggle_favorite(ITEM))
        self.assertEqual(follows.list_favorites("youtube"), [])

    def test_sources_are_separate_even_with_same_id(self):
        follows.toggle_favorite(ITEM)
        follows.toggle_favorite(OTHER)
        self.assertEqual(follows.list_favorites("youtube"), [ITEM])
        self.assertEqual(follows.list_favorites("jellyfin"), [OTHER])

    def test_toggle_needs_source_and_id(self):
        for bad in ({}, {"source": "youtube"}, {"id": "x"}):
            with self.assertRaises(ValueError):
                follows.toggle_favorite(bad)

    def test_no_temp_files_left(self):
        follows.toggle_favorite(ITEM)
        self.assertEqual([p.name for p in self.dir.iterdir()], ["favorites.json"])

    def test_corrupt_file_is_quarantined_and_store_recovers(self):
        (self.dir / "favorites.json").write_text("{not json")
        self.assertEqual(follows.list_favorites("youtube"), [])
        self.assertTrue((self.dir / "favorites.json.bad").exists())
        self.assertTrue(follows.toggle_favorite(ITEM))
        self.assertEqual(follows.list_favorites("youtube"), [ITEM])

    def test_non_list_file_is_quarantined(self):
        (self.dir / "favorites.json").write_text('{"a": 1}')
        self.assertEqual(follows.list_favorites("youtube"), [])
        self.assertTrue((self.dir / "favorites.json.bad").exists())


class TestFollows(Base):
    def test_follow_is_idempotent(self):
        follows.follow("UC1", "Chan")
        follows.follow("UC1", "Chan again")
        (row,) = follows.list_follows()
        self.assertEqual(row, {"channel_id": "UC1", "name": "Chan",
                               "last_video_id": None, "last_checked": None})
        self.assertEqual(follows.followed_ids(), {"UC1"})

    def test_unfollow(self):
        follows.follow("UC1", "A")
        follows.follow("UC2", "B")
        follows.unfollow("UC1")
        self.assertEqual(follows.followed_ids(), {"UC2"})
        follows.unfollow("missing")  # no error

    def test_record_seen(self):
        follows.follow("UC1", "A")
        follows.record_seen("UC1", "vid9", 123.0)
        (row,) = follows.list_follows()
        self.assertEqual((row["last_video_id"], row["last_checked"]), ("vid9", 123.0))
        follows.record_seen("gone", "x", 1.0)  # unknown channel is ignored
        self.assertEqual(len(follows.list_follows()), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_follows -v`
Expected: ERROR `ImportError: cannot import name 'follows'`.

- [ ] **Step 3: Write the implementation**

Create `sqlch/core/follows.py`:

```python
"""Favorites and followed YouTube channels: small JSON files in data_dir().

The daemon is the only writer. Every write replaces the file atomically, so
the gui can read these files directly without a lock."""

import json
import logging
import os
import tempfile
import threading

from sqlch.core.paths import data_dir

log = logging.getLogger(__name__)

FAVORITES = "favorites.json"
FOLLOWS = "youtube_follows.json"

_lock = threading.Lock()  # serializes read-modify-write between daemon threads


def _path(name: str):
    return data_dir() / name


def _quarantine(path) -> None:
    log.error("%s is unreadable; moving it to %s.bad", path, path.name)
    try:
        os.replace(path, path.with_name(path.name + ".bad"))
    except OSError:
        pass


def _read(name: str) -> list:
    path = _path(name)
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        _quarantine(path)
        return []
    if not isinstance(data, list):
        _quarantine(path)
        return []
    return data


def _write(name: str, rows: list) -> None:
    path = _path(name)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=name + ".")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(rows, f, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---- favorites ----

def list_favorites(source: str) -> list[dict]:
    return [r for r in _read(FAVORITES)
            if isinstance(r, dict) and r.get("source") == source]


def favorite_ids(source: str) -> set[str]:
    return {r.get("id") for r in list_favorites(source)}


def toggle_favorite(item: dict) -> bool:
    key = (item.get("source"), item.get("id"))
    if not all(key):
        raise ValueError("a favorite needs a source and an id")
    with _lock:
        rows = _read(FAVORITES)
        kept = [r for r in rows
                if not (isinstance(r, dict) and (r.get("source"), r.get("id")) == key)]
        added = len(kept) == len(rows)
        if added:
            kept.append(item)
        _write(FAVORITES, kept)
    return added


# ---- followed youtube channels ----

def list_follows() -> list[dict]:
    return [r for r in _read(FOLLOWS) if isinstance(r, dict) and r.get("channel_id")]


def followed_ids() -> set[str]:
    return {r["channel_id"] for r in list_follows()}


def follow(channel_id: str, name: str) -> None:
    with _lock:
        rows = _read(FOLLOWS)
        if any(isinstance(r, dict) and r.get("channel_id") == channel_id for r in rows):
            return
        rows.append({"channel_id": channel_id, "name": name,
                     "last_video_id": None, "last_checked": None})
        _write(FOLLOWS, rows)


def unfollow(channel_id: str) -> None:
    with _lock:
        rows = _read(FOLLOWS)
        kept = [r for r in rows
                if not (isinstance(r, dict) and r.get("channel_id") == channel_id)]
        if len(kept) != len(rows):
            _write(FOLLOWS, kept)


def record_seen(channel_id: str, video_id: str | None, checked: float) -> None:
    with _lock:
        rows = _read(FOLLOWS)
        for r in rows:
            if isinstance(r, dict) and r.get("channel_id") == channel_id:
                r["last_video_id"] = video_id
                r["last_checked"] = checked
                _write(FOLLOWS, rows)
                return
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest tests.test_follows -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add sqlch/core/follows.py tests/test_follows.py
git commit -m "sqlch: favorites and followed-channel store

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 2: Watcher (polling and notice queue)

**Files:**
- Create: `sqlch/core/watcher.py`
- Test: `tests/test_watcher.py`

**Interfaces:**
- Consumes: a `store` with `list_follows()` and `record_seen(channel_id, video_id, checked)` (Task 1's `follows` module by default); a `fetch(channel_id) -> list[{"id": str, "title": str}]` newest first.
- Produces (in `sqlch.core.watcher`):
  - `class Watcher(fetch, store=follows, clock=time.time)` with `poll_once()`, `drain() -> list[str]`, `run(interval: Callable[[], float])`
  - `start(fetch, interval) -> None` (starts the module-level watcher on a daemon thread)
  - `drain() -> list[str]` (module level; `[]` before `start`)
  - Constants `SUMMARY_OVER = 3`, `GIVE_UP_AFTER = 10`, `MAX_NOTICES = 20`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_watcher.py`:

```python
import unittest

from sqlch.core import watcher


class FakeStore:
    def __init__(self, rows):
        self.rows = rows

    def list_follows(self):
        return [dict(r) for r in self.rows]

    def record_seen(self, cid, vid, checked):
        for r in self.rows:
            if r["channel_id"] == cid:
                r["last_video_id"] = vid
                r["last_checked"] = checked


def row(cid="UC1", name="Chan", last=None):
    return {"channel_id": cid, "name": name, "last_video_id": last, "last_checked": None}


def vids(*ids):
    return [{"id": i, "title": f"T {i}"} for i in ids]


def make(rows, feeds):
    store = FakeStore(rows)

    def fetch(cid):
        feed = feeds[cid]
        if isinstance(feed, Exception):
            raise feed
        return feed

    return watcher.Watcher(fetch, store=store, clock=lambda: 42.0), store


class TestPoll(unittest.TestCase):
    def test_first_poll_records_and_stays_quiet(self):
        w, store = make([row()], {"UC1": vids("b", "a")})
        w.poll_once()
        self.assertEqual(w.drain(), [])
        self.assertEqual(store.rows[0]["last_video_id"], "b")
        self.assertEqual(store.rows[0]["last_checked"], 42.0)

    def test_no_change_is_quiet(self):
        w, store = make([row(last="b")], {"UC1": vids("b", "a")})
        w.poll_once()
        self.assertEqual(w.drain(), [])

    def test_one_new_video(self):
        w, store = make([row(last="b")], {"UC1": vids("c", "b", "a")})
        w.poll_once()
        self.assertEqual(w.drain(), ["Chan: T c"])
        self.assertEqual(store.rows[0]["last_video_id"], "c")
        w.poll_once()
        self.assertEqual(w.drain(), [])

    def test_up_to_three_are_listed_oldest_first(self):
        w, _ = make([row(last="a")], {"UC1": vids("d", "c", "b", "a")})
        w.poll_once()
        self.assertEqual(w.drain(), ["Chan: T b", "Chan: T c", "Chan: T d"])

    def test_more_than_three_become_a_summary(self):
        w, _ = make([row(last="a")], {"UC1": vids("e", "d", "c", "b", "a")})
        w.poll_once()
        self.assertEqual(w.drain(), ["Chan: 4 new videos"])

    def test_last_seen_rolled_off_feed_counts_whole_feed_as_new(self):
        w, _ = make([row(last="gone")], {"UC1": vids("b", "a")})
        w.poll_once()
        self.assertEqual(w.drain(), ["Chan: T a", "Chan: T b"])

    def test_empty_feed_changes_nothing(self):
        w, store = make([row(last="a")], {"UC1": []})
        w.poll_once()
        self.assertEqual(w.drain(), [])
        self.assertEqual(store.rows[0]["last_video_id"], "a")


class TestFailures(unittest.TestCase):
    def test_gives_up_once_after_ten_failures(self):
        w, _ = make([row()], {"UC1": OSError("down")})
        for _ in range(9):
            w.poll_once()
        self.assertEqual(w.drain(), [])
        w.poll_once()
        self.assertEqual(w.drain(), ["Can't reach Chan"])
        w.poll_once()
        self.assertEqual(w.drain(), [])

    def test_success_resets_the_counter(self):
        feeds = {"UC1": OSError("down")}
        w, _ = make([row()], feeds)
        for _ in range(9):
            w.poll_once()
        feeds["UC1"] = vids("a")
        w.poll_once()
        feeds["UC1"] = OSError("down")
        for _ in range(9):
            w.poll_once()
        self.assertEqual(w.drain(), [])
        w.poll_once()
        self.assertEqual(w.drain(), ["Can't reach Chan"])

    def test_one_failing_channel_does_not_stop_the_others(self):
        w, store = make([row("UC1", "Bad"), row("UC2", "Good", last="a")],
                        {"UC1": OSError("x"), "UC2": vids("b", "a")})
        w.poll_once()
        self.assertEqual(w.drain(), ["Good: T b"])


class TestQueue(unittest.TestCase):
    def test_drain_clears(self):
        w, _ = make([row(last="a")], {"UC1": vids("b", "a")})
        w.poll_once()
        self.assertEqual(len(w.drain()), 1)
        self.assertEqual(w.drain(), [])

    def test_keeps_only_newest_twenty(self):
        w, _ = make([], {})
        for i in range(25):
            w._push(f"n{i}")
        got = w.drain()
        self.assertEqual(len(got), watcher.MAX_NOTICES)
        self.assertEqual(got[0], "n5")
        self.assertEqual(got[-1], "n24")

    def test_module_drain_before_start_is_empty(self):
        self.assertEqual(watcher.drain(), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_watcher -v`
Expected: ERROR `ImportError: cannot import name 'watcher'`.

- [ ] **Step 3: Write the implementation**

Create `sqlch/core/watcher.py`:

```python
"""Polls followed YouTube channels and queues in-app notices for new uploads.

The gui drains the queue over the control socket (`drain_notices`) and shows
each notice as a toast."""

import logging
import threading
import time
from collections import deque
from typing import Callable

from sqlch.core import follows

log = logging.getLogger(__name__)

SUMMARY_OVER = 3     # more new videos than this from one channel -> one summary notice
GIVE_UP_AFTER = 10   # consecutive failures before a single "can't reach" notice
MAX_NOTICES = 20


class Watcher:
    def __init__(self, fetch, store=follows, clock=time.time):
        self._fetch = fetch
        self._store = store
        self._clock = clock
        self._notices: deque[str] = deque(maxlen=MAX_NOTICES)
        self._lock = threading.Lock()
        self._fails: dict[str, int] = {}

    def _push(self, text: str) -> None:
        with self._lock:
            self._notices.append(text)

    def drain(self) -> list[str]:
        with self._lock:
            out = list(self._notices)
            self._notices.clear()
        return out

    def poll_once(self) -> None:
        for ch in self._store.list_follows():
            cid = ch["channel_id"]
            name = ch.get("name") or cid
            try:
                entries = self._fetch(cid)
            except Exception as e:
                n = self._fails.get(cid, 0) + 1
                self._fails[cid] = n
                log.warning("feed for %s failed (%d): %s", name, n, e)
                if n == GIVE_UP_AFTER:
                    self._push(f"Can't reach {name}")
                continue
            self._fails.pop(cid, None)
            if not entries:
                continue
            newest = entries[0]["id"]
            last = ch.get("last_video_id")
            if last is not None and newest != last:
                ids = [e["id"] for e in entries]
                new = entries[:ids.index(last)] if last in ids else entries
                if len(new) > SUMMARY_OVER:
                    self._push(f"{name}: {len(new)} new videos")
                else:
                    for e in reversed(new):
                        self._push(f"{name}: {e['title']}")
            self._store.record_seen(cid, newest, self._clock())

    def run(self, interval: Callable[[], float]) -> None:
        while True:
            try:
                self.poll_once()
            except Exception:
                log.exception("watcher poll failed")
            time.sleep(interval())


_watcher: Watcher | None = None


def start(fetch, interval: Callable[[], float]) -> None:
    global _watcher
    _watcher = Watcher(fetch)
    threading.Thread(target=_watcher.run, args=(interval,),
                     daemon=True, name="watcher").start()


def drain() -> list[str]:
    return _watcher.drain() if _watcher else []
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest tests.test_watcher -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add sqlch/core/watcher.py tests/test_watcher.py
git commit -m "sqlch: watcher polls followed channels and queues notices

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 3: YouTube channels, sections, and feed fetch

**Files:**
- Modify: `sqlch/sources/base.py` (`make_item`)
- Modify: `sqlch/sources/youtube.py`
- Test: `tests/test_source_youtube.py`, `tests/test_sources.py`

**Interfaces:**
- Consumes: `follows.list_follows()` from Task 1.
- Produces:
  - `make_item(..., channel_id=None)` — item dict gains key `"channel_id"`.
  - `youtube.sections() -> [{"id": "channels", "title": "CHANNELS"}]`
  - `youtube.browse("section:channels")` and `browse(None)` -> followed channels (folder items with `channel_id` set, `path` = `https://www.youtube.com/channel/<id>/videos`) followed by config shortcuts.
  - `youtube.valid_channel_id(s: str) -> bool`
  - `youtube.parse_feed(xml: bytes) -> list[{"id","title"}]` (newest first, feed order)
  - `youtube.fetch_feed(channel_id: str) -> list[{"id","title"}]` (raises `ValueError` on a bad id)
  - `youtube.poll_seconds() -> float`

- [ ] **Step 1: Write the failing tests**

In `tests/test_source_youtube.py`, extend `setUp` (add one patch to the existing tuple so tests never read real follows):

```python
        for p in (mock.patch.object(youtube, "ytdlp_path", lambda: "/bin/yt-dlp"),
                  mock.patch.object(youtube, "cache_dir", lambda: Path(self._tmp.name)),
                  mock.patch.object(youtube.follows, "list_follows", lambda: [])):
```

Append these tests inside `class TestYoutube` (before `if __name__`):

```python
    def test_sections(self):
        self.assertEqual(youtube.sections(), [{"id": "channels", "title": "CHANNELS"}])

    def test_channels_section_lists_follows_then_shortcuts(self):
        self.cfg(shortcuts=[{"name": "Short", "url": "https://www.youtube.com/@s"}])
        row = {"channel_id": "UC" + "a" * 22, "name": "Followed"}
        with mock.patch.object(youtube.follows, "list_follows", lambda: [row]):
            items = youtube.browse("section:channels")
        self.assertEqual([i["title"] for i in items], ["Followed", "Short"])
        self.assertEqual(items[0]["channel_id"], row["channel_id"])
        self.assertEqual(items[0]["kind"], "folder")
        self.assertEqual(items[0]["path"],
                         f"https://www.youtube.com/channel/{row['channel_id']}/videos")
        self.assertIsNone(items[1]["channel_id"])

    def test_root_is_the_channels_section(self):
        self.cfg()
        row = {"channel_id": "UC" + "b" * 22, "name": "F"}
        with mock.patch.object(youtube.follows, "list_follows", lambda: [row]):
            self.assertEqual(youtube.browse(None), youtube.browse("section:channels"))

    def test_video_items_carry_channel_id(self):
        self.cfg()
        entries = [{"id": "abc", "title": "S", "channel": "Band", "channel_id": "UC1"}]
        with mock.patch.object(youtube.subprocess, "run", return_value=_proc(entries)):
            (item,) = youtube.search("x")
        self.assertEqual(item["channel_id"], "UC1")

    def test_valid_channel_id(self):
        self.assertTrue(youtube.valid_channel_id("UC" + "a" * 22))
        for bad in ("", "UC123", "XX" + "a" * 22, "UC" + "a" * 21 + "/", "UC" + "a" * 23):
            self.assertFalse(youtube.valid_channel_id(bad))

    FEED = (b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" '
            b'xmlns="http://www.w3.org/2005/Atom"><title>Chan</title>'
            b'<entry><id>yt:video:vid2</id><yt:videoId>vid2</yt:videoId>'
            b'<title>Second</title></entry>'
            b'<entry><id>yt:video:vid1</id><yt:videoId>vid1</yt:videoId>'
            b'<title>First</title></entry></feed>')

    def test_parse_feed_newest_first(self):
        self.assertEqual(youtube.parse_feed(self.FEED),
                         [{"id": "vid2", "title": "Second"},
                          {"id": "vid1", "title": "First"}])

    def test_parse_feed_refuses_dtds(self):
        evil = (b'<?xml version="1.0"?><!DOCTYPE feed [<!ENTITY a "aaaa">]>'
                b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>&a;</title>'
                b'</entry></feed>')
        with self.assertRaises(ValueError):
            youtube.parse_feed(evil)

    def test_fetch_feed_requests_the_feed_url(self):
        cid = "UC" + "c" * 22
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = self.FEED
        with mock.patch.object(youtube, "urlopen", return_value=resp) as op:
            out = youtube.fetch_feed(cid)
        self.assertEqual(op.call_args[0][0],
                         f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}")
        self.assertEqual(out[0]["id"], "vid2")

    def test_fetch_feed_rejects_bad_ids(self):
        with self.assertRaises(ValueError):
            youtube.fetch_feed("UC1&x=y")

    def test_poll_seconds(self):
        self.cfg()
        self.assertEqual(youtube.poll_seconds(), 30 * 60)
        self.cfg(poll_minutes=10)
        self.assertEqual(youtube.poll_seconds(), 600)
        self.cfg(poll_minutes=0)
        self.assertEqual(youtube.poll_seconds(), 60)
        self.cfg(poll_minutes="soon")
        self.assertEqual(youtube.poll_seconds(), 30 * 60)
```

Append to `tests/test_sources.py` inside its existing item test class (use the existing class; if `make_item` tests are in a class named differently, add to that class):

```python
    def test_make_item_channel_id_defaults_to_none(self):
        self.assertIsNone(make_item("local", "a", "A")["channel_id"])
        self.assertEqual(make_item("youtube", "a", "A", channel_id="UC1")["channel_id"], "UC1")
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest tests.test_source_youtube tests.test_sources -v`
Expected: FAIL/ERROR (`channel_id` unexpected keyword, `follows` / `sections` / `parse_feed` missing).

- [ ] **Step 3: Implement**

In `sqlch/sources/base.py`, replace `make_item`:

```python
def make_item(source, id, title, *, kind="track", artist=None, album=None,
              art=None, duration=None, path=None, channel_id=None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"unknown item kind: {kind}")
    if kind == "folder" and path is None:
        raise ValueError("folder items need a path")
    return {"source": source, "id": id, "title": title, "artist": artist,
            "album": album, "art": art, "duration": duration, "kind": kind,
            "path": path, "channel_id": channel_id}
```

In `sqlch/sources/youtube.py`:

Replace the import block's first lines so it reads:

```python
import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from urllib.request import urlopen

from sqlch.core import follows
from sqlch.core.paths import cache_dir
from sqlch.sources import source_config
from sqlch.sources.base import Target, make_item
```

Add after `WATCH = ...`:

```python
CHANNEL_VIDEOS = "https://www.youtube.com/channel/{}/videos"
FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
DEFAULT_POLL_MINUTES = 30
_CHANNEL_ID = re.compile(r"^UC[\w-]{22}$")
_ATOM = "{http://www.w3.org/2005/Atom}"
_YT = "{http://www.youtube.com/xml/schemas/2015}"
```

In `_to_item`, change the video `make_item` call to pass the channel id:

```python
    return make_item(NAME, e["id"], title, kind="video",
                     artist=e.get("channel") or e.get("uploader"),
                     duration=e.get("duration"), channel_id=e.get("channel_id"))
```

Replace `browse` and add the new functions right after it:

```python
def sections() -> list[dict]:
    return [{"id": "channels", "title": "CHANNELS"}]


def _channels() -> list[dict]:
    items = [make_item(NAME, f["channel_id"], f.get("name") or f["channel_id"],
                       kind="folder", path=CHANNEL_VIDEOS.format(f["channel_id"]),
                       channel_id=f["channel_id"])
             for f in follows.list_follows()]
    items += [make_item(NAME, s["url"], s["name"], kind="folder", path=s["url"])
              for s in _shortcuts()]
    return items


def browse(path: str | None = None) -> list[dict]:
    if not path or path == "section:channels":
        return _channels()
    if not path.startswith("https://"):
        raise ValueError("bad youtube path")
    return _items(_extract(path, LIST_LIMIT))


def valid_channel_id(channel_id: str) -> bool:
    return bool(_CHANNEL_ID.match(channel_id or ""))


def parse_feed(xml: bytes) -> list[dict]:
    # A real feed never declares a DTD; refusing one rules out entity-expansion
    # tricks without adding a dependency.
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise ValueError("feed declares a DTD")
    out = []
    for entry in ET.fromstring(xml).iter(_ATOM + "entry"):
        vid = entry.findtext(_YT + "videoId")
        if vid:
            out.append({"id": vid, "title": entry.findtext(_ATOM + "title") or vid})
    return out


def fetch_feed(channel_id: str) -> list[dict]:
    if not valid_channel_id(channel_id):
        raise ValueError("bad channel id")
    with urlopen(FEED.format(channel_id), timeout=8) as r:
        return parse_feed(r.read())


def poll_seconds() -> float:
    minutes = source_config(NAME).get("poll_minutes")
    if isinstance(minutes, bool) or not isinstance(minutes, (int, float)):
        minutes = DEFAULT_POLL_MINUTES
    return max(1, minutes) * 60
```

(The old `browse` is replaced; its shortcut-listing behavior now lives in `_channels`.)

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m unittest tests.test_source_youtube tests.test_sources -v`
Expected: all PASS, including the pre-existing youtube tests.

- [ ] **Step 5: Commit**

```bash
git add sqlch/sources/base.py sqlch/sources/youtube.py tests/test_source_youtube.py tests/test_sources.py
git commit -m "sqlch: youtube channels section, channel ids on items, feed fetch

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 4: Section registry helper, Jellyfin and Spotify sections

**Files:**
- Modify: `sqlch/sources/__init__.py`
- Modify: `sqlch/sources/jellyfin.py`, `sqlch/sources/spotify.py`
- Test: `tests/test_sources.py`, `tests/test_source_jellyfin.py`, `tests/test_source_spotify.py`

**Interfaces:**
- Produces:
  - `sources.BROWSE = {"id": "browse", "title": "BROWSE"}`, `sources.FAVORITES = {"id": "favorites", "title": "FAVORITES"}`
  - `sources.sections_for(source) -> list[dict]` — the source's own `sections()` (or `[BROWSE]` when it has none or it raises) followed by `FAVORITES`.
  - `jellyfin.sections()` -> LIBRARIES, PLAYLISTS; `jellyfin.browse("section:libraries")` == old root; `browse("section:playlists")` lists playlists; `browse("Playlist:<id>")` lists the playlist's items in playlist order.
  - `spotify.sections()` -> SHORTCUTS; `spotify.browse("section:shortcuts")` == old root.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sources.py` (new class, add `import types` if absent; the file already imports `unittest`):

```python
class TestSectionsFor(unittest.TestCase):
    def test_source_without_sections_gets_browse_and_favorites(self):
        from sqlch import sources
        src = types.SimpleNamespace(NAME="x")
        self.assertEqual([s["id"] for s in sources.sections_for(src)],
                         ["browse", "favorites"])

    def test_own_sections_come_first_then_favorites(self):
        from sqlch import sources
        src = types.SimpleNamespace(NAME="x", sections=lambda: [{"id": "a", "title": "A"}])
        self.assertEqual([s["id"] for s in sources.sections_for(src)], ["a", "favorites"])

    def test_broken_sections_fall_back_to_browse(self):
        from sqlch import sources

        def boom():
            raise RuntimeError("x")

        src = types.SimpleNamespace(NAME="x", sections=boom)
        with self.assertLogs("sqlch.sources", level="ERROR"):
            self.assertEqual([s["id"] for s in sources.sections_for(src)],
                             ["browse", "favorites"])

    def test_registered_sources_have_sections(self):
        from sqlch import sources
        for name, mod in sources.REGISTRY.items():
            ids = [s["id"] for s in sources.sections_for(mod)]
            self.assertEqual(ids[-1], "favorites", name)
            self.assertEqual(len(ids), len(set(ids)), name)
```

Append to `tests/test_source_jellyfin.py` (inside the existing test class, using `mock` and `jellyfin` already imported there; check the file's imports first and add any that are missing):

```python
    def test_sections(self):
        self.assertEqual([s["id"] for s in jellyfin.sections()],
                         ["libraries", "playlists"])

    def test_libraries_section_is_the_old_root(self):
        with mock.patch.object(jellyfin, "_user_id", return_value="u"), \
             mock.patch.object(jellyfin, "_get", return_value={"Items": []}) as get:
            self.assertEqual(jellyfin.browse("section:libraries"), [])
        self.assertEqual(get.call_args[0][0], "/UserViews")

    def test_playlists_section(self):
        with mock.patch.object(jellyfin, "_items", return_value=["x"]) as items:
            self.assertEqual(jellyfin.browse("section:playlists"), ["x"])
        items.assert_called_once_with({"IncludeItemTypes": "Playlist",
                                       "Recursive": "true", "SortBy": "SortName"})

    def test_playlist_contents_keep_playlist_order(self):
        with mock.patch.object(jellyfin, "_items", return_value=[]) as items:
            jellyfin.browse("Playlist:abc")
        items.assert_called_once_with({"parentId": "abc"})
```

Append to `tests/test_source_spotify.py` (inside its existing test class; add imports if missing):

```python
    def test_sections(self):
        self.assertEqual([s["id"] for s in spotify.sections()], ["shortcuts"])

    def test_shortcuts_section_is_the_old_root(self):
        with mock.patch.object(spotify, "_shortcuts", return_value=["s"]):
            self.assertEqual(spotify.browse("section:shortcuts"), ["s"])
            self.assertEqual(spotify.browse(None), ["s"])
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest tests.test_sources tests.test_source_jellyfin tests.test_source_spotify -v`
Expected: FAIL (`sections_for`, `sections` missing).

- [ ] **Step 3: Implement**

In `sqlch/sources/__init__.py`, add after `safe_available`:

```python
BROWSE = {"id": "browse", "title": "BROWSE"}
FAVORITES = {"id": "favorites", "title": "FAVORITES"}


def sections_for(source) -> list[dict]:
    """The source's own sections (BROWSE when it has none), then FAVORITES."""
    own = getattr(source, "sections", None)
    mine = [BROWSE]
    if own:
        try:
            mine = list(own())
        except Exception:
            log.exception("source %s: sections() failed", getattr(source, "NAME", source))
    return mine + [FAVORITES]
```

In `sqlch/sources/jellyfin.py`, replace the start of `browse`:

```python
def sections() -> list[dict]:
    return [{"id": "libraries", "title": "LIBRARIES"},
            {"id": "playlists", "title": "PLAYLISTS"}]


def browse(path: str | None = None) -> list[dict]:
    if path == "section:playlists":
        return _items({"IncludeItemTypes": "Playlist", "Recursive": "true",
                       "SortBy": "SortName"})
    if not path or path == "section:libraries":
        data = _get("/UserViews", {"userId": _user_id()})
        return [_to_item({**jf, "Type": jf.get("Type") or "CollectionFolder"})
                for jf in data.get("Items", [])]
    kind, _, jid = path.partition(":")
    if not jid:
        raise ValueError("bad jellyfin path")
    if kind == "Playlist":
        return _items({"parentId": jid})
    if kind == "MusicArtist":
        return _items({"AlbumArtistIds": jid, "IncludeItemTypes": "MusicAlbum",
                       "Recursive": "true", "SortBy": "ProductionYear,SortName"})
    return _items({"parentId": jid,
                   "SortBy": "ParentIndexNumber,IndexNumber,SortName"})
```

(This replaces the whole existing `browse` function body; the logic after the first two branches is unchanged apart from the new `Playlist` branch.)

In `sqlch/sources/spotify.py`, replace the first lines of `browse`:

```python
def sections() -> list[dict]:
    return [{"id": "shortcuts", "title": "SHORTCUTS"}]


def browse(path: str | None = None) -> list[dict]:
    if not path or path == "section:shortcuts":
        return _shortcuts()
```

(The rest of `browse` stays as is.)

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m unittest tests.test_sources tests.test_source_jellyfin tests.test_source_spotify tests.test_source_local tests.test_source_video -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add sqlch/sources tests/test_sources.py tests/test_source_jellyfin.py tests/test_source_spotify.py
git commit -m "sqlch: sections registry helper, jellyfin and spotify sections

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 5: Daemon commands and watcher startup

**Files:**
- Modify: `sqlch/core/daemon.py`
- Test: `tests/test_daemon_follows.py`

**Interfaces:**
- Consumes: `follows.toggle_favorite/follow/unfollow` (Task 1), `watcher.drain/start` (Task 2), `youtube.valid_channel_id/fetch_feed/poll_seconds` (Task 3).
- Produces daemon commands:
  - `{"cmd": "toggle_favorite", "item": {...}}` -> `{"ok": True, "favorite": bool}` or `{"ok": False, "error": ...}`
  - `{"cmd": "follow", "channel_id": str, "name": str}` -> `{"ok": True}` or error (invalid id)
  - `{"cmd": "unfollow", "channel_id": str}` -> `{"ok": True}`
  - `{"cmd": "drain_notices"}` -> `{"ok": True, "notices": [str, ...]}`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_daemon_follows.py`:

```python
import unittest
from unittest import mock

from sqlch.core import daemon

CID = "UC" + "a" * 22


class TestDaemonFollowCommands(unittest.TestCase):
    def test_toggle_favorite(self):
        item = {"source": "youtube", "id": "x"}
        with mock.patch.object(daemon.follows, "toggle_favorite", return_value=True) as t:
            self.assertEqual(daemon._handle({"cmd": "toggle_favorite", "item": item}),
                             {"ok": True, "favorite": True})
        t.assert_called_once_with(item)

    def test_toggle_favorite_rejects_bad_input(self):
        self.assertFalse(daemon._handle({"cmd": "toggle_favorite"})["ok"])
        resp = daemon._handle({"cmd": "toggle_favorite", "item": {"title": "no id"}})
        self.assertFalse(resp["ok"])

    def test_follow(self):
        with mock.patch.object(daemon.follows, "follow") as f:
            resp = daemon._handle({"cmd": "follow", "channel_id": CID, "name": "Chan"})
        self.assertEqual(resp, {"ok": True})
        f.assert_called_once_with(CID, "Chan")

    def test_follow_rejects_invalid_channel_id(self):
        with mock.patch.object(daemon.follows, "follow") as f:
            resp = daemon._handle({"cmd": "follow", "channel_id": "bad", "name": "x"})
        self.assertFalse(resp["ok"])
        f.assert_not_called()

    def test_follow_without_name_uses_the_id(self):
        with mock.patch.object(daemon.follows, "follow") as f:
            daemon._handle({"cmd": "follow", "channel_id": CID})
        f.assert_called_once_with(CID, CID)

    def test_unfollow(self):
        with mock.patch.object(daemon.follows, "unfollow") as u:
            self.assertEqual(daemon._handle({"cmd": "unfollow", "channel_id": CID}),
                             {"ok": True})
        u.assert_called_once_with(CID)

    def test_drain_notices(self):
        with mock.patch.object(daemon.watcher, "drain", return_value=["a", "b"]):
            self.assertEqual(daemon._handle({"cmd": "drain_notices"}),
                             {"ok": True, "notices": ["a", "b"]})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_daemon_follows -v`
Expected: ERROR `AttributeError: module 'sqlch.core.daemon' has no attribute 'follows'`.

- [ ] **Step 3: Implement**

In `sqlch/core/daemon.py`, change the import line:

```python
from sqlch import sources
from sqlch.core import discover, follows, library, notify, player, watcher
from sqlch.sources import youtube
from sqlch.core.paths import runtime_dir
```

Insert these branches in `_handle`, just before the final `return {'ok': False, 'error': f'unknown cmd: {cmd}'}`:

```python
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
    if cmd == 'drain_notices':
        return {'ok': True, 'notices': watcher.drain()}
```

In `run_daemon`, start the watcher right after the mpris thread line:

```python
    threading.Thread(target=mpris_daemon.main, daemon=True, name="mpris").start()
    watcher.start(youtube.fetch_feed, youtube.poll_seconds)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest tests.test_daemon_follows tests.test_player_items -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add sqlch/core/daemon.py tests/test_daemon_follows.py
git commit -m "sqlch: daemon commands for favorites, follows, and notices

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 6: In-window toast

**Files:**
- Create: `sqlch_gui/ui/toast.py`
- Modify: `sqlch_gui/ui/now_playing.py` (cover overlay near `self.lbl_live_tag` / `self.cover_overlay.add_overlay(...)`, around line 63-69; add a method)
- Modify: `sqlch_gui/ui/window.py` (`_daemon_monitor_loop`, new `_show_notices`)
- Modify: `sqlch_gui/ui/common.py` (CSS, next to `.corner-tag-left`)
- Test: `tests/test_toast.py`

**Interfaces:**
- Produces:
  - `Toast(schedule=GLib.timeout_add)` (a `Gtk.Label`) with `push(text: str) -> None`; shows one message at a time for `SHOW_MS = 6000` ms, queues the rest.
  - `NowPlayingPanel.show_toast(text: str) -> None`.
- Consumes: daemon command `drain_notices` (Task 5).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_toast.py`:

```python
import unittest

import gi
gi.require_version("Gtk", "4.0")

from sqlch_gui.ui.toast import SHOW_MS, Toast


class Clock:
    """Stands in for GLib.timeout_add: collects callbacks, fires on demand."""

    def __init__(self):
        self.pending = []

    def __call__(self, ms, fn):
        self.pending.append((ms, fn))

    def fire(self):
        _ms, fn = self.pending.pop(0)
        fn()


class TestToast(unittest.TestCase):
    def test_hidden_until_pushed(self):
        self.assertFalse(Toast(schedule=Clock()).get_visible())

    def test_push_shows_text_then_hides(self):
        clock = Clock()
        t = Toast(schedule=clock)
        t.push("Chan: Video")
        self.assertTrue(t.get_visible())
        self.assertEqual(t.get_text(), "Chan: Video")
        self.assertEqual(clock.pending[0][0], SHOW_MS)
        clock.fire()
        self.assertFalse(t.get_visible())

    def test_second_push_waits_for_the_first(self):
        clock = Clock()
        t = Toast(schedule=clock)
        t.push("one")
        t.push("two")
        self.assertEqual(t.get_text(), "one")
        self.assertEqual(len(clock.pending), 1)
        clock.fire()
        self.assertEqual(t.get_text(), "two")
        self.assertTrue(t.get_visible())
        clock.fire()
        self.assertFalse(t.get_visible())

    def test_push_after_idle_shows_again(self):
        clock = Clock()
        t = Toast(schedule=clock)
        t.push("one")
        clock.fire()
        t.push("two")
        self.assertEqual(t.get_text(), "two")
        self.assertTrue(t.get_visible())

    def test_does_not_block_clicks(self):
        self.assertFalse(Toast(schedule=Clock()).get_can_target())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_toast -v`
Expected: ERROR `ModuleNotFoundError: sqlch_gui.ui.toast`.

- [ ] **Step 3: Implement**

Create `sqlch_gui/ui/toast.py`:

```python
"""In-window toast: a label overlaid on the cover art, one message at a time."""

from collections import deque

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import GLib, Gtk

SHOW_MS = 6000


class Toast(Gtk.Label):
    def __init__(self, schedule=GLib.timeout_add):
        super().__init__()
        self.add_css_class("toast")
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.END)
        self.set_ellipsize(3)
        self.set_can_target(False)  # never swallow clicks meant for the cover
        self.set_visible(False)
        self._schedule = schedule
        self._queue: deque[str] = deque()
        self._showing = False

    def push(self, text: str) -> None:
        self._queue.append(text)
        if not self._showing:
            self._next()

    def _next(self) -> bool:
        if not self._queue:
            self._showing = False
            self.set_visible(False)
            return False
        self._showing = True
        self.set_text(self._queue.popleft())
        self.set_visible(True)
        self._schedule(SHOW_MS, self._next)
        return False
```

In `sqlch_gui/ui/now_playing.py`, add `from .toast import Toast` to the imports at the top, and right after the line `self.cover_overlay.add_overlay(self.lbl_live_tag)` add:

```python
        # Overlay on the cover (never a child that sizes it), so the card's
        # height does not change when a toast appears.
        self.toast = Toast()
        self.cover_overlay.add_overlay(self.toast)
```

Add this method to `NowPlayingPanel` (next to `update`):

```python
    def show_toast(self, text: str) -> None:
        self.toast.push(text)
```

In `sqlch_gui/ui/window.py`, change `_daemon_monitor_loop` to drain notices every 5th pass:

```python
    def _daemon_monitor_loop(self):
        import time
        from .. import metadata
        tick = 0
        while self._keep_running:
            resp = daemon.send({"cmd": "status"})
            icy = metadata.get_icy_track()
            vol, muted = daemon.get_vol_state()
            bitrate = daemon.get_stream_bitrate()
            fmt = daemon.get_stream_format()
            buffer = daemon.get_stream_buffer()

            GLib.idle_add(
                self._apply_daemon_state,
                resp, icy, vol, muted, bitrate, fmt, buffer
            )
            tick += 1
            if tick % 5 == 0:
                GLib.idle_add(self._show_notices, daemon.send({"cmd": "drain_notices"}))
            time.sleep(1.0)

    def _show_notices(self, resp) -> bool:
        if self._keep_running and resp and resp.get("ok"):
            for text in resp.get("notices") or []:
                self.now_playing.show_toast(text)
        return False
```

In `sqlch_gui/ui/common.py`, add directly after the `.corner-tag-left {{ ... }}` block:

```css
    .toast {{
        font-family: {mono};
        font-weight: 700;
        font-size: 0.75em;
        padding: 5px 10px;
        margin: 8px;
        border-radius: 9px;
        border: {hairline};
        background-color: {root};
        color: {outline};
    }}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest tests.test_toast tests.test_header tests.test_gui_style -v`
Expected: all PASS (`test_gui_style` guards the CSS; if it fails on the new block, fix the CSS to match its rules).

- [ ] **Step 5: Commit**

```bash
git add sqlch_gui tests/test_toast.py
git commit -m "sqlch-gui: in-window toast on the cover art, fed by drain_notices

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 7: Pane section row, star, and follow

**Files:**
- Modify: `sqlch_gui/ui/source_pane.py`
- Modify: `sqlch_gui/ui/common.py` (CSS for `.section-pill`, `.row-btn`)
- Test: `tests/test_source_pane.py`

**Interfaces:**
- Consumes: `sources.sections_for` (Task 4); daemon commands `toggle_favorite`, `follow`, `unfollow` (Task 5); `follows.list_favorites/favorite_ids/followed_ids` (Task 1).
- Produces: `SourcePane(parent_window, source, run_async=..., play=None, store=None, send=None)` — `store` defaults to `sqlch.core.follows`, `send` defaults to `daemon.send`. Pane state: `_sections`, `_section`, `_fav_ids`, `_followed`. Methods: `_select_section(id)`, `_toggle_favorite(item, button)`, `_toggle_follow(item, button)`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_source_pane.py`, replace the `make` helper and add a `FakeStore` and new tests:

```python
class FakeStore:
    def __init__(self, favs=(), followed=()):
        self.favs = list(favs)
        self.followed = set(followed)

    def list_favorites(self, source):
        return [f for f in self.favs if f["source"] == source]

    def favorite_ids(self, source):
        return {f["id"] for f in self.list_favorites(source)}

    def followed_ids(self):
        return set(self.followed)


def make(src, run=sync, play=None, store=None, send=None):
    return SourcePane(Gtk.Box(), src, run_async=run, play=play or (lambda i: None),
                      store=store or FakeStore(),
                      send=send or (lambda m: {"ok": True}))
```

Add a sectioned fake source and tests (append before `if __name__`):

```python
class Sectioned(Fake):
    def __init__(self):
        super().__init__(tree={"section:a": [FOLDER], "section:b": [TRACK], "/d": [TRACK]})

    def sections(self):
        return [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]


VIDEO = {"source": "fake", "id": "v", "title": "Vid", "artist": "Chan",
         "kind": "video", "channel_id": "UC1"}


class TestSections(unittest.TestCase):
    def test_source_without_sections_shows_browse_and_favorites(self):
        p = make(Fake())
        self.assertEqual([s["id"] for s in p._sections], ["browse", "favorites"])
        p.on_shown()
        self.assertEqual(p._section, "browse")

    def test_first_section_loads_by_default(self):
        s = Sectioned()
        p = make(s)
        p.on_shown()
        self.assertEqual(s.browsed, ["section:a"])
        self.assertEqual(p._items, [FOLDER])

    def test_selecting_a_section_loads_it_and_resets_navigation(self):
        s = Sectioned()
        p = make(s)
        p.on_shown()
        p._activate(FOLDER)
        self.assertEqual(p._stack, [("/d", "Dir")])
        p._select_section("b")
        self.assertEqual(p._stack, [])
        self.assertEqual(s.browsed[-1], "section:b")
        self.assertEqual(p._items, [TRACK])

    def test_search_then_clear_returns_to_the_section(self):
        s = Sectioned()
        p = make(s)
        p.on_shown()
        p._select_section("b")
        p._search("q")
        self.assertTrue(p._searching)
        p._search("")
        self.assertFalse(p._searching)
        self.assertEqual(s.browsed[-1], "section:b")

    def test_favorites_come_from_the_store_not_the_source(self):
        s = Sectioned()
        fav = {**TRACK, "source": "fake"}
        p = make(s, store=FakeStore(favs=[fav, {**TRACK, "source": "other", "id": "z"}]))
        p.on_shown()
        p._select_section("favorites")
        self.assertEqual(p._items, [fav])
        self.assertNotIn("section:favorites", s.browsed)

    def test_active_pill_follows_the_section(self):
        p = make(Sectioned())
        p.on_shown()
        self.assertTrue(p._pills["a"].has_css_class("active"))
        p._select_section("b")
        self.assertFalse(p._pills["a"].has_css_class("active"))
        self.assertTrue(p._pills["b"].has_css_class("active"))


class TestStarAndFollow(unittest.TestCase):
    def test_star_state_comes_from_the_store(self):
        p = make(Fake(tree={None: [TRACK]}), store=FakeStore(favs=[TRACK]))
        p.on_shown()
        self.assertEqual(p._fav_ids, {"t"})

    def test_toggle_favorite_sends_to_daemon_and_updates_button(self):
        sent = []
        p = make(Fake(), send=lambda m: sent.append(m) or {"ok": True, "favorite": True})
        p.on_shown()
        btn = Gtk.Button(label="☆")
        p._toggle_favorite(TRACK, btn)
        self.assertEqual(sent, [{"cmd": "toggle_favorite", "item": TRACK}])
        self.assertEqual(btn.get_label(), "★")
        self.assertIn("t", p._fav_ids)
        sent.clear()
        p._send = lambda m: {"ok": True, "favorite": False}
        p._toggle_favorite(TRACK, btn)
        self.assertEqual(btn.get_label(), "☆")
        self.assertNotIn("t", p._fav_ids)

    def test_toggle_favorite_failure_shows_status(self):
        p = make(Fake(), send=lambda m: None)
        p.on_shown()
        p._toggle_favorite(TRACK, Gtk.Button(label="☆"))
        self.assertIn("Couldn't update favorites", p.status.get_text())

    def test_unfavoriting_in_favorites_section_refreshes_the_list(self):
        store = FakeStore(favs=[TRACK])
        p = make(Fake(), store=store, send=lambda m: {"ok": True, "favorite": False})
        p.on_shown()
        p._select_section("favorites")
        self.assertEqual(p._items, [TRACK])
        store.favs.clear()
        p._toggle_favorite(TRACK, Gtk.Button(label="★"))
        self.assertEqual(p._items, [])

    def test_follow_sends_channel_id_and_channel_name(self):
        sent = []
        p = make(Fake(tree={None: [VIDEO]}),
                 send=lambda m: sent.append(m) or {"ok": True})
        p.on_shown()
        btn = Gtk.Button(label="Follow")
        p._toggle_follow(VIDEO, btn)
        self.assertEqual(sent, [{"cmd": "follow", "channel_id": "UC1", "name": "Chan"}])
        self.assertEqual(btn.get_label(), "Unfollow")
        self.assertIn("UC1", p._followed)

    def test_unfollow_sends_unfollow(self):
        sent = []
        p = make(Fake(tree={None: [VIDEO]}), store=FakeStore(followed=["UC1"]),
                 send=lambda m: sent.append(m) or {"ok": True})
        p.on_shown()
        btn = Gtk.Button(label="Unfollow")
        p._toggle_follow(VIDEO, btn)
        self.assertEqual(sent, [{"cmd": "unfollow", "channel_id": "UC1"}])
        self.assertEqual(btn.get_label(), "Follow")
        self.assertNotIn("UC1", p._followed)

    def test_channel_folder_uses_its_title_as_the_name(self):
        sent = []
        chan = {"source": "fake", "id": "UC1", "title": "Chan Folder", "kind": "folder",
                "path": "/c", "channel_id": "UC1"}
        p = make(Fake(), send=lambda m: sent.append(m) or {"ok": True})
        p.on_shown()
        p._toggle_follow(chan, Gtk.Button(label="Follow"))
        self.assertEqual(sent[0]["name"], "Chan Folder")

    def test_rows_only_offer_follow_when_there_is_a_channel(self):
        p = make(Fake())
        labels = []

        def collect(widget):
            child = widget.get_first_child()
            while child:
                if isinstance(child, Gtk.Button):
                    labels.append(child.get_label())
                collect(child)
                child = child.get_next_sibling()

        collect(p._build_row(TRACK))
        self.assertEqual(labels, ["☆"])
        labels.clear()
        collect(p._build_row(VIDEO))
        self.assertEqual(labels, ["☆", "Follow"])
```

(Existing pane tests keep working: they call `make(src)` which now injects the fake store and send.)

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest tests.test_source_pane -v`
Expected: ERROR — `SourcePane.__init__() got an unexpected keyword argument 'store'`.

- [ ] **Step 3: Implement**

In `sqlch_gui/ui/source_pane.py`:

Change the imports:

```python
import threading

from gi.repository import Gtk, GLib

from sqlch.core import follows
from sqlch.sources import safe_available, sections_for

from .. import daemon
from .timefmt import format_duration
```

Change the constructor signature and add state right after `self._play_error = False`:

```python
    def __init__(self, parent_window, source, run_async=_thread_run, play=None,
                 store=None, send=None):
```

```python
        self._store = store or follows
        self._send = send or (lambda msg: daemon.send(msg))
        self._sections = sections_for(source)
        self._section = self._sections[0]["id"]
        self._fav_ids: set = set()
        self._followed: set = set()
```

After `self.append(search_box)` add the section row:

```python
        self.section_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._pills: dict[str, Gtk.Button] = {}
        for sec in self._sections:
            pill = Gtk.Button(label=sec["title"])
            pill.add_css_class("section-pill")
            pill.connect("clicked", lambda _b, sid=sec["id"]: self._select_section(sid))
            self.section_row.append(pill)
            self._pills[sec["id"]] = pill
        self._mark_pills()
        self.append(self.section_row)
```

Replace `_current_path`, `_reload`, and `_load`, and add the new methods:

```python
    def _current_path(self):
        if self._stack:
            return self._stack[-1][0]
        if self._section == "browse":
            return None
        return f"section:{self._section}"

    def _mark_pills(self):
        for sid, pill in self._pills.items():
            if sid == self._section:
                pill.add_css_class("active")
            else:
                pill.remove_css_class("active")

    def _select_section(self, sid):
        self._section = sid
        self._stack = []
        self._searching = False
        self.entry.set_text("")
        self._mark_pills()
        self._reload()

    def _browse(self, path):
        if path == "section:favorites":
            return self._store.list_favorites(self.source.NAME)
        return self.source.browse(path)

    def _reload(self):
        self._load(lambda: self._browse(self._current_path()))

    def _with_marks(self, work):
        """Also refresh star/follow state; runs in the worker with the load."""
        def run():
            result = work()
            self._fav_ids = self._store.favorite_ids(self.source.NAME)
            self._followed = self._store.followed_ids()
            return result
        return run

    def _load(self, work):
        self._gen += 1
        gen = self._gen
        self._pending = work
        self._update_nav()
        self._run(self._with_marks(work), lambda result, err: self._show(gen, result, err))
```

In `_build_row`, insert before `click = Gtk.GestureClick()`:

```python
        star = Gtk.Button(label="★" if item.get("id") in self._fav_ids else "☆")
        star.add_css_class("row-btn")
        star.set_valign(Gtk.Align.CENTER)
        star.connect("clicked", lambda b, it=item: self._toggle_favorite(it, b))
        row.append(star)
        if item.get("channel_id"):
            following = item["channel_id"] in self._followed
            fol = Gtk.Button(label="Unfollow" if following else "Follow")
            fol.add_css_class("row-btn")
            fol.set_valign(Gtk.Align.CENTER)
            fol.connect("clicked", lambda b, it=item: self._toggle_follow(it, b))
            row.append(fol)
```

Add the two toggle methods (after `_played`):

```python
    def _toggle_favorite(self, item, button):
        def done(result, err):
            resp = result or {}
            if err is not None or not resp.get("ok"):
                self._set_status("Couldn't update favorites: "
                                 f"{err or resp.get('error') or 'daemon not running'}")
                return False
            if resp["favorite"]:
                self._fav_ids.add(item["id"])
            else:
                self._fav_ids.discard(item["id"])
            button.set_label("★" if resp["favorite"] else "☆")
            if (self._section == "favorites" and not self._stack
                    and not self._searching and not resp["favorite"]):
                self._reload()
            return False

        self._run(lambda: self._send({"cmd": "toggle_favorite", "item": item}), done)

    def _toggle_follow(self, item, button):
        cid = item["channel_id"]
        following = cid in self._followed
        if following:
            msg = {"cmd": "unfollow", "channel_id": cid}
        else:
            name = item["title"] if item.get("kind") == "folder" else item.get("artist")
            msg = {"cmd": "follow", "channel_id": cid, "name": name or cid}

        def done(result, err):
            resp = result or {}
            if err is not None or not resp.get("ok"):
                self._set_status("Couldn't update follows: "
                                 f"{err or resp.get('error') or 'daemon not running'}")
                return False
            if following:
                self._followed.discard(cid)
            else:
                self._followed.add(cid)
            button.set_label("Follow" if following else "Unfollow")
            if following and self._section == "channels" and not self._stack \
                    and not self._searching:
                self._reload()
            return False

        self._run(lambda: self._send(msg), done)
```

In `sqlch_gui/ui/common.py`, add after the `.toast` block:

```css
    .section-pill {{
        font-family: {mono};
        font-size: 0.7em;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 9px;
        border: {hairline};
        background: none;
        color: {root};
    }}
    .section-pill.active {{
        background-color: {root};
        color: {outline};
    }}
    .row-btn {{
        font-family: {mono};
        font-size: 0.7em;
        padding: 1px 6px;
        min-height: 0;
        border: {hairline};
        border-radius: 8px;
        background: none;
        color: {root};
    }}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest tests.test_source_pane tests.test_gui_style -v`
Expected: all PASS, including every pre-existing pane test.

- [ ] **Step 5: Commit**

```bash
git add sqlch_gui tests/test_source_pane.py
git commit -m "sqlch-gui: section row, favorites star, and follow buttons in source panes

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push origin main
```

---

### Task 8: Whole-suite check, live smoke test, spec sync

**Files:**
- Modify: `docs/superpowers/specs/2026-10-18-source-sections-design.md`

- [ ] **Step 1: Run the whole suite**

Run: `python3 -m unittest discover -s tests -t . 2>&1 | tail -8`
Expected: `OK`. Fix any failure before continuing (a likely one: a test elsewhere that compares an item dict exactly and now sees the extra `channel_id` key).

- [ ] **Step 2: Sync the spec with what was built**

In the spec, make these edits so it matches the code:
- Section 2: replace "Daemon commands: `toggle_favorite` (item) and `list_favorites` (source)." with "Daemon command: `toggle_favorite` (item). The GUI reads favorites directly through `sqlch.core.follows` (writes are atomic renames); only the daemon writes."
- Section 3: replace "Daemon commands: `follow`, `unfollow`. The daemon owns both files so the GUI and the watcher never write concurrently." with "Daemon commands: `follow`, `unfollow`. The daemon owns writes to both files; the GUI reads them directly."
- Section 4a: replace "`Toast.show(text)`" with "`Toast.push(text)`".
- Section 1: replace "`section:favorites` is answered by sqlch core (`follows.list_favorites(source)`) and never reaches the source" with "`section:favorites` is answered by the pane from `follows.list_favorites(source)` and never reaches the source".

- [ ] **Step 3: Live smoke test (needs the user)**

Read the dev-launch memory and the installed wrapper to run the working tree. Start a dev daemon and GUI from the working tree, then check each of these by eye and report what you saw:
1. Every pane shows a section row; YouTube shows `CHANNELS · FAVORITES`, Jellyfin `LIBRARIES · PLAYLISTS · FAVORITES`, Spotify `SHORTCUTS · FAVORITES`, Local/Video `BROWSE · FAVORITES`.
2. Starring an item turns the star solid and the item appears under FAVORITES; unstarring it there removes it from the list.
3. YouTube search → a video row shows `Follow`; pressing it makes the channel appear under CHANNELS with `Unfollow`; opening it lists the channel's latest videos.
4. Jellyfin PLAYLISTS lists playlists and opening one lists its tracks in playlist order. (This relies on Jellyfin returning playlist items for `parentId`; if it returns nothing, switch `browse("Playlist:<id>")` to `/Playlists/<id>/Items` and say so.)
5. Toast: stop the dev daemon, edit `~/.local/share/sqlch/youtube_follows.json` and set one channel's `last_video_id` to `"old"`, start the daemon (it polls immediately on start), and within about 5 s a toast appears on the cover art, then disappears after 6 s. Because `"old"` is not in the feed, expect a summary toast like `Chan: 15 new videos`.
6. Kill every dev instance afterwards (by PID, in a separate command).

- [ ] **Step 4: Commit**

```bash
git add docs
git commit -m "docs: sync sections spec with the implementation

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push origin main
```
