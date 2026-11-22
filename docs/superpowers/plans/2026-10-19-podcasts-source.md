# Podcasts Source Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** A PODCASTS source pane that searches Apple Podcasts and Podcast Index together, plays RSS episodes in mpv, follows shows, and groups show lists by source, genre, or A–Z.

**Architecture:** A new source module `sqlch/sources/podcasts.py` (plus directory clients in `_podcast_dirs.py`) plugs into the existing registry, so the dock gives it a pane for free. Followed shows get a third store in `sqlch/core/follows.py` with daemon commands. `SourcePane` gains two generic features: a sort pill driven by `source.GROUPINGS`, with the grouping logic in a pure module `sqlch_gui/ui/grouping.py`, and a Follow button for items carrying `feed_url`. Spotify loses its SHORTCUTS section.

**Tech Stack:** Python 3, GTK 4 (PyGObject), urllib + xml.etree (no `requests`: the GUI env lacks it), unittest.

**Spec:** `docs/superpowers/specs/2026-10-19-podcasts-source-design.md`

**Branch:** `unstable` (the nixos flake builds `github:SW-philip/sqlch/unstable`).

**Running tests:** there is no pytest in this env. Use `python3 -m unittest`:
- one file: `python3 -m unittest tests.test_source_podcasts -v`
- everything: `python3 -m unittest -q`

**Baseline:** 513 tests, 3 errors, all in `tests.test_header.TestPreviousTracksReserveSpace` (`IndexError: tuple index out of range`). They fail before this work and are not part of it. Lines like `ModuleNotFoundError: No module named 'sqlch.sources.nope'` are expected log noise from `test_sources`.

**Conventions to match:** see `sqlch/sources/spotify.py` and `sqlch/sources/youtube.py` for module shape (`NAME`, `TITLE`, `LABEL`, `HINT`, `available`, `browse`, `search`, `resolve`); see `sqlch/core/follows.py` for store rules (the daemon is the only writer, atomic `_write`, `_lock`). Commit subjects are lowercase `sqlch: ...` / `sqlch-gui: ...` / `tests: ...` / `docs: ...`, and every commit message ends with:

```
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

**Art note:** Now Playing shows `item["art"]` only when it is a local file (`sqlch_gui/ui/now_playing.py:418`), and `player.play_target` uses `meta["art"]` only when the item has no `art`. So podcast items keep the remote image URL under a separate `image` key and leave `art` None. `resolve` downloads the image into the cache and returns that path as `meta["art"]`.

---

### Task 1: `make_item` carries podcast fields

**Files:**
- Modify: `sqlch/sources/base.py`
- Test: `tests/test_sources.py`

**Step 1: Update the failing test**

In `tests/test_sources.py`, `TestMakeItem.test_defaults` becomes:

```python
    def test_defaults(self):
        item = make_item("local", "a/b.mp3", "B")
        self.assertEqual(item, {
            "source": "local", "id": "a/b.mp3", "title": "B", "artist": None,
            "album": None, "art": None, "duration": None, "kind": "track",
            "path": None, "channel_id": None, "date": None, "genre": None,
            "providers": None, "feed_url": None, "url": None})
```

and add to `TestMakeItem`:

```python
    def test_podcast_fields(self):
        item = make_item("podcasts", "f", "Show", kind="folder", path="feed:f",
                         genre="Comedy", providers=["apple"], feed_url="https://x/f")
        self.assertEqual((item["genre"], item["providers"], item["feed_url"]),
                         ("Comedy", ["apple"], "https://x/f"))
        self.assertEqual(make_item("podcasts", "e", "Ep", url="https://x/e.mp3")["url"],
                         "https://x/e.mp3")
```

**Step 2: Run it and check it fails**

Run: `python3 -m unittest tests.test_sources -v`
Expected: FAIL in `test_defaults` (missing keys) and ERROR in `test_podcast_fields` (unexpected keyword `genre`).

**Step 3: Implement**

`sqlch/sources/base.py`, replace `make_item`:

```python
def make_item(source, id, title, *, kind="track", artist=None, album=None,
              art=None, duration=None, path=None, channel_id=None, date=None,
              genre=None, providers=None, feed_url=None, url=None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"unknown item kind: {kind}")
    if kind == "folder" and path is None:
        raise ValueError("folder items need a path")
    return {"source": source, "id": id, "title": title, "artist": artist,
            "album": album, "art": art, "duration": duration, "kind": kind,
            "path": path, "channel_id": channel_id, "date": date,
            "genre": genre, "providers": providers, "feed_url": feed_url,
            "url": url}
```

(Keep the existing body's validation exactly. Only the signature and the returned dict change.)

**Step 4: Run the tests, then the whole suite**

Run: `python3 -m unittest tests.test_sources -v` → PASS
Run: `python3 -m unittest -q` → only the 3 baseline `test_header` errors. If any other test compares a full item dict, add the four `None` keys to its expected value.

**Step 5: Commit**

```bash
git add sqlch/sources/base.py tests/test_sources.py
git commit -m "sqlch: items carry genre, providers, feed_url and an audio url"
```

---

### Task 2: Apple Podcasts directory client

**Files:**
- Create: `sqlch/sources/_podcast_dirs.py`
- Test: `tests/test_podcast_dirs.py`

**Step 1: Write the failing test**

```python
import json
import unittest
from unittest import mock

from sqlch.sources import _podcast_dirs as dirs


