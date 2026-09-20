from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.configuration import database_path as configured_database_path
from src.database import connect, migrate_database


def _now() -> datetime:
    return datetime.now(timezone.utc)


class JobTracker:
    def __init__(
        self,
        config_path: str | Path = "config/project.yaml",
        *,
        database: str | Path | None = None,
    ) -> None:
        self.config_path = Path(config_path)
        self.database = (
            Path(database) if database is not None else configured_database_path(config_path)
        )
        migrate_database(config_path, database=self.database)

    def start(
        self, job_type: str, *, model_version: str | None = None, job_id: str | None = None
    ) -> str:
        started_at = _now()
        job_id = job_id or f"job_{started_at.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
        with connect(self.database) as connection:
            connection.execute(
                """
                INSERT INTO pipeline_job_runs(
                    job_id, job_type, started_at, status, model_version, details_json
                ) VALUES (?, ?, ?, 'RUNNING', ?, '{}')
                """,
                (job_id, job_type, started_at.isoformat(), model_version),
            )
            connection.commit()
        return job_id

    def finish_success(
        self,
        job_id: str,
        *,
        records_processed: int | None = None,
        model_version: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        finished_at = _now()
        with connect(self.database) as connection:
            row = connection.execute(
                "SELECT started_at FROM pipeline_job_runs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Job não encontrado: {job_id}")
            started_at = datetime.fromisoformat(row["started_at"])
            duration = (finished_at - started_at).total_seconds()
            connection.execute(
                """
                UPDATE pipeline_job_runs
                SET finished_at = ?, duration_seconds = ?, status = 'SUCCESS',
                    records_processed = ?, model_version = COALESCE(?, model_version),
                    error_message = NULL, stack_trace = NULL, details_json = ?
                WHERE job_id = ?
                """,
                (
                    finished_at.isoformat(),
                    duration,
                    records_processed,
                    model_version,
                    json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
                    job_id,
                ),
            )
            connection.commit()

    def finish_failure(
        self,
        job_id: str,
        error: BaseException,
        *,
        model_version: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        finished_at = _now()
        stack = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        with connect(self.database) as connection:
            row = connection.execute(
                "SELECT started_at FROM pipeline_job_runs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Job não encontrado: {job_id}")
            started_at = datetime.fromisoformat(row["started_at"])
            duration = (finished_at - started_at).total_seconds()
            connection.execute(
                """
                UPDATE pipeline_job_runs
                SET finished_at = ?, duration_seconds = ?, status = 'FAILED',
                    model_version = COALESCE(?, model_version), error_message = ?,
                    stack_trace = ?, details_json = ?
                WHERE job_id = ?
                """,
                (
                    finished_at.isoformat(),
                    duration,
                    model_version,
                    (str(error) or type(error).__name__)[:2000],
                    stack[:20000],
                    json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
                    job_id,
                ),
            )
            connection.commit()
