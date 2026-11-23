import { create } from "zustand";
import { api, buildAuthedUrl, initBackendConnection, isTauriRuntime } from "../api/client";
import {
  computeLayersUnionBbox,
  formatLayerDisplayName,
  isValidWgs84Bbox,
  normalizeLayerPath,
  sortLayersByCartography,
} from "../utils/layerOrder";
import type {
  BasemapKind,
  CheckpointRequest,
  EnvInfo,
  ExecutionPolicy,
  ExecutionRow,
  FigureAnnotation,
  FigureItem,
  HighlightedFeature,
  IdentifyResult,
  LayerItem,
  LayerRole,
  MapToolMode,
  PendingContainer,
  PlanSnapshot,
  SessionSummary,
  ToolActivity,
  UsageStats,
  WorkspaceFileItem,
  WorkspaceTab,
} from "../types/studio";

const LAYER_COLORS = ["#1d4ed8", "#0d9488", "#b45309", "#7c3aed", "#dc2626", "#0369a1"];
const RAMP_PALETTES = ["#eff6ff", "#93c5fd", "#3b82f6", "#1d4ed8", "#1e3a8a"];

const layerLoadSeq = new Map<string, number>();
const pathLoadSeq = new Map<string, number>();

interface StudioState {
  ready: boolean;
  initError: string | null;
  isTauri: boolean;
  env: EnvInfo | null;
  projectDir: string;
  files: WorkspaceFileItem[];
  attachedFiles: WorkspaceFileItem[];
  sessions: SessionSummary[];
  activeSessionId: string;
  busy: boolean;
  plan: PlanSnapshot;
  waiting: CheckpointRequest | null;
  messages: any[];
  toolFeed: ToolActivity[];
  executions: ExecutionRow[];
  figures: FigureItem[];
  layers: LayerItem[];
  orderPinned: boolean;
  soloLayerId: string | null;
  soloBackupVisible: Record<string, boolean> | null;
  highlightedFeature: HighlightedFeature | null;
  pendingContainer: PendingContainer | null;
  activeTab: WorkspaceTab;
  mapTool: MapToolMode;
  basemap: BasemapKind;
  fitBoundsSeq: number;
  fitBoundsTarget: [number, number, number, number] | null;
  identifyPopup: IdentifyResult | null;
  selectedLayerPaths: string[];
  selectedFids: number[];
  drawnBboxWgs84: [number, number, number, number] | null;
  drawnGeometryGeojson: Record<string, any> | null;
  clickedPointWgs84: [number, number] | null;
  figureAnnotations: FigureAnnotation[];
  executionPolicy: ExecutionPolicy;
  usage: UsageStats;
  attrLayerPath: string | null;
  selectedExecId: string | null;
  settingsOpen: boolean;
  toast: string | null;

  bootstrap: () => Promise<void>;
  refreshWorkspace: () => Promise<void>;
  switchProject: (dir: string) => Promise<void>;
  selectSession: (sessionId: string) => Promise<void>;
  createNewSession: (name?: string) => Promise<void>;
  attachAndAddLayer: (filePath: string) => Promise<void>;
  addLayerByPath: (
    filePath: string,
    kindHint?: "vector" | "raster",
    opts?: { role?: LayerRole; sourceTool?: string; skipAutoFit?: boolean; silentTableSkip?: boolean }
  ) => Promise<void>;
  toggleLayerVisible: (id: string) => void;
  toggleLayerSolo: (id: string) => void;
  setLayerOpacity: (id: string, opacity: number) => void;
  moveLayer: (id: string, dir: -1 | 1) => void;
  resetLayerOrder: () => void;
  removeLayer: (id: string) => void;
  zoomToLayer: (bbox: [number, number, number, number] | null) => void;
  focusResultLayers: () => void;
  refreshLayerViewport: (
    id: string,
    bbox: [number, number, number, number],
    zoom: number,
    signal?: AbortSignal
  ) => Promise<void>;
  highlightAttributeRow: (
    path: string,
    fid: number,
    rowBbox?: [number, number, number, number] | null
  ) => Promise<void>;
  clearHighlight: () => void;
  setPendingContainer: (pending: PendingContainer | null) => void;
  styleVectorLayerByField: (id: string, field: string | null) => Promise<void>;
  updateRasterStyle: (id: string, band: number, colormap: string) => void;
  toggleLayerSelectedForContext: (path: string) => void;
  setActiveTab: (tab: WorkspaceTab) => void;
  setMapTool: (tool: MapToolMode) => void;
  setBasemap: (bm: BasemapKind) => void;
  setIdentifyPopup: (popup: IdentifyResult | null) => void;
  setSelectedFids: (fids: number[]) => void;
  setDrawnAoi: (bbox: [number, number, number, number] | null, geojson?: Record<string, any> | null) => void;
  setClickedPoint: (pt: [number, number] | null) => void;
  addFigureAnnotation: (ann: FigureAnnotation) => void;
  removeFigureAnnotation: (id: string) => void;
  setExecutionPolicy: (policy: ExecutionPolicy) => void;
  setAttrLayerPath: (path: string | null) => void;
  setSelectedExecId: (id: string | null) => void;
  setSettingsOpen: (open: boolean) => void;
  setToast: (msg: string | null) => void;
  sendMessage: (text: string) => Promise<void>;
  replyCheckpoint: (text: string, optionId?: string) => Promise<void>;
  stopRun: () => Promise<void>;
  cancelCheckpoint: () => Promise<void>;
  buildWorkspaceContext: () => Record<string, any>;
}

