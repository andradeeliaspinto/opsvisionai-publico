from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error

FEATURE_NAMES = [
    "lag_1",
    "lag_7",
    "lag_14",
    "lag_28",
    "rolling_mean_7",
    "rolling_mean_14",
    "rolling_mean_28",
    "weekday_sin",
    "weekday_cos",
    "is_weekend",
    "month",
]


def build_features(history: list[float] | np.ndarray, date: pd.Timestamp) -> list[float]:
    values = np.asarray(history, dtype=float)
    if len(values) < 28:
        raise ValueError("São necessários pelo menos 28 dias de histórico para as features.")
    weekday = date.dayofweek
    return [
        values[-1],
        values[-7],
        values[-14],
        values[-28],
        values[-7:].mean(),
        values[-14:].mean(),
        values[-28:].mean(),
        np.sin(2 * np.pi * weekday / 7),
        np.cos(2 * np.pi * weekday / 7),
        int(weekday >= 5),
        date.month,
    ]


def training_arrays(series: pd.Series, end_index: int) -> tuple[np.ndarray, np.ndarray]:
    features, targets = [], []
    for index in range(28, end_index):
        features.append(
            build_features(series.iloc[index - 28 : index].tolist(), series.index[index])
        )
        targets.append(float(series.iloc[index]))
    return np.asarray(features), np.asarray(targets)


def build_feature_frame(series: pd.Series) -> pd.DataFrame:
    """Materializa as features conhecidas antes de cada data e o alvo observado."""
    rows = []
    for index in range(28, len(series)):
        row = {"date": series.index[index]}
        row.update(
            dict(
                zip(
                    FEATURE_NAMES,
                    build_features(series.iloc[index - 28 : index].tolist(), series.index[index]),
                )
            )
        )
        row["incident_count"] = float(series.iloc[index])
        rows.append(row)
    return pd.DataFrame(rows)


def rolling_evaluation(
    model,
    series: pd.Series,
    first_origin: int,
    last_origin: int,
    horizon: int = 7,
) -> pd.DataFrame:
    rows = []
    for origin_index in range(first_origin, last_origin + 1):
        origin_date = series.index[origin_index]
        history = series.iloc[origin_index - 27 : origin_index + 1].astype(float).tolist()
        for step in range(1, horizon + 1):
            target_date = origin_date + pd.Timedelta(days=step)
            model_value = max(
                0.0,
                float(
                    model.predict(np.asarray(build_features(history, target_date)).reshape(1, -1))[
                        0
                    ]
                ),
            )
            history.append(model_value)
            rows.append(
                {
                    "origin_date": origin_date,
                    "target_date": target_date,
                    "horizon": step,
                    "actual": float(series.loc[target_date]),
                    "model_forecast": model_value,
                    "baseline_forecast": float(series.loc[target_date - pd.Timedelta(days=7)]),
                }
            )
    return pd.DataFrame(rows)


def candidates(random_state: int) -> dict:
    return {
        "Ridge": Ridge(alpha=100.0),
        "Random Forest": RandomForestRegressor(
            n_estimators=100,
            max_depth=8,
            min_samples_leaf=2,
            max_features=0.8,
            random_state=random_state,
            n_jobs=-1,
        ),
        "Gradient Boosting": GradientBoostingRegressor(
            n_estimators=100,
            max_depth=2,
            learning_rate=0.05,
            loss="huber",
            random_state=random_state,
        ),
    }


