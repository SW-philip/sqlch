# Live Radio Transport & Info Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework sqlch_gui's Now Playing transport row and info panel to match a live-radio mental model (VU-meter volume, one stop/play toggle, transport-bar record button, Station/Now-Playing/Previous context + diagnostics), plus drawer polish, per `docs/superpowers/specs/2026-07-31-live-radio-transport-design.md`.

**Architecture:** Six files change: `sqlch_gui/daemon.py` (new buffer-read helper), `sqlch_gui/ui/controls.py` (new `VolumeMeter` widget replacing `ThreadSlider`), `sqlch_gui/ui/common.py` (CSS: info-panel rename, art-caption removal, drawer polish), `sqlch_gui/ui/now_playing.py` (the big rewrite: info panel, transport row, the station-id unwrap bug fix), `sqlch_gui/ui/window.py` (thread buffer through to `update_indicators`, rename a stale widget reference), `sqlch_gui/ui/discover.py` (drawer polish). No test infrastructure exists in this repo (a GTK4/Wayland popup with Cairo-drawn widgets isn't practically unit-tested); every task ends with a manual verification step against a live dev instance instead of an automated test run, consistent with prior plans in this repo.

**Tech Stack:** Python 3, GTK4 (PyGObject), Gtk4LayerShell, Cairo (via PyGObject's `cairo` bindings).

## Global Constraints

- No Listeners diagnostic pill — no reliable data source exists (see spec's "Why").
- `EqStrip` the class stays untouched (still used by `station_list.py`'s mini now-playing indicator); only its use as `now_playing.py`'s volume-slider backing is removed.
- The album-tracklist-enrichment view is fully retired, not kept as a fallback (per spec, confirmed with the user).

---

## Dev instance launch (used by every verification step below)

```bash
pkill -f "python3 -m sqlch_gui"
```

Then, in a separate command, read the installed wrapper for current env vars (the nix store hash changes on rebuild, so re-read each time) and launch the working tree with `/home/prepko/sqlch` first in `PYTHONPATH`:

```bash
head -30 /etc/profiles/per-user/prepko/bin/sqlch-gui
# copy the export lines (especially LD_PRELOAD=.../libgtk4-layer-shell.so), then:
PYTHONPATH=/home/prepko/sqlch:$PYTHONPATH LD_PRELOAD=<path-from-wrapper> python3 -m sqlch_gui
```

A clean launch has no layer-shell warnings in its output; `VK_SUBOPTIMAL` Gdk warnings are benign noise. Kill the instance (by PID, separate command) once each verification step is done — don't leave dev instances running between tasks.

---

### Task 1: Add `daemon.get_stream_buffer()`

**Files:**
- Modify: `sqlch_gui/daemon.py:104-109` (right after `get_stream_format`)

- [ ] **Step 1: Add the helper**

Insert immediately after `get_stream_format` (which ends at line 109, right before `def get_sink_name():`):

```python
def get_stream_buffer() -> int | None:
    """Return mpv's cache-buffering-state (0-100), or None."""
    val = _mpv_get_property("cache-buffering-state")
    if val is not None:
        try:
            return int(val)
        except (ValueError, TypeError):
            pass
    return None
```

- [ ] **Step 2: Verify manually**

Launch the dev instance, play any station, then in a separate terminal:

```bash
python3 -c "
import sys; sys.path.insert(0, '/home/prepko/sqlch')
from sqlch_gui import daemon
print(daemon.get_stream_buffer())
"
```

Expected: an int between 0 and 100 (mpv reports full buffer at 100 once caching settles). If it prints `None` while a station is confirmed playing, double check `mpv_socket()`/`MPV_SOCK` resolves to the running instance's socket before treating this as a bug — a stale/missing socket path would also legitimately return `None`.

Kill the dev instance.

- [ ] **Step 3: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/daemon.py
git commit -m "$(cat <<'EOF'
feat(sqlch-gui): add get_stream_buffer daemon helper

Reads mpv's cache-buffering-state property, same _mpv_get_property
pattern as get_stream_bitrate/get_stream_channels. Backs the new
Buffer diagnostic pill in the Now Playing info panel.
EOF
)"
```

---

### Task 2: Replace `ThreadSlider` with `VolumeMeter` in `controls.py`

**Files:**
- Modify: `sqlch_gui/ui/controls.py:1-216` (imports, `_hex_to_rgb_floats`/`_shade` helpers, `ThreadSlider` class)

`RecordBubble` and `NavColumn` (lines 219 onward) are untouched by this task.

- [ ] **Step 1: Replace imports, helpers, and the whole `ThreadSlider` class**

Replace lines 1-216 (everything from the module docstring through the end of `ThreadSlider._on_scroll`) with:

```python
"""Custom GTK 4 tactile controls: pop-it bubble, VU-meter volume, spool nav rail."""

import math
import cairo
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GObject, GLib
from .. import palette


def _hex_to_rgb_floats(hex_val: str) -> tuple[float, float, float]:
    h = hex_val.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return r, g, b


class VolumeMeter(Gtk.DrawingArea):
    """Segmented volume VU meter: pips fill left-to-right with the current
    volume level, colored on a green-to-red gradient. Click a pip to jump
    the volume to that segment; scroll to nudge. Reads as a level meter,
    not a scrubber -- unlike the ThreadSlider it replaces, there is no
    drag gesture at all.

    Scrolling up while already at 100% engages the same 120% boost
    ThreadSlider had: an extra hot-colored overflow pip lights up past the
    N_SEGMENTS regular pips. The adjustment itself is never changed by
    boosting; only NowPlayingPanel's boost-toggled handler drives the
    actual wpctl volume change.
    """

    __gsignals__ = {
        'value-changed': (GObject.SignalFlags.RUN_LAST, None, (float,)),
        'boost-toggled': (GObject.SignalFlags.RUN_LAST, None, (bool,)),
    }

    N_SEGMENTS = 10
    _GAP = 2.0
    _MARGIN = 2.0

    def __init__(self, adjustment: Gtk.Adjustment):
        super().__init__()
        self.adj = adjustment
        self.boosted = False
        self.set_focusable(True)
        self.set_hexpand(True)
        self.set_size_request(-1, 18)

        self.adj.connect("value-changed", lambda _: self.queue_draw())
        self.set_draw_func(self._on_draw)
        self._update_tooltip()

        click_gest = Gtk.GestureClick.new()
        click_gest.set_button(1)
        click_gest.connect("released", self._on_click)
        self.add_controller(click_gest)

        scroll_gest = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll_gest.connect("scroll", self._on_scroll)
        self.add_controller(scroll_gest)

    def _update_tooltip(self):
        self.set_tooltip_text(
            "Scroll down to restore volume" if self.boosted
            else "Scroll up at max volume for a 120% boost"
        )

    def _norm(self) -> float:
        return (self.adj.get_value() - self.adj.get_lower()) / (self.adj.get_upper() - self.adj.get_lower())

    def _set_from_norm(self, norm: float):
        norm = max(0.0, min(1.0, norm))
        new_val = self.adj.get_lower() + norm * (self.adj.get_upper() - self.adj.get_lower())
        self.adj.set_value(new_val)
        self.emit('value-changed', new_val)

    def _segment_rects(self, width: float, height: float) -> list[tuple[float, float, float, float]]:
        """(x, y, w, h) for each of the N_SEGMENTS regular pips, evenly
        spaced across the widget width."""
        usable = width - 2.0 * self._MARGIN
        seg_w = (usable - self._GAP * (self.N_SEGMENTS - 1)) / self.N_SEGMENTS
        rects = []
        for i in range(self.N_SEGMENTS):
            x = self._MARGIN + i * (seg_w + self._GAP)
            rects.append((x, 0.0, seg_w, height))
        return rects

    @staticmethod
    def _rounded_bar(cr, x, y, w, h):
        r = min(w / 2.0, h / 2.0, 3.0)
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()

    def _on_draw(self, area, cr, width, height, user_data=None):
        colors = palette.load()
        low_rgb = _hex_to_rgb_floats(colors.get('SEVENTH', '#79a383'))
        hot_rgb = _hex_to_rgb_floats(colors.get('FORTE', '#eb6f92'))

        norm = self._norm()
        filled = round(norm * self.N_SEGMENTS)
        rects = self._segment_rects(width, height)

        for i, (x, y, w, h) in enumerate(rects):
            t = i / (self.N_SEGMENTS - 1)
            r = low_rgb[0] + (hot_rgb[0] - low_rgb[0]) * t
            g = low_rgb[1] + (hot_rgb[1] - low_rgb[1]) * t
            b = low_rgb[2] + (hot_rgb[2] - low_rgb[2]) * t
            alpha = 1.0 if i < filled else 0.18
            cr.set_source_rgba(r, g, b, alpha)
            self._rounded_bar(cr, x, y + 2.0, w, h - 4.0)
            cr.fill()

        if self.boosted:
            last_x = rects[-1][0] + rects[-1][2]
            overflow_w = width - self._MARGIN - last_x - self._GAP
            if overflow_w > 0:
                cr.set_source_rgba(*hot_rgb, 0.9)
                self._rounded_bar(cr, last_x + self._GAP, 2.0, overflow_w, height - 4.0)
                cr.fill()

    def _on_click(self, gesture, n_press, x, y):
        width = self.get_width()
        usable = width - 2.0 * self._MARGIN
        if usable <= 0:
            return
        if self.boosted:
            self.boosted = False
            self._update_tooltip()
            self.emit('boost-toggled', False)
        seg_w = usable / self.N_SEGMENTS
        idx = int((x - self._MARGIN) / seg_w)
        idx = max(0, min(self.N_SEGMENTS - 1, idx))
        self._set_from_norm((idx + 1) / self.N_SEGMENTS)

    def _on_scroll(self, controller, dx, dy):
        increasing = dy < 0
        if self.boosted:
            if increasing:
                return  # already at the 120% cap, nothing more to do
            self.boosted = False
            self._update_tooltip()
            self.emit('boost-toggled', False)
            self.queue_draw()
            return
        if increasing and self.adj.get_value() >= self.adj.get_upper() - 1e-6:
            self.boosted = True
            self._update_tooltip()
            self.emit('boost-toggled', True)
            self.queue_draw()
            return
        total_range = self.adj.get_upper() - self.adj.get_lower()
        step = total_range * 0.05
        new_val = self.adj.get_value() + (step if increasing else -step)
        new_val = max(self.adj.get_lower(), min(self.adj.get_upper(), new_val))
        self.adj.set_value(new_val)
        self.emit('value-changed', new_val)
```

(`colorsys` and the `_shade` helper are dropped entirely — nothing left in this file uses them once `ThreadSlider`'s gradient-shading is gone; `RecordBubble`'s gradients use raw RGBA tuples directly and `NavColumn` only needs `_hex_to_rgb_floats`.)

- [ ] **Step 2: Fix `NavColumn`'s docstring, which name-drops the class being removed**

`NavColumn` itself (further down the file, untouched by Step 1's replace range) has a stray reference to the old class name. Replace:

```python
    already established by ThreadSlider and RecordBubble.
    """
```

with:

```python
    already established by VolumeMeter and RecordBubble.
    """
```

- [ ] **Step 3: Verify manually (import-level only — this widget isn't wired into any layout until Task 4)**

```bash
cd /home/prepko/sqlch
python3 -c "
import sys; sys.path.insert(0, '.')
import gi
gi.require_version('Gtk', '4.0')
from sqlch_gui.ui.controls import VolumeMeter, RecordBubble, NavColumn
print('imports OK')
"
```

Expected: `imports OK`, no `ImportError`/`AttributeError`. Real interactive verification (click/scroll/boost) happens in Task 4 once `VolumeMeter` is actually placed in the transport row.

- [ ] **Step 4: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/controls.py
git commit -m "$(cat <<'EOF'
feat(sqlch-gui): replace ThreadSlider with a segmented VolumeMeter

Volume becomes a 10-segment VU-meter-style widget (click a pip to set
level, scroll to nudge, no drag) instead of a dot dragged over a
decorative EQ strip, which read as a timeline scrubber on a live
stream. The 120% boost mechanic carries over unchanged. Not yet wired
into any layout -- next task connects it into the transport row.
EOF
)"
```

---

### Task 3: CSS updates in `common.py` for the info panel

**Files:**
- Modify: `sqlch_gui/ui/common.py:20-30` (drop unused `dim_rgb`)
- Modify: `sqlch_gui/ui/common.py:112-152` (`.cover-art`, `.art-caption` family, `.cover-glyph`)
- Modify: `sqlch_gui/ui/common.py:504-524` (`.tracklist-panel` → `.info-panel`, `.tracklist-container label` → `.info-line`)

- [ ] **Step 1: Drop the now-unused `dim_rgb` variable**

Replace:

```python
    outline = colors.get('SHADOW', '#121214')
    score = colors.get('SCORE', '#121214')
    score_rgb = _hex_to_rgb(score)
    dim_rgb = _hex_to_rgb(colors.get('DIM', '#4c4e3c'))
    staff = colors.get('STAFF', '20,20,24')
```

with:

```python
    outline = colors.get('SHADOW', '#121214')
    score = colors.get('SCORE', '#121214')
    score_rgb = _hex_to_rgb(score)
    staff = colors.get('STAFF', '20,20,24')
```

- [ ] **Step 2: Remove the `.art-caption` family (the title/artist/genre overlay is gone; text now lives in the info panel below the art)**

Replace:

```python
    /* Size kept in sync with _COVER_SIZE in now_playing.py */
    .cover-art {{
        background-color: {colors.get('WING', '#e2dacf')};
        border-radius: 10px;
        border: 2px solid {outline};
        min-width: 220px;
        min-height: 220px;
        box-shadow: {slight};
    }}
    /* Title/artist/genre scrim docked to the art's bottom edge, tinted with
       the palette's DIM color. GTK CSS has no backdrop-filter/blur, so a
       translucent panel stands in for "blurred glass" while staying legible
       over arbitrary album art. */
    .art-caption {{
        background-color: rgba({dim_rgb}, 0.72);
        border-radius: 0 0 8px 8px;
        padding: 4px 8px 3px;
    }}
    /* Base .meta-title/.meta-artist/.thread-label colors are tuned for the
       light .card background -- override for legibility against this dark
       scrim, tinted with ROOT (niri's active-window-border color, see
       ~/nixos/home/niri/config.kdl.nix) so the overlay reads as "focused"
       the same way a niri window does. */
    .art-caption .meta-title, .art-caption .meta-artist {{
        color: {colors.get('ROOT', '#fdf8ee')};
        text-shadow: 0 1px 2px rgba({staff}, 0.9);
    }}
    .art-caption .thread-label {{
        color: rgba(255, 255, 255, 0.55);
    }}
    .art-caption .thread-label.lit {{
        color: {colors.get('ROOT', '#f4b84b')};
    }}
    .cover-glyph {{
        font-size: 38px;
        font-weight: 900;
        color: {colors.get('PIANO', '#2c2c30')};
        text-shadow: 0 2px 0 {lite_c};
        transform: rotate(-6deg);
    }}
```

with:

```python
    /* Size kept in sync with _COVER_SIZE in now_playing.py */
    .cover-art {{
        background-color: {colors.get('WING', '#e2dacf')};
        border-radius: 10px;
        border: 2px solid {outline};
        min-width: 220px;
        min-height: 220px;
        box-shadow: {slight};
    }}
    .cover-glyph {{
        font-size: 38px;
        font-weight: 900;
        color: {colors.get('PIANO', '#2c2c30')};
        text-shadow: 0 2px 0 {lite_c};
        transform: rotate(-6deg);
    }}
```

- [ ] **Step 3: Rename the tracklist-panel classes to info-panel/info-line**

Replace:

```python
    /* Tracklist panel - permanent full-width row below the meta text,
       no longer a flip-card back face. Looks like a typewriter ledger
       scrap pasted to cardboard. */
    .tracklist-panel {{
        background-color: {colors.get('STAGE', '#f9f6f0')};
        border-radius: 12px;
        border: 2px solid {outline};
        box-shadow: inset 0 0 4px rgba({staff}, 0.15), {cutout(3, 3)}, {slight};
        padding: 6px;
    }}

    /* Track info container styling */
    .tracklist-container label {{
        font-family: "Courier New", monospace;
        font-size: 0.72em;
        font-weight: bold;
        color: {colors.get('PIANO', '#2c2c30')};
        padding: 2px;
        text-shadow: 0 1px 0 {lite_c};
    }}

    """
```

with:

```python
    /* Radio-context info panel - permanent full-width row below the
       album art showing Station/Now Playing/Previous-tracks context
       plus stream diagnostic pills. Same cardboard-ledger look the
       former tracklist panel had. */
    .info-panel {{
        background-color: {colors.get('STAGE', '#f9f6f0')};
        border-radius: 12px;
        border: 2px solid {outline};
        box-shadow: inset 0 0 4px rgba({staff}, 0.15), {cutout(3, 3)}, {slight};
        padding: 6px;
    }}

    /* Station/Previous line styling -- monospace ledger look. The Now
       Playing line uses .meta-title instead, for visual prominence. */
    .info-line {{
        font-family: "Courier New", monospace;
        font-size: 0.72em;
        font-weight: bold;
        color: {colors.get('PIANO', '#2c2c30')};
        text-shadow: 0 1px 0 {lite_c};
    }}

    """
```

- [ ] **Step 4: Verify manually**

Launch the dev instance. Confirm the app starts without CSS parse errors or GTK warnings about unknown properties (check terminal output). The card will look unchanged for now — `now_playing.py` still references `.art-caption`/`.tracklist-panel`/`.tracklist-container` until Task 4, so this step only checks the CSS itself is valid Python/GTK CSS (no `dim_rgb`/`_hex_to_rgb` NameError, no malformed braces).

Kill the dev instance.

- [ ] **Step 5: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/common.py
git commit -m "$(cat <<'EOF'
style(sqlch-gui): rename tracklist-panel CSS to info-panel, drop art-caption

Drops the .art-caption overlay family (title/artist/genre text moves
off the album art into the info panel below it) and the now-unused
dim_rgb variable, and renames .tracklist-panel/.tracklist-container to
.info-panel/.info-line ahead of the info-panel rewrite in now_playing.py.
EOF
)"
```

---

### Task 4: Rewrite `NowPlayingPanel` — info panel, transport row, bug fix

**Files:**
- Modify: `sqlch_gui/ui/now_playing.py` (near-total rewrite)
- Modify: `sqlch_gui/ui/window.py:294-324` (`_daemon_monitor_loop`/`_apply_daemon_state`: thread buffer through)
- Modify: `sqlch_gui/ui/window.py:284-289` (`_reload_palette`: rename `vol_slider` → `vol_meter`)

This is the task that ties Tasks 1-3 together and actually changes what the card looks like and does. It's one coherent rewrite of `NowPlayingPanel` (imports, `__init__`, `reset_ui`, `update`, `update_indicators`, and several method renames/removals), done as a single replacement so intermediate states can't leave `update()` calling methods that no longer exist. It also carries the prerequisite bug fix from the spec (part 0): `resp["current"]` is `{"type": "station", "item": station}`, not a flat station dict — the station id/name/frequency now come from `curr.get("item") or {}` instead of `curr` directly. Lands in a single commit at the end.

- [ ] **Step 1: Replace the entire contents of `sqlch_gui/ui/now_playing.py`**

```python
"""Now Playing layout, stream management controls, and metadata rendering."""

import html
import threading
from collections import deque
from pathlib import Path
from gi.repository import Gtk, GLib, GdkPixbuf, GObject

from .. import daemon, metadata
from .controls import VolumeMeter, RecordBubble, NavColumn

_REC_MODE_LABELS = {"full": "F", "track": "T"}
_COVER_SIZE = 220     # keep in sync with .cover-art's min-width/min-height in common.py


class NowPlayingPanel(Gtk.Box):
    __gsignals__ = {
        'nav-selected': (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.set_margin_start(3)
        self.set_margin_end(3)
        self.set_margin_top(3)
        self.set_margin_bottom(3)
        self.set_valign(Gtk.Align.CENTER)
        self.win = parent_window

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.add_css_class("card")

        # --- Row 1: nav row + plain-text readout ---
        nav_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        nav_row.add_css_class("nav-row")

        self.nav_column = NavColumn()
        self.nav_column.connect("nav-selected", lambda nav, name: self.emit("nav-selected", name))
        nav_row.append(self.nav_column)

        self.lbl_readout = Gtk.Label(xalign=1.0)
        self.lbl_readout.add_css_class("readout-line")
        self.lbl_readout.set_hexpand(True)
        self.lbl_readout.set_halign(Gtk.Align.END)
        nav_row.append(self.lbl_readout)

        card.append(nav_row)

        # --- Row 2: album art, full card width, corner tags overlaid ---
        self.cover_img = Gtk.Image()
        self.cover_img.set_pixel_size(_COVER_SIZE)
        self.cover_placeholder = Gtk.Label(label="♪")
        self.cover_placeholder.add_css_class("cover-glyph")

        self.cover_stack = Gtk.Stack()
        self.cover_stack.add_css_class("cover-art")
        self.cover_stack.add_named(self.cover_placeholder, "placeholder")
        self.cover_stack.add_named(self.cover_img, "art")
        self.clear_cover()

        self.cover_overlay = Gtk.Overlay()
        self.cover_overlay.set_child(self.cover_stack)
        self.cover_overlay.set_halign(Gtk.Align.CENTER)

        self.lbl_live_tag = Gtk.Label(label="LIVE")
        self.lbl_live_tag.add_css_class("corner-tag")
        self.lbl_live_tag.add_css_class("corner-tag-left")
        self.lbl_live_tag.set_halign(Gtk.Align.START)
        self.lbl_live_tag.set_valign(Gtk.Align.START)
        self.lbl_live_tag.set_visible(False)
        self.cover_overlay.add_overlay(self.lbl_live_tag)

        self.lbl_format_tag = Gtk.Label()
        self.lbl_format_tag.add_css_class("corner-tag")
        self.lbl_format_tag.add_css_class("corner-tag-right")
        self.lbl_format_tag.set_halign(Gtk.Align.END)
        self.lbl_format_tag.set_valign(Gtk.Align.START)
        self.lbl_format_tag.set_visible(False)
        self.cover_overlay.add_overlay(self.lbl_format_tag)

        # REC corner tag (bottom-right) -- a passive status indicator now;
        # the transport row's RecordBubble owns the actual record controls.
        self.rec_tag = Gtk.Label(label="REC")
        self.rec_tag.add_css_class("corner-tag")
        self.rec_tag.add_css_class("corner-tag-rec")
        self.rec_tag.set_halign(Gtk.Align.END)
        self.rec_tag.set_valign(Gtk.Align.END)
        self.cover_overlay.add_overlay(self.rec_tag)

        card.append(self.cover_overlay)

        # --- Row 3: radio-context info panel (Station / Now Playing /
        # Previous tracks) plus stream diagnostic pills ---
        info_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        info_panel.add_css_class("info-panel")

        self.lbl_station = Gtk.Label(xalign=0.0)
        self.lbl_station.add_css_class("info-line")
        self.lbl_station.set_wrap(True)
        self.lbl_station.set_max_width_chars(30)
        info_panel.append(self.lbl_station)

        self.lbl_now_playing = Gtk.Label(xalign=0.0)
        self.lbl_now_playing.add_css_class("meta-title")
        self.lbl_now_playing.set_wrap(True)
        self.lbl_now_playing.set_max_width_chars(30)
        info_panel.append(self.lbl_now_playing)

        self.lbl_previous = Gtk.Label(xalign=0.0)
        self.lbl_previous.add_css_class("info-line")
        self.lbl_previous.set_wrap(True)
        self.lbl_previous.set_max_width_chars(30)
        self.lbl_previous.set_visible(False)
        info_panel.append(self.lbl_previous)

        pills_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.pill_codec = Gtk.Label()
        self.pill_codec.add_css_class("tech-badge")
        self.pill_codec.set_visible(False)
        self.pill_bitrate = Gtk.Label()
        self.pill_bitrate.add_css_class("tech-badge")
        self.pill_bitrate.set_visible(False)
        self.pill_buffer = Gtk.Label()
        self.pill_buffer.add_css_class("tech-badge")
        self.pill_buffer.set_visible(False)
        pills_row.append(self.pill_codec)
        pills_row.append(self.pill_bitrate)
        pills_row.append(self.pill_buffer)
        info_panel.append(pills_row)

        card.append(info_panel)

        # --- Row 4: RecordBubble / stop-play toggle | speaker + volume meter ---
        control_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.rec_bubble = RecordBubble()
        self.rec_bubble.connect("record-toggled", self.on_record_clicked)
        self.rec_bubble.connect("mode-changed", lambda w, m: self._update_rec_tag())
        control_row.append(self.rec_bubble)

        self.btn_toggle = Gtk.Button()
        self.btn_toggle.add_css_class("control-btn")
        self.btn_toggle.add_css_class("primary")
        self.btn_toggle.connect("clicked", self.on_toggle_play)
        control_row.append(self.btn_toggle)

        control_row.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        self.speaker_icon = Gtk.Image(icon_name="audio-volume-high-symbolic")
        self.speaker_icon.set_valign(Gtk.Align.CENTER)
        control_row.append(self.speaker_icon)

        self.vol_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=1.0, step_increment=0.05)
        self.vol_meter = VolumeMeter(self.vol_adj)
        self._vol_handler = self.vol_meter.connect("value-changed", self.on_vol_changed)
        self._pre_boost_vol: float | None = None
        self.vol_meter.connect("boost-toggled", self.on_boost_toggled)
        self.vol_meter.set_hexpand(True)
        control_row.append(self.vol_meter)

        card.append(control_row)

        card_overlay = Gtk.Overlay()
        card_overlay.set_child(card)
        lbl_brand = Gtk.Label(label="sqlch")
        lbl_brand.add_css_class("brand-tag")
        lbl_brand.set_halign(Gtk.Align.END)
        lbl_brand.set_valign(Gtk.Align.START)
        # Purely decorative: a bare Gtk.Label added via Gtk.Overlay.add_overlay()
        # does NOT click-through by default (Gtk.Widget.pick() resolves to the
        # topmost can_target widget at a point, regardless of whether it has any
        # click handling), so explicitly opt this label out of hit-testing to
        # guarantee toggle/meter clicks below always reach their real targets.
        lbl_brand.set_can_target(False)
        card_overlay.add_overlay(lbl_brand)
        self.append(card_overlay)

        self._cur_station_id = None
        self._cur_frequency = None
        self._cur_artist = None
        self._cur_title = None
        self._live_station_name = None
        self._history: deque[tuple[str, str]] = deque(maxlen=3)
        self._loaded = False
        self._vol = 0.0
        self._bitrate = None
        self._channels = None
        self._bt = False
        self._device_name = None
        self._rec_active = False
        self._rec_elapsed = 0
        self.reset_ui()

    def clear_cover(self):
        self.cover_stack.set_visible_child_name("placeholder")

    def reset_ui(self):
        self.lbl_station.set_text("")
        self.lbl_now_playing.set_markup("<b>Not Playing</b>")
        self.lbl_previous.set_visible(False)
        self.btn_toggle.set_icon_name("media-playback-start-symbolic")
        self.lbl_live_tag.set_visible(False)
        self.lbl_format_tag.set_visible(False)
        self.pill_codec.set_visible(False)
        self.pill_bitrate.set_visible(False)
        self.pill_buffer.set_visible(False)
        self._vol = 0.0
        self._bitrate = None
        self._channels = None
        self._bt = False
        self._device_name = None
        self._update_readout()
        self._rec_active = False
        self._rec_elapsed = 0
        self.rec_bubble.set_state(False, "full")
        self._update_rec_tag()
        self.clear_cover()
        self._cur_station_id = None
        self._cur_frequency = None
        self._cur_artist = None
        self._cur_title = None
        self._live_station_name = None
        self._history.clear()

    def _update_readout(self):
        parts = []
        if self._bitrate:
            parts.append(f"{self._bitrate}k")
        if self._channels:
            parts.append("Stereo" if self._channels == 2 else "Mono" if self._channels == 1 else f"{self._channels}Ch")
        if self._bt:
            parts.append("BT")
        if self._device_name:
            parts.append(self._device_name)
        self.lbl_readout.set_text(" · ".join(parts))

    def _update_rec_tag(self):
        letter = _REC_MODE_LABELS[self.rec_bubble.mode]
        self.rec_tag.set_text(f"REC·{letter}")
        if self._rec_active:
            self.rec_tag.add_css_class("active")
            m, s = divmod(self._rec_elapsed, 60)
            self.rec_tag.set_tooltip_text(f"Recording {m:02d}:{s:02d}")
        else:
            self.rec_tag.remove_css_class("active")
            self.rec_tag.set_tooltip_text("Idle")

    def get_current_id(self) -> str | None:
        return self._cur_station_id

    def get_current_track(self) -> tuple[str | None, str | None]:
        return self._cur_artist, self._cur_title

    def _update_station_line(self):
        freq_txt = f"{self._cur_frequency:.1f} FM · " if self._cur_frequency else ""
        genre = metadata.get_icy_genre()
        if not genre and self._cur_artist and self._cur_title:
            meta = metadata.get_enriched_meta(self._cur_artist, self._cur_title)
            if meta and meta.get("genres"):
                genre = meta["genres"][0]
        suffix = f" · {html.escape(genre)}" if genre else ""
        name = html.escape(self._live_station_name or "Unknown Station")
        self.lbl_station.set_markup(f"<b>STATION</b>  {freq_txt}{name}{suffix}")

    def _update_previous_line(self):
        if not self._history:
            self.lbl_previous.set_visible(False)
            return
        lines = [
            f"{i}. {html.escape(a)} — {html.escape(t)}"
            for i, (a, t) in enumerate(self._history, start=1)
        ]
        self.lbl_previous.set_markup("<b>PREVIOUS</b>\n" + "\n".join(lines))
        self.lbl_previous.set_visible(True)

    def update(self, resp: dict | None, icy: tuple[str | None, str | None]):
        if not resp or not resp.get("ok") or not resp.get("current"):
            self.reset_ui()
            return

        curr = resp["current"]
        # resp["current"] is {"type": "station", "item": station}, not a
        # flat station dict -- id/name/frequency live under "item".
        item = curr.get("item") or {}
        station_id = item.get("id")
        station_name = item.get("name") or "Unknown Station"
        frequency = item.get("frequency")

        if station_id != self._cur_station_id:
            self._history.clear()

        self._cur_station_id = station_id
        self._cur_frequency = frequency
        self._live_station_name = station_name

        raw_artist, raw_title = icy
        artist = raw_artist.strip() if raw_artist else ""
        title = raw_title.strip() if raw_title else ""

        if not artist and not title:
            self.clear_cover()
            self.lbl_live_tag.set_visible(True)
            self.lbl_now_playing.set_markup("<i>Live Stream</i>")
            self._cur_artist, self._cur_title = None, None
        else:
            self.lbl_live_tag.set_visible(False)
            display_artist = artist or "Unknown Artist"
            display_title = title or "Unknown Track"
            self.lbl_now_playing.set_markup(
                f"<b>{html.escape(display_artist)} — {html.escape(display_title)}</b>"
            )

            if artist != self._cur_artist or title != self._cur_title:
                if self._cur_artist or self._cur_title:
                    self._history.appendleft(
                        (self._cur_artist or "Unknown Artist", self._cur_title or "Unknown Track")
                    )
                self._cur_artist = artist
                self._cur_title = title
                metadata.run_enrich(artist, title)
                threading.Thread(target=self._async_fetch_cover, args=(artist, title), daemon=True).start()

        self._update_station_line()
        self._update_previous_line()

    def _async_fetch_cover(self, artist: str, title: str):
        import time
        time.sleep(3.0)  # give sqlch-enrich time to write enriched.json
        if self._cur_artist != artist or self._cur_title != title:
            return  # track already changed, bail
        path, mode = metadata.get_cover_info(artist, title)
        if mode == "remote" and path:
            import hashlib
            h = hashlib.md5(f"{artist.lower()}|{title.lower()}".encode()).hexdigest()
            local_path = metadata.COVERS_DIR / f"{h}.jpg"
            if metadata.download_cover(path, local_path):
                path = str(local_path)
                mode = "local"

        if mode == "local" and path and Path(path).exists():
            GLib.idle_add(self._apply_cover_path, path, artist, title)

    def _apply_cover_path(self, path: str, artist: str, title: str) -> bool:
        if self._cur_artist == artist and self._cur_title == title:
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, _COVER_SIZE, _COVER_SIZE, True)
                self.cover_img.set_from_pixbuf(pb)
                self.cover_stack.set_visible_child_name("art")
            except Exception:
                self.clear_cover()
        return False

    def update_indicators(self, bitrate: int | None, vol: float, muted: bool, bt: bool, playing: bool,
                          channels: int | None, recording: dict | None = None, fmt: str | None = None,
                          device_name: str | None = None, buffer: int | None = None):
        self._loaded = playing
        self.btn_toggle.set_icon_name("media-playback-stop-symbolic" if playing else "media-playback-start-symbolic")

        # Block signals temporarily to prevent loopback configuration cascades
        self.vol_meter.handler_block(self._vol_handler)
        self.vol_adj.set_value(vol)
        self.vol_meter.handler_unblock(self._vol_handler)

        if muted:
            self.speaker_icon.set_from_icon_name("audio-volume-muted-symbolic")
        elif vol < 0.4:
            self.speaker_icon.set_from_icon_name("audio-volume-low-symbolic")
        elif vol < 0.8:
            self.speaker_icon.set_from_icon_name("audio-volume-medium-symbolic")
        else:
            self.speaker_icon.set_from_icon_name("audio-volume-high-symbolic")

        self._vol = vol
        self._bitrate = bitrate
        self._channels = channels
        self._bt = bt
        self._device_name = device_name
        self._update_readout()

        if fmt:
            self.lbl_format_tag.set_text(fmt)
            self.lbl_format_tag.set_visible(True)
            self.pill_codec.set_text(f"Codec: {fmt}")
            self.pill_codec.set_visible(True)
        else:
            self.lbl_format_tag.set_visible(False)
            self.pill_codec.set_visible(False)

        if bitrate:
            self.pill_bitrate.set_text(f"Bitrate: {bitrate} kbps")
            self.pill_bitrate.set_visible(True)
        else:
            self.pill_bitrate.set_visible(False)

        if buffer is not None:
            self.pill_buffer.set_text(f"Buffer: {buffer}%")
            self.pill_buffer.set_visible(True)
        else:
            self.pill_buffer.set_visible(False)

        rec = recording or {}
        self._rec_active = bool(rec.get("active"))
        mode = rec.get("mode")
        if mode not in ("full", "track"):
            mode = self.rec_bubble.mode
        self.rec_bubble.set_state(self._rec_active, mode)
        self._rec_elapsed = int(rec.get("elapsed", 0))
        self._update_rec_tag()

    def on_record_clicked(self, bubble, mode):
        daemon.send({"cmd": "record", "action": "toggle", "mode": mode})

    def on_toggle_play(self, btn):
        if self._loaded:
            daemon.send({"cmd": "stop"})
        else:
            daemon.send({"cmd": "play", "query": "__last__"})

    def on_vol_changed(self, meter, val):
        self._vol = val
        self._update_readout()
        import subprocess
        subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{val:.2f}"], stdout=subprocess.DEVNULL)

    def on_boost_toggled(self, meter, active):
        import subprocess
        if active:
            self._pre_boost_vol = self.vol_adj.get_value()
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "1.20"], stdout=subprocess.DEVNULL)
        else:
            restore = self._pre_boost_vol if self._pre_boost_vol is not None else 0.0
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{restore:.2f}"], stdout=subprocess.DEVNULL)
            self._pre_boost_vol = None
