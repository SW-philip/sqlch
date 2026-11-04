"""In-window toast: a label overlaid on the cover art, one message at a time."""

from collections import deque

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import GLib, Gtk

SHOW_MS = 6000


class Toast(Gtk.Label):
    def __init__(self, schedule=GLib.timeout_add):
        super().__init__()
        self.add_css_class("toast")
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.END)
        self.set_ellipsize(3)
        self.set_can_target(False)  # never swallow clicks meant for the cover
        self.set_visible(False)
        self._schedule = schedule
        self._queue: deque[str] = deque()
        self._showing = False

    def push(self, text: str) -> None:
        self._queue.append(text)
        if not self._showing:
            self._next()

    def _next(self) -> bool:
        if not self._queue:
            self._showing = False
            self.set_visible(False)
            return False
        self._showing = True
        self.set_text(self._queue.popleft())
        self.set_visible(True)
        self._schedule(SHOW_MS, self._next)
        return False
