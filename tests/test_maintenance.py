"""Regressões dos problemas encontrados na revisão de código."""

import io
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from scripts.validate_post_mvp import LiveEvidenceOutput
from src.database import _enable_wal, connect
from src.file_io import atomic_output
from src.integrations.webhook import WebhookAlertAdapter
from src.modeling import FEATURE_NAMES, training_arrays
from src.serving_repository import ServingRepository

ROOT = Path(__file__).resolve().parents[1]


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def test_connection_commits_rolls_back_and_closes(self):
        database = self.root / "test.db"
        with connect(database) as connection:
            connection.execute("CREATE TABLE values_test (n INTEGER)")
            connection.execute("INSERT INTO values_test VALUES (1)")
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")
        with self.assertRaises(ValueError):
            with connect(database) as connection:
                connection.execute("INSERT INTO values_test VALUES (2)")
                raise ValueError("Interrupção controlada")
        with connect(database, read_only=True) as connection:
            self.assertEqual(connection.execute("SELECT sum(n) FROM values_test").fetchone()[0], 1)
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("INSERT INTO values_test VALUES (3)")

    def test_read_only_repository_accepts_special_characters_in_path(self):
        name = "NOC #1 dados.db" if sys.platform == "win32" else "NOC #1 ? dados.db"
        database = self.root / name
        with connect(database) as connection:
            connection.execute("CREATE TABLE metadata (key TEXT, value TEXT)")
            connection.execute("INSERT INTO metadata VALUES ('source','official')")
        repository = ServingRepository(database)
        self.assertEqual(repository.metadata(), {"source": "official"})

    def test_failed_file_write_keeps_previous_content(self):
        target = self.root / "forecast.csv"
        target.write_text("original", encoding="utf-8")
        with self.assertRaises(OSError):
            with atomic_output(target) as temporary:
                temporary.write_text("incompleto", encoding="utf-8")
                raise OSError("Falha de escrita simulada")
        self.assertEqual(target.read_text(), "original")
        self.assertEqual(list(self.root.iterdir()), [target])
        with atomic_output(target) as temporary:
            temporary.write_text("novo", encoding="utf-8")
        self.assertEqual(target.read_text(), "novo")

    def test_features_match_published_feature_dataset(self):
        daily = pd.read_csv(ROOT / "data/processed/incident_count_daily.csv", parse_dates=["date"])
        series = daily.set_index("date")["incident_count"]
        expected = pd.read_csv(ROOT / "data/processed/model_features.csv")
        features, targets = training_arrays(series, len(series))
        np.testing.assert_allclose(features, expected[FEATURE_NAMES].to_numpy(), rtol=0, atol=1e-12)
        np.testing.assert_array_equal(targets, expected["incident_count"].to_numpy())

    def test_two_processes_can_initialize_same_database(self):
        database = self.root / "migrations.db"
        command = [
            sys.executable,
            "-c",
            "import sys; from src.database import migrate_database; migrate_database(database=sys.argv[1])",
            str(database),
        ]
        processes = [
            subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for _ in range(2)
        ]
        try:
            for process in processes:
                _, error = process.communicate(timeout=30)
                self.assertEqual(process.returncode, 0, error.decode())
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
        with connect(database, read_only=True) as connection:
            self.assertEqual(
                connection.execute("SELECT count(*) FROM schema_migrations").fetchone()[0], 1
            )

    def test_wal_retries_busy_initialization(self):
        connection = MagicMock()
        busy = sqlite3.OperationalError("database is locked")
        busy.sqlite_errorcode = sqlite3.SQLITE_BUSY
        calls = []

        def execute(sql):
            calls.append(sql)
            if sql == "PRAGMA journal_mode" and calls.count(sql) == 1:
                raise busy
            cursor = MagicMock()
            cursor.fetchone.return_value = ("wal",)
            return cursor

        connection.execute.side_effect = execute
        with patch("src.database.time.sleep") as sleep:
            _enable_wal(connection)
        sleep.assert_called_once()
        self.assertEqual(calls.count("PRAGMA journal_mode"), 2)
        self.assertEqual(calls[-1], "PRAGMA busy_timeout = 30000")

    def test_wal_does_not_retry_unrelated_error(self):
        connection = MagicMock()
        error = sqlite3.OperationalError("disk I/O error")
        error.sqlite_errorcode = sqlite3.SQLITE_IOERR
        connection.execute.side_effect = [None, error, None]
        with patch("src.database.time.sleep") as sleep:
            with self.assertRaises(sqlite3.OperationalError):
                _enable_wal(connection)
        sleep.assert_not_called()
        connection.execute.assert_called_with("PRAGMA busy_timeout = 30000")

    def test_wal_stops_retrying_after_deadline(self):
        connection = MagicMock()
        busy = sqlite3.OperationalError("database is locked")
        busy.sqlite_errorcode = sqlite3.SQLITE_BUSY
        connection.execute.side_effect = [None, busy, None]
        with patch("src.database.time.monotonic", side_effect=[0.0, 31.0]):
            with patch("src.database.time.sleep") as sleep:
                with self.assertRaises(sqlite3.OperationalError):
                    _enable_wal(connection)
        sleep.assert_not_called()
        connection.execute.assert_called_with("PRAGMA busy_timeout = 30000")

    def test_fake_localhost_is_rejected_without_network(self):
        alert = {
            "alert_id": "fixture",
            "forecast_date": "2026-01-01",
            "horizon": 1,
            "predicted_incidents": 700,
            "alert_level": "ATENCAO",
            "rule_triggered": "fixture",
            "model_version": "fixture",
            "status": "OPEN",
        }
        adapter = WebhookAlertAdapter(webhook_url="http://localhost.example.invalid", dry_run=False)
        with patch("urllib.request.urlopen") as network:
            result = adapter.send(alert)
        self.assertEqual(result.status, "FAILED")
        network.assert_not_called()

    def test_progress_is_visible_before_validation_finishes(self):
        console = io.StringIO()
        evidence = io.StringIO()
        output = LiveEvidenceOutput(evidence, console)
        with patch.object(console, "flush", wraps=console.flush) as flush:
            output.write("teste em execução\n")
            flush.assert_called_once()
            self.assertEqual(console.getvalue(), "teste em execução\n")
        self.assertEqual(evidence.getvalue(), console.getvalue())


if __name__ == "__main__":
    unittest.main()
