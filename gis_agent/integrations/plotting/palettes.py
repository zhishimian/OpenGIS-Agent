"""科学感知地理配色体系、语义中性 Token 与分布归一化工具。"""
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

# ---------------------------------------------------------------------------
# 1. 图底分离与语义中性色 Token（顶刊实证提炼）
# ---------------------------------------------------------------------------
GEO_COLORS: dict[str, str] = {
    "land_muted": "#f0f0f0",
    "land_warm": "#f3f1ec",
    "land_context": "#e5e5e5",
    "ocean_soft": "#e8f1f8",
    "ocean_clean": "#f4f8fb",
    "water_accent": "#7eb6d9",
    "border_muted": "#b8b8b8",
    "border_subtle": "#d0d0d0",
    "border_study": "#333333",
    "nodata_gray": "#d9d9d9",
    "zero_neutral": "#f7f7f7",
    "text_primary": "#1f2328",
    "text_secondary": "#57606a",
    "grid_muted": "#cccccc",
    "highlight_accent": "#d64541",
    "highlight_gold": "#e6ab02",
    "marker_low": "#e6e6e6",
    "marker_mid": "#e8b44c",
    "marker_high": "#d96f32",
    "marker_extreme": "#9e2234",
}

# 禁用失真/高饱和伪彩默认色带（Anti-Slop Guard）
BANNED_CMAPS: frozenset[str] = frozenset({
    "jet",
    "jet_r",
    "rainbow",
    "rainbow_r",
    "hsv",
    "hsv_r",
    "gist_rainbow",
    "gist_rainbow_r",
    "nipy_spectral",
    "nipy_spectral_r",
    "prism",
    "flag",
})

# ---------------------------------------------------------------------------
# 2. 精选科学色带库（Crameri + CARTOColors + Paul Tol + 期刊定性 + 双变量矩阵）
# ---------------------------------------------------------------------------
_CRAMERI_SEQUENTIAL_STOPS: dict[str, list[str]] = {
    "batlow": ["#011959", "#124761", "#2c665d", "#627941", "#a58b2c", "#e69858", "#fdb1ab", "#faccfa"],
    "lajolla": ["#191900", "#3c2614", "#783932", "#c04d49", "#e17750", "#eaa253", "#f5d369", "#fffecb"],
    "oslo": ["#010101", "#0f2133", "#194169", "#3364a1", "#6b8ec8", "#97a9c9", "#c7ccd3", "#ffffff"],
    "lapaz": ["#1a0c64", "#253681", "#305c98", "#487da3", "#7398a0", "#a5a795", "#e4c9b2", "#fef2f3"],
    "bilbao": ["#4c0001", "#7d2e34", "#9d5754", "#a5745b", "#ad9061", "#bbb287", "#cbcac1", "#ffffff"],
    "acton": ["#260d40", "#443766", "#625c88", "#8e648e", "#c26b94", "#d995b8", "#e6c5de", "#f0eafa"],
    "hawaii": ["#8c0273", "#933252", "#985638", "#9c7e20", "#94ae30", "#74ce79", "#61e6ca", "#b3f2fd"],
    "turku": ["#000000", "#2c2c27", "#53523e", "#797750", "#af9c68", "#dba886", "#f9bfb7", "#ffe6e6"],
}