let activeEventSource: EventSource | null = null;

function openEventStream(sessionId: string) {
  if (activeEventSource) {
    activeEventSource.close();
    activeEventSource = null;
  }
  if (!sessionId) return;
  const es = new EventSource(buildAuthedUrl(`/api/sessions/${encodeURIComponent(sessionId)}/events`));
  activeEventSource = es;

  const parseMsg = (ev: MessageEvent) => {
    try {
      return JSON.parse(ev.data);
    } catch {
      return null;
    }
  };

  es.addEventListener("turn_started", () => {
    useStudioStore.setState({ busy: true, toolFeed: [] });
  });

  es.addEventListener("plan_updated", (ev) => {
    const parsed = parseMsg(ev);
    if (parsed?.payload) {
      useStudioStore.setState({ plan: parsed.payload });
    }
  });

  es.addEventListener("tool_started", (ev) => {
    const parsed = parseMsg(ev);
    if (!parsed?.payload) return;
    const { call_id, tool } = parsed.payload;
    useStudioStore.setState((s) => ({
      toolFeed: [...s.toolFeed, { id: String(call_id || Math.random()), tool: String(tool), status: "running" }],
    }));
  });

  es.addEventListener("tool_finished", (ev) => {
    const parsed = parseMsg(ev);
    if (!parsed?.payload) return;
    const { call_id, tool, ok, elapsed_ms, outputs } = parsed.payload;
    useStudioStore.setState((s) => ({
      toolFeed: s.toolFeed.map((item) =>
        item.id === String(call_id)
          ? { ...item, status: ok === false ? "error" : "ok", elapsedMs: elapsed_ms, outputs }
          : item
      ),
    }));
    const tName = String(tool || "");
    if (tName === "run_python_script" || tName === "write_file" || tName === "edit_file" || tName.startsWith("qgis_")) {
      void api
        .getExecutions(sessionId)
        .then((res) => {
          if (res.items) useStudioStore.setState({ executions: res.items });
        })
        .catch(() => {});
    }
  });

  es.addEventListener("artifact_published", (ev) => {
    const parsed = parseMsg(ev);
    const p = parsed?.payload;
    if (!p?.path) return;
    const role: LayerRole =
      p.role === "result" || p.is_finish ? "result" : p.role === "input" ? "input" : "intermediate";
    const sourceTool = typeof p.source_tool === "string" ? p.source_tool : undefined;
    if (p.kind === "vector" || p.kind === "raster") {
      void useStudioStore.getState().addLayerByPath(p.path, p.kind, { role, sourceTool });
    } else if (p.kind === "table" && role === "input" && String(p.path).toLowerCase().endsWith(".csv")) {
      void useStudioStore.getState().addLayerByPath(p.path, "vector", {
        role: "input",
        sourceTool,
        silentTableSkip: true,
      });
    } else if (p.kind === "figure") {
      void api.listFigures(sessionId).then((res) => {
        useStudioStore.setState({ figures: res.figures });
      });
    }
  });

  es.addEventListener("interaction_required", (ev) => {
    const parsed = parseMsg(ev);
    if (parsed?.payload) {
      useStudioStore.setState({ waiting: parsed.payload });
    }
  });

  es.addEventListener("usage_updated", (ev) => {
    const parsed = parseMsg(ev);
    if (parsed?.payload) {
      useStudioStore.setState({ usage: parsed.payload });
    }
  });

  es.addEventListener("session_settled", () => {
    void useStudioStore.getState().selectSession(sessionId);
    void useStudioStore.getState().refreshWorkspace();
  });

  es.addEventListener("error", (ev) => {
    if (ev instanceof MessageEvent && ev.data) {
      const parsed = parseMsg(ev);
      if (parsed?.payload?.error) {
        useStudioStore.setState({ busy: false, toast: String(parsed.payload.error) });
      }
    }
  });
}

