# sqlch-gui header Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The top of the sqlch-gui popup becomes a uniremote-style header: nameplate, live plate (connected LED + track + station), and folder tabs that drive the existing drawer.

**Architecture:** New `Header` widget (`sqlch_gui/ui/header.py`) owns the nameplate and plate and hosts the existing `NavColumn` (reworked into text folder tabs, same signal + `set_active` API). `now_playing.py` routes the station/track text into the header instead of the info panel; `window.py` passes daemon reachability from its existing poll. CSS lives in `_build_css` (`ui/common.py`), palette tokens only.

**Tech Stack:** Python 3.11+, PyGObject (Gtk4, Gtk4LayerShell, Pango), unittest-style tests in `tests/`.

Spec: `docs/superpowers/specs/2026-09-30-sqlch-header-design.md`.

## Global Constraints

- Everything else in sqlch keeps its look, info and behavior: cover art, LIVE tag, controls, volume meter, record bubble, codec/bitrate/buffer pills, previous-track line, drawer, torn seam, station list, discover.
- Colors only from palette tokens already in `_build_css` (`stage`, `wing`, `score`, `score_rgb`, `rest`, `root`, `outline`, `edge`, `drop`, `mono`, `prop`). No new hex. The existing test `test_no_paper_cutout_vocabulary` must keep passing: no `linear-gradient`, no `text-shadow`, at most one `feTurbulence`.
- **Width invariant:** the popup must not change width when text changes. The info panel is pinned to `_INFO_PANEL_WIDTH` (300) in `now_playing.py`; the header follows the same rule: `set_size_request(width, -1)`, both plate labels single-line, ellipsized, `width_chars=1`, `max_width_chars=1`, `hexpand=True`.
- LED = daemon reachable (`daemon.send(...)` returned non-`None`), NOT the existing "stale" flag (stale = stopped/idle).
- `NavColumn` public surface unchanged: signal `nav-selected` (str), attribute `active`, method `set_active(name)` with names `mini`, `library`, `discover`; `set_active` does not emit. `window.py`'s drawer code is not edited.
- Comments only where the WHY is non-obvious.
- Work in a git worktree of `~/sqlch` (create: `git -C ~/sqlch worktree add ../sqlch-header -b sqlch-header main`); subagents must run `git rev-parse --show-toplevel` and confirm `/home/prepko/sqlch-header` before any commit.
- Test command (from the worktree root; run the FULL suite once before each commit, focused tests while iterating):

```bash
nix-shell -p 'python3.withPackages (p: [ p.pytest p.pygobject3 p.pycairo p.requests p.pydbus ])' \
  gtk4 gtk4-layer-shell gobject-introspection --run 'python -m pytest tests -q'
```
  Record the baseline (pass/fail per test) BEFORE any change in Task 1 Step 0; any test already failing at baseline is reported, not fixed.

## File Structure

| File | Responsibility |
|---|---|
| `sqlch_gui/ui/header.py` (create) | `Header` widget + `SNARK` |
| `sqlch_gui/ui/controls.py` (modify `NavColumn`, ~272-374) | icon buttons → text folder tabs, same API |
| `sqlch_gui/ui/common.py` (modify `_build_css`) | add `.sq-*` classes; retire `.nav-row`, `.nav-btn*`, `.brand-tag` |
| `sqlch_gui/ui/now_playing.py` (modify) | host header; route text; drop brand overlay + old labels |
| `sqlch_gui/ui/window.py` (modify `_apply_daemon_state`, ~line 331) | pass connection state |
| `tests/test_header.py` (create), `tests/test_gui_style.py` (modify) | tests |

---

### Task 1: Header widget, plate CSS, tests

**Files:**
- Create: `sqlch_gui/ui/header.py`, `tests/test_header.py`
- Modify: `sqlch_gui/ui/common.py` (add classes inside `_build_css`, right after the `.brand-tag {{ … }}` block), `tests/test_gui_style.py`