SEQUENTIAL_PALETTES: dict[str, list[str]] = {
    **_CRAMERI_SEQUENTIAL_STOPS,
    "carto_teal": ["#d1eeea", "#a8dbd9", "#85c4c9", "#68abb8", "#4f90a6", "#3b738f", "#2a5674"],
    "carto_mint": ["#e4f1e1", "#b4d9cc", "#89c0b6", "#63a6a0", "#448c8a", "#287274", "#0d585f"],
    "carto_oryel": ["#ecda9a", "#efc47e", "#f3ad6a", "#f7945d", "#f97b57", "#f66356", "#ee4d5a"],
    "carto_peach": ["#fde0c5", "#facba6", "#f8b58b", "#f59e72", "#f2855d", "#ef6a4c", "#eb4a40"],
    "carto_burg": ["#ffc6c4", "#f4a3a8", "#e38191", "#cc607d", "#ad466c", "#8b3058", "#672044"],
    "carto_brwnyl": ["#ede5cf", "#e0c2a2", "#d39c83", "#c1766f", "#a65461", "#813753", "#541f3f"],
    "carto_bluyl": ["#f7feae", "#b7e6a5", "#7ccba2", "#46aea0", "#089099", "#00718b", "#045275"],
    "carto_emrld": ["#d3f2a3", "#97e196", "#6cc08b", "#4c9b82", "#217a79", "#105965", "#074050"],
    "carto_sunsetdark": ["#fcde9c", "#faa476", "#f0746e", "#e34f6f", "#dc3977", "#b9257a", "#7c1d6f"],
    "tol_iridescent": [
        "#fefbe9", "#fcf7d5", "#f5f3c1", "#eaf0b5", "#ddecbf", "#d0e7ca",
        "#c2e3d2", "#b5ddd8", "#a8d8dc", "#9bd2e1", "#8dcbe4", "#81c4e7",
        "#7bbce7", "#7eb2e4", "#88a5dd", "#9398d2", "#9b8ac4", "#9d7db2",
        "#9a709e", "#906388", "#805770", "#684957", "#46353a",
    ],
    "hypsometric": ["#d8e6cf", "#e7ecd1", "#f3eac2", "#e4cfa0", "#cca97f", "#b68e74", "#d6cfc7", "#f5f5f5"],
    "bathymetry": ["#ebf5fb", "#c6e2f2", "#99cae6", "#6baddb", "#408bc9", "#2466a8", "#13427d", "#09244d"],
    "nordic_snow": ["#cfe1ef", "#a9c8e0", "#7fa6ca", "#5682ad", "#36648f", "#23507a", "#163a5b", "#0c2338"],
    "slate_teal": ["#dceae8", "#b2d1ce", "#85b5b2", "#5c9593", "#3d7474", "#275658", "#163a3d"],
    "muted_ochre": ["#f2eadc", "#e0cca9", "#c8ab7c", "#ae8b57", "#8f6b3c", "#6e4f28", "#4d3519"],
    "sage_forest": ["#e5ece2", "#c3d5bc", "#9bbb93", "#739d6c", "#4f7e4b", "#335e32", "#1e4020"],
    "pub_dem_terrain": ["#6f9860", "#a6c576", "#e6de9c", "#d9af68", "#bc7344", "#8a4d32", "#d9d2cb"],
}

_CRAMERI_DIVERGING_STOPS: dict[str, list[str]] = {
    "vik": ["#001261", "#034a85", "#4b90b3", "#bdd6e3", "#e7c6b2", "#ca8258", "#9c3709", "#590008"],
    "roma": ["#7e1700", "#a05f1b", "#be9d3e", "#d2de98", "#9be2d5", "#46accc", "#2471b4", "#033198"],
    "bam": ["#65024b", "#ac4993", "#da93c8", "#f3dded", "#ebf1df", "#a3c67d", "#538735", "#0d4c00"],
    "broc": ["#2c1a4c", "#2a5183", "#6f92b3", "#c4d2e0", "#e4e4c8", "#aeae73", "#646434", "#262600"],
    "cork": ["#2c194c", "#2a5284", "#688db0", "#c0cfde", "#c8dbc8", "#71a071", "#266a25", "#0f2903"],
}

DIVERGING_PALETTES: dict[str, list[str]] = {
    **_CRAMERI_DIVERGING_STOPS,
    "tol_sunset": ["#364b9a", "#4a7bb7", "#6ea6cd", "#98cae1", "#c2e4ef", "#eaeccc", "#feda8b", "#fdb366", "#f67e4b", "#dd3d2d", "#a50026"],
    "tol_burd": ["#2166ac", "#4393c3", "#92c5de", "#d1e5f0", "#f7f7f7", "#fddbc7", "#f4a582", "#d6604d", "#b2182b"],
    "carto_geyser": ["#008080", "#70a494", "#b4c8a8", "#f6edbd", "#edbb8a", "#de8a5a", "#ca562c"],
    "carto_armyrose": ["#798234", "#a3ad62", "#d0d3a2", "#fdfbe4", "#f0c6c3", "#df91a3", "#d46780"],
    "carto_tealrose": ["#009392", "#72aaa1", "#b1c7b3", "#f1eac8", "#e5b9ad", "#d98994", "#d0587e"],
    "carto_earth": ["#a16928", "#bd925a", "#d6bd8d", "#edeac2", "#b5c8b8", "#79a7ac", "#2887a1"],
    "carto_temps": ["#009392", "#39b185", "#9ccb86", "#e9e29c", "#eeb479", "#e88471", "#cf597e"],
}

