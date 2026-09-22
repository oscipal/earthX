import { create } from 'zustand';

import * as api from './api';
import type { CoverageResponse } from './api';
import { clampBboxLongitude, FOOTPRINT_FETCH_LIMIT, showFootprints } from './coverage';
import type { DatasetOption } from './datasets';
import { datasetsFrom, defaultRenderOf, quicklookPlan } from './datasets';
import { fallbackNotice, findFallback, fullDayRange, NO_FALLBACK_MESSAGE } from './dateFallback';
import { downloadRequestFor } from './download';
import { polygonBbox, quicklookCoords, unionBbox } from './geoUtils';
import { buildGroups, groupIndexOfItem, MissingProperty } from './grouping';
import type { LayerOverlay, MapLayer } from './layers';
import { buildTileUrl, footprintsFC } from './mapLayers';
import type { Projection, Theme } from './preferences';
import { loadProjection, loadTheme, saveProjection, saveTheme } from './preferences';
import { autoRescale } from './render';
import type { AppliedRender, Bbox, DownloadedInfo, StacItem, TimeStepGroup, ToolMode } from './types';

const PAGE_LIMIT = 100;
// The prototype's own richtwert (`max_search_items`); there is no server config
// endpoint to read it from any more (M2-07a scope — the prototype's `/api/config`
// is gone), so it stays a constant here until a task actually needs it tunable.
const MAX_SEARCH_ITEMS = 300;
// Debounced so a drag across the map doesn't fire a coverage request per
// frame — 400ms is a pause long enough to tell "still panning" from
// "settled", not a measurement.
const COVERAGE_DEBOUNCE_MS = 400;

function buildDatetime(from: string, to: string): string | undefined {
  const start = from ? `${from}T00:00:00Z` : '..';
  const end = to ? `${to}T23:59:59Z` : '..';
  if (start === '..' && end === '..') return undefined;
  return `${start}/${end}`;
}

// Narrower than zustand's actual `set`/`get` (no `replace` flag, no functional
// partial) — every call site below only ever needs a plain partial, and a
// function accepting more than this is still assignable to it.
type SetState = (partial: Partial<AppState>) => void;
type GetState = () => AppState;

let coverageDebounceHandle: number | undefined;
// Bumped on every refresh so a slow request that finishes after a newer one
// started can tell it has been superseded and must not overwrite fresher
// state (the same pattern `mapLayers.ts` uses for quicklook loads).
let coverageGen = 0;

function scheduleCoverageRefresh(set: SetState, get: GetState): void {
  window.clearTimeout(coverageDebounceHandle);
  coverageDebounceHandle = window.setTimeout(() => void refreshCoverage(set, get), COVERAGE_DEBOUNCE_MS);
}

