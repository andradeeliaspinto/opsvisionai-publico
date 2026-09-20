from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import joblib
import pandas as pd
import yaml
from sklearn.base import clone
from sklearn.metrics import mean_absolute_error

from src.configuration import database_path as configured_database_path
from src.configuration import model_policy, project_root
from src.database import connect, migrate_database
from src.model_registry import (
    export_active_registry_json,
    finalize_candidate_status,
    get_active_model,
    register_candidate,
)
from src.modeling import FEATURE_NAMES, candidates, rolling_evaluation, training_arrays


@dataclass(frozen=True)
class PromotionDecision:
    eligible: bool
    decision: str
    reasons: list[str]
    relative_improvement_over_champion: float
    relative_improvement_over_baseline: float
    absolute_mean_bias_ratio: float


def decide_promotion(
    *,
    candidate_mae: float,
    champion_mae: float,
    baseline_mae: float,
    candidate_mean_bias: float,
    candidate_mean_actual: float,
    horizons_won_against_baseline: int,
    new_actuals_count: int,
    days_since_last_training: int,
    temporal_evaluation_valid: bool,
    policy: dict[str, Any],
) -> PromotionDecision:
    promotion = policy["promotion"]
    retraining = policy["retraining"]
    improvement_champion = (
        (champion_mae - candidate_mae) / champion_mae if champion_mae else float("-inf")
    )
    improvement_baseline = (
        (baseline_mae - candidate_mae) / baseline_mae if baseline_mae else float("-inf")
    )
    bias_ratio = (
        abs(candidate_mean_bias) / candidate_mean_actual if candidate_mean_actual else float("inf")
    )
    reasons: list[str] = []
    if (
        not all(
            math.isfinite(v)
            for v in [
                candidate_mae,
                champion_mae,
                baseline_mae,
                candidate_mean_bias,
                candidate_mean_actual,
            ]
        )
        or min(candidate_mae, champion_mae, baseline_mae) < 0
    ):
        reasons.append("Métricas inválidas ou não finitas.")
    if promotion.get("require_temporal_evaluation", True) and not temporal_evaluation_valid:
        reasons.append("Janela de promoção não é comprovadamente posterior ao treino do Champion.")
    if new_actuals_count < int(retraining["minimum_new_actuals"]):
        reasons.append(
            f"Novos realizados insuficientes: {new_actuals_count} < "
            f"{int(retraining['minimum_new_actuals'])}."
        )
    if days_since_last_training < int(retraining["minimum_days_between_runs"]):
        reasons.append(
            f"Intervalo mínimo de retreino não atendido: {days_since_last_training} < "
            f"{int(retraining['minimum_days_between_runs'])} dias."
        )
    if improvement_champion < float(promotion["minimum_relative_improvement_over_champion"]):
        reasons.append(
            "Challenger não atingiu a melhoria mínima sobre o Champion "
            f"({100 * improvement_champion:.2f}%)."
        )
    if improvement_baseline < float(promotion["minimum_relative_improvement_over_baseline"]):
        reasons.append(
            "Challenger não atingiu a melhoria mínima sobre o baseline "
            f"({100 * improvement_baseline:.2f}%)."
        )
    if bias_ratio > float(promotion["maximum_absolute_mean_bias_ratio"]):
        reasons.append(f"Viés relativo excede o limite ({100 * bias_ratio:.2f}%).")
    if horizons_won_against_baseline < int(promotion["minimum_horizons_won_against_baseline"]):
        reasons.append(
            f"Challenger venceu o baseline em poucos horizontes: {horizons_won_against_baseline}."
        )

    eligible = not reasons
    return PromotionDecision(
        eligible=eligible,
        decision="PROMOTED" if eligible else "REJECTED",
        reasons=reasons or ["Todos os critérios da política foram atendidos."],
        relative_improvement_over_champion=float(improvement_champion),
        relative_improvement_over_baseline=float(improvement_baseline),
        absolute_mean_bias_ratio=float(bias_ratio),
    )


def _evaluate_estimator(
    estimator: Any, series: pd.Series, train_end: int, horizon: int
) -> pd.DataFrame:
    x_train, y_train = training_arrays(series, train_end)
    estimator.fit(x_train, y_train)
    return rolling_evaluation(
        estimator,
        series,
        first_origin=train_end - 1,
        last_origin=len(series) - horizon - 1,
        horizon=horizon,
    )


