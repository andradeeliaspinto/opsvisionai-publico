from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from src.acquire_data import download_source
from src.alerts import generate_operational_alerts
from src.configuration import database_path, operations_config, project_root
from src.database import connect, utc_now
from src.inference import run_inference
from src.file_io import atomic_output
from src.integrations import dispatch_operational_alerts
from src.job_tracking import JobTracker
from src.locking import exclusive_file_lock
from src.logging_utils import configure_logging, job_logger, update_logger_context
from src.model_registry import get_active_model
from src.monitoring import refresh_monitoring_metrics
from src.prepare_data import prepare_dataset
from src.serving import publish_serving_store


def tracked_operation(config_path, job_type, action):
    config_path = Path(config_path).resolve()
    root = project_root(config_path)
    tracker = JobTracker(config_path)
    job_id = f"job_{uuid4().hex}"
    job_started = False
    logging_ready = False
    logger = job_logger(__name__, job_id=job_id)
    details = {}
    active = None
    try:
        with exclusive_file_lock(
            root / operations_config(config_path)["pipeline"]["lock_file"], job_id=job_id
        ):
            # Só registre RUNNING depois de obter o lock: um concorrente ainda
            # aguardando não pode ser confundido com um job abandonado.
            tracker.start(job_type, job_id=job_id)
            job_started = True
            configure_logging(config_path)
            logging_ready = True
            # Só o detentor do lock recupera jobs interrompidos por encerramento abrupto.
            with connect(database_path(config_path)) as connection:
                connection.execute(
                    "UPDATE pipeline_job_runs SET status='FAILED', finished_at=?, error_message='Execução interrompida; lock liberado pelo SO', duration_seconds=(julianday(?) - julianday(started_at))*86400 WHERE status='RUNNING' AND job_id != ?",
                    (utc_now(), utc_now(), job_id),
                )
            active = get_active_model(config_path)
            update_logger_context(logger, model_version=active["model_version"])
            logger.info("Iniciando %s", job_type)
            result = action(config_path, logger, details)
            details.update(result)
            tracker.finish_success(
                job_id,
                model_version=get_active_model(config_path)["model_version"],
                records_processed=result.get("records_processed"),
                details=details,
            )
            logger.info("Job concluído com sucesso")
        return {"job_id": job_id, "status": "SUCCESS", **result}
    except (Exception, KeyboardInterrupt) as exc:
        if not job_started:
            tracker.start(job_type, job_id=job_id)
        tracker.finish_failure(
            job_id, exc, model_version=active["model_version"] if active else None, details=details
        )
        if logging_ready:
            logger.exception("Job falhou: %s", job_type)
        raise


def daily_action(config_path, logger, details):
    details["stage"] = "ingestion"
    download_source(config_path)
    details["stage"] = "preparation"
    quality = prepare_dataset(config_path)
    logger.info("Preparação: %s incidentes", quality["analysis_incidents"])
    details["stage"] = "inference"
    inference = run_inference(config_path)
    details["inference_run_id"] = inference["inference_run_id"]
    details["stage"] = "publication"
    publish_serving_store(config_path)
    details["stage"] = "monitoring"
    monitoring = refresh_monitoring_metrics(config_path)
    details["stage"] = "alerts"
    alerts = generate_operational_alerts(
        config_path, inference_run_id=inference["inference_run_id"]
    )
    details["stage"] = "integration"
    integration = dispatch_operational_alerts(
        config_path, inference_run_id=inference["inference_run_id"], force_dry_run=True
    )
    logger.info(
        "Alertas=%s; integração DRY_RUN; métricas LIVE=%s",
        alerts["alerts_persisted"],
        monitoring["live_forecasts_evaluated"],
    )
    details["stage"] = "complete"
    return {
        "records_processed": quality["analysis_incidents"],
        "inference": inference,
        "monitoring": monitoring,
        "alerts": alerts["alerts_persisted"],
        "integration_mode": integration["mode"],
        "data_mode": "OFFLINE_REPLAY",
    }


def run_daily(config_path="config/project.yaml"):
    result = tracked_operation(config_path, "DAILY_PIPELINE", daily_action)
    path = project_root(config_path) / "evidence/36_daily_pipeline.json"
    with atomic_output(path) as temporary:
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