QUALITATIVE_PALETTES: dict[str, list[str]] = {
    "okabe_ito": ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#F0E442", "#000000"],
    "tol_muted": ["#332288", "#88CCEE", "#44AA99", "#117733", "#999933", "#DDCC77", "#CC6677", "#882255", "#AA4499"],
    "tol_bright": ["#4477AA", "#EE6677", "#228833", "#CCBB44", "#66CCEE", "#AA3377", "#BBBBBB"],
    "npg": ["#E64B35", "#4DBBD5", "#00A087", "#3C5488", "#F39B7F", "#8491B4", "#91D1C2", "#DC0000", "#7E6148", "#B09C85"],
    "lancet": ["#00468B", "#ED0000", "#42B540", "#0099B4", "#925E9F", "#FDAF91", "#AD002A", "#ADB6B6", "#1B1919"],
    "aaas": ["#3B4992", "#EE0000", "#008B45", "#631879", "#008280", "#BB0021", "#5F559B", "#A20056", "#808180", "#1B1919"],
    "jco": ["#0073C2", "#EFC000", "#868686", "#CD534C", "#7AA6DC", "#003C67", "#8F7700", "#3B3B3B", "#A73030", "#4A6990"],
    "carto_safe": ["#88CCEE", "#CC6677", "#DDCC77", "#117733", "#332288", "#AA4499", "#44AA99", "#999933", "#661100", "#6699CC", "#888888"],
    "carto_prism": ["#5F4690", "#1D6996", "#38A6A5", "#0F8554", "#73AF48", "#EDAD08", "#E17C05", "#CC503E", "#94346E", "#6F4070", "#994E95", "#666666"],
    "morandi_geo": ["#6B8E8E", "#C89B7B", "#8FA3B8", "#D4B483", "#A4849C", "#7D9B76", "#B87A7A", "#9E9A90"],
    "landcover_soft": ["#4D8C57", "#A3C585", "#DFC98A", "#C77A62", "#6CA6CD", "#8B7D7B", "#D9D9D9"],
    "pub_lulc": ["#e6c86b", "#2e7d32", "#81c784", "#4f92c3", "#d64541", "#c9b38c", "#b3d4e5"],
}


def build_bivariate_palette(
    c00: str = "#e8e8e8",
    c10: str = "#5ac8c8",
    c01: str = "#be64ac",
    c11: str = "#3b4994",
    n: int = 3,
) -> list[list[str]]:
    """按四角色彩进行双线性插值，生成 n×n 双变量二维 hex 矩阵（row 0=低Y，col 0=低X）。"""
    if n < 2 or n > 9:
        raise ValueError("双变量矩阵维度 n 必须在 [2, 9] 之间。")
    rgb00 = np.asarray(mcolors.to_rgb(c00), dtype=float)
    rgb10 = np.asarray(mcolors.to_rgb(c10), dtype=float)
    rgb01 = np.asarray(mcolors.to_rgb(c01), dtype=float)
    rgb11 = np.asarray(mcolors.to_rgb(c11), dtype=float)
    grid: list[list[str]] = []
    for row in range(n):
        v = row / (n - 1)
        row_colors: list[str] = []
        for col in range(n):
            u = col / (n - 1)
            rgb = (
                (1 - u) * (1 - v) * rgb00
                + u * (1 - v) * rgb10
                + (1 - u) * v * rgb01
                + u * v * rgb11
            )
            row_colors.append(mcolors.to_hex(np.clip(rgb, 0.0, 1.0)))
        grid.append(row_colors)
    return grid


