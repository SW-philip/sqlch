import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlch.sources import local


def _touch(root, rel):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch()


class TestLocalSource(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        for rel in ("Artist/Album/01 - First Song.mp3",
                    "Artist/Album/02 - Second.flac",
                    "Artist/Album/cover.jpg", "Artist/Album/notes.txt",
                    "Solo/loose.ogg", ".hidden/secret.mp3"):
            _touch(self.root, rel)
        p = mock.patch.object(local, "source_config",
                              lambda name: {"library_root": str(self.root)})
        p.start()
        self.addCleanup(p.stop)

    def test_browse_root(self):
        items = local.browse(None)
        self.assertEqual([i["title"] for i in items], ["Artist", "Solo"])
        for i in items:
            self.assertEqual(i["kind"], "folder")
            self.assertEqual(i["path"], i["id"])

    def test_browse_album(self):
        items = local.browse("Artist/Album")
        self.assertEqual([i["title"] for i in items], ["First Song", "Second"])
        self.assertEqual(items[0]["artist"], "Artist")
        self.assertEqual(items[0]["album"], "Album")
        self.assertTrue(items[0]["art"].endswith("cover.jpg"))
        self.assertEqual(items[0]["id"], "Artist/Album/01 - First Song.mp3")

    def test_browse_solo(self):
        (t,) = local.browse("Solo")
        self.assertIsNone(t["artist"])
        self.assertEqual(t["album"], "Solo")
        self.assertIsNone(t["art"])

    def test_unsafe_paths(self):
        for bad in ("../x", "/etc"):
            with self.assertRaises(ValueError):
                local.browse(bad)

    def test_search(self):
        self.assertEqual(len(local.search("second artist")), 1)
        self.assertEqual(local.search("secret"), [])
        self.assertEqual(local.search(""), [])

    def test_search_cap(self):
        for i in range(205):
            _touch(self.root, f"Many/{i:03}.mp3")
        self.assertEqual(len(local.search("many")), 200)

    def test_resolve(self):
        t = local.resolve({"id": "Artist/Album/02 - Second.flac"})
        self.assertEqual(t.url, str(self.root / "Artist/Album/02 - Second.flac"))
        self.assertFalse(t.video)
        self.assertEqual(t.meta["title"], "Second")
        with self.assertRaises(FileNotFoundError):
            local.resolve({"id": "nope.mp3"})

    def test_available(self):
        self.assertTrue(local.available())
        with mock.patch.object(local, "source_config",
                               lambda n: {"library_root": str(self.root / "x")}):
            self.assertFalse(local.available())

    def test_registered(self):
        from sqlch.sources import REGISTRY
        self.assertIn("local", REGISTRY)
        self.assertIs(REGISTRY["local"], local)
