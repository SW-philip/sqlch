import unittest

from sqlch.core.player import _parse_icy
from sqlch_gui.metadata import parse_icy


class TestParseIcyEntityDecoding(unittest.TestCase):
    """Some stations' broadcast automation sends ICY StreamTitle text
    already HTML-entity-encoded (e.g. WXPN HD2, WMMR), which otherwise
    shows up raw in the GUI, MPRIS, and waybar/playerctl."""

    def test_core_decodes_apos(self):
        self.assertEqual(
            _parse_icy("Charley Crockett - I&apos;m Just A Clown"),
            ("Charley Crockett", "I'm Just A Clown"),
        )

    def test_core_decodes_amp(self):
        self.assertEqual(
            _parse_icy("Hall &amp; Oates - Rich Girl"),
            ("Hall & Oates", "Rich Girl"),
        )

    def test_gui_decodes_apos(self):
        self.assertEqual(
            parse_icy("Charley Crockett - I&apos;m Just A Clown"),
            ("Charley Crockett", "I'm Just A Clown"),
        )

    def test_gui_decodes_amp(self):
        self.assertEqual(
            parse_icy("Hall &amp; Oates - Rich Girl"),
            ("Hall & Oates", "Rich Girl"),
        )

    def test_gui_decodes_amp_before_iheart_dispatch(self):
        title = (
            'AC &amp; DC - text="Thunderstruck" song_spot="M" '
            'spotInstanceId="-1"'
        )
        self.assertEqual(parse_icy(title), ("AC & DC", "Thunderstruck"))

    def test_plain_text_without_entities_unaffected(self):
        self.assertEqual(
            _parse_icy("Damn Yankees - Bad Reputation"),
            ("Damn Yankees", "Bad Reputation"),
        )


if __name__ == "__main__":
    unittest.main()
