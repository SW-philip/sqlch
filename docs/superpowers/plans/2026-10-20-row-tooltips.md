# Row Tooltips Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hovering a source-pane row or a library station row shows a tooltip with the full title plus metadata/description; the station row's live-track text scrolls inside its label when too wide.

**Architecture:** Items gain an optional `description` (filled by podcasts and Jellyfin). Pure functions in `sqlch_gui/ui/tooltips.py` build the tooltip text; `SourcePane._build_row` and `StationListPanel` set it. A `ScrollLabel` widget (offset maths in a GTK-free module) replaces the ellipsized live label on station rows.

**Tech Stack:** Python 3, GTK4 (PyGObject), unittest, `uv run python -m unittest` (pytest is not in the venv).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-10-20-row-tooltips-design.md`.
- Repo is `/home/prepko/sqlch`, branch `unstable`; commit only there; never `commit --amend`; do not push.
- Item field name is `description` (str | None, default None) on `make_item`.
- Description in tooltips is truncated to 300 characters with an ellipsis.
- YouTube gets no description; spotify/local/video files unchanged.
- Station tooltip: full name; `group · <freq>` (freq as `f"{freq:.1f}"`); live line when present.
- Item tooltip: full title; `artist · album · date · duration` (empty parts omitted, via `format_date`/`format_duration` from `sqlch_gui/ui/timefmt.py`); description after a blank line; folders get title+metadata only; None when no title.
- GUI tests that need `gi` follow the existing pattern (`import gi` at module top of `tests/test_station_list.py`); pure logic is tested without `gi`.
- Comments only where the WHY is non-obvious. Python follows sqlch conventions (`ruff`).
- Commits: lowercase one-liner `area: what`, with second `-m` paragraph `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

---

### Task 1: description field, podcasts and Jellyfin

**Files:**
- Modify: `sqlch/sources/base.py` (`make_item`)
- Modify: `sqlch/sources/podcasts.py` (`parse_feed`)
- Modify: `sqlch/sources/jellyfin.py` (`_to_item`, `_items`)
- Test: `tests/test_sources.py`, `tests/test_source_podcasts.py`, `tests/test_source_jellyfin.py`

**Interfaces:**
- Produces: `make_item(..., description: str | None = None)`; every item dict has key `"description"`. `podcasts.strip_html(text) -> str | None`.

- [ ] **Step 1: Write failing tests.**

`tests/test_sources.py`, add inside the existing test class that has `test_make_item_channel_id_defaults_to_none`:

```python
    def test_make_item_description_defaults_to_none(self):
        self.assertIsNone(make_item("local", "a", "A")["description"])
        self.assertEqual(make_item("local", "a", "A", description="d")["description"], "d")
```

`tests/test_source_podcasts.py`, add to `TestFeed`:

```python
    def test_description_is_html_stripped(self):
        feed = (b'<?xml version="1.0"?><rss version="2.0"><channel><title>S</title>'
                b'<item><title>E</title><guid>g</guid><enclosure url="https://c/e.mp3"/>'
                b'<description>&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt; &amp;amp; more&lt;/p&gt;</description>'
                b'</item><item><title>N</title><guid>h</guid><enclosure url="https://c/n.mp3"/>'
                b'</item></channel></rss>')
        eps = {e["title"]: e for e in podcasts.parse_feed(feed, "https://f/s")}
        self.assertEqual(eps["E"]["description"], "Hello world & more")
        self.assertIsNone(eps["N"]["description"])

    def test_strip_html(self):
        self.assertEqual(podcasts.strip_html("<p>a</p>\n\n<p>b  c</p>"), "a b c")
        self.assertIsNone(podcasts.strip_html("  <br/> "))
        self.assertIsNone(podcasts.strip_html(None))
```

`tests/test_source_jellyfin.py`, add a new class at the end:

