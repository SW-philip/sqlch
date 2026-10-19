import http.client
import tempfile
import unittest
from pathlib import Path
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


FEED = b"""<?xml version="1.0"?>
<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" version="2.0"><channel>
  <title>The Show</title>
  <itunes:image href="https://img/show.jpg"/>
  <item><title>Old</title><guid>g1</guid>
    <pubDate>Mon, 05 Oct 2026 10:00:00 +0000</pubDate>
    <enclosure url="https://cdn/old.mp3" type="audio/mpeg"/>
    <itunes:duration>1:02:03</itunes:duration></item>
  <item><title>New</title>
    <pubDate>Fri, 16 Oct 2026 00:00:00 GMT</pubDate>
    <enclosure url="https://cdn/new.mp3" type="audio/mpeg"/>
    <itunes:image href="https://img/new.jpg"/>
    <itunes:duration>45:30</itunes:duration></item>
  <item><title>Text only</title><guid>g3</guid></item>
  <item><title>Seconds</title><guid>g4</guid><enclosure url="https://cdn/s.mp3"/>
    <itunes:duration>90</itunes:duration><pubDate>garbage</pubDate></item>
</channel></rss>"""


class TestFeed(unittest.TestCase):
    def test_parse_feed(self):
        eps = podcasts.parse_feed(FEED, "https://f/show")
        self.assertEqual([e["title"] for e in eps], ["New", "Old", "Seconds"])
        new, old, secs = eps
        self.assertEqual((new["id"], new["url"], new["duration"], new["date"]),
                         ("https://cdn/new.mp3", "https://cdn/new.mp3", 2730, 1792108800))
        self.assertEqual(new["image"], "https://img/new.jpg")
        self.assertEqual((old["id"], old["duration"], old["image"]),
                         ("g1", 3723, "https://img/show.jpg"))
        self.assertEqual((secs["duration"], secs["date"]), (90, None))
        for e in eps:
            self.assertEqual((e["kind"], e["artist"], e["source"]), ("track", "The Show", "podcasts"))
            self.assertIsNone(e["feed_url"])
            self.assertIsNone(e["art"])

    def test_not_rss(self):
        with self.assertRaises(ValueError):
            podcasts.parse_feed(b"<html/>", "https://f/x")

    def test_duration_formats(self):
        d = podcasts.parse_duration
        self.assertEqual([d("90"), d("1:30"), d("1:00:00"), d(""), d(None), d("abc"), d("1:2:3:4")],
                         [90, 90, 3600, None, None, None, None])
        self.assertEqual([d("inf"), d("1e400"), d("-5"), d("1:-30"), d("0")],
                         [None, None, None, None, None])

    def test_date_without_zone_is_utc(self):
        self.assertEqual(podcasts._date("Fri, 16 Oct 2026 00:00:00 -0000"), 1792108800)

    def test_invalid_xml_is_value_error(self):
        with self.assertRaisesRegex(ValueError, "not valid XML"):
            podcasts.parse_feed(b"<rss><channel>", "https://f/x")

    def test_enclosure_url_is_stripped(self):
        feed = (b'<rss><channel><title>S</title><item><title>X</title>'
                b'<enclosure url=" https://cdn/x.mp3 "/></item></channel></rss>')
        [ep] = podcasts.parse_feed(feed, "https://f/x")
        self.assertEqual((ep["url"], ep["id"]), ("https://cdn/x.mp3", "https://cdn/x.mp3"))

    def test_fetch_feed_rejects_oversized(self):
        with mock.patch.object(podcasts, "_download",
                               return_value=b"x" * (podcasts.MAX_FEED_BYTES + 1)) as dl:
            with self.assertRaisesRegex(ValueError, "too large"):
                podcasts._fetch_feed("https://f/x")
        dl.assert_called_once_with("https://f/x", podcasts.MAX_FEED_BYTES + 1)

    def test_fetch_feed_at_the_cap_is_fine(self):
        data = b"x" * podcasts.MAX_FEED_BYTES
        with mock.patch.object(podcasts, "_download", return_value=data):
            self.assertIs(podcasts._fetch_feed("https://f/x"), data)

    def test_browse_feed_rejects_non_http(self):
        for bad in ("feed:file:///etc/passwd", "feed:", "nope"):
            with self.assertRaises(ValueError):
                podcasts.browse(bad)

    def test_browse_feed_fetches_and_parses(self):
        with mock.patch.object(podcasts, "_fetch_feed", return_value=FEED) as f:
            eps = podcasts.browse("feed:https://f/show")
        f.assert_called_once_with("https://f/show")
        self.assertEqual(len(eps), 3)


