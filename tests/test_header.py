import unittest

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from sqlch_gui.ui.header import SNARK, Header


def _header():
    return Header(Gtk.Box(), 300)


class TestHeader(unittest.TestCase):
    def test_nameplate_and_css_classes(self):
        h = _header()
        self.assertTrue(h.has_css_class("sq-header"))
        self.assertTrue(h.track.has_css_class("sq-track"))
        self.assertTrue(h.station.has_css_class("sq-station"))

    def test_text_labels_cannot_widen_the_popup(self):
        h = _header()
        for label in (h.track, h.station):
            self.assertEqual(label.get_max_width_chars(), 1)
            self.assertEqual(label.get_width_chars(), 1)
            self.assertTrue(label.get_single_line_mode())
            self.assertFalse(label.get_wrap())

    def test_track_and_station_text(self):
        h = _header()
        h.set_track("<b>A — B</b>")
        h.set_station("<b>STATION</b>  WXPN")
        self.assertEqual(h.track.get_text(), "A — B")
        self.assertEqual(h.station.get_text(), "STATION  WXPN")

    def test_disconnect_shows_snark_and_reconnect_restores_station(self):
        h = _header()
        h.set_station("<b>STATION</b>  WXPN")
        h.set_connected(False)
        self.assertIn(h.station.get_text(), SNARK)
        h.set_connected(True)
        self.assertEqual(h.station.get_text(), "STATION  WXPN")

    def test_station_updates_while_disconnected_do_not_clobber_snark(self):
        h = _header()
        h.set_connected(False)
        snark = h.station.get_text()
        h.set_station("<b>STATION</b>  NEW")
        self.assertEqual(h.station.get_text(), snark)
        h.set_connected(True)
        self.assertEqual(h.station.get_text(), "STATION  NEW")

    def test_snark_is_stable_within_one_disconnect(self):
        h = _header()
        h.set_connected(False)
        first = h.station.get_text()
        h.set_connected(False)
        self.assertEqual(h.station.get_text(), first)

    def test_offline_and_stale_classes(self):
        h = _header()
        plate = h.station.get_parent().get_parent()
        h.set_connected(False)
        self.assertTrue(plate.has_css_class("offline"))
        h.set_connected(True)
        self.assertFalse(plate.has_css_class("offline"))
        h.set_stale(True)
        self.assertTrue(plate.has_css_class("stale"))
        h.set_stale(False)
        self.assertFalse(plate.has_css_class("stale"))

    def test_tabs_widget_is_hosted_and_classed(self):
        tabs = Gtk.Box()
        h = Header(tabs, 300)
        self.assertTrue(tabs.has_css_class("sq-tabs"))
        self.assertIs(tabs.get_parent(), h)