```python
class TestDescription(unittest.TestCase):
    def test_overview_maps_to_description_and_is_requested(self):
        seen = {}

        def fake_get(path, params=None):
            seen["params"] = params
            return {"Items": [{"Id": "1", "Name": "Ep", "Type": "Episode",
                               "Overview": "Plot here"},
                              {"Id": "2", "Name": "Song", "Type": "Audio"}]}

        with mock.patch.object(jellyfin, "_get", fake_get), \
             mock.patch.object(jellyfin, "_user_id", return_value="U"):
            items = jellyfin._items({"parentId": "L"})
        self.assertEqual(items[0]["description"], "Plot here")
        self.assertIsNone(items[1]["description"])
        self.assertEqual(seen["params"]["Fields"], "Overview")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/sqlch && uv run python -m unittest tests.test_sources tests.test_source_podcasts tests.test_source_jellyfin 2>&1 | tail -15`
Expected: the new tests FAIL (KeyError `description` / no `strip_html` / no `Fields`).

- [ ] **Step 3: Implement.**

`base.py` — add `description=None` to the `make_item` keyword list (after `url=None`) and `"description": description` to the returned dict.

`podcasts.py` — add near the other helpers (add `import html` and `import re` at the top if missing):

```python
_TAGS = re.compile(r"<[^>]*>")


def strip_html(text) -> str | None:
    if not text:
        return None
    plain = " ".join(html.unescape(_TAGS.sub(" ", text)).split())
    return plain or None
```

In `parse_feed`, pass `description=strip_html(it.findtext("description") or it.findtext(f"{_ITUNES}summary"))` to the `make_item(...)` call for episodes.

`jellyfin.py` — in `_to_item` pass `description=jf.get("Overview") or None` to `make_item`; in `_items` change the request to `_get("/Items", {"userId": _user_id(), "Fields": "Overview", **params})` (params after, so a caller can still override).

- [ ] **Step 4: Run to verify pass, then the whole suite and lint**

Run: `cd ~/sqlch && uv run python -m unittest discover tests 2>&1 | tail -6 && uv run ruff check sqlch`
Expected: OK (tests needing `gi` may be skipped or fail identically to baseline; report the baseline difference, if any), ruff clean.

- [ ] **Step 5: Commit**

```bash
cd ~/sqlch && git add sqlch/sources tests/test_sources.py tests/test_source_podcasts.py tests/test_source_jellyfin.py
git commit -m "sources: items carry an optional description (podcasts, jellyfin)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: tooltip text and wiring

**Files:**
- Create: `sqlch_gui/ui/tooltips.py`
- Modify: `sqlch_gui/ui/source_pane.py` (`_build_row`)
- Modify: `sqlch_gui/ui/station_list.py` (`_build_station_row`, `_append_group_rows`, `refresh`, `set_active`, `_apply_probe`)
- Test: `tests/test_tooltips.py` (new, no `gi`), `tests/test_station_list.py`

**Interfaces:**
- Consumes: item dicts with optional `description`; `format_date`, `format_duration` from `sqlch_gui/ui/timefmt.py`.
- Produces: `item_tooltip(item: dict) -> str | None`; `station_tooltip(station: dict, live_text: str = "") -> str`; `StationListPanel._show_live(row, live_lbl, text)` which sets the label text and visibility and refreshes `row`'s tooltip; every station row carries `row._station` (the station dict).

- [ ] **Step 1: Write failing tests.** Create `tests/test_tooltips.py`:

```python
import unittest

from sqlch_gui.ui.tooltips import item_tooltip, station_tooltip


class TestItemTooltip(unittest.TestCase):
    def test_title_only(self):
        self.assertEqual(item_tooltip({"title": "Song"}), "Song")

    def test_no_title_is_none(self):
        self.assertIsNone(item_tooltip({"title": ""}))
        self.assertIsNone(item_tooltip({}))

    def test_metadata_line_skips_empty_parts(self):
        tip = item_tooltip({"title": "T", "artist": "A", "album": None,
                            "date": 1792108800, "duration": 125})
        self.assertEqual(tip, "T\nA · Oct 16, 2026 · 2:05")

    def test_description_after_blank_line(self):
        tip = item_tooltip({"title": "T", "artist": "A", "description": "About it"})
        self.assertEqual(tip, "T\nA\n\nAbout it")

    def test_description_truncated_to_300(self):
        tip = item_tooltip({"title": "T", "description": "x" * 400})
        desc = tip.split("\n\n", 1)[1]
        self.assertEqual(len(desc), 300)
        self.assertTrue(desc.endswith("…"))

    def test_folder_has_no_description(self):
        tip = item_tooltip({"title": "Show", "kind": "folder", "artist": "Net",
                            "description": "ignored"})
        self.assertEqual(tip, "Show\nNet")


