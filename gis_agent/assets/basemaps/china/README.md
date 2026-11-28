# Standard China Basemap (`china_standard.gpkg`)

Offline standard China administrative basemap in **CGCS2000 (`EPSG:4490`)** for compliant thematic cartography:

- `provinces`: 34 provincial administrative units (`adcode`, `name`, `short_name`), including Taiwan Province, Hong Kong, Macao, and Hainan Island.
- `ten_dash_line`: South China Sea islands and ten-dash boundary segments (`adcode = "100000_JD"`).
- `national_boundary`: Dissolved outer boundary geometry of China.

## Custom Override
Users with an officially downloaded Ministry of Natural Resources / Tianditu `GS(2024)0650` dataset may point `GIS_AGENT_CHINA_BASEMAP` (or pass `custom_path=...` to `load_china_standard_basemap` / `plot_china_standard_map`) to their local GeoPackage, Shapefile, or GeoJSON.
