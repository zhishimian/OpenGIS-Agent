"""出版级微排版主题与 4 档偶数物理字阶工具。"""
from __future__ import annotations

import math
from typing import Any, Sequence

import matplotlib
from matplotlib import colors as mcolors
from matplotlib import patheffects as path_effects
from matplotlib import ticker as mticker
from matplotlib import transforms as mtransforms
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpecFromSubplotSpec, SubplotSpec
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Ellipse, FancyArrowPatch, FancyBboxPatch, Patch, Rectangle
from matplotlib.path import Path as MplPath
import numpy as np
from gis_agent.integrations.plotting.palettes import GEO_COLORS

def _snap_even(val: float, minimum: int = 10) -> int:
    snapped = int(round(float(val) / 2.0) * 2)
    return max(int(minimum), snapped)


def _resolve_pt(explicit: float | None, rc_key: str, fallback: float) -> float:
    if explicit is not None:
        return float(explicit)
    raw = matplotlib.rcParams.get(rc_key, fallback)
    try:
        val = float(raw)
        if math.isfinite(val) and val > 0:
            return val
    except (TypeError, ValueError):
        pass
    return float(fallback)


# ---------------------------------------------------------------------------
# 3. 六大可组合制图原语
# ---------------------------------------------------------------------------
def apply_publication_theme(
    style: str = "light_geo",
    font_scale: float = 1.0,
    *,
    fig_width: float | None = None,
    font_style: str | None = None,
) -> dict[str, Any]:
    """应用出版级微排版基线（4 档偶数大字阶；默认保留既有字体栈，可选 serif/sans 切换）。"""
    if font_scale <= 0 or not math.isfinite(font_scale):
        raise ValueError("font_scale 必须为正数。")
    if fig_width is not None and (fig_width <= 0 or not math.isfinite(fig_width)):
        raise ValueError("fig_width 必须为正数。")
    themes = {
        "light_geo": {
            "figure.facecolor": "#ffffff",
            "axes.facecolor": "#ffffff",
            "axes.edgecolor": "#4a4a4a",
            "axes.labelcolor": GEO_COLORS["text_primary"],
            "text.color": GEO_COLORS["text_primary"],
            "xtick.color": "#4a4a4a",
            "ytick.color": "#4a4a4a",
            "axes.spines.top": True,
            "axes.spines.right": True,
        },
        "editorial_warm": {
            "figure.facecolor": "#faf8f4",
            "axes.facecolor": "#faf8f4",
            "axes.edgecolor": "#524c44",
            "axes.labelcolor": "#22201d",
            "text.color": "#22201d",
            "xtick.color": "#524c44",
            "ytick.color": "#524c44",
            "axes.spines.top": True,
            "axes.spines.right": True,
        },
        "minimal_white": {
            "figure.facecolor": "#ffffff",
            "axes.facecolor": "#ffffff",
            "axes.edgecolor": "#7a7a7a",
            "axes.labelcolor": GEO_COLORS["text_primary"],
            "text.color": GEO_COLORS["text_primary"],
            "xtick.color": "#57606a",
            "ytick.color": "#57606a",
            "axes.spines.top": False,
            "axes.spines.right": False,
        },
    }
    if style not in themes:
        raise ValueError(f"未知主题 '{style}'；可选：{sorted(themes)}")

    if font_style is not None:
        from gis_agent.integrations.plotting.runtime import configure_plotting

        configure_plotting(font_style=font_style)

    width_factor = max(1.0, float(fig_width) / 8.5) if fig_width is not None else 1.0
    scale = float(font_scale) * width_factor
    t4 = _snap_even(10.0 * scale, 10)
    t3 = _snap_even(12.0 * scale, 12)
    t2 = _snap_even(14.0 * scale, 14)
    t1 = _snap_even(16.0 * scale, 16)
    sizes = {
        "T1": t1,
        "T2": t2,
        "T3": t3,
        "T4": t4,
        "title": t1,
        "panel_label": t2,
        "axis": t3,
        "legend": t3,
        "legend_title": t2,
        "tick": t4,
        "base": t3,
        "note": t4,
    }
    params = {
        **themes[style],
        "font.size": t3,
        "axes.titlesize": t1,
        "axes.titleweight": "bold",
        "axes.labelsize": t3,
        "xtick.labelsize": t4,
        "ytick.labelsize": t4,
        "legend.fontsize": t3,
        "legend.title_fontsize": t2,
        "axes.linewidth": 0.65,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "xtick.major.size": 3.2,
        "ytick.major.size": 3.2,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "axes.grid": False,
        "legend.frameon": False,
        "savefig.dpi": 300,
    }
    matplotlib.rcParams.update(params)
    return {"style": style, "fonts": sizes, "colors": dict(GEO_COLORS)}
