"""Sistema visual oficial do OpsVisionAI."""

from .theme import (
    ASSETS_DIR,
    LOGO_PATH,
    OPSVISION_CATEGORICAL,
    OPSVISION_COLORS,
    OPSVISION_SEQUENTIAL,
    STATUS_COLORS,
    STREAMLIT_ICON_PATH,
    WATERMARK_PATH,
    add_matplotlib_watermark,
    add_opsvision_watermark,
    add_plotly_watermark,
    apply_plotly_theme,
    configure_matplotlib_theme,
    get_streamlit_css,
    validate_visual_assets,
)

__all__ = [
    "ASSETS_DIR",
    "LOGO_PATH",
    "OPSVISION_CATEGORICAL",
    "OPSVISION_COLORS",
    "OPSVISION_SEQUENTIAL",
    "STATUS_COLORS",
    "STREAMLIT_ICON_PATH",
    "WATERMARK_PATH",
    "add_matplotlib_watermark",
    "add_opsvision_watermark",
    "add_plotly_watermark",
    "apply_plotly_theme",
    "configure_matplotlib_theme",
    "get_streamlit_css",
    "validate_visual_assets",
]
