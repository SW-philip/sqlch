import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlch.sources import REGISTRY, video


def _touch(root, rel):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch()


class TestVideoSource(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        for rel in ("Shows/Show/01 - Pilot.mkv", "Shows/Show/02 - Second.mp4",
                    "Shows/Show/notes.txt", "Shows/Show/song.mp3",
                    "Movie.webm", ".hidden/x.mkv"):
            _touch(self.root, rel)
        p = mock.patch.object(video, "source_config",
                              lambda name: {"library_root": str(self.root)})
        p.start()
        self.addCleanup(p.stop)

    def test_registered(self):
        self.assertIs(REGISTRY["video"], video)

    def test_browse_lists_videos_only(self):
        items = video.browse("Shows/Show")
        self.assertEqual([i["title"] for i in items], ["Pilot", "Second"])
        self.assertTrue(all(i["kind"] == "video" for i in items))

    def test_browse_root(self):
        items = video.browse(None)
        self.assertEqual([(i["title"], i["kind"]) for i in items],
                         [("Shows", "folder"), ("Movie", "video")])

    def test_search(self):
        self.assertEqual([i["title"] for i in video.search("pilot show")], ["Pilot"])
        self.assertEqual(video.search("song"), [])
        self.assertEqual(video.search("x"), [])

    def test_resolve_is_video(self):
        t = video.resolve(video.browse("Shows/Show")[0])
        self.assertTrue(t.video)
        self.assertEqual(t.url, str(self.root / "Shows/Show/01 - Pilot.mkv"))
        self.assertEqual(t.meta["title"], "Pilot")

    def test_resolve_rejects_non_video_and_escape(self):
        base = {"source": "video", "title": "x"}
        with self.assertRaises(ValueError):
            video.resolve({**base, "id": "Shows/Show/song.mp3"})
        with self.assertRaises(ValueError):
            video.resolve({**base, "id": "../etc/passwd"})
        with self.assertRaises(FileNotFoundError):
            video.resolve({**base, "id": "gone.mkv"})

    def test_default_root_and_availability(self):
        with mock.patch.object(video, "source_config", lambda n: {}):
            self.assertEqual(video._root(), Path("~/Videos").expanduser())
        self.assertTrue(video.available())
