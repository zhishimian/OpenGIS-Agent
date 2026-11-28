# Raster Surfaces, DEMs & OD Flow Network Guide

## 1. DEM, Composite Dashboards & Continuous Surfaces (`raster_dem.py`)

- **Map + Statistical Panels**: For asymmetric map + bar/histogram composites, use `create_composite_layout("map_left_stats_right"|"map_top_stats_bottom", n_stats=2)` so `ax_map`, `ax_cbar`, `ax_legend`, and `stat_axes` are locked into collision-free GridSpec slots (zero manual `fig.add_axes` overlap).
- **Transparent `NoData` Over Basemaps**: Whenever overlaying a clipped raster (e.g., CONUS snowfall, county DEM) on top of vector countries/oceans (`zorder=1`), call `get_scientific_cmap(..., nodata_color=None)` so masked/outer `NoData` pixels stay transparent instead of covering neighbor countries in a gray rectangle.
- **Reprojection & Resampling**: Reproject rasters cleanly via `rasterio.vrt.WarpedVRT(..., resampling=Resampling.bilinear)` for continuous fields (`Resampling.nearest` for categorical land cover) and match `imshow(..., extent=plotting_extent(...), origin="upper", rasterized=True)`.
- **Elevation vs. Zero-Anchored Fields**:
  - Elevation / DEM: map true `[vmin, vmax]` onto `"pub_dem_terrain"` or `"hypsometric"` layered softly over `matplotlib.colors.LightSource.hillshade(...)` — never force `zero_anchored=True` on non-zero elevation.
  - Non-negative flux / rainfall / snow starting at `0`: use `get_scientific_cmap(..., zero_anchored=True)` + `build_perceptual_norm(vals)` + `add_continuous_colorbar(..., zero_label=None)`.
- **Multi-Panel Shared Scales**: When comparing panels (`create_thematic_layout(n_panels=...)`), lock identical `cmap` and `norm` across every panel and share one colorbar inside `lay.ax_legend`.
- **Optional Marginal Profiles**: Only when spatial longitude/latitude gradients are explicitly requested, use `attach_marginal_profiles(fig, ratio=0.19, pad=0.03)`.

## 2. OD Flow & Hub Networks (`flow_od.py`)

- **Sorted Curved Arcs + Hub Hierarchy**:
  - Paint calm polygon fills (`#f7f6f4`) + muted context (`#efeeea`/`#e8f1f8`) at `zorder=1-2` and primary border at `zorder=8` (or `zorder=6` below major hubs if hubs sit on borders).
  - Call `add_flow_arcs(ax, flows, value_col=..., directed=False|True, symmetric=True, n_classes=4, cmap="carto_oryel", halo=True, zorder=5.0)` so stronger corridors draw smoothly on top.
  - Scale hub markers (`scatter` `s` in `pt^2`) above arcs (`zorder=7`, `edgecolor="#ffffff"`) and cap labels at top hubs (`add_leader_callouts`).
- **Combined Flow + Size Legend Card**:
  - Pass `line_items=flow_res["legend_items"]` directly into `add_size_legend(ax_leg, hub_items, layout="nested"|"vertical", title=..., line_title=..., frameon=True)` inside `lay.ax_legend` so flow widths and hub sizes share one compact framed card without empty bottom voids.
