# Thematic Choropleth, Categorical & Bivariate Map Guide

Use `create_thematic_layout(n_panels=1, legend_pos="bottom"|"right")` and `finalize_map_panel(ax, crs=...)` to keep panels aligned, margins balanced, and legends collision-free.

## Encoding & Classification Rules

1. **Continuous vs. Discrete (`<= 5` classes)**:
   - Continuous rates or fields (`> 5` intervals): pair `get_scientific_cmap("sequential", "nordic_snow", zero_anchored=True)` + `build_perceptual_norm(vals)` + `add_continuous_colorbar(..., zero_label=None)`. Keep exact `0` (`#f7f7f7`) distinct from `NoData` (`#d9d9d9`, hatch `///`).
   - Signed changes / anomalies: `get_scientific_cmap("diverging", "vik")` + `TwoSlopeNorm(vmin, 0.0, vmax)`.
   - Discrete classes (`<= 5` tiers): explicit `BoundaryNorm` or [classify_values.py](../scripts/classify_values.py) (`method="fisher_jenks"`, pinned `jenkspy==0.4.1`). Derive legend handles from the exact plotted palette/intervals — NEVER stack dual count + `%` columns in one legend.
2. **Categorical & Land Cover (`<= 8` classes)**:
   - Use `get_palette("pub_lulc", n=k)` or `"okabe_ito"`; merge rare tails into `"Other"` (`#cccccc`).
3. **Bivariate Choropleth**:
   - Classify `(x, y)` via `bivariate_classify(x, y, bins=3)`, color with `get_bivariate_palette("teal_terracotta")`, and render `add_bivariate_legend` in a quiet corner or dedicated legend slot.
4. **Basemap Context, Hierarchy & Projection**:
   - Paint out-of-scope neighboring units in muted `#efeeea` (`#c4c0b8` borders, `zorder=1`) and water in `#e8f1f8` — never float an isolated province on pure white.
   - Enforce strict `zorder`: context (`0-1`) -> thematic fills (`2`) -> hydro (`3`) -> sub-borders (`4`) -> points/roads (`5-6`, white edge halo) -> primary national/study outline (`8`) -> chrome (`10+`).
   - Dense administrative units (`> 25`): apply a 2-tier label hierarchy (`T3=12 pt` bold hubs, `T4=10 pt` secondary units; use `add_leader_callouts` in congested corridors; never shrink to `8 pt`).
   - Keep `~8.5 in` wide standalone maps clean; omit redundant macro locator insets on iconic continental/national extents (CONUS, China, Global). See [choropleth.py](../scripts/choropleth.py) for an executable JSON-configured reference.