**Interfaces:**
- Produces: `Header(tabs: Gtk.Widget, width: int)` (a `Gtk.Box`), methods `set_track(markup: str)`, `set_station(markup: str)`, `set_connected(connected: bool)`, `set_stale(stale: bool)`; attributes `track`, `station` (`Gtk.Label`), `SNARK: tuple[str, ...]`. CSS classes used: `sq-header`, `sq-nameplate`, `sq-plate` (+ `stale`, `offline`), `sq-led`, `sq-track`, `sq-station`, `sq-tabs` (added to the `tabs` widget).

- [ ] **Step 0: Record baseline** — run the test command on a clean worktree; save the summary line.

- [ ] **Step 1: Write failing tests** — `tests/test_header.py`:

```python
import unittest

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from sqlch_gui.ui.header import SNARK, Header


def _header():
    return Header(Gtk.Box(), 300)


class TestHeader(unittest.TestCase):
    def test_nameplate_and_css_classes(self):
        h = _header()
        self.assertTrue(h.has_css_class("sq-header"))
        self.assertTrue(h.track.has_css_class("sq-track"))
        self.assertTrue(h.station.has_css_class("sq-station"))

    def test_text_labels_cannot_widen_the_popup(self):
        h = _header()
        for label in (h.track, h.station):
            self.assertEqual(label.get_max_width_chars(), 1)
            self.assertEqual(label.get_width_chars(), 1)
            self.assertTrue(label.get_single_line_mode())
            self.assertFalse(label.get_wrap())

    def test_track_and_station_text(self):
        h = _header()
        h.set_track("<b>A — B</b>")
        h.set_station("<b>STATION</b>  WXPN")
        self.assertEqual(h.track.get_text(), "A — B")
        self.assertEqual(h.station.get_text(), "STATION  WXPN")

    def test_disconnect_shows_snark_and_reconnect_restores_station(self):
        h = _header()
        h.set_station("<b>STATION</b>  WXPN")
        h.set_connected(False)
        self.assertIn(h.station.get_text(), SNARK)
        h.set_connected(True)
        self.assertEqual(h.station.get_text(), "STATION  WXPN")

    def test_station_updates_while_disconnected_do_not_clobber_snark(self):
        h = _header()
        h.set_connected(False)
        snark = h.station.get_text()
        h.set_station("<b>STATION</b>  NEW")
        self.assertEqual(h.station.get_text(), snark)
        h.set_connected(True)
        self.assertEqual(h.station.get_text(), "STATION  NEW")

    def test_snark_is_stable_within_one_disconnect(self):
        h = _header()
        h.set_connected(False)
        first = h.station.get_text()
        h.set_connected(False)
        self.assertEqual(h.station.get_text(), first)

    def test_offline_and_stale_classes(self):
        h = _header()
        plate = h.station.get_parent().get_parent()
        h.set_connected(False)
        self.assertTrue(plate.has_css_class("offline"))
        h.set_connected(True)
        self.assertFalse(plate.has_css_class("offline"))
        h.set_stale(True)
        self.assertTrue(plate.has_css_class("stale"))
        h.set_stale(False)
        self.assertFalse(plate.has_css_class("stale"))

    def test_tabs_widget_is_hosted_and_classed(self):
        tabs = Gtk.Box()
        h = Header(tabs, 300)
        self.assertTrue(tabs.has_css_class("sq-tabs"))
        self.assertIs(tabs.get_parent(), h)
```

Append to `tests/test_gui_style.py`, inside `TestFlatStylesheet`:

```python
    def test_header_classes_are_styled(self):
        from sqlch_gui.ui import common
        css = common._build_css(dict(palette._DEFAULTS))
        for selector in (".sq-header", ".sq-nameplate", ".sq-plate", ".sq-led",
                         ".sq-track", ".sq-station", ".sq-tabs"):
            self.assertIn(selector + " {", css, f"{selector} missing")
```

- [ ] **Step 2: Run to verify failure** — focused: `python -m pytest tests/test_header.py tests/test_gui_style.py -q`. Expected: `ModuleNotFoundError: sqlch_gui.ui.header` and the style test FAIL.

- [ ] **Step 3: Implement** — `sqlch_gui/ui/header.py`:

