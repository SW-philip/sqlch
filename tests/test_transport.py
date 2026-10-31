import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlch.core import playqueue, transport

A = {"source": "fake", "id": "a", "title": "A", "kind": "track"}
B = {"source": "fake", "id": "b", "title": "B", "kind": "track"}
C = {"source": "fake", "id": "c", "title": "C", "kind": "track"}
KEXP = {"id": "kexp", "name": "KEXP", "url": "http://kexp.example/s"}
WXPN = {"id": "wxpn", "name": "WXPN", "url": "http://wxpn.example/s"}


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.patch(mock.patch.object(playqueue, "data_dir", lambda: Path(tmp.name)))
        self.player = self.patch(mock.patch.object(transport, "player"))
        self.player.current.return_value = None
        self.player.item_progress.return_value = (None, None)
        self.library = self.patch(mock.patch.object(transport, "library"))
        self.notify = self.patch(mock.patch.object(transport, "notify"))
        self.src = mock.Mock()
        self.src.resolve.side_effect = lambda item: f"target:{item.get('id')}"
        self.patch(mock.patch.dict("sqlch.sources.REGISTRY", {"fake": self.src}))
        transport._fails = 0

    def patch(self, p):
        m = p.start()
        self.addCleanup(p.stop)
        return m

    def item(self, it=A):
        return playqueue.make_entry("item", it)

    def station(self, st=KEXP):
        return playqueue.make_entry("station", st)

    def playing(self, entry, mode="media"):
        playqueue.set_mode(mode)
        playqueue.set_now(entry)

    def played_ids(self):
        return [c.args[1]["id"] for c in self.player.play_target.call_args_list]

    def state(self):
        return playqueue.read()


class TestStartItem(Base):
    def test_plays_sets_media_now_and_context(self):
        transport.start_item(B, context=[A, B, C])
        self.player.play_target.assert_called_once_with("target:b", B, start=None)
        s = self.state()
        self.assertEqual((s["mode"], s["now"]["item"]), ("media", B))
        self.assertEqual(s["context"]["index"], 1)

    def test_no_context_clears_the_old_one(self):
        transport.start_item(A, context=[A, B])
        transport.start_item(B)
        self.assertIsNone(self.state()["context"])

    def test_resume_uses_the_saved_point(self):
        with mock.patch.object(transport.progress, "get", return_value={"position": 300}), \
             mock.patch.object(transport.progress, "resume_point", return_value=300.0):
            transport.start_item(A, resume=True)
        self.player.play_target.assert_called_once_with("target:a", A, start=300.0)

    def test_unknown_source_and_resolve_errors(self):
        with self.assertRaisesRegex(transport.PlayError, "unknown source: nope"):
            transport.start_item({"source": "nope", "id": "x"})
        self.src.resolve.side_effect = FileNotFoundError("gone")
        with self.assertRaisesRegex(transport.PlayError, "resolve failed: gone"):
            transport.start_item(A)
        self.player.play_target.assert_not_called()

    def test_item_without_id_still_plays_but_is_not_recorded(self):
        transport.start_item({"source": "fake", "title": "t"})
        self.player.play_target.assert_called_once()
        self.assertIsNone(self.state()["now"])


class TestStartStation(Base):
    def test_sets_radio_and_now(self):
        self.player.current.return_value = {"type": "station"}
        transport.start_station(KEXP)
        self.player.play_station.assert_called_once_with(KEXP)
        s = self.state()
        self.assertEqual((s["mode"], s["now"]["station"]["id"]), ("radio", "kexp"))

    def test_parks_the_playing_item_first(self):
        self.player.current.return_value = {"type": "item", "item": A}
        self.player.item_progress.return_value = (120.0, 300.0)
        transport.start_station(KEXP)
        r = self.state()["resume"]
        self.assertEqual((r["entry"]["item"]["id"], r["pos"], r["dur"]), ("a", 120.0, 300.0))

    def test_station_that_would_not_start_changes_nothing(self):
        self.player.current.return_value = None
        transport.start_station(KEXP)
        self.assertEqual(self.state()["mode"], "radio")
        self.assertIsNone(self.state()["now"])


