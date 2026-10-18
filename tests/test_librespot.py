import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

from sqlch.core import handoff, player


class Api(BaseHTTPRequestHandler):
    log: list = []
    status = (200, {"track": {"position": 12500, "duration": 200000}})
    ready = True

    def _reply(self, code, body=None):
        raw = json.dumps(body).encode() if body is not None else b""
        self.send_response(code)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        Api.log.append(("GET", self.path, None))
        if self.path == "/":
            self._reply(200, {"playback_ready": Api.ready})
        elif self.path == "/status":
            self._reply(*Api.status)
        else:
            self._reply(404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n)) if n else None
        Api.log.append(("POST", self.path, body))
        self._reply(200)

    def log_message(self, *a):
        pass


class TestLibrespot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Api)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        Api.log = []
        Api.ready = True
        Api.status = (200, {"track": {"position": 12500, "duration": 200000}})
        self.lib = handoff.Librespot(self.base)

    def test_usable_needs_playback_ready(self):
        self.assertTrue(self.lib.usable())
        Api.ready = False
        self.assertFalse(self.lib.usable())

    def test_unreachable_is_not_usable(self):
        self.assertFalse(handoff.Librespot("http://127.0.0.1:1").usable())

    def test_controls_hit_the_right_endpoints(self):
        self.lib.play("spotify:track:T1")
        self.lib.toggle()
        self.lib.stop()
        self.lib.seek(42.5)
        self.assertEqual(Api.log, [
            ("POST", "/player/play", {"uri": "spotify:track:T1"}),
            ("POST", "/player/playpause", None),
            ("POST", "/player/pause", None),
            ("POST", "/player/seek", {"position": 42500})])

    def test_progress_in_seconds(self):
        self.assertEqual(self.lib.progress(), (12.5, 200.0))

    def test_progress_when_idle_or_down(self):
        Api.status = (204, None)
        self.assertEqual(self.lib.progress(), (None, None))
        Api.status = (200, {"track": None})
        self.assertEqual(self.lib.progress(), (None, None))
        self.assertEqual(handoff.Librespot("http://127.0.0.1:1").progress(), (None, None))

    def test_play_failure_is_a_runtime_error(self):
        with self.assertRaisesRegex(RuntimeError, "go-librespot"):
            handoff.Librespot("http://127.0.0.1:1").play("x")

    def test_stop_never_raises_when_down(self):
        handoff.Librespot("http://127.0.0.1:1").stop()


class TestPreferred(unittest.TestCase):
    def setUp(self):
        self.a, self.b = mock.Mock(), mock.Mock()
        self.p = handoff.Preferred(self.a, self.b)

    def test_primary_when_usable_and_sticks(self):
        self.a.usable.return_value = True
        self.p.play("u")
        self.a.usable.return_value = False  # went away mid-track
        self.p.toggle()
        self.p.seek(5)
        self.p.progress()
        self.a.play.assert_called_once_with("u")
        self.a.toggle.assert_called_once()
        self.a.seek.assert_called_once_with(5)
        self.a.progress.assert_called_once()
        self.b.play.assert_not_called()

    def test_falls_back_when_primary_unusable(self):
        self.a.usable.return_value = False
        self.p.play("u")
        self.p.stop()
        self.b.play.assert_called_once_with("u")
        self.b.stop.assert_called_once()
        self.a.play.assert_not_called()

    def test_falls_back_when_primary_play_fails(self):
        self.a.usable.return_value = True
        self.a.play.side_effect = RuntimeError("no active session")
        self.p.play("u")
        self.b.play.assert_called_once_with("u")
        self.p.stop()
        self.b.stop.assert_called_once()
        self.a.stop.assert_not_called()

    def test_mpris_has_no_progress(self):
        m = handoff.Mpris("spotify", "spotify")
        self.assertEqual(m.progress(), (None, None))
        m.seek(3)


class TestPlayerRouting(unittest.TestCase):
    def tearDown(self):
        player._current = None

    def test_seek_and_progress_go_to_the_handoff(self):
        player._current = {"type": "item", "item": {}, "handoff": "spotify"}
        with mock.patch.object(player.handoff, "seek") as seek, \
             mock.patch.object(player.handoff, "progress", return_value=(1.0, 2.0)), \
             mock.patch.object(player, "mpv_command") as cmd:
            player.seek(9)
            self.assertEqual(player.item_progress(), (1.0, 2.0))
        seek.assert_called_once_with("spotify", 9.0)
        cmd.assert_not_called()

    def test_without_handoff_still_uses_mpv(self):
        player._current = {"type": "item", "item": {}}
        with mock.patch.object(player, "mpv_command") as cmd:
            player.seek(9)
        cmd.assert_called_once_with("seek", 9.0, "absolute")


if __name__ == "__main__":
    unittest.main()
