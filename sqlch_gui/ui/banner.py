"""Torn-ribbon banner and cut-flag pennant shapes for the fabric aesthetic.

GTK4 CSS has no ::before/::after pseudo-elements or clip-path, so the
triangular tails (ribbon) and notched flag point (pennant) that the design
calls for are drawn directly with Cairo, same idiom as knob.py/eq_strip.py.

Gtk.Overlay always paints overlay children on top of the main child, and
only the main child drives the widget's natural size. So the label (which
must be visible) is the overlay child, and the Cairo canvas (the shape,
which must render underneath the text) is the main child. The canvas has
no text of its own to size itself by, so its size is pulled from measuring
the label once up front and pinned with set_size_request().
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from .. import palette


def _hex_to_rgb_floats(hex_val: str) -> tuple[float, float, float]:
    h = hex_val.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return r, g, b


def _shade(r: float, g: float, b: float, factor: float) -> tuple[float, float, float]:
    return r * factor, g * factor, b * factor


class RibbonBanner(Gtk.Overlay):
    """Section-header banner with a torn-ribbon shape (small triangle tails)."""

    TAIL_H = 6.0

    def __init__(self, text: str, gold: bool = False):
        super().__init__()
        self._gold = gold

        self.label = Gtk.Label(label=text.upper(), xalign=0.0)
        self.label.add_css_class("ribbon-label")
        self.label.set_margin_start(14)
        self.label.set_margin_end(14)
        self.label.set_margin_top(5)
        self.label.set_margin_bottom(4)
        self.label.set_valign(Gtk.Align.START)
        self.label.set_halign(Gtk.Align.FILL)

        self.canvas = Gtk.DrawingArea()
        self.canvas.set_draw_func(self._on_draw)
        self.set_child(self.canvas)
        self.add_overlay(self.label)

        self._resize_canvas()

    def set_text(self, text: str):
        self.label.set_text(text.upper())
        self._resize_canvas()
        self.canvas.queue_draw()

    def _resize_canvas(self):
        _min_w, nat_w, _mb, _nb = self.label.measure(Gtk.Orientation.HORIZONTAL, -1)
        _min_h, nat_h, _mb, _nb = self.label.measure(Gtk.Orientation.VERTICAL, nat_w)
        self.canvas.set_size_request(nat_w, nat_h + int(self.TAIL_H))

    def _on_draw(self, area, cr, width, height, user_data=None):
        colors = palette.load()
        body_hex = colors.get('ROOT', '#f4b84b') if self._gold else colors.get('BAR', '#6a6a6a')
        r, g, b = _hex_to_rgb_floats(body_hex)
        tr, tg, tb = _shade(r, g, b, 0.55)

        body_h = max(0.0, height - self.TAIL_H)

        cr.set_source_rgba(r, g, b, 1.0)
        cr.rectangle(0, 0, width, body_h)
        cr.fill()

        cr.set_source_rgba(tr, tg, tb, 1.0)
        cr.move_to(0, body_h)
        cr.line_to(6, body_h)
        cr.line_to(0, height)
        cr.close_path()
        cr.fill()

        cr.move_to(width, body_h)
        cr.line_to(width - 6, body_h)
        cr.line_to(width, height)
        cr.close_path()
        cr.fill()


class PennantTag(Gtk.Overlay):
    """Cut-flag pennant shape, replacing rounded-pill tag chips."""

    NOTCH = 8.0

    def __init__(self, text: str, country: bool = False):
        super().__init__()
        self._country = country

        self.label = Gtk.Label(label=text)
        self.label.add_css_class("pennant-label")
        self.label.set_margin_start(7)
        self.label.set_margin_end(4 + int(self.NOTCH))
        self.label.set_margin_top(3)
        self.label.set_margin_bottom(3)
        self.label.set_valign(Gtk.Align.FILL)
        self.label.set_halign(Gtk.Align.FILL)

        self.canvas = Gtk.DrawingArea()
        self.canvas.set_draw_func(self._on_draw)
        self.set_child(self.canvas)
        self.add_overlay(self.label)

        min_w, nat_w, _mb, _nb = self.label.measure(Gtk.Orientation.HORIZONTAL, -1)
        _min_h, nat_h, _mb, _nb = self.label.measure(Gtk.Orientation.VERTICAL, nat_w)
        self.canvas.set_size_request(nat_w, nat_h)

    def _on_draw(self, area, cr, width, height, user_data=None):
        colors = palette.load()
        body_hex = colors.get('SOTTO', '#d5a66d') if self._country else colors.get('BAR', '#6a6a6a')
        r, g, b = _hex_to_rgb_floats(body_hex)
        cr.set_source_rgba(r, g, b, 1.0)

        notch = min(self.NOTCH, width * 0.5)
        cr.move_to(0, 0)
        cr.line_to(width - notch, 0)
        cr.line_to(width, height / 2.0)
        cr.line_to(width - notch, height)
        cr.line_to(0, height)
        cr.close_path()
        cr.fill()
