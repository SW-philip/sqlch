"""Custom GTK 4 Rotary Knob Component."""

import math
import cairo
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GObject

class RotaryKnob(Gtk.DrawingArea):
    """A tactile rotary dial widget backing onto a Gtk.Adjustment."""

    __gsignals__ = {
        'value-changed': (GObject.SignalFlags.RUN_LAST, None, (float,)),
    }

    def __init__(self, adjustment: Gtk.Adjustment, label: str = ""):
        super().__init__()
        self.adj = adjustment
        self.label = label
        self.set_focusable(True)
        self.set_size_request(65, 65)

        # Connect internal update triggers
        self.adj.connect("value-changed", lambda _: self.queue_draw())
        self.set_draw_func(self._on_draw)

        # Interaction gesture tracking
        self.drag_start_y = 0.0
        self.drag_start_val = 0.0

        drag_gest = Gtk.GestureDrag.new()
        drag_gest.connect("drag-begin", self._on_drag_begin)
        drag_gest.connect("drag-update", self._on_drag_update)
        self.add_controller(drag_gest)

        scroll_gest = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll_gest.connect("scroll", self._on_scroll)
        self.add_controller(scroll_gest)

    def _on_draw(self, area, cr, width, height, user_data=None):
        cx = width / 2.0
        cy = height / 2.0
        radius = min(width, height) / 2.0 - 6.0

        # Physical angle limits (270-degree throw layout)
        min_angle = 0.75 * math.pi
        max_angle = 2.25 * math.pi

        # Map current scale position
        norm = (self.adj.get_value() - self.adj.get_lower()) / (self.adj.get_upper() - self.adj.get_lower())
        current_angle = min_angle + norm * (max_angle - min_angle)

        # Draw outer metal bezel
        cr.set_line_width(3.0)
        cr.set_source_rgba(0.12, 0.12, 0.14, 1.0) # Using solid baseline tone
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()

        # Faceplate
        cr.set_source_rgba(0.20, 0.20, 0.22, 1.0)
        cr.arc(cx, cy, radius - 1, 0, 2 * math.pi)
        cr.fill()

        # Dashed stitch ring, echoes the fabric hem convention used elsewhere in the UI
        cr.save()
        cr.set_dash([2.0, 3.0])
        cr.set_line_width(1.5)
        cr.set_source_rgba(0.9, 0.9, 0.9, 0.35)
        cr.arc(cx, cy, radius + 4.0, 0, 2 * math.pi)
        cr.stroke()
        cr.restore()

        # Unused tracking arc track
        cr.set_line_width(4.0)
        cr.set_source_rgba(0.1, 0.1, 0.1, 0.4)
        cr.arc(cx, cy, radius - 6, min_angle, max_angle)
        cr.stroke()

        # High-visibility marker line indicating current turn position
        cr.set_line_width(4.0)
        cr.set_source_rgba(0.85, 0.61, 0.25, 1.0) # Accent point
        mx = cx + (radius - 12) * math.cos(current_angle)
        my = cy + (radius - 12) * math.sin(current_angle)
        cr.move_to(cx, cy)
        cr.line_to(mx, my)
        cr.stroke()

        # Center cap core
        cr.set_source_rgba(0.12, 0.12, 0.14, 1.0)
        cr.arc(cx, cy, radius * 0.25, 0, 2 * math.pi)
        cr.fill()

    def _on_drag_begin(self, gesture, start_x, start_y):
        self.drag_start_y = start_y
        self.drag_start_val = self.adj.get_value()
        self.grab_focus()

    def _on_drag_update(self, gesture, offset_x, offset_y):
        # Vertical drag delta modifies settings relative to overall range
        total_range = self.adj.get_upper() - self.adj.get_lower()
        delta_y = -offset_y  # Drag up to increase value
        sensitivity = 0.005  # Drag scale rate

        new_val = self.drag_start_val + (delta_y * sensitivity * total_range)
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
