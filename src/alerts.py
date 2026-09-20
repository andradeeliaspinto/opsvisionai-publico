from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import pandas as pd

from src.configuration import alert_policy, project_root
from src.configuration import database_path as configured_database_path
from src.database import connect, migrate_database


def derive_thresholds(actuals: pd.Series, levels=None) -> dict[str, float]:
    clean = pd.to_numeric(actuals, errors="coerce").dropna().astype(float)
    if clean.empty:
        raise ValueError("Não há realizados válidos para derivar os limites de alerta.")
    quantiles = (
        [levels[n]["lower_percentile"] for n in ["ATENCAO", "ALTO", "CRITICO"]]
        if levels
        else [0.75, 0.90, 0.97]
    )
    if not (0 < quantiles[0] < quantiles[1] < quantiles[2] < 1):
        raise ValueError("Percentis devem ser crescentes e estar entre 0 e 1.")
    return {key: float(clean.quantile(q)) for key, q in zip(["p75", "p90", "p97"], quantiles)}


def classify_alert(
    predicted_incidents: float, thresholds: dict[str, float]
) -> tuple[str, float, str]:
    value = float(predicted_incidents)
    if value >= thresholds["p97"]:
        return (
            "CRITICO",
            thresholds["p97"],
            "Previsão igual ou superior ao limite histórico CRITICO configurado",
        )
    if value >= thresholds["p90"]:
        return (
            "ALTO",
            thresholds["p90"],
            "Previsão igual ou superior ao limite histórico ALTO configurado",
        )
    if value >= thresholds["p75"]:
        return (
            "ATENCAO",
            thresholds["p75"],
            "Previsão igual ou superior ao limite histórico ATENCAO configurado",
        )
    return "NORMAL", thresholds["p75"], "Previsão abaixo do limite histórico ATENCAO configurado"


