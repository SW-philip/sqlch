import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlch.core import playqueue

TRACK = {"source": "local", "id": "a", "title": "Song A", "artist": "Band", "kind": "track"}
TRACK_B = {"source": "local", "id": "b", "title": "Song B", "kind": "track"}
STATION = {"id": "kexp", "name": "KEXP", "url": "http://kexp.example/stream", "extra": "dropped"}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        p = mock.patch.object(playqueue, "data_dir", lambda: self.dir)
        p.start()
        self.addCleanup(p.stop)

    def item(self, it=TRACK):
        return playqueue.make_entry("item", it)

    def station(self):
        return playqueue.make_entry("station", STATION)

    def uids(self):
        return [e["uid"] for e in playqueue.read()["entries"]]


class TestEntries(Base):
    def test_item_entry_keeps_the_whole_item(self):
        e = self.item()
        self.assertEqual((e["kind"], e["item"]), ("item", TRACK))
        self.assertTrue(e["uid"])

    def test_station_entry_keeps_only_id_name_url(self):
        e = self.station()
        self.assertEqual(e["station"], {"id": "kexp", "name": "KEXP",
                                        "url": "http://kexp.example/stream"})

    def test_uids_are_unique(self):
        self.assertNotEqual(self.item()["uid"], self.item()["uid"])

    def test_bad_entries_raise(self):
        for kind, payload in (("item", {}), ("item", {"source": "x"}),
                              ("station", {"name": "no url"}), ("nope", TRACK),
                              ("item", None)):
            with self.assertRaises(ValueError):
                playqueue.make_entry(kind, payload)

    def test_labels(self):
        self.assertEqual(playqueue.entry_title(self.item()), "Song A")
        self.assertEqual(playqueue.entry_label(self.item()), "Song A — Band")
        self.assertEqual(playqueue.entry_label(self.item(TRACK_B)), "Song B")
        self.assertEqual(playqueue.entry_title(self.station()), "KEXP")
        self.assertEqual(playqueue.entry_subtitle(self.station()), "radio")
        self.assertEqual(playqueue.entry_subtitle(self.item()), "Band")


class TestState(Base):
    def test_empty_default(self):
        s = playqueue.read()
        self.assertEqual(s, {"mode": "radio", "entries": [], "now": None,
                             "context": None, "history": [], "resume": None})

    def test_add_orders_and_returns_index(self):
        a, b, c = self.item(), self.item(TRACK_B), self.station()
        self.assertEqual(playqueue.add(a), 0)
        self.assertEqual(playqueue.add(b), 1)
        self.assertEqual(playqueue.add(c, at=1), 1)
        self.assertEqual(self.uids(), [a["uid"], c["uid"], b["uid"]])

    def test_add_play_next_goes_first(self):
        a, b = self.item(), self.item(TRACK_B)
        playqueue.add(a)
        playqueue.add(b, play_next=True)
        self.assertEqual(self.uids(), [b["uid"], a["uid"]])

    def test_add_clamps_at(self):
        a, b = self.item(), self.item(TRACK_B)
        playqueue.add(a, at=99)
        playqueue.add(b, at=-5)
        self.assertEqual(self.uids(), [b["uid"], a["uid"]])

    def test_remove(self):
        a = self.item()
        playqueue.add(a)
        self.assertTrue(playqueue.remove(a["uid"]))
        self.assertFalse(playqueue.remove(a["uid"]))
        self.assertEqual(self.uids(), [])

    def test_move_counts_the_target_after_removal(self):
        a, b, c = self.item(), self.item(TRACK_B), self.station()
        for e in (a, b, c):
            playqueue.add(e)
        self.assertTrue(playqueue.move(a["uid"], 2))
        self.assertEqual(self.uids(), [b["uid"], c["uid"], a["uid"]])
        self.assertTrue(playqueue.move(a["uid"], 0))
        self.assertEqual(self.uids(), [a["uid"], b["uid"], c["uid"]])
        self.assertFalse(playqueue.move("nope", 0))

    def test_take_drops_everything_before(self):
        a, b, c = self.item(), self.item(TRACK_B), self.station()
        for e in (a, b, c):
            playqueue.add(e)
        self.assertEqual(playqueue.take(b["uid"])["uid"], b["uid"])
        self.assertEqual(self.uids(), [c["uid"]])
        self.assertIsNone(playqueue.take("nope"))
        self.assertEqual(self.uids(), [c["uid"]])

    def test_pop_head_and_clear(self):
        a, b = self.item(), self.item(TRACK_B)
        playqueue.add(a)
        playqueue.add(b)
        self.assertEqual(playqueue.pop_head()["uid"], a["uid"])
        playqueue.clear()
        self.assertIsNone(playqueue.pop_head())

    def test_clear_keeps_resume(self):
        a = self.item()
        playqueue.add(self.item(TRACK_B))
        playqueue.set_resume(a, 90.0, 300.0)
        playqueue.clear()
        self.assertEqual(playqueue.read()["resume"]["entry"]["uid"], a["uid"])

    def test_mode_now_resume(self):
        a = self.item()
        playqueue.set_mode("media")
        playqueue.set_now(a)
        playqueue.set_resume(a, 12.5, None)
        s = playqueue.read()
        self.assertEqual((s["mode"], s["now"]["uid"]), ("media", a["uid"]))
        self.assertEqual((s["resume"]["pos"], s["resume"]["dur"]), (12.5, None))
        playqueue.clear_resume()
        playqueue.set_now(None)
        s = playqueue.read()
        self.assertEqual((s["now"], s["resume"]), (None, None))

    def test_resume_head_flag_round_trips(self):
        a = self.item()
        playqueue.set_resume(a, 0.0, None, head=True)
        self.assertIs(playqueue.read()["resume"]["head"], True)
        playqueue.set_resume(a, 5.0, None)
        self.assertNotIn("head", playqueue.read()["resume"])

    def test_unknown_mode_raises(self):
        with self.assertRaises(ValueError):
            playqueue.set_mode("shuffle")

    def test_history_is_capped_and_pops_newest_first(self):
        entries = [self.item({**TRACK, "id": str(i)}) for i in range(playqueue.HISTORY_MAX + 5)]
        for e in entries:
            playqueue.push_history(e)
        self.assertEqual(len(playqueue.read()["history"]), playqueue.HISTORY_MAX)
        self.assertEqual(playqueue.pop_history()["uid"], entries[-1]["uid"])
        self.assertEqual(len(playqueue.read()["history"]), playqueue.HISTORY_MAX - 1)

    def test_pop_history_empty(self):
        self.assertIsNone(playqueue.pop_history())


