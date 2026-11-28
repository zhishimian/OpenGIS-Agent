"""Short copyable archetype template: continuous raster / DEM surface with hillshade & colorbar."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from gis_agent.integrations.plotting import (
    GEO_COLORS,
    MapPanel,
    add_continuous_colorbar,
    build_perceptual_norm,
    configure_plotting,
    create_thematic_layout,
    export_figure,
    finalize_map_panel,
    get_scientific_cmap,
)


def draw(raster_path: str, output_dir: str, *, mode: str = "dem", title: str = "", label: str = "Value",
         formats: tuple[str, ...] = ("png", "svg")) -> dict:
    configure_plotting(font_style="serif", svg_editable_text=True)
    import matplotlib.pyplot as plt
    import numpy as np
    import rasterio
    from matplotlib.colors import LightSource, Normalize
    from rasterio.enums import Resampling
    from rasterio.plot import plotting_extent

    with rasterio.open(raster_path) as src:
        factor = max(src.width, src.height) / 1400
        out_shape = (max(1, round(src.height / max(1, factor))), max(1, round(src.width / max(1, factor))))
        arr = src.read(1, out_shape=out_shape, masked=True, resampling=Resampling.bilinear)
        transform = src.transform * src.transform.scale(src.width / out_shape[1], src.height / out_shape[0])
        crs = src.crs
    extent = plotting_extent(arr, transform)
    vals = arr.compressed()
    if mode == "dem":
        cmap = get_scientific_cmap("sequential", "pub_dem_terrain")
        norm = Normalize(float(vals.min()), float(vals.max()))
    else:
        cmap = get_scientific_cmap("sequential", "nordic_snow", zero_anchored=True)
        norm = build_perceptual_norm(vals)

    lay = create_thematic_layout(n_panels=1, fig_width=8.6, legend_pos="none")
    ax = lay.axes[0]
    try:
        if mode == "dem":
            shade = LightSource(azdeg=315, altdeg=45).hillshade(arr.filled(float(vals.min())), vert_exag=1.5)
            ax.imshow(shade, extent=extent, origin="upper", cmap="gray", alpha=0.35, zorder=1, rasterized=True)
        im = ax.imshow(arr, extent=extent, origin="upper", cmap=cmap, norm=norm, alpha=0.88, zorder=2, rasterized=True)
        ax.set_aspect("equal")
        if title:
            ax.set_title(title, fontsize=lay.theme["fonts"]["T1"], fontweight="bold", pad=10)
        crs_units = "degree" if crs is not None and crs.is_geographic else "metre"
        add_continuous_colorbar(
            ax, im, bounds=[0.54, 0.04, 0.40, 0.13], label=label, zero_label=None,
            nodata_label="NoData" if np.any(arr.mask) else None,
        )
        finalize_map_panel(ax, crs=crs, crs_units=crs_units, loc="auto", north_loc="auto")
        return export_figure(lay.fig, output_dir, formats=formats, inputs=(raster_path,), map_panels=(MapPanel("main", ax, str(crs)),))
    finally:
        plt.close(lay.fig)


if __name__ == "__main__":
    draw(**json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
