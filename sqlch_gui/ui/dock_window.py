"""One docked Library/Discover window: a transparent output-sized overlay
holding an OverlayCard (see overlay_card.py for why the surface never moves)."""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gtk, Gtk4LayerShell

from .dock import Rect
from .overlay_card import OverlayCard, grip

PANEL_WIDTH = 320
FADE_MS = 160


class DockedWindow(Gtk.Window):
    def __init__(self, manager, name: str, title: str, panel: Gtk.Widget):
        super().__init__()
        self.manager = manager
        self.name = name
        self._fade_id = None

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

        self.card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.card.add_css_class("popup-window")

        self.handle = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.handle.add_css_class("dock-handle")
        lbl = Gtk.Label(label=title, xalign=0.0, hexpand=True)
        lbl.add_css_class("dock-title")
        self.close_btn = Gtk.Button(icon_name="window-close-symbolic")
        self.close_btn.add_css_class("dock-close")
        self.close_btn.connect("clicked", lambda _b: manager.toggle(name))
        self.handle.append(lbl)
        self.handle.append(grip())
        self.handle.append(self.close_btn)
        self.card.append(self.handle)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_child(panel)
        self.card.append(scroll)

        self.overlay = OverlayCard(
            self, self.card, self.handle,
            on_drag=lambda r: manager.magnet_for(name, r),
            on_drop=lambda r: manager.commit_drag(name, r),
            on_drag_start=lambda: manager.drag_started(name),
            exclude=(self.close_btn,))
        self.overlay.rect = Rect(0, 0, PANEL_WIDTH, 0)

    @property
    def rect(self) -> Rect:
        return self.overlay.rect

    def place(self, rect: Rect):
        self.overlay.place(rect)

    def flash(self):
        self.overlay.flash()

    # --- fade (sequential: a window is fully out before another fades in) ---

    def _fade(self, target: float, on_done=None):
        if self._fade_id:
            self.remove_tick_callback(self._fade_id)
        if target == 0.0 and not self.get_mapped():
            # No frame clock ticks before first map, so on_done would never run.
            self._fade_id = None
            self.set_opacity(target)
            if on_done:
                on_done()
            return
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
