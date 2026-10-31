import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlch.core import daemon, playqueue

TRACK = {"source": "fake", "id": "a", "title": "A", "kind": "track"}
KEXP = {"id": "kexp", "name": "KEXP", "url": "http://kexp.example/s"}


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = mock.patch.object(playqueue, "data_dir", lambda: Path(tmp.name))
        p.start()
        self.addCleanup(p.stop)
        self.transport = mock.patch.object(daemon, "transport").start()
        self.addCleanup(mock.patch.stopall)
        self.player = mock.patch.object(daemon, "player").start()
        self.player.current.return_value = None
        self.transport.play_entry.return_value = True

    def call(self, **msg):
        return daemon._handle(msg)

    def uids(self):
        return [e["uid"] for e in playqueue.read()["entries"]]


class TestQueueAdd(Base):
    def test_queues_when_something_is_waiting(self):
        playqueue.add(playqueue.make_entry("item", TRACK))
        r = self.call(cmd="queue_add", kind="station", payload=KEXP)
        self.assertEqual((r["ok"], r["played"], r["index"]), (True, False, 1))
        self.assertEqual(len(self.uids()), 2)
        self.transport.play_entry.assert_not_called()

    def test_queues_when_something_is_playing(self):
        self.player.current.return_value = {"type": "item", "item": TRACK}
        r = self.call(cmd="queue_add", kind="station", payload=KEXP)
        self.assertFalse(r["played"])
        self.assertEqual(len(self.uids()), 1)

    def test_plays_at_once_when_idle_and_empty(self):
        r = self.call(cmd="queue_add", kind="station", payload=KEXP)
        self.assertEqual((r["ok"], r["played"]), (True, True))
        self.assertEqual(self.uids(), [])
        (entry,), _ = self.transport.play_entry.call_args
        self.assertEqual(entry["station"]["id"], "kexp")

    def test_idle_play_failure_is_reported(self):
        self.transport.play_entry.return_value = False
        r = self.call(cmd="queue_add", kind="station", payload=KEXP)
        self.assertFalse(r["ok"])
        self.assertIn("error", r)

    def test_at_and_play_next(self):
        a = playqueue.make_entry("item", TRACK)
        playqueue.add(a)
        self.call(cmd="queue_add", kind="station", payload=KEXP, at=0)
        self.assertEqual(playqueue.read()["entries"][0]["kind"], "station")
        self.call(cmd="queue_add", kind="item", payload={**TRACK, "id": "z"}, play_next=True)
        self.assertEqual(playqueue.read()["entries"][0]["item"]["id"], "z")

    def test_station_with_a_bad_url_is_refused(self):
        r = self.call(cmd="queue_add", kind="station",
                      payload={"id": "x", "name": "X", "url": "file:///etc/passwd"})
        self.assertEqual((r["ok"], r["error"]), (False, "not a stream address"))
        self.assertEqual(self.uids(), [])
        self.transport.play_entry.assert_not_called()

    def test_bad_payload(self):
        self.assertFalse(self.call(cmd="queue_add", kind="item", payload={})["ok"])
        self.assertFalse(self.call(cmd="queue_add")["ok"])


class TestQueueEdits(Base):
    def setUp(self):
        super().setUp()
        self.a = playqueue.make_entry("item", TRACK)
        self.b = playqueue.make_entry("station", KEXP)
        playqueue.add(self.a)
        playqueue.add(self.b)

    def test_remove(self):
        self.assertTrue(self.call(cmd="queue_remove", uid=self.a["uid"])["ok"])
        self.assertEqual(self.uids(), [self.b["uid"]])
        self.assertFalse(self.call(cmd="queue_remove", uid="nope")["ok"])

    def test_move(self):
        self.assertTrue(self.call(cmd="queue_move", uid=self.a["uid"], to=1)["ok"])
        self.assertEqual(self.uids(), [self.b["uid"], self.a["uid"]])
        self.assertFalse(self.call(cmd="queue_move", uid="nope", to=0)["ok"])
        self.assertFalse(self.call(cmd="queue_move", uid=self.a["uid"])["ok"])
        self.assertFalse(self.call(cmd="queue_move", uid=self.a["uid"], to="1")["ok"])

    def test_clear(self):
        self.assertTrue(self.call(cmd="queue_clear")["ok"])
        self.assertEqual(self.uids(), [])

    def test_play_jumps_and_drops_the_ones_before(self):
        self.assertTrue(self.call(cmd="queue_play", uid=self.b["uid"])["ok"])
        (entry,), _ = self.transport.play_entry.call_args
        self.assertEqual(entry["uid"], self.b["uid"])
        self.assertEqual(self.uids(), [])
        self.assertFalse(self.call(cmd="queue_play", uid="nope")["ok"])


