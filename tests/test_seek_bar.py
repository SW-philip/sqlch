import unittest

import gi
gi.require_version("Gtk", "4.0")

from sqlch_gui.ui.controls import SeekBar


class TestSeekBar(unittest.TestCase):
    def test_hidden_until_positive_duration(self):
        bar = SeekBar()
        self.assertFalse(bar.get_visible())
        for args in ((None, None), (5, 0), (None, 90)):
            bar.set_state(*args)
            self.assertFalse(bar.get_visible(), args)

    def test_set_state_shows_and_formats(self):
        bar = SeekBar()
        bar.set_state(10, 100)
        self.assertTrue(bar.get_visible())
        self.assertEqual(bar._scale.get_value(), 10)
        self.assertEqual(bar._scale.get_adjustment().get_upper(), 100)
        self.assertEqual(bar._time.get_text(), "0:10 / 1:40")

    def test_user_move_emits_seek(self):
        bar = SeekBar()
        got = []
        bar.connect("seek-requested", lambda _b, pos: got.append(pos))
        self.assertFalse(bar._on_change_value(None, None, 42.0))
        self.assertEqual(got, [42.0])

    def test_poll_does_not_fight_user(self):
        import time
        bar = SeekBar()
        bar.set_state(10, 100)
        bar._on_change_value(None, None, 42.0)
        bar._scale.set_value(42.0)
        bar.set_state(60, 100)
        self.assertEqual(bar._scale.get_value(), 42.0)
        self.assertGreater(bar._hold_until, time.monotonic())
        bar._hold_until = 0
        bar.set_state(60, 100)
        self.assertEqual(bar._scale.get_value(), 60)

    def test_stop_hides_even_during_hold(self):
        bar = SeekBar()
        bar.set_state(10, 100)
        bar._on_change_value(None, None, 42.0)
        bar.set_state(None, None)
        self.assertFalse(bar.get_visible())


    def test_skip_buttons_only_with_a_queue(self):
        bar = SeekBar()
        bar.set_state(10, 100)
        self.assertFalse(bar._next.get_visible())
        bar.set_state(10, 100, True)
        self.assertTrue(bar._next.get_visible())

    def test_skip_without_duration_shows_only_skip(self):
        bar = SeekBar()
        bar.set_state(None, None, True)
        self.assertTrue(bar.get_visible())
        self.assertTrue(bar._prev.get_visible())
        self.assertFalse(bar._scale.get_visible())
        self.assertFalse(bar._fwd.get_visible())

    def test_buttons_emit(self):
        bar = SeekBar()
        got = []
        bar.connect("seek-relative", lambda _b, d: got.append(d))
        bar.connect("skip", lambda _b, f: got.append(f))
        for b in (bar._back, bar._fwd, bar._prev, bar._next):
            b.emit("clicked")
        self.assertEqual(got, [-15.0, 30.0, False, True])


if __name__ == "__main__":
    unittest.main()
