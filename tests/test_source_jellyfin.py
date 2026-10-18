import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlch.sources import REGISTRY, jellyfin


def _cfg(**kw):
    return mock.patch.object(jellyfin, "source_config", lambda n: kw)


class FakeAPI:
    def __init__(self, responses):
        self.responses, self.calls = responses, []

    def __call__(self, path, params=None):
        self.calls.append((path, params))
        return self.responses[path]


class TestOpen(unittest.TestCase):
    def test_builds_url_and_sends_token(self):
        seen = {}

        class Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b'{"ok": 1}'

        def fake(req, timeout):
            seen["url"], seen["tok"] = req.full_url, req.get_header("Authorization")
            return Resp()

        with _cfg(server="http://j:8096/", token_file="/nonexistent"), \
             mock.patch.object(jellyfin, "_token", return_value="KEY"), \
             mock.patch.object(jellyfin, "urlopen", fake):
            self.assertEqual(jellyfin._get("/Items", {"a": "b c"}), {"ok": 1})
        self.assertEqual(seen, {"url": "http://j:8096/Items?a=b+c", "tok": 'MediaBrowser Token="KEY"'})


class TestJellyfin(unittest.TestCase):
    def setUp(self):
        jellyfin._user_ids.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tok = Path(self._tmp.name) / "tok"
        self.tok.write_text("KEY\n")
        for p in (_cfg(server="http://j:8096/", token_file=str(self.tok)),
                  mock.patch.object(jellyfin, "cache_dir",
                                    lambda: Path(self._tmp.name))):
            p.start()
            self.addCleanup(p.stop)

    def api(self, **extra):
        resp = {"/Users": [{"Id": "U1"}], **extra}
        fake = FakeAPI(resp)
        p = mock.patch.object(jellyfin, "_get", fake)
        p.start()
        self.addCleanup(p.stop)
        return fake

    def test_registered(self):
        self.assertIs(REGISTRY["jellyfin"], jellyfin)

    def test_available_needs_readable_token(self):
        self.assertTrue(jellyfin.available())
        with _cfg(token_file=str(self.tok) + ".missing"):
            self.assertFalse(jellyfin.available())

    def test_root_lists_libraries_as_folders(self):
        fake = self.api(**{"/UserViews": {"Items": [
            {"Id": "L1", "Name": "Music", "Type": "CollectionFolder"}]}})
        (it,) = jellyfin.browse(None)
        self.assertEqual((it["title"], it["kind"], it["path"]),
                         ("Music", "folder", "CollectionFolder:L1"))
        self.assertEqual(fake.calls[-1][1], {"userId": "U1"})

    def test_browse_container_and_kinds(self):
        fake = self.api(**{"/Items": {"Items": [
            {"Id": "A1", "Name": "Album", "Type": "MusicAlbum", "AlbumArtist": "Band"},
            {"Id": "T1", "Name": "Song", "Type": "Audio", "Artists": ["Band"],
             "Album": "Album", "RunTimeTicks": 1_800_000_000},
            {"Id": "M1", "Name": "Film", "Type": "Movie"},
            {"Id": "E1", "Name": "Pilot", "Type": "Episode",
             "SeriesName": "Show", "SeasonName": "S1"}]}})
        items = jellyfin.browse("CollectionFolder:L1")
        self.assertEqual([i["kind"] for i in items], ["folder", "track", "video", "video"])
        self.assertEqual(items[0]["path"], "MusicAlbum:A1")
        self.assertEqual((items[1]["artist"], items[1]["duration"]), ("Band", 180.0))
        self.assertEqual((items[3]["artist"], items[3]["album"]), ("Show", "S1"))
        self.assertEqual(fake.calls[-1][1]["parentId"], "L1")

    def test_artist_browses_their_albums(self):
        fake = self.api(**{"/Items": {"Items": []}})
        jellyfin.browse("MusicArtist:AR1")
        params = fake.calls[-1][1]
        self.assertEqual(params["AlbumArtistIds"], "AR1")
        self.assertNotIn("parentId", params)

    def test_bad_path(self):
        self.api()
        with self.assertRaises(ValueError):
            jellyfin.browse("nonsense")

    def test_search(self):
        fake = self.api(**{"/Items": {"Items": []}})
        self.assertEqual(jellyfin.search("  "), [])
        jellyfin.search("daft")
        params = fake.calls[-1][1]
        self.assertEqual(params["searchTerm"], "daft")
        self.assertEqual(params["Limit"], jellyfin.SEARCH_LIMIT)

    def test_user_id_config_wins_and_is_cached(self):
        fake = self.api(**{"/Items": {"Items": []}})
        jellyfin.search("a")
        jellyfin.search("b")
        self.assertEqual([c[0] for c in fake.calls].count("/Users"), 1)
        with _cfg(server="http://j", token_file=str(self.tok), user_id="CFG"):
            self.assertEqual(jellyfin._user_id(), "CFG")

    def test_resolve_audio_downloads_cover(self):
        self.api(**{"/Items/T1": {
            "Id": "T1", "Name": "Song", "Type": "Audio", "Artists": ["Band"],
            "Album": "Album", "AlbumId": "A1", "AlbumPrimaryImageTag": "x"}})
        with mock.patch.object(jellyfin, "_open", return_value=b"jpg") as op:
            t = jellyfin.resolve({"id": "T1"})
        self.assertEqual(t.url, "http://j:8096/Items/T1/Download")
        self.assertEqual(t.headers, ('Authorization: MediaBrowser Token="KEY"',))
        self.assertFalse(t.video)
        self.assertEqual(t.meta["title"], "Song")
        self.assertTrue(t.meta["art"].endswith("jellyfin/A1.jpg"))
        self.assertEqual(Path(t.meta["art"]).read_bytes(), b"jpg")
        self.assertEqual(op.call_args[0][0], "/Items/A1/Images/Primary")

    def test_resolve_video_without_art_and_folder_rejected(self):
        self.api(**{"/Items/M1": {"Id": "M1", "Name": "Film", "Type": "Movie"},
                    "/Items/F1": {"Id": "F1", "Name": "Dir", "Type": "Folder"}})
        t = jellyfin.resolve({"id": "M1"})
        self.assertTrue(t.video)
        self.assertIsNone(t.meta["art"])
        with self.assertRaises(ValueError):
            jellyfin.resolve({"id": "F1"})

    def test_cover_failure_is_not_fatal(self):
        self.api(**{"/Items/T1": {"Id": "T1", "Name": "S", "Type": "Audio",
                                  "ImageTags": {"Primary": "x"}}})
        with mock.patch.object(jellyfin, "_open", side_effect=OSError):
            t = jellyfin.resolve({"id": "T1"})
        self.assertIsNone(t.meta["art"])


if __name__ == "__main__":
    unittest.main()
