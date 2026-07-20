import sqlite3
import tempfile
import unittest
from pathlib import Path

from sqlch.core import curation_db


class TestConnect(unittest.TestCase):
    def test_connect_creates_all_three_tables(self):
        with tempfile.TemporaryDirectory() as d:
            conn = curation_db.connect(Path(d) / "test.db")
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertEqual(
                tables,
                {"heard_tracks", "candidate_probes", "stations_curation"},
            )
            conn.close()

    def test_connect_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "test.db"
            curation_db.connect(path).close()
            conn = curation_db.connect(path)  # must not raise on existing schema
            conn.execute("SELECT 1")
            conn.close()

    def test_db_path_defaults_under_data_dir(self):
        from sqlch.core.paths import data_dir
        self.assertEqual(curation_db.db_path(), data_dir() / "curation.db")


class TestHeardTracks(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = curation_db.connect(Path(self._tmp.name) / "test.db")

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_record_and_has_heard(self):
        self.assertFalse(curation_db.has_heard(self.conn, "Pearl Jam", "Even Flow"))
        curation_db.record_heard_track(
            self.conn, "wmmr-mmr-rocks", "Pearl Jam", "Even Flow", when=1000
        )
        self.assertTrue(curation_db.has_heard(self.conn, "Pearl Jam", "Even Flow"))

    def test_has_heard_is_case_sensitive_exact_match(self):
        curation_db.record_heard_track(
            self.conn, "wmmr-mmr-rocks", "Pearl Jam", "Even Flow", when=1000
        )
        self.assertFalse(curation_db.has_heard(self.conn, "pearl jam", "even flow"))

    def test_heard_pairs_returns_set_of_tuples(self):
        curation_db.record_heard_track(self.conn, "s1", "A", "X", when=1)
        curation_db.record_heard_track(self.conn, "s1", "B", "Y", when=2)
        self.assertEqual(
            curation_db.heard_pairs(self.conn), {("A", "X"), ("B", "Y")}
        )

    def test_heard_pairs_skips_rows_missing_artist_or_title(self):
        curation_db.record_heard_track(self.conn, "s1", None, "X", when=1)
        curation_db.record_heard_track(self.conn, "s1", "B", None, when=2)
        self.assertEqual(curation_db.heard_pairs(self.conn), set())


class TestCandidateProbes(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = curation_db.connect(Path(self._tmp.name) / "test.db")

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_first_probe_is_recorded(self):
        curation_db.record_candidate_probe(self.conn, "s1", "A", "X", when=1000)
        probes = curation_db.get_probes(self.conn, "s1")
        self.assertEqual(len(probes), 1)
        self.assertEqual(probes[0]["artist"], "A")
        self.assertEqual(probes[0]["title"], "X")
        self.assertEqual(probes[0]["observed_at"], 1000)

    def test_repeat_of_same_title_is_not_recorded_again(self):
        curation_db.record_candidate_probe(self.conn, "s1", "A", "X", when=1000)
        curation_db.record_candidate_probe(self.conn, "s1", "A", "X", when=1180)
        self.assertEqual(len(curation_db.get_probes(self.conn, "s1")), 1)

    def test_title_change_is_recorded_as_new_row(self):
        curation_db.record_candidate_probe(self.conn, "s1", "A", "X", when=1000)
        curation_db.record_candidate_probe(self.conn, "s1", "B", "Y", when=1180)
        self.assertEqual(len(curation_db.get_probes(self.conn, "s1")), 2)

    def test_probes_are_scoped_per_station(self):
        curation_db.record_candidate_probe(self.conn, "s1", "A", "X", when=1000)
        curation_db.record_candidate_probe(self.conn, "s2", "A", "X", when=1000)
        self.assertEqual(len(curation_db.get_probes(self.conn, "s1")), 1)
        self.assertEqual(len(curation_db.get_probes(self.conn, "s2")), 1)

    def test_get_probes_returns_in_chronological_order(self):
        curation_db.record_candidate_probe(self.conn, "s1", "A", "X", when=2000)
        curation_db.record_candidate_probe(self.conn, "s1", "B", "Y", when=1000)
        probes = curation_db.get_probes(self.conn, "s1")
        self.assertEqual([p["observed_at"] for p in probes], [1000, 2000])
