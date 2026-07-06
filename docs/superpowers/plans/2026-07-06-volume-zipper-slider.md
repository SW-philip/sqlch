# Volume Control: Rotary Knob → Zipper Slider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the volume `RotaryKnob` with a full-width "zipper" slider (`ZipperSlider`) that visually unzips as volume drops, plus a hot-pepper sticker (`PepperToggle`) that toggles a hard-coded 120% volume boost.

**Architecture:** Two tasks, ordered so the app is fully working after each commit. Task 1 renames `knob.py` → `controls.py`, deletes `RotaryKnob`, adds `ZipperSlider`, and wires it into `now_playing.py` as a complete (if boost-less) replacement for the old knob — volume range drops from 0.0–1.3 to 0.0–1.0. Task 2 adds `PepperToggle` to `controls.py` and wires the 120%-boost toggle into `now_playing.py`, building on Task 1's already-working slider. This split avoids an intermediate broken-import state (which the prior `RecordKnob`→`RecordBubble` plan's two-commit split risked, since `now_playing.py` still imported the old name between those two commits).

**Tech Stack:** Python 3.12, GTK4 (PyGObject), Cairo (pycairo — already imported in this file for `RecordBubble`). No test framework in this repo; pure-syntax changes are checked with `python3 -c "import ast; ast.parse(...)"` and GTK/visual changes are verified by running the app (matches `docs/plans/2026-07-04-sqlch-gui-now-playing-lbp-plan.md` and `docs/superpowers/plans/2026-07-05-rec-bubble.md` conventions).

**Spec:** `docs/superpowers/specs/2026-07-06-volume-zipper-slider-design.md`

---

## Task 1: Rename `knob.py` → `controls.py`, replace `RotaryKnob` with `ZipperSlider`

**Files:**
- Rename: `sqlch_gui/ui/knob.py` → `sqlch_gui/ui/controls.py`
- Modify: `sqlch_gui/ui/controls.py:1` (docstring), `:9-118` (the entire `RotaryKnob` class → `ZipperSlider`)
- Modify: `sqlch_gui/ui/now_playing.py:9` (import)
- Modify: `sqlch_gui/ui/now_playing.py:136-148` (vol adjustment/widget construction)
- Modify: `sqlch_gui/ui/now_playing.py:176-180` (hub_row wiring + new full-width volume row)
- Modify: `sqlch_gui/ui/now_playing.py:412-415` (`update_indicators` signal-block dance)
- Modify: `sqlch_gui/ui/now_playing.py:484` (`on_vol_changed` param name)

- [ ] **Step 1: Rename the file with git**

```bash
cd /home/prepko/sqlch
git mv sqlch_gui/ui/knob.py sqlch_gui/ui/controls.py
```

- [ ] **Step 2: Replace the docstring and `RotaryKnob` class with `ZipperSlider`**

In `sqlch_gui/ui/controls.py`, replace lines 1-118 (from the module docstring through the end of the `RotaryKnob` class, i.e. everything before the two blank lines that precede `class RecordBubble`) with:

