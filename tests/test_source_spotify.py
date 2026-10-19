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


class TestHint(unittest.TestCase):
    def test_hint_mentions_login(self):
        self.assertIn("sqlch spotify-login", spotify.HINT)


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
        self.assertEqual([s["id"] for s in spotify.sections()],
                         ["shortcuts", "playlists", "artists"])

    def test_shortcuts_section_is_the_old_root(self):
        with mock.patch.object(spotify, "_shortcuts", return_value=["s"]):
            self.assertEqual(spotify.browse("section:shortcuts"), ["s"])
            self.assertEqual(spotify.browse(None), ["s"])

    def logged_in(self, value=True):
        p = mock.patch.object(spotify.spotify_auth, "logged_in", return_value=value)
        p.start()
        self.addCleanup(p.stop)

    def test_client_id_and_redirect_port(self):
        self.assertEqual(spotify.client_id(), "abc")
        self.assertEqual(spotify.redirect_port(), 8888)
        self.cfg(env_file=str(self.env), redirect_port=9001)
        self.assertEqual(spotify.redirect_port(), 9001)
        self.cfg(env_file=str(self.env), redirect_port="nope")
        self.assertEqual(spotify.redirect_port(), 8888)
        self.cfg(env_file=str(self.dir / "missing"))
        self.assertIsNone(spotify.client_id())

    def test_get_uses_the_user_token_when_logged_in(self):
        self.logged_in()
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = b'{"ok": 1}'
        with mock.patch.object(spotify.spotify_auth, "access_token",
                               return_value="USER") as at, \
             mock.patch.object(spotify, "urlopen", return_value=resp) as op:
            self.assertEqual(spotify._get("/x"), {"ok": 1})
        self.assertEqual(op.call_args[0][0].get_header("Authorization"), "Bearer USER")
        at.assert_called_once_with("abc")

    def test_get_uses_the_app_token_when_logged_out(self):
        self.logged_in(False)
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = b'{"ok": 1}'
        with mock.patch.object(spotify, "_token", return_value="APP"), \
             mock.patch.object(spotify, "urlopen", return_value=resp) as op:
            spotify._get("/x")
        self.assertEqual(op.call_args[0][0].get_header("Authorization"), "Bearer APP")

    def test_library_sections_need_login(self):
        self.logged_in(False)
        for sec in ("section:playlists", "section:artists"):
            with self.assertRaisesRegex(RuntimeError, "spotify-login"):
                spotify.browse(sec)

    def test_playlists_section_maps_items(self):
        self.logged_in()
        page = {"items": [{"id": "P1", "name": "Mine"}, None, {"name": "no id"}],
                "next": None}
        with mock.patch.object(spotify, "_get", return_value=page) as get:
            out = spotify.browse("section:playlists")
        self.assertEqual([(i["title"], i["kind"], i["path"]) for i in out],
                         [("Mine", "folder", "playlist:P1")])
        get.assert_called_once_with("/me/playlists", {"limit": 50, "offset": 0})

    def test_playlists_page_by_offset_until_next_is_empty(self):
        self.logged_in()
        pages = [{"items": [{"id": f"A{i}", "name": "a"} for i in range(50)], "next": "u"},
                 {"items": [{"id": "B", "name": "b"}], "next": None}]
        with mock.patch.object(spotify, "_get", side_effect=pages) as get:
            out = spotify.browse("section:playlists")
        self.assertEqual(len(out), 51)
        self.assertEqual([c.args[1]["offset"] for c in get.call_args_list], [0, 50])

    def test_playlists_are_capped_at_200(self):
        self.logged_in()
        page = lambda n: {"items": [{"id": f"P{n}-{i}", "name": "p"} for i in range(50)],
                          "next": "more"}
        with mock.patch.object(spotify, "_get", side_effect=[page(n) for n in range(10)]) as get:
            out = spotify.browse("section:playlists")
        self.assertEqual(len(out), 200)
        self.assertEqual(get.call_count, 4)

    def test_artists_section_pages_by_cursor(self):
        self.logged_in()
        pages = [{"artists": {"items": [{"id": "AR1", "name": "One"}],
                              "cursors": {"after": "AR1"}}},
                 {"artists": {"items": [{"id": "AR2", "name": "Two"}, None],
                              "cursors": {"after": None}}}]
        with mock.patch.object(spotify, "_get", side_effect=pages) as get:
            out = spotify.browse("section:artists")
        self.assertEqual([(i["title"], i["path"]) for i in out],
                         [("One", "artist:AR1"), ("Two", "artist:AR2")])
        self.assertEqual(get.call_args_list[0].args,
                         ("/me/following", {"type": "artist", "limit": 50}))
        self.assertEqual(get.call_args_list[1].args,
                         ("/me/following", {"type": "artist", "limit": 50, "after": "AR1"}))

    def test_artists_are_capped_at_200(self):
        self.logged_in()
        n = iter(range(200))

        def page(*a, **k):
            return {"artists": {"items": [{"id": f"X{next(n)}", "name": "x"}
                                          for _ in range(50)],
                                "cursors": {"after": "more"}}}

        with mock.patch.object(spotify, "_get", side_effect=page) as get:
            out = spotify.browse("section:artists")
        self.assertEqual(len(out), 200)
        self.assertEqual(get.call_count, 4)


if __name__ == "__main__":
    unittest.main()
