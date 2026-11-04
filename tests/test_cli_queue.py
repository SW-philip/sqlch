import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from sqlch.cli import main
from sqlch.core import playqueue

KEXP = {"id": "kexp", "name": "KEXP", "url": "http://kexp.example/s", "group": "x"}


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = mock.patch.object(playqueue, "data_dir", lambda: Path(tmp.name))
        p.start()
        self.addCleanup(p.stop)

    def run_cmd(self, fn, args, call=None):
        with mock.patch.object(main, "daemon_call", call or mock.Mock(return_value={"ok": True})) as dc, \
                redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            try:
                fn(args)
                code = None
            except SystemExit as e:
                code = e.code
        return dc, code, out.getvalue(), err.getvalue()


class TestQueueList(Base):
    def test_empty(self):
        _, code, out, _ = self.run_cmd(main.queue_cmd, [])
        self.assertIsNone(code)
        self.assertEqual(out.strip(), "mode: radio")

    def test_lists_now_and_entries(self):
        playqueue.set_mode("media")
        playqueue.set_now(playqueue.make_entry("item", {"source": "x", "id": "1", "title": "Now", "artist": "Me"}))
        playqueue.add(playqueue.make_entry("station", KEXP))
        playqueue.add(playqueue.make_entry("item", {"source": "x", "id": "2", "title": "Later"}))
        _, _, out, _ = self.run_cmd(main.queue_cmd, ["list"])
        self.assertEqual(out.splitlines(), ["mode: media", "now:  Now — Me",
                                            "  1. KEXP", "  2. Later"])


class TestQueueAdd(Base):
    def test_adds_a_known_station(self):
        with mock.patch.object(main.library, "find_station", return_value=KEXP):
            dc, code, _, _ = self.run_cmd(main.queue_cmd, ["add", "kexp"])
        self.assertIsNone(code)
        dc.assert_called_once_with({"cmd": "queue_add", "kind": "station",
                                    "payload": {"id": "kexp", "name": "KEXP",
                                                "url": "http://kexp.example/s"}})

    def test_adds_a_bare_stream_url(self):
        with mock.patch.object(main.library, "find_station", return_value=None):
            dc, _, _, _ = self.run_cmd(main.queue_cmd, ["add", "http://x.example/live"])
        payload = dc.call_args.args[0]["payload"]
        self.assertEqual((payload["name"], payload["url"]),
                         ("http://x.example/live", "http://x.example/live"))

    def test_unknown_station_exits_nonzero(self):
        with mock.patch.object(main.library, "find_station", return_value=None):
            dc, code, _, err = self.run_cmd(main.queue_cmd, ["add", "nonsense"])
        self.assertEqual(code, 1)
        dc.assert_not_called()
        self.assertIn("nonsense", err)

    def test_add_needs_an_argument(self):
        _, code, _, err = self.run_cmd(main.queue_cmd, ["add"])
        self.assertEqual(code, 2)
        self.assertIn("usage", err)

    def test_daemon_down(self):
        with mock.patch.object(main.library, "find_station", return_value=KEXP):
            _, code, _, err = self.run_cmd(main.queue_cmd, ["add", "kexp"],
                                           call=mock.Mock(return_value=None))
        self.assertEqual(code, 1)
        self.assertIn("daemon", err)

    def test_daemon_error_is_shown(self):
        with mock.patch.object(main.library, "find_station", return_value=KEXP):
            _, code, _, err = self.run_cmd(main.queue_cmd, ["add", "kexp"],
                                           call=mock.Mock(return_value={"ok": False, "error": "boom"}))
        self.assertEqual(code, 1)
        self.assertIn("boom", err)


class TestQueueClear(Base):
    def test_clear(self):
        dc, code, _, _ = self.run_cmd(main.queue_cmd, ["clear"])
        self.assertIsNone(code)
        dc.assert_called_once_with({"cmd": "queue_clear"})

    def test_unknown_subcommand(self):
        _, code, _, err = self.run_cmd(main.queue_cmd, ["shuffle"])
        self.assertEqual(code, 2)
        self.assertIn("usage", err)


class TestMode(Base):
    def test_shows_the_mode(self):
        playqueue.set_mode("media")
        dc, _, out, _ = self.run_cmd(main.mode_cmd, [])
        self.assertEqual(out.strip(), "media")
        dc.assert_not_called()

    def test_sets_the_mode(self):
        dc, code, _, _ = self.run_cmd(main.mode_cmd, ["radio"])
        self.assertIsNone(code)
        dc.assert_called_once_with({"cmd": "set_mode", "mode": "radio"})

    def test_rejects_unknown_mode(self):
        dc, code, _, err = self.run_cmd(main.mode_cmd, ["shuffle"])
        self.assertEqual(code, 2)
        dc.assert_not_called()
        self.assertIn("usage", err)

    def test_daemon_down(self):
        _, code, _, err = self.run_cmd(main.mode_cmd, ["media"], call=mock.Mock(return_value=None))
        self.assertEqual(code, 1)
        self.assertIn("daemon", err)


if __name__ == "__main__":
    unittest.main()
