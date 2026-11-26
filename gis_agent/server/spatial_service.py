"""Viewport-adaptive vector GeoJSON, WarpedVRT raster PNG preview, spatial Identify & attribute paging."""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import io
import math
from pathlib import Path
from threading import RLock
from typing import Any

from gis_agent.runtime.inspect_fast import _clean_scalar, _inspect_raster_rasterio, _inspect_vector_pyogrio

RASTER_CACHE_MAX_BYTES = 64 * 1024 * 1024


def _split_uri(raw_path: str) -> tuple[Path, str | None]:
    if "|layername=" in raw_path:
        raw, layer = raw_path.split("|layername=", 1)
        return Path(raw).expanduser().resolve(), layer.split("|", 1)[0]
    return Path(raw_path).expanduser().resolve(), None


def _is_valid_wgs84_bounds(bounds: list[float] | None) -> bool:
    if not bounds or len(bounds) != 4:
        return False
    try:
        w, s, e, n = (float(v) for v in bounds)
    except (TypeError, ValueError):
        return False
    if not all(math.isfinite(v) for v in (w, s, e, n)):
        return False
    if w == 0.0 and s == 0.0 and e == 0.0 and n == 0.0:
        return False
    return -180.5 <= w <= e <= 180.5 and -90.5 <= s <= n <= 90.5


def _to_wgs84_bounds(crs_str: str | None, extent: list[float]) -> list[float] | None:
    if not extent or len(extent) != 4 or any(not math.isfinite(v) for v in extent):
        return None
    if not crs_str or crs_str.upper() in {"EPSG:4326", "OGC:CRS84", "CRS:84"}:
        cand = [float(v) for v in extent]
        return cand if _is_valid_wgs84_bounds(cand) else None
    from pyproj import CRS, Transformer

    try:
        src = CRS.from_user_input(crs_str)
        if src.is_geographic and src.to_epsg() == 4326:
            cand = [float(v) for v in extent]
            return cand if _is_valid_wgs84_bounds(cand) else None
        transformer = Transformer.from_crs(src, "EPSG:4326", always_xy=True)
        w, s, e, n = transformer.transform_bounds(*extent, densify_pts=21)
        if all(math.isfinite(v) for v in (w, s, e, n)):
            cand = [round(float(w), 6), round(float(s), 6), round(float(e), 6), round(float(n), 6)]
            return cand if _is_valid_wgs84_bounds(cand) else None
    except Exception:
        return None
    return None


CSV_LON_CANDIDATES = ("lon", "lng", "longitude", "long", "x", "jd", "经度")
CSV_LAT_CANDIDATES = ("lat", "latitude", "y", "wd", "纬度")
MAX_CSV_PREVIEW_ROWS = 50_000


def _read_csv_df(file_path: Path, *, nrows: int | None = None):
    import pandas as pd

    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return pd.read_csv(file_path, nrows=nrows, encoding=enc)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(file_path, nrows=nrows, encoding="utf-8", encoding_errors="replace")


def _detect_csv_lon_lat(fieldnames: list[str]) -> tuple[str | None, str | None]:
    lower_map = {str(col).strip().lower(): str(col) for col in fieldnames}
    lon_col = next((lower_map[c] for c in CSV_LON_CANDIDATES if c in lower_map), None)
    lat_col = next((lower_map[c] for c in CSV_LAT_CANDIDATES if c in lower_map), None)
    return lon_col, lat_col


