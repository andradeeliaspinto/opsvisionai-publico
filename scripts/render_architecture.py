"""Gera o diagrama histórico do MVP com Matplotlib.

Para a arquitetura pós-MVP, use scripts/generate_post_mvp_evidence.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.visualization.theme import OPSVISION_COLORS, configure_matplotlib_theme

PNG = ROOT / "evidence" / "12_architecture_revised.png"
SVG = ROOT / "evidence" / "12_architecture_revised.svg"


def box(ax, x, y, w, h, title, body, color):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.012,rounding_size=0.018",
        facecolor=OPSVISION_COLORS["white"],
        edgecolor=color,
        linewidth=1.8,
    )
    ax.add_patch(patch)
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            0.012,
            h,
            boxstyle="round,pad=0,rounding_size=0.006",
            facecolor=color,
            edgecolor=color,
        )
    )
    ax.text(
        x + 0.025,
        y + h - 0.045,
        title,
        ha="left",
        va="top",
        fontsize=10.5,
        weight="bold",
        color=OPSVISION_COLORS["navy"],
    )
    ax.text(
        x + 0.025,
        y + h - 0.095,
        body,
        ha="left",
        va="top",
        fontsize=8.4,
        linespacing=1.35,
        color=OPSVISION_COLORS["slate"],
    )
    return (x, y, w, h)


def arrow(ax, source, target, label=None):
    forward = target[0] >= source[0]
    x1 = source[0] + source[2] if forward else source[0]
    y1 = source[1] + source[3] / 2
    x2 = target[0] if forward else target[0] + target[2]
    y2 = target[1] + target[3] / 2
    ax.add_patch(
        FancyArrowPatch(
            (x1, y1),
            (x2, y2),
            arrowstyle="-|>",
            mutation_scale=13,
            color=OPSVISION_COLORS["light_blue"],
            linewidth=2.1,
        )
    )
    if label:
        ax.text(
            (x1 + x2) / 2,
            y1 + 0.025,
            label,
            ha="center",
            va="bottom",
            fontsize=7.5,
            color=OPSVISION_COLORS["slate"],
        )


def main():
    configure_matplotlib_theme()
    fig, ax = plt.subplots(figsize=(16, 8.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor(OPSVISION_COLORS["background"])
    ax.set_facecolor(OPSVISION_COLORS["background"])

    ax.text(
        0.04,
        0.95,
        "OpsVisionAI — arquitetura implementada do MVP",
        fontsize=21,
        weight="bold",
        color=OPSVISION_COLORS["navy"],
        va="top",
    )
    ax.text(
        0.04,
        0.905,
        "A fonte oficial percorre tratamento, modelagem, inferência persistida e serving antes de chegar ao dashboard.",
        fontsize=10.5,
        color=OPSVISION_COLORS["slate"],
        va="top",
    )

    w, h = 0.16, 0.18
    y1, y2, y3 = 0.65, 0.38, 0.11
    xs = [0.04, 0.235, 0.43, 0.625, 0.82]

    source = box(
        ax,
        xs[0],
        y1,
        w,
        h,
        "FONTE OFICIAL",
        "LW-DATASET.xlsx\naba Dataset Geral\n122.543 incidentes",
        OPSVISION_COLORS["slate"],
    )
    ingest = box(
        ax,
        xs[1],
        y1,
        w,
        h,
        "INGESTÃO",
        "acquire_data.py\nvalidação SHA-256\nmetadados",
        OPSVISION_COLORS["cyan"],
    )
    raw = box(
        ax,
        xs[2],
        y1,
        w,
        h,
        "RAW / BRONZE",
        "XLSX preservado\nsem sobrescrita\nfonte auditável",
        OPSVISION_COLORS["primary_blue"],
    )
    clean = box(
        ax,
        xs[3],
        y1,
        w,
        h,
        "CLEAN / SILVER",
        "schema normalizado\ndatas e prioridades\nausências explícitas",
        OPSVISION_COLORS["primary_blue"],
    )
    analytical = box(
        ax,
        xs[4],
        y1,
        w,
        h,
        "ANALYTICAL / GOLD",
        "série diária 2025\nresumos e 11 features",
        OPSVISION_COLORS["royal_blue"],
    )
    for a, b in zip([source, ingest, raw, clean], [ingest, raw, clean, analytical]):
        arrow(ax, a, b)

    features = box(
        ax,
        xs[4],
        y2,
        w,
        h,
        "FEATURES",
        "lags 1/7/14/28\nmédias móveis\ncalendário",
        OPSVISION_COLORS["royal_blue"],
    )
    training = box(
        ax,
        xs[3],
        y2,
        w,
        h,
        "MODEL TRAINING",
        "Ridge + candidatos\nbaseline D-7\nsplit cronológico",
        OPSVISION_COLORS["violet"],
    )
    evaluation = box(
        ax,
        xs[2],
        y2,
        w,
        h,
        "AVALIAÇÃO",
        "67 origens\n469 previsões\nMAE por horizonte",
        OPSVISION_COLORS["violet"],
    )
    registry = box(
        ax,
        xs[1],
        y2,
        w,
        h,
        "MODEL REGISTRY",
        "ridge_v1_20251231\n11 features\ncutoff 31/12/2025",
        OPSVISION_COLORS["violet"],
    )
    inference = box(
        ax,
        xs[0],
        y2,
        w,
        h,
        "INFERENCE JOB",
        "carrega modelo ativo\ngera D+1 a D+7\n14 registros por execução",
        OPSVISION_COLORS["primary_blue"],
    )
    for a, b in zip(
        [features, training, evaluation, registry], [training, evaluation, registry, inference]
    ):
        arrow(ax, a, b)
    ax.add_patch(
        FancyArrowPatch(
            (analytical[0] + analytical[2] / 2, analytical[1]),
            (features[0] + features[2] / 2, features[1] + features[3]),
            arrowstyle="-|>",
            mutation_scale=13,
            color=OPSVISION_COLORS["light_blue"],
            linewidth=2.1,
        )
    )

    storage = box(
        ax,
        xs[0],
        y3,
        w,
        h,
        "PREDICTION STORAGE",
        "run, origem e data-alvo\nhorizonte e valor\nversão + histórico",
        OPSVISION_COLORS["primary_blue"],
    )
    serving = box(
        ax,
        xs[1],
        y3,
        w,
        h,
        "SERVING LAYER",
        "SQLite local\n12 tabelas + 4 views\ncontrato curado",
        OPSVISION_COLORS["dark_blue"],
    )
    repo = box(
        ax,
        xs[2],
        y3,
        w,
        h,
        "ACESSO READ-ONLY",
        "ServingRepository\nconsultas sem treino\nnem inferência",
        OPSVISION_COLORS["dark_blue"],
    )
    dashboard = box(
        ax,
        xs[3],
        y3,
        w,
        h,
        "STREAMLIT",
        "4 áreas\nKPIs, filtros e gráficos\nidentidade oficial",
        OPSVISION_COLORS["cyan"],
    )
    user = box(
        ax,
        xs[4],
        y3,
        w,
        h,
        "COORDENADOR DO NOC",
        "capacidade\npriorização\npreparação operacional",
        OPSVISION_COLORS["navy"],
    )
    for a, b in zip([storage, serving, repo, dashboard], [serving, repo, dashboard, user]):
        arrow(ax, a, b)
    ax.add_patch(
        FancyArrowPatch(
            (inference[0] + inference[2] / 2, inference[1]),
            (storage[0] + storage[2] / 2, storage[1] + storage[3]),
            arrowstyle="-|>",
            mutation_scale=13,
            color=OPSVISION_COLORS["light_blue"],
            linewidth=2.1,
        )
    )

    ax.text(
        0.04,
        0.055,
        "Processamento local, previsões persistidas e dashboard conectado ao SQLite",
        fontsize=9,
        weight="bold",
        color=OPSVISION_COLORS["primary_blue"],
    )
    fig.savefig(PNG, dpi=200, bbox_inches="tight", pad_inches=0.2)
    fig.savefig(SVG, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)


if __name__ == "__main__":
    main()
