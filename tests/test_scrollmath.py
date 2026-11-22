import unittest

from sqlch_gui.ui.scrollmath import scroll_offset


class TestScrollOffset(unittest.TestCase):
    def test_no_overflow_is_zero(self):
        self.assertEqual(scroll_offset(5.0, 0), 0.0)
        self.assertEqual(scroll_offset(5.0, -3), 0.0)

    def test_pauses_at_start(self):
        self.assertEqual(scroll_offset(0.0, 100, speed=50, pause=1.0), 0.0)
        self.assertEqual(scroll_offset(0.9, 100, speed=50, pause=1.0), 0.0)

    def test_travels_at_speed_then_pauses_at_end(self):
        self.assertAlmostEqual(scroll_offset(2.0, 100, speed=50, pause=1.0), 50.0)
        self.assertEqual(scroll_offset(3.0, 100, speed=50, pause=1.0), 100.0)
        self.assertEqual(scroll_offset(3.9, 100, speed=50, pause=1.0), 100.0)

    def test_returns_and_loops(self):
        self.assertAlmostEqual(scroll_offset(5.0, 100, speed=50, pause=1.0), 50.0)
        self.assertEqual(scroll_offset(6.0, 100, speed=50, pause=1.0), 0.0)
        self.assertAlmostEqual(scroll_offset(8.0, 100, speed=50, pause=1.0), 50.0)

    def test_always_within_bounds(self):
        for i in range(0, 4000):
            v = scroll_offset(i / 100, 73.0)
            self.assertTrue(0.0 <= v <= 73.0)
