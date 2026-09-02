"""Custom GTK 4 tactile controls: pop-it bubble, VU-meter volume, spool nav rail."""

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


class VolumeMeter(Gtk.DrawingArea):
    """Segmented volume VU meter: pips fill left-to-right with the current
    volume level, colored on a green-to-red gradient. Click a pip to jump
    the volume to that segment; scroll to nudge. Reads as a level meter,
    not a scrubber -- unlike the ThreadSlider it replaces, there is no
    drag gesture at all.

    Scrolling up while already at 100% engages the same 120% boost
    ThreadSlider had: an extra hot-colored overflow pip lights up past the
    N_SEGMENTS regular pips. The adjustment itself is never changed by
    boosting; only NowPlayingPanel's boost-toggled handler drives the
    actual wpctl volume change.
    """

    __gsignals__ = {
        'value-changed': (GObject.SignalFlags.RUN_LAST, None, (float,)),
        'boost-toggled': (GObject.SignalFlags.RUN_LAST, None, (bool,)),
    }

    N_SEGMENTS = 10
    _GAP = 2.0
    _MARGIN = 2.0
    _BOOST_ZONE = 16.0

    def __init__(self, adjustment: Gtk.Adjustment):
        super().__init__()
        self.adj = adjustment
        self.boosted = False
        self.set_focusable(True)
        self.set_hexpand(True)
        self.set_size_request(-1, 18)

        self.adj.connect("value-changed", lambda _: self.queue_draw())
        self.set_draw_func(self._on_draw)
        self._update_tooltip()

        click_gest = Gtk.GestureClick.new()
        click_gest.set_button(1)
        click_gest.connect("released", self._on_click)
        self.add_controller(click_gest)

        scroll_gest = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll_gest.connect("scroll", self._on_scroll)
        self.add_controller(scroll_gest)

    def _update_tooltip(self):
        self.set_tooltip_text(
            "Scroll down to restore volume" if self.boosted
            else "Scroll up at max volume for a 120% boost"
        )

    def _norm(self) -> float:
        return (self.adj.get_value() - self.adj.get_lower()) / (self.adj.get_upper() - self.adj.get_lower())

    def _set_from_norm(self, norm: float):
        norm = max(0.0, min(1.0, norm))
        new_val = self.adj.get_lower() + norm * (self.adj.get_upper() - self.adj.get_lower())
        self.adj.set_value(new_val)
        self.emit('value-changed', new_val)

    def _segment_rects(self, width: float, height: float) -> list[tuple[float, float, float, float]]:
        """(x, y, w, h) for each of the N_SEGMENTS regular pips, evenly
        spaced across the widget width, with _BOOST_ZONE reserved past
        the last pip for the boost overflow indicator."""
        usable = width - 2.0 * self._MARGIN - self._BOOST_ZONE
        seg_w = (usable - self._GAP * (self.N_SEGMENTS - 1)) / self.N_SEGMENTS
        rects = []
        for i in range(self.N_SEGMENTS):
            x = self._MARGIN + i * (seg_w + self._GAP)
            rects.append((x, 0.0, seg_w, height))
        return rects

    @staticmethod
    def _rounded_bar(cr, x, y, w, h):
        r = min(w / 2.0, h / 2.0, 3.0)
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()

    def _on_draw(self, area, cr, width, height, user_data=None):
        colors = palette.load()
        trough = _hex_to_rgb_floats(colors.get('DIM', '#1a1828'))
        score = _hex_to_rgb_floats(colors.get('SCORE', '#e0def4'))
        low_rgb = _hex_to_rgb_floats(colors.get('SEVENTH', '#79a383'))
        hot_rgb = _hex_to_rgb_floats(colors.get('FORTE', '#eb6f92'))

        norm = self._norm()
        filled = round(norm * self.N_SEGMENTS)
        rects = self._segment_rects(width, height)

        # Recessed trough behind the whole pip strip (matches the CSS
        # slider-trough idiom -- DIM well, pips sit proud of it).
        cr.set_source_rgba(*trough, 1.0)
        self._rounded_bar(cr, 0.0, 1.0, width, max(0.0, height - 2.0))
        cr.fill()

        for i, (x, y, w, h) in enumerate(rects):
            t = i / (self.N_SEGMENTS - 1)
            r = low_rgb[0] + (hot_rgb[0] - low_rgb[0]) * t
            g = low_rgb[1] + (hot_rgb[1] - low_rgb[1]) * t
            b = low_rgb[2] + (hot_rgb[2] - low_rgb[2]) * t
            if i < filled:
                cr.set_source_rgba(r, g, b, 1.0)
            else:
                cr.set_source_rgba(*score, 0.12)
            self._rounded_bar(cr, x, y + 2.0, w, h - 4.0)
            cr.fill()

        if self.boosted:
            last_x = rects[-1][0] + rects[-1][2]
            overflow_w = width - self._MARGIN - last_x - self._GAP
            if overflow_w > 0:
                cr.set_source_rgba(*hot_rgb, 1.0)
                self._rounded_bar(cr, last_x + self._GAP, 2.0, overflow_w, height - 4.0)
                cr.fill()

    def _on_click(self, gesture, n_press, x, y):
        width = self.get_width()
        usable = width - 2.0 * self._MARGIN - self._BOOST_ZONE
        if usable <= 0:
            return
        if self.boosted:
            self.boosted = False
            self._update_tooltip()
            self.emit('boost-toggled', False)
        seg_w = usable / self.N_SEGMENTS
        idx = int((x - self._MARGIN) / seg_w)
        idx = max(0, min(self.N_SEGMENTS - 1, idx))
        self._set_from_norm((idx + 1) / self.N_SEGMENTS)

    def _on_scroll(self, controller, dx, dy):
        increasing = dy < 0
        if self.boosted:
            if increasing:
                return  # already at the 120% cap, nothing more to do
            self.boosted = False
            self._update_tooltip()
            self.emit('boost-toggled', False)
            self.queue_draw()
            return
        if increasing and self.adj.get_value() >= self.adj.get_upper() - 1e-6:
            self.boosted = True
            self._update_tooltip()
            self.emit('boost-toggled', True)
            self.queue_draw()
            return
        total_range = self.adj.get_upper() - self.adj.get_lower()
        step = total_range * 0.05
        new_val = self.adj.get_value() + (step if increasing else -step)
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
        self.set_size_request(34, 34)
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
        colors = palette.load()
        if self.recording:
            face = _hex_to_rgb_floats(colors.get('FORTE', '#eb6f92'))
            glyph = _hex_to_rgb_floats(colors.get('SCORE', '#e0def4'))
        else:
            face = _hex_to_rgb_floats(colors.get('WING', '#393552'))
            glyph = _hex_to_rgb_floats(colors.get('LYRIC', '#c9c5da'))
        ring = _hex_to_rgb_floats(colors.get('SCORE', '#e0def4'))

        cx, cy = width / 2.0, height / 2.0
        radius = min(width, height) / 2.0 - 3.0

        # Flat disc + hairline ring, same vocabulary as the CSS .control-btn.
        cr.set_source_rgba(*face, 1.0)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.fill()

        cr.set_line_width(1.0)
        cr.set_source_rgba(*ring, 0.15)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()

        # Centered record glyph: a small filled square.
        s = radius * 0.5
        cr.set_source_rgba(*glyph, 1.0)
        cr.rectangle(cx - s / 2.0, cy - s / 2.0, s, s)
        cr.fill()