class TestSetModeAndStatus(Base):
    def test_set_mode(self):
        self.assertEqual(self.call(cmd="set_mode", mode="media"), {"ok": True})
        self.transport.set_mode.assert_called_once_with("media")

    def test_set_mode_rejects_unknown(self):
        self.transport.set_mode.side_effect = ValueError("unknown mode: x")
        r = self.call(cmd="set_mode", mode="x")
        self.assertEqual((r["ok"], r["error"]), (False, "unknown mode: x"))

    def test_status_reports_mode_and_queue_length(self):
        playqueue.set_mode("media")
        playqueue.add(playqueue.make_entry("item", TRACK))
        rec = mock.Mock(status=mock.Mock(return_value={"active": False}))
        self.player.status_string.return_value = "s"
        with mock.patch.dict("sys.modules", {"sqlch.core.recorder": rec}):
            r = self.call(cmd="status")
        self.assertEqual((r["mode"], r["queue_len"]), ("media", 1))


class TestRouting(Base):
    def test_next_prev_stop_go_through_transport(self):
        with mock.patch.object(daemon, "track_once"):
            self.call(cmd="next")
            self.transport.next_cmd.assert_called_once_with()
            self.call(cmd="prev")
            self.transport.prev_cmd.assert_called_once_with()
            self.call(cmd="stop")
            self.transport.stop.assert_called_once_with()

    def test_play_station_goes_through_transport(self):
        with mock.patch.object(daemon, "track_once"), \
             mock.patch.object(daemon.library, "find_station", return_value=KEXP):
            r = self.call(cmd="play", query="kexp")
        self.assertTrue(r["ok"])
        self.transport.start_station.assert_called_once_with(KEXP)

    def test_play_item_passes_context_and_resume(self):
        with mock.patch.object(daemon, "track_once"):
            r = self.call(cmd="play_item", item=TRACK, context=[TRACK], resume=True)
        self.assertEqual(r, {"ok": True})
        self.transport.start_item.assert_called_once_with(TRACK, context=[TRACK], resume=True)

    def test_play_item_ignores_a_non_list_context(self):
        with mock.patch.object(daemon, "track_once"):
            self.call(cmd="play_item", item=TRACK, context="junk")
        self.transport.start_item.assert_called_once_with(TRACK, context=None, resume=False)

    def test_play_item_passes_the_source_play_mode(self):
        with mock.patch.object(daemon, "track_once"):
            self.call(cmd="play_item", item=TRACK, mode="album")
        self.transport.start_item.assert_called_once_with(
            TRACK, context=None, resume=False, mode="album")

    def test_play_item_error_is_returned(self):
        self.transport.PlayError = Exception
        self.transport.start_item.side_effect = Exception("resolve failed: x")
        with mock.patch.object(daemon, "track_once"):
            r = self.call(cmd="play_item", item=TRACK)
        self.assertEqual((r["ok"], r["error"]), (False, "resolve failed: x"))


class TestLoops(Base):
    def test_track_loop_body_parks_and_swallows_errors(self):
        with mock.patch.object(daemon, "track_once", side_effect=RuntimeError("x")):
            daemon.sample_once()
        self.transport.park.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
