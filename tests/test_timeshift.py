import unittest
from pathlib import Path
from unittest import mock

import gi
gi.require_version("Gtk", "4.0")

from sqlch.core import daemon, player
from sqlch_gui.ui.controls import TimelineBar


def _args(**kw):
    with mock.patch.object(player, "mpv_bin", return_value="mpv"), \
         mock.patch.object(player, "mpv_socket", return_value=Path("/r/s")), \
         mock.patch.object(player, "mpris_plugin", return_value=None):
        return player._mpv_args("URL", **kw)


def _mpv(state, pos):
    return lambda prop: {"demuxer-cache-state": state, "time-pos": pos}[prop]


class TestBufferArgs(unittest.TestCase):
    def test_station_gets_hour_buffer(self):
        a = _args(timeshift=True)
        self.assertIn("--cache-secs=3600", a)
        self.assertIn(f"--demuxer-max-bytes={player.TIMESHIFT_BYTES}", a)
        self.assertIn(f"--demuxer-max-back-bytes={player.TIMESHIFT_BYTES}", a)
        self.assertEqual(a[-1], "URL")

    def test_default_has_no_hour_buffer(self):
        self.assertFalse(any(x.startswith("--cache-secs") for x in _args()))


class TestTimeshift(unittest.TestCase):
    STATE = {"seekable-ranges": [{"start": 100.0, "end": 400.0}]}

    def test_reads_playhead_and_span(self):
        with mock.patch.object(player, "mpv_get", _mpv(self.STATE, 380.0)):
            self.assertEqual(player.timeshift(),
                             {"pos": 380.0, "start": 100.0, "end": 400.0})

    def test_none_without_ranges_or_pos(self):
        with mock.patch.object(player, "mpv_get", _mpv({}, 5.0)):
            self.assertIsNone(player.timeshift())
        with mock.patch.object(player, "mpv_get", _mpv(self.STATE, None)):
            self.assertIsNone(player.timeshift())

    def test_seek_relative_clamps(self):
        with mock.patch.object(player, "mpv_get", _mpv(self.STATE, 110.0)), \
             mock.patch.object(player, "seek") as seek:
            player.seek_relative(-15)
            seek.assert_called_with(100.0)
            player.seek_relative(1000)
            seek.assert_called_with(400.0 - player.LIVE_MARGIN)

    def test_go_live(self):
        with mock.patch.object(player, "mpv_get", _mpv(self.STATE, 150.0)), \
             mock.patch.object(player, "seek") as seek:
            player.go_live()
        seek.assert_called_once_with(400.0 - player.LIVE_MARGIN)

    def test_noop_without_buffer(self):
        with mock.patch.object(player, "mpv_get", _mpv({}, None)), \
             mock.patch.object(player, "seek") as seek:
            player.seek_relative(15)
            player.go_live()
        seek.assert_not_called()


class TestDaemon(unittest.TestCase):
    def test_commands(self):
        with mock.patch.object(player, "seek_relative") as rel, \
             mock.patch.object(player, "go_live") as live:
            self.assertEqual(daemon._handle({"cmd": "seek_rel", "delta": "-15"}), {"ok": True})
            rel.assert_called_once_with(-15.0)
            self.assertFalse(daemon._handle({"cmd": "seek_rel"})["ok"])
            self.assertEqual(daemon._handle({"cmd": "go_live"}), {"ok": True})
            live.assert_called_once_with()

    def test_status_carries_timeshift_for_stations_only(self):
        ts = {"pos": 1.0, "start": 0.0, "end": 2.0}
        with mock.patch.object(player, "current", return_value={"type": "station", "item": {}}), \
             mock.patch.object(player, "status_string", return_value="x"), \
             mock.patch.object(player, "timeshift", return_value=ts), \
             mock.patch("sqlch.core.recorder.status", return_value={}):
            self.assertEqual(daemon._handle({"cmd": "status"})["timeshift"], ts)


class TestTimelineBar(unittest.TestCase):
    def test_hidden_until_enough_buffer(self):
        bar = TimelineBar()
        self.assertFalse(bar.get_visible())
        for ts in (None, {"pos": 5, "start": 0, "end": 5}):
            bar.set_state(ts)
            self.assertFalse(bar.get_visible())
        bar.set_state({"pos": 60, "start": 0, "end": 60})
        self.assertTrue(bar.get_visible())

    def test_label_and_live_button(self):
        bar = TimelineBar()
        bar.set_state({"pos": 59, "start": 0, "end": 60})
        self.assertEqual(bar._label.get_text(), "LIVE")
        self.assertFalse(bar._live.get_sensitive())
        bar.set_state({"pos": 0, "start": 0, "end": 750})
        self.assertEqual(bar._label.get_text(), "−12:30 behind live")
        self.assertTrue(bar._live.get_sensitive())

    def test_buttons_emit(self):
        bar = TimelineBar()
        got = []
        bar.connect("seek-relative", lambda _b, d: got.append(("rel", d)))
        bar.connect("go-live", lambda _b: got.append(("live",)))
        bar._back.emit("clicked")
        bar._fwd.emit("clicked")
        bar._live.emit("clicked")
        self.assertEqual(got, [("rel", -15.0), ("rel", 15.0), ("live",)])

    def test_poll_does_not_fight_user_seek(self):
        bar = TimelineBar()
        ts = {"pos": 100, "start": 0, "end": 200}
        bar.set_state(ts)
        bar._ts = dict(ts)
        bar._strip.get_width = lambda: 100
        got = []
        bar.connect("seek-requested", lambda _b, p: got.append(p))
        bar._seek_to_x(25)
        self.assertEqual(got, [50.0])
        bar.set_state(dict(ts, pos=190))
        self.assertEqual(bar._ts["pos"], 50.0)
        bar._hold_until = 0
        bar.set_state(dict(ts, pos=190))
        self.assertEqual(bar._ts["pos"], 190)


if __name__ == "__main__":
    unittest.main()
