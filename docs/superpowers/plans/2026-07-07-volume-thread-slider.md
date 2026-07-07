# Volume Control: Zipper + Pepper → Thread & Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `ZipperSlider` + `PepperToggle` with a single widget, `ThreadSlider` — a tufted upholstery button riding a dashed sewing thread, dragged past the thread's end onto a fixed "nub" to engage a hard-coded 120% volume boost.

**Architecture:** Two tasks, ordered so the app is fully working after each commit (mirrors the split used in `docs/superpowers/plans/2026-07-06-volume-zipper-slider.md`). Task 1 deletes `ZipperSlider` and `PepperToggle` outright and adds `ThreadSlider` in a boost-less form — plain dashed thread, tufted button, click/drag/scroll — wired into `now_playing.py` as a complete (if boost-less) replacement. Task 2 expands `ThreadSlider` in place with the nub, the boosted/hot rendering state, and the drag-past-edge-to-engage / click-or-drag-to-disengage interaction, then reconnects `NowPlayingPanel`'s existing `_pre_boost_vol` bookkeeping to the new widget's `boost-toggled` signal.

**Tech Stack:** Python 3.12, GTK4 (PyGObject), Cairo (pycairo). No test framework in this repo; pure-syntax changes are checked with `python3 -c "import ast; ast.parse(...)"` and GTK/visual changes are verified by running the app per the `sqlch-gui-dev-launch` memory (working tree + wrapper env + `LD_PRELOAD`, killed by PID once verified — never left running in the background).

**Spec:** `docs/superpowers/specs/2026-07-07-volume-thread-slider-design.md`

---

## Task 1: Replace `ZipperSlider` + `PepperToggle` with a boost-less `ThreadSlider`

**Files:**
- Modify: `sqlch_gui/ui/controls.py:1` (module docstring)
- Modify: `sqlch_gui/ui/controls.py:28-203` (the entire `ZipperSlider` class → `ThreadSlider`)
- Modify: `sqlch_gui/ui/controls.py:327-412` (delete the entire `PepperToggle` class)
- Modify: `sqlch_gui/ui/now_playing.py:9` (import)
- Modify: `sqlch_gui/ui/now_playing.py:136-143` (volume adjustment/widget construction)
- Modify: `sqlch_gui/ui/now_playing.py:179-180` (`vol_row` wiring)
- Modify: `sqlch_gui/ui/now_playing.py:490-509` (`on_vol_changed` simplification, remove `on_boost_toggled`)

- [ ] **Step 1: Update the module docstring**

In `sqlch_gui/ui/controls.py`, replace line 1:

```python
"""Custom GTK 4 tactile controls: pop-it bubble, zipper slider, boost toggle."""
```

with:

```python
"""Custom GTK 4 tactile controls: pop-it bubble, thread-and-button volume slider."""
```

- [ ] **Step 2: Replace `ZipperSlider` (lines 28-203) with a boost-less `ThreadSlider`**

Replace the entire block from `class ZipperSlider(Gtk.DrawingArea):` (line 28) through the end of its `_on_scroll` method (line 203 — the line before the two blank lines that precede `class RecordBubble`) with:

