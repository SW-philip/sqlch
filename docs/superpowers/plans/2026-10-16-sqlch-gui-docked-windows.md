# sqlch-gui docked windows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Library/Discover slide-out drawer with separate fade-toggled layer-shell windows that drag and magnetically snap to Now Playing.

**Architecture:** Pure geometry (`ui/dock.py`) and persistence (`ui/dock_state.py`) are GTK-free and unit-tested. `DockedWindow` is a layer-shell window (anchored TOP+LEFT, positioned by margins) hosting an existing panel under a drag-handle strip. `DockManager` owns the windows, computes layout from state + Now Playing's rect, and handles toggle/drag-end. `SqlchPopupWindow` keeps only Now Playing + daemon loop.

**Tech Stack:** Python 3, GTK4, gtk4-layer-shell, `unittest`.

## Global Constraints

- Repo is `~/sqlch` (branch `main`); run tests from there: `python -m unittest tests.<module> -v`.
- Colors come from `palette` through `_build_css` in `sqlch_gui/ui/common.py`; no hardcoded hex.
- Comments only where the WHY is non-obvious.
- Commits: lowercase one-liner `sqlch-gui: what`, ending with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Spec: `docs/superpowers/specs/2026-10-16-sqlch-gui-docked-windows-design.md`. Snap distance 20 px; fade ~160 ms; state file `~/.local/state/sqlch-gui/windows.json`; panel width 320.
- `.popup-window` has CSS margin `2px 10px 10px 2px` (shadow room), so a surface rect includes ~12 px of transparent margin between visible cards. `DOCK_GAP = -8` overlaps surfaces to leave a ~4 px visual gap.
- Panels `StationListPanel`/`DiscoverPanel` already exist and are reused unchanged, except `StationListPanel.on_shown/abort_probes` get called by the manager.

## File Structure

- Create `sqlch_gui/ui/dock.py` — Rect + `touches`, `snap`, `clamp`, `default_dock`.
- Create `sqlch_gui/ui/dock_state.py` — load/save/sanitize window state.
- Create `sqlch_gui/ui/dock_window.py` — `DockedWindow`.
- Create `sqlch_gui/ui/dock_manager.py` — `DockManager`.
- Modify `sqlch_gui/__init__.py` — add `XDG_STATE`.
- Modify `sqlch_gui/ui/controls.py` — `NavColumn` independent toggles.
- Modify `sqlch_gui/ui/window.py` — remove drawer, use `DockManager`.
- Modify `sqlch_gui/ui/common.py` — `.dock-handle`/`.dock-title`/`.dock-close` CSS.
- Modify `sqlch_gui/ui/banner.py` — delete `TornSeparator` (only if unused after Task 5).
- Tests: `tests/test_dock.py`, `tests/test_dock_state.py`, `tests/test_nav_column.py`.

---

### Task 1: Dock geometry

**Files:**
- Create: `sqlch_gui/ui/dock.py`
- Test: `tests/test_dock.py`

**Interfaces:**
- Produces:
  - `Rect(x, y, w, h)` NamedTuple with `.right`, `.bottom`, `.moved(dx, dy) -> Rect`
  - `DOCK_GAP = -8`, `SNAP_DIST = 20`
  - `touches(a: Rect, b: Rect, gap: int = DOCK_GAP, tol: int = 2) -> bool`
  - `snap(rect, others: list[Rect], dist: int = SNAP_DIST, gap: int = DOCK_GAP) -> Rect`
  - `clamp(rect, mon_w: int, mon_h: int) -> Rect`
  - `default_dock(np_rect: Rect, items: list[tuple[str, int]], gap: int = DOCK_GAP) -> dict[str, Rect]` — items are `(name, width)` ordered nearest-to-Now-Playing first; result rects are top-aligned with `np_rect`, same height.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dock.py
import unittest

from sqlch_gui.ui.dock import (
    DOCK_GAP, Rect, clamp, default_dock, snap, touches,
)

NP = Rect(1000, 48, 290, 500)
FLUSH_X = NP.x + DOCK_GAP - 320   # left edge of a 320-wide window flush against NP


