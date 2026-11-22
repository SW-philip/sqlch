import unittest
from unittest import mock

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from sqlch_gui.ui.radio_pane import RadioPane


def panel():
    p = Gtk.Box()
    p.on_shown = mock.Mock()
    p.abort_probes = mock.Mock()
    return p


class TestRadioPane(unittest.TestCase):
    def make(self):
        lib, disc = panel(), panel()
        return RadioPane(lib, disc), lib, disc

    def test_starts_on_library_with_pill_marked(self):
        pane, lib, disc = self.make()
        self.assertEqual(pane.section, "library")
        self.assertEqual(pane.stack.get_visible_child(), lib)
        self.assertTrue(pane._pills["library"].has_css_class("active"))
        self.assertFalse(pane._pills["discover"].has_css_class("active"))

    def test_select_switches_visible_panel(self):
        pane, lib, disc = self.make()
        pane.select("discover")
        self.assertEqual(pane.stack.get_visible_child(), disc)
        self.assertTrue(pane._pills["discover"].has_css_class("active"))
        self.assertFalse(pane._pills["library"].has_css_class("active"))

    def test_unknown_section_ignored(self):
        pane, lib, _ = self.make()
        pane.select("nope")
        self.assertEqual(pane.stack.get_visible_child(), lib)

    def test_library_probes_only_run_while_library_is_showing(self):
        pane, lib, disc = self.make()
        pane.on_shown()
        lib.on_shown.assert_called_once()
        pane.select("discover")
        lib.abort_probes.assert_called_once()
        pane.select("library")
        self.assertEqual(lib.on_shown.call_count, 2)
        pane.on_hidden()
        self.assertEqual(lib.abort_probes.call_count, 2)

    def test_hidden_pane_does_not_start_probes_on_select(self):
        pane, lib, disc = self.make()
        pane.select("discover")
        pane.select("library")
        lib.on_shown.assert_not_called()

    def test_shown_on_discover_does_not_probe_library(self):
        pane, lib, disc = self.make()
        pane.select("discover")
        pane.on_shown()
        lib.on_shown.assert_not_called()


if __name__ == "__main__":
    unittest.main()
