from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.configuration import database_path as configured_database_path

EXPECTED_TABS = [
    "Visão Geral",
    "Previsão D+1 a D+7",
    "Histórico e Incidentes",
    "Qualidade e Modelo",
    "Monitoramento do Modelo",
    "Operações e Alertas",
]


def _exception_message(element: object) -> str:
    for attribute in ("message", "value"):
        value = getattr(element, attribute, None)
        if value:
            return str(value)
    return str(element)


def validate_dashboard(output_path: Path) -> dict:
    try:
        import plotly  # noqa: F401
        import streamlit
        from streamlit.testing.v1 import AppTest
    except ImportError as exc:
        raise RuntimeError(
            "Dependências do dashboard ausentes. Ative o ambiente virtual e execute "
            "`python -m pip install -r requirements.txt`."
        ) from exc

    app_path = ROOT / "app.py"
    database_path = configured_database_path(ROOT / "config/project.yaml")
    if not database_path.exists():
        raise RuntimeError(
            "Serving store ausente. Execute `python run_pipeline.py` antes da validação."
        )

    app = AppTest.from_file(str(app_path), default_timeout=60)
    app.run()
    exceptions = [_exception_message(item) for item in app.exception]
    if exceptions:
        raise RuntimeError("O Streamlit registrou exceções: " + " | ".join(exceptions))

    tab_labels = [item.label for item in app.tabs]
    checks = {
        "expected_tabs": tab_labels == EXPECTED_TABS,
        "minimum_metrics": len(app.metric) >= 8,
        "minimum_dataframes": len(app.dataframe) >= 5,
        "horizon_selector": len(app.selectbox) >= 1,
        "historical_date_filter": len(app.date_input) >= 1,
        "title": bool(app.title) and app.title[0].value == "OpsVisionAI",
    }
    historical_filter = next(item for item in app.date_input if item.label == "Período histórico")
    original_range = historical_filter.value
    historical_filter.set_value((original_range[0],)).run()
    checks["partial_date_selection"] = not app.exception
    historical_filter = next(item for item in app.date_input if item.label == "Período histórico")
    historical_filter.set_value(()).run()
    checks["empty_date_selection"] = not app.exception
    historical_filter = next(item for item in app.date_input if item.label == "Período histórico")
    historical_filter.set_value(original_range).run()
    source = next(item for item in app.selectbox if item.label == "Origem da avaliação")
    source.select("Backtest histórico — Fase 4").run()
    checks["backtest_interaction"] = not app.exception and any(
        item.label == "MAE da seleção" for item in app.metric
    )
    source = next(item for item in app.selectbox if item.label == "Origem da avaliação")
    source.select("Operacional — realizados disponíveis").run()
    checks["live_empty_state"] = not app.exception and any(
        "Dados realizados ainda insuficientes" in item.value for item in app.info
    )
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError("Critérios funcionais não atendidos: " + ", ".join(failed))

    result = {
        "validated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "passed",
        "app": app_path.relative_to(ROOT).as_posix(),
        "serving_database": database_path.relative_to(ROOT).as_posix(),
        "streamlit_version": streamlit.__version__,
        "tabs": tab_labels,
        "metrics": len(app.metric),
        "dataframes": len(app.dataframe),
        "selectboxes": len(app.selectbox),
        "date_inputs": len(app.date_input),
        "exceptions": exceptions,
        "checks": checks,
        "scope_note": (
            "AppTest valida as seis abas e interação entre monitoramento operacional vazio e backtest histórico."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Valida o dashboard OpsVisionAI com Streamlit AppTest."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "evidence/17_dashboard_runtime_validation.json",
        help="Arquivo JSON gerado somente quando todos os critérios são aprovados.",
    )
    args = parser.parse_args()
    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    try:
        result = validate_dashboard(output_path)
    except Exception as exc:
        print(f"FALHA: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Evidência gravada em: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
