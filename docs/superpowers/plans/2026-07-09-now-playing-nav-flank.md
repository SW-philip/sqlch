# Now Playing: Flanking Nav/Controls + Collapsible Dropdowns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flank the Now Playing album art with a nav column (Mini/Library/Discover) on the left and REC/Stop/Mute on the right, grow the art to match the button-stack height, and replace the window's 3-page `Gtk.Stack` nav model with a permanently-visible Now Playing block plus a capped-height Library/Discover dropdown underneath it.

**Architecture:** Two tasks. Task 1 adds a new, currently-unused `NavColumn` widget to `controls.py` (a self-contained, syntax-checkable addition that changes no runtime behavior). Task 2 does the full wiring in one pass — `now_playing.py`'s layout, `common.py`'s CSS, and `window.py`'s nav model — because `now_playing.py` and `window.py` change together (`NowPlayingPanel` starts emitting a `nav-selected` signal that only makes sense once `window.py` stops treating it as an interchangeable `Gtk.Stack` page), so splitting them into separately-runnable tasks would leave a broken intermediate app.

**Tech Stack:** Python 3.12, GTK4 (PyGObject), Cairo (pycairo). No test framework in this repo; pure-syntax changes are checked with `python3 -c "import ast; ast.parse(...)"` and GTK/visual changes are verified by running the app per the `sqlch-gui-dev-launch` memory (working tree + wrapper env + `LD_PRELOAD`, killed by PID once verified — never left running in the background).

**Spec:** `docs/superpowers/specs/2026-07-09-now-playing-nav-flank-design.md`

---

## Task 1: Add the `NavColumn` widget to `controls.py`

**Files:**
- Modify: `sqlch_gui/ui/controls.py:1` (module docstring)
- Modify: `sqlch_gui/ui/controls.py:422` (append new class at end of file)

- [ ] **Step 1: Update the module docstring**

Replace line 1:

```python
"""Custom GTK 4 tactile controls: pop-it bubble, thread-and-button volume slider."""
```

with:

```python
"""Custom GTK 4 tactile controls: pop-it bubble, thread-and-button volume slider, spool nav rail."""
```

- [ ] **Step 2: Append the `NavColumn` class**

The file currently ends at line 422 with `RecordBubble`'s last line (`cr.stroke_preserve()`). Append, separated by two blank lines (matching the existing separation between `ThreadSlider` and `RecordBubble`):

```python


class NavColumn(Gtk.Box):
    """Vertical nav-icon rail: Mini (collapse), Library, Discover.

    Not three independent toggle buttons -- clicking Library or Discover
    opens that section (auto-collapsing whichever was open), re-clicking
    the already-open one is a no-op, and only Mini collapses back down to
    nothing selected. Mini's icon is a hand-drawn spool (thread wound back
    up) rather than a stock symbolic icon, echoing the thread/button
    vocabulary already established by ThreadSlider and RecordBubble.
    """

    __gsignals__ = {
        'nav-selected': (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class("sidebar")
        self.set_valign(Gtk.Align.CENTER)

        self.active = "mini"
        self._buttons = {}

        self._spool = Gtk.DrawingArea()
        self._spool.set_content_width(18)
        self._spool.set_content_height(18)
        self._spool.set_draw_func(self._draw_spool)

        btn_mini = Gtk.Button()
        btn_mini.set_child(self._spool)
        btn_mini.add_css_class("nav-btn")
        btn_mini.set_tooltip_text("Mini")
        btn_mini.connect("clicked", lambda b: self._select("mini"))
        self.append(btn_mini)
        self._buttons["mini"] = btn_mini

        btn_library = Gtk.Button(icon_name="view-list-symbolic")
        btn_library.add_css_class("nav-btn")
        btn_library.set_tooltip_text("Station Library")
        btn_library.connect("clicked", lambda b: self._select("library"))
        self.append(btn_library)
        self._buttons["library"] = btn_library

        btn_discover = Gtk.Button(icon_name="folder-saved-search-symbolic")
        btn_discover.add_css_class("nav-btn")
        btn_discover.set_tooltip_text("Discover Stations")
        btn_discover.connect("clicked", lambda b: self._select("discover"))
        self.append(btn_discover)
        self._buttons["discover"] = btn_discover

        self._buttons["mini"].add_css_class("active")

    def _select(self, name: str):
        if name == self.active:
            return  # re-clicking the already-open one (or idle Mini) is a no-op
        self._buttons[self.active].remove_css_class("active")
        self.active = name
        self._buttons[name].add_css_class("active")
        self._spool.queue_draw()
        self.emit("nav-selected", name)

    def _draw_spool(self, area, cr, width, height, user_data=None):
        colors = palette.load()
        mini_active = self.active == "mini"
        # Matches .nav-btn.active's `color: {outline}` (palette SHADOW) when
        # Mini is selected, .nav-btn's plain `color: {REST}` otherwise --
        # Cairo draws don't pick up GTK CSS `color`, so it's read explicitly.
        rgb = _hex_to_rgb_floats(colors.get('SHADOW' if mini_active else 'REST', '#4e4e52'))

        cx, cy = width / 2.0, height / 2.0
        rx, ry = width * 0.42, height * 0.16
        top, bottom = cy - height * 0.32, cy + height * 0.32

        cr.set_source_rgba(*rgb, 1.0)
        cr.set_line_width(1.4)

        # Two dashed rims (the spool's end-caps) joined by two verticals
        # (the spindle) -- reads as thread wound back onto a spool.
        cr.set_dash([1.6, 1.4])
        for rim_y in (top, bottom):
            cr.save()
            cr.translate(cx, rim_y)
            cr.scale(rx, ry)
            cr.arc(0, 0, 1.0, 0, 2 * math.pi)
            cr.restore()
            cr.stroke()

        cr.set_dash([])
        cr.move_to(cx - rx, top)
        cr.line_to(cx - rx, bottom)
        cr.stroke()
        cr.move_to(cx + rx, top)
        cr.line_to(cx + rx, bottom)
        cr.stroke()
```

