from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.configuration import database_path as configured_database_path
from src.configuration import operations_config, project_root
from src.database import connect, migrate_database
from src.integrations.webhook import WebhookAlertAdapter


def dispatch_operational_alerts(
    config_path: str | Path = "config/project.yaml",
    *,
    database: str | Path | None = None,
    inference_run_id: str | None = None,
    force_dry_run: bool | None = None,
    write_evidence: bool = True,
) -> dict[str, Any]:
    root = project_root(config_path)
    database_file = (
        Path(database) if database is not None else configured_database_path(config_path)
    )
    migrate_database(config_path, database=database_file)
    settings = operations_config(config_path)["integration"]
    dry_run = bool(settings.get("dry_run", True)) if force_dry_run is None else bool(force_dry_run)
    adapter = WebhookAlertAdapter(
        webhook_url=os.getenv(str(settings["webhook_url_env"])),
        payload_format=str(settings.get("payload_format", "generic")),
        dry_run=dry_run,
        timeout_seconds=float(settings.get("timeout_seconds", 5)),
        max_retries=int(settings.get("max_retries", 2)),
        retry_backoff_seconds=float(settings.get("retry_backoff_seconds", 1.0)),
    )

    with connect(database_file, read_only=True) as connection:
        if inference_run_id is None:
            row = connection.execute(
                "SELECT inference_run_id FROM operational_alerts ORDER BY generated_at DESC LIMIT 1"
            ).fetchone()
            inference_run_id = None if row is None else str(row["inference_run_id"])
        alerts = (
            []
            if inference_run_id is None
            else [
                dict(row)
                for row in connection.execute(
                    """
                SELECT * FROM operational_alerts
                WHERE inference_run_id = ? AND status = 'OPEN'
                ORDER BY horizon
                """,
                    (inference_run_id,),
                )
            ]
        )

    delivered: list[dict[str, Any]] = []
    for alert in alerts:
        mode = "DRY_RUN" if dry_run else "LIVE"
        idempotency_key = f"{alert['alert_id']}:{adapter.name}:{adapter.payload_format}:{mode}"
        with connect(database_file, read_only=True) as connection:
            existing = connection.execute(
                "SELECT status, payload_json FROM integration_delivery_log WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        if existing is not None:
            delivered.append(
                {
                    "alert_id": alert["alert_id"],
                    "status": "SKIPPED",
                    "reason": "Entrega já registrada para esta chave idempotente.",
                    "payload": json.loads(existing["payload_json"]),
                }
            )
            continue

        result = adapter.send(alert)
        attempted_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        delivery_id = f"delivery_{uuid4().hex}"
        with connect(database_file) as connection:
            connection.execute(
                """
                INSERT INTO integration_delivery_log(
                    delivery_id, idempotency_key, alert_id, attempted_at,
                    adapter_name, payload_format, mode, status, attempts,
                    http_status, error_message, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    delivery_id,
                    idempotency_key,
                    alert["alert_id"],
                    attempted_at,
                    adapter.name,
                    adapter.payload_format,
                    result.mode,
                    result.status,
                    result.attempts,
                    result.http_status,
                    result.error_message,
                    json.dumps(result.payload, ensure_ascii=False, sort_keys=True),
                ),
            )
            connection.commit()
        delivered.append(
            {
                "delivery_id": delivery_id,
                "alert_id": alert["alert_id"],
                "status": result.status,
                "mode": result.mode,
                "attempts": result.attempts,
                "payload": result.payload,
                "error_message": result.error_message,
            }
        )

    summary = {
        "inference_run_id": inference_run_id,
        "adapter": adapter.name,
        "payload_format": adapter.payload_format,
        "mode": "DRY_RUN" if dry_run else "LIVE",
        "alerts_considered": len(alerts),
        "results": delivered,
        "network_calls_performed": 0
        if dry_run
        else sum(item.get("attempts", 0) for item in delivered if item.get("status") != "SKIPPED"),
    }
    if write_evidence and database is None:
        evidence = root / "evidence"
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "35_integration_dry_run.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return summary
