"""经纬网刻度、比例尺与指北针、图例、色带及像素级墨水避让原语。"""
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
from gis_agent.integrations.plotting.connectors import add_locator_inset
from gis_agent.integrations.plotting.palettes import (
    DIVERGING_PALETTES, GEO_COLORS, QUALITATIVE_PALETTES, SEQUENTIAL_PALETTES,
    _CRAMERI_DIVERGING_STOPS, _CRAMERI_NAMES, _check_banned_cmap,
    get_bivariate_palette, get_scientific_cmap,
)
from gis_agent.integrations.plotting.theme import _resolve_pt, _snap_even

def _format_dms(value: float, *, is_lon: bool, dms: bool) -> str:
    hemi = ("E" if value >= 0 else "W") if is_lon else ("N" if value >= 0 else "S")
    if abs(value) < 1e-9 or (not is_lon and abs(value) < 1e-9):
        return "0°"
    if not dms:
        return f"{abs(value):.4g}°{hemi}"
    total_sec = round(abs(value) * 3600.0)
    deg = total_sec // 3600
    rem = total_sec % 3600
    minutes = rem // 60
    sec = rem % 60
    if sec:
        return f"{deg}°{minutes}'{sec}\"{hemi}"
    if minutes:
        return f"{deg}°{minutes}'{hemi}"
    return f"{deg}°{hemi}"


def _looks_geographic_crs(crs: Any, xlim: tuple[float, float], ylim: tuple[float, float]) -> bool:
    if crs is not None:
        try:
            import pyproj

            parsed = crs if isinstance(crs, pyproj.CRS) else pyproj.CRS.from_user_input(crs)
            return bool(parsed.is_geographic)
        except Exception:
            pass
        text = str(crs).upper()
        if "4326" in text or "4269" in text or "GEOG" in text:
            return True
        return False
    return -180.5 <= xlim[0] <= xlim[1] <= 180.5 and -90.5 <= ylim[0] <= ylim[1] <= 90.5


_GEO_STEPS_WIDE: tuple[float, ...] = (30.0, 20.0, 15.0, 10.0, 5.0, 2.0, 1.0)
_GEO_STEPS_FINE: tuple[float, ...] = (
    1.0, 0.5, 0.25, 1.0 / 6.0, 1.0 / 12.0, 1.0 / 30.0, 1.0 / 60.0,
)


def _choose_geo_step(span_deg: float) -> float:
    span = abs(float(span_deg))
    if not math.isfinite(span) or span <= 0.0:
        return 1.0
    pool = _GEO_STEPS_WIDE if span >= 2.5 else _GEO_STEPS_FINE
    return min(
        pool,
        key=lambda s: (0 if 3.2 <= span / s <= 6.2 else 1, abs(span / s - 4.8)),
    )


def _parse_step_pair(step_val: float | tuple[float, float] | Sequence[float]) -> tuple[float, float]:
    if isinstance(step_val, (tuple, list)):
        sx, sy = float(step_val[0]), float(step_val[1])
    else:
        sx = sy = float(step_val)
    if not (math.isfinite(sx) and math.isfinite(sy)) or sx <= 0.0 or sy <= 0.0:
        raise ValueError("step_deg / step 必须为正数。")
    return sx, sy


def _projected_geo_ticks(
    parsed_crs: Any,
    xlim: tuple[float, float],
    ylim: tuple[float, float],
    *,
    step_deg: float | tuple[float, float] | None = None,
) -> tuple[list[float], list[float]] | None:
    """在投影坐标轴上迭代反求整数经纬度（或整分）对应的投影刻度坐标。"""
    try:
        import pyproj

        x0, x1 = sorted((float(xlim[0]), float(xlim[1])))
        y0, y1 = sorted((float(ylim[0]), float(ylim[1])))
        span_x, span_y = x1 - x0, y1 - y0
        if not (math.isfinite(span_x) and math.isfinite(span_y)) or span_x <= 0.0 or span_y <= 0.0:
            return None

        inv = pyproj.Transformer.from_crs(parsed_crs, "EPSG:4326", always_xy=True)
        fwd = pyproj.Transformer.from_crs("EPSG:4326", parsed_crs, always_xy=True)

        x_mid = 0.5 * (x0 + x1)
        y_mid = 0.5 * (y0 + y1)
        lon_mid, lat_mid = inv.transform(x_mid, y_mid)
        if not (math.isfinite(lon_mid) and math.isfinite(lat_mid)) or abs(lat_mid) >= 89.5:
            return None

        gx = np.linspace(x0, x1, 5)
        gy = np.linspace(y0, y1, 5)
        xx, yy = np.meshgrid(gx, gy)
        lons_grid, lats_grid = inv.transform(xx.ravel(), yy.ravel())
        lons_arr = np.asarray(lons_grid, dtype=float)
        lats_arr = np.asarray(lats_grid, dtype=float)
        valid = (
            np.isfinite(lons_arr)
            & np.isfinite(lats_arr)
            & (lons_arr >= -180.0)
            & (lons_arr <= 180.0)
            & (lats_arr >= -90.0)
            & (lats_arr <= 90.0)
        )
        if int(np.sum(valid)) < 5:
            return None
        lons_v = lons_arr[valid]
        lats_v = lats_arr[valid]
        if float(np.ptp(lons_v)) > 175.0:
            return None

        lon_min, lon_max = float(np.min(lons_v)), float(np.max(lons_v))
        lat_min, lat_max = float(np.min(lats_v)), float(np.max(lats_v))
        lon_span = lon_max - lon_min
        lat_span = lat_max - lat_min
        if not (1e-4 < lon_span < 175.0 and 1e-4 < lat_span < 170.0):
            return None

        if step_deg is not None:
            dx_deg, dy_deg = _parse_step_pair(step_deg)
        else:
            dx_deg = _choose_geo_step(lon_span)
            dy_deg = _choose_geo_step(lat_span)

        k_lon0 = math.floor(lon_min / dx_deg) - 1
        k_lon1 = math.ceil(lon_max / dx_deg) + 1
        k_lat0 = math.floor(lat_min / dy_deg) - 1
        k_lat1 = math.ceil(lat_max / dy_deg) + 1
        if (k_lon1 - k_lon0) > 60 or (k_lat1 - k_lat0) > 60:
            return None

        h_x = max(1e-6, span_x * 1e-4)
        h_y = max(1e-6, span_y * 1e-4)
        x_lo, x_hi = x0 + 0.025 * span_x, x1 - 0.025 * span_x
        y_lo, y_hi = y0 + 0.025 * span_y, y1 - 0.025 * span_y

        xs: list[float] = []
        for k in range(k_lon0, k_lon1 + 1):
            target_lon = k * dx_deg
            if not (-180.0 < target_lon < 180.0):
                continue
            x, _ = fwd.transform(target_lon, lat_mid)
            if not math.isfinite(x):
                continue
            for _ in range(8):
                lon_act, _ = inv.transform(x, y_mid)
                if not math.isfinite(lon_act):
                    break
                if abs(target_lon - lon_act) < 1e-7:
                    break
                lon_2, _ = inv.transform(x + h_x, y_mid)
                dlon_dx = (lon_2 - lon_act) / h_x
                if not math.isfinite(dlon_dx) or abs(dlon_dx) < 1e-12:
                    break
                x += (target_lon - lon_act) / dlon_dx
            lon_check, _ = inv.transform(x, y_mid)
            if math.isfinite(x) and math.isfinite(lon_check) and abs(lon_check - target_lon) < 1e-3:
                if x_lo < x < x_hi:
                    xs.append(float(x))

        ys: list[float] = []
        for k in range(k_lat0, k_lat1 + 1):
            target_lat = k * dy_deg
            if not (-89.5 < target_lat < 89.5):
                continue
            _, y = fwd.transform(lon_mid, target_lat)
            if not math.isfinite(y):
                continue
            for _ in range(8):
                _, lat_act = inv.transform(x_mid, y)
                if not math.isfinite(lat_act):
                    break
                if abs(target_lat - lat_act) < 1e-7:
                    break
                _, lat_2 = inv.transform(x_mid, y + h_y)
                dlat_dy = (lat_2 - lat_act) / h_y
                if not math.isfinite(dlat_dy) or abs(dlat_dy) < 1e-12:
                    break
                y += (target_lat - lat_act) / dlat_dy
            _, lat_check = inv.transform(x_mid, y)
            if math.isfinite(y) and math.isfinite(lat_check) and abs(lat_check - target_lat) < 1e-3:
                if y_lo < y < y_hi:
                    ys.append(float(y))

        xs = sorted(set(xs))
        ys = sorted(set(ys))
        if len(xs) >= 2 and len(ys) >= 2:
            return xs, ys
    except Exception:
        return None
    return None


