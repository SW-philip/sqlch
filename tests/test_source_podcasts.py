import unittest
from unittest import mock

from sqlch.sources import REGISTRY, podcasts


def show(url, title, genre=None, artist=None, image=None):
    return {"feed_url": url, "title": title, "artist": artist, "genre": genre, "image": image}


class Dirs:
    """Patch the directory list podcasts.search sees."""

    def __init__(self, test, **fns):
        p = mock.patch.object(podcasts, "_directories",
                              lambda: [(n, fns[n]) for n in podcasts.PROVIDERS if n in fns])
        p.start()
        test.addCleanup(p.stop)


def boom(q):
    raise OSError("down")


class TestBasics(unittest.TestCase):
    def test_registered(self):
        self.assertIs(REGISTRY["podcasts"], podcasts)

    def test_shape(self):
        self.assertTrue(podcasts.available())
        self.assertEqual(podcasts.GROUPINGS, ("source", "genre", "az"))
        self.assertTrue(podcasts.HAS_DATES)
        self.assertEqual([s["id"] for s in podcasts.sections()], ["following"])

    def test_norm_feed(self):
        n = podcasts.norm_feed
        self.assertEqual(n("https://www.Feeds.Example.com/show/"), "feeds.example.com/show")
        self.assertEqual(n("http://feeds.example.com/show"), "feeds.example.com/show")
        self.assertEqual(n("https://x.com/rss?id=1"), "x.com/rss?id=1")


class TestSearch(unittest.TestCase):
    def test_blank_query(self):
        self.assertEqual(podcasts.search("  "), [])

    def test_merges_duplicates_across_directories(self):
        Dirs(self,
             apple=lambda q: [show("https://feeds.x.com/a", "A", "Comedy"),
                              show("https://feeds.x.com/b", "B")],
             podcastindex=lambda q: [show("http://www.feeds.x.com/a/", "A (pi)", None, "Ann",
                                          "https://img/a"),
                                     show("https://feeds.x.com/c", "C", "News")])
        items = podcasts.search("x")
        self.assertEqual([i["title"] for i in items], ["A", "B", "C"])
        a = items[0]
        self.assertEqual(a["providers"], ["apple", "podcastindex"])
        self.assertEqual((a["genre"], a["artist"], a["image"]), ("Comedy", "Ann", "https://img/a"))
        self.assertEqual((a["kind"], a["path"], a["feed_url"]),
                         ("folder", "feed:https://feeds.x.com/a", "https://feeds.x.com/a"))
        self.assertIsNone(a["art"])
        self.assertEqual(items[2]["providers"], ["podcastindex"])
        self.assertIsNone(podcasts.last_warning())

    def test_one_directory_down_warns_and_returns_the_rest(self):
        Dirs(self, apple=lambda q: [show("https://f/a", "A")], podcastindex=boom)
        self.assertEqual([i["title"] for i in podcasts.search("x")], ["A"])
        self.assertEqual(podcasts.last_warning(), "Podcast Index unavailable")

    def test_all_down_raises(self):
        Dirs(self, apple=boom, podcastindex=boom)
        with self.assertRaises(RuntimeError):
            podcasts.search("x")

    def test_warning_clears_on_next_call(self):
        Dirs(self, apple=lambda q: [], podcastindex=boom)
        podcasts.search("x")
        self.assertIsNotNone(podcasts.last_warning())
        podcasts.browse("section:following")
        self.assertIsNone(podcasts.last_warning())

    def test_directories_without_a_key_is_apple_only(self):
        with mock.patch.object(podcasts.dirs, "pi_credentials", return_value=None):
            self.assertEqual([n for n, _ in podcasts._directories()], ["apple"])
        with mock.patch.object(podcasts.dirs, "pi_credentials", return_value=("k", "s")):
            self.assertEqual([n for n, _ in podcasts._directories()], ["apple", "podcastindex"])