```python
class ThreadSlider(Gtk.DrawingArea):
    """Full-width volume fader drawn as a tufted upholstery button riding
    a dashed sewing thread. Backs onto a Gtk.Adjustment, same as the
    zipper slider it replaces, but the track is a plain thread with no
    open/closed states -- all the visual richness lives in the button.
    Click anywhere on the thread to jump there; drag the button; scroll
    to nudge.
    """

    __gsignals__ = {
        'value-changed': (GObject.SignalFlags.RUN_LAST, None, (float,)),
    }

    # Single source of truth for the button's edge margin, so drawing
    # and hit-testing can never drift apart.
    _MARGIN = 10.0

    def __init__(self, adjustment: Gtk.Adjustment):
        super().__init__()
        self.adj = adjustment
        self.set_focusable(True)
        self.set_hexpand(True)
        self.set_size_request(-1, 34)

        self.adj.connect("value-changed", lambda _: self.queue_draw())
        self.set_draw_func(self._on_draw)

        self.drag_start_val = 0.0
        self._dragging = False

        click_gest = Gtk.GestureClick.new()
        click_gest.set_button(1)
        click_gest.connect("released", self._on_click)
        self.add_controller(click_gest)

        drag_gest = Gtk.GestureDrag.new()
        drag_gest.connect("drag-begin", self._on_drag_begin)
        drag_gest.connect("drag-update", self._on_drag_update)
        drag_gest.connect("drag-end", self._on_drag_end)
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

    def _usable_width(self, width: float) -> float:
        return width - 2.0 * self._MARGIN

    def _button_x(self, width: float) -> float:
        return self._MARGIN + self._norm() * self._usable_width(width)

    def _on_draw(self, area, cr, width, height, user_data=None):
        cy = height / 2.0
        button_x = self._button_x(width)

        bar_rgb = _hex_to_rgb_floats(palette.load().get('BAR', '#6e6a86'))
        thread_rgb = _shade(bar_rgb, 1.15)
        button_rgb = _shade(bar_rgb, 1.05)
        dimple_rgb = _shade(bar_rgb, 0.3)

        # The sewing thread: a plain dashed line the full track width --
        # no zipped/open states, all the richness lives in the button.
        cr.save()
        cr.set_dash([4.0, 4.0])
        cr.set_line_width(2.0)
        cr.set_source_rgba(*thread_rgb, 0.7)
        cr.move_to(self._MARGIN - 2.0, cy)
        cr.line_to(width - self._MARGIN + 2.0, cy)
        cr.stroke()
        cr.restore()

        # Tufted button: domed radial gradient, single center dimple,
        # four pull-lines radiating out to the puckered fabric edge --
        # the chesterfield-upholstery look.
        radius = 15.0
        gradient = cairo.RadialGradient(
            button_x - radius * 0.3, cy - radius * 0.3, radius * 0.1,
            button_x, cy, radius,
        )
        gradient.add_color_stop_rgba(0.0, *_shade(button_rgb, 1.5), 1.0)
        gradient.add_color_stop_rgba(0.5, *button_rgb, 1.0)
        gradient.add_color_stop_rgba(1.0, *_shade(button_rgb, 0.55), 1.0)
        cr.set_source(gradient)
        cr.arc(button_x, cy, radius, 0, 2 * math.pi)
        cr.fill()

        cr.set_source_rgba(*dimple_rgb, 1.0)
        cr.arc(button_x, cy, 2.6, 0, 2 * math.pi)
        cr.fill()

        cr.save()
        cr.set_source_rgba(0.0, 0.0, 0.0, 0.3)
        cr.set_line_width(1.0)
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            cr.move_to(button_x, cy)
            cr.line_to(button_x + dx * radius * 0.7, cy + dy * radius * 0.7)
        cr.stroke()
        cr.restore()

    def _on_click(self, gesture, n_press, x, y):
        if self._dragging:
            return
        width = self.get_width()
        usable = self._usable_width(width)
        if usable <= 0:
            return
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
        total_range = self.adj.get_upper() - self.adj.get_lower()
        delta_norm = offset_x / usable
        new_val = self.drag_start_val + delta_norm * total_range
        new_val = max(self.adj.get_lower(), min(self.adj.get_upper(), new_val))
        self.adj.set_value(new_val)
        self.emit('value-changed', new_val)

    def _on_drag_end(self, gesture, offset_x, offset_y):
        # Deferred to idle so any 'released' from the co-installed
        # GestureClick for this same button-up is still guarded by
        # _dragging, no matter which controller GTK dispatches first.
        GLib.idle_add(self._clear_dragging)

    def _clear_dragging(self):
        self._dragging = False
        return GLib.SOURCE_REMOVE

    def _on_scroll(self, controller, dx, dy):
        total_range = self.adj.get_upper() - self.adj.get_lower()
        step = (total_range * 0.05) if dy > 0 else -(total_range * 0.05)
        new_val = self.adj.get_value() - step
        new_val = max(self.adj.get_lower(), min(self.adj.get_upper(), new_val))
        self.adj.set_value(new_val)
        self.emit('value-changed', new_val)
```

(This preserves the two blank lines that already separate this class from `class RecordBubble` below — do not add or remove blank lines around it.)

- [ ] **Step 3: Delete the entire `PepperToggle` class**

Delete lines 327-412 of `sqlch_gui/ui/controls.py` in full — the two blank lines after `RecordBubble`'s last line (`cr.stroke_preserve()`) through the end of the file (`class PepperToggle(Gtk.DrawingArea):` and everything below it). After this deletion, `RecordBubble`'s `cr.stroke_preserve()` line is the last line in the file (with a single trailing newline).