def _threshold_id(
    actuals: pd.DataFrame,
    thresholds: dict[str, float],
    policy_version: int,
) -> str:
    payload = {
        "start": actuals["actual_date"].min(),
        "end": actuals["actual_date"].max(),
        "count": len(actuals),
        "sum": float(actuals["actual_incidents"].sum()),
        "thresholds": thresholds,
        "policy_version": policy_version,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return "thresholds_" + digest[:20]


def generate_operational_alerts(
    config_path: str | Path = "config/project.yaml",
    *,
    database: str | Path | None = None,
    inference_run_id: str | None = None,
    write_evidence: bool = True,
) -> dict[str, Any]:
    root = project_root(config_path)
    database_file = (
        Path(database) if database is not None else configured_database_path(config_path)
    )
    migrate_database(config_path, database=database_file)
    policy = alert_policy(config_path)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    with connect(database_file, read_only=True) as connection:
        actuals = pd.read_sql_query(
            "SELECT actual_date, actual_incidents FROM daily_actuals ORDER BY actual_date",
            connection,
        )
        if inference_run_id is None:
            row = connection.execute(
                """
                SELECT inference_run_id
                FROM forecast_predictions
                ORDER BY prediction_generated_at DESC, inference_run_id DESC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                raise RuntimeError("Nenhuma execução de inferência disponível para alertas.")
            inference_run_id = str(row["inference_run_id"])
        forecasts = pd.read_sql_query(
            """
            SELECT inference_run_id, forecast_date, horizon, predicted_incidents, data_cutoff_date,
                   forecast_method, model_version
            FROM forecast_predictions
            WHERE inference_run_id = ? AND is_recommended = 1
            ORDER BY horizon
            """,
            connection,
            params=(inference_run_id,),
        )
    if len(forecasts) != 7:
        raise RuntimeError(
            f"A execução {inference_run_id} deve possuir sete previsões recomendadas; "
            f"foram encontradas {len(forecasts)}."
        )

    actuals = actuals[actuals["actual_date"] <= forecasts["data_cutoff_date"].min()]
    thresholds = derive_thresholds(actuals["actual_incidents"], policy["levels"])
    threshold_set_id = _threshold_id(actuals, thresholds, int(policy["policy_version"]))
    with connect(database_file) as connection:
        connection.execute(
            """
            INSERT INTO alert_threshold_snapshots(
                threshold_set_id, computed_at, history_start_date, history_end_date,
                observations, method, p75, p90, p97, policy_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(threshold_set_id) DO UPDATE SET computed_at = excluded.computed_at
            """,
            (
                threshold_set_id,
                generated_at,
                str(actuals["actual_date"].min()),
                str(actuals["actual_date"].max()),
                int(len(actuals)),
                policy["method"] + ":" + json.dumps(policy["levels"], sort_keys=True),
                thresholds["p75"],
                thresholds["p90"],
                thresholds["p97"],
                int(policy["policy_version"]),
            ),
        )
        connection.commit()

    classified: list[dict[str, Any]] = []
    persisted = 0
    with connect(database_file) as connection:
        for forecast in forecasts.to_dict(orient="records"):
            level, threshold_value, rule = classify_alert(
                float(forecast["predicted_incidents"]), thresholds
            )
            row = {
                **forecast,
                "alert_level": level,
                "threshold_value": threshold_value,
                "rule_triggered": rule,
            }
            classified.append(row)
            if level == "NORMAL":
                continue
            alert_id = (
                "alert_"
                + uuid5(
                    NAMESPACE_URL,
                    f"opsvision:{inference_run_id}:{forecast['forecast_method']}:{forecast['horizon']}",
                ).hex
            )
            connection.execute(
                """
                INSERT INTO operational_alerts(
                    alert_id, inference_run_id, generated_at, forecast_date, horizon,
                    predicted_incidents, alert_level, rule_triggered, threshold_value,
                    threshold_set_id, model_version, forecast_method, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
                ON CONFLICT(inference_run_id, forecast_method, horizon) DO UPDATE SET
                    generated_at = excluded.generated_at,
                    forecast_date = excluded.forecast_date,
                    predicted_incidents = excluded.predicted_incidents,
                    alert_level = excluded.alert_level,
                    rule_triggered = excluded.rule_triggered,
                    threshold_value = excluded.threshold_value,
                    threshold_set_id = excluded.threshold_set_id,
                    model_version = excluded.model_version
                """,
                (
                    alert_id,
                    inference_run_id,
                    generated_at,
                    forecast["forecast_date"],
                    int(forecast["horizon"]),
                    float(forecast["predicted_incidents"]),
                    level,
                    rule,
                    threshold_value,
                    threshold_set_id,
                    forecast["model_version"],
                    forecast["forecast_method"],
                ),
            )
            persisted += 1
        connection.commit()

    summary = {
        "generated_at": generated_at,
        "inference_run_id": inference_run_id,
        "threshold_set_id": threshold_set_id,
        "threshold_method": policy["method"],
        "thresholds": {key: round(value, 4) for key, value in thresholds.items()},
        "forecasts_evaluated": len(classified),
        "alerts_persisted": persisted,
        "level_counts": pd.Series([item["alert_level"] for item in classified])
        .value_counts()
        .to_dict(),
        "classification": classified,
    }
    if write_evidence and database is None:
        evidence = root / "evidence"
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "33_alert_thresholds.json").write_text(
            json.dumps(
                {
                    "threshold_set_id": threshold_set_id,
                    "method": policy["method"],
                    "history_start_date": str(actuals["actual_date"].min()),
                    "history_end_date": str(actuals["actual_date"].max()),
                    "observations": len(actuals),
                    "thresholds": summary["thresholds"],
                    "configured_levels": policy["levels"],
                    "rationale": policy["documentation"]["rationale"],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        pd.DataFrame(classified).to_csv(evidence / "34_operational_alerts.csv", index=False)
    return summary
