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
