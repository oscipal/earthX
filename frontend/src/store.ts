import { create } from 'zustand';

import { clipTileUrl } from './aoiClip';
import * as api from './api';
import type { CoverageResponse, ResolutionFactor } from './api';
import {
  bandViewportBbox,
  bboxContains,
  clampBboxLongitude,
  FOOTPRINT_FETCH_LIMIT,
  levelForViewport,
  roundBboxToGrid,
  showFootprints,
  VIEWPORT_ROUND_LEVELS,
} from './coverage';
import type { DatasetOption } from './datasets';
import { acquisitionNote, datasetsFrom, defaultRenderOf, preferredGeoreferencedAsset, quicklookPlan } from './datasets';
import { fallbackNotice, findFallback, fullDayRange, NO_FALLBACK_MESSAGE } from './dateFallback';
import {
  assetHostsOf,
  decideDownloadOutcome,
  decideDownloadOutcomeForLayer,
  downloadRequestFor,
  downloadRequestForSelection,
  isCogFormat,
  originalFileLinks,
  type OriginalFileLink,
} from './download';
import { coordsBbox, polygonBbox, quicklookCoords, searchArea, unionBbox } from './geoUtils';
import { buildGroups, groupIndexOfItem, groupItemIdsFor, MissingProperty } from './grouping';
import type { LayerOverlay, LayerRestore, MapLayer } from './layers';
import { buildTileUrl, footprintsFC } from './mapLayers';
import type { Projection, Theme } from './preferences';
import { loadProjection, loadTheme, saveProjection, saveTheme } from './preferences';
import { appliedRenderFrom, autoRescale } from './render';
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

// The items a selection-wide action (download, "add to layers") applies to:
// the picked scenes, or — with nothing picked — the whole active time step.
// Shared so `openDownloadForSelection`/`confirmDownload` (V-4) build the same
// set `addCurrentToLayers` already did.
function selectionItemsFrom(s: AppState): StacItem[] {
  const group = s.groups[s.activeGroupIndex];
  return s.selectedIds.length ? s.items.filter((it) => s.selectedIds.includes(it.id)) : (group?.items ?? []);
}

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

// M3-19 §3: the last few viewport (no-AOI) answers, so a pan/zoom that stays
// inside a bbox already asked for skips the request instead of repeating it.
// Keyed on dataset/level/datetime — an AOI query never reads or writes this,
// it always asks fresh (`plans/m3-19-weltueberblick-ausschnitt.md`: "mit AOI
// bleibt alles wie heute"). Module-level like `coverageGen` above: it holds
// no more than the interaction needs to feel warm, nothing a reload should
// have to restore.
interface ViewportCoverageEntry {
  datasetId: string;
  level: number;
  datetime: string | undefined;
  bbox: Bbox;
  coverage: CoverageResponse;
  footprints: GeoJSON.FeatureCollection | null;
}
const VIEWPORT_CACHE_SIZE = 8;
let viewportCoverageCache: ViewportCoverageEntry[] = [];

function cachedViewportCoverage(
  datasetId: string,
  level: number,
  datetime: string | undefined,
  viewport: Bbox,
): ViewportCoverageEntry | undefined {
  return viewportCoverageCache.find(
    (e) => e.datasetId === datasetId && e.level === level && e.datetime === datetime && bboxContains(e.bbox, viewport),
  );
}

function rememberViewportCoverage(entry: ViewportCoverageEntry): void {
  viewportCoverageCache = [entry, ...viewportCoverageCache].slice(0, VIEWPORT_CACHE_SIZE);
}

function scheduleCoverageRefresh(set: SetState, get: GetState): void {
  window.clearTimeout(coverageDebounceHandle);
  coverageDebounceHandle = window.setTimeout(() => void refreshCoverage(set, get), COVERAGE_DEBOUNCE_MS);
}

