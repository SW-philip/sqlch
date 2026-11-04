import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlch.sources import _podcast_dirs as dirs


class FakeResp:
    def __init__(self, body):
        self.body = body

    def read(self, n=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Recorder:
    def __init__(self, payload):
        self.payload, self.requests = payload, []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        return FakeResp(json.dumps(self.payload).encode())


class TestApple(unittest.TestCase):
    def test_parses_results_and_drops_ones_without_a_feed(self):
        rec = Recorder({"results": [
            {"feedUrl": "https://f/a", "collectionName": "A", "artistName": "Ann",
             "primaryGenreName": "Comedy", "artworkUrl600": "https://img/a"},
            {"collectionName": "No feed"},
            {"feedUrl": "https://f/b", "collectionName": "B", "artworkUrl100": "https://img/b"}]})
        with mock.patch.object(dirs, "urlopen", rec):
            shows = dirs.apple_search("comedy")
        self.assertEqual(shows, [
            {"feed_url": "https://f/a", "title": "A", "artist": "Ann",
             "genre": "Comedy", "image": "https://img/a"},
            {"feed_url": "https://f/b", "title": "B", "artist": None,
             "genre": None, "image": "https://img/b"}])

    def test_query_url(self):
        rec = Recorder({"results": []})
        with mock.patch.dict("os.environ", {"SQLCH_APPLE_PODCASTS_BASE": "http://apple"}), \
                mock.patch.object(dirs, "urlopen", rec):
            dirs.apple_search("linux unplugged")
        url = rec.requests[0].full_url
        self.assertTrue(url.startswith("http://apple/search?"))
        self.assertIn("media=podcast", url)
        self.assertIn("entity=podcast", url)
        self.assertIn("term=linux+unplugged", url)


class TestPodcastIndex(unittest.TestCase):
    def test_auth_headers(self):
        h = dirs.pi_headers("K", "S", 1700000000)
        self.assertEqual(h["X-Auth-Key"], "K")
        self.assertEqual(h["X-Auth-Date"], "1700000000")
        self.assertEqual(h["Authorization"],
                         hashlib.sha1(b"KS1700000000").hexdigest())

    def test_parses_feeds_with_first_category_as_genre(self):
        rec = Recorder({"feeds": [
            {"url": "https://f/a", "title": "A", "author": "Ann", "artwork": "https://img/a",
             "categories": {"102": "Technology", "9": "News"}},
            {"url": "https://f/b", "title": "B", "categories": None},
            {"title": "no url"}]})
        with mock.patch.dict("os.environ", {"SQLCH_PODCASTINDEX_BASE": "http://pi"}), \
                mock.patch.object(dirs, "urlopen", rec):
            shows = dirs.pi_search("linux", ("K", "S"), now=lambda: 5)
        self.assertEqual(shows, [
            {"feed_url": "https://f/a", "title": "A", "artist": "Ann",
             "genre": "Technology", "image": "https://img/a"},
            {"feed_url": "https://f/b", "title": "B", "artist": None,
             "genre": None, "image": None}])
        req = rec.requests[0]
        self.assertTrue(req.full_url.startswith("http://pi/search/byterm?"))
        self.assertIn("q=linux", req.full_url)
        self.assertEqual(req.get_header("X-auth-key"), "K")


class TestCredentials(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict("os.environ", {}, clear=False)
        p.start()
        self.addCleanup(p.stop)
        for k in ("PODCASTINDEX_API_KEY", "PODCASTINDEX_API_SECRET"):
            dirs.os.environ.pop(k, None)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.env = Path(self._tmp.name) / "env"

    def test_env_vars_win(self):
        with mock.patch.dict("os.environ", {"PODCASTINDEX_API_KEY": "k",
                                            "PODCASTINDEX_API_SECRET": "s"}):
            self.assertEqual(dirs.pi_credentials(str(self.env)), ("k", "s"))

    def test_from_file_strips_quotes_and_comments(self):
        self.env.write_text('# c\nPODCASTINDEX_API_KEY="k"\nPODCASTINDEX_API_SECRET=s\n')
        self.assertEqual(dirs.pi_credentials(str(self.env)), ("k", "s"))

    def test_missing_file_or_half_a_pair_is_none(self):
        self.assertIsNone(dirs.pi_credentials(str(self.env)))
        self.env.write_text("PODCASTINDEX_API_KEY=k\n")
        self.assertIsNone(dirs.pi_credentials(str(self.env)))