class TestPark(Base):
    def test_ignores_radio_idle_and_unloaded(self):
        for cur in (None, {"type": "station", "item": KEXP}):
            self.player.current.return_value = cur
            transport.park()
        self.player.current.return_value = {"type": "item", "item": A}
        self.player.item_progress.return_value = (0, None)
        transport.park()
        self.assertIsNone(self.state()["resume"])


class TestAdvance(Base):
    def test_plays_the_head_and_files_the_finished_one(self):
        a, b = self.item(A), self.item(B)
        self.playing(a)
        playqueue.add(b)
        self.assertTrue(transport.advance())
        self.assertEqual(self.played_ids(), ["b"])
        s = self.state()
        self.assertEqual((s["entries"], s["now"]["uid"], s["mode"]), ([], b["uid"], "media"))
        self.assertEqual([h["uid"] for h in s["history"]], [a["uid"]])

    def test_falls_back_to_the_context(self):
        playqueue.set_context([A, B, C], "a")
        self.playing(self.item(A))
        self.assertTrue(transport.advance())
        self.assertEqual(self.played_ids(), ["b"])
        self.assertTrue(transport.advance())
        self.assertEqual(self.played_ids(), ["b", "c"])
        self.assertFalse(transport.advance())

    def test_explicit_queue_beats_the_context(self):
        playqueue.set_context([A, B], "a")
        self.playing(self.item(A))
        playqueue.add(self.item(C))
        transport.advance()
        self.assertEqual(self.played_ids(), ["c"])

    def test_nothing_left(self):
        self.playing(self.item(A))
        self.assertFalse(transport.advance())
        self.player.play_target.assert_not_called()

    def test_station_entry_flips_to_radio_and_keeps_the_rest(self):
        self.playing(self.item(A))
        st, b = self.station(), self.item(B)
        playqueue.add(st)
        playqueue.add(b)
        self.player.current.return_value = {"type": "station"}
        self.assertTrue(transport.advance())
        self.player.play_station.assert_called_once_with(st["station"])
        s = self.state()
        self.assertEqual((s["mode"], s["now"]["uid"]), ("radio", st["uid"]))
        self.assertEqual([e["uid"] for e in s["entries"]], [b["uid"]])
        self.assertEqual((s["resume"]["entry"]["uid"], s["resume"]["pos"]), (b["uid"], 0.0))

    def test_station_entry_with_nothing_after_clears_resume(self):
        playqueue.set_resume(self.item(A), 50.0, 100.0)
        playqueue.add(self.station())
        self.player.current.return_value = {"type": "station"}
        transport.advance()
        self.assertIsNone(self.state()["resume"])

    def test_unplayable_entries_are_skipped_with_a_notice(self):
        self.playing(self.item(A))
        bad = self.item({"source": "fake", "id": "bad"})
        good = self.item(C)
        self.src.resolve.side_effect = (
            lambda item: (_ for _ in ()).throw(OSError("nope")) if item["id"] == "bad"
            else f"target:{item['id']}")
        playqueue.add(bad)
        playqueue.add(good)
        self.assertTrue(transport.advance())
        self.assertEqual(self.played_ids(), ["c"])
        self.notify.notify.assert_called_once()

    def test_three_failures_in_a_row_stop_advance(self):
        self.playing(self.item(A))
        self.src.resolve.side_effect = OSError("nope")
        for i in range(4):
            playqueue.add(self.item({"source": "fake", "id": f"x{i}"}))
        self.assertFalse(transport.advance())
        self.assertEqual(len(self.state()["entries"]), 1)  # the fourth was never tried
        self.assertEqual(transport._fails, 0)  # reset so the next press tries again