def add_graticule_frame(
    ax: Axes,
    *,
    crs: Any = None,
    style: str = "ticks_only",
    dms: bool = True,
    step: float | tuple[float, float] | None = None,
    step_deg: float | tuple[float, float] | None = None,
    labelsize: float | None = None,
    color: str = GEO_COLORS["text_secondary"],
    grid_alpha: float = 0.38,
    zorder: int = 2,
) -> Any:
    """为普通 Axes 或 Cartopy GeoAxes 渲染克制的度分经纬框线或极简无框底板。"""
    if style not in {"ticks_only", "minimal_grid", "clean_borderless"}:
        raise ValueError(f"不支持的 graticule style '{style}'。")
    tick_pt = _resolve_pt(labelsize, "xtick.labelsize", 10.0)
    is_geo = hasattr(ax, "gridlines") and hasattr(ax, "projection")

    if style == "clean_borderless":
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(False)
        return None

    if is_geo:
        if "geo" in ax.spines:
            ax.spines["geo"].set_visible(True)
            ax.spines["geo"].set_linewidth(0.6)
            ax.spines["geo"].set_edgecolor("#4a4a4a")
        lw = 0.35 if style == "minimal_grid" else 0.0
        alpha = grid_alpha if style == "minimal_grid" else 0.0
        try:
            gl = ax.gridlines(
                draw_labels=True,
                dms=dms,
                x_inline=False,
                y_inline=False,
                linewidth=lw,
                color="#b8b8b8",
                alpha=alpha,
                linestyle="--",
                zorder=zorder,
            )
            gl.top_labels = False
            gl.right_labels = False
            gl.left_labels = True
            gl.bottom_labels = True
            gl.xlabel_style = {"size": tick_pt, "color": color}
            gl.ylabel_style = {"size": tick_pt, "color": color}
            eff_step = step_deg if step_deg is not None else step
            if eff_step is not None:
                sx, sy = _parse_step_pair(eff_step)
                gl.xlocator = mticker.MultipleLocator(sx)
                gl.ylocator = mticker.MultipleLocator(sy)
            return gl
        except Exception:
            if style == "minimal_grid":
                return ax.gridlines(draw_labels=False, linewidth=0.35, color="#b8b8b8", alpha=grid_alpha, linestyle="--", zorder=zorder)
            return None

    # 普通 Matplotlib Axes
    for sp in ax.spines.values():
        sp.set_visible(True)
        sp.set_linewidth(0.6)
        sp.set_edgecolor("#4a4a4a")

    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    is_geog = _looks_geographic_crs(crs, xlim, ylim)
    if step is not None:
        sx, sy = _parse_step_pair(step)
        ax.xaxis.set_major_locator(mticker.MultipleLocator(sx))
        ax.yaxis.set_major_locator(mticker.MultipleLocator(sy))
    elif is_geog:
        if step_deg is not None:
            sx, sy = _parse_step_pair(step_deg)
            ax.xaxis.set_major_locator(mticker.MultipleLocator(sx))
            ax.yaxis.set_major_locator(mticker.MultipleLocator(sy))
        else:
            span_x = abs(float(xlim[1]) - float(xlim[0]))
            span_y = abs(float(ylim[1]) - float(ylim[0]))
            if span_x > 1e-4 and span_y > 1e-4:
                ax.xaxis.set_major_locator(mticker.MultipleLocator(_choose_geo_step(span_x)))
                ax.yaxis.set_major_locator(mticker.MultipleLocator(_choose_geo_step(span_y)))
            else:
                ax.xaxis.set_major_locator(mticker.MaxNLocator(nbins=5))
                ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=5))
    else:
        ax.xaxis.set_major_locator(mticker.MaxNLocator(nbins=5))
        ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=5))

    if is_geog:
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda val, _: _format_dms(val, is_lon=True, dms=dms)))
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda val, _: _format_dms(val, is_lon=False, dms=dms)))
    elif crs is not None:
        try:
            import pyproj

            parsed = crs if isinstance(crs, pyproj.CRS) else pyproj.CRS.from_user_input(crs)
            if parsed.is_projected:
                transformer = pyproj.Transformer.from_crs(parsed, "EPSG:4326", always_xy=True)
                y_mid = 0.5 * (ylim[0] + ylim[1])
                x_mid = 0.5 * (xlim[0] + xlim[1])

                def _fmt_x(val: float, _pos: int) -> str:
                    lon, _ = transformer.transform(val, y_mid)
                    return _format_dms(lon, is_lon=True, dms=dms) if math.isfinite(lon) else f"{val:.0f}"

                def _fmt_y(val: float, _pos: int) -> str:
                    _, lat = transformer.transform(x_mid, val)
                    return _format_dms(lat, is_lon=False, dms=dms) if math.isfinite(lat) else f"{val:.0f}"

                ax.xaxis.set_major_formatter(mticker.FuncFormatter(_fmt_x))
                ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_y))
                if ax.get_xlabel() in {"Easting [metre]", "Easting [meter]"}:
                    ax.set_xlabel("")
                if ax.get_ylabel() in {"Northing [metre]", "Northing [meter]"}:
                    ax.set_ylabel("")
                if step is None or step_deg is not None:
                    solved = _projected_geo_ticks(parsed, xlim, ylim, step_deg=step_deg)
                    if solved is not None:
                        xt, yt = list(solved[0]), list(solved[1])
                        if step_deg is None and ax.figure is not None:
                            fig_w, _ = map(float, ax.figure.get_size_inches())
                            box_w_in = max(float(ax.get_position().width) * fig_w, 0.5)
                            max_x_ticks = max(2, int(box_w_in / max(tick_pt * 5.2 / 72.0, 0.50)))
                            if len(xt) > max_x_ticks:
                                xt = xt[:: max(2, math.ceil(len(xt) / max_x_ticks))]
                        ax.set_xticks(xt)
                        ax.set_yticks(yt)
        except Exception:
            pass

    ax.tick_params(
        axis="both",
        which="major",
        labelsize=tick_pt,
        colors=color,
        direction="out",
        length=2.8,
        width=0.55,
        labeltop=False,
        labelright=False,
        labelbottom=True,
        labelleft=True,
        top=True,
        right=True,
    )
    if style == "minimal_grid":
        ax.grid(True, which="major", linestyle="--", linewidth=0.35, color="#b8b8b8", alpha=grid_alpha, zorder=zorder)
    else:
        ax.grid(False)
    return None

def _nice_scale_length(target_m: float) -> float:
    if target_m <= 0 or not math.isfinite(target_m):
        return 1000.0
    exp = 10.0 ** math.floor(math.log10(target_m))
    frac = target_m / exp
    for mult in (1.0, 2.0, 2.5, 5.0, 10.0):
        if frac <= mult * 1.15:
            return mult * exp
    return 10.0 * exp


