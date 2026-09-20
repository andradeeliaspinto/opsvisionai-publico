"""QA reproduzível; fixtures são temporárias e não alteram o banco entregue."""

from __future__ import annotations

import contextlib
import importlib.metadata
import io
import json
import platform
import sqlite3
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.validate_dashboard import validate_dashboard
from src.configuration import database_path
from src.database import database_catalog
from validate_project import validate


class LiveEvidenceOutput:
    """Mostra cada teste imediatamente e preserva a saída para a evidência."""

    def __init__(self, evidence, console):
        self.evidence = evidence
        self.console = console

    def write(self, text):
        self.evidence.write(text)
        self.console.write(text)
        self.console.flush()
        return len(text)

    def flush(self):
        self.evidence.flush()
        self.console.flush()


def main():
    evidence = ROOT / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    output = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    print(f"[1/4] Executando {suite.countTestCases()} testes; andamento abaixo.", flush=True)
    live_output = LiveEvidenceOutput(output, sys.stdout)
    with contextlib.redirect_stderr(live_output), contextlib.redirect_stdout(live_output):
        result = unittest.TextTestRunner(stream=live_output, verbosity=2).run(suite)
    (evidence / "38_post_mvp_tests.txt").write_text(output.getvalue(), encoding="utf-8")
    print("[2/4] Validando o dashboard com AppTest...", flush=True)
    dashboard = validate_dashboard(evidence / "17_dashboard_runtime_validation.json")
    print("[3/4] Health check e leitura do dataset oficial...", flush=True)
    health = validate()
    (evidence / "18_project_health_check.json").write_text(
        json.dumps(health, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    database = database_path(ROOT / "config/project.yaml")
    print("[4/4] Conferindo integridade do SQLite e salvando evidências...", flush=True)
    catalog = database_catalog(database)
    with contextlib.closing(sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)) as con:
        catalog["integrity_check"] = con.execute("PRAGMA integrity_check").fetchone()[0]
        catalog["foreign_key_violations"] = con.execute("PRAGMA foreign_key_check").fetchall()
        catalog["schema"] = [
            dict(zip(["type", "name", "sql"], row))
            for row in con.execute(
                "SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
            )
        ]
        active = con.execute(
            "SELECT count(*) FROM registered_models WHERE status='ACTIVE'"
        ).fetchone()[0]
        running = con.execute(
            "SELECT count(*) FROM pipeline_job_runs WHERE status='RUNNING'"
        ).fetchone()[0]
    (evidence / "39_post_mvp_database.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    versions = {
        name: importlib.metadata.version(name)
        for name in [
            "pandas",
            "openpyxl",
            "numpy",
            "scikit-learn",
            "streamlit",
            "plotly",
            "matplotlib",
            "Pillow",
            "PyYAML",
            "joblib",
        ]
    }
    checks = {
        "unit_tests": result.wasSuccessful(),
        "dashboard": dashboard["status"] == "passed",
        "health": health["status"] == "passed",
        "sqlite_integrity": catalog["integrity_check"] == "ok",
        "foreign_keys": not catalog["foreign_key_violations"],
        "one_active_model": active == 1,
        "no_running_jobs": running == 0,
    }
    summary = {
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if all(checks.values()) else "failed",
        "tests_run": result.testsRun,
        "tests_passed": result.testsRun
        - len(result.failures)
        - len(result.errors)
        - len(result.skipped),
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "checks": checks,
        "dashboard": dashboard,
        "health": health,
        "versions": versions,
        "python": sys.version,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "fixture_scope": "Sintéticos somente em cópias temporárias para testes; não são evidência de realizados reais.",
    }
    (evidence / "37_post_mvp_qa.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # O QA registra as versões no JSON; não reescreve o contrato de instalação.
    print(
        json.dumps(
            {"status": summary["status"], "tests_run": result.testsRun, "checks": checks},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
