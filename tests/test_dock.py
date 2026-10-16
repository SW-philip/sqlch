# tests/test_dock.py
import unittest

from sqlch_gui.ui.dock import (
    BREAK_OUT, DOCK_GAP, SNAP_IN, Magnet, Rect, clamp, default_dock, held_at, magnet,
    pack, screen_edge_rects, snap, touches,
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


class TestPack(unittest.TestCase):
    def _slot(self, n):
        return Rect(NP.x - n * (320 + DOCK_GAP), NP.y, 320, NP.h)

    def test_no_placed_matches_default_dock(self):
        items = [("library", 320), ("discover", 320)]
        self.assertEqual(pack(NP, items, []), default_dock(NP, items))

    def test_placed_in_slot1_pushes_unplaced_to_slot2(self):
        d = pack(NP, [("discover", 320)], [self._slot(1)])
        self.assertEqual(d["discover"], Rect(FLUSH_X - DOCK_GAP - 320, 48, 320, 500))
        self.assertEqual(d["discover"], self._slot(2))

    def test_two_placed_chain_pushes_to_slot3(self):
        d = pack(NP, [("discover", 320)], [self._slot(1), self._slot(2)])
        self.assertEqual(d["discover"], self._slot(3))

    def test_placed_without_vertical_overlap_ignored(self):
        items = [("library", 320)]
        far = [Rect(FLUSH_X, 2000, 320, 500)]
        self.assertEqual(pack(NP, items, far), default_dock(NP, items))

    def test_placed_right_of_np_ignored(self):
        items = [("library", 320)]
        right = [Rect(NP.right + 50, 48, 320, 500)]
        self.assertEqual(pack(NP, items, right), default_dock(NP, items))

    def test_two_unplaced_chain_after_placed(self):
        d = pack(NP, [("library", 320), ("discover", 320)], [self._slot(1)])
        self.assertEqual(d["library"], self._slot(2))
        self.assertEqual(d["discover"], self._slot(3))


class TestMagnet(unittest.TestCase):
    Y = 148  # no y candidate within SNAP_IN of NP (top 48)

    def _card(self, x, y=None):
        return Rect(x, self.Y if y is None else y, 320, 500)

    def test_a_far_stays_free(self):
        raw = self._card(FLUSH_X - 30)
        self.assertEqual(magnet(raw, [NP], Magnet(None, None)),
                         (raw, Magnet(None, None), False))

    def test_b_snaps_flush_with_click(self):
        r, held, clicked = magnet(self._card(FLUSH_X - 20), [NP], Magnet(None, None))
        self.assertEqual(r, self._card(FLUSH_X))
        self.assertEqual(held, Magnet(FLUSH_X, None))
        self.assertTrue(clicked)

    def test_c_held_stays_without_click(self):
        r, held, clicked = magnet(self._card(FLUSH_X - 30), [NP], Magnet(FLUSH_X, None))
        self.assertEqual(r, self._card(FLUSH_X))
        self.assertEqual(held, Magnet(FLUSH_X, None))
        self.assertFalse(clicked)

    def test_d_breaks_away_past_threshold(self):
        raw = self._card(FLUSH_X - BREAK_OUT - 1)
        self.assertEqual(magnet(raw, [NP], Magnet(FLUSH_X, None)),
                         (raw, Magnet(None, None), False))

    def test_e_reapproach_clicks_again(self):
        _, held, _ = magnet(self._card(FLUSH_X - 60), [NP], Magnet(FLUSH_X, None))
        self.assertEqual(held, Magnet(None, None))
        r, held, clicked = magnet(self._card(FLUSH_X - SNAP_IN), [NP], held)
        self.assertEqual(r, self._card(FLUSH_X))
        self.assertTrue(clicked)

    def test_f_axes_independent(self):
        # x held flush, y free: y follows raw
        r, held, clicked = magnet(self._card(FLUSH_X - 10, 300), [NP], Magnet(FLUSH_X, None))
        self.assertEqual(r, self._card(FLUSH_X, 300))
        self.assertEqual(held, Magnet(FLUSH_X, None))
        self.assertFalse(clicked)
        # y then snaps to NP top while x stays held; only the y entry clicks
        r, held, clicked = magnet(self._card(FLUSH_X - 10, 60), [NP], held)
        self.assertEqual(r, self._card(FLUSH_X, 48))
        self.assertEqual(held, Magnet(FLUSH_X, 48))
        self.assertTrue(clicked)

    def test_g_screen_edges_leave_margin(self):
        edges = screen_edge_rects(1920, 1080)
        cases = [
            (Rect(5, 300, 290, 500), Rect(12, 300, 290, 500)),
            (Rect(1920 - 290 - 5, 300, 290, 500), Rect(1920 - 290 - 12, 300, 290, 500)),
            (Rect(700, 4, 290, 500), Rect(700, 12, 290, 500)),
            (Rect(700, 1080 - 500 - 4, 290, 500), Rect(700, 1080 - 500 - 12, 290, 500)),
        ]
        for raw, want in cases:
            r, _, clicked = magnet(raw, edges, Magnet(None, None))
            self.assertEqual(r, want)
            self.assertTrue(clicked)


if __name__ == "__main__":
    unittest.main()


class TestHeldAt(unittest.TestCase):
    def test_free_window_holds_nothing(self):
        self.assertEqual(held_at(Rect(100, 300, 320, 500), [NP]), Magnet(None, None))

    def test_side_docked_and_top_aligned_holds_both_axes(self):
        r = Rect(FLUSH_X, NP.y, 320, NP.h)
        self.assertEqual(held_at(r, [NP]), Magnet(FLUSH_X, NP.y))

    def test_side_docked_but_not_aligned_holds_only_x(self):
        r = Rect(FLUSH_X, NP.y + 100, 320, NP.h)
        self.assertEqual(held_at(r, [NP]), Magnet(FLUSH_X, None))

    def test_stacked_below_and_left_aligned_holds_both_axes(self):
        r = Rect(NP.x, NP.bottom + DOCK_GAP, 290, 200)
        self.assertEqual(held_at(r, [NP]), Magnet(NP.x, r.y))

    def test_seeded_nudge_does_not_click_and_breaks_at_break_out(self):
        r = Rect(FLUSH_X, NP.y, 320, NP.h)
        held = held_at(r, [NP])
        shown, held, clicked = magnet(r.moved(-30, 0), [NP], held)
        self.assertEqual((shown.x, clicked), (FLUSH_X, False))
        shown, held, _ = magnet(r.moved(-(BREAK_OUT + 1), 0), [NP], held)
        self.assertEqual(shown.x, FLUSH_X - BREAK_OUT - 1)

    def test_default_np_is_held_against_right_screen_edge(self):
        np = Rect(1920 - 12 - 290, 48, 290, 500)
        self.assertEqual(held_at(np, screen_edge_rects(1920, 1080)), Magnet(np.x, None))