def add_scalebar_and_north(
    ax: Axes,
    *,
    crs_units: str = "metre",
    lat_center: float | None = None,
    loc: str = "lower left",
    scale: bool = True,
    north: bool = True,
    north_loc: str = "upper left",
    color: str = GEO_COLORS["text_primary"],
    fontsize: float | None = None,
    use_matplotlib_scalebar: bool = False,
    scale_style: str = "cartographic",
    north_style: str = "compass_star",
) -> dict[str, Any]:
    """自动选择整洁比例尺长度并渲染出版级分段比例尺（cartographic/ticked/double_box）与罗盘星指北针（compass_star/sleek_needle/chevron/line_arrow）。"""
    scale_st = scale_style.strip().lower()
    if scale_st not in {"cartographic", "ticked", "double_box"}:
        raise ValueError(f"不支持的 scale_style '{scale_style}'；可选 'cartographic'、'ticked' 或 'double_box'。")
    north_st = north_style.strip().lower()
    if north_st not in {"compass_star", "sleek_needle", "chevron", "line_arrow"}:
        raise ValueError(f"不支持的 north_style '{north_style}'；可选 'compass_star'、'sleek_needle'、'chevron' 或 'line_arrow'。")

    tick_pt = _resolve_pt(fontsize, "xtick.labelsize", 10.0)
    north_pt = _snap_even(tick_pt + 2.0, 12)
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    span_x = abs(float(xlim[1]) - float(xlim[0]))
    if span_x <= 0 or not math.isfinite(span_x):
        return {"scale_length_m": None, "backend": "none"}

    units_norm = crs_units.strip().lower()
    if units_norm in {"metre", "meter", "metres", "meters", "m"}:
        dx_metres = span_x
    elif units_norm in {"km", "kilometre", "kilometres", "kilometer", "kilometers"}:
        dx_metres = span_x * 1000.0
    elif units_norm in {"degree", "degrees", "deg"}:
        lat = float(lat_center) if lat_center is not None else 0.5 * (float(ylim[0]) + float(ylim[1]))
        lat = max(-85.0, min(85.0, lat))
        dx_metres = span_x * 111_320.0 * max(math.cos(math.radians(lat)), 0.1)
    else:
        raise ValueError(f"不支持的 crs_units '{crs_units}'。")

    fig = ax.figure
    fig_w, fig_h = map(float, fig.get_size_inches()) if fig is not None else (8.5, 6.0)
    pos = ax.get_position()
    box_w_in = max(float(pos.width) * fig_w, 0.5)
    box_h_in = max(float(pos.height) * fig_h, 0.5)
    aspect_xy = float(np.clip(box_h_in / box_w_in, 0.45, 2.2))

    target_frac = 0.16 if box_w_in < 3.6 else 0.22
    max_frac = 0.24 if box_w_in < 3.6 else 0.35
    bar_metres = _nice_scale_length(dx_metres * target_frac)
    frac_len = max(0.08, min(max_frac, bar_metres / max(dx_metres, 1e-9)))
    bar_metres = _nice_scale_length(dx_metres * frac_len)
    frac_len = max(0.08, min(max_frac, bar_metres / max(dx_metres, 1e-9)))

    resolved_loc: str | None = None
    if scale:
        resolved_loc = loc.strip().lower()
        if resolved_loc == "auto":
            try:
                est_w_frac = max(0.24, frac_len + (0.14 if box_w_in < 3.6 else 0.08))
                ranked_sb = rank_quiet_corners(
                    ax,
                    candidates=("lower left", "lower right", "lower center"),
                    box_frac=(min(0.45, est_w_frac), 0.14),
                )
                resolved_loc = ranked_sb[0][0]
            except Exception:
                resolved_loc = "lower left"

    use_km = bar_metres >= 1000.0
    unit_label = "km" if use_km else "m"
    end_val = bar_metres / 1000.0 if use_km else bar_metres
    mid_val = end_val / 2.0
    fmt = lambda v: f"{int(round(v))}" if abs(v - round(v)) < 1e-6 else f"{v:.1f}"

    is_geo = hasattr(ax, "projection")
    backend = f"cartographic_{scale_st}" if scale else "north_only"
    scale_artist = None

    if scale and use_matplotlib_scalebar and (not is_geo) and units_norm in {"metre", "meter", "m"}:
        try:
            from matplotlib_scalebar.scalebar import ScaleBar

            sb = ScaleBar(
                1.0,
                units="m",
                location=resolved_loc,
                color=color,
                box_alpha=0.0,
                font_properties={"size": tick_pt},
                length_fraction=0.22,
                scale_loc="bottom",
                pad=0.35,
                sep=2,
            )
            if hasattr(sb, "set_gid"):
                sb.set_gid("scalebar")
            ax.add_artist(sb)
            scale_artist = sb
            backend = "matplotlib_scalebar"
        except Exception:
            pass

    if scale and backend != "matplotlib_scalebar":
        loc_norm = resolved_loc
        end_label = f"{fmt(end_val)} {unit_label}"
        pad_x_left = max(0.055, 0.035 + (tick_pt * 0.45 / 72.0) / box_w_in)
        pad_x_right = max(0.068, 0.045 + (len(end_label) * tick_pt * 0.36 / 72.0) / box_w_in)
        if "right" in loc_norm:
            x0 = max(0.04, 1.0 - pad_x_right - frac_len)
        elif "center" in loc_norm:
            x0 = 0.5 - 0.5 * frac_len
        else:
            x0 = pad_x_left

        lbl_h_frac = (tick_pt * 1.25 / 72.0) / box_h_in
        y0 = (1.0 - 0.052 - 0.015 - lbl_h_frac) if "upper" in loc_norm else 0.052
        halo = [path_effects.withStroke(linewidth=2.2, foreground="#ffffff", alpha=0.92)]
        scale_parts: list[Any] = []

        if scale_st in {"cartographic", "double_box"}:
            bar_h = 0.0085
            q = frac_len * 0.25
            h2 = frac_len * 0.50
            blocks = (
                (0.0, q, color),
                (q, q, "#ffffff"),
                (h2, h2, color),
            )
            if scale_st == "double_box":
                blocks = [(i * q, q, color if i % 2 == 0 else "#ffffff") for i in range(4)]
            for bx, bw, bcol in blocks:
                seg = Rectangle(
                    (x0 + bx, y0), bw, bar_h,
                    facecolor=bcol, edgecolor=color, linewidth=0.65,
                    transform=ax.transAxes, zorder=12, gid="scalebar",
                )
                ax.add_patch(seg)
                scale_parts.append(seg)
                if scale_st == "double_box":
                    upper = Rectangle(
                        (x0 + bx, y0 + bar_h / 2), bw, bar_h / 2,
                        facecolor="#ffffff" if bcol == color else color, edgecolor=color,
                        linewidth=0.65, transform=ax.transAxes, zorder=12, gid="scalebar",
                    )
                    ax.add_patch(upper)
                    scale_parts.append(upper)
            for frac in (0.0, 0.5, 1.0):
                rx = x0 + frac * frac_len
                riser, = ax.plot(
                    [rx, rx], [y0 + bar_h, y0 + bar_h + 0.0055],
                    color=color, linewidth=0.65, transform=ax.transAxes, zorder=12, gid="scalebar",
                )
                scale_parts.append(riser)
            lbl_y = y0 + bar_h + 0.009
        else:
            base_line, = ax.plot(
                [x0, x0 + frac_len], [y0, y0],
                color=color, linewidth=0.9, transform=ax.transAxes, zorder=12, gid="scalebar",
            )
            scale_parts.append(base_line)
            for frac, th in ((0.0, 0.011), (0.25, 0.0065), (0.5, 0.011), (1.0, 0.011)):
                rx = x0 + frac * frac_len
                tick_ln, = ax.plot(
                    [rx, rx], [y0, y0 + th],
                    color=color, linewidth=0.75, transform=ax.transAxes, zorder=12, gid="scalebar",
                )
                scale_parts.append(tick_ln)
            lbl_y = y0 + 0.015

        bar_w_in = frac_len * box_w_in
        end_half_w_in = 0.5 * len(end_label) * tick_pt * 0.55 / 72.0 + (tick_pt * 0.4 / 72.0)
        end_ha = "center" if bar_w_in >= max(0.34, end_half_w_in * 1.05) else "left"
        end_x = (x0 + frac_len) if end_ha == "center" else (x0 + frac_len + 0.012)
        ax.text(
            x0, lbl_y, "0", fontsize=tick_pt, color=color, ha="center", va="bottom",
            transform=ax.transAxes, zorder=13, gid="scalebar", path_effects=halo,
        )
        if bar_w_in >= 1.15 and frac_len >= 0.22:
            ax.text(
                x0 + 0.5 * frac_len, lbl_y, fmt(mid_val), fontsize=tick_pt, color=color,
                ha="center", va="bottom", transform=ax.transAxes, zorder=13, gid="scalebar", path_effects=halo,
            )
        ax.text(
            end_x, lbl_y, end_label, fontsize=tick_pt, color=color,
            ha=end_ha, va="bottom", transform=ax.transAxes, zorder=13, gid="scalebar", path_effects=halo,
        )
        scale_artist = scale_parts

    north_artists: list[Any] = []
    resolved_north_loc: str | None = None
    if north:
        nloc = north_loc.strip().lower()
        if nloc == "auto":
            try:
                ranked_na = rank_quiet_corners(
                    ax,
                    exclude=(resolved_loc,) if resolved_loc else (),
                    candidates=("upper right", "upper left"),
                    box_frac=(0.14, 0.18),
                )
                nloc = ranked_na[0][0]
            except Exception:
                nloc = "upper right" if resolved_loc != "upper right" else "upper left"
        resolved_north_loc = nloc
        n_h_frac = (north_pt * 1.25 / 72.0) / box_h_in
        r_n = 0.044
        r_s = 0.028
        r_ew = 0.026
        sx = r_ew * aspect_xy
        nx_margin = max(0.055 + sx, 0.055 + (north_pt * 0.50 / 72.0) / box_w_in)
        nx = nx_margin if "left" in nloc else (1.0 - nx_margin if "right" in nloc else 0.50)
        ny = (1.0 - 0.048 - r_n - 0.010 - n_h_frac) if "upper" in nloc else (0.052 + r_s)
        n_halo = [path_effects.withStroke(linewidth=2.0, foreground="#ffffff", alpha=0.90)]

        if north_st == "compass_star":
            r_ring = 0.62 * r_s
            ring = Ellipse(
                (nx, ny), width=2.0 * r_ring * aspect_xy, height=2.0 * r_ring,
                facecolor="none", edgecolor=color, linewidth=0.55, alpha=0.55,
                transform=ax.transAxes, zorder=11.5, gid="north_arrow",
            )
            ax.add_patch(ring)
            north_artists.append(ring)

            wx = 0.25 * sx
            wy = 0.25 * r_ew
            p_n = (nx, ny + r_n)
            p_e = (nx + sx, ny)
            p_s = (nx, ny - r_s)
            p_w = (nx - sx, ny)
            p_ne = (nx + wx, ny + wy)
            p_se = (nx + wx, ny - wy)
            p_sw = (nx - wx, ny - wy)
            p_nw = (nx - wx, ny + wy)
            center = (nx, ny)
            facets = (
                ((center, p_n, p_ne), color),
                ((center, p_n, p_nw), "#ffffff"),
                ((center, p_e, p_se), color),
                ((center, p_e, p_ne), "#ffffff"),
                ((center, p_s, p_sw), color),
                ((center, p_s, p_se), "#ffffff"),
                ((center, p_w, p_nw), color),
                ((center, p_w, p_sw), "#ffffff"),
            )
            for pts, fc in facets:
                tri = matplotlib.patches.Polygon(
                    pts, closed=True, facecolor=fc, edgecolor=color, linewidth=0.55,
                    transform=ax.transAxes, zorder=12, gid="north_arrow",
                )
                ax.add_patch(tri)
                north_artists.append(tri)
        elif north_st == "sleek_needle":
            hw = 0.34 * sx
            mid_y = ny - 0.15 * r_s
            left_p = matplotlib.patches.Polygon(
                [(nx, ny + r_n), (nx - hw, mid_y), (nx, ny)],
                closed=True, facecolor=color, edgecolor=color, linewidth=0.65,
                transform=ax.transAxes, zorder=12, gid="north_arrow",
            )
            right_p = matplotlib.patches.Polygon(
                [(nx, ny + r_n), (nx + hw, mid_y), (nx, ny)],
                closed=True, facecolor="#ffffff", edgecolor=color, linewidth=0.65,
                transform=ax.transAxes, zorder=12, gid="north_arrow",
            )
            tail, = ax.plot(
                [nx, nx], [ny - r_s, ny], color=color, linewidth=0.8,
                transform=ax.transAxes, zorder=12, gid="north_arrow",
            )
            cross, = ax.plot(
                [nx - 0.45 * sx, nx + 0.45 * sx], [ny - 0.35 * r_s, ny - 0.35 * r_s],
                color=color, linewidth=0.65, transform=ax.transAxes, zorder=12, gid="north_arrow",
            )
            ax.add_patch(left_p)
            ax.add_patch(right_p)
            north_artists.extend([left_p, right_p, tail, cross])
        elif north_st == "line_arrow":
            shaft, = ax.plot([nx, nx], [ny - r_s, ny + r_n], color=color, linewidth=1.0,
                             transform=ax.transAxes, zorder=12, gid="north_arrow")
            head, = ax.plot([nx - sx * 0.6, nx, nx + sx * 0.6],
                            [ny, ny + r_n, ny], color=color, linewidth=1.0,
                            transform=ax.transAxes, zorder=12, gid="north_arrow")
            north_artists.extend([shaft, head])
        else:
            cw = 0.54 * sx
            left_poly = matplotlib.patches.Polygon(
                [(nx, ny + r_n), (nx - cw, ny - 0.5 * r_s), (nx, ny - 0.05 * r_s)],
                closed=True, facecolor=color, edgecolor=color, linewidth=0.7,
                transform=ax.transAxes, zorder=12, gid="north_arrow",
            )
            right_poly = matplotlib.patches.Polygon(
                [(nx, ny + r_n), (nx + cw, ny - 0.5 * r_s), (nx, ny - 0.05 * r_s)],
                closed=True, facecolor="#ffffff", edgecolor=color, linewidth=0.7,
                transform=ax.transAxes, zorder=12, gid="north_arrow",
            )
            ax.add_patch(left_poly)
            ax.add_patch(right_poly)
            north_artists.extend([left_poly, right_poly])

        n_txt = ax.text(
            nx, ny + r_n + 0.010, "N",
            fontsize=north_pt, fontweight="bold", color=color,
            ha="center", va="bottom", transform=ax.transAxes, zorder=13, gid="north_arrow",
            path_effects=n_halo,
        )
        north_artists.append(n_txt)

    return {
        "scale_length_m": bar_metres if scale else None,
        "label": f"{fmt(end_val)} {unit_label}" if scale else None,
        "backend": backend,
        "scale_style": scale_st,
        "north_style": north_st,
        "scalebar_loc": resolved_loc,
        "north_loc": resolved_north_loc,
        "scale_artist": scale_artist,
        "north_artists": north_artists,
    }

