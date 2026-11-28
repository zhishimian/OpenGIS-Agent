# Scientific Cartographic Color Theory & Palette Atlas

Color on a publication map is a precision encoding channel, never arbitrary decoration. Choose palettes from perceptual lightness/chroma geometry rather than banned rainbow ramps (`jet`, `rainbow`, `hsv`, `gist_rainbow`, `nipy_spectral`, `prism`, `flag`).

## Generalizable Color Principles

1. **60-30-10 Luminance & Chroma Budget**:
   - **60% Quiet Canvas & Context**: High lightness (`L*` 90-99), near-zero chroma (`#ffffff`, `#faf8f4`, `#efeeea`, `#e8f1f8`).
   - **30% Core Thematic Surface**: Low-to-moderate chroma (`C*` 20-45) editorial ramps (`pub_dem_terrain`, `nordic_snow`, `slate_teal`, `muted_ochre`, `sage_forest`, `batlow`).
   - **10% High-Salience Focal Accents**: Crisp white-haloed markers (`#e8b44c`, `#d96f32`, `#9e2234`) and unified study-area coral/crimson boundaries (`#d64541` edge, optional soft tint `#f4a59a`).
2. **Perceptual Uniformity, Skewed Normalization & Continuous Colorbars**:
   - Render continuous fields (`> 5` levels) via `add_continuous_colorbar`; reserve discrete swatches for `<= 5` explicit classes.
   - For non-negative right-skewed fields starting at true `0` (rainfall, snow, emissions), pair `get_scientific_cmap("sequential", "nordic_snow", zero_anchored=True)` + `build_perceptual_norm(values)` + `add_continuous_colorbar(..., zero_label=None)`.
   - For DEM elevation, always map true `[vmin, vmax]` onto `pub_dem_terrain` or `hypsometric` over subtle hillshade — NEVER force `zero_anchored=True` on non-zero terrain elevation.
   - For signed deltas/anomalies, pair `diverging` ramps with `TwoSlopeNorm(vmin, 0.0, vmax)`.
   - For unordered categories (`<= 8` classes), merge tiny long tails into `"Other"` (`#cccccc`).
3. **Zero vs. NoData Isolation**: Keep `NoData` (`GEO_COLORS["nodata_gray"]` = `#d9d9d9`, optional `///` hatch) visibly separate from valid `0` (`#f7f7f7`).
4. **CVD & Grayscale Safety**: Avoid pure `#ff0000` vs `#00ff00`; prefer Okabe-Ito, Crameri, Paul Tol, or CARTOColors.
5. **Cross-Panel Color Linkage**: Composite figures MUST lock identical hex colors, `cmap`, `norm`, and study-highlight colors across all panels.

## Curated Palette Atlas (`gis_agent.integrations.plotting.palettes`)

### Basemap & Figure-Ground Tokens (`GEO_COLORS`)

| Token | Hex | Recommended Role |
| :--- | :--- | :--- |
| `land_muted` / `land_warm` | `#f0f0f0` / `#f3f1ec` | Out-of-scope landmass / warm editorial canvas land |
| `land_context` | `#e5e5e5` | Surrounding non-study provinces, states, or context |
| `ocean_soft` / `ocean_clean` | `#e8f1f8` / `#f4f8fb` | Soft pale-blue ocean or locator water |
| `water_accent` | `#7eb6d9` | Major focal rivers, lakes, or coastal channels |
| `border_muted` / `border_subtle` | `#b8b8b8` / `#d0d0d0` | Country/province context borders / hairlines |
| `border_study` | `#333333` | Primary focal outline (`0.9-1.2pt`) |
| `nodata_gray` / `zero_neutral` | `#d9d9d9` / `#f7f7f7` | Missing pixels vs. valid exact zero |
| `text_primary` / `text_secondary` | `#1f2328` / `#57606a` | Soft-ink labels vs. graticule ticks & notes |
| `highlight_accent` / `highlight_gold` | `#d64541` / `#e6ab02` | Unified study-area highlight & inset extent frame |
| `marker_low` / `marker_mid` / `marker_high` / `marker_extreme` | `#e6e6e6` / `#e8b44c` / `#d96f32` / `#9e2234` | Hierarchical white-haloed focal points |

