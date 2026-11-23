---
name: gis-terrain-and-hydrology
description: Distinguish bare-earth DEMs from DSM object heights, separate raw engineering terrain from sink-filled hydrological surfaces, trace D8 flow direction and accumulation, delineate nested catchments vs multi-outlet partitions, calculate connected flood storage, and guard slopes/bilinear checks against NoData cliffs. Use for DEM derivatives, watershed routing, or inundation storage tasks. Skip for basic raster reprojection or spectral bands without hydrology.
compatibility: Requires GeoPython (numpy, rasterio); scipy or QGIS grass/saga algorithms optional.
---

# Terrain derivatives and watershed hydrology

Separate engineering terrain from sink-filled hydrological DEMs, match D8 directional codes to the originating tool, and enforce upstream/flood connectivity semantics cleanly.

## Workflow & Guardrails

1. **Raw vs filled surface isolation**: Never mix bare-earth DEM elevation, DSM canopy/roof elevation, and relative object height (`DSM - DEM`). Restrict sink-filled DEMs (`dem_filled`) strictly to D8 flow direction, accumulation, stream routing, and flood connectivity masks; **ALL** engineering elevations (structure/crest heights, valley profiles, hillslope gradients, and earthwork cut/fill volumes) MUST read the raw unfilled DEM.
2. **Pre-operator domain & NoData masking**: Mask ocean/background constant `0 m` water bodies, raster NoData, and finite-sentinel exclusions (`-9999`) before TPI, sink-filling, slope stencils, or bilinear interpolation; bounds-check raster edges before indexing rather than silently clamping out-of-range coordinates.
3. **D8 directional code standards**: Verify the tool's flow direction convention before tracing downstream:
   - **GRASS `r.watershed`**: `1=NE, 2=N, 3=NW, 4=W, 5=SW, 6=S, 7=SE, 8=E` (negative codes mark spillover leaving bounds).
   - **ESRI / TauDEM**: powers of two `1=E, 2=SE, 4=S, 8=SW, 16=W, 32=NW, 64=N, 128=NE`.
4. **Pour-point snapping & nested catchments**: When `Snap Pour Point` misplaces an isolated noisy outlet, tune snapping radius or stream-threshold tiers locally rather than dropping snapping globally for un-snapped D8 downstream tracing. Single-outlet complete upstream tracing yields overlapping masks (`upper <= lower`); simultaneous multi-seed partitioning stops at intermediate outlets, shrinking downstream basin areas. Account explicitly for self-cell counting and metric cell area (`dx * dy`).
5. **Flood volume connectivity**: Compute reservoir/inundation storage only over flood cells hydraulically connected to the water seed (`connected_inundation_volume`), excluding isolated dry depressions behind ridges.

## References & Runnable Assets

- Complete terrain, NoData, D8, and catchment reference: [terrain hydrology](references/terrain-hydrology.md).
- Nested catchment, masked bilinear, and work/cache counterexamples: [terrain_counterexamples.py](scripts/terrain_counterexamples.py).
- Pure NumPy Kahn D8 flow accumulation, nested catchment check, and connected flood volume: [hydrology_routing.py](scripts/hydrology_routing.py).
