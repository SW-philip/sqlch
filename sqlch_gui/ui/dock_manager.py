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
        self._tick = np_win.add_tick_callback(self._watch_np)
        for n in dock_state.NAMES:
            nav.set_open(n, self.state[n]["open"])

    # --- geometry ---

    def monitor_size(self):
        surface = self.np.get_surface()
        mon = self.np.get_display().get_monitor_at_surface(surface) if surface else None
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

    def clamp(self, rect):
        size = self.monitor_size()
        return dock.clamp(rect, *size) if size else rect

    def _open_names(self):
        return [n for n in dock_state.NAMES if self.state[n]["open"]]

    def _slot_rects(self, np):
        """Target rect for every open window."""
        unplaced = [(n, PANEL_WIDTH) for n in self._open_names()
                    if self.state[n]["placed"] is None]
        rects = dock.default_dock(np, unplaced)
        for n in self._open_names():
            p = self.state[n]["placed"]
            if p is None:
                continue
            if p["mode"] == "np":
                r = dock.Rect(np.x + p["dx"], np.y + p["dy"], PANEL_WIDTH, np.h)
            else:
                r = dock.Rect(p["x"], p["y"], PANEL_WIDTH, np.h)
            rects[n] = self.clamp(r)
        return rects

    def relayout(self):
        np = self.np_rect()
        if np is None:
            return
        for n, r in self._slot_rects(np).items():
            self.windows[n].place(r)

    def _watch_np(self, _w, _clock):
        np = self.np_rect()
        if np != self._last_np:
            self._last_np = np
            self.relayout()
        return True

    # --- toggle ---

    def toggle(self, name):
        opening = not self.state[name]["open"]
        self.state[name]["open"] = opening
        self.nav.set_open(name, opening)
        win = self.windows[name]
        if opening:
            self.relayout()
            win.fade_in()
            self._on_shown[name]()
        else:
            win.fade_out(self._on_hidden[name])
            self.relayout()   # closed windows free their dock slot
        dock_state.save(self.state)

    def show_saved(self):
        """Present windows that were open last session. Called once Now
        Playing has an allocation."""
        self.relayout()
        for n in self._open_names():
            self.windows[n].fade_in()
            self._on_shown[n]()

    # --- drag release ---

    def commit_drag(self, name, rect):
        np = self.np_rect()
        if np is None:
            return
        others = [np] + [self.windows[n].rect for n in self._open_names() if n != name]
        snapped = self.clamp(dock.snap(rect, others))
        docked_to = [np] + [self.windows[n].rect for n in self._open_names()
                            if n != name and self._is_np_group(n, np)]
        if any(dock.touches(snapped, o) for o in docked_to):
            self.state[name]["placed"] = {
                "mode": "np", "dx": snapped.x - np.x, "dy": snapped.y - np.y}
        else:
            self.state[name]["placed"] = {"mode": "free", "x": snapped.x, "y": snapped.y}
        self.windows[name].place(snapped)
        dock_state.save(self.state)

    def _is_np_group(self, name, np):
        p = self.state[name]["placed"]
        return p is None or p["mode"] == "np"

    def shutdown(self):
        self.np.remove_tick_callback(self._tick)
        for w in self.windows.values():
            w.close()