// Fetches the density grid for the current dataset/AOI/date filter (M2-07c),
// and — only once the backend's `footprints_advised` and the frontend's own
// zoom brake (coverage.ts) both agree — the real scene footprints to replace
// it with. `bbox` is the search AOI (`aoi`, drawn/uploaded), never the map's
// pan/zoom viewport: `adr/0004` §6.3 ties the geotile *level* to the map's
// zoom, but its "räumlicher Filter" (has_spatial_filter) means an actual
// narrowing criterion. Sending the viewport as `bbox` on every pan would
// silently turn every browse into a "filtered" query and permanently disable
// the coverage route's own world-view cap (`WORLD_LEVEL_CAP`) — the bug
// behind the too-coarse cells reported after M2-07c's first local run; see
// the PR for the measured levels and the (backend, Otto's-call) proposal.
//
// A failed density fetch clears the layer (nothing to fall back to); a
// failed *footprints* fetch instead leaves `coverage` in place and
// `coverageFootprints` at `null`, so `MapView`'s `coverageDisplayFor` falls
// back to the density it already has rather than losing the whole layer over
// a second, optional request.
async function refreshCoverage(set: SetState, get: GetState): Promise<void> {
  const s = get();
  if (!s.showCoverage || !s.datasetId) {
    set({ coverage: null, coverageFootprints: null, coverageError: null, coverageLoading: false });
    return;
  }
  const gen = ++coverageGen;
  const { datasetId } = s;
  const rawBbox = s.aoi ? polygonBbox(s.aoi) : null;
  // Clamped to ±180° longitude — a wide AOI drawn across a wrapped world
  // copy (MapLibre repeats the map at low zoom) can otherwise carry corners
  // past ±180, which the coverage route refuses outright (coverage.ts).
  const bbox = rawBbox ? clampBboxLongitude(rawBbox) : undefined;
  const zoom = Math.floor(s.mapZoom);
  const datetime = buildDatetime(s.dateFrom, s.dateTo);
  set({ coverageLoading: true, coverageError: null });
  let coverage: CoverageResponse;
  try {
    coverage = await api.fetchCoverage({ datasetId, zoom, bbox, datetime });
  } catch (e) {
    if (gen !== coverageGen) return;
    set({
      coverage: null,
      coverageFootprints: null,
      coverageLoading: false,
      coverageError: `Coverage not available: ${(e as Error).message}`,
    });
    return;
  }
  if (gen !== coverageGen) return;
  set({ coverage, coverageFootprints: null, coverageLoading: false, coverageError: null });
  if (!showFootprints(coverage, get().mapZoom)) return;
  try {
    const { features } = await api.searchAllPages({ collection: datasetId, bbox, datetime }, FOOTPRINT_FETCH_LIMIT);
    if (gen !== coverageGen) return;
    set({ coverageFootprints: footprintsFC(features) });
  } catch {
    // Left at `null` — the density fill this dataset/viewport already has
    // stays on screen (E5: a failed extra fetches degrades, it doesn't 404).
  }
}

function foundNotice(features: StacItem[], groups: TimeStepGroup[], numberMatched: number | null): string {
  const base = `${features.length} scene(s) in ${groups.length} time step(s).`;
  if (numberMatched !== null && numberMatched > features.length) {
    return `${base} ${numberMatched} matched in total — narrow the area or date range to see the rest.`;
  }
  return base;
}

interface AppState {
  // --- map / selection ---
  toolMode: ToolMode;
  aoi: GeoJSON.Geometry | null;
  lastAoi: GeoJSON.Geometry | null; // most recent AOI, for "use last"
  flyToBbox: Bbox | null;
  // --- view preferences (V-1), saved per browser (preferences.ts) ---
  theme: Theme;
  projection: Projection;
  // --- coverage heatmap (M2-07c) ---
  showCoverage: boolean;
  coverage: CoverageResponse | null;
  coverageLoading: boolean;
  coverageError: string | null;
  // Real scene footprints, fetched only once the coverage answer's
  // `footprints_advised` (plus the zoom brake, coverage.ts) switches the map
  // away from the density cells — `null` while density is showing or nothing
  // has loaded yet.
  coverageFootprints: GeoJSON.FeatureCollection | null;
  // The map's zoom only — never its pan/viewport bbox, which is not the
  // "räumlicher Filter" `adr/0004` §6.3 means (see `refreshCoverage`).
  mapZoom: number;

  // --- ui layout ---
  panelCollapsed: boolean; // left control panel slid off to the left
  // Viewing a full-resolution raster (M2-07b) instead of browsing quicklooks —
  // swaps ResultsPanel/ViewBar for ViewerControls (App.tsx).
  focusMode: boolean;
  showDownloaded: boolean;
  focusLoading: boolean; // fetching statistics while entering focus / "auto"

  // --- layer manager ---
  layers: MapLayer[]; // pinned images (top of list = top of map)
  layerManagerOpen: boolean;
  // The layer the download dialog (M2-07d) is open for, `null` when closed.
  downloadDialogLayerId: string | null;

  // --- render params for a full-res raster, committed via "Apply" (F18) ---
  appliedRender: AppliedRender;
  // Pending stretch/colormap edits, not yet committed to `appliedRender`.
  pendingColormapName: string; // '' = none
  pendingVmin: string;
  pendingVmax: string;

  // --- data ---
  config: { point_buffer_deg: number } | null; // no server config endpoint any more; the client default (0.05) applies
  datasets: DatasetOption[];
  datasetId: string | null;
  items: StacItem[];
  groups: TimeStepGroup[];
  activeGroupIndex: number;
  selectedIds: string[];
  downloaded: Record<string, DownloadedInfo>;

