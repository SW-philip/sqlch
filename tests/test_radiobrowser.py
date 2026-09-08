import json
import unittest
from unittest.mock import patch

from sqlch_gui import radiobrowser


class _FakeResp:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


_RAW = [
    {
        "name": "  Jazz FM  ",
        "url_resolved": "http://jazz.example/stream",
        "url": "http://jazz.example/old",
        "favicon": "http://jazz.example/fav.png",
        "tags": "jazz,smooth",
        "countrycode": "GB",
        "bitrate": 128,
    }
]


def _capture(bucket, payload=None):
    body = json.dumps(_RAW if payload is None else payload).encode()

    def _open(req, timeout=0):
        bucket.append(req.full_url)
        return _FakeResp(body)

    return _open


class TestSearchUrlBuilding(unittest.TestCase):
    def test_search_includes_limit_and_offset(self):
        urls = []
        with patch("urllib.request.urlopen", _capture(urls)):
            radiobrowser.search("jazz")
        self.assertIn("byname/jazz", urls[0])
        self.assertIn("limit=25", urls[0])
        self.assertIn("offset=0", urls[0])

    def test_search_offset_advances(self):
        urls = []
        with patch("urllib.request.urlopen", _capture(urls)):
            radiobrowser.search("jazz", offset=25)
        self.assertIn("offset=25", urls[0])

    def test_search_by_tag_keeps_existing_params(self):
        urls = []
        with patch("urllib.request.urlopen", _capture(urls)):
            radiobrowser.search_by_tag("Jazz", offset=50)
        u = urls[0]
        self.assertIn("bytag/jazz", u)
        self.assertIn("order=votes", u)
        self.assertIn("hidebroken=true", u)
        self.assertIn("limit=25", u)
        self.assertIn("offset=50", u)

    def test_blank_query_skips_request(self):
        urls = []
        with patch("urllib.request.urlopen", _capture(urls)):
            self.assertEqual(radiobrowser.search("   "), [])
        self.assertEqual(urls, [])


class TestNormalization(unittest.TestCase):
    def test_result_keys_and_values(self):
        with patch("urllib.request.urlopen", _capture([], payload=_RAW)):
            out = radiobrowser.search("jazz")
        self.assertEqual(len(out), 1)
        self.assertEqual(
            set(out[0]),
            {"name", "url", "favicon", "tags", "country", "bitrate"},
        )
        self.assertEqual(out[0]["name"], "Jazz FM")
        self.assertEqual(out[0]["url"], "http://jazz.example/stream")
        self.assertEqual(out[0]["country"], "GB")
        self.assertEqual(out[0]["bitrate"], 128)

    def test_empty_response_returns_empty(self):
        with patch("urllib.request.urlopen", _capture([], payload=[])):
            self.assertEqual(radiobrowser.search("jazz"), [])

    def test_network_error_returns_empty(self):
        def _boom(req, timeout=0):
            raise OSError("network down")

        with patch("urllib.request.urlopen", _boom):
            self.assertEqual(radiobrowser.search("jazz"), [])
            self.assertEqual(radiobrowser.search_by_tag("jazz"), [])