```

Removed entirely versus the old file: `on_stop`, `on_toggle_mute`, `on_rec_mode_cycle`, `_set_genre`, `_sync_tracklist`, `_async_resync_tracklist`, `_fmt_duration`, `_TRACKLIST_HEIGHT`, `self.eq_strip`/`vol_overlay` wiring, `self.track_list_box`, `caption_box`.

- [ ] **Step 2: Thread the buffer reading through `window.py`'s daemon poll**

Replace (`window.py:294-324`):

```python
    def _daemon_monitor_loop(self):
        import time
        from .. import metadata
        while self._keep_running:
            resp = daemon.send({"cmd": "status"})
            icy = metadata.get_icy_track()
            vol, muted = daemon.get_vol_state()
            bitrate = daemon.get_stream_bitrate()
            channels = daemon.get_stream_channels()
            fmt = daemon.get_stream_format()
            device_name = daemon.get_sink_name()

            GLib.idle_add(
                self._apply_daemon_state,
                resp, icy, vol, muted, bitrate, channels, fmt, device_name
            )
            time.sleep(1.0)

    def _apply_daemon_state(self, resp, icy, vol, muted, bitrate, channels, fmt, device_name) -> bool:
        if not self._keep_running:
            return False
        self.now_playing.update(resp, icy=icy)
        playing = bool(resp and resp.get("ok") and resp.get("current"))
        recording = resp.get("recording") if resp else None
        self.now_playing.update_indicators(
            bitrate, vol, muted, self._bt_active, playing, channels,
            recording=recording, fmt=fmt, device_name=device_name,
        )
        artist, title = self.now_playing.get_current_track()
        self.station_list.set_active(self.now_playing.get_current_id(), artist, title)
        return False
