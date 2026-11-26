import type { LayerItem, LayerRole } from "../types/studio";

export function normalizeLayerPath(raw: string): string {
  const [filePart, layerPart] = raw.split("|layername=", 2);
  const cleanPath = filePart.replace(/\\/g, "/").replace(/\/+/g, "/");
  const isWindows = /^[a-zA-Z]:/.test(cleanPath);
  const normFile = isWindows ? cleanPath.toLowerCase() : cleanPath;
  if (layerPart !== undefined) {
    return `${normFile}|layername=${layerPart.split("|", 1)[0]}`;
  }
  return normFile;
}

export function formatLayerDisplayName(raw: string): string {
  const [filePart, layerPart] = raw.split("|layername=", 2);
  const baseName = filePart.split(/[\\/]/).pop() || filePart;
  if (layerPart) {
    const sub = layerPart.split("|", 1)[0];
    return `${baseName} :: ${sub}`;
  }
  return baseName;
}

export function isValidWgs84Bbox(bbox: unknown): bbox is [number, number, number, number] {
  if (!Array.isArray(bbox) || bbox.length !== 4) return false;
  const nums = bbox.map(Number);
  if (!nums.every(Number.isFinite)) return false;
  const [w, s, e, n] = nums;
  if (w === 0 && s === 0 && e === 0 && n === 0) return false;
  return w >= -180.5 && e <= 180.5 && s >= -90.5 && n <= 90.5 && e >= w && n >= s;
}

export function geometryTier(layer: Pick<LayerItem, "kind" | "geometryType">): number {
  if (layer.kind === "raster") return 4;
  const gt = (layer.geometryType || "").toLowerCase();
  if (gt.includes("point")) return 0;
  if (gt.includes("line")) return 1;
  if (gt.includes("polygon")) return 3;
  return 2;
}

export function roleTier(role: LayerRole): number {
  if (role === "result") return 0;
  if (role === "intermediate") return 1;
  return 2;
}

export function bboxArea(bbox: [number, number, number, number] | null | undefined): number {
  if (!isValidWgs84Bbox(bbox)) return Number.POSITIVE_INFINITY;
  const [w, s, e, n] = bbox;
  return Math.max(0, e - w) * Math.max(0, n - s);
}

/** Sort layers top-to-bottom for panel display & draw stack: Point > Line > Small Polygon > Large Polygon > Raster. */
export function sortLayersByCartography(layers: LayerItem[]): LayerItem[] {
  return [...layers]
    .map((layer, idx) => ({ layer, idx }))
    .sort((a, b) => {
      const gtDiff = geometryTier(a.layer) - geometryTier(b.layer);
      if (gtDiff !== 0) return gtDiff;

      const rDiff = roleTier(a.layer.role) - roleTier(b.layer.role);
      if (rDiff !== 0) return rDiff;

      if (geometryTier(a.layer) === 3) {
        const areaA = bboxArea(a.layer.fullBboxWgs84 || a.layer.bboxWgs84);
        const areaB = bboxArea(b.layer.fullBboxWgs84 || b.layer.bboxWgs84);
        if (areaA !== areaB) return areaA - areaB;
      }

      return a.idx - b.idx;
    })
    .map((item) => item.layer);
}

export function computeLayersUnionBbox(layers: LayerItem[]): [number, number, number, number] | null {
  let west = Number.POSITIVE_INFINITY;
  let south = Number.POSITIVE_INFINITY;
  let east = Number.NEGATIVE_INFINITY;
  let north = Number.NEGATIVE_INFINITY;
  let found = false;

  for (const lyr of layers) {
    const b = lyr.fullBboxWgs84 || lyr.bboxWgs84;
    if (!isValidWgs84Bbox(b)) continue;
    found = true;
    west = Math.min(west, b[0]);
    south = Math.min(south, b[1]);
    east = Math.max(east, b[2]);
    north = Math.max(north, b[3]);
  }
  if (!found) return null;
  const union: [number, number, number, number] = [west, south, east, north];
  return isValidWgs84Bbox(union) ? union : null;
}