```python
"""Custom GTK 4 tactile controls: pop-it bubble and zipper slider."""

import math
import cairo
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GObject

class ZipperSlider(Gtk.DrawingArea):
    """Full-width volume fader drawn as a zipper: mesh-shut tape behind
    the pull, teeth splayed open ahead of it. Backs onto a Gtk.Adjustment,
    same as the rotary knob it replaces, but reads position along x
    instead of angle. Click anywhere on the track to jump there; drag the
    pull; scroll to nudge.
    """

    __gsignals__ = {
        'value-changed': (GObject.SignalFlags.RUN_LAST, None, (float,)),
    }

    def __init__(self, adjustment: Gtk.Adjustment):
        super().__init__()
        self.adj = adjustment
        self.set_focusable(True)
        self.set_hexpand(True)
        self.set_size_request(-1, 34)

        self.adj.connect("value-changed", lambda _: self.queue_draw())
        self.set_draw_func(self._on_draw)

        self.drag_start_val = 0.0

        click_gest = Gtk.GestureClick.new()
        click_gest.set_button(1)
        click_gest.connect("released", self._on_click)
        self.add_controller(click_gest)

        drag_gest = Gtk.GestureDrag.new()
        drag_gest.connect("drag-begin", self._on_drag_begin)
        drag_gest.connect("drag-update", self._on_drag_update)
        self.add_controller(drag_gest)

        scroll_gest = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll_gest.connect("scroll", self._on_scroll)
        self.add_controller(scroll_gest)

    def _norm(self) -> float:
        return (self.adj.get_value() - self.adj.get_lower()) / (self.adj.get_upper() - self.adj.get_lower())

    def _set_from_norm(self, norm: float):
        norm = max(0.0, min(1.0, norm))
        new_val = self.adj.get_lower() + norm * (self.adj.get_upper() - self.adj.get_lower())
        self.adj.set_value(new_val)
        self.emit('value-changed', new_val)

    def _on_draw(self, area, cr, width, height, user_data=None):
        pull_x = 10.0 + self._norm() * (width - 20.0)

        # Closed (zipped) tape from the left edge to the pull
        cr.set_source_rgba(0.42, 0.48, 0.36, 1.0)
        cr.rectangle(4.0, height * 0.28, max(0.0, pull_x - 4.0), height * 0.44)
        cr.fill()

        # Mesh teeth on the closed side: alternating light/dark ticks
        tooth_w = 5.0
        x = 6.0
        toggle = False
        while x < pull_x - tooth_w:
            if toggle:
                cr.set_source_rgba(0.79, 0.76, 0.66, 1.0)
            else:
                cr.set_source_rgba(0.66, 0.62, 0.50, 1.0)
            cr.rectangle(x, height / 2.0 - 3.0, tooth_w, 6.0)
            cr.fill()
            x += tooth_w
            toggle = not toggle

        # Open (unzipped) side past the pull: teeth splayed apart as short
        # dashed strokes angling away from the centerline
        cr.save()
        cr.set_dash([3.0, 3.0])
        cr.set_line_width(1.5)
        cr.set_source_rgba(0.66, 0.62, 0.50, 0.8)
        gap_x = pull_x + 14.0
        while gap_x < width - 6.0:
            cr.move_to(gap_x, height / 2.0 - 6.0)
            cr.line_to(gap_x + 4.0, height / 2.0)
            cr.move_to(gap_x, height / 2.0 + 6.0)
            cr.line_to(gap_x + 4.0, height / 2.0)
            gap_x += 9.0
        cr.stroke()
        cr.restore()

        # Zipper pull: rounded body + angled tab, tilted like a real pull
        cr.save()
        cr.translate(pull_x, height / 2.0)
        cr.rotate(-0.12)
        cr.set_source_rgba(0.85, 0.70, 0.35, 1.0)
        cr.rectangle(-9.0, -9.0, 14.0, 12.0)
        cr.fill()
        cr.rectangle(-2.0, -2.0, 11.0, 5.0)
        cr.fill()
        cr.set_source_rgba(0.35, 0.25, 0.08, 0.6)
        cr.set_line_width(1.2)
        cr.rectangle(-9.0, -9.0, 14.0, 12.0)
        cr.stroke()
        cr.restore()

    def _on_click(self, gesture, n_press, x, y):
        width = self.get_width()
        if width <= 20:
            return
        self._set_from_norm((x - 10.0) / (width - 20.0))

    def _on_drag_begin(self, gesture, start_x, start_y):
        self.drag_start_val = self.adj.get_value()
        self.grab_focus()

    def _on_drag_update(self, gesture, offset_x, offset_y):
        width = self.get_width()
        if width <= 20:
            return
        total_range = self.adj.get_upper() - self.adj.get_lower()
        delta_norm = offset_x / (width - 20.0)
        new_val = self.drag_start_val + delta_norm * total_range
        new_val = max(self.adj.get_lower(), min(self.adj.get_upper(), new_val))
        self.adj.set_value(new_val)
        self.emit('value-changed', new_val)

    def _on_scroll(self, controller, dx, dy):
        total_range = self.adj.get_upper() - self.adj.get_lower()
        step = (total_range * 0.05) if dy > 0 else -(total_range * 0.05)
        new_val = self.adj.get_value() - step
        new_val = max(self.adj.get_lower(), min(self.adj.get_upper(), new_val))
        self.adj.set_value(new_val)
        self.emit('value-changed', new_val)

```

