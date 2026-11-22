import unittest
from unittest import mock

from sqlch.core import watcher


class FakeStore:
    def __init__(self, rows):
        self.rows = rows

    def list_follows(self):
        return [dict(r) for r in self.rows]

    def record_seen(self, cid, vid, checked):
        for r in self.rows:
            if r["channel_id"] == cid:
                r["last_video_id"] = vid
                r["last_checked"] = checked


def row(cid="UC1", name="Chan", last=None):
    return {"channel_id": cid, "name": name, "last_video_id": last, "last_checked": None}


def vids(*ids):
    return [{"id": i, "title": f"T {i}"} for i in ids]


def make(rows, feeds):
    store = FakeStore(rows)

    def fetch(cid):
        feed = feeds[cid]
        if isinstance(feed, Exception):
            raise feed
        return feed

    return watcher.Watcher(fetch, store=store, clock=lambda: 42.0), store


class Stop(Exception):
    pass


class TestRun(unittest.TestCase):
    def test_bad_interval_falls_back_to_default(self):
        w, _ = make([], {})
        polled = []
        w.poll_once = lambda: polled.append(1)

        def bad():
            raise AttributeError("sources is a list")

        with mock.patch.object(watcher.time, "sleep", side_effect=Stop) as sleep:
            with self.assertRaises(Stop):
                w.run(bad)
        self.assertEqual(polled, [1])
        sleep.assert_called_once_with(watcher.DEFAULT_INTERVAL)


class TestPoll(unittest.TestCase):
    def test_first_poll_records_and_stays_quiet(self):
        w, store = make([row()], {"UC1": vids("b", "a")})
        w.poll_once()
        self.assertEqual(w.drain(), [])
        self.assertEqual(store.rows[0]["last_video_id"], "b")
        self.assertEqual(store.rows[0]["last_checked"], 42.0)

    def test_no_change_is_quiet(self):
        w, store = make([row(last="b")], {"UC1": vids("b", "a")})
        w.poll_once()
        self.assertEqual(w.drain(), [])

    def test_one_new_video(self):
        w, store = make([row(last="b")], {"UC1": vids("c", "b", "a")})
        w.poll_once()
        self.assertEqual(w.drain(), ["Chan: T c"])
        self.assertEqual(store.rows[0]["last_video_id"], "c")
        w.poll_once()
        self.assertEqual(w.drain(), [])

    def test_up_to_three_are_listed_oldest_first(self):
        w, _ = make([row(last="a")], {"UC1": vids("d", "c", "b", "a")})
        w.poll_once()
        self.assertEqual(w.drain(), ["Chan: T b", "Chan: T c", "Chan: T d"])

    def test_more_than_three_become_a_summary(self):
        w, _ = make([row(last="a")], {"UC1": vids("e", "d", "c", "b", "a")})
        w.poll_once()
        self.assertEqual(w.drain(), ["Chan: 4 new videos"])

    def test_last_seen_rolled_off_feed_counts_whole_feed_as_new(self):
        w, _ = make([row(last="gone")], {"UC1": vids("b", "a")})
        w.poll_once()
        self.assertEqual(w.drain(), ["Chan: T a", "Chan: T b"])

    def test_empty_feed_changes_nothing(self):
        w, store = make([row(last="a")], {"UC1": []})
        w.poll_once()
        self.assertEqual(w.drain(), [])
        self.assertEqual(store.rows[0]["last_video_id"], "a")


class TestFailures(unittest.TestCase):
    def test_gives_up_once_after_ten_failures(self):
        w, _ = make([row()], {"UC1": OSError("down")})
        for _ in range(9):
            w.poll_once()
        self.assertEqual(w.drain(), [])
        w.poll_once()
        self.assertEqual(w.drain(), ["Can't reach Chan"])
        w.poll_once()
        self.assertEqual(w.drain(), [])

    def test_success_resets_the_counter(self):
        feeds = {"UC1": OSError("down")}
        w, _ = make([row()], feeds)
        for _ in range(9):
            w.poll_once()
        feeds["UC1"] = vids("a")
        w.poll_once()
        feeds["UC1"] = OSError("down")
        for _ in range(9):
            w.poll_once()
        self.assertEqual(w.drain(), [])
        w.poll_once()
        self.assertEqual(w.drain(), ["Can't reach Chan"])

    def test_one_failing_channel_does_not_stop_the_others(self):
        w, store = make([row("UC1", "Bad"), row("UC2", "Good", last="a")],
                        {"UC1": OSError("x"), "UC2": vids("b", "a")})
        w.poll_once()
        self.assertEqual(w.drain(), ["Good: T b"])


class TestQueue(unittest.TestCase):
    def test_drain_clears(self):
        w, _ = make([row(last="a")], {"UC1": vids("b", "a")})
        w.poll_once()
        self.assertEqual(len(w.drain()), 1)
        self.assertEqual(w.drain(), [])

    def test_keeps_only_newest_twenty(self):
        w, _ = make([], {})
        for i in range(25):
            w._push(f"n{i}")
        got = w.drain()
        self.assertEqual(len(got), watcher.MAX_NOTICES)
        self.assertEqual(got[0], "n5")
        self.assertEqual(got[-1], "n24")

    def test_module_drain_before_start_is_empty(self):
        self.assertEqual(watcher.drain(), [])


if __name__ == "__main__":
    unittest.main()
