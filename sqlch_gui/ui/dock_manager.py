"""Owns the docked windows: layout from persisted state + Now Playing's
rect, toggle with sequential fades, and the live magnet while dragging."""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gtk4LayerShell

from . import dock, dock_state
from .dock_window import DockedWindow, PANEL_WIDTH

_TITLES = {"library": "LIBRARY", "discover": "DISCOVER"}
NP_EDGE = 12   # default right clearance, and the screen-edge magnet margin
NP_TOP = 48


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
        self._held = {}
        self._np_held = dock.Magnet(None, None)
        self._np_start = None
        self._np_before = None
        self._np_room = 0
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
        """Now Playing's card rect in overlay coordinates, from state["np"]
        (None = top-right default) clamped to NP's overlay. Places the card
        there when it isn't already, so the first valid call (overlay and
        card both sized) is what makes NP appear. None until then."""
        area, size = self.np.area_size(), self.np.card_size()
        if area is None or size is None:
            return None
        w, h = size
        p = self.state["np"]
        x, y = (area[0] - NP_EDGE - w, NP_TOP) if p is None else (p["x"], p["y"])
        rect = dock.clamp(dock.Rect(x, y, w, h), *area)
        if rect != self.np.overlay.rect:
            self.np.place_card(rect)
        return rect

    def clamp(self, rect, win=None):
        size = None
        if win is not None and win.get_width() > 0 and win.get_height() > 0:
            size = (win.get_width(), win.get_height())
        size = size or self.np.area_size() or self.monitor_size()
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
        for n, r in dock.pack(np, unplaced, list(rects.values())).items():
            rects[n] = self.clamp(r, self.windows[n])
        return rects

    def relayout(self):
        np = self.np_rect()
        if np is None:
            return
        self._last_np = np
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

    def np_changed(self):
        self._on_np_changed()

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

    # --- drag ---

    def _others(self, name):
        np = self.np_rect()
        return ([np] if np is not None else []) + [
            self.windows[n].rect for n in self._open_names() if n != name]

    def drag_started(self, name):
        self._held[name] = dock.held_at(self.windows[name].rect, self._others(name))

    def magnet_for(self, name, candidate):
        """Live-snapped, clamped rect for a window being dragged; flashes the
        window when an axis newly clicks into place."""
        rect, self._held[name], clicked = dock.magnet(
            candidate, self._others(name), self._held.get(name, dock.Magnet(None, None)))
        if clicked:
            self.windows[name].flash()
        return self.clamp(rect, self.windows[name])

    def commit_drag(self, name, rect):
        self._held.pop(name, None)
        np = self.np_rect()
        if np is None:
            return
        snapped = self.clamp(rect, self.windows[name])
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

    # --- dragging Now Playing (magnets only to the screen edges) ---

    def np_drag_started(self):
        self._np_start = self.np.overlay.rect
        self._np_before = self.state["np"]
        slots = self._slot_rects(self._np_start)
        self._np_room = dock.group_left_room(
            self._np_start, [r for n, r in slots.items() if self._is_np_group(n)])
        area = self.np.area_size()
        self._np_held = (dock.held_at(self._np_start, dock.screen_edge_rects(*area, NP_EDGE))
                         if area else dock.Magnet(None, None))

    def np_drag(self, candidate):
        """Live NP position; docked windows follow because relayout places
        them at NP-relative offsets."""
        area, size = self.np.area_size(), self.np.card_size()
        if area is None or size is None:
            return None
        candidate = dock.Rect(candidate.x, candidate.y, *size)
        rect, self._np_held, clicked = dock.magnet(
            candidate, dock.screen_edge_rects(*area, NP_EDGE), self._np_held)
        # After the magnet, so the left-edge target can't pull NP into its group.
        rect = dock.clamp(rect._replace(x=max(rect.x, self._np_room)), *area)
        if clicked:
            self.np.overlay.flash()
        # Back at the start (e.g. a plain click) keeps a default None position.
        self.state["np"] = (self._np_before if rect == self._np_start
                            else {"x": rect.x, "y": rect.y})
        self.relayout()
        return rect

    def np_drop(self, _rect):
        self._np_held = dock.Magnet(None, None)
        dock_state.save(self.state)
        self.relayout()

    def _is_np_group(self, name):
        p = self.state[name]["placed"]
        return p is None or p["mode"] == "np"

    def shutdown(self):
        for w in self.windows.values():
            w.close()
