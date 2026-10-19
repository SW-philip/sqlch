import unittest

from sqlch_gui.ui.grouping import LABELS, MODES, group, next_mode

PROV = {"apple": {"title": "APPLE PODCASTS", "short": "apple"},
        "podcastindex": {"title": "PODCAST INDEX", "short": "pi"}}


def it(title, genre=None, providers=("apple",)):
    return {"title": title, "genre": genre, "providers": list(providers)}


A = it("smartless", "Comedy", ("apple", "podcastindex"))
B = it("Conan", "Comedy")
C = it("Serial", "True Crime")
D = it("Linux Unplugged", "Technology", ("podcastindex",))
E = it("Mystery", None, ("apple",))


def shape(rows):
    return [(r[0], r[1] if r[0] == "header" else r[1]["title"], r[2]) for r in rows]


class TestGrouping(unittest.TestCase):
    def test_modes_cycle(self):
        self.assertEqual(MODES, ("source", "genre", "az"))
        self.assertEqual([next_mode(m, MODES) for m in MODES], ["genre", "az", "source"])
        self.assertEqual(LABELS["az"], "A–Z")

    def test_az(self):
        self.assertEqual(shape(group([C, A, B], "az", PROV)), [
            ("item", "Conan", "Comedy"), ("item", "Serial", "True Crime"),
            ("item", "smartless", "Comedy")])

    def test_genre_puts_other_last_and_tags_providers(self):
        self.assertEqual(shape(group([E, D, A, B], "genre", PROV)), [
            ("header", "Comedy", 0),
            ("item", "Conan", "apple"), ("item", "smartless", "apple·pi"),
            ("header", "Technology", 0), ("item", "Linux Unplugged", "pi"),
            ("header", "Other", 0), ("item", "Mystery", "apple")])

    def test_source_nests_genre_and_repeats_shared_shows(self):
        self.assertEqual(shape(group([A, B, C, D], "source", PROV)), [
            ("header", "APPLE PODCASTS", 0),
            ("header", "Comedy", 1), ("item", "Conan", ""), ("item", "smartless", ""),
            ("header", "True Crime", 1), ("item", "Serial", ""),
            ("header", "PODCAST INDEX", 0),
            ("header", "Comedy", 1), ("item", "smartless", ""),
            ("header", "Technology", 1), ("item", "Linux Unplugged", "")])

    def test_source_with_unknown_and_missing_providers(self):
        rows = shape(group([it("X", "Arts", ("zeta",)), it("Y", "Arts", ())], "source", PROV))
        self.assertEqual(rows, [("header", "ZETA", 0), ("header", "Arts", 1), ("item", "X", ""),
                                ("header", "OTHER", 0), ("header", "Arts", 1), ("item", "Y", "")])

    def test_empty(self):
        for m in MODES:
            self.assertEqual(group([], m, PROV), [])

    def test_non_string_genre_and_title_do_not_raise(self):
        bad = it(None, 5)
        for m in MODES:
            rows = group([bad, B], m, PROV)
            self.assertIn(("item", bad), [r[:2] for r in rows])
        self.assertEqual(group([bad, B], "genre", PROV)[-2:],
                         [("header", "Other", 0), ("item", bad, "apple")])
        self.assertEqual(group([bad], "az", PROV), [("item", bad, "")])
        self.assertEqual(group([bad], "source", PROV)[1], ("header", "Other", 1))