```python
"""Top of the popup: nameplate, live plate (LED + track + station), and the
folder-tab row (hosted, not owned -- NavColumn keeps its own signal/API).
Modeled on uniremote's header (~/nixos/pkgs/uniremote/.../header.py)."""

import random

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Pango

SNARK = (
    "Daemon's gone quiet.",
    "Nobody's spinning records.",
    "Dead air. The bad kind.",
    "sqlch is not answering.",
    "The transmitter is out to lunch.",
)


def _plate_label(css_class: str) -> Gtk.Label:
    # width_chars/max_width_chars=1 + hexpand: the label takes whatever width
    # the pinned header gives it instead of dragging the popup wider with a
    # long title (see the info-panel note in now_playing.py).
    label = Gtk.Label(xalign=0.0, hexpand=True)
    label.set_ellipsize(Pango.EllipsizeMode.END)
    label.set_single_line_mode(True)
    label.set_width_chars(1)
    label.set_max_width_chars(1)
    label.add_css_class(css_class)
    return label


class Header(Gtk.Box):
    def __init__(self, tabs: Gtk.Widget, width: int):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("sq-header")
        self.set_size_request(width, -1)
        self._connected = True
        self._station_markup = ""

        nameplate = Gtk.Label(label="SQLCH", xalign=0.0)
        nameplate.add_css_class("sq-nameplate")
        self.append(nameplate)

        led = Gtk.Box(valign=Gtk.Align.CENTER)
        led.add_css_class("sq-led")
        self.track = _plate_label("sq-track")
        self.station = _plate_label("sq-station")
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        text.append(self.track)
        text.append(self.station)
        self._plate = Gtk.Box(spacing=10)
        self._plate.add_css_class("sq-plate")
        self._plate.append(led)
        self._plate.append(text)
        self.append(self._plate)

        tabs.add_css_class("sq-tabs")
        self.append(tabs)

    def set_track(self, markup: str) -> None:
        self.track.set_markup(markup)

    def set_station(self, markup: str) -> None:
        self._station_markup = markup
        if self._connected:
            self.station.set_markup(markup)

    def set_connected(self, connected: bool) -> None:
        if connected == self._connected:
            return
        self._connected = connected
        if connected:
            self._plate.remove_css_class("offline")
            self.station.set_markup(self._station_markup)
        else:
            self._plate.add_css_class("offline")
            snark = GLib.markup_escape_text(random.choice(SNARK))
            self.station.set_markup(f"<i>{snark}</i>")

    def set_stale(self, stale: bool) -> None:
        if stale:
            self._plate.add_css_class("stale")
        else:
            self._plate.remove_css_class("stale")
```

Note: `GLib.markup_escape_text` escapes the apostrophe as `&apos;`; Pango renders it back as `'`, so `station.get_text()` equals the original `SNARK` entry.

In `common.py` `_build_css`, after the `.brand-tag {{ … }}` block (do NOT remove `.brand-tag`/`.nav-*` yet — Tasks 2/3 do), add:

```python
    .sq-header {{
        padding: 2px 2px 0 2px;
    }}
    .sq-nameplate {{
        font-family: {mono};
        font-size: 0.6em;
        font-weight: 700;
        letter-spacing: 0.24em;
        color: {rest};
        margin: 4px 4px 0 4px;
    }}
    .sq-plate {{
        padding: 6px 4px 8px 4px;
    }}
    .sq-plate.stale .sq-track,
    .sq-plate.stale .sq-station,
    .sq-plate.offline .sq-track {{
        opacity: 0.5;
    }}
    .sq-led {{
        min-width: 9px;
        min-height: 9px;
        border-radius: 9999px;
        background-color: {score};
        box-shadow: 0 0 6px rgba({score_rgb}, 0.6);
    }}
    .sq-plate.offline .sq-led {{
        background-color: transparent;
        border: 1px solid {rest};
        box-shadow: none;
    }}
    .sq-track {{
        font-family: {prop};
        font-size: 1.1em;
        font-weight: 700;
        color: {score};
    }}
    .sq-station {{
        font-family: {mono};
        font-size: 0.72em;
        color: {rest};
    }}
    .sq-tabs {{
        border-bottom: 2px solid {root};
    }}
```

- [ ] **Step 4: Run to verify pass** — full test command; compare against the baseline (no new failures).

- [ ] **Step 5: Commit**