class TestNextPrev(Base):
    def test_radio_next_and_prev_cycle_stations(self):
        self.player.current.return_value = {"type": "station", "item": KEXP}
        self.library.next_station.return_value = WXPN
        transport.next_cmd()
        self.library.next_station.assert_called_once_with("kexp")
        self.player.play_station.assert_called_with(WXPN)
        self.library.prev_station.return_value = KEXP
        transport.prev_cmd()
        self.library.prev_station.assert_called_once_with("kexp")

    def test_radio_next_when_idle_starts_the_first_station(self):
        self.library.list_stations.return_value = [KEXP, WXPN]
        transport.next_cmd()
        self.player.play_station.assert_called_once_with(KEXP)
        self.player.play_station.reset_mock()
        transport.prev_cmd()
        self.player.play_station.assert_called_once_with(WXPN)

    def test_media_next_advances(self):
        self.playing(self.item(A))
        playqueue.add(self.item(B))
        transport.next_cmd()
        self.assertEqual(self.played_ids(), ["b"])

    def test_media_prev_restarts_when_more_than_three_seconds_in(self):
        self.playing(self.item(A))
        playqueue.push_history(self.item(B))
        self.player.current.return_value = {"type": "item", "item": A}
        self.player.item_progress.return_value = (3.5, 100.0)
        transport.prev_cmd()
        self.player.seek.assert_called_once_with(0.0)
        self.player.play_target.assert_not_called()

    def test_media_prev_steps_back_and_requeues_the_current(self):
        a, b = self.item(A), self.item(B)
        self.playing(a)
        playqueue.push_history(b)
        self.player.current.return_value = {"type": "item", "item": A}
        self.player.item_progress.return_value = (2.0, 100.0)
        transport.prev_cmd()
        self.assertEqual(self.played_ids(), ["b"])
        s = self.state()
        self.assertEqual(s["now"]["uid"], b["uid"])
        self.assertEqual([e["uid"] for e in s["entries"]], [a["uid"]])
        self.assertEqual(s["history"], [])

    def test_media_prev_failure_restores_history_and_keeps_now(self):
        a, b = self.item(A), self.item(B)
        self.playing(a)
        playqueue.push_history(b)
        self.player.current.return_value = {"type": "item", "item": A}
        self.player.item_progress.return_value = (2.0, 100.0)
        self.src.resolve.side_effect = OSError("gone")
        transport.prev_cmd()
        s = self.state()
        self.assertEqual([h["uid"] for h in s["history"]], [b["uid"]])
        self.assertEqual(s["entries"], [])
        self.assertEqual(s["now"]["uid"], a["uid"])

    def test_media_prev_with_no_history_restarts(self):
        self.playing(self.item(A))
        self.player.current.return_value = {"type": "item", "item": A}
        self.player.item_progress.return_value = (1.0, 100.0)
        transport.prev_cmd()
        self.player.seek.assert_called_once_with(0.0)

    def test_media_prev_when_idle_does_nothing(self):
        self.playing(None)
        transport.prev_cmd()
        self.player.seek.assert_not_called()


class TestSetMode(Base):
    def test_to_media_resumes_at_the_saved_point(self):
        a = self.item(A)
        playqueue.set_resume(a, 100.0, 300.0)
        playqueue.add(a)  # as after a station entry: the head is also the resume entry
        transport.set_mode("media")
        self.player.play_target.assert_called_once_with("target:a", A, start=100.0)
        s = self.state()
        self.assertEqual((s["mode"], s["entries"], s["resume"]), ("media", [], None))

    def test_resume_near_the_end_starts_over(self):
        playqueue.set_resume(self.item(A), 295.0, 300.0)
        transport.set_mode("media")
        self.player.play_target.assert_called_once_with("target:a", A, start=None)

    def test_resume_before_the_minimum_starts_over(self):
        playqueue.set_resume(self.item(A), 5.0, 300.0)
        transport.set_mode("media")
        self.player.play_target.assert_called_once_with("target:a", A, start=None)

    def test_to_media_without_resume_plays_the_head(self):
        playqueue.add(self.item(B))
        transport.set_mode("media")
        self.assertEqual(self.played_ids(), ["b"])

    def test_to_media_with_nothing_only_flips_the_mode(self):
        transport.set_mode("media")
        self.player.play_target.assert_not_called()
        self.assertEqual(self.state()["mode"], "media")

    def test_to_radio_parks_then_starts_the_last_station(self):
        self.playing(self.item(A))
        self.player.current.return_value = {"type": "item", "item": A}
        self.player.item_progress.return_value = (60.0, 200.0)
        self.library.last_played_station.return_value = KEXP

        def started(st):
            self.player.current.return_value = {"type": "station"}
        self.player.play_station.side_effect = started
        transport.set_mode("radio")
        self.player.play_station.assert_called_once_with(KEXP)
        s = self.state()
        self.assertEqual((s["mode"], s["resume"]["pos"]), ("radio", 60.0))

    def test_to_radio_without_a_last_station_only_flips(self):
        self.playing(self.item(A))
        self.library.last_played_station.return_value = None
        transport.set_mode("radio")
        self.player.play_station.assert_not_called()
        self.assertEqual(self.state()["mode"], "radio")

    def test_same_mode_is_a_no_op(self):
        transport.set_mode("radio")
        self.player.play_station.assert_not_called()

    def test_unknown_mode_raises(self):
        with self.assertRaises(ValueError):
            transport.set_mode("shuffle")


