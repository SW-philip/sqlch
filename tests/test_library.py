import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlch_gui import library


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


class TestFavorite(_LibraryBackedTestCase):
    def setUp(self):
        super().setUp()
        library.add_url("Test Station", "http://example.com/stream")
        self._station_id = library.get_station_list()[0]["id"]

    def test_favorite_defaults_false(self):
        station = library.get_station_list()[0]
        self.assertFalse(station["favorite"])

    def test_set_favorite_true_updates_station(self):
        self.assertTrue(library.set_favorite(self._station_id, True))
        station = library.get_station_list()[0]
        self.assertTrue(station["favorite"])

    def test_set_favorite_survives_reload(self):
        library.set_favorite(self._station_id, True)
        data = json.loads(self._lib_path.read_text())
        self.assertTrue(data["stations"][0]["favorite"])

    def test_set_favorite_false_clears_it(self):
        library.set_favorite(self._station_id, True)
        library.set_favorite(self._station_id, False)
        self.assertFalse(library.get_station_list()[0]["favorite"])

    def test_set_favorite_unknown_id_returns_false(self):
        self.assertFalse(library.set_favorite("no-such-id", True))


if __name__ == "__main__":
    unittest.main()
