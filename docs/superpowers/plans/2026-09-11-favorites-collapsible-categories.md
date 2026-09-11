# Favorites Section & Collapsible Categories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a starrable favorites concept and collapsible category headers to sqlch-gui's Station Library list (`sqlch_gui/ui/station_list.py`), both persisted to `library.json`.

**Architecture:** `library.py` gains a `favorite` bool field per station and a persisted `collapsed_groups` list. `banner.py`'s `RibbonBanner` gains optional self-toggling collapse behavior with a chevron and callback. `station_list.py` extracts its per-station row construction into a reusable helper, uses it to render a pinned "★ Favorites" section (in addition to normal category groups — a favorited station gets two row widgets, since a GTK widget can only have one parent), and wires collapse state into its existing search-filter predicate so an active search always overrides a collapsed category.

**Tech Stack:** Python, PyGObject (GTK4), unittest (existing test style: direct widget construction, no mocking of GTK itself).

## Global Constraints

- Scope is `sqlch_gui` only (the GUI's Station Library list). The Discover panel (`sqlch_gui/ui/discover.py`) and the TUI/CLI codepaths are untouched.
- No new files for persistence — favorite status and collapsed-group state both live in the existing `library.json`, read/written through `library.py`'s existing `_load_library`/`_save_library` helpers.
- No migration step — both new fields default cleanly for existing `library.json` files (same pattern as `group`/`bitrate`/`channels` backfilling in `get_station_list()`).
- No favorite/collapse controls in the right-click edit popover — the row star icon and banner chevron are the only entry points.
- Follow existing test conventions: real GTK widgets constructed directly in `unittest.TestCase`s (see `tests/test_gui_style.py`), no `Gtk.Application`/display setup, private methods called directly where that's the simplest way to drive behavior (e.g. `banner._on_click(...)`, `banner._on_draw(...)`).

---

## Task 1: `library.py` — favorite field and `set_favorite`

**Files:**
- Modify: `sqlch_gui/library.py:126-139` (`get_station_list`), and insert a new function after `set_group` (currently ending `sqlch_gui/library.py:212`).
- Create: `tests/test_library.py`

**Interfaces:**
- Produces: `library.set_favorite(station_id: str, is_favorite: bool) -> bool`. Each dict returned by `library.get_station_list()` now always has a `"favorite": bool` key (default `False`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_library.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlch_gui import library


class _LibraryBackedTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._lib_path = Path(self._tmp.name) / "library.json"
        self._freq_path = Path(self._tmp.name) / "freq_cache.json"
        self._lib_patch = patch.object(library, "LIBRARY_JSON", self._lib_path)
        self._freq_patch = patch.object(library, "FREQ_CACHE_JSON", self._freq_path)
        self._lib_patch.start()
        self._freq_patch.start()

    def tearDown(self):
        self._lib_patch.stop()
        self._freq_patch.stop()
        self._tmp.cleanup()


class TestFavorite(_LibraryBackedTestCase):
    def setUp(self):
        super().setUp()
        library.add_url("Test Station", "http://example.com/stream")
        self._station_id = library.get_station_list()[0]["id"]

    def test_favorite_defaults_false(self):
        station = library.get_station_list()[0]
        self.assertFalse(station["favorite"])

    def test_set_favorite_true_updates_station(self):
        self.assertTrue(library.set_favorite(self._station_id, True))
        station = library.get_station_list()[0]
        self.assertTrue(station["favorite"])

    def test_set_favorite_survives_reload(self):
        library.set_favorite(self._station_id, True)
        data = json.loads(self._lib_path.read_text())
        self.assertTrue(data["stations"][0]["favorite"])

    def test_set_favorite_false_clears_it(self):
        library.set_favorite(self._station_id, True)
        library.set_favorite(self._station_id, False)
        self.assertFalse(library.get_station_list()[0]["favorite"])

    def test_set_favorite_unknown_id_returns_false(self):
        self.assertFalse(library.set_favorite("no-such-id", True))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_library.py -v`
Expected: FAIL — `AttributeError: module 'sqlch_gui.library' has no attribute 'set_favorite'` (and `test_favorite_defaults_false` fails with `KeyError: 'favorite'`).

- [ ] **Step 3: Implement**

In `sqlch_gui/library.py`, inside `get_station_list()` (`sqlch_gui/library.py:126-139`), add the backfill next to the existing `channels` check:

```python
def get_station_list() -> list[dict]:
    """Return the list of all library stations with populated frequencies and fallback metrics."""
    lib = _load_library()
    stations = lib.get("stations", [])
    for s in stations:
        if not s.get("frequency"):
            s["frequency"] = _assign_frequency(s["id"])
        if "group" not in s:
            s["group"] = "Unsorted"
        if "bitrate" not in s:
            s["bitrate"] = None
        if "channels" not in s:
            s["channels"] = None
        if "favorite" not in s:
            s["favorite"] = False
    return stations
```

Add `set_favorite` right after `set_group` (`sqlch_gui/library.py:204-212`), before `backfill_freqs`:

```python
def set_favorite(station_id: str, is_favorite: bool) -> bool:
    """Mark or unmark a station as a favorite."""
    lib = _load_library()
    for s in lib["stations"]:
        if s["id"] == station_id:
            s["favorite"] = bool(is_favorite)
            _save_library(lib)
            return True
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_library.py -v`
Expected: PASS (all `TestFavorite` cases)

- [ ] **Step 5: Commit**

```bash
git add sqlch_gui/library.py tests/test_library.py
git commit -m "feat(sqlch-gui): add favorite field and set_favorite to library"
```

---

## Task 2: `library.py` — persisted collapsed-group state

**Files:**
- Modify: `sqlch_gui/library.py` — append after `backfill_freqs` (currently ending `sqlch_gui/library.py:226`).
- Modify: `tests/test_library.py` — add a new test class.

**Interfaces:**
- Consumes: `_load_library()`, `_save_library()` (existing private helpers).
- Produces: `library.get_collapsed_groups() -> list[str]`, `library.set_collapsed_groups(names: list[str]) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_library.py` (before the `if __name__ == "__main__":` line):

```python
class TestCollapsedGroups(_LibraryBackedTestCase):
    def test_defaults_to_empty_list(self):
        self.assertEqual(library.get_collapsed_groups(), [])

    def test_set_and_get_round_trip(self):
        library.set_collapsed_groups(["Rock", "News"])
        self.assertEqual(library.get_collapsed_groups(), ["Rock", "News"])

    def test_set_overwrites_previous_value(self):
        library.set_collapsed_groups(["Rock"])
        library.set_collapsed_groups(["News"])
        self.assertEqual(library.get_collapsed_groups(), ["News"])

    def test_persists_to_disk(self):
        library.set_collapsed_groups(["Jazz"])
        data = json.loads(self._lib_path.read_text())
        self.assertEqual(data["collapsed_groups"], ["Jazz"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_library.py -v -k CollapsedGroups`
Expected: FAIL — `AttributeError: module 'sqlch_gui.library' has no attribute 'get_collapsed_groups'`

- [ ] **Step 3: Implement**

Append to `sqlch_gui/library.py`:

```python


def get_collapsed_groups() -> list[str]:
    """Return the list of category group names currently collapsed in the UI."""
    lib = _load_library()
    return list(lib.get("collapsed_groups", []))


def set_collapsed_groups(names: list[str]):
    """Persist the full set of currently-collapsed category group names."""
    lib = _load_library()
    lib["collapsed_groups"] = list(names)
    _save_library(lib)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_library.py -v`
Expected: PASS (all cases in the file)

- [ ] **Step 5: Commit**

```bash
git add sqlch_gui/library.py tests/test_library.py
git commit -m "feat(sqlch-gui): persist collapsed category group state"
```

---

## Task 3: `banner.py` — collapsible `RibbonBanner`

**Files:**
- Modify: `sqlch_gui/ui/banner.py:1-40`
- Modify: `tests/test_gui_style.py` — extend `TestBannerWidgets` (`tests/test_gui_style.py:64-77`)

**Interfaces:**
- Produces: `RibbonBanner(text: str, gold: bool = False, collapsible: bool = False, collapsed: bool = False, on_toggle: Callable[[bool], None] | None = None)`. `RibbonBanner.set_collapsed(collapsed: bool) -> None`. Existing `RibbonBanner.set_text(text: str)` and `.label` (a `Gtk.Label`) are unchanged in meaning; `.label.get_text()` now includes a `"▾ "`/`"▸ "` prefix when `collapsible=True`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_gui_style.py`'s `TestBannerWidgets` class (after `test_ribbon_banner_is_a_box_with_engraved_label`, `tests/test_gui_style.py:65-77`):

```python
    def test_ribbon_banner_collapsible_starts_expanded_with_chevron(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from sqlch_gui.ui.banner import RibbonBanner
        b = RibbonBanner("news", collapsible=True)
        self.assertEqual(b.label.get_text(), "▾ NEWS")

    def test_ribbon_banner_collapsible_can_start_collapsed(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from sqlch_gui.ui.banner import RibbonBanner
        b = RibbonBanner("news", collapsible=True, collapsed=True)
        self.assertEqual(b.label.get_text(), "▸ NEWS")

    def test_ribbon_banner_click_toggles_and_calls_on_toggle(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from sqlch_gui.ui.banner import RibbonBanner
        toggled = []
        b = RibbonBanner("news", collapsible=True, on_toggle=toggled.append)

        b._on_click(None, 1, 0, 0)
        self.assertEqual(b.label.get_text(), "▸ NEWS")
        self.assertEqual(toggled, [True])

        b._on_click(None, 1, 0, 0)
        self.assertEqual(b.label.get_text(), "▾ NEWS")
        self.assertEqual(toggled, [True, False])

    def test_ribbon_banner_set_collapsed_updates_chevron(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from sqlch_gui.ui.banner import RibbonBanner
        b = RibbonBanner("news", collapsible=True)
        b.set_collapsed(True)
        self.assertEqual(b.label.get_text(), "▸ NEWS")

    def test_ribbon_banner_non_collapsible_has_no_chevron(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from sqlch_gui.ui.banner import RibbonBanner
        b = RibbonBanner("news")
        self.assertEqual(b.label.get_text(), "NEWS")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_gui_style.py -v -k collapsible`
Expected: FAIL — `TypeError: RibbonBanner.__init__() got an unexpected keyword argument 'collapsible'`

- [ ] **Step 3: Implement**

Replace `sqlch_gui/ui/banner.py:1-40` with:

```python
"""Section-rule headers, flat tag chips, and the drawer seam.

RibbonBanner and PennantTag were Cairo-drawn papercraft shapes (torn
ribbon tails, a cut-flag notch); they are now plain CSS-styled boxes.
TornSeparator still draws the drawer seam, but as a recessed hairline
groove with a short grab bar rather than a ragged tear.
"""

from typing import Callable

import cairo
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk
from .. import palette


def _hex_to_rgb_floats(hex_val: str) -> tuple[float, float, float]:
    h = hex_val.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return r, g, b


class RibbonBanner(Gtk.Box):
    """Section header: a hairline top-rule with a small engraved label,
    left-set. The rule IS the break -- no box frame around the group.

    When collapsible, a leading chevron shows expand/collapse state and a
    primary click anywhere on the banner toggles it, calling on_toggle
    with the new collapsed state.
    """

    _CHEVRON_OPEN = "▾ "
    _CHEVRON_CLOSED = "▸ "

    def __init__(
        self,
        text: str,
        gold: bool = False,
        collapsible: bool = False,
        collapsed: bool = False,
        on_toggle: Callable[[bool], None] | None = None,
    ):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_hexpand(True)
        self.add_css_class("section-rule")
        if gold:
            self.add_css_class("gold")
        self._text = text
        self._collapsible = collapsible
        self._collapsed = collapsed
        self._on_toggle = on_toggle
        self.label = Gtk.Label(xalign=0.0)
        self.label.set_hexpand(True)
        self.append(self.label)
        self._update_label()

        if collapsible:
            click = Gtk.GestureClick()
            click.set_button(Gdk.BUTTON_PRIMARY)
            click.connect("released", self._on_click)
            self.add_controller(click)

    def _update_label(self):
        prefix = ""
        if self._collapsible:
            prefix = self._CHEVRON_CLOSED if self._collapsed else self._CHEVRON_OPEN
        self.label.set_text(prefix + self._text.upper())

    def _on_click(self, gesture, n_press, x, y):
        self._collapsed = not self._collapsed
        self._update_label()
        if self._on_toggle:
            self._on_toggle(self._collapsed)

    def set_text(self, text: str):
        self._text = text
        self._update_label()

    def set_collapsed(self, collapsed: bool):
        self._collapsed = collapsed
        self._update_label()
```

(The rest of the file — `PennantTag` and `TornSeparator`, `sqlch_gui/ui/banner.py:42-121` in the original — is unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_gui_style.py -v`
Expected: PASS (all cases, including the pre-existing `TestBannerWidgets`/`TestPaletteDefaults`/`TestFlatStylesheet` ones — confirms the non-collapsible path is unchanged)

- [ ] **Step 5: Commit**

```bash
git add sqlch_gui/ui/banner.py tests/test_gui_style.py
git commit -m "feat(sqlch-gui): add collapsible chevron toggle to RibbonBanner"
```

---

## Task 4: `station_list.py` — extract row builder, add star toggle

**Files:**
- Modify: `sqlch_gui/ui/station_list.py:15-19` (add `_parse_freq`), `:105-179` (`refresh`), `:196-208` (`show_context_menu`'s local `_freq`)
- Create: `tests/test_station_list.py`

**Interfaces:**
- Consumes: `library.set_favorite` (Task 1), `library.get_station_list()` (existing, now includes `"favorite"`).
- Produces: `StationListPanel._build_station_row(s: dict) -> tuple[Gtk.Box, Gtk.Label, EqStrip]`, `StationListPanel.on_toggle_favorite(station_id: str, currently_favorite: bool) -> None`, module-level `_parse_freq(v) -> float` in `station_list.py`. `_rows_map` keeps its current shape this task: `dict[str, tuple[Gtk.Box, Gtk.Label, EqStrip]]` (list-per-id comes in Task 5).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_station_list.py`:

```python
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from sqlch_gui import library


def _make_panel():
    from sqlch_gui.ui.station_list import StationListPanel
    return StationListPanel(None)


class _LibraryBackedTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._lib_path = Path(self._tmp.name) / "library.json"
        self._freq_path = Path(self._tmp.name) / "freq_cache.json"
        self._lib_patch = patch.object(library, "LIBRARY_JSON", self._lib_path)
        self._freq_patch = patch.object(library, "FREQ_CACHE_JSON", self._freq_path)
        self._lib_patch.start()
        self._freq_patch.start()

    def tearDown(self):
        self._lib_patch.stop()
        self._freq_patch.stop()
        self._tmp.cleanup()


class TestStationRowStarButton(_LibraryBackedTestCase):
    def test_row_star_button_reflects_favorite_state(self):
        library.add_url("Test Station", "http://example.com/stream")
        sid = library.get_station_list()[0]["id"]
        panel = _make_panel()
        row, live_lbl, mini_eq = panel._rows_map[sid]
        star = row.get_first_child()
        self.assertIsInstance(star, Gtk.Button)
        self.assertEqual(star.get_icon_name(), "non-starred-symbolic")

    def test_clicking_star_toggles_favorite_and_refreshes(self):
        library.add_url("Test Station", "http://example.com/stream")
        sid = library.get_station_list()[0]["id"]
        panel = _make_panel()
        panel.on_toggle_favorite(sid, False)
        self.assertTrue(library.get_station_list()[0]["favorite"])
        row, live_lbl, mini_eq = panel._rows_map[sid]
        star = row.get_first_child()
        self.assertEqual(star.get_icon_name(), "starred-symbolic")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_station_list.py -v`
Expected: FAIL — `test_row_star_button_reflects_favorite_state` fails with `AssertionError: <Gtk.Label...> is not an instance of <class 'gi.repository.Gtk.Button'>` (the row's first child is currently the frequency label, no star button exists yet); `test_clicking_star_toggles_favorite_and_refreshes` fails with `AttributeError: 'StationListPanel' object has no attribute 'on_toggle_favorite'`.

- [ ] **Step 3: Implement**

In `sqlch_gui/ui/station_list.py`, add `_parse_freq` next to `format_live_text` (`sqlch_gui/ui/station_list.py:15-19`):

```python
def format_live_text(artist: str | None, title: str | None) -> str:
    parts = [p for p in (artist, title) if p]
    if not parts:
        return ""
    return "♫ " + " — ".join(parts)


def _parse_freq(v) -> float:
    try:
        return float(str(v or "0").split()[0])
    except (ValueError, IndexError):
        return 0.0
```

Replace `refresh()` (`sqlch_gui/ui/station_list.py:105-179`) with:

```python
    def refresh(self):
        """Rebuild entire listing catalog mapping."""
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)
        self._rows_map.clear()

        stations = library.get_station_list()

        # Sort catalog entries cleanly by grouping parameters
        groups = {}
        for s in stations:
            g = s.get("group", "Unsorted")
            groups.setdefault(g, []).append(s)

        for g_name in sorted(groups.keys()):
            # Category header: a hairline section rule spanning the list.
            self.list_box.append(RibbonBanner(g_name))

            for s in sorted(groups[g_name], key=lambda x: _parse_freq(x.get("frequency"))):
                row, live_lbl, mini_eq = self._build_station_row(s)
                self.list_box.append(row)
                self._rows_map[s["id"]] = (row, live_lbl, mini_eq)

        # Re-apply any already-probed live lines to the rebuilt rows
        for s_id, (row, live_lbl, mini_eq) in self._rows_map.items():
            text = self._probe_titles.get(s_id, "")
            if text and s_id != self._active_id:
                live_lbl.set_text(text)
                live_lbl.set_visible(True)
            if s_id == self._active_id:
                row.add_css_class("active")
                mini_eq.set_visible(True)
                mini_eq.set_active(True)

    def _build_station_row(self, s: dict) -> tuple[Gtk.Box, Gtk.Label, EqStrip]:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.add_css_class("station-row")

        btn_star = Gtk.Button(
            icon_name="starred-symbolic" if s.get("favorite") else "non-starred-symbolic"
        )
        btn_star.add_css_class("control-btn")
        btn_star.set_tooltip_text("Toggle favorite")
        btn_star.connect(
            "clicked",
            lambda b, sid=s["id"], fav=s.get("favorite", False): self.on_toggle_favorite(sid, fav),
        )

        freq_lbl = Gtk.Label()
        freq_lbl.add_css_class("station-freq")
        freq_lbl.set_text(f"{_parse_freq(s.get('frequency')):.1f}")

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        body.set_hexpand(True)
        name_lbl = Gtk.Label(label=s.get("name"), xalign=0.0)
        name_lbl.set_ellipsize(3)  # Pango.EllipsizeMode.END
        live_lbl = Gtk.Label(xalign=0.0)
        live_lbl.add_css_class("station-live")
        live_lbl.set_ellipsize(3)
        live_lbl.set_visible(False)
        body.append(name_lbl)
        body.append(live_lbl)

        mini_eq = EqStrip(n_beads=3, width=18, height=11)
        mini_eq.set_valign(Gtk.Align.CENTER)
        mini_eq.set_visible(False)

        tag_pennant = PennantTag(s.get("group", "Unsorted"))
        tag_pennant.set_valign(Gtk.Align.CENTER)

        row.append(btn_star)
        row.append(freq_lbl)
        row.append(body)
        row.append(mini_eq)
        row.append(tag_pennant)

        # Secondary click binding context setup
        click_gesture = Gtk.GestureClick()
        click_gesture.set_button(0)
        click_gesture.connect(
            "released", lambda g, n, x, y, st=s: self.on_row_clicked(g, n, x, y, st)
        )
        row.add_controller(click_gesture)

        return row, live_lbl, mini_eq

    def on_toggle_favorite(self, station_id: str, currently_favorite: bool):
        library.set_favorite(station_id, not currently_favorite)
        self.refresh()
```

Note the `colors = palette.load()` local variable from the original `refresh()` is dropped — it was unused (dead code left over from an earlier version).

In `show_context_menu` (`sqlch_gui/ui/station_list.py:188-228`), remove the local nested `_freq` def and use the module-level one instead:

```python
        ent_edit_freq = Gtk.Entry(text=f"{_parse_freq(station.get('frequency')):.1f}")
```

(delete the `def _freq(v): ...` block that preceded it, `sqlch_gui/ui/station_list.py:198-202`)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_station_list.py tests/test_gui_style.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sqlch_gui/ui/station_list.py tests/test_station_list.py
git commit -m "feat(sqlch-gui): extract station row builder, add favorite star toggle"
```

---

## Task 5: `station_list.py` — pinned Favorites section

**Files:**
- Modify: `sqlch_gui/ui/station_list.py` — constants near `sqlch_gui/ui/station_list.py:11-13`, `refresh()`, `set_active()` (`sqlch_gui/ui/station_list.py:255-269`), `_apply_probe()` (`sqlch_gui/ui/station_list.py:326-336`)
- Modify: `tests/test_station_list.py`

**Interfaces:**
- Consumes: `StationListPanel._build_station_row` (Task 4).
- Produces: `StationListPanel._append_group_rows(group_name: str, stations: list[dict], gold: bool = False) -> None`. `_rows_map` shape changes to `dict[str, list[tuple[Gtk.Box, Gtk.Label, EqStrip]]]` — a list per station id, since a favorited station gets two row widgets. Module-level `FAVORITES_GROUP = "★ Favorites"` in `station_list.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_station_list.py` (before `if __name__ == "__main__":`):

```python
def _iter_rows(list_box):
    row = list_box.get_first_child()
    while row is not None:
        yield row
        row = row.get_next_sibling()


def _is_banner(row):
    from sqlch_gui.ui.banner import RibbonBanner
    return isinstance(row.get_child(), RibbonBanner)


def _row_children(row):
    children = []
    child = row.get_child().get_first_child()
    while child is not None:
        children.append(child)
        child = child.get_next_sibling()
    return children


def _station_name(row):
    _star, _freq, body, *_rest = _row_children(row)
    return body.get_first_child().get_text()


class TestFavoritesSection(_LibraryBackedTestCase):
    def _add(self, name, url):
        library.add_url(name, url)
        return library.get_station_list()[-1]["id"]

    def test_no_favorites_section_when_none_favorited(self):
        self._add("Alpha", "http://a")
        panel = _make_panel()
        banners = [
            row.get_child().label.get_text()
            for row in _iter_rows(panel.list_box)
            if _is_banner(row)
        ]
        self.assertNotIn("★ FAVORITES", banners)

    def test_favorites_section_appears_first_when_populated(self):
        sid = self._add("Zeta", "http://z")
        library.set_favorite(sid, True)
        panel = _make_panel()
        first_row = panel.list_box.get_first_child()
        self.assertEqual(first_row.get_child().label.get_text(), "★ FAVORITES")

    def test_favorited_station_has_two_row_entries(self):
        sid = self._add("Zeta", "http://z")
        library.set_favorite(sid, True)
        panel = _make_panel()
        self.assertEqual(len(panel._rows_map[sid]), 2)

    def test_non_favorited_station_has_one_row_entry(self):
        sid = self._add("Alpha", "http://a")
        panel = _make_panel()
        self.assertEqual(len(panel._rows_map[sid]), 1)

    def test_favorites_sorted_alphabetically(self):
        sid_z = self._add("Zeta", "http://z")
        sid_a = self._add("Alpha", "http://a")
        library.set_favorite(sid_z, True)
        library.set_favorite(sid_a, True)
        panel = _make_panel()
        fav_banner = panel.list_box.get_first_child()
        first_station_row = fav_banner.get_next_sibling()
        second_station_row = first_station_row.get_next_sibling()
        self.assertEqual(_station_name(first_station_row), "Alpha")
        self.assertEqual(_station_name(second_station_row), "Zeta")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_station_list.py -v -k Favorites`
Expected: FAIL — `AssertionError: 2 != 1` on `test_favorited_station_has_two_row_entries` (no Favorites section built yet), and `test_favorites_section_appears_first_when_populated` fails since the first row is the station's own category banner.

- [ ] **Step 3: Implement**

Add `FAVORITES_GROUP` next to the other module constants (`sqlch_gui/ui/station_list.py:11-13`):

```python
PROBE_STALE_SECS = 45
PROBE_TICK_SECS = 60
PROBE_WORKERS = 4
FAVORITES_GROUP = "★ Favorites"
```

Replace `refresh()` (the version from Task 4) with:

```python
    def refresh(self):
        """Rebuild entire listing catalog mapping."""
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)
        self._rows_map.clear()

        stations = library.get_station_list()

        # Sort catalog entries cleanly by grouping parameters
        groups = {}
        for s in stations:
            g = s.get("group", "Unsorted")
            groups.setdefault(g, []).append(s)

        favorites = sorted(
            (s for s in stations if s.get("favorite")),
            key=lambda s: (s.get("name") or "").lower(),
        )
        if favorites:
            self._append_group_rows(FAVORITES_GROUP, favorites, gold=True)

        for g_name in sorted(groups.keys()):
            self._append_group_rows(
                g_name,
                sorted(groups[g_name], key=lambda x: _parse_freq(x.get("frequency"))),
            )

        # Re-apply any already-probed live lines to the rebuilt rows
        for s_id, entries in self._rows_map.items():
            text = self._probe_titles.get(s_id, "")
            for row, live_lbl, mini_eq in entries:
                if text and s_id != self._active_id:
                    live_lbl.set_text(text)
                    live_lbl.set_visible(True)
                if s_id == self._active_id:
                    row.add_css_class("active")
                    mini_eq.set_visible(True)
                    mini_eq.set_active(True)

    def _append_group_rows(self, group_name: str, stations: list[dict], gold: bool = False):
        # Category header: a hairline section rule spanning the list.
        self.list_box.append(RibbonBanner(group_name, gold=gold))
        for s in stations:
            row, live_lbl, mini_eq = self._build_station_row(s)
            self.list_box.append(row)
            self._rows_map.setdefault(s["id"], []).append((row, live_lbl, mini_eq))
```

Replace `set_active()` (`sqlch_gui/ui/station_list.py:255-269`):

```python
    def set_active(self, active_id: str | None, icy_artist: str | None = None, icy_title: str | None = None):
        self._active_id = active_id
        for s_id, entries in self._rows_map.items():
            for row, live_lbl, mini_eq in entries:
                if s_id == active_id:
                    row.add_css_class("active")
                    mini_eq.set_visible(True)
                    mini_eq.set_active(True)
                    text = format_live_text(icy_artist, icy_title) or self._probe_titles.get(s_id, "")
                else:
                    row.remove_css_class("active")
                    mini_eq.set_active(False)
                    mini_eq.set_visible(False)
                    text = self._probe_titles.get(s_id, "")
                live_lbl.set_text(text)
                live_lbl.set_visible(bool(text))
```

Replace `_apply_probe()` (`sqlch_gui/ui/station_list.py:326-336`):

```python
    def _apply_probe(self, s_id: str, text: str) -> bool:
        if text:
            self._probe_titles[s_id] = text
        else:
            self._probe_titles.pop(s_id, None)
        for row, live_lbl, mini_eq in self._rows_map.get(s_id, []):
            if s_id != self._active_id:
                live_lbl.set_text(text)
                live_lbl.set_visible(bool(text))
        return False
```

Also update `_probe_all()`'s station filter (`sqlch_gui/ui/station_list.py:295-297`) — no change needed, it already filters `library.get_station_list()` by id, unrelated to `_rows_map`'s shape.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_station_list.py tests/test_gui_style.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sqlch_gui/ui/station_list.py tests/test_station_list.py
git commit -m "feat(sqlch-gui): render pinned Favorites section in station list"
```

---

## Task 6: `station_list.py` — collapsible categories

**Files:**
- Modify: `sqlch_gui/ui/station_list.py` — `__init__` (`sqlch_gui/ui/station_list.py:65-71`), `_append_group_rows` (Task 5), `filter_station_rows` (`sqlch_gui/ui/station_list.py:74-100`)
- Modify: `tests/test_station_list.py`

**Interfaces:**
- Consumes: `library.get_collapsed_groups`/`set_collapsed_groups` (Task 2), `RibbonBanner(..., collapsible=, collapsed=, on_toggle=)` (Task 3), `_append_group_rows` (Task 5).
- Produces: `StationListPanel.on_toggle_group(group_name: str, collapsed: bool) -> None`. `self._collapsed_groups: set[str]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_station_list.py` (before `if __name__ == "__main__":`):

```python
class TestCollapsibleCategories(_LibraryBackedTestCase):
    def _add(self, name, url, group=None):
        library.add_url(name, url)
        sid = library.get_station_list()[-1]["id"]
        if group:
            library.set_group(sid, group)
        return sid

    def test_group_banner_starts_expanded(self):
        self._add("Alpha", "http://a", group="Rock")
        panel = _make_panel()
        banner_row = next(r for r in _iter_rows(panel.list_box) if _is_banner(r))
        self.assertEqual(banner_row.get_child().label.get_text(), "▾ ROCK")

    def test_toggling_group_hides_its_rows_and_persists(self):
        self._add("Alpha", "http://a", group="Rock")
        panel = _make_panel()
        panel.on_toggle_group("Rock", True)
        self.assertIn("Rock", panel._collapsed_groups)
        self.assertEqual(library.get_collapsed_groups(), ["Rock"])
        station_row = next(r for r in _iter_rows(panel.list_box) if not _is_banner(r))
        self.assertFalse(panel.filter_station_rows(station_row))

    def test_expanding_group_shows_rows_again(self):
        self._add("Alpha", "http://a", group="Rock")
        panel = _make_panel()
        panel.on_toggle_group("Rock", True)
        panel.on_toggle_group("Rock", False)
        self.assertEqual(library.get_collapsed_groups(), [])
        station_row = next(r for r in _iter_rows(panel.list_box) if not _is_banner(r))
        self.assertTrue(panel.filter_station_rows(station_row))

    def test_collapsed_state_loaded_on_construction(self):
        library.set_collapsed_groups(["Rock"])
        self._add("Alpha", "http://a", group="Rock")
        panel = _make_panel()
        banner_row = next(r for r in _iter_rows(panel.list_box) if _is_banner(r))
        self.assertEqual(banner_row.get_child().label.get_text(), "▸ ROCK")
        station_row = next(r for r in _iter_rows(panel.list_box) if not _is_banner(r))
        self.assertFalse(panel.filter_station_rows(station_row))

    def test_search_overrides_collapse(self):
        self._add("Alpha", "http://a", group="Rock")
        panel = _make_panel()
        panel.on_toggle_group("Rock", True)
        panel.filter_entry.set_text("alpha")
        station_row = next(r for r in _iter_rows(panel.list_box) if not _is_banner(r))
        self.assertTrue(panel.filter_station_rows(station_row))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_station_list.py -v -k Collapsible`
Expected: FAIL — `test_group_banner_starts_expanded` fails (`"ROCK" != "▾ ROCK"`, current `_append_group_rows` builds a plain non-collapsible `RibbonBanner`), `on_toggle_group` doesn't exist yet.

- [ ] **Step 3: Implement**

In `__init__` (`sqlch_gui/ui/station_list.py:65-71`), add the collapsed-groups state next to the other instance state:

```python
        self._rows_map = {}
        self._active_id = None
        self._probe_titles: dict[str, str] = {}
        self._probe_running = False
        self._abort_probes = threading.Event()
        self._last_probe = 0.0
        self._collapsed_groups: set[str] = set(library.get_collapsed_groups())
        GLib.timeout_add_seconds(PROBE_TICK_SECS, self._probe_tick)
        self.refresh()
```

Replace `_append_group_rows` (from Task 5) to wire collapsibility and tag each row with its group:

```python
    def _append_group_rows(self, group_name: str, stations: list[dict], gold: bool = False):
        # Category header: a hairline section rule spanning the list.
        banner = RibbonBanner(
            group_name,
            gold=gold,
            collapsible=True,
            collapsed=group_name in self._collapsed_groups,
            on_toggle=lambda collapsed, g=group_name: self.on_toggle_group(g, collapsed),
        )
        self.list_box.append(banner)
        for s in stations:
            row, live_lbl, mini_eq = self._build_station_row(s)
            row._group_name = group_name
            self.list_box.append(row)
            self._rows_map.setdefault(s["id"], []).append((row, live_lbl, mini_eq))

    def on_toggle_group(self, group_name: str, collapsed: bool):
        if collapsed:
            self._collapsed_groups.add(group_name)
        else:
            self._collapsed_groups.discard(group_name)
        library.set_collapsed_groups(sorted(self._collapsed_groups))
        self.list_box.invalidate_filter()
```

Replace `filter_station_rows` (`sqlch_gui/ui/station_list.py:74-100`):

```python
    def filter_station_rows(self, row) -> bool:
        search_text = self.filter_entry.get_text().lower().strip()
        child = row.get_child()

        if not search_text:
            if isinstance(child, RibbonBanner):
                return True
            return getattr(child, "_group_name", None) not in self._collapsed_groups

        # Section-rule headers never participate in filtering.
        if isinstance(child, RibbonBanner):
            return False
        # Let explicit structural heading text rows through without suppression
        if not isinstance(child, Gtk.Box):
            return True

        # Extract textual tags or names hidden in sub-elements
        for widget in child:
            if isinstance(widget, PennantTag):  # Group tag pennant
                if search_text in widget.label.get_text().lower():
                    return True
            elif isinstance(widget, Gtk.Box):  # Primary center box
                for label in widget:
                    if isinstance(label, Gtk.Label) and search_text in label.get_text().lower():
                        return True
            elif isinstance(widget, Gtk.Label):  # Side info chips
                if search_text in widget.get_text().lower():
                    return True

        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_station_list.py tests/test_gui_style.py tests/test_library.py -v`
Expected: PASS (full set from all six tasks)

- [ ] **Step 5: Commit**

```bash
git add sqlch_gui/ui/station_list.py tests/test_station_list.py
git commit -m "feat(sqlch-gui): make category headers collapsible, persisted"
```

---

## Final check

Run the full test suite to confirm nothing else regressed:

```bash
python -m pytest tests/ -v
```

Expected: PASS across the board, including the pre-existing `test_curation_db.py`, `test_icy_parse.py`, `test_icy_probe_move.py`, `test_radiobrowser.py`, `test_recorder.py`.

Manually verify in the running app (`sqlch-gui`) per the design doc's Testing section: star/unstar a station, restart the app and confirm favorite + collapse state survived, search over a collapsed category and confirm matches surface, and play a favorited station from both its rows and confirm both show the active/eq state.
