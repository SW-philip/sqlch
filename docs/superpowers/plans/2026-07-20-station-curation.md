# Station Curation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the algo-killer curation engine — new stations go on a bounded probation where the daemon passively samples what they actually broadcast, and a drift-consistency gate + discovery-yield score decides whether they graduate to a curated presets list, entirely independent of your own listening volume.

**Architecture:** A new `sqlch/core/curation_db.py` owns a SQLite database (`curation.db`, stdlib `sqlite3`, no new dependency) with three tables — `heard_tracks` (your personal corpus, written continuously by the daemon's existing metadata watcher), `candidate_probes` (raw polled observations for stations on probation), and `stations_curation` (one row of state per station). A new `sqlch/core/curation.py` holds the pure gate/score math and orchestration on top of that DB. `icyprobe.py` moves from `sqlch_gui` to `sqlch/core` so the daemon can own the probation poller independent of whether the GUI is running. The daemon gets a new background thread (same idiom as the existing `mpris` thread) that polls every candidate station every ~3 minutes and evaluates due probations once a day. CLI surfaces the pipeline: `sqlch add` reports probation status, `sqlch presets` lists graduated stations, `sqlch info` shows a curation block.

**Tech Stack:** Python 3.11+ stdlib (`sqlite3`, `threading`, `time`), existing `icyprobe` raw-socket ICY prober, stdlib `unittest` for tests (matches `tests/test_recorder.py`, the only existing test file).

**Spec:** `docs/superpowers/specs/2026-07-20-station-curation-design.md`

---

## Scope note

This plan builds the core engine end-to-end through the CLI only (`sqlch add`, `sqlch presets`, `sqlch info`). The spec's TUI status indicator and GUI status indicator / tracklist-click engagement signal are explicitly deferred to a follow-up plan — they're presentation on top of data this plan already produces, not required to validate the pipeline, and pulling them in here would mean testing GTK widgets that don't otherwise need touching. Once this lands and there's real probation data to look at, a second plan can add the TUI/GUI surfacing without touching anything built here.

## File structure

| File | Change | Responsibility |
|---|---|---|
| `sqlch/core/icyprobe.py` | Create (moved) | Raw ICY StreamTitle prober, unchanged logic |
| `sqlch_gui/icyprobe.py` | Modify | Re-export from `sqlch.core.icyprobe` |
| `sqlch/core/curation_db.py` | Create | SQLite schema + connection + CRUD for all three tables |
| `sqlch/core/curation.py` | Create | Admission filter, gate/score math, probation orchestration, poller loop |
| `sqlch/core/player.py` | Modify | `_watch_metadata` also records heard tracks; thread through `station_id` |
| `sqlch/core/daemon.py` | Modify | Start the curation poller thread; new `presets`/`curation_info` commands |
| `sqlch/cli/main.py` | Modify | `add_cmd` reports probation; new `presets_cmd`; `info_cmd` gains curation block |
| `tests/test_icy_probe_move.py` | Create | Confirms the moved module + GUI re-export both work |
| `tests/test_curation_db.py` | Create | Schema + CRUD unit tests (tempfile-backed DB) |
| `tests/test_curation.py` | Create | Gate/score math + orchestration unit tests (fakes, no real network/DB file) |

Notes for the engineer:

- **Threading/connection idiom:** SQLite connections are not safe to share across threads. Every `curation_db.py` function takes an explicit `conn: sqlite3.Connection` parameter — callers own the connection lifecycle. The daemon's poller thread opens one connection per poll cycle; CLI commands and the player's watcher thread each open a short-lived connection per call via `curation_db.connect()`. Never store a connection in a module global.
- **Time is always injectable.** Every function that reasons about "now" (`start_probation`, `poll_once`, `evaluate_station`, `evaluate_due_candidates`) takes `now: int | None = None` and defaults to `int(time.time())`. This is what makes probation-window logic testable without sleeping for 14 days.
- **Network is always injectable.** Every function that would otherwise call `icyprobe.fetch_stream_title` takes a `prober` parameter defaulting to the real function, so tests pass a fake.
- **Run tests from the repo root:** `python -m unittest discover -s tests -v`.

---

### Task 1: Move icyprobe to core

**Files:**
- Create: `sqlch/core/icyprobe.py`
- Modify: `sqlch_gui/icyprobe.py`
- Modify: `sqlch_gui/ui/station_list.py:309` (import path only, if needed)
- Test: `tests/test_icy_probe_move.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest


class TestIcyProbeMove(unittest.TestCase):
    def test_core_module_has_fetch_stream_title(self):
        from sqlch.core.icyprobe import fetch_stream_title
        self.assertTrue(callable(fetch_stream_title))

    def test_gui_module_reexports_same_function(self):
        from sqlch.core.icyprobe import fetch_stream_title as core_fn
        from sqlch_gui.icyprobe import fetch_stream_title as gui_fn
        self.assertIs(core_fn, gui_fn)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_icy_probe_move -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sqlch.core.icyprobe'`

- [ ] **Step 3: Move the file and re-export**

Copy the full current contents of `sqlch_gui/icyprobe.py` verbatim into a new `sqlch/core/icyprobe.py` (same module docstring, same `_MAX_METAINT`/`_TITLE_RE`/etc. constants, same `_normalize`, `_recv_until`, `fetch_stream_title` — no logic changes).

Replace the entire contents of `sqlch_gui/icyprobe.py` with:

```python
"""Re-export of the ICY prober, which now lives in sqlch.core so the
daemon can run it independent of whether the GUI is running."""

from sqlch.core.icyprobe import fetch_stream_title

__all__ = ["fetch_stream_title"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_icy_probe_move -v`
Expected: PASS

- [ ] **Step 5: Verify the existing GUI call site still works**

`sqlch_gui/ui/station_list.py:309` calls `icyprobe.fetch_stream_title(st["url"])` via `from .. import ... icyprobe ...` — this still resolves through the re-export, no change needed there. Confirm with:

Run: `python -c "from sqlch_gui import icyprobe; print(icyprobe.fetch_stream_title)"`
Expected: prints the function object, no error

- [ ] **Step 6: Commit**

```bash
git add sqlch/core/icyprobe.py sqlch_gui/icyprobe.py tests/test_icy_probe_move.py
git commit -m "refactor: move icyprobe to sqlch.core, re-export from sqlch_gui"
```

---

### Task 2: curation_db schema and connection

**Files:**
- Create: `sqlch/core/curation_db.py`
- Test: `tests/test_curation_db.py`

- [ ] **Step 1: Write the failing test**

```python
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sqlch.core import curation_db


class TestConnect(unittest.TestCase):
    def test_connect_creates_all_three_tables(self):
        with tempfile.TemporaryDirectory() as d:
            conn = curation_db.connect(Path(d) / "test.db")
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertEqual(
                tables,
                {"heard_tracks", "candidate_probes", "stations_curation"},
            )
            conn.close()

    def test_connect_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "test.db"
            curation_db.connect(path).close()
            conn = curation_db.connect(path)  # must not raise on existing schema
            conn.execute("SELECT 1")
            conn.close()

    def test_db_path_defaults_under_data_dir(self):
        from sqlch.core.paths import data_dir
        self.assertEqual(curation_db.db_path(), data_dir() / "curation.db")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_curation_db -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sqlch.core.curation_db'`

- [ ] **Step 3: Write the implementation**

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlch.core.paths import data_dir

_SCHEMA = """
CREATE TABLE IF NOT EXISTS heard_tracks (
    station_id TEXT NOT NULL,
    artist TEXT,
    title TEXT,
    first_heard_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS candidate_probes (
    station_id TEXT NOT NULL,
    artist TEXT,
    title TEXT,
    observed_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS stations_curation (
    station_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    probation_started_at INTEGER NOT NULL,
    probation_ends_at INTEGER NOT NULL,
    score REAL,
    gate_passed INTEGER
);
"""


def db_path() -> Path:
    return data_dir() / "curation.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or db_path()))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_curation_db -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add sqlch/core/curation_db.py tests/test_curation_db.py
git commit -m "feat: add curation.db schema and connection helper"
```

---

### Task 3: heard_tracks CRUD

**Files:**
- Modify: `sqlch/core/curation_db.py`
- Modify: `tests/test_curation_db.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_curation_db.py`:

```python
class TestHeardTracks(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = curation_db.connect(Path(self._tmp.name) / "test.db")

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_record_and_has_heard(self):
        self.assertFalse(curation_db.has_heard(self.conn, "Pearl Jam", "Even Flow"))
        curation_db.record_heard_track(
            self.conn, "wmmr-mmr-rocks", "Pearl Jam", "Even Flow", when=1000
        )
        self.assertTrue(curation_db.has_heard(self.conn, "Pearl Jam", "Even Flow"))

    def test_has_heard_is_case_sensitive_exact_match(self):
        curation_db.record_heard_track(
            self.conn, "wmmr-mmr-rocks", "Pearl Jam", "Even Flow", when=1000
        )
        self.assertFalse(curation_db.has_heard(self.conn, "pearl jam", "even flow"))

    def test_heard_pairs_returns_set_of_tuples(self):
        curation_db.record_heard_track(self.conn, "s1", "A", "X", when=1)
        curation_db.record_heard_track(self.conn, "s1", "B", "Y", when=2)
        self.assertEqual(
            curation_db.heard_pairs(self.conn), {("A", "X"), ("B", "Y")}
        )

    def test_heard_pairs_skips_rows_missing_artist_or_title(self):
        curation_db.record_heard_track(self.conn, "s1", None, "X", when=1)
        curation_db.record_heard_track(self.conn, "s1", "B", None, when=2)
        self.assertEqual(curation_db.heard_pairs(self.conn), set())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_curation_db -v`
Expected: FAIL — `AttributeError: module 'sqlch.core.curation_db' has no attribute 'record_heard_track'`

- [ ] **Step 3: Write the implementation**

Append to `sqlch/core/curation_db.py`:

```python
import time


def record_heard_track(
    conn: sqlite3.Connection,
    station_id: str,
    artist: str | None,
    title: str | None,
    *,
    when: int | None = None,
) -> None:
    conn.execute(
        "INSERT INTO heard_tracks (station_id, artist, title, first_heard_at) "
        "VALUES (?, ?, ?, ?)",
        (station_id, artist, title, when if when is not None else int(time.time())),
    )
    conn.commit()


def has_heard(conn: sqlite3.Connection, artist: str, title: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM heard_tracks WHERE artist = ? AND title = ? LIMIT 1",
        (artist, title),
    ).fetchone()
    return row is not None


def heard_pairs(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    rows = conn.execute(
        "SELECT artist, title FROM heard_tracks "
        "WHERE artist IS NOT NULL AND title IS NOT NULL"
    ).fetchall()
    return {(r["artist"], r["title"]) for r in rows}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_curation_db -v`
Expected: PASS (7 tests total)

- [ ] **Step 5: Commit**

```bash
git add sqlch/core/curation_db.py tests/test_curation_db.py
git commit -m "feat: add heard_tracks CRUD to curation_db"
```

---

### Task 4: candidate_probes CRUD with dedup

**Files:**
- Modify: `sqlch/core/curation_db.py`
- Modify: `tests/test_curation_db.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_curation_db.py`:

```python
class TestCandidateProbes(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = curation_db.connect(Path(self._tmp.name) / "test.db")

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_first_probe_is_recorded(self):
        curation_db.record_candidate_probe(self.conn, "s1", "A", "X", when=1000)
        probes = curation_db.get_probes(self.conn, "s1")
        self.assertEqual(len(probes), 1)
        self.assertEqual(probes[0]["artist"], "A")
        self.assertEqual(probes[0]["title"], "X")
        self.assertEqual(probes[0]["observed_at"], 1000)

    def test_repeat_of_same_title_is_not_recorded_again(self):
        curation_db.record_candidate_probe(self.conn, "s1", "A", "X", when=1000)
        curation_db.record_candidate_probe(self.conn, "s1", "A", "X", when=1180)
        self.assertEqual(len(curation_db.get_probes(self.conn, "s1")), 1)

    def test_title_change_is_recorded_as_new_row(self):
        curation_db.record_candidate_probe(self.conn, "s1", "A", "X", when=1000)
        curation_db.record_candidate_probe(self.conn, "s1", "B", "Y", when=1180)
        self.assertEqual(len(curation_db.get_probes(self.conn, "s1")), 2)

    def test_probes_are_scoped_per_station(self):
        curation_db.record_candidate_probe(self.conn, "s1", "A", "X", when=1000)
        curation_db.record_candidate_probe(self.conn, "s2", "A", "X", when=1000)
        self.assertEqual(len(curation_db.get_probes(self.conn, "s1")), 1)
        self.assertEqual(len(curation_db.get_probes(self.conn, "s2")), 1)

    def test_get_probes_returns_in_chronological_order(self):
        curation_db.record_candidate_probe(self.conn, "s1", "A", "X", when=2000)
        curation_db.record_candidate_probe(self.conn, "s1", "B", "Y", when=1000)
        probes = curation_db.get_probes(self.conn, "s1")
        self.assertEqual([p["observed_at"] for p in probes], [1000, 2000])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_curation_db -v`
Expected: FAIL — `AttributeError: ... no attribute 'record_candidate_probe'`

- [ ] **Step 3: Write the implementation**

Append to `sqlch/core/curation_db.py`:

```python
def record_candidate_probe(
    conn: sqlite3.Connection,
    station_id: str,
    artist: str | None,
    title: str | None,
    *,
    when: int | None = None,
) -> None:
    last = conn.execute(
        "SELECT artist, title FROM candidate_probes "
        "WHERE station_id = ? ORDER BY observed_at DESC LIMIT 1",
        (station_id,),
    ).fetchone()
    if last is not None and last["artist"] == artist and last["title"] == title:
        return
    conn.execute(
        "INSERT INTO candidate_probes (station_id, artist, title, observed_at) "
        "VALUES (?, ?, ?, ?)",
        (station_id, artist, title, when if when is not None else int(time.time())),
    )
    conn.commit()


def get_probes(conn: sqlite3.Connection, station_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT artist, title, observed_at FROM candidate_probes "
        "WHERE station_id = ? ORDER BY observed_at ASC",
        (station_id,),
    ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_curation_db -v`
Expected: PASS (12 tests total)

- [ ] **Step 5: Commit**

```bash
git add sqlch/core/curation_db.py tests/test_curation_db.py
git commit -m "feat: add candidate_probes CRUD with title-change dedup"
```

---

### Task 5: stations_curation state CRUD

**Files:**
- Modify: `sqlch/core/curation_db.py`
- Modify: `tests/test_curation_db.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_curation_db.py`:

```python
class TestStationsCuration(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = curation_db.connect(Path(self._tmp.name) / "test.db")

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_get_curation_state_returns_none_for_unknown_station(self):
        self.assertIsNone(curation_db.get_curation_state(self.conn, "nope"))

    def test_upsert_then_get_roundtrips(self):
        curation_db.upsert_curation_state(
            self.conn, "s1",
            status="candidate", probation_started_at=1000,
            probation_ends_at=2000, score=None, gate_passed=None,
        )
        state = curation_db.get_curation_state(self.conn, "s1")
        self.assertEqual(state["status"], "candidate")
        self.assertEqual(state["probation_started_at"], 1000)
        self.assertEqual(state["probation_ends_at"], 2000)
        self.assertIsNone(state["score"])
        self.assertIsNone(state["gate_passed"])

    def test_upsert_updates_existing_row_in_place(self):
        curation_db.upsert_curation_state(
            self.conn, "s1",
            status="candidate", probation_started_at=1000,
            probation_ends_at=2000, score=None, gate_passed=None,
        )
        curation_db.upsert_curation_state(self.conn, "s1", status="preset", score=0.6)
        state = curation_db.get_curation_state(self.conn, "s1")
        self.assertEqual(state["status"], "preset")
        self.assertEqual(state["score"], 0.6)
        self.assertEqual(state["probation_started_at"], 1000)  # untouched field kept

    def test_candidate_station_ids_only_returns_candidates(self):
        curation_db.upsert_curation_state(
            self.conn, "s1", status="candidate",
            probation_started_at=1000, probation_ends_at=2000,
            score=None, gate_passed=None,
        )
        curation_db.upsert_curation_state(
            self.conn, "s2", status="preset",
            probation_started_at=1000, probation_ends_at=2000,
            score=0.5, gate_passed=1,
        )
        self.assertEqual(curation_db.candidate_station_ids(self.conn), ["s1"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_curation_db -v`
Expected: FAIL — `AttributeError: ... no attribute 'get_curation_state'`

- [ ] **Step 3: Write the implementation**

Append to `sqlch/core/curation_db.py`:

```python
_STATE_FIELDS = (
    "status", "probation_started_at", "probation_ends_at", "score", "gate_passed",
)


def get_curation_state(conn: sqlite3.Connection, station_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM stations_curation WHERE station_id = ?", (station_id,)
    ).fetchone()
    return dict(row) if row is not None else None


def upsert_curation_state(conn: sqlite3.Connection, station_id: str, **fields) -> None:
    unknown = set(fields) - set(_STATE_FIELDS)
    if unknown:
        raise ValueError(f"unknown curation state field(s): {sorted(unknown)}")

    existing = get_curation_state(conn, station_id)
    if existing is None:
        missing = set(_STATE_FIELDS) - {"score", "gate_passed"} - set(fields)
        if missing:
            raise ValueError(f"new curation row missing required field(s): {sorted(missing)}")
        row = {f: fields.get(f) for f in _STATE_FIELDS}
        conn.execute(
            "INSERT INTO stations_curation "
            "(station_id, status, probation_started_at, probation_ends_at, score, gate_passed) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (station_id, row["status"], row["probation_started_at"],
             row["probation_ends_at"], row["score"], row["gate_passed"]),
        )
    else:
        merged = {**existing, **fields}
        conn.execute(
            "UPDATE stations_curation SET status = ?, probation_started_at = ?, "
            "probation_ends_at = ?, score = ?, gate_passed = ? WHERE station_id = ?",
            (merged["status"], merged["probation_started_at"], merged["probation_ends_at"],
             merged["score"], merged["gate_passed"], station_id),
        )
    conn.commit()


def candidate_station_ids(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT station_id FROM stations_curation WHERE status = 'candidate'"
    ).fetchall()
    return [r["station_id"] for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_curation_db -v`
Expected: PASS (16 tests total)

- [ ] **Step 5: Commit**

```bash
git add sqlch/core/curation_db.py tests/test_curation_db.py
git commit -m "feat: add stations_curation state CRUD"
```

---

### Task 6: Gate and score pure functions

**Files:**
- Create: `sqlch/core/curation.py`
- Create: `tests/test_curation.py`

- [ ] **Step 1: Write the failing tests**

```python
import unittest

from sqlch.core import curation

_DAY = 86400


def _probe(artist, title, day, hour=12):
    return {"artist": artist, "title": title, "observed_at": day * _DAY + hour * 3600}


class TestUniqueArtistRatio(unittest.TestCase):
    def test_empty_probes_is_zero(self):
        self.assertEqual(curation.unique_artist_ratio([]), 0.0)

    def test_all_same_artist_is_low_ratio(self):
        probes = [_probe("A", f"T{i}", 0) for i in range(10)]
        self.assertEqual(curation.unique_artist_ratio(probes), 0.1)

    def test_all_different_artists_is_one(self):
        probes = [_probe(f"A{i}", f"T{i}", 0) for i in range(5)]
        self.assertEqual(curation.unique_artist_ratio(probes), 1.0)

    def test_probes_missing_artist_are_excluded_from_denominator(self):
        probes = [_probe("A", "T1", 0), _probe(None, "T2", 0)]
        self.assertEqual(curation.unique_artist_ratio(probes), 1.0)


class TestDriftConsistency(unittest.TestCase):
    def test_less_than_two_days_of_data_is_zero(self):
        probes = [_probe("A", "T1", 0), _probe("B", "T2", 0)]
        self.assertEqual(curation.drift_consistency(probes), 0.0)

    def test_identical_daily_rotation_is_high(self):
        rotation = ["A", "B", "C"]
        probes = [
            _probe(artist, f"{artist}-song", day)
            for day in range(5)
            for artist in rotation
        ]
        self.assertEqual(curation.drift_consistency(probes), 1.0)

    def test_completely_disjoint_daily_artists_is_zero(self):
        probes = [_probe(f"day0-{i}", "T", 0) for i in range(3)] + \
                 [_probe(f"day1-{i}", "T", 1) for i in range(3)]
        self.assertEqual(curation.drift_consistency(probes), 0.0)


class TestPassesGate(unittest.TestCase):
    def test_low_diversity_fails_regardless_of_drift(self):
        probes = [_probe("A", f"T{i}", day) for day in range(5) for i in range(3)]
        self.assertFalse(curation.passes_gate(probes))

    def test_high_diversity_and_repeating_rotation_passes(self):
        rotation = [f"Artist{i}" for i in range(10)]
        probes = [
            _probe(artist, f"{artist}-song", day)
            for day in range(5)
            for artist in rotation
        ]
        self.assertTrue(curation.passes_gate(probes))

    def test_high_diversity_but_random_no_repeating_pattern_fails(self):
        # Every day's 20 artists are entirely disjoint from every other day's -
        # high diversity, but nothing recurs, so drift_consistency stays at 0.
        probes = [
            _probe(f"day{day}-artist{i}", "T", day)
            for day in range(5)
            for i in range(20)
        ]
        self.assertFalse(curation.passes_gate(probes))


class TestDiscoveryYield(unittest.TestCase):
    def test_no_scoreable_probes_is_zero(self):
        self.assertEqual(curation.discovery_yield([], set()), 0.0)

    def test_all_new_is_one(self):
        probes = [_probe("A", "X", 0), _probe("B", "Y", 0)]
        self.assertEqual(curation.discovery_yield(probes, set()), 1.0)

    def test_all_already_heard_is_zero(self):
        probes = [_probe("A", "X", 0), _probe("B", "Y", 0)]
        heard = {("A", "X"), ("B", "Y")}
        self.assertEqual(curation.discovery_yield(probes, heard), 0.0)

    def test_half_new_is_half(self):
        probes = [_probe("A", "X", 0), _probe("B", "Y", 0)]
        heard = {("A", "X")}
        self.assertEqual(curation.discovery_yield(probes, heard), 0.5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_curation -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sqlch.core.curation'`

- [ ] **Step 3: Write the implementation**

```python
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone

# Provisional defaults — expected to need tuning against real probation data,
# not load-bearing design decisions. See docs/superpowers/specs/2026-07-20-station-curation-design.md.
MIN_BITRATE_KBPS = 96
PROBATION_DAYS = 14
POLL_INTERVAL_SECONDS = 180
MIN_ARTIST_DIVERSITY = 0.5
MIN_DRIFT_CONSISTENCY = 0.2
MIN_DISCOVERY_YIELD = 0.3

PROBATION_SECONDS = PROBATION_DAYS * 86400


def unique_artist_ratio(probes: list[dict]) -> float:
    artists = [p["artist"] for p in probes if p.get("artist")]
    if not artists:
        return 0.0
    return len(set(artists)) / len(artists)


def passes_diversity_check(probes: list[dict], *, min_ratio: float = MIN_ARTIST_DIVERSITY) -> bool:
    return unique_artist_ratio(probes) >= min_ratio


def _daily_artist_sets(probes: list[dict]) -> list[set[str]]:
    days: dict = defaultdict(set)
    for p in probes:
        if not p.get("artist"):
            continue
        day = datetime.fromtimestamp(p["observed_at"], tz=timezone.utc).date()
        days[day].add(p["artist"])
    return [days[d] for d in sorted(days)]


def drift_consistency(probes: list[dict]) -> float:
    """Average Jaccard similarity between consecutive days' artist sets.

    A station shuffling from an unbounded pool looks flat/random day to day;
    a station with a real format or DJ shows a repeating rhythm. That
    recurring shape — not sameness — is the signal this measures.
    """
    daily = _daily_artist_sets(probes)
    if len(daily) < 2:
        return 0.0
    scores = []
    for a, b in zip(daily, daily[1:]):
        union = a | b
        if not union:
            continue
        scores.append(len(a & b) / len(union))
    return sum(scores) / len(scores) if scores else 0.0


def _most_recent_day_probes(probes: list[dict]) -> list[dict]:
    """Diversity is a same-day loop check (a 40-song rotation repeats within
    a day), so it's scored on the latest day alone - not cumulatively across
    the whole probation window, where even a healthy repeating format would
    look artificially low simply because the same artists keep recurring."""
    if not probes:
        return []
    days = [datetime.fromtimestamp(p["observed_at"], tz=timezone.utc).date() for p in probes]
    latest = max(days)
    return [p for p, d in zip(probes, days) if d == latest]


def passes_gate(
    probes: list[dict],
    *,
    min_ratio: float = MIN_ARTIST_DIVERSITY,
    min_drift: float = MIN_DRIFT_CONSISTENCY,
) -> bool:
    return (
        passes_diversity_check(_most_recent_day_probes(probes), min_ratio=min_ratio)
        and drift_consistency(probes) >= min_drift
    )


def discovery_yield(probes: list[dict], heard: set[tuple[str, str]]) -> float:
    scored = [p for p in probes if p.get("artist") and p.get("title")]
    if not scored:
        return 0.0
    new = sum(1 for p in scored if (p["artist"], p["title"]) not in heard)
    return new / len(scored)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_curation -v`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add sqlch/core/curation.py tests/test_curation.py
git commit -m "feat: add drift-consistency gate and discovery-yield score"
```

---

### Task 7: Admission filter

**Files:**
- Modify: `sqlch/core/curation.py`
- Modify: `tests/test_curation.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_curation.py`:

```python
class TestAdmissionCheck(unittest.TestCase):
    def _station(self, **overrides):
        st = {
            "id": "s1",
            "url": "http://example.com/stream",
            "tags": ["rock"],
            "stream": {"bitrate": 128},
        }
        st.update(overrides)
        return st

    def test_passes_with_good_bitrate_tags_and_live_probe(self):
        ok, reason = curation.admission_check(
            self._station(), prober=lambda url, timeout=4.0: "Artist - Title"
        )
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_fails_below_bitrate_floor(self):
        ok, reason = curation.admission_check(
            self._station(stream={"bitrate": 32}),
            prober=lambda url, timeout=4.0: "Artist - Title",
        )
        self.assertFalse(ok)
        self.assertIn("bitrate", reason)

    def test_unknown_bitrate_does_not_fail_the_floor_check(self):
        ok, reason = curation.admission_check(
            self._station(stream={"bitrate": None}),
            prober=lambda url, timeout=4.0: "Artist - Title",
        )
        self.assertTrue(ok)

    def test_fails_with_no_tags(self):
        ok, reason = curation.admission_check(
            self._station(tags=[]),
            prober=lambda url, timeout=4.0: "Artist - Title",
        )
        self.assertFalse(ok)
        self.assertIn("tag", reason)

    def test_fails_when_probe_returns_nothing(self):
        ok, reason = curation.admission_check(
            self._station(), prober=lambda url, timeout=4.0: None
        )
        self.assertFalse(ok)
        self.assertIn("probe", reason)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_curation -v`
Expected: FAIL — `AttributeError: module 'sqlch.core.curation' has no attribute 'admission_check'`

- [ ] **Step 3: Write the implementation**

Append to `sqlch/core/curation.py`:

```python
from sqlch.core import icyprobe


def admission_check(
    station: dict,
    *,
    prober=icyprobe.fetch_stream_title,
) -> tuple[bool, str | None]:
    bitrate = (station.get("stream") or {}).get("bitrate")
    if bitrate is not None and bitrate < MIN_BITRATE_KBPS:
        return False, f"bitrate {bitrate}kbps below {MIN_BITRATE_KBPS}kbps floor"

    if not station.get("tags"):
        return False, "no tags"

    title = prober(station["url"], timeout=4.0)
    if not title:
        return False, "station did not respond to a stream-title probe"

    return True, None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_curation -v`
Expected: PASS (19 tests)

- [ ] **Step 5: Commit**

```bash
git add sqlch/core/curation.py tests/test_curation.py
git commit -m "feat: add station admission filter"
```

---

### Task 8: Probation lifecycle (start, poll, evaluate)

**Files:**
- Modify: `sqlch/core/curation.py`
- Modify: `tests/test_curation.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_curation.py`:

```python
import tempfile
from pathlib import Path

from sqlch.core import curation_db


class TestStartProbation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = curation_db.connect(Path(self._tmp.name) / "test.db")

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_start_probation_creates_candidate_row(self):
        curation.start_probation(self.conn, "s1", now=1000)
        state = curation_db.get_curation_state(self.conn, "s1")
        self.assertEqual(state["status"], "candidate")
        self.assertEqual(state["probation_started_at"], 1000)
        self.assertEqual(state["probation_ends_at"], 1000 + curation.PROBATION_SECONDS)


class TestPollOnce(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = curation_db.connect(Path(self._tmp.name) / "test.db")
        curation.start_probation(self.conn, "s1", now=1000)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_poll_records_a_probe_for_each_candidate_url(self):
        curation.poll_once(
            self.conn,
            station_urls=[("s1", "http://example.com/s1")],
            prober=lambda url, timeout=4.0: "Artist - Title",
            now=1180,
        )
        probes = curation_db.get_probes(self.conn, "s1")
        self.assertEqual(len(probes), 1)
        self.assertEqual(probes[0], {"artist": "Artist", "title": "Title", "observed_at": 1180})

    def test_poll_skips_stations_the_probe_cant_reach(self):
        curation.poll_once(
            self.conn,
            station_urls=[("s1", "http://example.com/s1")],
            prober=lambda url, timeout=4.0: None,
            now=1180,
        )
        self.assertEqual(curation_db.get_probes(self.conn, "s1"), [])


class TestEvaluateStation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = curation_db.connect(Path(self._tmp.name) / "test.db")

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def _seed_passing_probes(self, station_id="s1", start_day=0, num_days=5):
        rotation = [f"Artist{i}" for i in range(10)]
        for day in range(start_day, start_day + num_days):
            for artist in rotation:
                curation_db.record_candidate_probe(
                    self.conn, station_id, artist, f"{artist}-song",
                    when=day * 86400 + 3600,
                )

    def test_evaluation_before_probation_ends_leaves_station_a_candidate(self):
        curation.start_probation(self.conn, "s1", now=1000)
        result = curation.evaluate_station(self.conn, "s1", now=1000 + 10)
        self.assertEqual(result["status"], "candidate")

    def test_failing_gate_is_rejected(self):
        curation.start_probation(self.conn, "s1", now=0)
        curation_db.record_candidate_probe(self.conn, "s1", "OnlyArtist", "T1", when=100)
        result = curation.evaluate_station(
            self.conn, "s1", now=curation.PROBATION_SECONDS + 1
        )
        self.assertEqual(result["status"], "rejected")
        self.assertFalse(result["gate_passed"])

    def test_passing_gate_and_high_score_is_preset(self):
        curation.start_probation(self.conn, "s1", now=0)
        self._seed_passing_probes()
        result = curation.evaluate_station(
            self.conn, "s1", now=curation.PROBATION_SECONDS + 1
        )
        self.assertEqual(result["status"], "preset")
        self.assertEqual(result["score"], 1.0)  # nothing in heard_tracks yet

    def test_passing_gate_but_low_score_extends_probation_once(self):
        curation.start_probation(self.conn, "s1", now=0)
        self._seed_passing_probes()
        for artist in [f"Artist{i}" for i in range(10)]:
            curation_db.record_heard_track(self.conn, "other", artist, f"{artist}-song", when=1)

        result = curation.evaluate_station(
            self.conn, "s1", now=curation.PROBATION_SECONDS + 1
        )
        self.assertEqual(result["status"], "candidate")
        self.assertTrue(result.get("extended"))
        state = curation_db.get_curation_state(self.conn, "s1")
        self.assertEqual(state["probation_ends_at"], 2 * curation.PROBATION_SECONDS)

    def test_second_low_score_after_extension_is_finally_rejected(self):
        curation.start_probation(self.conn, "s1", now=0)
        self._seed_passing_probes()
        for artist in [f"Artist{i}" for i in range(10)]:
            curation_db.record_heard_track(self.conn, "other", artist, f"{artist}-song", when=1)
        curation.evaluate_station(self.conn, "s1", now=curation.PROBATION_SECONDS + 1)

        result = curation.evaluate_station(
            self.conn, "s1", now=2 * curation.PROBATION_SECONDS + 1
        )
        self.assertEqual(result["status"], "rejected")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_curation -v`
Expected: FAIL — `AttributeError: module 'sqlch.core.curation' has no attribute 'start_probation'`

- [ ] **Step 3: Write the implementation**

Append to `sqlch/core/curation.py`:

```python
from sqlch.core import curation_db
from sqlch.core.player import _parse_icy


def start_probation(conn, station_id: str, *, now: int | None = None) -> None:
    now = now if now is not None else int(time.time())
    curation_db.upsert_curation_state(
        conn, station_id,
        status="candidate",
        probation_started_at=now,
        probation_ends_at=now + PROBATION_SECONDS,
        score=None,
        gate_passed=None,
    )


def poll_once(
    conn,
    *,
    station_urls: list[tuple[str, str]],
    prober=icyprobe.fetch_stream_title,
    now: int | None = None,
) -> None:
    now = now if now is not None else int(time.time())
    for station_id, url in station_urls:
        raw_title = prober(url, timeout=4.0)
        if not raw_title:
            continue
        artist, track = _parse_icy(raw_title)
        if not track:
            continue
        curation_db.record_candidate_probe(conn, station_id, artist, track, when=now)


def evaluate_station(conn, station_id: str, *, now: int | None = None) -> dict:
    now = now if now is not None else int(time.time())
    state = curation_db.get_curation_state(conn, station_id)
    if state is None or state["status"] != "candidate":
        return {"status": state["status"] if state else None}

    if now < state["probation_ends_at"]:
        return {"status": "candidate"}

    probes = curation_db.get_probes(conn, station_id)
    if not passes_gate(probes):
        curation_db.upsert_curation_state(
            conn, station_id, status="rejected", gate_passed=False, score=None
        )
        return {"status": "rejected", "gate_passed": False, "score": None}

    heard = curation_db.heard_pairs(conn)
    score = discovery_yield(probes, heard)
    already_extended = (
        state["probation_ends_at"] - state["probation_started_at"] > PROBATION_SECONDS
    )

    if score >= MIN_DISCOVERY_YIELD:
        curation_db.upsert_curation_state(
            conn, station_id, status="preset", gate_passed=True, score=score
        )
        return {"status": "preset", "gate_passed": True, "score": score}

    if already_extended:
        curation_db.upsert_curation_state(
            conn, station_id, status="rejected", gate_passed=True, score=score
        )
        return {"status": "rejected", "gate_passed": True, "score": score}

    curation_db.upsert_curation_state(
        conn, station_id,
        status="candidate",
        gate_passed=True,
        score=score,
        probation_ends_at=state["probation_started_at"] + 2 * PROBATION_SECONDS,
    )
    return {"status": "candidate", "gate_passed": True, "score": score, "extended": True}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_curation -v`
Expected: PASS (27 tests)

- [ ] **Step 5: Commit**

```bash
git add sqlch/core/curation.py tests/test_curation.py
git commit -m "feat: add probation lifecycle - start, poll, evaluate"
```

---

### Task 9: Poller loop and evaluate-all-due orchestration

**Files:**
- Modify: `sqlch/core/curation.py`
- Modify: `tests/test_curation.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_curation.py`:

```python
class TestEvaluateDueCandidates(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = curation_db.connect(Path(self._tmp.name) / "test.db")

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_evaluates_every_candidate_once(self):
        curation.start_probation(self.conn, "s1", now=0)
        curation.start_probation(self.conn, "s2", now=0)
        curation_db.record_candidate_probe(self.conn, "s1", "OnlyOne", "T", when=10)
        curation_db.record_candidate_probe(self.conn, "s2", "OnlyOne", "T", when=10)

        curation.evaluate_due_candidates(self.conn, now=curation.PROBATION_SECONDS + 1)

        self.assertEqual(curation_db.get_curation_state(self.conn, "s1")["status"], "rejected")
        self.assertEqual(curation_db.get_curation_state(self.conn, "s2")["status"], "rejected")

    def test_ignores_candidates_still_within_probation(self):
        curation.start_probation(self.conn, "s1", now=0)
        curation.evaluate_due_candidates(self.conn, now=10)
        self.assertEqual(curation_db.get_curation_state(self.conn, "s1")["status"], "candidate")


class TestRunPollerLoop(unittest.TestCase):
    def test_poller_stops_promptly_when_stop_event_is_set(self):
        import threading
        import time as time_mod
        from unittest import mock

        stop_event = threading.Event()
        calls = []

        def fake_poll_once(conn, **kwargs):
            calls.append(1)

        with tempfile.TemporaryDirectory() as d:
            db_path = Path(d) / "test.db"
            with mock.patch.object(curation, "poll_once", fake_poll_once), \
                 mock.patch.object(curation, "evaluate_due_candidates", lambda conn, **k: None):
                t = threading.Thread(
                    target=curation.run_poller,
                    kwargs={"db_path": db_path, "interval": 0.01, "stop_event": stop_event},
                    daemon=True,
                )
                t.start()
                time_mod.sleep(0.05)
                stop_event.set()
                t.join(timeout=2)
                self.assertFalse(t.is_alive())
        self.assertGreater(len(calls), 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_curation -v`
Expected: FAIL — `AttributeError: module 'sqlch.core.curation' has no attribute 'evaluate_due_candidates'`

- [ ] **Step 3: Write the implementation**

Append to `sqlch/core/curation.py`:

```python
import threading


def evaluate_due_candidates(conn, *, now: int | None = None) -> None:
    now = now if now is not None else int(time.time())
    for station_id in curation_db.candidate_station_ids(conn):
        evaluate_station(conn, station_id, now=now)


def _candidate_station_urls(conn) -> list[tuple[str, str]]:
    from sqlch.core import library

    ids = set(curation_db.candidate_station_ids(conn))
    if not ids:
        return []
    return [(st["id"], st["url"]) for st in library.list_stations() if st["id"] in ids]


def run_poller(
    *,
    db_path=None,
    interval: float = POLL_INTERVAL_SECONDS,
    stop_event: threading.Event | None = None,
) -> None:
    stop_event = stop_event or threading.Event()
    while not stop_event.is_set():
        try:
            conn = curation_db.connect(db_path)
            try:
                poll_once(conn, station_urls=_candidate_station_urls(conn))
                evaluate_due_candidates(conn)
            finally:
                conn.close()
        except Exception:
            pass
        stop_event.wait(interval)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_curation -v`
Expected: PASS (30 tests)

- [ ] **Step 5: Commit**

```bash
git add sqlch/core/curation.py tests/test_curation.py
git commit -m "feat: add curation poller loop"
```

---

### Task 10: Wire the poller into the daemon

**Files:**
- Modify: `sqlch/core/daemon.py:115-119`

- [ ] **Step 1: Write the failing test**

There's no existing daemon-level test harness to extend safely (the daemon binds a real socket and loops forever), so this step is verified by direct inspection + a manual daemon run rather than a new automated test — consistent with how `run_daemon()` itself has no test coverage today.

Run: `grep -n "curation" sqlch/core/daemon.py`
Expected: no output (confirms the wiring doesn't exist yet)

- [ ] **Step 2: Add the poller thread**

In `sqlch/core/daemon.py`, modify `run_daemon()`:

```python
def run_daemon():
    sock = control_sock()
    # Start MPRIS daemon in background thread
    from sqlch.core import mpris_daemon
    threading.Thread(target=mpris_daemon.main, daemon=True, name="mpris").start()

    # Start the station curation poller in background thread
    from sqlch.core import curation
    threading.Thread(target=curation.run_poller, daemon=True, name="curation-poller").start()

    try:
```

(This inserts the new block directly after the existing `mpris` thread start, before the existing `try:` that unlinks the socket — no other lines in `run_daemon()` change.)

- [ ] **Step 3: Verify by running the daemon manually**

Run: `python -m sqlch.cli.main daemon` (or `sqlch daemon` if installed), then in another terminal:

Run: `python -c "
import socket, json
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect('/run/user/1000/sqlch/control.sock')  # adjust XDG_RUNTIME_DIR if different
s.sendall(b'{\"cmd\": \"ping\"}\n')
print(s.recv(4096))
"`

Expected: `{"ok": true, "msg": "pong"}` — confirms the daemon is still accepting connections normally with the new background thread running (no crash on startup).

- [ ] **Step 4: Commit**

```bash
git add sqlch/core/daemon.py
git commit -m "feat: start the curation poller thread in the daemon"
```

---

### Task 11: Record heard tracks from live playback

**Files:**
- Modify: `sqlch/core/player.py:168-192` (`_watch_metadata`)
- Modify: `sqlch/core/player.py:286-309` (`play_station`, thread the station id through)
- Test: `tests/test_player_heard_tracks.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest
from unittest import mock

from sqlch.core import player


class TestWatchMetadataRecordsHeardTracks(unittest.TestCase):
    def test_track_change_calls_curation_record_heard(self):
        calls = []

        def fake_record_heard(station_id, artist, title):
            calls.append((station_id, artist, title))

        metas = iter([
            {"icy-title": "Pearl Jam - Even Flow"},
            None,  # stops the loop via _metadata_stop below
        ])

        def fake_mpv_get(prop):
            if prop == "metadata":
                try:
                    return next(metas)
                except StopIteration:
                    player._metadata_stop.set()
                    return None
            return None

        with mock.patch.object(player, "mpv_get", fake_mpv_get), \
             mock.patch.object(player, "_mpv_ipc", lambda *a, **k: None), \
             mock.patch.object(player, "_apply_enrichment_now", lambda *a, **k: None), \
             mock.patch("sqlch.core.curation.record_heard", fake_record_heard), \
             mock.patch("time.sleep", lambda *_: None):
            player._metadata_stop.clear()
            player._watch_metadata("WMMR - MMR Rocks", "wmmr-mmr-rocks")

        self.assertIn(("wmmr-mmr-rocks", "Pearl Jam", "Even Flow"), calls)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_player_heard_tracks -v`
Expected: FAIL — `TypeError: _watch_metadata() takes 1 positional argument but 2 were given`

- [ ] **Step 3: Update `_watch_metadata` and its caller**

In `sqlch/core/player.py`, replace the `_watch_metadata` function (currently lines 168-192):

```python
def _watch_metadata(station_name: str, station_id: str | None = None) -> None:
    _metadata_stop.clear()
    last_seen: str | None = None
    _mpv_ipc({"command": ["observe_property", 1, "metadata"]})

    while not _metadata_stop.is_set():
        meta = mpv_get("metadata")
        if not meta:
            time.sleep(0.5)
            continue
        icy = meta.get("icy-title") or meta.get("title")
        if icy and icy != last_seen:
            last_seen = icy
            artist, track = _parse_icy(icy)
            if track:
                try:
                    _apply_enrichment_now(artist, track, station_name)
                except Exception:
                    pass
                try:
                    from sqlch.core import recorder
                    recorder.on_track_change(artist, track)
                except Exception:
                    pass
                if station_id:
                    try:
                        from sqlch.core import curation
                        curation.record_heard(station_id, artist, track)
                    except Exception:
                        pass
        time.sleep(0.5)
```

Then in `play_station` (currently lines 286-309), update the thread construction to pass the station id:

```python
    if _wait_for_ipc():
        _metadata_thread = threading.Thread(
            target=_watch_metadata,
            args=(station.get("name", "Station"), station.get("id")),
            daemon=True,
        )
        _metadata_thread.start()
```

- [ ] **Step 4: Add `curation.record_heard`**

In `sqlch/core/curation.py`, add:

```python
def record_heard(station_id: str, artist: str | None, title: str | None) -> None:
    conn = curation_db.connect()
    try:
        curation_db.record_heard_track(conn, station_id, artist, title)
    finally:
        conn.close()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m unittest tests.test_player_heard_tracks -v`
Expected: PASS

- [ ] **Step 6: Run the full suite to check nothing else broke**

Run: `python -m unittest discover -s tests -v`
Expected: all tests PASS (recorder tests unaffected — `recorder.on_track_change` call site is untouched)

- [ ] **Step 7: Commit**

```bash
git add sqlch/core/player.py sqlch/core/curation.py tests/test_player_heard_tracks.py
git commit -m "feat: record heard tracks from live playback into curation.db"
```

---

### Task 12: `sqlch add` reports probation

**Files:**
- Modify: `sqlch/cli/main.py:201-244` (`add_cmd`)
- Test: `tests/test_cli_add_curation.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest
from unittest import mock

from sqlch.cli import main as cli_main


class TestAddCmdReportsProbation(unittest.TestCase):
    def test_add_reports_probation_on_pass(self):
        fake_results = [{"name": "Test Station", "url": "http://example.com/s"}]
        fake_station = {"id": "test-station", "name": "Test Station"}

        with mock.patch("sqlch.core.discover.load_last_search", return_value=fake_results), \
             mock.patch("sqlch.core.library.add_station", return_value=fake_station), \
             mock.patch("sqlch.core.curation.admission_check", return_value=(True, None)), \
             mock.patch("sqlch.core.curation.start_probation") as start_probation, \
             mock.patch("builtins.print") as mock_print:
            cli_main.add_cmd(["1"])

        start_probation.assert_called_once()
        printed = " ".join(str(c.args[0]) for c in mock_print.call_args_list)
        self.assertIn("probation", printed.lower())

    def test_add_reports_rejection_reason_on_fail(self):
        fake_results = [{"name": "Test Station", "url": "http://example.com/s"}]
        fake_station = {"id": "test-station", "name": "Test Station"}

        with mock.patch("sqlch.core.discover.load_last_search", return_value=fake_results), \
             mock.patch("sqlch.core.library.add_station", return_value=fake_station), \
             mock.patch("sqlch.core.curation.admission_check", return_value=(False, "no tags")), \
             mock.patch("sqlch.core.curation.start_probation") as start_probation, \
             mock.patch("builtins.print") as mock_print:
            cli_main.add_cmd(["1"])

        start_probation.assert_not_called()
        printed = " ".join(str(c.args[0]) for c in mock_print.call_args_list)
        self.assertIn("no tags", printed)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_cli_add_curation -v`
Expected: FAIL — printed output doesn't mention "probation" (current `add_cmd` just prints `f"Added: {st['name']}"`)

- [ ] **Step 3: Update `add_cmd`**

In `sqlch/cli/main.py`, replace the tail of `add_cmd` (the two lines after `chosen`/`name`/`url` are resolved — currently just `st = library.add_station(name=name, url=url); print(f"Added: {st['name']}")`):

```python
    st = library.add_station(name=name, url=url)

    from sqlch.core import curation
    passed, reason = curation.admission_check(st)
    if passed:
        conn = curation.curation_db.connect()
        try:
            curation.start_probation(conn, st["id"])
        finally:
            conn.close()
        print(f"Added: {st['name']} — on probation for {curation.PROBATION_DAYS} days")
    else:
        print(f"Added: {st['name']} — not entering probation ({reason})")
```

No new import needed in `main.py` for `curation_db` — `curation.py` already imports it at module level (Task 8's `from sqlch.core import curation_db`), so `curation.curation_db.connect()` resolves through the `curation` import already added above.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_cli_add_curation -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sqlch/cli/main.py tests/test_cli_add_curation.py
git commit -m "feat: sqlch add runs the admission filter and starts probation"
```

---

### Task 13: `sqlch presets` command

**Files:**
- Modify: `sqlch/cli/main.py` (`dispatch_command`, new `presets_cmd`)
- Test: `tests/test_cli_presets.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest
from unittest import mock

from sqlch.cli import main as cli_main


class TestPresetsCmd(unittest.TestCase):
    def test_lists_only_preset_stations(self):
        stations = [
            {"id": "s1", "name": "Station One"},
            {"id": "s2", "name": "Station Two"},
        ]
        states = {
            "s1": {"status": "preset", "score": 0.72},
            "s2": {"status": "candidate", "score": None},
        }

        with mock.patch("sqlch.core.library.list_stations", return_value=stations), \
             mock.patch(
                 "sqlch.core.curation.curation_db.get_curation_state",
                 side_effect=lambda conn, sid: states.get(sid),
             ), \
             mock.patch("sqlch.core.curation.curation_db.connect"), \
             mock.patch("builtins.print") as mock_print:
            cli_main.presets_cmd()

        printed = " ".join(str(c.args[0]) for c in mock_print.call_args_list)
        self.assertIn("Station One", printed)
        self.assertNotIn("Station Two", printed)

    def test_no_presets_yet(self):
        with mock.patch("sqlch.core.library.list_stations", return_value=[]), \
             mock.patch("sqlch.core.curation.curation_db.connect"), \
             mock.patch("builtins.print") as mock_print:
            cli_main.presets_cmd()

        printed = " ".join(str(c.args[0]) for c in mock_print.call_args_list)
        self.assertIn("No presets yet", printed)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_cli_presets -v`
Expected: FAIL — `AttributeError: module 'sqlch.cli.main' has no attribute 'presets_cmd'`

- [ ] **Step 3: Add `presets_cmd` and wire dispatch**

In `sqlch/cli/main.py`, add after `list_cmd`:

```python
def presets_cmd() -> None:
    from sqlch.core import curation, library

    stations = library.list_stations()
    conn = curation.curation_db.connect()
    try:
        presets = [
            (st, curation.curation_db.get_curation_state(conn, st["id"]))
            for st in stations
        ]
    finally:
        conn.close()
    presets = [(st, state) for st, state in presets if state and state["status"] == "preset"]

    if not presets:
        print("No presets yet.")
        return
    for st, state in presets:
        score = state.get("score")
        score_str = f"{score:.2f}" if score is not None else "-"
        print(f"{st['id']:20} {st['name']:30} score={score_str}")
```

In `dispatch_command`, add before the final `print(f'Unknown command: {cmd}', ...)`:

```python
    if cmd == 'presets':
        presets_cmd()
        return
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_cli_presets -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sqlch/cli/main.py tests/test_cli_presets.py
git commit -m "feat: add sqlch presets command"
```

---

### Task 14: `sqlch info` curation block

**Files:**
- Modify: `sqlch/cli/main.py:190-198` (`info_cmd`)
- Test: `tests/test_cli_info_curation.py`

- [ ] **Step 1: Write the failing test**

```python
import json
import unittest
from unittest import mock

from sqlch.cli import main as cli_main


class TestInfoCmdCurationBlock(unittest.TestCase):
    def test_info_includes_curation_state_when_present(self):
        station = {"id": "s1", "name": "Station One"}
        state = {"status": "candidate", "probation_ends_at": 2000, "score": None}

        with mock.patch("sqlch.core.library.find_station", return_value=station), \
             mock.patch(
                 "sqlch.core.curation.curation_db.get_curation_state", return_value=state
             ), \
             mock.patch("sqlch.core.curation.curation_db.connect"), \
             mock.patch("builtins.print") as mock_print:
            cli_main.info_cmd(["s1"])

        printed = "".join(str(c.args[0]) for c in mock_print.call_args_list)
        parsed = json.loads(printed)
        self.assertEqual(parsed["curation"]["status"], "candidate")

    def test_info_omits_curation_block_when_never_curated(self):
        station = {"id": "s1", "name": "Station One"}

        with mock.patch("sqlch.core.library.find_station", return_value=station), \
             mock.patch(
                 "sqlch.core.curation.curation_db.get_curation_state", return_value=None
             ), \
             mock.patch("sqlch.core.curation.curation_db.connect"), \
             mock.patch("builtins.print") as mock_print:
            cli_main.info_cmd(["s1"])

        printed = "".join(str(c.args[0]) for c in mock_print.call_args_list)
        parsed = json.loads(printed)
        self.assertNotIn("curation", parsed)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_cli_info_curation -v`
Expected: FAIL — printed JSON has no `curation` key even in the first test (current `info_cmd` just dumps the station dict)

- [ ] **Step 3: Update `info_cmd`**

Replace `info_cmd` in `sqlch/cli/main.py`:

```python
def info_cmd(args: list[str]) -> None:
    if not args:
        print('Usage: sqlch info <station-id>', file=sys.stderr)
        sys.exit(1)
    st = library.find_station(args[0])
    if not st:
        print('Station not found.', file=sys.stderr)
        sys.exit(1)

    from sqlch.core import curation
    conn = curation.curation_db.connect()
    try:
        state = curation.curation_db.get_curation_state(conn, st["id"])
    finally:
        conn.close()

    out = dict(st)
    if state:
        out["curation"] = state
    print(json.dumps(out, indent=2))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_cli_info_curation -v`
Expected: PASS

- [ ] **Step 5: Run the full suite one final time**

Run: `python -m unittest discover -s tests -v`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add sqlch/cli/main.py tests/test_cli_info_curation.py
git commit -m "feat: sqlch info shows curation state when present"
```

---

## After this plan

The core loop is complete and fully exercised via CLI: `sqlch add` runs admission + starts probation, the daemon polls candidates every ~3 minutes and evaluates due ones, `sqlch presets` shows what's graduated, `sqlch info` shows any station's curation state. Nothing here requires the GUI or TUI to be running.

Follow-up plan (separate spec-review cycle, not needed to validate this one): TUI status indicator in the station list, GUI status indicator in `station_list.py`, and wiring `now_playing.py`'s tracklist-flip interaction as an optional engagement signal feeding into scoring.
