import unittest

from sqlch_gui.ui.tooltips import item_tooltip, station_tooltip


class TestItemTooltip(unittest.TestCase):
    def test_title_only(self):
        self.assertEqual(item_tooltip({"title": "Song"}), "Song")

    def test_no_title_is_none(self):
        self.assertIsNone(item_tooltip({"title": ""}))
        self.assertIsNone(item_tooltip({}))

    def test_metadata_line_skips_empty_parts(self):
        tip = item_tooltip({"title": "T", "artist": "A", "album": None,
                            "date": 1792108800, "duration": 125})
        self.assertEqual(tip, "T\nA · Oct 16, 2026 · 2:05")

    def test_description_after_blank_line(self):
        tip = item_tooltip({"title": "T", "artist": "A", "description": "About it"})
        self.assertEqual(tip, "T\nA\n\nAbout it")

    def test_description_truncated_to_300(self):
        tip = item_tooltip({"title": "T", "description": "x" * 400})
        desc = tip.split("\n\n", 1)[1]
        self.assertEqual(len(desc), 300)
        self.assertTrue(desc.endswith("…"))

    def test_folder_has_no_description(self):
        tip = item_tooltip({"title": "Show", "kind": "folder", "artist": "Net",
                            "description": "ignored"})
        self.assertEqual(tip, "Show\nNet")


class TestStationTooltip(unittest.TestCase):
    ST = {"name": "KEXP", "group": "Indie", "frequency": "90.3 FM"}

    def test_static(self):
        self.assertEqual(station_tooltip(self.ST), "KEXP\nIndie · 90.3")

    def test_live_line(self):
        self.assertEqual(station_tooltip(self.ST, "♫ Band — Song"),
                         "KEXP\nIndie · 90.3\n♫ Band — Song")

    def test_missing_group_and_freq(self):
        self.assertEqual(station_tooltip({"name": "X"}), "X\nUnsorted · 0.0")
