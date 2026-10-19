import json
import unittest
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
