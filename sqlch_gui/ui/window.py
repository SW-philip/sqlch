"""Now Playing: a transparent output-sized layer-shell overlay whose card is
dragged by the nameplate strip (see overlay_card.py)."""

import threading
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gtk, GLib, Gio, Gtk4LayerShell

from .. import daemon, palette
from .common import load_custom_css
from .header import next_connected
from .now_playing import NowPlayingPanel
from .station_list import StationListPanel
from .discover import DiscoverPanel
from .dock_manager import DockManager
from .overlay_card import OverlayCard
from .source_pane import SourcePane
from sqlch.sources import REGISTRY as SOURCES, safe_available


class _SizeWatch(Gtk.Widget):
    """Single-child passthrough that reports allocation changes. Gtk.Fixed
    sizes the card from its content and nothing else signals that, and a
    Gtk.Box's size_allocate vfunc is bypassed by its layout manager."""

    def __init__(self, child: Gtk.Widget, on_resize):
        super().__init__()
        self._child = child
        self._on_resize = on_resize
        self._size = (0, 0)
        child.set_parent(self)

    def do_measure(self, orientation, for_size):
        return self._child.measure(orientation, for_size)

    def do_size_allocate(self, width, height, baseline):
        self._child.allocate(width, height, baseline, None)
        if (width, height) != self._size:
            self._size = (width, height)
            # Never re-place the card from inside an allocation.
            GLib.idle_add(self._on_resize)

    def do_dispose(self):
        if self._child is not None:
            self._child.unparent()
            self._child = None
        Gtk.Widget.do_dispose(self)


class SqlchPopupWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("sqlch-gui")
        self.set_decorated(False)
        self.add_css_class("dock-overlay")
        self._missed_polls = 0

        # Inject theme constants
        load_custom_css()

        Gtk4LayerShell.init_for_window(self)
        Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.TOP)
        Gtk4LayerShell.set_namespace(self, "sqlch-gui")
        for edge in (Gtk4LayerShell.Edge.TOP, Gtk4LayerShell.Edge.LEFT,
                     Gtk4LayerShell.Edge.RIGHT, Gtk4LayerShell.Edge.BOTTOM):
            Gtk4LayerShell.set_anchor(self, edge, True)
        # Same exclusive zone as the docked overlays, so all of them share
        # one coordinate space.
        Gtk4LayerShell.set_exclusive_zone(self, 0)
        Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.ON_DEMAND)

        self.now_playing = NowPlayingPanel(self)
        self.station_list = StationListPanel(self)
        self.discover = DiscoverPanel(self)

        self.card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.card.add_css_class("popup-window")
        self.card.append(_SizeWatch(self.now_playing, self._card_resized))
        # Hidden until DockManager first places it; the Fixed would
        # otherwise paint it at the overlay's top-left corner.
        self.card.set_opacity(0.0)

        self.overlay = OverlayCard(
            self, self.card, self.now_playing.header.nameplate_row,
            on_drag=lambda r: self.docks.np_drag(r),
            on_drop=lambda r: self.docks.np_drop(r),
            on_drag_start=lambda: self.docks.np_drag_started(),
            exclude=(self.now_playing.nav_column,),
            sized=False)

        panels = {"library": self.station_list, "discover": self.discover}
        titles = {}
        for name, src in SOURCES.items():
            panels[name] = lambda s=src: SourcePane(self, s)
            titles[name] = src.TITLE
        self.now_playing.nav_column.set_sources([
            {"name": n, "label": s.LABEL, "available": safe_available(s), "hint": s.HINT}
            for n, s in SOURCES.items()])

        self.docks = DockManager(
            self, panels=panels, titles=titles,
            nav=self.now_playing.nav_column,
            on_shown={"library": self.station_list.on_shown, "discover": lambda: None},
            on_hidden={"library": self.station_list.abort_probes, "discover": lambda: None},
        )
        self.now_playing.connect("nav-toggled", lambda _p, name: self.docks.toggle(name))
        self.connect("map", lambda _w: GLib.idle_add(self.docks.show_saved))

        # Runtime environment loops initialization parameters
        self._keep_running = True

        # Fire monitoring loop threads
        threading.Thread(target=self._daemon_monitor_loop, daemon=True).start()

        # Re-skin live when the system theme rewrites palette.sh
        self._pal_reload_pending = False
        pal_file = Gio.File.new_for_path(palette.palette_path())
        self._pal_monitor = pal_file.monitor_file(Gio.FileMonitorFlags.NONE, None)
        self._pal_monitor.connect("changed", self._on_palette_changed)

        # Connect focus destruction patterns
        self.connect("close-request", self.on_close_request)

    # --- card geometry (positioning policy lives in DockManager) ---

    def area_size(self):
        w, h = self.get_width(), self.get_height()
        return (w, h) if w > 0 and h > 0 else None

    def card_size(self):
        # Gtk.Fixed allocates children at their minimum size.
        minimum, _natural = self.card.get_preferred_size()
        if minimum.width <= 0 or minimum.height <= 0:
            return None
        return minimum.width, minimum.height

    def place_card(self, rect):
        self.overlay.place(rect)
        self.card.set_opacity(1.0)

    def _card_resized(self):
        self.docks.np_changed()
        return False

    def trigger_library_refresh(self):
        self.station_list.refresh()

    def _on_palette_changed(self, monitor, file, other_file, event_type):
        # Theme switchers rewrite/rename the file in bursts; debounce to one reload
        if self._pal_reload_pending:
            return
        self._pal_reload_pending = True
        GLib.timeout_add(300, self._reload_palette)

    def _reload_palette(self) -> bool:
        self._pal_reload_pending = False
        load_custom_css()
        self.station_list.refresh()  # group headers bake palette hex into markup
        self.now_playing.vol_meter.queue_draw()  # VU meter re-reads palette on next draw
        return False

    def on_close_request(self, win):
        self._keep_running = False
        self.docks.shutdown()

    def _daemon_monitor_loop(self):
        import time
        from .. import metadata
        while self._keep_running:
            resp = daemon.send({"cmd": "status"})
            icy = metadata.get_icy_track()
            vol, muted = daemon.get_vol_state()
            bitrate = daemon.get_stream_bitrate()
            fmt = daemon.get_stream_format()
            buffer = daemon.get_stream_buffer()

            GLib.idle_add(
                self._apply_daemon_state,
                resp, icy, vol, muted, bitrate, fmt, buffer
            )
            time.sleep(1.0)

    def _apply_daemon_state(self, resp, icy, vol, muted, bitrate, fmt, buffer) -> bool:
        if not self._keep_running:
            return False
        self._missed_polls, connected = next_connected(
            self._missed_polls, resp is not None)
        self.now_playing.set_connected(connected)
        self.now_playing.update(resp, icy=icy)
        playing = bool(resp and resp.get("ok") and resp.get("current"))
        recording = resp.get("recording") if resp else None
        self.now_playing.update_indicators(
            bitrate, vol, muted, playing,
            recording=recording, fmt=fmt, buffer=buffer,
        )
        artist, title = self.now_playing.get_current_track()
        self.station_list.set_active(self.now_playing.get_current_id(), artist, title)
        return False