# Study-Area & Multi-Scale Locator Map Guide

Distilled from publication benchmarks (Yunnan, Dongting Basin, Tianjin, Taihu study-area figures). Copy [study_area_china.py](../scripts/study_area_china.py) and adapt data layers rather than probing plotting source files or building `GridSpec` from scratch.

## Layout & Composition Rules

1. **Default `"3panel_left"` Hierarchy & Flush Grid Alignment**:
   - Call `create_study_area_layout("3panel_left")` (`(a)` macro top-left, `(b)` region bottom-left, `(c)` main study hero on right occupying ~65% canvas). Use `"3panel_top"` only for wide east-west regions, or `"2panel_side"` for 2-scale locators.
   - Lock panel frames flush with `ax.set_aspect("equal", adjustable="datalim")` (built into `finalize_map_panel`) so `GridSpec` outer borders align cleanly across `(a)`, `(b)`, `(c)` instead of shrinking unevenly.
   - Keep one unified language across all panels, titles, badges, and legends.
2. **Exact Basemap Schema & Neighbor Context**:
   - `load_china_standard_basemap(crs=CHINA_ALBERS_PROJ)` returns `{"provinces", "ten_dash_line", "national_boundary"}`. `provinces` has columns `["adcode", "name", "short_name", "geometry"]` (e.g. filter via `short_name == "..."` or `adcode == "610000"`).
   - Never float a lone province/county on blank white: paint neighbors at `zorder=1` in `#efeeea` with `#c4c0b8` borders, plus soft `#e8f1f8` oceans/lakes.
   - Label quiet surrounding neighbors/provinces via `label_context_polygons(ax, context_gdf, name_col, exclude_geom=study_union)` so names stay strictly inside the viewport and clear of the study-area boundary (`frame_overflow_warning == False`).
   - On China macro panels (`(a)`): call `plot_china_standard_map(ax_macro, scs_label=None)` (`CHINA_ALBERS_PROJ`, ten-dash line, `south_china_sea_inset`, `scs_label=None`).
3. **Unified Cross-Panel Study Highlight & Clean Annotations**:
   - Highlight the study polygon consistently across `(a)`, `(b)`, `(c)` using `#f4a59a` fill and `GEO_COLORS["highlight_accent"]` (`#d64541`) edge (`zorder=8`).
   - For place annotations (county seat, rivers, neighbors), use halo-only `path_effects=[withStroke(linewidth=2.5, foreground="#ffffff")]` or `add_leader_callouts` — NEVER add white `bbox=dict(...)` pills (`callout_box_warning`).
   - Prefer clean highlights over long cross-panel diagonal connectors; reserve `add_zoom_connectors` / `add_orthogonal_bus_connectors` strictly for compact adjacent gaps.
4. **Masked Terrain / DEM + Hillshade (Zero Gray Box Leakage)**:
   - Compute `LightSource(azdeg=315, altdeg=45).hillshade(...)`, mask it strictly with `dem_array.mask` (`np.ma.masked_where(dem_array.mask, shade)`), and use a transparent bad-value colormap (`gray_cmap = plt.get_cmap("gray").copy(); gray_cmap.set_bad(alpha=0.0)`) so NO gray rectangle leaks outside the county boundary!
   - Pair DEM elevation with true `[vmin, vmax]` range and `"pub_dem_terrain"` / `"hypsometric"` (never `zero_anchored=True` on non-zero elevation). Draw rivers (`zorder=4`) and roads (`zorder=5`) beneath the county outline (`zorder=8`).
5. **Human-Natural Chrome & Legend Placement**:
   - Place legends/colorbars either cleanly **outside** the map face (e.g., dedicated `fig.add_axes(...)` legend/colorbar card alongside `(a)`/`(b)` or beneath `(c)`) or inside an genuinely empty lower corner BEFORE calling `finalize_map_panel`.
   - Always put panel titles in `ax.set_title(...)` **outside** the frame (`pad=8`); NEVER stamp a panel title inside the map corner where `(a)/(b)/(c)` badges, scalebars, or north arrows live.
   - Call `finalize_map_panel(lay.ax_main, crs=crs, loc="auto", north=True, north_loc="auto")` LAST (`loc="auto"` keeps scalebars strictly in the lower zone `lower left|right|center`; `north_loc="auto"` keeps north arrows strictly in the upper zone `upper right|left`). Keep a single hero north arrow on `(c)` and `north=False` on `(a)`/`(b)`.
