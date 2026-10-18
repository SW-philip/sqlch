import unittest
from pathlib import Path
from unittest import mock

from sqlch.core import daemon, player
from sqlch.sources.base import Target


class TestMpvArgs(unittest.TestCase):
    def _args(self, mpris=None, **kw):
        with mock.patch.object(player, "mpv_bin", return_value="mpv"), \
             mock.patch.object(player, "mpv_socket", return_value=Path("/r/mpv.sock")), \
             mock.patch.object(player, "mpris_plugin", return_value=mpris):
            return player._mpv_args("URL", **kw)

    def test_audio_default(self):
        a = self._args()
        self.assertEqual(a[0], "mpv")
        self.assertIn("--input-ipc-server=/r/mpv.sock", a)
        self.assertIn("--force-window=no", a)
        self.assertIn("--no-video", a)
        self.assertNotIn("--wayland-app-id=sqlch-video", a)
        self.assertEqual(a[-1], "URL")

    def test_mpris_script_inserted_at_index_two(self):
        self.assertEqual(self._args(mpris="/p/mpris.so")[2], "--script=/p/mpris.so")

    def test_video_shows_a_tagged_window(self):
        a = self._args(video=True)
        self.assertIn("--force-window=yes", a)
        self.assertNotIn("--force-window=no", a)
        self.assertIn("--wayland-app-id=sqlch-video", a)
        self.assertNotIn("--no-video", a)

    def test_http_headers_are_passed_to_mpv(self):
        a = self._args(headers=("Authorization: X", "K: v"))
        self.assertIn("--http-header-fields-append=Authorization: X", a)
        self.assertIn("--http-header-fields-append=K: v", a)
        self.assertEqual(a[-1], "URL")
        self.assertFalse(any("http-header" in x for x in self._args()))

    def test_preview_volume(self):
        self.assertIn("--volume=60", self._args(preview=True))


class TestPlayTarget(unittest.TestCase):
    def test_spawns_and_records_current_item(self):
        item = {"source": "local", "id": "a.mp3", "title": "A"}
        with mock.patch.object(player, "stop"), \
             mock.patch.object(player.notify, "notify"), \
             mock.patch.object(player, "_spawn_mpv") as spawn:
            player.play_target(Target("/m/a.mp3", False, {"title": "A"}), item)
        spawn.assert_called_once_with("/m/a.mp3", video=False)
        self.assertEqual(player.current(), {"type": "item", "item": item})

    def test_seek_is_absolute(self):
        with mock.patch.object(player, "mpv_command") as cmd:
            player.seek(42)
        cmd.assert_called_once_with("seek", 42.0, "absolute")

    def test_item_progress(self):
        with mock.patch.object(player, "mpv_get", side_effect=[12.5, 200.0]):
            self.assertEqual(player.item_progress(), (12.5, 200.0))


