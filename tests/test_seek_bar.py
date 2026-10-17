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


if __name__ == "__main__":
    unittest.main()
