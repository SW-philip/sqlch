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


if __name__ == "__main__":
    unittest.main()
