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
                  mock.patch.object(youtube, "cache_dir", lambda: Path(self._tmp.name))):
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


if __name__ == "__main__":
    unittest.main()
