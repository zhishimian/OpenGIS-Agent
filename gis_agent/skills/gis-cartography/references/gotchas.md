# Plotting Gotchas (Consult Only On Runtime Error)

- Never call `pyplot` before `configure_plotting()` + `apply_publication_theme()`; otherwise CJK/Serif font families reset cleanly away.
- Never loop `for row in gdf.itertuples(): gpd.GeoSeries([row.geometry]).plot(...)` — vectorize `.plot()` calls and set `rasterized=True` on heavy rasters (`<= 15 s` render, SVG `<= 8 MB`).
- Always pass `crs=...` to `add_graticule_frame` / `finalize_map_panel` without arbitrary metric `step` tuples (`duplicate_axis_ticks_warning`, `bare_axis_label_warning`).
- Raster `imshow`: `rasterio` bounds are `(left, bottom, right, top)`, whereas Matplotlib `imshow` extent is `(left, right, bottom, top)` — always use `rasterio.plot.plotting_extent(array, transform)` and `WarpedVRT` for rotated/reprojected grids.
- Bilinear resampling mixes categorical integers — use `Resampling.nearest` for LULC/classes and `Resampling.bilinear` for continuous DEMs/fields.
- `AnchoredSizeBar.txt_label` is a `TextArea` (not `Text`): prefer `add_scalebar_and_north` / `finalize_map_panel`. For manual `AnchoredSizeBar`, pass `fontproperties=FontProperties(size=10)` at construction.
- Offline Cartopy (`PROJ_NETWORK=OFF`): never rely on `cartopy.feature` downloads; plot local bundled vectors instead. On `GeoAxes`, never use `sharex`/`sharey` directly (`attach_marginal_profiles(..., main_projection=...)` handles it safely).
- Nonconsecutive filtered GeoDataFrame indices: pass positional lists/arrays of colors aligned to the filtered dataframe rather than raw unreset series when styling discrete classes.
- Register physical `.gpkg`/`.tif` paths in `export_figure(..., inputs=...)`, not `path|layer` pseudo-URIs, and always `plt.close(fig)` inside `finally:`.