```

with:

```python
    def _daemon_monitor_loop(self):
        import time
        from .. import metadata
        while self._keep_running:
            resp = daemon.send({"cmd": "status"})
            icy = metadata.get_icy_track()
            vol, muted = daemon.get_vol_state()
            bitrate = daemon.get_stream_bitrate()
            channels = daemon.get_stream_channels()
            fmt = daemon.get_stream_format()
            device_name = daemon.get_sink_name()
            buffer = daemon.get_stream_buffer()

            GLib.idle_add(
                self._apply_daemon_state,
                resp, icy, vol, muted, bitrate, channels, fmt, device_name, buffer
            )
            time.sleep(1.0)

    def _apply_daemon_state(self, resp, icy, vol, muted, bitrate, channels, fmt, device_name, buffer) -> bool:
        if not self._keep_running:
            return False
        self.now_playing.update(resp, icy=icy)
        playing = bool(resp and resp.get("ok") and resp.get("current"))
        recording = resp.get("recording") if resp else None
        self.now_playing.update_indicators(
            bitrate, vol, muted, self._bt_active, playing, channels,
            recording=recording, fmt=fmt, device_name=device_name, buffer=buffer,
        )
        artist, title = self.now_playing.get_current_track()
        self.station_list.set_active(self.now_playing.get_current_id(), artist, title)
        return False