  // --- filters ---
  dateFrom: string;
  dateTo: string;

  // --- ui ---
  searching: boolean;
  downloading: boolean; // no operation in 07a sets this; 07d's download will
  playing: boolean;
  error: string | null;
  notice: string | null;

  // --- actions ---
  loadDatasets: () => Promise<void>;
  setDatasetId: (id: string) => void;
  setToolMode: (m: ToolMode) => void;
  setAoi: (g: GeoJSON.Geometry | null) => void;
  clearAoi: () => void;
  useLastAoi: () => void;
  flyTo: (b: Bbox) => void;
  clearFly: () => void;
  togglePanel: () => void;
  setPanelCollapsed: (v: boolean) => void;
  clearAll: () => void;
  toggleLayerManager: () => void;
  addCurrentToLayers: () => void;
  removeLayer: (id: string) => void;
  toggleLayerVisible: (id: string) => void;
  setLayerOpacity: (id: string, v: number) => void;
  moveLayer: (id: string, dir: 'up' | 'down') => void;
  selectLayer: (id: string) => void;
  openDownloadDialog: (id: string) => void;
  closeDownloadDialog: () => void;
  confirmDownload: () => Promise<void>;
  enterFocus: () => Promise<void>;
  exitFocus: () => void;
  toggleDownloaded: () => void;
  setPendingColormapName: (v: string) => void;
  setPendingVmin: (v: string) => void;
  setPendingVmax: (v: string) => void;
  applyRender: () => void;
  autoStretch: () => Promise<void>;
  zoomToView: () => void;
  setActiveGroupIndex: (i: number) => void;
  focusItem: (id: string) => void;
  toggleSelected: (id: string) => void;
  selectAllInActiveGroup: () => void;
  clearSelection: () => void;
  setDateFrom: (v: string) => void;
  setDateTo: (v: string) => void;
  setPlaying: (v: boolean) => void;
  setError: (v: string | null) => void;
  setNotice: (v: string | null) => void;
  runSearch: () => Promise<void>;
  toggleCoverage: () => void;
  setMapZoom: (zoom: number) => void;
  toggleTheme: () => void;
  toggleProjection: () => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  toolMode: 'none',
  aoi: null,
  lastAoi: null,
  flyToBbox: null,
  theme: loadTheme(),
  projection: loadProjection(),
  showCoverage: false,
  coverage: null,
  coverageLoading: false,
  coverageError: null,
  coverageFootprints: null,
  mapZoom: 1.6,

  panelCollapsed: false,
  focusMode: false,
  showDownloaded: true,
  focusLoading: false,

  layers: [],
  layerManagerOpen: false,
  downloadDialogLayerId: null,

  appliedRender: {},
  pendingColormapName: '',
  pendingVmin: '',
  pendingVmax: '',

  config: null,
  datasets: [],
  datasetId: null,
  items: [],
  groups: [],
  activeGroupIndex: 0,
  selectedIds: [],
  downloaded: {},

  dateFrom: '',
  dateTo: '',

  searching: false,
  downloading: false,
  playing: false,
  error: null,
  notice: null,

  loadDatasets: async () => {
    try {
      const collections = await api.fetchCollections();
      const datasets = datasetsFrom(collections);
      const firstViewable = datasets.find((d) => d.viewable);
      set({ datasets, datasetId: (firstViewable ?? datasets[0])?.id ?? null });
    } catch (e) {
      set({ error: `Backend not reachable: ${(e as Error).message}` });
    }
  },
  setDatasetId: (datasetId) => {
    set({
      datasetId,
      items: [],
      groups: [],
      activeGroupIndex: 0,
      selectedIds: [],
      error: null,
      notice: null,
      focusMode: false,
      downloaded: {},
      appliedRender: {},
      coverage: null,
      coverageFootprints: null,
      coverageError: null,
    });
    scheduleCoverageRefresh(set, get);
  },

