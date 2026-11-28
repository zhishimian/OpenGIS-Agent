"""Short copyable archetype template: OD flow network with sorted curved arcs + combined size/flow card."""
from __future__ import annotations

import json
from pathlib import Path

from gis_agent.integrations.plotting import (
    GEO_COLORS,
    MapPanel,
    add_flow_arcs,
    add_size_legend,
    configure_plotting,
    create_thematic_layout,
    export_figure,
    finalize_map_panel,
)


def draw(
    *,
    study_gdf,
    neighbors_gdf,
    flows,
    hubs_gdf,
    hub_size_col: str,
    flow_col: str,
    output_dir: str,
    crs,
    title: str = "",
    directed: bool = False,
    formats: tuple[str, ...] = ("png", "svg"),
    inputs: tuple[str, ...] = (),
) -> dict:
    configure_plotting(font_style="serif", svg_editable_text=True)
    import matplotlib.pyplot as plt

    lay = create_thematic_layout(n_panels=1, fig_width=8.8, legend_pos="right")
    ax = lay.axes[0]
    try:
        ax.set_facecolor(GEO_COLORS["ocean_soft"])
        if neighbors_gdf is not None and not neighbors_gdf.empty:
            neighbors_gdf.to_crs(crs).plot(ax=ax, facecolor="#efeeea", edgecolor="#c4c0b8", linewidth=0.5, zorder=1)
        study_proj = study_gdf.to_crs(crs)
        study_proj.plot(ax=ax, facecolor="#f7f6f4", edgecolor=GEO_COLORS["border_study"], linewidth=1.0, zorder=2)

        flow_res = add_flow_arcs(ax, flows, value_col=flow_col, directed=directed, symmetric=True, n_classes=4, zorder=5.0)
        hubs_proj = hubs_gdf.to_crs(crs)
        hubs_proj.plot(
            ax=ax, markersize=hubs_proj[hub_size_col], color=GEO_COLORS["marker_high"],
            edgecolor="#ffffff", linewidth=0.8, zorder=7.0,
        )
        study_proj.boundary.plot(ax=ax, color=GEO_COLORS["border_study"], linewidth=1.1, zorder=8.0)

        ax.set_aspect("equal")
        if title:
            ax.set_title(title, fontsize=lay.theme["fonts"]["T1"], fontweight="bold", pad=10)
        finalize_map_panel(ax, crs=crs, loc="auto", north_loc="auto")

        v_max = float(hubs_proj[hub_size_col].max())
        hub_items = [(f"{round(v_max * f):g}", float(v_max * f)) for f in (1.0, 0.5, 0.2)]
        add_size_legend(
            lay.ax_legend,
            hub_items,
            layout="nested",
            title=hub_size_col,
            line_items=flow_res["legend_items"],
            line_title=flow_col,
            frameon=True,
        )
        return export_figure(lay.fig, output_dir, formats=formats, inputs=inputs, map_panels=(MapPanel("main", ax, str(crs)),))
    finally:
        plt.close(lay.fig)


if __name__ == "__main__":
    print(json.dumps({"template": Path(__file__).name, "requires": "study_gdf + flows + hubs_gdf"}))
