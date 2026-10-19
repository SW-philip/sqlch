import json
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

    def bad_files(self, name="favorites.json"):
        return sorted(self.dir.glob(name + ".*.bad"))

    def test_reader_leaves_corrupt_file_alone(self):
        for text in ("{not json", '{"a": 1}'):
            (self.dir / "favorites.json").write_text(text)
            self.assertEqual(follows.list_favorites("youtube"), [])
            self.assertEqual(follows.favorite_ids("youtube"), set())
            self.assertEqual((self.dir / "favorites.json").read_text(), text)
            self.assertEqual(self.bad_files(), [])
        (self.dir / "youtube_follows.json").write_text("{not json")
        self.assertEqual(follows.list_follows(), [])
        self.assertEqual(follows.followed_ids(), set())
        self.assertTrue((self.dir / "youtube_follows.json").exists())
        self.assertEqual(self.bad_files("youtube_follows.json"), [])

    def test_writer_quarantines_corrupt_file_then_succeeds(self):
        (self.dir / "favorites.json").write_text("{not json")
        self.assertTrue(follows.toggle_favorite(ITEM))
        self.assertEqual(follows.list_favorites("youtube"), [ITEM])
        (bad,) = self.bad_files()
        self.assertEqual(bad.read_text(), "{not json")

    def test_writer_quarantines_non_list_file(self):
        (self.dir / "favorites.json").write_text('{"a": 1}')
        self.assertTrue(follows.toggle_favorite(ITEM))
        self.assertEqual(len(self.bad_files()), 1)

    def test_writer_raises_on_os_error_and_touches_nothing(self):
        (self.dir / "favorites.json").write_text(json.dumps([ITEM]))
        before = sorted(p.name for p in self.dir.iterdir())
        with mock.patch.object(Path, "read_text", side_effect=PermissionError("no")):
            with self.assertRaises(PermissionError):
                follows.toggle_favorite(OTHER)
            with self.assertRaises(PermissionError):
                follows.follow("UC1", "A")
            self.assertEqual(follows.list_favorites("youtube"), [])
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), before)
        self.assertEqual(follows.list_favorites("youtube"), [ITEM])

    def test_two_quarantines_keep_two_files(self):
        for text in ("{one", "{two"):
            (self.dir / "favorites.json").write_text(text)
            follows.toggle_favorite(ITEM)
        self.assertEqual(len(self.bad_files()), 2)
        self.assertEqual({p.read_text() for p in self.bad_files()}, {"{one", "{two"})


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


SHOW = {"source": "podcasts", "id": "https://f/a", "title": "A", "kind": "folder",
        "path": "feed:https://f/a", "feed_url": "https://f/a", "artist": "Ann",
        "genre": "Comedy", "providers": ["apple"], "image": "https://img/a",
        "art": None, "url": None}


class TestPodcastFollows(Base):
    def test_empty(self):
        self.assertEqual(follows.list_podcasts(), [])
        self.assertEqual(follows.followed_feeds(), set())

    def test_follow_stores_only_the_show_fields(self):
        follows.follow_podcast(SHOW)
        self.assertEqual(follows.list_podcasts(), [
            {"feed_url": "https://f/a", "title": "A", "artist": "Ann",
             "genre": "Comedy", "providers": ["apple"], "image": "https://img/a"}])
        self.assertEqual(follows.followed_feeds(), {"https://f/a"})

    def test_duplicate_follow_is_ignored(self):
        follows.follow_podcast(SHOW)
        follows.follow_podcast({**SHOW, "title": "Again"})
        self.assertEqual([r["title"] for r in follows.list_podcasts()], ["A"])

    def test_unfollow(self):
        follows.follow_podcast(SHOW)
        follows.unfollow_podcast("https://f/a")
        self.assertEqual(follows.list_podcasts(), [])
        follows.unfollow_podcast("https://f/a")  # absent: no error

    def test_follow_needs_a_feed_url(self):
        with self.assertRaises(ValueError):
            follows.follow_podcast({"title": "x"})

    def test_follow_cleans_a_messy_item(self):
        follows.follow_podcast({"feed_url": "https://f/m", "title": {"x": 1}, "artist": "",
                                "genre": 5, "providers": "apple", "image": "file:///x"})
        self.assertEqual(follows.list_podcasts(), [
            {"feed_url": "https://f/m", "title": None, "artist": None, "genre": None,
             "providers": [], "image": None}])

    def test_follow_keeps_only_string_providers(self):
        follows.follow_podcast({**SHOW, "providers": ["apple", 3, None, "podcastindex"]})
        self.assertEqual(follows.list_podcasts()[0]["providers"], ["apple", "podcastindex"])

    def test_reader_skips_malformed_rows(self):
        good = {"feed_url": "https://f/a", "title": "A"}
        (self.dir / "podcast_follows.json").write_text(json.dumps(
            ["x", {"feed_url": ["https://f/b"]}, {"feed_url": "file:///etc/passwd"}, good]))
        self.assertEqual(follows.list_podcasts(), [good])
        self.assertEqual(follows.followed_feeds(), {"https://f/a"})

    def test_reader_leaves_corrupt_file_alone(self):
        path = self.dir / "podcast_follows.json"
        path.write_text("{not json")
        self.assertEqual(follows.list_podcasts(), [])
        self.assertEqual(follows.followed_feeds(), set())
        self.assertEqual(path.read_text(), "{not json")
        self.assertEqual(list(self.dir.glob("podcast_follows.json.*.bad")), [])

    def test_writer_quarantines_corrupt_file_then_succeeds(self):
        (self.dir / "podcast_follows.json").write_text("{not json")
        follows.follow_podcast(SHOW)
        self.assertEqual(follows.followed_feeds(), {"https://f/a"})
        (bad,) = self.dir.glob("podcast_follows.json.*.bad")
        self.assertEqual(bad.read_text(), "{not json")

if __name__ == "__main__":
    unittest.main()