BIVARIATE_PALETTES: dict[str, list[list[str]]] = {
    "stevens_pinkblue": [
        ["#e8e8e8", "#ace4e4", "#5ac8c8"],
        ["#dfb0d6", "#a5add3", "#5698b9"],
        ["#be64ac", "#8c62aa", "#3b4994"],
    ],
    "stevens_bluered": [
        ["#e8e8e8", "#e4acac", "#c85a5a"],
        ["#b0d5df", "#ad9ea5", "#985356"],
        ["#64acbe", "#627f8c", "#574249"],
    ],
    "stevens_greenblue": [
        ["#e8e8e8", "#b5c0da", "#6c83b5"],
        ["#b8d6be", "#90b2b3", "#567994"],
        ["#73ae80", "#5a9178", "#2a5a5b"],
    ],
    "stevens_purplegold": [
        ["#e8e8e8", "#e4d9ac", "#c8b35a"],
        ["#cbb8d7", "#c8ada0", "#af8e53"],
        ["#9972af", "#976b82", "#804d36"],
    ],
    "teal_terracotta": [
        ["#f2efe9", "#a3d3cf", "#2b8b8c"],
        ["#eab8a3", "#9b9d9c", "#2d6d78"],
        ["#d6684f", "#8a5a54", "#3b3746"],
    ],
    "bivariate_5x5_ocean_amber": build_bivariate_palette("#f2f2f2", "#1e78b4", "#e66101", "#2b1c47", n=5),
}

_CRAMERI_NAMES: frozenset[str] = frozenset(_CRAMERI_SEQUENTIAL_STOPS) | frozenset(_CRAMERI_DIVERGING_STOPS)


def list_palettes() -> dict[str, list[str]]:
    """返回内置所有类别下的全部可选色带名称。"""
    return {
        "sequential": sorted(SEQUENTIAL_PALETTES),
        "diverging": sorted(DIVERGING_PALETTES),
        "qualitative": sorted(QUALITATIVE_PALETTES),
        "bivariate": sorted(BIVARIATE_PALETTES),
    }


def _check_banned_cmap(name: str) -> None:
    cleaned = name.strip().lower()
    base = cleaned[:-2] if cleaned.endswith("_r") else cleaned
    if cleaned in BANNED_CMAPS or base in BANNED_CMAPS:
        raise ValueError(
            f"禁用失真/伪彩默认色带 '{name}'（感知非线性且对色觉障碍者不友好）。"
            "请改用 'batlow'、'vik'、'roma'、'carto_teal'、'tol_sunset' 或 'viridis' 等科学色带。"
        )


def _lookup_crameri_cmap(base_name: str):
    try:
        import cmcrameri.cm as cmc_cm
    except ImportError:
        return None
    cmap = getattr(cmc_cm, base_name, None)
    if cmap is None and hasattr(cmc_cm, "cmaps"):
        cmap = cmc_cm.cmaps.get(base_name)
    return cmap


