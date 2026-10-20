"""A one-line label that scrolls sideways when its text is wider than the space."""

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from .scrollmath import scroll_offset  # noqa: E402


class ScrollLabel(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__()
        # NEVER would clamp the adjustment; EXTERNAL scrolls without a bar
        self.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.NEVER)
        self.set_hexpand(True)
        self.set_propagate_natural_height(True)
        self.label = Gtk.Label(xalign=0.0)
        self.set_child(self.label)
        self._tick_id = 0
        self._t0 = None
        self.connect("map", self._on_map)
        self.connect("unmap", self._on_unmap)

    def set_text(self, text: str) -> None:
        # callers re-set the same text on every daemon poll; don't restart the marquee
        if text == self.label.get_text():
            return
        self.label.set_text(text)
        self._t0 = None
        self.get_hadjustment().set_value(0)

    def get_text(self) -> str:
        return self.label.get_text()

    def _on_map(self, *_):
        if not self._tick_id:
            self._tick_id = self.add_tick_callback(self._tick)

    def _on_unmap(self, *_):
        if self._tick_id:
            self.remove_tick_callback(self._tick_id)
            self._tick_id = 0

    def _tick(self, _widget, clock):
        adj = self.get_hadjustment()
        overflow = adj.get_upper() - adj.get_page_size()
        if overflow <= 0:
            return True
        now = clock.get_frame_time() / 1e6
        if self._t0 is None:
            self._t0 = now
        adj.set_value(scroll_offset(now - self._t0, overflow))
        return True
