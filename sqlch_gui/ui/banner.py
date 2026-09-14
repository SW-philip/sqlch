"""Section-rule headers, flat tag chips, and the drawer seam.

RibbonBanner and PennantTag were Cairo-drawn papercraft shapes (torn
ribbon tails, a cut-flag notch); they are now plain CSS-styled boxes.
TornSeparator still draws the drawer seam, but as a recessed hairline
groove with a short grab bar rather than a ragged tear.
"""

from typing import Callable

import cairo
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk
from .. import palette


def _hex_to_rgb_floats(hex_val: str) -> tuple[float, float, float]:
    h = hex_val.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return r, g, b


class RibbonBanner(Gtk.Box):
    """Section header: a hairline top-rule with a small engraved label,
    left-set. The rule IS the break -- no box frame around the group.

    When collapsible, a leading chevron shows expand/collapse state and a
    primary click anywhere on the banner toggles it, calling on_toggle
    with the new collapsed state.
    """

    _CHEVRON_OPEN = "▾ "
    _CHEVRON_CLOSED = "▸ "

    def __init__(
        self,
        text: str,
        gold: bool = False,
        collapsible: bool = False,
        collapsed: bool = False,
        on_toggle: Callable[[bool], None] | None = None,
    ):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_hexpand(True)
        self.add_css_class("section-rule")
        if gold:
            self.add_css_class("gold")
        self._text = text
        self._collapsible = collapsible
        self._collapsed = collapsed
        self._on_toggle = on_toggle
        self.label = Gtk.Label(xalign=0.0)
        self.label.set_hexpand(True)
        self.append(self.label)
        self._update_label()

        if collapsible:
            click = Gtk.GestureClick()
            click.set_button(Gdk.BUTTON_PRIMARY)
            click.connect("released", self._on_click)
            self.add_controller(click)

    def _update_label(self):
        prefix = ""
        if self._collapsible:
            prefix = self._CHEVRON_CLOSED if self._collapsed else self._CHEVRON_OPEN
        self.label.set_text(prefix + self._text.upper())

    def _on_click(self, gesture, n_press, x, y):
        self._collapsed = not self._collapsed
        self._update_label()
        if self._on_toggle:
            self._on_toggle(self._collapsed)

    def set_text(self, text: str):
        self._text = text
        self._update_label()

    def set_collapsed(self, collapsed: bool):
        self._collapsed = collapsed
        self._update_label()


class PennantTag(Gtk.Box):
    """Flat tag chip (was a Cairo cut-flag pennant). `.label` is kept as a
    real child so station_list's filter can read its text."""

    def __init__(self, text: str, country: bool = False):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.add_css_class("tag-chip")
        if country:
            self.add_css_class("country")
        self.label = Gtk.Label(label=text)
        self.append(self.label)


class TornSeparator(Gtk.DrawingArea):
    """Drawer seam between the Now Playing sheet and the drawer: a recessed
    hairline groove with a short centered grab bar.

    Purely visual -- the window owns the drag gesture and drawer state;
    this widget just draws the seam and swaps the grab/grabbing cursor.
    VERTICAL is a strip beside Now Playing (side drawer); HORIZONTAL a
    strip below it (drop drawer) -- same construction, axes swapped.
    """

    _THICKNESS = 18
    _GRAB = 23.0

    def __init__(self, orientation: Gtk.Orientation = Gtk.Orientation.HORIZONTAL):
        super().__init__()
        self._orientation = orientation
        if orientation == Gtk.Orientation.VERTICAL:
            self.set_vexpand(True)
            self.set_content_width(self._THICKNESS)
        else:
            self.set_hexpand(True)
            self.set_content_height(self._THICKNESS)
        self.set_draw_func(self._on_draw)
        self.set_cursor_from_name("grab")
        self.set_tooltip_text("Drag to open the drawer")

    def set_grabbed(self, grabbed: bool):
        self.set_cursor_from_name("grabbing" if grabbed else "grab")

    def _on_draw(self, area, cr, width, height, user_data=None):
        colors = palette.load()
        stage = _hex_to_rgb_floats(colors.get('STAGE', '#2a273f'))
        score = _hex_to_rgb_floats(colors.get('SCORE', '#e0def4'))
        lyric = _hex_to_rgb_floats(colors.get('LYRIC', '#c9c5da'))
        vertical = self._orientation == Gtk.Orientation.VERTICAL

        cr.set_source_rgba(*stage, 1.0)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        # Faint full-length hairline down the seam's centerline.
        cr.set_line_width(1.0)
        cr.set_source_rgba(*score, 0.15)
        if vertical:
            x = round(width / 2.0) + 0.5
            cr.move_to(x, 4.0)
            cr.line_to(x, height - 4.0)
        else:
            y = round(height / 2.0) + 0.5
            cr.move_to(4.0, y)
            cr.line_to(width - 4.0, y)
        cr.stroke()

        # Short, more-opaque grab bar at the center.
        cr.set_line_width(2.0)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(*lyric, 0.55)
        if vertical:
            cx = width / 2.0
            cr.move_to(cx, height / 2.0 - self._GRAB)
            cr.line_to(cx, height / 2.0 + self._GRAB)
        else:
            cy = height / 2.0
            cr.move_to(width / 2.0 - self._GRAB, cy)
            cr.line_to(width / 2.0 + self._GRAB, cy)
        cr.stroke()