def add_bivariate_legend(
    fig_or_ax: Figure | Axes,
    bounds: Sequence[float],
    colors_grid: str | Sequence[Sequence[str]] = "stevens_pinkblue",
    x_label: str = "Variable X",
    y_label: str = "Variable Y",
    *,
    x_ticks: tuple[str, str] = ("Low", "High"),
    y_ticks: tuple[str, str] = ("Low", "High"),
    fontsize: float | None = None,
    arrow_color: str = "#333333",
    title: str | None = None,
    zorder: int = 12,
) -> Axes:
    """绘制 3×3 或 5×5 双变量二维色彩矩阵图例，带正交箭头与边界标签。"""
    matrix = get_bivariate_palette(colors_grid) if isinstance(colors_grid, str) else [list(r) for r in colors_grid]
    n_rows = len(matrix)
    n_cols = len(matrix[0]) if n_rows else 0
    if n_rows < 2 or n_cols != n_rows:
        raise ValueError("colors_grid 必须为方阵（至少 2×2）。")

    label_pt = _resolve_pt(fontsize, "xtick.labelsize", 10.0)
    title_pt = _snap_even(label_pt + 2.0, 12)
    rgb = np.array([[mcolors.to_rgb(c) for c in row] for row in matrix], dtype=float)
    leg_ax = add_locator_inset(
        fig_or_ax, bounds, shape="rect", facecolor="none", frame_lw=0.0, zorder=zorder,
    )
    leg_ax.set_gid("bivariate_legend")
    leg_ax.imshow(
        rgb,
        origin="lower",
        extent=(0, n_cols, 0, n_rows),
        aspect="equal",
        interpolation="nearest",
        zorder=1,
    )
    for k in range(n_cols + 1):
        leg_ax.plot([k, k], [0, n_rows], color="#ffffff", linewidth=0.55, zorder=2)
        leg_ax.plot([0, n_cols], [k, k], color="#ffffff", linewidth=0.55, zorder=2)
    leg_ax.set_xlim(-0.55, n_cols + 0.15)
    leg_ax.set_ylim(-0.55, n_rows + 0.15)

    arrow_kw = dict(arrowstyle="-|>,head_width=0.18,head_length=0.28", color=arrow_color, lw=0.85)
    leg_ax.annotate("", xy=(n_cols + 0.05, -0.16), xytext=(0.0, -0.16), arrowprops=arrow_kw, clip_on=False)
    leg_ax.annotate("", xy=(-0.16, n_rows + 0.05), xytext=(-0.16, 0.0), arrowprops=arrow_kw, clip_on=False)

    leg_ax.text(-0.10, -0.34, x_ticks[0], fontsize=label_pt, color=arrow_color, ha="left", va="top", clip_on=False)
    leg_ax.text(n_cols + 0.10, -0.34, x_ticks[1], fontsize=label_pt, color=arrow_color, ha="right", va="top", clip_on=False)
    leg_ax.text(n_cols * 0.5, -1.05, x_label, fontsize=label_pt, fontweight="bold", color=arrow_color, ha="center", va="top", clip_on=False)

    leg_ax.text(-0.34, -0.10, y_ticks[0], fontsize=label_pt, color=arrow_color, ha="right", va="bottom", rotation=90, clip_on=False)
    leg_ax.text(-0.34, n_rows + 0.10, y_ticks[1], fontsize=label_pt, color=arrow_color, ha="right", va="top", rotation=90, clip_on=False)
    leg_ax.text(-1.05, n_rows * 0.5, y_label, fontsize=label_pt, fontweight="bold", color=arrow_color, ha="right", va="center", rotation=90, clip_on=False)

    if title:
        leg_ax.set_title(title, fontsize=title_pt, fontweight="bold", pad=4, color=arrow_color)
    return leg_ax


