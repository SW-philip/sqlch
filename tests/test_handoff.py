import subprocess
import unittest
from unittest import mock

from sqlch.core import handoff, player
from sqlch.sources.base import Target


def cp(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


class TestMpris(unittest.TestCase):
    def setUp(self):
        self.h = handoff.Mpris("spotify", "spotify")

    def test_play_opens_uri_when_running(self):
        calls = []

        def pc(*a, player):
            calls.append(a)
            return cp(0, "spotify\n")

        with mock.patch.object(handoff, "_playerctl", pc):
            self.h.play("spotify:track:T1")
        self.assertEqual(calls[-1], ("open", "spotify:track:T1"))

    def test_play_launches_app_and_waits(self):
        states = iter([False, False, True])
        with mock.patch.object(self.h, "_running", lambda: next(states)), \
             mock.patch.object(handoff.shutil, "which", return_value="/bin/spotify"), \
             mock.patch.object(handoff.subprocess, "Popen") as popen, \
             mock.patch.object(handoff.time, "sleep"), \
             mock.patch.object(handoff, "_playerctl", return_value=cp(0)):
            self.h.play("spotify:track:T1")
        popen.assert_called_once()

    def test_not_installed_and_refused(self):
        with mock.patch.object(self.h, "_running", lambda: False), \
             mock.patch.object(handoff.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "not installed"):
                self.h.play("x")
        with mock.patch.object(self.h, "_running", lambda: True), \
             mock.patch.object(handoff, "_playerctl", return_value=cp(1, err="no good")):
            with self.assertRaisesRegex(RuntimeError, "no good"):
                self.h.play("x")

    def test_stop_never_raises(self):
        with mock.patch.object(handoff, "_playerctl", side_effect=RuntimeError):
            self.h.stop()


class TestPlayerHandoff(unittest.TestCase):
    def setUp(self):
        self.item = {"source": "spotify", "id": "T1", "title": "S"}
        self.t = Target("spotify:track:T1", False, {"title": "S", "art": "/c/a.jpg"},
                        handoff="spotify")
        p = mock.patch.object(player.notify, "notify")
        p.start()
        self.addCleanup(p.stop)

    def test_play_target_hands_off_without_mpv(self):
        with mock.patch.object(player, "stop"), \
             mock.patch.object(player, "_spawn_mpv") as spawn, \
             mock.patch.object(player.handoff, "play") as play:
            player.play_target(self.t, self.item)
        spawn.assert_not_called()
        play.assert_called_once_with("spotify", "spotify:track:T1", None)
        cur = player.current()
        self.assertEqual((cur["handoff"], cur["item"]["art"]), ("spotify", "/c/a.jpg"))

    def test_pause_and_stop_go_to_the_handoff(self):
        with mock.patch.object(player, "stop"), mock.patch.object(player.handoff, "play"):
            player.play_target(self.t, self.item)
        with mock.patch.object(player.handoff, "toggle") as toggle:
            player.pause()
        toggle.assert_called_once_with("spotify")
        with mock.patch.object(player.handoff, "stop") as stop, \
             mock.patch.object(player, "_kill_existing"), \
             mock.patch("sqlch.core.recorder.stop"):
            player.stop(notify_user=False)
        stop.assert_called_once_with("spotify")
        self.assertIsNone(player.current())

    def test_now_playing_info_without_mpv(self):
        with mock.patch.object(player, "stop"), mock.patch.object(player.handoff, "play"):
            player.play_target(self.t, self.item)
        self.addCleanup(setattr, player, "_current", None)
        with mock.patch.object(player, "mpv_socket") as sock:
            sock.return_value.exists.return_value = False
            info = player.now_playing_info()
        self.assertEqual((info["status"], info["station"], info["track"]),
                         ("playing", "SPOTIFY", "S"))


class TestFollowHandoff(unittest.TestCase):
    def setUp(self):
        player._current = {"type": "item", "handoff": "spotify",
                           "item": {"source": "spotify", "id": "T1", "title": "S"}}
        self.addCleanup(setattr, player, "_current", None)
        src = mock.Mock()
        src.resolve.return_value = Target("spotify:track:T2", False,
                                          {"title": "Next", "artist": "A", "album": "Al",
                                           "art": "/c/n.jpg"}, handoff="spotify")
        p = mock.patch.dict("sqlch.sources.REGISTRY", {"spotify": src})
        p.start()
        self.addCleanup(p.stop)
        self.src = src

    def test_autoplayed_track_replaces_the_item(self):
        with mock.patch.object(player.handoff, "track_uri", return_value="spotify:track:T2"):
            cur = player.current()
        self.assertEqual((cur["item"]["id"], cur["item"]["title"], cur["item"]["artist"],
                          cur["item"]["art"], cur["handoff"]),
                         ("T2", "Next", "A", "/c/n.jpg", "spotify"))

    def test_same_track_does_not_resolve(self):
        with mock.patch.object(player.handoff, "track_uri", return_value="spotify:track:T1"):
            player.current()
        self.src.resolve.assert_not_called()

    def test_failed_lookup_keeps_item_and_is_not_retried(self):
        self.src.resolve.side_effect = OSError("offline")
        with mock.patch.object(player.handoff, "track_uri", return_value="spotify:track:T2"):
            self.assertEqual(player.current()["item"]["id"], "T1")
            player.current()
        self.assertEqual(self.src.resolve.call_count, 1)

    def test_unknown_uri_is_ignored(self):
        with mock.patch.object(player.handoff, "track_uri", return_value=None):
            self.assertEqual(player.current()["item"]["id"], "T1")


class TestTrackUri(unittest.TestCase):
    def test_mpris_parses_spotify_trackid(self):
        h = handoff.Mpris("spotify", "spotify")
        with mock.patch.object(handoff, "_playerctl",
                               return_value=cp(0, "/com/spotify/track/4uLU6hMCjMI75M1A2tKUQC\n")):
            self.assertEqual(h.track_uri(), "spotify:track:4uLU6hMCjMI75M1A2tKUQC")
        with mock.patch.object(handoff, "_playerctl", return_value=cp(1)):
            self.assertIsNone(h.track_uri())


if __name__ == "__main__":
    unittest.main()


class TestHandoffState(unittest.TestCase):
    def test_mpris_status_words(self):
        h = handoff.Mpris("spotify", "spotify")
        for out, want in (("Playing\n", "playing"), ("Paused\n", "paused"),
                          ("Stopped\n", "stopped"), ("wat\n", None), ("", None)):
            with mock.patch.object(handoff, "_playerctl", return_value=cp(0, out)):
                self.assertEqual(h.state(), want, out)

    def test_mpris_nonzero_is_unknown(self):
        with mock.patch.object(handoff, "_playerctl", return_value=cp(1, "Playing\n")):
            self.assertIsNone(handoff.Mpris("spotify", "spotify").state())

    def test_librespot_status(self):
        h = handoff.Librespot()
        trk = {"uri": "spotify:track:T1"}
        for status, want in (({"stopped": True, "track": trk}, "stopped"),
                             ({"stopped": False, "paused": True, "track": trk}, "paused"),
                             ({"stopped": False, "paused": False, "track": trk}, "playing"),
                             ({"track": trk}, "playing"),
                             ({}, None), (None, None)):
            with mock.patch.object(h, "_call", return_value=status):
                self.assertEqual(h.state(), want, status)

    def test_librespot_down_is_unknown(self):
        h = handoff.Librespot()
        with mock.patch.object(h, "_call", side_effect=OSError("down")):
            self.assertIsNone(h.state())

    def test_preferred_delegates_to_active(self):
        a, b = mock.Mock(), mock.Mock()
        a.state.return_value, b.state.return_value = "paused", "playing"
        pref = handoff.Preferred(a, b)
        self.assertEqual(pref.state(), "playing")
        pref.active = a
        self.assertEqual(pref.state(), "paused")

    def test_module_state_swallows_errors(self):
        for exc in (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            h = mock.Mock()
            h.state.side_effect = exc("x")
            with mock.patch.dict(handoff.HANDLERS, {"t": h}):
                self.assertIsNone(handoff.state("t"))
        h.state.side_effect = None
        h.state.return_value = "stopped"
        with mock.patch.dict(handoff.HANDLERS, {"t": h}):
            self.assertEqual(handoff.state("t"), "stopped")
