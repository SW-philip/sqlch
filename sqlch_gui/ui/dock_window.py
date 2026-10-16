"""One docked Library/Discover window.

The layer-shell surface is a transparent output-sized overlay that never
moves; the card is placed inside it with Gtk.Fixed and only the card's rect
is input-sensitive. Dragging a surface by changing its margins feeds back
into the gesture's own coordinates and runs away under compositor lag, so
the drag gesture lives on the stationary Fixed and its offsets are absolute."""

import cairo
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gtk, Gtk4LayerShell

from .dock import Rect

PANEL_WIDTH = 320
FADE_MS = 160


class DockedWindow(Gtk.Window):
    def __init__(self, manager, name: str, title: str, panel: Gtk.Widget):
        super().__init__()
        self.manager = manager
        self.name = name
        self.rect = Rect(0, 0, PANEL_WIDTH, 0)
        self._fade_id = None
        self._drag_start = self.rect

        self.set_title(f"sqlch-gui {name}")
        self.set_decorated(False)
        self.add_css_class("dock-overlay")
        Gtk4LayerShell.init_for_window(self)
        Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.TOP)
        Gtk4LayerShell.set_namespace(self, f"sqlch-gui-{name}")
        for edge in (Gtk4LayerShell.Edge.TOP, Gtk4LayerShell.Edge.LEFT,
                     Gtk4LayerShell.Edge.RIGHT, Gtk4LayerShell.Edge.BOTTOM):
            Gtk4LayerShell.set_anchor(self, edge, True)
        # 0 (not -1): laid out inside other panels' exclusive zones, the same
        # origin Now Playing's margins are measured from.
        Gtk4LayerShell.set_exclusive_zone(self, 0)
        Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.ON_DEMAND)

        self.fixed = Gtk.Fixed()
        self.set_child(self.fixed)

        self.card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.card.add_css_class("popup-window")
        self.fixed.put(self.card, 0, 0)

        self.handle = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.handle.add_css_class("dock-handle")
        lbl = Gtk.Label(label=title, xalign=0.0, hexpand=True)
        lbl.add_css_class("dock-title")
        self.close_btn = Gtk.Button(icon_name="window-close-symbolic")
        self.close_btn.add_css_class("dock-close")
        self.close_btn.connect("clicked", lambda _b: manager.toggle(name))
        self.handle.append(lbl)
        self.handle.append(self.close_btn)
        self.card.append(self.handle)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_child(panel)
        self.card.append(scroll)

        drag = Gtk.GestureDrag.new()
        drag.connect("drag-begin", self._drag_begin)
        drag.connect("drag-update", self._drag_update)
        drag.connect("drag-end", self._drag_end)
        self.fixed.add_controller(drag)
        self.handle.set_cursor_from_name("grab")

        self.connect("map", lambda _w: self._apply_input_region())

    # --- placement ---

    def place(self, rect: Rect):
        self.rect = rect
        self.fixed.move(self.card, rect.x, rect.y)
        self.card.set_size_request(rect.w, rect.h)
        self._apply_input_region()

    def _apply_input_region(self):
        surface = self.get_surface()
        if surface is None or self.rect.w <= 0 or self.rect.h <= 0:
            return
        r = self.rect
        surface.set_input_region(
            cairo.Region(cairo.RectangleInt(r.x, r.y, r.w, r.h)))

    # --- fade (sequential: a window is fully out before another fades in) ---

    def _fade(self, target: float, on_done=None):
        if self._fade_id:
            self.remove_tick_callback(self._fade_id)
        start, t0 = self.get_opacity(), None

        def tick(_w, clock):
            nonlocal t0
            now = clock.get_frame_time()
            t0 = now if t0 is None else t0
            k = min(1.0, (now - t0) / (FADE_MS * 1000))
            self.set_opacity(start + (target - start) * k)
            if k >= 1.0:
                self._fade_id = None
                if on_done:
                    on_done()
                return False
            return True

        self._fade_id = self.add_tick_callback(tick)

    def fade_in(self):
        if not self.get_visible():
            self.set_opacity(0.0)
        self.set_visible(True)
        self._fade(1.0)

    def fade_out(self, on_done=None):
        def done():
            self.set_visible(False)
            if on_done:
                on_done()
        self._fade(0.0, done)

    # --- drag ---

    def _in_widget(self, widget, x, y):
        ok, b = widget.compute_bounds(self.fixed)
        return ok and b.get_x() <= x <= b.get_x() + b.get_width() \
            and b.get_y() <= y <= b.get_y() + b.get_height()

    def _drag_begin(self, gesture, x, y):
        if not self._in_widget(self.handle, x, y) or self._in_widget(self.close_btn, x, y):
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return
        self._drag_start = self.rect

    def _drag_to(self, ox, oy):
        self.place(self.manager.clamp(
            self._drag_start.moved(round(ox), round(oy)), self))

    def _drag_update(self, _g, ox, oy):
        self._drag_to(ox, oy)

    def _drag_end(self, _g, ox, oy):
        self._drag_to(ox, oy)
        if self.rect == self._drag_start:
            return
        self.manager.commit_drag(self.name, self.rect)