def run_retraining(
    config_path: str | Path = "config/project.yaml",
    *,
    database: str | Path | None = None,
    write_evidence: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    config_path = Path(config_path).resolve()
    root = project_root(config_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    policy = model_policy(config_path)
    database_file = (
        Path(database) if database is not None else configured_database_path(config_path)
    )
    migrate_database(config_path, database=database_file)
    champion = get_active_model(config_path, database=database_file)

    daily = pd.read_csv(root / "data/processed/incident_count_daily.csv", parse_dates=["date"])
    series = daily.set_index("date")["incident_count"].astype(float)
    horizon = int(policy["retraining"]["forecast_horizon_days"])
    evaluation_days = int(policy["retraining"]["evaluation_window_days"])
    if evaluation_days <= horizon or len(series) <= 28 + evaluation_days:
        raise ValueError("Janela temporal insuficiente para o retreino configurado.")
    train_end = len(series) - evaluation_days
    evaluation_start = series.index[train_end].date().isoformat()
    evaluation_end = series.index[-1].date().isoformat()
    temporal_valid = bool(series.index[train_end - 1] < series.index[train_end])

    champion_artifact = joblib.load(root / champion["artifact_path"])
    if pd.Timestamp(evaluation_start) > pd.Timestamp(champion["training_end_date"]):
        champion_predictions = rolling_evaluation(
            champion_artifact,
            series,
            first_origin=train_end - 1,
            last_origin=len(series) - horizon - 1,
            horizon=horizon,
        )
    else:
        champion_predictions = _evaluate_estimator(
            clone(champion_artifact), series, train_end, horizon
        )
    champion_mae = float(
        mean_absolute_error(champion_predictions["actual"], champion_predictions["model_forecast"])
    )
    baseline_mae = float(
        mean_absolute_error(
            champion_predictions["actual"], champion_predictions["baseline_forecast"]
        )
    )

    development = series.iloc[:train_end]
    internal_end = max(35, int(len(development) * 0.75))
    candidate_results: list[tuple[str, Any, float]] = []
    for name, estimator in candidates(int(config["project"]["random_state"])).items():
        predictions = _evaluate_estimator(estimator, development, internal_end, horizon)
        mae = float(mean_absolute_error(predictions["actual"], predictions["model_forecast"]))
        candidate_results.append((name, estimator, mae))
    selected_name, selected_estimator, _ = min(candidate_results, key=lambda item: item[2])
    candidate_predictions = _evaluate_estimator(selected_estimator, series, train_end, horizon)
    candidate_mae = float(
        mean_absolute_error(
            candidate_predictions["actual"], candidate_predictions["model_forecast"]
        )
    )

    signed_error = candidate_predictions["model_forecast"] - candidate_predictions["actual"]
    mean_bias = float(signed_error.mean())
    mean_actual = float(candidate_predictions["actual"].mean())
    horizon_frame = candidate_predictions.groupby("horizon").apply(
        lambda group: pd.Series(
            {
                "candidate_mae": (group["model_forecast"] - group["actual"]).abs().mean(),
                "baseline_mae": (group["baseline_forecast"] - group["actual"]).abs().mean(),
            }
        ),
        include_groups=False,
    )
    horizons_won = int((horizon_frame["candidate_mae"] < horizon_frame["baseline_mae"]).sum())

    current_time = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    model_code = selected_name.lower().replace(" ", "_")
    candidate_version = (
        f"{model_code}_challenger_{current_time.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:6]}"
    )
    artifact_path = root / "models" / "candidates" / f"{candidate_version}.joblib"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    x_all, y_all = training_arrays(series, len(series))
    selected_estimator.fit(x_all, y_all)
    joblib.dump(selected_estimator, artifact_path)

    champion_training_end = pd.Timestamp(champion["training_end_date"])
    new_actuals = int((series.index > champion_training_end).sum())
    promotion_window_is_new = bool(pd.Timestamp(evaluation_start) > champion_training_end)
    champion_trained_at = datetime.fromisoformat(champion["trained_at"])
    days_since_training = max(0, (current_time - champion_trained_at).days)
    decision = decide_promotion(
        candidate_mae=candidate_mae,
        champion_mae=champion_mae,
        baseline_mae=baseline_mae,
        candidate_mean_bias=mean_bias,
        candidate_mean_actual=mean_actual,
        horizons_won_against_baseline=horizons_won,
        new_actuals_count=new_actuals,
        days_since_last_training=days_since_training,
        temporal_evaluation_valid=temporal_valid and promotion_window_is_new,
        policy=policy,
    )
    reason = " ".join(decision.reasons)

    register_candidate(
        {
            "model_version": candidate_version,
            "algorithm": selected_name,
            "model_code": model_code,
            "trained_at": current_time.isoformat(),
            "training_start_date": series.index.min().date().isoformat(),
            "training_end_date": series.index.max().date().isoformat(),
            "evaluation_start_date": evaluation_start,
            "evaluation_end_date": evaluation_end,
            "evaluation_mae": candidate_mae,
            "baseline_mae": baseline_mae,
            "mean_signed_error": mean_bias,
            "mean_actual": mean_actual,
            "horizons_won_against_baseline": horizons_won,
            "artifact_path": artifact_path.relative_to(root).as_posix(),
            "status": "CANDIDATE",
            "decision_reason": "Aguardando decisão da política Champion × Challenger.",
            "feature_names": FEATURE_NAMES,
            "hyperparameters": selected_estimator.get_params(deep=False),
        },
        config_path,
        database=database_file,
    )

    promotion_id = f"promotion_{current_time.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    promotion_record = {
        "promotion_id": promotion_id,
        "evaluated_at": current_time.isoformat(),
        "candidate_version": candidate_version,
        "champion_version": champion["model_version"],
        "candidate_mae": candidate_mae,
        "champion_mae": champion_mae,
        "baseline_mae": baseline_mae,
        "candidate_mean_bias": mean_bias,
        "candidate_mean_actual": mean_actual,
        "horizons_won_against_baseline": horizons_won,
        "new_actuals_count": new_actuals,
        "decision": decision.decision,
        "reason": reason,
        "policy_version": int(policy["policy_version"]),
        "evaluation_start_date": evaluation_start,
        "evaluation_end_date": evaluation_end,
        "details": {
            "days_since_last_training": days_since_training,
            "temporal_evaluation_valid": temporal_valid,
            "promotion_window_is_new": promotion_window_is_new,
            "evaluation_kind": "NEW_HOLDOUT" if promotion_window_is_new else "HISTORICAL_REPLAY",
            "candidate_metrics": {name: round(mae, 6) for name, _, mae in candidate_results},
            "decision": asdict(decision),
        },
    }
    finalize_candidate_status(
        candidate_version,
        promoted=decision.eligible,
        reason=reason,
        config_path=config_path,
        database=database_file,
        decision_record=promotion_record,
    )
    if decision.eligible:
        export_active_registry_json(config_path, database=database_file)

    summary = {
        "promotion_id": promotion_id,
        "evaluated_at": current_time.isoformat(),
        "champion_version_before": champion["model_version"],
        "candidate_version": candidate_version,
        "candidate_algorithm": selected_name,
        "evaluation_start_date": evaluation_start,
        "evaluation_end_date": evaluation_end,
        "temporal_evaluation_valid": temporal_valid,
        "promotion_window_is_new": promotion_window_is_new,
        "evaluation_kind": "NEW_HOLDOUT" if promotion_window_is_new else "HISTORICAL_REPLAY",
        "candidate_mae": round(candidate_mae, 6),
        "champion_mae": round(champion_mae, 6),
        "baseline_mae": round(baseline_mae, 6),
        "candidate_mean_bias": round(mean_bias, 6),
        "candidate_mean_actual": round(mean_actual, 6),
        "horizons_won_against_baseline": horizons_won,
        "new_actuals_count": new_actuals,
        "days_since_last_training": days_since_training,
        "decision": decision.decision,
        "reason": reason,
        "active_model_after": get_active_model(config_path, database=database_file)[
            "model_version"
        ],
        "data_limitation": (
            "Não existem realizados posteriores a 31/12/2025; a política rejeita "
            "promoção sem novos dados e mantém o Champion inalterado."
        ),
    }
    if write_evidence and database is None:
        evidence = root / "evidence"
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "30_retrain_decision.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        with connect(database_file, read_only=True) as connection:
            pd.read_sql_query(
                "SELECT * FROM registered_models ORDER BY trained_at DESC", connection
            ).to_csv(evidence / "31_model_registry.csv", index=False)
            pd.read_sql_query(
                "SELECT * FROM model_promotion_history ORDER BY evaluated_at DESC", connection
            ).to_csv(evidence / "32_promotion_history.csv", index=False)
    return summary