class TestStationTooltip(unittest.TestCase):
    ST = {"name": "KEXP", "group": "Indie", "frequency": "90.3 FM"}

    def test_static(self):
        self.assertEqual(station_tooltip(self.ST), "KEXP\nIndie · 90.3")

    def test_live_line(self):
        self.assertEqual(station_tooltip(self.ST, "♫ Band — Song"),
                         "KEXP\nIndie · 90.3\n♫ Band — Song")

    def test_missing_group_and_freq(self):
        self.assertEqual(station_tooltip({"name": "X"}), "X\nUnsorted · 0.0")
```

Append to `tests/test_station_list.py` (a class using `_LibraryBackedTestCase`):

```python
class TestStationTooltips(_LibraryBackedTestCase):
    def test_row_tooltip_includes_live_text_when_set(self):
        library.add_url("Tip Station", "http://example.com/stream")
        sid = library.get_station_list()[0]["id"]
        panel = _make_panel()
        row, live_lbl, mini_eq = panel._rows_map[sid][0]
        self.assertTrue(row.get_tooltip_text().startswith("Tip Station\n"))
        panel._apply_probe(sid, "♫ Band — Song")
        self.assertTrue(row.get_tooltip_text().endswith("♫ Band — Song"))
        panel._apply_probe(sid, "")
        self.assertNotIn("Band", row.get_tooltip_text())
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/sqlch && uv run python -m unittest tests.test_tooltips tests.test_station_list 2>&1 | tail -12`
Expected: `ModuleNotFoundError: sqlch_gui.ui.tooltips` (and the station test fails or is skipped where `gi` is missing; say which).

- [ ] **Step 3: Implement.** Create `sqlch_gui/ui/tooltips.py`:

```python
"""Hover text for list rows. Pure functions: no GTK, so they test anywhere."""

from .timefmt import format_date, format_duration

DESCRIPTION_MAX = 300


def _freq(v) -> float:
    try:
        return float(str(v or "0").split()[0])
    except (ValueError, IndexError):
        return 0.0


def item_tooltip(item: dict) -> str | None:
    title = item.get("title")
    if not title:
        return None
    meta = " · ".join(x for x in (item.get("artist"), item.get("album"),
                                  format_date(item.get("date")),
                                  format_duration(item.get("duration"))) if x)
    lines = [title] + ([meta] if meta else [])
    desc = item.get("description")
    if desc and item.get("kind") != "folder":
        if len(desc) > DESCRIPTION_MAX:
            desc = desc[:DESCRIPTION_MAX - 1].rstrip() + "…"
        return "\n".join(lines) + "\n\n" + desc
    return "\n".join(lines)


def station_tooltip(station: dict, live_text: str = "") -> str:
    lines = [station.get("name") or "",
             f"{station.get('group') or 'Unsorted'} · {_freq(station.get('frequency')):.1f}"]
    if live_text:
        lines.append(live_text)
    return "\n".join(lines)
```

(The truncation test requires exactly 300 characters: `desc[:299].rstrip() + "…"` is 300 only if the 299th char is not whitespace; the test uses `"x" * 400`, so it holds. Keep `rstrip` so real text never ends in a space before the ellipsis.)

`source_pane.py` — add `from .tooltips import item_tooltip` to the imports and, in `_build_row` just before `return row`, add `row.set_tooltip_text(item_tooltip(item))`.

`station_list.py` — add `from .tooltips import station_tooltip`. In `_build_station_row`, before `return row, live_lbl, mini_eq`: `row._station = s` and `row.set_tooltip_text(station_tooltip(s))`. Add a method:

```python
    def _show_live(self, row, live_lbl, text):
        live_lbl.set_text(text)
        live_lbl.set_visible(bool(text))
        row.set_tooltip_text(station_tooltip(row._station, text))