  // Activating a draw tool slides the control panel away so it can't block the
  // map while you draw; finishing a draw re-opens it (see MapView).
  setToolMode: (toolMode) =>
    set(toolMode === 'none' ? { toolMode } : { toolMode, panelCollapsed: true }),
  // The AOI is also the coverage route's spatial filter (`refreshCoverage`),
  // so every way it can change reschedules a refresh.
  setAoi: (aoi) => {
    set((s) => ({ aoi, lastAoi: aoi ?? s.lastAoi }));
    scheduleCoverageRefresh(set, get);
  },
  clearAoi: () => {
    set({ aoi: null });
    scheduleCoverageRefresh(set, get);
  },
  useLastAoi: () => {
    const g = get().lastAoi;
    if (!g) return;
    const bb = polygonBbox(g);
    set({ aoi: g, toolMode: 'none', ...(bb ? { flyToBbox: bb } : {}) });
    scheduleCoverageRefresh(set, get);
  },
  flyTo: (flyToBbox) => set({ flyToBbox }),
  clearFly: () => set({ flyToBbox: null }),
  togglePanel: () => set((s) => ({ panelCollapsed: !s.panelCollapsed })),
  setPanelCollapsed: (panelCollapsed) => set({ panelCollapsed }),
  clearAll: () => {
    set({
      aoi: null,
      items: [],
      groups: [],
      activeGroupIndex: 0,
      selectedIds: [],
      panelCollapsed: false,
      playing: false,
      error: null,
      notice: null,
      focusMode: false,
      downloaded: {},
      appliedRender: {},
      pendingColormapName: '',
      pendingVmin: '',
      pendingVmax: '',
    });
    scheduleCoverageRefresh(set, get);
  },

  toggleLayerManager: () => set((s) => ({ layerManagerOpen: !s.layerManagerOpen })),
  addCurrentToLayers: () => {
    const s = get();
    const group = s.groups[s.activeGroupIndex];
    const overlays: LayerOverlay[] = [];
    if (s.focusMode) {
      const entries = s.selectedIds.length
        ? Object.entries(s.downloaded).filter(([id]) => s.selectedIds.includes(id))
        : Object.entries(s.downloaded);
      for (const [, info] of entries) {
        overlays.push({
          kind: 'raster',
          tileUrl: buildTileUrl(info, s.appliedRender),
          bounds: info.bounds,
          minZoom: info.minZoom,
          maxZoom: info.maxZoom,
        });
      }
    } else {
      const items = s.selectedIds.length
        ? s.items.filter((it) => s.selectedIds.includes(it.id))
        : (group?.items ?? []);
      const browsed = s.datasets.find((d) => d.id === s.datasetId);
      for (const it of items) {
        const plan = browsed ? quicklookPlan(it, browsed) : null;
        if (!plan) continue;
        if (plan.kind === 'image') {
          const coords = quicklookCoords(it);
          if (coords) overlays.push({ kind: 'image', url: plan.href, coords });
          continue;
        }
        // The preview substitute (M2-10): pinned at the one level it is read on,
        // so a pinned preview stays a preview and never turns into a full-
        // resolution read when the map zooms in on it.
        if (!it.bbox || !browsed) continue;
        overlays.push({
          kind: 'raster',
          tileUrl: api.buildTileTemplate(browsed.id, it.id, plan.asset),
          bounds: it.bbox,
          minZoom: plan.zoom,
          maxZoom: plan.zoom,
        });
      }
    }
    if (overlays.length === 0) {
      set({ error: 'Nothing to add — search and pick a time step first.' });
      return;
    }
    const dataset = s.datasets.find((d) => d.id === s.datasetId);
    const name = `${dataset?.title ?? s.datasetId ?? '?'} · ${group?.label ?? ''}`;
    const layer: MapLayer = {
      id: `L${Date.now().toString(36)}`,
      name,
      visible: true,
      opacity: 1,
      overlays,
      restore: {
        focusMode: s.focusMode,
        downloaded: { ...s.downloaded },
        appliedRender: { ...s.appliedRender },
        activeGroupIndex: s.activeGroupIndex,
        selectedIds: [...s.selectedIds],
        aoi: s.aoi,
        datasetId: s.datasetId,
      },
    };
    set({ layers: [layer, ...s.layers], layerManagerOpen: true, notice: `Added "${name}" to layers.` });
  },
  removeLayer: (id) => set((s) => ({ layers: s.layers.filter((l) => l.id !== id) })),
  toggleLayerVisible: (id) =>
    set((s) => ({ layers: s.layers.map((l) => (l.id === id ? { ...l, visible: !l.visible } : l)) })),
  setLayerOpacity: (id, opacity) =>
    set((s) => ({ layers: s.layers.map((l) => (l.id === id ? { ...l, opacity } : l)) })),
  moveLayer: (id, dir) =>
    set((s) => {
      const arr = [...s.layers];
      const i = arr.findIndex((l) => l.id === id);
      const j = dir === 'up' ? i - 1 : i + 1;
      if (i < 0 || j < 0 || j >= arr.length) return {};
      [arr[i], arr[j]] = [arr[j], arr[i]];
      return { layers: arr };
    }),
  selectLayer: (id) =>
    set((s) => {
      const l = s.layers.find((x) => x.id === id);
      if (!l) return {};
      const r = l.restore;
      return {
        focusMode: r.focusMode,
        downloaded: r.downloaded,
        appliedRender: r.appliedRender,
        activeGroupIndex: r.activeGroupIndex,
        selectedIds: r.selectedIds,
        aoi: r.aoi,
        showDownloaded: true,
      };
    }),

