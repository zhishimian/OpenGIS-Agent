"""OD 流向弧线与气泡尺寸-线宽组合图例原语。"""
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
from gis_agent.integrations.plotting.chrome import _resolve_cbar_cmap
from gis_agent.integrations.plotting.palettes import GEO_COLORS
from gis_agent.integrations.plotting.theme import _resolve_pt, _snap_even

def _extract_flow_records(flows: Any, value_col: str | None) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """将 GeoDataFrame / DataFrame / 序列统一解析为起止坐标与数值向量。"""
    x0s: list[float] = []
    y0s: list[float] = []
    x1s: list[float] = []
    y1s: list[float] = []
    vals: list[float] = []

    def _push(a0: float, b0: float, a1: float, b1: float, val: Any) -> None:
        try:
            fx0, fy0, fx1, fy1, fv = float(a0), float(b0), float(a1), float(b1), float(val)
        except (TypeError, ValueError):
            return
        if all(math.isfinite(z) for z in (fx0, fy0, fx1, fy1, fv)) and math.hypot(fx1 - fx0, fy1 - fy0) > 1e-9:
            x0s.append(fx0)
            y0s.append(fy0)
            x1s.append(fx1)
            y1s.append(fy1)
            vals.append(fv)

    if hasattr(flows, "geometry"):
        col = value_col or ("value" if "value" in flows.columns else None)
        if col is None or col not in flows.columns:
            raise ValueError("GeoDataFrame 输入必须通过 value_col 指定流量数值字段。")
        for geom, raw_val in zip(flows.geometry, flows[col]):
            if geom is None or getattr(geom, "is_empty", True):
                continue
            gtype = getattr(geom, "geom_type", "")
            if gtype == "MultiLineString" and len(geom.geoms) > 0:
                geom = max(geom.geoms, key=lambda part: part.length)
                gtype = getattr(geom, "geom_type", "")
            if gtype == "LineString" and len(geom.coords) >= 2:
                c0, c1 = geom.coords[0], geom.coords[-1]
                _push(c0[0], c0[1], c1[0], c1[1], raw_val)
    elif hasattr(flows, "columns"):
        col = value_col or ("value" if "value" in flows.columns else None)
        if not {"x0", "y0", "x1", "y1"}.issubset(flows.columns):
            raise ValueError("DataFrame 输入必须包含 x0, y0, x1, y1 列。")
        if col is None or col not in flows.columns:
            raise ValueError("DataFrame 输入必须通过 value_col 指定流量数值字段。")
        for row in flows.itertuples(index=False):
            _push(getattr(row, "x0"), getattr(row, "y0"), getattr(row, "x1"), getattr(row, "y1"), getattr(row, col))
    else:
        for item in flows:
            if isinstance(item, dict):
                v = item.get(value_col or "value")
                _push(item["x0"], item["y0"], item["x1"], item["y1"], v)
            elif isinstance(item, (tuple, list)) and len(item) >= 5:
                _push(item[0], item[1], item[2], item[3], item[4])
            else:
                raise ValueError("flows 元素需为 GeoDataFrame、DataFrame、dict 或 (x0, y0, x1, y1, value) 元组。")

    return (
        np.asarray(x0s, dtype=float),
        np.asarray(y0s, dtype=float),
        np.asarray(x1s, dtype=float),
        np.asarray(y1s, dtype=float),
        np.asarray(vals, dtype=float),
    )


def _format_flow_num(val: float) -> str:
    if abs(val) >= 100.0 and abs(val - round(val)) < 1e-4:
        return f"{int(round(val)):,}"
    if abs(val) >= 10.0 and abs(val - round(val)) < 1e-4:
        return f"{int(round(val))}"
    return f"{val:.3g}"


def _snap_flow_breaks(vmin: float, vmax: float, vals: np.ndarray, n_classes: int) -> list[float]:
    uniq = np.unique(vals)
    m = max(1, min(int(n_classes), len(uniq)))
    if m == 1 or vmax <= vmin:
        return [float(vmin), float(vmax)]
    edges = [float(v) for v in np.quantile(vals, np.linspace(0.0, 1.0, m + 1))]
    snapped = [float(vmin)]
    for inner in edges[1:-1]:
        if inner <= 0:
            cand = inner
        else:
            mag = 10.0 ** math.floor(math.log10(inner))
            step = mag * (0.5 if inner / mag >= 2.0 else 0.25)
            cand = round(inner / step) * step
        if cand > snapped[-1] and cand < vmax:
            snapped.append(float(cand))
    snapped.append(float(vmax))
    if len(snapped) == m + 1:
        return snapped
    if len(edges) == m + 1 and all(b > a for a, b in zip(edges, edges[1:])):
        return edges
    return [float(v) for v in np.linspace(vmin, vmax, m + 1)]