- [ ] **Step 3: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/controls.py').read())"
```

Expected: no output, exit code 0.

- [ ] **Step 4: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/controls.py
git commit -m "$(cat <<'EOF'
feat(sqlch-gui): add NavColumn nav rail with a hand-drawn spool glyph

Adds the Mini/Library/Discover nav rail as its own widget ahead of
wiring it into now_playing.py and window.py in a follow-up commit.
Mini's icon is drawn Cairo-side (two dashed rims joined by a spindle,
"thread wound back onto a spool") instead of using a stock symbolic
icon, matching the hand-drawn language ThreadSlider and RecordBubble
already established elsewhere in this file. Not yet referenced
anywhere, so this changes no runtime behavior on its own.
EOF
)"
```

---

## Task 2: Wire the flanked layout and collapsible nav model into `now_playing.py`, `common.py`, and `window.py`

**Files:**
- Modify: `sqlch_gui/ui/common.py:165-172` (`.cover-art` min size)
- Modify: `sqlch_gui/ui/common.py:522-542` (`.flip-tag-btn*` → `.corner-tag-flip*`)
- Modify: `sqlch_gui/ui/now_playing.py:1-246` (imports, `__gsignals__`, entire `__init__`)
- Modify: `sqlch_gui/ui/window.py:15-105` (`__init__`'s box/nav construction, `switch_panel` → `on_nav_selected`)

- [ ] **Step 1: Grow the album art in `common.py`**

In `sqlch_gui/ui/common.py`, replace lines 165-172:

```python
    .cover-art {{
        background-color: {colors.get('WING', '#e2dacf')};
        border-radius: 12px;
        min-width: 124px;
        min-height: 124px;
        border: 2px dashed {thread};
        box-shadow: 0 0 0 1px transparent, {slight}, {hem(5)};
    }}
```

with:

```python
    .cover-art {{
        background-color: {colors.get('WING', '#e2dacf')};
        border-radius: 12px;
        min-width: 150px;
        min-height: 150px;
        border: 2px dashed {thread};
        box-shadow: 0 0 0 1px transparent, {slight}, {hem(5)};
    }}
```

- [ ] **Step 2: Replace the flip-tab CSS with a corner-tag variant**

The flip button moves from a side-tab (flush against the art's right edge)
to a small overlay glyph tucked in the art's own bottom-right corner,
alongside the LIVE/format corner tags. Replace lines 522-542:

```python
    /* Flip Tab Button - Styled to look like a canvas tag sticking out of the seam */
    .flip-tag-btn {{
        background-color: {colors.get('ROOT', '#f4b84b')};
        color: {outline};
        border: 2px dashed {thread};
        border-left: none;
        border-radius: 0 8px 8px 0;
        margin-left: -2px; /* Pulls it flush right against the main art frame */
        padding: 0 4px;
        min-height: 48px;
        min-width: 24px;
        box-shadow: 2px 2px 0 0 {outline};
        transition: transform 120ms ease, background-color 120ms ease;
    }}
    .flip-tag-btn:hover {{
        background-color: {colors.get('WING', '#fff5dd')};
        transform: translateX(2px);
    }}
    .flip-tag-btn:active {{
        transform: translateX(0px);
    }}
```

with:

```python
    /* Flip corner glyph - a small clickable tag tucked into the art's own
       bottom-right corner, same rotation family as corner-tag-right
       (used by the top-right format tag) since both sit on the right. */
    .corner-tag-flip {{
        background-color: {colors.get('BAR', '#6a6a6a')};
        color: {score};
        border: none;
        border-radius: 8px;
        padding: 3px 5px;
        min-height: 0;
        min-width: 0;
        margin: 5px;
        box-shadow: 0 2px 0 rgba({staff}, 0.4);
        transform: rotate(4deg);
        transition: transform 120ms ease, background-color 120ms ease;
    }}
    .corner-tag-flip:hover {{
        background-color: {colors.get('WING', '#fff5dd')};
        transform: rotate(4deg) scale(1.1);
    }}
    .corner-tag-flip:active {{
        transform: rotate(4deg) scale(0.92);
    }}
```

- [ ] **Step 3: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/common.py').read())"
```

Expected: no output, exit code 0.

- [ ] **Step 4: Update `now_playing.py`'s imports and add the `nav-selected` signal**

Replace lines 1-16:

```python
"""Now Playing layout, stream management controls, and metadata rendering."""

import html
import threading
from pathlib import Path
from gi.repository import Gtk, GLib, GdkPixbuf

from .. import daemon, metadata
from .controls import ThreadSlider, RecordBubble
from .eq_strip import EqStrip

_REC_MODE_LABELS = {"full": "FULL", "track": "TRK"}

class NowPlayingPanel(Gtk.Box):
    def __init__(self, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
```

with:

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

class NowPlayingPanel(Gtk.Box):
    __gsignals__ = {
        'nav-selected': (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
```

- [ ] **Step 5: Replace the rest of `__init__`**

Replace from `self.set_margin_start(6)` (the original line 17) through the
blank line before `def clear_cover(self):` (the original line 247 was
`self.reset_ui()`, followed by a blank line at 247) — i.e. everything from
line 17 to line 247 inclusive — with:

```python
        self.set_margin_start(6)
        self.set_margin_end(6)
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_valign(Gtk.Align.CENTER)
        self.win = parent_window

        # Header card
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class("card")

        # --- Flanked album deck: nav column / art / transport column ---
        deck_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        deck_box.set_halign(Gtk.Align.CENTER)

        self.nav_column = NavColumn()
        self.nav_column.connect("nav-selected", lambda nav, name: self.emit("nav-selected", name))
        deck_box.append(self.nav_column)

        # Hero cover art elements (Front side)
        self.cover_img = Gtk.Image()
        self.cover_img.set_pixel_size(150)
        self.cover_placeholder = Gtk.Label(label="♪")
        self.cover_placeholder.add_css_class("cover-glyph")

        self.cover_stack = Gtk.Stack()
        self.cover_stack.add_css_class("cover-art")
        self.cover_stack.add_named(self.cover_placeholder, "placeholder")
        self.cover_stack.add_named(self.cover_img, "art")
        self.clear_cover()

        # Tracklist Matrix Sheet (Back side)
        track_scroll = Gtk.ScrolledWindow()
        track_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        track_scroll.set_size_request(150, 150)
        track_scroll.add_css_class("art-card-back")

        self.track_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.track_list_box.add_css_class("tracklist-container")
        track_scroll.set_child(self.track_list_box)

        # Core physical deck stack switcher
        self.deck_stack = Gtk.Stack()
        self.deck_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.deck_stack.set_transition_duration(250)
        self.deck_stack.add_named(self.cover_stack, "front")
        self.deck_stack.add_named(track_scroll, "back")

        # Main stitched wrap framework
        self.stack_wrapper = Gtk.Box()
        self.stack_wrapper.add_css_class("album-deck-wrapper")
        self.stack_wrapper.append(self.deck_stack)

        # Overlay carries the sewn-on corner tags without affecting deck sizing
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

        # Flip-to-tracklist control tucked into the art's own bottom-right
        # corner (third corner tag), freeing the transport column below to
        # hold only REC/Stop/Mute.
        self.flip_btn = Gtk.Button(icon_name="object-flip-horizontal-symbolic")
        self.flip_btn.add_css_class("corner-tag-flip")
        self.flip_btn.set_halign(Gtk.Align.END)
        self.flip_btn.set_valign(Gtk.Align.END)
        self.flip_btn.connect("clicked", self.on_flip_clicked)
        self.cover_overlay.add_overlay(self.flip_btn)

        deck_box.append(self.cover_overlay)

        # Transport column on the right: REC / Stop / Mute, stacked
        btn_stop = Gtk.Button(icon_name="media-playback-stop-symbolic")
        btn_stop.add_css_class("control-btn")
        btn_stop.connect("clicked", self.on_stop)
        btn_stop.set_valign(Gtk.Align.CENTER)

        self.btn_mute = Gtk.Button(icon_name="audio-volume-high-symbolic")
        self.btn_mute.add_css_class("control-btn")
        self.btn_mute.set_valign(Gtk.Align.CENTER)
        self.btn_mute.connect("clicked", self.on_toggle_mute)

        self.rec_knob = RecordBubble()
        self.rec_knob.connect("record-toggled", self.on_record_toggled)
        self.rec_knob.connect("mode-changed", self.on_rec_mode_changed)

        self.lbl_rec_mode = Gtk.Label(label=_REC_MODE_LABELS[self.rec_knob.mode])
        self.lbl_rec_mode.add_css_class("small-badge")
        self.lbl_rec_mode.set_halign(Gtk.Align.END)
        self.lbl_rec_mode.set_valign(Gtk.Align.END)
        self.lbl_rec_mode.set_can_target(False)

        rec_bubble_overlay = Gtk.Overlay()
        rec_bubble_overlay.set_child(self.rec_knob)
        rec_bubble_overlay.add_overlay(self.lbl_rec_mode)

        rec_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        rec_wrap.set_valign(Gtk.Align.CENTER)
        rec_wrap.set_halign(Gtk.Align.CENTER)
        rec_wrap.append(rec_bubble_overlay)
        lbl_rec_tag = Gtk.Label(label="REC")
        lbl_rec_tag.add_css_class("knob-tag")
        rec_wrap.append(lbl_rec_tag)

        right_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right_col.set_valign(Gtk.Align.CENTER)
        right_col.append(rec_wrap)
        right_col.append(btn_stop)
        right_col.append(self.btn_mute)
        deck_box.append(right_col)

        card.append(deck_box)

        self.eq_strip = EqStrip()
        self.eq_strip.set_halign(Gtk.Align.CENTER)
        card.append(self.eq_strip)

        # Meta details text stack, centered below the art
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        text_box.set_halign(Gtk.Align.CENTER)
        self.lbl_title = Gtk.Label(xalign=0.5, justify=Gtk.Justification.CENTER)
        self.lbl_title.add_css_class("meta-title")
        self.lbl_title.set_wrap(True)
        self.lbl_title.set_max_width_chars(36)

        self.lbl_artist = Gtk.Label(xalign=0.5, justify=Gtk.Justification.CENTER)
        self.lbl_artist.add_css_class("meta-artist")
        self.lbl_artist.set_wrap(True)
        self.lbl_artist.set_max_width_chars(36)

        self.lbl_genre = Gtk.Label(xalign=0.5, justify=Gtk.Justification.CENTER)
        self.lbl_genre.add_css_class("thread-label")

        text_box.append(self.lbl_title)
        text_box.append(self.lbl_artist)
        text_box.append(self.lbl_genre)
        card.append(text_box)

        # Volume + primary transport + tech readout live directly in this
        # same card now -- REC/Stop/Mute moved up into the flanking column
        # above, so there's no separate "control deck" card anymore.
        self.vol_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=1.0, step_increment=0.05)

        self.vol_slider = ThreadSlider(self.vol_adj)
        self._vol_handler = self.vol_slider.connect("value-changed", self.on_vol_changed)

        self._pre_boost_vol: float | None = None
        self.vol_slider.connect("boost-toggled", self.on_boost_toggled)

        vol_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vol_row.append(self.vol_slider)
        card.append(vol_row)

        lbl_vol_tag = Gtk.Label(label="VOL")
        lbl_vol_tag.add_css_class("knob-tag")
        lbl_vol_tag.set_halign(Gtk.Align.START)
        card.append(lbl_vol_tag)

        # Primary transport at 6 o'clock
        self.btn_toggle = Gtk.Button()
        self.btn_toggle.add_css_class("control-btn")
        self.btn_toggle.add_css_class("primary")
        self.btn_toggle.set_halign(Gtk.Align.CENTER)
        self.btn_toggle.connect("clicked", self.on_toggle_play)
        card.append(self.btn_toggle)

        # Readout strip
        self.tech_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.tech_box.set_halign(Gtk.Align.CENTER)

        self.lbl_vol_percent = Gtk.Label(label="0%")
        self.lbl_vol_percent.add_css_class("tech-badge")
        self.lbl_vol_percent.set_width_chars(5)

        self.lbl_rec = Gtk.Label()
        self.lbl_rec.add_css_class("tech-badge")
        self.lbl_rec.add_css_class("rec-badge")

        self.lbl_bitrate = Gtk.Label()
        self.lbl_bitrate.add_css_class("tech-badge")
        self.lbl_channels = Gtk.Label()
        self.lbl_channels.add_css_class("tech-badge")
        self.lbl_bt = Gtk.Label(label="BT")
        self.lbl_bt.add_css_class("tech-badge")

        self.lbl_device = Gtk.Label()
        self.lbl_device.add_css_class("tech-badge")
        self.lbl_device.set_ellipsize(3)
        self.lbl_device.set_max_width_chars(12)
        self.lbl_device.set_visible(False)

        self.tech_box.append(self.lbl_rec)
        self.tech_box.append(self.lbl_vol_percent)
        self.tech_box.append(self.lbl_bitrate)
        self.tech_box.append(self.lbl_channels)
        self.tech_box.append(self.lbl_bt)
        self.tech_box.append(self.lbl_device)
        card.append(self.tech_box)

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
        self.reset_ui()

```

(Keep the blank line right after `self.reset_ui()` — that's the same blank
line that already separates `__init__` from `def clear_cover(self):`, which
is untouched, along with every method below it.)

- [ ] **Step 6: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/now_playing.py').read())"
```

Expected: no output, exit code 0.

- [ ] **Step 7: Replace `window.py`'s box/nav construction**

In `sqlch_gui/ui/window.py`, replace from `self.set_title("sqlch-gui")`
(original line 18) through `self.switch_panel("now_playing")` (original
line 77), i.e. lines 18-77:

```python
        self.set_title("sqlch-gui")
        # Width sized so track/album lines usually fit un-ellipsized; the
        # sidebar is content-sized, so extra width all goes to the stack.
        self.set_default_size(450, 430)
        
        # Inject theme constants
        load_custom_css()

        # Initialize layer-shell layer
        Gtk4LayerShell.init_for_window(self)
        Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.TOP)
        Gtk4LayerShell.set_namespace(self, "sqlch-gui")
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.TOP, True)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.RIGHT, True)
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.TOP, 48)
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.RIGHT, 12)
        Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.ON_DEMAND)

        # Top surface: sidebar and stack are quilted side by side — patches
        # butt against each other at a seam, nothing overlaps or floats.
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        main_box.add_css_class("popup-window")
        self.set_child(main_box)

        # Navigation column sidebar patch
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        sidebar.add_css_class("sidebar")
        sidebar.set_valign(Gtk.Align.CENTER)
        main_box.append(sidebar)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(200)
        self.stack.set_hexpand(True)
        main_box.append(self.stack)

        # Instantiating presentation views
        self.now_playing = NowPlayingPanel(self)
        self.station_list = StationListPanel(self)
        self.discover = DiscoverPanel(self)

        self.stack.add_named(self.now_playing, "now_playing")
        self.stack.add_named(self.station_list, "station_list")
        self.stack.add_named(self.discover, "discover")

        # Sidebar control button array map
        self.nav_buttons = {}
        for name, icon, tooltip in [
            ("now_playing", "media-playlist-consecutive-symbolic", "Now Playing"),
            ("station_list", "view-list-symbolic", "Station Library"),
            ("discover", "folder-saved-search-symbolic", "Discover Stations")
        ]:
            btn = Gtk.Button(icon_name=icon)
            btn.add_css_class("nav-btn")
            btn.set_tooltip_text(tooltip)
            btn.connect("clicked", lambda b, n=name: self.switch_panel(n))
            sidebar.append(btn)
            self.nav_buttons[name] = btn

        self.switch_panel("now_playing")
