"""Owns the docked windows: layout from persisted state + Now Playing's
rect, toggle with sequential fades, and snap-on-release."""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gtk4LayerShell

from . import dock, dock_state
from .dock_window import DockedWindow, PANEL_WIDTH

_TITLES = {"library": "LIBRARY", "discover": "DISCOVER"}


class DockManager:
    def __init__(self, np_win, panels, nav, on_shown, on_hidden):
        self.np = np_win
        self.nav = nav
        self._on_shown = on_shown
        self._on_hidden = on_hidden
        self.state = dock_state.load()
        self.windows = {
            n: DockedWindow(self, n, _TITLES[n], panels[n]) for n in dock_state.NAMES
        }
        self._last_np = None
        self._pending_show = False
        self._saved_done = False
        self._surface_hooked = False
        self._retry_left = 0
        np_win.connect("map", self._on_np_map)
        for n in dock_state.NAMES:
            nav.set_open(n, self.state[n]["open"])

    # --- geometry ---

    def _np_monitor(self):
        surface = self.np.get_surface()
        return self.np.get_display().get_monitor_at_surface(surface) if surface else None

    def monitor_size(self):
        mon = self._np_monitor()
        if mon is None:
            return None
        g = mon.get_geometry()
        return g.width, g.height

    def np_rect(self):
        size = self.monitor_size()
        w, h = self.np.get_width(), self.np.get_height()
        if size is None or w <= 0 or h <= 0:
            return None
        right = Gtk4LayerShell.get_margin(self.np, Gtk4LayerShell.Edge.RIGHT)
        top = Gtk4LayerShell.get_margin(self.np, Gtk4LayerShell.Edge.TOP)
        return dock.Rect(size[0] - right - w, top, w, h)

    def clamp(self, rect, win=None):
        size = None
        if win is not None and win.get_width() > 0 and win.get_height() > 0:
            size = (win.get_width(), win.get_height())
        size = size or self.monitor_size()
        return dock.clamp(rect, *size) if size else rect

    def _open_names(self):
        return [n for n in dock_state.NAMES if self.state[n]["open"]]

    def _slot_rects(self, np):
        """Target rect for every open window."""
        rects = {}
        for n in self._open_names():
            p = self.state[n]["placed"]
            if p is None:
                continue
            if p["mode"] == "np":
                r = dock.Rect(np.x + p["dx"], np.y + p["dy"], PANEL_WIDTH, np.h)
            else:
                r = dock.Rect(p["x"], p["y"], PANEL_WIDTH, np.h)
            rects[n] = self.clamp(r, self.windows[n])
        unplaced = [(n, PANEL_WIDTH) for n in self._open_names()
                    if self.state[n]["placed"] is None]
        rects.update(dock.pack(np, unplaced, list(rects.values())))
        return rects

    def relayout(self):
        np = self.np_rect()
        if np is None:
            return
        for n, r in self._slot_rects(np).items():
            self.windows[n].place(r)

    def _on_np_map(self, _w):
        self._on_np_changed()

    def _hook_surface(self):
        if self._surface_hooked:
            return True
        surface = self.np.get_surface()
        if surface is None:
            return False
        self._surface_hooked = True
        for sig in ("layout", "enter-monitor", "leave-monitor"):
            try:
                surface.connect(sig, self._on_np_changed)
            except TypeError:
                pass
        surface.connect("notify::width", self._on_np_changed)
        surface.connect("notify::height", self._on_np_changed)
        return True

    def _service(self):
        """Apply any NP change or pending show; True if something was done."""
        if not self._hook_surface():
            return False
        np = self.np_rect()
        if np is None:
            return False
        if self._pending_show:
            self._pending_show = False
            self._last_np = np
            self._present_saved()
            return True
        if np == self._last_np:
            return False
        self._last_np = np
        self.relayout()
        return True

    def _on_np_changed(self, *_args):
        # Surface signals can fire before the widget allocation updates, so
        # an unchanged or missing rect gets a short bounded retry.
        if not self._service() or self._pending_show:
            self._retry(60 if self.np_rect() is None or self._pending_show else 2)

    def _retry(self, frames):
        if self._retry_left:
            self._retry_left = max(self._retry_left, frames)
            return
        self._retry_left = frames

        def tick(_w, _clock):
            self._retry_left -= 1
            if self._service() and not self._pending_show:
                self._retry_left = 0
            if self._retry_left <= 0:
                self._retry_left = 0
                return False
            return True

        self.np.add_tick_callback(tick)

    # --- toggle ---

    def toggle(self, name):
        opening = not self.state[name]["open"]
        self.state[name]["open"] = opening
        self.nav.set_open(name, opening)
        win = self.windows[name]
        if opening:
            self.relayout()
            self._fade_in(name)
        else:
            def closed():
                self._on_hidden[name]()
                self.relayout()   # free the dock slot once the fade is done
            win.fade_out(closed)
        dock_state.save(self.state)

    def _fade_in(self, name):
        win = self.windows[name]
        mon = self._np_monitor()
        if mon is not None:
            Gtk4LayerShell.set_monitor(win, mon)
        win.fade_in()
        self._on_shown[name]()

    def show_saved(self):
        """Present windows that were open last session; deferred until Now
        Playing has an allocation."""
        if self._saved_done:
            return
        if self.np_rect() is None:
            self._pending_show = True
            return
        self._present_saved()

    def _present_saved(self):
        self._saved_done = True
        self.relayout()
        for n in self._open_names():
            self._fade_in(n)

    # --- drag release ---

    def commit_drag(self, name, rect):
        np = self.np_rect()
        if np is None:
            return
        others = [np] + [self.windows[n].rect for n in self._open_names() if n != name]
        snapped = self.clamp(dock.snap(rect, others), self.windows[name])
        docked_to = [np] + [self.windows[n].rect for n in self._open_names()
                            if n != name and self._is_np_group(n)]
        if any(dock.touches(snapped, o) for o in docked_to):
            self.state[name]["placed"] = {
                "mode": "np", "dx": snapped.x - np.x, "dy": snapped.y - np.y}
        else:
            self.state[name]["placed"] = {"mode": "free", "x": snapped.x, "y": snapped.y}
        self.windows[name].place(snapped)
        dock_state.save(self.state)
        self.relayout()

    def _is_np_group(self, name):
        p = self.state[name]["placed"]
        return p is None or p["mode"] == "np"

    def shutdown(self):
        for w in self.windows.values():
            w.close()
