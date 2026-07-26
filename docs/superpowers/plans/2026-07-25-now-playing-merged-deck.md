# Now Playing Merged Deck Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure sqlch_gui's Now Playing card from a busy, multi-patch layout into a single merged deck patch with one plain-text readout, per `docs/superpowers/specs/2026-07-25-now-playing-merged-deck-design.md`.

**Architecture:** All changes live in three files: `sqlch_gui/ui/controls.py` (simplify `ThreadSlider`, flatten `NavColumn`, retire `RecordBubble`), `sqlch_gui/ui/common.py` (CSS — drop hem/border from inner elements, add REC-tag and readout CSS), and `sqlch_gui/ui/now_playing.py` (the layout rewrite that ties it together). No test infrastructure exists in this repo (a GTK4/Wayland popup with Cairo-drawn widgets isn't practically unit-tested); every task ends with a manual verification step against a live dev instance instead of an automated test run, consistent with how prior specs/plans in this repo (e.g. `2026-07-12-sqlch-gui-compact-scale-plan.md`) have handled verification.

**Tech Stack:** Python 3, GTK4 (PyGObject), Gtk4LayerShell, Cairo (via PyGObject's `cairo` bindings).

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

### Task 1: Simplify ThreadSlider's volume mechanic

**Files:**
- Modify: `sqlch_gui/ui/controls.py:28-286` (the `ThreadSlider` class)

- [ ] **Step 1: Replace the class docstring and geometry constants**

Replace lines 28-58 (class docstring through the geometry constants) with:

```python
class ThreadSlider(Gtk.DrawingArea):
    """Full-width volume fader: a plain dot riding a dotted sewing
    thread. Backs onto a Gtk.Adjustment, same as before -- click
    anywhere on the thread to jump there; drag the button; scroll to
    nudge.

    Scrolling up while already at 100% engages a hard-coded 120% volume
    boost: the button docks in a small overflow zone past the track's
    right edge and re-colors hot (palette FORTE). The adjustment itself
    is never changed by boosting; only NowPlayingPanel's boost-toggled
    handler drives the actual wpctl volume change. Scrolling down while
    boosted disengages it and resumes normal volume stepping. There is
    no drag-to-boost gesture -- boost is scroll-only, and drag/click
    always operate on the plain 0-100% range.
    """

    __gsignals__ = {
        'value-changed': (GObject.SignalFlags.RUN_LAST, None, (float,)),
        'boost-toggled': (GObject.SignalFlags.RUN_LAST, None, (bool,)),
    }

    # Single source of truth for the button's edge margin and the
    # boost-overflow zone reserved past the track's right edge, so
    # drawing and hit-testing can never drift apart.
    _MARGIN = 8.0
    _BOOST_ZONE = 16.0
```

- [ ] **Step 2: Update `_usable_width`/`_button_x`/`_track_right`, drop `_nub_x`**

Replace lines 106-116 (`_usable_width` through `_nub_x`) with:

```python
    def _usable_width(self, width: float) -> float:
        return width - 2.0 * self._MARGIN - self._BOOST_ZONE

    def _button_x(self, width: float) -> float:
        return self._MARGIN + self._norm() * self._usable_width(width)

    def _track_right(self, width: float) -> float:
        return self._MARGIN + self._usable_width(width)
```

- [ ] **Step 3: Rewrite `_on_draw`**

Replace the whole `_on_draw` method (lines 118-189) with:

```python
    def _on_draw(self, area, cr, width, height, user_data=None):
        cy = height / 2.0
        track_right = self._track_right(width)
        button_x = track_right + self._BOOST_ZONE if self.boosted else self._button_x(width)

        colors = palette.load()
        bar_rgb = _hex_to_rgb_floats(colors.get('BAR', '#6e6a86'))
        thread_rgb = _shade(bar_rgb, 1.15)
        button_rgb = _shade(bar_rgb, 1.05)
        forte_rgb = _hex_to_rgb_floats(colors.get('FORTE', '#eb6f92'))

        # The sewing thread: evenly spaced dots across the track only --
        # drawn as discrete filled circles rather than a cairo dashed
        # stroke, since a dashed stroke's phase drifts against the pixel
        # grid and beats, making some dots read fainter or skipped
        # entirely.
        cr.save()
        cr.set_source_rgba(*thread_rgb, 0.7)
        dot_spacing = 6.0
        x = self._MARGIN - 2.0
        while x <= track_right:
            cr.arc(x, cy, 1.0, 0, 2 * math.pi)
            cr.fill()
            x += dot_spacing
        cr.restore()

        if self.boosted:
            # Filled overflow highlight showing the boosted zone is active.
            cr.save()
            cr.set_source_rgba(*forte_rgb, 0.35)
            cr.rectangle(track_right, cy - 2.0, self._BOOST_ZONE, 4.0)
            cr.fill()
            cr.restore()

        # The button: a small flat disc with a hint of a highlight so it
        # still reads as round, nothing more. Hot-colored (FORTE) while
        # boosted, neutral otherwise.
        base_rgb = forte_rgb if self.boosted else button_rgb
        radius = 6.0
        gradient = cairo.RadialGradient(
            button_x - radius * 0.3, cy - radius * 0.3, radius * 0.1,
            button_x, cy, radius,
        )
        gradient.add_color_stop_rgba(0.0, *_shade(base_rgb, 1.3), 1.0)
        gradient.add_color_stop_rgba(1.0, *_shade(base_rgb, 0.8), 1.0)
        cr.set_source(gradient)
        cr.arc(button_x, cy, radius, 0, 2 * math.pi)
        cr.fill()
```

- [ ] **Step 4: Simplify click, drag, and scroll handlers**

Replace `_on_click` through `_on_drag_end` (lines 191-274) with:

```python
    def _on_click(self, gesture, n_press, x, y):
        if self._dragging:
            return
        width = self.get_width()
        usable = self._usable_width(width)
        if usable <= 0:
            return
        if self.boosted:
            self.boosted = False
            self._update_tooltip()
            self.emit('boost-toggled', False)
        self._set_from_norm((x - self._MARGIN) / usable)

    def _on_drag_begin(self, gesture, start_x, start_y):
        self.drag_start_val = self.adj.get_value()
        self.grab_focus()

    def _on_drag_update(self, gesture, offset_x, offset_y):
        self._dragging = True
        width = self.get_width()
        usable = self._usable_width(width)
        if usable <= 0:
            return
        if self.boosted:
            self.boosted = False
            self._update_tooltip()
            self.emit('boost-toggled', False)
        total_range = self.adj.get_upper() - self.adj.get_lower()
        delta_norm = offset_x / usable
        raw_val = self.drag_start_val + delta_norm * total_range
        new_val = max(self.adj.get_lower(), min(self.adj.get_upper(), raw_val))
        self.adj.set_value(new_val)
        self.emit('value-changed', new_val)

    def _on_drag_end(self, gesture, offset_x, offset_y):
        # Deferred to idle so any 'released' from the co-installed
        # GestureClick for this same button-up is still guarded by
        # _dragging, no matter which controller GTK dispatches first.
        GLib.idle_add(self._clear_dragging)
```

Also drop the `self._drag_from_nub = False` line from `__init__` (it's no longer read anywhere) and remove the `drag_start_val = 0.0` / `self._dragging = False` pair's neighboring `_drag_from_nub` init specifically -- keep the other two.

- [ ] **Step 5: Rewrite `_on_scroll` and `_update_tooltip`**

Replace `_update_tooltip` (lines 91-95) with:

```python
    def _update_tooltip(self):
        self.set_tooltip_text(
            "Scroll down to restore volume" if self.boosted
            else "Scroll up at max volume for a 120% boost"
        )
```

Replace `_on_scroll` (lines 276-286) with:

```python
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

- [ ] **Step 6: Verify manually**

Launch the dev instance (see launch section above). Play a station, then:
1. Click at various points along the volume thread -- value jumps directly under the cursor, no dead zone.
2. Drag the button -- follows the cursor smoothly across the full 0-100% range.
3. With volume at 100%, scroll up -- button docks in the overflow zone, turns red/hot, tooltip changes to "Scroll down to restore volume", actual system volume audibly increases (verify with `wpctl get-volume @DEFAULT_AUDIO_SINK@` showing `1.20`).
4. Scroll down once while boosted -- button returns to the track at the pre-boost position, volume restores.
5. Drag the button while boosted -- boost disengages immediately and the drag takes over from wherever boost was (no nub to fight).

Kill the dev instance.

- [ ] **Step 7: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/controls.py
git commit -m "$(cat <<'EOF'
refactor(sqlch-gui): replace ThreadSlider's drag-nub boost with scroll-to-boost

Simplifies the volume fader per the merged-deck redesign spec: plain
click/drag across the full 0-100% range, boost past 100% moves to
scroll-wheel-only so there's no nub geometry to navigate around.
EOF
)"
```

---

### Task 2: Flatten NavColumn into a horizontal row

**Files:**
- Modify: `sqlch_gui/ui/controls.py:412-462` (`NavColumn.__init__`)
- Modify: `sqlch_gui/ui/common.py:117-125` (remove `.sidebar`)

- [ ] **Step 1: Change orientation and drop the sidebar background class**

In `controls.py`, in `NavColumn.__init__` (around line 428), change:

```python
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class("sidebar")
        self.set_valign(Gtk.Align.CENTER)
```

to:

```python
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.set_valign(Gtk.Align.CENTER)
```

Also update the class docstring's opening line (line 413) from `"""Vertical nav-icon rail: Mini (collapse), Library, Discover.` to `"""Horizontal nav-icon row: Mini (collapse), Library, Discover.` -- leave the rest of the docstring (the behavior description) unchanged, it's still accurate.

- [ ] **Step 2: Remove the now-unused `.sidebar` CSS rule**

In `common.py`, delete the entire `.sidebar { ... }` block (lines 117-125):

```python
    .sidebar {{
        background-color: {colors.get('GRAD_STAGE_LO', '#b04343')};
        background-image: {svg_tactile_filter}, linear-gradient(130deg, {colors.get('GRAD_STAGE_HI', '#d35f5f')}, {colors.get('GRAD_STAGE_LO', '#b04343')});
        background-repeat: repeat, no-repeat;
        border-radius: 10px;
        padding: 4px 2px;
        border: 2px dashed {thread};
        box-shadow: 0 0 0 2px transparent, {slight}, {hem(5)};
    }}
```

- [ ] **Step 3: Verify manually**

Launch the dev instance. Confirm:
1. The Mini/Library/Discover icons now sit in a horizontal row (not a vertical rail) with no separately-colored background patch behind them.
2. Clicking Library opens the drawer and highlights the Library icon; clicking Discover switches to Discover; clicking Mini (or re-clicking the active one) collapses/no-ops correctly, same as before.
3. Dragging the drawer's seam still syncs the nav row's active highlight (`NavColumn.set_active`) correctly.

Kill the dev instance.

- [ ] **Step 4: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/controls.py sqlch_gui/ui/common.py
git commit -m "$(cat <<'EOF'
refactor(sqlch-gui): flatten NavColumn to a horizontal row

Drops the vertical sidebar rail and its own background patch, per the
merged-deck redesign spec -- nav icons now sit directly on the card.
EOF
)"
```

---

### Task 3: Strip decorative CSS from inner elements, add REC-tag and readout styles

**Files:**
- Modify: `sqlch_gui/ui/common.py`

- [ ] **Step 1: Simplify `.cover-art`**

Replace (around line 165-172):

```python
    .cover-art {{
        background-color: {colors.get('WING', '#e2dacf')};
        border-radius: 10px;
        min-width: 98px;
        min-height: 98px;
        border: 2px dashed {thread};
        box-shadow: 0 0 0 1px transparent, {slight}, {hem(5)};
    }}
```

with:

```python
    .cover-art {{
        background-color: {colors.get('WING', '#e2dacf')};
        border-radius: 10px;
        min-width: 98px;
        min-height: 98px;
        box-shadow: {slight};
    }}
```

- [ ] **Step 2: Simplify `.control-btn` and `.control-btn.primary`**

Replace the whole block (around lines 271-305) with:

```python
    .control-btn {{
        border-radius: 11px;
        min-width: 28px;
        min-height: 28px;
        padding: 0;
        background-color: {colors.get('WING', '#f2ece1')};
        color: {score};
        box-shadow: {slight};
        transition: transform 80ms ease, box-shadow 80ms ease;
    }}
    .control-btn:hover {{
        background-color: {colors.get('MUTE', '#e5dcce')};
        box-shadow: 0 0 0 1px {outline}, {slight_lift};
        transform: translateY(-1px);
    }}
    .control-btn:active {{
        transform: translateY(2px);
        box-shadow: {slight_press};
    }}
    .control-btn.primary {{
        min-width: 36px;
        min-height: 36px;
        border-radius: 13px;
        background-color: {colors.get('PIANO', '#2c2c30')};
        color: {colors.get('HALL', '#fdf8ee')};
        box-shadow: 0 0 0 2px {outline}, {slight};
        text-shadow: 0 -1px 0 rgba(255,255,255,0.30), 0 1px 2px rgba({staff}, 0.70);
    }}
    .control-btn.primary:hover {{
        background-color: {colors.get('SOTTO', '#454549')};
        box-shadow: 0 0 0 2px {outline}, {slight_lift};
    }}
```

- [ ] **Step 3: Add `.corner-tag-rec` and `.readout-line`**

Directly after the existing `.corner-tag-right { ... }` block (around line 199), insert:

```python
    .corner-tag-rec {{
        background-color: {colors.get('MUTE', '#e5dcce')};
        color: {colors.get('BAR', '#6b6b70')};
        transform: rotate(-4deg);
    }}
    .corner-tag-rec.active {{
        background-color: {colors.get('FORTE', '#8c3b3b')};
        color: {colors.get('HALL', '#fdf8ee')};
    }}
```

Directly after the `.knob-tag { ... }` block (around line 413), insert:

```python
    .readout-line {{
        font-family: "Courier New", monospace;
        font-size: 0.72em;
        color: {colors.get('BAR', '#6b6b70')};
        letter-spacing: 0.02em;
    }}
```

- [ ] **Step 4: Verify manually (visual smoke test only -- full behavior verified in Task 4)**

Launch the dev instance. Confirm the app still starts without CSS parse errors or GTK warnings about unknown properties (check the terminal output), and that Stop/Mute/Play buttons and the cover art still render (they'll look slightly flatter -- no dashed border -- which is expected; the REC tag and readout line aren't wired up until Task 4, so nothing new is visible yet).

Kill the dev instance.

- [ ] **Step 5: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/common.py
git commit -m "$(cat <<'EOF'
style(sqlch-gui): drop dashed-hem borders from cover art and control buttons

Per the merged-deck redesign spec, only the outer popup window and the
card patch keep a stitched border now. Also adds .corner-tag-rec and
.readout-line, used by the next task's layout rewrite.
EOF
)"
```

---

### Task 4: Restructure NowPlayingPanel into the merged deck layout

**Files:**
- Modify: `sqlch_gui/ui/now_playing.py` (whole file effectively rewritten; see below for exact replacements)

This is the task that ties Tasks 1-3 together and actually changes what the card looks like. It's one coherent rewrite of `NowPlayingPanel`, done in ordered steps so intermediate states stay syntactically valid, but only the final step (launching the app) proves it actually works -- there's no way to test GTK layout code without running it.

- [ ] **Step 1: Update the import and mode-label constant**

Replace lines 1-12:

```python
"""Now Playing layout, stream management controls, and metadata rendering."""

import html
import threading
from pathlib import Path
from gi.repository import Gtk, GLib, GdkPixbuf, GObject

from .. import daemon, metadata
from .controls import ThreadSlider, RecordBubble, NavColumn
from .eq_strip import EqStrip

_REC_MODE_LABELS = {"full": "FULL", "track": "TRK"}
```

with:

```python
"""Now Playing layout, stream management controls, and metadata rendering."""

import html
import threading
from pathlib import Path
from gi.repository import Gtk, GLib, GdkPixbuf, GObject

from .. import daemon, metadata
from .controls import ThreadSlider, NavColumn
from .eq_strip import EqStrip

_REC_MODE_LABELS = {"full": "F", "track": "T"}
```

- [ ] **Step 2: Rewrite `__init__`**

Replace the entire `__init__` method (from `def __init__(self, parent_window):` through the line before `def clear_cover(self):`, i.e. lines 19-253) with:

```python
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

        self.nav_column = NavColumn()
        self.nav_column.connect("nav-selected", lambda nav, name: self.emit("nav-selected", name))
        nav_row.append(self.nav_column)

        self.lbl_readout = Gtk.Label(xalign=1.0)
        self.lbl_readout.add_css_class("readout-line")
        self.lbl_readout.set_hexpand(True)
        self.lbl_readout.set_halign(Gtk.Align.END)
        nav_row.append(self.lbl_readout)

        card.append(nav_row)

        # --- Row 2: cover art (with its 4 corner tags) + text, EQ behind text ---
        art_text_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.cover_img = Gtk.Image()
        self.cover_img.set_pixel_size(98)
        self.cover_placeholder = Gtk.Label(label="♪")
        self.cover_placeholder.add_css_class("cover-glyph")

        self.cover_stack = Gtk.Stack()
        self.cover_stack.add_css_class("cover-art")
        self.cover_stack.add_named(self.cover_placeholder, "placeholder")
        self.cover_stack.add_named(self.cover_img, "art")
        self.clear_cover()

        track_scroll = Gtk.ScrolledWindow()
        track_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        track_scroll.set_size_request(98, 98)
        track_scroll.add_css_class("art-card-back")

        self.track_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.track_list_box.add_css_class("tracklist-container")
        track_scroll.set_child(self.track_list_box)

        self.deck_stack = Gtk.Stack()
        self.deck_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.deck_stack.set_transition_duration(250)
        self.deck_stack.add_named(self.cover_stack, "front")
        self.deck_stack.add_named(track_scroll, "back")

        self.stack_wrapper = Gtk.Box()
        self.stack_wrapper.add_css_class("album-deck-wrapper")
        self.stack_wrapper.append(self.deck_stack)

        self.cover_overlay = Gtk.Overlay()
        self.cover_overlay.set_child(self.stack_wrapper)

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

        self.flip_btn = Gtk.Button(icon_name="object-flip-horizontal-symbolic")
        self.flip_btn.add_css_class("corner-tag-flip")
        self.flip_btn.set_halign(Gtk.Align.END)
        self.flip_btn.set_valign(Gtk.Align.END)
        self.flip_btn.connect("clicked", self.on_flip_clicked)
        self.cover_overlay.add_overlay(self.flip_btn)

        # REC corner tag (bottom-left, 4th corner) -- replaces RecordBubble.
        # Plain text tag from the same .corner-tag family as LIVE/format;
        # left-click toggles recording, right-click cycles FULL/TRACK mode.
        self.rec_tag = Gtk.Button(label="REC")
        self.rec_tag.add_css_class("corner-tag")
        self.rec_tag.add_css_class("corner-tag-rec")
        self.rec_tag.set_halign(Gtk.Align.START)
        self.rec_tag.set_valign(Gtk.Align.END)
        self.rec_tag.connect("clicked", self.on_record_clicked)
        rec_right_click = Gtk.GestureClick.new()
        rec_right_click.set_button(3)
        rec_right_click.connect("released", self.on_rec_mode_cycle)
        self.rec_tag.add_controller(rec_right_click)
        self.cover_overlay.add_overlay(self.rec_tag)

        art_text_row.append(self.cover_overlay)

        # Title/artist/genre text, with the EQ strip painted behind it.
        # The Overlay sizes to its main child (eq_strip) by default, which
        # would clip the text block -- set_measure_overlay tells it to
        # also account for the text_box overlay child's own size.
        self.eq_strip = EqStrip()
        self.eq_strip.set_halign(Gtk.Align.FILL)
        self.eq_strip.set_valign(Gtk.Align.CENTER)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_box.set_halign(Gtk.Align.START)
        text_box.set_valign(Gtk.Align.CENTER)
        self.lbl_title = Gtk.Label(xalign=0.0, justify=Gtk.Justification.LEFT)
        self.lbl_title.add_css_class("meta-title")
        self.lbl_title.set_wrap(True)
        self.lbl_title.set_max_width_chars(22)

        self.lbl_artist = Gtk.Label(xalign=0.0, justify=Gtk.Justification.LEFT)
        self.lbl_artist.add_css_class("meta-artist")
        self.lbl_artist.set_wrap(True)
        self.lbl_artist.set_max_width_chars(22)

        self.lbl_genre = Gtk.Label(xalign=0.0, justify=Gtk.Justification.LEFT)
        self.lbl_genre.add_css_class("thread-label")

        text_box.append(self.lbl_title)
        text_box.append(self.lbl_artist)
        text_box.append(self.lbl_genre)

        text_overlay = Gtk.Overlay()
        text_overlay.set_child(self.eq_strip)
        text_overlay.add_overlay(text_box)
        text_overlay.set_measure_overlay(text_box, True)
        text_overlay.set_hexpand(True)
        art_text_row.append(text_overlay)

        card.append(art_text_row)

        # --- Row 3: Stop / Volume / Mute / Play, one merged control row ---
        control_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        btn_stop = Gtk.Button(icon_name="media-playback-stop-symbolic")
        btn_stop.add_css_class("control-btn")
        btn_stop.connect("clicked", self.on_stop)
        control_row.append(btn_stop)

        self.vol_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=1.0, step_increment=0.05)
        self.vol_slider = ThreadSlider(self.vol_adj)
        self._vol_handler = self.vol_slider.connect("value-changed", self.on_vol_changed)
        self._pre_boost_vol: float | None = None
        self.vol_slider.connect("boost-toggled", self.on_boost_toggled)
        self.vol_slider.set_hexpand(True)
        control_row.append(self.vol_slider)

        self.btn_mute = Gtk.Button(icon_name="audio-volume-high-symbolic")
        self.btn_mute.add_css_class("control-btn")
        self.btn_mute.connect("clicked", self.on_toggle_mute)
        control_row.append(self.btn_mute)

        self.btn_toggle = Gtk.Button()
        self.btn_toggle.add_css_class("control-btn")
        self.btn_toggle.add_css_class("primary")
        self.btn_toggle.connect("clicked", self.on_toggle_play)
        control_row.append(self.btn_toggle)

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
        # guarantee stop/mute/knob clicks below always reach their real targets.
        lbl_brand.set_can_target(False)
        card_overlay.add_overlay(lbl_brand)
        self.append(card_overlay)

        self._cur_station_id = None
        self._cur_artist = None
        self._cur_title = None
        self._loaded = False
        self._vol = 0.0
        self._bitrate = None
        self._channels = None
        self._bt = False
        self._device_name = None
        self._rec_mode = "full"
        self._rec_active = False
        self._rec_elapsed = 0
        self.reset_ui()
```

- [ ] **Step 3: Rewrite `reset_ui`**

Replace the `reset_ui` method with:

```python
    def reset_ui(self):
        self.lbl_title.set_markup("<b>Not Playing</b>")
        self.lbl_artist.set_text("Select a station from the library")
        self._set_genre(None)
        self.btn_toggle.set_icon_name("media-playback-start-symbolic")
        self.eq_strip.set_active(False)
        self.lbl_live_tag.set_visible(False)
        self.lbl_format_tag.set_visible(False)
        self._vol = 0.0
        self._bitrate = None
        self._channels = None
        self._bt = False
        self._device_name = None
        self._update_readout()
        self._rec_mode = "full"
        self._rec_active = False
        self._rec_elapsed = 0
        self._update_rec_tag()
        self.clear_cover()
        self._cur_station_id = None
        self._cur_artist = None
        self._cur_title = None

        # Sync back-plate layout status
        self.stack_wrapper.remove_css_class("flipped")
        self.deck_stack.set_visible_child_name("front")
```

- [ ] **Step 4: Add `_update_readout` and `_update_rec_tag` helpers**

Insert these two new methods directly after `reset_ui` (before `get_current_id`):

```python
    def _update_readout(self):
        parts = []
        parts.append(f"{int(self._vol * 100)}%")
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
        letter = _REC_MODE_LABELS[self._rec_mode]
        self.rec_tag.set_label(f"REC·{letter}")
        if self._rec_active:
            self.rec_tag.add_css_class("active")
            m, s = divmod(self._rec_elapsed, 60)
            self.rec_tag.set_tooltip_text(f"Recording {m:02d}:{s:02d} · left-click to stop · right-click: mode")
        else:
            self.rec_tag.remove_css_class("active")
            self.rec_tag.set_tooltip_text("Left-click to record · right-click: mode")
```

- [ ] **Step 5: Replace REC signal handlers with the tag's click/right-click handlers**

Find `on_record_toggled` and `on_rec_mode_changed` (near the bottom of the file, just before `on_toggle_play`):

```python
    def on_record_toggled(self, knob, mode):
        daemon.send({"cmd": "record", "action": "toggle", "mode": mode})

    def on_rec_mode_changed(self, knob, mode):
        self.lbl_rec_mode.set_text(_REC_MODE_LABELS[mode])
```

Replace them with:

```python
    def on_record_clicked(self, btn):
        daemon.send({"cmd": "record", "action": "toggle", "mode": self._rec_mode})

    def on_rec_mode_cycle(self, gesture, n_press, x, y):
        if self._rec_active:
            return  # mode locked while a take is rolling
        modes = ("full", "track")
        i = modes.index(self._rec_mode)
        self._rec_mode = modes[(i + 1) % len(modes)]
        self._update_rec_tag()
```

- [ ] **Step 6: Rewrite `on_vol_changed` and `update_indicators`**

Replace `on_vol_changed`:

```python
    def on_vol_changed(self, slider, val):
        self._vol = val
        self._update_readout()
        import subprocess
        subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{val:.2f}"], stdout=subprocess.DEVNULL)
```

Replace `update_indicators` (its full body, keeping the same signature) with:

```python
    def update_indicators(self, bitrate: int | None, vol: float, muted: bool, bt: bool, playing: bool,
                          channels: int | None, recording: dict | None = None, fmt: str | None = None,
                          device_name: str | None = None):
        self._loaded = playing
        self.btn_toggle.set_icon_name("media-playback-pause-symbolic" if playing else "media-playback-start-symbolic")
        self.eq_strip.set_active(playing)

        # Block signals temporarily to prevent loopback configuration cascades
        self.vol_slider.handler_block(self._vol_handler)
        self.vol_adj.set_value(vol)
        self.vol_slider.handler_unblock(self._vol_handler)

        if muted:
            self.btn_mute.set_icon_name("audio-volume-muted-symbolic")
        elif vol < 0.4:
            self.btn_mute.set_icon_name("audio-volume-low-symbolic")
        elif vol < 0.8:
            self.btn_mute.set_icon_name("audio-volume-medium-symbolic")
        else:
            self.btn_mute.set_icon_name("audio-volume-high-symbolic")

        self._vol = vol
        self._bitrate = bitrate
        self._channels = channels
        self._bt = bt
        self._device_name = device_name
        self._update_readout()

        if fmt:
            self.lbl_format_tag.set_text(fmt)
            self.lbl_format_tag.set_visible(True)
        else:
            self.lbl_format_tag.set_visible(False)

        rec = recording or {}
        self._rec_active = bool(rec.get("active"))
        mode = rec.get("mode")
        if mode in ("full", "track"):
            self._rec_mode = mode
        self._rec_elapsed = int(rec.get("elapsed", 0))
        self._update_rec_tag()
```

- [ ] **Step 7: Sanity-check the file for leftover references**

Run a search to confirm nothing still references the removed widgets:

```bash
cd /home/prepko/sqlch
grep -n "rec_knob\|lbl_rec_mode\|lbl_rec\b\|lbl_vol_percent\|lbl_bitrate\|lbl_channels\|lbl_bt\b\|lbl_device\|tech_box\|deck_box\|right_col\|rec_wrap\|RecordBubble" sqlch_gui/ui/now_playing.py
```

Expected: no output. If anything shows up, it's a leftover reference from the old layout that step 2-6 should have replaced -- fix it before continuing.

- [ ] **Step 8: Verify manually against the full spec testing checklist**

Launch the dev instance. Walk through:
1. Card renders as one merged patch -- nav row on top, art+text row, control row, only the card's own border and the outer window frame visible (no per-element dashed borders inside).
2. Nav row is horizontal with no separate background patch; Mini/Library/Discover selection and drawer-seam sync still work (from Task 2, re-confirm here since layout changed around it).
3. Readout line (bottom-right of nav row) shows/hides segments correctly: play a station and confirm `NN% · NNNk · Stereo · BT · <device>`-style text appears/disappears matching bitrate/channels/BT/device availability.
4. EQ strip animates behind the title/artist text while playing, is inert when stopped, doesn't visually collide with or get clipped by the text (confirms `set_measure_overlay` sizing worked).
5. REC tag (bottom-left of cover art): left-click toggles recording (turns red, tooltip shows elapsed time), right-click cycles FULL/TRACK (`REC·F` / `REC·T` updates immediately), right-click is a no-op while actively recording.
6. Volume slider behavior from Task 1 still holds inside the new control row.
7. Play button is visually larger/emphasized in the control row; Stop and Mute are smaller flanking buttons; all three are comfortably clickable.
8. LIVE tag, format tag, and flip-to-tracklist corner tags still appear/behave exactly as before (unaffected by this task).
9. Switch `palette.sh` to a different theme and confirm the simplified `.cover-art`/`.control-btn` styling and new `.corner-tag-rec`/`.readout-line` still read correctly (colors sourced from palette, not hardcoded).

Kill the dev instance.

- [ ] **Step 9: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/now_playing.py
git commit -m "$(cat <<'EOF'
refactor(sqlch-gui): merge Now Playing into a single deck layout

Replaces the flanked nav/art/transport columns and 6-chip readout strip
with three rows (nav+readout, art+text, controls) in one card patch.
REC moves from the RecordBubble widget to a 4th corner tag on the cover
art. Implements the merged-deck redesign spec.
EOF
)"
```

---

### Task 5: Delete the now-unused RecordBubble class

**Files:**
- Modify: `sqlch_gui/ui/controls.py:289-409` (delete the `RecordBubble` class)

- [ ] **Step 1: Confirm nothing references it anymore**

```bash
cd /home/prepko/sqlch
grep -rn "RecordBubble" sqlch_gui/
```

Expected: no output (Task 4 already dropped the import and usage in `now_playing.py`).

- [ ] **Step 2: Delete the class**

Delete the entire `RecordBubble` class definition (lines 289-409 in the original file -- from `class RecordBubble(Gtk.DrawingArea):` through the end of its `_on_draw` method, i.e. everything between the `ThreadSlider` class and the `NavColumn` class).

- [ ] **Step 3: Verify manually**

Launch the dev instance. Confirm the app starts cleanly with no `ImportError` or `NameError`, and the Now Playing card still looks/behaves exactly as it did at the end of Task 4 (this step is a pure deletion, no behavior change).

Kill the dev instance.

- [ ] **Step 4: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/controls.py
git commit -m "$(cat <<'EOF'
refactor(sqlch-gui): remove RecordBubble, superseded by the REC corner tag

Dead code following the merged-deck redesign -- recording is now
controlled from the cover art's REC corner tag (now_playing.py).
EOF
)"
```

---

### Task 6: Final cross-theme QA pass

**Files:** none (verification only)

- [ ] **Step 1: Full walkthrough**

Launch the dev instance. Re-run the full checklist from the design spec's "Testing" section end to end in one sitting (not per-task in isolation this time), including:
1. Library and Discover panels are visually unchanged from before this redesign (confirms the "out of scope" boundary held -- no accidental CSS bleed from the `.control-btn`/`.cover-art` changes, since neither class is used there).
2. Switch through at least two `palette.sh` themes and re-check the merged card, REC tag, and readout line in each.
3. Resize/reopen the popup a few times (mini <-> library <-> discover <-> mini) to confirm the drawer spring-snap animation and seam drag still feel unchanged (Task 2/4 didn't touch `window.py`).

- [ ] **Step 2: Report results**

If everything in the spec's testing checklist passes, the redesign is complete. If anything's off (spacing, wrapping, a missed reference), fix inline and re-verify rather than opening a new task -- this is polish on already-committed work, not new scope.
