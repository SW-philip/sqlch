import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlch.sources import REGISTRY, spotify


class Fake:
    def __init__(self, responses):
        self.responses, self.calls = responses, []

    def __call__(self, path, params=None):
        self.calls.append((path, params))
        return self.responses[path]


TRACK = {"id": "T1", "name": "Song", "duration_ms": 200000,
         "artists": [{"name": "A"}, {"name": "B"}],
         "album": {"id": "AL1", "name": "Album", "images": [{"url": "http://img/x"}]}}


class TestSpotify(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        env = self.dir / "env"
        env.write_text('# c\nSPOTIFY_CLIENT_ID="abc"\nSPOTIFY_CLIENT_SECRET=def\n')
        self.env = env
        for p in (mock.patch.object(spotify, "cache_dir", lambda: self.dir),
                  mock.patch.dict("os.environ", {}, clear=False)):
            p.start()
            self.addCleanup(p.stop)
        for k in ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"):
            spotify.os.environ.pop(k, None)
        self.cfg(env_file=str(env))

    def cfg(self, **kw):
        p = mock.patch.object(spotify, "source_config", lambda n: kw)
        p.start()
        self.addCleanup(p.stop)

    def api(self, **resp):
        fake = Fake(resp)
        p = mock.patch.object(spotify, "_get", fake)
        p.start()
        self.addCleanup(p.stop)
        return fake

    def test_registered(self):
        self.assertIs(REGISTRY["spotify"], spotify)

    def test_credentials_from_file_strip_quotes(self):
        self.assertEqual(spotify._credentials(), ("abc", "def"))
        self.assertTrue(spotify.available())

    def test_unavailable_without_credentials(self):
        self.cfg(env_file=str(self.dir / "missing"))
        self.assertFalse(spotify.available())
        self.env.write_text("SPOTIFY_CLIENT_ID=x\n")
        self.cfg(env_file=str(self.env))
        self.assertFalse(spotify.available())

    def test_env_vars_win(self):
        with mock.patch.dict("os.environ", {"SPOTIFY_CLIENT_ID": "e1", "SPOTIFY_CLIENT_SECRET": "e2"}):
            self.assertEqual(spotify._credentials(), ("e1", "e2"))

    def test_token_cached_until_expiry(self):
        (self.dir / "spotify_token.json").write_text(
            json.dumps({"access_token": "TOK", "expires_at": 9e12}))
        self.assertEqual(spotify._token(), "TOK")

    def test_root_shortcuts_parse_uris_and_urls(self):
        self.cfg(env_file=str(self.env), shortcuts=[
            {"name": "A", "uri": "spotify:playlist:PL1"},
            {"name": "B", "url": "https://open.spotify.com/intl-de/artist/AR9?si=x"},
            {"name": "bad", "uri": "spotify:track:T1"}, {"uri": "spotify:album:X"}, "junk"])
        self.assertEqual([(i["title"], i["path"]) for i in spotify.browse(None)],
                         [("A", "playlist:PL1"), ("B", "artist:AR9")])

    def test_search_orders_artists_albums_tracks(self):
        fake = self.api(**{"/search": {
            "artists": {"items": [{"id": "AR", "name": "Band"}]},
            "albums": {"items": [{"id": "AL", "name": "Rec", "artists": [{"name": "Band"}]}]},
            "playlists": {"items": [None, {"id": "PL", "name": "Mix"}]},
            "tracks": {"items": [TRACK, {"name": "no id"}]}}})
        out = spotify.search("band")
        self.assertEqual([(i["kind"], i["title"]) for i in out],
                         [("folder", "Band"), ("folder", "Rec"), ("folder", "Mix"),
                          ("track", "Song")])
        self.assertEqual(out[1]["path"], "album:AL")
        self.assertEqual(out[2]["path"], "playlist:PL")
        self.assertEqual(out[1]["artist"], "Band")
        self.assertEqual((out[3]["artist"], out[3]["album"], out[3]["duration"]),
                         ("A, B", "Album", 200.0))
        self.assertEqual(fake.calls[0][1]["q"], "band")
        self.assertEqual(spotify.search("  "), [])

    def test_browse_artist_album_playlist(self):
        fake = self.api(**{
            "/artists/AR/albums": {"items": [{"id": "AL", "name": "Rec"}]},
            "/albums/AL": {"name": "Rec", "tracks": {"items": [
                {"id": "T9", "name": "One", "artists": [{"name": "Band"}]}]}},
            "/playlists/PL/tracks": {"items": [{"track": TRACK}, {"track": None}, None]}})
        self.assertEqual(spotify.browse("artist:AR")[0]["path"], "album:AL")
        (t,) = spotify.browse("album:AL")
        self.assertEqual((t["title"], t["album"]), ("One", "Rec"))
        self.assertEqual([i["title"] for i in spotify.browse("playlist:PL")], ["Song"])
        self.assertEqual(fake.calls[0][1]["include_groups"], "album,single")

    def test_bad_paths(self):
        for bad in ("nope", "track:T1", "artist:a/b", "artist:", "artist:../x"):
            with self.assertRaises(ValueError):
                spotify.browse(bad)

    def test_resolve_is_a_spotify_handoff(self):
        self.api(**{"/tracks/T1": TRACK})
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = b"img"
        with mock.patch.object(spotify, "urlopen", return_value=resp):
            t = spotify.resolve({"id": "T1"})
        self.assertEqual((t.url, t.handoff, t.video), ("spotify:track:T1", "spotify", False))
        self.assertEqual((t.meta["title"], t.meta["artist"], t.meta["album"]),
                         ("Song", "A, B", "Album"))
        self.assertEqual(Path(t.meta["art"]).read_bytes(), b"img")

    def test_resolve_rejects_bad_ids_and_survives_cover_failure(self):
        for bad in ("", "a b", "x/../y"):
            with self.assertRaises(ValueError):
                spotify.resolve({"id": bad})
        self.api(**{"/tracks/T1": TRACK})
        with mock.patch.object(spotify, "urlopen", side_effect=OSError):
            self.assertIsNone(spotify.resolve({"id": "T1"}).meta["art"])

    def test_sections(self):
        self.assertEqual([s["id"] for s in spotify.sections()], ["shortcuts"])

    def test_shortcuts_section_is_the_old_root(self):
        with mock.patch.object(spotify, "_shortcuts", return_value=["s"]):
            self.assertEqual(spotify.browse("section:shortcuts"), ["s"])
            self.assertEqual(spotify.browse(None), ["s"])


if __name__ == "__main__":
    unittest.main()
