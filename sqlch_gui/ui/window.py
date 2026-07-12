"""Core structural surface frame container initialized via Wayland Layer Shell bindings."""

import threading
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gtk, GLib, Gio, Gtk4LayerShell

from .. import daemon, palette
from .banner import TornSeparator
from .common import load_custom_css
from .now_playing import NowPlayingPanel
from .station_list import StationListPanel
from .discover import DiscoverPanel

MAX_DRAWER_HEIGHT = 320        # ceiling; the effective max also fits the monitor
DRAWER_BOTTOM_GAP = 12         # breathing room kept above the screen's bottom edge
DRAWER_OPEN_THRESHOLD = 0.35   # fraction of max height that commits an open
DRAWER_FLING_VELOCITY = 600.0  # px/s at release that overrides position
DRAWER_CLICK_SLOP = 8.0        # px of travel under which a "drag" is just a click
DRAWER_SPRING_OMEGA = 20.0     # rad/s
DRAWER_SPRING_ZETA = 0.78      # underdamped: slight fabric-settle overshoot

class SqlchPopupWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("sqlch-gui")
        # Now Playing is permanently visible; Library/Discover live in a
        # drawer beneath the torn seam. Height is content-driven so the
        # layer-shell surface hugs the card when closed and grows as the
        # drawer is pulled open.
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

        # Top surface: Now Playing stays permanently visible; Library/
        # Discover live in a drag-open drawer stacked below the torn seam.
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        main_box.add_css_class("popup-window")
        self.set_child(main_box)

        # Instantiating presentation views
        self.now_playing = NowPlayingPanel(self)
        self.station_list = StationListPanel(self)
        self.discover = DiscoverPanel(self)
        main_box.append(self.now_playing)

        # The torn seam doubles as the drawer's drag handle
        self.seam = TornSeparator()
        seam_drag = Gtk.GestureDrag.new()
        seam_drag.connect("drag-begin", self._on_seam_drag_begin)
        seam_drag.connect("drag-update", self._on_seam_drag_update)
        seam_drag.connect("drag-end", self._on_seam_drag_end)
        self.seam.add_controller(seam_drag)
        main_box.append(self.seam)

        # Drawer region: a clipping ScrolledWindow whose height-request is
        # the drawer position (0 = closed .. MAX_DRAWER_HEIGHT = open),
        # driven by seam drags and the spring snap. The "mini" page is the
        # parked empty state so the panels unmap (and stop probing) while
        # the drawer is shut.
        self.dropdown_stack = Gtk.Stack()
        self.dropdown_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.dropdown_stack.set_transition_duration(150)
        self.dropdown_stack.add_named(Gtk.Box(), "mini")
        self.dropdown_stack.add_named(self.station_list, "library")
        self.dropdown_stack.add_named(self.discover, "discover")
        self.dropdown_stack.set_visible_child_name("mini")

        self.dropdown_scroll = Gtk.ScrolledWindow()
        self.dropdown_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.dropdown_scroll.set_size_request(-1, 0)
        self.dropdown_scroll.set_child(self.dropdown_stack)
        main_box.append(self.dropdown_scroll)

        self._drawer_pos = 0.0
        self._drawer_target = 0.0
        self._drawer_max = float(MAX_DRAWER_HEIGHT)
        self._drawer_tick_id = None
        self._drawer_panel = "library"  # what a bare seam-drag reveals
        self._drag_start_h = 0.0
        self._drag_vel = 0.0
        self._drag_pending = 0.0
        self._drag_last = (0, 0.0)

        self.now_playing.connect("nav-selected", self.on_nav_selected)

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

    def on_nav_selected(self, panel, name: str):
        if name == "mini":
            self.station_list.abort_probes()
            self._animate_drawer_to(0.0)
        else:
            self._drawer_panel = name
            self.dropdown_stack.set_visible_child_name(name)
            self._animate_drawer_to(self._compute_drawer_max())
            if name == "library":
                self.station_list.on_shown()

    # --- Drawer: seam drag + spring snap ---

    def _compute_drawer_max(self) -> float:
        """MAX_DRAWER_HEIGHT capped so the fully open window still fits on
        the monitor below the layer-shell top margin. Whenever a fresh
        measurement can't be trusted -- surface/monitor unresolved, window
        not yet allocated, or an animation in flight (allocation lags
        _drawer_pos by a frame) -- reuse the last good value instead of
        ever falling back to the bare ceiling."""
        if self._drawer_tick_id:
            return self._drawer_max
        surface = self.get_surface()
        monitor = self.get_display().get_monitor_at_surface(surface) if surface else None
        if monitor is None or self.get_height() <= 0:
            return self._drawer_max
        # Everything that isn't drawer: current window height minus the
        # drawer's current share of it
        overhead = self.get_height() - round(self._drawer_pos)
        top_margin = Gtk4LayerShell.get_margin(self, Gtk4LayerShell.Edge.TOP)
        avail = monitor.get_geometry().height - top_margin - overhead - DRAWER_BOTTOM_GAP
        self._drawer_max = float(max(0, min(MAX_DRAWER_HEIGHT, avail)))
        return self._drawer_max

    def _set_drawer_pos(self, pos: float):
        self._drawer_pos = pos
        self.dropdown_scroll.set_size_request(-1, max(0, round(pos)))

    def _stop_drawer_anim(self):
        if self._drawer_tick_id:
            self.dropdown_scroll.remove_tick_callback(self._drawer_tick_id)
            self._drawer_tick_id = None

    def _on_seam_drag_begin(self, gesture, start_x, start_y):
        self._stop_drawer_anim()  # grab mid-snap steals the drawer back
        self._compute_drawer_max()
        self._drag_start_h = self._drawer_pos
        self._drag_vel = 0.0
        self._drag_pending = self._drawer_pos
        self._drag_last = (GLib.get_monotonic_time(), self._drawer_pos)
        self.seam.set_grabbed(True)
        if self._drawer_pos == 0.0:
            self.dropdown_stack.set_visible_child_name(self._drawer_panel)
        # Coalesce drag positions onto the frame clock: pointers report at
        # up to 1000Hz, and relayouting the window per motion event (rather
        # than once per frame) is what reads as drag lag
        self._drawer_tick_id = self.dropdown_scroll.add_tick_callback(self._drag_frame)

    def _drag_frame(self, widget, frame_clock):
        if self._drag_pending != self._drawer_pos:
            self._set_drawer_pos(self._drag_pending)
        return GLib.SOURCE_CONTINUE

    def _on_seam_drag_update(self, gesture, offset_x, offset_y):
        pos = max(0.0, min(self._drawer_max, self._drag_start_h + offset_y))
        now = GLib.get_monotonic_time()
        then, last_pos = self._drag_last
        dt = (now - then) / 1_000_000
        if dt > 0.008:
            # Exponentially smoothed release velocity for fling detection.
            # Sampling under ~8ms would let a 2px release-twitch read as
            # thousands of px/s; the clamp bounds any surviving spike.
            inst = max(-3000.0, min(3000.0, (pos - last_pos) / dt))
            self._drag_vel = 0.7 * self._drag_vel + 0.3 * inst
            self._drag_last = (now, pos)
        self._drag_pending = pos

    def _on_seam_drag_end(self, gesture, offset_x, offset_y):
        self._stop_drawer_anim()  # retire the drag coalescer
        self._set_drawer_pos(self._drag_pending)
        self.seam.set_grabbed(False)
        if abs(self._drawer_pos - self._drag_start_h) < DRAWER_CLICK_SLOP:
            # A click, not a drag: settle back to whichever state we were in
            opening = self._drag_start_h > self._drawer_max * 0.5
        elif abs(self._drag_vel) > DRAWER_FLING_VELOCITY:
            opening = self._drag_vel > 0  # a committed flick wins outright
        else:
            opening = self._drawer_pos > self._drawer_max * DRAWER_OPEN_THRESHOLD

        if opening:
            self.now_playing.nav_column.set_active(self._drawer_panel)
            self._animate_drawer_to(self._drawer_max, initial_vel=self._drag_vel)
            if self._drawer_panel == "library":
                self.station_list.on_shown()
        else:
            self.now_playing.nav_column.set_active("mini")
            self.station_list.abort_probes()
            self._animate_drawer_to(0.0, initial_vel=self._drag_vel)

    def _animate_drawer_to(self, target: float, initial_vel: float = 0.0):
        """Spring-mass-damper snap on the frame clock. Seeded with the drag
        release velocity so the snap continues the hand's motion instead of
        restarting from rest."""
        self._stop_drawer_anim()
        self._drawer_target = float(target)
        k = DRAWER_SPRING_OMEGA ** 2
        c = 2.0 * DRAWER_SPRING_ZETA * DRAWER_SPRING_OMEGA
        vel = initial_vel
        last_us = None

        def tick(widget, frame_clock):
            nonlocal vel, last_us
            now_us = frame_clock.get_frame_time()
            if last_us is None:
                last_us = now_us
                return GLib.SOURCE_CONTINUE
            # Cap dt so a stalled frame can't blow up the integration
            dt = min((now_us - last_us) / 1_000_000, 0.033)
            last_us = now_us

            pos = self._drawer_pos
            vel += (k * (self._drawer_target - pos) - c * vel) * dt
            pos += vel * dt
            if pos < 0.0:
                pos, vel = 0.0, 0.0  # hard floor: no tucking above the seam

            if abs(pos - self._drawer_target) < 0.5 and abs(vel) < 8.0:
                self._set_drawer_pos(self._drawer_target)
                self._drawer_tick_id = None
                if self._drawer_target == 0.0:
                    # Park on the empty page so the panels unmap and the
                    # library's probe tick stops sweeping while shut
                    self.dropdown_stack.set_visible_child_name("mini")
                return GLib.SOURCE_REMOVE

            self._set_drawer_pos(pos)
            return GLib.SOURCE_CONTINUE

        self._drawer_tick_id = self.dropdown_scroll.add_tick_callback(tick)

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
        self.now_playing.vol_slider.queue_draw()  # zipper tape re-reads palette on next draw
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
            device_name = daemon.get_sink_name()

            GLib.idle_add(
                self._apply_daemon_state,
                resp, icy, vol, muted, bitrate, channels, fmt, device_name
            )
            time.sleep(1.0)

    def _apply_daemon_state(self, resp, icy, vol, muted, bitrate, channels, fmt, device_name) -> bool:
        if not self._keep_running:
            return False
        self.now_playing.update(resp, icy=icy)
        playing = bool(resp and resp.get("ok") and resp.get("current"))
        recording = resp.get("recording") if resp else None
        self.now_playing.update_indicators(
            bitrate, vol, muted, self._bt_active, playing, channels,
            recording=recording, fmt=fmt, device_name=device_name,
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