class TestDaemonItems(unittest.TestCase):
    def setUp(self):
        self.src = mock.Mock()
        self.src.resolve.return_value = Target("/m/a.mp3")
        patch = mock.patch.dict("sqlch.sources.REGISTRY", {"fake": self.src})
        patch.start()
        self.addCleanup(patch.stop)

    def test_play_item_resolves_and_plays(self):
        item = {"source": "fake", "id": "1", "title": "T"}
        with mock.patch.object(player, "play_target") as play:
            resp = daemon._handle({"cmd": "play_item", "item": item})
        self.assertEqual(resp, {"ok": True})
        play.assert_called_once_with(Target("/m/a.mp3"), item)

    def test_play_item_errors(self):
        self.assertFalse(daemon._handle({"cmd": "play_item"})["ok"])
        r = daemon._handle({"cmd": "play_item", "item": {"source": "nope"}})
        self.assertFalse(r["ok"])
        self.src.resolve.side_effect = FileNotFoundError("gone")
        r = daemon._handle({"cmd": "play_item", "item": {"source": "fake"}})
        self.assertFalse(r["ok"])
        self.assertIn("gone", r["error"])

    def test_seek(self):
        with mock.patch.object(player, "seek") as seek:
            self.assertEqual(daemon._handle({"cmd": "seek", "pos": 30}), {"ok": True})
        seek.assert_called_once_with(30.0)
        self.assertFalse(daemon._handle({"cmd": "seek"})["ok"])

    def test_status_reports_progress_only_for_items(self):
        rec = mock.Mock(status=mock.Mock(return_value={"active": False}))
        with mock.patch.object(player, "status_string", return_value="s"), \
             mock.patch.dict("sys.modules", {"sqlch.core.recorder": rec}), \
             mock.patch.object(player, "item_progress", return_value=(5.0, 90.0)):
            with mock.patch.object(player, "current",
                                   return_value={"type": "item", "item": {}}):
                r = daemon._handle({"cmd": "status"})
            self.assertEqual((r["position"], r["duration"]), (5.0, 90.0))
            with mock.patch.object(player, "current",
                                   return_value={"type": "station", "item": {}}):
                r = daemon._handle({"cmd": "status"})
            self.assertNotIn("position", r)


if __name__ == "__main__":
    unittest.main()


class TestNowPlayingInfo(unittest.TestCase):
    def setUp(self):
        old = player._current
        self.addCleanup(setattr, player, "_current", old)
        sock = mock.Mock()
        sock.exists.return_value = True
        p = mock.patch.object(player, "mpv_socket", return_value=sock)
        p.start()
        self.addCleanup(p.stop)

    def test_item_describes_the_source_not_the_last_station(self):
        player._current = {"type": "item", "item": {
            "source": "local", "id": "a.mp3", "title": "Song", "artist": "Band"}}
        with mock.patch.object(player.library, "last_played_station",
                               side_effect=AssertionError("fallback used")), \
             mock.patch.object(player, "mpv_get",
                               side_effect=AssertionError("icy used")):
            info = player.now_playing_info()
            text = player.status_string()
        self.assertEqual(info, {"status": "playing", "station": "LOCAL",
                                "artist": "Band", "track": "Song"})
        self.assertIn("LOCAL", text)
        self.assertIn("Band — Song", text)

    def test_item_without_artist_omits_it(self):
        player._current = {"type": "item", "item": {"source": "local", "title": "S"}}
        self.assertEqual(player.now_playing_info(),
                         {"status": "playing", "station": "LOCAL", "track": "S"})

    def test_station_still_uses_icy(self):
        player._current = {"type": "station", "item": {"name": "KEXP"}}
        with mock.patch.object(player, "mpv_get",
                               return_value={"icy-title": "Artist - Track"}):
            info = player.now_playing_info()
        self.assertEqual(info["station"], "KEXP")
        self.assertEqual(info["track"], "Track")


class TestPlayTargetHeaders(unittest.TestCase):
    def test_headers_only_passed_when_present(self):
        item = {"source": "jellyfin", "id": "T1", "title": "S"}
        with mock.patch.object(player, "stop"), \
             mock.patch.object(player.notify, "notify"), \
             mock.patch.object(player, "_spawn_mpv") as spawn:
            player.play_target(Target("u", True, {"title": "S"}, ("H: v",)), item)
        spawn.assert_called_once_with("u", video=True, headers=("H: v",))


class TestPlayTargetArt(unittest.TestCase):
    def test_target_art_fills_missing_item_art(self):
        item = {"source": "jellyfin", "id": "T1", "title": "S", "art": None}
        with mock.patch.object(player, "stop"), \
             mock.patch.object(player.notify, "notify"), \
             mock.patch.object(player, "_spawn_mpv"):
            player.play_target(Target("u", False, {"title": "S", "art": "/c/a.jpg"}), item)
            self.assertEqual(player.current()["item"]["art"], "/c/a.jpg")
            self.assertIsNone(item["art"])
