"""Custom GTK 4 Rotary Knob Component."""

import math
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


class RecordKnob(Gtk.DrawingArea):
    """Two-detent record switch drawn in the RotaryKnob idiom.

    Right-click spins the pointer between the FULL and TRACK detents;
    left-click emits 'record-toggled' with the selected mode. Recording
    state is pushed in from the daemon poll via set_state() — the widget
    never assumes its click succeeded.
    """

    __gsignals__ = {
        'record-toggled': (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    MODES = ("full", "track")
    # Lower arc detents (y grows downward): FULL lower-left, TRACK lower-right
    _ANGLES = {"full": 0.75 * math.pi, "track": 0.25 * math.pi}

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

    def _on_draw(self, area, cr, width, height, user_data=None):
        cx = width / 2.0
        cy = height / 2.0
        radius = min(width, height) / 2.0 - 5.0
        rec_red = (0.86, 0.20, 0.18)

        # Hot ring while recording sits outside the bezel
        if self.recording:
            cr.set_line_width(2.5)
            cr.set_source_rgba(*rec_red, 0.9)
            cr.arc(cx, cy, radius + 2.0, 0, 2 * math.pi)
            cr.stroke()

        # Outer metal bezel + faceplate (matches RotaryKnob)
        cr.set_line_width(3.0)
        cr.set_source_rgba(0.12, 0.12, 0.14, 1.0)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()
        cr.set_source_rgba(0.20, 0.20, 0.22, 1.0)
        cr.arc(cx, cy, radius - 1, 0, 2 * math.pi)
        cr.fill()

        # Dashed stitch ring, matches RotaryKnob
        cr.save()
        cr.set_dash([2.0, 3.0])
        cr.set_line_width(1.5)
        cr.set_source_rgba(0.9, 0.9, 0.9, 0.35)
        cr.arc(cx, cy, radius + 4.0, 0, 2 * math.pi)
        cr.stroke()
        cr.restore()

        # Detent dots at both switch positions
        for ang in self._ANGLES.values():
            dx = cx + (radius - 4) * math.cos(ang)
            dy = cy + (radius - 4) * math.sin(ang)
            cr.set_source_rgba(0.1, 0.1, 0.1, 0.6)
            cr.arc(dx, dy, 2.0, 0, 2 * math.pi)
            cr.fill()

        # Pointer snapped to the selected detent
        angle = self._ANGLES[self.mode]
        if self.recording:
            cr.set_source_rgba(*rec_red, 1.0)
        else:
            cr.set_source_rgba(0.85, 0.61, 0.25, 1.0)  # RotaryKnob accent
        cr.set_line_width(4.0)
        mx = cx + (radius - 9) * math.cos(angle)
        my = cy + (radius - 9) * math.sin(angle)
        cr.move_to(cx, cy)
        cr.line_to(mx, my)
        cr.stroke()

        # Center cap doubles as the recording lamp
        if self.recording:
            cr.set_source_rgba(*rec_red, 1.0)
        else:
            cr.set_source_rgba(0.12, 0.12, 0.14, 1.0)
        cr.arc(cx, cy, radius * 0.28, 0, 2 * math.pi)
        cr.fill()
