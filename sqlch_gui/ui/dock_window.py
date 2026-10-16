"""One docked Library/Discover window: a layer-shell surface anchored
TOP+LEFT and positioned purely by margins, with a drag handle that snaps."""

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
        self._drag_off = (0.0, 0.0)
        self._drag_tick = None
        self._drag_start = self.rect

        self.set_title(f"sqlch-gui {name}")
        self.set_decorated(False)
        Gtk4LayerShell.init_for_window(self)
        Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.TOP)
        Gtk4LayerShell.set_namespace(self, f"sqlch-gui-{name}")
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.TOP, True)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.LEFT, True)
        Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.ON_DEMAND)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.add_css_class("popup-window")
        self.set_child(root)

        handle = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        handle.add_css_class("dock-handle")
        lbl = Gtk.Label(label=title, xalign=0.0, hexpand=True)
        lbl.add_css_class("dock-title")
        close = Gtk.Button(icon_name="window-close-symbolic")
        close.add_css_class("dock-close")
        close.connect("clicked", lambda _b: manager.toggle(name))
        handle.append(lbl)
        handle.append(close)
        root.append(handle)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_child(panel)
        root.append(scroll)

        drag = Gtk.GestureDrag.new()
        drag.connect("drag-begin", self._drag_begin)
        drag.connect("drag-update", self._drag_update)
        drag.connect("drag-end", self._drag_end)
        handle.add_controller(drag)
        handle.set_cursor_from_name("grab")

    # --- placement ---

    def place(self, rect: Rect):
        self.rect = rect
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.LEFT, rect.x)
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.TOP, rect.y)
        self.set_default_size(rect.w, rect.h)

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
    # The surface moves under the pointer, so GestureDrag offsets are
    # relative to the *current* surface position: new = applied + offset
    # re-derives the pointer's total travel. Commits are coalesced to one
    # per frame so each margin change lands before the next motion event.

    def _drag_begin(self, _g, _x, _y):
        self._drag_off = (0.0, 0.0)
        self._drag_start = self.rect
        self._drag_tick = self.add_tick_callback(self._drag_frame)

    def _drag_update(self, _g, ox, oy):
        self._drag_off = (ox, oy)

    def _apply_drag_offset(self):
        ox, oy = self._drag_off
        if ox or oy:
            self._drag_off = (0.0, 0.0)
            self.place(self.manager.clamp(self.rect.moved(round(ox), round(oy))))

    def _drag_frame(self, _w, _clock):
        self._apply_drag_offset()
        return True

    def _drag_end(self, _g, _ox, _oy):
        if self._drag_tick:
            self.remove_tick_callback(self._drag_tick)
            self._drag_tick = None
        self._apply_drag_offset()
        if self.rect == self._drag_start:
            return
        self.manager.commit_drag(self.name, self.rect)
