from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib

from src.file_io import atomic_output
from src.configuration import database_path as configured_database_path
from src.configuration import project_root
from src.database import connect, migrate_database, utc_now


def _artifact_trained_at(path: Path) -> str:
    return (
        datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        .replace(microsecond=0)
        .isoformat()
    )


def _row_to_dict(row: Any) -> dict[str, Any]:
    result = dict(row)
    # Registros gerados por versões antigas no Windows podem conter '\\'.
    if "artifact_path" in result:
        result["artifact_path"] = result["artifact_path"].replace("\\", "/")
    for field in ("feature_names_json", "hyperparameters_json"):
        if field in result:
            result[field.removesuffix("_json")] = json.loads(result[field] or "{}")
    return result


def sync_legacy_registry(
    config_path: str | Path = "config/project.yaml",
    *,
    database: str | Path | None = None,
) -> dict[str, Any]:
    """Semeia o registry SQLite a partir do registry JSON sem sobrescrever um ACTIVE existente."""
    root = project_root(config_path)
    database_file = (
        Path(database) if database is not None else configured_database_path(config_path)
    )
    migrate_database(config_path, database=database_file)

    with connect(database_file) as connection:
        active_row = connection.execute(
            "SELECT * FROM registered_models WHERE status = 'ACTIVE' LIMIT 1"
        ).fetchone()
        if active_row is not None:
            return _row_to_dict(active_row)

    legacy_path = root / "models/model_registry.json"
    if not legacy_path.exists():
        raise FileNotFoundError("Registry legado ausente e nenhum modelo ACTIVE foi registrado.")
    legacy = json.loads(legacy_path.read_text(encoding="utf-8"))["active_model"]
    legacy["artifact_path"] = legacy["artifact_path"].replace("\\", "/")
    artifact = root / legacy["artifact_path"]
    if not artifact.exists():
        raise FileNotFoundError(f"Artefato do modelo ativo ausente: {artifact}")
    estimator = joblib.load(artifact)
    now = utc_now()
    values = (
        legacy["model_version"],
        legacy["model_name"],
        legacy["model_code"],
        _artifact_trained_at(artifact),
        legacy["training_series_start"],
        legacy["training_series_end"],
        legacy.get("test_start_date"),
        legacy.get("test_end_date"),
        legacy.get("model_test_mae"),
        legacy.get("baseline_test_mae"),
        None,
        None,
        legacy.get("horizons_model_wins"),
        legacy["artifact_path"],
        "ACTIVE",
        "Modelo Champion migrado do registry JSON validado na Fase 4.",
        json.dumps(legacy.get("feature_names", []), ensure_ascii=False),
        json.dumps(estimator.get_params(deep=False), ensure_ascii=False, default=str),
        now,
        now,
    )
    with connect(database_file) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO registered_models(
                model_version, algorithm, model_code, trained_at,
                training_start_date, training_end_date,
                evaluation_start_date, evaluation_end_date,
                evaluation_mae, baseline_mae, mean_signed_error, mean_actual,
                horizons_won_against_baseline, artifact_path, status,
                decision_reason, feature_names_json, hyperparameters_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        connection.commit()
        active_row = connection.execute(
            "SELECT * FROM registered_models WHERE status = 'ACTIVE' LIMIT 1"
        ).fetchone()
    if active_row is None:
        raise RuntimeError("Não foi possível registrar o modelo Champion.")
    return _row_to_dict(active_row)


def get_active_model(
    config_path: str | Path = "config/project.yaml",
    *,
    database: str | Path | None = None,
) -> dict[str, Any]:
    return sync_legacy_registry(config_path, database=database)


def register_candidate(
    record: dict[str, Any],
    config_path: str | Path = "config/project.yaml",
    *,
    database: str | Path | None = None,
) -> None:
    database_file = (
        Path(database) if database is not None else configured_database_path(config_path)
    )
    migrate_database(config_path, database=database_file)
    now = utc_now()
    with connect(database_file) as connection:
        connection.execute(
            """
            INSERT INTO registered_models(
                model_version, algorithm, model_code, trained_at,
                training_start_date, training_end_date,
                evaluation_start_date, evaluation_end_date,
                evaluation_mae, baseline_mae, mean_signed_error, mean_actual,
                horizons_won_against_baseline, artifact_path, status,
                decision_reason, feature_names_json, hyperparameters_json,
                created_at, updated_at
            ) VALUES (
                :model_version, :algorithm, :model_code, :trained_at,
                :training_start_date, :training_end_date,
                :evaluation_start_date, :evaluation_end_date,
                :evaluation_mae, :baseline_mae, :mean_signed_error, :mean_actual,
                :horizons_won_against_baseline, :artifact_path, :status,
                :decision_reason, :feature_names_json, :hyperparameters_json,
                :created_at, :updated_at
            )
            """,
            {
                **record,
                "artifact_path": record["artifact_path"].replace("\\", "/"),
                "feature_names_json": json.dumps(
                    record.get("feature_names", []), ensure_ascii=False
                ),
                "hyperparameters_json": json.dumps(
                    record.get("hyperparameters", {}),
                    ensure_ascii=False,
                    default=str,
                    sort_keys=True,
                ),
                "created_at": record.get("created_at", now),
                "updated_at": now,
            },
        )
        connection.commit()


def finalize_candidate_status(
    candidate_version: str,
    *,
    promoted: bool,
    reason: str,
    config_path: str | Path = "config/project.yaml",
    database: str | Path | None = None,
    decision_record: dict | None = None,
) -> None:
    database_file = (
        Path(database) if database is not None else configured_database_path(config_path)
    )
    now = utc_now()
    with connect(database_file) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if promoted:
            connection.execute(
                """
                UPDATE registered_models
                SET status = 'ARCHIVED', decision_reason = ?, updated_at = ?
                WHERE status = 'ACTIVE'
                """,
                (f"Arquivado após promoção de {candidate_version}.", now),
            )
            connection.execute(
                """
                UPDATE registered_models
                SET status = 'ACTIVE', decision_reason = ?, updated_at = ?
                WHERE model_version = ? AND status = 'CANDIDATE'
                """,
                (reason, now, candidate_version),
            )
        else:
            connection.execute(
                """
                UPDATE registered_models
                SET status = 'REJECTED', decision_reason = ?, updated_at = ?
                WHERE model_version = ? AND status = 'CANDIDATE'
                """,
                (reason, now, candidate_version),
            )
        changed = connection.execute("SELECT changes()").fetchone()[0]
        if changed == 0:
            raise RuntimeError(f"Candidato não encontrado ou já finalizado: {candidate_version}")
        active_count = connection.execute(
            "SELECT COUNT(*) FROM registered_models WHERE status = 'ACTIVE'"
        ).fetchone()[0]
        if active_count != 1:
            raise RuntimeError(f"Registry inconsistente: {active_count} modelos ACTIVE.")
        if decision_record is not None:
            payload = dict(decision_record)
            payload["details_json"] = json.dumps(payload.pop("details", {}), ensure_ascii=False)
            columns = ", ".join(payload)
            placeholders = ", ".join("?" for _ in payload)
            connection.execute(
                f"INSERT INTO model_promotion_history ({columns}) VALUES ({placeholders})",
                tuple(payload.values()),
            )
        connection.commit()


def export_active_registry_json(
    config_path: str | Path = "config/project.yaml",
    *,
    database: str | Path | None = None,
) -> Path:
    root = project_root(config_path)
    active = get_active_model(config_path, database=database)
    payload = {
        "registry_schema_version": 2,
        "source_of_truth": "SQLite registered_models",
        "active_model": {
            "model_version": active["model_version"],
            "model_name": active["algorithm"],
            "model_code": active["model_code"],
            "artifact_path": active["artifact_path"],
            "data_cutoff_date": active["training_end_date"],
            "training_series_start": active["training_start_date"],
            "training_series_end": active["training_end_date"],
            "feature_names": active["feature_names"],
            "test_start_date": active["evaluation_start_date"],
            "test_end_date": active["evaluation_end_date"],
            "model_test_mae": active["evaluation_mae"],
            "baseline_test_mae": active["baseline_mae"],
            "horizons_model_wins": active["horizons_won_against_baseline"],
            "relative_mae_reduction": (active["baseline_mae"] - active["evaluation_mae"])
            / active["baseline_mae"],
            "recommended_method_code": active["model_code"],
        },
    }
    path = root / "models/model_registry.json"
    with atomic_output(path) as temporary:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
