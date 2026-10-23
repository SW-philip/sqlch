"""Custom GTK 4 tactile controls: pop-it bubble, volume ramp, spool nav rail."""

import math
import time
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GObject, GLib
from .. import palette
from .timefmt import format_duration


def _hex_to_rgb_floats(hex_val: str) -> tuple[float, float, float]:
    h = hex_val.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return r, g, b


def _rounded_rect(cr, x, y, w, h, r):
    r = min(w / 2.0, h / 2.0, r)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


class VolumeRamp(Gtk.DrawingArea):
    """Volume as a rising wedge of thin bars -- the shape of the universal
    volume glyph. Bars light in ROOT up to the current level, with the edge
    clipped mid-bar so the fill tracks the real value instead of snapping to
    a segment; unlit bars are faint ticks. Click or drag to scrub, scroll to
    nudge. No trough: the wedge sits straight on the card.

    Scrolling up while already at 100% engages the 120% boost: the extra
    full-height bar past the ramp lights in FORTE. The adjustment itself is
    never changed by boosting; only NowPlayingPanel's boost-toggled handler
    drives the actual wpctl volume change.
    """

    __gsignals__ = {
        'value-changed': (GObject.SignalFlags.RUN_LAST, None, (float,)),
        'boost-toggled': (GObject.SignalFlags.RUN_LAST, None, (bool,)),
    }

    N_BARS = 16
    _FILL = 0.5       # bar width as a fraction of the bar pitch
    _MIN_FRAC = 0.45  # first bar's height as a fraction of the tallest
    _BOOST_GAP = 6.0  # extra space before the boost bar sets it apart

    def __init__(self, adjustment: Gtk.Adjustment):
        super().__init__()
        self.adj = adjustment
        self.boosted = False
        self.set_focusable(True)
        self.set_hexpand(True)
        self.set_size_request(-1, 22)

        self.adj.connect("value-changed", lambda _: self._refresh())
        self.set_draw_func(self._on_draw)
        self._update_tooltip()

        click_gest = Gtk.GestureClick.new()
        click_gest.set_button(1)
        click_gest.connect("pressed", lambda _g, _n, x, _y: self._scrub(x))
        self.add_controller(click_gest)

        drag_gest = Gtk.GestureDrag.new()
        drag_gest.connect("drag-update", self._on_drag_update)
        self.add_controller(drag_gest)

        scroll_gest = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll_gest.connect("scroll", self._on_scroll)
        self.add_controller(scroll_gest)

    def _refresh(self):
        self._update_tooltip()
        self.queue_draw()

    def _update_tooltip(self):
        if self.boosted:
            self.set_tooltip_text("Volume 120% · scroll down to restore")
        else:
            self.set_tooltip_text(
                f"Volume {round(self._norm() * 100)}% · scroll up at max for a 120% boost")

    def _norm(self) -> float:
        return (self.adj.get_value() - self.adj.get_lower()) / (self.adj.get_upper() - self.adj.get_lower())

    def _set_from_norm(self, norm: float):
        norm = max(0.0, min(1.0, norm))
        new_val = self.adj.get_lower() + norm * (self.adj.get_upper() - self.adj.get_lower())
        if abs(new_val - self.adj.get_value()) < 0.005:
            return  # drag jitter -- don't spam wpctl with no-op changes
        self.adj.set_value(new_val)
        self.emit('value-changed', new_val)

    def _pitch(self, width: float) -> float:
        """Bar-to-bar spacing; the boost bar takes one more pitch past the ramp."""
        return (width - self._BOOST_GAP) / (self.N_BARS + 1)

    def _ramp_width(self, width: float) -> float:
        """Width of the regular ramp; the boost bar and its gap sit past it."""
        pitch = self._pitch(width)
        return (self.N_BARS - 1) * pitch + pitch * self._FILL

    def _bar_rects(self, width: float, height: float) -> list[tuple[float, float, float, float]]:
        """(x, y, w, h) for each regular bar, bottom-aligned, rising linearly
        from _MIN_FRAC of the height to full height."""
        pitch = self._pitch(width)
        rects = []
        for i in range(self.N_BARS):
            t = i / (self.N_BARS - 1)
            h = height * (self._MIN_FRAC + (1.0 - self._MIN_FRAC) * t)
            rects.append((i * pitch, height - h, pitch * self._FILL, h))
        return rects

    def _norm_at(self, x: float) -> float:
        ramp = self._ramp_width(self.get_width())
        return 0.0 if ramp <= 0 else max(0.0, min(1.0, x / ramp))

    @staticmethod
    def _rounded_bar(cr, x, y, w, h):
        _rounded_rect(cr, x, y, w, h, 2.0)

    def _on_draw(self, area, cr, width, height, user_data=None):
        colors = palette.load()
        score = _hex_to_rgb_floats(colors.get('SCORE', '#e0def4'))
        lit = _hex_to_rgb_floats(colors.get('ROOT', '#c4a7e7'))
        hot = _hex_to_rgb_floats(colors.get('FORTE', '#eb6f92'))

        rects = self._bar_rects(width, height)
        for x, y, w, h in rects:
            cr.set_source_rgba(*score, 0.12)
            self._rounded_bar(cr, x, y, w, h)
            cr.fill()

        # Lit overlay clipped at the exact level, so a bar can be part-lit.
        level_x = 1.0 if self.boosted else self._norm()
        level_x *= self._ramp_width(width)
        if level_x > 0:
            cr.save()
            cr.rectangle(0, 0, level_x, height)
            cr.clip()
            cr.set_source_rgba(*lit, 1.0)
            for x, y, w, h in rects:
                self._rounded_bar(cr, x, y, w, h)
            cr.fill()
            cr.restore()

        bw = rects[-1][2]
        bx = width - bw
        if bw > 0:
            if self.boosted:
                cr.set_source_rgba(*hot, 1.0)
            else:
                cr.set_source_rgba(*score, 0.06)
            self._rounded_bar(cr, bx, 0.0, bw, height)
            cr.fill()

    def _unboost(self):
        if self.boosted:
            self.boosted = False
            self.emit('boost-toggled', False)
            self._refresh()

    def _scrub(self, x: float):
        self.grab_focus()
        self._unboost()
        self._set_from_norm(self._norm_at(x))

    def _on_drag_update(self, gesture, dx, _dy):
        ok, sx, _sy = gesture.get_start_point()
        if ok:
            self._scrub(sx + dx)

    def _on_scroll(self, controller, dx, dy):
        increasing = dy < 0
        if self.boosted:
            if not increasing:
                self._unboost()
            return  # already at the 120% cap when increasing
        if increasing and self.adj.get_value() >= self.adj.get_upper() - 1e-6:
            self.boosted = True
            self.emit('boost-toggled', True)
            self._refresh()
            return
        step = (self.adj.get_upper() - self.adj.get_lower()) * 0.05
        new_val = self.adj.get_value() + (step if increasing else -step)
        new_val = max(self.adj.get_lower(), min(self.adj.get_upper(), new_val))
        self.adj.set_value(new_val)
        self.emit('value-changed', new_val)