def add_flow_arcs(
    ax: Axes,
    flows: Any,
    *,
    value_col: str | None = None,
    directed: bool = False,
    symmetric: bool = True,
    bend_outward: bool = True,
    curvature: float = 0.18,
    length_scale: bool = True,
    breaks: Sequence[float] | None = None,
    n_classes: int = 4,
    lw_range: tuple[float, float] = (0.7, 4.2),
    alpha_range: tuple[float, float] = (0.38, 0.94),
    gamma: float = 0.75,
    cmap: str | Any = "carto_oryel",
    colors: Sequence[str] | None = None,
    halo: bool = True,
    halo_color: str = "#ffffff",
    halo_alpha: float = 0.65,
    top_n: int | None = None,
    min_value: float | None = None,
    margin_frac: float = 0.0,
    arrow_pos: float = 0.88,
    arrow_scale: float = 1.0,
    zorder: float = 5.0,
    transform: Any = None,
    gid: str = "flow_arcs",
) -> dict[str, Any]:
    """绘制出版级二次贝塞尔 OD/空间流向弧线，按权重升序叠绘并返回图例元数据。"""
    if top_n is not None and int(top_n) <= 0:
        raise ValueError("top_n 必须为正整数。")
    if n_classes <= 0:
        raise ValueError("n_classes 必须为正整数。")
    lw_min, lw_max = float(lw_range[0]), float(lw_range[1])
    al_min, al_max = float(alpha_range[0]), float(alpha_range[1])

    x0, y0, x1, y1, vals = _extract_flow_records(flows, value_col)
    if min_value is not None and len(vals):
        keep = vals >= float(min_value)
        x0, y0, x1, y1, vals = x0[keep], y0[keep], x1[keep], y1[keep], vals[keep]
    if top_n is not None and len(vals) > int(top_n):
        top_idx = np.argsort(-vals, kind="mergesort")[: int(top_n)]
        x0, y0, x1, y1, vals = x0[top_idx], y0[top_idx], x1[top_idx], y1[top_idx], vals[top_idx]

    if len(vals) == 0:
        return {
            "count": 0,
            "breaks": [],
            "colors": [],
            "linewidths": [],
            "alphas": [],
            "legend_items": [],
            "artists": [],
        }

    # 严格升序排序（Bottom-Up Layering：弱流沉底、强主干走廊置顶）
    order = np.argsort(vals, kind="mergesort")
    x0, y0, x1, y1, vals = x0[order], y0[order], x1[order], y1[order], vals[order]
    vmin, vmax = float(vals[0]), float(vals[-1])

    if breaks is not None:
        edge_list = [float(v) for v in breaks]
        if len(edge_list) < 2 or any(b <= a for a, b in zip(edge_list, edge_list[1:])):
            raise ValueError("breaks 必须为严格递增的至少两个数值边界。")
    else:
        edge_list = _snap_flow_breaks(vmin, vmax, vals, int(n_classes))

    n_bins = max(len(edge_list) - 1, 1)
    if len(edge_list) > 2:
        cls_idx = np.clip(np.digitize(vals, edge_list[1:-1], right=True), 0, n_bins - 1)
    else:
        cls_idx = np.zeros(len(vals), dtype=int)

    if colors is not None:
        raw_cols = [mcolors.to_hex(c) for c in colors]
        if len(raw_cols) < n_bins:
            cmap_tmp = mcolors.LinearSegmentedColormap.from_list("flow_custom", raw_cols, N=256)
            cls_hex = [mcolors.to_hex(cmap_tmp(u)) for u in np.linspace(0.0, 1.0, n_bins)] if n_bins > 1 else [raw_cols[-1]]
        else:
            cls_hex = raw_cols[:n_bins]
    else:
        cmap_obj = _resolve_cbar_cmap(cmap)
        sample_u = [0.75] if n_bins == 1 else np.linspace(0.22, 0.96, n_bins)
        cls_hex = [mcolors.to_hex(cmap_obj(float(u))) for u in sample_u]

    if vmax > vmin:
        u_vals = np.clip((vals - vmin) / (vmax - vmin), 0.0, 1.0)
    else:
        u_vals = np.full_like(vals, 0.7)
    lws = lw_min + (lw_max - lw_min) * (u_vals ** float(gamma))
    alphas = al_min + (al_max - al_min) * u_vals

    rgba = np.array([mcolors.to_rgba(cls_hex[int(c)], alpha=float(a)) for c, a in zip(cls_idx, alphas)], dtype=float)

    dx = x1 - x0
    dy = y1 - y0
    lengths = np.hypot(dx, dy)
    nx = -dy / lengths
    ny = dx / lengths

    k_arr = np.full(len(lengths), float(curvature), dtype=float)
    if length_scale and len(lengths) > 0:
        l_med = max(float(np.median(lengths)), 1e-9)
        k_arr = k_arr * np.clip((l_med / np.maximum(lengths, 1e-9)) ** 0.30, 0.50, 1.35)

    if directed and symmetric:
        signs = -np.ones_like(lengths)
    elif bend_outward:
        cx_all = float(np.median(np.concatenate([x0, x1])))
        cy_all = float(np.median(np.concatenate([y0, y1])))
        mx = 0.5 * (x0 + x1)
        my = 0.5 * (y0 + y1)
        dot = nx * (mx - cx_all) + ny * (my - cy_all)
        signs = np.where(dot >= 0.0, 1.0, -1.0)
    else:
        signs = np.ones_like(lengths)

    cx_ctrl = 0.5 * (x0 + x1) + signs * k_arr * lengths * nx
    cy_ctrl = 0.5 * (y0 + y1) + signs * k_arr * lengths * ny

    t0 = float(np.clip(margin_frac, 0.0, 0.40))
    t1 = 1.0 - t0
    ts = np.linspace(t0, t1, 32)[None, :]
    omt = 1.0 - ts
    bx = (omt ** 2) * x0[:, None] + 2.0 * ts * omt * cx_ctrl[:, None] + (ts ** 2) * x1[:, None]
    by = (omt ** 2) * y0[:, None] + 2.0 * ts * omt * cy_ctrl[:, None] + (ts ** 2) * y1[:, None]
    segments = np.stack([bx, by], axis=-1)

    tx_kw = {"transform": transform} if transform is not None else {}
    artists: list[Any] = []
    if halo:
        halo_lc = LineCollection(
            segments,
            linewidths=lws + 1.4,
            colors=halo_color,
            alpha=float(halo_alpha),
            capstyle="round",
            zorder=float(zorder) - 0.15,
            **tx_kw,
        )
        halo_lc.set_gid(gid)
        ax.add_collection(halo_lc)
        artists.append(halo_lc)

    arc_lc = LineCollection(
        segments,
        linewidths=lws,
        colors=rgba,
        capstyle="round",
        zorder=float(zorder),
        **tx_kw,
    )
    arc_lc.set_gid(gid)
    ax.add_collection(arc_lc)
    artists.append(arc_lc)

    if directed:
        t_arr = float(np.clip(arrow_pos, 0.15, t1 - 0.015))
        omt_a = 1.0 - t_arr
        px = (omt_a ** 2) * x0 + 2.0 * t_arr * omt_a * cx_ctrl + (t_arr ** 2) * x1
        py = (omt_a ** 2) * y0 + 2.0 * t_arr * omt_a * cy_ctrl + (t_arr ** 2) * y1
        tx_vec = 2.0 * omt_a * (cx_ctrl - x0) + 2.0 * t_arr * (x1 - cx_ctrl)
        ty_vec = 2.0 * omt_a * (cy_ctrl - y0) + 2.0 * t_arr * (y1 - cy_ctrl)
        tnorm = np.maximum(np.hypot(tx_vec, ty_vec), 1e-12)
        ux = tx_vec / tnorm
        uy = ty_vec / tnorm
        vx = -uy
        vy = ux

        fig = ax.figure
        pos = ax.get_position()
        fig_w_in = float(fig.get_size_inches()[0]) if fig is not None else 8.5
        box_w_pt = max(float(pos.width) * fig_w_in * 72.0, 50.0)
        xlim = ax.get_xlim()
        seg_span_x = float(np.ptp(segments[:, :, 0])) * 1.08
        span_x = abs(float(xlim[1]) - float(xlim[0])) if ax.has_data() and abs(float(xlim[1]) - float(xlim[0])) > 1.01 else seg_span_x
        if span_x <= 0:
            span_x = max(seg_span_x, 1.0)
        data_per_pt = span_x / box_w_pt
        a_len = np.maximum(lws * 2.4, 5.5) * float(arrow_scale) * data_per_pt
        a_hw = a_len * 0.44

        tip_x = px + 0.35 * a_len * ux
        tip_y = py + 0.35 * a_len * uy
        lw_x = tip_x - a_len * ux + a_hw * vx
        lw_y = tip_y - a_len * uy + a_hw * vy
        nt_x = tip_x - 0.72 * a_len * ux
        nt_y = tip_y - 0.72 * a_len * uy
        rw_x = tip_x - a_len * ux - a_hw * vx
        rw_y = tip_y - a_len * uy - a_hw * vy
        verts = np.stack([
            np.column_stack([tip_x, tip_y]),
            np.column_stack([lw_x, lw_y]),
            np.column_stack([nt_x, nt_y]),
            np.column_stack([rw_x, rw_y]),
        ], axis=1)
        arrows = PolyCollection(
            verts,
            facecolors=rgba,
            edgecolors="#ffffff",
            linewidths=0.35,
            zorder=float(zorder) + 0.10,
            **tx_kw,
        )
        arrows.set_gid(gid)
        ax.add_collection(arrows)
        artists.append(arrows)

    legend_items: list[dict[str, Any]] = []
    for b in range(n_bins):
        lo, hi = edge_list[b], edge_list[b + 1]
        in_bin = cls_idx == b
        if np.any(in_bin):
            rep_lw = float(np.mean(lws[in_bin]))
            rep_alpha = float(np.mean(alphas[in_bin]))
        else:
            mid_u = (0.5 * (lo + hi) - vmin) / max(vmax - vmin, 1e-12) if vmax > vmin else 0.7
            mid_u = float(np.clip(mid_u, 0.0, 1.0))
            rep_lw = lw_min + (lw_max - lw_min) * (mid_u ** float(gamma))
            rep_alpha = al_min + (al_max - al_min) * mid_u
        lbl = _format_flow_num(lo) if abs(hi - lo) < 1e-9 else f"{_format_flow_num(lo)} – {_format_flow_num(hi)}"
        legend_items.append({
            "label": lbl,
            "color": cls_hex[b],
            "kind": "line",
            "linewidth": round(rep_lw, 2),
            "alpha": round(rep_alpha, 2),
        })

    return {
        "count": int(len(vals)),
        "breaks": edge_list,
        "colors": cls_hex,
        "linewidths": [round(float(x), 3) for x in lws],
        "alphas": [round(float(x), 3) for x in alphas],
        "legend_items": legend_items,
        "artists": artists,
    }