export const useStudioStore = create<StudioState>((set, get) => ({
  ready: false,
  initError: null,
  isTauri: isTauriRuntime(),
  env: null,
  projectDir: "",
  files: [],
  attachedFiles: [],
  sessions: [],
  activeSessionId: "",
  busy: false,
  plan: { goal: "", steps: [] },
  waiting: null,
  messages: [],
  toolFeed: [],
  executions: [],
  figures: [],
  layers: [],
  orderPinned: false,
  soloLayerId: null,
  soloBackupVisible: null,
  highlightedFeature: null,
  pendingContainer: null,
  activeTab: "map",
  mapTool: "pan",
  basemap: "offline",
  fitBoundsSeq: 0,
  fitBoundsTarget: null,
  identifyPopup: null,
  selectedLayerPaths: [],
  selectedFids: [],
  drawnBboxWgs84: null,
  drawnGeometryGeojson: null,
  clickedPointWgs84: null,
  figureAnnotations: [],
  executionPolicy: "auto",
  usage: { calls: 0, prompt_tokens: 0, cached_tokens: 0, completion_tokens: 0, cache_hit_ratio: 0, estimated_cny: 0 },
  attrLayerPath: null,
  selectedExecId: null,
  settingsOpen: false,
  toast: null,

  bootstrap: async () => {
    try {
      await initBackendConnection();
      const [env, sessRes] = await Promise.all([api.getEnv(), api.listSessions()]);
      let sid = sessRes.sessions[0]?.session_id || "";
      if (!sid) {
        const created = await api.createSession();
        sid = created.session_id;
      }
      set({
        ready: true,
        initError: null,
        isTauri: isTauriRuntime(),
        env,
        projectDir: env.project_dir,
        sessions: sessRes.sessions,
        settingsOpen: !env.preferences,
        basemap: env.preferences?.basemap ?? "offline",
        executionPolicy: env.preferences?.execution_policy ?? "auto",
      });
      await get().selectSession(sid);
      await get().refreshWorkspace();
    } catch (err: any) {
      set({ ready: false, initError: err?.message || "连接后端服务失败" });
    }
  },

  refreshWorkspace: async () => {
    const sid = get().activeSessionId;
    const [filesRes, sessRes, env] = await Promise.all([
      api.listFiles(sid || undefined),
      api.listSessions(),
      api.getEnv(),
    ]);
    set({
      projectDir: filesRes.project_dir,
      files: filesRes.items,
      attachedFiles: filesRes.attached || [],
      sessions: sessRes.sessions,
      env,
    });
  },

  switchProject: async (dir: string) => {
    await api.selectWorkspace(dir);
    set({
      layers: [],
      figures: [],
      selectedLayerPaths: [],
      drawnBboxWgs84: null,
      drawnGeometryGeojson: null,
      orderPinned: false,
      soloLayerId: null,
      soloBackupVisible: null,
      highlightedFeature: null,
      pendingContainer: null,
    });
    const sessRes = await api.listSessions();
    let sid = sessRes.sessions[0]?.session_id || "";
    if (!sid) {
      sid = (await api.createSession()).session_id;
    }
    await get().selectSession(sid);
    await get().refreshWorkspace();
  },

  selectSession: async (sessionId: string) => {
    const prevSessionId = get().activeSessionId;
    const isSwitching = Boolean(prevSessionId && prevSessionId !== sessionId);
    const det = await api.getSessionDetail(sessionId);
    set({
      selectedExecId: sessionId === prevSessionId ? get().selectedExecId : null,
      activeSessionId: sessionId,
      busy: Boolean(det.busy),
      plan: det.plan || { goal: "", steps: [] },
      waiting: det.waiting || null,
      messages: det.messages || [],
      executions: det.executions || [],
      figures: det.figures || [],
      usage: det.usage || { calls: 0, prompt_tokens: 0, cached_tokens: 0, completion_tokens: 0, cache_hit_ratio: 0, estimated_cny: 0 },
      ...(isSwitching
        ? {
            layers: [],
            toolFeed: [],
            selectedLayerPaths: [],
            selectedFids: [],
            orderPinned: false,
            soloLayerId: null,
            soloBackupVisible: null,
            highlightedFeature: null,
            pendingContainer: null,
          }
        : {}),
    });
    openEventStream(sessionId);
    const sessionLayers = [...(det.layers || [])].sort((a, b) =>
      a.role === "result" && b.role !== "result" ? -1 : a.role !== "result" && b.role === "result" ? 1 : 0
    );
    for (const lyr of sessionLayers) {
      const exists = get().layers.some((x) => normalizeLayerPath(x.path) === normalizeLayerPath(lyr.path));
      if (!exists) {
        void get().addLayerByPath(lyr.path, lyr.kind, {
          role: lyr.role === "result" ? "result" : "intermediate",
        });
      }
    }
  },

  createNewSession: async (name?: string) => {
    const res = await api.createSession(name);
    set({
      layers: [],
      figures: [],
      toolFeed: [],
      selectedLayerPaths: [],
      selectedFids: [],
      figureAnnotations: [],
      orderPinned: false,
      soloLayerId: null,
      soloBackupVisible: null,
      highlightedFeature: null,
      pendingContainer: null,
    });
    await get().selectSession(res.session_id);
    await get().refreshWorkspace();
  },

  attachAndAddLayer: async (filePath: string) => {
    const att = await api.attachFile(filePath);
    await get().refreshWorkspace();
    if (att.kind === "vector" || att.kind === "raster" || filePath.toLowerCase().endsWith(".csv")) {
      await get().addLayerByPath(att.path, att.kind === "raster" ? "raster" : "vector", { role: "input" });
    } else {
      set({ toast: `已附加文件：${att.name}` });
    }
  },

  addLayerByPath: async (filePath: string, kindHint?: "vector" | "raster", opts = {}) => {
    const targetSessionId = get().activeSessionId;
    const normKey = normalizeLayerPath(filePath);
    const pSeq = (pathLoadSeq.get(normKey) || 0) + 1;
    pathLoadSeq.set(normKey, pSeq);

    try {
      const meta = await api.getLayerMeta(filePath);
      if (get().activeSessionId !== targetSessionId || pathLoadSeq.get(normKey) !== pSeq) {
        return;
      }
      if (meta.kind === "table") {
        if (!opts.silentTableSkip) {
          set({ toast: "该表格文件未检测到可用经纬度列，为纯属性表" });
        }
        return;
      }
      if (meta.kind === "container" && meta.layers?.length) {
        const containerRole: LayerRole = opts.role ?? "input";
        if (meta.layers.length <= 4) {
          for (const sub of meta.layers) {
            await get().addLayerByPath(sub.source, "vector", { ...opts, role: containerRole });
          }
        } else {
          for (const sub of meta.layers.slice(0, 2)) {
            await get().addLayerByPath(sub.source, "vector", { ...opts, role: containerRole });
          }
          set({
            pendingContainer: {
              path: filePath,
              name: formatLayerDisplayName(filePath),
              role: containerRole,
              layers: meta.layers,
            },
          });
        }
        return;
      }

      const preExisting = get().layers.find((l) => normalizeLayerPath(l.path) === normKey);
      const id = preExisting?.id || `${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
      const lSeq = (layerLoadSeq.get(id) || 0) + 1;
      layerLoadSeq.set(id, lSeq);

      const hadAnyBoundsBefore = get().layers.some((l) => isValidWgs84Bbox(l.fullBboxWgs84 || l.bboxWgs84));
      const hadResultBefore = get().layers.some((l) => l.role === "result" && l.id !== id);
      const role: LayerRole =
        preExisting?.role === "result" || opts.role === "result"
          ? "result"
          : opts.role ?? preExisting?.role ?? "input";
      const promotedToResult = Boolean(preExisting && preExisting.role !== "result" && role === "result");
      const kind: "vector" | "raster" = kindHint || (meta.kind === "raster" ? "raster" : "vector");
      const name = formatLayerDisplayName(filePath);
      const newFields: string[] = (meta.fields || []).map((f: any) => f.name || String(f));
      const preservedStyleField =
        preExisting?.styleField && (newFields.length === 0 || newFields.includes(preExisting.styleField))
          ? preExisting.styleField
          : null;
      const initialFullBbox = isValidWgs84Bbox(meta.bbox_wgs84) ? meta.bbox_wgs84 : null;

      let nextVisible = preExisting?.visible ?? true;
      if (!preExisting) {
        if (role === "intermediate") {
          nextVisible = !hadResultBefore;
        } else {
          nextVisible = true;
        }
      } else if (promotedToResult) {
        nextVisible = true;
      }

      const baseLayer: LayerItem = {
        id,
        path: filePath,
        name,
        kind,
        role,
        sourceTool: opts.sourceTool ?? preExisting?.sourceTool,
        userTouchedVisible: promotedToResult ? false : preExisting?.userTouchedVisible,
        visible: nextVisible,
        opacity:
          preExisting?.opacity ??
          (role === "input" ? (kind === "raster" ? 0.72 : 0.48) : kind === "raster" ? 0.85 : 0.78),
        color: preExisting?.color || LAYER_COLORS[get().layers.length % LAYER_COLORS.length],
        styleField: preservedStyleField,
        breaks: preservedStyleField ? preExisting?.breaks ?? [] : [],
        palette: RAMP_PALETTES,
        band: preExisting?.band ?? 1,
        bandCount: meta.bands?.length || 1,
        colormap: preExisting?.colormap ?? "viridis",
        bboxWgs84: initialFullBbox,
        fullBboxWgs84: initialFullBbox,
        fields: newFields,
        geometryType: meta.geometry_type,
        totalFeatures: meta.feature_count,
        warnings: Array.isArray(meta.warnings) ? meta.warnings : [],
        loading: true,
      };

      set((s) => {
        const autoCollapseOldIntermediate =
          role === "result" || (!preExisting && role === "intermediate" && !hadResultBefore);
        const mapped = (s.layers.some((l) => l.id === id)
          ? s.layers.map((l) => (l.id === id ? baseLayer : l))
          : [baseLayer, ...s.layers]
        ).map((l) =>
          autoCollapseOldIntermediate && l.id !== id && l.role === "intermediate" && !l.userTouchedVisible
            ? { ...l, visible: false }
            : l
        );
        return {
          layers: s.orderPinned ? mapped : sortLayersByCartography(mapped),
        };
      });

      const isStale = () =>
        get().activeSessionId !== targetSessionId ||
        layerLoadSeq.get(id) !== lSeq ||
        !get().layers.some((x) => x.id === id);

      if (kind === "vector") {
        const gj = await api.getVectorGeojson(filePath, { zoom: 9, max_features: 5000 });
        if (isStale()) return;

        const gjBbox = isValidWgs84Bbox(gj.meta?.bbox_wgs84) ? gj.meta.bbox_wgs84 : null;
        const finalFullBbox = initialFullBbox || gjBbox;
        const resolvedFields: string[] = gj.meta?.fields || newFields;
        const validStyleField =
          preservedStyleField && resolvedFields.includes(preservedStyleField) ? preservedStyleField : null;
        const mergedWarnings = Array.from(
          new Set<string>([
            ...(Array.isArray(meta.warnings) ? meta.warnings : []),
            ...(Array.isArray(gj.meta?.warnings) ? gj.meta.warnings : []),
          ])
        );
        const shouldAutoFit = Boolean(
          finalFullBbox &&
            !opts.skipAutoFit &&
            !preExisting &&
            ((role === "result" && !hadResultBefore) || !hadAnyBoundsBefore)
        );

        set((s) => {
          const updated = s.layers.map((l) =>
            l.id === id
              ? {
                  ...l,
                  geojson: gj,
                  truncated: Boolean(gj.meta?.truncated),
                  viewportReturned: Array.isArray(gj.features) ? gj.features.length : undefined,
                  viewportLoading: false,
                  bboxWgs84: finalFullBbox,
                  fullBboxWgs84: finalFullBbox,
                  geometryType: gj.meta?.geometry_type || l.geometryType,
                  totalFeatures: gj.meta?.total_features ?? l.totalFeatures,
                  fields: resolvedFields,
                  styleField: validStyleField,
                  breaks: validStyleField ? l.breaks : [],
                  warnings: mergedWarnings,
                  loading: false,
                }
              : l
          );
          return {
            layers: s.orderPinned ? updated : sortLayersByCartography(updated),
            ...(shouldAutoFit && finalFullBbox ? { fitBoundsTarget: finalFullBbox, fitBoundsSeq: s.fitBoundsSeq + 1 } : {}),
          };
        });
      } else {
        const url = buildAuthedUrl("/api/spatial/raster/preview", {
          path: filePath,
          band: baseLayer.band,
          colormap: baseLayer.colormap,
          width: 1024,
          height: 1024,
          _ts: Date.now(),
        });
        if (isStale()) return;
        const shouldAutoFit = Boolean(
          initialFullBbox &&
            !opts.skipAutoFit &&
            !preExisting &&
            ((role === "result" && !hadResultBefore) || !hadAnyBoundsBefore)
        );
        set((s) => {
          const updated = s.layers.map((l) =>
            l.id === id
              ? {
                  ...l,
                  rasterUrl: url,
                  rasterBounds: initialFullBbox || undefined,
                  loading: false,
                }
              : l
          );
          return {
            layers: s.orderPinned ? updated : sortLayersByCartography(updated),
            ...(shouldAutoFit && initialFullBbox
              ? { fitBoundsTarget: initialFullBbox, fitBoundsSeq: s.fitBoundsSeq + 1 }
              : {}),
          };
        });
      }
    } catch (err: any) {
      set({ toast: `加载图层失败 (${formatLayerDisplayName(filePath)}): ${err?.message || err}` });
    }
  },

  toggleLayerVisible: (id) =>
    set((s) => ({
      soloLayerId: null,
      soloBackupVisible: null,
      layers: s.layers.map((l) => (l.id === id ? { ...l, visible: !l.visible, userTouchedVisible: true } : l)),
    })),

  toggleLayerSolo: (id) =>
    set((s) => {
      if (s.soloLayerId === id) {
        const backup = s.soloBackupVisible || {};
        return {
          soloLayerId: null,
          soloBackupVisible: null,
          layers: s.layers.map((l) => ({
            ...l,
            visible: Object.prototype.hasOwnProperty.call(backup, l.id) ? backup[l.id] : l.visible,
          })),
        };
      }
      const backup = s.soloBackupVisible ?? Object.fromEntries(s.layers.map((l) => [l.id, l.visible]));
      return {
        soloLayerId: id,
        soloBackupVisible: backup,
        layers: s.layers.map((l) => ({ ...l, visible: l.id === id })),
      };
    }),

  setLayerOpacity: (id, opacity) =>
    set((s) => ({ layers: s.layers.map((l) => (l.id === id ? { ...l, opacity } : l)) })),

  moveLayer: (id, dir) =>
    set((s) => {
      const idx = s.layers.findIndex((l) => l.id === id);
      const next = idx + dir;
      if (idx < 0 || next < 0 || next >= s.layers.length) return {};
      const copy = [...s.layers];
      const [item] = copy.splice(idx, 1);
      copy.splice(next, 0, item);
      return { layers: copy, orderPinned: true };
    }),

  resetLayerOrder: () =>
    set((s) => ({
      orderPinned: false,
      layers: sortLayersByCartography(s.layers),
    })),

  removeLayer: (id) =>
    set((s) => {
      const removed = s.layers.find((l) => l.id === id);
      const clearH =
        removed &&
        s.highlightedFeature &&
        normalizeLayerPath(removed.path) === normalizeLayerPath(s.highlightedFeature.path);
      return {
        layers: s.layers.filter((l) => l.id !== id),
        ...(s.soloLayerId === id ? { soloLayerId: null, soloBackupVisible: null } : {}),
        ...(clearH ? { highlightedFeature: null } : {}),
      };
    }),

  zoomToLayer: (bbox) => {
    if (!isValidWgs84Bbox(bbox)) {
      set({ toast: "该图层缺少有效的 WGS84 坐标范围，无法缩放定位" });
      return;
    }
    set((s) => ({ fitBoundsTarget: bbox, fitBoundsSeq: s.fitBoundsSeq + 1, activeTab: "map" }));
  },

  focusResultLayers: () => {
    const s = get();
    const visibleResults = s.layers.filter((l) => l.visible && l.role === "result");
    const targetLayers = visibleResults.length ? visibleResults : s.layers.filter((l) => l.visible);
    const union = computeLayersUnionBbox(targetLayers.length ? targetLayers : s.layers);
    if (!union) {
      set({ toast: "当前没有具备有效地理范围的可视图层" });
      return;
    }
    set({ fitBoundsTarget: union, fitBoundsSeq: s.fitBoundsSeq + 1, activeTab: "map" });
  },

  refreshLayerViewport: async (id, bbox, zoom, signal) => {
    const targetSessionId = get().activeSessionId;
    const lyr = get().layers.find((l) => l.id === id);
    if (!lyr || lyr.kind !== "vector" || !lyr.visible) return;
    set((s) => ({
      layers: s.layers.map((l) => (l.id === id ? { ...l, viewportLoading: true } : l)),
    }));
    try {
      const gj = await api.getVectorGeojson(lyr.path, { bbox, zoom, max_features: 5000, signal });
      if (get().activeSessionId !== targetSessionId) return;
      set((s) => ({
        layers: s.layers.map((l) =>
          l.id === id
            ? {
                ...l,
                geojson: gj,
                viewportLoading: false,
                viewportReturned: Array.isArray(gj.features) ? gj.features.length : 0,
              }
            : l
        ),
      }));
    } catch (err: any) {
      if (err?.name === "AbortError") return;
      set((s) => ({
        layers: s.layers.map((l) => (l.id === id ? { ...l, viewportLoading: false } : l)),
      }));
    }
  },

  highlightAttributeRow: async (path, fid, rowBbox = null) => {
    const norm = normalizeLayerPath(path);
    const lyr = get().layers.find((l) => normalizeLayerPath(l.path) === norm);
    const cached = lyr?.geojson?.features?.find((f) => Number(f.properties?._fid) === fid) || null;
    if (isValidWgs84Bbox(rowBbox)) {
      get().zoomToLayer(rowBbox);
    }
    if (cached) {
      set({ highlightedFeature: { path, fid, feature: cached } });
      return;
    }
    set({ highlightedFeature: { path, fid, feature: null } });
    try {
      const gj = await api.getVectorGeojson(path, { fids: [fid] });
      const current = get().highlightedFeature;
      if (!current || normalizeLayerPath(current.path) !== norm || current.fid !== fid) return;
      const feat = gj.features?.[0] || null;
      set({ highlightedFeature: { path, fid, feature: feat } });
      if (!isValidWgs84Bbox(rowBbox) && isValidWgs84Bbox(gj.meta?.bbox_wgs84)) {
        get().zoomToLayer(gj.meta.bbox_wgs84);
      }
    } catch {
      // Ignore transient highlight fetch failure; keep selection state without crash.
    }
  },

  clearHighlight: () => set({ highlightedFeature: null }),

  setPendingContainer: (pendingContainer) => set({ pendingContainer }),

  styleVectorLayerByField: async (id, field) => {
    const lyr = get().layers.find((l) => l.id === id);
    if (!lyr) return;
    if (!field) {
      set((s) => ({ layers: s.layers.map((l) => (l.id === id ? { ...l, styleField: null, breaks: [] } : l)) }));
      return;
    }
    const res = await api.getAttributes(lyr.path, { page: 1, page_size: 10, stats_field: field });
    const breaks: number[] = res.stats?.quantile_breaks || [];
    set((s) => ({ layers: s.layers.map((l) => (l.id === id ? { ...l, styleField: field, breaks } : l)) }));
  },

  updateRasterStyle: (id, band, colormap) => {
    set((s) => ({
      layers: s.layers.map((l) =>
        l.id === id
          ? {
              ...l,
              band,
              colormap,
              rasterUrl: buildAuthedUrl("/api/spatial/raster/preview", {
                path: l.path,
                band,
                colormap,
                width: 1024,
                height: 1024,
                _ts: Date.now(),
              }),
            }
          : l
      ),
    }));
  },

  toggleLayerSelectedForContext: (path) =>
    set((s) => ({
      selectedLayerPaths: s.selectedLayerPaths.includes(path)
        ? s.selectedLayerPaths.filter((x) => x !== path)
        : [...s.selectedLayerPaths, path],
    })),

  setActiveTab: (activeTab) => set({ activeTab }),
  setMapTool: (mapTool) => set({ mapTool }),
  setBasemap: (basemap) => set({ basemap }),
  setIdentifyPopup: (identifyPopup) => set({ identifyPopup }),
  setSelectedFids: (selectedFids) => set({ selectedFids }),
  setDrawnAoi: (drawnBboxWgs84, drawnGeometryGeojson = null) => set({ drawnBboxWgs84, drawnGeometryGeojson }),
  setClickedPoint: (clickedPointWgs84) => set({ clickedPointWgs84 }),
  addFigureAnnotation: (ann) => set((s) => ({ figureAnnotations: [...s.figureAnnotations, ann] })),
  removeFigureAnnotation: (id) => set((s) => ({ figureAnnotations: s.figureAnnotations.filter((a) => a.id !== id) })),
  setExecutionPolicy: (executionPolicy) => set({ executionPolicy }),
  setAttrLayerPath: (attrLayerPath) => set({ attrLayerPath }),
  setSelectedExecId: (selectedExecId) => set({ selectedExecId }),
  setSettingsOpen: (settingsOpen) => set({ settingsOpen }),
  setToast: (toast) => set({ toast }),

  buildWorkspaceContext: () => {
    const s = get();
    return {
      project_path: s.projectDir || undefined,
      selected_layers: s.selectedLayerPaths.length ? s.selectedLayerPaths : s.layers.filter((l) => l.visible).map((l) => l.path),
      visible_layers: s.layers.filter((l) => l.visible).map((l) => l.path),
      selected_feature_ids: s.selectedFids,
      drawn_bbox_wgs84: s.drawnBboxWgs84,
      drawn_geometry_geojson: s.drawnGeometryGeojson,
      clicked_point_wgs84: s.clickedPointWgs84,
      figure_annotations: s.figureAnnotations.map(({ figure_path, norm_bbox, note, target_gid }) => ({
        figure_path,
        norm_bbox,
        note,
        ...(target_gid ? { target_gid } : {}),
      })),
      execution_policy: s.executionPolicy,
    };
  },

  sendMessage: async (text: string) => {
    const s = get();
    if (!s.activeSessionId) return;
    set({
      busy: true,
      messages: [...s.messages, { role: "user", origin: "user", content: text }],
    });
    try {
      await api.sendMessage(s.activeSessionId, text, s.buildWorkspaceContext());
      set({ figureAnnotations: [] });
    } catch (err: any) {
      set({ busy: false, toast: err?.message || "发送失败" });
    }
  },

  replyCheckpoint: async (text: string, optionId?: string) => {
    const s = get();
    if (!s.activeSessionId || !s.waiting) return;
    set({ busy: true });
    try {
      await api.replyCheckpoint(s.activeSessionId, {
        text,
        option_id: optionId,
        request_id: s.waiting.request_id,
        workspace_context: s.buildWorkspaceContext(),
      });
      set({ waiting: null, figureAnnotations: [] });
    } catch (err: any) {
      set({ busy: false, toast: err?.message || "提交检查点回复失败" });
    }
  },

  stopRun: async () => {
    const sid = get().activeSessionId;
    if (!sid) return;
    await api.stopSession(sid);
    set({ toast: "正在停止当前任务并安全回收子进程…" });
  },

  cancelCheckpoint: async () => {
    const sid = get().activeSessionId;
    if (!sid) return;
    await api.cancelCheckpoint(sid);
    await get().selectSession(sid);
  },
}));
