# tests/test_dock.py
import unittest

from sqlch_gui.ui.dock import (
    DOCK_GAP, Rect, clamp, default_dock, pack, snap, touches,
)

NP = Rect(1000, 48, 290, 500)
FLUSH_X = NP.x - DOCK_GAP - 320  # left edge of a 320-wide window flush against NP


class TestSnap(unittest.TestCase):
    def test_snaps_edge_and_top_within_dist(self):
        r = snap(Rect(FLUSH_X + 8, 60, 320, 500), [NP], 20)
        self.assertEqual((r.x, r.y), (FLUSH_X, 48))

    def test_outside_dist_unchanged(self):
        r = Rect(FLUSH_X - 60, 60, 320, 500)
        self.assertEqual(snap(r, [NP], 20), r)

    def test_no_vertical_overlap_no_side_snap(self):
        r = Rect(FLUSH_X + 8, 2000, 320, 500)
        self.assertEqual(snap(r, [NP], 20), r)

    def test_bottom_align(self):
        r = snap(Rect(FLUSH_X + 3, 48 + 500 - 320 + 10, 320, 320), [NP], 20)
        self.assertEqual(r.bottom, NP.bottom)

    def test_stack_below(self):
        r = snap(Rect(1005, NP.bottom + DOCK_GAP + 9, 290, 200), [NP], 20)
        self.assertEqual(r.y, NP.bottom + DOCK_GAP)
        self.assertEqual(r.x, 1000)   # left-aligned while stacked

    def test_snaps_to_nearest_of_several(self):
        far = Rect(0, 48, 320, 500)
        r = snap(Rect(FLUSH_X + 5, 48, 320, 500), [far, NP], 20)
        self.assertEqual(r.x, FLUSH_X)


class TestTouches(unittest.TestCase):
    def test_flush_touches(self):
        self.assertTrue(touches(Rect(FLUSH_X, 48, 320, 500), NP))

    def test_apart_does_not(self):
        self.assertFalse(touches(Rect(FLUSH_X - 40, 48, 320, 500), NP))


class TestClampAndDefault(unittest.TestCase):
    def test_clamp_keeps_onscreen(self):
        self.assertEqual(clamp(Rect(-50, 900, 320, 300), 1920, 1080), Rect(0, 780, 320, 300))

    def test_clamp_oversize_pins_origin(self):
        self.assertEqual(clamp(Rect(10, 10, 3000, 300), 1920, 1080).x, 0)

    def test_default_dock_chains_leftward(self):
        d = default_dock(NP, [("library", 320), ("discover", 320)])
        self.assertEqual(d["library"], Rect(FLUSH_X, 48, 320, 500))
        self.assertEqual(d["discover"].x, d["library"].x - DOCK_GAP - 320)

    def test_default_dock_skips_missing(self):
        d = default_dock(NP, [("discover", 320)])
        self.assertEqual(d["discover"].x, FLUSH_X)
        self.assertNotIn("library", d)
