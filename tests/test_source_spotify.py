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

    def test_search_lists_songs_artists_albums_playlists_under_headings(self):
        fake = self.api(**{"/search": {
            "artists": {"items": [{"id": "AR", "name": "Band"}]},
            "albums": {"items": [{"id": "AL", "name": "Rec", "artists": [{"name": "Band"}]}]},
            "playlists": {"items": [None, {"id": "PL", "name": "Mix"}]},
            "tracks": {"items": [TRACK, {"name": "no id"}]}}})
        out = spotify.search("band")
        self.assertEqual([(i["group"], i["kind"], i["title"]) for i in out],
                         [("SONGS", "track", "Song"), ("ARTISTS", "folder", "Band"),
                          ("ALBUMS", "folder", "Rec"), ("PLAYLISTS", "folder", "Mix")])
        self.assertEqual(out[2]["path"], "album:AL")
        self.assertEqual(out[3]["path"], "playlist:PL")
        self.assertEqual(out[2]["artist"], "Band")
        self.assertEqual((out[0]["artist"], out[0]["album"], out[0]["duration"]),
                         ("A, B", "Album", 200.0))
        self.assertEqual(fake.calls[0][1]["q"], "band")
        self.assertEqual(spotify.search("  "), [])

    def test_hover_info(self):
        t = {**TRACK, "track_number": 3, "explicit": True,
             "album": {**TRACK["album"], "release_date": "2019-05-01", "total_tracks": 12}}
        self.assertEqual(spotify._track(t)["info"],
                         "Song\nA, B\nAlbum · 2019\nTrack 3 of 12 · 3:20 · Explicit")
        album = spotify._folder("album", {"id": "AL", "name": "Rec", "album_type": "single",
                                          "release_date": "2020", "total_tracks": 2,
                                          "artists": [{"name": "Band"}]})
        self.assertEqual(album["info"], "Rec\nBand\nSingle · 2020 · 2 tracks")
        pl = spotify._folder("playlist", {"id": "PL", "name": "Mix",
                                          "owner": {"display_name": "me"},
                                          "items": {"total": 40},
                                          "description": "Loud &amp; <a href=x>fast</a>"})
        self.assertEqual(pl["info"], "Mix\nPlaylist by me · 40 tracks\nLoud & fast")
        self.assertEqual(spotify._folder("artist", {"id": "AR", "name": "Band"})["info"],
                         "Band\nArtist")

    def test_artist_page_lists_albums_before_singles(self):
        self.api(**{"/artists/AR/albums": {"items": [
            {"id": "S1", "name": "Hit", "album_type": "single"},
            {"id": "A1", "name": "LP", "album_type": "album"}, None]}})
        self.assertEqual([(i["group"], i["title"]) for i in spotify.browse("artist:AR")],
                         [("ALBUMS", "LP"), ("SINGLES & EPS", "Hit")])

    def test_menu_for_a_track_when_logged_in(self):
        self.logged_in()
        self.api(**{"/tracks/T1": {**TRACK, "artists": [{"id": "AR", "name": "A"}]},
                    "/me/library/contains": [True]})
        entries = spotify.menu({"kind": "track", "id": "T1", "title": "Song"})
        self.assertEqual(entries, [
            {"label": "Go to album: Album", "path": "album:AL1", "title": "Album"},
            {"label": "Go to artist: A", "path": "artist:AR", "title": "A"},
            {"label": "Remove from your library", "action": "remove"},
            {"label": "Add to queue", "action": "queue"},
            {"label": "Copy Spotify link", "copy": "https://open.spotify.com/track/T1"}])

    def test_menu_for_an_artist_follows(self):
        self.logged_in()
        fake = self.api(**{"/me/library/contains": [False]})
        entries = spotify.menu({"kind": "folder", "id": "AR", "path": "artist:AR"})
        self.assertEqual(entries[0], {"label": "Follow", "action": "save"})
        self.assertEqual(fake.calls, [("/me/library/contains", {"uris": "spotify:artist:AR"})])

    def test_menu_logged_out_only_offers_navigation_and_link(self):
        self.logged_in(False)
        self.api(**{"/albums/AL": {"artists": [{"id": "AR", "name": "Band"}, {"name": "x"}]}})
        entries = spotify.menu({"kind": "folder", "id": "AL", "path": "album:AL"})
        self.assertEqual([e.get("path") or e.get("copy") or "note" for e in entries],
                         ["artist:AR", "note", "https://open.spotify.com/album/AL"])

    def test_menu_without_library_scope_says_to_log_in_again(self):
        self.logged_in()
        with mock.patch.object(spotify, "_get", side_effect=OSError):
            entries = spotify.menu({"kind": "folder", "id": "PL", "path": "playlist:PL"})
        self.assertEqual(entries[0], {"label": spotify.RELOGIN, "note": True})

    def test_menu_rejects_bad_items(self):
        for bad in ({"kind": "track", "id": "a/b"}, {"kind": "folder", "path": "nope:X"},
                    {"kind": "folder", "path": "section:playlists"}):
            with self.assertRaises(ValueError):
                spotify.menu(bad)

    def test_act_saves_removes_and_queues_by_uri(self):
        self.logged_in()
        with mock.patch.object(spotify, "_send") as send:
            self.assertEqual(spotify.act({"kind": "track", "id": "T1", "title": "Song"},
                                         "save"), "Saved Song")
            self.assertEqual(spotify.act({"kind": "folder", "path": "artist:AR",
                                          "title": "Band"}, "remove"), "Unfollowed Band")
            self.assertEqual(spotify.act({"kind": "track", "id": "T1", "title": "Song"},
                                         "queue"), "Queued Song")
        self.assertEqual([c.args for c in send.call_args_list], [
            ("PUT", "/me/library", {"uris": "spotify:track:T1"}),
            ("DELETE", "/me/library", {"uris": "spotify:artist:AR"}),
            ("POST", "/me/player/queue", {"uri": "spotify:track:T1"})])
        with self.assertRaises(ValueError):
            spotify.act({"kind": "folder", "path": "album:AL"}, "queue")

    def test_act_needs_login(self):
        self.logged_in(False)
        with self.assertRaisesRegex(RuntimeError, "spotify-login"):
            spotify.act({"kind": "track", "id": "T1"}, "save")

    def test_send_maps_scope_errors_to_relogin(self):
        err = spotify.HTTPError("u", 403, "no", {}, None)
        with mock.patch.object(spotify, "_bearer", return_value="X"), \
             mock.patch.object(spotify, "urlopen", side_effect=err):
            with self.assertRaisesRegex(RuntimeError, "again"):
                spotify._send("PUT", "/me/library", {"uris": "spotify:track:T1"})

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
                         ["playlists", "artists"])

    def test_root_is_playlists(self):
        with mock.patch.object(spotify, "_my_playlists", return_value=[]), \
                mock.patch.object(spotify.spotify_auth, "logged_in", return_value=True):
            self.assertEqual(spotify.browse(None), [])
            self.assertEqual(spotify.browse("section:playlists"), [])

    def test_hint_has_no_shortcuts(self):
        self.assertNotIn("shortcuts", spotify.HINT)

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