def add_clean_legend(
    ax: Axes,
    items: Sequence[Any],
    *,
    title: str | None = None,
    loc: str = "lower left",
    ncol: int = 1,
    frameon: bool = False,
    frame_alpha: float = 0.84,
    show_pct: bool = False,
    nodata_label: str | None = None,
    nodata_color: str = GEO_COLORS["nodata_gray"],
    nodata_hatch: str = "///",
    zero_label: str | None = None,
    zero_color: str = GEO_COLORS["zero_neutral"],
    fontsize: float | None = None,
    title_fontsize: float | None = None,
    bbox_to_anchor: Any = None,
    title_align: str = "center",
    frame_facecolor: str = "#faf9f7",
    frame_edgecolor: str = "#b8b4ac",
    frame_lw: float = 0.7,
    borderpad: float = 0.55,
    labelspacing: float = 0.45,
):
    """构建无遮挡紧凑图例，可选附加单一数值或百分比、独立 0 / NoData 色块及居中加粗标题边框。"""
    align_norm = title_align.strip().lower()
    if align_norm not in {"left", "center", "right"}:
        raise ValueError(f"不支持的 title_align '{title_align}'；可选 'left'、'center' 或 'right'。")
    item_pt = _resolve_pt(fontsize, "legend.fontsize", 10.0)
    hdr_pt = _resolve_pt(title_fontsize, "legend.title_fontsize", _snap_even(item_pt + 2.0, 12))
    parsed_items: list[dict[str, Any]] = []
    numeric_vals: list[float] = []
    for raw in items:
        if isinstance(raw, dict):
            val = raw.get("pct")
            item = {
                "label": str(raw["label"]),
                "color": raw["color"],
                "kind": str(raw.get("kind", "patch")).lower(),
                "pct": val,
                "edgecolor": raw.get("edgecolor", "#666666" if str(raw.get("kind", "patch")).lower() == "patch" else raw["color"]),
                "lw": float(raw.get("linewidth", 0.5 if str(raw.get("kind", "patch")).lower() == "patch" else 1.5)),
                "hatch": raw.get("hatch"),
                "marker": raw.get("marker", "o"),
                "alpha": float(raw.get("alpha", 1.0)),
            }
        elif isinstance(raw, (tuple, list)) and len(raw) >= 2:
            val = raw[2] if len(raw) >= 3 else None
            item = {
                "label": str(raw[0]),
                "color": raw[1],
                "kind": "patch",
                "pct": val,
                "edgecolor": "#666666",
                "lw": 0.5,
                "hatch": None,
                "marker": "o",
                "alpha": 1.0,
            }
        else:
            raise ValueError("items 元素需为 dict 或 (label, color[, pct]) 元组。")
        if val is not None:
            numeric_vals.append(float(val))
        parsed_items.append(item)

    total_numeric = sum(v for v in numeric_vals if v > 0.0)
    looks_like_counts = bool(numeric_vals) and (max(numeric_vals) > 100.0 or total_numeric > 105.0)

    handles: list[Any] = []
    for item in parsed_items:
        label = item["label"]
        pct = item["pct"]
        if show_pct and pct is not None:
            pct_val = (100.0 * float(pct) / total_numeric) if (looks_like_counts and total_numeric > 0.0) else float(pct)
            label = f"{label} ({pct_val:.1f}%)"

        kind, color, edgecolor, lw, hatch, marker, alpha = (
            item["kind"], item["color"], item["edgecolor"], item["lw"], item["hatch"], item["marker"], item["alpha"]
        )
        if kind == "line":
            handles.append(Line2D([0], [0], color=color, linewidth=lw, label=label, alpha=alpha))
        elif kind == "marker":
            handles.append(
                Line2D([0], [0], color="none", marker=marker, markerfacecolor=color,
                       markeredgecolor=edgecolor, markeredgewidth=lw, markersize=6, label=label, alpha=alpha)
            )
        else:
            handles.append(
                Patch(facecolor=color, edgecolor=edgecolor, linewidth=lw, hatch=hatch, label=label, alpha=alpha)
            )

    if zero_label:
        handles.append(Patch(facecolor=zero_color, edgecolor="#999999", linewidth=0.5, label=zero_label))
    if nodata_label:
        handles.append(Patch(facecolor=nodata_color, edgecolor="#888888", linewidth=0.5, hatch=nodata_hatch, label=nodata_label))

    legend = ax.legend(
        handles=handles,
        title=title,
        loc=loc,
        ncol=ncol,
        frameon=frameon,
        fontsize=item_pt,
        title_fontsize=hdr_pt,
        bbox_to_anchor=bbox_to_anchor,
        handlelength=1.4,
        handleheight=0.95,
        borderpad=borderpad,
        labelspacing=labelspacing,
        columnspacing=1.0,
    )
    if frameon and legend is not None:
        frame = legend.get_frame()
        frame.set_facecolor(frame_facecolor)
        frame.set_alpha(frame_alpha)
        frame.set_edgecolor(frame_edgecolor)
        frame.set_linewidth(frame_lw)
    if legend is not None:
        legend.set_gid("legend")
        if hasattr(legend, "set_alignment"):
            legend.set_alignment(align_norm)
        if hasattr(legend, "_legend_box") and legend._legend_box is not None:
            legend._legend_box.align = align_norm
        if legend.get_title() is not None:
            legend.get_title().set_fontweight("bold")
    return legend


def add_leader_callouts(
    ax: Axes,
    items: Sequence[Any],
    *,
    use_adjust_text: bool = True,
    fontsize: float | None = None,
    text_color: str = GEO_COLORS["text_primary"],
    line_color: str = "#4a4a4a",
    dot_color: str | None = None,
    halo_width: float = 2.2,
    line_width: float = 0.65,
    dot_size: float = 14.0,
    transform: Any = None,
    zorder: int = 15,
) -> list[Any]:
    """批量绘制 实心锚点 + L 型折线/直线引出线 + 白色光晕标注（支持 adjustText 防碰撞）。"""
    label_pt = _resolve_pt(fontsize, "font.size", 10.0)
    halo = [path_effects.withStroke(linewidth=halo_width, foreground="#ffffff", alpha=0.92)]
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    span_x = abs(float(xlim[1]) - float(xlim[0])) or 1.0
    span_y = abs(float(ylim[1]) - float(ylim[0])) or 1.0

    created: list[Any] = []
    auto_texts: list[Any] = []
    auto_xs: list[float] = []
    auto_ys: list[float] = []

    for idx, raw in enumerate(items):
        if isinstance(raw, dict):
            label = str(raw["label"])
            x, y = float(raw["xy"][0]), float(raw["xy"][1])
            xytext = raw.get("xytext")
            dx, dy = raw.get("dx"), raw.get("dy")
            l_shape = bool(raw.get("l_shape", True))
            ha = raw.get("ha")
            va = raw.get("va")
            t_color = raw.get("color", text_color)
            d_color = raw.get("dot_color", dot_color or line_color)
        elif isinstance(raw, (tuple, list)) and len(raw) >= 3:
            label, x, y = str(raw[0]), float(raw[1]), float(raw[2])
            xytext = (float(raw[3]), float(raw[4])) if len(raw) >= 5 else None
            dx, dy, l_shape, ha, va = None, None, True, None, None
            t_color, d_color = text_color, (dot_color or line_color)
        else:
            raise ValueError("callout item 必须包含 label 与 xy。")

        scatter_kw = dict(
            s=dot_size, color=d_color, edgecolor="#ffffff", linewidth=0.45, zorder=zorder, gid="callouts",
        )
        if transform is not None:
            scatter_kw["transform"] = transform
        dot = ax.scatter([x], [y], **scatter_kw)
        created.append(dot)

        if xytext is None and (dx is not None or dy is not None):
            xytext = (x + float(dx or 0.0), y + float(dy or 0.0))

        if xytext is not None:
            tx, ty = float(xytext[0]), float(xytext[1])
            conn = "angle,angleA=0,angleB=90,rad=2" if l_shape else "arc3,rad=0.0"
            ann_kw = dict(
                xy=(x, y),
                xytext=(tx, ty),
                ha=ha or ("left" if tx >= x else "right"),
                va=va or "center",
                fontsize=label_pt,
                color=t_color,
                zorder=zorder + 1,
                gid="callouts",
                arrowprops=dict(arrowstyle="-", color=line_color, lw=line_width, connectionstyle=conn, shrinkA=0, shrinkB=1.5),
                path_effects=halo,
            )
            if transform is not None:
                ann_kw["xycoords"] = transform
                ann_kw["textcoords"] = transform
            ann = ax.annotate(label, **ann_kw)
            created.append(ann)
        elif use_adjust_text and transform is None:
            txt = ax.text(
                x, y, label,
                fontsize=label_pt, color=t_color, ha="center", va="center",
                zorder=zorder + 1, gid="callouts", path_effects=halo,
            )
            auto_texts.append(txt)
            auto_xs.append(x)
            auto_ys.append(y)
            created.append(txt)
        else:
            # Tier A 或带投影 transform 时的确定性黄金角放射避让
            angle = idx * 2.399963229728653
            r_x = 0.045 * span_x
            r_y = 0.045 * span_y
            tx = x + r_x * math.cos(angle)
            ty = y + r_y * math.sin(angle)
            ann_kw = dict(
                xy=(x, y),
                xytext=(tx, ty),
                ha="left" if tx >= x else "right",
                va="center",
                fontsize=label_pt,
                color=t_color,
                zorder=zorder + 1,
                gid="callouts",
                arrowprops=dict(arrowstyle="-", color=line_color, lw=line_width, shrinkA=0, shrinkB=1.5),
                path_effects=halo,
            )
            if transform is not None:
                ann_kw["xycoords"] = transform
                ann_kw["textcoords"] = transform
            ann = ax.annotate(label, **ann_kw)
            created.append(ann)

    if auto_texts:
        adjusted = False
        try:
            from adjustText import adjust_text

            adjust_text(
                auto_texts,
                x=auto_xs,
                y=auto_ys,
                ax=ax,
                arrowprops=dict(arrowstyle="-", color=line_color, lw=line_width),
                expand=(1.15, 1.25),
            )
            adjusted = True
        except Exception:
            adjusted = False
        if not adjusted:
            for idx, (txt, x, y) in enumerate(zip(auto_texts, auto_xs, auto_ys)):
                angle = idx * 2.399963229728653
                txt.set_position((x + 0.04 * span_x * math.cos(angle), y + 0.04 * span_y * math.sin(angle)))
                ax.annotate(
                    "",
                    xy=(x, y),
                    xytext=txt.get_position(),
                    arrowprops=dict(arrowstyle="-", color=line_color, lw=line_width, shrinkA=0, shrinkB=1.5),
                    zorder=zorder,
                )
    return created