- [ ] **Step 4: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/controls.py').read())"
```

Expected: no output, exit code 0.

- [ ] **Step 5: Update the import in `now_playing.py`**

Replace line 9:

```python
from .controls import ZipperSlider, RecordBubble, PepperToggle
```

with:

```python
from .controls import ThreadSlider, RecordBubble
```

- [ ] **Step 6: Replace the volume adjustment/widget construction**

Replace lines 136-143:

```python
        self.vol_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=1.0, step_increment=0.05)

        self.vol_slider = ZipperSlider(self.vol_adj)
        self._vol_handler = self.vol_slider.connect("value-changed", self.on_vol_changed)

        self._pre_boost_vol: float | None = None
        self.pepper = PepperToggle()
        self.pepper.connect("boost-toggled", self.on_boost_toggled)
```

with:

```python
        self.vol_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=1.0, step_increment=0.05)

        self.vol_slider = ThreadSlider(self.vol_adj)
        self._vol_handler = self.vol_slider.connect("value-changed", self.on_vol_changed)
```

- [ ] **Step 7: Remove the pepper from `vol_row`**

Replace lines 179-180:

```python
        vol_row.append(self.vol_slider)
        vol_row.append(self.pepper)
```

with:

```python
        vol_row.append(self.vol_slider)
```

- [ ] **Step 8: Simplify `on_vol_changed` and remove `on_boost_toggled`**

Replace lines 490-509 (from `def on_vol_changed` through the end of the file):

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

with:

```python
    def on_vol_changed(self, slider, val):
        # Dynamically push numeric modifications into stdout subsystem
        self.lbl_vol_percent.set_text(f"{int(val * 100)}%")
        import subprocess
        subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{val:.2f}"], stdout=subprocess.DEVNULL)
```

(`on_boost_toggled` and `_pre_boost_vol` come back in Task 2, once `ThreadSlider` actually emits `boost-toggled` again.)

- [ ] **Step 9: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/now_playing.py').read())"
```

Expected: no output, exit code 0.

- [ ] **Step 10: Run the app and visually verify the boost-less slider**

Launch per the `sqlch-gui-dev-launch` memory conventions (working tree, wrapper env + `LD_PRELOAD`; kill any prior instance with a separate `pkill -f "python3 -m sqlch_gui"` command first). Confirm:
- A full-width dashed thread sits below the REC/Stop/Mute row, with a "VOL" tag beneath it — no zipper teeth, no pepper.
- A domed, tufted button (center dimple + four radiating pull-lines) sits on the thread at the current volume position.
- Dragging the button, clicking anywhere else on the thread, and scrolling over it all change volume, and the existing percent readout in the tech-badge strip updates accordingly.
- REC bubble, Stop, and Mute are visually/behaviorally unaffected.
- No console errors/tracebacks on startup or interaction.

Kill the dev instance by PID (separate command) once verified.

- [ ] **Step 11: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/controls.py sqlch_gui/ui/now_playing.py
git commit -m "$(cat <<'EOF'
feat(sqlch-gui): replace zipper+pepper with a thread-and-button slider