```

with:

```python
        self.set_title("sqlch-gui")
        # Now Playing is permanently visible and taller (art grown to flank
        # height); Library/Discover render as a capped-height dropdown
        # below it rather than swapping the whole window.
        self.set_default_size(450, 700)

        # Inject theme constants
        load_custom_css()

        # Initialize layer-shell layer
        Gtk4LayerShell.init_for_window(self)
        Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.TOP)
        Gtk4LayerShell.set_namespace(self, "sqlch-gui")
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.TOP, True)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.RIGHT, True)
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.TOP, 48)
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.RIGHT, 12)
        Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.ON_DEMAND)

        # Top surface: Now Playing stays permanently visible; Library/
        # Discover render in a capped-height dropdown stacked below it.
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        main_box.add_css_class("popup-window")
        self.set_child(main_box)

        # Instantiating presentation views
        self.now_playing = NowPlayingPanel(self)
        self.station_list = StationListPanel(self)
        self.discover = DiscoverPanel(self)
        main_box.append(self.now_playing)

        # Dropdown region: always allocated at this fixed height, whether
        # or not it's showing anything -- that's what keeps the window
        # from resizing when a dropdown opens or closes.
        self.dropdown_stack = Gtk.Stack()
        self.dropdown_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.dropdown_stack.set_transition_duration(150)
        self.dropdown_stack.add_named(Gtk.Box(), "mini")
        self.dropdown_stack.add_named(self.station_list, "library")
        self.dropdown_stack.add_named(self.discover, "discover")
        self.dropdown_stack.set_visible_child_name("mini")

        self.dropdown_scroll = Gtk.ScrolledWindow()
        self.dropdown_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.dropdown_scroll.set_size_request(-1, 220)
        self.dropdown_scroll.set_child(self.dropdown_stack)
        main_box.append(self.dropdown_scroll)

        self.now_playing.connect("nav-selected", self.on_nav_selected)
