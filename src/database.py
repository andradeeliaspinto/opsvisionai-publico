from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.configuration import database_path as configured_database_path

MODEL_STATUSES = ("CANDIDATE", "ACTIVE", "ARCHIVED", "REJECTED")
JOB_STATUSES = ("RUNNING", "SUCCESS", "FAILED")
ALERT_LEVELS = ("ATENCAO", "ALTO", "CRITICO")
ALERT_STATUSES = ("OPEN", "ACKNOWLEDGED", "CLOSED")


MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS pipeline_job_runs (
            job_id TEXT PRIMARY KEY,
            job_type TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            duration_seconds REAL,
            status TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
            records_processed INTEGER,
            model_version TEXT,
            error_message TEXT,
            stack_trace TEXT,
            details_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_pipeline_job_started
            ON pipeline_job_runs(started_at DESC);
        CREATE INDEX IF NOT EXISTS idx_pipeline_job_status
            ON pipeline_job_runs(status, started_at DESC);

        CREATE TABLE IF NOT EXISTS registered_models (
            model_version TEXT PRIMARY KEY,
            algorithm TEXT NOT NULL,
            model_code TEXT NOT NULL,
            trained_at TEXT NOT NULL,
            training_start_date TEXT NOT NULL,
            training_end_date TEXT NOT NULL,
            evaluation_start_date TEXT,
            evaluation_end_date TEXT,
            evaluation_mae REAL,
            baseline_mae REAL,
            mean_signed_error REAL,
            mean_actual REAL,
            horizons_won_against_baseline INTEGER,
            artifact_path TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('CANDIDATE', 'ACTIVE', 'ARCHIVED', 'REJECTED')),
            decision_reason TEXT NOT NULL,
            feature_names_json TEXT NOT NULL,
            hyperparameters_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_registered_models_one_active
            ON registered_models(status) WHERE status = 'ACTIVE';
        CREATE INDEX IF NOT EXISTS idx_registered_models_status
            ON registered_models(status, trained_at DESC);

        CREATE TABLE IF NOT EXISTS model_promotion_history (
            promotion_id TEXT PRIMARY KEY,
            evaluated_at TEXT NOT NULL,
            candidate_version TEXT NOT NULL,
            champion_version TEXT,
            candidate_mae REAL NOT NULL,
            champion_mae REAL NOT NULL,
            baseline_mae REAL NOT NULL,
            candidate_mean_bias REAL NOT NULL,
            candidate_mean_actual REAL NOT NULL,
            horizons_won_against_baseline INTEGER NOT NULL,
            new_actuals_count INTEGER NOT NULL,
            decision TEXT NOT NULL CHECK (decision IN ('PROMOTED', 'REJECTED')),
            reason TEXT NOT NULL,
            policy_version INTEGER NOT NULL,
            evaluation_start_date TEXT NOT NULL,
            evaluation_end_date TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_promotion_evaluated
            ON model_promotion_history(evaluated_at DESC);

        CREATE TABLE IF NOT EXISTS forecast_monitoring_metrics (
            metric_id TEXT PRIMARY KEY,
            source_signature TEXT NOT NULL,
            evaluation_source TEXT NOT NULL CHECK (evaluation_source IN ('LIVE', 'BACKTEST')),
            computed_at TEXT NOT NULL,
            inference_run_id TEXT,
            model_version TEXT NOT NULL,
            forecast_method TEXT NOT NULL,
            period_start TEXT,
            period_end TEXT,
            metric_scope TEXT NOT NULL CHECK (metric_scope IN ('AGGREGATE', 'HORIZON')),
            horizon INTEGER,
            observations INTEGER NOT NULL CHECK (observations >= 0),
            mae REAL,
            mean_signed_error REAL,
            mean_actual REAL,
            CHECK (
                (metric_scope = 'AGGREGATE' AND horizon IS NULL)
                OR (metric_scope = 'HORIZON' AND horizon BETWEEN 1 AND 7)
            )
        );
        CREATE INDEX IF NOT EXISTS idx_monitoring_lookup
            ON forecast_monitoring_metrics(
                evaluation_source, computed_at DESC, model_version, forecast_method, horizon
            );

        CREATE TABLE IF NOT EXISTS alert_threshold_snapshots (
            threshold_set_id TEXT PRIMARY KEY,
            computed_at TEXT NOT NULL,
            history_start_date TEXT NOT NULL,
            history_end_date TEXT NOT NULL,
            observations INTEGER NOT NULL,
            method TEXT NOT NULL,
            p75 REAL NOT NULL,
            p90 REAL NOT NULL,
            p97 REAL NOT NULL,
            policy_version INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS operational_alerts (
            alert_id TEXT PRIMARY KEY,
            inference_run_id TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            forecast_date TEXT NOT NULL,
            horizon INTEGER NOT NULL CHECK (horizon BETWEEN 1 AND 7),
            predicted_incidents REAL NOT NULL CHECK (predicted_incidents >= 0),
            alert_level TEXT NOT NULL CHECK (alert_level IN ('ATENCAO', 'ALTO', 'CRITICO')),
            rule_triggered TEXT NOT NULL,
            threshold_value REAL NOT NULL,
            threshold_set_id TEXT NOT NULL,
            model_version TEXT NOT NULL,
            forecast_method TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('OPEN', 'ACKNOWLEDGED', 'CLOSED')),
            acknowledged_at TEXT,
            closed_at TEXT,
            UNIQUE (inference_run_id, forecast_method, horizon),
            FOREIGN KEY (threshold_set_id) REFERENCES alert_threshold_snapshots(threshold_set_id)
        );
        CREATE INDEX IF NOT EXISTS idx_alerts_status_date
            ON operational_alerts(status, forecast_date);

        CREATE TABLE IF NOT EXISTS integration_delivery_log (
            delivery_id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            alert_id TEXT NOT NULL,
            attempted_at TEXT NOT NULL,
            adapter_name TEXT NOT NULL,
            payload_format TEXT NOT NULL,
            mode TEXT NOT NULL CHECK (mode IN ('DRY_RUN', 'LIVE')),
            status TEXT NOT NULL CHECK (status IN ('DRY_RUN', 'SUCCESS', 'FAILED', 'SKIPPED')),
            attempts INTEGER NOT NULL CHECK (attempts >= 0),
            http_status INTEGER,
            error_message TEXT,
            payload_json TEXT NOT NULL,
            FOREIGN KEY (alert_id) REFERENCES operational_alerts(alert_id)
        );
        CREATE INDEX IF NOT EXISTS idx_delivery_attempted
            ON integration_delivery_log(attempted_at DESC);
        """,
    ),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _enable_wal(connection: sqlite3.Connection, timeout_seconds: float = 30.0) -> None:
    """Aguarda disputa na inicialização do WAL sem ocultar outros erros."""
    deadline = time.monotonic() + timeout_seconds
    # A troca de journal pode retornar BUSY antes de usar todo o busy_timeout.
    connection.execute("PRAGMA busy_timeout = 250")
    try:
        while True:
            try:
                mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
                if str(mode).lower() != "wal":
                    connection.execute("PRAGMA journal_mode = WAL").fetchone()
                return
            except sqlite3.OperationalError as exc:
                code = getattr(exc, "sqlite_errorcode", 0) & 0xFF
                remaining = deadline - time.monotonic()
                if code not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) or remaining <= 0:
                    raise
                time.sleep(min(0.05, remaining))
    finally:
        connection.execute("PRAGMA busy_timeout = 30000")


@contextmanager
def connect(database: str | Path, *, read_only: bool = False):
    """Abre, confirma ou desfaz a transação e sempre fecha a conexão."""
    path = Path(database).resolve()
    if read_only:
        connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        if not read_only:
            _enable_wal(connection)
        with connection:
            yield connection
    finally:
        connection.close()


def migrate_database(
    config_path: str | Path = "config/project.yaml",
    *,
    database: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(database) if database is not None else configured_database_path(config_path)
    applied_now: list[int] = []
    with connect(path) as connection:
        # A leitura da versão e a migração ficam sob o mesmo lock do SQLite.
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        applied = {
            int(row["version"])
            for row in connection.execute("SELECT version FROM schema_migrations")
        }
        for version, script in MIGRATIONS:
            if version in applied:
                continue
            for statement in script.split(";"):
                if statement.strip():
                    connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, utc_now()),
            )
            applied_now.append(version)
        connection.commit()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    return {
        "database": str(path),
        "applied_now": applied_now,
        "latest_version": max((version for version, _ in MIGRATIONS), default=0),
        "integrity": integrity,
    }


def object_exists(connection: sqlite3.Connection, name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name = ? AND type IN ('table', 'view')",
            (name,),
        ).fetchone()
        is not None
    )


def database_catalog(database: str | Path) -> dict[str, Any]:
    path = Path(database)
    with connect(path, read_only=True) as connection:
        objects = connection.execute(
            """
            SELECT type, name, sql
            FROM sqlite_master
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()
        tables: dict[str, int] = {}
        views: dict[str, int] = {}
        indexes: list[str] = []
        for row in objects:
            if row["type"] == "table":
                tables[row["name"]] = int(
                    connection.execute(f'SELECT COUNT(*) FROM "{row["name"]}"').fetchone()[0]
                )
            elif row["type"] == "view":
                views[row["name"]] = int(
                    connection.execute(f'SELECT COUNT(*) FROM "{row["name"]}"').fetchone()[0]
                )
            elif row["type"] == "index":
                indexes.append(row["name"])
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    return {
        "database": str(path),
        "integrity": integrity,
        "tables": tables,
        "views": views,
        "indexes": indexes,
    }
