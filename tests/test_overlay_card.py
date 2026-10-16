import unittest

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from sqlch_gui.ui.dock import Rect
from sqlch_gui.ui.overlay_card import OverlayCard


class TestStrayDragEvents(unittest.TestCase):
    def setUp(self):
        self.calls = {"drag": 0, "drop": 0, "start": 0}
        card, handle = Gtk.Box(), Gtk.Box()
        card.append(handle)

        def on_drag(r):
            self.calls["drag"] += 1
            return None

        def on_drop(_r):
            self.calls["drop"] += 1

        def on_start():
            self.calls["start"] += 1

        self.oc = OverlayCard(Gtk.Window(), card, handle, on_drag=on_drag,
                              on_drop=on_drop, on_drag_start=on_start)
        self.start = Rect(100, 200, 320, 400)
        self.oc.place(self.start)

    def test_update_and_end_without_accepted_begin_do_nothing(self):
        self.oc._drag_update(None, 5, 5)
        self.oc._drag_end(None, 5, 5)
        self.assertEqual(self.oc.rect, self.start)
        self.assertEqual(self.calls, {"drag": 0, "drop": 0, "start": 0})

    def test_accepted_drag_moves_and_drops_once_then_strays_are_ignored(self):
        self.oc._accept_drag()
        self.oc._drag_update(None, 10, 20)
        self.oc._drag_end(None, 30, 40)
        moved = self.start.moved(30, 40)
        self.assertEqual(self.oc.rect, moved)
        self.assertEqual(self.calls, {"drag": 2, "drop": 1, "start": 1})
        self.oc._drag_update(None, 5, 5)
        self.oc._drag_end(None, 5, 5)
        self.assertEqual(self.oc.rect, moved)
        self.assertEqual(self.calls, {"drag": 2, "drop": 1, "start": 1})

    def test_cancel_ends_the_drag_in_place_without_drop(self):
        self.oc._accept_drag()
        self.oc._drag_update(None, 10, 0)
        self.oc._drag_cancel(None, None)
        self.oc._drag_end(None, 50, 50)
        self.assertEqual(self.oc.rect, self.start.moved(10, 0))
        self.assertEqual(self.calls["drop"], 0)


if __name__ == "__main__":
    unittest.main()
