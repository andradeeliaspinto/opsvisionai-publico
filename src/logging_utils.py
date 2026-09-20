from __future__ import annotations

import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from src.configuration import operations_config, project_root


class ContextDefaultsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "job_id"):
            record.job_id = "-"
        if not hasattr(record, "model_version"):
            record.model_version = "-"
        return True


def configure_logging(config_path: str | Path = "config/project.yaml") -> Path:
    root = project_root(config_path)
    settings = operations_config(config_path)["logging"]
    log_path = root / settings["file"]
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    if getattr(root_logger, "_opsvision_configured", None) == str(log_path):
        return log_path
    for handler in list(root_logger.handlers):
        if getattr(handler, "_opsvision", False):
            root_logger.removeHandler(handler)
            handler.close()

    level = getattr(logging, str(settings.get("level", "INFO")).upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | job=%(job_id)s | "
        "model=%(model_version)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    formatter.converter = time.gmtime
    context_filter = ContextDefaultsFilter()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(context_filter)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=int(settings.get("max_bytes", 2_097_152)),
        backupCount=int(settings.get("backup_count", 3)),
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(context_filter)

    root_logger.setLevel(level)
    stream_handler._opsvision = True
    file_handler._opsvision = True
    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)
    root_logger._opsvision_configured = str(log_path)
    return log_path


def job_logger(
    name: str,
    *,
    job_id: str = "-",
    model_version: str = "-",
) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(
        logging.getLogger(name),
        {"job_id": job_id, "model_version": model_version},
    )


def update_logger_context(logger: logging.LoggerAdapter, **values: Any) -> None:
    logger.extra.update({key: value for key, value in values.items() if value is not None})