```bash
git add sqlch_gui/ui/header.py sqlch_gui/ui/common.py tests/test_header.py tests/test_gui_style.py
git commit -m "sqlch-gui: Header widget (nameplate, live plate) + plate CSS

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: NavColumn becomes folder tabs

**Files:**
- Modify: `sqlch_gui/ui/controls.py` (`NavColumn`, lines ~272-374), `sqlch_gui/ui/common.py` (tab CSS; retire `.nav-row`, `.nav-btn`, `.nav-btn:hover`, `.nav-btn.active`), `tests/test_gui_style.py` (`TestPlayerEdgeBorder`), `tests/test_header.py` (append)

**Interfaces:**
- Consumes: CSS class `sq-tabs` added by `Header` (Task 1).
- Produces: `NavColumn` unchanged API (`nav-selected` signal, `.active`, `set_active(name)`), now three text tabs `NOW` (`mini`), `LIBRARY` (`library`), `DISCOVER` (`discover`), each a `Gtk.Button` with class `sq-tab` (active one also `active`).

- [ ] **Step 1: Write failing tests** — append to `tests/test_header.py`:

```python
class TestNavTabs(unittest.TestCase):
    def _nav(self):
        from sqlch_gui.ui.controls import NavColumn
        return NavColumn()

    def test_three_text_tabs_mini_active(self):
        nav = self._nav()
        self.assertEqual(nav.active, "mini")
        labels = {name: b.get_label() for name, b in nav._buttons.items()}
        self.assertEqual(labels, {"mini": "NOW", "library": "LIBRARY", "discover": "DISCOVER"})
        for name, b in nav._buttons.items():
            self.assertTrue(b.has_css_class("sq-tab"))
            self.assertEqual(b.has_css_class("active"), name == "mini")

    def test_click_selects_and_emits(self):
        nav = self._nav()
        seen = []
        nav.connect("nav-selected", lambda _n, name: seen.append(name))
        nav._buttons["library"].emit("clicked")
        self.assertEqual(nav.active, "library")
        self.assertEqual(seen, ["library"])
        nav._buttons["library"].emit("clicked")  # re-click is a no-op
        self.assertEqual(seen, ["library"])

    def test_set_active_syncs_highlight_without_emitting(self):
        nav = self._nav()
        seen = []
        nav.connect("nav-selected", lambda _n, name: seen.append(name))
        nav.set_active("discover")
        self.assertEqual(nav.active, "discover")
        self.assertTrue(nav._buttons["discover"].has_css_class("active"))
        self.assertFalse(nav._buttons["mini"].has_css_class("active"))
        self.assertEqual(seen, [])
```

In `tests/test_gui_style.py` `TestPlayerEdgeBorder`: update the docstring class list and the tuple in `test_player_classes_use_a_stronger_border_than_hairline` from `(".card", ".nav-row", ".nav-btn", ".cover-art", ".info-panel", ".control-btn")` to `(".card", ".sq-tab", ".cover-art", ".info-panel", ".control-btn")`.

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/test_header.py tests/test_gui_style.py -q`. Expected: the three `TestNavTabs` tests FAIL (labels/class), `.sq-tab` rule missing.

- [ ] **Step 3: Implement** — in `controls.py`, replace the `NavColumn` class with the version below. Keep the `_select`/`set_active` semantics exactly. After editing, run `python -m pyflakes sqlch_gui/ui/controls.py` (or ruff) and remove any import that became unused (`cairo`, `math`, `_hex_to_rgb_floats` are likely still used by `VolumeMeter`/`RecordBubble` — remove only what pyflakes flags).

