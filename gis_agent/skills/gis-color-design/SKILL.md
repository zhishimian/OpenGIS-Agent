---
name: gis-color-design
description: GIS cartography color design guide and curated publication palette library for terrain DEMs, land cover, hydro/climate, diverging anomalies, bivariate maps, and multi-layer figure-ground hierarchy. Routine maps can use built-in defaults without loading this skill; load on demand when custom thematic ramps, high-contrast publication palettes, or multi-layer color tuning are needed.
compatibility: Requires gis_agent.integrations.plotting (palettes, theme) with Matplotlib/NumPy in GIS Python.
---

# GIS Cartographic Color Design

Load this skill **only when** choosing specialized thematic color ramps, resolving multi-layer contrast issues, or styling custom publication palettes. Routine locator/thematic maps work out of the box with `apply_publication_theme` and default ramps.

## Scenario-to-Palette Quick Lookup

| Cartographic Subject | Recommended Call | Visual Notes |
| :--- | :--- | :--- |
| **Elevation / DEM** | `get_scientific_cmap("sequential", "pub_dem_terrain")` or `"hypsometric"` | Always pair with subtle hillshade (`blend_mode` / alpha) and **true `[vmin, vmax]`**; never `zero_anchored=True` on non-zero elevation |
| **Precipitation / Runoff / Snow** | `get_scientific_cmap("sequential", "nordic_snow", zero_anchored=True)` + `build_perceptual_norm(vals)` | Anchors `0` to clean `#f7f7f7` while keeping `NoData` `#d9d9d9` distinct |
| **Moisture / Water / Flood** | `get_scientific_cmap("sequential", "carto_bluyl")` or `"slate_teal"` | Avoid saturated pure cyan; pair lakes with `GEO_COLORS["water_accent"]` (`#7eb6d9`) |
| **Vegetation / NDVI / Greening** | `get_scientific_cmap("sequential", "carto_mint")` or `"sage_forest"` | Keep midtones restrained (`C*` 20-45) so overlaid vector routes stay crisp |
| **Heat / LST / Density / Flow** | `get_scientific_cmap("sequential", "carto_oryel")` or `"lajolla_r"` | Sort high values to top `zorder`; apply white edge halos to markers |
| **Signed Delta / Anomaly** | `get_scientific_cmap("diverging", "vik")` / `"tol_burd"` / `"carto_temps"` | Always pair with `TwoSlopeNorm(vmin, vcenter=0.0, vmax)` |
| **Land Use / Categorical (<= 8)** | `get_palette("pub_lulc", n=k)` or `"okabe_ito"` / `"morandi_geo"` | Merge >8 minor categories into `"Other"` (`#cccccc`) |
| **Study-Area Highlight & Context** | Land `#efeeea`, Border `#c4c0b8`, Study fill `#f4a59a` / edge `GEO_COLORS["highlight_accent"]` (`#d64541`) | Use one unified coral/crimson highlight hue across macro, regional, and main panels |
| **Bivariate (X, Y)** | `get_bivariate_palette("teal_terracotta")` or `"stevens_pinkblue"` | Pair with `bivariate_classify` + `add_bivariate_legend` |

## 60-30-10 Figure-Ground Hierarchy

1. **60% Quiet Context**: Surrounding states/provinces `#efeeea` (`#c4c0b8` borders), soft ocean `#e8f1f8` — never paint pure blank white voids around a study polygon.
2. **30% Thematic Surface**: Low-chroma (`C*` 20-45) continuous ramps (`nordic_snow`, `pub_dem_terrain`, `batlow`, `carto_teal`).
3. **10% Focal Markers & Borders**: White-haloed points (`marker_high` `#d96f32`, `marker_extreme` `#9e2234`) and crisp `zorder=8` study boundary (`#d64541` or `#333333`).

For full stop-hex specifications, custom ramp synthesis, and CVD safety rules, inspect [the curated palette atlas](references/palettes.md).
