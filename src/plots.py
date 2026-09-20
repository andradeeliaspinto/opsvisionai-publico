from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "opsvision-matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.visualization import (
    OPSVISION_COLORS,
    add_matplotlib_watermark,
    configure_matplotlib_theme,
)

OBSERVED_COLOR = OPSVISION_COLORS["navy"]
MODEL_COLOR = OPSVISION_COLORS["primary_blue"]
BASELINE_COLOR = OPSVISION_COLORS["violet"]
HIGHLIGHT_COLOR = OPSVISION_COLORS["cyan"]
SECONDARY_COLOR = OPSVISION_COLORS["slate"]

configure_matplotlib_theme()


def _style_axes(ax, *, grid_axis: str = "y") -> None:
    ax.grid(False)
    ax.grid(axis=grid_axis)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.margins(x=0.02)


def _set_title(ax, title: str, subtitle: str) -> None:
    ax.set_title(title, loc="left", pad=28)
    ax.text(
        0,
        1.015,
        subtitle,
        transform=ax.transAxes,
        color=SECONDARY_COLOR,
        fontsize=9.5,
        va="bottom",
    )


def _save(fig, ax, path: Path) -> None:
    fig.tight_layout(pad=1.2)
    add_matplotlib_watermark(ax)
    fig.savefig(path)
    plt.close(fig)


def generate_plots(root: str | Path = ".") -> None:
    root = Path(root)
    processed = root / "data/processed"
    evidence = root / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    model_summary = json.loads((evidence / "05_model_summary.json").read_text(encoding="utf-8"))

    daily = pd.read_csv(processed / "incident_count_daily.csv", parse_dates=["date"])
    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.plot(
        daily["date"],
        daily["incident_count"],
        color=OBSERVED_COLOR,
        linewidth=2.0,
        label="Realizado",
    )
    ax.axvline(
        pd.Timestamp(model_summary["test_start_date"]),
        color=HIGHLIGHT_COLOR,
        linestyle="--",
        linewidth=2.0,
        label="Início do teste",
    )
    _set_title(
        ax,
        "Volume diário de incidentes — janela analítica",
        "Série observada e limite da avaliação cronológica",
    )
    ax.set_xlabel("Data")
    ax.set_ylabel("Incidentes abertos")
    ax.legend(loc="upper left", ncol=2)
    _style_axes(ax)
    fig.autofmt_xdate(rotation=0)
    _save(fig, ax, evidence / "06_daily_series.png")

    weekday = pd.read_csv(processed / "weekday_summary.csv")
    labels = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    ax.bar(
        labels,
        weekday["mean"],
        color=OBSERVED_COLOR,
        edgecolor=OPSVISION_COLORS["white"],
        linewidth=0.8,
    )
    _set_title(
        ax,
        "Média de incidentes por dia da semana",
        "Perfil histórico usado pelo baseline sazonal de sete dias",
    )
    ax.set_xlabel("Dia da semana")
    ax.set_ylabel("Média diária")
    _style_axes(ax)
    _save(fig, ax, evidence / "07_weekday_profile.png")

    predictions = pd.read_csv(evidence / "03_test_predictions.csv")
    model_mae = (predictions["actual"] - predictions["model_forecast"]).abs().mean()
    baseline_mae = (predictions["actual"] - predictions["baseline_forecast"]).abs().mean()
    fig, ax = plt.subplots(figsize=(7, 4.8))
    bars = ax.bar(
        ["Modelo", "Baseline sazonal"],
        [model_mae, baseline_mae],
        color=[MODEL_COLOR, BASELINE_COLOR],
        edgecolor=OPSVISION_COLORS["white"],
        linewidth=0.8,
    )
    bars[1].set_hatch("//")
    _set_title(
        ax,
        "Erro no teste cronológico — menor é melhor",
        f"MAE em {model_summary['test_rolling_origins']} origens rolling-origin e horizontes D+1 a D+7",
    )
    ax.set_ylabel("MAE (incidentes)")
    _style_axes(ax)
    for bar, value in zip(bars, [model_mae, baseline_mae]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.45,
            f"{value:.2f}",
            ha="center",
            color=OPSVISION_COLORS["navy"],
            fontweight="bold",
        )
    _save(fig, ax, evidence / "08_model_vs_baseline.png")

    forecast = pd.read_csv(processed / "forecast_7_days.csv", parse_dates=["date"])
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.plot(
        forecast["date"],
        forecast["baseline_forecast"],
        marker="s",
        linestyle="--",
        color=BASELINE_COLOR,
        label="Baseline sazonal",
    )
    ax.plot(
        forecast["date"],
        forecast["model_forecast"],
        marker="o",
        linestyle="-",
        color=MODEL_COLOR,
        label=model_summary["selected_model"],
    )
    _set_title(
        ax,
        "Previsão de volume — D+1 a D+7",
        "Comparação dos dois métodos persistidos pelo job de inferência",
    )
    ax.set_xlabel("Data prevista")
    ax.set_ylabel("Incidentes previstos")
    ax.legend(loc="upper right", ncol=2)
    _style_axes(ax)
    fig.autofmt_xdate(rotation=0)
    _save(fig, ax, evidence / "09_forecast_7_days.png")

    hourly = pd.read_csv(processed / "hourly_summary.csv")
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.bar(
        hourly["hour"],
        hourly["incident_count"],
        color=OBSERVED_COLOR,
        edgecolor=OPSVISION_COLORS["white"],
        linewidth=0.5,
    )
    _set_title(
        ax,
        "Distribuição das aberturas por hora",
        "Contagem histórica por hora de abertura do incidente",
    )
    ax.set_xlabel("Hora do dia")
    ax.set_ylabel("Incidentes abertos")
    ax.set_xticks(range(0, 24, 2))
    _style_axes(ax)
    _save(fig, ax, evidence / "11_hourly_profile.png")


if __name__ == "__main__":
    generate_plots()
