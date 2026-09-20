from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent
REQUIRED_TABLES = {
    "daily_actuals",
    "forecast_predictions",
    "backtest_predictions",
    "model_metrics",
    "horizon_metrics",
    "validation_candidates",
    "category_summary",
    "priority_summary",
    "assignment_group_summary",
    "weekday_summary",
    "hourly_summary",
    "metadata",
    "schema_migrations",
    "pipeline_job_runs",
    "registered_models",
    "model_promotion_history",
    "forecast_monitoring_metrics",
    "alert_threshold_snapshots",
    "operational_alerts",
    "integration_delivery_log",
}
REQUIRED_VIEWS = {
    "v_latest_inference_run",
    "v_recommended_forecast",
    "v_forecast_vs_actual",
    "v_backtest_comparison",
}
REQUIRED_PREDICTION_FIELDS = {
    "inference_run_id",
    "prediction_generated_at",
    "origin_date",
    "forecast_date",
    "horizon",
    "predicted_incidents",
    "forecast_method",
    "model_version",
    "data_cutoff_date",
    "is_recommended",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class HealthCheck:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def add(self, name: str, passed: bool, detail: Any) -> None:
        self.checks.append({"name": name, "passed": bool(passed), "detail": detail})

    @property
    def passed(self) -> bool:
        return all(item["passed"] for item in self.checks)


def validate() -> dict[str, Any]:
    health = HealthCheck()
    config = yaml.safe_load((ROOT / "config/project.yaml").read_text(encoding="utf-8"))

    raw_path = ROOT / config["source"]["raw_file"]
    observed_hash = file_sha256(raw_path) if raw_path.exists() else None
    health.add(
        "dataset_sha256",
        observed_hash == config["source"]["expected_sha256"],
        {"observed": observed_hash, "expected": config["source"]["expected_sha256"]},
    )

    raw = pd.read_excel(
        raw_path,
        sheet_name=config["source"]["sheet_name"],
        usecols=["Número", "Aberto", "Categoria"],
        engine="openpyxl",
    )
    workbook_columns = len(
        pd.read_excel(
            raw_path,
            sheet_name=config["source"]["sheet_name"],
            nrows=0,
            engine="openpyxl",
        ).columns
    )
    opened = pd.to_datetime(raw["Aberto"], errors="coerce")
    ids = raw["Número"].astype("string").str.strip()
    selected = raw[(opened >= "2025-01-01") & (opened < "2026-01-01")].copy()
    selected_opened = opened.loc[selected.index]
    category_missing_share = float(
        (
            selected["Categoria"].isna() | selected["Categoria"].astype("string").str.strip().eq("")
        ).mean()
    )
    source_facts = {
        "rows": int(len(raw)),
        "columns_in_workbook": int(workbook_columns),
        "distinct_ids": int(ids.nunique(dropna=True)),
        "invalid_ids": int((ids.isna() | ids.eq("")).sum()),
        "invalid_dates": int(opened.isna().sum()),
        "duplicate_ids": int(ids.duplicated().sum()),
        "date_min": opened.min().isoformat(),
        "date_max": opened.max().isoformat(),
        "rows_2025": int(len(selected)),
        "rows_before_2025": int((opened < "2025-01-01").sum()),
        "days_2025": int(selected_opened.dt.floor("D").nunique()),
        "category_missing_share_2025": round(category_missing_share, 8),
    }
    health.add(
        "dataset_facts",
        source_facts
        == {
            "rows": 122543,
            "columns_in_workbook": 19,
            "distinct_ids": 122543,
            "invalid_ids": 0,
            "invalid_dates": 0,
            "duplicate_ids": 0,
            "date_min": "2023-01-02T20:19:58",
            "date_max": "2025-12-31T23:45:18",
            "rows_2025": 121811,
            "rows_before_2025": 732,
            "days_2025": 365,
            "category_missing_share_2025": 0.63804583,
        },
        source_facts,
    )

    quality = json.loads((ROOT / "evidence/01_quality_report.json").read_text(encoding="utf-8"))
    health.add(
        "quality_report_matches_source",
        quality["source_rows"] == source_facts["rows"]
        and quality["analysis_incidents"] == source_facts["rows_2025"]
        and quality["valid_source_rows_excluded_from_analysis_window"]
        == source_facts["rows_before_2025"]
        and quality["category_missing_share"]
        == round(source_facts["category_missing_share_2025"], 4),
        {
            "source_rows": quality["source_rows"],
            "analysis_incidents": quality["analysis_incidents"],
            "excluded": quality["valid_source_rows_excluded_from_analysis_window"],
            "category_missing_share": quality["category_missing_share"],
        },
    )

    daily = pd.read_csv(ROOT / "data/processed/incident_count_daily.csv", parse_dates=["date"])
    health.add(
        "daily_series",
        len(daily) == 365
        and int(daily["incident_count"].sum()) == 121811
        and int((daily["incident_count"] == 0).sum()) == 0
        and (daily["date"].diff().dropna() == pd.Timedelta(days=1)).all(),
        {
            "rows": int(len(daily)),
            "sum": int(daily["incident_count"].sum()),
            "zero_days": int((daily["incident_count"] == 0).sum()),
            "minimum": int(daily["incident_count"].min()),
            "maximum": int(daily["incident_count"].max()),
        },
    )

    model = json.loads((ROOT / "evidence/05_model_summary.json").read_text(encoding="utf-8"))
    registry = json.loads((ROOT / "models/model_registry.json").read_text(encoding="utf-8"))
    active = registry["active_model"]
    health.add(
        "model_registry",
        active["model_version"] == model["model_version"]
        and (ROOT / active["artifact_path"]).is_file()
        and active["data_cutoff_date"] == "2025-12-31",
        {
            "model_version": active["model_version"],
            "artifact_path": active["artifact_path"],
            "data_cutoff_date": active["data_cutoff_date"],
        },
    )

    features = pd.read_csv(ROOT / "data/processed/model_features.csv")
    feature_names = list(active["feature_names"])
    health.add(
        "feature_contract_without_target_leakage",
        len(features) == 337
        and len(feature_names) == 11
        and "incident_count" not in feature_names
        and set(feature_names).issubset(features.columns),
        {"rows": int(len(features)), "features": feature_names},
    )

    backtest = pd.read_csv(
        ROOT / "evidence/03_test_predictions.csv",
        parse_dates=["origin_date", "target_date"],
    )
    daily_indexed = daily.set_index("date")["incident_count"]
    baseline_expected = backtest["target_date"].map(
        lambda target: float(daily_indexed.loc[target - pd.Timedelta(days=7)])
    )
    alignment_ok = (
        len(backtest) == 469
        and backtest["origin_date"].nunique() == 67
        and sorted(backtest["horizon"].unique().tolist()) == list(range(1, 8))
        and baseline_expected.equals(backtest["baseline_forecast"])
        and (
            backtest["target_date"]
            == backtest["origin_date"] + pd.to_timedelta(backtest["horizon"], unit="D")
        ).all()
    )
    health.add(
        "temporal_alignment_and_baseline",
        alignment_ok,
        {
            "origins": int(backtest["origin_date"].nunique()),
            "predictions": int(len(backtest)),
            "horizons": sorted(backtest["horizon"].unique().tolist()),
        },
    )

    model_mae = float((backtest["actual"] - backtest["model_forecast"]).abs().mean())
    baseline_mae = float((backtest["actual"] - backtest["baseline_forecast"]).abs().mean())
    relative_reduction = float((baseline_mae - model_mae) / baseline_mae)
    horizon_calculated = backtest.groupby("horizon").apply(
        lambda group: pd.Series(
            {
                "model_mae": (group["actual"] - group["model_forecast"]).abs().mean(),
                "baseline_mae": (group["actual"] - group["baseline_forecast"]).abs().mean(),
            }
        ),
        include_groups=False,
    )
    horizon_published = pd.read_csv(ROOT / "evidence/04_metrics_by_horizon.csv").set_index(
        "horizon"
    )
    horizon_delta = (horizon_calculated - horizon_published).abs().to_numpy().max()
    health.add(
        "metrics_recomputed",
        round(model_mae, 4) == model["model_test_mae"]
        and round(baseline_mae, 4) == model["baseline_test_mae"]
        and abs(relative_reduction - model["relative_mae_reduction"]) < 1e-6
        and horizon_delta < 1e-9,
        {
            "model_mae": round(model_mae, 6),
            "baseline_mae": round(baseline_mae, 6),
            "relative_reduction": round(relative_reduction, 8),
            "horizons_model_wins": int(
                (horizon_calculated["model_mae"] < horizon_calculated["baseline_mae"]).sum()
            ),
        },
    )

    predictions = pd.read_csv(ROOT / "data/processed/forecast_predictions.csv")
    latest_run_id = predictions.sort_values(["prediction_generated_at", "inference_run_id"]).iloc[
        -1
    ]["inference_run_id"]
    latest = predictions[predictions["inference_run_id"] == latest_run_id]
    prediction_key_duplicates = int(
        predictions.duplicated(["inference_run_id", "forecast_method", "horizon"]).sum()
    )
    health.add(
        "prediction_storage",
        REQUIRED_PREDICTION_FIELDS.issubset(predictions.columns)
        and predictions["inference_run_id"].nunique() >= 2
        and len(latest) == 14
        and sorted(latest["horizon"].unique().tolist()) == list(range(1, 8))
        and latest["forecast_method"].nunique() == 2
        and int(latest["is_recommended"].sum()) == 7
        and prediction_key_duplicates == 0,
        {
            "stored_runs": int(predictions["inference_run_id"].nunique()),
            "stored_rows": int(len(predictions)),
            "latest_run_id": latest_run_id,
            "latest_rows": int(len(latest)),
            "duplicate_keys": prediction_key_duplicates,
        },
    )

    database = ROOT / config["serving"]["database_file"]
    uri = f"{database.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        views = {
            row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='view'")
        }
        indexes = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
        latest_rows = connection.execute("SELECT COUNT(*) FROM v_latest_inference_run").fetchone()[
            0
        ]
        recommended_rows = connection.execute(
            "SELECT COUNT(*) FROM v_recommended_forecast"
        ).fetchone()[0]
        database_latest_run = connection.execute(
            "SELECT inference_run_id FROM v_latest_inference_run LIMIT 1"
        ).fetchone()[0]
    health.add(
        "sqlite_serving_contract",
        integrity == "ok"
        and tables == REQUIRED_TABLES
        and views == REQUIRED_VIEWS
        and "ux_forecast_run_method_horizon" in indexes
        and latest_rows == 14
        and recommended_rows == 7
        and database_latest_run == latest_run_id,
        {
            "integrity": integrity,
            "tables": len(tables),
            "views": len(views),
            "indexes": sorted(indexes),
            "latest_rows": latest_rows,
            "recommended_rows": recommended_rows,
            "latest_run_id": database_latest_run,
        },
    )

    repository_source = (ROOT / "src/serving_repository.py").read_text(encoding="utf-8")
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    health.add(
        "serving_repository_read_only",
        "mode=ro" in repository_source
        and "ServingRepository" in app_source
        and "read_csv" not in app_source
        and "joblib" not in app_source,
        {
            "sqlite_uri_mode": "mode=ro" in repository_source,
            "dashboard_uses_repository": "ServingRepository" in app_source,
            "dashboard_reads_csv": "read_csv" in app_source,
            "dashboard_loads_model": "joblib" in app_source,
        },
    )

    runtime_evidence = ROOT / "evidence/17_dashboard_runtime_validation.json"
    runtime = (
        json.loads(runtime_evidence.read_text(encoding="utf-8"))
        if runtime_evidence.exists()
        else {}
    )
    health.add(
        "dashboard_runtime_evidence",
        runtime.get("status") == "passed"
        and runtime.get("exceptions") == []
        and len(runtime.get("tabs", [])) == 6,
        {
            "status": runtime.get("status"),
            "tabs": runtime.get("tabs", []),
            "exceptions": runtime.get("exceptions"),
        },
    )

    packaged_tests = unittest.defaultTestLoader.discover(str(ROOT / "tests")).countTestCases()
    health.add(
        "automated_test_inventory",
        packaged_tests >= 17,
        {"packaged_test_cases": packaged_tests},
    )

    required_artifacts = [
        ROOT / "models/model_registry.json",
        ROOT / "models/selected_model.joblib",
        ROOT / "evidence/06_daily_series.png",
        ROOT / "evidence/08_model_vs_baseline.png",
        ROOT / "evidence/09_forecast_7_days.png",
        ROOT / "evidence/12_architecture_revised.png",
        database,
    ]
    missing_artifacts = [
        str(path.relative_to(ROOT)) for path in required_artifacts if not path.is_file()
    ]
    health.add("required_artifacts", not missing_artifacts, {"missing": missing_artifacts})

    return {
        "validated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "passed" if health.passed else "failed",
        "project": "OpsVisionAI",
        "checks_passed": sum(item["passed"] for item in health.checks),
        "checks_total": len(health.checks),
        "checks": health.checks,
        "facts": {
            "dataset_rows": source_facts["rows"],
            "analysis_incidents": source_facts["rows_2025"],
            "analysis_days": source_facts["days_2025"],
            "model": model["selected_model"],
            "model_mae": round(model_mae, 4),
            "baseline_mae": round(baseline_mae, 4),
            "relative_mae_reduction": round(relative_reduction, 6),
            "test_origins": int(backtest["origin_date"].nunique()),
            "test_predictions": int(len(backtest)),
            "latest_inference_run_id": latest_run_id,
            "stored_inference_runs": int(predictions["inference_run_id"].nunique()),
            "stored_prediction_rows": int(len(predictions)),
            "sqlite_tables": len(tables),
            "sqlite_views": len(views),
            "packaged_test_cases": packaged_tests,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Executa o health check ponta a ponta do OpsVisionAI."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "evidence/18_project_health_check.json",
    )
    args = parser.parse_args()
    result = validate()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Evidência gravada em: {output}")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