(This preserves the trailing two blank lines that already separate the file's classes — do not add or remove blank lines around `class RecordBubble` below.)

- [ ] **Step 3: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/controls.py').read())"
```

Expected: no output, exit code 0.

- [ ] **Step 4: Update the import in `now_playing.py`**

Replace:

```python
from .knob import RotaryKnob, RecordBubble
```

with:

```python
from .controls import ZipperSlider, RecordBubble
```

- [ ] **Step 5: Replace the volume adjustment/widget construction**

Replace:

```python
        self.vol_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=1.3, step_increment=0.05)

        self.vol_knob = RotaryKnob(self.vol_adj)
        self._vol_handler = self.vol_knob.connect("value-changed", self.on_vol_changed)

        vol_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vol_wrap.set_valign(Gtk.Align.CENTER)
        vol_wrap.set_halign(Gtk.Align.CENTER)
        vol_wrap.append(self.vol_knob)
        lbl_vol_tag = Gtk.Label(label="VOL")
        lbl_vol_tag.add_css_class("knob-tag")
        vol_wrap.append(lbl_vol_tag)
```

with:

```python
        self.vol_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=1.0, step_increment=0.05)

        self.vol_slider = ZipperSlider(self.vol_adj)
        self._vol_handler = self.vol_slider.connect("value-changed", self.on_vol_changed)
```

- [ ] **Step 6: Move volume out of `hub_row` into its own full-width row**

Replace:

```python
        hub_row.append(rec_wrap)
        hub_row.append(btn_stop)
        hub_row.append(vol_wrap)
        hub_row.append(self.btn_mute)
        deck.append(hub_row)
```

with:

```python
        hub_row.append(rec_wrap)
        hub_row.append(btn_stop)
        hub_row.append(self.btn_mute)
        deck.append(hub_row)

        # Full-width zipper volume row, sewn in below the hub
        vol_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vol_row.append(self.vol_slider)
        deck.append(vol_row)

        lbl_vol_tag = Gtk.Label(label="VOL")
        lbl_vol_tag.add_css_class("knob-tag")
        lbl_vol_tag.set_halign(Gtk.Align.START)
        deck.append(lbl_vol_tag)
```

- [ ] **Step 7: Rename `vol_knob` references in `update_indicators`**

Replace:

```python
        # Block signals temporarily to prevent loopback configuration cascades
        self.vol_knob.handler_block(self._vol_handler)
        self.vol_adj.set_value(vol)
        self.vol_knob.handler_unblock(self._vol_handler)
```

with:

```python
        # Block signals temporarily to prevent loopback configuration cascades
        self.vol_slider.handler_block(self._vol_handler)
        self.vol_adj.set_value(vol)
        self.vol_slider.handler_unblock(self._vol_handler)
```

- [ ] **Step 8: Rename the `on_vol_changed` parameter**

Replace:

```python
    def on_vol_changed(self, knob, val):
```

with:

```python
    def on_vol_changed(self, slider, val):
```

- [ ] **Step 9: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/now_playing.py').read())"
```

Expected: no output, exit code 0.

- [ ] **Step 10: Run the app and visually verify the slider**