```

- [ ] **Step 8: Replace `switch_panel` with `on_nav_selected`**

Replace lines 96-107 (`switch_panel` in full, plus the unchanged
`trigger_library_refresh` right after it, shown here only so the block is
unambiguous to locate):

```python
    def switch_panel(self, name: str):
        self.stack.set_visible_child_name(name)
        for k, btn in self.nav_buttons.items():
            if k == name:
                btn.add_css_class("active")
            else:
                btn.remove_css_class("active")
        if name == "station_list":
            self.station_list.on_shown()

    def trigger_library_refresh(self):
        self.station_list.refresh()
```

with:

```python
    def on_nav_selected(self, panel, name: str):
        self.dropdown_stack.set_visible_child_name(name)
        if name == "library":
            self.station_list.on_shown()

    def trigger_library_refresh(self):
        self.station_list.refresh()
```

- [ ] **Step 9: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/window.py').read())"
```

Expected: no output, exit code 0.

- [ ] **Step 10: Run the app and visually verify the full feature**

Launch per the `sqlch-gui-dev-launch` memory conventions (working tree,
wrapper env + `LD_PRELOAD`; kill any prior instance with a separate
`pkill -f "python3 -m sqlch_gui"` command first). Confirm:

1. On launch, only the Now Playing block is visible — nav column (Mini
   highlighted active) to the left of the album art, REC/Stop/Mute stacked
   to the right, no dropdown content beneath, window at its normal size
   with no jank on startup.
