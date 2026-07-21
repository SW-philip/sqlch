"""Torn-ribbon banner and cut-flag pennant shapes for the fabric aesthetic.

GTK4 CSS has no ::before/::after pseudo-elements or clip-path, so the
triangular tails (ribbon) and notched flag point (pennant) that the design
calls for are drawn directly with Cairo, same idiom as controls.py/eq_strip.py.

Gtk.Overlay always paints overlay children on top of the main child, and
only the main child drives the widget's natural size. So the label (which
must be visible) is the overlay child, and the Cairo canvas (the shape,
which must render underneath the text) is the main child. The canvas has
no text of its own to size itself by, so its size is pulled from measuring
the label once up front and pinned with set_size_request().
"""

import math

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


class TornSeparator(Gtk.DrawingArea):
    """Torn-paper seam between the Now Playing sheet and the drawer.

    Reads as the ragged edge of the sheet where the drawer tucks under
    it; a short run of stitch dashes in the middle is the grab
    affordance. Purely visual -- the window owns the drag gesture and
    drawer state, this widget just draws the seam and swaps the
    grab/grabbing cursor.

    HORIZONTAL (the default) is a strip below Now Playing, torn along
    its bottom edge, for a drawer that drops down. VERTICAL is a strip
    beside Now Playing, torn along its edge facing the drawer, for a
    drawer that slides out to the side -- same construction, axes
    swapped.
    """

    _THICKNESS = 18
    _BODY = 8.0

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

    def _tear_points(self, width: float, height: float) -> list[tuple[float, float]]:
        # Depths and spacing are hashed from the tooth index (not random)
        # so the tear never shimmers between redraws.
        points = []
        if self._orientation == Gtk.Orientation.VERTICAL:
            y, i = 0.0, 0
            max_depth = width - 2.0
            while y < height:
                frac = abs(math.sin(i * 12.9898 + 4.1414))
                depth = self._BODY + 1.5 + frac * (max_depth - self._BODY - 1.5)
                points.append((width - depth, y))
                y += 9.0 * (0.7 + 0.6 * abs(math.sin(i * 7.31)))
                i += 1
            points.append((width - self._BODY - 1.5, float(height)))
        else:
            x, i = 0.0, 0
            max_depth = height - 2.0
            while x < width:
                frac = abs(math.sin(i * 12.9898 + 4.1414))
                points.append((x, self._BODY + 1.5 + frac * (max_depth - self._BODY - 1.5)))
                x += 9.0 * (0.7 + 0.6 * abs(math.sin(i * 7.31)))
                i += 1
            points.append((float(width), self._BODY + 1.5))
        return points

    def _on_draw(self, area, cr, width, height, user_data=None):
        colors = palette.load()
        paper = _hex_to_rgb_floats(colors.get('STAGE', '#f9f6f0'))
        shadow = _hex_to_rgb_floats(colors.get('SHADOW', '#0f0e17'))
        thread = _hex_to_rgb_floats(colors.get('BAR', '#6a6a6a'))

        points = self._tear_points(width, height)
        vertical = self._orientation == Gtk.Orientation.VERTICAL

        def tear_path(offset: float):
            if vertical:
                cr.move_to(width, 0)
                cr.line_to(width - self._BODY - offset, 0)
                for px, py in points:
                    cr.line_to(px - offset, py)
                cr.line_to(width, height)
            else:
                cr.move_to(0, 0)
                cr.line_to(0, self._BODY + offset)
                for px, py in points:
                    cr.line_to(px, py + offset)
                cr.line_to(width, 0)
            cr.close_path()

        # Soft shadow peeking out under the tear, then the paper on top
        cr.set_source_rgba(*shadow, 0.25)
        tear_path(1.5)
        cr.fill()
        cr.set_source_rgba(*paper, 1.0)
        tear_path(0.0)
        cr.fill()

        # Centered stitch dashes: the "grab here" cue, same thread
        # vocabulary as ThreadSlider/RecordBubble
        cr.save()
        cr.set_dash([4.0, 3.5])
        cr.set_line_width(1.6)
        cr.set_source_rgba(*thread, 0.8)
        if vertical:
            cx = width - self._BODY / 2.0 - 0.5
            cr.move_to(cx, height / 2.0 - 23.0)
            cr.line_to(cx, height / 2.0 + 23.0)
        else:
            cy = self._BODY / 2.0 + 0.5
            cr.move_to(width / 2.0 - 23.0, cy)
            cr.line_to(width / 2.0 + 23.0, cy)
        cr.stroke()
        cr.restore()


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
