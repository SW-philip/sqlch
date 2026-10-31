import unittest
from unittest import mock

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from sqlch.core import playqueue
from sqlch_gui.ui import dnd
from sqlch_gui.ui.playlist_pane import PlaylistPane

A = {"source": "fake", "id": "a", "title": "Song A", "artist": "Band", "kind": "track"}
B = {"source": "fake", "id": "b", "title": "Song B", "kind": "track"}
KEXP = {"id": "kexp", "name": "KEXP", "url": "http://kexp.example/s"}


def sync(work, done):
    try:
        result, err = work(), None
    except Exception as e:
        result, err = None, str(e)
    done(result, err)


def state(**kw):
    s = {"mode": "media", "entries": [], "now": None, "context": None,
         "history": [], "resume": None}
    s.update(kw)
    return s


def entry(kind, payload):
    return playqueue.make_entry(kind, payload)


def labels(widget, acc=None):
    acc = [] if acc is None else acc
    child = widget.get_first_child()
    while child:
        if isinstance(child, Gtk.Label):
            acc.append(child.get_text())
        labels(child, acc)
        child = child.get_next_sibling()
    return acc


def make(st, sent=None):
    box = {"state": st}
    pane = PlaylistPane(None, read=lambda: box["state"],
                        send=(lambda m: (sent.append(m), {"ok": True})[1]) if sent is not None
                        else (lambda m: {"ok": True}),
                        run_async=sync, watch=False)
    return pane, box


class TestRows(unittest.TestCase):
    def test_now_row_then_entries(self):
        now, a, k = entry("item", A), entry("item", A), entry("station", KEXP)
        pane, _ = make(state(now=now, entries=[a, k]))
        texts = labels(pane.list)
        self.assertEqual(texts[0], "▶")  # the now marker
        self.assertIn("KEXP", texts)
        self.assertIn("radio", texts)
        self.assertEqual(len(pane._entries), 2)
        self.assertEqual(len(pane._row_widgets), 2)

    def test_empty_queue_has_no_rows(self):
        pane, _ = make(state())
        self.assertEqual(pane._entries, [])
        self.assertIsNone(pane.list.get_row_at_index(0))

    def test_refresh_is_a_no_op_when_nothing_changed(self):
        pane, box = make(state(entries=[entry("item", A)]))
        before = pane._row_widgets[0]
        self.assertFalse(pane.refresh())
        self.assertIs(pane._row_widgets[0], before)
        box["state"] = state(entries=[entry("item", A), entry("item", B)])
        pane.refresh()
        self.assertEqual(len(pane._entries), 2)

    def test_refresh_ignores_a_moving_resume_position_in_media_mode(self):
        a = entry("item", A)
        pane, box = make(state(mode="media", resume={"entry": a, "pos": 10.0, "dur": 90.0}))
        before = pane._sig
        box["state"] = state(mode="media", resume={"entry": a, "pos": 15.0, "dur": 90.0})
        pane.refresh()
        self.assertEqual(pane._sig, before)


class TestModeToggle(unittest.TestCase):
    def test_follows_the_state(self):
        pane, box = make(state(mode="media"))
        self.assertTrue(pane.btn_media.get_active())
        box["state"] = state(mode="radio")
        pane.refresh()
        self.assertTrue(pane.btn_radio.get_active())

    def test_click_sends_set_mode(self):
        sent = []
        pane, _ = make(state(mode="media"), sent)
        pane.btn_radio.emit("clicked")
        self.assertEqual(sent, [{"cmd": "set_mode", "mode": "radio"}])

    def test_syncing_the_toggle_from_state_sends_nothing(self):
        sent = []
        pane, box = make(state(mode="media"), sent)
        box["state"] = state(mode="radio")
        pane.refresh()
        self.assertEqual(sent, [])


class TestResumeLine(unittest.TestCase):
    def test_shown_only_while_parked(self):
        a = entry("item", A)
        r = {"entry": a, "pos": 412.0, "dur": 900.0}
        pane, box = make(state(mode="radio", resume=r))
        self.assertTrue(pane.status.get_visible())
        self.assertEqual(pane.status.get_text(), "resume: Song A, 6:52")
        box["state"] = state(mode="media", resume=r)
        pane.refresh()
        self.assertFalse(pane.status.get_visible())


class TestActions(unittest.TestCase):
    def test_remove_button_sends_queue_remove(self):
        a = entry("item", A)
        sent = []
        pane, _ = make(state(entries=[a]), sent)
        pane._remove_buttons[a["uid"]].emit("clicked")
        self.assertEqual(sent, [{"cmd": "queue_remove", "uid": a["uid"]}])

    def test_clear_button(self):
        sent = []
        pane, _ = make(state(entries=[entry("item", A)]), sent)
        pane.btn_clear.emit("clicked")
        self.assertEqual(sent, [{"cmd": "queue_clear"}])

    def test_play_row(self):
        a = entry("item", A)
        sent = []
        pane, _ = make(state(entries=[a]), sent)
        pane._play(a)
        self.assertEqual(sent, [{"cmd": "queue_play", "uid": a["uid"]}])

    def test_error_shows_in_the_status_line(self):
        pane = PlaylistPane(None, read=lambda: state(), run_async=sync, watch=False,
                            send=lambda m: {"ok": False, "error": "boom"})
        pane.btn_clear.emit("clicked")
        self.assertIn("boom", pane.status.get_text())
        self.assertTrue(pane.status.get_visible())


class TestDrop(unittest.TestCase):
    def setUp(self):
        self.a, self.b, self.c = entry("item", A), entry("item", B), entry("station", KEXP)
        self.sent = []
        self.pane, _ = make(state(entries=[self.a, self.b, self.c]), self.sent)
        self.pane._midpoints = lambda: [10.0, 30.0, 50.0]

    def test_a_new_station_inserts_at_the_gap(self):
        ok = self.pane._on_drop(None, dnd.encode(
            {"kind": "station", "payload": dnd.station_payload(KEXP)}), 5, 40)
        self.assertTrue(ok)
        self.assertEqual(self.sent, [{"cmd": "queue_add", "kind": "station",
                                      "payload": dnd.station_payload(KEXP), "at": 2}])

    def test_reorder_down(self):
        self.pane._on_drop(None, dnd.encode({"move": self.a["uid"]}), 5, 999)
        self.assertEqual(self.sent, [{"cmd": "queue_move", "uid": self.a["uid"], "to": 2}])

    def test_reorder_up(self):
        self.pane._on_drop(None, dnd.encode({"move": self.c["uid"]}), 5, 0)
        self.assertEqual(self.sent, [{"cmd": "queue_move", "uid": self.c["uid"], "to": 0}])

    def test_strangers_and_unknown_moves_are_refused(self):
        self.assertFalse(self.pane._on_drop(None, "just text", 5, 5))
        self.assertFalse(self.pane._on_drop(None, dnd.encode({"move": "nope"}), 5, 5))
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
