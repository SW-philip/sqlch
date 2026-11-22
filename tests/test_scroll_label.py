import unittest

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from sqlch_gui.ui.scroll_label import ScrollLabel  # noqa: E402

LONG = "a long track title that overflows " * 6


class TestScrollLabelSetText(unittest.TestCase):
    def setUp(self):
        if not Gtk.init_check():
            self.skipTest("no display")
        self.s = ScrollLabel()
        self.s.set_text(LONG)
        self.s._t0 = 1.5
        self.s.get_hadjustment().configure(40.0, 0, 500, 1, 10, 100)

    def test_same_text_keeps_progress(self):
        self.s.set_text(LONG)
        self.assertEqual(self.s._t0, 1.5)
        self.assertEqual(self.s.get_hadjustment().get_value(), 40.0)

    def test_new_text_resets(self):
        self.s.set_text("other")
        self.assertIsNone(self.s._t0)
        self.assertEqual(self.s.get_hadjustment().get_value(), 0.0)
        self.assertEqual(self.s.get_text(), "other")
