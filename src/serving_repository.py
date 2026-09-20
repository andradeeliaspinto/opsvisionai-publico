from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd


class ServingRepository:
    """Contrato de leitura entre o dashboard e o serving store SQLite."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)

    def _read(self, query: str, params: tuple = ()) -> pd.DataFrame:
        uri = f"{self.database_path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=30)) as connection:
            return pd.read_sql_query(query, connection, params=params)

    def metadata(self) -> dict[str, str]:
        frame = self._read("SELECT key, value FROM metadata")
        return dict(zip(frame["key"], frame["value"]))

    def model_metrics(self) -> pd.Series:
        return self._read("SELECT * FROM model_metrics LIMIT 1").iloc[0]

    def daily_actuals(self) -> pd.DataFrame:
        return self._read(
            "SELECT actual_date, actual_incidents FROM daily_actuals ORDER BY actual_date"
        )

    def latest_forecasts(self) -> pd.DataFrame:
        return self._read("SELECT * FROM v_latest_inference_run ORDER BY forecast_method, horizon")

    def recommended_forecast(self) -> pd.DataFrame:
        return self._read("SELECT * FROM v_recommended_forecast ORDER BY horizon")

    def backtest(self) -> pd.DataFrame:
        return self._read("SELECT * FROM v_backtest_comparison ORDER BY origin_date, horizon")

    def horizon_metrics(self) -> pd.DataFrame:
        return self._read("SELECT * FROM horizon_metrics ORDER BY horizon")

    def validation_candidates(self) -> pd.DataFrame:
        return self._read("SELECT * FROM validation_candidates ORDER BY validation_mae")

    def category_summary(self) -> pd.DataFrame:
        return self._read("SELECT * FROM category_summary ORDER BY incident_count DESC")

    def priority_summary(self) -> pd.DataFrame:
        return self._read("SELECT * FROM priority_summary ORDER BY incident_count DESC")

    def assignment_group_summary(self) -> pd.DataFrame:
        return self._read("SELECT * FROM assignment_group_summary ORDER BY incident_count DESC")

    def weekday_summary(self) -> pd.DataFrame:
        return self._read("SELECT * FROM weekday_summary ORDER BY weekday_number")

    def hourly_summary(self) -> pd.DataFrame:
        return self._read("SELECT * FROM hourly_summary ORDER BY hour")

    def jobs(self):
        return self._read(
            "SELECT job_id, job_type, started_at, finished_at, duration_seconds, status, records_processed, model_version, error_message FROM pipeline_job_runs ORDER BY started_at DESC, rowid DESC LIMIT 100"
        )

    def registry(self):
        return self._read(
            "SELECT model_version, algorithm, status, training_end_date, evaluation_mae, baseline_mae, decision_reason FROM registered_models ORDER BY trained_at DESC"
        )

    def promotion_history(self):
        return self._read(
            "SELECT evaluated_at, candidate_version, champion_version, candidate_mae, champion_mae, baseline_mae, decision, reason FROM model_promotion_history ORDER BY evaluated_at DESC"
        )

    def alerts(self):
        return self._read("SELECT * FROM operational_alerts ORDER BY generated_at DESC, horizon")

    def deliveries(self):
        return self._read(
            "SELECT attempted_at, alert_id, mode, status, attempts, payload_format, payload_json, error_message FROM integration_delivery_log ORDER BY attempted_at DESC"
        )

    def monitoring_observations(self, source="LIVE"):
        if source not in {"LIVE", "BACKTEST"}:
            raise ValueError("Fonte de monitoramento deve ser LIVE ou BACKTEST.")
        if source == "LIVE":
            return self._read("""SELECT inference_run_id, model_version, forecast_method,
                forecast_date AS target_date, horizon, predicted_incidents AS predicted,
                actual_incidents AS actual, signed_error, absolute_error
                FROM v_forecast_vs_actual WHERE actual_incidents IS NOT NULL
                AND prediction_generated_at < forecast_date
                AND data_cutoff_date < forecast_date""")
        return self._read("""SELECT 'BACKTEST_FINAL' AS inference_run_id, m.model_version,
            m.selected_model AS forecast_method, b.target_date, b.horizon,
            b.model_forecast AS predicted, b.actual,
            b.model_forecast - b.actual AS signed_error,
            b.model_absolute_error AS absolute_error
            FROM v_backtest_comparison b CROSS JOIN model_metrics m""")