ZipperSlider (denim hardware) and PepperToggle (a vegetable sticker)
read as two unrelated material worlds bolted together. ThreadSlider
replaces both with one object in the same fabric-craft language as the
rest of the app: a tufted upholstery button riding a plain dashed
sewing thread. This commit ships the boost-less base -- click/drag/
scroll all work exactly as before -- the 120% boost (dragging the
button off the thread onto a nub) lands in a follow-up commit.
EOF
)"
```

---

## Task 2: Add the nub and 120% boost to `ThreadSlider`

**Files:**
- Modify: `sqlch_gui/ui/controls.py` (docstring comment inside `ThreadSlider`, `__gsignals__`, class constants, `__init__`, `_usable_width`/`_button_x`, `_on_draw`, `_on_click`, `_on_drag_begin`, `_on_drag_update`, `_on_drag_end`, `_on_scroll` — the entire `ThreadSlider` class from Task 1)
- Modify: `sqlch_gui/ui/now_playing.py` (re-add `_pre_boost_vol` + `boost-toggled` connection, re-add `on_boost_toggled`)

- [ ] **Step 1: Replace the entire `ThreadSlider` class with the boost-aware version**

Replace the entire `ThreadSlider` class written in Task 1 (from `class ThreadSlider(Gtk.DrawingArea):` through the end of its `_on_scroll` method) with:

```python
class ThreadSlider(Gtk.DrawingArea):
    """Full-width volume fader drawn as a tufted upholstery button riding
    a dashed sewing thread. Backs onto a Gtk.Adjustment, same as the
    zipper slider it replaces, but the track is a plain thread with no
    open/closed states -- all the visual richness lives in the button.
    Click anywhere on the thread to jump there; drag the button; scroll
    to nudge.

    Past the thread's right edge sits a fixed, always-visible "nub" (an
    empty buttonhole loop). Dragging the button past the track's edge
    and onto the nub engages a hard-coded 120% volume boost -- the same
    button re-colors hot (palette FORTE) and docks there. The
    adjustment itself is never changed by boosting; only
    NowPlayingPanel's boost-toggled handler drives the actual wpctl
    volume change. Boost only engages via drag (a plain click on the
    empty nub is a no-op); it disengages either by clicking the docked
    button (pops back to the exact pre-boost value) or by dragging it
    back onto the thread (lands wherever dropped, manual value wins).
    """

    __gsignals__ = {
        'value-changed': (GObject.SignalFlags.RUN_LAST, None, (float,)),
        'boost-toggled': (GObject.SignalFlags.RUN_LAST, None, (bool,)),
    }

    # Single source of truth for the button's edge margin and the nub's
    # geometry, so drawing and hit-testing can never drift apart.
    _MARGIN = 10.0
    _NUB_GAP = 10.0
    _NUB_ZONE = 34.0
    _NUB_RADIUS_X = 9.0
    _NUB_RADIUS_Y = 13.0

    def __init__(self, adjustment: Gtk.Adjustment):
        super().__init__()
        self.adj = adjustment
        self.boosted = False
        self.set_focusable(True)
        self.set_hexpand(True)
        self.set_size_request(-1, 34)

        self.adj.connect("value-changed", lambda _: self.queue_draw())
        self.set_draw_func(self._on_draw)
        self._update_tooltip()

        self.drag_start_val = 0.0
        self._dragging = False
        self._drag_from_nub = False

        click_gest = Gtk.GestureClick.new()
        click_gest.set_button(1)
        click_gest.connect("released", self._on_click)
        self.add_controller(click_gest)

        drag_gest = Gtk.GestureDrag.new()
        drag_gest.connect("drag-begin", self._on_drag_begin)
        drag_gest.connect("drag-update", self._on_drag_update)
        drag_gest.connect("drag-end", self._on_drag_end)
        self.add_controller(drag_gest)

        scroll_gest = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll_gest.connect("scroll", self._on_scroll)
        self.add_controller(scroll_gest)

    def _update_tooltip(self):
        self.set_tooltip_text(
            "Tap the button to restore volume" if self.boosted
            else "Drag the button onto the nub for 120% boost"
        )

    def _norm(self) -> float:
        return (self.adj.get_value() - self.adj.get_lower()) / (self.adj.get_upper() - self.adj.get_lower())

    def _set_from_norm(self, norm: float):
        norm = max(0.0, min(1.0, norm))
        new_val = self.adj.get_lower() + norm * (self.adj.get_upper() - self.adj.get_lower())
        self.adj.set_value(new_val)
        self.emit('value-changed', new_val)

    def _usable_width(self, width: float) -> float:
        return width - 2.0 * self._MARGIN - self._NUB_ZONE

    def _button_x(self, width: float) -> float:
        return self._MARGIN + self._norm() * self._usable_width(width)

    def _track_right(self, width: float) -> float:
        return self._MARGIN + self._usable_width(width)

    def _nub_x(self, width: float) -> float:
        return self._track_right(width) + self._NUB_GAP + self._NUB_RADIUS_X

    def _on_draw(self, area, cr, width, height, user_data=None):
        cy = height / 2.0
        thread_x = self._button_x(width)
        nub_x = self._nub_x(width)
        track_right = self._track_right(width)

        colors = palette.load()
        bar_rgb = _hex_to_rgb_floats(colors.get('BAR', '#6e6a86'))
        thread_rgb = _shade(bar_rgb, 1.15)
        button_rgb = _shade(bar_rgb, 1.05)
        dimple_rgb = _shade(bar_rgb, 0.3)
        forte_rgb = _hex_to_rgb_floats(colors.get('FORTE', '#eb6f92'))

        # The sewing thread: a plain dashed line across the track only
        # (never through the nub zone) -- no open/closed states.
        cr.save()
        cr.set_dash([4.0, 4.0])
        cr.set_line_width(2.0)
        cr.set_source_rgba(*thread_rgb, 0.7)
        cr.move_to(self._MARGIN - 2.0, cy)
        cr.line_to(track_right, cy)
        cr.stroke()
        cr.restore()

        # The nub: an empty buttonhole loop past the thread's end,
        # always visible whether or not the button is docked there --
        # that's the discoverability cue.
        cr.save()
        cr.set_source_rgba(*thread_rgb, 0.6)
        cr.set_line_width(1.6)
        cr.save()
        cr.translate(nub_x, cy)
        cr.scale(self._NUB_RADIUS_X, self._NUB_RADIUS_Y)
        cr.arc(0, 0, 1.0, 0, 2 * math.pi)
        cr.restore()
        cr.stroke()
        cr.move_to(nub_x - self._NUB_RADIUS_X + 2.0, cy)
        cr.line_to(nub_x + self._NUB_RADIUS_X - 2.0, cy)
        cr.stroke()
        cr.restore()

        if self.boosted:
            # Ghost marker: a faint ring at the resting spot the button
            # will return to once un-boosted.
            cr.save()
            cr.set_dash([1.5, 1.5])
            cr.set_line_width(1.2)
            cr.set_source_rgba(*thread_rgb, 0.5)
            cr.arc(thread_x, cy, 3.0, 0, 2 * math.pi)
            cr.stroke()
            cr.restore()
            button_x = nub_x
            base_rgb = forte_rgb
        else:
            button_x = thread_x
            base_rgb = button_rgb

        # Tufted button: domed radial gradient, single center dimple,
        # four pull-lines radiating out to the puckered fabric edge --
        # the chesterfield-upholstery look, not a sew-through button.
        radius = 15.0
        gradient = cairo.RadialGradient(
            button_x - radius * 0.3, cy - radius * 0.3, radius * 0.1,
            button_x, cy, radius,
        )
        gradient.add_color_stop_rgba(0.0, *_shade(base_rgb, 1.5), 1.0)
        gradient.add_color_stop_rgba(0.5, *base_rgb, 1.0)
        gradient.add_color_stop_rgba(1.0, *_shade(base_rgb, 0.55), 1.0)
        cr.set_source(gradient)
        cr.arc(button_x, cy, radius, 0, 2 * math.pi)
        cr.fill()

        cr.set_source_rgba(*dimple_rgb, 1.0)
        cr.arc(button_x, cy, 2.6, 0, 2 * math.pi)
        cr.fill()

        cr.save()
        cr.set_source_rgba(0.0, 0.0, 0.0, 0.3)
        cr.set_line_width(1.0)
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            cr.move_to(button_x, cy)
            cr.line_to(button_x + dx * radius * 0.7, cy + dy * radius * 0.7)
        cr.stroke()
        cr.restore()

    def _on_click(self, gesture, n_press, x, y):
        if self._dragging:
            return
        width = self.get_width()
        usable = self._usable_width(width)
        if usable <= 0:
            return
        if self.boosted:
            if x > self._track_right(width):
                # Tapping the docked button: quick pop back to pre-boost.
                self.boosted = False
                self._update_tooltip()
                self.emit('boost-toggled', False)
                self.queue_draw()
            else:
                # Tapping the thread while boosted: manual override --
                # un-boost, then jump straight to the clicked position.
                self.boosted = False
                self._update_tooltip()
                self.emit('boost-toggled', False)
                self._set_from_norm((x - self._MARGIN) / usable)
            return
        if x > self._track_right(width):
            return  # clicking the empty nub/gap does nothing -- drag only
        self._set_from_norm((x - self._MARGIN) / usable)

    def _on_drag_begin(self, gesture, start_x, start_y):
        self.drag_start_val = self.adj.get_value()
        self._drag_from_nub = self.boosted
        self.grab_focus()

    def _on_drag_update(self, gesture, offset_x, offset_y):
        self._dragging = True
        width = self.get_width()
        usable = self._usable_width(width)
        if usable <= 0:
            return

        if self._drag_from_nub:
            nub_x = self._nub_x(width)
            candidate_x = nub_x + offset_x
            if candidate_x > self._track_right(width):
                return  # still parked over the nub; nothing changes
            if self.boosted:
                self.boosted = False
                self._update_tooltip()
                self.emit('boost-toggled', False)
            norm = max(0.0, min(1.0, (candidate_x - self._MARGIN) / usable))
            new_val = self.adj.get_lower() + norm * (self.adj.get_upper() - self.adj.get_lower())
            self.adj.set_value(new_val)
            self.emit('value-changed', new_val)
            return

        total_range = self.adj.get_upper() - self.adj.get_lower()
        delta_norm = offset_x / usable
        raw_val = self.drag_start_val + delta_norm * total_range
        if raw_val > self.adj.get_upper():
            return  # reaching past the track's end -- not a value yet
        new_val = max(self.adj.get_lower(), raw_val)
        self.adj.set_value(new_val)
        self.emit('value-changed', new_val)

    def _on_drag_end(self, gesture, offset_x, offset_y):
        if not self._drag_from_nub:
            width = self.get_width()
            usable = self._usable_width(width)
            if usable > 0:
                total_range = self.adj.get_upper() - self.adj.get_lower()
                delta_norm = offset_x / usable
                raw_val = self.drag_start_val + delta_norm * total_range
                overshoot_px = (raw_val - self.adj.get_upper()) * usable
                if overshoot_px >= self._NUB_GAP + self._NUB_RADIUS_X:
                    self.boosted = True
                    self._update_tooltip()
                    self.emit('boost-toggled', True)
                    self.queue_draw()
        # Deferred to idle so any 'released' from the co-installed
        # GestureClick for this same button-up is still guarded by
        # _dragging, no matter which controller GTK dispatches first.
        GLib.idle_add(self._clear_dragging)

    def _clear_dragging(self):
        self._dragging = False
        return GLib.SOURCE_REMOVE

    def _on_scroll(self, controller, dx, dy):
        if self.boosted:
            self.boosted = False
            self._update_tooltip()
            self.emit('boost-toggled', False)
        total_range = self.adj.get_upper() - self.adj.get_lower()
        step = (total_range * 0.05) if dy > 0 else -(total_range * 0.05)
        new_val = self.adj.get_value() - step
        new_val = max(self.adj.get_lower(), min(self.adj.get_upper(), new_val))
        self.adj.set_value(new_val)
        self.emit('value-changed', new_val)
