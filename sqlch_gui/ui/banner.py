"""Section-rule headers and flat tag chips.

RibbonBanner and PennantTag were Cairo-drawn papercraft shapes (torn
ribbon tails, a cut-flag notch); they are now plain CSS-styled boxes.
"""

from typing import Callable

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk


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