def _inspect_csv(file_path: Path) -> dict[str, Any]:
    import numpy as np
    import pandas as pd

    df = _read_csv_df(file_path, nrows=MAX_CSV_PREVIEW_ROWS + 1)
    truncated_csv = len(df) > MAX_CSV_PREVIEW_ROWS
    if truncated_csv:
        df = df.iloc[:MAX_CSV_PREVIEW_ROWS]
    fields = [{"name": str(c), "type": str(df[c].dtype)} for c in df.columns]
    lon_col, lat_col = _detect_csv_lon_lat([str(c) for c in df.columns])
    if not lon_col or not lat_col:
        return {
            "kind": "table",
            "source": str(file_path),
            "feature_count": int(len(df)),
            "fields": fields,
            "warnings": ["no_spatial_columns"],
        }

    lons = pd.to_numeric(df[lon_col], errors="coerce")
    lats = pd.to_numeric(df[lat_col], errors="coerce")
    valid_mask = (
        lons.notna()
        & lats.notna()
        & np.isfinite(lons)
        & np.isfinite(lats)
        & lons.between(-180.0, 180.0)
        & lats.between(-90.0, 90.0)
    )
    valid_count = int(valid_mask.sum())
    if len(df) > 0 and valid_count == 0:
        return {
            "kind": "table",
            "source": str(file_path),
            "feature_count": int(len(df)),
            "fields": fields,
            "warnings": ["no_spatial_columns"],
        }

    warnings: list[str] = []
    bbox: list[float] | None = None
    if valid_count == 0:
        warnings.append("empty_features")
    else:
        cand = [
            round(float(lons[valid_mask].min()), 6),
            round(float(lats[valid_mask].min()), 6),
            round(float(lons[valid_mask].max()), 6),
            round(float(lats[valid_mask].max()), 6),
        ]
        bbox = cand if _is_valid_wgs84_bounds(cand) else None
    if truncated_csv:
        warnings.append("csv_preview_truncated")
    return {
        "kind": "vector",
        "source": str(file_path),
        "feature_count": valid_count,
        "geometry_type": "Point",
        "crs": "EPSG:4326",
        "fields": fields,
        "bbox_wgs84": bbox,
        "warnings": warnings,
        "is_csv_points": True,
        "lon_col": lon_col,
        "lat_col": lat_col,
    }


def _read_csv_geojson(
    file_path: Path,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    max_features: int = 5000,
    fids: list[int] | None = None,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    import numpy as np
    import pandas as pd

    df = _read_csv_df(file_path, nrows=MAX_CSV_PREVIEW_ROWS)
    all_fields = [str(c) for c in df.columns]
    lon_col, lat_col = _detect_csv_lon_lat(all_fields)
    if not lon_col or not lat_col:
        raise ValueError("该 CSV 不包含可识别的经纬度坐标列")

    df = df.copy()
    df["_fid"] = df.index.astype(int)
    lons = pd.to_numeric(df[lon_col], errors="coerce")
    lats = pd.to_numeric(df[lat_col], errors="coerce")
    valid_mask = (
        lons.notna()
        & lats.notna()
        & np.isfinite(lons)
        & np.isfinite(lats)
        & lons.between(-180.0, 180.0)
        & lats.between(-90.0, 90.0)
    )
    df["_lon"] = lons
    df["_lat"] = lats
    valid_df = df.loc[valid_mask]
    total_features = int(len(valid_df))

    if fids:
        clean_fids = set(int(x) for x in fids[:200])
        view_df = valid_df.loc[valid_df["_fid"].isin(clean_fids)]
        truncated = False
    else:
        view_df = valid_df
        if bbox is not None:
            w, s, e, n = bbox
            view_df = view_df.loc[view_df["_lon"].between(w, e) & view_df["_lat"].between(s, n)]
        limit = max(100, min(int(max_features), 20000))
        truncated = len(view_df) > limit
        if truncated:
            view_df = view_df.iloc[:limit]

    use_fields = [f for f in fields if f in all_fields] if fields is not None else all_fields[:24]
    features: list[dict[str, Any]] = []
    for rec in view_df.to_dict(orient="records"):
        lon_v = round(float(rec["_lon"]), 6)
        lat_v = round(float(rec["_lat"]), 6)
        props = _json_safe_row({k: rec.get(k) for k in use_fields})
        props["_fid"] = int(rec["_fid"])
        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Point", "coordinates": [lon_v, lat_v]},
        })

    bounds = None
    if len(view_df):
        cand = [
            round(float(view_df["_lon"].min()), 6),
            round(float(view_df["_lat"].min()), 6),
            round(float(view_df["_lon"].max()), 6),
            round(float(view_df["_lat"].max()), 6),
        ]
        bounds = cand if _is_valid_wgs84_bounds(cand) else None

    warnings: list[str] = []
    if total_features == 0:
        warnings.append("empty_features")
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "path": str(file_path),
            "layer": None,
            "crs": "EPSG:4326",
            "geometry_type": "Point",
            "fields": all_fields,
            "total_features": total_features,
            "returned_features": len(features),
            "truncated": bool(truncated or (bbox is not None and total_features > len(features) and not fids)),
            "simplified_tol_deg": 0.0,
            "bbox_wgs84": bounds,
            "warnings": warnings,
        },
    }


