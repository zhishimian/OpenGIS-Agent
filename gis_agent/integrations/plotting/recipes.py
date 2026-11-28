"""出版级地理制图高频版式骨架与一键收尾助手（Option A 骨架封装）。

提供高内聚的版式排布（`create_study_area_layout` / `create_composite_layout` /
`create_thematic_layout`）、安全邻区标注（`label_context_polygons`）与单面板收尾
（`finalize_map_panel`），将对齐、面板留白（>= 12 pt）、4 档偶数文字阶梯、经纬网、
智能避让比例尺与指北针等易错排版细节内化到框架层，降低 Agent 拼装风险。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from matplotlib import patheffects as path_effects
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpecFromSubplotSpec
import matplotlib.pyplot as plt

from gis_agent.integrations.plotting.chrome import (
    add_graticule_frame,
    add_scalebar_and_north,
)
from gis_agent.integrations.plotting.palettes import GEO_COLORS
from gis_agent.integrations.plotting.theme import apply_publication_theme


@dataclass
class StudyAreaLayout:
    """研究区多面板区位图骨架容器。"""

    fig: Figure
    ax_macro: Axes
    ax_region: Axes | None
    ax_main: Axes
    theme: dict[str, Any]
    panel_axes: dict[str, Axes]
    mode: str


@dataclass
class CompositeLayout:
    """科研“主地图 + 统计面板 + 独立色带/图例槽”复合排版骨架容器。"""

    fig: Figure
    ax_map: Axes
    ax_cbar: Axes
    ax_legend: Axes
    stat_axes: list[Axes]
    theme: dict[str, Any]
    panel_axes: dict[str, Axes]
    mode: str


@dataclass
class ThematicLayout:
    """单面板或多面板专题地图骨架容器。"""

    fig: Figure
    axes: list[Axes]
    ax_legend: Axes | None
    theme: dict[str, Any]
    panel_axes: dict[str, Axes]


def _stamp_panel_badge(
    ax: Axes,
    label: str,
    *,
    fontsize: float,
    color: str = GEO_COLORS["text_primary"],
) -> None:
    """在面板左上内角放置清晰、带轻微白底描边的 (a)/(b)/(c) 徽章。"""
    if not label:
        return
    ax.text(
        0.032,
        0.962,
        label,
        transform=ax.transAxes,
        fontsize=fontsize,
        fontweight="bold",
        color=color,
        ha="left",
        va="top",
        zorder=20,
        gid="panel_badge",
        path_effects=[path_effects.withStroke(linewidth=2.4, foreground="#ffffff", alpha=0.92)],
    )


def create_study_area_layout(
    mode: str = "3panel_left",
    *,
    fig_width: float = 8.8,
    fig_height: float | None = None,
    panel_labels: Sequence[str] | None = None,
    theme_style: str = "light_geo",
    dpi: int = 300,
) -> StudyAreaLayout:
    """创建对齐、留白合规的研究区区位图多面板骨架。"""
    mode_norm = mode.strip().lower()
    if mode_norm not in {"3panel_left", "3panel_top", "2panel_side"}:
        raise ValueError(f"不支持的区位图 mode '{mode}'；可选 '3panel_left'、'3panel_top' 或 '2panel_side'。")

    theme = apply_publication_theme(theme_style, fig_width=fig_width)
    badge_pt = float(theme["fonts"]["T2"])

    if mode_norm == "3panel_left":
        h = float(fig_height) if fig_height is not None else round(fig_width * 0.66, 2)
        fig = plt.figure(figsize=(fig_width, h), dpi=dpi)
        gs = fig.add_gridspec(
            2,
            2,
            width_ratios=[0.35, 0.65],
            height_ratios=[1.0, 1.0],
            left=0.065,
            right=0.935,
            top=0.955,
            bottom=0.075,
            wspace=0.22,
            hspace=0.20,
        )
        ax_macro = fig.add_subplot(gs[0, 0])
        ax_region = fig.add_subplot(gs[1, 0])
        ax_main = fig.add_subplot(gs[:, 1])
        labels = ("(a)", "(b)", "(c)") if panel_labels is None else tuple(panel_labels)
        axes_seq = (ax_macro, ax_region, ax_main)
        panel_axes = {"macro": ax_macro, "region": ax_region, "main": ax_main}
    elif mode_norm == "3panel_top":
        h = float(fig_height) if fig_height is not None else round(fig_width * 1.15, 2)
        fig = plt.figure(figsize=(fig_width, h), dpi=dpi)
        gs = fig.add_gridspec(
            2,
            2,
            width_ratios=[1.0, 1.0],
            height_ratios=[0.34, 0.66],
            left=0.075,
            right=0.925,
            top=0.960,
            bottom=0.060,
            wspace=0.20,
            hspace=0.16,
        )
        ax_macro = fig.add_subplot(gs[0, 0])
        ax_region = fig.add_subplot(gs[0, 1])
        ax_main = fig.add_subplot(gs[1, :])
        labels = ("(a)", "(b)", "(c)") if panel_labels is None else tuple(panel_labels)
        axes_seq = (ax_macro, ax_region, ax_main)
        panel_axes = {"macro": ax_macro, "region": ax_region, "main": ax_main}
    else:  # 2panel_side
        h = float(fig_height) if fig_height is not None else round(fig_width * 0.60, 2)
        fig = plt.figure(figsize=(fig_width, h), dpi=dpi)
        gs = fig.add_gridspec(
            1,
            2,
            width_ratios=[0.36, 0.64],
            left=0.065,
            right=0.935,
            top=0.950,
            bottom=0.085,
            wspace=0.22,
        )
        ax_macro = fig.add_subplot(gs[0, 0])
        ax_region = None
        ax_main = fig.add_subplot(gs[0, 1])
        labels = ("(a)", "(b)") if panel_labels is None else tuple(panel_labels)
        axes_seq = (ax_macro, ax_main)
        panel_axes = {"macro": ax_macro, "main": ax_main}

    for idx, ax in enumerate(axes_seq):
        if idx < len(labels) and labels[idx]:
            _stamp_panel_badge(ax, labels[idx], fontsize=badge_pt)

    return StudyAreaLayout(
        fig=fig,
        ax_macro=ax_macro,
        ax_region=ax_region,
        ax_main=ax_main,
        theme=theme,
        panel_axes=panel_axes,
        mode=mode_norm,
    )


def create_composite_layout(
    mode: str = "map_left_stats_right",
    *,
    n_stats: int = 2,
    fig_width: float = 11.5,
    fig_height: float | None = None,
    map_ratio: float = 0.62,
    panel_labels: Sequence[str] | None = None,
    theme_style: str = "light_geo",
    dpi: int = 300,
) -> CompositeLayout:
    """创建科研“主地图 + 独立色带/图例槽 + 统计子图组”复合 Panel 骨架。

    通过嵌套 GridSpec 提前锁定各子图的物理边界与垂直间距，彻底避免手算 `add_axes`
    坐标导致 `(b)` 的 X 轴标签与 `(c)` 标题撞车。
    """
    mode_norm = mode.strip().lower()
    if mode_norm not in {"map_left_stats_right", "map_top_stats_bottom"}:
        raise ValueError(
            f"不支持的复合图 mode '{mode}'；可选 'map_left_stats_right' 或 'map_top_stats_bottom'。"
        )
    if not (1 <= n_stats <= 3):
        raise ValueError("n_stats 必须在 [1, 3] 之间。")
    if not (0.45 <= map_ratio <= 0.78):
        raise ValueError("map_ratio 必须在 [0.45, 0.78] 之间。")

    theme = apply_publication_theme(theme_style, fig_width=fig_width)
    badge_pt = float(theme["fonts"]["T2"])

    stat_axes: list[Axes] = []
    if mode_norm == "map_left_stats_right":
        h = float(fig_height) if fig_height is not None else round(fig_width * (0.72 if n_stats <= 2 else 0.84), 2)
        fig = plt.figure(figsize=(fig_width, h), dpi=dpi)
        outer = fig.add_gridspec(
            1,
            2,
            width_ratios=[map_ratio, 1.0 - map_ratio],
            left=0.068,
            right=0.955,
            top=0.880,
            bottom=0.095,
            wspace=0.15,
        )
        ax_map = fig.add_subplot(outer[0, 0])

        # 右栏扁平拆为 2 + n_stats 行：色带槽、图例槽与统计图共享大间隔，彻底消除嵌套挤压与重叠
        right_ratios = [0.32, 0.72] + [1.0] * n_stats
        right_gs = GridSpecFromSubplotSpec(
            2 + n_stats,
            1,
            subplot_spec=outer[0, 1],
            height_ratios=right_ratios,
            hspace=0.98 if n_stats >= 2 else 0.65,
        )
        ax_cbar = fig.add_subplot(right_gs[0, 0])
        ax_cbar.set_axis_off()
        ax_legend = fig.add_subplot(right_gs[1, 0])
        ax_legend.set_axis_off()
        for idx in range(n_stats):
            sax = fig.add_subplot(right_gs[2 + idx, 0])
            sax.spines["top"].set_visible(False)
            sax.spines["right"].set_visible(False)
            stat_axes.append(sax)
    else:  # map_top_stats_bottom
        h = float(fig_height) if fig_height is not None else round(fig_width * 0.78, 2)
        fig = plt.figure(figsize=(fig_width, h), dpi=dpi)
        outer = fig.add_gridspec(
            2,
            1,
            height_ratios=[map_ratio, 1.0 - map_ratio],
            left=0.065,
            right=0.955,
            top=0.900,
            bottom=0.090,
            hspace=0.34,
        )
        top_gs = GridSpecFromSubplotSpec(
            1,
            2,
            subplot_spec=outer[0, 0],
            width_ratios=[0.74, 0.26],
            wspace=0.14,
        )
        ax_map = fig.add_subplot(top_gs[0, 0])
        side_gs = GridSpecFromSubplotSpec(2, 1, subplot_spec=top_gs[0, 1], height_ratios=[0.35, 0.65], hspace=0.20)
        ax_cbar = fig.add_subplot(side_gs[0, 0])
        ax_cbar.set_axis_off()
        ax_legend = fig.add_subplot(side_gs[1, 0])
        ax_legend.set_axis_off()

        bot_gs = GridSpecFromSubplotSpec(1, n_stats, subplot_spec=outer[1, 0], wspace=0.30)
        for idx in range(n_stats):
            sax = fig.add_subplot(bot_gs[0, idx])
            sax.spines["top"].set_visible(False)
            sax.spines["right"].set_visible(False)
            stat_axes.append(sax)

    labels = tuple(f"({chr(97 + i)})" for i in range(1 + n_stats)) if panel_labels is None else tuple(panel_labels)
    if labels and labels[0]:
        _stamp_panel_badge(ax_map, labels[0], fontsize=badge_pt)

    panel_axes: dict[str, Axes] = {"main": ax_map}
    for idx, sax in enumerate(stat_axes):
        panel_axes[f"stat_{idx + 1}"] = sax

    return CompositeLayout(
        fig=fig,
        ax_map=ax_map,
        ax_cbar=ax_cbar,
        ax_legend=ax_legend,
        stat_axes=stat_axes,
        theme=theme,
        panel_axes=panel_axes,
        mode=mode_norm,
    )


def label_context_polygons(
    ax: Axes,
    gdf: Any,
    name_col: str,
    *,
    exclude_geom: Any = None,
    fontsize: float | None = None,
    color: str = "#6e6a63",
    italic: bool = True,
    max_labels: int = 8,
    min_area_frac: float = 0.012,
    halo: bool = True,
) -> list[Any]:
    """在当前视口内、避开研究区边界与图框边缘的安全空白区域标注周边邻区名称。"""
    from shapely.geometry import box as shp_box

    if gdf is None or len(gdf) == 0 or name_col not in gdf.columns:
        return []

    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    x0, x1 = min(float(xlim[0]), float(xlim[1])), max(float(xlim[0]), float(xlim[1]))
    y0, y1 = min(float(ylim[0]), float(ylim[1])), max(float(ylim[0]), float(ylim[1]))
    span_x, span_y = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)

    safe_win = shp_box(x0 + 0.08 * span_x, y0 + 0.08 * span_y, x1 - 0.08 * span_x, y1 - 0.08 * span_y)
    safe_area = max(float(safe_win.area), 1e-12)
    excl = None
    if exclude_geom is not None:
        buf = 0.045 * min(span_x, span_y)
        excl = exclude_geom.buffer(buf)

    candidates: list[tuple[float, str, float, float]] = []
    for _, row in gdf.iterrows():
        raw_name = row[name_col]
        if raw_name is None:
            continue
        name = str(raw_name).strip()
        if not name or name.lower() == "nan":
            continue
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        vis = geom.intersection(safe_win)
        if vis.is_empty:
            continue
        if excl is not None:
            vis = vis.difference(excl)
        if vis.is_empty:
            continue
        if hasattr(vis, "geoms"):
            polys = [g for g in vis.geoms if getattr(g, "area", 0.0) > 0]
            if not polys:
                continue
            vis = max(polys, key=lambda g: g.area)
        area_frac = float(getattr(vis, "area", 0.0)) / safe_area
        if area_frac < min_area_frac:
            continue
        pt = vis.representative_point()
        candidates.append((area_frac, name, float(pt.x), float(pt.y)))

    candidates.sort(key=lambda item: item[0], reverse=True)
    pt_sz = float(fontsize) if fontsize is not None else float(plt.rcParams.get("legend.fontsize", 12.0))
    pe = [path_effects.withStroke(linewidth=2.4, foreground="#ffffff", alpha=0.88)] if halo else None

    placed: list[Any] = []
    min_dist = 0.09 * min(span_x, span_y)
    kept_pts: list[tuple[float, float]] = []
    seen_names: set[str] = set()
    for _, name, px, py in candidates:
        if name in seen_names:
            continue
        if any(((px - kx) ** 2 + (py - ky) ** 2) ** 0.5 < min_dist for kx, ky in kept_pts):
            continue
        t = ax.text(
            px,
            py,
            name,
            fontsize=pt_sz,
            fontstyle="italic" if italic else "normal",
            color=color,
            ha="center",
            va="center",
            clip_on=True,
            zorder=9.5,
            gid="context_label",
            path_effects=pe,
        )
        placed.append(t)
        kept_pts.append((px, py))
        seen_names.add(name)
        if len(placed) >= max_labels:
            break
    return placed


def create_thematic_layout(
    n_panels: int = 1,
    *,
    ncols: int | None = None,
    fig_width: float = 8.8,
    fig_height: float | None = None,
    legend_pos: str = "bottom",
    panel_labels: Sequence[str] | None = None,
    theme_style: str = "light_geo",
    dpi: int = 300,
) -> ThematicLayout:
    """创建对齐、留白合规的单面板或多面板专题地图骨架（带可选图例/色带预留槽）。"""
    if n_panels < 1 or n_panels > 12:
        raise ValueError("n_panels 必须在 [1, 12] 之间。")
    leg_mode = legend_pos.strip().lower()
    if leg_mode not in {"bottom", "right", "none", "inside"}:
        raise ValueError(f"不支持的 legend_pos '{legend_pos}'；可选 'bottom'、'right'、'none' 或 'inside'。")

    theme = apply_publication_theme(theme_style, fig_width=fig_width)
    badge_pt = float(theme["fonts"]["T2"])

    cols = int(ncols) if ncols is not None else (1 if n_panels == 1 else (2 if n_panels <= 4 else 3))
    cols = max(1, min(cols, n_panels))
    rows = (n_panels + cols - 1) // cols

    if fig_height is None:
        base_h = fig_width * (0.70 if n_panels == 1 else 0.56 * rows / max(cols, 1) * 1.35)
        if leg_mode == "bottom":
            base_h += 0.65
        h = round(max(4.6, min(11.5, base_h)), 2)
    else:
        h = float(fig_height)

    fig = plt.figure(figsize=(fig_width, h), dpi=dpi)
    left, right, top, bottom = 0.085, 0.935, 0.940, 0.085

    ax_legend: Axes | None = None
    if leg_mode == "bottom":
        map_bottom = 0.21
        ax_legend = fig.add_axes([0.12, 0.04, 0.76, 0.11])
        ax_legend.set_axis_off()
        bottom = map_bottom
    elif leg_mode == "right":
        map_right = 0.74
        ax_legend = fig.add_axes([0.765, 0.12, 0.205, 0.78])
        ax_legend.set_axis_off()
        right = map_right

    gs = fig.add_gridspec(
        rows,
        cols,
        left=left,
        right=right,
        top=top,
        bottom=bottom,
        wspace=0.22,
        hspace=0.24,
    )
    axes: list[Axes] = []
    panel_axes: dict[str, Axes] = {}
    for idx in range(n_panels):
        r, c = divmod(idx, cols)
        ax = fig.add_subplot(gs[r, c])
        axes.append(ax)
        panel_axes[f"panel_{idx + 1}"] = ax
        if panel_labels is not None:
            if idx < len(panel_labels) and panel_labels[idx]:
                _stamp_panel_badge(ax, panel_labels[idx], fontsize=badge_pt)
        elif n_panels > 1:
            _stamp_panel_badge(ax, f"({chr(97 + idx)})", fontsize=badge_pt)

    return ThematicLayout(
        fig=fig,
        axes=axes,
        ax_legend=ax_legend,
        theme=theme,
        panel_axes=panel_axes,
    )


def finalize_map_panel(
    ax: Axes,
    *,
    crs: Any = None,
    graticule: bool = True,
    scalebar: bool = True,
    north: bool = True,
    loc: str = "auto",
    north_loc: str = "auto",
    north_style: str = "compass_star",
    scale_style: str = "cartographic",
    crs_units: str = "metre",
    dms: bool = True,
    graticule_style: str = "ticks_only",
    step_deg: float | tuple[float, float] | None = None,
    align_box: bool = True,
) -> dict[str, Any]:
    """一键收尾单个地图面板：框体严格对齐 + 清除裸轴标签 + 整数度经纬网 + 智能避让比例尺/指北针。"""
    ax.set_xlabel("")
    ax.set_ylabel("")
    if align_box and not hasattr(ax, "projection"):
        # 使用 adjustable="datalim" 扩张数据范围而非缩窄 Axes 框体，确保多面板外框线严格对齐
        ax.set_aspect("equal", adjustable="datalim")

    grat_meta: dict[str, Any] | None = None
    if graticule:
        grat_meta = add_graticule_frame(
            ax,
            crs=crs,
            style=graticule_style,
            dms=dms,
            step_deg=step_deg,
        )

    chrome_meta: dict[str, Any] | None = None
    if scalebar or north:
        chrome_meta = add_scalebar_and_north(
            ax,
            crs_units=crs_units,
            loc=loc,
            scale=scalebar,
            north=north,
            north_loc=north_loc,
            scale_style=scale_style,
            north_style=north_style,
        )

    return {"graticule": grat_meta, "chrome": chrome_meta}


__all__ = [
    "CompositeLayout",
    "StudyAreaLayout",
    "ThematicLayout",
    "create_composite_layout",
    "create_study_area_layout",
    "create_thematic_layout",
    "finalize_map_panel",
    "label_context_polygons",
]
