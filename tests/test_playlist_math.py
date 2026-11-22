import unittest

from sqlch_gui.ui.playlist_math import insert_index, move_target


class TestInsertIndex(unittest.TestCase):
    MIDS = [10.0, 30.0, 50.0]

    def test_above_between_below(self):
        self.assertEqual(insert_index(self.MIDS, 0), 0)
        self.assertEqual(insert_index(self.MIDS, 10), 1)  # on a midpoint: after that row
        self.assertEqual(insert_index(self.MIDS, 29.9), 1)
        self.assertEqual(insert_index(self.MIDS, 40), 2)
        self.assertEqual(insert_index(self.MIDS, 999), 3)

    def test_empty_list(self):
        self.assertEqual(insert_index([], 12), 0)


class TestMoveTarget(unittest.TestCase):
    def test_moving_down_counts_after_removal(self):
        self.assertEqual(move_target(0, 3), 2)   # A to the very end of [A, B, C]
        self.assertEqual(move_target(0, 2), 1)

    def test_moving_up(self):
        self.assertEqual(move_target(2, 0), 0)
        self.assertEqual(move_target(2, 1), 1)

    def test_dropping_next_to_itself_is_a_no_op(self):
        self.assertEqual(move_target(1, 1), 1)
        self.assertEqual(move_target(1, 2), 1)


if __name__ == "__main__":
    unittest.main()