### Sequential Palettes (`get_scientific_cmap("sequential", name)`)

| Name | Stops (low -> high) | Best Domains |
| :--- | :--- | :--- |
| `pub_dem_terrain` | `#6f9860` `#a6c576` `#e6de9c` `#d9af68` `#bc7344` `#8a4d32` `#d9d2cb` | Publication hypsometric DEM relief (pair with subtle hillshade) |
| `hypsometric` | `#d8e6cf` `#e7ecd1` `#f3eac2` `#e4cfa0` `#cca97f` `#b68e74` `#d6cfc7` `#f5f5f5` | Soft muted regional elevation backdrop under overlays |
| `batlow` | `#011959` `#124761` `#2c665d` `#627941` `#a58b2c` `#e69858` `#fdb1ab` `#faccfa` | Default perceptual geophysical/climate field |
| `nordic_snow` | `#cfe1ef` `#a9c8e0` `#7fa6ca` `#5682ad` `#36648f` `#23507a` `#163a5b` `#0c2338` | Low-chroma precipitation, snowfall, water-equivalent fields |
| `lajolla` | `#191900` `#3c2614` `#783932` `#c04d49` `#e17750` `#eaa253` `#f5d369` `#fffecb` | LST, heatwave, wildfire, drought exposure (`_r` light-low) |
| `oslo` | `#010101` `#0f2133` `#194169` `#3364a1` `#6b8ec8` `#97a9c9` `#c7ccd3` `#ffffff` | Bathymetry, snow cover, runoff (`_r` light-low) |
| `lapaz` / `bilbao` / `acton` / `hawaii` / `turku` | Crameri scientific ramps | Shelf/accessibility, aridity/erosion, urban density, biodiversity, geology |
| `carto_teal` / `carto_mint` / `carto_bluyl` / `carto_emrld` | CARTO cool/green ramps | Hydrology, NDVI greening, transit access, canopy height |
| `carto_oryel` / `carto_peach` / `carto_burg` / `carto_brwnyl` / `carto_sunsetdark` | CARTO warm ramps | Solar/wind, heat stress, vulnerability, soil carbon, OD flows |
| `tol_iridescent` / `bathymetry` / `slate_teal` / `muted_ochre` / `sage_forest` | Editorial & Tol ramps | Smooth linear gradients, marine depth, drylands, parkland |

### Diverging Palettes (`get_scientific_cmap("diverging", name)`)

- `vik`, `roma`, `bam`, `broc`, `cork` (Crameri)
- `tol_sunset`, `tol_burd` (Paul Tol)
- `carto_geyser`, `carto_armyrose`, `carto_tealrose`, `carto_earth`, `carto_temps` (CARTO)

### Qualitative & Journal Palettes (`get_palette(name, n=...)`)

- `pub_lulc` (7): `#e6c86b`, `#2e7d32`, `#81c784`, `#4f92c3`, `#d64541`, `#c9b38c`, `#b3d4e5` (Cropland, Forest, Shrub/Grass, Water, Built-up, Barren, Snow/Wetland)
- `landcover_soft` (7): `#4D8C57`, `#A3C585`, `#DFC98A`, `#C77A62`, `#6CA6CD`, `#8B7D7B`, `#D9D9D9`
- `okabe_ito` (8), `tol_muted` (9), `tol_bright` (7), `npg` (10), `lancet` (9), `aaas` (10), `jco` (10), `carto_safe` (11), `carto_prism` (12), `morandi_geo` (8).

### Bivariate Corner Matrices (`get_bivariate_palette(name)`)

- `stevens_pinkblue`, `stevens_bluered`, `stevens_greenblue`, `stevens_purplegold`, `teal_terracotta` (3x3)
- `bivariate_5x5_ocean_amber` (5x5), or build any `n x n` via `build_bivariate_palette(c00, c10, c01, c11, n)`.
