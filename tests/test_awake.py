import unittest
from unittest import mock

from sqlch.core import awake


def state(cur, **props):
    props = {"vid": 1, "pause": False, "eof-reached": False, "idle-active": False, **props}
    return (mock.patch.object(awake.player, "current", return_value=cur),
            mock.patch.object(awake.player, "mpv_get", side_effect=props.get))


VIDEO = {"type": "item", "item": {"source": "youtube", "kind": "video"}}


class WantedTests(unittest.TestCase):
    def check(self, expected, cur, **kw):
        a, b = state(cur, **kw)
        with a, b:
            self.assertIs(awake.wanted(), expected)

    def test_video_counts(self):
        self.check(True, VIDEO)

    def test_audio_does_not(self):
        self.check(False, {"type": "item", "item": {"source": "podcasts"}}, vid=False)
        self.check(False, {"type": "station"})
        self.check(False, {**VIDEO, "handoff": "spotify"})
        self.check(False, None)

    def test_paused_finished_or_gone_do_not(self):
        for props in ({"pause": True}, {"pause": None}, {"vid": None},
                      {"eof-reached": True}, {"idle-active": True}):
            self.check(False, VIDEO, **props)


class HoldTests(unittest.TestCase):
    def test_one_inhibitor_held_then_released(self):
        proc = mock.Mock(**{"poll.return_value": None})
        with mock.patch.object(awake.subprocess, "Popen", return_value=proc) as popen, \
                mock.patch.object(awake.shutil, "which", side_effect=lambda n: "/bin/" + n), \
                mock.patch.object(awake, "wanted", side_effect=[True, True, False]):
            for _ in range(3):
                awake.update()
        popen.assert_called_once()
        self.assertIn("--what=idle", popen.call_args.args[0])
        proc.stdin.close.assert_called_once()