def add_size_legend(
    ax: Axes,
    items: Sequence[Any],
    *,
    shape: str = "circle",
    layout: str = "nested",
    title: str | None = None,
    loc: str = "center",
    bounds: Sequence[float] | None = None,
    facecolor: str = "#d96f32",
    edgecolor: str = "#ffffff",
    edgewidth: float = 0.8,
    alpha: float = 0.85,
    frameon: bool = True,
    frame_facecolor: str = "#faf9f7",
    frame_edgecolor: str = "#b8b4ac",
    frame_lw: float = 0.7,
    fontsize: float | None = None,
    title_fontsize: float | None = None,
    title_align: str = "center",
    line_items: Sequence[Any] | None = None,
    line_title: str | None = None,
    gid: str = "size_legend",
) -> dict[str, Any]:
    """绘制与 scatter(s=pt^2) 一一对应的嵌套/排布枢纽比例圆图例，可选与流线图例紧凑合卡。"""
    if shape.strip().lower() != "circle":
        raise ValueError("add_size_legend 当前仅支持 shape='circle'。")
    layout_norm = layout.strip().lower()
    if layout_norm not in {"nested", "vertical", "horizontal"}:
        raise ValueError("layout 仅支持 'nested'、'vertical' 或 'horizontal'。")
    align_norm = title_align.strip().lower()
    if align_norm not in {"left", "center", "right"}:
        raise ValueError(f"不支持的 title_align '{title_align}'。")

    parsed: list[dict[str, Any]] = []
    for raw in items:
        if isinstance(raw, dict):
            s_val = float(raw.get("size", raw.get("s", 36.0)))
            parsed.append({
                "label": str(raw["label"]),
                "size": s_val,
                "color": raw.get("color", facecolor),
                "edgecolor": raw.get("edgecolor", edgecolor),
                "edgewidth": float(raw.get("edgewidth", edgewidth)),
                "alpha": float(raw.get("alpha", alpha)),
            })
        elif isinstance(raw, (tuple, list)) and len(raw) >= 2:
            parsed.append({
                "label": str(raw[0]),
                "size": float(raw[1]),
                "color": facecolor,
                "edgecolor": edgecolor,
                "edgewidth": float(edgewidth),
                "alpha": float(alpha),
            })
        else:
            raise ValueError("items 元素需为 (label, size_pt2) 或包含 label/size 的字典。")
    if not parsed or any(not math.isfinite(p["size"]) or p["size"] <= 0 for p in parsed):
        raise ValueError("items 不能为空且每个 size 必须为正有限数值（scatter 点面积 pt^2）。")

    item_pt = float(_snap_even(_resolve_pt(fontsize, "legend.fontsize", 10.0), 10))
    hdr_pt = float(_snap_even(_resolve_pt(title_fontsize, "legend.title_fontsize", _snap_even(item_pt + 2.0, 12)), 10))

    if bounds is not None:
        if len(bounds) != 4:
            raise ValueError("bounds 必须为 4 元组 [x0, y0, width, height]。")
        target_ax = ax.inset_axes([float(v) for v in bounds], zorder=12)
        target_ax.set_axis_off()
        target_ax.set_gid(gid)
    elif ax.has_data() and getattr(ax, "axison", True):
        corner_map = {
            "lower left": [0.03, 0.04, 0.28, 0.34],
            "lower right": [0.69, 0.04, 0.28, 0.34],
            "upper left": [0.03, 0.62, 0.28, 0.34],
            "upper right": [0.69, 0.62, 0.28, 0.34],
            "center": [0.36, 0.33, 0.28, 0.34],
        }
        target_ax = ax.inset_axes(corner_map.get(loc.strip().lower(), corner_map["lower left"]), zorder=12)
        target_ax.set_axis_off()
        target_ax.set_gid(gid)
    else:
        target_ax = ax
        target_ax.set_axis_off()
        target_ax.set_gid(gid)

    if (layout_norm in {"vertical", "horizontal"}) and not (layout_norm == "vertical" and line_items):
        handles: list[Any] = []
        for entry in parsed:
            ms = 2.0 * math.sqrt(entry["size"] / math.pi)
            handles.append(
                Line2D(
                    [0], [0],
                    color="none",
                    marker="o",
                    markerfacecolor=entry["color"],
                    markeredgecolor=entry["edgecolor"],
                    markeredgewidth=entry["edgewidth"],
                    markersize=ms,
                    alpha=entry["alpha"],
                    label=entry["label"],
                )
            )
        if line_items:
            for lraw in line_items:
                if isinstance(lraw, dict):
                    handles.append(
                        Line2D(
                            [0], [0],
                            color=lraw["color"],
                            linewidth=float(lraw.get("linewidth", 1.8)),
                            alpha=float(lraw.get("alpha", 1.0)),
                            label=str(lraw["label"]),
                        )
                    )
                else:
                    handles.append(Line2D([0], [0], color=lraw[1], linewidth=1.8, label=str(lraw[0])))
        ncol = len(handles) if layout_norm == "horizontal" else 1
        leg = target_ax.legend(
            handles=handles,
            title=title or line_title,
            loc=loc,
            ncol=ncol,
            frameon=frameon,
            fontsize=item_pt,
            title_fontsize=hdr_pt,
            borderpad=0.6,
            labelspacing=0.65,
            columnspacing=1.0,
        )
        if frameon and leg is not None:
            fr = leg.get_frame()
            fr.set_facecolor(frame_facecolor)
            fr.set_edgecolor(frame_edgecolor)
            fr.set_linewidth(frame_lw)
        if leg is not None:
            leg.set_gid(gid)
            if hasattr(leg, "set_alignment"):
                leg.set_alignment(align_norm)
            if hasattr(leg, "_legend_box") and leg._legend_box is not None:
                leg._legend_box.align = align_norm
            if leg.get_title() is not None:
                leg.get_title().set_fontweight("bold")
        return {"ax": target_ax, "layout": layout_norm, "scale_factor": 1.0, "legend": leg}

    if layout_norm == "vertical" and line_items:
        target_ax.set_xlim(0.0, 1.0)
        target_ax.set_ylim(0.0, 1.0)
        v_artists: list[Any] = []
        if frameon:
            card = FancyBboxPatch(
                (0.02, 0.02),
                0.96,
                0.96,
                boxstyle="round,pad=0.0,rounding_size=0.025",
                facecolor=frame_facecolor,
                edgecolor=frame_edgecolor,
                linewidth=frame_lw,
                transform=target_ax.transAxes,
                zorder=1,
                gid=gid,
            )
            target_ax.add_patch(card)
            v_artists.append(card)

        lines_v: list[dict[str, Any]] = []
        for lraw in line_items:
            if isinstance(lraw, dict):
                lines_v.append({
                    "label": str(lraw["label"]),
                    "color": lraw["color"],
                    "linewidth": float(lraw.get("linewidth", 1.8)),
                    "alpha": float(lraw.get("alpha", 1.0)),
                })
            elif isinstance(lraw, (tuple, list)) and len(lraw) >= 2:
                lines_v.append({"label": str(lraw[0]), "color": lraw[1], "linewidth": 1.8, "alpha": 1.0})

        fig = target_ax.figure
        pos = target_ax.get_position()
        fig_w_in, fig_h_in = map(float, fig.get_size_inches()) if fig is not None else (8.5, 6.0)
        box_w_in = max(float(pos.width) * fig_w_in, 0.5)
        box_h_in = max(float(pos.height) * fig_h_in, 0.5)

        circ_weight = (1.2 if title else 0.0) + len(parsed) * 1.05
        line_weight = (1.2 if line_title else 0.0) + len(lines_v) * 0.90
        total_span = 0.88
        sec1_span = total_span * (circ_weight / max(circ_weight + line_weight, 1e-6))

        y_cur = 0.95
        tx_x = 0.50 if align_norm == "center" else (0.08 if align_norm == "left" else 0.92)
        if title:
            th1 = target_ax.text(
                tx_x, y_cur, str(title),
                fontsize=hdr_pt, fontweight="bold", color=GEO_COLORS["text_primary"],
                ha=align_norm, va="top", transform=target_ax.transAxes, zorder=4, gid=gid,
            )
            v_artists.append(th1)
            sec1_top = y_cur - min(0.11, ((hdr_pt * 1.45) / 72.0) / box_h_in + 0.02)
        else:
            sec1_top = y_cur - 0.01

        div_y = 0.95 - sec1_span
        circ_bot = div_y + 0.025
        row_h_in = max((sec1_top - circ_bot) * box_h_in / max(len(parsed), 1), 0.08)
        raw_r_in = [math.sqrt(p["size"] / math.pi) / 72.0 for p in parsed]
        max_r_in = max(raw_r_in)
        scale_v = min(1.0, (0.44 * row_h_in) / max_r_in, (0.14 * box_w_in) / max_r_in)
        cx_v = max(0.10 + (max_r_in * scale_v) / box_w_in, 0.19)
        lbl_x_v = max(cx_v + (max_r_in * scale_v) / box_w_in + 0.10, 0.34)
        step_c = (sec1_top - circ_bot) / max(len(parsed), 1)
        for idx_c, (entry, r_in) in enumerate(zip(parsed, raw_r_in)):
            yc = sec1_top - (idx_c + 0.5) * step_c
            r_sc = r_in * scale_v
            if fig is not None:
                c_trans = fig.dpi_scale_trans + mtransforms.ScaledTranslation(cx_v, yc, target_ax.transAxes)
                circ = Circle(
                    (0.0, 0.0), radius=r_sc,
                    facecolor=entry["color"], edgecolor=entry["edgecolor"],
                    linewidth=entry["edgewidth"], alpha=entry["alpha"],
                    transform=c_trans, zorder=4, gid=gid,
                )
            else:
                circ = Circle(
                    (cx_v, yc), radius=r_sc,
                    facecolor=entry["color"], edgecolor=entry["edgecolor"],
                    linewidth=entry["edgewidth"], alpha=entry["alpha"],
                    transform=target_ax.transAxes, zorder=4, gid=gid,
                )
            tc = target_ax.text(
                lbl_x_v, yc, entry["label"],
                fontsize=item_pt, color=GEO_COLORS["text_primary"],
                ha="left", va="center", transform=target_ax.transAxes, zorder=4, gid=gid,
            )
            target_ax.add_patch(circ)
            v_artists.extend([circ, tc])

        div, = target_ax.plot(
            [0.07, 0.93], [div_y, div_y],
            color="#d8d4cc", linewidth=0.65, transform=target_ax.transAxes, zorder=3, gid=gid,
        )
        v_artists.append(div)

        y_cur2 = div_y - 0.025
        if line_title:
            th2 = target_ax.text(
                tx_x, y_cur2, str(line_title),
                fontsize=hdr_pt, fontweight="bold", color=GEO_COLORS["text_primary"],
                ha=align_norm, va="top", transform=target_ax.transAxes, zorder=4, gid=gid,
            )
            v_artists.append(th2)
            row2_top = y_cur2 - min(0.11, ((hdr_pt * 1.45) / 72.0) / box_h_in + 0.02)
        else:
            row2_top = y_cur2 - 0.01

        step_l = (row2_top - 0.05) / max(len(lines_v), 1)
        for idx_l, lrow in enumerate(lines_v):
            yl = row2_top - (idx_l + 0.45) * step_l
            ln, = target_ax.plot(
                [0.08, 0.28], [yl, yl],
                color=lrow["color"], linewidth=lrow["linewidth"], alpha=lrow["alpha"],
                solid_capstyle="round", transform=target_ax.transAxes, zorder=4, gid=gid,
            )
            tl = target_ax.text(
                0.34, yl, lrow["label"],
                fontsize=item_pt, color=GEO_COLORS["text_primary"],
                ha="left", va="center", transform=target_ax.transAxes, zorder=4, gid=gid,
            )
            v_artists.extend([ln, tl])

        return {"ax": target_ax, "layout": "vertical", "scale_factor": round(float(scale_v), 4), "artists": v_artists}

    # layout == "nested": 紧凑暖色卡片内组合线宽分级与同底切嵌套比例圆
    target_ax.set_xlim(0.0, 1.0)
    target_ax.set_ylim(0.0, 1.0)
    artists: list[Any] = []
    if frameon:
        card = FancyBboxPatch(
            (0.02, 0.02),
            0.96,
            0.96,
            boxstyle="round,pad=0.0,rounding_size=0.025",
            facecolor=frame_facecolor,
            edgecolor=frame_edgecolor,
            linewidth=frame_lw,
            transform=target_ax.transAxes,
            zorder=1,
            gid=gid,
        )
        target_ax.add_patch(card)
        artists.append(card)

    parsed_desc = sorted(parsed, key=lambda item: item["size"], reverse=True)
    fig = target_ax.figure
    pos = target_ax.get_position()
    fig_w_in, fig_h_in = map(float, fig.get_size_inches()) if fig is not None else (8.5, 6.0)
    box_w_in = max(float(pos.width) * fig_w_in, 0.5)
    box_h_in = max(float(pos.height) * fig_h_in, 0.5)

    lines_norm: list[dict[str, Any]] = []
    if line_items:
        for lraw in line_items:
            if isinstance(lraw, dict):
                lines_norm.append({
                    "label": str(lraw["label"]),
                    "color": lraw["color"],
                    "linewidth": float(lraw.get("linewidth", 1.8)),
                    "alpha": float(lraw.get("alpha", 1.0)),
                })
            elif isinstance(lraw, (tuple, list)) and len(lraw) >= 2:
                lines_norm.append({"label": str(lraw[0]), "color": lraw[1], "linewidth": 1.8, "alpha": 1.0})

    line_rows = (1.15 if line_title else 0.0) + len(lines_norm) * 0.90
    circ_rows = (1.15 if title else 0.0) + max(len(parsed_desc) * 1.0, 2.6)
    y_cursor = 0.94

    if lines_norm:
        frac_line = min(0.62, line_rows / max(line_rows + circ_rows, 1e-6))
        sec1_h = max(0.24, frac_line * 0.86)
        sec1_bot = y_cursor - sec1_h
        if line_title:
            tx_h = 0.50 if align_norm == "center" else (0.08 if align_norm == "left" else 0.92)
            t1 = target_ax.text(
                tx_h,
                y_cursor,
                str(line_title),
                fontsize=hdr_pt,
                fontweight="bold",
                color=GEO_COLORS["text_primary"],
                ha=align_norm,
                va="top",
                transform=target_ax.transAxes,
                zorder=4,
                gid=gid,
            )
            artists.append(t1)
        row_top = y_cursor - (0.09 if line_title else 0.02)
        n_ln = len(lines_norm)
        step_ln = (row_top - sec1_bot) / max(n_ln, 1)
        for idx_l, lrow in enumerate(lines_norm):
            yl = row_top - (idx_l + 0.45) * step_ln
            ln, = target_ax.plot(
                [0.08, 0.28],
                [yl, yl],
                color=lrow["color"],
                linewidth=lrow["linewidth"],
                alpha=lrow["alpha"],
                solid_capstyle="round",
                transform=target_ax.transAxes,
                zorder=4,
                gid=gid,
            )
            tl = target_ax.text(
                0.34,
                yl,
                lrow["label"],
                fontsize=item_pt,
                color=GEO_COLORS["text_primary"],
                ha="left",
                va="center",
                transform=target_ax.transAxes,
                zorder=4,
                gid=gid,
            )
            artists.extend([ln, tl])
        div_y = sec1_bot - 0.02
        div, = target_ax.plot(
            [0.07, 0.93],
            [div_y, div_y],
            color="#d8d4cc",
            linewidth=0.65,
            transform=target_ax.transAxes,
            zorder=3,
            gid=gid,
        )
        artists.append(div)
        y_cursor = div_y - 0.03

    if title:
        tx_h2 = 0.50 if align_norm == "center" else (0.08 if align_norm == "left" else 0.92)
        t2 = target_ax.text(
            tx_h2,
            y_cursor,
            str(title),
            fontsize=hdr_pt,
            fontweight="bold",
            color=GEO_COLORS["text_primary"],
            ha=align_norm,
            va="top",
            transform=target_ax.transAxes,
            zorder=4,
            gid=gid,
        )
        artists.append(t2)
        sec2_top = y_cursor - min(0.11, ((hdr_pt * 1.45) / 72.0) / box_h_in + 0.02)
    else:
        sec2_top = y_cursor - 0.02

    sec2_bot = 0.06
    raw_r_in = [math.sqrt(entry["size"] / math.pi) / 72.0 for entry in parsed_desc]
    max_r_in = max(raw_r_in)
    avail_h_in = max((sec2_top - sec2_bot) * box_h_in * 0.84, 0.12)
    avail_w_in = max(0.32 * box_w_in, 0.12)
    scale_factor = min(1.0, (0.5 * avail_h_in) / max_r_in, avail_w_in / max_r_in)
    r_ins = [r * scale_factor for r in raw_r_in]
    r_max_scaled = max(r_ins)

    cx_ax = max(0.08 + r_max_scaled / box_w_in, 0.22)
    circ_bot_ax = sec2_bot + 0.02
    label_x_ax = max(cx_ax + r_max_scaled / box_w_in + 0.16, 0.52)

    raw_lbl_ys = [circ_bot_ax + (2.0 * r) / box_h_in for r in r_ins]
    min_gap_ax = ((item_pt * 1.32) / 72.0) / box_h_in
    # 自底向上推开较小气泡文字，保证零重叠
    lbl_ys = list(raw_lbl_ys)
    for k in range(len(lbl_ys) - 2, -1, -1):
        lbl_ys[k] = max(lbl_ys[k], lbl_ys[k + 1] + min_gap_ax)
    max_allow_y = sec2_top - 0.02
    if lbl_ys and lbl_ys[0] > max_allow_y:
        shift = lbl_ys[0] - max_allow_y
        lbl_ys = [max(circ_bot_ax + 0.02, y - shift) for y in lbl_ys]
        too_close = len(lbl_ys) > 1 and any(lbl_ys[k] - lbl_ys[k + 1] < min_gap_ax * 0.85 for k in range(len(lbl_ys) - 1))
        if too_close:
            top_spread = min(max_allow_y, max(lbl_ys[0], circ_bot_ax + 0.02 + (len(lbl_ys) - 1) * min_gap_ax))
            lbl_ys = list(np.linspace(top_spread, circ_bot_ax + 0.02, len(lbl_ys)))

    offset_trans = mtransforms.ScaledTranslation(cx_ax, circ_bot_ax, target_ax.transAxes)
    circle_trans = fig.dpi_scale_trans + offset_trans if fig is not None else target_ax.transAxes

    for idx_c, (entry, r_in, y_top_raw, y_lbl) in enumerate(zip(parsed_desc, r_ins, raw_lbl_ys, lbl_ys)):
        if fig is not None:
            circ = Circle(
                (0.0, r_in),
                radius=r_in,
                facecolor=entry["color"],
                edgecolor=entry["edgecolor"],
                linewidth=entry["edgewidth"],
                alpha=entry["alpha"],
                transform=circle_trans,
                zorder=3 + idx_c * 0.1,
                gid=gid,
            )
        else:
            circ = Circle(
                (cx_ax, circ_bot_ax + r_in),
                radius=r_in,
                facecolor=entry["color"],
                edgecolor=entry["edgecolor"],
                linewidth=entry["edgewidth"],
                alpha=entry["alpha"],
                transform=target_ax.transAxes,
                zorder=3 + idx_c * 0.1,
                gid=gid,
            )
        target_ax.add_patch(circ)
        artists.append(circ)

        elbow_x = cx_ax + (r_max_scaled / box_w_in) + 0.06
        lead_end_x = label_x_ax - 0.03
        lead, = target_ax.plot(
            [cx_ax, elbow_x, lead_end_x],
            [y_top_raw, y_lbl, y_lbl],
            color="#6b727a",
            linewidth=0.65,
            linestyle=":",
            transform=target_ax.transAxes,
            zorder=4,
            gid=gid,
        )
        txt = target_ax.text(
            label_x_ax,
            y_lbl,
            entry["label"],
            fontsize=item_pt,
            color=GEO_COLORS["text_primary"],
            ha="left",
            va="center",
            transform=target_ax.transAxes,
            zorder=4,
            gid=gid,
        )
        artists.extend([lead, txt])

    return {
        "ax": target_ax,
        "layout": "nested",
        "scale_factor": round(float(scale_factor), 4),
        "artists": artists,
    }