```

- [ ] **Step 2: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/controls.py').read())"
```

Expected: no output, exit code 0.

- [ ] **Step 3: Re-add `_pre_boost_vol` and connect `boost-toggled`**

In `sqlch_gui/ui/now_playing.py`, replace:

```python
        self.vol_slider = ThreadSlider(self.vol_adj)
        self._vol_handler = self.vol_slider.connect("value-changed", self.on_vol_changed)
```

with:

```python
        self.vol_slider = ThreadSlider(self.vol_adj)
        self._vol_handler = self.vol_slider.connect("value-changed", self.on_vol_changed)

        self._pre_boost_vol: float | None = None
        self.vol_slider.connect("boost-toggled", self.on_boost_toggled)
```

- [ ] **Step 4: Re-add the boost-toggle handler**

Directly below `on_vol_changed`, add:

```python

    def on_boost_toggled(self, slider, active):
        import subprocess
        if active:
            self._pre_boost_vol = self.vol_adj.get_value()
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "1.20"], stdout=subprocess.DEVNULL)
        else:
            restore = self._pre_boost_vol if self._pre_boost_vol is not None else 0.0
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{restore:.2f}"], stdout=subprocess.DEVNULL)
            self._pre_boost_vol = None
```

`on_vol_changed` itself needs no change here: `ThreadSlider` always emits `boost-toggled(False)` *before* `value-changed` whenever a manual interaction overrides an active boost (see the drag-from-nub, click, and scroll branches in Step 1 above), so by the time `on_vol_changed` runs, `on_boost_toggled(False)` has already restored `_pre_boost_vol` and cleared it — no `if boosted` special-casing needed on the `NowPlayingPanel` side, unlike the old `PepperToggle` wiring.

