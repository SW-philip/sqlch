# REC Control: Dial → Pop-it Bubble Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the REC control's rotary-dial visuals (`RecordKnob`) with a silicone "pop-it" bubble (`RecordBubble`) sewn into the fabric deck, since the dial metaphor promised a rotation the widget never supported. Mode (FULL/TRACK) moves from an angle-pointer to a small corner badge.

**Architecture:** Two tasks. Task 1 rewrites the widget itself in `knob.py` (rename, redraw, new `mode-changed` signal) in isolation — it has no GTK-layout dependents yet, so it's verifiable by syntax check plus visual inspection of the bubble alone. Task 2 wires the corner badge into `now_playing.py`, which depends on Task 1's rename and new signal existing first.

**Tech Stack:** Python 3.12, GTK4 (PyGObject), Cairo (pycairo, `import cairo` for `RadialGradient` — new to this file, not used elsewhere in the repo yet, confirmed available: `python3 -c "import cairo"` succeeds). No test framework in this repo; pure-syntax changes are checked with `python3 -c "import ast; ast.parse(...)"` and GTK/visual changes are verified by running the app (matches `docs/plans/2026-07-04-sqlch-gui-now-playing-lbp-plan.md` conventions).

**Spec:** `docs/superpowers/specs/2026-07-05-rec-bubble-design.md`

---

## Task 1: Rewrite `RecordKnob` → `RecordBubble`

**Files:**
- Modify: `sqlch_gui/ui/knob.py:1-6` (add `import cairo`)
- Modify: `sqlch_gui/ui/knob.py:120-242` (the entire `RecordKnob` class)

- [ ] **Step 1: Add the `cairo` import**

In `sqlch_gui/ui/knob.py`, replace:

```python
"""Custom GTK 4 Rotary Knob Component."""

import math
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GObject
```

with:

```python
"""Custom GTK 4 Rotary Knob Component."""

import math
import cairo
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GObject
```

- [ ] **Step 2: Replace the `RecordKnob` class with `RecordBubble`**

Replace the entire class (currently lines 120-242, from `class RecordKnob(Gtk.DrawingArea):` through the end of the file) with:

```python
class RecordBubble(Gtk.DrawingArea):
    """Two-mode record button drawn as a pop-it silicone bubble.

    Right-click cycles the FULL/TRACK mode (emits 'mode-changed' so the
    mode can be displayed outside this widget, e.g. a corner badge);
    left-click emits 'record-toggled' with the selected mode. Recording
    state is pushed in from the daemon poll via set_state() — the widget
    never assumes its click succeeded. There is no drag gesture: this
    control is pressed, never turned.
    """

    __gsignals__ = {
        'record-toggled': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'mode-changed': (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    MODES = ("full", "track")

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
        self.emit('mode-changed', self.mode)

    def _on_draw(self, area, cr, width, height, user_data=None):
        cx = width / 2.0
        cy = height / 2.0
        radius = min(width, height) / 2.0 - 5.0

        if self.recording:
            # Soft glow behind the pressed bubble
            cr.set_source_rgba(0.86, 0.20, 0.18, 0.25)
            cr.arc(cx, cy, radius + 5.0, 0, 2 * math.pi)
            cr.fill()

        # Dashed stitch ring, matches RotaryKnob; turns red while recording
        cr.save()
        cr.set_dash([2.0, 3.0])
        cr.set_line_width(1.5)
        if self.recording:
            cr.set_source_rgba(0.86, 0.20, 0.18, 0.6)
        else:
            cr.set_source_rgba(0.9, 0.9, 0.9, 0.35)
        cr.arc(cx, cy, radius + 4.0, 0, 2 * math.pi)
        cr.stroke()
        cr.restore()

        # Silicone bubble face: convex bump when idle, pressed-in dimple
        # when recording. Same gradient trick fakes both: a highlight near
        # the upper-left reads as "light hitting a bump sticking up"; a
        # highlight shifted toward the center/lower-right of a darker,
        # more saturated fill reads as "light entering a pressed dimple."
        if self.recording:
            gradient = cairo.RadialGradient(
                cx - radius * 0.15, cy - radius * 0.1, radius * 0.05,
                cx, cy, radius,
            )
            gradient.add_color_stop_rgba(0.0, 0.53, 0.14, 0.13, 1.0)
            gradient.add_color_stop_rgba(0.55, 0.86, 0.20, 0.18, 1.0)
            gradient.add_color_stop_rgba(1.0, 0.66, 0.27, 0.24, 1.0)
        else:
            gradient = cairo.RadialGradient(
                cx - radius * 0.35, cy - radius * 0.35, radius * 0.1,
                cx, cy, radius,
            )
            gradient.add_color_stop_rgba(0.0, 0.23, 0.23, 0.24, 1.0)
            gradient.add_color_stop_rgba(0.55, 0.16, 0.16, 0.18, 1.0)
            gradient.add_color_stop_rgba(1.0, 0.12, 0.12, 0.13, 1.0)
        cr.set_source(gradient)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.fill()

        # Drop shadow under the bump (idle only — a pressed dimple casts
        # no shadow of its own).
        if not self.recording:
            cr.set_source_rgba(0.0, 0.0, 0.0, 0.25)
            cr.arc(cx, cy + 1.5, radius, 0, 2 * math.pi)
            cr.set_line_width(1.0)
            cr.stroke_preserve()
```

- [ ] **Step 3: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('sqlch_gui/ui/knob.py').read())"`
Expected: no output, exit code 0.

- [ ] **Step 4: Run the app and visually verify the bubble in isolation**

