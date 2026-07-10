"""Custom GTK 4 tactile controls: pop-it bubble, thread-and-button volume slider, spool nav rail."""

import colorsys
import math
import cairo
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GObject, GLib
from .. import palette


def _hex_to_rgb_floats(hex_val: str) -> tuple[float, float, float]:
    h = hex_val.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return r, g, b


def _shade(rgb: tuple[float, float, float], factor: float) -> tuple[float, float, float]:
    """Lighten (factor > 1) or darken (factor < 1) an RGB triple by scaling HSV value."""
    r, g, b = rgb
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    v = max(0.0, min(1.0, v * factor))
    return colorsys.hsv_to_rgb(h, s, v)


class ThreadSlider(Gtk.DrawingArea):
    """Full-width volume fader drawn as a tufted upholstery button riding
    a dashed sewing thread. Backs onto a Gtk.Adjustment, same as the
    zipper slider it replaces, but the track is a plain thread with no
    open/closed states -- all the visual richness lives in the button.
    Click anywhere on the thread to jump there; drag the button; scroll
    to nudge.

    Past the thread's right edge sits a fixed, always-visible "nub" (an
    empty buttonhole loop). Dragging the button past the track's edge
    and onto the nub engages a hard-coded 120% volume boost -- the same
    button re-colors hot (palette FORTE) and docks there. The
    adjustment itself is never changed by boosting; only
    NowPlayingPanel's boost-toggled handler drives the actual wpctl
    volume change. Boost only engages via drag (a plain click on the
    empty nub is a no-op); it disengages either by clicking the docked
    button (pops back to the exact pre-boost value) or by dragging it
    back onto the thread (lands wherever dropped, manual value wins).
    """

    __gsignals__ = {
        'value-changed': (GObject.SignalFlags.RUN_LAST, None, (float,)),
        'boost-toggled': (GObject.SignalFlags.RUN_LAST, None, (bool,)),
    }

    # Single source of truth for the button's edge margin and the nub's
    # geometry, so drawing and hit-testing can never drift apart.
    _MARGIN = 10.0
    _NUB_GAP = 10.0
    _NUB_ZONE = 34.0
    _NUB_RADIUS_X = 9.0
    _NUB_RADIUS_Y = 13.0

    def __init__(self, adjustment: Gtk.Adjustment):
        super().__init__()
        self.adj = adjustment
        self.boosted = False
        self.set_focusable(True)
        self.set_hexpand(True)
        self.set_size_request(-1, 34)

        self.adj.connect("value-changed", lambda _: self.queue_draw())
        self.set_draw_func(self._on_draw)
        self._update_tooltip()

        self.drag_start_val = 0.0
        self._dragging = False
        self._drag_from_nub = False

        click_gest = Gtk.GestureClick.new()
        click_gest.set_button(1)
        click_gest.connect("released", self._on_click)
        self.add_controller(click_gest)

        drag_gest = Gtk.GestureDrag.new()
        drag_gest.connect("drag-begin", self._on_drag_begin)
        drag_gest.connect("drag-update", self._on_drag_update)
        drag_gest.connect("drag-end", self._on_drag_end)
        self.add_controller(drag_gest)

        scroll_gest = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll_gest.connect("scroll", self._on_scroll)
        self.add_controller(scroll_gest)

    def _update_tooltip(self):
        self.set_tooltip_text(
            "Tap the button to restore volume" if self.boosted
            else "Drag the button onto the nub for 120% boost"
        )

    def _norm(self) -> float:
        return (self.adj.get_value() - self.adj.get_lower()) / (self.adj.get_upper() - self.adj.get_lower())

    def _set_from_norm(self, norm: float):
        norm = max(0.0, min(1.0, norm))
        new_val = self.adj.get_lower() + norm * (self.adj.get_upper() - self.adj.get_lower())
        self.adj.set_value(new_val)
        self.emit('value-changed', new_val)

    def _usable_width(self, width: float) -> float:
        return width - 2.0 * self._MARGIN - self._NUB_ZONE

    def _button_x(self, width: float) -> float:
        return self._MARGIN + self._norm() * self._usable_width(width)

    def _track_right(self, width: float) -> float:
        return self._MARGIN + self._usable_width(width)

    def _nub_x(self, width: float) -> float:
        return self._track_right(width) + self._NUB_GAP + self._NUB_RADIUS_X

    def _on_draw(self, area, cr, width, height, user_data=None):
        cy = height / 2.0
        thread_x = self._button_x(width)
        nub_x = self._nub_x(width)
        track_right = self._track_right(width)

        colors = palette.load()
        bar_rgb = _hex_to_rgb_floats(colors.get('BAR', '#6e6a86'))
        thread_rgb = _shade(bar_rgb, 1.15)
        button_rgb = _shade(bar_rgb, 1.05)
        dimple_rgb = _shade(bar_rgb, 0.3)
        forte_rgb = _hex_to_rgb_floats(colors.get('FORTE', '#eb6f92'))

        # The sewing thread: a plain dashed line across the track only
        # (never through the nub zone) -- no open/closed states.
        cr.save()
        cr.set_dash([4.0, 4.0])
        cr.set_line_width(2.0)
        cr.set_source_rgba(*thread_rgb, 0.7)
        cr.move_to(self._MARGIN - 2.0, cy)
        cr.line_to(track_right, cy)
        cr.stroke()
        cr.restore()

        # The nub: an empty buttonhole loop past the thread's end,
        # always visible whether or not the button is docked there --
        # that's the discoverability cue.
        cr.save()
        cr.set_source_rgba(*thread_rgb, 0.6)
        cr.set_line_width(1.6)
        cr.save()
        cr.translate(nub_x, cy)
        cr.scale(self._NUB_RADIUS_X, self._NUB_RADIUS_Y)
        cr.arc(0, 0, 1.0, 0, 2 * math.pi)
        cr.restore()
        cr.stroke()
        cr.move_to(nub_x - self._NUB_RADIUS_X + 2.0, cy)
        cr.line_to(nub_x + self._NUB_RADIUS_X - 2.0, cy)
        cr.stroke()
        cr.restore()

        if self.boosted:
            # Ghost marker: a faint ring at the resting spot the button
            # will return to once un-boosted.
            cr.save()
            cr.set_dash([1.5, 1.5])
            cr.set_line_width(1.2)
            cr.set_source_rgba(*thread_rgb, 0.5)
            cr.arc(thread_x, cy, 3.0, 0, 2 * math.pi)
            cr.stroke()
            cr.restore()
            button_x = nub_x
            base_rgb = forte_rgb
        else:
            button_x = thread_x
            base_rgb = button_rgb

        # Tufted button: domed radial gradient, single center dimple,
        # four pull-lines radiating out to the puckered fabric edge --
        # the chesterfield-upholstery look, not a sew-through button.
        radius = 15.0
        gradient = cairo.RadialGradient(
            button_x - radius * 0.3, cy - radius * 0.3, radius * 0.1,
            button_x, cy, radius,
        )
        gradient.add_color_stop_rgba(0.0, *_shade(base_rgb, 1.5), 1.0)
        gradient.add_color_stop_rgba(0.5, *base_rgb, 1.0)
        gradient.add_color_stop_rgba(1.0, *_shade(base_rgb, 0.55), 1.0)
        cr.set_source(gradient)
        cr.arc(button_x, cy, radius, 0, 2 * math.pi)
        cr.fill()

        cr.set_source_rgba(*dimple_rgb, 1.0)
        cr.arc(button_x, cy, 2.6, 0, 2 * math.pi)
        cr.fill()

        cr.save()
        cr.set_source_rgba(0.0, 0.0, 0.0, 0.3)
        cr.set_line_width(1.0)
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            cr.move_to(button_x, cy)
            cr.line_to(button_x + dx * radius * 0.7, cy + dy * radius * 0.7)
        cr.stroke()
        cr.restore()

    def _on_click(self, gesture, n_press, x, y):
        if self._dragging:
            return
        width = self.get_width()
        usable = self._usable_width(width)
        if usable <= 0:
            return
        if self.boosted:
            if x > self._track_right(width):
                # Tapping the docked button: quick pop back to pre-boost.
                self.boosted = False
                self._update_tooltip()
                self.emit('boost-toggled', False)
                self.queue_draw()
            else:
                # Tapping the thread while boosted: manual override --
                # un-boost, then jump straight to the clicked position.
                self.boosted = False
                self._update_tooltip()
                self.emit('boost-toggled', False)
                self._set_from_norm((x - self._MARGIN) / usable)
            return
        if x > self._track_right(width):
            return  # clicking the empty nub/gap does nothing -- drag only
        self._set_from_norm((x - self._MARGIN) / usable)

    def _on_drag_begin(self, gesture, start_x, start_y):
        self.drag_start_val = self.adj.get_value()
        self._drag_from_nub = self.boosted
        self.grab_focus()

    def _on_drag_update(self, gesture, offset_x, offset_y):
        self._dragging = True
        width = self.get_width()
        usable = self._usable_width(width)
        if usable <= 0:
            return

        if self._drag_from_nub:
            nub_x = self._nub_x(width)
            candidate_x = nub_x + offset_x
            if candidate_x > self._track_right(width):
                return  # still parked over the nub; nothing changes
            if self.boosted:
                self.boosted = False
                self._update_tooltip()
                self.emit('boost-toggled', False)
            norm = max(0.0, min(1.0, (candidate_x - self._MARGIN) / usable))
            new_val = self.adj.get_lower() + norm * (self.adj.get_upper() - self.adj.get_lower())
            self.adj.set_value(new_val)
            self.emit('value-changed', new_val)
            return

        total_range = self.adj.get_upper() - self.adj.get_lower()
        delta_norm = offset_x / usable
        raw_val = self.drag_start_val + delta_norm * total_range
        if raw_val > self.adj.get_upper():
            return  # reaching past the track's end -- not a value yet
        new_val = max(self.adj.get_lower(), raw_val)
        self.adj.set_value(new_val)
        self.emit('value-changed', new_val)

    def _on_drag_end(self, gesture, offset_x, offset_y):
        if not self._drag_from_nub:
            width = self.get_width()
            usable = self._usable_width(width)
            if usable > 0:
                total_range = self.adj.get_upper() - self.adj.get_lower()
                delta_norm = offset_x / usable
                raw_val = self.drag_start_val + delta_norm * total_range
                overshoot_px = (raw_val - self.adj.get_upper()) * usable
                if overshoot_px >= self._NUB_GAP + self._NUB_RADIUS_X:
                    self.boosted = True
                    self._update_tooltip()
                    self.emit('boost-toggled', True)
                    self.queue_draw()
        # Deferred to idle so any 'released' from the co-installed
        # GestureClick for this same button-up is still guarded by
        # _dragging, no matter which controller GTK dispatches first.
        GLib.idle_add(self._clear_dragging)

    def _clear_dragging(self):
        self._dragging = False
        return GLib.SOURCE_REMOVE

    def _on_scroll(self, controller, dx, dy):
        if self.boosted:
            self.boosted = False
            self._update_tooltip()
            self.emit('boost-toggled', False)
        total_range = self.adj.get_upper() - self.adj.get_lower()
        step = (total_range * 0.05) if dy > 0 else -(total_range * 0.05)
        new_val = self.adj.get_value() - step
        new_val = max(self.adj.get_lower(), min(self.adj.get_upper(), new_val))
        self.adj.set_value(new_val)
        self.emit('value-changed', new_val)


