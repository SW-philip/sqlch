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
        names = dock_state.NAMES + ("local",)
        s = dock_state.default_state(names)
        s["radio"] = {"open": True, "placed": {"mode": "np", "dx": -330, "dy": 12}}
        s["local"] = {"open": False, "placed": {"mode": "free", "x": 40, "y": 60}}
        dock_state.save(s, self.path)
        self.assertEqual(dock_state.load(self.path, names=names), s)

    def test_corrupt_file_gives_defaults(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json")
        self.assertEqual(dock_state.load(self.path), dock_state.default_state())

    def test_bad_entries_are_sanitized_individually(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({
            "radio": {"open": True, "placed": {"mode": "np", "dx": "x"}},
            "local": {"open": True, "placed": {"mode": "free", "x": 5, "y": 6}},
            "bogus": {"open": True},
        }))
        s = dock_state.load(self.path, names=dock_state.NAMES + ("local",))
        self.assertEqual(s["radio"], {"open": True, "placed": None})
        self.assertEqual(s["local"]["placed"], {"mode": "free", "x": 5, "y": 6})
        self.assertNotIn("bogus", s)

    def test_old_library_discover_state_migrates_to_radio(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({
            "library": {"open": False, "placed": {"mode": "free", "x": 7, "y": 8}},
            "discover": {"open": True, "placed": None},
        }))
        s = dock_state.load(self.path)
        self.assertEqual(s["radio"], {"open": True, "placed": {"mode": "free", "x": 7, "y": 8}})

    def test_existing_radio_state_wins_over_old_keys(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({
            "radio": {"open": False, "placed": None},
            "library": {"open": True, "placed": None},
        }))
        self.assertEqual(dock_state.load(self.path)["radio"], {"open": False, "placed": None})


class TestNowPlayingPosition(unittest.TestCase):
    def setUp(self):
        self.path = pathlib.Path(tempfile.mkdtemp()) / "windows.json"

    def _load_raw(self, raw):
        self.path.write_text(json.dumps(raw))
        return dock_state.load(self.path)

    def test_default_is_none(self):
        self.assertIsNone(dock_state.default_state()["np"])
        self.assertNotIn("np", dock_state.NAMES)

    def test_round_trip(self):
        s = dock_state.default_state()
        s["np"] = {"x": 900, "y": 48}
        dock_state.save(s, self.path)
        self.assertEqual(dock_state.load(self.path)["np"], {"x": 900, "y": 48})

    def test_missing_or_corrupt_np_is_none(self):
        self.assertIsNone(self._load_raw({"radio": {"open": True}})["np"])
        self.assertIsNone(self._load_raw({"np": "top-right"})["np"])
        self.assertIsNone(self._load_raw({"np": {"x": 5}})["np"])

    def test_non_int_coordinates_are_none(self):
        self.assertIsNone(self._load_raw({"np": {"x": 1.5, "y": 2}})["np"])
        self.assertIsNone(self._load_raw({"np": {"x": "1", "y": 2}})["np"])
        self.assertIsNone(self._load_raw({"np": {"x": True, "y": 2}})["np"])

    def test_extra_keys_are_dropped(self):
        self.assertEqual(self._load_raw({"np": {"x": 1, "y": 2, "z": 3}})["np"],
                         {"x": 1, "y": 2})


class TestExtraNames(unittest.TestCase):
    def setUp(self):
        self.path = pathlib.Path(tempfile.mkdtemp()) / "windows.json"
        self.names = dock_state.NAMES + ("local",)

    def test_extra_name_defaults_closed(self):
        s = dock_state.load(self.path, names=self.names)
        self.assertEqual(s["local"], {"open": False, "placed": None})

    def test_extra_name_round_trips(self):
        s = dock_state.default_state(self.names)
        s["local"] = {"open": True, "placed": {"mode": "free", "x": 5, "y": 6}}
        dock_state.save(s, self.path)
        self.assertEqual(dock_state.load(self.path, names=self.names)["local"], s["local"])

    def test_unknown_saved_name_is_dropped(self):
        self.path.write_text(json.dumps({"ghost": {"open": True}}))
        self.assertNotIn("ghost", dock_state.load(self.path, names=self.names))

    def test_default_names_ignore_saved_extra(self):
        self.path.write_text(json.dumps({"local": {"open": True}}))
        self.assertNotIn("local", dock_state.load(self.path))
