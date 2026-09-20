from __future__ import annotations

import math
from datetime import date
from typing import Any

REQUIRED_ALERT_FIELDS = {
    "alert_id",
    "forecast_date",
    "horizon",
    "predicted_incidents",
    "alert_level",
    "rule_triggered",
    "model_version",
    "status",
}


def validate_alert(alert: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_ALERT_FIELDS - set(alert))
    if missing:
        raise ValueError("Campos obrigatórios ausentes no alerta: " + ", ".join(missing))
    if not 1 <= int(alert["horizon"]) <= 7 or float(alert["horizon"]) != int(alert["horizon"]):
        raise ValueError("Horizonte deve ser inteiro entre 1 e 7.")
    value = float(alert["predicted_incidents"])
    if not math.isfinite(value) or value < 0:
        raise ValueError("Volume previsto deve ser finito e não negativo.")
    date.fromisoformat(str(alert["forecast_date"]))
    if alert["alert_level"] not in {"ATENCAO", "ALTO", "CRITICO"} or alert["status"] not in {
        "OPEN",
        "ACKNOWLEDGED",
        "CLOSED",
    }:
        raise ValueError("Nível ou status de alerta inválido.")
    if not str(alert["alert_id"]).strip() or not str(alert["model_version"]).strip():
        raise ValueError("Identificadores do alerta e modelo são obrigatórios.")


def _summary(alert: dict[str, Any]) -> str:
    return (
        f"OpsVisionAI {alert['alert_level']}: {float(alert['predicted_incidents']):.0f} "
        f"incidentes previstos para {alert['forecast_date']} (D+{int(alert['horizon'])})."
    )


def generic_payload(alert: dict[str, Any]) -> dict[str, Any]:
    validate_alert(alert)
    return {
        "event_type": "OPSVISION_FORECAST_ALERT",
        "alert_id": alert["alert_id"],
        "severity": alert["alert_level"],
        "status": alert["status"],
        "summary": _summary(alert),
        "forecast": {
            "date": alert["forecast_date"],
            "horizon": int(alert["horizon"]),
            "predicted_incidents": float(alert["predicted_incidents"]),
            "model_version": alert["model_version"],
        },
        "rule": alert["rule_triggered"],
        "generated_at": alert.get("generated_at"),
    }


def slack_payload(alert: dict[str, Any]) -> dict[str, Any]:
    validate_alert(alert)
    summary = _summary(alert)
    return {
        "text": summary,
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "OpsVisionAI — alerta operacional"},
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*{summary}*"}},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Nível:* {alert['alert_level']}"},
                    {"type": "mrkdwn", "text": f"*Modelo:* `{alert['model_version']}`"},
                    {"type": "mrkdwn", "text": f"*Regra:* {alert['rule_triggered']}"},
                    {"type": "mrkdwn", "text": f"*Status:* {alert['status']}"},
                ],
            },
        ],
    }


def teams_payload(alert: dict[str, Any]) -> dict[str, Any]:
    validate_alert(alert)
    summary = _summary(alert)
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "size": "Large",
                            "weight": "Bolder",
                            "text": "OpsVisionAI",
                        },
                        {"type": "TextBlock", "wrap": True, "text": summary},
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Nível", "value": str(alert["alert_level"])},
                                {"title": "Modelo", "value": str(alert["model_version"])},
                                {"title": "Regra", "value": str(alert["rule_triggered"])},
                                {"title": "Status", "value": str(alert["status"])},
                            ],
                        },
                    ],
                },
            }
        ],
    }


def build_payload(alert: dict[str, Any], payload_format: str) -> dict[str, Any]:
    serializers = {
        "generic": generic_payload,
        "slack": slack_payload,
        "teams": teams_payload,
    }
    try:
        serializer = serializers[payload_format.lower()]
    except KeyError as exc:
        raise ValueError(f"Formato de payload não suportado: {payload_format}") from exc
    return serializer(alert)