class TestSnap(unittest.TestCase):
    def test_snaps_edge_and_top_within_dist(self):
        r = snap(Rect(FLUSH_X + 8, 60, 320, 500), [NP], 20)
        self.assertEqual((r.x, r.y), (FLUSH_X, 48))

    def test_outside_dist_unchanged(self):
        r = Rect(FLUSH_X - 60, 60, 320, 500)
        self.assertEqual(snap(r, [NP], 20), r)

    def test_no_vertical_overlap_no_side_snap(self):
        r = Rect(FLUSH_X + 8, 2000, 320, 500)
        self.assertEqual(snap(r, [NP], 20), r)

    def test_bottom_align(self):
        r = snap(Rect(FLUSH_X + 3, 48 + 500 - 320 + 10, 320, 320), [NP], 20)
        self.assertEqual(r.bottom, NP.bottom)

    def test_stack_below(self):
        r = snap(Rect(1005, NP.bottom + DOCK_GAP + 9, 290, 200), [NP], 20)
        self.assertEqual(r.y, NP.bottom + DOCK_GAP)
        self.assertEqual(r.x, 1000)   # left-aligned while stacked

    def test_snaps_to_nearest_of_several(self):
        far = Rect(0, 48, 320, 500)
        r = snap(Rect(FLUSH_X + 5, 48, 320, 500), [far, NP], 20)
        self.assertEqual(r.x, FLUSH_X)


class TestTouches(unittest.TestCase):
    def test_flush_touches(self):
        self.assertTrue(touches(Rect(FLUSH_X, 48, 320, 500), NP))

    def test_apart_does_not(self):
        self.assertFalse(touches(Rect(FLUSH_X - 40, 48, 320, 500), NP))


class TestClampAndDefault(unittest.TestCase):
    def test_clamp_keeps_onscreen(self):
        self.assertEqual(clamp(Rect(-50, 900, 320, 300), 1920, 1080), Rect(0, 780, 320, 300))

    def test_clamp_oversize_pins_origin(self):
        self.assertEqual(clamp(Rect(10, 10, 3000, 300), 1920, 1080).x, 0)

    def test_default_dock_chains_leftward(self):
        d = default_dock(NP, [("library", 320), ("discover", 320)])
        self.assertEqual(d["library"], Rect(FLUSH_X, 48, 320, 500))
        self.assertEqual(d["discover"].x, d["library"].x + DOCK_GAP - 320)

    def test_default_dock_skips_missing(self):
        d = default_dock(NP, [("discover", 320)])
        self.assertEqual(d["discover"].x, FLUSH_X)
        self.assertNotIn("library", d)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ~/sqlch && python -m unittest tests.test_dock -v`
Expected: ImportError (`sqlch_gui.ui.dock` missing).

- [ ] **Step 3: Implement**

```python
# sqlch_gui/ui/dock.py
"""Pure rectangle math for docking the Library/Discover windows to Now
Playing. No GTK: positions are layer-shell margins in monitor pixels."""

from typing import NamedTuple

# .popup-window carries ~12px of transparent shadow margin between two
# adjacent cards; overlapping the surfaces by 8px leaves a ~4px visual gap.
DOCK_GAP = -8
SNAP_DIST = 20


class Rect(NamedTuple):
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    def moved(self, dx: int, dy: int) -> "Rect":
        return Rect(self.x + dx, self.y + dy, self.w, self.h)


def _v_overlap(a: Rect, b: Rect, slack: int = 0) -> bool:
    return a.y < b.bottom + slack and a.bottom > b.y - slack


def _h_overlap(a: Rect, b: Rect, slack: int = 0) -> bool:
    return a.x < b.right + slack and a.right > b.x - slack


def _side_adjacent(a: Rect, b: Rect, gap: int, tol: int) -> bool:
    return _v_overlap(a, b) and (
        abs(a.x - (b.right + gap)) <= tol or abs(a.right - (b.x - gap)) <= tol)


def _stacked(a: Rect, b: Rect, gap: int, tol: int) -> bool:
    return _h_overlap(a, b) and (
        abs(a.y - (b.bottom + gap)) <= tol or abs(a.bottom - (b.y - gap)) <= tol)


def touches(a: Rect, b: Rect, gap: int = DOCK_GAP, tol: int = 2) -> bool:
    return _side_adjacent(a, b, gap, tol) or _stacked(a, b, gap, tol)


def _pick(best, d, dist):
    if abs(d) <= dist and (best is None or abs(d) < abs(best)):
        return d
    return best


