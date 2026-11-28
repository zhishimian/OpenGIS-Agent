"""出版级轻量可组合地理制图原语与科学色彩体系（向后兼容门面模块）。

具体实现已按职责解耦至：
- palettes.py  (科学配色、GEO_COLORS 与归一化)
- theme.py     (微排版主题与 4 档偶数文字阶梯)
- connectors.py(插图容器、外切角聚焦连线与正交总线)
- chrome.py    (经纬网、比例尺/指北针、图例、色带与墨水避让)
- flow.py      (OD 流向弧线与尺寸-线宽组合图例)
- recipes.py   (高频版式骨架与一键收尾函数)
"""
from __future__ import annotations

from gis_agent.integrations.plotting.chrome import (
    add_bivariate_legend,
    add_clean_legend,
    add_continuous_colorbar,
    add_graticule_frame,
    add_leader_callouts,
    add_scalebar_and_north,
    add_smooth_contours,
    attach_marginal_profiles,
    compute_ax_ink_mask,
    find_quiet_corner,
    rank_quiet_corners,
    _format_cbar_tick,
    _resolve_cbar_cmap,
)
from gis_agent.integrations.plotting.connectors import (
    add_locator_inset,
    add_orthogonal_bus_connectors,
    add_zoom_connectors,
)
from gis_agent.integrations.plotting.flow import (
    add_flow_arcs,
    add_size_legend,
)
from gis_agent.integrations.plotting.palettes import (
    BANNED_CMAPS,
    BIVARIATE_PALETTES,
    DIVERGING_PALETTES,
    GEO_COLORS,
    QUALITATIVE_PALETTES,
    SEQUENTIAL_PALETTES,
    bivariate_classify,
    build_bivariate_palette,
    build_perceptual_norm,
    get_bivariate_palette,
    get_palette,
    get_scientific_cmap,
    list_palettes,
)
from gis_agent.integrations.plotting.theme import (
    _resolve_pt,
    _snap_even,
    apply_publication_theme,
)

__all__ = [
    "BANNED_CMAPS",
    "BIVARIATE_PALETTES",
    "DIVERGING_PALETTES",
    "GEO_COLORS",
    "QUALITATIVE_PALETTES",
    "SEQUENTIAL_PALETTES",
    "add_bivariate_legend",
    "add_clean_legend",
    "add_continuous_colorbar",
    "add_flow_arcs",
    "add_graticule_frame",
    "add_leader_callouts",
    "add_locator_inset",
    "add_orthogonal_bus_connectors",
    "add_scalebar_and_north",
    "add_size_legend",
    "add_smooth_contours",
    "add_zoom_connectors",
    "apply_publication_theme",
    "attach_marginal_profiles",
    "bivariate_classify",
    "build_bivariate_palette",
    "build_perceptual_norm",
    "compute_ax_ink_mask",
    "find_quiet_corner",
    "get_bivariate_palette",
    "get_palette",
    "get_scientific_cmap",
    "list_palettes",
    "rank_quiet_corners",
]
