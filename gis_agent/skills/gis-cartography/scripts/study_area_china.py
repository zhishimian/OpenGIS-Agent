"""Short copyable archetype template: 3-panel China study-area locator + DEM hero map.

Uses create_study_area_layout("3panel_left") + plot_china_standard_map + finalize_map_panel.
Replace source paths, layer names, and labels to match the user prompt language.
"""
from __future__ import annotations

import json
from pathlib import Path

from gis_agent.integrations.plotting import (
    CHINA_ALBERS_PROJ,
    GEO_COLORS,
    MapPanel,
    add_clean_legend,
    add_continuous_colorbar,
    configure_plotting,
    create_study_area_layout,
    export_figure,
    finalize_map_panel,
    get_scientific_cmap,
    load_china_standard_basemap,
    plot_china_standard_map,
)


def draw(
    *,
    study_gdf,
    province_short_name: str,
    dem_array,
    dem_extent,
    crs,
    output_dir: str,
    neighbors_gdf=None,
    rivers_gdf=None,
    roads_gdf=None,
    seat_gdf=None,
    labels: dict[str, str] | None = None,
    formats: tuple[str, ...] = ("png", "svg"),
    inputs: tuple[str, ...] = (),
) -> dict:
    configure_plotting(font_style="serif", svg_editable_text=True)
    import matplotlib.pyplot as plt
    from matplotlib import patheffects
    from matplotlib.colors import LightSource, Normalize
    import numpy as np

    lbl = {
        "province": "Host Province",
        "study": "Study Area",
        "neighbor": "Neighboring Regions",
        "river": "Rivers",
        "road": "Main Roads",
        "seat": "County Seat",
        "legend_title": "Legend",
        "elev": "Elevation (m)",
    } | (labels or {})

    basemap = load_china_standard_basemap(crs=CHINA_ALBERS_PROJ)
    provinces = basemap["provinces"]
    host_prov = provinces[provinces["short_name"] == province_short_name]
    study_albers = study_gdf.to_crs(CHINA_ALBERS_PROJ)

    lay = create_study_area_layout(mode="3panel_left", fig_width=8.8)
    try:
        # (a) Compliant China Albers basemap + South China Sea inset (scs_label=None)
        plot_china_standard_map(lay.ax_macro, scs_label=None)
        if not host_prov.empty:
            host_prov.plot(ax=lay.ax_macro, facecolor="#fae1dd", edgecolor="#b5655e", linewidth=0.6, zorder=4)
        study_albers.plot(
            ax=lay.ax_macro, facecolor="#f4a59a", edgecolor=GEO_COLORS["highlight_accent"], linewidth=0.9, zorder=8
        )
        finalize_map_panel(lay.ax_macro, crs=CHINA_ALBERS_PROJ, north=False, loc="auto")

        # (b) Regional context: muted neighbors + highlighted host province + unified study polygon
        prov_proj = provinces.to_crs(crs)
        host_proj = prov_proj[prov_proj["short_name"] == province_short_name]
        prov_proj.plot(ax=lay.ax_region, facecolor="#efeeea", edgecolor="#c4c0b8", linewidth=0.5, zorder=1)
        if not host_proj.empty:
            host_proj.plot(ax=lay.ax_region, facecolor="#faf8f4", edgecolor="#555555", linewidth=0.9, zorder=3)
            hb = host_proj.total_bounds
            lay.ax_region.set_xlim(hb[0] - (hb[2] - hb[0]) * 0.25, hb[2] + (hb[2] - hb[0]) * 0.25)
            lay.ax_region.set_ylim(hb[1] - (hb[3] - hb[1]) * 0.18, hb[3] + (hb[3] - hb[1]) * 0.18)
        study_proj = study_gdf.to_crs(crs)
        study_proj.plot(
            ax=lay.ax_region, facecolor="#f4a59a", edgecolor=GEO_COLORS["highlight_accent"], linewidth=1.0, zorder=8
        )
        lay.ax_region.set_aspect("equal", adjustable="datalim")
        finalize_map_panel(lay.ax_region, crs=crs, north=False, loc="auto")

        # (c) Hero main map: masked transparent hillshade + true [vmin, vmax] DEM + neighbor backdrop
        if neighbors_gdf is not None and not neighbors_gdf.empty:
            neighbors_gdf.to_crs(crs).plot(
                ax=lay.ax_main, facecolor="#efeeea", edgecolor="#c4c0b8", linewidth=0.6, zorder=1
            )
        else:
            lay.ax_main.set_facecolor("#efeeea")

        mask = np.ma.getmaskarray(dem_array)
        valid = dem_array.compressed() if np.ma.isMaskedArray(dem_array) else dem_array[np.isfinite(dem_array)]
        vmin, vmax = float(valid.min()), float(valid.max())
        norm = Normalize(vmin=vmin, vmax=vmax)
        cmap = get_scientific_cmap("sequential", "pub_dem_terrain", nodata_color=None)

        shade = LightSource(azdeg=315, altdeg=45).hillshade(
            dem_array.filled(vmin) if np.ma.isMaskedArray(dem_array) else dem_array, vert_exag=1.5
        )
        shade_masked = np.ma.masked_where(mask, shade)
        gray_cmap = plt.get_cmap("gray").copy()
        gray_cmap.set_bad(alpha=0.0)
        lay.ax_main.imshow(shade_masked, extent=dem_extent, origin="upper", cmap=gray_cmap, alpha=0.35, zorder=2, rasterized=True)
        mappable = lay.ax_main.imshow(
            np.ma.masked_where(mask, dem_array), extent=dem_extent, origin="upper",
            cmap=cmap, norm=norm, alpha=0.85, zorder=3, rasterized=True,
        )
        if rivers_gdf is not None and not rivers_gdf.empty:
            rivers_gdf.to_crs(crs).plot(ax=lay.ax_main, color=GEO_COLORS["water_accent"], linewidth=0.8, zorder=4)
        if roads_gdf is not None and not roads_gdf.empty:
            roads_gdf.to_crs(crs).plot(ax=lay.ax_main, color="#5f5f5f", linewidth=0.75, zorder=5)
        if seat_gdf is not None and not seat_gdf.empty:
            sp = seat_gdf.to_crs(crs)
            sp.plot(ax=lay.ax_main, color=GEO_COLORS["highlight_accent"], edgecolor="#ffffff", markersize=55, zorder=9)
        study_proj.boundary.plot(ax=lay.ax_main, color=GEO_COLORS["highlight_accent"], linewidth=1.3, zorder=8)

        b = study_proj.total_bounds
        pad_x, pad_y = (b[2] - b[0]) * 0.28, (b[3] - b[1]) * 0.24
        lay.ax_main.set_xlim(b[0] - pad_x, b[2] + pad_x)
        lay.ax_main.set_ylim(b[1] - pad_y, b[3] + pad_y)
        lay.ax_main.set_aspect("equal", adjustable="datalim")

        # Draw legend + colorbar BEFORE finalize_map_panel so loc="auto" sees and avoids them!
        leg_items = [{"label": lbl["study"], "color": GEO_COLORS["highlight_accent"], "kind": "line"}]
        if seat_gdf is not None and not seat_gdf.empty:
            leg_items.append({"label": lbl["seat"], "color": GEO_COLORS["highlight_accent"], "kind": "marker"})
        if rivers_gdf is not None and not rivers_gdf.empty:
            leg_items.append({"label": lbl["river"], "color": GEO_COLORS["water_accent"], "kind": "patch"})
        if roads_gdf is not None and not roads_gdf.empty:
            leg_items.append({"label": lbl["road"], "color": "#5f5f5f", "kind": "line"})
        add_clean_legend(lay.ax_main, leg_items, title=lbl["legend_title"], loc="lower left", frameon=True)
        add_continuous_colorbar(
            lay.ax_main, mappable, bounds=[0.54, 0.04, 0.40, 0.13], label=lbl["elev"], zero_label=None
        )
        finalize_map_panel(lay.ax_main, crs=crs, loc="auto", north=True, north_loc="auto")

        panels = (
            MapPanel("macro", lay.ax_macro, CHINA_ALBERS_PROJ),
            MapPanel("region", lay.ax_region, str(crs)),
            MapPanel("main", lay.ax_main, str(crs)),
        )
        return export_figure(lay.fig, output_dir, formats=formats, inputs=inputs, map_panels=panels)
    finally:
        plt.close(lay.fig)


if __name__ == "__main__":
    print(json.dumps({"template": Path(__file__).name, "requires": "study_gdf + province_short_name + dem_array"}))
