"""Fixtures sintéticas isoladas em diretórios temporários; nunca são dados de produção."""

import logging
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing, contextmanager
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import pandas as pd
import yaml

from src.alerts import classify_alert, derive_thresholds, generate_operational_alerts
from src.configuration import database_path, model_policy, operations_config
from src.database import connect, migrate_database
from src.integrations import dispatch_operational_alerts
from src.integrations.serializers import build_payload
from src.integrations.webhook import WebhookAlertAdapter
from src.job_tracking import JobTracker
from src.locking import PipelineAlreadyRunningError, exclusive_file_lock
from src.model_registry import (
    finalize_candidate_status,
    get_active_model,
    register_candidate,
)
from src.monitoring import (
    _metric_rows,
    calculate_error_metrics,
    refresh_monitoring_metrics,
)
from src.operations import tracked_operation
from src.retraining import decide_promotion
from src.serving import publish_serving_store

ROOT = Path(__file__).resolve().parents[1]


class OperationalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "Projeto NOC São Paulo"
        # No Windows, handlers abertos impedem a remoção da fixture temporária.
        self.addCleanup(self.close_fixture_logs)
        shutil.copytree(
            ROOT,
            self.root,
            ignore=shutil.ignore_patterns(
                "__pycache__",
                "*.pptx",
                "*.db",
                "*.db-wal",
                "*.db-shm",
                "logs",
                ".venv",
                "venv",
                "env",
                ".git",
                ".pytest_cache",
                "node_modules",
                "*.zip",
                "runtime",
            ),
        )
        self.db = database_path(self.root / "config/project.yaml")
        self.db.parent.mkdir(parents=True, exist_ok=True)
        with (
            closing(sqlite3.connect(database_path(ROOT / "config/project.yaml"))) as source,
            closing(sqlite3.connect(self.db)) as target,
        ):
            source.backup(target)
        self.config = self.root / "config/project.yaml"
        migrate_database(self.config)

    def close_fixture_logs(self):
        logger = logging.getLogger()
        configured = getattr(logger, "_opsvision_configured", None)
        if configured and Path(configured).is_relative_to(self.root):
            for handler in list(logger.handlers):
                if getattr(handler, "_opsvision", False):
                    logger.removeHandler(handler)
                    handler.close()
            delattr(logger, "_opsvision_configured")

    def candidate(self, version="fixture_candidate"):
        active = get_active_model(self.config)
        return {
            **active,
            "model_version": version,
            "status": "CANDIDATE",
            "decision_reason": "Fixture isolada",
        }

    def decision(self, **overrides):
        args = dict(
            candidate_mae=8,
            champion_mae=10,
            baseline_mae=11,
            candidate_mean_bias=1,
            candidate_mean_actual=100,
            horizons_won_against_baseline=7,
            new_actuals_count=90,
            days_since_last_training=90,
            temporal_evaluation_valid=True,
            policy=model_policy(self.config),
        )
        args.update(overrides)
        return decide_promotion(**args)


    def test_registry_reads_legacy_windows_artifact_path(self):
        import joblib

        active = get_active_model(self.config)
        legacy_path = active["artifact_path"].replace("/", "\\")
        with connect(self.db) as connection:
            connection.execute(
                "UPDATE registered_models SET artifact_path=? WHERE status='ACTIVE'",
                (legacy_path,),
            )
        restored = get_active_model(self.config)
        self.assertNotIn("\\", restored["artifact_path"])
        model = joblib.load(self.root / restored["artifact_path"])
        self.assertTrue(callable(model.predict))

    def test_candidate_registration_normalizes_windows_path(self):
        candidate = self.candidate()
        candidate["artifact_path"] = candidate["artifact_path"].replace("/", "\\")
        register_candidate(candidate, self.config)
        with connect(self.db, read_only=True) as connection:
            path = connection.execute(
                "SELECT artifact_path FROM registered_models WHERE model_version=?",
                (candidate["model_version"],),
            ).fetchone()[0]
        self.assertNotIn("\\", path)
        self.assertTrue((self.root / path).is_file())

    def test_lock_precedes_running_job_registration(self):
        @contextmanager
        def observe_lock(*args, **kwargs):
            with connect(self.db, read_only=True) as connection:
                count = connection.execute(
                    "SELECT count(*) FROM pipeline_job_runs WHERE job_type='LOCK_ORDER'"
                ).fetchone()[0]
            self.assertEqual(count, 0, "Ainda nao deve existir um job RUNNING sem lock")
            with exclusive_file_lock(*args, **kwargs) as lock:
                yield lock

        with patch("src.operations.exclusive_file_lock", observe_lock):
            result = tracked_operation(self.config, "LOCK_ORDER", lambda *_: {})
        self.assertEqual(result["status"], "SUCCESS")

    def test_rejected_concurrent_job_does_not_execute_action(self):
        lock = self.root / operations_config(self.config)["pipeline"]["lock_file"]
        with exclusive_file_lock(lock, job_id="owner"):
            with patch("src.operations.configure_logging") as logging_setup:
                with patch("src.operations.daily_action") as action:
                    with self.assertRaises(PipelineAlreadyRunningError):
                        tracked_operation(self.config, "LOCK_REJECTED", action)
                    action.assert_not_called()
                logging_setup.assert_not_called()
        with connect(self.db, read_only=True) as connection:
            row = connection.execute(
                "SELECT status, stack_trace FROM pipeline_job_runs WHERE job_type='LOCK_REJECTED'"
            ).fetchone()
        self.assertEqual(row["status"], "FAILED")
        self.assertIn("PipelineAlreadyRunningError", row["stack_trace"])

    def test_migration_is_idempotent_and_preserves_rows(self):
        self.assertFalse(
            (self.root / ".venv").exists(), "Ambiente virtual não deve entrar na fixture"
        )
        with connect(self.db) as c:
            before = c.execute("SELECT COUNT(*) FROM forecast_predictions").fetchone()[0]
        self.assertEqual(migrate_database(self.config)["applied_now"], [])
        with connect(self.db) as c:
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM forecast_predictions").fetchone()[0], before
            )
            self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_dashboard_uses_configured_database(self):
        from streamlit.testing.v1 import AppTest

        alternate = self.db.with_name("NOC #1.db")
        with closing(sqlite3.connect(self.db)) as source:
            with closing(sqlite3.connect(alternate)) as target:
                source.backup(target)
        self.db.unlink()
        config = yaml.safe_load(self.config.read_text(encoding="utf-8"))
        config["serving"]["database_file"] = str(alternate.relative_to(self.root))
        self.config.write_text(yaml.safe_dump(config), encoding="utf-8")
        app = AppTest.from_file(str(self.root / "app.py"), default_timeout=60).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.tabs), 6)
        self.assertFalse(self.db.exists(), "Dashboard não deve criar um banco no caminho antigo")

    def test_only_one_active_model(self):
        record = self.candidate()
        record["status"] = "ACTIVE"
        with self.assertRaises(sqlite3.IntegrityError):
            register_candidate(record, self.config)

    def test_candidate_inferior_rejected(self):
        self.assertFalse(self.decision(candidate_mae=12).eligible)

    def test_candidate_superior_eligible(self):
        self.assertTrue(self.decision().eligible)

    def test_baseline_gate(self):
        self.assertFalse(self.decision(baseline_mae=7).eligible)

    def test_new_observations_required(self):
        self.assertFalse(self.decision(new_actuals_count=0).eligible)

    def test_temporal_gate(self):
        self.assertFalse(self.decision(temporal_evaluation_valid=False).eligible)

    def test_non_finite_metrics_rejected(self):
        self.assertFalse(self.decision(candidate_mae=float("nan")).eligible)

    def test_promotion_and_rollback_protect_champion(self):
        before = get_active_model(self.config)["model_version"]
        with self.assertRaises(RuntimeError):
            finalize_candidate_status(
                "nonexistent", promoted=True, reason="test", config_path=self.config
            )
        self.assertEqual(get_active_model(self.config)["model_version"], before)
        record = self.candidate()
        register_candidate(record, self.config)
        finalize_candidate_status(
            record["model_version"], promoted=True, reason="fixture", config_path=self.config
        )
        self.assertEqual(get_active_model(self.config)["model_version"], record["model_version"])

    def test_rejection_preserves_champion(self):
        before = get_active_model(self.config)["model_version"]
        record = self.candidate()
        register_candidate(record, self.config)
        finalize_candidate_status(
            record["model_version"], promoted=False, reason="fixture", config_path=self.config
        )
        self.assertEqual(get_active_model(self.config)["model_version"], before)

    def test_metrics_and_horizon_counts(self):
        frame = pd.DataFrame(
            {
                "actual": [10, 20, 30],
                "predicted": [12, 17, 34],
                "horizon": [1, 1, 2],
                "target_date": ["2025-01-01"] * 3,
            }
        )
        metrics = calculate_error_metrics(frame)
        self.assertEqual(metrics["mae"], 3)
        self.assertEqual(metrics["mean_signed_error"], 1)
        rows = _metric_rows(
            frame,
            evaluation_source="BACKTEST",
            source_signature="fixture",
            computed_at="now",
            inference_run_id="fixture",
            model_version="fixture",
            forecast_method="ridge",
        )
        self.assertEqual([r["observations"] for r in rows], [3, 2, 1])

    def test_empty_metrics_are_null_not_zero(self):
        metrics = calculate_error_metrics(pd.DataFrame({"actual": [None], "predicted": [12]}))
        self.assertEqual(metrics["observations"], 0)
        self.assertIsNone(metrics["mae"])

    def test_monitoring_idempotent_and_no_fabricated_actuals(self):
        first = refresh_monitoring_metrics(self.config, database=self.db, write_evidence=False)
        with connect(self.db) as c:
            count = c.execute("SELECT COUNT(*) FROM forecast_monitoring_metrics").fetchone()[0]
        refresh_monitoring_metrics(self.config, database=self.db, write_evidence=False)
        self.assertEqual(first["live_forecasts_evaluated"], 0)
        with connect(self.db) as c:
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM forecast_monitoring_metrics").fetchone()[0], count
            )
            self.assertEqual(
                c.execute("SELECT MAX(actual_date) FROM daily_actuals").fetchone()[0], "2025-12-31"
            )

    def test_live_join_computes_known_fixture(self):
        # Datas e valores de teste permanecem apenas nesta cópia temporária.
        with connect(self.db) as c:
            c.execute(
                "INSERT INTO forecast_predictions VALUES ('2025-12-01T00:00:00+00:00','2025-12-01','2025-12-02',1,100,'fixture','fixture','2025-12-01',0,'fixture')"
            )
        refresh_monitoring_metrics(self.config, database=self.db, write_evidence=False)
        with connect(self.db) as c:
            actual = c.execute(
                "SELECT actual_incidents FROM daily_actuals WHERE actual_date='2025-12-02'"
            ).fetchone()[0]
            row = c.execute(
                "SELECT mae, mean_signed_error FROM forecast_monitoring_metrics WHERE model_version='fixture' AND metric_scope='AGGREGATE'"
            ).fetchone()
            self.assertEqual(row["mae"], abs(100 - actual))
            self.assertEqual(row["mean_signed_error"], 100 - actual)

    def test_late_replay_excluded_from_live_metrics(self):
        with connect(self.db) as c:
            c.execute(
                "INSERT INTO forecast_predictions VALUES ('2026-09-19T00:00:00+00:00','2025-12-01','2025-12-02',1,100,'fixture','fixture','2025-12-01',0,'fixture')"
            )
        refresh_monitoring_metrics(self.config, database=self.db, write_evidence=False)
        with connect(self.db) as c:
            row = c.execute(
                "SELECT observations, mae FROM forecast_monitoring_metrics WHERE model_version='fixture' AND metric_scope='AGGREGATE'"
            ).fetchone()
            self.assertEqual(row["observations"], 0)
            self.assertIsNone(row["mae"])

    def test_job_success_and_failure_persisted(self):
        result = tracked_operation(self.config, "FIXTURE_OK", lambda *_: {"records_processed": 3})

        def failure(*args):
            raise ValueError("Falha controlada de teste")

        with self.assertRaises(ValueError):
            tracked_operation(self.config, "FIXTURE_FAIL", failure)
        with connect(self.db) as c:
            row = c.execute(
                "SELECT * FROM pipeline_job_runs WHERE job_id=?", (result["job_id"],)
            ).fetchone()
            self.assertEqual(row["status"], "SUCCESS")
            row = c.execute(
                "SELECT * FROM pipeline_job_runs WHERE job_type='FIXTURE_FAIL'"
            ).fetchone()
            self.assertEqual(row["status"], "FAILED")
            self.assertIn("ValueError", row["stack_trace"])

    def test_keyboard_interrupt_is_recorded_as_failure(self):
        def interrupted(config, logger, details):
            raise KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            tracked_operation(self.config, "FIXTURE_INTERRUPTED", interrupted)
        with connect(self.db, read_only=True) as connection:
            row = connection.execute(
                "SELECT status,error_message FROM pipeline_job_runs WHERE job_type='FIXTURE_INTERRUPTED'"
            ).fetchone()
        self.assertEqual(row["status"], "FAILED")
        self.assertEqual(row["error_message"], "KeyboardInterrupt")

    def test_lock_blocks_second_process_and_releases(self):
        lock = self.root / "lock"
        code = "from src.locking import PipelineAlreadyRunningError, exclusive_file_lock; import sys\nwith exclusive_file_lock(sys.argv[1], job_id='child'): pass"
        with exclusive_file_lock(lock, job_id="parent"):
            result = subprocess.run(
                [sys.executable, "-B", "-c", code, str(lock)], cwd=ROOT, capture_output=True
            )
            self.assertNotEqual(result.returncode, 0)
        with exclusive_file_lock(lock, job_id="new"):
            pass

    def test_publication_preserves_operational_and_prediction_history(self):
        tracker = JobTracker(self.config)
        job = tracker.start("PERSISTENCE_FIXTURE")
        with connect(self.db) as c:
            before = c.execute("SELECT COUNT(*) FROM forecast_predictions").fetchone()[0]
            count = c.execute("SELECT COUNT(*) FROM operational_alerts").fetchone()[0]
        publish_serving_store(self.config)
        publish_serving_store(self.config)
        with connect(self.db) as c:
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM forecast_predictions").fetchone()[0], before
            )
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM operational_alerts").fetchone()[0], count
            )
            self.assertEqual(
                c.execute("SELECT status FROM pipeline_job_runs WHERE job_id=?", (job,)).fetchone()[
                    0
                ],
                "RUNNING",
            )

    def test_alert_boundary_and_percentiles(self):
        limits = derive_thresholds(pd.Series(range(101)))
        self.assertEqual(limits, {"p75": 75.0, "p90": 90.0, "p97": 97.0})
        self.assertEqual(
            [classify_alert(v, limits)[0] for v in [74, 75, 90, 97]],
            ["NORMAL", "ATENCAO", "ALTO", "CRITICO"],
        )

    def test_alerts_and_payload_are_idempotent(self):
        first = generate_operational_alerts(self.config, database=self.db, write_evidence=False)
        second = generate_operational_alerts(self.config, database=self.db, write_evidence=False)
        self.assertEqual(first["inference_run_id"], second["inference_run_id"])
        with connect(self.db) as c:
            count = c.execute(
                "SELECT COUNT(*) FROM operational_alerts WHERE inference_run_id=?",
                (first["inference_run_id"],),
            ).fetchone()[0]
        self.assertEqual(count, first["alerts_persisted"])
        with patch("urllib.request.urlopen") as network:
            result = dispatch_operational_alerts(
                self.config, database=self.db, force_dry_run=True, write_evidence=False
            )
            network.assert_not_called()
        self.assertEqual(result["network_calls_performed"], 0)
        self.assertEqual(result["mode"], "DRY_RUN")

    def test_serializers_and_retry_bound(self):
        with connect(self.db) as c:
            alert = dict(c.execute("SELECT * FROM operational_alerts LIMIT 1").fetchone())
        for format in ["generic", "teams", "slack"]:
            self.assertIsInstance(build_payload(alert, format), dict)
        with self.assertRaises(ValueError):
            build_payload({}, "generic")
        for field, value in [
            ("horizon", 8),
            ("predicted_incidents", float("nan")),
            ("forecast_date", "invalid"),
            ("status", "INVALID"),
        ]:
            with self.assertRaises(ValueError):
                build_payload({**alert, field: value}, "generic")
        adapter = WebhookAlertAdapter(
            webhook_url="https://example.invalid",
            dry_run=False,
            max_retries=2,
            retry_backoff_seconds=0,
        )
        with patch("urllib.request.urlopen", side_effect=URLError("fixture")) as mocked:
            result = adapter.send(alert)
        self.assertEqual(mocked.call_count, 3)
        self.assertEqual(result.status, "FAILED")


if __name__ == "__main__":
    unittest.main()