  openDownloadDialog: (id) => set({ downloadDialogLayerId: id, error: null }),
  closeDownloadDialog: () => set({ downloadDialogLayerId: null }),

  // Download the AOI crop for the layer the dialog is open for (M2-06's
  // `POST /collections/{dataset}/download`, M2-07d). `downloadRequestFor`
  // already refused anything that is not a full-resolution layer with a
  // drawn AOI, so a missing request here only means the layer was removed
  // while the dialog was open.
  confirmDownload: async () => {
    const s = get();
    const layer = s.layers.find((l) => l.id === s.downloadDialogLayerId);
    const req = layer && downloadRequestFor(layer);
    if (!req) {
      set({ downloadDialogLayerId: null });
      return;
    }
    set({ downloading: true, error: null });
    try {
      const blob = await api.downloadCrop({
        datasetId: req.datasetId,
        items: req.items,
        assets: req.assets,
        aoi: req.aoi,
        language: 'en',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${req.datasetId}-crop.zip`;
      a.click();
      URL.revokeObjectURL(url);
      set({ downloadDialogLayerId: null, notice: `Downloaded "${layer.name}".` });
    } catch (e) {
      set({ error: `Download failed: ${(e as Error).message}` });
    } finally {
      set({ downloading: false });
    }
  },

  // Enter full-resolution viewing (F10, M2-07b): build a tile URL per selected
  // item (or the whole active time step) from the registry's standard
  // visualisation, then measure a stretch once (adr/0006 §3.4) so the fields
  // are not left empty. Statistics are an optimisation (E5) — a failure keeps
  // the registry's static default in place instead of failing the view.
  enterFocus: async () => {
    const s = get();
    const group = s.groups[s.activeGroupIndex];
    const items = s.selectedIds.length
      ? s.items.filter((it) => s.selectedIds.includes(it.id))
      : (group?.items ?? []);
    if (items.length === 0) {
      set({ error: 'Nothing to view — pick a time step or select scenes first.' });
      return;
    }
    const dataset = s.datasets.find((d) => d.id === s.datasetId);
    if (!dataset || !dataset.viewable) {
      set({ error: 'Pick a dataset first.' });
      return;
    }
    const render = defaultRenderOf(dataset.collection);
    if (!render || render.assets.length === 0) {
      set({ error: `${dataset.title} has no default visualisation yet (earthx:default_render).` });
      return;
    }
    const asset = render.assets[0];
    const downloaded: Record<string, DownloadedInfo> = {};
    for (const it of items) {
      if (!it.bbox) continue;
      downloaded[it.id] = {
        tileUrl: api.buildTileTemplate(dataset.id, it.id, asset),
        bounds: it.bbox,
        asset,
        minZoom: dataset.zoom.min,
        maxZoom: dataset.zoom.max,
      };
    }
    if (Object.keys(downloaded).length === 0) {
      set({ error: 'None of the selected scenes carry a bounding box to render.' });
      return;
    }
    const rescale = render.rescale?.[0];
    set({
      error: null,
      focusMode: true,
      showDownloaded: true,
      downloaded,
      appliedRender: {
        expression: render.expression ?? undefined,
        colormapName: render.colormap_name ?? undefined,
        rescale: rescale ? `${rescale[0]},${rescale[1]}` : undefined,
      },
      pendingColormapName: render.colormap_name ?? '',
      pendingVmin: rescale ? String(rescale[0]) : '',
      pendingVmax: rescale ? String(rescale[1]) : '',
    });
    await get().autoStretch();
  },
  exitFocus: () =>
    set({
      focusMode: false,
      downloaded: {},
      appliedRender: {},
      pendingColormapName: '',
      pendingVmin: '',
      pendingVmax: '',
    }),
  toggleDownloaded: () => set((s) => ({ showDownloaded: !s.showDownloaded })),
  setPendingColormapName: (pendingColormapName) => set({ pendingColormapName }),
  setPendingVmin: (pendingVmin) => set({ pendingVmin }),
  setPendingVmax: (pendingVmax) => set({ pendingVmax }),
  // Commits the pending fields (F18) — nothing renders differently until this
  // runs, which is the point of an explicit "Apply".
  applyRender: () => {
    const s = get();
    const vmin = s.pendingVmin.trim();
    const vmax = s.pendingVmax.trim();
    set({
      appliedRender: {
        ...s.appliedRender,
        colormapName: s.pendingColormapName || undefined,
        rescale: vmin !== '' && vmax !== '' ? `${vmin},${vmax}` : undefined,
      },
    });
  },
  // Re-measures the stretch from `/statistics` (adr/0006 §3.4) and writes it into
  // the pending fields only — still needs "Apply" to take effect on the map.
  autoStretch: async () => {
    const s = get();
    const first = Object.entries(s.downloaded)[0];
    if (!s.datasetId || !first) return;
    const [itemId, info] = first;
    set({ focusLoading: true });
    try {
      const stats = await api.fetchStatistics(s.datasetId, itemId, info.asset);
      const range = autoRescale(stats);
      if (range) set({ pendingVmin: String(range[0]), pendingVmax: String(range[1]) });
    } catch (e) {
      set({ notice: `Could not measure a stretch automatically: ${(e as Error).message}` });
    } finally {
      set({ focusLoading: false });
    }
  },
  // Zoom to the selected scenes, else the active time step, else the whole AOI.
  zoomToView: () => {
    const { items, selectedIds, groups, activeGroupIndex, aoi, focusMode, downloaded } = get();
    if (focusMode) {
      const bb = unionBbox(Object.values(downloaded).map((info) => info.bounds));
      if (bb) set({ flyToBbox: bb });
      return;
    }
    let boxes = items.filter((it) => selectedIds.includes(it.id)).map((it) => it.bbox);
    if (boxes.length === 0) boxes = groups[activeGroupIndex]?.items.map((it) => it.bbox) ?? [];
    let bb = unionBbox(boxes);
    if (!bb && aoi) bb = polygonBbox(aoi);
    if (bb) set({ flyToBbox: bb });
  },
  setActiveGroupIndex: (activeGroupIndex) => set({ activeGroupIndex }),
  focusItem: (id) => {
    const idx = groupIndexOfItem(get().groups, id);
    if (idx >= 0) set({ activeGroupIndex: idx });
  },
  toggleSelected: (id) =>
    set((s) => ({
      selectedIds: s.selectedIds.includes(id)
        ? s.selectedIds.filter((x) => x !== id)
        : [...s.selectedIds, id],
    })),
  selectAllInActiveGroup: () =>
    set((s) => {
      const group = s.groups[s.activeGroupIndex];
      if (!group) return {};
      const merged = new Set([...s.selectedIds, ...group.items.map((it) => it.id)]);
      return { selectedIds: [...merged] };
    }),
  clearSelection: () => set({ selectedIds: [] }),
  setDateFrom: (dateFrom) => {
    set({ dateFrom });
    scheduleCoverageRefresh(set, get);
  },
  setDateTo: (dateTo) => {
    set({ dateTo });
    scheduleCoverageRefresh(set, get);
  },
  toggleCoverage: () => {
    const showCoverage = !get().showCoverage;
    set({ showCoverage });
    if (showCoverage) void refreshCoverage(set, get);
    else set({ coverage: null, coverageFootprints: null, coverageError: null, coverageLoading: false });
  },
  setMapZoom: (mapZoom) => {
    set({ mapZoom });
    scheduleCoverageRefresh(set, get);
  },
  setPlaying: (playing) => set({ playing }),
  setError: (error) => set({ error }),
  setNotice: (notice) => set({ notice }),
  toggleTheme: () => {
    const theme: Theme = get().theme === 'tech' ? 'normal' : 'tech';
    saveTheme(theme);
    set({ theme });
  },
  toggleProjection: () => {
    const projection: Projection = get().projection === 'mercator' ? 'globe' : 'mercator';
    saveProjection(projection);
    set({ projection });
  },

  runSearch: async () => {
    const { aoi, dateFrom, dateTo, datasetId, datasets } = get();
    if (!aoi) {
      set({ error: 'Draw or search an area of interest first.' });
      return;
    }
    const dataset = datasets.find((d) => d.id === datasetId);
    if (!dataset) {
      set({ error: 'Pick a dataset first.' });
      return;
    }
    if (!dataset.viewable) {
      set({ error: `This dataset cannot be shown yet: ${dataset.reason}` });
      return;
    }
    const bbox = polygonBbox(aoi);
    if (!bbox) {
      set({ error: 'Could not compute a bounding box for the area of interest.' });
      return;
    }
    const groupBy = dataset.groupBy;
    const applyResults = (
      features: StacItem[],
      notice: string | ((groups: TimeStepGroup[]) => string),
    ) => {
      try {
        const groups = buildGroups(features, groupBy);
        const text = typeof notice === 'function' ? notice(groups) : notice;
        set({ items: features, groups, activeGroupIndex: 0, selectedIds: [], error: null, notice: text });
      } catch (e) {
        if (e instanceof MissingProperty) {
          set({
            items: [],
            groups: [],
            activeGroupIndex: 0,
            selectedIds: [],
            error: `Grouping failed: ${e.message}`,
            notice: null,
          });
          return;
        }
        throw e;
      }
    };

    set({
      searching: true,
      error: null,
      notice: null,
      playing: false,
      panelCollapsed: true,
      focusMode: false,
      downloaded: {},
      appliedRender: {},
    });
    try {
      const datetimeRange = buildDatetime(dateFrom, dateTo);
      const page = await api.searchAllPages({ collection: dataset.id, bbox, datetime: datetimeRange }, MAX_SEARCH_ITEMS);
      if (page.features.length > 0) {
        applyResults(page.features, (groups) => foundNotice(page.features, groups, page.numberMatched));
        return;
      }
      if (!dateFrom && !dateTo) {
        applyResults([], 'No scenes found for this area.');
        return;
      }
      const fallback = await findFallback(
        (w) =>
          api.searchItems({
            collection: dataset.id,
            bbox,
            datetime: `${w.start}T00:00:00Z/${w.end}T23:59:59Z`,
            limit: PAGE_LIMIT,
          }),
        dateFrom,
        dateTo,
      );
      if (!fallback) {
        applyResults([], NO_FALLBACK_MESSAGE);
        return;
      }
      const range = fullDayRange(fallback.item);
      const full = range
        ? await api.searchAllPages({ collection: dataset.id, bbox, datetime: range }, MAX_SEARCH_ITEMS)
        : { features: [fallback.item], numberMatched: 1 };
      applyResults(full.features, fallbackNotice(fallback));
    } catch (e) {
      set({ error: `Search failed: ${(e as Error).message}`, items: [], groups: [], panelCollapsed: false });
    } finally {
      set({ searching: false });
    }
  },
}));