def snap(rect: Rect, others: list[Rect], dist: int = SNAP_DIST,
         gap: int = DOCK_GAP) -> Rect:
    """Snap each axis independently to the nearest candidate edge within
    `dist`. X first; top/bottom alignment only counts against windows that
    are side-adjacent after the X move, so a window can't align to something
    it isn't next to."""
    dx = None
    for o in others:
        if _v_overlap(rect, o, dist):
            dx = _pick(dx, o.right + gap - rect.x, dist)
            dx = _pick(dx, o.x - gap - rect.right, dist)
        if _h_overlap(rect, o, dist):
            dx = _pick(dx, o.x - rect.x, dist)
            dx = _pick(dx, o.right - rect.right, dist)
    rect = rect.moved(dx or 0, 0)

    dy = None
    for o in others:
        if _h_overlap(rect, o, dist):
            dy = _pick(dy, o.bottom + gap - rect.y, dist)
            dy = _pick(dy, o.y - gap - rect.bottom, dist)
        if _side_adjacent(rect, o, gap, dist):
            dy = _pick(dy, o.y - rect.y, dist)
            dy = _pick(dy, o.bottom - rect.bottom, dist)
    return rect.moved(0, dy or 0)


def clamp(rect: Rect, mon_w: int, mon_h: int) -> Rect:
    x = max(0, min(rect.x, mon_w - rect.w))
    y = max(0, min(rect.y, mon_h - rect.h))
    return Rect(x, y, rect.w, rect.h)


def default_dock(np_rect: Rect, items: list[tuple[str, int]],
                 gap: int = DOCK_GAP) -> dict[str, Rect]:
    out: dict[str, Rect] = {}
    edge = np_rect.x
    for name, w in items:
        edge = edge - gap - w
        out[name] = Rect(edge, np_rect.y, w, np_rect.h)
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd ~/sqlch && python -m unittest tests.test_dock -v`
Expected: all PASS. If `test_stack_below` fails on x, it means the dx pass is not left-aligning stacked windows — fix the `_h_overlap` branch, not the test.

- [ ] **Step 5: Commit**

```bash
cd ~/sqlch && git add sqlch_gui/ui/dock.py tests/test_dock.py && git commit -m "sqlch-gui: dock geometry (snap, clamp, default chain)"
```

---

### Task 2: Window state persistence

**Files:**
- Modify: `sqlch_gui/__init__.py` (add after the `XDG_DATA` line)
- Create: `sqlch_gui/ui/dock_state.py`
- Test: `tests/test_dock_state.py`

**Interfaces:**
- Produces:
  - `XDG_STATE` in `sqlch_gui` (`$XDG_STATE_HOME` or `~/.local/state`)
  - `NAMES = ("library", "discover")` (also the nearest-to-NP-first dock order)
  - State shape: `{name: {"open": bool, "placed": None | {"mode": "np", "dx": int, "dy": int} | {"mode": "free", "x": int, "y": int}}}`
  - `default_state() -> dict`, `load(path=STATE_PATH) -> dict` (always returns a full valid state), `save(state, path=STATE_PATH) -> None`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dock_state.py
import json
import pathlib
import tempfile
import unittest

from sqlch_gui.ui import dock_state


class TestDockState(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.path = self.tmp / "sub" / "windows.json"

    def test_missing_file_gives_defaults(self):
        self.assertEqual(dock_state.load(self.path), dock_state.default_state())

    def test_round_trip(self):
        s = dock_state.default_state()
        s["library"] = {"open": True, "placed": {"mode": "np", "dx": -330, "dy": 12}}
        s["discover"] = {"open": False, "placed": {"mode": "free", "x": 40, "y": 60}}
        dock_state.save(s, self.path)
        self.assertEqual(dock_state.load(self.path), s)

    def test_corrupt_file_gives_defaults(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json")
        self.assertEqual(dock_state.load(self.path), dock_state.default_state())

    def test_bad_entries_are_sanitized_individually(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({
            "library": {"open": True, "placed": {"mode": "np", "dx": "x"}},
            "discover": {"open": True, "placed": {"mode": "free", "x": 5, "y": 6}},
            "bogus": {"open": True},
        }))
        s = dock_state.load(self.path)
        self.assertEqual(s["library"], {"open": True, "placed": None})
        self.assertEqual(s["discover"]["placed"], {"mode": "free", "x": 5, "y": 6})
        self.assertNotIn("bogus", s)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ~/sqlch && python -m unittest tests.test_dock_state -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

In `sqlch_gui/__init__.py` after the `XDG_DATA = ...` line add:

```python
XDG_STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
```

```python
# sqlch_gui/ui/dock_state.py
"""Persisted open/placement state for the docked Library/Discover windows."""

