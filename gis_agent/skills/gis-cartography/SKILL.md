---
name: gis-cartography
description: Design and revise publication-grade thematic maps, study-area locator maps, and multi-panel figures with Matplotlib layout skeletons and composable cartographic primitives. Uses progressive archetype loading and fast convergence.
compatibility: Requires the checkout's plotting helpers plus Matplotlib, GeoPandas and Rasterio in GIS Python (optional Cartopy, cmcrameri, matplotlib-scalebar, adjustText enhance Tier B). Other hosts must expose the checkout on PYTHONPATH.
---

# Thematic Cartography (Progressive Router)

Reuse verified analytical layers, fields, units, and CRS directly; never fabricate unverified geometry or re-stage already prepared datasets. Match figure text language cleanly to the user prompt (never mix Chinese and English headers).

## 1. Five Non-Negotiable Floors
1. **China Basemap Compliance**: At national or cross-border scale, NEVER use Natural Earth, GADM, or Cartopy `BORDERS` for China; ALWAYS call `plot_china_standard_map` / `load_china_standard_basemap` (`CHINA_ALBERS_PROJ`, ten-dash line, `south_china_sea_inset`, `scs_label=None`) or user-supplied official boundaries (`china_standard_map_warning == False`).
2. **Typography & Bundled Fonts**: Call `configure_plotting(font_style="serif")` (or `"kaiti"`/`"sans"`) BEFORE importing `pyplot`, and `apply_publication_theme(..., fig_width=...)` so fonts stay `<= 4` even-integer sizes (`10 / 12 / 14 / 16 pt`, hard floor `>= 10 pt`). Never add stacked subtitles or `Sources:` footers.
3. **Zero Collisions & Honest Neighbor Context**: Always paint neighboring states/provinces/oceans (`#efeeea` fill, `#c4c0b8` borders — never float the study zone on blank white). Use `finalize_map_panel` / `add_scalebar_and_north(..., loc="auto", north_loc="auto")` for density-aware chrome, derive legend handles directly from plotted layers (`add_clean_legend`), keep primary boundaries at `zorder=8`, and keep ticks/labels inside frames without crowding (`component_crowding_warning == False`, `chrome_overlap_warning == False`).
4. **Honest Color & Scale Encoding**: Pair non-negative continuous fields with `get_scientific_cmap(..., zero_anchored=True)` + `build_perceptual_norm(vals)` + `add_continuous_colorbar(..., zero_label=None)`; render DEM elevation with true `[vmin, vmax]` terrain ramps (`"pub_dem_terrain"` or `"hypsometric"`) over subtle hillshade (never `zero_anchored=True` on elevation). Vectorize plotting (never `itertuples` loops) and set `rasterized=True` on heavy rasters.
5. **Two-Stage Export**: Develop with fast PNG (`formats=("png",)`), fix objective hard defects once, then run one final `formats=("png", "svg")` (`svg.fonttype="none"`).

## 2. Progressive Archetype Routing (Read ONLY What You Need)

Read **ONLY the single booklet + single short script** for your current map type, plus [API quick reference](references/api.md). **Do NOT bulk-read unrelated `references/` files.**

| Task Map Type | Read ONLY These Files | Skeleton / Recipe |
| :--- | :--- | :--- |
| **Study Area / Locator Map** | [study-area.md](references/study-area.md) + [study_area_china.py](scripts/study_area_china.py) | `create_study_area_layout` + `finalize_map_panel` |
| **Choropleth / Bivariate / Categorical** | [thematic-choropleth.md](references/thematic-choropleth.md) + [choropleth.py](scripts/choropleth.py) | `create_thematic_layout` + `finalize_map_panel` |
| **DEM / Continuous Raster / Multi-panel** | [flow-and-raster.md](references/flow-and-raster.md) + [raster_dem.py](scripts/raster_dem.py) | `create_thematic_layout` + `add_continuous_colorbar` |
| **OD Flow / Hub Network** | [flow-and-raster.md](references/flow-and-raster.md) + [flow_od.py](scripts/flow_od.py) | `add_flow_arcs` + `add_size_legend` |
| **API Signatures** | [api.md](references/api.md) (trust signatures directly — do NOT run `inspect.signature` probes or read plotting source unless an unresolved runtime error occurs) | — |
| **Custom Palette Tuning** | Load skill `gis-color-design` on demand | `get_scientific_cmap` / `get_palette` |
| **Visual QA / Troubleshooting** | [review.md](references/review.md) / (on error only) [gotchas.md](references/gotchas.md) | — |

## 3. Convergence & Cost Discipline ("1 Draft + 1-2 Hard-Defect Fixes")

- **Target rhythm**: `1 data inspect -> 1 complete script producing PNG -> 1 full-image read_image QA -> (only if hard defects exist) 1-2 targeted edits -> final PNG+SVG export & finish_task`.
- **Hard bans**:
  - NEVER write scratch probe scripts (`explore_*.py`, `test_cmap*.py`, `probe_*.py`, `read_diag.py`).
  - NEVER call `read_image` more than **3 times total** on a task (never slice/crop the same image 4 times in a row).
  - Stop and deliver once `layout_diagnostics` warnings are clear and no overlap/clipping exists — do NOT burn extra turns chasing subjective tint tweaks (users have editable SVG).

For Studio figures, apply the current task's explicit choices first, then saved cartography preferences (`north_style`, `scale_style`), then defaults above.
