"""Core structural surface frame container initialized via Wayland Layer Shell bindings."""

import threading
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gtk, GLib, Gtk4LayerShell

from .. import daemon
from .common import load_custom_css
from .now_playing import NowPlayingPanel
from .station_list import StationListPanel
from .discover import DiscoverPanel

class SqlchPopupWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("sqlch-gui")
        self.set_default_size(440, 500)
        
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
        Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.NONE)

        # Top box structure setup
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        main_box.add_css_class("popup-window")
        self.set_child(main_box)

        # Navigation column sidebar container
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        sidebar.add_css_class("sidebar")
        main_box.append(sidebar)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(200)
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

        # Connect focus destruction patterns
        self.connect("close-request", self.on_close_request)

    def switch_panel(self, name: str):
        self.stack.set_visible_child_name(name)
        for k, btn in self.nav_buttons.items():
            if k == name:
                btn.add_css_class("active")
            else:
                btn.remove_css_class("active")

    def trigger_library_refresh(self):
        self.station_list.refresh()

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
            
            GLib.idle_add(
                self._apply_daemon_state, 
                resp, icy, vol, muted, bitrate, channels
            )
            time.sleep(1.0)

    def _apply_daemon_state(self, resp, icy, vol, muted, bitrate, channels) -> bool:
        if not self._keep_running:
            return False
        self.now_playing.update(resp, icy=icy)
        playing = bool(resp and resp.get("ok") and resp.get("current"))
        self.now_playing.update_indicators(bitrate, vol, muted, self._bt_active, playing, channels)
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