2. Album art now visibly fills roughly the same height as the REC/Stop/Mute
   stack, with no obvious dead gap on either side — if it looks off,
   adjust `cover_img.set_pixel_size`, `.cover-art`'s min-width/min-height,
   and `track_scroll.set_size_request` (keep all three in sync) and/or
   `right_col`'s spacing until they line up.
3. Click the Library icon — the station list appears below, internally
   scrollable, capped height; Mini is no longer shown active; window does
   not resize.
4. Click Library again — no visible change (already open, stays open).
5. Click Discover — Discover replaces the station list below (Library's
   content disappears, only one dropdown visible at a time); window still
   does not resize.
6. Click Mini — dropdown area goes back to blank; Now Playing is the only
   visible content again.
7. While a dropdown is open, confirm the Now Playing block above it keeps
   updating live (track/volume/REC state) — it's the same long-lived
   widget instance, not torn down by the nav change.
8. Click the flip glyph in the album art's bottom-right corner — it still
   flips to the tracklist back-plate and back, unaffected by its new
   position/style.
9. If the window looks too tall/short or the dropdown area's fixed height
   feels wrong, adjust `set_default_size`'s height and/or
   `dropdown_scroll`'s `set_size_request` height together.
10. No console errors/tracebacks on startup or through any of the above
    interactions.

