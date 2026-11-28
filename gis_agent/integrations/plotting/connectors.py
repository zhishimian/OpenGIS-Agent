"""局部放大插图容器、外切角聚焦连线与正交总线连接器。"""
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

def add_locator_inset(
    fig_or_ax: Figure | Axes,
    bounds: Sequence[float],
    *,
    shape: str = "rect",
    projection: Any = None,
    frame_lw: float = 0.75,
    frame_color: str = "#4a4a4a",
    facecolor: str = GEO_COLORS["ocean_soft"],
    zorder: int = 10,
) -> Axes:
    """在画布或主图留白角创建矩形研究区框或带 Circular Clipping 的定位球小图。"""
    if shape not in {"rect", "circle"}:
        raise ValueError("shape 仅支持 'rect' 或 'circle'。")
    if len(bounds) != 4:
        raise ValueError("bounds 必须为 4 元组 [x0, y0, width, height]。")
    bx, by, bw, bh = [float(v) for v in bounds]

    if isinstance(fig_or_ax, Figure):
        fig = fig_or_ax
        kwargs = {"projection": projection} if projection is not None else {}
        inset_ax = fig.add_axes([bx, by, bw, bh], zorder=zorder, **kwargs)
    else:
        parent = fig_or_ax
        fig = parent.figure
        if projection is None:
            inset_ax = parent.inset_axes([bx, by, bw, bh], zorder=zorder)
        else:
            try:
                if fig.get_constrained_layout():
                    fig.canvas.draw()
            except Exception:
                pass
            pos = parent.get_position()
            fig_bounds = [
                pos.x0 + bx * pos.width,
                pos.y0 + by * pos.height,
                bw * pos.width,
                bh * pos.height,
            ]
            inset_ax = fig.add_axes(fig_bounds, projection=projection, zorder=zorder)

    inset_ax.set_gid("locator_inset")
    inset_ax.set_facecolor(facecolor)
    inset_ax.set_xticks([])
    inset_ax.set_yticks([])
    inset_ax.xaxis.label.set_visible(False)
    inset_ax.yaxis.label.set_visible(False)

    if shape == "circle":
        if hasattr(inset_ax, "set_box_aspect"):
            inset_ax.set_box_aspect(1.0)
        theta = np.linspace(0.0, 2.0 * np.pi, 128)
        verts = np.vstack([0.5 + 0.5 * np.cos(theta), 0.5 + 0.5 * np.sin(theta)]).T
        circle_path = MplPath(verts)
        if hasattr(inset_ax, "set_boundary"):
            inset_ax.set_boundary(circle_path, transform=inset_ax.transAxes)
            if "geo" in inset_ax.spines:
                inset_ax.spines["geo"].set_visible(frame_lw > 0)
                inset_ax.spines["geo"].set_linewidth(frame_lw)
                inset_ax.spines["geo"].set_edgecolor(frame_color)
        else:
            for sp in inset_ax.spines.values():
                sp.set_visible(False)
            clip_circle = Circle((0.5, 0.5), 0.5, transform=inset_ax.transAxes)
            inset_ax.patch.set_clip_path(clip_circle)
            if frame_lw > 0:
                ring = Circle(
                    (0.5, 0.5),
                    0.5,
                    transform=inset_ax.transAxes,
                    facecolor="none",
                    edgecolor=frame_color,
                    linewidth=frame_lw,
                    zorder=zorder + 20,
                    clip_on=False,
                )
                inset_ax.add_patch(ring)
            else:
                ring = None

            def _clip_children(_event: Any) -> None:
                for child in inset_ax.get_children():
                    if child in {ring, inset_ax.patch} or isinstance(child, matplotlib.spines.Spine):
                        continue
                    try:
                        child.set_clip_path(clip_circle)
                    except Exception:
                        pass

            fig.canvas.mpl_connect("draw_event", _clip_children)
    else:
        if "geo" in inset_ax.spines:
            inset_ax.spines["geo"].set_visible(frame_lw > 0)
            inset_ax.spines["geo"].set_linewidth(frame_lw)
            inset_ax.spines["geo"].set_edgecolor(frame_color)
        else:
            for sp in inset_ax.spines.values():
                sp.set_visible(frame_lw > 0)
                sp.set_linewidth(frame_lw)
                sp.set_edgecolor(frame_color)
    return inset_ax

