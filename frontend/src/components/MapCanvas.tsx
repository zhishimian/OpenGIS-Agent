import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  BoxSelect,
  Check,
  Crosshair,
  Eye,
  EyeOff,
  Focus,
  FolderPlus,
  Hand,
  Hexagon,
  Layers,
  Map as MapIcon,
  ChevronDown,
  Maximize2,
  MousePointerClick,
  Table2,
  Trash2,
  X,
} from "lucide-react";
import { api } from "../api/client";
import { useStudioStore } from "../store/useStudioStore";
import { formatLayerDisplayName, isValidWgs84Bbox } from "../utils/layerOrder";
import type { BasemapKind, GeoJsonFeatureCollection, LayerItem, LayerRole } from "../types/studio";

const mapTools = [
  { id: "pan", icon: Hand, label: "漫游" },
  { id: "identify", icon: Crosshair, label: "点查" },
  { id: "bbox", icon: BoxSelect, label: "框选范围" },
  { id: "polygon", icon: Hexagon, label: "绘制多边形" },
  { id: "select_fid", icon: MousePointerClick, label: "点选要素" },
] as const;

function buildStyleSpec(basemap: BasemapKind): maplibregl.StyleSpecification {
  if (basemap === "offline") {
    return {
      version: 8,
      name: "OpenGIS Offline",
      sources: {},
      layers: [
        {
          id: "bg-offline",
          type: "background",
          paint: { "background-color": "#f3f5f8" },
        },
      ],
    };
  }
  const tiles: Record<Exclude<BasemapKind, "offline">, string[]> = {
    positron: ["https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"],
    dark: ["https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"],
    osm: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
  };
  return {
    version: 8,
    sources: {
      basemap: { type: "raster", tiles: tiles[basemap], tileSize: 256, maxzoom: 19 },
    },
    layers: [{ id: "basemap-tiles", type: "raster", source: "basemap" }],
  };
}

function rampFillExpression(layer: LayerItem): any {
  if (!layer.styleField || layer.breaks.length < 2) return layer.color;
  const expr: any[] = ["step", ["coalesce", ["to-number", ["get", layer.styleField]], 0], layer.palette[0]];
  for (let i = 1; i < Math.min(layer.breaks.length - 1, layer.palette.length); i++) {
    expr.push(layer.breaks[i], layer.palette[i]);
  }
  return expr;
}

const SYSTEM_PREFIXES = ["ogis-user-aoi-", "ogis-highlight-"];

const WARNING_LABELS: Record<string, string> = {
  missing_crs: "缺少 CRS",
  empty_features: "空图层 (0 要素)",
  invalid_bounds: "范围非经纬度",
  csv_preview_truncated: "CSV 仅预览前 5 万行",
};

const ROLE_SECTIONS: Array<{ role: LayerRole; title: string }> = [
  { role: "result", title: "最终成果" },
  { role: "input", title: "原始输入" },
  { role: "intermediate", title: "中间过程" },
];

function extractBusinessLayerId(styleLayerId: string): string {
  const m = /^ogis-(.+)-(fill|line|pt|raster)$/.exec(styleLayerId);
  return m ? m[1] : styleLayerId.slice(5);
}