- [ ] **Step 5: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/now_playing.py').read())"
```

Expected: no output, exit code 0.

- [ ] **Step 6: Run the app and visually verify the full boost mechanic**

Launch per the `sqlch-gui-dev-launch` memory conventions. Confirm:
- An empty buttonhole "nub" is now visible past the thread's right edge at all times.
- Dragging the button past the thread's right edge and releasing on/past the nub: it snaps in, recolors to the palette's `FORTE` color, and volume jumps to 120% (verify with `wpctl get-volume @DEFAULT_AUDIO_SINK@` in another terminal, or by ear).
- Dragging past the edge but releasing short of the nub: the button springs back to the track's end without engaging boost.
- A plain click directly on the empty nub (not boosted, no drag): nothing happens.
- While boosted, clicking the docked button: it pops back to the exact pre-boost volume/position.
- While boosted, dragging the button back onto the thread: boost disengages and the dropped position becomes the new volume.
- While boosted, scrolling over the widget: boost disengages and the scroll nudge applies from the pre-boost value.
- Switch palettes (edit `~/.config/waybar/palette.sh` or set `SQLCH_GUI_PALETTE` to a different file) and confirm the thread/button idle colors and the boosted `FORTE` color both update live, without restarting the app.
- REC bubble, Stop, and Mute remain visually/behaviorally unaffected.
- No console errors/tracebacks on startup or interaction.

Kill the dev instance by PID (separate command) once verified.

- [ ] **Step 7: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/controls.py sqlch_gui/ui/now_playing.py
git commit -m "$(cat <<'EOF'
feat(sqlch-gui): drag the thread-slider button onto a nub for 120% boost

Extends ThreadSlider with a fixed, always-visible buttonhole "nub" past
the thread's end. Dragging the button off the thread and onto the nub
engages a hard-coded 120% boost -- the button itself docks there and
recolors using the palette's FORTE (warning/alert) key instead of a
hardcoded red, matching the system-wide "never hardcode hex" rule.
Boost only engages via drag; it disengages via a click on the docked
button (instant restore) or by dragging it back onto the thread
(manual value wins), both driving NowPlayingPanel's existing
wpctl-based pre/post-boost volume bookkeeping through the widget's
boost-toggled signal.
EOF
)"
```

