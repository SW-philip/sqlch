import unittest
from unittest import mock

from sqlch import sources
from sqlch.sources.base import Target, make_item


class TestMakeItem(unittest.TestCase):
    def test_defaults(self):
        item = make_item("local", "a/b.mp3", "B")
        self.assertEqual(item, {
            "source": "local", "id": "a/b.mp3", "title": "B", "artist": None,
            "album": None, "art": None, "duration": None, "kind": "track",
            "path": None})

    def test_folder_requires_path(self):
        with self.assertRaises(ValueError):
            make_item("local", "a", "A", kind="folder")
        self.assertEqual(
            make_item("local", "a", "A", kind="folder", path="a")["path"], "a")

    def test_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):
            make_item("local", "x", "X", kind="podcast")


class TestTarget(unittest.TestCase):
    def test_defaults(self):
        t = Target("file:///x.mp3")
        self.assertFalse(t.video)
        self.assertIsNone(t.meta)


class TestRegistry(unittest.TestCase):
    def test_failing_and_nameless_modules_are_skipped(self):
        # "nope" does not exist; "base" imports fine but has no NAME.
        self.assertEqual(sources._load(("nope", "base")), {})

    def test_reserved_name_is_skipped(self):
        fake = mock.Mock(NAME="library")
        with mock.patch("importlib.import_module", return_value=fake):
            self.assertEqual(sources._load(("x",)), {})

    def test_duplicate_name_keeps_first(self):
        a, b = mock.Mock(NAME="dup"), mock.Mock(NAME="dup")
        with mock.patch("importlib.import_module", side_effect=[a, b]):
            self.assertEqual(sources._load(("x", "y")), {"dup": a})

    def test_source_config(self):
        cfg = {"sources": {"local": {"library_root": "/m"}}}
        with mock.patch("sqlch.core.config.load", return_value=cfg):
            self.assertEqual(sources.source_config("local"), {"library_root": "/m"})
            self.assertEqual(sources.source_config("other"), {})
        with mock.patch("sqlch.core.config.load", return_value={}):
            self.assertEqual(sources.source_config("local"), {})


if __name__ == "__main__":
    unittest.main()


class TestSafeAvailable(unittest.TestCase):
    def test_raising_source_is_unavailable(self):
        src = mock.Mock(NAME="bad")
        src.available.side_effect = TypeError("boom")
        with self.assertLogs("sqlch.sources", "ERROR"):
            self.assertFalse(sources.safe_available(src))

    def test_normal_value_passes_through(self):
        self.assertTrue(sources.safe_available(mock.Mock(available=lambda: True)))
        self.assertFalse(sources.safe_available(mock.Mock(available=lambda: False)))