```

- [ ] **Step 3: Fix the stale `vol_slider` reference in `_reload_palette`**

Replace (`window.py:284-289`):

```python
    def _reload_palette(self) -> bool:
        self._pal_reload_pending = False
        load_custom_css()
        self.station_list.refresh()  # group headers bake palette hex into markup
        self.now_playing.vol_slider.queue_draw()  # zipper tape re-reads palette on next draw
        return False
```

with:

```python
    def _reload_palette(self) -> bool:
        self._pal_reload_pending = False
        load_custom_css()
        self.station_list.refresh()  # group headers bake palette hex into markup
        self.now_playing.vol_meter.queue_draw()  # VU meter re-reads palette on next draw
        return False
```

- [ ] **Step 4: Sanity-check for leftover references**

```bash
cd /home/prepko/sqlch
grep -n "vol_slider\|ThreadSlider\|eq_strip\|track_list_box\|caption_box\|art-caption\|tracklist-panel\|tracklist-container\|_sync_tracklist\|_set_genre\|on_toggle_mute\|on_stop\b\|on_rec_mode_cycle" sqlch_gui/ui/now_playing.py sqlch_gui/ui/window.py sqlch_gui/ui/common.py
```

Expected: no output (the `EqStrip` class definition itself in `sqlch_gui/ui/eq_strip.py` and its use in `sqlch_gui/ui/station_list.py` are untouched and won't match — this grep only targets the three files this task and Task 3 modified). If anything shows up, it's a leftover reference — fix it before continuing.

- [ ] **Step 5: Verify manually**

Launch the dev instance (see launch section above) and walk through:

1. Play a station that exposes ICY track tags. Confirm the info panel below the art shows **STATION** (frequency + name, plus genre if known), **NOW PLAYING** (`Artist — Title`, bold), and once a second track plays, **PREVIOUS** appears showing the prior track. Switch to a different station and confirm PREVIOUS clears (doesn't bleed across stations).
2. Play a station with no ICY tags. Confirm NOW PLAYING shows "Live Stream" (italic), PREVIOUS stays hidden, no crash or literal "None"/empty-string text anywhere.
3. Confirm the Codec/Bitrate/Buffer pills appear with real values while playing; if `daemon.get_stream_buffer()` legitimately returns `None` for some stream, confirm that one pill is simply absent (not blank).
4. Confirm the album art shows only LIVE (top-left)/format (top-right)/REC (bottom-right) corner badges — no title/artist/genre text overlaid on the art itself.
5. Transport row: RecordBubble left-click toggles recording (daemon reflects it within ~1s), right-click cycles FULL/TRACK mode and the corner REC badge's letter updates immediately (not just on the next poll tick). Confirm the corner REC badge is no longer clickable (no hover/press response).
6. Click the primary toggle button while playing: confirm it actually stops playback (check `sqlch status` or daemon state — mpv should exit/disconnect, not just go silent), and the button's icon shows the stop glyph while playing, play-triangle while idle. Click again to resume the last station.
7. Volume: click at a few different x-positions along the meter and confirm the filled-pip count matches; scroll up/down nudges by 5%; scrolling up at 100% engages the boost (hot overflow pip lights up), scrolling down disengages it. Confirm the speaker icon next to the meter changes with volume/mute state but isn't itself clickable.
8. Confirm the top readout (`lbl_readout`) no longer shows a volume percentage, but still shows bitrate/channels/BT/device name correctly.
9. In the Library drawer: confirm the active station's row now highlights (`.station-row.active`) and its mini-EQ indicator animates — this was silently broken before the bug fix in this task (station id was always `None`), so this is the regression check that the fix landed correctly.
10. Change the system theme (`palette.sh`) while the app is running; confirm the card, info panel, and VU meter all re-skin without errors.

Kill the dev instance.

- [ ] **Step 6: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/now_playing.py sqlch_gui/ui/window.py
git commit -m "$(cat <<'EOF'
refactor(sqlch-gui): live-radio transport row and info panel

Fixes a pre-existing bug where resp["current"]'s station id/name were
read off the wrong dict level (always None/"Unknown Station"), which
this rewrite's new Station line depends on -- it also fixes active-row
highlighting in the Library drawer as a side effect.

Replaces the album-tracklist-enrichment panel with a permanent
Station/Now-Playing/Previous-tracks block plus Codec/Bitrate/Buffer
diagnostic pills. Consolidates Stop/Pause/system-Mute into one
prominent stop/play toggle, wires the previously-unused RecordBubble
into the transport row (REC corner badge on the art becomes a passive
indicator), and swaps the volume slider for the new VolumeMeter widget
with the speaker icon beside it. Drops the volume percentage from the
top status readout now that volume is shown visually.

Implements docs/superpowers/specs/2026-07-31-live-radio-transport-design.md.
EOF
)"
```

