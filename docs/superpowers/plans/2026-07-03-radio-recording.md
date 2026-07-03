# Radio Recording Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record what's playing (bit-perfect, via mpv `stream-record`) in full-session or per-track mode, finalized into tagged files under `~/Music/radio/<Station>/`, controlled by a GUI record knob and `sqlch record` CLI.

**Architecture:** A new `sqlch/core/recorder.py` module runs inside the daemon and owns one recording session at a time (module-global state, same idiom as `player.py`). It starts/stops mpv's `stream-record` property over the existing IPC, rotates dump files on ICY track changes (track mode), and finalizes each closed dump with `ffprobe` codec detection + `ffmpeg -c copy` remux with embedded tags. The daemon exposes `record` commands and a `recording` status block; the CLI and GUI are thin clients of those.

**Tech Stack:** Python 3.11+ stdlib, mpv IPC (existing), ffmpeg/ffprobe (already runtime deps — preview uses ffplay), GTK4/Cairo for the GUI knob, stdlib `unittest` for tests (repo has no test infra; zero new dependencies).

**Spec:** `docs/superpowers/specs/2026-07-03-radio-recording-design.md`

---

## File structure

| File | Change | Responsibility |
|---|---|---|
| `sqlch/core/recorder.py` | Create | Recording session state machine + finalize pipeline (all recording logic lives here) |
| `tests/test_recorder.py` | Create | Unit tests: pure helpers, state machine (mpv mocked), finalize (real ffmpeg on synthesized audio) |
| `sqlch/core/daemon.py` | Modify | `record` command dispatch; `recording` block in `status` reply |
| `sqlch/core/player.py` | Modify | Stop recording on `stop()`; forward ICY track changes to recorder |
| `sqlch/cli/main.py` | Modify | `sqlch record [--full|--track|stop]` + help text |
| `sqlch_gui/ui/knob.py` | Modify | New `RecordKnob` two-detent switch widget |
| `sqlch_gui/ui/now_playing.py` | Modify | Knob in hub row, REC badge in readout strip |
| `sqlch_gui/ui/window.py` | Modify | Pass `recording` block from status poll into the panel |
| `sqlch_gui/ui/common.py` | Modify | `.rec-badge` CSS |

Notes for the engineer:

- **Import cycle guard:** `player.py` and `recorder.py` reference each other. `recorder.py` NEVER imports `player` at module level — only via the `_mpv()` lazy accessor. `player.py` and `daemon.py` import `recorder` lazily inside functions. Tests patch `_mpv()`, so tests never import `player` (which pulls in `requests`).
- **State idiom:** module-level globals + functions, matching `player.py` (`_current`, `stop()`, …). Don't introduce classes for the session.
- **Run tests from the repo root** (inside the nix dev shell so `requests` etc. are importable): `python -m unittest discover -s tests -v`.

---

### Task 1: Recorder pure helpers

**Files:**
- Create: `tests/test_recorder.py`
- Create: `tests/__init__.py` (empty)
- Create: `sqlch/core/recorder.py`

- [ ] **Step 1: Write the failing tests**

Create empty `tests/__init__.py`, then `tests/test_recorder.py`:

```python
import tempfile
import unittest
from pathlib import Path

from sqlch.core import recorder


class TestSanitizeFilename(unittest.TestCase):
    def test_replaces_path_separators(self):
        self.assertEqual(recorder.sanitize_filename("AC/DC - Back In Black"),
                         "AC-DC - Back In Black")

    def test_strips_control_chars_and_collapses_whitespace(self):
        self.assertEqual(recorder.sanitize_filename("a\x00b   c\n"), "ab c")

    def test_strips_leading_trailing_dots_and_spaces(self):
        self.assertEqual(recorder.sanitize_filename(" .hidden. "), "hidden")

    def test_empty_becomes_untitled(self):
        self.assertEqual(recorder.sanitize_filename("///"), "untitled")

    def test_caps_length(self):
        self.assertEqual(len(recorder.sanitize_filename("x" * 500)), 120)


class TestExtForCodec(unittest.TestCase):
    def test_known_codecs(self):
        self.assertEqual(recorder.ext_for_codec("aac"), ".m4a")
        self.assertEqual(recorder.ext_for_codec("mp3"), ".mp3")
        self.assertEqual(recorder.ext_for_codec("vorbis"), ".ogg")
        self.assertEqual(recorder.ext_for_codec("opus"), ".opus")

    def test_unknown_or_none_falls_back_to_mka(self):
        self.assertEqual(recorder.ext_for_codec("wma9"), ".mka")
        self.assertEqual(recorder.ext_for_codec(None), ".mka")

    def test_case_insensitive(self):
        self.assertEqual(recorder.ext_for_codec("AAC"), ".m4a")


class TestUniquePath(unittest.TestCase):
    def test_returns_path_unchanged_when_free(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.m4a"
            self.assertEqual(recorder.unique_path(p), p)

    def test_suffixes_on_collision(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.m4a"
            p.touch()
            self.assertEqual(recorder.unique_path(p), Path(td) / "a (2).m4a")
            (Path(td) / "a (2).m4a").touch()
            self.assertEqual(recorder.unique_path(p), Path(td) / "a (3).m4a")


class TestFormatTracklist(unittest.TestCase):
    def test_formats_entries(self):
        out = recorder.format_tracklist([
            (0.0, "Kraftwerk", "Autobahn"),
            (75.4, None, "Station Ident"),
        ])
        self.assertEqual(out, "[00:00] Kraftwerk - Autobahn\n[01:15] Station Ident\n")

    def test_empty_list(self):
        self.assertEqual(recorder.format_tracklist([]), "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_recorder -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sqlch.core.recorder'`

