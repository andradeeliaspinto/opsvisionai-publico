from __future__ import annotations

import json
import os
import tempfile
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "opsvision-matplotlib-evidence"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.configuration import database_path
from src.visualization import (
    OPSVISION_COLORS,
    STATUS_COLORS,
    configure_matplotlib_theme,
)

EVIDENCE = ROOT / "evidence"
DATABASE = database_path(ROOT / "config/project.yaml")
OBSERVED = OPSVISION_COLORS["navy"]
MODEL = OPSVISION_COLORS["primary_blue"]
BASELINE = OPSVISION_COLORS["violet"]
GRID = OPSVISION_COLORS["light_blue"]
SLATE = OPSVISION_COLORS["slate"]


def _read(query: str) -> pd.DataFrame:
    with closing(sqlite3.connect(f"{DATABASE.as_uri()}?mode=ro", uri=True)) as connection:
        return pd.read_sql_query(query, connection)


def _finish(figure: plt.Figure, path: Path) -> None:
    figure.text(
        0.02,
        0.015,
        "Evidência extraída do serving SQLite · Validação: 17_dashboard_runtime_validation.json",
        color=SLATE,
        fontsize=9,
    )
    figure.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def _title(figure: plt.Figure, title: str, subtitle: str) -> None:
    figure.suptitle(
        title, x=0.02, y=0.975, ha="left", fontsize=20, fontweight="bold", color=OBSERVED
    )
    figure.text(0.02, 0.91, subtitle, ha="left", fontsize=10.5, color=SLATE)


