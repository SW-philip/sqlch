import unittest

from sqlch_gui import palette

# Keys the flat CSS vocabulary and Cairo widgets read via colors.get(...).
# They exist in the current-generation palette.sh; these must also be in
# _DEFAULTS so the no-palette fallback still resolves them.
_REQUIRED_KEYS = (
    "HALL", "STAGE", "WING", "DIM", "SCORE", "LYRIC", "REST",
    "ROOT", "SEVENTH", "PIANO", "FORTE", "SOTTO", "SHADOW", "STAFF",
    "STAFF_A_OUTER", "STAFF_A_DROP", "STAFF_A_INSET_BOT",
)


class TestPaletteDefaults(unittest.TestCase):
    def test_defaults_cover_flat_vocabulary(self):
        missing = [k for k in _REQUIRED_KEYS if k not in palette._DEFAULTS]
        self.assertEqual(missing, [], f"_DEFAULTS missing keys: {missing}")

    def test_load_without_file_still_resolves_keys(self):
        colors = palette.load("/nonexistent/palette.sh")
        for k in _REQUIRED_KEYS:
            self.assertIn(k, colors)
            self.assertTrue(colors[k], f"{k} resolved empty")


class TestFlatStylesheet(unittest.TestCase):
    def _all_color_dicts(self):
        return (palette.load(), dict(palette._DEFAULTS))

    def test_build_css_is_a_pure_function(self):
        from sqlch_gui.ui import common
        css = common._build_css(dict(palette._DEFAULTS))
        self.assertIsInstance(css, str)
        self.assertIn(".popup-window", css)
        self.assertIn(".section-rule", css)

    def test_no_paper_cutout_vocabulary(self):
        from sqlch_gui.ui import common
        css = common._build_css(palette.load())
        self.assertNotIn("linear-gradient", css)
        self.assertNotIn("text-shadow", css)
        # a single faint noise texture, on the shell only
        self.assertLessEqual(css.count("feTurbulence"), 1)

    def test_css_parses_without_error_on_every_palette(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk
        from sqlch_gui.ui import common
        for colors in self._all_color_dicts():
            css = common._build_css(colors)
            errors = []
            prov = Gtk.CssProvider()
            prov.connect("parsing-error",
                         lambda p, sec, err: errors.append(err.message))
            prov.load_from_string(css)
            self.assertEqual(errors, [], f"CSS parse errors: {errors}")


if __name__ == "__main__":
    unittest.main()
