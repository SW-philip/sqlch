import unittest

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from sqlch_gui.ui.header import SNARK, Header, next_connected


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


class TestNavTabs(unittest.TestCase):
    def _nav(self):
        from sqlch_gui.ui.controls import NavColumn
        return NavColumn()

    def test_three_text_tabs_mini_active(self):
        nav = self._nav()
        self.assertEqual(nav.active, "mini")
        labels = {name: b.get_label() for name, b in nav._buttons.items()}
        self.assertEqual(labels, {"mini": "NOW", "library": "LIBRARY", "discover": "DISCOVER"})
        for name, b in nav._buttons.items():
            self.assertTrue(b.has_css_class("sq-tab"))
            self.assertEqual(b.has_css_class("active"), name == "mini")

    def test_click_selects_and_emits(self):
        nav = self._nav()
        seen = []
        nav.connect("nav-selected", lambda _n, name: seen.append(name))
        nav._buttons["library"].emit("clicked")
        self.assertEqual(nav.active, "library")
        self.assertEqual(seen, ["library"])
        nav._buttons["library"].emit("clicked")  # re-click is a no-op
        self.assertEqual(seen, ["library"])

    def test_set_active_syncs_highlight_without_emitting(self):
        nav = self._nav()
        seen = []
        nav.connect("nav-selected", lambda _n, name: seen.append(name))
        nav.set_active("discover")
        self.assertEqual(nav.active, "discover")
        self.assertTrue(nav._buttons["discover"].has_css_class("active"))
        self.assertFalse(nav._buttons["mini"].has_css_class("active"))
        self.assertEqual(seen, [])


class TestNowPlayingWiring(unittest.TestCase):
    def _panel(self):
        from sqlch_gui.ui.now_playing import NowPlayingPanel
        return NowPlayingPanel(None)

    def test_idle_state_lands_in_the_header(self):
        p = self._panel()
        self.assertEqual(p.header.track.get_text(), "Not Playing")
        self.assertTrue(p.header.station.get_text().startswith("STATION"))
        self.assertFalse(hasattr(p, "lbl_station"))
        self.assertFalse(hasattr(p, "lbl_now_playing"))

    def test_set_connected_reaches_the_header(self):
        from sqlch_gui.ui.header import SNARK
        p = self._panel()
        p.set_connected(False)
        self.assertIn(p.header.station.get_text(), SNARK)
        p.set_connected(True)
        self.assertTrue(p.header.station.get_text().startswith("STATION"))

    def test_stale_dims_the_plate(self):
        p = self._panel()  # reset_ui() at construction marks the panel stale
        plate = p.header.station.get_parent().get_parent()
        self.assertTrue(plate.has_css_class("stale"))

    def test_nav_column_is_inside_the_header(self):
        p = self._panel()
        self.assertIs(p.nav_column.get_parent(), p.header)

    def test_previous_track_line_and_pills_stay_in_the_info_panel(self):
        p = self._panel()
        self.assertIsNotNone(p.lbl_previous)
        self.assertIsNotNone(p.pill_codec)


class TestNextConnected(unittest.TestCase):
    def test_reply_resets_and_connects(self):
        self.assertEqual(next_connected(5, True), (0, True))

    def test_single_miss_stays_connected(self):
        self.assertEqual(next_connected(0, False), (1, True))

    def test_second_consecutive_miss_disconnects(self):
        self.assertEqual(next_connected(1, False), (2, False))
        self.assertEqual(next_connected(2, False), (3, False))


class TestPreviousTracksReserveSpace(unittest.TestCase):
    def _panel(self):
        from sqlch_gui.ui.now_playing import NowPlayingPanel
        return NowPlayingPanel(None)

    def test_previous_block_is_always_visible_with_three_slots(self):
        p = self._panel()
        self.assertTrue(p.lbl_previous.get_visible())
        self.assertEqual(len(p._prev_rows), 3)

    def test_height_does_not_change_as_history_fills(self):
        p = self._panel()
        empty = p.lbl_previous.measure(Gtk.Orientation.VERTICAL, 300)[1]
        p._history.appendleft(("Artist", "A very long title " * 20))
        p._history.appendleft(("B", "T"))
        p._history.appendleft(("C", "T"))
        p._update_previous_line()
        full = p.lbl_previous.measure(Gtk.Orientation.VERTICAL, 300)[1]
        self.assertEqual(empty, full)

    def test_rows_render_history_and_clear_on_reset(self):
        p = self._panel()
        p._history.appendleft(("A", "T"))
        p._update_previous_line()
        self.assertEqual(p._prev_rows[0].get_text(), "1. A — T")
        self.assertEqual(p._prev_rows[1].get_text().strip(), "")
        p.reset_ui()
        self.assertEqual(p._prev_rows[0].get_text().strip(), "")

    def test_empty_history_while_playing_says_playing_now(self):
        p = self._panel()
        self.assertEqual(p._prev_rows[0].get_text().strip(), "")  # idle: blank
        p._cur_station_id = "wxpn"
        p._update_previous_line()
        self.assertEqual(p._prev_rows[0].get_text(), "It's playing now")
        p._history.appendleft(("A", "T"))
        p._update_previous_line()
        self.assertEqual(p._prev_rows[0].get_text(), "1. A — T")
        p.reset_ui()
        self.assertEqual(p._prev_rows[0].get_text().strip(), "")