def _json_safe_row(row_dict: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for k, v in row_dict.items():
        if v is None:
            cleaned[str(k)] = None
        elif hasattr(v, "isoformat"):
            cleaned[str(k)] = v.isoformat()
        elif isinstance(v, (bytes, bytearray)):
            cleaned[str(k)] = f"<{len(v)} bytes>"
        else:
            cleaned[str(k)] = _clean_scalar(v)
    return cleaned


class SpatialService:
    """Stateless-disk, cached viewport vector/raster engine powered by pyogrio & rasterio."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._raster_cache: OrderedDict[str, tuple[int, dict[str, Any]]] = OrderedDict()
        self._raster_cache_bytes = 0

    def _cache_get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._raster_cache.get(key)
            if entry is None:
                return None
            self._raster_cache.move_to_end(key)
            return entry[1]

    def _cache_put(self, key: str, size_bytes: int, value: dict[str, Any]) -> None:
        if size_bytes > RASTER_CACHE_MAX_BYTES:
            return
        with self._lock:
            if key in self._raster_cache:
                old_sz, _ = self._raster_cache.pop(key)
                self._raster_cache_bytes -= old_sz
            while self._raster_cache and (self._raster_cache_bytes + size_bytes > RASTER_CACHE_MAX_BYTES):
                _, (ev_sz, _) = self._raster_cache.popitem(last=False)
                self._raster_cache_bytes -= ev_sz
            self._raster_cache[key] = (size_bytes, value)
            self._raster_cache_bytes += size_bytes

    def get_layer_meta(self, authorized_uri: str) -> dict[str, Any]:
        file_path, _layer = _split_uri(authorized_uri)
        ext = file_path.suffix.lower()
        if ext == ".csv":
            return _inspect_csv(file_path)
        if ext in {".tif", ".tiff", ".img", ".vrt", ".asc", ".nc"}:
            info = _inspect_raster_rasterio(authorized_uri)
            if info.get("kind") == "raster":
                info["bbox_wgs84"] = _to_wgs84_bounds(info.get("crs"), info.get("extent", []))
                warnings: list[str] = []
                if not info.get("crs"):
                    warnings.append("missing_crs")
                if info.get("extent") and info["bbox_wgs84"] is None:
                    warnings.append("invalid_bounds")
                info["warnings"] = warnings
            return info

        info = _inspect_vector_pyogrio(authorized_uri)
        if info.get("kind") == "container":
            for layer_entry in info.get("layers", []):
                try:
                    sub_meta = _inspect_vector_pyogrio(layer_entry["source"])
                    layer_entry["feature_count"] = sub_meta.get("feature_count")
                    layer_entry["crs"] = sub_meta.get("crs")
                    layer_entry["bbox_wgs84"] = _to_wgs84_bounds(sub_meta.get("crs"), sub_meta.get("extent", []))
                except Exception:
                    pass
            return info

        feature_count = int(info.get("feature_count") or 0)
        info["bbox_wgs84"] = None if feature_count == 0 else _to_wgs84_bounds(info.get("crs"), info.get("extent", []))
        vec_warnings: list[str] = []
        if feature_count == 0:
            vec_warnings.append("empty_features")
        if not info.get("crs"):
            vec_warnings.append("missing_crs")
        if feature_count > 0 and info.get("extent") and info["bbox_wgs84"] is None:
            vec_warnings.append("invalid_bounds")
        info["warnings"] = vec_warnings
        return info

    def get_vector_geojson(
        self,
        authorized_uri: str,
        *,
        bbox: tuple[float, float, float, float] | None = None,
        zoom: float | None = None,
        max_features: int = 5000,
        simplify_tol: float | None = None,
        fields: list[str] | None = None,
        fids: list[int] | None = None,
    ) -> dict[str, Any]:
        import json
        import pyogrio
        from pyproj import CRS, Transformer

        file_path, layer_name = _split_uri(authorized_uri)
        if file_path.suffix.lower() == ".csv":
            return _read_csv_geojson(file_path, bbox=bbox, max_features=max_features, fids=fids, fields=fields)

        info = pyogrio.read_info(str(file_path), layer=layer_name)
        total_features = int(info.get("features") or 0)
        raw_crs = info.get("crs")
        src_crs = CRS.from_user_input(raw_crs) if raw_crs else None
        geom_type = str(info.get("geometry_type") or "Unknown")
        raw_fields = info.get("fields")
        all_fields = [str(f) for f in raw_fields] if raw_fields is not None else []
        use_fields = [f for f in fields if f in all_fields] if fields is not None else all_fields[:24]

        query_bbox = None
        if bbox is not None and not fids:
            if src_crs is not None and not (src_crs.is_geographic and src_crs.to_epsg() == 4326):
                tr = Transformer.from_crs("EPSG:4326", src_crs, always_xy=True)
                query_bbox = tr.transform_bounds(*bbox, densify_pts=12)
            else:
                query_bbox = bbox

        if fids:
            clean_fids = list(dict.fromkeys(int(x) for x in fids))[:200]
            try:
                gdf = pyogrio.read_dataframe(
                    str(file_path),
                    layer=layer_name,
                    columns=use_fields,
                    fids=clean_fids,
                    fid_as_index=True,
                )
            except Exception:
                gdf = pyogrio.read_dataframe(
                    str(file_path),
                    layer=layer_name,
                    columns=use_fields,
                    fid_as_index=True,
                )
                gdf = gdf.loc[gdf.index.isin(clean_fids)]
            else:
                if len(gdf) == 0 and total_features > 0:
                    full_gdf = pyogrio.read_dataframe(
                        str(file_path),
                        layer=layer_name,
                        columns=use_fields,
                        fid_as_index=True,
                    )
                    gdf = full_gdf.loc[full_gdf.index.isin(clean_fids)]
            truncated = False
        else:
            limit = max(100, min(int(max_features), 20000))
            read_limit = limit if (total_features > limit or query_bbox is not None) else None
            gdf = pyogrio.read_dataframe(
                str(file_path),
                layer=layer_name,
                columns=use_fields,
                bbox=query_bbox,
                max_features=read_limit + 1 if read_limit is not None else None,
                fid_as_index=True,
            )
            truncated = read_limit is not None and len(gdf) > read_limit
            if truncated:
                gdf = gdf.iloc[:read_limit]

        if gdf.crs is not None:
            if not (gdf.crs.is_geographic and gdf.crs.to_epsg() == 4326):
                gdf = gdf.to_crs("EPSG:4326")

        effective_tol = None if fids else simplify_tol
        if not fids and effective_tol is None and zoom is not None and (total_features > 1500 or len(gdf) > 1500):
            deg_per_px = 360.0 / (256.0 * (2.0 ** max(0.0, min(float(zoom), 20.0))))
            effective_tol = max(deg_per_px * 1.1, 1e-5)

        if effective_tol and effective_tol > 0 and "Point" not in geom_type:
            simplified = gdf.geometry.simplify(effective_tol, preserve_topology=True)
            gdf = gdf.assign(geometry=simplified)

        gdf = gdf[~gdf.geometry.isna() & ~gdf.geometry.is_empty].copy()
        gdf["_fid"] = gdf.index.astype(int)
        for col in list(gdf.columns):
            if col == gdf.geometry.name or col == "_fid":
                continue
            if gdf[col].dtype == object or str(gdf[col].dtype).startswith("datetime"):
                gdf[col] = gdf[col].map(lambda v: _clean_scalar(v.isoformat() if hasattr(v, "isoformat") else v))

        geojson_obj = json.loads(gdf.to_json(drop_id=True)) if len(gdf) else {"type": "FeatureCollection", "features": []}
        raw_tb = info.get("total_bounds")
        fallback_tb = [float(x) for x in raw_tb] if raw_tb is not None else []
        raw_bounds = (
            [float(x) for x in gdf.total_bounds]
            if len(gdf)
            else _to_wgs84_bounds(src_crs.to_string() if src_crs else None, fallback_tb)
        )
        bounds = raw_bounds if _is_valid_wgs84_bounds(raw_bounds) else None
        warnings: list[str] = []
        if total_features == 0:
            warnings.append("empty_features")
        if src_crs is None:
            warnings.append("missing_crs")
        if total_features > 0 and raw_bounds is not None and bounds is None:
            warnings.append("invalid_bounds")
        geojson_obj["meta"] = {
            "path": str(file_path),
            "layer": layer_name,
            "crs": src_crs.to_string() if src_crs else "",
            "geometry_type": geom_type,
            "fields": all_fields,
            "total_features": total_features,
            "returned_features": len(geojson_obj.get("features", [])),
            "truncated": bool((not fids) and (truncated or (total_features > len(gdf) and query_bbox is not None))),
            "simplified_tol_deg": float(effective_tol) if effective_tol else 0.0,
            "bbox_wgs84": bounds,
            "warnings": warnings,
        }
        return geojson_obj

    def get_raster_preview(
        self,
        authorized_uri: str,
        *,
        bbox: tuple[float, float, float, float] | None = None,
        width: int = 1024,
        height: int = 1024,
        band: int = 1,
        colormap: str = "viridis",
        p_low: float = 2.0,
        p_high: float = 98.0,
    ) -> dict[str, Any]:
        import matplotlib
        import numpy as np
        from PIL import Image
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.vrt import WarpedVRT
        from rasterio.windows import bounds as window_bounds
        from rasterio.windows import from_bounds

        file_path, _ = _split_uri(authorized_uri)
        st = file_path.stat() if file_path.is_file() else None
        sig = f"{authorized_uri}|{st.st_mtime_ns if st else 0}|{st.st_size if st else 0}|{bbox}|{width}x{height}|{band}|{colormap}|{p_low}-{p_high}"
        cache_key = hashlib.sha256(sig.encode("utf-8")).hexdigest()
        if cached := self._cache_get(cache_key):
            return cached

        max_w = max(64, min(int(width), 1024))
        max_h = max(64, min(int(height), 1024))

        from contextlib import nullcontext

        with rasterio.open(authorized_uri) as src:
            band_count = int(src.count)
            use_vrt = src.crs is not None
            ds_ctx = WarpedVRT(src, crs="EPSG:4326", resampling=Resampling.bilinear) if use_vrt else nullcontext(src)
            with ds_ctx as ds:
                ds_bounds = tuple(float(v) for v in ds.bounds)
                if bbox is not None:
                    req_w = max(bbox[0], ds_bounds[0])
                    req_s = max(bbox[1], ds_bounds[1])
                    req_e = min(bbox[2], ds_bounds[2])
                    req_n = min(bbox[3], ds_bounds[3])
                    if req_w >= req_e or req_s >= req_n:
                        blank = io.BytesIO()
                        Image.new("RGBA", (2, 2), (0, 0, 0, 0)).save(blank, format="PNG")
                        return {
                            "png_bytes": blank.getvalue(),
                            "bounds_wgs84": list(ds_bounds),
                            "band": band,
                            "band_count": band_count,
                            "stats": {"min": None, "max": None, "vmin": None, "vmax": None},
                        }
                    win = from_bounds(req_w, req_s, req_e, req_n, ds.transform)
                else:
                    win = rasterio.windows.Window(0, 0, ds.width, ds.height)

                win = win.round_offsets(op="floor").round_lengths(op="ceil")
                exact_bounds = [round(float(v), 6) for v in window_bounds(win, ds.transform)]
                win_w = max(1, int(win.width))
                win_h = max(1, int(win.height))
                scale = min(max_w / win_w, max_h / win_h, 1.0)
                out_w = max(2, int(round(win_w * scale)))
                out_h = max(2, int(round(win_h * scale)))

                if band == 0 and ds.count >= 3:
                    arr = ds.read([1, 2, 3], window=win, out_shape=(3, out_h, out_w), masked=True)
                    rgb_u8 = np.zeros((out_h, out_w, 4), dtype=np.uint8)
                    valid = ~np.any(np.ma.getmaskarray(arr), axis=0)
                    for idx in range(3):
                        ch = arr[idx].astype(np.float64)
                        vals = ch[valid & np.isfinite(ch.data)].compressed() if hasattr(ch, "compressed") else ch.data[valid]
                        if vals.size:
                            lo, hi = np.percentile(vals, [p_low, p_high])
                            if hi <= lo:
                                hi = lo + 1.0
                            scaled = np.clip((ch.data - lo) / (hi - lo), 0.0, 1.0) * 255.0
                            rgb_u8[:, :, idx] = np.where(valid, scaled.astype(np.uint8), 0)
                    rgb_u8[:, :, 3] = np.where(valid, 255, 0).astype(np.uint8)
                    stats = {"min": None, "max": None, "vmin": None, "vmax": None, "mode": "rgb"}
                    rgba_u8 = rgb_u8
                else:
                    b_idx = max(1, min(int(band), ds.count))
                    arr = ds.read(b_idx, window=win, out_shape=(out_h, out_w), masked=True)
                    mask = np.ma.getmaskarray(arr) | ~np.isfinite(arr.data)
                    valid = ~mask
                    raw_vals = arr.data[valid].astype(np.float64)
                    if raw_vals.size == 0:
                        rgba_u8 = np.zeros((out_h, out_w, 4), dtype=np.uint8)
                        stats = {"min": None, "max": None, "vmin": None, "vmax": None, "mode": "single"}
                    else:
                        dmin = float(np.min(raw_vals))
                        dmax = float(np.max(raw_vals))
                        lo = float(np.percentile(raw_vals, p_low))
                        hi = float(np.percentile(raw_vals, p_high))
                        if not math.isfinite(hi - lo) or hi <= lo:
                            lo, hi = dmin, dmax
                        span = (hi - lo) if hi > lo else 1.0
                        norm = np.clip((np.where(valid, arr.data.astype(np.float64), lo) - lo) / span, 0.0, 1.0)
                        cmap_name = colormap if colormap in matplotlib.colormaps else "viridis"
                        cmap = matplotlib.colormaps[cmap_name]
                        rgba = cmap(norm)
                        rgba[:, :, 3] = np.where(valid, 1.0, 0.0)
                        rgba_u8 = np.clip(rgba * 255.0, 0, 255).astype(np.uint8)
                        stats = {
                            "min": round(dmin, 6),
                            "max": round(dmax, 6),
                            "vmin": round(lo, 6),
                            "vmax": round(hi, 6),
                            "mode": "single",
                        }

        buf = io.BytesIO()
        Image.fromarray(rgba_u8, mode="RGBA").save(buf, format="PNG")
        payload = {
            "png_bytes": buf.getvalue(),
            "bounds_wgs84": exact_bounds,
            "band": band,
            "band_count": band_count,
            "stats": stats,
        }
        self._cache_put(cache_key, len(payload["png_bytes"]), payload)
        return payload

    def identify(
        self,
        *,
        lon: float,
        lat: float,
        layers: list[dict[str, Any]],
        tolerance_m: float | None = None,
        zoom: float = 10.0,
    ) -> dict[str, Any]:
        import math as _math
        import numpy as np
        import pyogrio
        from pyproj import CRS, Transformer
        import rasterio
        from shapely.geometry import Point

        if tolerance_m is None:
            meters_per_px = 156543.03 * max(_math.cos(_math.radians(lat)), 0.1) / (2.0 ** max(0.0, min(zoom, 20.0)))
            tolerance_m = max(10.0, meters_per_px * 12.0)

        results: list[dict[str, Any]] = []
        for entry in layers:
            uri = str(entry["resolved_uri"])
            ltype = str(entry.get("type") or "auto")
            file_path, layer_name = _split_uri(uri)
            if ltype == "auto":
                ltype = "raster" if file_path.suffix.lower() in {".tif", ".tiff", ".img", ".vrt", ".asc"} else "vector"

            if ltype == "vector":
                info = pyogrio.read_info(str(file_path), layer=layer_name)
                raw_crs = info.get("crs")
                src_crs = CRS.from_user_input(raw_crs) if raw_crs else None
                if src_crs is not None and not (src_crs.is_geographic and src_crs.to_epsg() == 4326):
                    tr = Transformer.from_crs("EPSG:4326", src_crs, always_xy=True)
                    qx, qy = tr.transform(lon, lat)
                else:
                    qx, qy = lon, lat
                is_deg = src_crs is None or src_crs.is_geographic
                tol_units = (tolerance_m / 111_320.0) if is_deg else tolerance_m
                q_bbox = (qx - tol_units, qy - tol_units, qx + tol_units, qy + tol_units)
                gdf = pyogrio.read_dataframe(str(file_path), layer=layer_name, bbox=q_bbox, max_features=50, fid_as_index=True)
                hits: list[dict[str, Any]] = []
                if len(gdf):
                    pt = Point(qx, qy)
                    distances = gdf.geometry.distance(pt)
                    gdf = gdf.assign(_dist=distances).sort_values("_dist")
                    for fid, row in gdf.iterrows():
                        dist = float(row["_dist"])
                        if dist <= tol_units or dist == 0.0:
                            props = {c: row[c] for c in gdf.columns if c not in {gdf.geometry.name, "_dist"}}
                            hits.append({
                                "fid": int(fid),
                                "distance": round(dist * 111_320.0 if is_deg else dist, 2),
                                "properties": _json_safe_row(props),
                            })
                        if len(hits) >= 5:
                            break
                results.append({"path": uri, "type": "vector", "hits": hits})
            elif ltype == "raster":
                with rasterio.open(uri) as ds:
                    if ds.crs is not None:
                        tr = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True)
                        qx, qy = tr.transform(lon, lat)
                    else:
                        qx, qy = lon, lat
                    left, bottom, right, top = ds.bounds
                    if not (left <= qx <= right and bottom <= qy <= top):
                        results.append({"path": uri, "type": "raster", "inside": False, "bands": []})
                        continue
                    sample = next(ds.sample([(qx, qy)]))
                    band_hits: list[dict[str, Any]] = []
                    for idx in range(1, ds.count + 1):
                        raw_v = float(sample[idx - 1])
                        nodata = ds.nodatavals[idx - 1]
                        is_nd = (not math.isfinite(raw_v)) or (nodata is not None and math.isclose(raw_v, float(nodata), rel_tol=1e-7, abs_tol=1e-12))
                        scale = float(ds.scales[idx - 1]) if ds.scales else 1.0
                        offset = float(ds.offsets[idx - 1]) if ds.offsets else 0.0
                        phys = None if is_nd else (raw_v * scale + offset)
                        band_hits.append({
                            "band": idx,
                            "raw_value": None if is_nd else _clean_scalar(raw_v),
                            "physical_value": None if phys is None else round(float(phys), 6),
                            "unit": ds.units[idx - 1] or None,
                            "is_nodata": bool(is_nd),
                        })
                    results.append({"path": uri, "type": "raster", "inside": True, "bands": band_hits})

        return {"lon": lon, "lat": lat, "tolerance_m": round(tolerance_m, 2), "results": results}

    def get_attributes(
        self,
        authorized_uri: str,
        *,
        page: int = 1,
        page_size: int = 100,
        sort_by: str | None = None,
        order: str = "asc",
        query: str | None = None,
        stats_field: str | None = None,
    ) -> dict[str, Any]:
        import numpy as np
        import pandas as pd
        import pyogrio

        file_path, layer_name = _split_uri(authorized_uri)
        if file_path.suffix.lower() == ".csv":
            df = _read_csv_df(file_path, nrows=MAX_CSV_PREVIEW_ROWS).copy()
            all_fields = [str(c) for c in df.columns]
            lon_col, lat_col = _detect_csv_lon_lat(all_fields)
            df["_fid"] = df.index.astype(int)
            if lon_col and lat_col:
                lons = pd.to_numeric(df[lon_col], errors="coerce")
                lats = pd.to_numeric(df[lat_col], errors="coerce")
                df["_bbox_wgs84"] = [
                    [round(float(x), 6), round(float(y), 6), round(float(x), 6), round(float(y), 6)]
                    if (
                        x is not None
                        and y is not None
                        and math.isfinite(float(x))
                        and math.isfinite(float(y))
                        and -180.0 <= float(x) <= 180.0
                        and -90.0 <= float(y) <= 90.0
                    )
                    else None
                    for x, y in zip(lons, lats)
                ]
            else:
                df["_bbox_wgs84"] = None
        else:
            info = pyogrio.read_info(str(file_path), layer=layer_name)
            raw_fields = info.get("fields")
            all_fields = [str(f) for f in raw_fields] if raw_fields is not None else []
            gdf = pyogrio.read_dataframe(str(file_path), layer=layer_name, fid_as_index=True)
            if gdf.crs is not None and not (gdf.crs.is_geographic and gdf.crs.to_epsg() == 4326):
                gdf = gdf.to_crs("EPSG:4326")

            df = pd.DataFrame(gdf.drop(columns=[gdf.geometry.name], errors="ignore"))
            df["_fid"] = gdf.index.astype(int)
            if len(gdf) and gdf.geometry.name in gdf.columns:
                b = gdf.geometry.bounds
                df["_bbox_wgs84"] = [
                    [round(float(r.minx), 6), round(float(r.miny), 6), round(float(r.maxx), 6), round(float(r.maxy), 6)]
                    if all(math.isfinite(x) for x in (r.minx, r.miny, r.maxx, r.maxy))
                    else None
                    for r in b.itertuples(index=False)
                ]
            else:
                df["_bbox_wgs84"] = None

        stats_summary: dict[str, Any] | None = None
        if stats_field and stats_field in df.columns:
            series = pd.to_numeric(df[stats_field], errors="coerce").dropna()
            if len(series):
                vals = series.to_numpy(dtype=float)
                vmin, vmax = float(vals.min()), float(vals.max())
                q_breaks = [float(x) for x in np.quantile(vals, [0.0, 0.2, 0.4, 0.6, 0.8, 1.0])]
                eq_breaks = [float(x) for x in np.linspace(vmin, vmax, 6)]
                hist_counts, hist_edges = np.histogram(vals, bins=12)
                stats_summary = {
                    "field": stats_field,
                    "count": int(len(vals)),
                    "min": vmin,
                    "max": vmax,
                    "mean": float(vals.mean()),
                    "median": float(np.median(vals)),
                    "quantile_breaks": q_breaks,
                    "equal_interval_breaks": eq_breaks,
                    "histogram": [
                        {"start": float(hist_edges[i]), "end": float(hist_edges[i + 1]), "count": int(hist_counts[i])}
                        for i in range(len(hist_counts))
                    ],
                }

        if query and query.strip():
            q = query.strip().lower()
            text_cols = [c for c in all_fields if c in df.columns]
            if text_cols:
                mask = df[text_cols].astype(str).apply(lambda col: col.str.lower().str.contains(q, regex=False)).any(axis=1)
                df = df[mask]

        if sort_by and sort_by in df.columns:
            df = df.sort_values(by=sort_by, ascending=(order.lower() != "desc"), kind="mergesort")

        total = int(len(df))
        page = max(1, int(page))
        page_size = max(10, min(int(page_size), 500))
        start = (page - 1) * page_size
        slice_df = df.iloc[start : start + page_size]

        rows: list[dict[str, Any]] = []
        for rec in slice_df.to_dict(orient="records"):
            bbox_val = rec.pop("_bbox_wgs84", None)
            fid_val = int(rec.pop("_fid"))
            safe = _json_safe_row(rec)
            safe["_fid"] = fid_val
            safe["_bbox_wgs84"] = bbox_val
            rows.append(safe)

        return {
            "fields": all_fields,
            "page": page,
            "page_size": page_size,
            "total": total,
            "rows": rows,
            "stats": stats_summary,
        }
