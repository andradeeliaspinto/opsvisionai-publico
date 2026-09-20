"""Figuras de evidência (não screenshots), derivadas do SQLite e do QA executado."""

from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.configuration import database_path

EVIDENCE = ROOT / "evidence"
NAVY, BLUE, PURPLE, ORANGE = "#102C54", "#2384C6", "#775BA6", "#E59431"


def read(query):
    with closing(
        sqlite3.connect(
            f"{database_path(ROOT / 'config/project.yaml').as_uri()}?mode=ro", uri=True
        )
    ) as con:
        return pd.read_sql_query(query, con)


def save(fig, name):
    fig.text(
        0.025,
        0.025,
        "OpsVisionAI / DataSapiens · Evidência extraída do SQLite; não é screenshot do dashboard.",
        fontsize=9,
        color="#566278",
    )
    fig.savefig(EVIDENCE / name, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    jobs = read(
        "SELECT job_id,job_type,started_at,finished_at,duration_seconds,status,records_processed,model_version,error_message FROM pipeline_job_runs ORDER BY started_at"
    )
    models = read(
        "SELECT model_version,algorithm,status,evaluation_mae,baseline_mae,decision_reason FROM registered_models ORDER BY trained_at"
    )
    alerts = read("SELECT * FROM operational_alerts ORDER BY generated_at,horizon")
    forecast = read("SELECT * FROM v_recommended_forecast ORDER BY horizon")
    backtest = read("SELECT * FROM backtest_predictions")
    deliveries = read("SELECT * FROM integration_delivery_log ORDER BY attempted_at")
    for name, frame in [
        ("40_job_history.csv", jobs),
        ("31_model_registry.csv", read("SELECT * FROM registered_models")),
        ("32_promotion_history.csv", read("SELECT * FROM model_promotion_history")),
        ("40_alert_history.csv", alerts),
        ("40_delivery_history.csv", deliveries),
    ]:
        frame.to_csv(EVIDENCE / name, index=False)
    qa = json.loads((EVIDENCE / "37_post_mvp_qa.json").read_text(encoding="utf-8"))
    live_count = int(
        read(
            "SELECT count(*) AS n FROM forecast_predictions p JOIN daily_actuals a ON a.actual_date=p.forecast_date WHERE p.prediction_generated_at < p.forecast_date AND p.data_cutoff_date < p.forecast_date"
        ).iloc[0]["n"]
    )
    decision = json.loads((EVIDENCE / "30_retrain_decision.json").read_text(encoding="utf-8"))
    fig, axes = plt.subplots(2, 1, figsize=(13, 8), gridspec_kw={"height_ratios": [1, 1.4]})
    fig.suptitle(
        "Pós-MVP executado e validado",
        fontsize=23,
        fontweight="bold",
        color=NAVY,
        x=0.06,
        ha="left",
    )
    axes[0].axis("off")
    active = models.loc[models.status == "ACTIVE", "model_version"].iloc[0]
    dashboard = qa["dashboard"]
    delivery_modes = ", ".join(sorted(deliveries["mode"].unique())) or "sem entregas"
    text = (
        f"{qa['tests_passed']}/{qa['tests_run']} testes aprovados  |  "
        f"AppTest: {len(dashboard['tabs'])} abas, {len(dashboard['exceptions'])} exceções\n"
        f"Champion: {active}\n"
        f"Última decisão: {decision['decision']} · novos realizados: {decision['new_actuals_count']}\n"
        f"Monitoramento LIVE: {live_count} previsões elegíveis · integração: {delivery_modes}"
    )
    axes[0].text(0.015, 0.85, text, va="top", fontsize=14, color=NAVY, linespacing=1.9)
    axes[1].axis("off")
    display = jobs.tail(7)[
        ["job_type", "started_at", "status", "duration_seconds", "records_processed"]
    ].copy()
    display["started_at"] = display["started_at"].str[:19].str.replace("T", " ")
    display["duration_seconds"] = display["duration_seconds"].map(lambda x: f"{x:.2f}s")
    display["records_processed"] = display["records_processed"].fillna("—")
    table = axes[1].table(
        cellText=display.values,
        colLabels=["Job", "Início UTC", "Status", "Duração", "Registros"],
        loc="center",
        cellLoc="left",
        colWidths=[0.24, 0.28, 0.15, 0.15, 0.18],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1, 2)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#D9E4EF")
        if row == 0:
            cell.set_facecolor(NAVY)
            cell.set_text_props(color="white", weight="bold")
    fig.subplots_adjust(top=0.9, bottom=0.1, hspace=0.1)
    save(fig, "40_execution_evidence.png")

    model_error = (backtest["model_forecast"] - backtest["actual"]).abs()
    baseline_error = (backtest["baseline_forecast"] - backtest["actual"]).abs()
    metrics = (
        pd.DataFrame(
            {"horizon": backtest.horizon, "Ridge": model_error, "Baseline": baseline_error}
        )
        .groupby("horizon")
        .mean()
    )
    metrics.to_csv(EVIDENCE / "41_verified_horizon_metrics.csv")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.8))
    metrics.plot.bar(ax=axes[0], color=[BLUE, PURPLE], rot=0)
    axes[0].set_title("Backtest histórico · 20/10 a 31/12/2025", color=NAVY)
    axes[0].set_xlabel("Horizonte D+")
    axes[0].set_ylabel("MAE · incidentes")
    thresholds = json.loads((EVIDENCE / "33_alert_thresholds.json").read_text(encoding="utf-8"))["thresholds"]
    axes[1].plot(
        forecast.horizon,
        forecast.predicted_incidents,
        marker="o",
        color=BLUE,
        label="Ridge persistido",
    )
    axes[1].axhline(
        thresholds["p75"], color=ORANGE, linestyle="--", label=f"P75 = {thresholds['p75']:.0f}"
    )
    axes[1].axhline(
        thresholds["p90"], color=PURPLE, linestyle=":", label=f"P90 = {thresholds['p90']:.1f}"
    )
    axes[1].set_title("Forecast · 01/01 a 07/01/2026", color=NAVY)
    axes[1].set_xlabel("Horizonte D+")
    axes[1].set_ylabel("Incidentes previstos")
    axes[1].legend(loc="upper right")
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.2)
    fig.suptitle(
        "Histórico avaliado e forecast sem novos realizados",
        fontsize=19,
        color=NAVY,
        fontweight="bold",
    )
    fig.subplots_adjust(bottom=0.17, top=0.83, wspace=0.25)
    save(fig, "41_monitoring_alerts_evidence.png")

    fig, ax = plt.subplots(figsize=(13, 10))
    ax.axis("off")
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.3, 10)
    fig.suptitle("Arquitetura pós-MVP implementada", fontsize=22, fontweight="bold", color=NAVY)

    def box(x, y, label, color=BLUE):
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                3.6,
                0.7,
                boxstyle="round,pad=.08",
                facecolor="#F1F6FB",
                edgecolor=color,
                linewidth=1.5,
            )
        )
        ax.text(x + 1.8, y + 0.35, label, ha="center", va="center", fontsize=11, color=NAVY)

    def arrow(x, y, x2, y2):
        ax.annotate(
            "",
            xy=(x2, y2),
            xytext=(x, y),
            arrowprops={"arrowstyle": "->", "color": "#71849A", "lw": 1.4},
        )

    left = [
        "Entrypoint diário · lock e jobs",
        "Ingestão SHA + preparação",
        "Inferência com ACTIVE",
        "SQLite + histórico de forecasts",
        "Monitoramento + motor de alertas",
        "Repository read-only",
        "Streamlit · seis abas",
    ]
    right = [
        "Retreino sob demanda",
        "Seleção interna temporal",
        "Holdout comum + baseline",
        "Política Champion × Challenger",
        "Registry + decisão transacional",
    ]
    for i, label in enumerate(left):
        y = 8.6 - i * 1.2
        box(0.3, y, label)
        if i:
            arrow(2.1, y + 1.2, 2.1, y + 0.78)
    for i, label in enumerate(right):
        y = 8.6 - i * 1.2
        box(5.8, y, label, PURPLE)
        if i:
            arrow(7.6, y + 1.2, 7.6, y + 0.78)
    arrow(5.72, 4.15, 3.98, 6.55)
    box(5.8, 2.1, "Adapter + payload dry-run", ORANGE)
    arrow(3.98, 4.15, 5.72, 2.45)
    ax.text(
        7.6,
        0.8,
        "Sem envio externo\nSem novos realizados após 31/12/2025",
        ha="center",
        fontsize=11,
        color=NAVY,
    )
    save(fig, "42_post_mvp_architecture.png")
    snapshot = {
        "latest_inference_run_id": forecast.inference_run_id.iloc[0],
        "forecast": forecast[
            ["forecast_date", "horizon", "predicted_incidents", "model_version"]
        ].to_dict("records"),
        "jobs": len(jobs),
        "alerts": len(alerts),
        "dry_run_deliveries": int((deliveries["mode"] == "DRY_RUN").sum()),
        "active_model": active,
        "registered_models": len(models),
        "historical_model_mae": float(model_error.mean()),
        "historical_baseline_mae": float(baseline_error.mean()),
        "operational_live_evaluated": live_count,
        "source_cutoff": str(
            read("SELECT max(actual_date) AS cutoff FROM daily_actuals").iloc[0]["cutoff"]
        ),
    }
    (EVIDENCE / "43_post_mvp_snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in snapshot.items() if k != "forecast"}, ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    main()