```

Then replace each `live_lbl.set_text(text)` / `live_lbl.set_visible(...)` pair with `self._show_live(row, live_lbl, text)`: in `refresh` (the re-apply loop, keeping its `if text and s_id != self._active_id` guard), in `set_active`, and in `_apply_probe` (keeping its `if s_id != self._active_id` guard).

- [ ] **Step 4: Run to verify pass and lint**

Run: `cd ~/sqlch && uv run python -m unittest tests.test_tooltips tests.test_station_list tests.test_source_pane 2>&1 | tail -8 && uv run ruff check sqlch sqlch_gui`
Expected: PASS where `gi` exists. If GUI tests cannot run in this environment, say so explicitly and show that `tests.test_tooltips` passes and the files compile (`uv run python -m py_compile sqlch_gui/ui/station_list.py sqlch_gui/ui/source_pane.py`).

- [ ] **Step 5: Commit**

```bash
cd ~/sqlch && git add sqlch_gui/ui/tooltips.py sqlch_gui/ui/source_pane.py sqlch_gui/ui/station_list.py tests/test_tooltips.py tests/test_station_list.py
git commit -m "gui: hover tooltips on source rows and station rows" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: scrolling live label

**Files:**
- Create: `sqlch_gui/ui/scrollmath.py` (no GTK)
- Create: `sqlch_gui/ui/scroll_label.py`
- Modify: `sqlch_gui/ui/station_list.py` (`_build_station_row`)
- Test: `tests/test_scrollmath.py`

**Interfaces:**
- Produces: `scroll_offset(t: float, overflow: float, speed: float = 25.0, pause: float = 1.2) -> float` (0 when `overflow <= 0`; otherwise a ping-pong in `[0, overflow]`: wait `pause`, travel at `speed` px/s, wait `pause`, travel back, repeating). `ScrollLabel(Gtk.ScrolledWindow)` with `set_text(text)`, `get_text()`, and attribute `label` (the inner `Gtk.Label`, for CSS classes).
- Consumes: Task 2's `_show_live`, which calls `live_lbl.set_text` / `set_visible`.

- [ ] **Step 1: Write failing tests.** Create `tests/test_scrollmath.py`:

```python
import unittest

from sqlch_gui.ui.scrollmath import scroll_offset


class TestScrollOffset(unittest.TestCase):
    def test_no_overflow_is_zero(self):
        self.assertEqual(scroll_offset(5.0, 0), 0.0)
        self.assertEqual(scroll_offset(5.0, -3), 0.0)

    def test_pauses_at_start(self):
        self.assertEqual(scroll_offset(0.0, 100, speed=50, pause=1.0), 0.0)
        self.assertEqual(scroll_offset(0.9, 100, speed=50, pause=1.0), 0.0)

    def test_travels_at_speed_then_pauses_at_end(self):
        self.assertAlmostEqual(scroll_offset(2.0, 100, speed=50, pause=1.0), 50.0)
        self.assertEqual(scroll_offset(3.0, 100, speed=50, pause=1.0), 100.0)
        self.assertEqual(scroll_offset(3.9, 100, speed=50, pause=1.0), 100.0)

    def test_returns_and_loops(self):
        self.assertAlmostEqual(scroll_offset(5.0, 100, speed=50, pause=1.0), 50.0)
        self.assertEqual(scroll_offset(6.0, 100, speed=50, pause=1.0), 0.0)
        self.assertAlmostEqual(scroll_offset(8.0, 100, speed=50, pause=1.0), 50.0)

    def test_always_within_bounds(self):
        for i in range(0, 4000):
            v = scroll_offset(i / 100, 73.0)
            self.assertTrue(0.0 <= v <= 73.0)
```