Kill the dev instance by PID (separate command) once verified.

- [ ] **Step 11: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/common.py sqlch_gui/ui/now_playing.py sqlch_gui/ui/window.py
git commit -m "$(cat <<'EOF'
feat(sqlch-gui): flank album art with nav/transport, collapse Library+Discover

The album art used to sit alone next to a single flip button, with
REC/Stop/Mute in a separate control-deck card below, and a
window-global sidebar that was mostly empty space next to a small
popup. This collapses both gaps at once:

- NavColumn (Mini/Library/Discover) now sits directly left of the art,
  REC/Stop/Mute stack directly right of it, and the art itself grows
  to match that stack's height. The flip-to-tracklist button becomes a
  small corner glyph on the art itself, freeing the right column for
  just the three transport controls. The separate control-deck card is
  gone -- volume, play/pause, and the tech readout now live in the
  same card as the art.

- window.py drops the 3-page Gtk.Stack + global sidebar entirely. Now
  Playing is permanently visible; Station List and Discover render in
  a capped-height, always-allocated dropdown region underneath it
  instead, driven by NowPlayingPanel's new nav-selected signal. Only
  one dropdown is open at a time, re-clicking the open one is a no-op,
  and only Mini collapses back down -- see
  docs/superpowers/specs/2026-07-09-now-playing-nav-flank-design.md
  for the full behavioral spec.