def attach_marginal_profiles(
    fig: Figure,
    main_spec: SubplotSpec | None = None,
    *,
    top: bool = True,
    right: bool = True,
    ratio: float = 0.20,
    pad: float = 0.03,
    main_projection: Any = None,
) -> dict[str, Axes | None]:
    """围绕主地图正上方和/或正右侧创建紧密对齐的边际经纬度剖面/统计面板容器。"""
    if not (0.08 <= ratio <= 0.45):
        raise ValueError("ratio 应在 [0.08, 0.45] 之间。")
    nrows = 2 if top else 1
    ncols = 2 if right else 1
    height_ratios = [ratio, 1.0] if top else [1.0]
    width_ratios = [1.0, ratio] if right else [1.0]

    if main_spec is not None:
        gs = GridSpecFromSubplotSpec(
            nrows, ncols, subplot_spec=main_spec,
            width_ratios=width_ratios, height_ratios=height_ratios,
            wspace=pad, hspace=pad,
        )
    else:
        gs = fig.add_gridspec(
            nrows, ncols,
            width_ratios=width_ratios, height_ratios=height_ratios,
            wspace=pad, hspace=pad,
        )

    main_row = 1 if top else 0
    main_col = 0
    main_kw = {"projection": main_projection} if main_projection is not None else {}
    ax_main = fig.add_subplot(gs[main_row, main_col], **main_kw)

    tick_pt = _resolve_pt(None, "xtick.labelsize", 10.0)
    ax_top: Axes | None = None
    if top:
        top_kw = {"sharex": ax_main} if main_projection is None else {}
        ax_top = fig.add_subplot(gs[0, main_col], **top_kw)
        ax_top.tick_params(axis="x", labelbottom=False, bottom=False)
        ax_top.tick_params(axis="y", labelsize=tick_pt)
        ax_top.spines["top"].set_visible(False)
        ax_top.spines["right"].set_visible(False)

    ax_right: Axes | None = None
    if right:
        right_kw = {"sharey": ax_main} if main_projection is None else {}
        ax_right = fig.add_subplot(gs[main_row, 1], **right_kw)
        ax_right.tick_params(axis="y", labelleft=False, left=False)
        ax_right.tick_params(axis="x", labelsize=tick_pt)
        ax_right.spines["top"].set_visible(False)
        ax_right.spines["right"].set_visible(False)

    return {"main": ax_main, "top": ax_top, "right": ax_right}


def _resolve_cbar_cmap(cmap: Any):
    if cmap is None:
        return get_scientific_cmap("sequential", "nordic_snow")
    if isinstance(cmap, str):
        raw = cmap.strip()
        _check_banned_cmap(raw)
        key = raw[:-2].lower() if raw.endswith("_r") else raw.lower()
        if key in DIVERGING_PALETTES or key in _CRAMERI_DIVERGING_STOPS:
            return get_scientific_cmap("diverging", raw)
        if key in SEQUENTIAL_PALETTES or key in _CRAMERI_NAMES:
            return get_scientific_cmap("sequential", raw)
        if key in QUALITATIVE_PALETTES:
            return get_scientific_cmap("qualitative", raw)
        return matplotlib.colormaps[raw]
    return cmap


def _format_cbar_tick(val: float) -> str:
    if abs(val) < 1e-9:
        return "0"
    aval = abs(val)
    if 100.0 <= aval < 1e6:
        return f"{int(round(val))}"
    if 10.0 <= aval < 100.0:
        return f"{int(round(val))}" if abs(val - round(val)) < 0.05 else f"{val:.1f}"
    if abs(val - round(val)) < 1e-6:
        return f"{int(round(val))}"
    return f"{val:.3g}"


def _auto_cbar_ticks(norm: Any) -> list[float]:
    vmin = float(getattr(norm, "vmin", 0.0) if getattr(norm, "vmin", None) is not None else 0.0)
    vmax = float(getattr(norm, "vmax", 1.0) if getattr(norm, "vmax", None) is not None else 1.0)
    if not (math.isfinite(vmin) and math.isfinite(vmax)) or vmax <= vmin:
        return [vmin]
    fracs = np.array([0.0, 0.25, 0.5, 0.75, 1.0], dtype=float)
    if hasattr(norm, "inverse"):
        try:
            cand = np.asarray(norm.inverse(fracs), dtype=float)
            if cand.shape == fracs.shape and np.all(np.isfinite(cand)):
                return [float(v) for v in cand]
        except Exception:
            pass
    return [float(v) for v in np.linspace(vmin, vmax, 5)]


def add_continuous_colorbar(
    fig_or_ax: Figure | Axes,
    mappable: Any = None,
    *,
    cmap: Any = None,
    norm: Any = None,
    bounds: Sequence[float] | None = None,
    orientation: str = "horizontal",
    label: str | None = None,
    ticks: Sequence[float] | None = None,
    tick_labels: Sequence[str] | None = None,
    zero_label: str | None = None,
    zero_color: str = GEO_COLORS["zero_neutral"],
    nodata_label: str | None = None,
    nodata_color: str = GEO_COLORS["nodata_gray"],
    nodata_hatch: str = "///",
    fontsize: float | None = None,
    title_fontsize: float | None = None,
    frame_lw: float = 0.55,
    zorder: int = 12,
) -> dict[str, Any]:
    """生成高雅的连续渐变色带，支持 PowerNorm/LogNorm/TwoSlopeNorm 及独立的 0 / NoData 色块。"""
    orient = orientation.strip().lower()
    if orient not in {"horizontal", "vertical"}:
        raise ValueError("orientation 仅支持 'horizontal' 或 'vertical'。")

    if mappable is not None:
        if cmap is None:
            cmap = getattr(mappable, "cmap", None)
        if norm is None:
            norm = getattr(mappable, "norm", None)

    resolved_cmap = _resolve_cbar_cmap(cmap)
    if norm is None:
        if mappable is not None and hasattr(mappable, "get_clim"):
            cmin, cmax = mappable.get_clim()
            norm = mcolors.Normalize(vmin=float(cmin), vmax=float(cmax))
        else:
            norm = mcolors.Normalize(vmin=0.0, vmax=1.0)

    if bounds is not None:
        if len(bounds) != 4:
            raise ValueError("bounds 必须为 4 元组 [x0, y0, width, height]。")
        b = [float(v) for v in bounds]
        if isinstance(fig_or_ax, Figure):
            cax = fig_or_ax.add_axes(b, zorder=zorder)
        else:
            cax = fig_or_ax.inset_axes(b, zorder=zorder)
    else:
        if not isinstance(fig_or_ax, Axes):
            raise ValueError("bounds 为 None 时，fig_or_ax 必须为已创建的 Axes。")
        cax = fig_or_ax

    cax.set_xlim(0.0, 1.0)
    cax.set_ylim(0.0, 1.0)
    cax.set_axis_off()
    cax.set_gid("colorbar")

    tick_pt = _resolve_pt(fontsize, "xtick.labelsize", 10.0)
    hdr_pt = _resolve_pt(title_fontsize, "legend.title_fontsize", _snap_even(tick_pt + 2.0, 12))

    used_ticks = [float(v) for v in ticks] if ticks is not None else _auto_cbar_ticks(norm)
    if tick_labels is not None:
        if len(tick_labels) != len(used_ticks):
            raise ValueError("tick_labels 长度必须与 ticks 一致。")
        used_labels = [str(s) for s in tick_labels]
    else:
        if len(used_ticks) >= 3:
            try:
                us = [float(np.clip(norm(v), 0.0, 1.0)) for v in used_ticks]
                kept = [used_ticks[0]]
                kept_u = [us[0]]
                u_end = us[-1]
                for tv, uv in zip(used_ticks[1:-1], us[1:-1]):
                    if abs(uv - kept_u[-1]) >= 0.14 and abs(u_end - uv) >= 0.16:
                        kept.append(tv)
                        kept_u.append(uv)
                kept.append(used_ticks[-1])
                used_ticks = kept
            except Exception:
                pass
        used_labels = [_format_cbar_tick(v) for v in used_ticks]

    swatches: list[tuple[str, str, str | None]] = []
    if zero_label:
        swatches.append((str(zero_label), zero_color, None))
    if nodata_label:
        swatches.append((str(nodata_label), nodata_color, nodata_hatch))

    edge_col = "#6b727a"
    if orient == "horizontal":
        by0, by1 = (0.36, 0.56) if label else (0.42, 0.66)
        sx = 0.02
        sw_w = 0.055
        for s_lbl, s_col, s_hatch in swatches:
            cax.add_patch(Rectangle(
                (sx, by0), sw_w, by1 - by0,
                facecolor=s_col, edgecolor=edge_col, linewidth=frame_lw,
                hatch=s_hatch, zorder=2, gid="colorbar",
            ))
            cax.text(
                sx + 0.5 * sw_w, by0 - 0.11, s_lbl,
                fontsize=tick_pt, color=GEO_COLORS["text_primary"],
                ha="center", va="top", zorder=3, gid="colorbar",
            )
            sx += sw_w + 0.035

        bx0 = (sx + 0.02) if swatches else 0.03
        bx1 = 0.96
        grad = np.linspace(0.0, 1.0, 256)[None, :]
        cax.imshow(
            grad, extent=(bx0, bx1, by0, by1), cmap=resolved_cmap,
            vmin=0.0, vmax=1.0, aspect="auto", interpolation="bilinear",
            zorder=2, gid="colorbar",
        )
        cax.add_patch(Rectangle(
            (bx0, by0), bx1 - bx0, by1 - by0,
            facecolor="none", edgecolor=edge_col, linewidth=frame_lw,
            zorder=3, gid="colorbar",
        ))
        for tv, tlab in zip(used_ticks, used_labels):
            try:
                u = float(np.clip(norm(tv), 0.0, 1.0))
            except Exception:
                continue
            tx = bx0 + u * (bx1 - bx0)
            cax.plot([tx, tx], [by0 - 0.05, by0], color=edge_col, linewidth=frame_lw, zorder=3, gid="colorbar")
            cax.text(
                tx, by0 - 0.11, tlab,
                fontsize=tick_pt, color=GEO_COLORS["text_primary"],
                ha="center", va="top", zorder=3, gid="colorbar",
            )
        if label:
            cax.text(
                0.02 if swatches else bx0, by1 + 0.11, str(label),
                fontsize=hdr_pt, fontweight="bold", color=GEO_COLORS["text_primary"],
                ha="left", va="bottom", zorder=3, gid="colorbar",
            )
    else:
        bx0, bx1 = 0.14, 0.30
        by1 = 0.84 if label else 0.94
        sy = 0.04
        sw_h = 0.065
        for s_lbl, s_col, s_hatch in swatches:
            cax.add_patch(Rectangle(
                (bx0, sy), bx1 - bx0, sw_h,
                facecolor=s_col, edgecolor=edge_col, linewidth=frame_lw,
                hatch=s_hatch, zorder=2, gid="colorbar",
            ))
            cax.text(
                bx1 + 0.08, sy + 0.5 * sw_h, s_lbl,
                fontsize=tick_pt, color=GEO_COLORS["text_primary"],
                ha="left", va="center", zorder=3, gid="colorbar",
            )
            sy += sw_h + 0.035

        by0 = (sy + 0.03) if swatches else 0.06
        grad = np.linspace(0.0, 1.0, 256)[:, None]
        cax.imshow(
            grad, origin="lower", extent=(bx0, bx1, by0, by1), cmap=resolved_cmap,
            vmin=0.0, vmax=1.0, aspect="auto", interpolation="bilinear",
            zorder=2, gid="colorbar",
        )
        cax.add_patch(Rectangle(
            (bx0, by0), bx1 - bx0, by1 - by0,
            facecolor="none", edgecolor=edge_col, linewidth=frame_lw,
            zorder=3, gid="colorbar",
        ))
        for tv, tlab in zip(used_ticks, used_labels):
            try:
                u = float(np.clip(norm(tv), 0.0, 1.0))
            except Exception:
                continue
            ty = by0 + u * (by1 - by0)
            cax.plot([bx1, bx1 + 0.05], [ty, ty], color=edge_col, linewidth=frame_lw, zorder=3, gid="colorbar")
            cax.text(
                bx1 + 0.08, ty, tlab,
                fontsize=tick_pt, color=GEO_COLORS["text_primary"],
                ha="left", va="center", zorder=3, gid="colorbar",
            )
        if label:
            cax.text(
                0.04, by1 + 0.05, str(label),
                fontsize=hdr_pt, fontweight="bold", color=GEO_COLORS["text_primary"],
                ha="left", va="bottom", zorder=3, gid="colorbar",
            )

    return {"ax": cax, "bar_extent": (bx0, bx1, by0, by1), "ticks": used_ticks}