```python
class NavColumn(Gtk.Box):
    """Folder-tab row: NOW (collapse, Now Playing), LIBRARY, DISCOVER.

    Not three independent toggle buttons -- clicking Library or Discover
    opens that section (auto-collapsing whichever was open), re-clicking
    the already-open one is a no-op, and only NOW collapses back down to
    nothing selected. Hosted by Header, which styles the row as `.sq-tabs`.
    """

    __gsignals__ = {
        'nav-selected': (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    _TABS = (
        ("mini", "NOW", "Now Playing"),
        ("library", "LIBRARY", "Station Library"),
        ("discover", "DISCOVER", "Discover Stations"),
    )

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4,
                         homogeneous=True)
        self.active = "mini"
        self._buttons = {}
        for name, label, tip in self._TABS:
            button = Gtk.Button(label=label)
            button.add_css_class("sq-tab")
            button.set_tooltip_text(tip)
            button.connect("clicked", lambda _b, n=name: self._select(n))
            self.append(button)
            self._buttons[name] = button
        self._buttons["mini"].add_css_class("active")

    def set_active(self, name: str):
        """Sync the highlight to drawer state driven from outside (seam
        drags) without re-emitting nav-selected."""
        if name == self.active:
            return
        self._buttons[self.active].remove_css_class("active")
        self.active = name
        self._buttons[name].add_css_class("active")

    def _select(self, name: str):
        if name == self.active:
            return  # re-clicking the already-open one (or idle NOW) is a no-op
        self.set_active(name)
        self.emit("nav-selected", name)
```

In `common.py`: delete the `.nav-row`, `.nav-btn`, `.nav-btn:hover`, `.nav-btn.active` blocks and add:

```python
    .sq-tab {{
        padding: 4px 0;
        margin: 0;
        border-radius: 7px 7px 0 0;
        color: {rest};
        background-color: {wing};
        background-image: none;
        border: {edge};
        border-bottom-width: 0;
        box-shadow: none;
        font-family: {mono};
        font-size: 0.68em;
        font-weight: 700;
        letter-spacing: 0.12em;
    }}
    .sq-tab:hover {{
        background-color: {stage};
        color: {score};
    }}
    .sq-tab.active {{
        background-color: {root};
        border-color: {root};
        color: {outline};
    }}
```

- [ ] **Step 4: Run to verify pass** — full test command; no new failures vs baseline.

- [ ] **Step 5: Commit**

```bash
git add sqlch_gui/ui/controls.py sqlch_gui/ui/common.py tests/test_header.py tests/test_gui_style.py
git commit -m "sqlch-gui: NavColumn becomes text folder tabs (same API)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Wire the header into the card and the poll

**Files:**
- Modify: `sqlch_gui/ui/now_playing.py`, `sqlch_gui/ui/window.py` (`_apply_daemon_state`), `sqlch_gui/ui/common.py` (remove `.brand-tag`)
- Test: `tests/test_header.py` (append a card-level test)

**Interfaces:**
- Consumes: `Header(tabs, width)` and its methods (Task 1); tab-style `NavColumn` (Task 2).
- Produces: `NowPlayingPanel.header` (`Header`), `NowPlayingPanel.set_connected(connected: bool)`. The old `lbl_station` / `lbl_now_playing` attributes are removed.

- [ ] **Step 1: Write failing test** — append to `tests/test_header.py`:

```python
class TestNowPlayingWiring(unittest.TestCase):
    def _panel(self):
        from sqlch_gui.ui.now_playing import NowPlayingPanel
        return NowPlayingPanel(None)

    def test_idle_state_lands_in_the_header(self):
        p = self._panel()
        self.assertEqual(p.header.track.get_text(), "Not Playing")
        self.assertTrue(p.header.station.get_text().startswith("STATION"))
        self.assertFalse(hasattr(p, "lbl_station"))
        self.assertFalse(hasattr(p, "lbl_now_playing"))

    def test_set_connected_reaches_the_header(self):
        from sqlch_gui.ui.header import SNARK
        p = self._panel()
        p.set_connected(False)
        self.assertIn(p.header.station.get_text(), SNARK)
        p.set_connected(True)
        self.assertTrue(p.header.station.get_text().startswith("STATION"))

    def test_stale_dims_the_plate(self):
        p = self._panel()  # reset_ui() at construction marks the panel stale
        plate = p.header.station.get_parent().get_parent()
        self.assertTrue(plate.has_css_class("stale"))

    def test_nav_column_is_inside_the_header(self):
        p = self._panel()
        self.assertIs(p.nav_column.get_parent(), p.header)

    def test_previous_track_line_and_pills_stay_in_the_info_panel(self):
        p = self._panel()
        self.assertIsNotNone(p.lbl_previous)
        self.assertIsNotNone(p.pill_codec)
