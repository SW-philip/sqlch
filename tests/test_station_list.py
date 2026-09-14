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
        row, live_lbl, mini_eq = panel._rows_map[sid]
        star = row.get_first_child()
        self.assertIsInstance(star, Gtk.Button)
        self.assertEqual(star.get_icon_name(), "non-starred-symbolic")

    def test_clicking_star_toggles_favorite_and_refreshes(self):
        library.add_url("Test Station", "http://example.com/stream")
        sid = library.get_station_list()[0]["id"]
        panel = _make_panel()
        panel.on_toggle_favorite(sid, False)
        self.assertTrue(library.get_station_list()[0]["favorite"])
        row, live_lbl, mini_eq = panel._rows_map[sid]
        star = row.get_first_child()
        self.assertEqual(star.get_icon_name(), "starred-symbolic")


if __name__ == "__main__":
    unittest.main()
