import argparse
import json
from pathlib import Path

from src.configuration import database_path
from src.database import connect, database_catalog, migrate_database, utc_now
from src.integrations import dispatch_operational_alerts
from src.model_registry import sync_legacy_registry
from src.monitoring import refresh_monitoring_metrics
from src.operations import tracked_operation


def main():
    parser = argparse.ArgumentParser(
        description="Comandos de manutenção e consulta do OpsVisionAI."
    )
    parser.add_argument(
        "command", choices=["migrate", "monitor", "dry-run", "catalog", "acknowledge", "close"]
    )
    parser.add_argument(
        "--config", type=Path, default=Path(__file__).resolve().parent / "config/project.yaml"
    )
    parser.add_argument("--alert-id")
    args = parser.parse_args()

    def execute(config, logger, details):
        if args.command == "migrate":
            result = migrate_database(config)
            sync_legacy_registry(config)
            return result
        if args.command == "monitor":
            return refresh_monitoring_metrics(config)
        if args.command == "dry-run":
            return dispatch_operational_alerts(config, force_dry_run=True)
        if args.command == "catalog":
            return database_catalog(database_path(config))
        if not args.alert_id:
            raise ValueError("--alert-id é obrigatório")
        status = "ACKNOWLEDGED" if args.command == "acknowledge" else "CLOSED"
        field = "acknowledged_at" if args.command == "acknowledge" else "closed_at"
        with connect(database_path(config)) as connection:
            cursor = connection.execute(
                f"UPDATE operational_alerts SET status=?, {field}=? WHERE alert_id=? AND status != ?",
                (status, utc_now(), args.alert_id, "CLOSED"),
            )
            if cursor.rowcount != 1:
                raise ValueError("Alerta inexistente ou já encerrado")
        return {"alert_id": args.alert_id, "status": status}

    result = tracked_operation(args.config, args.command.upper(), execute)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
