"""Custom GTK 4 tactile controls: pop-it bubble and zipper slider."""

import math
import cairo
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GObject, GLib

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

    # Single source of truth for the pull's edge margin, so the drawn
    # position and the click/drag hit-testing can never drift apart.
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

    def _pull_x(self, width: float) -> float:
        return self._MARGIN + self._norm() * self._usable_width(width)

    def _on_draw(self, area, cr, width, height, user_data=None):
        pull_x = self._pull_x(width)

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
        if self._dragging:
            # A drag just released the pull on this same button-up; don't
            # let this click's 'released' event overwrite it with an
            # absolute jump. (GTK doesn't guarantee which of GestureClick's
            # 'released' vs GestureDrag's 'drag-end' fires first for the
            # same event, so the flag reset below is deferred to idle
            # rather than done inline in _on_drag_end -- that way this
            # check sees True regardless of dispatch order.)
            return
        width = self.get_width()
        usable = self._usable_width(width)
        if usable <= 0:
            return
        self._set_from_norm((x - self._MARGIN) / usable)

    def _on_drag_begin(self, gesture, start_x, start_y):
        self._dragging = True
        self.drag_start_val = self.adj.get_value()
        self.grab_focus()

    def _on_drag_update(self, gesture, offset_x, offset_y):
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

        # Dashed stitch ring, echoes the fabric-hem convention used elsewhere in this file; turns red while recording
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
