"""A draggable card inside a transparent output-sized layer-shell overlay.

The surface never moves; the card is placed inside it with Gtk.Fixed and only
the card's rect is input-sensitive. Dragging a surface by changing its
margins feeds back into the gesture's own coordinates and runs away under
compositor lag, so the drag gesture lives on the stationary Fixed and its
offsets are absolute."""

from typing import Callable

import cairo
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gdk, GLib, Gtk

from .dock import Rect
from .trace import trace

FLASH_MS = 180


def grip() -> Gtk.Label:
    """Subtle drag-handle glyph; styled by .dock-grip."""
    lbl = Gtk.Label(label="⋮⋮")
    lbl.add_css_class("dock-grip")
    return lbl


class OverlayCard:
    def __init__(self, window: Gtk.Window, card: Gtk.Widget,
                 handle: Gtk.Widget | None,
                 on_drag: Callable[[Rect], Rect | None] | None = None,
                 on_drop: Callable[[Rect], None] | None = None,
                 on_drag_start: Callable[[], None] | None = None,
                 exclude: tuple[Gtk.Widget, ...] = (),
                 sized: bool = True):
        self.window = window
        self.card = card
        self.handle = handle
        self.rect = Rect(0, 0, 0, 0)
        self._on_drag = on_drag
        self._on_drop = on_drop
        self._on_drag_start = on_drag_start
        self._exclude = exclude
        # False: the card keeps its natural size; place() only moves it.
        self._sized = sized
        self._drag_start = self.rect
        # drag-update/end can reach us for a press we DENIED, with
        # _drag_start left over from the last drag; only an accepted drag
        # may move the card.
        self._dragging = False
        self._flash_id = 0
        self._name = window.get_title()

        self.fixed = Gtk.Fixed()
        window.set_child(self.fixed)
        self.fixed.put(card, 0, 0)

        if handle is not None:
            drag = Gtk.GestureDrag.new()
            drag.set_button(Gdk.BUTTON_PRIMARY)
            drag.connect("drag-begin", self._drag_begin)
            drag.connect("drag-update", self._drag_update)
            drag.connect("drag-end", self._drag_end)
            drag.connect("cancel", self._drag_cancel)
            self.fixed.add_controller(drag)
            handle.set_cursor_from_name("grab")

        window.connect("map", lambda _w: self._apply_input_region())

    # --- placement ---

    def place(self, rect: Rect):
        trace("%s place %s -> %s", self._name, self.rect, rect, caller=2)
        self.rect = rect
        self.fixed.move(self.card, rect.x, rect.y)
        if self._sized:
            self.card.set_size_request(rect.w, rect.h)
        self._apply_input_region()

    def _apply_input_region(self):
        surface = self.window.get_surface()
        if surface is None:
            return
        r = self.rect
        # An unplaced overlay must stay click-through, never full-output.
        if r.w <= 0 or r.h <= 0:
            trace("%s input region EMPTY", self._name)
            surface.set_input_region(cairo.Region())
        else:
            trace("%s input region %s", self._name, r)
            surface.set_input_region(
                cairo.Region(cairo.RectangleInt(r.x, r.y, r.w, r.h)))

    # --- flash ---

    def flash(self):
        trace("%s flash", self._name)
        if self._flash_id:
            GLib.source_remove(self._flash_id)
        self.card.add_css_class("dock-flash")
        self._flash_id = GLib.timeout_add(FLASH_MS, self._end_flash)

    def _end_flash(self):
        self._flash_id = 0
        self.card.remove_css_class("dock-flash")
        return GLib.SOURCE_REMOVE

    # --- drag ---

    def _in_widget(self, widget, x, y):
        ok, b = widget.compute_bounds(self.fixed)
        return ok and b.get_x() <= x <= b.get_x() + b.get_width() \
            and b.get_y() <= y <= b.get_y() + b.get_height()

    def _drag_begin(self, gesture, x, y):
        if not self._in_widget(self.handle, x, y):
            trace("%s drag-begin %.1f,%.1f DENIED-not-in-handle", self._name, x, y)
            self._dragging = False
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return
        if any(self._in_widget(w, x, y) for w in self._exclude):
            trace("%s drag-begin %.1f,%.1f DENIED-excluded", self._name, x, y)
            self._dragging = False
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return
        trace("%s drag-begin %.1f,%.1f CLAIMED", self._name, x, y)
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self._accept_drag()

    def _accept_drag(self):
        self._drag_start = self.rect
        self._dragging = True
        if self._on_drag_start:
            self._on_drag_start()

    def _drag_cancel(self, _g, _seq):
        trace("%s gesture cancel dragging=%s rect %s", self._name, self._dragging, self.rect)
        self._dragging = False

    def _drag_to(self, ox, oy):
        candidate = self._drag_start.moved(round(ox), round(oy))
        shown = self._on_drag(candidate) if self._on_drag else None
        self.place(candidate if shown is None else shown)

    def _drag_update(self, _g, ox, oy):
        if not self._dragging:
            trace("%s drag-update IGNORED (no accepted drag)", self._name)
            return
        trace("%s drag-update %.1f,%.1f", self._name, ox, oy)
        self._drag_to(ox, oy)

    def _drag_end(self, _g, ox, oy):
        if not self._dragging:
            trace("%s drag-end IGNORED (no accepted drag)", self._name)
            return
        self._dragging = False
        before = self.rect
        self._drag_to(ox, oy)
        drop = self.rect != self._drag_start and self._on_drop is not None
        trace("%s drag-end %.1f,%.1f rect %s -> %s drag_start %s on_drop=%s",
              self._name, ox, oy, before, self.rect, self._drag_start, drop)
        if self.rect == self._drag_start:
            return
        if self._on_drop:
            self._on_drop(self.rect)