Follow the `sqlch-gui-dev-launch` memory conventions (working tree, wrapper env + LD_PRELOAD) to launch the app. Confirm:
- The REC control renders as a dark convex bubble at rest (not a dial — no pointer line, no detent dots).
- Left-click toggles recording; the bubble turns into a red, visually "pressed" dimple with a soft red glow and the dashed ring turns red.
- Right-click while idle still changes mode (no visible mode indicator yet — that's Task 2); right-click while recording is still a no-op.
- Tooltip text is unchanged (`REC FULL · left-click to record · right-click: mode`, etc).

- [ ] **Step 5: Commit**

```bash
git add sqlch_gui/ui/knob.py
git commit -m "feat(sqlch-gui): redraw REC control as a pop-it bubble, not a dial

RecordKnob copied RotaryKnob's rotary bezel/pointer but had no drag
gesture — it never turned, only clicked. Renamed to RecordBubble and
redrawn as a press-able silicone bubble (convex idle, pressed-in red
dimple while recording) so the shape stops promising a rotation that
was never there. Mode is no longer shown by pointer angle; adds a
mode-changed signal so an external corner badge (Task 2) can display
it instead."
```

---

## Task 2: Corner mode badge in `NowPlayingPanel`

**Files:**
- Modify: `sqlch_gui/ui/now_playing.py:9` (import)
- Modify: `sqlch_gui/ui/now_playing.py:152-165` (rec_wrap construction)
- Modify: `sqlch_gui/ui/now_playing.py:254` (reset_ui)
- Modify: `sqlch_gui/ui/now_playing.py:443` (update)
- Modify: `sqlch_gui/ui/now_playing.py:449-450` (on_record_toggled — unchanged code, included for context only)

- [ ] **Step 1: Update the import**

In `sqlch_gui/ui/now_playing.py`, replace:

```python
from .knob import RotaryKnob, RecordKnob
```

with:

```python
from .knob import RotaryKnob, RecordBubble
```

- [ ] **Step 2: Add a module-level mode label map**

Directly below the import block at the top of `sqlch_gui/ui/now_playing.py` (after the existing imports, before the first class definition), add:

```python
_REC_MODE_LABELS = {"full": "FULL", "track": "TRK"}
```

- [ ] **Step 3: Replace the `rec_knob` construction with a bubble + overlay badge**

Replace:

```python
        self.rec_knob = RecordKnob()
        self.rec_knob.connect("record-toggled", self.on_record_toggled)

        rec_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        rec_wrap.set_valign(Gtk.Align.CENTER)
        rec_wrap.set_halign(Gtk.Align.CENTER)
        rec_wrap.append(self.rec_knob)
        lbl_rec_tag = Gtk.Label(label="REC")
        lbl_rec_tag.add_css_class("knob-tag")
        rec_wrap.append(lbl_rec_tag)
```

with:

```python
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
```

(The instance attribute stays named `self.rec_knob` — it's referenced elsewhere in this file and in `window.py`; only its class changed. `rec_bubble_overlay` is a local since nothing outside this method needs it.)

- [ ] **Step 4: Update the badge on daemon-poll state changes (`reset_ui`)**

Replace:

```python
        self.rec_knob.set_state(False, None)
```

with:

```python
        self.rec_knob.set_state(False, None)
        self.lbl_rec_mode.set_text(_REC_MODE_LABELS[self.rec_knob.mode])
```

- [ ] **Step 5: Update the badge on daemon-poll state changes (`update`)**

Replace:

```python
        self.rec_knob.set_state(active, rec.get("mode"))
```

with:

```python
        self.rec_knob.set_state(active, rec.get("mode"))
        self.lbl_rec_mode.set_text(_REC_MODE_LABELS[self.rec_knob.mode])
```

- [ ] **Step 6: Add the `mode-changed` handler for instant right-click feedback**

Directly below the existing `on_record_toggled` method:

```python
    def on_record_toggled(self, knob, mode):
        daemon.send({"cmd": "record", "action": "toggle", "mode": mode})
```

add:

```python
    def on_rec_mode_changed(self, knob, mode):
        self.lbl_rec_mode.set_text(_REC_MODE_LABELS[mode])
```

- [ ] **Step 7: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('sqlch_gui/ui/now_playing.py').read())"`
Expected: no output, exit code 0.

- [ ] **Step 8: Run the app and visually verify the badge**

Launch per the `sqlch-gui-dev-launch` memory conventions. Confirm:
- A small "FULL" badge sits at the bottom-right corner of the REC bubble at rest.
- Right-click flips the badge to "TRK" and back instantly (no perceptible delay) — this is the `mode-changed` signal firing, not the daemon poll.
- Start a recording (left-click): the badge still reads the correct mode while the bubble goes red/pressed; right-click no longer changes it (mode locked while rolling — same as before).
- Stop recording: badge and bubble return to idle state correctly.
- If the badge visually overlaps the bubble's dashed ring more than looks right, adjust `set_margin_end` / `set_margin_bottom` on `self.lbl_rec_mode` by a few pixels and re-check — there's no exact spec for this, judge by eye against the approved mockup (bubble + corner badge, sewn/felt aesthetic).
- Confirm VOL knob, STOP, and MUTE buttons are visually unaffected.

- [ ] **Step 9: Commit**

```bash
git add sqlch_gui/ui/now_playing.py
git commit -m "feat(sqlch-gui): add corner mode badge for the REC bubble

Mode (FULL/TRACK) moved off the old dial's pointer angle onto a small
Gtk.Overlay badge next to the bubble, reusing the existing .small-badge
CSS class. Wired to both the daemon-poll set_state() path and the new
mode-changed signal, so right-click still gives instant feedback instead
of waiting on the ~1s poll cycle."
```