Launch per the `sqlch-gui-dev-launch` memory conventions (working tree, wrapper env + LD_PRELOAD). Confirm:
- A full-width zipper track sits below the REC/Stop/Mute row, with a "VOL" tag beneath it.
- The track shows closed/meshed tape from the left edge up to the pull, and an open/splayed gap from the pull to the right edge.
- Dragging the pull, clicking anywhere else on the track, and scrolling over the track all change volume, and the existing percent readout in the tech-badge strip updates accordingly.
- REC bubble, Stop, and Mute are visually/behaviorally unaffected.
- No console errors/tracebacks on startup or interaction.

- [ ] **Step 11: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/controls.py sqlch_gui/ui/now_playing.py
git rm sqlch_gui/ui/knob.py 2>/dev/null || true
git commit -m "feat(sqlch-gui): replace volume knob with a zipper slider

RotaryKnob only ever backed the volume control, so the rotary metaphor
went away entirely: ZipperSlider draws a full-width track that unzips
as volume drops and zips shut as it rises, with click-anywhere-to-jump
added on top of the existing drag/scroll interactions. knob.py is
renamed to controls.py since nothing in it is a knob anymore. Volume
range narrows from 0.0-1.3 to 0.0-1.0 continuous; the old >100% boost
lives in a separate fixed step next (see follow-up commit)."
```

(The `git rm` is a no-op safety net — `git mv` in Step 1 already staged the rename; this just guards against the file having been re-created by an editor/tooling in between.)

---

## Task 2: Add `PepperToggle` and wire the 120% LOUD boost

**Files:**
- Modify: `sqlch_gui/ui/controls.py:1` (docstring), append `PepperToggle` class at end of file
- Modify: `sqlch_gui/ui/now_playing.py:9` (import)
- Modify: `sqlch_gui/ui/now_playing.py` (`self.vol_slider`/`self._vol_handler` block — add pepper + pre-boost state)
- Modify: `sqlch_gui/ui/now_playing.py` (`vol_row` — append pepper)
- Modify: `sqlch_gui/ui/now_playing.py` (`on_vol_changed` — cancel boost on manual interaction)
- Modify: `sqlch_gui/ui/now_playing.py` (add `on_boost_toggled` handler)

- [ ] **Step 1: Update the module docstring**

In `sqlch_gui/ui/controls.py`, replace:

```python
"""Custom GTK 4 tactile controls: pop-it bubble and zipper slider."""
```

with:

```python
"""Custom GTK 4 tactile controls: pop-it bubble, zipper slider, boost toggle."""
```

- [ ] **Step 2: Append the `PepperToggle` class**

At the end of `sqlch_gui/ui/controls.py` (after the end of the `RecordBubble` class), add:

```python