import json
from pathlib import Path

from .. import XDG_STATE

STATE_PATH = XDG_STATE / "sqlch-gui" / "windows.json"
NAMES = ("library", "discover")


def default_state() -> dict:
    return {n: {"open": False, "placed": None} for n in NAMES}


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _placed(p):
    if not isinstance(p, dict):
        return None
    if p.get("mode") == "np" and _int(p.get("dx")) and _int(p.get("dy")):
        return {"mode": "np", "dx": p["dx"], "dy": p["dy"]}
    if p.get("mode") == "free" and _int(p.get("x")) and _int(p.get("y")):
        return {"mode": "free", "x": p["x"], "y": p["y"]}
    return None


def load(path: Path = STATE_PATH) -> dict:
    state = default_state()
    try:
        raw = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return state
    if not isinstance(raw, dict):
        return state
    for name in NAMES:
        entry = raw.get(name)
        if isinstance(entry, dict):
            state[name] = {"open": entry.get("open") is True,
                           "placed": _placed(entry.get("placed"))}
    return state


def save(state: dict, path: Path = STATE_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(path)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd ~/sqlch && python -m unittest tests.test_dock_state tests.test_dock -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/sqlch && git add sqlch_gui/__init__.py sqlch_gui/ui/dock_state.py tests/test_dock_state.py && git commit -m "sqlch-gui: persist docked window state"
```

---

### Task 3: NavColumn independent toggles

**Files:**
- Modify: `sqlch_gui/ui/controls.py:270-317` (`NavColumn`)
- Test: `tests/test_nav_column.py`

**Interfaces:**
- Produces: `NavColumn` with tabs LIBRARY and DISCOVER only (NOW is dropped: Now Playing is always visible). Signal `nav-toggled(str name)` emitted on user click. `set_open(name: str, is_open: bool)` syncs the highlight without emitting. `NavColumn.nav-selected`, `.active`, `.set_active` are removed.
- Consumes: `Header(tabs, width)` and `NowPlayingPanel` forward the signal in Task 5; `now_playing.py:26,43` currently forward `nav-selected`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_nav_column.py
import unittest

import gi
gi.require_version("Gtk", "4.0")

from sqlch_gui.ui.controls import NavColumn


class TestNavColumn(unittest.TestCase):
    def test_click_emits_toggle_and_does_not_flip_highlight(self):
        nav, seen = NavColumn(), []
        nav.connect("nav-toggled", lambda _n, name: seen.append(name))
        nav._buttons["library"].emit("clicked")
        nav._buttons["library"].emit("clicked")
        self.assertEqual(seen, ["library", "library"])
        self.assertFalse(nav._buttons["library"].has_css_class("active"))

    def test_set_open_syncs_highlight_independently(self):
        nav, seen = NavColumn(), []
        nav.connect("nav-toggled", lambda _n, name: seen.append(name))
        nav.set_open("library", True)
        nav.set_open("discover", True)
        self.assertTrue(nav._buttons["library"].has_css_class("active"))
        self.assertTrue(nav._buttons["discover"].has_css_class("active"))
        nav.set_open("library", False)
        self.assertFalse(nav._buttons["library"].has_css_class("active"))
        self.assertTrue(nav._buttons["discover"].has_css_class("active"))
        self.assertEqual(seen, [])
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ~/sqlch && python -m unittest tests.test_nav_column -v`
Expected: FAIL (`nav-toggled` unknown signal).

- [ ] **Step 3: Implement** — replace the whole `NavColumn` class body (and docstring) with:

```python
class NavColumn(Gtk.Box):
    """Folder-tab row: LIBRARY and DISCOVER toggle their docked windows
    independently. A click only emits `nav-toggled`; the DockManager decides
    what to open or close and syncs the highlight back with `set_open`, so
    the tab can never disagree with the window. Hosted by Header, which
    styles the row as `.sq-tabs`."""

    __gsignals__ = {
        'nav-toggled': (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    _TABS = (
        ("library", "LIBRARY", "Station Library"),
        ("discover", "DISCOVER", "Discover Stations"),
    )

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4,
                         homogeneous=True)
        self._buttons = {}
        for name, label, tip in self._TABS:
            button = Gtk.Button(label=label)
            button.add_css_class("sq-tab")
            button.set_tooltip_text(tip)
            button.connect("clicked", lambda _b, n=name: self.emit("nav-toggled", n))
            self.append(button)
            self._buttons[name] = button

    def set_open(self, name: str, is_open: bool):
        if is_open:
            self._buttons[name].add_css_class("active")
        else:
            self._buttons[name].remove_css_class("active")
```

In `sqlch_gui/ui/now_playing.py` change the signal definition at line 26 from `'nav-selected'` to `'nav-toggled'` and line 43 to:

```python
        self.nav_column.connect("nav-toggled", lambda nav, name: self.emit("nav-toggled", name))
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd ~/sqlch && python -m unittest tests.test_nav_column tests.test_header -v`
Expected: PASS. (`window.py` still references `nav-selected` until Task 5; do not launch the app yet.)

- [ ] **Step 5: Commit**

```bash
cd ~/sqlch && git add sqlch_gui/ui/controls.py sqlch_gui/ui/now_playing.py tests/test_nav_column.py && git commit -m "sqlch-gui: nav tabs toggle library/discover independently"
```

---

### Task 4: DockedWindow + DockManager + CSS

**Files:**
- Create: `sqlch_gui/ui/dock_window.py`, `sqlch_gui/ui/dock_manager.py`
- Modify: `sqlch_gui/ui/common.py` (inside `_build_css`, directly after the `.sq-nameplate {...}` rule near line 353)
- Test: extend `tests/test_gui_style.py` (CSS assertion)

**Interfaces:**
- Consumes: `dock.*`, `dock_state.*` (Tasks 1-2), `NavColumn.set_open` (Task 3).
- Produces:
  - `DockedWindow(manager, name, title, panel)` with `.rect -> Rect`, `place(rect)`, `fade_in()`, `fade_out()`, `PANEL_WIDTH = 320`.
  - `DockManager(np_win, panels: dict[str, Gtk.Widget], nav: NavColumn, on_shown: dict[str, callable], on_hidden: dict[str, callable])` with `toggle(name)`, `relayout()`, `shutdown()`.

- [ ] **Step 1: Write the failing CSS test** (append to `TestFlatStylesheet` in `tests/test_gui_style.py`)

```python
    def test_dock_handle_rules_present(self):
        from sqlch_gui.ui import common
        css = common._build_css(dict(palette._DEFAULTS))
        for sel in (".dock-handle", ".dock-title", ".dock-close"):
            self.assertIn(sel, css)
```

Run: `cd ~/sqlch && python -m unittest tests.test_gui_style -v` → FAIL.

- [ ] **Step 2: Add the CSS** after the `.sq-nameplate` rule in `_build_css`:

```python
    .dock-handle {{
        padding: 6px 8px 4px 10px;
    }}
    .dock-title {{
        font-family: {mono};
        font-size: 0.6em;
        font-weight: 700;
        letter-spacing: 0.24em;
        color: {rest};
    }}
    .dock-close {{
        min-width: 20px;
        min-height: 20px;
        padding: 0;
        color: {rest};
        background: transparent;
        border: none;
        box-shadow: none;
    }}
    .dock-close:hover {{
        color: {score};
    }}
```

Run the test again → PASS.

- [ ] **Step 3: Write `dock_window.py`**

```python
"""One docked Library/Discover window: a layer-shell surface anchored
TOP+LEFT and positioned purely by margins, with a drag handle that snaps."""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gtk, Gtk4LayerShell

from .dock import Rect

PANEL_WIDTH = 320
FADE_MS = 160


class DockedWindow(Gtk.Window):
    def __init__(self, manager, name: str, title: str, panel: Gtk.Widget):
        super().__init__()
        self.manager = manager
        self.name = name
        self.rect = Rect(0, 0, PANEL_WIDTH, 0)
        self._fade_id = None
        self._drag_off = (0.0, 0.0)
        self._drag_tick = None

        self.set_title(f"sqlch-gui {name}")
        self.set_decorated(False)
        Gtk4LayerShell.init_for_window(self)
        Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.TOP)
        Gtk4LayerShell.set_namespace(self, f"sqlch-gui-{name}")
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.TOP, True)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.LEFT, True)
        Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.ON_DEMAND)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.add_css_class("popup-window")
        self.set_child(root)

        handle = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        handle.add_css_class("dock-handle")
        lbl = Gtk.Label(label=title, xalign=0.0, hexpand=True)
        lbl.add_css_class("dock-title")
        close = Gtk.Button(icon_name="window-close-symbolic")
        close.add_css_class("dock-close")
        close.connect("clicked", lambda _b: manager.toggle(name))
        handle.append(lbl)
        handle.append(close)
        root.append(handle)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_child(panel)
        root.append(scroll)

        drag = Gtk.GestureDrag.new()
        drag.connect("drag-begin", self._drag_begin)
        drag.connect("drag-update", self._drag_update)
        drag.connect("drag-end", self._drag_end)
        handle.add_controller(drag)
        handle.set_cursor_from_name("grab")

    # --- placement ---

    def place(self, rect: Rect):
        self.rect = rect
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.LEFT, rect.x)
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.TOP, rect.y)
        self.set_default_size(rect.w, rect.h)

    # --- fade (sequential: a window is fully out before another fades in) ---

    def _fade(self, target: float, on_done=None):
        if self._fade_id:
            self.remove_tick_callback(self._fade_id)
        start, t0 = self.get_opacity(), None

        def tick(_w, clock):
            nonlocal t0
            now = clock.get_frame_time()
            t0 = now if t0 is None else t0
            k = min(1.0, (now - t0) / (FADE_MS * 1000))
            self.set_opacity(start + (target - start) * k)
            if k >= 1.0:
                self._fade_id = None
                if on_done:
                    on_done()
                return False
            return True

        self._fade_id = self.add_tick_callback(tick)

    def fade_in(self):
        self.set_opacity(0.0)
        self.set_visible(True)
        self._fade(1.0)

    def fade_out(self, on_done=None):
        def done():
            self.set_visible(False)
            if on_done:
                on_done()
        self._fade(0.0, done)

    # --- drag ---
    # The surface moves under the pointer, so GestureDrag offsets are
    # relative to the *current* surface position: new = applied + offset
    # re-derives the pointer's total travel. Commits are coalesced to one
    # per frame so each margin change lands before the next motion event.

    def _drag_begin(self, _g, _x, _y):
        self._drag_off = (0.0, 0.0)
        self._drag_tick = self.add_tick_callback(self._drag_frame)

    def _drag_update(self, _g, ox, oy):
        self._drag_off = (ox, oy)

    def _drag_frame(self, _w, _clock):
        ox, oy = self._drag_off
        if ox or oy:
            self._drag_off = (0.0, 0.0)
            self.place(self.manager.clamp(self.rect.moved(round(ox), round(oy))))
        return True

    def _drag_end(self, _g, _ox, _oy):
        if self._drag_tick:
            self.remove_tick_callback(self._drag_tick)
            self._drag_tick = None
        self.manager.commit_drag(self.name, self.rect)
```

- [ ] **Step 4: Write `dock_manager.py`**

```python
"""Owns the docked windows: layout from persisted state + Now Playing's
rect, toggle with sequential fades, and snap-on-release."""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import GLib, Gtk4LayerShell

from . import dock, dock_state
from .dock_window import DockedWindow, PANEL_WIDTH

_TITLES = {"library": "LIBRARY", "discover": "DISCOVER"}


class DockManager:
    def __init__(self, np_win, panels, nav, on_shown, on_hidden):
        self.np = np_win
        self.nav = nav
        self._on_shown = on_shown
        self._on_hidden = on_hidden
        self.state = dock_state.load()
        self.windows = {
            n: DockedWindow(self, n, _TITLES[n], panels[n]) for n in dock_state.NAMES
        }
        self._last_np = None
        self._tick = np_win.add_tick_callback(self._watch_np)
        for n in dock_state.NAMES:
            nav.set_open(n, self.state[n]["open"])

    # --- geometry ---

    def monitor_size(self):
        surface = self.np.get_surface()
        mon = self.np.get_display().get_monitor_at_surface(surface) if surface else None
        if mon is None:
            return None
        g = mon.get_geometry()
        return g.width, g.height

    def np_rect(self):
        size = self.monitor_size()
        w, h = self.np.get_width(), self.np.get_height()
        if size is None or w <= 0 or h <= 0:
            return None
        right = Gtk4LayerShell.get_margin(self.np, Gtk4LayerShell.Edge.RIGHT)
        top = Gtk4LayerShell.get_margin(self.np, Gtk4LayerShell.Edge.TOP)
        return dock.Rect(size[0] - right - w, top, w, h)

    def clamp(self, rect):
        size = self.monitor_size()
        return dock.clamp(rect, *size) if size else rect

    def _open_names(self):
        return [n for n in dock_state.NAMES if self.state[n]["open"]]

    def _slot_rects(self, np):
        """Target rect for every open window."""
        unplaced = [(n, PANEL_WIDTH) for n in self._open_names()
                    if self.state[n]["placed"] is None]
        rects = dock.default_dock(np, unplaced)
        for n in self._open_names():
            p = self.state[n]["placed"]
            if p is None:
                continue
            if p["mode"] == "np":
                r = dock.Rect(np.x + p["dx"], np.y + p["dy"], PANEL_WIDTH, np.h)
            else:
                r = dock.Rect(p["x"], p["y"], PANEL_WIDTH, np.h)
            rects[n] = self.clamp(r)
        return rects

    def relayout(self):
        np = self.np_rect()
        if np is None:
            return
        for n, r in self._slot_rects(np).items():
            self.windows[n].place(r)

    def _watch_np(self, _w, _clock):
        np = self.np_rect()
        if np != self._last_np:
            self._last_np = np
            self.relayout()
        return True

    # --- toggle ---

    def toggle(self, name):
        opening = not self.state[name]["open"]
        self.state[name]["open"] = opening
        self.nav.set_open(name, opening)
        win = self.windows[name]
        if opening:
            self.relayout()
            win.fade_in()
            self._on_shown[name]()
        else:
            win.fade_out(self._on_hidden[name])
            self.relayout()   # closed windows free their dock slot
        dock_state.save(self.state)

    def show_saved(self):
        """Present windows that were open last session. Called once Now
        Playing has an allocation."""
        self.relayout()
        for n in self._open_names():
            self.windows[n].fade_in()
            self._on_shown[n]()

    # --- drag release ---

    def commit_drag(self, name, rect):
        np = self.np_rect()
        if np is None:
            return
        others = [np] + [self.windows[n].rect for n in self._open_names() if n != name]
        snapped = self.clamp(dock.snap(rect, others))
        docked_to = [np] + [self.windows[n].rect for n in self._open_names()
                            if n != name and self._is_np_group(n, np)]
        if any(dock.touches(snapped, o) for o in docked_to):
            self.state[name]["placed"] = {
                "mode": "np", "dx": snapped.x - np.x, "dy": snapped.y - np.y}
        else:
            self.state[name]["placed"] = {"mode": "free", "x": snapped.x, "y": snapped.y}
        self.windows[name].place(snapped)
        dock_state.save(self.state)

    def _is_np_group(self, name, np):
        p = self.state[name]["placed"]
        return p is None or p["mode"] == "np"

    def shutdown(self):
        self.np.remove_tick_callback(self._tick)
        for w in self.windows.values():
            w.close()
```

Note: `GLib` import unused → remove it before committing if ruff flags it.

- [ ] **Step 5: Lint and commit**

Run: `cd ~/sqlch && ruff check sqlch_gui/ui/dock_window.py sqlch_gui/ui/dock_manager.py && python -m unittest tests.test_gui_style -v`
Expected: clean / PASS.

```bash
cd ~/sqlch && git add sqlch_gui/ui/dock_window.py sqlch_gui/ui/dock_manager.py sqlch_gui/ui/common.py tests/test_gui_style.py && git commit -m "sqlch-gui: docked window + manager with fade toggle and magnetic drag"
```

---

### Task 5: Wire into the main window, remove the drawer

**Files:**
- Modify: `sqlch_gui/ui/window.py` (rewrite lines 1-262 region; keep `trigger_library_refresh` and everything from `_on_palette_changed` down)
- Modify: `sqlch_gui/ui/banner.py` (delete `TornSeparator` if nothing else uses it)

**Interfaces:**
- Consumes: `DockManager(np_win, panels, nav, on_shown, on_hidden)`, `NowPlayingPanel.nav_column`, signal `nav-toggled`.

- [ ] **Step 1: Replace the module header and `__init__` body in `window.py`**

Delete the drawer constants (`MAX_DRAWER_WIDTH` … `DRAWER_SPRING_ZETA`), the `TornSeparator` import, and these members: `dropdown_stack`, `dropdown_scroll`, `seam`, all `_drawer_*`/`_drag_*` fields, `on_nav_selected`, `_measure_drawer_width`, `_compute_drawer_max`, `_set_drawer_pos`, `_stop_drawer_anim`, the three `_on_seam_drag_*` methods, `_animate_drawer_to`. Imports become:

```python
import threading
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gtk, GLib, Gio, Gtk4LayerShell

from .. import daemon, palette
from .common import load_custom_css
from .header import next_connected
from .now_playing import NowPlayingPanel
from .station_list import StationListPanel
from .discover import DiscoverPanel
from .dock_manager import DockManager
```

The `__init__` comment block and layer-shell setup stay (update the comment to: Now Playing is the permanent surface; Library/Discover are docked windows owned by `DockManager`). Replace everything from `main_box = ...` through `self.now_playing.connect("nav-selected", ...)` with:

```python
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        main_box.add_css_class("popup-window")
        self.set_child(main_box)

        self.now_playing = NowPlayingPanel(self)
        self.station_list = StationListPanel(self)
        self.discover = DiscoverPanel(self)
        main_box.append(self.now_playing)

        self.docks = DockManager(
            self,
            panels={"library": self.station_list, "discover": self.discover},
            nav=self.now_playing.nav_column,
            on_shown={"library": self.station_list.on_shown, "discover": lambda: None},
            on_hidden={"library": self.station_list.abort_probes, "discover": lambda: None},
        )
        self.now_playing.connect("nav-toggled", lambda _p, name: self.docks.toggle(name))
        self.connect("map", lambda _w: GLib.idle_add(self.docks.show_saved))
```

Keep the remaining `__init__` lines (`_keep_running`, monitor thread, palette monitor, `close-request`).

- [ ] **Step 2: Close docked windows with Now Playing**

```python
    def on_close_request(self, win):
        self._keep_running = False
        self.docks.shutdown()
```

- [ ] **Step 3: Remove dead code and verify imports**

Run: `cd ~/sqlch && grep -rn "TornSeparator\|dropdown\|_drawer\|nav-selected\|seam" sqlch_gui tests --include=*.py`
Expected: only `banner.py` (the class) and docstring mentions. Delete `TornSeparator` and update the `banner.py` module docstring accordingly if no other users remain; fix any leftover references (e.g. comments in `station_list.py:337` "drawer closed" → "window hidden", `controls.py` none).

Run: `cd ~/sqlch && ruff check sqlch_gui && python -m unittest discover -s tests -v 2>&1 | tail -15`
Expected: ruff clean, all tests PASS.

- [ ] **Step 4: Launch and verify manually on the desktop** (needs a Wayland session)

Run: `cd ~/sqlch && python -m sqlch_gui` (or the installed `sqlch-gui` launcher the flake provides).
Check each, and fix before committing:
1. Click LIBRARY: window fades in flush left of Now Playing, top-aligned. Click again: fades out, no slide.
2. Open both: Discover sits left of Library. Close Library: Discover re-packs against Now Playing.
3. Drag Library by its header: follows the pointer smoothly. **If it jitters or oscillates**, the margin-feedback in `DockedWindow._drag_frame` is lagging the compositor; fix by scaling the applied offset (`round(ox * 0.5)`) or by committing every other frame, and record the working factor in a comment.
4. Release within 20 px of Now Playing: snaps flush. Release far away: stays.
5. Quit and relaunch: open windows and placements return.
6. Close the Library window while its probe sweep runs: `abort_probes` called (no stuck sweep).

- [ ] **Step 5: Commit**

```bash
cd ~/sqlch && git add -A sqlch_gui tests && git commit -m "sqlch-gui: replace slide-out drawer with docked windows"
```

---

### Task 6: Deploy

**Files:** `~/nixos` flake input `sqlch` (lock bump only)

- [ ] **Step 1:** Push `~/sqlch` main, then in `~/nixos` (branch `wip`): `nix flake update sqlch`, `git add flake.lock`, commit `sqlch: docked gui windows`.
- [ ] **Step 2:** `nrs` on desktop; verify the checks in Task 5 Step 4 against the installed binary. Surface: `nrs` (offloads build to desktop).