export function MapCanvas({ onSwitchFolder }: { onSwitchFolder: () => void }) {
  const {
    env,
    isTauri,
    layers,
    files,
    basemap,
    mapTool,
    fitBoundsSeq,
    fitBoundsTarget,
    identifyPopup,
    selectedLayerPaths,
    selectedFids,
    attrLayerPath,
    drawnBboxWgs84,
    drawnGeometryGeojson,
    orderPinned,
    soloLayerId,
    highlightedFeature,
    pendingContainer,
    setBasemap,
    setMapTool,
    setIdentifyPopup,
    setDrawnAoi,
    setClickedPoint,
    setSelectedFids,
    toggleLayerVisible,
    toggleLayerSolo,
    setLayerOpacity,
    moveLayer,
    resetLayerOrder,
    removeLayer,
    zoomToLayer,
    focusResultLayers,
    refreshLayerViewport,
    highlightAttributeRow,
    clearHighlight,
    setPendingContainer,
    styleVectorLayerByField,
    updateRasterStyle,
    toggleLayerSelectedForContext,
    addLayerByPath,
    attachAndAddLayer,
    setAttrLayerPath,
    setToast,
  } = useStudioStore();

  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const bboxStartRef = useRef<[number, number] | null>(null);
  const viewportTimerRef = useRef<number | null>(null);
  const viewportControllersRef = useRef<Map<string, AbortController>>(new Map());
  const lastViewportRef = useRef<Map<string, { bbox: [number, number, number, number]; zoom: number }>>(new Map());
  const prevHasResultRef = useRef(false);

  const [bboxRect, setBboxRect] = useState<[number, number, number, number] | null>(null);
  const [polyVerts, setPolyVerts] = useState<Array<[number, number]>>([]);
  const [pickerOpen, setPickerOpen] = useState(false);

  const [layersCollapsed, setLayersCollapsed] = useState(false);
  const [groupOpen, setGroupOpen] = useState<Record<LayerRole, boolean>>({
    result: true,
    input: true,
    intermediate: true,
  });

  // Attribute drawer state
  const [attrRows, setAttrRows] = useState<any[]>([]);
  const [attrFields, setAttrFields] = useState<string[]>([]);
  const [attrPage, setAttrPage] = useState(1);
  const [attrTotal, setAttrTotal] = useState(0);
  const [attrQuery, setAttrQuery] = useState("");

  // Auto-collapse intermediate section once final result layers appear
  useEffect(() => {
    const hasResult = layers.some((l) => l.role === "result");
    if (hasResult && !prevHasResultRef.current) {
      setGroupOpen((prev) => ({ ...prev, result: true, intermediate: false }));
    } else if (!hasResult && prevHasResultRef.current) {
      setGroupOpen((prev) => ({ ...prev, intermediate: true }));
    }
    prevHasResultRef.current = hasResult;
  }, [layers]);

  // Initialize MapLibre
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: buildStyleSpec(basemap),
      center: [118.8, 32.1],
      zoom: 5,
      attributionControl: false,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), "bottom-right");
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: "metric" }), "bottom-left");
    const onStyleLoad = () => syncMapLayers();
    map.on("style.load", onStyleLoad);
    mapRef.current = map;
    const observer = new ResizeObserver(() => {
      if (map.getContainer().clientWidth > 0) map.resize();
    });
    observer.observe(containerRef.current);

    return () => {
      map.off("style.load", onStyleLoad);
      if (viewportTimerRef.current !== null) {
        window.clearTimeout(viewportTimerRef.current);
      }
      for (const ctrl of viewportControllersRef.current.values()) {
        ctrl.abort();
      }
      viewportControllersRef.current.clear();
      observer.disconnect();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Switch basemap cleanly then re-sync layers
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.setStyle(buildStyleSpec(basemap));
  }, [basemap]);

  // Fit bounds when triggered (strict WGS84 sanity check)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isValidWgs84Bbox(fitBoundsTarget)) return;
    const [w, s, e, n] = fitBoundsTarget;
    map.fitBounds(
      [
        [w, s],
        [e, n],
      ],
      { padding: 36, duration: 550, maxZoom: 15 }
    );
  }, [fitBoundsSeq]);

  // Sync OpenGIS layers into MapLibre style with explicit Z-order and preserved system overlays
  const syncMapLayers = () => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    const currentLayers = useStudioStore.getState().layers;
    const activeIds = new Set(currentLayers.map((l) => l.id));

    for (const styleLyr of map.getStyle().layers || []) {
      if (!styleLyr.id.startsWith("ogis-")) continue;
      if (SYSTEM_PREFIXES.some((prefix) => styleLyr.id.startsWith(prefix))) continue;
      const lid = extractBusinessLayerId(styleLyr.id);
      if (!activeIds.has(lid) && map.getLayer(styleLyr.id)) {
        map.removeLayer(styleLyr.id);
      }
    }

    const drawOrderIds: string[] = [];
    const ordered = [...currentLayers].reverse(); // bottom layer first, top layer last
    for (const lyr of ordered) {
      const srcId = `ogis-${lyr.id}`;
      const vis = lyr.visible ? "visible" : "none";
      if (lyr.kind === "vector" && lyr.geojson) {
        const existingSrc = map.getSource(srcId) as maplibregl.GeoJSONSource | undefined;
        if (!existingSrc) {
          map.addSource(srcId, { type: "geojson", data: lyr.geojson as any });
        } else {
          existingSrc.setData(lyr.geojson as any);
        }
        const fillId = `ogis-${lyr.id}-fill`;
        const lineId = `ogis-${lyr.id}-line`;
        const ptId = `ogis-${lyr.id}-pt`;
        const fillColor = rampFillExpression(lyr);
        if (!map.getLayer(fillId)) {
          map.addLayer({
            id: fillId,
            type: "fill",
            source: srcId,
            filter: ["in", ["geometry-type"], ["literal", ["Polygon", "MultiPolygon"]]],
            layout: { visibility: vis },
            paint: { "fill-color": fillColor, "fill-opacity": lyr.opacity * 0.55 },
          });
        } else {
          map.setLayoutProperty(fillId, "visibility", vis);
          map.setPaintProperty(fillId, "fill-color", fillColor);
          map.setPaintProperty(fillId, "fill-opacity", lyr.opacity * 0.55);
        }
        if (!map.getLayer(lineId)) {
          map.addLayer({
            id: lineId,
            type: "line",
            source: srcId,
            layout: { visibility: vis },
            paint: { "line-color": lyr.color, "line-width": 1.6, "line-opacity": lyr.opacity },
          });
        } else {
          map.setLayoutProperty(lineId, "visibility", vis);
          map.setPaintProperty(lineId, "line-color", lyr.color);
          map.setPaintProperty(lineId, "line-opacity", lyr.opacity);
        }
        if (!map.getLayer(ptId)) {
          map.addLayer({
            id: ptId,
            type: "circle",
            source: srcId,
            filter: ["in", ["geometry-type"], ["literal", ["Point", "MultiPoint"]]],
            layout: { visibility: vis },
            paint: {
              "circle-color": fillColor,
              "circle-radius": 5,
              "circle-stroke-width": 1.2,
              "circle-stroke-color": "#ffffff",
              "circle-opacity": lyr.opacity,
            },
          });
        } else {
          map.setLayoutProperty(ptId, "visibility", vis);
          map.setPaintProperty(ptId, "circle-color", fillColor);
          map.setPaintProperty(ptId, "circle-opacity", lyr.opacity);
        }
        drawOrderIds.push(fillId, lineId, ptId);
      } else if (lyr.kind === "raster" && lyr.rasterUrl && isValidWgs84Bbox(lyr.rasterBounds)) {
        const [w, s, e, n] = lyr.rasterBounds;
        const coords: [[number, number], [number, number], [number, number], [number, number]] = [
          [w, n],
          [e, n],
          [e, s],
          [w, s],
        ];
        const rId = `ogis-${lyr.id}-raster`;
        const existing = map.getSource(srcId) as maplibregl.ImageSource | undefined;
        if (!existing) {
          map.addSource(srcId, { type: "image", url: lyr.rasterUrl, coordinates: coords });
        } else {
          existing.updateImage({ url: lyr.rasterUrl, coordinates: coords });
        }
        if (!map.getLayer(rId)) {
          map.addLayer({
            id: rId,
            type: "raster",
            source: srcId,
            layout: { visibility: vis },
            paint: { "raster-opacity": lyr.opacity, "raster-fade-duration": 0 },
          });
        } else {
          map.setLayoutProperty(rId, "visibility", vis);
          map.setPaintProperty(rId, "raster-opacity", lyr.opacity);
        }
        drawOrderIds.push(rId);
      }
    }

    const state = useStudioStore.getState();

    // Attribute / click highlight overlay
    const hlSrcId = "ogis-highlight";
    const hlFeature = state.highlightedFeature?.feature;
    const hlData: GeoJsonFeatureCollection = hlFeature
      ? { type: "FeatureCollection", features: [hlFeature as any] }
      : { type: "FeatureCollection", features: [] };
    const existingHl = map.getSource(hlSrcId) as maplibregl.GeoJSONSource | undefined;
    if (!existingHl) {
      map.addSource(hlSrcId, { type: "geojson", data: hlData });
    } else {
      existingHl.setData(hlData);
    }
    if (!map.getLayer("ogis-highlight-fill")) {
      map.addLayer({
        id: "ogis-highlight-fill",
        type: "fill",
        source: hlSrcId,
        filter: ["in", ["geometry-type"], ["literal", ["Polygon", "MultiPolygon"]]],
        paint: { "fill-color": "#f59e0b", "fill-opacity": 0.34 },
      });
    }
    if (!map.getLayer("ogis-highlight-line")) {
      map.addLayer({
        id: "ogis-highlight-line",
        type: "line",
        source: hlSrcId,
        paint: { "line-color": "#fbbf24", "line-width": 3.5, "line-opacity": 0.98 },
      });
    }
    if (!map.getLayer("ogis-highlight-pt")) {
      map.addLayer({
        id: "ogis-highlight-pt",
        type: "circle",
        source: hlSrcId,
        filter: ["in", ["geometry-type"], ["literal", ["Point", "MultiPoint"]]],
        paint: {
          "circle-color": "#f59e0b",
          "circle-radius": 8,
          "circle-stroke-width": 2.5,
          "circle-stroke-color": "#ffffff",
        },
      });
    }

    // Drawn AOI preview overlay
    const aoiSrcId = "ogis-user-aoi";
    const aoiGeom =
      state.drawnGeometryGeojson ||
      (state.drawnBboxWgs84
        ? {
            type: "Polygon",
            coordinates: [
              [
                [state.drawnBboxWgs84[0], state.drawnBboxWgs84[1]],
                [state.drawnBboxWgs84[2], state.drawnBboxWgs84[1]],
                [state.drawnBboxWgs84[2], state.drawnBboxWgs84[3]],
                [state.drawnBboxWgs84[0], state.drawnBboxWgs84[3]],
                [state.drawnBboxWgs84[0], state.drawnBboxWgs84[1]],
              ],
            ],
          }
        : null);
    const aoiData: GeoJsonFeatureCollection = aoiGeom
      ? { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: aoiGeom as any }] }
      : { type: "FeatureCollection", features: [] };
    const existingAoi = map.getSource(aoiSrcId) as maplibregl.GeoJSONSource | undefined;
    if (!existingAoi) {
      map.addSource(aoiSrcId, { type: "geojson", data: aoiData });
    } else {
      existingAoi.setData(aoiData);
    }
    if (!map.getLayer("ogis-user-aoi-fill")) {
      map.addLayer({
        id: "ogis-user-aoi-fill",
        type: "fill",
        source: aoiSrcId,
        paint: { "fill-color": "#4f46e5", "fill-opacity": 0.14 },
      });
    }
    if (!map.getLayer("ogis-user-aoi-line")) {
      map.addLayer({
        id: "ogis-user-aoi-line",
        type: "line",
        source: aoiSrcId,
        paint: { "line-color": "#4f46e5", "line-width": 2, "line-dasharray": [2, 2] },
      });
    }

    // Reorder MapLibre rendering stack bottom -> top -> highlight -> user AOI
    const stackOrder = [
      ...drawOrderIds,
      "ogis-highlight-fill",
      "ogis-highlight-line",
      "ogis-highlight-pt",
      "ogis-user-aoi-fill",
      "ogis-user-aoi-line",
    ];
    for (const styleLayerId of stackOrder) {
      if (map.getLayer(styleLayerId)) {
        map.moveLayer(styleLayerId);
      }
    }
  };

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (map.isStyleLoaded()) {
      syncMapLayers();
    } else {
      const onStyle = () => syncMapLayers();
      map.once("style.load", onStyle);
      return () => {
        map.off("style.load", onStyle);
      };
    }
  }, [layers, basemap, fitBoundsSeq, highlightedFeature, drawnBboxWgs84, drawnGeometryGeojson]);

  // Viewport-adaptive debounced reload for truncated large vector layers
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const triggerReload = () => {
      if (viewportTimerRef.current !== null) {
        window.clearTimeout(viewportTimerRef.current);
      }
      viewportTimerRef.current = window.setTimeout(() => {
        const currentMap = mapRef.current;
        if (!currentMap) return;
        const activeLayers = useStudioStore.getState().layers;
        const truncatedVisible = activeLayers.filter(
          (l) => l.kind === "vector" && l.visible && l.truncated && !l.loading
        );
        if (!truncatedVisible.length) return;

        const b = currentMap.getBounds();
        const zoom = currentMap.getZoom();
        const viewBbox: [number, number, number, number] = [
          Math.max(-180, b.getWest()),
          Math.max(-90, b.getSouth()),
          Math.min(180, b.getEast()),
          Math.min(90, b.getNorth()),
        ];

        for (const lyr of truncatedVisible) {
          const prev = lastViewportRef.current.get(lyr.id);
          if (prev) {
            const zoomDiff = Math.abs(zoom - prev.zoom);
            const insidePrev =
              viewBbox[0] >= prev.bbox[0] &&
              viewBbox[1] >= prev.bbox[1] &&
              viewBbox[2] <= prev.bbox[2] &&
              viewBbox[3] <= prev.bbox[3];
            if (zoomDiff < 0.35 && insidePrev) {
              continue;
            }
          }
          const dx = Math.max((viewBbox[2] - viewBbox[0]) * 0.15, 0.002);
          const dy = Math.max((viewBbox[3] - viewBbox[1]) * 0.15, 0.002);
          const padded: [number, number, number, number] = [
            Number(Math.max(-180, viewBbox[0] - dx).toFixed(6)),
            Number(Math.max(-90, viewBbox[1] - dy).toFixed(6)),
            Number(Math.min(180, viewBbox[2] + dx).toFixed(6)),
            Number(Math.min(90, viewBbox[3] + dy).toFixed(6)),
          ];

          viewportControllersRef.current.get(lyr.id)?.abort();
          const ctrl = new AbortController();
          viewportControllersRef.current.set(lyr.id, ctrl);
          lastViewportRef.current.set(lyr.id, { bbox: padded, zoom });
          void refreshLayerViewport(lyr.id, padded, zoom, ctrl.signal);
        }
      }, 300);
    };

    map.on("moveend", triggerReload);
    return () => {
      map.off("moveend", triggerReload);
    };
  }, [refreshLayerViewport]);

  // Interactive mouse tool handlers
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (mapTool === "bbox") {
      map.dragPan.disable();
    } else {
      map.dragPan.enable();
    }

    const onClick = async (e: maplibregl.MapMouseEvent) => {
      const { lng, lat } = e.lngLat;
      if (mapTool === "identify") {
        const visLayers = layers.filter((l) => l.visible).map((l) => ({ path: l.path, type: l.kind }));
        if (!visLayers.length) {
          setToast("请先开启至少一个可见图层");
          return;
        }
        try {
          const res = await api.identify({ lon: lng, lat, zoom: map.getZoom(), layers: visLayers });
          setIdentifyPopup(res);
        } catch (err: any) {
          setToast(err?.message || "Identify 查询失败");
        }
      } else if (mapTool === "select_fid") {
        const feats = map
          .queryRenderedFeatures(e.point)
          .filter((f) => f.layer.id.startsWith("ogis-") && !SYSTEM_PREFIXES.some((p) => f.layer.id.startsWith(p)));
        const hit = feats[0];
        const fid = hit?.properties?._fid;
        if (typeof fid === "number") {
          setSelectedFids(selectedFids.includes(fid) ? selectedFids.filter((x) => x !== fid) : [...selectedFids, fid]);
          const lid = extractBusinessLayerId(hit.layer.id);
          const ownerLayer = layers.find((l) => l.id === lid);
          if (ownerLayer) {
            void highlightAttributeRow(ownerLayer.path, fid, null);
          }
        }
      } else if (mapTool === "polygon") {
        setPolyVerts((prev) => [...prev, [Number(lng.toFixed(6)), Number(lat.toFixed(6))]]);
      }
    };

    const onMouseDown = (e: maplibregl.MapMouseEvent) => {
      if (mapTool !== "bbox") return;
      bboxStartRef.current = [e.point.x, e.point.y];
      setBboxRect([e.point.x, e.point.y, e.point.x, e.point.y]);
    };

    const onMouseMove = (e: maplibregl.MapMouseEvent) => {
      if (mapTool !== "bbox" || !bboxStartRef.current) return;
      const [sx, sy] = bboxStartRef.current;
      setBboxRect([sx, sy, e.point.x, e.point.y]);
    };

    const onMouseUp = (e: maplibregl.MapMouseEvent) => {
      if (mapTool !== "bbox" || !bboxStartRef.current) return;
      const [sx, sy] = bboxStartRef.current;
      bboxStartRef.current = null;
      setBboxRect(null);
      if (Math.abs(e.point.x - sx) < 6 || Math.abs(e.point.y - sy) < 6) return;
      const sw = map.unproject([Math.min(sx, e.point.x), Math.max(sy, e.point.y)]);
      const ne = map.unproject([Math.max(sx, e.point.x), Math.min(sy, e.point.y)]);
      setDrawnAoi([
        Number(sw.lng.toFixed(6)),
        Number(sw.lat.toFixed(6)),
        Number(ne.lng.toFixed(6)),
        Number(ne.lat.toFixed(6)),
      ]);
      setMapTool("pan");
      syncMapLayers();
    };

    map.on("click", onClick);
    map.on("mousedown", onMouseDown);
    map.on("mousemove", onMouseMove);
    map.on("mouseup", onMouseUp);
    return () => {
      map.off("click", onClick);
      map.off("mousedown", onMouseDown);
      map.off("mousemove", onMouseMove);
      map.off("mouseup", onMouseUp);
      map.dragPan.enable();
    };
  }, [mapTool, layers, selectedFids]);

  // Tauri native drag-and-drop absolute file path support
  useEffect(() => {
    if (!isTauri) return;
    let unlisten: (() => void) | null = null;
    void (async () => {
      const { getCurrentWebviewWindow } = await import("@tauri-apps/api/webviewWindow");
      unlisten = await getCurrentWebviewWindow().onDragDropEvent(async (event) => {
        if (event.payload.type === "drop") {
          for (const filePath of event.payload.paths) {
            await attachAndAddLayer(filePath);
          }
        }
      });
    })();
    return () => {
      unlisten?.();
    };
  }, [isTauri]);

  // Load attributes drawer when active
  useEffect(() => {
    if (!attrLayerPath) return;
    void (async () => {
      try {
        const res = await api.getAttributes(attrLayerPath, { page: attrPage, page_size: 50, query: attrQuery || undefined });
        setAttrFields(res.fields || []);
        setAttrRows(res.rows || []);
        setAttrTotal(res.total || 0);
      } catch (err: any) {
        setToast(err?.message || "读取属性表失败");
      }
    })();
  }, [attrLayerPath, attrPage, attrQuery]);

  const finishPolygon = () => {
    if (polyVerts.length < 3) return;
    const ring = [...polyVerts, polyVerts[0]];
    const lons = ring.map((c) => c[0]);
    const lats = ring.map((c) => c[1]);
    setDrawnAoi(
      [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)],
      { type: "Polygon", coordinates: [ring] }
    );
    setPolyVerts([]);
    setMapTool("pan");
    syncMapLayers();
  };

  const spatialFiles = files.filter(
    (f) => f.is_spatial || (!f.is_dir && f.name.toLowerCase().endsWith(".csv"))
  );

  const openData = async () => {
    if (!isTauri) {
      setPickerOpen((open) => !open);
      return;
    }
    try {
      const paths = await api.pickNativeSpatialFiles();
      for (const path of paths) await attachAndAddLayer(path);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "无法打开数据文件");
    }
  };
  const showStart = layers.length === 0 && basemap === "offline" && mapTool === "pan" && !pickerOpen;

  return (
    <div className="map-workspace h-full flex flex-col relative">
      {/* Map Toolbar */}
      <div className="map-tools bg-white border-b border-slate-200 px-3 flex items-center justify-between gap-2 text-xs shrink-0">
        <div className="flex items-center gap-1">
          <select className="compact-map-tool" aria-label="地图工具" value={mapTool} onChange={(e) => {
            const tool = mapTools.find((item) => item.id === e.target.value);
            if (tool) setMapTool(tool.id);
          }}>
            {mapTools.map((tool) => <option key={tool.id} value={tool.id}>{tool.label}</option>)}
          </select>
          {mapTools.map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.id}
                title={t.label} aria-label={t.label} aria-pressed={mapTool === t.id}
                onClick={() => setMapTool(t.id)}
                className={`px-2 py-1 rounded flex items-center gap-1 transition cursor-pointer ${
                  mapTool === t.id ? "bg-sky-50 text-sky-800 ring-1 ring-sky-200" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{t.label}</span>
              </button>
            );
          })}
          {mapTool === "polygon" && polyVerts.length >= 3 && (
            <button onClick={finishPolygon} className="ml-1 px-2 py-1 rounded bg-indigo-600 text-white flex items-center gap-1 cursor-pointer">
              <Check className="w-3.5 h-3.5" /> 完成绘区 ({polyVerts.length})
            </button>
          )}
        </div>

        <div className="flex items-center gap-2">
          <select
            aria-label="底图" value={basemap}
            onChange={(e) => setBasemap(e.target.value as BasemapKind)}
            className="border border-slate-300 rounded px-2 py-1 text-xs bg-white"
          >
            <option value="offline">离线底图</option>
            <option value="positron">浅色 Carto 底图</option>
            <option value="dark">深色 Carto 底图</option>
            <option value="osm">OpenStreetMap</option>
          </select>

          <button
            onClick={openData}
            className="load-data-button"
          >
            <FolderPlus className="w-3.5 h-3.5" /> 加载数据
          </button>
        </div>
      </div>

      <div className="flex-1 relative min-h-0">
        <div data-north={env?.preferences?.north_style} data-scale={env?.preferences?.scale_style} ref={containerRef} className={`w-full h-full ${mapTool !== "pan" ? "cursor-crosshair" : ""}`} />

        {showStart && (
          <div className="map-start">
            <div className="map-start-content">
              <div className="map-mark"><MapIcon size={36} strokeWidth={1.4}/></div>
              <h1>加载第一个图层</h1>
              <p>{isTauri ? "选择空间数据文件，或将文件拖到地图上。" : "从工作目录选择矢量或栅格数据，在地图上查看。"}</p>
              <button onClick={openData}><FolderPlus size={17}/>{isTauri ? "选择空间数据" : "从工作目录加载"}</button>
            </div>
          </div>
        )}

        {/* BBox visual overlay */}
        {bboxRect && (
          <div
            style={{
              left: Math.min(bboxRect[0], bboxRect[2]),
              top: Math.min(bboxRect[1], bboxRect[3]),
              width: Math.abs(bboxRect[2] - bboxRect[0]),
              height: Math.abs(bboxRect[3] - bboxRect[1]),
            }}
            className="absolute border-2 border-indigo-600 bg-indigo-500/15 pointer-events-none z-10"
          />
        )}

        {/* Floating Layer Manager */}
        <div className={`absolute top-3 left-3 z-10 ${layers.length && !layersCollapsed ? "w-72" : "w-auto"} max-h-[72%] bg-white/95 backdrop-blur rounded-xl shadow-lg border border-slate-200 flex flex-col overflow-hidden text-xs`}>
          <div className="px-3 py-2 bg-slate-50 border-b border-slate-200 flex items-center justify-between gap-1 font-semibold text-slate-700">
            <button disabled={!layers.length} aria-expanded={layers.length > 0 && !layersCollapsed} onClick={() => setLayersCollapsed(!layersCollapsed)} className="flex items-center gap-1.5 cursor-pointer">
              <Layers className="w-3.5 h-3.5 text-sky-600" /> 图层 {layers.length} {layers.length > 0 && <ChevronDown size={13} className={layersCollapsed ? "-rotate-90" : ""}/>}
            </button>
            {layers.length > 0 && !layersCollapsed && (
              <div className="flex items-center gap-1">
                <button
                  onClick={focusResultLayers}
                  title="聚焦当前成果范围"
                  className="p-1 rounded hover:bg-slate-200/70 text-slate-600 cursor-pointer"
                >
                  <Focus className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={resetLayerOrder}
                  title="按制图规范重排图层 (点 > 线 > 面 > 栅格)"
                  className={`p-1 rounded hover:bg-slate-200/70 cursor-pointer ${orderPinned ? "text-amber-600 bg-amber-50" : "text-slate-600"}`}
                >
                  <ArrowUpDown className="w-3.5 h-3.5" />
                </button>
                {spatialFiles.length > 0 && (
                  <button onClick={() => setPickerOpen((v) => !v)} className="text-[11px] font-normal text-sky-600 hover:underline cursor-pointer pl-1">
                    工作区数据 ({spatialFiles.length})
                  </button>
                )}
              </div>
            )}
          </div>

          {layers.length > 0 && !layersCollapsed && (
            <div className="overflow-y-auto p-2 space-y-2.5">
              {ROLE_SECTIONS.map(({ role, title }) => {
                const groupLayers = layers.filter((l) => l.role === role);
                if (!groupLayers.length) return null;
                const isOpen = groupOpen[role];
                return (
                  <div key={role} className="space-y-1.5">
                    <button
                      onClick={() => setGroupOpen((prev) => ({ ...prev, [role]: !prev[role] }))}
                      className="w-full flex items-center justify-between px-1 py-0.5 text-[11px] font-semibold text-slate-500 hover:text-slate-800 cursor-pointer"
                    >
                      <span>{title} ({groupLayers.length})</span>
                      <ChevronDown size={12} className={`transition ${isOpen ? "" : "-rotate-90"}`} />
                    </button>
                    {isOpen && groupLayers.map((lyr) => {
                      const idx = layers.findIndex((x) => x.id === lyr.id);
                      const validBounds = isValidWgs84Bbox(lyr.fullBboxWgs84 || lyr.bboxWgs84);
                      const isSolo = soloLayerId === lyr.id;
                      return (
                        <div key={lyr.id} className="p-2 rounded-lg border border-slate-200 bg-white space-y-1.5">
                          <div className="flex items-center justify-between gap-1">
                            <button onClick={() => toggleLayerVisible(lyr.id)} className="flex items-center gap-1.5 min-w-0 font-medium text-slate-800 cursor-pointer">
                              {lyr.visible ? <Eye className="w-3.5 h-3.5 text-sky-600 shrink-0" /> : <EyeOff className="w-3.5 h-3.5 text-slate-400 shrink-0" />}
                              <span className="truncate" title={lyr.path}>{lyr.name}</span>
                            </button>
                            <div className="flex items-center gap-0.5 shrink-0 text-slate-400">
                              <button
                                onClick={() => toggleLayerSolo(lyr.id)}
                                title={isSolo ? "退出独显" : "独显此图层"}
                                className={`px-1 rounded text-[10px] font-semibold cursor-pointer ${isSolo ? "bg-amber-500 text-white" : "hover:bg-slate-100 hover:text-slate-700"}`}
                              >
                                S
                              </button>
                              <button
                                disabled={!validBounds}
                                onClick={() => zoomToLayer(lyr.fullBboxWgs84 || lyr.bboxWgs84)}
                                title={validBounds ? "缩放到图层" : "无有效 WGS84 范围"}
                                className="p-0.5 hover:text-slate-700 disabled:opacity-30 cursor-pointer"
                              >
                                <Maximize2 className="w-3 h-3" />
                              </button>
                              {lyr.kind === "vector" && (
                                <button onClick={() => setAttrLayerPath(lyr.path)} title="查看属性表" className="p-0.5 hover:text-slate-700 cursor-pointer">
                                  <Table2 className="w-3 h-3" />
                                </button>
                              )}
                              {idx > 0 && (
                                <button onClick={() => moveLayer(lyr.id, -1)} title="上移一层" className="p-0.5 hover:text-slate-700 cursor-pointer">
                                  <ArrowUp className="w-3 h-3" />
                                </button>
                              )}
                              {idx < layers.length - 1 && (
                                <button onClick={() => moveLayer(lyr.id, 1)} title="下移一层" className="p-0.5 hover:text-slate-700 cursor-pointer">
                                  <ArrowDown className="w-3 h-3" />
                                </button>
                              )}
                              <button onClick={() => removeLayer(lyr.id)} title="移除图层" className="p-0.5 hover:text-rose-600 cursor-pointer">
                                <Trash2 className="w-3 h-3" />
                              </button>
                            </div>
                          </div>

                          <div className="flex items-center gap-2 text-[11px] text-slate-500">
                            <span>透明</span>
                            <input
                              type="range"
                              min={0.1}
                              max={1}
                              step={0.05}
                              value={lyr.opacity}
                              onChange={(e) => setLayerOpacity(lyr.id, Number(e.target.value))}
                              className="flex-1 accent-sky-600"
                            />
                            <button
                              onClick={() => toggleLayerSelectedForContext(lyr.path)}
                              className={`px-1.5 py-0.5 rounded border text-[10px] cursor-pointer ${
                                selectedLayerPaths.includes(lyr.path) ? "bg-sky-600 text-white border-sky-600" : "border-slate-300 text-slate-600"
                              }`}
                            >
                              {selectedLayerPaths.includes(lyr.path) ? "已绑定" : "引用"}
                            </button>
                          </div>

                          {lyr.kind === "vector" && lyr.fields.length > 0 && (
                            <select
                              value={lyr.styleField || ""}
                              onChange={(e) => void styleVectorLayerByField(lyr.id, e.target.value || null)}
                              className="w-full border border-slate-200 rounded px-1.5 py-0.5 text-[11px] bg-slate-50"
                            >
                              <option value="">单色填充 ({lyr.totalFeatures ?? "?"} 要素)</option>
                              {lyr.fields.slice(0, 12).map((f) => (
                                <option key={f} value={f}>按 {f} 分级设色</option>
                              ))}
                            </select>
                          )}

                          {lyr.kind === "raster" && (
                            <div className="flex gap-1">
                              <select
                                value={lyr.band}
                                onChange={(e) => updateRasterStyle(lyr.id, Number(e.target.value), lyr.colormap)}
                                className="flex-1 border border-slate-200 rounded px-1 py-0.5 text-[11px] bg-slate-50"
                              >
                                {lyr.bandCount >= 3 && <option value={0}>RGB 合成</option>}
                                {Array.from({ length: lyr.bandCount }, (_, i) => i + 1).map((b) => (
                                  <option key={b} value={b}>波段 {b}</option>
                                ))}
                              </select>
                              <select
                                value={lyr.colormap}
                                onChange={(e) => updateRasterStyle(lyr.id, lyr.band, e.target.value)}
                                className="flex-1 border border-slate-200 rounded px-1 py-0.5 text-[11px] bg-slate-50"
                              >
                                <option value="viridis">Viridis</option>
                                <option value="terrain">Terrain</option>
                                <option value="RdYlBu">RdYlBu</option>
                                <option value="magma">Magma</option>
                                <option value="cividis">Cividis</option>
                              </select>
                            </div>
                          )}

                          {Boolean(lyr.warnings?.length) && (
                            <div className="flex flex-wrap gap-1">
                              {lyr.warnings!.map((w) => (
                                <span key={w} className="inline-flex items-center gap-0.5 text-[10px] text-rose-700 bg-rose-50 border border-rose-200 px-1.5 py-0.5 rounded">
                                  <AlertTriangle className="w-2.5 h-2.5" />
                                  {WARNING_LABELS[w] || w}
                                </span>
                              ))}
                            </div>
                          )}

                          {(lyr.viewportLoading || lyr.truncated) && (
                            <div className="text-[10px] text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded">
                              {lyr.viewportLoading
                                ? "正在加载当前视口细节…"
                                : lyr.viewportReturned !== undefined
                                ? `当前视口 ${lyr.viewportReturned} / 共 ${lyr.totalFeatures ?? "?"} 要素（缩放自动细化）`
                                : "要素较多，缩放平移将按视口自动细化"}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Active selection / highlight / AOI floating clear bar */}
        {(drawnBboxWgs84 || drawnGeometryGeojson || selectedFids.length > 0 || (highlightedFeature && !attrLayerPath)) && (
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 bg-white/95 backdrop-blur border border-slate-300 text-slate-800 rounded-full px-3 py-1 shadow-md flex items-center gap-2.5 text-xs">
            {(drawnBboxWgs84 || drawnGeometryGeojson) && (
              <span className="text-indigo-700 font-medium">已框选范围</span>
            )}
            {selectedFids.length > 0 && (
              <span className="text-sky-700 font-medium">已选 {selectedFids.length} 个要素</span>
            )}
            {highlightedFeature && !attrLayerPath && (
              <span className="text-amber-700 font-medium">
                高亮：{formatLayerDisplayName(highlightedFeature.path)} #{highlightedFeature.fid}
              </span>
            )}
            <button
              onClick={() => {
                setDrawnAoi(null, null);
                setSelectedFids([]);
                clearHighlight();
              }}
              className="px-2 py-0.5 rounded-full bg-slate-100 hover:bg-rose-50 hover:text-rose-700 text-slate-700 font-medium cursor-pointer"
            >
              清除框选
            </button>
          </div>
        )}

        {/* Multi-layer container (.gpkg) picker popover */}
        {pendingContainer && (
          <div className="absolute top-3 right-3 z-30 w-80 max-w-[calc(100%-1.5rem)] bg-white rounded-xl shadow-xl border border-slate-200 p-3 text-xs space-y-2 max-h-80 overflow-y-auto">
            <div className="flex items-center justify-between font-semibold text-slate-800">
              <span className="truncate">选择容器子图层：{pendingContainer.name}</span>
              <button onClick={() => setPendingContainer(null)} className="cursor-pointer text-slate-400 hover:text-slate-700">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <p className="text-[11px] text-slate-500">已自动加载前 2 个图层，可按需追加其余 {pendingContainer.layers.length - 2} 个子图层：</p>
            <div className="space-y-1">
              {pendingContainer.layers.map((sub) => (
                <button
                  key={sub.source}
                  onClick={() => void addLayerByPath(sub.source, "vector", { role: pendingContainer.role })}
                  className="w-full text-left px-2 py-1.5 rounded border border-slate-100 hover:bg-sky-50 flex items-center justify-between gap-2 cursor-pointer"
                >
                  <span className="truncate font-medium text-slate-700">{sub.name}</span>
                  <span className="text-[10px] text-slate-400 shrink-0">
                    {sub.geometry_type || "vector"} · {sub.feature_count ?? "?"}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Workspace quick file picker dropdown */}
        {pickerOpen && (
          <div className="absolute top-3 right-3 z-20 w-72 max-w-[calc(100%-1.5rem)] bg-white rounded-xl shadow-xl border border-slate-200 p-3 text-xs space-y-2 max-h-72 overflow-y-auto">
            <div className="flex items-center justify-between font-semibold">
              <span>工作区原始数据叠加对照</span>
              <button onClick={() => setPickerOpen(false)} className="cursor-pointer"><X className="w-3.5 h-3.5" /></button>
            </div>
            {spatialFiles.length === 0 && <div className="space-y-3 p-2">
              <p className="text-sm text-slate-600">当前目录没有可加载的空间数据。</p>
              <button className="text-sky-700 font-medium" onClick={() => { setPickerOpen(false); onSwitchFolder(); }}>切换工作目录</button>
            </div>}
            {spatialFiles.map((f) => (
              <button
                key={f.path}
                onClick={() => {
                  void addLayerByPath(f.path, f.kind === "raster" ? "raster" : "vector", { role: "input" });
                  setPickerOpen(false);
                }}
                className="w-full text-left px-2 py-1.5 rounded hover:bg-sky-50 flex items-center justify-between cursor-pointer"
              >
                <span className="truncate">{f.rel_path}</span>
                <span className="text-[10px] uppercase text-slate-400">{f.kind}</span>
              </button>
            ))}
          </div>
        )}

        {/* Identify Popup */}
        {identifyPopup && (
          <div className="absolute bottom-4 right-4 z-20 w-80 max-h-80 bg-white rounded-xl shadow-2xl border border-slate-200 flex flex-col overflow-hidden text-xs">
            <div className="px-3 py-2 bg-emerald-50 text-emerald-950 border-b border-emerald-100 flex items-center justify-between">
              <span className="font-mono">
                Identify ({identifyPopup.lon.toFixed(4)}, {identifyPopup.lat.toFixed(4)})
              </span>
              <button onClick={() => setIdentifyPopup(null)} className="cursor-pointer"><X className="w-3.5 h-3.5" /></button>
            </div>
            <div className="p-2.5 overflow-y-auto space-y-2.5">
              {identifyPopup.results.map((r, i) => (
                <div key={i} className="border border-slate-200 rounded-lg p-2 space-y-1">
                  <div className="font-semibold text-slate-700 truncate">{r.path.split(/[\\/]/).pop()}</div>
                  {r.type === "vector" && (!r.hits || r.hits.length === 0) && <div className="text-slate-400">未命中矢量要素</div>}
                  {r.hits?.map((h) => (
                    <div key={h.fid} className="bg-slate-50 rounded p-1.5 text-[11px] space-y-0.5">
                      <div className="font-mono text-sky-700">FID #{h.fid}</div>
                      {Object.entries(h.properties).slice(0, 8).map(([k, v]) => (
                        <div key={k} className="flex justify-between gap-2">
                          <span className="text-slate-500">{k}</span>
                          <span className="font-mono text-slate-800 truncate">{String(v)}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                  {r.type === "raster" && r.bands?.map((b) => (
                    <div key={b.band} className="flex justify-between text-[11px] bg-slate-50 px-2 py-1 rounded">
                      <span>波段 {b.band}</span>
                      <span className="font-mono font-medium">
                        {b.is_nodata ? "NoData" : `${b.physical_value} ${b.unit || ""}`}
                      </span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
            <div className="px-2.5 py-2 border-t border-slate-200 bg-slate-50 flex justify-end">
              <button
                onClick={() => {
                  setClickedPoint([Number(identifyPopup.lon.toFixed(6)), Number(identifyPopup.lat.toFixed(6))]);
                  setIdentifyPopup(null);
                }}
                className="px-2.5 py-1 rounded bg-sky-600 text-white text-[11px] hover:bg-sky-500 cursor-pointer"
              >
                将此点位加入对话上下文
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Collapsible Attribute Table Drawer */}
      {attrLayerPath && (
        <div className="h-56 border-t border-slate-300 bg-white flex flex-col shrink-0 text-xs">
          <div className="px-3 py-1.5 bg-slate-50 border-b border-slate-200 flex items-center justify-between gap-2">
            <span className="font-semibold text-slate-700 truncate">
              属性表：{formatLayerDisplayName(attrLayerPath)}（共 {attrTotal} 条）
            </span>
            <div className="flex items-center gap-2">
              {highlightedFeature && (
                <button
                  onClick={clearHighlight}
                  className="px-2 py-0.5 rounded bg-amber-100 text-amber-800 hover:bg-amber-200 cursor-pointer"
                >
                  清除高亮 (#{highlightedFeature.fid})
                </button>
              )}
              <input
                value={attrQuery}
                onChange={(e) => {
                  setAttrQuery(e.target.value);
                  setAttrPage(1);
                }}
                placeholder="筛选关键字..."
                className="border border-slate-300 rounded px-2 py-0.5 text-xs"
              />
              <button onClick={() => setAttrLayerPath(null)} className="text-slate-500 hover:text-slate-900 cursor-pointer">
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-auto">
            <table className="w-full text-left border-collapse text-[11px]">
              <thead className="sticky top-0 bg-slate-100 border-b border-slate-200">
                <tr>
                  <th className="px-2 py-1 font-mono">_fid</th>
                  {attrFields.map((f) => (
                    <th key={f} className="px-2 py-1 whitespace-nowrap">{f}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {attrRows.map((row) => {
                  const isHl = highlightedFeature?.fid === row._fid && highlightedFeature?.path === attrLayerPath;
                  return (
                    <tr
                      key={row._fid}
                      onClick={() => void highlightAttributeRow(attrLayerPath, row._fid, row._bbox_wgs84)}
                      className={`cursor-pointer ${isHl ? "bg-amber-100/80" : "hover:bg-sky-50"}`}
                    >
                      <td className="px-2 py-1 font-mono text-sky-700">{row._fid}</td>
                      {attrFields.map((f) => (
                        <td key={f} className="px-2 py-1 max-w-[180px] truncate">{String(row[f] ?? "")}</td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
