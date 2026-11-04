import unittest

import gi
gi.require_version("Gtk", "4.0")

from sqlch_gui.ui.toast import SHOW_MS, Toast


class Clock:
    """Stands in for GLib.timeout_add: collects callbacks, fires on demand."""

    def __init__(self):
        self.pending = []

    def __call__(self, ms, fn):
        self.pending.append((ms, fn))

    def fire(self):
        _ms, fn = self.pending.pop(0)
        fn()


class TestToast(unittest.TestCase):
    def test_hidden_until_pushed(self):
        self.assertFalse(Toast(schedule=Clock()).get_visible())

    def test_push_shows_text_then_hides(self):
        clock = Clock()
        t = Toast(schedule=clock)
        t.push("Chan: Video")
        self.assertTrue(t.get_visible())
        self.assertEqual(t.get_text(), "Chan: Video")
        self.assertEqual(clock.pending[0][0], SHOW_MS)
        clock.fire()
        self.assertFalse(t.get_visible())

    def test_second_push_waits_for_the_first(self):
        clock = Clock()
        t = Toast(schedule=clock)
        t.push("one")
        t.push("two")
        self.assertEqual(t.get_text(), "one")
        self.assertEqual(len(clock.pending), 1)
        clock.fire()
        self.assertEqual(t.get_text(), "two")
        self.assertTrue(t.get_visible())
        clock.fire()
        self.assertFalse(t.get_visible())

    def test_push_after_idle_shows_again(self):
        clock = Clock()
        t = Toast(schedule=clock)
        t.push("one")
        clock.fire()
        t.push("two")
        self.assertEqual(t.get_text(), "two")
        self.assertTrue(t.get_visible())

    def test_does_not_block_clicks(self):
        self.assertFalse(Toast(schedule=Clock()).get_can_target())


if __name__ == "__main__":
    unittest.main()