def run_modeling(config_path: str | Path = "config/project.yaml") -> dict:
    config_path = Path(config_path)
    root = config_path.parent.parent
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    processed = root / "data/processed"
    evidence = root / "evidence"
    models_dir = root / "models"
    evidence.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)

    daily = pd.read_csv(processed / "incident_count_daily.csv", parse_dates=["date"])
    series = daily.set_index("date")["incident_count"].astype(float)
    total_days = len(series)
    development_end = int(total_days * config["validation"]["development_fraction"])
    internal_training_end = int(total_days * config["validation"]["internal_training_fraction"])
    horizon = int(config["validation"]["forecast_horizon_days"])
    random_state = int(config["project"]["random_state"])

    validation_rows = []
    model_set = candidates(random_state)
    x_train, y_train = training_arrays(series, internal_training_end)
    for name, model in model_set.items():
        model.fit(x_train, y_train)
        validation = rolling_evaluation(
            model,
            series,
            first_origin=internal_training_end - 1,
            last_origin=development_end - horizon - 1,
            horizon=horizon,
        )
        validation_rows.append(
            {
                "candidate": name,
                "validation_mae": mean_absolute_error(
                    validation["actual"], validation["model_forecast"]
                ),
                "validation_baseline_mae": mean_absolute_error(
                    validation["actual"], validation["baseline_forecast"]
                ),
            }
        )
    validation_metrics = pd.DataFrame(validation_rows).sort_values("validation_mae")
    selected_name = str(validation_metrics.iloc[0]["candidate"])
    selected_model = model_set[selected_name]

    x_development, y_development = training_arrays(series, development_end)
    selected_model.fit(x_development, y_development)
    test_predictions = rolling_evaluation(
        selected_model,
        series,
        first_origin=development_end - 1,
        last_origin=total_days - horizon - 1,
        horizon=horizon,
    )
    model_mae = mean_absolute_error(test_predictions["actual"], test_predictions["model_forecast"])
    baseline_mae = mean_absolute_error(
        test_predictions["actual"], test_predictions["baseline_forecast"]
    )

    horizon_metrics = []
    for step, group in test_predictions.groupby("horizon"):
        horizon_metrics.append(
            {
                "horizon": int(step),
                "model_mae": mean_absolute_error(group["actual"], group["model_forecast"]),
                "baseline_mae": mean_absolute_error(group["actual"], group["baseline_forecast"]),
            }
        )
    horizon_metrics = pd.DataFrame(horizon_metrics)
    horizons_model_wins = int(
        (horizon_metrics["model_mae"] < horizon_metrics["baseline_mae"]).sum()
    )

    x_all, y_all = training_arrays(series, total_days)
    selected_model.fit(x_all, y_all)
    model_slug = selected_name.lower().replace(" ", "_")
    recommended_method = (
        "baseline sazonal de 7 dias" if baseline_mae <= model_mae else selected_name
    )
    recommended_method_code = "seasonal_naive_lag_7" if baseline_mae <= model_mae else model_slug
    data_cutoff = series.index[-1].date().isoformat()
    model_version = f"{model_slug}_v1_{data_cutoff.replace('-', '')}"
    versioned_artifact = models_dir / f"{model_version}.joblib"
    feature_frame = build_feature_frame(series)

    validation_metrics.to_csv(evidence / "02_validation_candidates.csv", index=False)
    test_predictions.to_csv(
        evidence / "03_test_predictions.csv", index=False, date_format="%Y-%m-%d"
    )
    horizon_metrics.to_csv(evidence / "04_metrics_by_horizon.csv", index=False)
    feature_frame.to_csv(processed / "model_features.csv", index=False, date_format="%Y-%m-%d")
    joblib.dump(selected_model, versioned_artifact)
    joblib.dump(selected_model, models_dir / "selected_model.joblib")

    summary = {
        "series_start": series.index.min().date().isoformat(),
        "series_end": series.index.max().date().isoformat(),
        "total_days": total_days,
        "internal_training_end_date": series.index[internal_training_end - 1].date().isoformat(),
        "validation_start_date": series.index[internal_training_end].date().isoformat(),
        "validation_end_date": series.index[development_end - 1].date().isoformat(),
        "validation_rolling_origins": int(development_end - horizon - internal_training_end + 1),
        "candidate_count": int(len(validation_metrics)),
        "selected_candidate_validation_mae": round(
            float(validation_metrics.iloc[0]["validation_mae"]), 4
        ),
        "validation_baseline_mae": round(
            float(validation_metrics.iloc[0]["validation_baseline_mae"]), 4
        ),
        "development_end_date": series.index[development_end - 1].date().isoformat(),
        "test_start_date": series.index[development_end].date().isoformat(),
        "test_end_date": series.index[-1].date().isoformat(),
        "test_rolling_origins": int(test_predictions["origin_date"].nunique()),
        "test_predictions": int(len(test_predictions)),
        "selected_model": selected_name,
        "selected_model_code": model_slug,
        "model_version": model_version,
        "model_artifact": versioned_artifact.relative_to(root).as_posix(),
        "feature_count": len(FEATURE_NAMES),
        "feature_names": FEATURE_NAMES,
        "training_data_cutoff": data_cutoff,
        "model_test_mae": round(float(model_mae), 4),
        "baseline_test_mae": round(float(baseline_mae), 4),
        "relative_mae_reduction": round(float((baseline_mae - model_mae) / baseline_mae), 6),
        "horizons_model_wins": horizons_model_wins,
        "model_wins_all_horizons": bool(horizons_model_wins == horizon),
        "recommended_method": recommended_method,
        "recommended_method_code": recommended_method_code,
        "predictive_hypothesis_confirmed": bool(model_mae < baseline_mae),
        "interpretation": (
            "O modelo superou o baseline no teste cronológico."
            if model_mae < baseline_mae
            else "O modelo não superou o baseline no teste cronológico; o MVP recomenda o baseline e registra a hipótese preditiva como não confirmada."
        ),
    }
    (evidence / "05_model_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    registry = {
        "registry_schema_version": 1,
        "active_model": {
            "model_version": model_version,
            "model_name": selected_name,
            "model_code": model_slug,
            "artifact_path": versioned_artifact.relative_to(root).as_posix(),
            "data_cutoff_date": data_cutoff,
            "training_series_start": series.index.min().date().isoformat(),
            "training_series_end": data_cutoff,
            "feature_names": FEATURE_NAMES,
            "test_start_date": summary["test_start_date"],
            "test_end_date": summary["test_end_date"],
            "model_test_mae": summary["model_test_mae"],
            "baseline_test_mae": summary["baseline_test_mae"],
            "relative_mae_reduction": summary["relative_mae_reduction"],
            "horizons_model_wins": summary["horizons_model_wins"],
            "recommended_method_code": recommended_method_code,
        },
    }
    (models_dir / "model_registry.json").write_text(
        json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(run_modeling(), ensure_ascii=False, indent=2))