class PepperToggle(Gtk.DrawingArea):
    """Hot-pepper sticker glued past the zipper's end. Toggles a hard
    120% volume boost — NowPlayingPanel owns what "boosted" actually
    does to system volume; this widget only tracks its own on/off look
    and is a plain optimistic toggle (no daemon-truth reflection, unlike
    RecordBubble): press again to flip back.
    """

    __gsignals__ = {
        'boost-toggled': (GObject.SignalFlags.RUN_LAST, None, (bool,)),
    }

    def __init__(self):
        super().__init__()
        self.active = False
        self.set_size_request(34, 34)
        self.set_focusable(True)
        self.set_draw_func(self._on_draw)
        self._update_tooltip()

        click = Gtk.GestureClick.new()
        click.set_button(1)
        click.connect("released", self._on_click)
        self.add_controller(click)

    def set_active(self, active: bool):
        """External, signal-free push (mirrors RecordBubble.set_state())."""
        if active == self.active:
            return
        self.active = active
        self._update_tooltip()
        self.queue_draw()

    def _update_tooltip(self):
        self.set_tooltip_text("Tap to restore volume" if self.active else "Tap for 120% boost")

    def _on_click(self, gesture, n_press, x, y):
        self.active = not self.active
        self._update_tooltip()
        self.queue_draw()
        self.emit('boost-toggled', self.active)

    def _on_draw(self, area, cr, width, height, user_data=None):
        cx = width / 2.0
        cy = height / 2.0
        radius = min(width, height) / 2.0 - 3.0

        cr.save()
        cr.translate(cx, cy)
        cr.rotate(0.14 if self.active else -0.14)

        if self.active:
            gradient = cairo.RadialGradient(-radius * 0.15, -radius * 0.1, radius * 0.05, 0, 0, radius)
            gradient.add_color_stop_rgba(0.0, 0.55, 0.10, 0.08, 1.0)
            gradient.add_color_stop_rgba(0.55, 0.82, 0.22, 0.14, 1.0)
            gradient.add_color_stop_rgba(1.0, 0.60, 0.18, 0.12, 1.0)
        else:
            gradient = cairo.RadialGradient(-radius * 0.35, -radius * 0.35, radius * 0.1, 0, 0, radius)
            gradient.add_color_stop_rgba(0.0, 0.55, 0.68, 0.32, 1.0)
            gradient.add_color_stop_rgba(0.55, 0.36, 0.50, 0.22, 1.0)
            gradient.add_color_stop_rgba(1.0, 0.24, 0.36, 0.14, 1.0)

        # Pepper body: teardrop via two mirrored bezier curves
        cr.set_source(gradient)
        cr.move_to(0, radius * 0.75)
        cr.curve_to(radius * 0.9, radius * 0.6, radius * 0.7, -radius * 0.5, 0, -radius * 0.55)
        cr.curve_to(-radius * 0.7, -radius * 0.5, -radius * 0.9, radius * 0.6, 0, radius * 0.75)
        cr.fill()

        # Stem
        cr.set_source_rgba(0.30, 0.42, 0.16, 1.0)
        cr.move_to(-radius * 0.12, -radius * 0.5)
        cr.line_to(radius * 0.12, -radius * 0.5)
        cr.line_to(radius * 0.05, -radius * 0.85)
        cr.line_to(-radius * 0.05, -radius * 0.85)
        cr.close_path()
        cr.fill()

        cr.restore()
```

- [ ] **Step 3: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/controls.py').read())"
```

Expected: no output, exit code 0.

- [ ] **Step 4: Update the import in `now_playing.py`**

Replace:

```python
from .controls import ZipperSlider, RecordBubble
```

with:

```python
from .controls import ZipperSlider, RecordBubble, PepperToggle
```

- [ ] **Step 5: Add the pepper toggle and pre-boost state**

Replace:

```python
        self.vol_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=1.0, step_increment=0.05)

        self.vol_slider = ZipperSlider(self.vol_adj)
        self._vol_handler = self.vol_slider.connect("value-changed", self.on_vol_changed)
```

with:

```python
        self.vol_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=1.0, step_increment=0.05)

        self.vol_slider = ZipperSlider(self.vol_adj)
        self._vol_handler = self.vol_slider.connect("value-changed", self.on_vol_changed)

        self._pre_boost_vol: float | None = None
        self.pepper = PepperToggle()
        self.pepper.connect("boost-toggled", self.on_boost_toggled)
```

- [ ] **Step 6: Append the pepper next to the slider in `vol_row`**

Replace:

```python
        # Full-width zipper volume row, sewn in below the hub
        vol_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vol_row.append(self.vol_slider)
        deck.append(vol_row)
```

with:

```python
        # Full-width zipper volume row, sewn in below the hub
        vol_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vol_row.append(self.vol_slider)
        vol_row.append(self.pepper)
        deck.append(vol_row)
```

- [ ] **Step 7: Cancel boost on manual slider interaction**

Replace:

