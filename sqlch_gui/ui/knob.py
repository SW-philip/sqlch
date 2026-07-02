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

    def _on_draw(self, area, cr, width, height, user_data):
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