- [ ] **Step 3: Write the helpers**

Create `sqlch/core/recorder.py`:

```python
"""Stream recording via mpv stream-record: session state + finalize pipeline.

The daemon owns at most one recording at a time. mpv dumps the raw stream
bytes (bit-perfect, no re-encode) into <recordings_dir>/.incoming/; on
finalize each dump is remuxed losslessly (ffmpeg -c copy) into a tagged
file under <recordings_dir>/<Station>/.

Import-cycle note: player.py calls into this module, so mpv access here goes
through the lazy _mpv() accessor instead of a top-level import.
"""

from __future__ import annotations

import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlch.core import config, notify

_CODEC_EXT = {
    "aac": ".m4a",
    "mp3": ".mp3",
    "vorbis": ".ogg",
    "opus": ".opus",
}
_FALLBACK_EXT = ".mka"

_lock = threading.Lock()
_session: dict[str, Any] | None = None


def _mpv():
    from sqlch.core import player
    return player


# ------------------------------------------------------------
# Paths + naming
# ------------------------------------------------------------

def recordings_dir() -> Path:
    d = config.load().get("recordings_dir")
    p = Path(d).expanduser() if d else Path.home() / "Music" / "radio"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _staging_dir() -> Path:
    p = recordings_dir() / ".incoming"
    p.mkdir(parents=True, exist_ok=True)
    return p


def sanitize_filename(name: str) -> str:
    """Make a station/track string safe as a single path component."""
    name = "".join(c for c in name if c.isprintable())
    for sep in ("/", "\\", ":"):
        name = name.replace(sep, "-")
    name = " ".join(name.split())
    name = name.strip(". ")
    return name[:120] or "untitled"


def ext_for_codec(codec: str | None) -> str:
    return _CODEC_EXT.get((codec or "").lower(), _FALLBACK_EXT)


def unique_path(dest: Path) -> Path:
    if not dest.exists():
        return dest
    for i in range(2, 1000):
        cand = dest.with_name(f"{dest.stem} ({i}){dest.suffix}")
        if not cand.exists():
            return cand
    return dest.with_name(f"{dest.stem} ({int(time.time())}){dest.suffix}")


def format_tracklist(entries: list[tuple[float, str | None, str | None]]) -> str:
    lines = []
    for elapsed, artist, title in entries:
        m, s = divmod(int(elapsed), 60)
        who = f"{artist} - {title}" if artist else (title or "Unknown")
        lines.append(f"[{m:02d}:{s:02d}] {who}")
    return "\n".join(lines) + ("\n" if lines else "")
```

Note: `sanitize_filename("///")` → separators become `-`, then `.strip(". ")` does NOT strip `-`; the test expects `untitled`, so strip happens on the *original* separators: `"/"` → `"-"` gives `"---"`. Adjust: strip `"-. "` at the ends — change the strip line to `name = name.strip("-. ")`. Keep the test as written; it pins this behavior.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_recorder -v`
Expected: PASS (all tests OK)

- [ ] **Step 5: Commit**

```bash
git add tests/__init__.py tests/test_recorder.py sqlch/core/recorder.py
git commit -m "feat(recorder): filename/codec/tracklist helpers with tests"
```

---

### Task 2: Finalize pipeline (ffprobe + ffmpeg remux)

**Files:**
- Modify: `sqlch/core/recorder.py`
- Test: `tests/test_recorder.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_recorder.py`:

```python
import shutil
import subprocess
from unittest import mock

_HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _synth_aac(dest: Path) -> None:
    """1 second of sine, AAC in an ADTS stream — same shape as a radio dump."""
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-c:a", "aac", "-f", "adts", str(dest)],
        check=True,
    )