class RecordBubble(Gtk.DrawingArea):
    """Two-mode record button, drawn as a keycap matching .control-btn.

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
    _DX, _DY = 3.0, 4.0  # hard-offset shadow, matches .control-btn
    _RADIUS = 7.0

    def __init__(self):
        super().__init__()
        self.mode = "full"
        self.recording = False
        self._pressed = False
        self.set_size_request(44 + int(self._DX), 26 + int(self._DY))
        self.set_valign(Gtk.Align.CENTER)
        self.set_focusable(True)
        self.set_draw_func(self._on_draw)
        self._update_tooltip()

        left = Gtk.GestureClick.new()
        left.set_button(1)
        left.connect("pressed", lambda *_: self._set_pressed(True))
        left.connect("released", self._on_left_click)
        left.connect("stopped", lambda *_: self._set_pressed(False))
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

    def _set_pressed(self, pressed: bool):
        if pressed != self._pressed:
            self._pressed = pressed
            self.queue_draw()

    def _on_left_click(self, gesture, n_press, x, y):
        self._set_pressed(False)
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

        staff = tuple(int(c) / 255.0 for c in colors.get('STAFF', '15,14,23').split(','))
        a_drop = float(colors.get('STAFF_A_DROP', '0.55'))

        # A keycap shaped like .control-btn, with the same hard offset as it
        # and the window shell; pressing slides the cap into its shadow.
        w, h = width - self._DX, height - self._DY
        x = y = 0.0
        if self._pressed:
            x, y = self._DX, self._DY
        else:
            cr.set_source_rgba(*staff, a_drop)
            _rounded_rect(cr, self._DX, self._DY, w, h, self._RADIUS)
            cr.fill()

        cr.set_source_rgba(*face, 1.0)
        _rounded_rect(cr, x, y, w, h, self._RADIUS)
        cr.fill()

        cr.set_line_width(2.0)
        cr.set_source_rgba(*ring, 0.32)
        _rounded_rect(cr, x + 1.0, y + 1.0, w - 2.0, h - 2.0, self._RADIUS - 1.0)
        cr.stroke()

        # Centered record glyph: a small filled square.
        cx, cy = x + w / 2.0, y + h / 2.0
        s = h * 0.32
        cr.set_source_rgba(*glyph, 1.0)
        cr.rectangle(cx - s / 2.0, cy - s / 2.0, s, s)
        cr.fill()


class NavColumn(Gtk.Box):
    """Folder-tab row: RADIO and the SOURCES menu toggle their docked windows
    independently. A click only emits `nav-toggled`; the DockManager decides
    what to open or close and syncs the highlight back with `set_open`, so
    the tab can never disagree with the window. Hosted by Header, which
    styles the row as `.sq-tabs`."""

    __gsignals__ = {
        'nav-toggled': (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    _TABS = (
        ("radio", "RADIO", "Radio: station library and discover"),
    )

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4,
                         homogeneous=True)
        self._buttons = {}
        for name, label, tip in self._TABS:
            button = Gtk.Button(label=label)
            button.add_css_class("sq-tab")
            button.set_tooltip_text(tip)
            button.connect("clicked", lambda _b, n=name: self.emit("nav-toggled", n))
            self.append(button)
            self._buttons[name] = button

        self._rows = {}
        self._open_sources = set()
        self._sources_btn = Gtk.Button(label="SOURCES")
        self._sources_btn.add_css_class("sq-tab")
        self._sources_btn.set_tooltip_text("Media sources")
        self._sources_btn.set_visible(False)
        self._pop = Gtk.Popover()
        self._pop.set_parent(self._sources_btn)
        self._sources_btn.connect("clicked", lambda _b: self._pop.popup())
        # A popover parented to a widget must be unparented before it dies.
        self.connect("destroy", lambda _w: self._pop.unparent())
        self.append(self._sources_btn)

    def set_sources(self, entries):
        self._rows = {}
        self._open_sources &= {e["name"] for e in entries}
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for e in entries:
            dot = Gtk.Label(label="\u25cb")
            text = Gtk.Label(label=e["label"], xalign=0.0)
            inner = Gtk.Box(spacing=8)
            inner.append(dot)
            inner.append(text)
            btn = Gtk.Button()
            btn.set_child(inner)
            btn.add_css_class("flat")
            btn.add_css_class("sq-source-row")
            if not e["available"]:
                btn.add_css_class("sq-source-off")
                btn.set_tooltip_text(e["hint"])
            btn.connect("clicked", lambda _b, n=e["name"]: self._pick(n))
            box.append(btn)
            if e["name"] in self._open_sources:
                dot.set_text("\u25cf")
            self._rows[e["name"]] = (btn, dot)
        self._pop.set_child(box)
        if self._open_sources:
            self._sources_btn.add_css_class("active")
        else:
            self._sources_btn.remove_css_class("active")
        self._sources_btn.set_visible(bool(entries))

    def _pick(self, name):
        self._pop.popdown()
        self.emit("nav-toggled", name)

    def set_open(self, name: str, is_open: bool):
        if name in self._buttons:
            if is_open:
                self._buttons[name].add_css_class("active")
            else:
                self._buttons[name].remove_css_class("active")
        elif name in self._rows:
            self._rows[name][1].set_text("\u25cf" if is_open else "\u25cb")
            if is_open:
                self._open_sources.add(name)
            else:
                self._open_sources.discard(name)
            if self._open_sources:
                self._sources_btn.add_css_class("active")
            else:
                self._sources_btn.remove_css_class("active")


class SeekBar(Gtk.Box):
    """Position scale for items with a known duration. The user's own moves
    are not overwritten by the 1 Hz status poll for HOLD seconds."""

    __gsignals__ = {
        'seek-requested': (GObject.SignalFlags.RUN_LAST, None, (float,)),
    }
    HOLD = 1.5

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.add_css_class("seek-bar")
        self._hold_until = 0.0
        self._scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 1)
        self._scale.set_draw_value(False)
        self._scale.set_hexpand(True)
        self._scale.connect("change-value", self._on_change_value)
        self._time = Gtk.Label(label="")
        self._time.add_css_class("seek-time")
        self.append(self._scale)
        self.append(self._time)
        self.set_visible(False)

    def _on_change_value(self, _scale, _scroll, value):
        self._hold_until = time.monotonic() + self.HOLD
        self.emit("seek-requested", float(value))
        return False

    def set_state(self, position, duration):
        if not duration or duration <= 0 or position is None:
            self.set_visible(False)
            return
        self.set_visible(True)
        self._time.set_text(
            f"{format_duration(position) or '0:00'} / {format_duration(duration)}")
        if time.monotonic() < self._hold_until:
            return
        self._scale.set_range(0, duration)
        self._scale.set_value(min(position, duration))


class TimelineBar(Gtk.Box):
    """Radio timeshift: the buffered hour as a strip with a playhead, a
    behind-live readout, back/forward 15 s and a LIVE button. Drawn as a
    timeline (buffered span, playhead tick, 10-minute marks from the live
    edge), not a scrubber dot. Hidden until there is audio to move into."""

    __gsignals__ = {
        'seek-requested': (GObject.SignalFlags.RUN_LAST, None, (float,)),
        'seek-relative': (GObject.SignalFlags.RUN_LAST, None, (float,)),
        'go-live': (GObject.SignalFlags.RUN_LAST, None, ()),
    }
    HOLD = 1.5
    MIN_BUFFER = 10.0
    LIVE_WITHIN = 3.0
    STEP = 15.0
    MARK_EVERY = 600.0

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.add_css_class("timeline-bar")
        self._hold_until = 0.0
        self._ts = None

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._back = Gtk.Button(label="−15")
        self._fwd = Gtk.Button(label="+15")
        self._live = Gtk.Button(label="LIVE")
        for b in (self._back, self._fwd, self._live):
            b.add_css_class("timeline-btn")
        self._back.connect("clicked", lambda _b: self.emit("seek-relative", -self.STEP))
        self._fwd.connect("clicked", lambda _b: self.emit("seek-relative", self.STEP))
        self._live.connect("clicked", lambda _b: self.emit("go-live"))

        self._strip = Gtk.DrawingArea()
        self._strip.set_hexpand(True)
        self._strip.set_content_height(16)
        self._strip.set_draw_func(self._on_draw)
        click = Gtk.GestureClick.new()
        click.connect("pressed", lambda _g, _n, x, _y: self._seek_to_x(x))
        self._strip.add_controller(click)
        drag = Gtk.GestureDrag.new()
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-begin", lambda _g, x, _y: self._seek_to_x(x))
        self._strip.add_controller(drag)
        self._drag_start_x = 0.0

        row.append(self._back)
        row.append(self._strip)
        row.append(self._fwd)
        row.append(self._live)
        self._label = Gtk.Label(label="")
        self._label.add_css_class("seek-time")
        self.append(row)
        self.append(self._label)
        self.set_visible(False)

    def behind(self) -> float:
        ts = self._ts
        return max(0.0, ts["end"] - ts["pos"]) if ts else 0.0

    def set_state(self, ts):
        if not ts or ts["end"] - ts["start"] < self.MIN_BUFFER:
            self._ts = None
            self.set_visible(False)
            return
        self.set_visible(True)
        if time.monotonic() >= self._hold_until:
            self._ts = ts
        else:
            self._ts = dict(ts, pos=self._ts["pos"] if self._ts else ts["pos"])
        behind = self.behind()
        at_live = behind < self.LIVE_WITHIN
        self._label.set_text(
            "LIVE" if at_live else f"−{format_duration(behind)} behind live")
        self._live.set_sensitive(not at_live)
        self._strip.queue_draw()

    def _x_to_pos(self, x: float):
        ts = self._ts
        w = self._strip.get_width()
        if not ts or w <= 0:
            return None
        frac = max(0.0, min(1.0, x / w))
        return ts["start"] + frac * (ts["end"] - ts["start"])

    def _seek_to_x(self, x: float):
        pos = self._x_to_pos(x)
        if pos is None:
            return
        self._hold_until = time.monotonic() + self.HOLD
        self._ts = dict(self._ts, pos=pos)
        self._strip.queue_draw()
        self.emit("seek-requested", pos)

    def _on_drag_update(self, gesture, dx, _dy):
        ok, sx, _sy = gesture.get_start_point()
        if ok:
            self._seek_to_x(sx + dx)

    def _on_draw(self, area, cr, width, height, user_data=None):
        ts = self._ts
        colors = palette.load()
        trough = _hex_to_rgb_floats(colors.get('DIM', '#1a1828'))
        span = _hex_to_rgb_floats(colors.get('WING', '#393552'))
        head = _hex_to_rgb_floats(colors.get('SCORE', '#e0def4'))
        cr.set_source_rgba(*trough, 1.0)
        cr.rectangle(0, 2, width, height - 4)
        cr.fill()
        if not ts:
            return
        total = ts["end"] - ts["start"]
        px = lambda t: (t - ts["start"]) / total * width  # noqa: E731
        cr.set_source_rgba(*span, 1.0)
        cr.rectangle(0, 2, px(ts["pos"]), height - 4)
        cr.fill()
        cr.set_source_rgba(*head, 0.45)
        t = ts["end"] - self.MARK_EVERY
        while t > ts["start"]:
            cr.rectangle(px(t) - 0.5, height - 6, 1, 4)
            t -= self.MARK_EVERY
        cr.fill()
        cr.set_source_rgba(*head, 1.0)
        cr.rectangle(min(max(px(ts["pos"]) - 1.5, 0), width - 3), 0, 3, height)
        cr.fill()
