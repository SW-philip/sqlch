"""Top of the popup: nameplate, live plate (LED + track + station), and the
folder-tab row (hosted, not owned -- NavColumn keeps its own signal/API).
Modeled on uniremote's header (~/nixos/pkgs/uniremote/.../header.py)."""

import random

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Pango

SNARK = (
    "Daemon's gone quiet.",
    "Nobody's spinning records.",
    "Dead air. The bad kind.",
    "sqlch is not answering.",
    "The transmitter is out to lunch.",
)


def _plate_label(css_class: str) -> Gtk.Label:
    # width_chars/max_width_chars=1 + hexpand: the label takes whatever width
    # the pinned header gives it instead of dragging the popup wider with a
    # long title (see the info-panel note in now_playing.py).
    label = Gtk.Label(xalign=0.0, hexpand=True)
    label.set_ellipsize(Pango.EllipsizeMode.END)
    label.set_single_line_mode(True)
    label.set_width_chars(1)
    label.set_max_width_chars(1)
    label.add_css_class(css_class)
    return label


class Header(Gtk.Box):
    def __init__(self, tabs: Gtk.Widget, width: int):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("sq-header")
        self.set_size_request(width, -1)
        self._connected = True
        self._station_markup = ""

        nameplate = Gtk.Label(label="SQLCH", xalign=0.0)
        nameplate.add_css_class("sq-nameplate")
        self.append(nameplate)

        led = Gtk.Box(valign=Gtk.Align.CENTER)
        led.add_css_class("sq-led")
        self.track = _plate_label("sq-track")
        self.station = _plate_label("sq-station")
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        text.append(self.track)
        text.append(self.station)
        self._plate = Gtk.Box(spacing=10)
        self._plate.add_css_class("sq-plate")
        self._plate.append(led)
        self._plate.append(text)
        self.append(self._plate)

        tabs.add_css_class("sq-tabs")
        self.append(tabs)

    def set_track(self, markup: str) -> None:
        self.track.set_markup(markup)

    def set_station(self, markup: str) -> None:
        self._station_markup = markup
        if self._connected:
            self.station.set_markup(markup)

    def set_connected(self, connected: bool) -> None:
        if connected == self._connected:
            return
        self._connected = connected
        if connected:
            self._plate.remove_css_class("offline")
            self.station.set_markup(self._station_markup)
        else:
            self._plate.add_css_class("offline")
            snark = GLib.markup_escape_text(random.choice(SNARK))
            self.station.set_markup(f"<i>{snark}</i>")

    def set_stale(self, stale: bool) -> None:
        if stale:
            self._plate.add_css_class("stale")
        else:
            self._plate.remove_css_class("stale")