class RecordBubble(Gtk.DrawingArea):
    """Two-mode record button drawn as a pop-it silicone bubble.

    Right-click cycles the FULL/TRACK mode (emits 'mode-changed' so the
    mode can be displayed outside this widget, e.g. a corner badge);
    left-click emits 'record-toggled' with the selected mode. Recording
    state is pushed in from the daemon poll via set_state() — the widget
    never assumes its click succeeded. There is no drag gesture: this
    control is pressed, never turned.
    """

    __gsignals__ = {
        'record-toggled': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'mode-changed': (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    MODES = ("full", "track")

    def __init__(self):
        super().__init__()
        self.mode = "full"
        self.recording = False
        self.set_size_request(46, 46)
        self.set_focusable(True)
        self.set_draw_func(self._on_draw)
        self._update_tooltip()

        left = Gtk.GestureClick.new()
        left.set_button(1)
        left.connect("released", self._on_left_click)
        self.add_controller(left)

        right = Gtk.GestureClick.new()
        right.set_button(3)
        right.connect("released", self._on_right_click)
        self.add_controller(right)

    def set_state(self, recording: bool, mode: str | None):
        """Reflect daemon truth from the status poll."""
        changed = recording != self.recording
        if recording and mode in self.MODES and mode != self.mode:
            self.mode = mode
            changed = True
        self.recording = recording
        if changed:
            self._update_tooltip()
            self.queue_draw()

    def _update_tooltip(self):
        action = "left-click to stop" if self.recording else "left-click to record"
        self.set_tooltip_text(
            f"REC {self.mode.upper()} · {action} · right-click: mode"
        )

    def _on_left_click(self, gesture, n_press, x, y):
        self.emit('record-toggled', self.mode)

    def _on_right_click(self, gesture, n_press, x, y):
        if self.recording:
            return  # mode locked while a take is rolling
        i = self.MODES.index(self.mode)
        self.mode = self.MODES[(i + 1) % len(self.MODES)]
        self._update_tooltip()
        self.queue_draw()
        self.emit('mode-changed', self.mode)

    def _on_draw(self, area, cr, width, height, user_data=None):
        cx = width / 2.0
        cy = height / 2.0
        radius = min(width, height) / 2.0 - 5.0

        if self.recording:
            # Soft glow behind the pressed bubble
            cr.set_source_rgba(0.86, 0.20, 0.18, 0.25)
            cr.arc(cx, cy, radius + 5.0, 0, 2 * math.pi)
            cr.fill()

        # Dashed stitch ring, echoes the fabric-hem convention used elsewhere in this file; turns red while recording
        cr.save()
        cr.set_dash([2.0, 3.0])
        cr.set_line_width(1.5)
        if self.recording:
            cr.set_source_rgba(0.86, 0.20, 0.18, 0.6)
        else:
            cr.set_source_rgba(0.9, 0.9, 0.9, 0.35)
        cr.arc(cx, cy, radius + 4.0, 0, 2 * math.pi)
        cr.stroke()
        cr.restore()

        # Silicone bubble face: convex bump when idle, pressed-in dimple
        # when recording. Same gradient trick fakes both: a highlight near
        # the upper-left reads as "light hitting a bump sticking up"; a
        # highlight shifted toward the center/lower-right of a darker,
        # more saturated fill reads as "light entering a pressed dimple."
        if self.recording:
            gradient = cairo.RadialGradient(
                cx - radius * 0.15, cy - radius * 0.1, radius * 0.05,
                cx, cy, radius,
            )
            gradient.add_color_stop_rgba(0.0, 0.53, 0.14, 0.13, 1.0)
            gradient.add_color_stop_rgba(0.55, 0.86, 0.20, 0.18, 1.0)
            gradient.add_color_stop_rgba(1.0, 0.66, 0.27, 0.24, 1.0)
        else:
            gradient = cairo.RadialGradient(
                cx - radius * 0.35, cy - radius * 0.35, radius * 0.1,
                cx, cy, radius,
            )
            gradient.add_color_stop_rgba(0.0, 0.23, 0.23, 0.24, 1.0)
            gradient.add_color_stop_rgba(0.55, 0.16, 0.16, 0.18, 1.0)
            gradient.add_color_stop_rgba(1.0, 0.12, 0.12, 0.13, 1.0)
        cr.set_source(gradient)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.fill()

        # Drop shadow under the bump (idle only — a pressed dimple casts
        # no shadow of its own).
        if not self.recording:
            cr.set_source_rgba(0.0, 0.0, 0.0, 0.25)
            cr.arc(cx, cy + 1.5, radius, 0, 2 * math.pi)
            cr.set_line_width(1.0)
            cr.stroke_preserve()


class NavColumn(Gtk.Box):
    """Vertical nav-icon rail: Mini (collapse), Library, Discover.

    Not three independent toggle buttons -- clicking Library or Discover
    opens that section (auto-collapsing whichever was open), re-clicking
    the already-open one is a no-op, and only Mini collapses back down to
    nothing selected. Mini's icon is a hand-drawn spool (thread wound back
    up) rather than a stock symbolic icon, echoing the thread/button
    vocabulary already established by ThreadSlider and RecordBubble.
    """

    __gsignals__ = {
        'nav-selected': (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class("sidebar")
        self.set_valign(Gtk.Align.CENTER)

        self.active = "mini"
        self._buttons = {}

        self._spool = Gtk.DrawingArea()
        self._spool.set_content_width(18)
        self._spool.set_content_height(18)
        self._spool.set_draw_func(self._draw_spool)

        btn_mini = Gtk.Button()
        btn_mini.set_child(self._spool)
        btn_mini.add_css_class("nav-btn")
        btn_mini.set_tooltip_text("Mini")
        btn_mini.connect("clicked", lambda b: self._select("mini"))
        self.append(btn_mini)
        self._buttons["mini"] = btn_mini

        btn_library = Gtk.Button(icon_name="view-list-symbolic")
        btn_library.add_css_class("nav-btn")
        btn_library.set_tooltip_text("Station Library")
        btn_library.connect("clicked", lambda b: self._select("library"))
        self.append(btn_library)
        self._buttons["library"] = btn_library

        btn_discover = Gtk.Button(icon_name="folder-saved-search-symbolic")
        btn_discover.add_css_class("nav-btn")
        btn_discover.set_tooltip_text("Discover Stations")
        btn_discover.connect("clicked", lambda b: self._select("discover"))
        self.append(btn_discover)
        self._buttons["discover"] = btn_discover

        self._buttons["mini"].add_css_class("active")

    def set_active(self, name: str):
        """Sync the highlight to drawer state driven from outside (seam
        drags) without re-emitting nav-selected."""
        if name == self.active:
            return
        self._buttons[self.active].remove_css_class("active")
        self.active = name
        self._buttons[name].add_css_class("active")
        self._spool.queue_draw()

    def _select(self, name: str):
        if name == self.active:
            return  # re-clicking the already-open one (or idle Mini) is a no-op
        self.set_active(name)
        self.emit("nav-selected", name)

    def _draw_spool(self, area, cr, width, height, user_data=None):
        colors = palette.load()
        mini_active = self.active == "mini"
        # Matches .nav-btn.active's `color: {outline}` (palette SHADOW) when
        # Mini is selected, .nav-btn's plain `color: {REST}` otherwise --
        # Cairo draws don't pick up GTK CSS `color`, so it's read explicitly.
        rgb = _hex_to_rgb_floats(colors.get('SHADOW' if mini_active else 'REST', '#4e4e52'))

        cx, cy = width / 2.0, height / 2.0
        rx, ry = width * 0.42, height * 0.16
        top, bottom = cy - height * 0.32, cy + height * 0.32

        cr.set_source_rgba(*rgb, 1.0)
        cr.set_line_width(1.4)

        # Two dashed rims (the spool's end-caps) joined by two verticals
        # (the spindle) -- reads as thread wound back onto a spool.
        cr.set_dash([1.6, 1.4])
        for rim_y in (top, bottom):
            cr.save()
            cr.translate(cx, rim_y)
            cr.scale(rx, ry)
            cr.arc(0, 0, 1.0, 0, 2 * math.pi)
            cr.restore()
            cr.stroke()

        cr.set_dash([])
        cr.move_to(cx - rx, top)
        cr.line_to(cx - rx, bottom)
        cr.stroke()
        cr.move_to(cx + rx, top)
        cr.line_to(cx + rx, bottom)
        cr.stroke()