def get_scientific_cmap(
    kind: str = "sequential",
    name: str | None = None,
    *,
    n: int | None = None,
    reverse: bool = False,
    nodata_color: str | None = GEO_COLORS["nodata_gray"],
    zero_anchored: bool = False,
    zero_color: str = GEO_COLORS["zero_neutral"],
):
    """获取经过科学感知校正的 Colormap，禁用 jet/rainbow 并内置 Tier A 回退。"""
    kind_norm = kind.strip().lower()
    if kind_norm not in {"sequential", "diverging", "qualitative", "categorical"}:
        raise ValueError(f"不支持的色带类型 '{kind}'；仅支持 sequential、diverging、qualitative。")

    defaults = {
        "sequential": "batlow",
        "diverging": "vik",
        "qualitative": "okabe_ito",
        "categorical": "okabe_ito",
    }
    raw_name = (name or defaults[kind_norm]).strip()
    _check_banned_cmap(raw_name)

    want_reverse = bool(reverse)
    base_name = raw_name
    if base_name.endswith("_r"):
        want_reverse = not want_reverse
        base_name = base_name[:-2]
    key = base_name.lower()

    cmap = None
    if key in _CRAMERI_NAMES or (
        key not in SEQUENTIAL_PALETTES
        and key not in DIVERGING_PALETTES
        and key not in QUALITATIVE_PALETTES
    ):
        cmap = _lookup_crameri_cmap(key)

    if cmap is None:
        if key in QUALITATIVE_PALETTES:
            colors = list(QUALITATIVE_PALETTES[key])
            if want_reverse:
                colors = colors[::-1]
            cmap = mcolors.ListedColormap(colors, name=raw_name)
        elif key in SEQUENTIAL_PALETTES:
            stops = list(SEQUENTIAL_PALETTES[key])
            if want_reverse:
                stops = stops[::-1]
            cmap = mcolors.LinearSegmentedColormap.from_list(raw_name, stops, N=256)
        elif key in DIVERGING_PALETTES:
            stops = list(DIVERGING_PALETTES[key])
            if want_reverse:
                stops = stops[::-1]
            cmap = mcolors.LinearSegmentedColormap.from_list(raw_name, stops, N=256)
        else:
            try:
                cmap = matplotlib.colormaps[raw_name]
                if reverse:
                    cmap = cmap.reversed()
            except KeyError as exc:
                raise ValueError(f"未知的科学色带名称：'{raw_name}'。可用色带见 list_palettes()。") from exc
            want_reverse = False

    if want_reverse and cmap is not None and key not in QUALITATIVE_PALETTES:
        if hasattr(cmap, "reversed"):
            cmap = cmap.reversed()

    if zero_anchored and kind_norm == "sequential" and key not in QUALITATIVE_PALETTES:
        z_rgb = np.array(mcolors.to_rgb(zero_color), dtype=float)
        c0_rgb = np.array(cmap(0.0)[:3], dtype=float)
        mid_rgb = tuple(np.clip(0.5 * (z_rgb + c0_rgb), 0.0, 1.0))
        sampled_stops: list[tuple[float, str]] = [
            (0.0, mcolors.to_hex(z_rgb)),
            (0.06, mcolors.to_hex(mid_rgb)),
        ]
        for u in np.linspace(0.0, 1.0, 12):
            pos = 0.12 + 0.88 * float(u)
            sampled_stops.append((pos, mcolors.to_hex(cmap(float(u))[:3])))
        cmap = mcolors.LinearSegmentedColormap.from_list(f"{raw_name}_zero", sampled_stops, N=256)

    if n is not None:
        if n <= 0:
            raise ValueError("离散分级数 n 必须为正整数。")
        if key in QUALITATIVE_PALETTES:
            colors = list(QUALITATIVE_PALETTES[key])
            if reverse ^ raw_name.endswith("_r"):
                colors = colors[::-1]
            sampled = [colors[i % len(colors)] for i in range(n)]
            cmap = mcolors.ListedColormap(sampled, name=f"{raw_name}_{n}")
        else:
            cmap = cmap.resampled(n)

    if hasattr(cmap, "with_extremes") and nodata_color is not None:
        cmap = cmap.with_extremes(bad=nodata_color)
    else:
        if hasattr(cmap, "copy"):
            cmap = cmap.copy()
        if nodata_color is not None:
            cmap.set_bad(nodata_color)
    return cmap


def get_palette(name: str = "okabe_ito", n: int | None = None) -> list[str]:
    """按名称返回可直接索引的 hex 色列表（支持定性色板与任意连续/发散色带采样）。"""
    _check_banned_cmap(name)
    key = name.strip().lower()
    if key in QUALITATIVE_PALETTES:
        colors = list(QUALITATIVE_PALETTES[key])
        if n is None:
            return colors
        if n <= 0:
            raise ValueError("n 必须为正整数。")
        return [colors[i % len(colors)] for i in range(n)]
    count = n or 7
    if count <= 0:
        raise ValueError("n 必须为正整数。")
    kind = "diverging" if key in DIVERGING_PALETTES or key in _CRAMERI_DIVERGING_STOPS else "sequential"
    cmap = get_scientific_cmap(kind, name=name)
    if count == 1:
        return [mcolors.to_hex(cmap(0.5))]
    return [mcolors.to_hex(cmap(i / (count - 1))) for i in range(count)]


def get_bivariate_palette(name: str = "stevens_pinkblue") -> list[list[str]]:
    """返回预设 n×n 双变量二维 hex 矩阵（row 0=低Y，col 0=低X）。"""
    key = name.strip().lower()
    if key not in BIVARIATE_PALETTES:
        raise ValueError(f"未知双变量色卡 '{name}'；可选：{sorted(BIVARIATE_PALETTES)}")
    return [list(row) for row in BIVARIATE_PALETTES[key]]


