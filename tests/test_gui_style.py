import pathlib
import unittest

from sqlch_gui import palette

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

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


class TestBannerWidgets(unittest.TestCase):
    def test_ribbon_banner_is_a_box_with_engraved_label(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk
        from sqlch_gui.ui.banner import RibbonBanner
        b = RibbonBanner("jazz")
        self.assertIsInstance(b, Gtk.Box)
        self.assertTrue(b.has_css_class("section-rule"))
        self.assertEqual(b.label.get_text(), "JAZZ")
        b.set_text("news")
        self.assertEqual(b.label.get_text(), "NEWS")
        g = RibbonBanner("browse categories", gold=True)
        self.assertTrue(g.has_css_class("gold"))

    def test_ribbon_banner_collapsible_starts_expanded_with_chevron(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from sqlch_gui.ui.banner import RibbonBanner
        b = RibbonBanner("news", collapsible=True)
        self.assertEqual(b.label.get_text(), "▾ NEWS")

    def test_ribbon_banner_collapsible_can_start_collapsed(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from sqlch_gui.ui.banner import RibbonBanner
        b = RibbonBanner("news", collapsible=True, collapsed=True)
        self.assertEqual(b.label.get_text(), "▸ NEWS")

    def test_ribbon_banner_click_toggles_and_calls_on_toggle(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from sqlch_gui.ui.banner import RibbonBanner
        toggled = []
        b = RibbonBanner("news", collapsible=True, on_toggle=toggled.append)

        b._on_click(None, 1, 0, 0)
        self.assertEqual(b.label.get_text(), "▸ NEWS")
        self.assertEqual(toggled, [True])

        b._on_click(None, 1, 0, 0)
        self.assertEqual(b.label.get_text(), "▾ NEWS")
        self.assertEqual(toggled, [True, False])

    def test_ribbon_banner_set_collapsed_updates_chevron(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from sqlch_gui.ui.banner import RibbonBanner
        b = RibbonBanner("news", collapsible=True)
        b.set_collapsed(True)
        self.assertEqual(b.label.get_text(), "▸ NEWS")

    def test_ribbon_banner_non_collapsible_has_no_chevron(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from sqlch_gui.ui.banner import RibbonBanner
        b = RibbonBanner("news")
        self.assertEqual(b.label.get_text(), "NEWS")

    def test_pennant_tag_is_a_box_exposing_label(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk
        from sqlch_gui.ui.banner import PennantTag
        p = PennantTag("US", country=True)
        self.assertIsInstance(p, Gtk.Box)
        self.assertTrue(p.has_css_class("tag-chip"))
        self.assertTrue(p.has_css_class("country"))
        self.assertEqual(p.label.get_text(), "US")

    def test_torn_separator_draw_does_not_raise(self):
        import cairo
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk
        from sqlch_gui.ui.banner import TornSeparator
        for orient in (Gtk.Orientation.VERTICAL, Gtk.Orientation.HORIZONTAL):
            sep = TornSeparator(orient)
            if orient == Gtk.Orientation.HORIZONTAL:
                w, h = 200, 18
            else:
                w, h = 18, 200
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
            cr = cairo.Context(surf)
            sep._on_draw(sep, cr, w, h)


class TestControlWidgetsFlat(unittest.TestCase):
    def _ctx(self, w, h):
        import cairo
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        return cairo.Context(surf)

    def test_record_bubble_draw_flat_no_raise(self):
        from sqlch_gui.ui.controls import RecordBubble
        b = RecordBubble()
        b._on_draw(b, self._ctx(34, 34), 34, 34)
        b.set_state(True, "track")
        b._on_draw(b, self._ctx(34, 34), 34, 34)

    def test_volume_meter_draw_flat_no_raise(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk
        from sqlch_gui.ui.controls import VolumeMeter
        adj = Gtk.Adjustment(value=0.6, lower=0.0, upper=1.0, step_increment=0.05)
        m = VolumeMeter(adj)
        m._on_draw(m, self._ctx(160, 18), 160, 18)
        m.boosted = True
        m._on_draw(m, self._ctx(160, 18), 160, 18)

    def test_controls_source_has_no_hardcoded_rgb_literals(self):
        src = (_REPO_ROOT / "sqlch_gui/ui/controls.py").read_text()
        # the pop-it bubble's hardcoded reds / greys are gone
        self.assertNotIn("0.86, 0.20, 0.18", src)
        self.assertNotIn("cairo.RadialGradient", src)


class TestEqStrip(unittest.TestCase):
    def test_bead_draw_no_raise_and_single_tone(self):
        import cairo
        from sqlch_gui.ui.eq_strip import EqStrip
        s = EqStrip(n_beads=3, width=18, height=11)
        s._running = True
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 18, 11)
        s._on_draw(s, cairo.Context(surf), 18, 11)
        src = (_REPO_ROOT / "sqlch_gui/ui/eq_strip.py").read_text()
        # the ROOT->SEVENTH cross-fade is gone
        self.assertNotIn("tail_r", src)


class TestDepthPass(unittest.TestCase):
    def test_drop_shadow_is_stronger_than_original(self):
        from sqlch_gui.ui import common
        css = common._build_css(dict(palette._DEFAULTS))
        self.assertIn("box-shadow: 0 2px 3px", css)
        self.assertNotIn("box-shadow: 0 1px 1px", css)

    def test_recess_shadow_is_stronger_than_original(self):
        from sqlch_gui.ui import common
        css = common._build_css(dict(palette._DEFAULTS))
        self.assertIn("inset 0 2px 4px", css)
        self.assertNotIn("inset 0 1px 2px", css)

    def test_cover_art_uses_recess_not_drop(self):
        from sqlch_gui.ui import common
        css = common._build_css(dict(palette._DEFAULTS))
        cover_rule = css.split(".cover-art {")[1].split("}")[0]
        self.assertIn("inset", cover_rule)


class TestPlayerEdgeBorder(unittest.TestCase):
    """The Now Playing card and its own children get a louder border than
    the app-wide hairline, so the player visibly separates from the shell
    even on palettes where STAGE/WING sit close in lightness. Scoped to
    classes now_playing.py owns outright (.card, .sq-tab,
    .cover-art, .info-panel, .control-btn) -- station list / discover /
    context-menu chrome keeps the original hairline."""

    def _rule(self, css, selector):
        return css.split(selector + " {")[1].split("}")[0]

    def test_player_classes_use_a_stronger_border_than_hairline(self):
        from sqlch_gui.ui import common
        css = common._build_css(dict(palette._DEFAULTS))
        for selector in (".card", ".sq-tab", ".cover-art",
                         ".info-panel", ".control-btn"):
            border = self._rule(css, selector).split("border:")[1].split(";")[0]
            self.assertIn("2px solid", border, f"{selector} border: {border!r}")
        self.assertNotIn("rgba(224, 222, 244, 0.14)",
                          self._rule(css, ".card"))

    def test_non_player_classes_keep_the_original_hairline(self):
        from sqlch_gui.ui import common
        css = common._build_css(dict(palette._DEFAULTS))
        for selector in (".station-row", ".list-header", ".menu-btn"):
            border = self._rule(css, selector).split("border:")[1].split(";")[0]
            self.assertIn("1px solid", border, f"{selector} border: {border!r}")

    def test_header_classes_are_styled(self):
        from sqlch_gui.ui import common
        css = common._build_css(dict(palette._DEFAULTS))
        for selector in (".sq-header", ".sq-nameplate", ".sq-plate", ".sq-led",
                         ".sq-track", ".sq-station", ".sq-tabs"):
            self.assertIn(selector + " {", css, f"{selector} missing")


if __name__ == "__main__":
    unittest.main()