// Fetches the density grid for the current dataset/AOI/date filter (M2-07c),
// and — only once the backend's `footprints_advised` and the frontend's own
// zoom brake (coverage.ts) both agree — the real scene footprints to replace
// it with.
//
// M3-19 (Otto, 23.09.2026, replacing adr/0010 answer 6a): with an AOI,
// `bbox` is that AOI (`aoi`, drawn/uploaded) and the level follows the map's
// floored zoom, unchanged from before. Without an AOI, `bbox` is the
// *visible map extent* instead — banded across the antimeridian and rounded
// outward to a coarser block (`coverage.ts`) so nearby viewports ask the
// same question — and the level is derived from the viewport's own size so
// roughly the same number of cells always covers the screen
// (`levelForViewport`). Either way `bbox` is a real spatial filter as far as
// the route is concerned, so its `WORLD_LEVEL_CAP` no longer applies to the
// no-AOI case; see the plan for why that is intended, not a leftover.
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
  const { datasetId, aoi } = s;
  const hasAoi = aoi !== null;
  const datetime = buildDatetime(s.dateFrom, s.dateTo);

  let bbox: Bbox | undefined;
  let level: number;
  let viewport: Bbox | undefined; // the raw (unrounded) extent, for the reuse check only
  if (aoi) {
    // Clamped to ±180° longitude — a wide AOI drawn across a wrapped world
    // copy (MapLibre repeats the map at low zoom) can otherwise carry corners
    // past ±180, which the coverage route refuses outright (coverage.ts).
    const rawBbox = polygonBbox(aoi);
    if (!rawBbox) {
      set({ coverage: null, coverageFootprints: null, coverageError: null, coverageLoading: false });
      return;
    }
    bbox = clampBboxLongitude(rawBbox);
    level = Math.floor(s.mapZoom);
  } else {
    if (s.viewportBbox === null || s.viewportSize === null) return; // map not ready yet
    level = levelForViewport(s.mapZoom, s.viewportSize.width, s.viewportSize.height);
    viewport = bandViewportBbox(s.viewportBbox);
    bbox = roundBboxToGrid(viewport, level - VIEWPORT_ROUND_LEVELS);
  }

  const gen = ++coverageGen;

  if (!hasAoi && viewport) {
    const cached = cachedViewportCoverage(datasetId, level, datetime, viewport);
    if (cached) {
      set({ coverage: cached.coverage, coverageFootprints: cached.footprints, coverageLoading: false, coverageError: null });
      return;
    }
  }

  set({ coverageLoading: true, coverageError: null });
  let coverage: CoverageResponse;
  try {
    coverage = await api.fetchCoverage({ datasetId, zoom: level, bbox, datetime });
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
  let footprints: GeoJSON.FeatureCollection | null = null;
  if (showFootprints(coverage, get().mapZoom)) {
    try {
      const { features } = await api.searchAllPages({ collection: datasetId, bbox, datetime }, FOOTPRINT_FETCH_LIMIT);
      if (gen === coverageGen) {
        footprints = footprintsFC(features);
        set({ coverageFootprints: footprints });
      }
    } catch {
      // Left at `null` — the density fill this dataset/viewport already has
      // stays on screen (E5: a failed extra fetch degrades, it doesn't 404).
    }
  }
  if (!hasAoi && viewport && gen === coverageGen && bbox) {
    rememberViewportCoverage({ datasetId, level, datetime, bbox, coverage, footprints });
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
  // M3-08: the point the current AOI was drawn or uploaded from, kept apart from
  // `aoi` (still the square `bufferPointToPolygon` built, which is what the map
  // shows and the download crops) — only `runSearch` reads this, to search by the
  // point itself rather than by its buffer square's bbox.
  aoiPoint: GeoJSON.Point | null;
  lastAoi: GeoJSON.Geometry | null; // most recent AOI, for "use last"
  lastAoiPoint: GeoJSON.Point | null; // the point behind lastAoi, if it had one
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
  mapZoom: number;
  // The visible map extent and its CSS-pixel size, reported by `MapView` on
  // `moveend`/first load. Read only by `refreshCoverage` to build the no-AOI
  // request (M3-19) — an AOI is still the only thing that counts as the
  // route's "räumlicher Filter" in the `adr/0004` §6.3 sense; this is never
  // sent as one, only banded/rounded into `bbox` the same way an AOI is.
  viewportBbox: Bbox | null;
  viewportSize: { width: number; height: number } | null;

  // --- ui layout ---
  panelCollapsed: boolean; // left control panel slid off to the left
  // Right-docked results list slid off to the right — collapsible the same
  // way as the left control panel, not freely draggable any more (V-5).
  resultsPanelCollapsed: boolean;
  // Viewing a full-resolution raster (M2-07b) instead of browsing quicklooks —
  // swaps ResultsPanel/ViewBar for ViewerControls (App.tsx).
  focusMode: boolean;
  showDownloaded: boolean;
  focusLoading: boolean; // fetching statistics while entering focus / "auto"
  // Whether the current focus view is cropped to `aoi` ("Crop to AOI") or
  // shows the whole selection uncropped ("View full selection", M3-09) —
  // meaningless while `focusMode` is false. Drives the map's AOI clipping
  // (`mapLayers.ts::syncFocusRaster`) and, once pinned, the layer's own
  // download (`download.ts::downloadRequestFor`, P19).
  cropToAoi: boolean;

  // --- layer manager ---
  layers: MapLayer[]; // pinned images (top of list = top of map)
  layerManagerOpen: boolean;
  // The layer the download dialog (M2-07d) is open for, `null` when closed.
  downloadDialogLayerId: string | null;
  // The dialog open for the current selection (V-4) rather than a pinned
  // layer — downloading a selected quicklook's original data straight from
  // the results list, before "Add to layers"/"View full resolution".
  downloadSelection: boolean;
  // The resolution choice in the open download dialog (F10c, M3-18 §10).
  // Native (`1`) every time the dialog opens — never chosen automatically,
  // and never remembered from a previous download.
  downloadResolution: ResolutionFactor;
  // The outcome the open dialog follows (M3-17 plan §4) — `null` while
  // nothing is open, or while `openDownloadDialog` is still fetching a
  // layer's items to decide it (the crop and disabled outcomes never need
  // that fetch and are known immediately).
  downloadOutcome: 'crop' | 'originals' | 'disabled' | null;
  // The clickable original-file links for the open dialog, once
  // `downloadOutcome === 'originals'` is known and, for a pinned layer, its
  // items have been fetched (`download.ts::originalFileLinks`). `null` while
  // still loading; an empty list is a real, valid answer ("no asset on this
  // dataset's own registered hosts").
  downloadOriginalLinks: OriginalFileLink[] | null;
  // Set once a crop download has actually answered with at least one group
  // dropped for not touching the AOI at all (review finding on M3-17: the
  // user has to see this, not just find fewer files than requested in the
  // ZIP's ATTRIBUTION.txt). The dialog stays open to show this English
  // sentence instead of closing on a successful download, same as any other
  // outcome the user needs to read before moving on. `null` otherwise.
  downloadSkippedGroupsNotice: string | null;

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
  // Which group is open in the results list — `null` while every group is
  // collapsed (V-11). Kept in sync with `activeGroupIndex` whenever that
  // changes some other way (a new search, the time slider, "play", picking
  // a pinned layer); manually collapsing the open group only changes this,
  // leaving `activeGroupIndex` — and anything keyed to "the current time
  // step" instead of "what the list has open" — untouched. `MapView` reads
  // this (not `activeGroupIndex`) for the browse-mode quicklooks/preview
  // tiles it shows, so collapsing every group hides them too.
  expandedGroupIndex: number | null;
  selectedIds: string[];
  downloaded: Record<string, DownloadedInfo>;

  // --- filters ---
  dateFrom: string;
  dateTo: string;

  // --- scene lookup by name (M2-17) ---
  sceneNameQuery: string;
  sceneLookupLoading: boolean;

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
  setAoi: (g: GeoJSON.Geometry | null, point?: GeoJSON.Point | null) => void;
  clearAoi: () => void;
  useLastAoi: () => void;
  flyTo: (b: Bbox) => void;
  clearFly: () => void;
  togglePanel: () => void;
  setPanelCollapsed: (v: boolean) => void;
  toggleResultsPanel: () => void;
  clearAll: () => void;
  toggleLayerManager: () => void;
  addCurrentToLayers: () => void;
  removeLayer: (id: string) => void;
  toggleLayerVisible: (id: string) => void;
  setLayerOpacity: (id: string, v: number) => void;
  moveLayer: (id: string, dir: 'up' | 'down') => void;
  selectLayer: (id: string) => void;
  openDownloadDialog: (id: string) => Promise<void>;
  openDownloadForSelection: () => void;
  closeDownloadDialog: () => void;
  setDownloadResolution: (factor: ResolutionFactor) => void;
  confirmDownload: () => Promise<void>;
  enterFocus: (cropToAoi: boolean) => Promise<void>;
  exitFocus: () => void;
  toggleDownloaded: () => void;
  setPendingColormapName: (v: string) => void;
  setPendingVmin: (v: string) => void;
  setPendingVmax: (v: string) => void;
  applyRender: () => void;
  autoStretch: () => Promise<void>;
  zoomToView: () => void;
  setActiveGroupIndex: (i: number) => void;
  toggleResultsGroup: (i: number) => void;
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
  setSceneNameQuery: (v: string) => void;
  findSceneByName: () => Promise<void>;
  toggleCoverage: () => void;
  setMapViewport: (zoom: number, bbox: Bbox, size: { width: number; height: number }) => void;
  toggleTheme: () => void;
  toggleProjection: () => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  toolMode: 'none',
  aoi: null,
  aoiPoint: null,
  lastAoi: null,
  lastAoiPoint: null,
  flyToBbox: null,
  theme: loadTheme(),
  projection: loadProjection(),
  showCoverage: false,
  coverage: null,
  coverageLoading: false,
  coverageError: null,
  coverageFootprints: null,
  mapZoom: 1.6,
  viewportBbox: null,
  viewportSize: null,

  panelCollapsed: false,
  resultsPanelCollapsed: false,
  focusMode: false,
  showDownloaded: true,
  focusLoading: false,
  cropToAoi: false,

  layers: [],
  layerManagerOpen: false,
  downloadDialogLayerId: null,
  downloadSelection: false,
  downloadResolution: 1,
  downloadOutcome: null,
  downloadOriginalLinks: null,
  downloadSkippedGroupsNotice: null,

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
  expandedGroupIndex: 0,
  selectedIds: [],
  downloaded: {},

  dateFrom: '',
  dateTo: '',

  sceneNameQuery: '',
  sceneLookupLoading: false,

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
      expandedGroupIndex: 0,
      selectedIds: [],
      error: null,
      notice: null,
      focusMode: false,
      cropToAoi: false,
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
  setAoi: (aoi, point = null) => {
    set((s) => ({
      aoi,
      aoiPoint: point,
      lastAoi: aoi ?? s.lastAoi,
      lastAoiPoint: aoi ? point : s.lastAoiPoint,
    }));
    scheduleCoverageRefresh(set, get);
  },
  clearAoi: () => {
    set({ aoi: null, aoiPoint: null });
    scheduleCoverageRefresh(set, get);
  },
  useLastAoi: () => {
    const { lastAoi: g, lastAoiPoint } = get();
    if (!g) return;
    const bb = polygonBbox(g);
    set({ aoi: g, aoiPoint: lastAoiPoint, toolMode: 'none', ...(bb ? { flyToBbox: bb } : {}) });
    scheduleCoverageRefresh(set, get);
  },
  flyTo: (flyToBbox) => set({ flyToBbox }),
  clearFly: () => set({ flyToBbox: null }),
  togglePanel: () => set((s) => ({ panelCollapsed: !s.panelCollapsed })),
  setPanelCollapsed: (panelCollapsed) => set({ panelCollapsed }),
  toggleResultsPanel: () => set((s) => ({ resultsPanelCollapsed: !s.resultsPanelCollapsed })),
  clearAll: () => {
    set({
      aoi: null,
      aoiPoint: null,
      items: [],
      groups: [],
      activeGroupIndex: 0,
      expandedGroupIndex: 0,
      selectedIds: [],
      panelCollapsed: false,
      playing: false,
      error: null,
      notice: null,
      focusMode: false,
      cropToAoi: false,
      downloaded: {},
      appliedRender: {},
      pendingColormapName: '',
      pendingVmin: '',
      pendingVmax: '',
    });
    scheduleCoverageRefresh(set, get);
  },

  toggleLayerManager: () => set((s) => ({ layerManagerOpen: !s.layerManagerOpen })),
  // M3-09 §10 (Otto): a "Crop & merge to AOI" view pins one layer *per
  // group*, not one for the whole selection — each with its own overlays,
  // its own download, matching what a group's download has always merged
  // into one file anyway (P19). "View full selection" and the quicklook
  // (browse-mode) case are unchanged: one layer for the whole pinned
  // selection, since there is nothing cropped to merge into groups.
  addCurrentToLayers: () => {
    const s = get();
    const activeGroup = s.groups[s.activeGroupIndex];
    const dataset = s.datasets.find((d) => d.id === s.datasetId);
    const batchId = Date.now().toString(36);
    const makeLayer = (name: string, overlays: LayerOverlay[], restore: LayerRestore, salt: number): MapLayer => ({
      id: `L${batchId}${salt}`,
      name,
      visible: true,
      opacity: 1,
      overlays,
      restore,
    });

    if (s.focusMode) {
      const entries = s.selectedIds.length
        ? Object.entries(s.downloaded).filter(([id]) => s.selectedIds.includes(id))
        : Object.entries(s.downloaded);
      if (entries.length === 0) {
        set({ error: 'Nothing to add — search and pick a time step first.' });
        return;
      }
      if (s.cropToAoi && s.aoi) {
        const aoi = s.aoi;
        const byGroupIndex = new Map<number, [string, DownloadedInfo][]>();
        for (const entry of entries) {
          const idx = groupIndexOfItem(s.groups, entry[0]);
          const bucket = byGroupIndex.get(idx) ?? [];
          bucket.push(entry);
          byGroupIndex.set(idx, bucket);
        }
        const newLayers = [...byGroupIndex.entries()].map(([idx, groupEntries], i) => {
          const label = idx >= 0 ? s.groups[idx]?.label : activeGroup?.label;
          const itemIds = groupEntries.map(([id]) => id);
          const overlays: LayerOverlay[] = groupEntries.map(([, info]) => ({
            kind: 'raster',
            tileUrl: clipTileUrl(buildTileUrl(info.tileUrl, s.appliedRender), aoi),
            bounds: info.bounds,
            minZoom: info.minZoom,
            maxZoom: info.maxZoom,
          }));
          return makeLayer(
            `${dataset?.title ?? s.datasetId ?? '?'} · ${label ?? ''}`,
            overlays,
            {
              focusMode: true,
              downloaded: Object.fromEntries(groupEntries),
              appliedRender: { ...s.appliedRender },
              activeGroupIndex: s.activeGroupIndex,
              selectedIds: itemIds,
              itemIds,
              // One group already (this is `addCurrentToLayers`'s own
              // per-group split, PR #84 F5) — a single-element list, not
              // `groupItemIdsFor`, which would just rediscover the same split.
              groupItemIds: [itemIds],
              aoi,
              cropToAoi: true,
              datasetId: s.datasetId,
            },
            i,
          );
        });
        set({
          layers: [...newLayers, ...s.layers],
          layerManagerOpen: true,
          notice: `Added ${newLayers.length} layer${newLayers.length === 1 ? '' : 's'} (one per group).`,
        });
        return;
      }
      const itemIds = entries.map(([id]) => id);
      const overlays: LayerOverlay[] = entries.map(([, info]) => ({
        kind: 'raster',
        tileUrl: buildTileUrl(info.tileUrl, s.appliedRender),
        bounds: info.bounds,
        minZoom: info.minZoom,
        maxZoom: info.maxZoom,
      }));
      const name = `${dataset?.title ?? s.datasetId ?? '?'} · ${activeGroup?.label ?? ''}`;
      const layer = makeLayer(
        name,
        overlays,
        {
          focusMode: true,
          downloaded: { ...s.downloaded },
          appliedRender: { ...s.appliedRender },
          activeGroupIndex: s.activeGroupIndex,
          selectedIds: [...s.selectedIds],
          itemIds,
          groupItemIds: groupItemIdsFor(itemIds, s.groups),
          aoi: s.aoi,
          cropToAoi: false,
          datasetId: s.datasetId,
        },
        0,
      );
      set({ layers: [layer, ...s.layers], layerManagerOpen: true, notice: `Added "${name}" to layers.` });
      return;
    }

    const items = s.selectedIds.length
      ? s.items.filter((it) => s.selectedIds.includes(it.id))
      : (activeGroup?.items ?? []);
    const itemIds = items.map((it) => it.id);
    const overlays: LayerOverlay[] = [];
    const browsed = s.datasets.find((d) => d.id === s.datasetId);
    for (const it of items) {
      const plan = browsed ? quicklookPlan(it, browsed) : null;
      if (!plan) continue;
      if (plan.kind === 'image') {
        const coords = quicklookCoords(it, browsed && preferredGeoreferencedAsset(browsed));
        if (coords) {
          overlays.push({
            kind: 'image',
            url: plan.href,
            coords,
            nodataMax: browsed?.viewable ? browsed.quicklookNodataMax : null,
          });
        }
        continue;
      }
      // The preview substitute (M2-10): pinned at the one level it is read on,
      // so a pinned preview stays a preview and never turns into a full-
      // resolution read when the map zooms in on it.
      // `browsed` is already non-null here (a plan needs one), named again so
      // TypeScript can narrow it for the call below.
      if (!it.bbox || !browsed) continue;
      overlays.push({
        kind: 'raster',
        tileUrl: buildTileUrl(api.buildTileTemplate(browsed.id, it.id, plan.asset), plan.render),
        bounds: it.bbox,
        minZoom: plan.zoom,
        maxZoom: plan.zoom,
      });
    }
    if (overlays.length === 0) {
      set({ error: 'Nothing to add — search and pick a time step first.' });
      return;
    }
    const name = `${dataset?.title ?? s.datasetId ?? '?'} · ${activeGroup?.label ?? ''}`;
    const layer = makeLayer(
      name,
      overlays,
      {
        focusMode: false,
        downloaded: { ...s.downloaded },
        appliedRender: { ...s.appliedRender },
        activeGroupIndex: s.activeGroupIndex,
        selectedIds: [...s.selectedIds],
        itemIds,
        groupItemIds: groupItemIdsFor(itemIds, s.groups),
        aoi: s.aoi,
        cropToAoi: false,
        datasetId: s.datasetId,
      },
      0,
    );
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
        expandedGroupIndex: r.activeGroupIndex,
        selectedIds: r.selectedIds,
        aoi: r.aoi,
        cropToAoi: r.cropToAoi,
        showDownloaded: true,
      };
    }),

  // Open the dialog for a pinned layer (M2-07d). The crop and disabled
  // outcomes (M3-17 plan §4) are known synchronously from the layer's own
  // `restore`; only the originals outcome needs the layer's STAC items
  // fetched first (`restore` keeps tile info, not asset `href`s) — done here,
  // once, rather than inside `download.ts`, which stays a pure module with no
  // network calls of its own.
  openDownloadDialog: async (id) => {
    set({
      downloadDialogLayerId: id,
      downloadSelection: false,
      downloadResolution: 1,
      downloadOutcome: null,
      downloadOriginalLinks: null,
      downloadSkippedGroupsNotice: null,
      error: null,
    });
    const s = get();
    const layer = s.layers.find((l) => l.id === id);
    if (!layer) return;
    const outcome = decideDownloadOutcomeForLayer(layer, s.datasets);
    set({ downloadOutcome: outcome });
    if (outcome !== 'originals') return;
    const datasetId = layer.restore.datasetId;
    const dataset = s.datasets.find((d) => d.id === datasetId);
    const asset = dataset?.viewable ? defaultRenderOf(dataset.collection)?.assets[0] : undefined;
    if (!datasetId || !dataset || !asset) {
      set({ downloadOriginalLinks: [] });
      return;
    }
    const hosts = assetHostsOf(dataset);
    try {
      const fetched = await Promise.all(layer.restore.itemIds.map((itemId) => api.fetchItem(datasetId, itemId)));
      const items = fetched.filter((it): it is StacItem => it !== undefined);
      const groupItemIds = layer.restore.groupItemIds.length > 0 ? layer.restore.groupItemIds : [layer.restore.itemIds];
      const groups = groupItemIds.map((ids, i) => ({
        label: `Group ${i + 1}`,
        items: items.filter((it) => ids.includes(it.id)),
      }));
      // Still the dialog open for this same layer? The user may have closed
      // it, or opened another one, while the fetch was in flight.
      if (get().downloadDialogLayerId === id) {
        set({ downloadOriginalLinks: originalFileLinks(groups, [asset], hosts) });
      }
    } catch (e) {
      if (get().downloadDialogLayerId === id) {
        set({ error: `Could not load the original files: ${(e as Error).message}`, downloadOriginalLinks: [] });
      }
    }
  },
  // Open the dialog for the current selection (V-4/M3-17) — the AOI crop or
  // the original files, without first "View full resolution" or "Add to
  // layers". Items are already loaded (`store.items`), so the originals
  // outcome needs no fetch here, unlike a pinned layer's.
  openDownloadForSelection: () => {
    const s = get();
    const dataset = s.datasets.find((d) => d.id === s.datasetId);
    const outcome = decideDownloadOutcome({ cropToAoi: null, hasAoi: !!s.aoi, isCog: isCogFormat(dataset) });
    if (outcome === 'disabled') {
      set({ error: 'Draw an AOI to download this dataset.' });
      return;
    }
    const items = selectionItemsFrom(s);
    if (items.length === 0) {
      set({ error: 'Nothing to download — pick a time step or select scenes first.' });
      return;
    }
    if (outcome === 'crop') {
      const req = downloadRequestForSelection(dataset, groupItemIdsFor(items.map((it) => it.id), s.groups), s.aoi);
      if (!req) {
        set({ error: 'Nothing to download — pick a time step or select scenes first.' });
        return;
      }
      set({
        downloadDialogLayerId: null,
        downloadSelection: true,
        downloadResolution: 1,
        downloadOutcome: 'crop',
        downloadOriginalLinks: null,
        downloadSkippedGroupsNotice: null,
        error: null,
      });
      return;
    }
    // 'originals': the dataset's default asset, straight from the source.
    const asset = dataset?.viewable ? defaultRenderOf(dataset.collection)?.assets[0] : undefined;
    const groupItemIds = groupItemIdsFor(
      items.map((it) => it.id),
      s.groups,
    );
    const groups = groupItemIds.map((ids, i) => ({
      label: s.groups[groupIndexOfItem(s.groups, ids[0])]?.label ?? `Group ${i + 1}`,
      items: items.filter((it) => ids.includes(it.id)),
    }));
    const links = asset ? originalFileLinks(groups, [asset], assetHostsOf(dataset)) : [];
    set({
      downloadDialogLayerId: null,
      downloadSelection: true,
      downloadResolution: 1,
      downloadOutcome: 'originals',
      downloadOriginalLinks: links,
      downloadSkippedGroupsNotice: null,
      error: null,
    });
  },
  closeDownloadDialog: () =>
    set({
      downloadDialogLayerId: null,
      downloadSelection: false,
      downloadOutcome: null,
      downloadOriginalLinks: null,
      downloadSkippedGroupsNotice: null,
    }),
  setDownloadResolution: (factor) => set({ downloadResolution: factor }),

  // Download the AOI crop for whatever the dialog is open for (M2-06's
  // `POST /collections/{dataset}/download`, M2-07d; V-4 added the selection
  // case). Only ever called for the 'crop' outcome — the 'originals' outcome
  // has no single request to confirm, just the links the dialog already
  // shows (M3-17 plan §6, F2 option 1). `downloadRequestFor`/
  // `downloadRequestForSelection` already refused anything incomplete, so a
  // missing request here only means the layer was removed, or the
  // selection/AOI changed, while the dialog was open.
  confirmDownload: async () => {
    const s = get();
    const layer = s.layers.find((l) => l.id === s.downloadDialogLayerId);
    const dataset = s.datasets.find((d) => d.id === s.datasetId);
    const req = s.downloadSelection
      ? downloadRequestForSelection(dataset, groupItemIdsFor(selectionItemsFrom(s).map((it) => it.id), s.groups), s.aoi)
      : layer && downloadRequestFor(layer, s.datasets);
    const name = s.downloadSelection
      ? `${dataset?.title ?? s.datasetId ?? '?'} · ${s.groups[s.activeGroupIndex]?.label ?? ''}`
      : (layer?.name ?? '');
    if (!req) {
      set({ downloadDialogLayerId: null, downloadSelection: false, downloadOutcome: null });
      return;
    }
    set({ downloading: true, error: null });
    try {
      const result = await api.downloadCrop({
        datasetId: req.datasetId,
        groups: req.groups,
        assets: req.assets,
        aoi: req.aoi,
        resolution: s.downloadResolution,
      });
      const url = URL.createObjectURL(result.blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${req.datasetId}-crop.zip`;
      a.click();
      URL.revokeObjectURL(url);
      if (result.skippedGroups > 0) {
        // A group never touched the AOI at all and was left out of the ZIP
        // (`api/tiler.py::download_crop`) — the user has to see that now, not
        // only by counting files inside the archive, so the dialog stays
        // open with this instead of closing on success (review finding).
        set({
          downloadSkippedGroupsNotice:
            `${result.skippedGroups} of ${result.totalGroups} group${result.totalGroups === 1 ? '' : 's'} ` +
            `did not overlap the AOI and ${result.skippedGroups === 1 ? 'was' : 'were'} skipped.`,
        });
      } else {
        set({
          downloadDialogLayerId: null,
          downloadSelection: false,
          downloadOutcome: null,
          notice: `Downloaded "${name}".`,
        });
      }
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
  // `cropToAoi` picks which of the two "View full resolution" buttons
  // (`ViewBar.tsx`) was pressed — "Crop to AOI" or "View full selection"
  // (M3-09); the AOI clip itself happens later, on the map
  // (`mapLayers.ts::syncFocusRaster`), never here.
  enterFocus: async (cropToAoi) => {
    const s = get();
    const group = s.groups[s.activeGroupIndex];
    const items = s.selectedIds.length
      ? s.items.filter((it) => s.selectedIds.includes(it.id))
      : (group?.items ?? []);
    if (items.length === 0) {
      set({ error: 'Nothing to view — pick a time step or select scenes first.' });
      return;
    }
    if (cropToAoi && !s.aoi) {
      set({ error: 'Draw or search an area of interest first.' });
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
      cropToAoi,
      showDownloaded: true,
      downloaded,
      appliedRender: appliedRenderFrom(render),
      pendingColormapName: render.colormap_name ?? '',
      pendingVmin: rescale ? String(rescale[0]) : '',
      pendingVmax: rescale ? String(rescale[1]) : '',
    });
    await get().autoStretch();
  },
  exitFocus: () =>
    set({
      focusMode: false,
      cropToAoi: false,
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
  // Zoom to the AOI; if none is drawn, to the pinned layer images; if there
  // are none of those either, the button stays disabled (App.tsx::canZoom)
  // and this is never called.
  zoomToView: () => {
    const { aoi, layers } = get();
    if (aoi) {
      const bb = polygonBbox(aoi);
      if (bb) {
        set({ flyToBbox: bb });
        return;
      }
    }
    const boxes = layers.flatMap((layer) =>
      layer.overlays.map((ov) => (ov.kind === 'raster' ? ov.bounds : coordsBbox(ov.coords))),
    );
    const bb = unionBbox(boxes);
    if (bb) set({ flyToBbox: bb });
  },
  // Also expands the matching group in the results list — everything that
  // moves the "current" time step this way (the time slider, "play",
  // clicking a scene, picking a pinned layer) is meant to bring the list
  // along with it. A manual collapse (`toggleResultsGroup`) is the one path
  // that intentionally leaves `activeGroupIndex` alone.
  setActiveGroupIndex: (activeGroupIndex) => set({ activeGroupIndex, expandedGroupIndex: activeGroupIndex }),
  // The results list's own toggle (V-11): collapsing the already-open group
  // only ever changes `expandedGroupIndex`, never `activeGroupIndex` — so
  // the map/time slider stay exactly where they were, they just lose their
  // quicklooks/preview tiles until something is expanded again. Opening a
  // different (collapsed) group goes through `setActiveGroupIndex` instead,
  // keeping both in sync as usual.
  toggleResultsGroup: (index) => {
    const s = get();
    if (index === s.expandedGroupIndex) set({ expandedGroupIndex: null });
    else s.setActiveGroupIndex(index);
  },
  focusItem: (id) => {
    const idx = groupIndexOfItem(get().groups, id);
    if (idx >= 0) set({ activeGroupIndex: idx, expandedGroupIndex: idx });
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
  setMapViewport: (mapZoom, viewportBbox, viewportSize) => {
    set({ mapZoom, viewportBbox, viewportSize });
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
    const { aoi, aoiPoint, dateFrom, dateTo, datasetId, datasets } = get();
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
    // M3-08 F2a/F5a: a point AOI searches by the point itself, a polygon by its
    // true shape, a rectangle by its bbox — `aoiPoint` is only ever read here,
    // never for display or the download crop, which stay on `aoi`.
    const area = searchArea(aoi, aoiPoint);
    if (!area.bbox && !area.intersects) {
      set({ error: 'Could not compute a search area for the area of interest.' });
      return;
    }
    const resultsGroupBy = dataset.resultsGroupBy;
    // O2 (Otto, 26.09.2026): a dataset without a time axis answers the same
    // for any chosen window, so its acquisition period — not a date filter
    // that would narrow nothing — is what the search notice adds when the
    // backend says it dropped `datetime` (`ignoredFilters`).
    const timeNote = dataset.hasTimeAxis ? null : acquisitionNote(dataset.collection);
    const applyResults = (
      features: StacItem[],
      notice: string | ((groups: TimeStepGroup[]) => string),
      ignoredFilters: readonly string[] = [],
    ) => {
      try {
        const groups = buildGroups(features, resultsGroupBy);
        const base = typeof notice === 'function' ? notice(groups) : notice;
        const withTruncated = area.truncatedNotice ? `${base} ${area.truncatedNotice}` : base;
        const text = timeNote && ignoredFilters.includes('datetime') ? `${withTruncated} ${timeNote}.` : withTruncated;
        set({
          items: features,
          groups,
          activeGroupIndex: 0,
          expandedGroupIndex: 0,
          selectedIds: [],
          error: null,
          notice: text,
        });
      } catch (e) {
        if (e instanceof MissingProperty) {
          set({
            items: [],
            groups: [],
            activeGroupIndex: 0,
            expandedGroupIndex: 0,
            selectedIds: [],
            error: `Grouping failed: ${e.message}`,
            notice: null,
          });
          return;
        }
        throw e;
      }
    };
    // O3 (Otto, 26.09.2026): a dataset with no browsable quicklook and no
    // meaningful coarse-tile preview (`browse: 'full_resolution'`, the DEM)
    // goes straight into the cropped full-resolution view after a search
    // with results — `runSearch` never runs without an AOI (checked above),
    // so this is always "Crop & merge to AOI", never "View full selection".
    const enterFullResolutionIfNeeded = async () => {
      if (dataset.browse === 'full_resolution') await get().enterFocus(true);
    };

    set({
      searching: true,
      error: null,
      notice: null,
      playing: false,
      panelCollapsed: true,
      focusMode: false,
      cropToAoi: false,
      downloaded: {},
      appliedRender: {},
    });
    try {
      const datetimeRange = buildDatetime(dateFrom, dateTo);
      const page = await api.searchAllPages(
        { collection: dataset.id, bbox: area.bbox, intersects: area.intersects, datetime: datetimeRange },
        MAX_SEARCH_ITEMS,
      );
      if (page.features.length > 0) {
        applyResults(page.features, (groups) => foundNotice(page.features, groups, page.numberMatched), page.ignoredFilters);
        await enterFullResolutionIfNeeded();
        return;
      }
      // O2: a dataset without a time axis never runs the ±90-day fallback —
      // it answers the same for any window, so an empty result means the AOI
      // has no coverage, not "wrong dates" (Otto, 26.09.2026; before this, a
      // DEM search with an unrelated date range answered "No results in the
      // chosen time range, nor within ±90 days", which named a filter that
      // was never really in effect).
      if (!dataset.hasTimeAxis || (!dateFrom && !dateTo)) {
        applyResults([], 'No scenes found for this area.', page.ignoredFilters);
        return;
      }
      const fallback = await findFallback(
        (w) =>
          api.searchItems({
            collection: dataset.id,
            bbox: area.bbox,
            intersects: area.intersects,
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
        ? await api.searchAllPages(
            { collection: dataset.id, bbox: area.bbox, intersects: area.intersects, datetime: range },
            MAX_SEARCH_ITEMS,
          )
        : { features: [fallback.item], numberMatched: 1, ignoredFilters: [] };
      applyResults(full.features, fallbackNotice(fallback), full.ignoredFilters);
      await enterFullResolutionIfNeeded();
    } catch (e) {
      set({ error: `Search failed: ${(e as Error).message}`, items: [], groups: [], panelCollapsed: false });
    } finally {
      set({ searching: false });
    }
  },

  setSceneNameQuery: (sceneNameQuery) => set({ sceneNameQuery }),

  // Looks up one scene by its exact name, only in the currently selected
  // dataset (Otto, 23.09.2026: no cross-dataset fallback, because the two
  // catalogues name the same scene differently — a miss must say so). Unlike
  // `runSearch`, this needs neither an AOI nor a date range and leaves both
  // untouched. On any failure only `error` changes; the trefferliste,
  // selection, AOI and date range stay exactly as they were (M2-17 F4).
  findSceneByName: async () => {
    const { sceneNameQuery, datasetId, datasets } = get();
    const name = sceneNameQuery.trim();
    if (!name) return;
    const dataset = datasets.find((d) => d.id === datasetId);
    if (!dataset) {
      set({ error: 'Pick a dataset first.' });
      return;
    }
    if (!dataset.viewable) {
      set({ error: `This dataset cannot be shown yet: ${dataset.reason}` });
      return;
    }
    set({ sceneLookupLoading: true, error: null });
    try {
      const item = await api.fetchItem(dataset.id, name);
      if (!item) {
        set({
          error: `No scene named "${name}" in ${dataset.title} — the two catalogues name the same scene differently.`,
          sceneLookupLoading: false,
        });
        return;
      }
      let groups: TimeStepGroup[];
      try {
        groups = buildGroups([item], dataset.resultsGroupBy);
      } catch (e) {
        if (e instanceof MissingProperty) {
          set({ error: `Grouping failed: ${e.message}`, sceneLookupLoading: false });
          return;
        }
        throw e;
      }
      const bbox = item.bbox ?? (item.geometry ? polygonBbox(item.geometry) : null);
      set({
        items: [item],
        groups,
        activeGroupIndex: 0,
        expandedGroupIndex: 0,
        selectedIds: [item.id],
        panelCollapsed: true,
        focusMode: false,
        cropToAoi: false,
        playing: false,
        downloaded: {},
        appliedRender: {},
        error: null,
        notice: `Scene ${item.id}, found by name.`,
        sceneLookupLoading: false,
        ...(bbox ? { flyToBbox: bbox } : {}),
      });
      // F7 (Otto, 26.09.2026): a dataset with no browsable quicklook and no
      // meaningful coarse-tile preview shows the found scene in full
      // resolution directly — a scene lookup carries no AOI, so this is
      // always "View full selection", never a crop.
      if (dataset.browse === 'full_resolution') await get().enterFocus(false);
    } catch (e) {
      if (e instanceof api.HttpError && e.status === 400) {
        set({ error: 'Not a valid scene name.', sceneLookupLoading: false });
        return;
      }
      set({ error: `Scene lookup failed: ${(e as Error).message}`, sceneLookupLoading: false });
    }
  },
}));