class FakeResp:
    def __init__(self, body):
        self.body = body

    def read(self, n=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Recorder:
    def __init__(self, payload):
        self.payload, self.requests = payload, []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        return FakeResp(json.dumps(self.payload).encode())


class TestApple(unittest.TestCase):
    def test_parses_results_and_drops_ones_without_a_feed(self):
        rec = Recorder({"results": [
            {"feedUrl": "https://f/a", "collectionName": "A", "artistName": "Ann",
             "primaryGenreName": "Comedy", "artworkUrl600": "https://img/a"},
            {"collectionName": "No feed"},
            {"feedUrl": "https://f/b", "collectionName": "B", "artworkUrl100": "https://img/b"}]})
        with mock.patch.object(dirs, "urlopen", rec):
            shows = dirs.apple_search("comedy")
        self.assertEqual(shows, [
            {"feed_url": "https://f/a", "title": "A", "artist": "Ann",
             "genre": "Comedy", "image": "https://img/a"},
            {"feed_url": "https://f/b", "title": "B", "artist": None,
             "genre": None, "image": "https://img/b"}])

    def test_query_url(self):
        rec = Recorder({"results": []})
        with mock.patch.dict("os.environ", {"SQLCH_APPLE_PODCASTS_BASE": "http://apple"}), \
                mock.patch.object(dirs, "urlopen", rec):
            dirs.apple_search("linux unplugged")
        url = rec.requests[0].full_url
        self.assertTrue(url.startswith("http://apple/search?"))
        self.assertIn("media=podcast", url)
        self.assertIn("entity=podcast", url)
        self.assertIn("term=linux+unplugged", url)
```

**Step 2: Run it and check it fails**

Run: `python3 -m unittest tests.test_podcast_dirs -v`
Expected: ERROR, `cannot import name '_podcast_dirs'`.

**Step 3: Implement**

`sqlch/sources/_podcast_dirs.py`:

```python
"""Podcast directory clients: Apple Podcasts search and Podcast Index.
urllib only, the gui env has no requests. Each search returns plain show
dicts {feed_url, title, artist, genre, image}; podcasts.py merges them."""

import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TIMEOUT = 6
LIMIT = 25
UA = "sqlch/1.0"


def _apple_base() -> str:
    return os.environ.get("SQLCH_APPLE_PODCASTS_BASE", "https://itunes.apple.com")


def _fetch_json(url: str, headers: dict | None = None) -> dict:
    req = Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def _show(feed_url, title, artist, genre, image) -> dict:
    return {"feed_url": feed_url, "title": title, "artist": artist or None,
            "genre": genre or None, "image": image or None}


def apple_search(term: str) -> list[dict]:
    q = urlencode({"media": "podcast", "entity": "podcast", "term": term, "limit": LIMIT})
    data = _fetch_json(f"{_apple_base()}/search?{q}")
    return [_show(r["feedUrl"], r["collectionName"], r.get("artistName"),
                  r.get("primaryGenreName"), r.get("artworkUrl600") or r.get("artworkUrl100"))
            for r in data.get("results") or []
            if isinstance(r, dict) and r.get("feedUrl") and r.get("collectionName")]
```

**Step 4: Run the tests**

Run: `python3 -m unittest tests.test_podcast_dirs -v` → PASS

**Step 5: Commit**

```bash
git add sqlch/sources/_podcast_dirs.py tests/test_podcast_dirs.py
git commit -m "sqlch: apple podcasts directory search"
```

---

### Task 3: Podcast Index client and credentials

**Files:**
- Modify: `sqlch/sources/_podcast_dirs.py`
- Test: `tests/test_podcast_dirs.py`

Podcast Index auth: headers `X-Auth-Key: <key>`, `X-Auth-Date: <unix seconds>`, `Authorization: sha1hex(key + secret + date)`, and a `User-Agent`. Search endpoint: `GET /search/byterm?q=...&max=N`, response `{"feeds": [{"url", "title", "author", "artwork", "categories": {"77": "Society", ...}}]}`.

**Step 1: Write the failing tests**

Append to `tests/test_podcast_dirs.py`:

```python
import hashlib
import tempfile
from pathlib import Path


class TestPodcastIndex(unittest.TestCase):
    def test_auth_headers(self):
        h = dirs.pi_headers("K", "S", 1700000000)
        self.assertEqual(h["X-Auth-Key"], "K")
        self.assertEqual(h["X-Auth-Date"], "1700000000")
        self.assertEqual(h["Authorization"],
                         hashlib.sha1(b"KS1700000000").hexdigest())

    def test_parses_feeds_with_first_category_as_genre(self):
        rec = Recorder({"feeds": [
            {"url": "https://f/a", "title": "A", "author": "Ann", "artwork": "https://img/a",
             "categories": {"102": "Technology", "9": "News"}},
            {"url": "https://f/b", "title": "B", "categories": None},
            {"title": "no url"}]})
        with mock.patch.dict("os.environ", {"SQLCH_PODCASTINDEX_BASE": "http://pi"}), \
                mock.patch.object(dirs, "urlopen", rec):
            shows = dirs.pi_search("linux", ("K", "S"), now=lambda: 5)
        self.assertEqual(shows, [
            {"feed_url": "https://f/a", "title": "A", "artist": "Ann",
             "genre": "Technology", "image": "https://img/a"},
            {"feed_url": "https://f/b", "title": "B", "artist": None,
             "genre": None, "image": None}])
        req = rec.requests[0]
        self.assertTrue(req.full_url.startswith("http://pi/search/byterm?"))
        self.assertIn("q=linux", req.full_url)
        self.assertEqual(req.get_header("X-auth-key"), "K")


class TestCredentials(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict("os.environ", {}, clear=False)
        p.start()
        self.addCleanup(p.stop)
        for k in ("PODCASTINDEX_API_KEY", "PODCASTINDEX_API_SECRET"):
            dirs.os.environ.pop(k, None)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.env = Path(self._tmp.name) / "env"

    def test_env_vars_win(self):
        with mock.patch.dict("os.environ", {"PODCASTINDEX_API_KEY": "k",
                                            "PODCASTINDEX_API_SECRET": "s"}):
            self.assertEqual(dirs.pi_credentials(str(self.env)), ("k", "s"))

    def test_from_file_strips_quotes_and_comments(self):
        self.env.write_text('# c\nPODCASTINDEX_API_KEY="k"\nPODCASTINDEX_API_SECRET=s\n')
        self.assertEqual(dirs.pi_credentials(str(self.env)), ("k", "s"))

    def test_missing_file_or_half_a_pair_is_none(self):
        self.assertIsNone(dirs.pi_credentials(str(self.env)))
        self.env.write_text("PODCASTINDEX_API_KEY=k\n")
        self.assertIsNone(dirs.pi_credentials(str(self.env)))
```

**Step 2: Run them and check they fail**

Run: `python3 -m unittest tests.test_podcast_dirs -v`
Expected: ERROR, `module ... has no attribute 'pi_headers'` (and `pi_search`, `pi_credentials`).

**Step 3: Implement**

Add to `sqlch/sources/_podcast_dirs.py` (put `import hashlib`, `import time` and `from pathlib import Path` with the other imports):

```python
DEFAULT_ENV_FILE = "/run/secrets/podcastindex_env"


def _pi_base() -> str:
    return os.environ.get("SQLCH_PODCASTINDEX_BASE", "https://api.podcastindex.org/api/1.0")


def pi_credentials(env_file: str | None = None) -> tuple[str, str] | None:
    key = os.environ.get("PODCASTINDEX_API_KEY")
    sec = os.environ.get("PODCASTINDEX_API_SECRET")
    if not (key and sec):
        try:
            text = Path(env_file or DEFAULT_ENV_FILE).expanduser().read_text()
        except OSError:
            return None
        vals = dict(line.split("=", 1) for line in text.splitlines()
                    if "=" in line and not line.lstrip().startswith("#"))
        key = vals.get("PODCASTINDEX_API_KEY", "").strip().strip("\"'")
        sec = vals.get("PODCASTINDEX_API_SECRET", "").strip().strip("\"'")
    return (key, sec) if key and sec else None


def pi_headers(key: str, secret: str, now: float) -> dict:
    date = str(int(now))
    return {"X-Auth-Key": key, "X-Auth-Date": date,
            "Authorization": hashlib.sha1((key + secret + date).encode()).hexdigest()}


def _first_category(cats) -> str | None:
    if isinstance(cats, dict) and cats:
        return next(iter(cats.values()))
    return None


def pi_search(term: str, creds: tuple[str, str], now=time.time) -> list[dict]:
    q = urlencode({"q": term, "max": LIMIT})
    data = _fetch_json(f"{_pi_base()}/search/byterm?{q}", pi_headers(*creds, now()))
    return [_show(f["url"], f["title"], f.get("author"),
                  _first_category(f.get("categories")), f.get("artwork") or f.get("image"))
            for f in data.get("feeds") or []
            if isinstance(f, dict) and f.get("url") and f.get("title")]
```

**Step 4: Run the tests**

Run: `python3 -m unittest tests.test_podcast_dirs -v` → PASS

**Step 5: Commit**

```bash
git add sqlch/sources/_podcast_dirs.py tests/test_podcast_dirs.py
git commit -m "sqlch: podcast index search with key/secret from env or secrets file"
```

---

### Task 4: Podcasts source search, merging and registration

**Files:**
- Create: `sqlch/sources/podcasts.py`
- Modify: `sqlch/sources/__init__.py` (`_MODULES`)
- Test: `tests/test_source_podcasts.py`

Behavior:
- `search` queries every configured directory in parallel. Apple is always one; Podcast Index is one only when `pi_credentials` finds a key.
- Results merge on the normalized feed URL (`norm_feed`: drop the scheme, lowercase the host, drop `www.`, drop a trailing `/`, keep the query). The first show seen keeps its title; `providers` collects every directory in `PROVIDERS` order; missing `genre`/`image`/`artist` are filled from later duplicates.
- If one directory fails, the rest still return and `last_warning()` names the failed ones. If all fail, `search` raises `RuntimeError`.
- The warning is kept per thread (`threading.local`), because the pane reads it in the same worker thread right after `search`.

**Step 1: Write the failing test**

`tests/test_source_podcasts.py`:

```python
import unittest
from unittest import mock

from sqlch.sources import REGISTRY, podcasts


def show(url, title, genre=None, artist=None, image=None):
    return {"feed_url": url, "title": title, "artist": artist, "genre": genre, "image": image}


class Dirs:
    """Patch the directory list podcasts.search sees."""

    def __init__(self, test, **fns):
        p = mock.patch.object(podcasts, "_directories",
                              lambda: [(n, fns[n]) for n in podcasts.PROVIDERS if n in fns])
        p.start()
        test.addCleanup(p.stop)


def boom(q):
    raise OSError("down")


class TestBasics(unittest.TestCase):
    def test_registered(self):
        self.assertIs(REGISTRY["podcasts"], podcasts)

    def test_shape(self):
        self.assertTrue(podcasts.available())
        self.assertEqual(podcasts.GROUPINGS, ("source", "genre", "az"))
        self.assertTrue(podcasts.HAS_DATES)
        self.assertEqual([s["id"] for s in podcasts.sections()], ["following"])

    def test_norm_feed(self):
        n = podcasts.norm_feed
        self.assertEqual(n("https://www.Feeds.Example.com/show/"), "feeds.example.com/show")
        self.assertEqual(n("http://feeds.example.com/show"), "feeds.example.com/show")
        self.assertEqual(n("https://x.com/rss?id=1"), "x.com/rss?id=1")


class TestSearch(unittest.TestCase):
    def test_blank_query(self):
        self.assertEqual(podcasts.search("  "), [])

    def test_merges_duplicates_across_directories(self):
        Dirs(self,
             apple=lambda q: [show("https://feeds.x.com/a", "A", "Comedy"),
                              show("https://feeds.x.com/b", "B")],
             podcastindex=lambda q: [show("http://www.feeds.x.com/a/", "A (pi)", None, "Ann",
                                          "https://img/a"),
                                     show("https://feeds.x.com/c", "C", "News")])
        items = podcasts.search("x")
        self.assertEqual([i["title"] for i in items], ["A", "B", "C"])
        a = items[0]
        self.assertEqual(a["providers"], ["apple", "podcastindex"])
        self.assertEqual((a["genre"], a["artist"], a["image"]), ("Comedy", "Ann", "https://img/a"))
        self.assertEqual((a["kind"], a["path"], a["feed_url"]),
                         ("folder", "feed:https://feeds.x.com/a", "https://feeds.x.com/a"))
        self.assertIsNone(a["art"])
        self.assertEqual(items[2]["providers"], ["podcastindex"])
        self.assertIsNone(podcasts.last_warning())

    def test_one_directory_down_warns_and_returns_the_rest(self):
        Dirs(self, apple=lambda q: [show("https://f/a", "A")], podcastindex=boom)
        self.assertEqual([i["title"] for i in podcasts.search("x")], ["A"])
        self.assertEqual(podcasts.last_warning(), "Podcast Index unavailable")

    def test_all_down_raises(self):
        Dirs(self, apple=boom, podcastindex=boom)
        with self.assertRaises(RuntimeError):
            podcasts.search("x")

    def test_warning_clears_on_next_call(self):
        Dirs(self, apple=lambda q: [], podcastindex=boom)
        podcasts.search("x")
        self.assertIsNotNone(podcasts.last_warning())
        podcasts.browse("section:following")
        self.assertIsNone(podcasts.last_warning())

    def test_directories_without_a_key_is_apple_only(self):
        with mock.patch.object(podcasts.dirs, "pi_credentials", return_value=None):
            self.assertEqual([n for n, _ in podcasts._directories()], ["apple"])
        with mock.patch.object(podcasts.dirs, "pi_credentials", return_value=("k", "s")):
            self.assertEqual([n for n, _ in podcasts._directories()], ["apple", "podcastindex"])
```

(`test_warning_clears_on_next_call` calls `browse("section:following")`, which Task 6 implements. Until then, Task 4's `browse` handles that path by returning `[]`, as shown below.)

**Step 2: Run it and check it fails**

Run: `python3 -m unittest tests.test_source_podcasts -v`
Expected: ERROR, `cannot import name 'podcasts'`.

**Step 3: Implement**

`sqlch/sources/podcasts.py`:

```python
"""Podcasts from several directories (Apple Podcasts, Podcast Index) merged on
their feed URL. Episodes come from the show's RSS feed and play in mpv."""

import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from sqlch.sources import _podcast_dirs as dirs
from sqlch.sources import source_config
from sqlch.sources.base import make_item

NAME = "podcasts"
TITLE = "PODCASTS"
LABEL = "Podcasts"
HINT = ("Searches Apple Podcasts. Put PODCASTINDEX_API_KEY and "
        "PODCASTINDEX_API_SECRET in /run/secrets/podcastindex_env to search "
        "Podcast Index too.")
HAS_DATES = True
GROUPINGS = ("source", "genre", "az")
# Directory id -> header title and the short tag shown on merged rows, in display order.
PROVIDERS = {"apple": {"title": "APPLE PODCASTS", "short": "apple", "label": "Apple Podcasts"},
             "podcastindex": {"title": "PODCAST INDEX", "short": "pi", "label": "Podcast Index"}}

_state = threading.local()


def available() -> bool:
    return True


def sections() -> list[dict]:
    return [{"id": "following", "title": "FOLLOWING"}]


def last_warning() -> str | None:
    """A note about directories that failed during this thread's last search."""
    return getattr(_state, "warning", None)


def norm_feed(url: str) -> str:
    p = urlsplit(url.strip())
    host = p.netloc.lower().removeprefix("www.")
    return host + p.path.rstrip("/") + (f"?{p.query}" if p.query else "")


def _directories() -> list[tuple]:
    out = [("apple", dirs.apple_search)]
    cfg = source_config(NAME)
    creds = dirs.pi_credentials(cfg.get("env_file") if isinstance(cfg, dict) else None)
    if creds:
        out.append(("podcastindex", lambda q: dirs.pi_search(q, creds)))
    return out


def show_item(s: dict, providers: list[str]) -> dict:
    item = make_item(NAME, s["feed_url"], s["title"], kind="folder",
                     path=f"feed:{s['feed_url']}", artist=s.get("artist"),
                     genre=s.get("genre"), providers=list(providers),
                     feed_url=s["feed_url"])
    item["image"] = s.get("image")
    return item


def _merge(batches: list[tuple]) -> list[dict]:
    merged: dict[str, dict] = {}
    for provider, shows in batches:
        for s in shows:
            key = norm_feed(s["feed_url"])
            m = merged.get(key)
            if m is None:
                merged[key] = show_item(s, [provider])
                continue
            if provider not in m["providers"]:
                m["providers"].append(provider)
            for f in ("genre", "artist", "image"):
                m[f] = m[f] or s.get(f)
    return list(merged.values())


def search(query: str) -> list[dict]:
    _state.warning = None
    query = (query or "").strip()
    if not query:
        return []
    directories = _directories()
    with ThreadPoolExecutor(max_workers=len(directories)) as ex:
        futures = [(name, ex.submit(fn, query)) for name, fn in directories]
    batches, failed = [], []
    for name, fut in futures:
        try:
            batches.append((name, fut.result()))
        except Exception as e:
            failed.append((name, e))
    if not batches:
        raise RuntimeError(f"no podcast directory answered: {failed[0][1]}")
    if failed:
        _state.warning = " and ".join(PROVIDERS[n]["label"] for n, _ in failed) + " unavailable"
    return _merge(batches)


def browse(path: str | None = None) -> list[dict]:
    _state.warning = None
    if not path or path == "section:following":
        return []
    raise ValueError("bad podcasts path")
```

`sqlch/sources/__init__.py`: add `"podcasts"` to the end of `_MODULES`:

```python
_MODULES = ("local", "video", "jellyfin", "youtube", "spotify", "podcasts")
```

**Step 4: Run the tests**

Run: `python3 -m unittest tests.test_source_podcasts tests.test_sources -v` → PASS

**Step 5: Commit**

```bash
git add sqlch/sources/podcasts.py sqlch/sources/__init__.py tests/test_source_podcasts.py
git commit -m "sqlch: podcasts source searches apple and podcast index, merged on feed url"
```

---

### Task 5: RSS episodes and playback

**Files:**
- Modify: `sqlch/sources/podcasts.py`
- Test: `tests/test_source_podcasts.py`

Behavior:
- `browse("feed:<url>")` fetches the feed (http/https only, at most `MAX_FEED_BYTES`) and returns `parse_feed(data, url)`.
- `parse_feed` returns episode tracks, newest first, capped at `FEED_LIMIT`: id = `<guid>` (else the enclosure URL), title, `artist` = show title, `date` = pubDate as epoch seconds, `duration` from `itunes:duration` (`SS`, `MM:SS`, `HH:MM:SS`), `url` = enclosure, `image` = episode `itunes:image` else channel `itunes:image` else channel `<image><url>`. Items without an enclosure URL are skipped. Episodes have **no** `feed_url`, so they get no Follow button.
- `resolve(item)` needs an http(s) `url`. Its meta is `{title, artist: show, album: show, art: <cached local image or None>}`.
- `xml.etree.ElementTree` on a feed: the expat bundled with Python 3.11+ refuses entity-expansion bombs. The byte cap bounds the rest.

**Step 1: Write the failing tests**

Append to `tests/test_source_podcasts.py`:

```python
import tempfile
from pathlib import Path

FEED = b"""<?xml version="1.0"?>
<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" version="2.0"><channel>
  <title>The Show</title>
  <itunes:image href="https://img/show.jpg"/>
  <item><title>Old</title><guid>g1</guid>
    <pubDate>Mon, 05 Oct 2026 10:00:00 +0000</pubDate>
    <enclosure url="https://cdn/old.mp3" type="audio/mpeg"/>
    <itunes:duration>1:02:03</itunes:duration></item>
  <item><title>New</title>
    <pubDate>Fri, 16 Oct 2026 00:00:00 GMT</pubDate>
    <enclosure url="https://cdn/new.mp3" type="audio/mpeg"/>
    <itunes:image href="https://img/new.jpg"/>
    <itunes:duration>45:30</itunes:duration></item>
  <item><title>Text only</title><guid>g3</guid></item>
  <item><title>Seconds</title><guid>g4</guid><enclosure url="https://cdn/s.mp3"/>
    <itunes:duration>90</itunes:duration><pubDate>garbage</pubDate></item>
</channel></rss>"""


class TestFeed(unittest.TestCase):
    def test_parse_feed(self):
        eps = podcasts.parse_feed(FEED, "https://f/show")
        self.assertEqual([e["title"] for e in eps], ["New", "Old", "Seconds"])
        new, old, secs = eps
        self.assertEqual((new["id"], new["url"], new["duration"], new["date"]),
                         ("https://cdn/new.mp3", "https://cdn/new.mp3", 2730, 1792108800))
        self.assertEqual(new["image"], "https://img/new.jpg")
        self.assertEqual((old["id"], old["duration"], old["image"]),
                         ("g1", 3723, "https://img/show.jpg"))
        self.assertEqual((secs["duration"], secs["date"]), (90, None))
        for e in eps:
            self.assertEqual((e["kind"], e["artist"], e["source"]), ("track", "The Show", "podcasts"))
            self.assertIsNone(e["feed_url"])
            self.assertIsNone(e["art"])

    def test_not_rss(self):
        with self.assertRaises(ValueError):
            podcasts.parse_feed(b"<html/>", "https://f/x")

    def test_duration_formats(self):
        d = podcasts.parse_duration
        self.assertEqual([d("90"), d("1:30"), d("1:00:00"), d(""), d(None), d("abc"), d("1:2:3:4")],
                         [90, 90, 3600, None, None, None, None])

    def test_browse_feed_rejects_non_http(self):
        for bad in ("feed:file:///etc/passwd", "feed:", "nope"):
            with self.assertRaises(ValueError):
                podcasts.browse(bad)

    def test_browse_feed_fetches_and_parses(self):
        with mock.patch.object(podcasts, "_fetch_feed", return_value=FEED) as f:
            eps = podcasts.browse("feed:https://f/show")
        f.assert_called_once_with("https://f/show")
        self.assertEqual(len(eps), 3)


class TestResolve(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        p = mock.patch.object(podcasts, "cache_dir", lambda: Path(self._tmp.name))
        p.start()
        self.addCleanup(p.stop)

    def ep(self, **kw):
        e = podcasts.parse_feed(FEED, "https://f/show")[0]
        e.update(kw)
        return e

    def test_resolve_targets_the_enclosure(self):
        with mock.patch.object(podcasts, "_cached_art", return_value="/tmp/a.jpg") as art:
            t = podcasts.resolve(self.ep())
        art.assert_called_once_with("https://img/new.jpg")
        self.assertEqual(t.url, "https://cdn/new.mp3")
        self.assertFalse(t.video)
        self.assertEqual(t.meta, {"title": "New", "artist": "The Show",
                                  "album": "The Show", "art": "/tmp/a.jpg"})

    def test_resolve_needs_an_http_url(self):
        for url in (None, "", "file:///x.mp3"):
            with self.assertRaises(ValueError):
                podcasts.resolve(self.ep(url=url))

    def test_cached_art_downloads_once(self):
        calls = []

        def fake_get(url):
            calls.append(url)
            return b"img"

        with mock.patch.object(podcasts, "_download", fake_get):
            p1 = podcasts._cached_art("https://img/a.jpg")
            p2 = podcasts._cached_art("https://img/a.jpg")
        self.assertEqual(p1, p2)
        self.assertEqual(Path(p1).read_bytes(), b"img")
        self.assertEqual(calls, ["https://img/a.jpg"])
        self.assertIsNone(podcasts._cached_art(None))

    def test_cached_art_failure_is_none(self):
        with mock.patch.object(podcasts, "_download", side_effect=OSError("x")):
            self.assertIsNone(podcasts._cached_art("https://img/b.jpg"))
```

`1792108800` is `2026-10-16T00:00:00Z`, the same constant `tests/test_source_pane.py` uses.

**Step 2: Run them and check they fail**

Run: `python3 -m unittest tests.test_source_podcasts -v`
Expected: ERROR, no attribute `parse_feed` / `parse_duration` / `resolve`.

**Step 3: Implement**

Add to `sqlch/sources/podcasts.py`. The imports go at the top with the others:

```python
import hashlib
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen

from sqlch.core.paths import cache_dir
from sqlch.sources.base import Target
```

Then:

```python
FEED_LIMIT = 100
MAX_FEED_BYTES = 10 * 1024 * 1024
TIMEOUT = 8
_ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


def _is_http(url) -> bool:
    return isinstance(url, str) and url.startswith(("http://", "https://"))


def _download(url: str, limit: int = MAX_FEED_BYTES) -> bytes:
    req = Request(url, headers={"User-Agent": dirs.UA})
    with urlopen(req, timeout=TIMEOUT) as r:
        return r.read(limit)


def _fetch_feed(url: str) -> bytes:
    return _download(url)


def parse_duration(text) -> int | None:
    text = (text or "").strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) > 3:
        return None
    try:
        secs = 0
        for p in parts:
            secs = secs * 60 + int(float(p))
    except ValueError:
        return None
    return secs or None


def _date(text) -> int | None:
    try:
        return int(parsedate_to_datetime(text).timestamp())
    except (TypeError, ValueError, IndexError):
        return None


def _image(node) -> str | None:
    el = node.find(f"{_ITUNES}image")
    href = el.get("href") if el is not None else None
    return href or (node.findtext("image/url") or "").strip() or None


def parse_feed(data: bytes, feed_url: str) -> list[dict]:
    root = ET.fromstring(data)
    channel = root.find("channel")
    if channel is None:
        raise ValueError("not an RSS feed")
    show = (channel.findtext("title") or "").strip() or feed_url
    show_image = _image(channel)
    episodes = []
    for it in channel.findall("item"):
        enc = it.find("enclosure")
        url = enc.get("url") if enc is not None else None
        if not url:
            continue
        guid = (it.findtext("guid") or "").strip() or url
        ep = make_item(NAME, guid, (it.findtext("title") or "").strip() or "Untitled",
                       artist=show, date=_date(it.findtext("pubDate")),
                       duration=parse_duration(it.findtext(f"{_ITUNES}duration")), url=url)
        ep["image"] = _image(it) or show_image
        episodes.append(ep)
    episodes.sort(key=lambda e: e["date"] or 0, reverse=True)
    return episodes[:FEED_LIMIT]


def _cached_art(url) -> str | None:
    if not _is_http(url):
        return None
    dest = cache_dir() / "podcasts" / (hashlib.sha1(url.encode()).hexdigest()[:20] + ".img")
    if dest.is_file():
        return str(dest)
    try:
        data = _download(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    except OSError:
        return None
    return str(dest)


def resolve(item: dict) -> Target:
    url = item.get("url")
    if not _is_http(url):
        raise ValueError("episode has no audio url")
    show = item.get("artist")
    meta = {"title": item.get("title"), "artist": show, "album": show,
            "art": _cached_art(item.get("image"))}
    return Target(url, False, meta)
```

Replace Task 4's `browse` with:

```python
def browse(path: str | None = None) -> list[dict]:
    _state.warning = None
    if not path or path == "section:following":
        return []
    kind, _, url = path.partition(":")
    if kind != "feed" or not _is_http(url):
        raise ValueError("bad podcasts path")
    return parse_feed(_fetch_feed(url), url)
```

(GdkPixbuf/Gtk sniff the image type from its bytes, so the cache's `.img` extension doesn't matter. Check that `_apply_cover_path` in `now_playing.py` loads by content, not by extension. If it goes by extension, use the URL's suffix when it is `.jpg/.jpeg/.png/.webp`, else `.jpg`.)

**Step 4: Run the tests**

Run: `python3 -m unittest tests.test_source_podcasts -v` → PASS

**Step 5: Commit**

```bash
git add sqlch/sources/podcasts.py tests/test_source_podcasts.py
git commit -m "sqlch: podcast episodes from RSS, enclosure playback with cached art"
```

---

### Task 6: Followed podcasts store and FOLLOWING section

**Files:**
- Modify: `sqlch/core/follows.py`
- Modify: `sqlch/sources/podcasts.py` (`browse("section:following")`)
- Test: `tests/test_follows.py`, `tests/test_source_podcasts.py`

**Step 1: Write the failing tests**

Append to `tests/test_follows.py` (it already has a `Base` that points `data_dir` at a temp dir):

```python
SHOW = {"source": "podcasts", "id": "https://f/a", "title": "A", "kind": "folder",
        "path": "feed:https://f/a", "feed_url": "https://f/a", "artist": "Ann",
        "genre": "Comedy", "providers": ["apple"], "image": "https://img/a",
        "art": None, "url": None}


class TestPodcastFollows(Base):
    def test_empty(self):
        self.assertEqual(follows.list_podcasts(), [])
        self.assertEqual(follows.followed_feeds(), set())

    def test_follow_stores_only_the_show_fields(self):
        follows.follow_podcast(SHOW)
        self.assertEqual(follows.list_podcasts(), [
            {"feed_url": "https://f/a", "title": "A", "artist": "Ann",
             "genre": "Comedy", "providers": ["apple"], "image": "https://img/a"}])
        self.assertEqual(follows.followed_feeds(), {"https://f/a"})

    def test_duplicate_follow_is_ignored(self):
        follows.follow_podcast(SHOW)
        follows.follow_podcast({**SHOW, "title": "Again"})
        self.assertEqual([r["title"] for r in follows.list_podcasts()], ["A"])

    def test_unfollow(self):
        follows.follow_podcast(SHOW)
        follows.unfollow_podcast("https://f/a")
        self.assertEqual(follows.list_podcasts(), [])
        follows.unfollow_podcast("https://f/a")  # absent: no error

    def test_follow_needs_a_feed_url(self):
        with self.assertRaises(ValueError):
            follows.follow_podcast({"title": "x"})
```

Append to `tests/test_source_podcasts.py`:

```python
class TestFollowing(unittest.TestCase):
    def test_following_section_lists_stored_shows_as_folders(self):
        rows = [{"feed_url": "https://f/a", "title": "A", "artist": "Ann",
                 "genre": "Comedy", "providers": ["apple", "podcastindex"],
                 "image": "https://img/a"}]
        with mock.patch.object(podcasts.follows, "list_podcasts", return_value=rows):
            items = podcasts.browse("section:following")
        self.assertEqual(len(items), 1)
        a = items[0]
        self.assertEqual((a["kind"], a["path"], a["feed_url"], a["genre"], a["providers"]),
                         ("folder", "feed:https://f/a", "https://f/a", "Comedy",
                          ["apple", "podcastindex"]))

    def test_root_is_following(self):
        with mock.patch.object(podcasts.follows, "list_podcasts", return_value=[]):
            self.assertEqual(podcasts.browse(None), [])
```

**Step 2: Run them and check they fail**

Run: `python3 -m unittest tests.test_follows tests.test_source_podcasts -v`
Expected: ERROR, no attribute `list_podcasts` / `follows`.

**Step 3: Implement**

`sqlch/core/follows.py`: update the module docstring's first line to `"""Favorites, followed YouTube channels and followed podcasts: small JSON files in data_dir().`, add `PODCASTS = "podcast_follows.json"` next to `FOLLOWS`, and append:

```python
# ---- followed podcasts ----

_PODCAST_FIELDS = ("feed_url", "title", "artist", "genre", "providers", "image")


def list_podcasts() -> list[dict]:
    return [r for r in _read(PODCASTS) if isinstance(r, dict) and r.get("feed_url")]


def followed_feeds() -> set[str]:
    return {r["feed_url"] for r in list_podcasts()}


def follow_podcast(item: dict) -> None:
    row = {k: item.get(k) for k in _PODCAST_FIELDS}
    if not row["feed_url"]:
        raise ValueError("a followed podcast needs a feed_url")
    with _lock:
        rows = _read_for_write(PODCASTS)
        if any(isinstance(r, dict) and r.get("feed_url") == row["feed_url"] for r in rows):
            return
        rows.append(row)
        _write(PODCASTS, rows)


def unfollow_podcast(feed_url: str) -> None:
    with _lock:
        rows = _read_for_write(PODCASTS)
        kept = [r for r in rows
                if not (isinstance(r, dict) and r.get("feed_url") == feed_url)]
        if len(kept) != len(rows):
            _write(PODCASTS, kept)
```

`sqlch/sources/podcasts.py`: add `from sqlch.core import follows` to the imports, and in `browse` replace `return []` for the following section with:

```python
    if not path or path == "section:following":
        return [show_item(r, r.get("providers") or []) for r in follows.list_podcasts()]
```

**Step 4: Run the tests**

Run: `python3 -m unittest tests.test_follows tests.test_source_podcasts -v` → PASS

**Step 5: Commit**

```bash
git add sqlch/core/follows.py sqlch/sources/podcasts.py tests/test_follows.py tests/test_source_podcasts.py
git commit -m "sqlch: followed podcasts store and the FOLLOWING section"
```

---

### Task 7: Daemon follow commands for podcasts

**Files:**
- Modify: `sqlch/core/daemon.py` (next to the `follow`/`unfollow` handlers, around line 195)
- Test: `tests/test_daemon_follows.py`

**Step 1: Write the failing tests**

Append to `TestDaemonFollowCommands` in `tests/test_daemon_follows.py`:

```python
    def test_podcast_follow(self):
        item = {"feed_url": "https://f/a", "title": "A"}
        with mock.patch.object(daemon.follows, "follow_podcast") as f:
            self.assertEqual(daemon._handle({"cmd": "podcast_follow", "item": item}),
                             {"ok": True})
        f.assert_called_once_with(item)

    def test_podcast_follow_rejects_non_http_feeds(self):
        with mock.patch.object(daemon.follows, "follow_podcast") as f:
            for msg in ({"cmd": "podcast_follow"},
                        {"cmd": "podcast_follow", "item": "x"},
                        {"cmd": "podcast_follow", "item": {"feed_url": "file:///etc/passwd"}}):
                self.assertFalse(daemon._handle(msg)["ok"])
        f.assert_not_called()

    def test_podcast_unfollow(self):
        with mock.patch.object(daemon.follows, "unfollow_podcast") as u:
            self.assertEqual(daemon._handle({"cmd": "podcast_unfollow",
                                             "feed_url": "https://f/a"}), {"ok": True})
            self.assertFalse(daemon._handle({"cmd": "podcast_unfollow", "feed_url": 3})["ok"])
        u.assert_called_once_with("https://f/a")
```

**Step 2: Run them and check they fail**

Run: `python3 -m unittest tests.test_daemon_follows -v`
Expected: FAIL, the unknown command response is not `{"ok": True}`.

**Step 3: Implement**

In `sqlch/core/daemon.py`, after the `unfollow` block:

```python
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
```

**Step 4: Run the tests**

Run: `python3 -m unittest tests.test_daemon_follows -v` → PASS

**Step 5: Commit**

```bash
git add sqlch/core/daemon.py tests/test_daemon_follows.py
git commit -m "sqlch: daemon follows and unfollows podcasts"
```

---

### Task 8: Pure grouping module

**Files:**
- Create: `sqlch_gui/ui/grouping.py`
- Test: `tests/test_grouping.py`

`group(items, mode, providers)` returns rows for the pane to draw:
- `("header", text, depth)`: a group header. Depth 0 is the outer level and depth 1 is genre under source.
- `("item", item, tag)`: a row plus a short tag for its subtitle (`""` for none).

Modes:
- `source`: one depth-0 header per provider (in `providers` order, then any unknown ids A–Z, then `OTHER` for items with no providers), then depth-1 genre headers, then items A–Z. An item from two providers appears under both. No tag.
- `genre`: depth-0 genre headers (A–Z by casefold, `Other` last), items A–Z, tag = provider shorts joined by `·`.
- `az`: items A–Z by casefolded title, no headers, tag = genre (or `""`).

**Step 1: Write the failing test**

```python
import unittest

from sqlch_gui.ui.grouping import LABELS, MODES, group, next_mode

PROV = {"apple": {"title": "APPLE PODCASTS", "short": "apple"},
        "podcastindex": {"title": "PODCAST INDEX", "short": "pi"}}


def it(title, genre=None, providers=("apple",)):
    return {"title": title, "genre": genre, "providers": list(providers)}


A = it("smartless", "Comedy", ("apple", "podcastindex"))
B = it("Conan", "Comedy")
C = it("Serial", "True Crime")
D = it("Linux Unplugged", "Technology", ("podcastindex",))
E = it("Mystery", None, ("apple",))


def shape(rows):
    return [(r[0], r[1] if r[0] == "header" else r[1]["title"], r[2]) for r in rows]


class TestGrouping(unittest.TestCase):
    def test_modes_cycle(self):
        self.assertEqual(MODES, ("source", "genre", "az"))
        self.assertEqual([next_mode(m, MODES) for m in MODES], ["genre", "az", "source"])
        self.assertEqual(LABELS["az"], "A–Z")

    def test_az(self):
        self.assertEqual(shape(group([C, A, B], "az", PROV)), [
            ("item", "Conan", "Comedy"), ("item", "Serial", "True Crime"),
            ("item", "smartless", "Comedy")])

    def test_genre_puts_other_last_and_tags_providers(self):
        self.assertEqual(shape(group([E, D, A, B], "genre", PROV)), [
            ("header", "Comedy", 0),
            ("item", "Conan", "apple"), ("item", "smartless", "apple·pi"),
            ("header", "Technology", 0), ("item", "Linux Unplugged", "pi"),
            ("header", "Other", 0), ("item", "Mystery", "apple")])

    def test_source_nests_genre_and_repeats_shared_shows(self):
        self.assertEqual(shape(group([A, B, C, D], "source", PROV)), [
            ("header", "APPLE PODCASTS", 0),
            ("header", "Comedy", 1), ("item", "Conan", ""), ("item", "smartless", ""),
            ("header", "True Crime", 1), ("item", "Serial", ""),
            ("header", "PODCAST INDEX", 0),
            ("header", "Comedy", 1), ("item", "smartless", ""),
            ("header", "Technology", 1), ("item", "Linux Unplugged", "")])

    def test_source_with_unknown_and_missing_providers(self):
        rows = shape(group([it("X", "Arts", ("zeta",)), it("Y", "Arts", ())], "source", PROV))
        self.assertEqual(rows, [("header", "ZETA", 0), ("header", "Arts", 1), ("item", "X", ""),
                                ("header", "OTHER", 0), ("header", "Arts", 1), ("item", "Y", "")])

    def test_empty(self):
        for m in MODES:
            self.assertEqual(group([], m, PROV), [])
```

**Step 2: Run it and check it fails**

Run: `python3 -m unittest tests.test_grouping -v`
Expected: ERROR, `No module named 'sqlch_gui.ui.grouping'`.

**Step 3: Implement**

`sqlch_gui/ui/grouping.py`:

```python
"""Grouping for a source pane's sort pill: pure, no Gtk. group() turns show
items into ("header", text, depth) and ("item", item, tag) rows."""

MODES = ("source", "genre", "az")
LABELS = {"source": "SOURCE", "genre": "GENRE", "az": "A–Z"}
OTHER = "Other"


def next_mode(mode: str, modes=MODES) -> str:
    return modes[(modes.index(mode) + 1) % len(modes)] if mode in modes else modes[0]


def _title(item) -> str:
    return (item.get("title") or "").casefold()


def _genre(item) -> str:
    return item.get("genre") or OTHER


def _by_genre(items, depth, tag) -> list:
    rows = []
    for g in sorted({_genre(i) for i in items}, key=lambda g: (g == OTHER, g.casefold())):
        rows.append(("header", g, depth))
        rows += [("item", i, tag(i)) for i in sorted(items, key=_title) if _genre(i) == g]
    return rows


def group(items, mode, providers=None) -> list:
    providers = providers or {}

    def shorts(i):
        return "·".join(providers.get(p, {}).get("short", p) for p in i.get("providers") or [])

    if mode == "az":
        return [("item", i, i.get("genre") or "") for i in sorted(items, key=_title)]
    if mode == "genre":
        return _by_genre(items, 0, shorts)
    seen = {p for i in items for p in i.get("providers") or []}
    order = [p for p in providers if p in seen] + sorted(seen - set(providers))
    rows = []
    for p in order:
        rows.append(("header", providers.get(p, {}).get("title", p.upper()), 0))
        rows += _by_genre([i for i in items if p in (i.get("providers") or [])], 1, lambda i: "")
    loose = [i for i in items if not i.get("providers")]
    if loose:
        rows.append(("header", OTHER.upper(), 0))
        rows += _by_genre(loose, 1, lambda i: "")
    return rows
```

**Step 4: Run the tests**

Run: `python3 -m unittest tests.test_grouping -v` → PASS

**Step 5: Commit**

```bash
git add sqlch_gui/ui/grouping.py tests/test_grouping.py
git commit -m "sqlch-gui: grouping rows for source, genre and A-Z show lists"
```

---

### Task 9: SourcePane follows podcasts and shows search warnings

**Files:**
- Modify: `sqlch_gui/ui/source_pane.py` (`_with_marks`, `_show`, `_build_row`, `_toggle_follow`)
- Test: `tests/test_source_pane.py`

Changes:
1. `_with_marks` adds the followed feeds to the followed set, and returns the source's `last_warning()` as a fourth value.
2. `_show` unpacks four values and shows the warning in the status line, before "Nothing here".
3. `_build_row` offers Follow when an item has `channel_id` **or** `feed_url`.
4. `_toggle_follow` sends `podcast_follow` / `podcast_unfollow` for `feed_url` items, and reloads after an unfollow in `channels` **or** `following`.

**Step 1: Write the failing tests**

In `tests/test_source_pane.py`, extend `FakeStore`:

```python
class FakeStore:
    def __init__(self, favs=(), followed=(), feeds=()):
        self.favs = list(favs)
        self.followed = set(followed)
        self.feeds = set(feeds)

    ...existing methods...

    def followed_feeds(self):
        return set(self.feeds)
```

Append a test class:

```python
SHOW = {"source": "fake", "id": "https://f/a", "title": "Show", "kind": "folder",
        "path": "feed:https://f/a", "feed_url": "https://f/a", "genre": "Comedy",
        "providers": ["apple"]}


def button_labels(widget, out=None):
    out = [] if out is None else out
    child = widget.get_first_child()
    while child:
        if isinstance(child, Gtk.Button):
            out.append(child.get_label())
        button_labels(child, out)
        child = child.get_next_sibling()
    return out


class TestPodcastFollow(unittest.TestCase):
    def test_feed_rows_offer_follow(self):
        p = make(Fake(tree={None: [SHOW]}))
        p.on_shown()
        self.assertIn("Follow", button_labels(p._build_row(SHOW)))
        p = make(Fake(tree={None: [SHOW]}), store=FakeStore(feeds=["https://f/a"]))
        p.on_shown()
        self.assertIn("Unfollow", button_labels(p._build_row(SHOW)))

    def test_follow_sends_podcast_follow_with_the_item(self):
        sent = []
        p = make(Fake(tree={None: [SHOW]}), send=lambda m: sent.append(m) or {"ok": True})
        p.on_shown()
        btn = Gtk.Button(label="Follow")
        p._toggle_follow(SHOW, btn)
        self.assertEqual(sent, [{"cmd": "podcast_follow", "item": SHOW}])
        self.assertEqual(btn.get_label(), "Unfollow")

    def test_unfollow_in_following_reloads(self):
        sent = []
        src = Fake(tree={"section:following": [SHOW]})
        src.sections = lambda: [{"id": "following", "title": "FOLLOWING"}]
        p = make(src, store=FakeStore(feeds=["https://f/a"]),
                 send=lambda m: sent.append(m) or {"ok": True})
        p.on_shown()
        src.tree["section:following"] = []
        p._toggle_follow(SHOW, Gtk.Button(label="Unfollow"))
        self.assertEqual(sent, [{"cmd": "podcast_unfollow", "feed_url": "https://f/a"}])
        self.assertEqual(p._items, [])


class TestSearchWarning(unittest.TestCase):
    def test_warning_shows_in_status(self):
        src = Fake()
        src.last_warning = lambda: "Podcast Index unavailable"
        p = make(src)
        p.on_shown()
        p._search("x")
        self.assertTrue(p.status.get_visible())
        self.assertEqual(p.status.get_text(), "Podcast Index unavailable")

    def test_no_warning_hook_is_fine(self):
        p = make(Fake())
        p.on_shown()
        p._search("x")
        self.assertFalse(p.status.get_visible())
```

**Step 2: Run them and check they fail**

Run: `python3 -m unittest tests.test_source_pane -v`
Expected: the new tests FAIL or ERROR (no Follow button on feed rows, a `KeyError: 'channel_id'` in `_toggle_follow`, no warning in status). The existing tests still pass.

**Step 3: Implement**

`_with_marks`:

```python
    def _with_marks(self, work):
        """Read star/follow state and any source warning in the worker; _show
        applies them on the main thread."""
        def run():
            result = work()
            warn = getattr(self.source, "last_warning", None)
            return (result, set(self._store.favorite_ids(self.source.NAME)),
                    set(self._store.followed_ids()) | set(self._store.followed_feeds()),
                    warn() if warn else None)
        return run
```

`_show`: change the unpack to

```python
        warning = None
        if err is None:
            result, self._fav_ids, self._followed, warning = result
```

and replace its final `self._set_status("" if self._items else "Nothing here")` with

```python
        self._set_status(warning or ("" if self._items else "Nothing here"))
```

`_build_row`: replace the `if item.get("channel_id"):` block with

```python
        follow_key = item.get("channel_id") or item.get("feed_url")
        if follow_key:
            following = follow_key in self._followed
            fol = Gtk.Button(label="Unfollow" if following else "Follow")
            fol.add_css_class("row-btn")
            fol.set_valign(Gtk.Align.CENTER)
            fol.connect("clicked", lambda b, it=item: self._toggle_follow(it, b))
            row.append(fol)
```

`_toggle_follow`: replace the top (everything before `def done`) with

```python
    def _toggle_follow(self, item, button):
        key = item.get("channel_id") or item["feed_url"]
        following = key in self._followed
        if item.get("channel_id"):
            if following:
                msg = {"cmd": "unfollow", "channel_id": key}
            else:
                name = item["title"] if item.get("kind") == "folder" else item.get("artist")
                msg = {"cmd": "follow", "channel_id": key, "name": name or key}
        elif following:
            msg = {"cmd": "podcast_unfollow", "feed_url": key}
        else:
            msg = {"cmd": "podcast_follow", "item": item}
```

and inside `done`, use `key` in place of `cid`, and widen the reload condition:

```python
            if following:
                self._followed.discard(key)
            else:
                self._followed.add(key)
            button.set_label("Follow" if following else "Unfollow")
            if following and self._section in ("channels", "following") \
                    and not self._stack and not self._searching:
                self._reload()
```

`sqlch.core.follows` (the real store) already has `followed_feeds` from Task 6. Any other fake store in the tests (grep `def followed_ids` under `tests/`) also needs a `followed_feeds` returning `set()`.

**Step 4: Run the tests**

Run: `python3 -m unittest tests.test_source_pane -v` → PASS (old and new)

**Step 5: Commit**

```bash
git add sqlch_gui/ui/source_pane.py tests/test_source_pane.py
git commit -m "sqlch-gui: source panes follow podcasts and show source warnings"
```

---

### Task 10: SourcePane sort pill and grouped show lists

**Files:**
- Modify: `sqlch_gui/ui/source_pane.py` (`__init__` search row, `_fill`, new helpers)
- Test: `tests/test_source_pane.py`

Behavior:
- When `source.GROUPINGS` exists, the search row gets a `section-pill` button labeled with `LABELS[mode]`, starting with the first mode. A click moves to `next_mode` and calls `_fill()`, never `_load()`.
- `_fill` groups only when `self._grouped()` is true: the source has `GROUPINGS`, there is no folder stack (top level), and either a search is showing or the section is not `favorites`. Otherwise, today's code runs unchanged (including Oldest first).
- Headers are `RibbonBanner(text, gold=(depth == 0), collapsible=True, collapsed=..., on_toggle=...)`, with depth-1 headers indented 10 px. Collapse state lives in `self._collapsed` (a set of header paths such as `"APPLE PODCASTS/Comedy"`) and resets on every `_show`. `_apply_collapse` walks the rows and hides everything below a collapsed header until the next header at the same or a shallower depth. A row is hidden by hiding its `Gtk.ListBoxRow` parent.
- Grouped item rows get the tag added to their subtitle.

**Step 1: Write the failing tests**

Append to `tests/test_source_pane.py`:

```python
from sqlch_gui.ui.banner import RibbonBanner


def show_item(title, genre, providers):
    return {"source": "fake", "id": title, "title": title, "kind": "folder",
            "path": f"feed:{title}", "feed_url": f"https://f/{title}",
            "genre": genre, "providers": list(providers)}


SHOWS = [show_item("Serial", "True Crime", ["apple"]),
         show_item("Conan", "Comedy", ["apple", "podcastindex"])]


def grouped_fake(tree=None):
    src = Fake(tree=tree or {"section:following": SHOWS, "feed:Conan": [TRACK]})
    src.GROUPINGS = ("source", "genre", "az")
    src.PROVIDERS = {"apple": {"title": "APPLE PODCASTS", "short": "apple"},
                     "podcastindex": {"title": "PODCAST INDEX", "short": "pi"}}
    src.sections = lambda: [{"id": "following", "title": "FOLLOWING"}]
    return src


def list_texts(p):
    """Header texts and row titles in list order, visible rows only."""
    out = []
    row = p.list.get_first_child()
    while row:
        child = row.get_child() if isinstance(row, Gtk.ListBoxRow) else row
        if row.get_visible():
            if isinstance(child, RibbonBanner):
                out.append(("H", child._text))
            else:
                out.append(("R", labels_of(child)[0].get_text()))
        row = row.get_next_sibling()
    return out


class TestGroupedPane(unittest.TestCase):
    def test_no_sort_pill_without_groupings(self):
        p = make(Fake())
        self.assertIsNone(p.btn_group)

    def test_source_mode_by_default(self):
        p = make(grouped_fake())
        p.on_shown()
        self.assertEqual(p.btn_group.get_label(), "SOURCE")
        self.assertEqual(list_texts(p), [
            ("H", "APPLE PODCASTS"), ("H", "Comedy"), ("R", "Conan"),
            ("H", "True Crime"), ("R", "Serial"),
            ("H", "PODCAST INDEX"), ("H", "Comedy"), ("R", "Conan")])

    def test_cycling_regroups_without_reloading(self):
        src = grouped_fake()
        p = make(src)
        p.on_shown()
        loads = len(src.browsed)
        p.btn_group.emit("clicked")
        self.assertEqual(p.btn_group.get_label(), "GENRE")
        self.assertEqual(list_texts(p), [("H", "Comedy"), ("R", "Conan"),
                                         ("H", "True Crime"), ("R", "Serial")])
        p.btn_group.emit("clicked")
        self.assertEqual(p.btn_group.get_label(), "A–Z")
        self.assertEqual(list_texts(p), [("R", "Conan"), ("R", "Serial")])
        self.assertEqual(len(src.browsed), loads)

    def test_collapsing_a_source_hides_its_genres_and_rows(self):
        p = make(grouped_fake())
        p.on_shown()
        p._toggle_group("APPLE PODCASTS", True)
        self.assertEqual(list_texts(p), [("H", "APPLE PODCASTS"), ("H", "PODCAST INDEX"),
                                         ("H", "Comedy"), ("R", "Conan")])
        p._toggle_group("APPLE PODCASTS", False)
        p._toggle_group("APPLE PODCASTS/Comedy", True)
        self.assertEqual(list_texts(p)[:4], [("H", "APPLE PODCASTS"), ("H", "Comedy"),
                                             ("H", "True Crime"), ("R", "Serial")])

    def test_episode_lists_are_not_grouped(self):
        p = make(grouped_fake())
        p.on_shown()
        p._activate(SHOWS[1])
        self.assertEqual(list_texts(p), [("R", "Song")])

    def test_favorites_are_not_grouped(self):
        p = make(grouped_fake(), store=FakeStore(favs=SHOWS))
        p.on_shown()
        p._select_section("favorites")
        self.assertEqual(list_texts(p), [("R", "Serial"), ("R", "Conan")])

    def test_search_results_are_grouped(self):
        src = grouped_fake()
        src.search = lambda q: SHOWS
        p = make(src)
        p.on_shown()
        p._search("x")
        self.assertEqual(list_texts(p)[0], ("H", "APPLE PODCASTS"))
```

`labels_of` already exists further down `tests/test_source_pane.py`. Put the new class after it, or move `labels_of` up. If `RibbonBanner` does not keep its text as `_text`, use whatever attribute it does keep (`banner.py:39` sets `self._text`).

**Step 2: Run them and check they fail**

Run: `python3 -m unittest tests.test_source_pane.TestGroupedPane -v`
Expected: ERROR, `'SourcePane' object has no attribute 'btn_group'`.

**Step 3: Implement**

Imports at the top of `sqlch_gui/ui/source_pane.py`:

```python
from .banner import RibbonBanner
from .grouping import LABELS, group, next_mode
```

In `__init__`, next to `self._oldest_first = False`:

```python
        self._groupings = tuple(getattr(source, "GROUPINGS", ()) or ())
        self._group_mode = self._groupings[0] if self._groupings else None
        self._collapsed: set = set()
        self._group_rows: list = []
```

In the search row, after the `HAS_DATES` block and before `self.append(search_box)`:

```python
        self.btn_group = None
        if self._groupings:
            self.btn_group = Gtk.Button(label=LABELS.get(self._group_mode, self._group_mode))
            self.btn_group.add_css_class("section-pill")
            self.btn_group.set_tooltip_text("Group by")
            self.btn_group.connect("clicked", self._on_group_clicked)
            search_box.append(self.btn_group)
```

In `_show`, before `self._fill()`, reset collapse state: `self._collapsed = set()`.

Replace `_fill`:

```python
    def _fill(self):
        while child := self.list.get_first_child():
            self.list.remove(child)
        self._row_refs = {}
        self._group_rows = []
        if self._grouped():
            self._fill_grouped()
            return
        items = self._items
        if self._oldest_first:
            # Stable: undated rows (folders) keep their place after the dated ones.
            items = sorted(items, key=lambda i: (i.get("date") is None, i.get("date") or 0))
        for item in items:
            self.list.append(self._build_row(item))

    def _grouped(self):
        return bool(self._groupings) and not self._stack and \
            (self._searching or self._section != "favorites")

    def _fill_grouped(self):
        path: list[str] = []
        providers = getattr(self.source, "PROVIDERS", None) or {}
        for kind, value, extra in group(self._items, self._group_mode, providers):
            if kind == "header":
                del path[extra:]
                path.append(value)
                key = "/".join(path)
                banner = RibbonBanner(value, gold=extra == 0, collapsible=True,
                                      collapsed=key in self._collapsed,
                                      on_toggle=lambda c, k=key: self._toggle_group(k, c))
                if extra:
                    banner.set_margin_start(10 * extra)
                self.list.append(banner)
                self._group_rows.append((banner, extra, key))
            else:
                row = self._build_row(value, tag=extra)
                self.list.append(row)
                self._group_rows.append((row, None, None))
        self._apply_collapse()

    def _toggle_group(self, key, collapsed):
        if collapsed:
            self._collapsed.add(key)
        else:
            self._collapsed.discard(key)
        self._apply_collapse()

    def _apply_collapse(self):
        hidden_below = None  # depth of the collapsed header hiding what follows
        for widget, depth, key in self._group_rows:
            if depth is not None and hidden_below is not None and depth <= hidden_below:
                hidden_below = None
            (widget.get_parent() or widget).set_visible(hidden_below is None)
            if depth is not None and hidden_below is None and key in self._collapsed:
                hidden_below = depth

    def _on_group_clicked(self, button):
        self._group_mode = next_mode(self._group_mode, self._groupings)
        button.set_label(LABELS.get(self._group_mode, self._group_mode))
        self._fill()
```

`_build_row` gains a `tag` parameter that joins the subtitle:

```python
    def _build_row(self, item, tag=None):
        ...
        sub_text = " · ".join(x for x in (item.get("artist"), item.get("album"),
                                          format_date(item.get("date")), tag) if x)
```

Note: a `RibbonBanner` toggles itself (chevron) and then calls `on_toggle(collapsed)`. The test calls `_toggle_group` directly, so the banner's chevron isn't involved there. In the real UI the banner and `_collapsed` agree because the banner is built from `_collapsed` on every `_fill`.

**Step 4: Run the tests**

Run: `python3 -m unittest tests.test_source_pane -v` → PASS (all, old and new)

**Step 5: Commit**

```bash
git add sqlch_gui/ui/source_pane.py tests/test_source_pane.py
git commit -m "sqlch-gui: sort pill groups show lists by source, genre or A-Z"
```

---

### Task 11: Spotify drops SHORTCUTS

**Files:**
- Modify: `sqlch/sources/spotify.py`
- Test: `tests/test_source_spotify.py`

**Step 1: Update the tests**

In `tests/test_source_spotify.py`:
- Delete `test_root_shortcuts_parse_uris_and_urls` (around line 80).
- Change `test_sections` to expect `["playlists", "artists"]`.
- Replace `test_shortcuts_section_is_the_old_root` with:

```python
    def test_root_is_playlists(self):
        with mock.patch.object(spotify, "_my_playlists", return_value=[]), \
                mock.patch.object(spotify.spotify_auth, "logged_in", return_value=True):
            self.assertEqual(spotify.browse(None), [])
            self.assertEqual(spotify.browse("section:playlists"), [])

    def test_hint_has_no_shortcuts(self):
        self.assertNotIn("shortcuts", spotify.HINT)
```

**Step 2: Run them and check they fail**

Run: `python3 -m unittest tests.test_source_spotify -v`
Expected: `test_sections` and `test_hint_has_no_shortcuts` FAIL.

**Step 3: Implement**

In `sqlch/sources/spotify.py`:
- `HINT`: delete the final `'Browse shortcuts: ...'` string piece. Make sure the preceding piece still ends cleanly, e.g. `"Run \`sqlch spotify-login\` to see your playlists and followed artists."`
- Delete `_shortcuts()` entirely.
- Delete `_REF`. `grep -n "_REF" sqlch/sources/spotify.py` should then show nothing. If anything else uses it, keep it.
- `sections()`:

```python
def sections() -> list[dict]:
    return [{"id": "playlists", "title": "PLAYLISTS"},
            {"id": "artists", "title": "ARTISTS"}]
```

- `browse`: the first two branches become

```python
    if not path or path == "section:playlists":
        _need_login()
        return _compact(_folder("playlist", p) for p in _my_playlists())
```

(Delete the old `section:shortcuts` branch and the now-duplicate `section:playlists` branch.)
- If `source_config` or `re` are now unused, remove their imports (`grep -n "source_config\|re\." sqlch/sources/spotify.py`).

**Step 4: Run the tests**

Run: `python3 -m unittest tests.test_source_spotify -v` → PASS

**Step 5: Commit**

```bash
git add sqlch/sources/spotify.py tests/test_source_spotify.py
git commit -m "sqlch: spotify pane drops the SHORTCUTS section"
```

---

### Task 12: Full suite, live check, docs

**Step 1: Full suite**

Run: `python3 -m unittest -q`
Expected: only the 3 baseline `test_header` errors.

**Step 2: Live search smoke test (network)**

```bash
python3 -c "
from sqlch.sources import podcasts
items = podcasts.search('linux unplugged')
print(len(items), podcasts.last_warning())
for i in items[:5]: print(i['title'], i['genre'], i['providers'])
eps = podcasts.browse(items[0]['path'])
print(len(eps), eps[0]['title'], eps[0]['duration'], eps[0]['url'][:60])
print(podcasts.resolve(eps[0]))
"
```

Expected: several shows (Apple only unless a Podcast Index key exists), episodes newest first, and a `Target` with an https audio URL and a cached art path.

**Step 3: Run the app**

Use the `run` skill (or launch `python3 -m sqlch_gui` with the daemon running). Open the Sources popover → Podcasts. Check: search groups under SOURCE, the pill cycles GENRE → A–Z, headers collapse, a show opens to episodes with Oldest first, an episode plays and Now Playing shows the cover, Follow puts the show in FOLLOWING and Unfollow removes it, and Spotify's pills read PLAYLISTS · ARTISTS · FAVORITES.

**Step 4: README**

Add a short Podcasts entry next to the other sources in `README.md`: what it searches, the optional `/run/secrets/podcastindex_env` with `PODCASTINDEX_API_KEY` / `PODCASTINDEX_API_SECRET` (free key at api.podcastindex.org), and the `sources.podcasts.env_file` override.

**Step 5: Commit**

```bash
git add README.md
git commit -m "docs: podcasts source in the README"
```

Not in this plan: the sops secret for Podcast Index in `~/nixos` (`roles/sops-shared.nix` holds `spotify_env` as the pattern). Ask before touching it.
