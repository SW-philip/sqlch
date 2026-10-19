import unittest

import gi
gi.require_version("Gtk", "4.0")

from sqlch_gui.ui.controls import NavColumn


ENTRIES = [
    {"name": "local", "label": "Local", "available": True, "hint": ""},
    {"name": "jelly", "label": "Jellyfin", "available": False, "hint": "no server"},
]


class TestNavColumn(unittest.TestCase):
    def test_click_emits_toggle_and_does_not_flip_highlight(self):
        nav, seen = NavColumn(), []
        nav.connect("nav-toggled", lambda _n, name: seen.append(name))
        nav._buttons["radio"].emit("clicked")
        nav._buttons["radio"].emit("clicked")
        self.assertEqual(seen, ["radio", "radio"])
        self.assertFalse(nav._buttons["radio"].has_css_class("active"))

    def test_set_open_syncs_highlight_independently(self):
        nav, seen = NavColumn(), []
        nav.connect("nav-toggled", lambda _n, name: seen.append(name))
        nav.set_sources(ENTRIES)
        nav.set_open("radio", True)
        nav.set_open("local", True)
        self.assertTrue(nav._buttons["radio"].has_css_class("active"))
        self.assertTrue(nav._sources_btn.has_css_class("active"))
        nav.set_open("radio", False)
        self.assertFalse(nav._buttons["radio"].has_css_class("active"))
        self.assertTrue(nav._sources_btn.has_css_class("active"))
        self.assertEqual(seen, [])


class TestNavSources(unittest.TestCase):
    def test_tab_hidden_until_sources_set(self):
        nav = NavColumn()
        self.assertFalse(nav._sources_btn.get_visible())
        nav.set_sources(ENTRIES)
        self.assertTrue(nav._sources_btn.get_visible())

    def test_row_click_emits_and_keeps_dot(self):
        nav, seen = NavColumn(), []
        nav.set_sources(ENTRIES)
        nav.connect("nav-toggled", lambda _n, name: seen.append(name))
        nav._rows["local"][0].emit("clicked")
        self.assertEqual(seen, ["local"])
        self.assertEqual(nav._rows["local"][1].get_text(), "\u25cb")

    def test_set_open_syncs_dot_and_tab(self):
        nav = NavColumn()
        nav.set_sources(ENTRIES)
        nav.set_open("local", True)
        self.assertEqual(nav._rows["local"][1].get_text(), "\u25cf")
        self.assertTrue(nav._sources_btn.has_css_class("active"))
        nav.set_open("jelly", True)
        nav.set_open("local", False)
        self.assertEqual(nav._rows["local"][1].get_text(), "\u25cb")
        self.assertTrue(nav._sources_btn.has_css_class("active"))
        nav.set_open("jelly", False)
        self.assertFalse(nav._sources_btn.has_css_class("active"))

    def test_unavailable_row_is_dimmed_with_hint(self):
        nav = NavColumn()
        nav.set_sources(ENTRIES)
        off = nav._rows["jelly"][0]
        self.assertTrue(off.has_css_class("sq-source-off"))
        self.assertEqual(off.get_tooltip_text(), "no server")
        self.assertFalse(nav._rows["local"][0].has_css_class("sq-source-off"))

    def test_library_open_leaves_sources_tab_alone(self):
        nav = NavColumn()
        nav.set_sources(ENTRIES)
        nav.set_open("radio", True)
        self.assertTrue(nav._buttons["radio"].has_css_class("active"))
        self.assertFalse(nav._sources_btn.has_css_class("active"))


class TestNavSourcesReload(unittest.TestCase):
    def test_removed_name_is_dropped(self):
        nav = NavColumn()
        nav.set_sources(ENTRIES)
        nav.set_sources([ENTRIES[0]])
        self.assertNotIn("jelly", nav._rows)
        nav.set_open("jelly", True)
        self.assertFalse(nav._sources_btn.has_css_class("active"))

    def test_open_state_survives_reload_only_for_existing(self):
        nav = NavColumn()
        nav.set_sources(ENTRIES)
        nav.set_open("local", True)
        nav.set_sources(ENTRIES)
        self.assertEqual(nav._rows["local"][1].get_text(), "\u25cf")
        self.assertTrue(nav._sources_btn.has_css_class("active"))
        nav.set_sources([ENTRIES[1]])
        self.assertFalse(nav._sources_btn.has_css_class("active"))

    def test_unknown_name_is_a_noop(self):
        nav = NavColumn()
        nav.set_sources(ENTRIES)
        nav.set_open("nope", True)
        self.assertFalse(nav._sources_btn.has_css_class("active"))
        self.assertEqual(nav._open_sources, set())
