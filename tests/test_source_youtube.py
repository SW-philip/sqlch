import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlch.sources import REGISTRY, youtube


def _proc(entries, rc=0, err=""):
    return mock.Mock(returncode=rc, stdout=json.dumps({"entries": entries}), stderr=err)


class TestYoutube(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        for p in (mock.patch.object(youtube, "ytdlp_path", lambda: "/bin/yt-dlp"),
                  mock.patch.object(youtube, "cache_dir", lambda: Path(self._tmp.name)),
                  mock.patch.object(youtube.follows, "list_follows", lambda: [])):
            p.start()
            self.addCleanup(p.stop)

    def cfg(self, **kw):
        p = mock.patch.object(youtube, "source_config", lambda n: kw)
        p.start()
        self.addCleanup(p.stop)

    def test_registered(self):
        self.assertIs(REGISTRY["youtube"], youtube)

    def test_available_needs_ytdlp(self):
        self.assertTrue(youtube.available())
        with mock.patch.object(youtube, "ytdlp_path", lambda: None):
            self.assertFalse(youtube.available())

    def test_root_lists_shortcuts_and_skips_bad(self):
        self.cfg(shortcuts=[{"name": "Chan", "url": "https://www.youtube.com/@c"},
                            {"name": "no url"}, "junk"])
        (it,) = youtube.browse(None)
        self.assertEqual((it["title"], it["kind"], it["path"]),
                         ("Chan", "folder", "https://www.youtube.com/@c"))

    def test_root_empty_without_config(self):
        self.cfg()
        self.assertEqual(youtube.browse(None), [])

    def test_search_maps_entries(self):
        self.cfg()
        entries = [
            {"id": "abc", "title": "Song", "channel": "Band", "duration": 200},
            {"id": "PL1", "title": "List", "_type": "playlist",
             "url": "https://www.youtube.com/playlist?list=PL1"},
            {"title": "no id"}]
        with mock.patch.object(youtube.subprocess, "run", return_value=_proc(entries)) as run:
            items = youtube.search("lofi")
        cmd = run.call_args[0][0]
        self.assertEqual(cmd[-2:], ["--", "ytsearch25:lofi"])
        self.assertEqual([(i["kind"], i["title"]) for i in items],
                         [("video", "Song"), ("folder", "List")])
        self.assertEqual((items[0]["artist"], items[0]["duration"]), ("Band", 200))
        self.assertEqual(items[1]["path"], "https://www.youtube.com/playlist?list=PL1")

    def test_blank_search(self):
        self.assertEqual(youtube.search("  "), [])

    def test_browse_rejects_non_https_paths(self):
        for bad in ("-o /tmp/x", "file:///etc/passwd", "ytsearch:x"):
            with self.assertRaises(ValueError):
                youtube.browse(bad)

    def test_ytdlp_failure_reports_last_line(self):
        self.cfg()
        bad = _proc([], rc=1, err="WARN x\nERROR: video unavailable\n")
        with mock.patch.object(youtube.subprocess, "run", return_value=bad):
            with self.assertRaisesRegex(RuntimeError, "video unavailable"):
                youtube.search("x")

    def test_resolve_is_video_watch_url_with_cover(self):
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = b"jpg"
        with mock.patch.object(youtube, "urlopen", return_value=resp):
            t = youtube.resolve({"id": "abc_-1", "title": "Song", "artist": "Band"})
        self.assertEqual(t.url, "https://www.youtube.com/watch?v=abc_-1")
        self.assertTrue(t.video)
        self.assertEqual(Path(t.meta["art"]).read_bytes(), b"jpg")
        self.assertEqual((t.meta["title"], t.meta["artist"]), ("Song", "Band"))

    def test_resolve_survives_cover_failure_and_rejects_bad_ids(self):
        with mock.patch.object(youtube, "urlopen", side_effect=OSError):
            self.assertIsNone(youtube.resolve({"id": "abc"}).meta["art"])
        for bad in ("", "a b", "a&b=c", "../x"):
            with self.assertRaises(ValueError):
                youtube.resolve({"id": bad})

    def test_sections(self):
        self.assertEqual(youtube.sections(), [{"id": "channels", "title": "CHANNELS"}])

    def test_channels_section_lists_follows_then_shortcuts(self):
        self.cfg(shortcuts=[{"name": "Short", "url": "https://www.youtube.com/@s"}])
        row = {"channel_id": "UC" + "a" * 22, "name": "Followed"}
        with mock.patch.object(youtube.follows, "list_follows", lambda: [row]):
            items = youtube.browse("section:channels")
        self.assertEqual([i["title"] for i in items], ["Followed", "Short"])
        self.assertEqual(items[0]["channel_id"], row["channel_id"])
        self.assertEqual(items[0]["kind"], "folder")
        self.assertEqual(items[0]["path"],
                         f"https://www.youtube.com/channel/{row['channel_id']}/videos")
        self.assertIsNone(items[1]["channel_id"])

    def test_root_is_the_channels_section(self):
        self.cfg()
        row = {"channel_id": "UC" + "b" * 22, "name": "F"}
        with mock.patch.object(youtube.follows, "list_follows", lambda: [row]):
            self.assertEqual(youtube.browse(None), youtube.browse("section:channels"))

    def test_video_items_carry_channel_id(self):
        self.cfg()
        entries = [{"id": "abc", "title": "S", "channel": "Band", "channel_id": "UC1"}]
        with mock.patch.object(youtube.subprocess, "run", return_value=_proc(entries)):
            (item,) = youtube.search("x")
        self.assertEqual(item["channel_id"], "UC1")

    def test_valid_channel_id(self):
        self.assertTrue(youtube.valid_channel_id("UC" + "a" * 22))
        for bad in ("", "UC123", "XX" + "a" * 22, "UC" + "a" * 21 + "/", "UC" + "a" * 23):
            self.assertFalse(youtube.valid_channel_id(bad))

    FEED = (b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" '
            b'xmlns="http://www.w3.org/2005/Atom"><title>Chan</title>'
            b'<entry><id>yt:video:vid2</id><yt:videoId>vid2</yt:videoId>'
            b'<title>Second</title></entry>'
            b'<entry><id>yt:video:vid1</id><yt:videoId>vid1</yt:videoId>'
            b'<title>First</title></entry></feed>')

    def test_parse_feed_newest_first(self):
        self.assertEqual(youtube.parse_feed(self.FEED),
                         [{"id": "vid2", "title": "Second"},
                          {"id": "vid1", "title": "First"}])

    def test_parse_feed_refuses_dtds(self):
        evil = (b'<?xml version="1.0"?><!DOCTYPE feed [<!ENTITY a "aaaa">]>'
                b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>&a;</title>'
                b'</entry></feed>')
        with self.assertRaises(ValueError):
            youtube.parse_feed(evil)

    def test_fetch_feed_requests_the_feed_url(self):
        cid = "UC" + "c" * 22
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = self.FEED
        with mock.patch.object(youtube, "urlopen", return_value=resp) as op:
            out = youtube.fetch_feed(cid)
        self.assertEqual(op.call_args[0][0],
                         f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}")
        self.assertEqual(out[0]["id"], "vid2")

    def test_fetch_feed_rejects_bad_ids(self):
        with self.assertRaises(ValueError):
            youtube.fetch_feed("UC1&x=y")

    def test_poll_seconds(self):
        self.cfg()
        self.assertEqual(youtube.poll_seconds(), 30 * 60)
        self.cfg(poll_minutes=10)
        self.assertEqual(youtube.poll_seconds(), 600)
        self.cfg(poll_minutes=0)
        self.assertEqual(youtube.poll_seconds(), 60)
        self.cfg(poll_minutes="soon")
        self.assertEqual(youtube.poll_seconds(), 30 * 60)


if __name__ == "__main__":
    unittest.main()