---

### Task 5: Drawer polish (`discover.py`, `common.py`)

**Files:**
- Modify: `sqlch_gui/ui/discover.py:22-33` (search bar), `sqlch_gui/ui/discover.py:76` (results list vexpand)
- Modify: `sqlch_gui/ui/common.py` (new `.search-btn` class, `.station-live` recolor)

- [ ] **Step 1: Add a `.search-btn` CSS class so the search button matches the entry's height/border, add `results_box.set_vexpand`**

In `common.py`, insert a new class right after `.field-entry:focus-within` (which currently ends the CSS block just before the closing `"""`):

Replace:

```python
    .field-entry:focus-within {{
        border: 2px solid {colors.get('ROOT', '#f4b84b')};
        box-shadow: 0 0 0 2px {colors.get('ROOT', '#f4b84b')};
    }}
```

with:

```python
    .field-entry:focus-within {{
        border: 2px solid {colors.get('ROOT', '#f4b84b')};
        box-shadow: 0 0 0 2px {colors.get('ROOT', '#f4b84b')};
    }}

    /* Matches .field-entry's height/border/shadow so Discover's search
       button doesn't sit visually offset from the entry beside it. */
    .search-btn {{
        border-radius: 8px;
        padding: 4px 8px;
        border: 2px solid {outline};
        box-shadow: {cutout(2, 2)}, {slight_press};
        background-color: {colors.get('WING', '#fff5dd')};
        color: {score};
    }}
    .search-btn:hover {{
        background-color: {colors.get('MUTE', '#e5dcce')};
    }}
```