class TestResolve(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        p = mock.patch.object(podcasts, "cache_dir", lambda: Path(self._tmp.name))
        p.start()
        self.addCleanup(p.stop)

    def ep(self, **kw):
        e = podcasts.parse_feed(FEED, "https://f/show")[0]
        e.update(kw)
        return e

    def test_resolve_targets_the_enclosure(self):
        with mock.patch.object(podcasts, "_cached_art", return_value="/tmp/a.jpg") as art:
            t = podcasts.resolve(self.ep())
        art.assert_called_once_with("https://img/new.jpg")
        self.assertEqual(t.url, "https://cdn/new.mp3")
        self.assertFalse(t.video)
        self.assertEqual(t.meta, {"title": "New", "artist": "The Show",
                                  "album": "The Show", "art": "/tmp/a.jpg"})

    def test_resolve_needs_an_http_url(self):
        for url in (None, "", "file:///x.mp3"):
            with self.assertRaises(ValueError):
                podcasts.resolve(self.ep(url=url))

    def test_cached_art_downloads_once(self):
        calls = []

        def fake_get(url, *args, **kwargs):
            calls.append(url)
            return b"img"

        with mock.patch.object(podcasts, "_download", fake_get):
            p1 = podcasts._cached_art("https://img/a.jpg")
            p2 = podcasts._cached_art("https://img/a.jpg")
        self.assertEqual(p1, p2)
        self.assertEqual(Path(p1).read_bytes(), b"img")
        self.assertEqual(calls, ["https://img/a.jpg"])
        self.assertIsNone(podcasts._cached_art(None))

    def test_cached_art_failure_is_none(self):
        with mock.patch.object(podcasts, "_download", side_effect=OSError("x")):
            self.assertIsNone(podcasts._cached_art("https://img/b.jpg"))

    def test_art_failure_never_blocks_playback(self):
        with mock.patch.object(podcasts, "_download", side_effect=http.client.InvalidURL("x")):
            self.assertIsNone(podcasts._cached_art("https://img/c.jpg"))
            t = podcasts.resolve(self.ep())
        self.assertEqual(t.url, "https://cdn/new.mp3")
        self.assertIsNone(t.meta["art"])

    def test_cached_art_is_small_and_quick(self):
        with mock.patch.object(podcasts, "_download", return_value=b"img") as dl:
            p = podcasts._cached_art("https://img/d.jpg")
        dl.assert_called_once_with("https://img/d.jpg", podcasts.MAX_ART_BYTES,
                                   timeout=podcasts.ART_TIMEOUT)
        self.assertEqual(podcasts.MAX_ART_BYTES, 2 * 1024 * 1024)
        self.assertEqual(podcasts.ART_TIMEOUT, 3)
        self.assertEqual([f.name for f in Path(p).parent.iterdir()], [Path(p).name])


class TestFollowing(unittest.TestCase):
    def test_following_section_lists_stored_shows_as_folders(self):
        rows = [{"feed_url": "https://f/a", "title": "A", "artist": "Ann",
                 "genre": "Comedy", "providers": ["apple", "podcastindex"],
                 "image": "https://img/a"}]
        with mock.patch.object(podcasts.follows, "list_podcasts", return_value=rows):
            items = podcasts.browse("section:following")
        self.assertEqual(len(items), 1)
        a = items[0]
        self.assertEqual((a["kind"], a["path"], a["feed_url"], a["genre"], a["providers"]),
                         ("folder", "feed:https://f/a", "https://f/a", "Comedy",
                          ["apple", "podcastindex"]))

    def test_root_is_following(self):
        with mock.patch.object(podcasts.follows, "list_podcasts", return_value=[]):
            self.assertEqual(podcasts.browse(None), [])