class TestContext(Base):
    ITEMS = [{**TRACK, "id": str(i)} for i in range(3)]

    def test_next_in_context_walks_the_list(self):
        playqueue.set_context(self.ITEMS, "0")
        self.assertEqual(playqueue.next_in_context()["id"], "1")
        self.assertEqual(playqueue.next_in_context()["id"], "2")
        self.assertIsNone(playqueue.next_in_context())

    def test_context_starts_at_the_playing_item(self):
        playqueue.set_context(self.ITEMS, "1")
        self.assertEqual(playqueue.next_in_context()["id"], "2")

    def test_unknown_current_id_means_no_context(self):
        playqueue.set_context(self.ITEMS, "zzz")
        self.assertIsNone(playqueue.read()["context"])

    def test_none_clears_and_folders_are_dropped(self):
        folder = {"source": "local", "id": "d", "kind": "folder"}
        playqueue.set_context([folder, *self.ITEMS], "0")
        self.assertEqual([i["id"] for i in playqueue.read()["context"]["items"]],
                         ["0", "1", "2"])
        playqueue.set_context(None, None)
        self.assertIsNone(playqueue.read()["context"])


class TestPersistence(Base):
    def test_round_trip_and_no_temp_files(self):
        a = self.item()
        playqueue.add(a)
        playqueue.set_mode("media")
        self.assertEqual(playqueue.read()["entries"][0]["item"], TRACK)
        self.assertEqual([p.name for p in self.dir.iterdir()], ["queue.json"])

    def test_corrupt_file_is_quarantined_by_a_write(self):
        (self.dir / "queue.json").write_text("{not json")
        self.assertEqual(playqueue.read()["entries"], [])  # reading never renames
        self.assertTrue((self.dir / "queue.json").exists())
        playqueue.add(self.item())
        bad = [p for p in self.dir.iterdir() if p.name.endswith(".bad")]
        self.assertEqual(len(bad), 1)
        self.assertEqual(len(playqueue.read()["entries"]), 1)

    def test_non_dict_payload_counts_as_corrupt(self):
        (self.dir / "queue.json").write_text("[1, 2]")
        playqueue.set_mode("media")
        self.assertEqual(len([p for p in self.dir.iterdir() if p.name.endswith(".bad")]), 1)

    def test_malformed_entries_are_dropped_on_read(self):
        good = self.item()
        (self.dir / "queue.json").write_text(json.dumps({
            "mode": "media",
            "entries": [good, {"uid": "x", "kind": "item"}, "junk", {"kind": "station"}],
        }))
        s = playqueue.read()
        self.assertEqual([e["uid"] for e in s["entries"]], [good["uid"]])
        self.assertEqual((s["now"], s["history"], s["resume"]), (None, [], None))

    def test_unknown_mode_falls_back_to_radio(self):
        (self.dir / "queue.json").write_text(json.dumps({"mode": "weird"}))
        self.assertEqual(playqueue.read()["mode"], "radio")


if __name__ == "__main__":
    unittest.main()