- [ ] **Step 2: Recolor `.station-live` to a brighter accent**

Replace:

```python
    .station-live {{
        font-size: 0.8em;
        font-style: italic;
        color: {colors.get('FIFTH', '#6b6b70')};
        text-shadow: 0 1px 0 {lite_c};
    }}
```

with:

```python
    .station-live {{
        font-size: 0.8em;
        font-style: italic;
        color: {colors.get('SEVENTH', '#79a383')};
        text-shadow: 0 1px 0 {lite_c};
    }}
```

(`.station-row.active .station-live`, which forces the HALL color when the row is the active station, is unaffected and needs no change.)

- [ ] **Step 3: Apply `.search-btn` and fix the results pane so it visibly fills empty space**

In `discover.py`, replace:

```python
        btn_go = Gtk.Button(icon_name="edit-find-symbolic")
        btn_go.connect("clicked", self.on_search)
```

with:

```python
        btn_go = Gtk.Button(icon_name="edit-find-symbolic")
        btn_go.add_css_class("search-btn")
        btn_go.connect("clicked", self.on_search)
```

Then replace:

```python
        self.results_box = Gtk.ListBox()
        self.results_box.add_css_class("list-plate")
        self.results_box.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll.set_child(self.results_box)
        self.append(scroll)
```

