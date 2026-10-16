import unittest

import gi
gi.require_version("Gtk", "4.0")

from sqlch_gui.ui.controls import NavColumn


class TestNavColumn(unittest.TestCase):
    def test_click_emits_toggle_and_does_not_flip_highlight(self):
        nav, seen = NavColumn(), []
        nav.connect("nav-toggled", lambda _n, name: seen.append(name))
        nav._buttons["library"].emit("clicked")
        nav._buttons["library"].emit("clicked")
        self.assertEqual(seen, ["library", "library"])
        self.assertFalse(nav._buttons["library"].has_css_class("active"))

    def test_set_open_syncs_highlight_independently(self):
        nav, seen = NavColumn(), []
        nav.connect("nav-toggled", lambda _n, name: seen.append(name))
        nav.set_open("library", True)
        nav.set_open("discover", True)
        self.assertTrue(nav._buttons["library"].has_css_class("active"))
        self.assertTrue(nav._buttons["discover"].has_css_class("active"))
        nav.set_open("library", False)
        self.assertFalse(nav._buttons["library"].has_css_class("active"))
        self.assertTrue(nav._buttons["discover"].has_css_class("active"))
        self.assertEqual(seen, [])