class TestPlayEntry(Base):
    def test_item_entry_plays_and_drops_the_context(self):
        playqueue.set_context([A, B], "a")
        self.assertTrue(transport.play_entry(self.item(C)))
        self.assertEqual(self.played_ids(), ["c"])
        self.assertIsNone(self.state()["context"])

    def test_failed_entry_returns_false(self):
        self.src.resolve.side_effect = OSError("nope")
        self.assertFalse(transport.play_entry(self.item(C)))


class TestTick(Base):
    def setUp(self):
        super().setUp()
        self.player.current.return_value = {"type": "item", "item": A}

    def test_not_ended_does_nothing(self):
        self.player.playback_ended.return_value = False
        playqueue.add(self.item(B))
        transport.tick()
        self.player.play_target.assert_not_called()

    def test_radio_and_idle_do_nothing(self):
        self.player.playback_ended.return_value = True
        for cur in (None, {"type": "station", "item": KEXP}):
            self.player.current.return_value = cur
            transport.tick()
        self.player.play_target.assert_not_called()
        self.player.stop.assert_not_called()

    def test_ended_advances(self):
        self.player.playback_ended.return_value = True
        playqueue.add(self.item(B))
        transport.tick()
        self.assertEqual(self.played_ids(), ["b"])

    def test_ended_with_nothing_left_stops_and_clears(self):
        self.player.playback_ended.return_value = True
        self.playing(self.item(A))
        playqueue.set_resume(self.item(A), 299.0, 300.0)
        transport.tick()
        self.player.stop.assert_called_once_with(notify_user=False)
        s = self.state()
        self.assertEqual((s["now"], s["resume"]), (None, None))

    def test_ended_handoff_is_left_to_autoplay(self):
        self.player.current.return_value = {"type": "item", "item": A, "handoff": "spotify"}
        self.player.playback_ended.return_value = True
        transport.tick()
        self.player.stop.assert_not_called()


class TestStop(Base):
    def test_parks_stops_and_clears_now(self):
        self.playing(self.item(A))
        self.player.current.return_value = {"type": "item", "item": A}
        self.player.item_progress.return_value = (80.0, 200.0)
        transport.stop()
        self.player.stop.assert_called_once_with()
        s = self.state()
        self.assertEqual((s["now"], s["resume"]["pos"]), (None, 80.0))


class TestCanGo(Base):
    def test_radio_needs_stations(self):
        self.library.list_stations.return_value = []
        self.assertFalse(transport.can_go_next())
        self.assertFalse(transport.can_go_previous())
        self.library.list_stations.return_value = [KEXP]
        self.assertTrue(transport.can_go_next())
        self.assertTrue(transport.can_go_previous())

    def test_media_next_needs_entries_or_context(self):
        playqueue.set_mode("media")
        self.assertFalse(transport.can_go_next())
        playqueue.add(self.item(B))
        self.assertTrue(transport.can_go_next())
        playqueue.clear()
        playqueue.set_context([A, B], "a")
        self.assertTrue(transport.can_go_next())

    def test_media_previous_needs_history_or_something_playing(self):
        playqueue.set_mode("media")
        self.assertFalse(transport.can_go_previous())
        playqueue.push_history(self.item(B))
        self.assertTrue(transport.can_go_previous())


if __name__ == "__main__":
    unittest.main()