with:

```python
        self.results_box = Gtk.ListBox()
        self.results_box.add_css_class("list-plate")
        self.results_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.results_box.set_vexpand(True)
        scroll.set_child(self.results_box)
        self.append(scroll)
```

(`scroll` already has `set_vexpand(True)` — the missing piece was the `Gtk.ListBox` inside it not expanding to fill that space, which is what left `.list-plate`'s background looking like a void below a short or empty result list.)

- [ ] **Step 4: Verify manually**

Launch the dev instance, open the Discover drawer:

1. Confirm the search entry and its button now read as one aligned row (same height, matching border/shadow) rather than the button looking visually offset.
2. Before searching: confirm the (empty) results pane below the genre tag grid visibly fills the remaining drawer height with the `.list-plate` background, instead of stopping short and leaving a bare void.
3. Run a search or click a genre tag: confirm results render normally and the pane still fills correctly with a handful of rows.
4. Open the Library drawer: confirm each station row's "♫ ..." subtext (`.station-live`) now reads in a brighter accent color, legible against the row background, in at least two `palette.sh` themes.

Kill the dev instance.

- [ ] **Step 5: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/discover.py sqlch_gui/ui/common.py
git commit -m "$(cat <<'EOF'
style(sqlch-gui): tighten Discover search-bar alignment, fix void pane

Gives the Discover search button a .search-btn class matching the
entry's height/border so the row reads as aligned, sets vexpand on the
results ListBox (the ScrolledWindow around it already had vexpand, but
the list inside wasn't stretching, leaving its .list-plate background
looking like a void below a short/empty result list), and brightens
.station-live's subtext color for legibility in the Library drawer.
EOF
)"
```

---

### Task 6: Final cross-theme QA pass

**Files:** none (verification only)

- [ ] **Step 1: Full walkthrough**

Launch the dev instance. Re-run the design spec's full testing checklist end to end in one sitting (not per-task in isolation this time):

1. Play several different stations in a row (including at least one with no ICY tags, and one where enrichment/cover art is slow) and confirm the info panel (Station/Now Playing/Previous/pills) always reflects current reality with no stale data left over from a previous station.
2. Exercise the transport row fully: RecordBubble toggle + mode cycle, primary stop/play toggle, volume meter click/scroll/boost, speaker icon state — all in one sitting, back to back.
3. Confirm the top readout, Library drawer (active-row highlight, mini-EQ, brighter station-live subtext), and Discover drawer (aligned search bar, filled results pane) all together.
4. Switch through at least two `palette.sh` themes and re-check: album art corner badges, info panel, VU meter colors (including the boosted overflow pip), Library and Discover drawers.
5. Resize/reopen the popup a few times (mini ↔ library ↔ discover ↔ mini) to confirm the seam-drag drawer's spring-snap animation still feels unchanged.

- [ ] **Step 2: Report results**

If everything passes, the redesign is complete. If anything's off (spacing, a missed reference, a value that needs live-tuning like segment count or the search-button styling), fix inline and re-verify rather than opening a new task — this is polish on already-committed work, not new scope.