_CORNER_ANCHORS: dict[str, tuple[float, float, int, int]] = {
    "lower right": (0.97, 0.03, -1, 1),
    "lower left": (0.03, 0.03, 1, 1),
    "upper right": (0.97, 0.97, -1, -1),
    "upper left": (0.03, 0.97, 1, -1),
    "lower center": (0.50, 0.03, 0, 1),
    "upper center": (0.50, 0.97, 0, -1),
}


def _corner_window(
    corner: str,
    x_lo: float,
    x_hi: float,
    y_lo: float,
    y_hi: float,
    box_frac: tuple[float, float],
) -> tuple[float, float, float, float]:
    if corner not in _CORNER_ANCHORS:
        raise ValueError(f"不支持的角落 '{corner}'；可选：{sorted(_CORNER_ANCHORS)}")
    fx, fy, dx_dir, dy_dir = _CORNER_ANCHORS[corner]
    bw, bh = float(box_frac[0]), float(box_frac[1])
    if dx_dir > 0:
        u0, u1 = fx, min(1.0, fx + bw)
    elif dx_dir < 0:
        u0, u1 = max(0.0, fx - bw), fx
    else:
        u0, u1 = max(0.0, fx - 0.5 * bw), min(1.0, fx + 0.5 * bw)

    if dy_dir > 0:
        v0, v1 = fy, min(1.0, fy + bh)
    else:
        v0, v1 = max(0.0, fy - bh), fy

    sx, sy = x_hi - x_lo, y_hi - y_lo
    return x_lo + u0 * sx, y_lo + v0 * sy, x_lo + u1 * sx, y_lo + v1 * sy