@unittest.skipUnless(_HAS_FFMPEG, "ffmpeg/ffprobe not on PATH")
class TestFinalize(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        patcher = mock.patch.object(
            recorder.config, "load",
            return_value={"recordings_dir": str(self.root)},
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._td.cleanup)

    def test_finalize_remuxes_tags_and_removes_raw(self):
        raw = self.root / ".incoming" / "rec-x-0.dump"
        raw.parent.mkdir(parents=True)
        _synth_aac(raw)

        dest = recorder._finalize(
            raw, "KEXP 90.3", {"artist": "Kraftwerk", "title": "Autobahn"},
            "Kraftwerk - Autobahn",
        )
        self.assertIsNotNone(dest)
        self.assertEqual(dest, self.root / "KEXP 90.3" / "Kraftwerk - Autobahn.m4a")
        self.assertTrue(dest.exists())
        self.assertFalse(raw.exists())

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format_tags=artist,title",
             "-of", "default=noprint_wrappers=1", str(dest)],
            capture_output=True, text=True,
        ).stdout
        self.assertIn("artist=Kraftwerk", probe)
        self.assertIn("title=Autobahn", probe)

    def test_finalize_partial_suffix(self):
        raw = self.root / ".incoming" / "rec-x-1.dump"
        raw.parent.mkdir(parents=True)
        _synth_aac(raw)
        dest = recorder._finalize(raw, "KEXP 90.3", {}, "Some Song", partial=True)
        self.assertEqual(dest.name, "Some Song (partial).m4a")

    def test_finalize_empty_raw_returns_none(self):
        raw = self.root / ".incoming" / "empty.dump"
        raw.parent.mkdir(parents=True)
        raw.touch()
        self.assertIsNone(recorder._finalize(raw, "X", {}, "Y"))
        self.assertFalse(raw.exists())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_recorder.TestFinalize -v`
Expected: FAIL — `AttributeError: module 'sqlch.core.recorder' has no attribute '_finalize'`

- [ ] **Step 3: Implement the pipeline**

Append to `sqlch/core/recorder.py`:

```python
# ------------------------------------------------------------
# Finalize: raw dump -> tagged file
# ------------------------------------------------------------

def _probe_codec(path: Path) -> str | None:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        out = r.stdout.strip().splitlines()
        return out[0].strip() or None if out else None
    except Exception:
        return None


def _remux(raw: Path, dest: Path, tags: dict[str, str]) -> bool:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-i", str(raw), "-map", "0:a", "-c", "copy"]
    for k, v in tags.items():
        if v:
            cmd += ["-metadata", f"{k}={v}"]
    cmd.append(str(dest))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return r.returncode == 0 and dest.exists() and dest.stat().st_size > 0
    except Exception:
        return False


def _finalize(
    raw: Path,
    station_name: str,
    tags: dict[str, str],
    stem: str,
    partial: bool = False,
) -> Path | None:
    """Remux one closed raw dump into its tagged final file.

    Returns the final path, or None (failure keeps the raw for salvage;
    empty raws are discarded silently).
    """
    try:
        if not raw.exists() or raw.stat().st_size == 0:
            raw.unlink(missing_ok=True)
            return None
        codec = _probe_codec(raw)
        if partial:
            stem += " (partial)"
        dest_dir = recordings_dir() / sanitize_filename(station_name)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = unique_path(dest_dir / (sanitize_filename(stem) + ext_for_codec(codec)))
        if _remux(raw, dest, tags):
            raw.unlink(missing_ok=True)
            return dest
        notify.notify("sqlch record",
                      f"Could not finalize '{stem}' — raw kept in {raw.parent}")
        return None
    except Exception:
        notify.notify("sqlch record", f"Finalize error for '{stem}'")
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_recorder -v`
Expected: PASS (TestFinalize included; skips cleanly if ffmpeg absent)

- [ ] **Step 5: Commit**

```bash
git add sqlch/core/recorder.py tests/test_recorder.py
git commit -m "feat(recorder): lossless finalize pipeline (ffprobe + ffmpeg -c copy remux with tags)"
```

---

### Task 3: Recording session state machine

**Files:**
- Modify: `sqlch/core/recorder.py`
- Test: `tests/test_recorder.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_recorder.py`. The fake mpv patches `recorder._mpv` so `player.py` (and its `requests` import chain) is never touched:

```python
class FakeMpv:
    """Stands in for sqlch.core.player: records set_property calls."""

    def __init__(self, playing=True, icy=None):
        self._playing = playing
        self._icy = icy
        self.props: list[tuple] = []

    class _Sock:
        def __init__(self, exists): self._e = exists
        def exists(self): return self._e

    def mpv_socket(self):
        return self._Sock(self._playing)

    def mpv_get(self, prop):
        if not self._playing:
            return None
        if prop == "pid":
            return 4242
        if prop == "metadata":
            return {"icy-title": self._icy} if self._icy else {}
        if prop == "filtered-metadata":
            return {"icy-genre": "electronic"}
        return None

    def mpv_command(self, *parts):
        self.props.append(parts)

    def stream_record_values(self):
        return [p[2] for p in self.props
                if p[0] == "set_property" and p[1] == "stream-record"]

    @staticmethod
    def _parse_icy(title):
        if " - " in title:
            a, t = title.split(" - ", 1)
            return a.strip() or None, t.strip() or None
        return None, title.strip() or None