```

(If `NowPlayingPanel(None)` cannot be constructed without a window in this environment, the implementer may pass a minimal stub object as `parent_window`; the constructor only stores it.)

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/test_header.py -q`. Expected: `AttributeError: header` FAILs.

- [ ] **Step 3: Implement** — in `now_playing.py`:

1. Add `from .header import Header` next to the other `.controls` import.
2. Replace the "Row 1: nav row" block (the `nav_row` Box, the `NavColumn()` setup with `set_hexpand`/`set_halign`, and `card.append(nav_row)`, ~lines 36-48) with:

```python
        # --- Row 1: header (nameplate, live plate, folder tabs) ---
        self.nav_column = NavColumn()
        self.nav_column.connect("nav-selected", lambda nav, name: self.emit("nav-selected", name))
        self.header = Header(self.nav_column, _INFO_PANEL_WIDTH)
        card.append(self.header)
```

3. Delete the `lbl_station` and `lbl_now_playing` creation blocks from `info_panel` (the two `Gtk.Label(xalign=0.0)` blocks with css classes `info-line` / `meta-title`, and their `info_panel.append(...)` calls). Leave `lbl_previous`, `pills_row`, the pills and `info_scroll` untouched. Update the "Row 3" comment to say the panel now holds only Previous tracks + pills.
4. Replace the five text call sites:
   - `self.lbl_station.set_markup(` → `self.header.set_station(` (in `reset_ui` and `_update_station_line`)
   - `self.lbl_now_playing.set_markup(` → `self.header.set_track(` (in `reset_ui`, and both branches of `update`)
5. Remove the brand overlay: delete the `card_overlay = Gtk.Overlay()` … `card_overlay.add_overlay(lbl_brand)` block (including the `lbl_brand` comment) and replace `self.append(card_overlay)` with `self.append(card)`.
6. In `_set_stale`, add one line at the end of the method body: `self.header.set_stale(stale)`.
7. Add:

```python
    def set_connected(self, connected: bool):
        self.header.set_connected(connected)
```

In `window.py` `_apply_daemon_state`, add as the first statement after the `_keep_running` guard, before `self.now_playing.update(...)`:

```python
        self.now_playing.set_connected(resp is not None)
```

In `common.py`, delete the now-unused `.brand-tag {{ … }}` block. Then `grep -rn "brand-tag\|nav-row\|nav-btn\|lbl_station\|lbl_now_playing" sqlch_gui tests` must print nothing.

- [ ] **Step 4: Run to verify pass** — full test command; no new failures vs baseline.

- [ ] **Step 5: Try launching** — if `WAYLAND_DISPLAY` is set and `gtk4-layer-shell` resolves, run `timeout 8 python -m sqlch_gui` from the worktree (inside the same nix-shell) and record any traceback / `Gtk-CRITICAL`; if it cannot start, say why. Do not leave a process running.

- [ ] **Step 6: Commit**

```bash
git add sqlch_gui/ui/now_playing.py sqlch_gui/ui/window.py sqlch_gui/ui/common.py tests/test_header.py
git commit -m "sqlch-gui: header replaces nav row + brand tag; plate shows track/station

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Merge and deploy (controller + Phil; no subagent)

- [ ] Final whole-branch review with the ledger's deferred minors; fix wave if needed.
- [ ] Fast-forward `sqlch-header` into `~/sqlch` `main`; remove the worktree and branch.
- [ ] **Phil decides:** pushing `~/sqlch` `main` to `github:SW-philip/sqlch` (outward-facing; not done without his say-so). sqlch reaches the nixos config as flake input `github:SW-philip/sqlch` (`flake.nix:45`), and `pkgs/sqlch/default.nix` separately pins `rev = 394d75f5…` via `fetchFromGitHub` — before `nrs`, check which of the two actually supplies `sqlch-gui` on each host, then `nix flake update sqlch` (and bump that rev/sha256 only if that pin is the GUI's source), `git add`, `nrs`.
- [ ] Phil's eyeball (screenshot-assisted): connected + playing, connected + stopped, daemon stopped (LED hollow + snark), a very long track title (popup width must NOT change), drawer open/close via each tab, tab accent contrast on several `drmis` themes.
- [ ] Update memory `sqlch_house_style_followup.md` with the outcome.
