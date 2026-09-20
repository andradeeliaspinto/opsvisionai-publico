from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from src.database import connect, database_catalog, migrate_database


def _read_csv(path: Path, **kwargs) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Artefato necessário ao serving não encontrado: {path}")
    return pd.read_csv(path, **kwargs)


def publish_serving_store(config_path: str | Path = "config/project.yaml") -> dict:
    """Publica tabelas e views curadas em SQLite para consumo exclusivo do dashboard."""
    config_path = Path(config_path)
    root = config_path.parent.parent
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    processed = root / "data/processed"
    evidence = root / "evidence"
    database_path = root / config["serving"]["database_file"]
    database_path.parent.mkdir(parents=True, exist_ok=True)
    migrate_database(config_path)

    actuals = _read_csv(processed / "incident_count_daily.csv")
    actuals = actuals.rename(columns={"date": "actual_date", "incident_count": "actual_incidents"})
    forecasts = _read_csv(root / config["inference"]["predictions_file"])
    backtest = _read_csv(evidence / "03_test_predictions.csv")
    horizon_metrics = _read_csv(evidence / "04_metrics_by_horizon.csv")
    validation_candidates = _read_csv(evidence / "02_validation_candidates.csv")
    model_summary = json.loads((evidence / "05_model_summary.json").read_text(encoding="utf-8"))
    inference_summary = json.loads(
        (evidence / "06_inference_summary.json").read_text(encoding="utf-8")
    )
    source_metadata = json.loads(
        (root / "data/raw/source_metadata.json").read_text(encoding="utf-8")
    )
    quality_report = json.loads((evidence / "01_quality_report.json").read_text(encoding="utf-8"))

    model_metrics = pd.DataFrame(
        [
            {
                "selected_model": model_summary["selected_model"],
                "model_version": model_summary["model_version"],
                "model_test_mae": model_summary["model_test_mae"],
                "baseline_test_mae": model_summary["baseline_test_mae"],
                "relative_mae_reduction": model_summary["relative_mae_reduction"],
                "horizons_model_wins": model_summary["horizons_model_wins"],
                "recommended_method": model_summary["recommended_method"],
                "recommended_method_code": model_summary["recommended_method_code"],
                "predictive_hypothesis_confirmed": model_summary["predictive_hypothesis_confirmed"],
                "test_start_date": model_summary["test_start_date"],
                "test_end_date": model_summary["test_end_date"],
                "test_rolling_origins": model_summary["test_rolling_origins"],
                "test_predictions": model_summary["test_predictions"],
            }
        ]
    )
    metadata = pd.DataFrame(
        [
            ("dataset", source_metadata["dataset"]),
            ("publisher", source_metadata["publisher"]),
            ("provenance", source_metadata["provenance"]),
            ("source_file", source_metadata["local_file"]),
            ("source_sheet", source_metadata["sheet_name"]),
            ("source_sha256", source_metadata["sha256"]),
            ("license", source_metadata["license"]),
            ("source_rows", str(quality_report["source_rows"])),
            ("analysis_incidents", str(quality_report["analysis_incidents"])),
            (
                "weekend_or_outside_08_18_share",
                str(quality_report["weekend_or_outside_08_18_share"]),
            ),
            ("category_missing_share", str(quality_report["category_missing_share"])),
            ("series_start", model_summary["series_start"]),
            ("series_end", model_summary["series_end"]),
            ("prediction_generated_at", inference_summary["prediction_generated_at"]),
            ("inference_run_id", inference_summary["inference_run_id"]),
            ("stored_inference_runs", str(inference_summary["stored_inference_runs"])),
            ("data_cutoff_date", inference_summary["data_cutoff_date"]),
        ],
        columns=["key", "value"],
    )

    tables = {
        "daily_actuals": actuals,
        "forecast_predictions": forecasts,
        "backtest_predictions": backtest,
        "model_metrics": model_metrics,
        "horizon_metrics": horizon_metrics,
        "validation_candidates": validation_candidates,
        "category_summary": _read_csv(processed / "category_summary.csv"),
        "priority_summary": _read_csv(processed / "priority_summary.csv"),
        "assignment_group_summary": _read_csv(processed / "assignment_group_summary.csv"),
        "weekday_summary": _read_csv(processed / "weekday_summary.csv"),
        "hourly_summary": _read_csv(processed / "hourly_summary.csv"),
        "metadata": metadata,
    }

    with connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        for table_name, frame in tables.items():
            definitions = ", ".join(
                f'"{name}" {"REAL" if pd.api.types.is_numeric_dtype(dtype) else "TEXT"}'
                for name, dtype in frame.dtypes.items()
            )
            connection.execute(f'CREATE TABLE IF NOT EXISTS "{table_name}" ({definitions})')
            columns = ", ".join(f'"{name}"' for name in frame.columns)
            placeholders = ", ".join("?" for _ in frame.columns)
            records = list(
                frame.astype(object).where(frame.notna(), None).itertuples(index=False, name=None)
            )
            if table_name == "forecast_predictions":
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_forecast_run_method_horizon ON forecast_predictions(inference_run_id, forecast_method, horizon)"
                )
                verb = "INSERT OR IGNORE"
            elif table_name == "daily_actuals":
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_actual_date ON daily_actuals(actual_date)"
                )
                verb = "INSERT OR REPLACE"
            else:
                connection.execute(f'DELETE FROM "{table_name}"')
                verb = "INSERT"
            connection.executemany(
                f'{verb} INTO "{table_name}" ({columns}) VALUES ({placeholders})', records
            )
        sql = """
            CREATE INDEX IF NOT EXISTS idx_actual_date ON daily_actuals(actual_date);
            CREATE INDEX IF NOT EXISTS idx_forecast_date ON forecast_predictions(forecast_date);
            CREATE INDEX IF NOT EXISTS idx_forecast_generated ON forecast_predictions(prediction_generated_at);
            CREATE INDEX IF NOT EXISTS idx_forecast_run ON forecast_predictions(inference_run_id);
            CREATE UNIQUE INDEX IF NOT EXISTS ux_forecast_run_method_horizon
            ON forecast_predictions(inference_run_id, forecast_method, horizon);

            DROP VIEW IF EXISTS v_latest_inference_run;
            CREATE VIEW v_latest_inference_run AS
            SELECT *
            FROM forecast_predictions
            WHERE inference_run_id = (
                SELECT inference_run_id
                FROM forecast_predictions
                ORDER BY prediction_generated_at DESC, inference_run_id DESC
                LIMIT 1
            );

            DROP VIEW IF EXISTS v_recommended_forecast;
            CREATE VIEW v_recommended_forecast AS
            SELECT inference_run_id, prediction_generated_at, origin_date, forecast_date, horizon,
                   predicted_incidents, forecast_method, model_version, data_cutoff_date
            FROM v_latest_inference_run
            WHERE is_recommended = 1
            ORDER BY horizon;

            DROP VIEW IF EXISTS v_forecast_vs_actual;
            CREATE VIEW v_forecast_vs_actual AS
            SELECT p.inference_run_id, p.prediction_generated_at, p.origin_date,
                   p.forecast_date, p.horizon,
                   p.predicted_incidents, p.forecast_method, p.model_version,
                   p.data_cutoff_date,
                   a.actual_incidents,
                   p.predicted_incidents - a.actual_incidents AS signed_error,
                   CASE WHEN a.actual_incidents IS NULL THEN NULL
                        ELSE ABS(a.actual_incidents - p.predicted_incidents) END AS absolute_error
            FROM forecast_predictions p
            LEFT JOIN daily_actuals a ON a.actual_date = p.forecast_date;

            DROP VIEW IF EXISTS v_backtest_comparison;
            CREATE VIEW v_backtest_comparison AS
            SELECT origin_date, target_date, horizon, actual,
                   model_forecast, baseline_forecast,
                   ABS(actual - model_forecast) AS model_absolute_error,
                   ABS(actual - baseline_forecast) AS baseline_absolute_error
            FROM backtest_predictions;
            """
        for statement in sql.split(";"):
            if statement.strip():
                connection.execute(statement)
        connection.commit()

    catalog = database_catalog(database_path)
    manifest = {
        "database": database_path.relative_to(root).as_posix(),
        "tables": catalog["tables"],
        "views": [
            "v_latest_inference_run",
            "v_recommended_forecast",
            "v_forecast_vs_actual",
            "v_backtest_comparison",
        ],
        "serving_contract": "O dashboard consulta apenas views/tabelas curadas deste SQLite; não carrega o modelo.",
    }
    (evidence / "07_serving_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    print(json.dumps(publish_serving_store(), ensure_ascii=False, indent=2))
