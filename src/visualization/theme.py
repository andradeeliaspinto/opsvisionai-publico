"""Cores, imagens e estilos usados nos gráficos e no dashboard.

Os caminhos são resolvidos a partir deste arquivo para que o projeto funcione
independentemente do diretório corrente usado para iniciar o Python/Streamlit.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "assets"
LOGO_PATH = ASSETS_DIR / "opsvisionai_logo_transparent.png"
WATERMARK_PATH = ASSETS_DIR / "opsvisionai_symbol_watermark_16pct.png"
STREAMLIT_ICON_PATH = ASSETS_DIR / "opsvisionai_streamlit_icon_512.png"

OPSVISION_COLORS = {
    "navy": "#03123A",
    "dark_blue": "#0D276F",
    "royal_blue": "#0F46AF",
    "primary_blue": "#0869D2",
    "cyan": "#0F9BF0",
    "violet": "#3C30B6",
    "light_blue": "#C2D1E7",
    "slate": "#7181A2",
    "background": "#F7F7F7",
    "white": "#FFFFFF",
}

OPSVISION_CATEGORICAL = [
    "#0F46AF",
    "#0F9BF0",
    "#3C30B6",
    "#0869D2",
    "#0D276F",
    "#7181A2",
]

OPSVISION_SEQUENTIAL = [
    "#C2D1E7",
    "#0F9BF0",
    "#0869D2",
    "#0F46AF",
    "#0D276F",
    "#03123A",
]

STATUS_COLORS = {
    "success": "#168C7A",
    "warning": "#D98E04",
    "critical": "#C23B4A",
}


def validate_visual_assets() -> dict[str, Path]:
    """Valida e devolve os três assets oficiais exigidos pelo produto."""

    assets = {
        "logo": LOGO_PATH,
        "watermark": WATERMARK_PATH,
        "streamlit_icon": STREAMLIT_ICON_PATH,
    }
    missing = [str(path) for path in assets.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Assets oficiais do OpsVisionAI não encontrados: " + ", ".join(missing)
        )
    return assets


def configure_matplotlib_theme() -> None:
    """Configura o tema global Matplotlib sem modificar dados ou escalas."""

    import matplotlib as mpl
    from cycler import cycler

    mpl.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10.5,
            "text.color": OPSVISION_COLORS["navy"],
            "axes.labelcolor": OPSVISION_COLORS["navy"],
            "axes.titlecolor": OPSVISION_COLORS["navy"],
            "axes.titlesize": 15,
            "axes.titleweight": 700,
            "axes.titlepad": 14,
            "axes.labelsize": 11,
            "axes.labelpad": 8,
            "axes.facecolor": OPSVISION_COLORS["white"],
            "figure.facecolor": OPSVISION_COLORS["white"],
            "savefig.facecolor": OPSVISION_COLORS["white"],
            "axes.edgecolor": OPSVISION_COLORS["light_blue"],
            "axes.linewidth": 0.8,
            "axes.grid": True,
            "axes.axisbelow": True,
            "axes.prop_cycle": cycler(color=OPSVISION_CATEGORICAL),
            "grid.color": OPSVISION_COLORS["light_blue"],
            "grid.alpha": 0.42,
            "grid.linewidth": 0.7,
            "xtick.color": OPSVISION_COLORS["slate"],
            "ytick.color": OPSVISION_COLORS["slate"],
            "xtick.labelsize": 9.5,
            "ytick.labelsize": 9.5,
            "legend.frameon": False,
            "legend.fontsize": 9.5,
            "lines.linewidth": 2.3,
            "lines.markersize": 6,
            "figure.dpi": 120,
            "savefig.dpi": 240,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.16,
        }
    )


@lru_cache(maxsize=1)
def _watermark_array() -> Any:
    validate_visual_assets()
    import matplotlib.image as mpimg

    return mpimg.imread(WATERMARK_PATH)


def add_matplotlib_watermark(ax: Any, width_fraction: float = 0.115) -> Any:
    """Adiciona a marca oficial no canto inferior direito de um eixo Matplotlib.

    A imagem já contém transparência de 16%; nenhuma opacidade adicional é
    aplicada. O símbolo é desenhado abaixo das séries para preservar a leitura.
    """

    image = _watermark_array()
    figure = ax.figure
    figure.canvas.draw()
    bbox = ax.get_window_extent()
    image_ratio = image.shape[0] / image.shape[1]
    height_fraction = width_fraction * (bbox.width / bbox.height) * image_ratio
    x_right = 0.985
    y_bottom = 0.025
    x_left = x_right - width_fraction
    y_top = min(y_bottom + height_fraction, 0.32)
    x_limits = ax.get_xlim()
    y_limits = ax.get_ylim()
    artist = ax.imshow(
        image,
        extent=(x_left, x_right, y_bottom, y_top),
        transform=ax.transAxes,
        interpolation="antialiased",
        aspect="auto",
        zorder=0.25,
        clip_on=True,
    )
    ax.set_xlim(x_limits)
    ax.set_ylim(y_limits)
    return artist


@lru_cache(maxsize=1)
def _watermark_data_uri() -> str:
    validate_visual_assets()
    encoded = base64.b64encode(WATERMARK_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def add_plotly_watermark(figure: Any) -> Any:
    """Adiciona a marca oficial a uma figura Plotly usando um data URI portátil."""

    figure.add_layout_image(
        {
            "source": _watermark_data_uri(),
            "xref": "paper",
            "yref": "paper",
            "x": 0.99,
            "y": 0.025,
            "sizex": 0.12,
            "sizey": 0.18,
            "xanchor": "right",
            "yanchor": "bottom",
            "sizing": "contain",
            "opacity": 1.0,
            "layer": "below",
        }
    )
    return figure


def apply_plotly_theme(figure: Any, *, watermark: bool = True) -> Any:
    """Aplica tipografia, grid, margens e semântica visual global ao Plotly."""

    figure.update_layout(
        template="plotly_white",
        colorway=OPSVISION_CATEGORICAL,
        font={"family": "Arial, sans-serif", "size": 13, "color": OPSVISION_COLORS["navy"]},
        title={"font": {"size": 20, "color": OPSVISION_COLORS["navy"]}, "x": 0.01},
        paper_bgcolor=OPSVISION_COLORS["white"],
        plot_bgcolor=OPSVISION_COLORS["white"],
        hoverlabel={
            "bgcolor": OPSVISION_COLORS["white"],
            "bordercolor": OPSVISION_COLORS["light_blue"],
            "font": {"color": OPSVISION_COLORS["navy"]},
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0.0,
            "title_text": "",
        },
        margin={"l": 58, "r": 26, "t": 76, "b": 54},
    )
    figure.update_xaxes(
        showgrid=False,
        linecolor=OPSVISION_COLORS["light_blue"],
        tickfont={"color": OPSVISION_COLORS["slate"]},
        title_font={"color": OPSVISION_COLORS["navy"]},
        zeroline=False,
    )
    figure.update_yaxes(
        showgrid=True,
        gridcolor="rgba(194, 209, 231, 0.55)",
        linecolor=OPSVISION_COLORS["light_blue"],
        tickfont={"color": OPSVISION_COLORS["slate"]},
        title_font={"color": OPSVISION_COLORS["navy"]},
        zeroline=False,
    )
    figure.update_traces(
        line={"width": 2.5},
        marker={"size": 7},
        selector={"type": "scatter"},
    )
    if watermark:
        add_plotly_watermark(figure)
    return figure


def add_opsvision_watermark(target: Any) -> Any:
    """Despacha a aplicação da marca para Matplotlib ou Plotly."""

    if hasattr(target, "add_layout_image"):
        return add_plotly_watermark(target)
    if hasattr(target, "imshow") and hasattr(target, "transAxes"):
        return add_matplotlib_watermark(target)
    raise TypeError("Objeto não reconhecido como eixo Matplotlib ou figura Plotly.")


def get_streamlit_css() -> str:
    """CSS central do dashboard, com contraste e hierarquia para leitura 24x7."""

    return f"""
    <style>
      :root {{
        --ops-navy: {OPSVISION_COLORS["navy"]};
        --ops-dark-blue: {OPSVISION_COLORS["dark_blue"]};
        --ops-blue: {OPSVISION_COLORS["primary_blue"]};
        --ops-cyan: {OPSVISION_COLORS["cyan"]};
        --ops-violet: {OPSVISION_COLORS["violet"]};
        --ops-light-blue: {OPSVISION_COLORS["light_blue"]};
        --ops-slate: {OPSVISION_COLORS["slate"]};
        --ops-background: {OPSVISION_COLORS["background"]};
      }}
      .stApp {{ background: var(--ops-background); color: var(--ops-navy); }}
      [data-testid="stHeader"] {{ background: rgba(247, 247, 247, 0.94); }}
      [data-testid="stSidebar"] {{
        background: {OPSVISION_COLORS["white"]};
        border-right: 1px solid var(--ops-light-blue);
      }}
      [data-testid="stSidebar"] [data-testid="stImage"] {{ margin: 0.25rem auto 1rem; }}
      h1, h2, h3, h4, h5, h6 {{ color: var(--ops-navy); letter-spacing: -0.01em; }}
      h1 {{ font-weight: 750; }}
      a {{ color: var(--ops-blue); }}
      [data-testid="stCaptionContainer"] {{ color: var(--ops-slate); }}
      [data-testid="stMetric"] {{
        background: {OPSVISION_COLORS["white"]};
        border: 1px solid var(--ops-light-blue);
        border-left: 4px solid var(--ops-blue);
        border-radius: 10px;
        padding: 0.9rem 1rem;
        min-height: 112px;
      }}
      [data-testid="stMetricLabel"] {{ color: var(--ops-slate); }}
      [data-testid="stMetricValue"] {{ color: var(--ops-navy); font-weight: 720; }}
      [data-baseweb="tab-list"] {{ gap: 0.35rem; border-bottom: 1px solid var(--ops-light-blue); }}
      [data-baseweb="tab"] {{
        color: var(--ops-slate);
        background: transparent;
        border-radius: 8px 8px 0 0;
        padding-left: 1rem;
        padding-right: 1rem;
      }}
      [aria-selected="true"][data-baseweb="tab"] {{ color: var(--ops-navy); font-weight: 700; }}
      [data-baseweb="tab-highlight"] {{ background-color: var(--ops-blue); }}
      [data-testid="stDataFrame"], [data-testid="stTable"] {{
        border: 1px solid var(--ops-light-blue);
        border-radius: 9px;
        overflow: hidden;
      }}
      [data-testid="stPlotlyChart"] {{
        background: {OPSVISION_COLORS["white"]};
        border: 1px solid rgba(194, 209, 231, 0.75);
        border-radius: 10px;
        padding: 0.2rem;
      }}
      [data-testid="stAlert"] {{ border-radius: 9px; }}
      hr {{ border-color: var(--ops-light-blue); }}
      .opsvision-accent {{
        width: 76px;
        height: 4px;
        margin: -0.3rem 0 1rem;
        background: var(--ops-cyan);
        border-radius: 999px;
      }}
      .opsvision-sidebar-note {{
        color: var(--ops-slate);
        font-size: 0.82rem;
        line-height: 1.45;
      }}
    </style>
    """
