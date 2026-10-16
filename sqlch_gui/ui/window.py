"""Core structural surface frame container initialized via Wayland Layer Shell bindings."""

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


class SqlchPopupWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("sqlch-gui")
        self._missed_polls = 0
        # Now Playing is the permanent surface; Library/Discover are docked
        # windows owned by DockManager.
        self.set_default_size(290, -1)

        # Inject theme constants
        load_custom_css()

        # Initialize layer-shell layer
        Gtk4LayerShell.init_for_window(self)
        Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.TOP)
        Gtk4LayerShell.set_namespace(self, "sqlch-gui")
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.TOP, True)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.RIGHT, True)
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.TOP, 48)
        Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.RIGHT, 12)
        Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.ON_DEMAND)

        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        main_box.add_css_class("popup-window")
        self.set_child(main_box)

        self.now_playing = NowPlayingPanel(self)
        self.station_list = StationListPanel(self)
        self.discover = DiscoverPanel(self)
        main_box.append(self.now_playing)

        self.docks = DockManager(
            self,
            panels={"library": self.station_list, "discover": self.discover},
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