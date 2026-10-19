import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlch.core import follows

ITEM = {"source": "youtube", "id": "abc", "title": "Song", "kind": "video"}
OTHER = {"source": "jellyfin", "id": "abc", "title": "Same id", "kind": "track"}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        p = mock.patch.object(follows, "data_dir", lambda: self.dir)
        p.start()
        self.addCleanup(p.stop)


class TestFavorites(Base):
    def test_empty(self):
        self.assertEqual(follows.list_favorites("youtube"), [])
        self.assertEqual(follows.favorite_ids("youtube"), set())

    def test_toggle_adds_then_removes(self):
        self.assertTrue(follows.toggle_favorite(ITEM))
        self.assertEqual(follows.list_favorites("youtube"), [ITEM])
        self.assertEqual(follows.favorite_ids("youtube"), {"abc"})
        self.assertFalse(follows.toggle_favorite(ITEM))
        self.assertEqual(follows.list_favorites("youtube"), [])

    def test_sources_are_separate_even_with_same_id(self):
        follows.toggle_favorite(ITEM)
        follows.toggle_favorite(OTHER)
        self.assertEqual(follows.list_favorites("youtube"), [ITEM])
        self.assertEqual(follows.list_favorites("jellyfin"), [OTHER])

    def test_toggle_needs_source_and_id(self):
        for bad in ({}, {"source": "youtube"}, {"id": "x"}):
            with self.assertRaises(ValueError):
                follows.toggle_favorite(bad)

    def test_no_temp_files_left(self):
        follows.toggle_favorite(ITEM)
        self.assertEqual([p.name for p in self.dir.iterdir()], ["favorites.json"])

    def test_corrupt_file_is_quarantined_and_store_recovers(self):
        (self.dir / "favorites.json").write_text("{not json")
        self.assertEqual(follows.list_favorites("youtube"), [])
        self.assertTrue((self.dir / "favorites.json.bad").exists())
        self.assertTrue(follows.toggle_favorite(ITEM))
        self.assertEqual(follows.list_favorites("youtube"), [ITEM])

    def test_non_list_file_is_quarantined(self):
        (self.dir / "favorites.json").write_text('{"a": 1}')
        self.assertEqual(follows.list_favorites("youtube"), [])
        self.assertTrue((self.dir / "favorites.json.bad").exists())


class TestFollows(Base):
    def test_follow_is_idempotent(self):
        follows.follow("UC1", "Chan")
        follows.follow("UC1", "Chan again")
        (row,) = follows.list_follows()
        self.assertEqual(row, {"channel_id": "UC1", "name": "Chan",
                               "last_video_id": None, "last_checked": None})
        self.assertEqual(follows.followed_ids(), {"UC1"})

    def test_unfollow(self):
        follows.follow("UC1", "A")
        follows.follow("UC2", "B")
        follows.unfollow("UC1")
        self.assertEqual(follows.followed_ids(), {"UC2"})
        follows.unfollow("missing")  # no error

    def test_record_seen(self):
        follows.follow("UC1", "A")
        follows.record_seen("UC1", "vid9", 123.0)
        (row,) = follows.list_follows()
        self.assertEqual((row["last_video_id"], row["last_checked"]), ("vid9", 123.0))
        follows.record_seen("gone", "x", 1.0)  # unknown channel is ignored
        self.assertEqual(len(follows.list_follows()), 1)


if __name__ == "__main__":
    unittest.main()