(Timeline for overflow 100, speed 50, pause 1: 0–1 hold at 0; 1–3 forward; 3–4 hold at 100; 4–6 back; period 6.)

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/sqlch && uv run python -m unittest tests.test_scrollmath 2>&1 | tail -5`
Expected: `ModuleNotFoundError: sqlch_gui.ui.scrollmath`.

- [ ] **Step 3: Implement.** `sqlch_gui/ui/scrollmath.py`:

```python
def scroll_offset(t: float, overflow: float, speed: float = 25.0,
                  pause: float = 1.2) -> float:
    """Marquee position at time t: hold, travel to the far end, hold, travel back."""
    if overflow <= 0:
        return 0.0
    travel = overflow / speed
    phase = t % (2 * (pause + travel))
    if phase < pause:
        return 0.0
    phase -= pause
    if phase < travel:
        return phase * speed
    phase -= travel
    if phase < pause:
        return overflow
    phase -= pause
    return max(0.0, overflow - phase * speed)
```

`sqlch_gui/ui/scroll_label.py`:

```python
"""A one-line label that scrolls sideways when its text is wider than the space."""

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from .scrollmath import scroll_offset


class ScrollLabel(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__()
        # NEVER would clamp the adjustment; EXTERNAL scrolls without a bar
        self.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.NEVER)
        self.set_hexpand(True)
        self.set_propagate_natural_height(True)
        self.label = Gtk.Label(xalign=0.0)
        self.set_child(self.label)
        self._tick_id = 0
        self._t0 = None
        self.connect("map", self._on_map)
        self.connect("unmap", self._on_unmap)

    def set_text(self, text: str) -> None:
        self.label.set_text(text)
        self._t0 = None
        self.get_hadjustment().set_value(0)

    def get_text(self) -> str:
        return self.label.get_text()

    def _on_map(self, *_):
        if not self._tick_id:
            self._tick_id = self.add_tick_callback(self._tick)

    def _on_unmap(self, *_):
        if self._tick_id:
            self.remove_tick_callback(self._tick_id)
            self._tick_id = 0

    def _tick(self, _widget, clock):
        adj = self.get_hadjustment()
        overflow = adj.get_upper() - adj.get_page_size()
        if overflow <= 0:
            return True
        now = clock.get_frame_time() / 1e6
        if self._t0 is None:
            self._t0 = now
        adj.set_value(scroll_offset(now - self._t0, overflow))
        return True
```

`station_list.py` `_build_station_row`: replace the live label construction

```python
        live_lbl = Gtk.Label(xalign=0.0)
        live_lbl.add_css_class("station-live")
        live_lbl.set_ellipsize(3)
        live_lbl.set_visible(False)
```

with

```python
        live_lbl = ScrollLabel()
        live_lbl.label.add_css_class("station-live")
        live_lbl.set_visible(False)
```

and add `from .scroll_label import ScrollLabel` to the imports. Any other code that treats `live_lbl` as a `Gtk.Label` (grep `live_lbl` in `station_list.py` and its tests) must use only `set_text`, `get_text`, `set_visible`.

- [ ] **Step 4: Run to verify pass**

Run: `cd ~/sqlch && uv run python -m unittest tests.test_scrollmath tests.test_station_list tests.test_tooltips 2>&1 | tail -8 && uv run ruff check sqlch sqlch_gui`
Expected: PASS (GUI tests only where `gi` exists; otherwise report that and run `uv run python -m py_compile sqlch_gui/ui/scroll_label.py sqlch_gui/ui/station_list.py`). Do not claim the widget animates correctly unless it was actually run under GTK; say so plainly if it was not.

- [ ] **Step 5: Commit**

```bash
cd ~/sqlch && git add sqlch_gui/ui/scrollmath.py sqlch_gui/ui/scroll_label.py sqlch_gui/ui/station_list.py tests/test_scrollmath.py
git commit -m "gui: station live-track text scrolls inside its label" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-review

- Spec coverage: item field + podcasts + Jellyfin (Task 1); YouTube/others untouched; tooltip text functions and both wirings, live-tooltip refresh (Task 2); scrolling widget (Task 3); tests for each listed category (Tasks 1-3).
- Types: `item_tooltip`/`station_tooltip` signatures match their callers; `_show_live(row, live_lbl, text)` is used identically at all three call sites; `ScrollLabel.set_text/get_text/set_visible` cover every use of `live_lbl`.
- Risk: the visual behaviour of `ScrollLabel` can only be confirmed under a running GTK session (live check after deploy: a long ICY title should scroll, short ones stay still).