class TestSession(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.addCleanup(self._td.cleanup)
        for target, kw in [
            (mock.patch.object(recorder.config, "load",
                               return_value={"recordings_dir": str(self.root)}), {}),
            (mock.patch.object(recorder.notify, "notify"), {}),
            (mock.patch.object(recorder, "_finalize", return_value=None), {}),
        ]:
            target.start()
            self.addCleanup(target.stop)
        recorder._session = None  # isolate tests

    def _start(self, mode="full", icy="Kraftwerk - Autobahn"):
        self.fake = FakeMpv(icy=icy)
        p = mock.patch.object(recorder, "_mpv", return_value=self.fake)
        p.start()
        self.addCleanup(p.stop)
        return recorder.start(mode, {"name": "KEXP 90.3", "id": "kexp"})

    def test_start_requires_playback(self):
        self.fake = FakeMpv(playing=False)
        with mock.patch.object(recorder, "_mpv", return_value=self.fake):
            resp = recorder.start("full", {"name": "X"})
        self.assertFalse(resp["ok"])
        self.assertIn("nothing playing", resp["error"])

    def test_start_rejects_bad_mode(self):
        resp = recorder.start("shuffle", {"name": "X"})
        self.assertFalse(resp["ok"])

    def test_start_sets_stream_record_and_status(self):
        resp = self._start()
        self.assertTrue(resp["ok"])
        vals = self.fake.stream_record_values()
        self.assertEqual(len(vals), 1)
        self.assertTrue(vals[0].startswith(str(self.root / ".incoming")))
        st = recorder.status()
        self.assertTrue(st["active"])
        self.assertEqual(st["mode"], "full")
        self.assertEqual(st["station"], "KEXP 90.3")

    def test_double_start_refused(self):
        self._start()
        resp = recorder.start("full", {"name": "KEXP 90.3"})
        self.assertFalse(resp["ok"])
        self.assertIn("already recording", resp["error"])

    def test_full_mode_track_change_only_logs(self):
        self._start(mode="full")
        recorder.on_track_change("Neu!", "Hallogallo")
        self.assertEqual(len(self.fake.stream_record_values()), 1)  # no rotation
        self.assertEqual(len(recorder._session["tracklist"]), 2)  # start icy + change

    def test_track_mode_rotates_and_finalizes_previous(self):
        self._start(mode="track")
        recorder.on_track_change("Neu!", "Hallogallo")
        recorder._join_finalizers()
        vals = self.fake.stream_record_values()
        self.assertEqual(len(vals), 2)
        self.assertNotEqual(vals[0], vals[1])
        recorder._finalize.assert_called_once()
        _, kwargs_or_args = recorder._finalize.call_args[0], recorder._finalize.call_args
        args = recorder._finalize.call_args[0]
        self.assertEqual(args[3], "Kraftwerk - Autobahn")  # stem = track that ENDED
        self.assertTrue(recorder._finalize.call_args[1]["partial"])  # first file partial

    def test_stop_clears_property_and_state(self):
        self._start(mode="full")
        resp = recorder.stop()
        recorder._join_finalizers()
        self.assertTrue(resp["ok"])
        self.assertEqual(self.fake.stream_record_values()[-1], "")
        self.assertFalse(recorder.status()["active"])

    def test_stop_when_idle_errors(self):
        resp = recorder.stop()
        self.assertFalse(resp["ok"])

    def test_full_mode_stop_writes_tracklist_sidecar(self):
        self._start(mode="full")
        recorder.on_track_change("Neu!", "Hallogallo")
        with mock.patch.object(recorder, "_finalize",
                               return_value=self.root / "KEXP 90.3" / "s.m4a") as fin:
            (self.root / "KEXP 90.3").mkdir(parents=True, exist_ok=True)
            recorder.stop()
            recorder._join_finalizers()
        sidecar = self.root / "KEXP 90.3" / "s.tracklist.txt"
        self.assertTrue(sidecar.exists())
        self.assertIn("Kraftwerk - Autobahn", sidecar.read_text())
        self.assertIn("Hallogallo", sidecar.read_text())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_recorder.TestSession -v`
Expected: FAIL — `AttributeError: ... no attribute 'start'`

- [ ] **Step 3: Implement the session state machine**

Append to `sqlch/core/recorder.py`:

```python
# ------------------------------------------------------------
# Session state machine (daemon-side singleton)
# ------------------------------------------------------------

_finalizers: list[threading.Thread] = []


def _spawn_finalizer(target, *args) -> None:
    t = threading.Thread(target=target, args=args, daemon=True)
    _finalizers.append(t)
    t.start()


def _join_finalizers(timeout: float = 10.0) -> None:
    """Test hook: wait for background finalize threads."""
    for t in list(_finalizers):
        t.join(timeout)
    _finalizers.clear()


def _raw_path(started_at: datetime, seq: int) -> Path:
    return _staging_dir() / f"rec-{started_at:%Y%m%d-%H%M%S}-{seq}.dump"


def start(mode: str, station: dict[str, Any] | None) -> dict[str, Any]:
    global _session
    if mode not in ("full", "track"):
        return {"ok": False, "error": f"unknown mode: {mode}"}
    p = _mpv()
    with _lock:
        if _session:
            return {"ok": False, "error": "already recording",
                    "recording": _status_locked()}
        if not p.mpv_socket().exists() or p.mpv_get("pid") is None:
            return {"ok": False, "error": "nothing playing"}

        station = station or {}
        started_at = datetime.now()
        raw = _raw_path(started_at, 0)
        p.mpv_command("set_property", "stream-record", str(raw))

        artist = title = None
        meta = p.mpv_get("metadata") or {}
        icy = meta.get("icy-title") or meta.get("title")
        if icy:
            artist, title = p._parse_icy(icy)
        fmeta = p.mpv_get("filtered-metadata") or {}
        genre = fmeta.get("icy-genre") or fmeta.get("genre")

        _session = {
            "mode": mode,
            "station": station,
            "started": time.monotonic(),
            "started_at": started_at,
            "raw": raw,
            "seq": 0,
            "tracklist": [],
            "current_track": (artist, title),
            "first_file": True,
            "icy_genre": genre,
        }
        if title:
            _session["tracklist"].append((0.0, artist, title))
    notify.notify("sqlch record",
                  f"Recording ({mode})\n{station.get('name', 'station')}")
    return {"ok": True, "recording": status()}


def on_track_change(artist: str | None, title: str | None) -> None:
    """Called by the daemon's metadata watcher on every ICY title change."""
    with _lock:
        if not _session:
            return
        elapsed = time.monotonic() - _session["started"]
        prev_track = _session["current_track"]
        _session["current_track"] = (artist, title)
        _session["tracklist"].append((elapsed, artist, title))
        if _session["mode"] != "track":
            return
        p = _mpv()
        _session["seq"] += 1
        new_raw = _raw_path(_session["started_at"], _session["seq"])
        old_raw = _session["raw"]
        p.mpv_command("set_property", "stream-record", str(new_raw))
        _session["raw"] = new_raw
        partial = _session["first_file"]
        _session["first_file"] = False
        station_name = _session["station"].get("name", "Station")
    _spawn_finalizer(_finalize_track, old_raw, station_name, prev_track, partial)


def stop() -> dict[str, Any]:
    global _session
    with _lock:
        if not _session:
            return {"ok": False, "error": "not recording"}
        sess = _session
        _session = None
    p = _mpv()
    if p.mpv_socket().exists():
        p.mpv_command("set_property", "stream-record", "")
        time.sleep(0.2)  # give mpv a beat to flush + close the dump

    station_name = sess["station"].get("name", "Station")
    if sess["mode"] == "track":
        last_partial = True  # stop always cuts the playing song short
        _spawn_finalizer(_finalize_track, sess["raw"], station_name,
                         sess["current_track"], last_partial)
    else:
        _spawn_finalizer(_finalize_session, sess, station_name)
    notify.notify("sqlch record", "Recording stopped")
    return {"ok": True}


def status() -> dict[str, Any]:
    with _lock:
        return _status_locked()


def _status_locked() -> dict[str, Any]:
    if not _session:
        return {"active": False}
    return {
        "active": True,
        "mode": _session["mode"],
        "elapsed": int(time.monotonic() - _session["started"]),
        "file": str(_session["raw"]),
        "station": _session["station"].get("name"),
    }


# ------------------------------------------------------------
# Per-mode finalize wrappers (run on background threads)
# ------------------------------------------------------------

def _finalize_track(
    raw: Path,
    station_name: str,
    track: tuple[str | None, str | None],
    partial: bool,
) -> None:
    artist, title = track
    stem = f"{artist} - {title}" if artist and title else (title or raw.stem)
    tags = {
        "artist": artist or "",
        "title": title or "",
        "album": station_name,
        "comment": f"Recorded from {station_name} by sqlch",
    }
    if artist and title:
        try:
            from sqlch.core import enrich
            meta = enrich.enrich_track(artist, title)
            if meta.get("album"):
                tags["album"] = meta["album"]
            if meta.get("year"):
                tags["date"] = str(meta["year"])
            if meta.get("genres"):
                tags["genre"] = ", ".join(meta["genres"])
        except Exception:
            pass
    _finalize(raw, station_name, tags, stem, partial=partial)


def _finalize_session(sess: dict[str, Any], station_name: str) -> None:
    stamp = f"{sess['started_at']:%Y-%m-%d %H%M}"
    stem = f"{station_name} - {stamp}"
    tags = {
        "title": stem,
        "artist": station_name,
        "album": station_name,
        "date": f"{sess['started_at']:%Y-%m-%d}",
        "genre": sess.get("icy_genre") or "",
        "comment": "Recorded by sqlch",
    }
    dest = _finalize(sess["raw"], station_name, tags, stem)
    if dest and sess["tracklist"]:
        try:
            dest.with_suffix(".tracklist.txt").write_text(
                format_tracklist(sess["tracklist"])
            )
        except Exception:
            pass
```

- [ ] **Step 4: Run the full test file**

Run: `python -m unittest tests.test_recorder -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sqlch/core/recorder.py tests/test_recorder.py
git commit -m "feat(recorder): session state machine — start/stop/track rotation/status"
```

---

### Task 4: Daemon + player integration

**Files:**
- Modify: `sqlch/core/daemon.py` (command dispatch, `_handle`)
- Modify: `sqlch/core/player.py` (`stop()`, `_watch_metadata`)

No unit tests for this task (socket daemon has no test harness); verified live in Task 8. Keep changes minimal and mechanical.

- [ ] **Step 1: Add the `record` command to `daemon._handle`**

In `sqlch/core/daemon.py`, inside `_handle`, before the final `return {'ok': False, 'error': f'unknown cmd: {cmd}'}`:

```python
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
```

- [ ] **Step 2: Add the `recording` block to the `status` reply**

Still in `_handle`, replace the existing status branch:

```python
    if cmd == 'status':
        from sqlch.core import recorder
        return {
            'ok': True,
            'status': player.status_string(),
            'current': player.current(),
            'recording': recorder.status(),
        }
```

- [ ] **Step 3: Finalize recordings on playback stop / station switch**

In `sqlch/core/player.py`, `stop()` — add the recorder stop before `_kill_existing()` (mpv must still be alive so `stream-record` can be cleared and the dump flushed). `play_station()` already calls `stop(notify_user=False)`, so station switches are covered by this single hook:

```python
def stop(notify_user: bool = True) -> None:
    global _current, _preview_timer
    if _preview_timer:
        _preview_timer.cancel()
        _preview_timer = None
    from sqlch.core import recorder
    recorder.stop()  # no-op {'ok': False} when idle
    _kill_existing()
    _current = None
    if notify_user:
        notify.notify("sqlch", "Playback stopped")
```

- [ ] **Step 4: Forward ICY track changes to the recorder**

In `sqlch/core/player.py`, `_watch_metadata`, inside the `if icy and icy != last_seen:` block after the enrichment try/except:

```python
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
```

- [ ] **Step 5: Sanity-check the wiring compiles and tests still pass**

Run: `python -c "import sqlch.core.daemon, sqlch.core.player, sqlch.core.recorder" && python -m unittest tests.test_recorder -v`
Expected: no import errors; tests PASS

- [ ] **Step 6: Commit**

```bash
git add sqlch/core/daemon.py sqlch/core/player.py
git commit -m "feat(daemon): record command, recording status block, stop/track-change hooks"
```

---

### Task 5: CLI `sqlch record`

**Files:**
- Modify: `sqlch/cli/main.py`

- [ ] **Step 1: Add dispatch + command**

In `sqlch/cli/main.py`, add to `dispatch_command` (next to the other branches):

```python
    if cmd == 'record':
        record_cmd(args)
        return
```

Add the command function (near `preview_cmd`):

```python
def record_cmd(args: list[str]) -> None:
    if args and args[0] == 'stop':
        resp = daemon_call({'cmd': 'record', 'action': 'stop'})
        if resp is None:
            print('sqlch: daemon not running (recording requires the daemon)',
                  file=sys.stderr)
            sys.exit(1)
        if not resp.get('ok'):
            print(resp.get('error', 'record stop failed'), file=sys.stderr)
            sys.exit(1)
        print('Recording stopped.')
        return

    mode = 'track' if '--track' in args else 'full'
    status_resp = daemon_call({'cmd': 'record', 'action': 'status'})
    if status_resp is None:
        print('sqlch: daemon not running (recording requires the daemon)',
              file=sys.stderr)
        sys.exit(1)

    rec = status_resp.get('recording') or {}
    if rec.get('active'):
        m, s = divmod(int(rec.get('elapsed', 0)), 60)
        print(f"● recording ({rec.get('mode')}) "
              f"{rec.get('station') or ''} — {m:02d}:{s:02d}")
        print("  'sqlch record stop' to stop")
        return

    resp = daemon_call({'cmd': 'record', 'action': 'start', 'mode': mode})
    if not resp or not resp.get('ok'):
        print((resp or {}).get('error', 'record failed'), file=sys.stderr)
        sys.exit(1)
    st = (resp.get('recording') or {}).get('station')
    print(f"● recording ({mode})" + (f": {st}" if st else ""))
```

- [ ] **Step 2: Update HELP text**

In the `HELP` string, after the `  sqlch stop\n` line, add:

```python
    '  sqlch record [--full|--track]   (start; shows status if active)\n'
    '  sqlch record stop\n'
```

- [ ] **Step 3: Verify behavior without a daemon**

Run: `python -m sqlch.cli.main record` (with no daemon running; use `python -c "from sqlch.cli.main import main; import sys; sys.argv=['sqlch','record']; main()"` if the module isn't directly runnable)
Expected: `sqlch: daemon not running (recording requires the daemon)` on stderr, exit code 1

- [ ] **Step 4: Commit**

```bash
git add sqlch/cli/main.py
git commit -m "feat(cli): sqlch record --full/--track/stop"
```

---

### Task 6: GUI `RecordKnob` widget

**Files:**
- Modify: `sqlch_gui/ui/knob.py`

- [ ] **Step 1: Implement the widget**

Append to `sqlch_gui/ui/knob.py` (module already imports `math`, `Gtk`, `Gdk`, `GObject`):

```python
class RecordKnob(Gtk.DrawingArea):
    """Two-detent record switch drawn in the RotaryKnob idiom.

    Right-click spins the pointer between the FULL and TRACK detents;
    left-click emits 'record-toggled' with the selected mode. Recording
    state is pushed in from the daemon poll via set_state() — the widget
    never assumes its click succeeded.
    """

    __gsignals__ = {
        'record-toggled': (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    MODES = ("full", "track")
    # Lower arc detents (y grows downward): FULL lower-left, TRACK lower-right
    _ANGLES = {"full": 0.75 * math.pi, "track": 0.25 * math.pi}

    def __init__(self):
        super().__init__()
        self.mode = "full"
        self.recording = False
        self.set_size_request(52, 52)
        self.set_focusable(True)
        self.set_draw_func(self._on_draw)
        self._update_tooltip()

        left = Gtk.GestureClick.new()
        left.set_button(1)
        left.connect("released", self._on_left_click)
        self.add_controller(left)

        right = Gtk.GestureClick.new()
        right.set_button(3)
        right.connect("released", self._on_right_click)
        self.add_controller(right)

    def set_state(self, recording: bool, mode: str | None):
        """Reflect daemon truth from the status poll."""
        changed = recording != self.recording
        if recording and mode in self.MODES and mode != self.mode:
            self.mode = mode
            changed = True
        self.recording = recording
        if changed:
            self._update_tooltip()
            self.queue_draw()

    def _update_tooltip(self):
        action = "left-click to stop" if self.recording else "left-click to record"
        self.set_tooltip_text(
            f"REC {self.mode.upper()} · {action} · right-click: mode"
        )

    def _on_left_click(self, gesture, n_press, x, y):
        self.emit('record-toggled', self.mode)

    def _on_right_click(self, gesture, n_press, x, y):
        if self.recording:
            return  # mode locked while a take is rolling
        i = self.MODES.index(self.mode)
        self.mode = self.MODES[(i + 1) % len(self.MODES)]
        self._update_tooltip()
        self.queue_draw()

    def _on_draw(self, area, cr, width, height, user_data=None):
        cx = width / 2.0
        cy = height / 2.0
        radius = min(width, height) / 2.0 - 5.0
        rec_red = (0.86, 0.20, 0.18)

        # Hot ring while recording sits outside the bezel
        if self.recording:
            cr.set_line_width(2.5)
            cr.set_source_rgba(*rec_red, 0.9)
            cr.arc(cx, cy, radius + 2.0, 0, 2 * math.pi)
            cr.stroke()

        # Outer metal bezel + faceplate (matches RotaryKnob)
        cr.set_line_width(3.0)
        cr.set_source_rgba(0.12, 0.12, 0.14, 1.0)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()
        cr.set_source_rgba(0.20, 0.20, 0.22, 1.0)
        cr.arc(cx, cy, radius - 1, 0, 2 * math.pi)
        cr.fill()

        # Detent dots at both switch positions
        for ang in self._ANGLES.values():
            dx = cx + (radius - 4) * math.cos(ang)
            dy = cy + (radius - 4) * math.sin(ang)
            cr.set_source_rgba(0.1, 0.1, 0.1, 0.6)
            cr.arc(dx, dy, 2.0, 0, 2 * math.pi)
            cr.fill()

        # Pointer snapped to the selected detent
        angle = self._ANGLES[self.mode]
        if self.recording:
            cr.set_source_rgba(*rec_red, 1.0)
        else:
            cr.set_source_rgba(0.85, 0.61, 0.25, 1.0)  # RotaryKnob accent
        cr.set_line_width(4.0)
        mx = cx + (radius - 9) * math.cos(angle)
        my = cy + (radius - 9) * math.sin(angle)
        cr.move_to(cx, cy)
        cr.line_to(mx, my)
        cr.stroke()

        # Center cap doubles as the recording lamp
        if self.recording:
            cr.set_source_rgba(*rec_red, 1.0)
        else:
            cr.set_source_rgba(0.12, 0.12, 0.14, 1.0)
        cr.arc(cx, cy, radius * 0.28, 0, 2 * math.pi)
        cr.fill()
```

- [ ] **Step 2: Verify it imports**

Run: `python -c "import gi; gi.require_version('Gtk','4.0'); from sqlch_gui.ui.knob import RecordKnob; print('ok')"`
Expected: `ok` (needs the GTK4 environment; if `gi` is missing outside the nix shell, run inside it)

- [ ] **Step 3: Commit**

```bash
git add sqlch_gui/ui/knob.py
git commit -m "feat(sqlch-gui): RecordKnob two-detent record switch widget"
```

---

### Task 7: GUI wiring — hub row, REC badge, status poll

**Files:**
- Modify: `sqlch_gui/ui/now_playing.py`
- Modify: `sqlch_gui/ui/window.py`
- Modify: `sqlch_gui/ui/common.py`

- [ ] **Step 1: Add the knob and badge to `NowPlayingPanel`**

In `sqlch_gui/ui/now_playing.py`:

Import (line 9 area):

```python
from .knob import RotaryKnob, RecordKnob
```

In `__init__`, where the hub row is assembled, add the record knob as the leftmost element (final order: record | stop | volume | mute):

```python
        self.rec_knob = RecordKnob()
        self.rec_knob.set_valign(Gtk.Align.CENTER)
        self.rec_knob.connect("record-toggled", self.on_record_toggled)

        hub_row.append(self.rec_knob)
        hub_row.append(btn_stop)
        hub_row.append(self.vol_knob)
        hub_row.append(self.btn_mute)
```

(Replace the existing three `hub_row.append(...)` lines.)

In the readout strip, add the REC badge as the first badge:

```python
        self.lbl_rec = Gtk.Label()
        self.lbl_rec.add_css_class("tech-badge")
        self.lbl_rec.add_css_class("rec-badge")

        self.tech_box.append(self.lbl_rec)
        self.tech_box.append(self.lbl_vol_percent)
```

(`self.tech_box.append(self.lbl_vol_percent)` already exists — just make `lbl_rec` come first.)

- [ ] **Step 2: Drive knob + badge from the status poll**

Change the `update_indicators` signature (add trailing param):

```python
    def update_indicators(self, bitrate: int | None, vol: float, muted: bool,
                          bt: bool, playing: bool, channels: int | None,
                          recording: dict | None = None):
```

At the end of `update_indicators`, add:

```python
        rec = recording or {}
        active = bool(rec.get("active"))
        self.rec_knob.set_state(active, rec.get("mode"))
        if active:
            m, s = divmod(int(rec.get("elapsed", 0)), 60)
            self.lbl_rec.set_text(f"REC {m:02d}:{s:02d}")
        self.lbl_rec.set_visible(active)
```

In `reset_ui`, add:

```python
        self.rec_knob.set_state(False, None)
        self.lbl_rec.set_visible(False)
```

Add the click handler (next to `on_stop`):

```python
    def on_record_toggled(self, knob, mode):
        daemon.send({"cmd": "record", "action": "toggle", "mode": mode})
```

- [ ] **Step 3: Pass the recording block through `window.py`**

In `sqlch_gui/ui/window.py`, `_apply_daemon_state`, change the `update_indicators` call:

```python
        recording = resp.get("recording") if resp else None
        self.now_playing.update_indicators(
            bitrate, vol, muted, self._bt_active, playing, channels,
            recording=recording,
        )
```

- [ ] **Step 4: Style the badge**

In `sqlch_gui/ui/common.py`, after the `.tech-badge, .tag-chip` block, add:

```python
    .tech-badge.rec-badge {{
        background-color: {colors.get('FORTE', '#8c3b3b')};
        color: {colors.get('HALL', '#fdf8ee')};
        text-shadow: 0 1px 0 rgba({staff}, 0.60);
        outline: 1px dashed {thread_light};
    }}
```

(Inside the `css = f"""..."""` string; `colors`, `staff`, and `thread_light` are already in scope.)

- [ ] **Step 5: Verify the GUI modules import**

Run: `python -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Gtk4LayerShell','1.0'); import sqlch_gui.ui.now_playing, sqlch_gui.ui.window, sqlch_gui.ui.common; print('ok')"`
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add sqlch_gui/ui/now_playing.py sqlch_gui/ui/window.py sqlch_gui/ui/common.py
git commit -m "feat(sqlch-gui): wire record knob + REC badge into now-playing deck"
```

---

### Task 8: Manual end-to-end verification

**Files:** none (verification only). Per the spec, this feature's acceptance is manual — the repo has no daemon/GUI test harness.

The daemon must be restarted to pick up the new code (`sqlch daemon`, or however the user's session runs it — check `pgrep -af "sqlch daemon"` and restart that process). The GUI working tree launches per `~/.claude/projects/-home-prepko-sqlch/memory/sqlch-gui-dev-launch.md`: copy env exports (incl. `LD_PRELOAD` of `libgtk4-layer-shell.so`) from `head -30 /etc/profiles/per-user/prepko/bin/sqlch-gui`, but put `/home/prepko/sqlch` FIRST in `PYTHONPATH`; kill old instances with `pkill -f "python3 -m sqlch_gui"` in a SEPARATE command.

- [ ] **Step 1: Run the automated suite one last time**

Run: `python -m unittest discover -s tests -v`
Expected: all PASS

- [ ] **Step 2: Full-session recording via CLI**

```bash
sqlch play <some station>
sqlch record            # → "● recording (full): <station>"
sqlch record            # → status line with elapsed, no double-start
sleep 60
sqlch record stop
```
Expected: `~/Music/radio/<Station>/<Station> - YYYY-MM-DD HHMM.m4a` (ext per codec) exists, plays in mpv, `ffprobe` shows title/artist/album/date tags; `.tracklist.txt` sidecar alongside if any ICY titles aired; `.incoming/` empty.

- [ ] **Step 3: Track-mode recording via CLI**

```bash
sqlch record --track
# wait through at least 2 track changes (pick a music station)
sqlch record stop
```
Expected: per-song files `<Artist> - <Title>.m4a` tagged with artist/title (+ album/year/genre when enrichment has them); first and last files carry ` (partial)`.

- [ ] **Step 4: Station switch mid-recording**

Start a recording, then `sqlch play <other station>`.
Expected: recording finalizes (file appears for the first station), playback switches; `sqlch record` reports not recording.

- [ ] **Step 5: Error paths**

```bash
sqlch stop && sqlch record      # → "nothing playing" error
# stop the daemon, then:
sqlch record                    # → "daemon not running" error, exit 1
```

- [ ] **Step 6: GUI knob**

Launch the working-tree GUI (see note above). Verify: knob sits left of stop in the hub row; right-click flips pointer FULL↔TRACK (tooltip updates); left-click starts — knob lamp/ring goes red and `REC mm:ss` badge counts up within ~1s (poll interval); left-click again stops — knob returns to idle within ~1s; recording started from the CLI also lights the knob (daemon truth wins). Kill the dev instance (by PID, separate command) when done.

- [ ] **Step 7: Final commit if fixes were needed, and push**

```bash
git status   # commit any verification fixes with their own messages
git push
```
