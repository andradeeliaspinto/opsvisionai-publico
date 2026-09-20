from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.configuration import database_path as configured_database_path
from src.configuration import project_root
from src.database import connect, migrate_database

BASELINE_CODE = "seasonal_naive_lag_7"
BASELINE_VERSION = "baseline_lag7_v1"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _digest(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def calculate_error_metrics(
    frame: pd.DataFrame,
    *,
    actual_column: str = "actual",
    prediction_column: str = "predicted",
) -> dict[str, float | int | None]:
    valid = frame[[actual_column, prediction_column]].dropna().astype(float)
    if valid.empty:
        return {
            "observations": 0,
            "mae": None,
            "mean_signed_error": None,
            "mean_actual": None,
        }
    signed_error = valid[prediction_column] - valid[actual_column]
    return {
        "observations": int(len(valid)),
        "mae": float(signed_error.abs().mean()),
        "mean_signed_error": float(signed_error.mean()),
        "mean_actual": float(valid[actual_column].mean()),
    }


def _metric_rows(
    frame: pd.DataFrame,
    *,
    evaluation_source: str,
    source_signature: str,
    computed_at: str,
    inference_run_id: str | None,
    model_version: str,
    forecast_method: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    observed = frame.dropna(subset=["actual", "predicted"]).copy()
    period_start = (
        None if observed.empty else str(pd.to_datetime(observed["target_date"]).min().date())
    )
    period_end = (
        None if observed.empty else str(pd.to_datetime(observed["target_date"]).max().date())
    )

    def append_metric(scope: str, subset: pd.DataFrame, horizon: int | None) -> None:
        metrics = calculate_error_metrics(subset)
        identity = {
            "source_signature": source_signature,
            "scope": scope,
            "horizon": horizon,
        }
        rows.append(
            {
                "metric_id": "metric_" + _digest(identity)[:24],
                "source_signature": source_signature,
                "evaluation_source": evaluation_source,
                "computed_at": computed_at,
                "inference_run_id": inference_run_id,
                "model_version": model_version,
                "forecast_method": forecast_method,
                "period_start": period_start,
                "period_end": period_end,
                "metric_scope": scope,
                "horizon": horizon,
                **metrics,
            }
        )

    append_metric("AGGREGATE", observed, None)
    if not observed.empty:
        for horizon, group in observed.groupby("horizon"):
            append_metric("HORIZON", group, int(horizon))
    return rows


def refresh_monitoring_metrics(
    config_path: str | Path = "config/project.yaml",
    *,
    database: str | Path | None = None,
    write_evidence: bool = True,
) -> dict[str, Any]:
    root = project_root(config_path)
    database_file = (
        Path(database) if database is not None else configured_database_path(config_path)
    )
    migrate_database(config_path, database=database_file)
    backtest_model = json.loads(
        (root / "evidence/05_model_summary.json").read_text(encoding="utf-8")
    )
    active = {
        "model_version": backtest_model["model_version"],
        "model_code": backtest_model["selected_model_code"],
    }
    computed_at = _now()

    with connect(database_file, read_only=True) as connection:
        live_raw = pd.read_sql_query(
            """
            SELECT p.inference_run_id, p.forecast_date AS target_date, p.horizon,
                   p.predicted_incidents AS predicted, p.forecast_method,
                   p.model_version,
                   CASE WHEN p.prediction_generated_at < p.forecast_date
                         AND p.data_cutoff_date < p.forecast_date
                        THEN a.actual_incidents ELSE NULL END AS actual
            FROM forecast_predictions p
            LEFT JOIN daily_actuals a ON a.actual_date = p.forecast_date
            ORDER BY p.prediction_generated_at, p.inference_run_id,
                     p.forecast_method, p.horizon
            """,
            connection,
        )
        backtest_raw = pd.read_sql_query(
            """
            SELECT target_date, horizon, actual, model_forecast, baseline_forecast
            FROM backtest_predictions
            ORDER BY origin_date, horizon
            """,
            connection,
        )

    rows: list[dict[str, Any]] = []
    if not live_raw.empty:
        for (run_id, method, version), group in live_raw.groupby(
            ["inference_run_id", "forecast_method", "model_version"], dropna=False
        ):
            signature = _digest(
                {
                    "source": "LIVE",
                    "run": run_id,
                    "method": method,
                    "version": version,
                    "actual_dates": group.dropna(subset=["actual"])["target_date"].tolist(),
                    "actual_values": group.dropna(subset=["actual"])["actual"].tolist(),
                }
            )
            rows.extend(
                _metric_rows(
                    group,
                    evaluation_source="LIVE",
                    source_signature=signature,
                    computed_at=computed_at,
                    inference_run_id=str(run_id),
                    model_version=str(version),
                    forecast_method=str(method),
                )
            )

    backtest_signature = _digest(
        {
            "source": "BACKTEST",
            "rows": backtest_raw.to_dict(orient="records"),
            "start": backtest_raw["target_date"].min(),
            "end": backtest_raw["target_date"].max(),
            "actual_sum": float(backtest_raw["actual"].sum()),
            "active_model": active["model_version"],
        }
    )
    model_frame = backtest_raw.rename(columns={"model_forecast": "predicted"})
    rows.extend(
        _metric_rows(
            model_frame,
            evaluation_source="BACKTEST",
            source_signature=backtest_signature + "_model",
            computed_at=computed_at,
            inference_run_id="BACKTEST_FINAL",
            model_version=active["model_version"],
            forecast_method=active["model_code"],
        )
    )
    baseline_frame = backtest_raw.rename(columns={"baseline_forecast": "predicted"})
    rows.extend(
        _metric_rows(
            baseline_frame,
            evaluation_source="BACKTEST",
            source_signature=backtest_signature + "_baseline",
            computed_at=computed_at,
            inference_run_id="BACKTEST_FINAL",
            model_version=BASELINE_VERSION,
            forecast_method=BASELINE_CODE,
        )
    )

    with connect(database_file) as connection:
        connection.executemany(
            """
            INSERT INTO forecast_monitoring_metrics(
                metric_id, source_signature, evaluation_source, computed_at,
                inference_run_id, model_version, forecast_method,
                period_start, period_end, metric_scope, horizon,
                observations, mae, mean_signed_error, mean_actual
            ) VALUES (
                :metric_id, :source_signature, :evaluation_source, :computed_at,
                :inference_run_id, :model_version, :forecast_method,
                :period_start, :period_end, :metric_scope, :horizon,
                :observations, :mae, :mean_signed_error, :mean_actual
            )
            ON CONFLICT(metric_id) DO UPDATE SET
                computed_at = excluded.computed_at,
                observations = excluded.observations,
                mae = excluded.mae,
                mean_signed_error = excluded.mean_signed_error,
                mean_actual = excluded.mean_actual,
                period_start = excluded.period_start,
                period_end = excluded.period_end
            """,
            rows,
        )
        connection.commit()

    live_evaluated = sum(
        int(row["observations"])
        for row in rows
        if row["evaluation_source"] == "LIVE" and row["metric_scope"] == "AGGREGATE"
    )
    summary = {
        "computed_at": computed_at,
        "database": str(database_file),
        "metric_rows_upserted": len(rows),
        "live_forecasts_evaluated": live_evaluated,
        "live_evaluation_available": bool(live_evaluated),
        "backtest_observations": int(len(backtest_raw)),
        "signed_error_definition": "predicted_incidents - actual_incidents",
        "data_limitation": (
            "O dataset termina em 31/12/2025; não há realizados para os forecasts "
            "de 01/01/2026 a 07/01/2026. O monitoramento LIVE permanece sem métricas "
            "até que observações reais sejam disponibilizadas."
        ),
    }
    if write_evidence and database is None:
        evidence = root / "evidence"
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "28_monitoring_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        pd.DataFrame(rows).to_csv(evidence / "29_monitoring_metrics.csv", index=False)
    return summary