EOF
)"
```

---

## Self-Review Notes

- **Spec coverage:** Nav column (Mini/Library/Discover, same order, spool
  glyph) → Task 1 + Task 2 Step 5. REC/Stop/Mute flanking the art on the
  right → Task 2 Step 5's `right_col`. Art grown to match the button-stack
  height → Task 2 Steps 1 and 5 (`.cover-art`, `cover_img.set_pixel_size`,
  `track_scroll.set_size_request`, all moved to 150 together). Flip button
  relocated to the art's own bottom-right corner → Task 2 Steps 2 and 5.
  Control-deck card removed, volume/play/readout folded into the one
  remaining card → Task 2 Step 5. Nav behavior (open/auto-collapse-other/
  no-op-on-reclick/only-Mini-collapses) → Task 1 Step 2's `NavColumn._select`.
  Fixed-height, always-scrollable, never-resizing dropdown region → Task 2
  Steps 7-8's `dropdown_scroll`/`dropdown_stack`. `station_list.on_shown()`
  still firing on Library open → Task 2 Step 8. `trigger_library_refresh`
  and `_reload_palette` continuing to work unchanged → left alone
  deliberately (both only reference `self.station_list`/`self.now_playing`,
  which still exist under the same names). All spec sections have a
  corresponding step.
- **Placeholder scan:** No TBD/TODO; every step shows complete code. Sizing
  constants (150px art/right-col match, 220px dropdown height, 700px window
  height) are concrete decisions, not placeholders — Step 10 explicitly
  calls out visually checking and adjusting them together if they're off,
  which is expected first-pass UI tuning, not missing design work.
- **Type/name consistency:** `NavColumn.emit("nav-selected", name)` in Task
  1 matches `NowPlayingPanel`'s `__gsignals__` re-declaration and its
  `self.nav_column.connect("nav-selected", ...)` forwarding lambda in Task
  2 Step 5, which in turn matches `window.py`'s
  `self.now_playing.connect("nav-selected", self.on_nav_selected)` in Step
  7 and `on_nav_selected(self, panel, name)`'s signature in Step 8. The
  three name strings ("mini", "library", "discover") are identical across
  `NavColumn._buttons`/`_select`, `window.py`'s `dropdown_stack.add_named`
  page names, and `on_nav_selected`'s `if name == "library"` check — no
  translation layer needed between them. `self.station_list`/`self.discover`
  attribute names on `SqlchPopupWindow` are unchanged from today, so
  `discover.py`'s existing `self.win.trigger_library_refresh()` call
  keeps working without modification.
