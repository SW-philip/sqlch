import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from sqlch_gui import library


def _make_panel():
    from sqlch_gui.ui.station_list import StationListPanel
    return StationListPanel(None)


class _LibraryBackedTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._lib_path = Path(self._tmp.name) / "library.json"
        self._freq_path = Path(self._tmp.name) / "freq_cache.json"
        self._lib_patch = patch.object(library, "LIBRARY_JSON", self._lib_path)
        self._freq_patch = patch.object(library, "FREQ_CACHE_JSON", self._freq_path)
        self._lib_patch.start()
        self._freq_patch.start()

    def tearDown(self):
        self._lib_patch.stop()
        self._freq_patch.stop()
        self._tmp.cleanup()


class TestStationRowStarButton(_LibraryBackedTestCase):
    def test_row_star_button_reflects_favorite_state(self):
        library.add_url("Test Station", "http://example.com/stream")
        sid = library.get_station_list()[0]["id"]
        panel = _make_panel()
        row, live_lbl, mini_eq = panel._rows_map[sid][0]
        star = row.get_first_child()
        self.assertIsInstance(star, Gtk.Button)
        self.assertEqual(star.get_icon_name(), "non-starred-symbolic")

    def test_clicking_star_toggles_favorite_and_refreshes(self):
        library.add_url("Test Station", "http://example.com/stream")
        sid = library.get_station_list()[0]["id"]
        panel = _make_panel()
        panel.on_toggle_favorite(sid, False)
        self.assertTrue(library.get_station_list()[0]["favorite"])
        row, live_lbl, mini_eq = panel._rows_map[sid][0]
        star = row.get_first_child()
        self.assertEqual(star.get_icon_name(), "starred-symbolic")


def _iter_rows(list_box):
    row = list_box.get_first_child()
    while row is not None:
        yield row
        row = row.get_next_sibling()


def _is_banner(row):
    from sqlch_gui.ui.banner import RibbonBanner
    return isinstance(row.get_child(), RibbonBanner)


def _row_children(row):
    children = []
    child = row.get_child().get_first_child()
    while child is not None:
        children.append(child)
        child = child.get_next_sibling()
    return children


def _station_name(row):
    _star, _freq, body, *_rest = _row_children(row)
    return body.get_first_child().get_text()


class TestFavoritesSection(_LibraryBackedTestCase):
    def _add(self, name, url):
        library.add_url(name, url)
        return library.get_station_list()[-1]["id"]

    def test_no_favorites_section_when_none_favorited(self):
        self._add("Alpha", "http://a")
        panel = _make_panel()
        banners = [
            row.get_child().label.get_text()
            for row in _iter_rows(panel.list_box)
            if _is_banner(row)
        ]
        self.assertNotIn("★ FAVORITES", banners)

    def test_favorites_section_appears_first_when_populated(self):
        sid = self._add("Zeta", "http://z")
        library.set_favorite(sid, True)
        panel = _make_panel()
        first_row = panel.list_box.get_first_child()
        self.assertEqual(first_row.get_child().label.get_text(), "★ FAVORITES")

    def test_favorited_station_has_two_row_entries(self):
        sid = self._add("Zeta", "http://z")
        library.set_favorite(sid, True)
        panel = _make_panel()
        self.assertEqual(len(panel._rows_map[sid]), 2)

    def test_non_favorited_station_has_one_row_entry(self):
        sid = self._add("Alpha", "http://a")
        panel = _make_panel()
        self.assertEqual(len(panel._rows_map[sid]), 1)

    def test_favorites_sorted_alphabetically(self):
        sid_z = self._add("Zeta", "http://z")
        sid_a = self._add("Alpha", "http://a")
        library.set_favorite(sid_z, True)
        library.set_favorite(sid_a, True)
        panel = _make_panel()
        fav_banner = panel.list_box.get_first_child()
        first_station_row = fav_banner.get_next_sibling()
        second_station_row = first_station_row.get_next_sibling()
        self.assertEqual(_station_name(first_station_row), "Alpha")
        self.assertEqual(_station_name(second_station_row), "Zeta")


if __name__ == "__main__":
    unittest.main()
