# Visual QA Hard-Defect Checklist & Stopping Rule

Check `layout_diagnostics` in `export_figure` output AND inspect the single full-image `preview.png` via `read_image`.

## Six Objective Hard-Defect Checks

1. **Typography Floor & Font Stack**: `small_text_warning == False` (`min_font_pt >= 10`), `non_even_font_warning == False`, `fragmented_font_tiers_warning == False` (`<= 4` even sizes `10/12/14/16 pt`). Zero missing-glyph warnings; one consistent language matching the prompt.
2. **All Hygiene Flags Clear (`False`)**: Verify zero warnings for `subtitle_detected_warning`, `callout_box_warning`, `duplicate_axis_ticks_warning`, `bare_axis_label_warning`, `china_standard_map_warning`, `chrome_overlap_warning`, `component_crowding_warning`, `clipped_text_warning`, `frame_overflow_warning`, and `excessive_margin_warning`.
3. **No Visual Occlusions**: Scalebars, north arrows, badges, callouts, and framed legends do NOT overlap data polygons, routes, islands, coastlines, subplot titles, or graticule ticks.
4. **Honest Neighbor Context & Z-Order**: Study zone sits on `#efeeea`/`#c4c0b8` surrounding neighbors (`#e8f1f8` ocean/water where applicable) rather than floating on empty white; primary boundaries remain crisp (`zorder=8`) above overlaid lines/points.
5. **China Basemap & Scale Honesty**: National/cross-border China panels include compliant `CHINA_ALBERS_PROJ`, ten-dash line, and `south_china_sea_inset` (`scs_label=None`). Continuous colorbars show crisp plain numbers (no accidental `1.14e+03`).
6. **Connector & Inset Discipline**: Local/provincial locators use clean highlight fills or dashed focus frames; optional `add_zoom_connectors` / `add_orthogonal_bus_connectors` appear only on compact adjacent panel gaps without crossing text or graticules.

## Stopping Rule (No Endless Polishing)

- Run **1 full-image `read_image`** on the fast PNG draft (`formats=("png",)`).
- If any hard defect above fails, batch **all** fixes into **1-2 targeted edits** and verify once.
- As soon as all hard defects above are zero, export `formats=("png", "svg")` immediately and call `finish_task`. NEVER loop on subjective tint tweaks or cut 4 zoomed crops of an already clean figure.