---

## Self-Review Notes

- **Spec coverage:** "Concept: one object, two homes" and file organization → Task 1 (delete both old classes, single new `ThreadSlider`). `ThreadSlider` rendering (thread, button, palette-driven idle colors) → Task 1 Step 2. Nub rendering, boosted/`FORTE` recolor, ghost marker → Task 2 Step 1's `_on_draw`. Normal-range interaction (click/drag/scroll) → Task 1 Step 2; carried into Task 2 unchanged for the non-nub case. Engaging boost only via drag-past-edge with spring-back → Task 2 Step 1's `_on_drag_update`/`_on_drag_end`. Disengaging via click-on-docked-button (exact restore) or drag-back (manual value wins) or scroll (un-boost then apply) → Task 2 Step 1's `_on_click`/`_on_drag_update`/`_on_scroll`. Boost semantics owned by `NowPlayingPanel` (`_pre_boost_vol`, wpctl calls) → Task 2 Steps 3-4. Layout (`vol_row` single widget, VOL caption unchanged, no percent duplication) → Task 1 Steps 6-7. All spec sections have a corresponding step.
- **Placeholder scan:** No TBD/TODO; every step shows complete code, not descriptions of code.
- **Type/name consistency:** `self.vol_slider` (a `ThreadSlider`) used consistently from Task 1 Step 6 onward, including `update_indicators`'s existing `handler_block`/`handler_unblock` calls (untouched — they already reference `self.vol_slider`, so no step needed there). `on_vol_changed(self, slider, val)`'s parameter name and signal shape match `ThreadSlider`'s `value-changed(float)` throughout both tasks. `on_boost_toggled(self, slider, active)` matches `ThreadSlider`'s `boost-toggled(bool)` signal shape introduced in Task 2 Step 1. `_pre_boost_vol` naming and its `None`-fallback restore logic in Task 2 Step 4 exactly matches the pre-existing `PepperToggle`-era handler being restored, so `NowPlayingPanel`'s external behavior (what `wpctl` gets called with, when) is unchanged from before this whole redesign.
