# Plotting Recipes & Primitives Quick Reference

Call `configure_plotting()` BEFORE `apply_publication_theme()` and BEFORE importing `pyplot`. Put checkout on `PYTHONPATH` if outside `run_python_script`.

## High-Level Skeleton Recipes (`gis_agent.integrations.plotting`)

```python
from gis_agent.integrations.plotting import (
    CHINA_ALBERS_PROJ, GEO_COLORS, MapPanel, configure_plotting, export_figure,
    create_study_area_layout, create_composite_layout, create_thematic_layout,
    finalize_map_panel, label_context_polygons, load_china_standard_basemap,
    plot_china_standard_map, add_clean_legend, add_continuous_colorbar,
    add_scalebar_and_north, add_graticule_frame, add_locator_inset,
    add_leader_callouts, get_scientific_cmap, build_perceptual_norm,
    add_flow_arcs, add_size_legend, add_smooth_contours,
)
```

1. **Study Area**: `lay = create_study_area_layout(mode="3panel_left", fig_width=8.8)` -> `StudyAreaLayout(fig, ax_macro, ax_region, ax_main, theme, panel_axes, mode)` (`3panel_left|3panel_top|2panel_side`).
2. **Map + Stats Composite**: `lay = create_composite_layout(mode="map_left_stats_right", n_stats=2, fig_width=11.5)` -> `CompositeLayout(fig, ax_map, ax_cbar, ax_legend, stat_axes, theme, panel_axes, mode)` (`map_left_stats_right|map_top_stats_bottom`). Separates `ax_cbar`/`ax_legend` and prevents stacked `stat_axes` xlabel/title collisions.
3. **Thematic Multi-Panel**: `lay = create_thematic_layout(n_panels=1, fig_width=8.8, legend_pos="bottom")` -> `ThematicLayout(fig, axes, ax_legend, theme, panel_axes)`.
4. **Panel Finalizer & Context Labels**:
   - `finalize_map_panel(ax, crs=crs, graticule=True, scalebar=True, north=True, loc="auto", north_loc="auto", north_style="compass_star", scale_style="cartographic", crs_units="metre", dms=True)` — call **after** legends/colorbars!
   - `label_context_polygons(ax, gdf, name_col, *, exclude_geom=None, fontsize=None, max_labels=8)` — places clipped italic neighbor names safely outside `exclude_geom`.

## Core Primitives & Exact Signatures (`gis_agent.integrations.plotting`)

- `configure_plotting(font_files=None, *, font_style="serif", svg_editable_text=True)` (`serif|kaiti|fangsong|sans`)
- `export_figure(fig, output_dir, *, formats=("png",), dpi=300, inputs=(), map_panels=())`
- `apply_publication_theme(style="light_geo", font_scale=1.0, *, fig_width=None)` -> `{"fonts":{"T1":16,"T2":14,"T3":12,"T4":10},"colors":...}`
- `load_china_standard_basemap(crs=CHINA_ALBERS_PROJ)` -> `{"provinces","ten_dash_line","national_boundary"}`; `provinces` cols `["adcode","name","short_name","geometry"]`.
- `plot_china_standard_map(ax, *, data_gdf=None, column=None, cmap=None, norm=None, add_scs_inset=True, inset_bounds=(0.78,0.02,0.20,0.28), crs=CHINA_ALBERS_PROJ, scs_label=None, approval_note=None)`
- `get_scientific_cmap(kind="sequential", name=None, *, n=None, reverse=False, nodata_color=None, zero_anchored=False, zero_color="#f7f7f7")` — pass `nodata_color=None` when overlaying a raster over a vector basemap so `NoData` stays transparent!
- `build_perceptual_norm(values, *, vmin=None, vmax=None, positive_only=True, target_median_pos=0.40)`
- `add_continuous_colorbar(fig_or_ax, mappable=None, *, cmap=None, norm=None, bounds=None, orientation="horizontal", label=None, ticks=None, zero_label=None, nodata_label=None)` — pass `lay.ax_cbar` directly or `ax` with `bounds=[x0,y0,w,h]`.
- `add_clean_legend(ax, items, *, title=None, loc="lower left", ncol=1, frameon=False, frame_alpha=0.84, show_pct=False, nodata_label=None, zero_label=None, title_align="center")` — with `show_pct=True`, 3-tuples `(lbl, hex, count_or_pct)` auto-normalize counts cleanly; omit `show_pct` to display literal counts e.g. `f"{lbl} ({count})"`.
- `add_locator_inset(fig_or_ax, bounds, *, shape="rect"|"circle", projection=None, frame_lw=0.75, facecolor=GEO_COLORS["ocean_soft"])`
- `add_graticule_frame(ax, *, crs=None, style="ticks_only", dms=True, step_deg=None)`
- `add_scalebar_and_north(ax, *, crs_units="metre", loc="auto", scale=True, north=True, north_loc="auto", scale_style="cartographic", north_style="compass_star")`
- `add_leader_callouts(ax, items, *, use_adjust_text=True, fontsize=None, zorder=15)`
- `add_flow_arcs(ax, flows, *, value_col=None, directed=False, symmetric=True, n_classes=4, cmap="carto_oryel", zorder=5.0)` & `add_size_legend(ax, items, *, layout="nested"|"vertical"|"horizontal", title=None, line_items=None, line_title=None, frameon=True)`
- `add_smooth_contours(ax, grid, extent, *, levels=8, smooth_sigma=1.0, colors="#4a4a4a", linewidths=0.7, label=True, fmt="%g") -> {"contours", "levels", "labels"}`
- `attach_marginal_profiles`, `add_zoom_connectors`, `add_orthogonal_bus_connectors`, `add_bivariate_legend`, `bivariate_classify`, `get_palette`, `list_palettes`, `find_quiet_corner`, `rank_quiet_corners`.
