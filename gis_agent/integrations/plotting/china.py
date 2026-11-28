"""Compliant China standard basemap loader and synchronized South China Sea inset renderer."""
from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import geopandas as gpd
from matplotlib.axes import Axes
import numpy as np
from pyproj import Transformer
from shapely.ops import unary_union
from shapely.validation import make_valid

CHINA_ALBERS_PROJ = (
    "+proj=aea +lat_0=0 +lon_0=105 +lat_1=25 +lat_2=47 "
    "+x_0=0 +y_0=0 +ellps=GRS80 +units=m +no_defs"
)

DEFAULT_CHINA_BASEMAP = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "basemaps"
    / "china"
    / "china_standard.gpkg"
)


def _projected_extent(
    lon_min: float, lon_max: float, lat_min: float, lat_max: float, crs: str,
) -> tuple[float, float, float, float]:
    """Compute projected bounding box by sampling boundary edges densely for curved projections."""
    xs = np.concatenate([
        np.linspace(lon_min, lon_max, 40),
        np.full(40, lon_max),
        np.linspace(lon_max, lon_min, 40),
        np.full(40, lon_min),
    ])
    ys = np.concatenate([
        np.full(40, lat_min),
        np.linspace(lat_min, lat_max, 40),
        np.full(40, lat_max),
        np.linspace(lat_max, lat_min, 40),
    ])
    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    px, py = transformer.transform(xs, ys)
    return float(np.min(px)), float(np.max(px)), float(np.min(py)), float(np.max(py))


def load_china_standard_basemap(
    crs: str | None = CHINA_ALBERS_PROJ,
    custom_path: str | Path | None = None,
) -> dict[str, gpd.GeoDataFrame]:
    """Load bundled (or user-overridden) standard China provinces, ten-dash line, and national boundary."""
    env_override = os.environ.get("GIS_AGENT_CHINA_BASEMAP")
    path = Path(custom_path or env_override or DEFAULT_CHINA_BASEMAP).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"中国标准底图文件不存在：{path}")

    if path.suffix.lower() == ".gpkg":
        import pyogrio

        available = {name for name, _ in pyogrio.list_layers(path)}
        if "provinces" in available:
            provinces = gpd.read_file(path, layer="provinces")
        else:
            first_layer = pyogrio.list_layers(path)[0][0]
            provinces = gpd.read_file(path, layer=first_layer)
        ten_dash = (
            gpd.read_file(path, layer="ten_dash_line")
            if "ten_dash_line" in available
            else gpd.GeoDataFrame(geometry=[], crs=provinces.crs)
        )
        if "national_boundary" in available:
            national = gpd.read_file(path, layer="national_boundary")
        else:
            national = gpd.GeoDataFrame(
                [{"adcode": "100000", "name": "中国", "geometry": make_valid(unary_union(provinces.geometry.tolist()))}],
                crs=provinces.crs,
            )
    else:
        provinces = gpd.read_file(path)
        ten_dash = gpd.GeoDataFrame(geometry=[], crs=provinces.crs)
        national = gpd.GeoDataFrame(
            [{"adcode": "100000", "name": "中国", "geometry": make_valid(unary_union(provinces.geometry.tolist()))}],
            crs=provinces.crs,
        )

    layers = {"provinces": provinces, "ten_dash_line": ten_dash, "national_boundary": national}
    if crs:
        for key, gdf in layers.items():
            if not gdf.empty and gdf.crs is not None:
                layers[key] = gdf.to_crs(crs)
            elif gdf.crs is None:
                layers[key] = gdf.set_crs(crs, allow_override=True)
    return layers


def _draw_basemap_and_data(
    target_ax: Axes,
    basemap: dict[str, gpd.GeoDataFrame],
    *,
    data_gdf: gpd.GeoDataFrame | None,
    column: str | None,
    cmap: Any,
    norm: Any,
    base_facecolor: str,
    province_edgecolor: str,
    province_linewidth: float,
    national_edgecolor: str,
    national_linewidth: float,
    dash_color: str,
    dash_linewidth: float,
    missing_color: str,
    draw_ten_dash: bool = True,
) -> None:
    basemap["provinces"].plot(
        ax=target_ax,
        facecolor=base_facecolor,
        edgecolor=province_edgecolor,
        linewidth=province_linewidth,
        zorder=2,
    )
    if data_gdf is not None and column is not None and not data_gdf.empty:
        plot_kwargs: dict[str, Any] = {
            "ax": target_ax,
            "column": column,
            "edgecolor": province_edgecolor,
            "linewidth": province_linewidth,
            "zorder": 2.5,
        }
        if cmap is not None:
            plot_kwargs["cmap"] = cmap
        if norm is not None:
            plot_kwargs["norm"] = norm
        if data_gdf[column].isna().any():
            plot_kwargs["missing_kwds"] = {
                "color": missing_color,
                "hatch": "///",
                "edgecolor": province_edgecolor,
            }
        data_gdf.plot(**plot_kwargs)
    if not basemap["national_boundary"].empty:
        basemap["national_boundary"].boundary.plot(
            ax=target_ax,
            color=national_edgecolor,
            linewidth=national_linewidth,
            zorder=4,
        )
    if draw_ten_dash and not basemap["ten_dash_line"].empty:
        basemap["ten_dash_line"].plot(
            ax=target_ax,
            facecolor=dash_color,
            edgecolor=dash_color,
            linewidth=dash_linewidth,
            zorder=5,
        )
    # Suppress GeoPandas auto-injected "Easting [metre]" / "Northing [metre]" labels
    target_ax.set_xlabel("")
    target_ax.set_ylabel("")


