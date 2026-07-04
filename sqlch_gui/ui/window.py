"""Core structural surface frame container initialized via Wayland Layer Shell bindings."""

import threading
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gtk, GLib, Gio, Gtk4LayerShell

from .. import daemon, palette
from .common import load_custom_css
from .now_playing import NowPlayingPanel
from .station_list import StationListPanel
from .discover import DiscoverPanel

class SqlchPopupWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("sqlch-gui")
        # Width sized so track/album lines usually fit un-ellipsized; the
        # sidebar is content-sized, so extra width all goes to the stack.
        self.set_default_size(450, 430)
        
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

        # Top surface: sidebar and stack are quilted side by side — patches
        # butt against each other at a seam, nothing overlaps or floats.
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        main_box.add_css_class("popup-window")
        self.set_child(main_box)

        # Navigation column sidebar patch
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        sidebar.add_css_class("sidebar")
        sidebar.set_valign(Gtk.Align.START)
        main_box.append(sidebar)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(200)
        self.stack.set_hexpand(True)
        main_box.append(self.stack)

        # Instantiating presentation views
        self.now_playing = NowPlayingPanel(self)
        self.station_list = StationListPanel(self)
        self.discover = DiscoverPanel(self)

        self.stack.add_named(self.now_playing, "now_playing")
        self.stack.add_named(self.station_list, "station_list")
        self.stack.add_named(self.discover, "discover")

        # Sidebar control button array map
        self.nav_buttons = {}
        for name, icon, tooltip in [
            ("now_playing", "media-playlist-consecutive-symbolic", "Now Playing"),
            ("station_list", "view-list-symbolic", "Station Library"),
            ("discover", "folder-saved-search-symbolic", "Discover Stations")
        ]:
            btn = Gtk.Button(icon_name=icon)
            btn.add_css_class("nav-btn")
            btn.set_tooltip_text(tooltip)
            btn.connect("clicked", lambda b, n=name: self.switch_panel(n))
            sidebar.append(btn)
            self.nav_buttons[name] = btn

        self.switch_panel("now_playing")

        # Runtime environment loops initialization parameters
        self._bt_active = False
        self._keep_running = True
        
        # Fire monitoring loop threads
        threading.Thread(target=self._daemon_monitor_loop, daemon=True).start()
        threading.Thread(target=self._bluetooth_monitor_loop, daemon=True).start()

        # Re-skin live when the system theme rewrites palette.sh
        self._pal_reload_pending = False
        pal_file = Gio.File.new_for_path(palette.palette_path())
        self._pal_monitor = pal_file.monitor_file(Gio.FileMonitorFlags.NONE, None)
        self._pal_monitor.connect("changed", self._on_palette_changed)

        # Connect focus destruction patterns
        self.connect("close-request", self.on_close_request)

    def switch_panel(self, name: str):
        self.stack.set_visible_child_name(name)
        for k, btn in self.nav_buttons.items():
            if k == name:
                btn.add_css_class("active")
            else:
                btn.remove_css_class("active")
        if name == "station_list":
            self.station_list.on_shown()

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
        return False

    def on_close_request(self, win):
        self._keep_running = False

    def _daemon_monitor_loop(self):
        import time
        from .. import metadata
        while self._keep_running:
            resp = daemon.send({"cmd": "status"})
            icy = metadata.get_icy_track()
            vol, muted = daemon.get_vol_state()
            bitrate = daemon.get_stream_bitrate()
            channels = daemon.get_stream_channels()
            fmt = daemon.get_stream_format()

            GLib.idle_add(
                self._apply_daemon_state,
                resp, icy, vol, muted, bitrate, channels, fmt
            )
            time.sleep(1.0)

    def _apply_daemon_state(self, resp, icy, vol, muted, bitrate, channels, fmt) -> bool:
        if not self._keep_running:
            return False
        self.now_playing.update(resp, icy=icy)
        playing = bool(resp and resp.get("ok") and resp.get("current"))
        recording = resp.get("recording") if resp else None
        self.now_playing.update_indicators(
            bitrate, vol, muted, self._bt_active, playing, channels,
            recording=recording, fmt=fmt,
        )
        artist, title = self.now_playing.get_current_track()
        self.station_list.set_active(self.now_playing.get_current_id(), artist, title)
        return False

    def _bluetooth_monitor_loop(self):
        import time
        while self._keep_running:
            active = daemon.get_bt_active()
            GLib.idle_add(self._apply_bluetooth_state, active)
            time.sleep(4.0)

    def _apply_bluetooth_state(self, active: bool) -> bool:
        self._bt_active = active
        return False