class NavColumn(Gtk.Box):
    """Horizontal nav-icon row: Mini (collapse, labeled Now Playing), Library,
    Discover.

    Not three independent toggle buttons -- clicking Library or Discover
    opens that section (auto-collapsing whichever was open), re-clicking
    the already-open one is a no-op, and only Mini collapses back down to
    nothing selected. Mini's icon is a hand-drawn display/monitor glyph
    rather than a stock symbolic icon, matching the hand-drawn vocabulary
    already established by VolumeMeter and RecordBubble.
    """

    __gsignals__ = {
        'nav-selected': (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.set_valign(Gtk.Align.CENTER)

        self.active = "mini"
        self._buttons = {}

        self._display = Gtk.DrawingArea()
        self._display.set_content_width(14)
        self._display.set_content_height(14)
        self._display.set_draw_func(self._draw_display)

        btn_mini = Gtk.Button()
        btn_mini.set_child(self._display)
        btn_mini.add_css_class("nav-btn")
        btn_mini.set_tooltip_text("Now Playing")
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
        self._display.queue_draw()

    def _select(self, name: str):
        if name == self.active:
            return  # re-clicking the already-open one (or idle Mini) is a no-op
        self.set_active(name)
        self.emit("nav-selected", name)

    def _draw_display(self, area, cr, width, height, user_data=None):
        colors = palette.load()
        mini_active = self.active == "mini"
        # Matches the new .nav-btn foreground: SCORE when Now Playing is the
        # active view, plain REST otherwise. Cairo draws don't pick up GTK
        # CSS `color`, so it's read from the palette explicitly.
        rgb = _hex_to_rgb_floats(colors.get('SCORE' if mini_active else 'REST', '#e0def4'))
        cr.set_source_rgba(*rgb, 1.0)
        cr.set_line_width(1.4)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)

        # Screen: rounded rect
        screen_w, screen_h = width * 0.72, height * 0.58
        x0, y0 = (width - screen_w) / 2.0, height * 0.08
        r = 1.6
        cr.new_sub_path()
        cr.arc(x0 + screen_w - r, y0 + r, r, -math.pi / 2, 0)
        cr.arc(x0 + screen_w - r, y0 + screen_h - r, r, 0, math.pi / 2)
        cr.arc(x0 + r, y0 + screen_h - r, r, math.pi / 2, math.pi)
        cr.arc(x0 + r, y0 + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()
        cr.stroke()

        # Stand: short neck below the screen, plus a small base foot.
        cx = width / 2.0
        neck_top = y0 + screen_h
        neck_bottom = neck_top + height * 0.14
        cr.move_to(cx, neck_top)
        cr.line_to(cx, neck_bottom)
        cr.stroke()

        foot_half = width * 0.16
        cr.move_to(cx - foot_half, neck_bottom)
        cr.line_to(cx + foot_half, neck_bottom)
        cr.stroke()