def plot_china_standard_map(
    ax: Axes,
    *,
    data_gdf: gpd.GeoDataFrame | None = None,
    column: str | None = None,
    cmap: Any = None,
    norm: Any = None,
    add_scs_inset: bool = True,
    inset_bounds: tuple[float, float, float, float] = (0.78, 0.02, 0.20, 0.28),
    crs: str = CHINA_ALBERS_PROJ,
    base_facecolor: str = "#f2f1ed",
    province_edgecolor: str = "#8f8b82",
    province_linewidth: float = 0.55,
    national_edgecolor: str = "#2b2b2b",
    national_linewidth: float = 0.9,
    dash_color: str = "#2b2b2b",
    dash_linewidth: float = 1.0,
    missing_color: str = "#e6e4de",
    approval_note: str | None = None,
    render_overlay: Callable[[Axes], None] | None = None,
    custom_path: str | Path | None = None,
) -> dict[str, Any]:
    """Plot a compliant China basemap (Albers equal-area + optional choropleth + South China Sea inset)."""
    basemap = load_china_standard_basemap(crs=crs, custom_path=custom_path)
    projected_data = data_gdf
    if projected_data is not None and not projected_data.empty:
        if projected_data.crs is not None:
            projected_data = projected_data.to_crs(crs)
        else:
            projected_data = projected_data.set_crs(crs)

    _draw_basemap_and_data(
        ax,
        basemap,
        data_gdf=projected_data,
        column=column,
        cmap=cmap,
        norm=norm,
        base_facecolor=base_facecolor,
        province_edgecolor=province_edgecolor,
        province_linewidth=province_linewidth,
        national_edgecolor=national_edgecolor,
        national_linewidth=national_linewidth,
        dash_color=dash_color,
        dash_linewidth=dash_linewidth,
        missing_color=missing_color,
        draw_ten_dash=not add_scs_inset,
    )
    main_lat_min = 17.5 if add_scs_inset else 2.0
    x0, x1, y0, y1 = _projected_extent(72.5, 136.0, main_lat_min, 54.5, crs)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal", adjustable="box")
    if ax.get_gid() is None:
        ax.set_gid("china_standard_map")

    inset_ax: Axes | None = None
    if add_scs_inset:
        inset_ax = ax.inset_axes(list(inset_bounds))
        inset_ax.set_gid("south_china_sea_inset")
        inset_ax.set_facecolor("#ffffff")
        for spine in inset_ax.spines.values():
            spine.set_edgecolor("#333333")
            spine.set_linewidth(0.8)
        inset_ax.set_xticks([])
        inset_ax.set_yticks([])
        _draw_basemap_and_data(
            inset_ax,
            basemap,
            data_gdf=projected_data,
            column=column,
            cmap=cmap,
            norm=norm,
            base_facecolor=base_facecolor,
            province_edgecolor=province_edgecolor,
            province_linewidth=max(0.4, province_linewidth * 0.8),
            national_edgecolor=national_edgecolor,
            national_linewidth=max(0.7, national_linewidth * 0.85),
            dash_color=dash_color,
            dash_linewidth=dash_linewidth,
            missing_color=missing_color,
            draw_ten_dash=True,
        )
        if render_overlay is not None:
            render_overlay(inset_ax)
        ix0, ix1, iy0, iy1 = _projected_extent(105.8, 123.5, 1.8, 25.4, crs)
        inset_ax.set_xlim(ix0, ix1)
        inset_ax.set_ylim(iy0, iy1)
        inset_ax.set_aspect("equal", adjustable="box")
        inset_ax.text(
            0.06,
            0.04,
            "南海诸岛",
            transform=inset_ax.transAxes,
            fontsize=10,
            color="#2b2b2b",
            ha="left",
            va="bottom",
            zorder=10,
        )

    if approval_note:
        ax.text(
            0.015,
            0.015,
            approval_note,
            transform=ax.transAxes,
            fontsize=10,
            color="#555555",
            ha="left",
            va="bottom",
            zorder=10,
        )

    return {"crs": crs, "main_ax": ax, "inset_ax": inset_ax, "basemap": basemap}