def _score_vector_occupancy(geoms: Any, wx0: float, wy0: float, wx1: float, wy1: float) -> float:
    from shapely.geometry import box as shp_box

    if hasattr(geoms, "geometry"):
        seq = list(geoms.geometry)
    elif hasattr(geoms, "geom_type"):
        seq = [geoms]
    else:
        seq = list(geoms)
    valid = [g for g in seq if g is not None and not getattr(g, "is_empty", False)]
    if not valid:
        return 0.0
    total_count = len(valid)
    if total_count > 5000:
        step = max(1, total_count // 5000)
        valid = valid[::step][:5000]

    win_box = shp_box(wx0, wy0, wx1, wy1)
    win_area = max(float(win_box.area), 1e-12)
    win_perim = max(2.0 * ((wx1 - wx0) + (wy1 - wy0)), 1e-12)

    area_frac = 0.0
    line_frac = 0.0
    pts_inside = 0
    for g in valid:
        try:
            gx0, gy0, gx1, gy1 = g.bounds
        except Exception:
            continue
        if gx1 < wx0 or gx0 > wx1 or gy1 < wy0 or gy0 > wy1:
            continue
        gtype = getattr(g, "geom_type", "")
        if "Point" in gtype:
            if g.intersects(win_box):
                pts_inside += 1
        elif "Line" in gtype:
            try:
                line_frac += float(g.intersection(win_box).length) / win_perim
            except Exception:
                line_frac += 0.1
        else:
            try:
                area_frac += float(g.intersection(win_box).area) / win_area
            except Exception:
                area_frac += 0.25

    pt_score = min(1.0, pts_inside / max(min(len(valid) * 0.08, 25.0), 1.0)) if pts_inside else 0.0
    return float(min(1.0, max(area_frac + min(line_frac, 1.0), pt_score)))


def compute_ax_ink_mask(
    ax: Axes,
    *,
    ignore_gids: set[str] | None = None,
    pad_px: int = 3,
    tol: float = 12.0,
) -> np.ndarray:
    """Render ax in memory to capture occupied pixels (geometries, labels, and overlapping child/other axes)."""
    fig = ax.figure
    if fig is None or fig.canvas is None:
        return np.zeros((1, 1), dtype=bool)

    hidden: list[Any] = []
    if ignore_gids:
        for obj in ax.get_children():
            gid = getattr(obj, "get_gid", lambda: None)()
            if gid in ignore_gids and obj.get_visible():
                obj.set_visible(False)
                hidden.append(obj)
        for other_ax in fig.axes:
            if other_ax is ax:
                continue
            if other_ax.get_gid() in ignore_gids and other_ax.get_visible():
                other_ax.set_visible(False)
                hidden.append(other_ax)
    try:
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        rgba = np.asarray(fig.canvas.buffer_rgba())
        H, W = rgba.shape[:2]
        bb = ax.get_window_extent(renderer)
        r0 = max(0, H - int(round(bb.y1)) + pad_px)
        r1 = min(H, H - int(round(bb.y0)) - pad_px)
        c0 = max(0, int(round(bb.x0)) + pad_px)
        c1 = min(W, int(round(bb.x1)) - pad_px)
        if r1 <= r0 or c1 <= c0:
            return np.zeros((1, 1), dtype=bool)
        crop = rgba[r0:r1, c0:c1, :3].astype(np.float32)
        bg = np.asarray(mcolors.to_rgb(ax.get_facecolor()), dtype=np.float32) * 255.0
        mask = np.max(np.abs(crop - bg), axis=-1) > tol
        if float(np.mean(mask)) >= 0.85:
            # Full-bleed raster or filled backdrop: switch to local gradient density
            gray = 0.299 * crop[..., 0] + 0.587 * crop[..., 1] + 0.114 * crop[..., 2]
            gx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
            gy = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
            grad = gx + gy
            thr = max(8.0, float(np.percentile(grad, 75)) * 1.15)
            mask = grad > thr
        mh, mw = mask.shape
        def _paint_bbox(obb: Any) -> None:
            if obb is None or getattr(obb, "width", 0.0) <= 0 or getattr(obb, "height", 0.0) <= 0:
                return
            or0 = max(0, (H - int(round(obb.y1))) - r0)
            or1 = min(mh, (H - int(round(obb.y0))) - r0)
            oc0 = max(0, int(round(obb.x0)) - c0)
            oc1 = min(mw, int(round(obb.x1)) - c0)
            if or1 > or0 and oc1 > oc0:
                mask[or0:or1, oc0:oc1] = True

        for other_ax in fig.axes:
            if other_ax is ax or not other_ax.get_visible():
                continue
            if ignore_gids and other_ax.get_gid() in ignore_gids:
                continue
            try:
                _paint_bbox(other_ax.get_window_extent(renderer))
            except Exception:
                continue

        leg = ax.get_legend()
        if leg is not None and leg.get_visible():
            if not (ignore_gids and getattr(leg, "get_gid", lambda: None)() in ignore_gids):
                try:
                    _paint_bbox(leg.get_window_extent(renderer))
                except Exception:
                    pass

        for txt in ax.texts:
            if not txt.get_visible():
                continue
            gid = getattr(txt, "get_gid", lambda: None)()
            if ignore_gids and gid in ignore_gids:
                continue
            try:
                _paint_bbox(txt.get_window_extent(renderer))
            except Exception:
                pass
        return mask
    finally:
        for obj in hidden:
            obj.set_visible(True)


def rank_quiet_corners(
    ax: Axes,
    geoms: Any = None,
    *,
    raster_mask: np.ndarray | None = None,
    raster_extent: Sequence[float] | None = None,
    exclude: Sequence[str] = (),
    candidates: Sequence[str] = ("lower right", "lower left", "upper right", "upper left"),
    box_frac: tuple[float, float] = (0.30, 0.26),
) -> list[tuple[str, float]]:
    """按信息占有率升序评估主图四隅/中栏的空白度，为指北针、比例尺、圆形区位与内嵌图例选址。"""
    excluded = {str(e).strip().lower() for e in exclude}
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    x_lo, x_hi = min(float(xlim[0]), float(xlim[1])), max(float(xlim[0]), float(xlim[1]))
    y_lo, y_hi = min(float(ylim[0]), float(ylim[1])), max(float(ylim[0]), float(ylim[1]))

    r_mask: np.ndarray | None = None
    if raster_mask is not None:
        r_mask = np.asarray(raster_mask, dtype=bool)
        if r_mask.ndim != 2 or r_mask.size == 0:
            r_mask = None

    ink_mask: np.ndarray | None = None
    if r_mask is None and geoms is None:
        ink_mask = compute_ax_ink_mask(ax)

    # Hard collision bboxes in axes fraction [u0, v0, u1, v1] for legend, child axes, badges, and texts
    obstacle_boxes: list[tuple[float, float, float, float]] = []
    fig = ax.figure
    if fig is not None and fig.canvas is not None:
        try:
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            ax_bb = ax.get_window_extent(renderer)
            aw = max(float(ax_bb.width), 1.0)
            ah = max(float(ax_bb.height), 1.0)

            def _to_axes_box(obb: Any) -> tuple[float, float, float, float] | None:
                if obb is None or obb.width <= 0 or obb.height <= 0:
                    return None
                u0 = (obb.x0 - ax_bb.x0) / aw
                u1 = (obb.x1 - ax_bb.x0) / aw
                v0 = (obb.y0 - ax_bb.y0) / ah
                v1 = (obb.y1 - ax_bb.y0) / ah
                if u1 <= 0.0 or u0 >= 1.0 or v1 <= 0.0 or v0 >= 1.0:
                    return None
                return (max(0.0, u0), max(0.0, v0), min(1.0, u1), min(1.0, v1))

            leg = ax.get_legend()
            if leg is not None and leg.get_visible():
                bx = _to_axes_box(leg.get_window_extent(renderer))
                if bx is not None:
                    obstacle_boxes.append(bx)
            for other_ax in fig.axes:
                if other_ax is ax or not other_ax.get_visible():
                    continue
                bx = _to_axes_box(other_ax.get_window_extent(renderer))
                if bx is not None:
                    obstacle_boxes.append(bx)
            for txt in ax.texts:
                if not txt.get_visible():
                    continue
                gid = getattr(txt, "get_gid", lambda: None)()
                if gid in {"scalebar", "north_arrow", "graticule_labels", "graticule_ticks"}:
                    continue
                bx = _to_axes_box(txt.get_window_extent(renderer))
                if bx is not None:
                    obstacle_boxes.append(bx)
        except Exception:
            pass

    ranked: list[tuple[str, float]] = []
    span_x = max(x_hi - x_lo, 1e-12)
    span_y = max(y_hi - y_lo, 1e-12)
    for raw_corner in candidates:
        corner = str(raw_corner).strip().lower()
        if corner in excluded:
            continue
        wx0, wy0, wx1, wy1 = _corner_window(corner, x_lo, x_hi, y_lo, y_hi, box_frac)
        cu0, cv0, cu1, cv1 = (wx0 - x_lo) / span_x, (wy0 - y_lo) / span_y, (wx1 - x_lo) / span_x, (wy1 - y_lo) / span_y
        scores: list[float] = []

        if r_mask is not None:
            rx0, rx1, ry0, ry1 = (
                [float(v) for v in raster_extent]
                if raster_extent is not None
                else [x_lo, x_hi, y_lo, y_hi]
            )
            nrows, ncols = r_mask.shape
            rspan_x = max(rx1 - rx0, 1e-12)
            rspan_y = max(ry1 - ry0, 1e-12)
            c0 = int(np.clip(math.floor((wx0 - rx0) / rspan_x * ncols), 0, ncols))
            c1 = int(np.clip(math.ceil((wx1 - rx0) / rspan_x * ncols), 0, ncols))
            # imshow 默认 origin="upper"：行 0 对应 y=ry1（顶边）
            r0 = int(np.clip(math.floor((ry1 - wy1) / rspan_y * nrows), 0, nrows))
            r1 = int(np.clip(math.ceil((ry1 - wy0) / rspan_y * nrows), 0, nrows))
            if r1 > r0 and c1 > c0:
                scores.append(float(np.mean(r_mask[r0:r1, c0:c1])))
            else:
                scores.append(0.0)

        if geoms is not None:
            scores.append(_score_vector_occupancy(geoms, wx0, wy0, wx1, wy1))

        if not scores and ink_mask is not None:
            mh, mw = ink_mask.shape
            u0, u1 = (wx0 - x_lo) / span_x, (wx1 - x_lo) / span_x
            v0, v1 = (wy0 - y_lo) / span_y, (wy1 - y_lo) / span_y
            ic0 = int(np.clip(math.floor(u0 * mw), 0, mw))
            ic1 = int(np.clip(math.ceil(u1 * mw), 0, mw))
            ir0 = int(np.clip(math.floor((1.0 - v1) * mh), 0, mh))
            ir1 = int(np.clip(math.ceil((1.0 - v0) * mh), 0, mh))
            if ir1 > ir0 and ic1 > ic0:
                scores.append(float(np.mean(ink_mask[ir0:ir1, ic0:ic1])))
            else:
                scores.append(0.0)

        base_score = float(max(scores)) if scores else 0.0
        for bu0, bv0, bu1, bv1 in obstacle_boxes:
            if not (cu1 <= bu0 or cu0 >= bu1 or cv1 <= bv0 or cv0 >= bv1):
                base_score += 10.0
        ranked.append((corner, round(base_score, 6)))

    ranked.sort(key=lambda item: item[1])
    return ranked


def find_quiet_corner(
    ax: Axes,
    geoms: Any = None,
    *,
    raster_mask: np.ndarray | None = None,
    raster_extent: Sequence[float] | None = None,
    exclude: Sequence[str] = (),
    candidates: Sequence[str] = ("lower right", "lower left", "upper right", "upper left"),
    box_frac: tuple[float, float] = (0.30, 0.26),
) -> str:
    """返回信息占有率最低的最安静主图角落名（用于指北针、比例尺、圆形区位或图例放置）。"""
    ranked = rank_quiet_corners(
        ax,
        geoms,
        raster_mask=raster_mask,
        raster_extent=raster_extent,
        exclude=exclude,
        candidates=candidates,
        box_frac=box_frac,
    )
    if not ranked:
        raise ValueError("所有候选角落均被排除，无法选出空白位置。")
    return ranked[0][0]
