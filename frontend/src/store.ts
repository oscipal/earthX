import { create } from 'zustand';

import * as api from './api';
import type { ItemPage, SearchQuery } from './api';
import type { DatasetOption } from './datasets';
import { datasetsFrom, defaultRenderOf, quicklookAsset } from './datasets';
import { fallbackNotice, findFallback, fullDayRange, NO_FALLBACK_MESSAGE } from './dateFallback';
import { polygonBbox, quicklookCoords, unionBbox } from './geoUtils';
import { buildGroups, groupIndexOfItem, MissingProperty } from './grouping';
import type { LayerOverlay, MapLayer } from './layers';
import { buildTileUrl } from './mapLayers';
import { autoRescale } from './render';
import type { AppliedRender, Bbox, DownloadedInfo, StacItem, TimeStepGroup, ToolMode } from './types';

const PAGE_LIMIT = 100;
// The prototype's own richtwert (`max_search_items`); there is no server config
// endpoint to read it from any more (M2-07a scope — the prototype's `/api/config`
// is gone), so it stays a constant here until a task actually needs it tunable.
const MAX_SEARCH_ITEMS = 300;

function buildDatetime(from: string, to: string): string | undefined {
  const start = from ? `${from}T00:00:00Z` : '..';
  const end = to ? `${to}T23:59:59Z` : '..';
  if (start === '..' && end === '..') return undefined;
  return `${start}/${end}`;
}

// Pages through `nextToken` until the result is complete or `MAX_SEARCH_ITEMS`
// is reached — the API never sorts (D8, `earthx.api.main`), so "the nearest
// date" and "the full set for a date" both have to walk every page rather
// than trust the first one.
async function searchAllPages(
  q: Omit<SearchQuery, 'limit' | 'token'>,
): Promise<{ features: StacItem[]; numberMatched: number | null }> {
  let token: string | undefined;
  const features: StacItem[] = [];
  let numberMatched: number | null = null;
  do {
    const page: ItemPage = await api.searchItems({ ...q, limit: PAGE_LIMIT, token });
    features.push(...page.features);
    if (numberMatched === null) numberMatched = page.numberMatched;
    token = page.nextToken ?? undefined;
  } while (token && features.length < MAX_SEARCH_ITEMS);
  return { features, numberMatched };
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
  // Global coverage footprints — rebuilt properly with 07c (M2-05b); these
  // stay permanently off/empty in 07a so MapView's existing rendering has
  // something well-typed to read.
  showCoverage: boolean;
  coverageFC: GeoJSON.FeatureCollection | null;

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
}

export const useAppStore = create<AppState>((set, get) => ({
  toolMode: 'none',
  aoi: null,
  lastAoi: null,
  flyToBbox: null,
  showCoverage: false,
  coverageFC: null,

  panelCollapsed: false,
  focusMode: false,
  showDownloaded: true,
  focusLoading: false,

  layers: [],
  layerManagerOpen: false,

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
  setDatasetId: (datasetId) =>
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
    }),

  // Activating a draw tool slides the control panel away so it can't block the
  // map while you draw; finishing a draw re-opens it (see MapView).
  setToolMode: (toolMode) =>
    set(toolMode === 'none' ? { toolMode } : { toolMode, panelCollapsed: true }),
  setAoi: (aoi) => set((s) => ({ aoi, lastAoi: aoi ?? s.lastAoi })),
  clearAoi: () => set({ aoi: null }),
  useLastAoi: () => {
    const g = get().lastAoi;
    if (!g) return;
    const bb = polygonBbox(g);
    set({ aoi: g, toolMode: 'none', ...(bb ? { flyToBbox: bb } : {}) });
  },
  flyTo: (flyToBbox) => set({ flyToBbox }),
  clearFly: () => set({ flyToBbox: null }),
  togglePanel: () => set((s) => ({ panelCollapsed: !s.panelCollapsed })),
  setPanelCollapsed: (panelCollapsed) => set({ panelCollapsed }),
  clearAll: () =>
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
    }),

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
        overlays.push({ kind: 'raster', tileUrl: buildTileUrl(info, s.appliedRender), bounds: info.bounds });
      }
    } else {
      const items = s.selectedIds.length
        ? s.items.filter((it) => s.selectedIds.includes(it.id))
        : (group?.items ?? []);
      for (const it of items) {
        const coords = quicklookCoords(it.geometry, it.bbox);
        const asset = quicklookAsset(it);
        if (coords && asset) overlays.push({ kind: 'image', url: asset.href, coords });
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
      downloaded[it.id] = { tileUrl: api.buildTileTemplate(dataset.id, it.id, asset), bounds: it.bbox, asset };
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
  setDateFrom: (dateFrom) => set({ dateFrom }),
  setDateTo: (dateTo) => set({ dateTo }),
  setPlaying: (playing) => set({ playing }),
  setError: (error) => set({ error }),
  setNotice: (notice) => set({ notice }),

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
      const page = await searchAllPages({ collection: dataset.id, bbox, datetime: datetimeRange });
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
        ? await searchAllPages({ collection: dataset.id, bbox, datetime: range })
        : { features: [fallback.item], numberMatched: 1 };
      applyResults(full.features, fallbackNotice(fallback));
    } catch (e) {
      set({ error: `Search failed: ${(e as Error).message}`, items: [], groups: [], panelCollapsed: false });
    } finally {
      set({ searching: false });
    }
  },
}));