```python
    def on_vol_changed(self, slider, val):
        # Dynamically push numeric modifications into stdout subsystem
        self.lbl_vol_percent.set_text(f"{int(val * 100)}%")
        import subprocess
        subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{val:.2f}"], stdout=subprocess.DEVNULL)
```

with:

```python
    def on_vol_changed(self, slider, val):
        if self.pepper.active:
            # Touching the fader always means manual control wins.
            self.pepper.set_active(False)
            self._pre_boost_vol = None

        # Dynamically push numeric modifications into stdout subsystem
        self.lbl_vol_percent.set_text(f"{int(val * 100)}%")
        import subprocess
        subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{val:.2f}"], stdout=subprocess.DEVNULL)
```

- [ ] **Step 8: Add the boost-toggle handler**

Directly below the `on_vol_changed` method, add:

```python

    def on_boost_toggled(self, pepper, active):
        import subprocess
        if active:
            self._pre_boost_vol = self.vol_adj.get_value()
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "1.20"], stdout=subprocess.DEVNULL)
        else:
            restore = self._pre_boost_vol if self._pre_boost_vol is not None else 0.0
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{restore:.2f}"], stdout=subprocess.DEVNULL)
            self._pre_boost_vol = None
```

- [ ] **Step 9: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/now_playing.py').read())"
```

Expected: no output, exit code 0.

- [ ] **Step 10: Run the app and visually verify the boost**

Launch per the `sqlch-gui-dev-launch` memory conventions. Confirm:
- A hot-pepper sticker sits just right of the zipper track, green/idle at rest.
- Tapping it: volume jumps to 120% (check via `wpctl get-volume @DEFAULT_AUDIO_SINK@` in another terminal, or the system volume actually gets louder), and the pepper visually flips to its "hot" look (redder gradient, opposite tilt).
- Tapping it again: volume restores to whatever it was before boosting, pepper flips back to idle.
- While boosted, drag/click/scroll the zipper track: confirm the pepper immediately un-toggles back to idle and the manually-chosen volume takes effect (no fight between the two).
- REC bubble, Stop, and Mute remain visually/behaviorally unaffected.
- No console errors/tracebacks on startup or interaction.

- [ ] **Step 11: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/controls.py sqlch_gui/ui/now_playing.py
git commit -m "feat(sqlch-gui): add pepper-toggle 120% LOUD boost

PepperToggle sits past the zipper track's end and hard-sets volume to
120% when tapped, restoring the pre-boost volume when tapped again.
It's a plain local optimistic toggle rather than daemon-truth-reflecting
like RecordBubble, since boost has no server-side state to reconcile
with. Manually touching the zipper slider while boosted cancels the
boost first, so dragging/clicking/scrolling always wins over the
pepper's state."
```

---

## Self-Review Notes

- **Spec coverage:** File organization (rename) → Task 1 Step 1. `ZipperSlider` rendering/interaction → Task 1 Step 2. `PepperToggle` rendering/interaction → Task 2 Step 2. Boost semantics (store/restore, cancel-on-manual-interaction) → Task 2 Steps 5, 7, 8. Layout (`hub_row` drop, new `vol_row`, single "VOL" caption, no duplicate percent) → Task 1 Steps 5-6, Task 2 Step 6. Range change (1.3 → 1.0) → Task 1 Step 5. All spec sections have a corresponding step.
- **Placeholder scan:** No TBD/TODO; every step shows complete code, not descriptions of code.
- **Type/name consistency:** `self.vol_slider` (not `vol_knob`) used consistently from Task 1 Step 5 onward, including in `update_indicators` (Step 7) and `on_vol_changed`'s parameter rename (Step 8). `self.pepper` and `PepperToggle`/`on_boost_toggled`/`_pre_boost_vol` names introduced in Task 2 are used consistently across its own steps. `ZipperSlider`'s `value-changed(float)` signal shape matches what `on_vol_changed(self, slider, val)` expects everywhere it's referenced.
