import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlch.core import progress


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        p = mock.patch.object(progress, "data_dir", lambda: self.dir)
        p.start()
        self.addCleanup(p.stop)


class TestProgress(Base):
    def test_empty(self):
        self.assertEqual(progress.read_all(), {})
        self.assertIsNone(progress.get("youtube", "a"))

    def test_record_keeps_position(self):
        progress.record("youtube", "a", 120, 1000)
        row = progress.get("youtube", "a")
        self.assertEqual((row["position"], row["duration"], row["watched"]),
                         (120.0, 1000, False))

    def test_sources_do_not_collide(self):
        progress.record("youtube", "a", 50, 100)
        self.assertIsNone(progress.get("jellyfin", "a"))

    def test_crossing_threshold_marks_watched_and_resets_position(self):
        progress.record("youtube", "a", 899, 1000)
        self.assertFalse(progress.get("youtube", "a")["watched"])
        progress.record("youtube", "a", 900, 1000)
        row = progress.get("youtube", "a")
        self.assertTrue(row["watched"])
        self.assertEqual(row["position"], 0)

    def test_watched_is_sticky(self):
        progress.record("youtube", "a", 950, 1000)
        progress.record("youtube", "a", 10, 1000)
        self.assertTrue(progress.get("youtube", "a")["watched"])

    def test_unknown_duration_never_auto_watched(self):
        progress.record("youtube", "a", 5000, None)
        self.assertFalse(progress.get("youtube", "a")["watched"])

    def test_duration_survives_a_record_without_one(self):
        progress.record("youtube", "a", 10, 1000)
        progress.record("youtube", "a", 20, None)
        self.assertEqual(progress.get("youtube", "a")["duration"], 1000)

    def test_negative_position_ignored(self):
        progress.record("youtube", "a", -1, 100)
        self.assertEqual(progress.read_all(), {})

    def test_mark_both_ways(self):
        progress.mark("youtube", "a", True)
        self.assertTrue(progress.get("youtube", "a")["watched"])
        progress.mark("youtube", "a", False)
        row = progress.get("youtube", "a")
        self.assertFalse(row["watched"])
        self.assertIsNone(progress.resume_point(row))

    def test_corrupt_file_reads_empty(self):
        (self.dir / progress.FILE).write_text("{nope")
        self.assertEqual(progress.read_all(), {})


class TestResume(unittest.TestCase):
    def test_resume_point(self):
        self.assertEqual(progress.resume_point({"position": 300, "watched": False}), 300.0)

    def test_too_early_or_watched_or_missing(self):
        self.assertIsNone(progress.resume_point({"position": 5}))
        self.assertIsNone(progress.resume_point({"position": 300, "watched": True}))
        self.assertIsNone(progress.resume_point(None))

    def test_fraction(self):
        self.assertEqual(progress.fraction({"position": 250, "duration": 1000}), 0.25)
        self.assertEqual(progress.fraction({"watched": True}), 1.0)
        self.assertEqual(progress.fraction(None), 0.0)
        self.assertEqual(progress.fraction({"position": 5, "duration": 0}), 0.0)


if __name__ == "__main__":
    unittest.main()
