"""Decorative EQ bead strip — a non-audio-reactive procedural animation.

Revisits the "future work" item tabled in the 2026-07-01 visual refresh
spec: a real audio-reactive meter needs an mpv audio-filter pipeline
(astats/showvolume) and was judged too risky then. This is the decorative
fallback that spec named, drawn in the same Cairo-widget idiom as the
knobs in knob.py.
"""

import math
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib
from .. import palette


def _hex_to_rgb_floats(hex_val: str) -> tuple[float, float, float]:
    h = hex_val.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return r, g, b


class EqStrip(Gtk.DrawingArea):
    """Row of soft fabric 'beads' that bob in a procedural wave while active."""

    N_BEADS = 7
    FRAME_MS = 80

    def __init__(self):
        super().__init__()
        self.set_size_request(90, 24)
        self._phase = 0.0
        self._running = False
        self._timer_id = None
        self.set_draw_func(self._on_draw)
        self.connect("destroy", lambda *_: self.set_active(False))

    def set_active(self, active: bool):
        if active == self._running:
            return
        self._running = active
        if active and self._timer_id is None:
            self._timer_id = GLib.timeout_add(self.FRAME_MS, self._tick)
        elif not active and self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None
            self._phase = 0.0
            self.queue_draw()

    def _tick(self) -> bool:
        self._phase += 0.35
        self.queue_draw()
        return self._running

    def _on_draw(self, area, cr, width, height, user_data=None):
        colors = palette.load()
        top_r, top_g, top_b = _hex_to_rgb_floats(colors.get('ROOT', '#f6b83c'))
        tail_r, tail_g, tail_b = _hex_to_rgb_floats(colors.get('SEVENTH', '#c8723c'))

        n = self.N_BEADS
        gap = 3.0
        bead_w = (width - gap * (n - 1)) / n

        for i in range(n):
            if self._running:
                level = 0.35 + 0.65 * abs(math.sin(self._phase + i * 0.8))
            else:
                level = 0.12
            bead_h = max(3.0, height * level)
            x = i * (bead_w + gap)
            y = height - bead_h

            t = i / (n - 1) if n > 1 else 0.0
            r = top_r + (tail_r - top_r) * t
            g = top_g + (tail_g - top_g) * t
            b = top_b + (tail_b - top_b) * t
            cr.set_source_rgba(r, g, b, 1.0)
            self._rounded_bar(cr, x, y, bead_w, bead_h)
            cr.fill()

    @staticmethod
    def _rounded_bar(cr, x, y, w, h):
        r = min(w / 2.0, h / 2.0, 4.0)
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()
