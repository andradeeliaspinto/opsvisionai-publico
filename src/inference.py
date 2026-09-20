from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import joblib
import numpy as np
import pandas as pd
import yaml

from src.file_io import atomic_output
from src.model_registry import get_active_model
from src.modeling import build_features

BASELINE_CODE = "seasonal_naive_lag_7"
BASELINE_VERSION = "baseline_lag7_v1"


def run_inference(config_path: str | Path = "config/project.yaml") -> dict:
    """Carrega o modelo ativo, gera D+1 a D+7 e preserva o histórico de execuções."""
    config_path = Path(config_path).resolve()
    root = config_path.parent.parent
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    processed = root / "data/processed"
    evidence = root / "evidence"
    active = get_active_model(config_path)
    active["model_name"] = active["algorithm"]
    active["recommended_method_code"] = (
        active["model_code"] if active["evaluation_mae"] < active["baseline_mae"] else BASELINE_CODE
    )
    model = joblib.load(root / active["artifact_path"])

    daily = pd.read_csv(processed / "incident_count_daily.csv", parse_dates=["date"])
    series = daily.set_index("date")["incident_count"].astype(float)
    horizon = int(config["validation"]["forecast_horizon_days"])
    cutoff = series.index[-1]
    if pd.Timestamp(active["training_end_date"]) > cutoff:
        raise ValueError("O modelo foi treinado além do corte de inferência.")
    run_started_at = datetime.now(timezone.utc).replace(microsecond=0)
    generated_at = run_started_at.isoformat()
    inference_run_id = f"run_{run_started_at.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    recommended_code = active["recommended_method_code"]

    history = series.tolist()
    rows: list[dict] = []
    wide_rows: list[dict] = []
    for step in range(1, horizon + 1):
        forecast_date = cutoff + pd.Timedelta(days=step)
        model_value = max(
            0.0,
            float(
                model.predict(np.asarray(build_features(history, forecast_date)).reshape(1, -1))[0]
            ),
        )
        history.append(model_value)
        baseline_value = float(series.loc[forecast_date - pd.Timedelta(days=7)])

        for method, version, value in [
            (BASELINE_CODE, BASELINE_VERSION, baseline_value),
            (active["model_code"], active["model_version"], model_value),
        ]:
            rows.append(
                {
                    "inference_run_id": inference_run_id,
                    "prediction_generated_at": generated_at,
                    "origin_date": cutoff.date().isoformat(),
                    "forecast_date": forecast_date.date().isoformat(),
                    "horizon": step,
                    "predicted_incidents": round(value, 2),
                    "forecast_method": method,
                    "model_version": version,
                    "data_cutoff_date": cutoff.date().isoformat(),
                    "is_recommended": method == recommended_code,
                }
            )
        wide_rows.append(
            {
                "date": forecast_date,
                "horizon": step,
                "baseline_forecast": round(baseline_value, 2),
                "model_forecast": round(model_value, 2),
                "recommended_method": (
                    "baseline sazonal de 7 dias"
                    if recommended_code == BASELINE_CODE
                    else active["model_name"]
                ),
                "recommended_forecast": round(
                    baseline_value if recommended_code == BASELINE_CODE else model_value, 2
                ),
            }
        )

    current = pd.DataFrame(rows)
    predictions_path = root / config["inference"]["predictions_file"]
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    if predictions_path.exists():
        previous = pd.read_csv(predictions_path)
        if "inference_run_id" not in previous.columns:
            legacy_timestamp = previous["prediction_generated_at"].astype("string")
            previous["inference_run_id"] = legacy_timestamp.map(
                lambda value: "legacy_" + re.sub(r"[^0-9A-Za-z]+", "", str(value))
            )
        current = pd.concat([previous, current], ignore_index=True)
        current = current.drop_duplicates(
            subset=["inference_run_id", "forecast_method", "horizon"],
            keep="last",
        )
    current = current.sort_values(
        ["prediction_generated_at", "inference_run_id", "forecast_method", "horizon"]
    ).reset_index(drop=True)
    with atomic_output(predictions_path) as temporary:
        current.to_csv(temporary, index=False)

    wide = pd.DataFrame(wide_rows)
    current_path = root / config["inference"]["current_forecast_file"]
    with atomic_output(current_path) as temporary:
        wide.to_csv(temporary, index=False, date_format="%Y-%m-%d")

    summary = {
        "inference_run_id": inference_run_id,
        "prediction_generated_at": generated_at,
        "data_cutoff_date": cutoff.date().isoformat(),
        "forecast_start_date": wide["date"].min().date().isoformat(),
        "forecast_end_date": wide["date"].max().date().isoformat(),
        "horizon_days": horizon,
        "rows_persisted_current_run": len(rows),
        "rows_persisted_total": int(len(current)),
        "stored_inference_runs": int(current["inference_run_id"].nunique()),
        "model_version": active["model_version"],
        "recommended_method_code": recommended_code,
        "prediction_store": predictions_path.relative_to(root).as_posix(),
    }
    with atomic_output(evidence / "06_inference_summary.json") as temporary:
        temporary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run_inference(), ensure_ascii=False, indent=2))