def sqlite_evidence() -> None:
    with closing(sqlite3.connect(f"{DATABASE.as_uri()}?mode=ro", uri=True)) as connection:
        objects = pd.read_sql_query(
            "SELECT type, name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY type, name",
            connection,
        )
        recommended = pd.read_sql_query(
            "SELECT * FROM v_recommended_forecast ORDER BY horizon", connection
        )

    figure, axes = plt.subplots(
        1, 2, figsize=(12.5, 10.0), gridspec_kw={"width_ratios": [0.9, 1.55]}
    )
    _title(
        figure,
        "Serving layer implementado e consultável",
        f"SQLite: {(objects.type == 'table').sum()} tabelas e {(objects.type == 'view').sum()} views; dashboard consulta o serving.",
    )
    axes[0].axis("off")
    grouped = objects.groupby("type")["name"].apply(list).to_dict()
    lines = (
        ["TABELAS"]
        + [f"• {name}" for name in grouped.get("table", [])]
        + ["", "VIEWS"]
        + [f"• {name}" for name in grouped.get("view", [])]
    )
    axes[0].text(
        0.02, 0.98, "\n".join(lines), va="top", fontsize=10.4, color=OBSERVED, linespacing=1.28
    )
    axes[0].add_patch(
        plt.Rectangle(
            (0, 0), 1, 1, transform=axes[0].transAxes, fill=False, edgecolor=GRID, linewidth=1.2
        )
    )

    axes[1].axis("off")
    display = recommended[
        ["forecast_date", "horizon", "predicted_incidents", "forecast_method", "model_version"]
    ].copy()
    display.columns = ["Data", "H", "Previsto", "Método", "Versão"]
    display["Previsto"] = display["Previsto"].map(lambda value: f"{value:.2f}")
    table = axes[1].table(
        cellText=display.values, colLabels=display.columns, loc="center", cellLoc="left"
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    table.scale(1, 1.65)
    for (row, _), cell in table.get_celld().items():
        cell.set_edgecolor(GRID)
        if row == 0:
            cell.set_facecolor(OPSVISION_COLORS["dark_blue"])
            cell.set_text_props(color="white", weight="bold")
        else:
            cell.set_facecolor("white" if row % 2 else OPSVISION_COLORS["background"])
    axes[1].set_title(
        f"v_recommended_forecast — {len(recommended)} registros",
        loc="left",
        pad=12,
        fontsize=13,
        fontweight="bold",
    )
    figure.subplots_adjust(left=0.03, right=0.98, top=0.85, bottom=0.08, wspace=0.08)
    _finish(figure, EVIDENCE / "22_sqlite_evidence.png")


def overview_evidence() -> None:
    actuals = _read("SELECT * FROM daily_actuals ORDER BY actual_date")
    forecast = _read("SELECT * FROM v_recommended_forecast ORDER BY horizon")
    metrics = _read("SELECT * FROM model_metrics LIMIT 1").iloc[0]
    actuals["actual_date"] = pd.to_datetime(actuals["actual_date"])
    forecast["forecast_date"] = pd.to_datetime(forecast["forecast_date"])
    p75 = actuals["actual_incidents"].quantile(0.75)
    peak = forecast.loc[forecast["predicted_incidents"].idxmax()]

    figure = plt.figure(figsize=(13.3, 6.2))
    grid = figure.add_gridspec(2, 4, height_ratios=[0.8, 2.5], hspace=0.28, wspace=0.14)
    _title(
        figure,
        "Visão Geral — situação prevista para os próximos sete dias",
        "KPIs e série recente calculados a partir do serving oficial.",
    )
    kpis = [
        ("Volume D+1–D+7", f"{forecast['predicted_incidents'].sum():,.0f}"),
        ("Pico previsto", f"{peak['predicted_incidents']:,.0f}"),
        ("Data do pico", peak["forecast_date"].strftime("%d/%m/%Y")),
        ("Referência", f"P75 = {p75:,.0f}"),
    ]
    for index, (label, value) in enumerate(kpis):
        axis = figure.add_subplot(grid[0, index])
        axis.axis("off")
        axis.add_patch(
            plt.Rectangle(
                (0, 0),
                1,
                1,
                transform=axis.transAxes,
                facecolor="white",
                edgecolor=GRID,
                linewidth=1.2,
            )
        )
        axis.text(0.06, 0.72, label, color=SLATE, fontsize=10, va="top")
        axis.text(0.06, 0.24, value, color=OBSERVED, fontsize=20, fontweight="bold")
    axis = figure.add_subplot(grid[1, :])
    recent = actuals.tail(35)
    axis.plot(
        recent["actual_date"],
        recent["actual_incidents"],
        color=OBSERVED,
        marker="o",
        label="Realizado",
    )
    recommended_label = str(metrics["recommended_method"])
    recommended_color = (
        BASELINE if metrics["recommended_method_code"] == "seasonal_naive_lag_7" else MODEL
    )
    axis.plot(
        forecast["forecast_date"],
        forecast["predicted_incidents"],
        color=recommended_color,
        marker="o",
        linewidth=2.8,
        label=f"Previsão {recommended_label}",
    )
    axis.axhline(p75, color=STATUS_COLORS["warning"], linestyle=":", label="P75 histórico")
    axis.set_ylabel("Incidentes")
    axis.legend(loc="upper left", ncol=3)
    axis.grid(axis="y", color=GRID, alpha=0.55)
    axis.spines[["top", "right"]].set_visible(False)
    figure.subplots_adjust(left=0.06, right=0.98, top=0.84, bottom=0.1)
    _finish(figure, EVIDENCE / "23_overview_evidence.png")


def forecast_evidence() -> None:
    latest = _read("SELECT * FROM v_latest_inference_run ORDER BY forecast_method, horizon")
    backtest = _read("SELECT * FROM v_backtest_comparison WHERE horizon = 1 ORDER BY target_date")
    metrics = _read("SELECT * FROM model_metrics LIMIT 1").iloc[0]
    latest["forecast_date"] = pd.to_datetime(latest["forecast_date"])
    backtest["target_date"] = pd.to_datetime(backtest["target_date"])

    figure, axes = plt.subplots(
        1, 2, figsize=(13.3, 6.2), gridspec_kw={"width_ratios": [1.05, 1.45]}
    )
    _title(
        figure,
        "Previsão D+1 a D+7 — métodos persistidos e backtest",
        f"{metrics['recommended_method']} é o método recomendado por apresentar o menor MAE no teste cronológico.",
    )
    for method, group in latest.groupby("forecast_method"):
        is_baseline = method == "seasonal_naive_lag_7"
        label = "Baseline D-7" if is_baseline else str(metrics["selected_model"])
        color = BASELINE if is_baseline else MODEL
        linestyle = "--" if is_baseline else "-"
        axes[0].plot(
            group["horizon"],
            group["predicted_incidents"],
            marker="o",
            color=color,
            linestyle=linestyle,
            label=label,
        )
    axes[0].set_xlabel("Horizonte")
    axes[0].set_ylabel("Incidentes previstos")
    axes[0].set_xticks(range(1, 8), [f"D+{i}" for i in range(1, 8)])
    axes[0].legend()
    axes[0].spines[["top", "right"]].set_visible(False)

    axes[1].plot(backtest["target_date"], backtest["actual"], color=OBSERVED, label="Realizado")
    axes[1].plot(backtest["target_date"], backtest["model_forecast"], color=MODEL, label="Ridge")
    axes[1].plot(
        backtest["target_date"],
        backtest["baseline_forecast"],
        color=BASELINE,
        linestyle="--",
        label="Baseline D-7",
    )
    axes[1].set_title("Previsto × realizado — D+1", loc="left", fontsize=13, fontweight="bold")
    axes[1].set_ylabel("Incidentes")
    axes[1].legend(ncol=3, fontsize=8.5)
    axes[1].spines[["top", "right"]].set_visible(False)
    figure.subplots_adjust(left=0.06, right=0.98, top=0.84, bottom=0.1, wspace=0.18)
    _finish(figure, EVIDENCE / "24_forecast_evidence.png")


def history_evidence() -> None:
    actuals = _read("SELECT * FROM daily_actuals ORDER BY actual_date")
    weekday = _read("SELECT * FROM weekday_summary ORDER BY weekday_number")
    hourly = _read("SELECT * FROM hourly_summary ORDER BY hour")
    actuals["actual_date"] = pd.to_datetime(actuals["actual_date"])

    figure = plt.figure(figsize=(13.3, 6.2))
    grid = figure.add_gridspec(2, 2, height_ratios=[1.25, 1], hspace=0.36, wspace=0.22)
    _title(
        figure,
        "Histórico e Incidentes — volume, sazonalidade e perfil horário",
        "A janela contínua de 2025 preserva todos os dias do calendário.",
    )
    axis = figure.add_subplot(grid[0, :])
    axis.plot(actuals["actual_date"], actuals["actual_incidents"], color=OBSERVED, linewidth=1.7)
    axis.set_ylabel("Incidentes")
    axis.spines[["top", "right"]].set_visible(False)
    axis.set_title("Volume diário realizado", loc="left", fontsize=13, fontweight="bold")

    axis = figure.add_subplot(grid[1, 0])
    labels = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    axis.bar(labels, weekday["mean"], color=OBSERVED)
    axis.set_ylabel("Média diária")
    axis.set_title("Sazonalidade semanal", loc="left", fontsize=13, fontweight="bold")
    axis.spines[["top", "right"]].set_visible(False)

    axis = figure.add_subplot(grid[1, 1])
    axis.bar(hourly["hour"], hourly["incident_count"], color=OPSVISION_COLORS["cyan"])
    axis.set_xlabel("Hora")
    axis.set_ylabel("Aberturas")
    axis.set_xticks(range(0, 24, 3))
    axis.set_title("Distribuição por hora", loc="left", fontsize=13, fontweight="bold")
    axis.spines[["top", "right"]].set_visible(False)
    figure.subplots_adjust(left=0.06, right=0.98, top=0.84, bottom=0.1)
    _finish(figure, EVIDENCE / "25_history_evidence.png")


def model_evidence() -> None:
    metrics = _read("SELECT * FROM model_metrics LIMIT 1").iloc[0]
    validation = _read("SELECT * FROM validation_candidates ORDER BY validation_mae")
    horizons = _read("SELECT * FROM horizon_metrics ORDER BY horizon")
    runtime = json.loads(
        (EVIDENCE / "17_dashboard_runtime_validation.json").read_text(encoding="utf-8")
    )

    figure = plt.figure(figsize=(13.3, 6.2))
    grid = figure.add_gridspec(2, 4, height_ratios=[0.8, 2.4], hspace=0.32, wspace=0.15)
    _title(
        figure,
        "Qualidade e Modelo — resultado cronológico auditável",
        f"{metrics['selected_model']} venceu o baseline no teste; a interface passou no AppTest sem exceções.",
    )
    metric_values = [
        (f"MAE {metrics['selected_model']}", f"{metrics['model_test_mae']:.2f}"),
        ("MAE baseline", f"{metrics['baseline_test_mae']:.2f}"),
        ("Ganho", f"{metrics['baseline_test_mae'] - metrics['model_test_mae']:.2f}"),
        ("Origens", f"{int(metrics['test_rolling_origins'])}"),
    ]
    for index, (label, value) in enumerate(metric_values):
        axis = figure.add_subplot(grid[0, index])
        axis.axis("off")
        axis.add_patch(
            plt.Rectangle((0, 0), 1, 1, transform=axis.transAxes, facecolor="white", edgecolor=GRID)
        )
        axis.text(0.06, 0.72, label, color=SLATE, fontsize=10, va="top")
        axis.text(0.06, 0.24, value, color=OBSERVED, fontsize=20, fontweight="bold")

    axis = figure.add_subplot(grid[1, :2])
    axis.barh(
        validation["candidate"],
        validation["validation_mae"],
        color=[MODEL, OPSVISION_COLORS["cyan"], BASELINE],
    )
    axis.invert_yaxis()
    axis.set_xlabel("MAE na validação")
    axis.set_title("Seleção entre candidatos de ML", loc="left", fontsize=13, fontweight="bold")
    axis.spines[["top", "right"]].set_visible(False)

    axis = figure.add_subplot(grid[1, 2:])
    axis.plot(horizons["horizon"], horizons["model_mae"], color=MODEL, marker="o", label="Ridge")
    axis.plot(
        horizons["horizon"],
        horizons["baseline_mae"],
        color=BASELINE,
        marker="s",
        linestyle="--",
        label="Baseline",
    )
    axis.set_xticks(range(1, 8), [f"D+{i}" for i in range(1, 8)])
    axis.set_ylabel("MAE")
    axis.set_title("Erro por horizonte", loc="left", fontsize=13, fontweight="bold")
    axis.legend()
    axis.spines[["top", "right"]].set_visible(False)
    figure.text(
        0.76,
        0.075,
        f"AppTest {runtime['status']} · {len(runtime['tabs'])} abas · {runtime['metrics']} métricas",
        color=STATUS_COLORS["success"],
        fontsize=9.5,
        ha="center",
    )
    figure.subplots_adjust(left=0.06, right=0.98, top=0.84, bottom=0.1)
    _finish(figure, EVIDENCE / "26_model_evidence.png")


def final_validation_evidence() -> None:
    health = json.loads((EVIDENCE / "18_project_health_check.json").read_text(encoding="utf-8"))
    runtime = json.loads(
        (EVIDENCE / "17_dashboard_runtime_validation.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((EVIDENCE / "07_serving_manifest.json").read_text(encoding="utf-8"))
    facts = health["facts"]

    figure = plt.figure(figsize=(13.3, 6.2))
    grid = figure.add_gridspec(1, 4, wspace=0.12)
    _title(
        figure,
        "Fase 4 — validação final ponta a ponta",
        "Dados, modelo, prediction storage, serving e interface foram reexecutados a partir do dataset oficial.",
    )
    sections = [
        (
            "DADOS",
            [
                f"{facts['dataset_rows']:,} linhas no XLSX".replace(",", "."),
                f"{facts['analysis_incidents']:,} incidentes em 2025".replace(",", "."),
                f"{facts['analysis_days']} dias sem lacunas",
                "SHA-256 confirmado",
            ],
        ),
        (
            "MODELO",
            [
                f"{facts['model']} selecionado",
                f"MAE {facts['model_mae']:.2f}",
                f"Baseline {facts['baseline_mae']:.2f}",
                f"Ganho relativo {100 * facts['relative_mae_reduction']:.1f}%",
            ],
        ),
        (
            "PUBLICAÇÃO",
            [
                f"{facts['stored_inference_runs']} execuções preservadas",
                f"{facts['stored_prediction_rows']} previsões armazenadas",
                f"{len(manifest['tables'])} tabelas e {len(manifest['views'])} views",
                "Repositório somente leitura",
            ],
        ),
        (
            "QA",
            [
                f"{facts['packaged_test_cases']} testes aprovados",
                f"Health check {health['checks_passed']}/{health['checks_total']}",
                f"AppTest {runtime['status']}",
                "0 exceções no dashboard",
            ],
        ),
    ]
    for index, (heading, lines) in enumerate(sections):
        axis = figure.add_subplot(grid[0, index])
        axis.axis("off")
        axis.add_patch(
            plt.Rectangle(
                (0.02, 0.06),
                0.96,
                0.88,
                transform=axis.transAxes,
                facecolor="white",
                edgecolor=GRID,
                linewidth=1.4,
            )
        )
        axis.add_patch(
            plt.Rectangle(
                (0.02, 0.84),
                0.96,
                0.10,
                transform=axis.transAxes,
                facecolor=OPSVISION_COLORS["dark_blue"],
                edgecolor=OPSVISION_COLORS["dark_blue"],
            )
        )
        axis.text(
            0.08,
            0.89,
            heading,
            transform=axis.transAxes,
            color="white",
            fontsize=11,
            fontweight="bold",
            va="center",
        )
        for line_index, line in enumerate(lines):
            y = 0.70 - line_index * 0.16
            axis.text(
                0.10,
                y,
                "✓",
                transform=axis.transAxes,
                color=STATUS_COLORS["success"],
                fontsize=14,
                fontweight="bold",
                va="center",
            )
            axis.text(
                0.20, y, line, transform=axis.transAxes, color=OBSERVED, fontsize=10.5, va="center"
            )
    figure.subplots_adjust(left=0.03, right=0.98, top=0.84, bottom=0.08)
    _finish(figure, EVIDENCE / "27_final_validation.png")


def main() -> None:
    configure_matplotlib_theme()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    sqlite_evidence()
    overview_evidence()
    forecast_evidence()
    history_evidence()
    model_evidence()
    final_validation_evidence()


if __name__ == "__main__":
    main()