def add_zoom_connectors(
    fig: Figure,
    src_ax: Axes,
    dst_ax: Axes,
    focus_bbox: Sequence[float],
    *,
    draw_box: bool = True,
    color: str = "#444444",
    linewidth: float = 0.9,
    linestyle: str = "--",
    box_color: str | None = None,
    box_linewidth: float = 1.1,
    alpha: float = 0.85,
    zorder: float = 20.0,
) -> dict[str, Any]:
    """Draw non-crossing outer-tangent zoom connectors from src_ax focus_bbox to dst_ax after layout draw."""
    x0, y0, x1, y1 = [float(v) for v in focus_bbox]
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0

    box_patch = None
    if draw_box:
        box_patch = Rectangle(
            (x0, y0),
            max(x1 - x0, 1e-12),
            max(y1 - y0, 1e-12),
            fill=False,
            edgecolor=box_color or color,
            linewidth=box_linewidth,
            linestyle=linestyle,
            zorder=15,
        )
        src_ax.add_patch(box_patch)

    fig.canvas.draw()
    inv_fig = fig.transFigure.inverted()
    p_lo = inv_fig.transform(src_ax.transData.transform((x0, y0)))
    p_hi = inv_fig.transform(src_ax.transData.transform((x1, y1)))
    sx0, sx1 = min(float(p_lo[0]), float(p_hi[0])), max(float(p_lo[0]), float(p_hi[0]))
    sy0, sy1 = min(float(p_lo[1]), float(p_hi[1])), max(float(p_lo[1]), float(p_hi[1]))

    dst_pos = dst_ax.get_position()
    dx0, dy0, dx1, dy1 = float(dst_pos.x0), float(dst_pos.y0), float(dst_pos.x1), float(dst_pos.y1)

    x_gap = max(dx0 - sx1, sx0 - dx1)
    y_gap = max(dy0 - sy1, sy0 - dy1)
    if x_gap >= y_gap:
        if 0.5 * (dx0 + dx1) >= 0.5 * (sx0 + sx1):
            pairs = [((sx1, sy1), (dx0, dy1)), ((sx1, sy0), (dx0, dy0))]
        else:
            pairs = [((sx0, sy1), (dx1, dy1)), ((sx0, sy0), (dx1, dy0))]
    else:
        if 0.5 * (dy0 + dy1) < 0.5 * (sy0 + sy1):
            pairs = [((sx0, sy0), (dx0, dy1)), ((sx1, sy0), (dx1, dy1))]
        else:
            pairs = [((sx0, sy1), (dx0, dy0)), ((sx1, sy1), (dx1, dy0))]

    lines: list[Line2D] = []
    for (ax_pt, bx_pt) in pairs:
        line = Line2D(
            [ax_pt[0], bx_pt[0]],
            [ax_pt[1], bx_pt[1]],
            transform=fig.transFigure,
            color=color,
            linewidth=linewidth,
            linestyle=linestyle,
            alpha=alpha,
            clip_on=False,
            zorder=zorder,
        )
        line.set_in_layout(False)
        fig.lines.append(line)
        lines.append(line)
    return {"lines": lines, "box": box_patch, "pairs": pairs}


def add_orthogonal_bus_connectors(
    fig: Figure,
    src_ax: Axes,
    links: Sequence[dict[str, Any]],
    *,
    side: str = "right",
    color: str = "#555555",
    linewidth: float = 0.85,
    alpha: float = 0.9,
    arrow: bool = True,
    zorder: float = 20.0,
) -> list[Any]:
    """Route 1-to-N non-crossing orthogonal bus lines from src_ax data points to stacked target panels."""
    if not links:
        return []
    fig.canvas.draw()
    inv_fig = fig.transFigure.inverted()
    src_pos = src_ax.get_position()

    resolved: list[dict[str, Any]] = []
    for item in links:
        sx_raw, sy_raw = inv_fig.transform(src_ax.transData.transform(item["xy"]))
        dpos = item["dst_ax"].get_position()
        dx_edge = float(dpos.x0) if side == "right" else float(dpos.x1)
        dy_mid = 0.5 * (float(dpos.y0) + float(dpos.y1))
        resolved.append({
            "sx": float(sx_raw),
            "sy": float(sy_raw),
            "dx": dx_edge,
            "dy": dy_mid,
            "color": item.get("color", color),
        })

    if side == "right":
        gx0 = float(src_pos.x1)
        gx1 = min(r["dx"] for r in resolved)
    else:
        gx0 = max(r["dx"] for r in resolved)
        gx1 = float(src_pos.x0)
    gw = max(gx1 - gx0, 0.015)

    resolved.sort(key=lambda r: r["dy"], reverse=True)
    n = len(resolved)
    tracks = (
        np.linspace(gx0 + 0.30 * gw, gx0 + 0.78 * gw, n)
        if side == "right"
        else np.linspace(gx1 - 0.30 * gw, gx1 - 0.78 * gw, n)
    )

    artists: list[Any] = []
    halo_pe = [path_effects.withStroke(linewidth=linewidth + 1.6, foreground="#ffffff", alpha=0.88)]
    for r, tx in zip(resolved, tracks):
        xs = [r["sx"], float(tx), float(tx), r["dx"]]
        ys = [r["sy"], r["sy"], r["dy"], r["dy"]]
        if arrow:
            # Draw stem + vertical + short tail, finishing with crisp FancyArrowPatch
            stem = Line2D(
                xs[:-1],
                ys[:-1],
                transform=fig.transFigure,
                color=r["color"],
                linewidth=linewidth,
                alpha=alpha,
                path_effects=halo_pe,
                clip_on=False,
                zorder=zorder,
            )
            stem.set_in_layout(False)
            fig.lines.append(stem)
            artists.append(stem)
            arr = FancyArrowPatch(
                (float(tx), r["dy"]),
                (r["dx"], r["dy"]),
                transform=fig.transFigure,
                arrowstyle="-|>,head_length=4.5,head_width=2.6",
                color=r["color"],
                linewidth=linewidth,
                alpha=alpha,
                path_effects=halo_pe,
                clip_on=False,
                zorder=zorder,
            )
            arr.set_in_layout(False)
            fig.add_artist(arr)
            artists.append(arr)
        else:
            line = Line2D(
                xs,
                ys,
                transform=fig.transFigure,
                color=r["color"],
                linewidth=linewidth,
                alpha=alpha,
                path_effects=halo_pe,
                clip_on=False,
                zorder=zorder,
            )
            line.set_in_layout(False)
            fig.lines.append(line)
            artists.append(line)
    return artists
