# tests/test_dock_state.py
import json
import pathlib
import tempfile
import unittest

from sqlch_gui.ui import dock_state


class TestDockState(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.path = self.tmp / "sub" / "windows.json"

    def test_missing_file_gives_defaults(self):
        self.assertEqual(dock_state.load(self.path), dock_state.default_state())

    def test_round_trip(self):
        s = dock_state.default_state()
        s["library"] = {"open": True, "placed": {"mode": "np", "dx": -330, "dy": 12}}
        s["discover"] = {"open": False, "placed": {"mode": "free", "x": 40, "y": 60}}
        dock_state.save(s, self.path)
        self.assertEqual(dock_state.load(self.path), s)

    def test_corrupt_file_gives_defaults(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json")
        self.assertEqual(dock_state.load(self.path), dock_state.default_state())

    def test_bad_entries_are_sanitized_individually(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({
            "library": {"open": True, "placed": {"mode": "np", "dx": "x"}},
            "discover": {"open": True, "placed": {"mode": "free", "x": 5, "y": 6}},
            "bogus": {"open": True},
        }))
        s = dock_state.load(self.path)
        self.assertEqual(s["library"], {"open": True, "placed": None})
        self.assertEqual(s["discover"]["placed"], {"mode": "free", "x": 5, "y": 6})
        self.assertNotIn("bogus", s)