def bivariate_classify(
    x: Sequence[float] | np.ndarray,
    y: Sequence[float] | np.ndarray,
    *,
    bins: int = 3,
    method: str = "quantile",
) -> dict[str, Any]:
    """将双变量数值 (x, y) 同步分箱到 [0, bins-1]×[0, bins-1]，非有限值安全标为 -1。"""
    if bins < 2 or bins > 9:
        raise ValueError("bins 必须在 [2, 9] 之间。")
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    if x_arr.shape != y_arr.shape or x_arr.ndim != 1:
        raise ValueError("x 与 y 必须是等长一维序列。")
    valid = np.isfinite(x_arr) & np.isfinite(y_arr)
    x_bin = np.full(x_arr.shape, -1, dtype=int)
    y_bin = np.full(y_arr.shape, -1, dtype=int)
    pair_index = np.full(x_arr.shape, -1, dtype=int)

    def _edges(vals: np.ndarray) -> np.ndarray:
        if method == "equal":
            edges = np.linspace(float(vals.min()), float(vals.max()), bins + 1)
        elif method == "quantile":
            edges = np.quantile(vals, np.linspace(0.0, 1.0, bins + 1))
        else:
            raise ValueError("method 仅支持 'quantile' 或 'equal'。")
        for idx in range(1, len(edges)):
            if edges[idx] <= edges[idx - 1]:
                edges[idx] = edges[idx - 1] + 1e-12
        return edges

    if not np.any(valid):
        return {
            "x_bin": x_bin,
            "y_bin": y_bin,
            "pair_index": pair_index,
            "x_breaks": [],
            "y_breaks": [],
            "bins": bins,
        }

    x_edges = _edges(x_arr[valid])
    y_edges = _edges(y_arr[valid])
    xv = np.clip(np.digitize(x_arr[valid], x_edges[1:-1], right=True), 0, bins - 1)
    yv = np.clip(np.digitize(y_arr[valid], y_edges[1:-1], right=True), 0, bins - 1)
    x_bin[valid] = xv
    y_bin[valid] = yv
    pair_index[valid] = yv * bins + xv
    return {
        "x_bin": x_bin,
        "y_bin": y_bin,
        "pair_index": pair_index,
        "x_breaks": [float(v) for v in x_edges],
        "y_breaks": [float(v) for v in y_edges],
        "bins": bins,
    }

def build_perceptual_norm(
    values: Any,
    *,
    vmin: float | None = None,
    vmax: float | None = None,
    positive_only: bool = True,
    target_median_pos: float = 0.40,
    gamma_bounds: tuple[float, float] = (0.28, 0.85),
) -> mcolors.Normalize:
    """按有效正值中位数求解感知幂指数 PowerNorm，避免偏态连续场大片发白或发死。"""
    if isinstance(values, np.ma.MaskedArray):
        raw = np.asarray(values.compressed(), dtype=float)
    else:
        raw = np.asarray(values, dtype=float).ravel()
    finite = raw[np.isfinite(raw)]
    sample = finite[finite > 0.0] if positive_only else finite
    if sample.size == 0:
        lo = 0.0 if vmin is None else float(vmin)
        hi = (lo + 1.0) if (vmax is None or float(vmax) <= lo) else float(vmax)
        return mcolors.Normalize(vmin=lo, vmax=hi)

    lo = (0.0 if positive_only else float(np.min(sample))) if vmin is None else float(vmin)
    hi = float(np.max(sample)) if vmax is None else float(vmax)
    if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
        return mcolors.Normalize(vmin=lo, vmax=lo + 1.0)

    p50 = float(np.median(sample))
    u50 = (p50 - lo) / (hi - lo)
    t_mid = float(np.clip(target_median_pos, 0.15, 0.75))
    if 0.0 < u50 < t_mid - 0.05:
        gamma = math.log(t_mid) / math.log(u50)
        gamma = float(np.clip(gamma, float(gamma_bounds[0]), float(gamma_bounds[1])))
        return mcolors.PowerNorm(gamma=round(gamma, 2), vmin=lo, vmax=hi)
    return mcolors.Normalize(vmin=lo, vmax=hi)
