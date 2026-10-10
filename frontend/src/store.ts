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
import { buildGroups, groupIndexOfItem, groupItemIdsFor } from './grouping';
import type { LayerOverlay, LayerRestore, MapLayer } from './layers';
import { buildTileUrl, footprintsFC } from './mapLayers';
import type { Projection, Theme } from './preferences';
import { loadProjection, loadTheme, saveProjection, saveTheme } from './preferences';
import { appliedRenderFrom, autoRescale } from './render';
import type { ResultSection, SectionSearchAnswer } from './sections';
import {
  buildSections,
  combineAnswers,
  firstSectionWithItems,
  LOAD_MORE_NOTE,
  NO_SCENES_NOTE,
  needsFallback,
  withSourceState,
} from './sections';
import { fullResolutionLayers } from './searchLayers';
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
// set `addCurrentToLayers` already did, and so the processing panel (M4-13b)
// offers its scenes from that same set.
export function selectionItemsFrom(s: AppState): StacItem[] {
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
  // The coverage map has a dataset of its own (chosen at the "Coverage" button,
  // M3-10), independent of the dataset whose results the map shows.
  const datasetId = s.coverageDatasetId ?? s.datasetId;
  if (!s.showCoverage || !datasetId) {
    set({ coverage: null, coverageFootprints: null, coverageError: null, coverageLoading: false });
    return;
  }
  const { aoi } = s;
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
      const { features } = await api.searchAllPages({ collections: [datasetId], bbox, datetime }, FOOTPRINT_FETCH_LIMIT);
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

// With a page token left, "Load more" fetches the rest, so the notice only says
// how many there are.
function foundNotice(
  features: StacItem[],
  groups: TimeStepGroup[],
  numberMatched: number | null,
  canLoadMore: boolean,
): string {
  const base = `${features.length} scene(s) in ${groups.length} time step(s).`;
  if (numberMatched !== null && numberMatched > features.length) {
    return canLoadMore
      ? `${base} ${numberMatched} matched in total.`
      : `${base} ${numberMatched} matched in total — narrow the area or date range to see the rest.`;
  }
  return base;
}

// A layer id prefix, unique per call: the clock alone gives two pins within one
// millisecond the same id, and a layer is found again by that id.
let batchSeq = 0;
function nextBatchId(): string {
  return `${Date.now().toString(36)}-${(batchSeq++).toString(36)}-`;
}

// A search answer that names nothing dropped and nothing missing — for the paths
// that build a result without a search behind it.
const NO_ANSWER_FILTERS: SectionSearchAnswer & { ignoredFilters: string[]; incompleteCollections: never[] } = {
  ignoredFilters: [],
  ignoredFiltersByCollection: {},
  incompleteCollections: [],
};

// What leaving the full-resolution view resets — the same set `exitFocus` clears.
const LEAVE_FOCUS = {
  focusMode: false,
  cropToAoi: false,
  downloaded: {},
  appliedRender: {},
  pendingColormapName: '',
  pendingVmin: '',
  pendingVmax: '',
} as const;

// The list-facing state an open section stands for: its scenes and groups, first
// time step open. `null` closes everything.
function openSectionState(section: ResultSection | null) {
  return {
    openSectionId: section?.datasetId ?? null,
    items: section?.items ?? [],
    groups: section?.groups ?? [],
    activeGroupIndex: 0,
    expandedGroupIndex: 0,
  };
}

const groupKeyId = (group: TimeStepGroup | undefined) => group?.key.join('\u0000');

// The open section again after "Load more" added scenes to it: the same time
// steps stay active and open, found by their key — new scenes can move their index.
function reopenedSectionState(s: AppState, section: ResultSection | null) {
  const indexOf = (index: number) =>
    Math.max(0, section?.groups.findIndex((g) => groupKeyId(g) === groupKeyId(s.groups[index])) ?? 0);
  return {
    ...openSectionState(section),
    activeGroupIndex: indexOf(s.activeGroupIndex),
    expandedGroupIndex: s.expandedGroupIndex === null ? null : indexOf(s.expandedGroupIndex),
  };
}

type ViewableDataset = Extract<DatasetOption, { viewable: true }>;

function viewableDatasets(datasets: DatasetOption[], ids: readonly string[]): ViewableDataset[] {
  return ids
    .map((id) => datasets.find((d) => d.id === id))
    .filter((d): d is ViewableDataset => d?.viewable === true);
}

// The search the results belong to (M3-10b): what "Load more" continues and what
// the ±90-day fallback of a chosen dataset asks again. Its AOI and dates are the
// ones it ran with; changing them in the control panel afterwards drops only the
// page token (`dropPageToken`).
interface SearchContext {
  datasetIds: string[];
  query: Omit<api.SearchQuery, 'limit' | 'token'>;
  dateFrom: string;
  dateTo: string;
  aoi: GeoJSON.Geometry;
  truncatedNotice: string | null;
  // Every scene loaded so far and what the answers said about them, over every
  // "Load more".
  features: StacItem[];
  answer: SectionSearchAnswer;
  numberMatched: number | null;
  // The page token left over — the mixed one for the whole search, never one per
  // dataset (M3-10 F1). `null` once the search is complete or cannot go on.
  nextToken: string | null;
  // The backend's `open_collections` of the last page; `null` if it named none.
  openCollections: string[] | null;
}

// Whether "Load more" may still bring scenes of this dataset: its source has pages
// left (Otto, 30.09.2026). Unknown counts as open — the fallback would otherwise
// claim "no results in the chosen time range" too early.
function sourceOpen(ctx: SearchContext, datasetId: string): boolean {
  return ctx.nextToken !== null && (ctx.openCollections?.includes(datasetId) ?? true);
}

// Bumped by everything that replaces or drops the results, so a "Load more" or a
// fallback answering afterwards can tell that its results are gone.
let searchGen = 0;

// Item ids are unique only within a collection.
const sceneKey = (item: StacItem) => `${item.collection ?? ''}\u0000${item.id}`;

// The AOI crops of every dataset without a browsable preview (`browse:
// 'full_resolution'`, the DEM): part of that dataset's results, on the map while
// it is the one chosen in the dropdown (Otto, 30.09.2026). `problems` names a
// dataset whose scenes could not be drawn.
function cropsForSearch(
  datasets: ViewableDataset[],
  sections: ResultSection[],
  aoi: GeoJSON.Geometry,
): { crops: MapLayer[]; problems: string[] } {
  const batchId = nextBatchId();
  const problems: string[] = [];
  const crops = datasets.flatMap((dataset) => {
    const section = sections.find((x) => x.datasetId === dataset.id);
    if (dataset.browse !== 'full_resolution' || !section || section.items.length === 0) return [];
    const drawn = fullResolutionLayers(dataset, section, aoi, batchId);
    if (drawn.length === 0) {
      problems.push(
        defaultRenderOf(dataset.collection)?.assets[0]
          ? `${dataset.title}: none of its scenes carries a bounding box to draw.`
          : `${dataset.title} has no default visualisation yet (earthx:default_render).`,
      );
    }
    return drawn;
  });
  return { crops, problems };
}

function resultsNotice(ctx: SearchContext, datasets: ViewableDataset[], sections: ResultSection[]): string {
  if (ctx.features.length === 0) {
    return datasets.length === 1 || (!ctx.dateFrom && !ctx.dateTo)
      ? 'No scenes found for this area.'
      : 'No scenes found for this area and date range.';
  }
  if (datasets.length === 1) {
    return foundNotice(sections[0].items, sections[0].groups, ctx.numberMatched, ctx.nextToken !== null);
  }
  // What the search found in its date range: a fallback's scenes are not counted.
  const own = sections.filter((section) => section.origin === 'search');
  const steps = own.reduce((sum, section) => sum + section.groups.length, 0);
  const found = own.reduce((sum, section) => sum + section.items.length, 0);
  return `${found} scene(s) in ${steps} time step(s) across ${datasets.length} datasets.`;
}

// Lays out the scenes a search has loaded: one section per dataset asked, their
// AOI crops and the search notice. A new search opens the first dataset with
// scenes, else the active one. "Load more" (`keepOpen`) keeps the dataset and
// time step that are open; a dataset showing its ±90-day fallback keeps it while
// the search still has nothing of its own for it, and a dataset whose new scenes
// cannot be grouped keeps the scenes it had.
function showSearchResults(set: SetState, get: GetState, ctx: SearchContext, keepOpen: boolean): void {
  const s = get();
  const datasets = viewableDatasets(s.datasets, ctx.datasetIds);
  const { sections: built, stray } = buildSections(ctx.features, datasets, ctx.answer);
  const failed = datasets.length === 1 && !keepOpen ? built[0]?.groupingError : null;
  if (failed) {
    set({
      ...openSectionState(null),
      sections: [],
      searchCrops: [],
      selectedIds: [],
      searchContext: null,
      error: `Grouping failed: ${failed}`,
      notice: null,
    });
    return;
  }
  const sections = built.map((fresh) => {
    const section = withSourceState(fresh, sourceOpen(ctx, fresh.datasetId));
    const shown = keepOpen ? s.sections.find((x) => x.datasetId === section.datasetId) : undefined;
    if (!shown) return section;
    if (section.groupingError && !shown.groupingError) {
      const note = `Grouping failed: ${section.groupingError} — the scenes loaded since are left out.`;
      return shown.notes.includes(note) ? shown : { ...shown, notes: [...shown.notes, note] };
    }
    if (shown.origin === 'fallback' && section.items.length === 0) {
      // A source that failed only now is still said.
      const added = section.notes.filter((note) => note !== NO_SCENES_NOTE && !shown.notes.includes(note));
      return { ...shown, incomplete: section.incomplete, notes: [...shown.notes, ...added] };
    }
    return section;
  });
  const open = keepOpen
    ? (sections.find((x) => x.datasetId === s.openSectionId) ?? null)
    : (firstSectionWithItems(sections) ?? sections.find((x) => x.datasetId === s.datasetId) ?? sections[0] ?? null);
  // O2 (Otto, 26.09.2026): a dataset without a time axis answers the same for
  // any chosen window, so its acquisition period is what the notice adds when
  // the backend dropped `datetime`. With several datasets that note stands in
  // each section instead.
  const single = datasets.length === 1 ? datasets[0] : null;
  const timeNote =
    single && !single.hasTimeAxis && ctx.answer.ignoredFilters.includes('datetime')
      ? acquisitionNote(single.collection)
      : null;
  const { crops, problems } = cropsForSearch(datasets, sections, ctx.aoi);
  const notice = [
    resultsNotice(ctx, datasets, sections),
    ctx.truncatedNotice,
    timeNote && `${timeNote}.`,
    stray > 0 ? `${stray} scene(s) of other datasets were left out.` : null,
    ...problems,
  ]
    .filter(Boolean)
    .join(' ');
  set({
    sections,
    ...(keepOpen ? reopenedSectionState(s, open) : openSectionState(open)),
    ...(open ? { datasetId: open.datasetId } : {}),
    searchCrops: crops,
    selectedIds: keepOpen ? s.selectedIds.filter((id) => open?.items.some((it) => it.id === id)) : [],
    searchContext: ctx,
    error: null,
    notice,
  });
}

// The ±90-day fallback for one dataset of the search (M3-10 F7, Otto
// 30.09.2026): asks only that dataset around the searched date range and puts
// the nearest day's scenes, or that there are none, in its section. With one
// dataset searched the search notice says it too, as before M3-10, and a failure
// is thrown for `runSearch` to report (`rethrow`); otherwise the failure is said
// in the dataset's box. Pages only within that day, never with "Load more".
async function runFallback(set: SetState, get: GetState, datasetId: string, rethrow: boolean): Promise<void> {
  const s = get();
  const ctx = s.searchContext;
  const section = s.sections.find((x) => x.datasetId === datasetId);
  const [dataset] = viewableDatasets(s.datasets, [datasetId]);
  if (!ctx || !section || !dataset) return;
  if (!needsFallback(section, dataset, ctx.dateFrom, ctx.dateTo, sourceOpen(ctx, datasetId))) return;
  if (s.fallbackDatasetIds.includes(datasetId)) return;
  const gen = searchGen;
  set({ fallbackDatasetIds: [...s.fallbackDatasetIds, datasetId] });
  // Only a section still waiting for this fallback is replaced: a "Load more"
  // that answered first may have brought scenes in the date range.
  const replace = (make: (current: ResultSection) => ResultSection) => {
    if (gen !== searchGen) return null;
    const now = get();
    const current = now.sections.find((x) => x.datasetId === datasetId);
    if (!current || current.origin !== 'search' || current.items.length > 0) return null;
    const replacement = make(current);
    return { now, replacement, sections: now.sections.map((x) => (x.datasetId === datasetId ? replacement : x)) };
  };
  const withoutNoScenes = (current: ResultSection) =>
    current.notes.filter((note) => note !== NO_SCENES_NOTE && note !== LOAD_MORE_NOTE);
  try {
    const query = { ...ctx.query, collections: [datasetId] };
    const found = await findFallback(
      (w) =>
        api.searchItems({ ...query, datetime: `${w.start}T00:00:00Z/${w.end}T23:59:59Z`, limit: PAGE_LIMIT }),
      ctx.dateFrom,
      ctx.dateTo,
    );
    let built: ResultSection | null = null;
    if (found) {
      const range = fullDayRange(found.item);
      const full = range
        ? await api.searchAllPages({ ...query, datetime: range }, MAX_SEARCH_ITEMS)
        : { features: [found.item], ...NO_ANSWER_FILTERS };
      built = buildSections(full.features, [dataset], full).sections[0];
    }
    const done = replace((current) =>
      found && built
        ? { ...built, origin: 'fallback', notes: [fallbackNotice(found), ...built.notes] }
        : { ...current, origin: 'fallback', notes: [NO_FALLBACK_MESSAGE, ...withoutNoScenes(current)] },
    );
    if (!done) return;
    const { now, replacement, sections } = done;
    const { crops, problems } = cropsForSearch(viewableDatasets(now.datasets, ctx.datasetIds), sections, ctx.aoi);
    const singleNotice = replacement.groupingError
      ? { error: `Grouping failed: ${replacement.groupingError}`, notice: null }
      : { notice: [replacement.notes[0], ctx.truncatedNotice, ...problems].filter(Boolean).join(' ') };
    set({
      sections,
      ...(now.openSectionId === datasetId ? openSectionState(replacement) : {}),
      searchCrops: crops,
      ...(ctx.datasetIds.length === 1 ? singleNotice : {}),
    });
  } catch (e) {
    if (rethrow) throw e;
    // Not tried again for this search.
    const note = `Could not look for the nearest date: ${(e as Error).message}`;
    const done = replace((current) => ({ ...current, origin: 'fallback', notes: [note, ...withoutNoScenes(current)] }));
    if (done) set({ sections: done.sections });
  } finally {
    if (gen === searchGen) set({ fallbackDatasetIds: get().fallbackDatasetIds.filter((id) => id !== datasetId) });
  }
}

// A search on screen that the control panel would no longer run the same way
// (another AOI, other dates) cannot be continued: "Load more" would add scenes of
// the old one (M3-10 §4.4). The results themselves stay.
function dropPageToken(set: SetState, get: GetState): void {
  const ctx = get().searchContext;
  if (ctx?.nextToken) set({ searchContext: { ...ctx, nextToken: null } });
}

// What every replacement of the results resets besides the results themselves.
function forgetSearch() {
  searchGen += 1;
  return { searchContext: null, loadingMore: false, loadMoreError: null, fallbackDatasetIds: [] };
}

export interface AppState {
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
  // The dataset the coverage map is drawn for; `null` while it is off.
  coverageDatasetId: string | null;
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
  // The AOI crops a search draws by itself for a dataset with no browsable preview
  // (`browse: 'full_resolution'`): part of that dataset's results, on the map only
  // while that dataset is the one chosen in the results dropdown. Not in `layers`;
  // `pinSearchCrops` copies them there.
  searchCrops: MapLayer[];
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
  // M3-10: what the dataset filter has ticked — a search asks all of them at once.
  selectedDatasetIds: string[];
  // The *active* dataset: the one the map, time slider, heatmap, full-resolution
  // view and download follow. It is the open results section's dataset, or the
  // one picked in the heatmap legend; always one of `selectedDatasetIds`.
  datasetId: string | null;
  // One entry per dataset the last search asked, in filter order (M3-10). `items`,
  // `groups` and the two indices below mirror the *open* section only.
  sections: ResultSection[];
  openSectionId: string | null;
  searchContext: SearchContext | null;
  // "Load more" (M3-10b): running, and why it last failed.
  loadingMore: boolean;
  loadMoreError: string | null;
  // The datasets whose ±90-day fallback is running.
  fallbackDatasetIds: string[];
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
  toggleDatasetSelected: (id: string) => void;
  setOpenSection: (id: string) => void;
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
  loadMore: () => Promise<void>;
  setSceneNameQuery: (v: string) => void;
  findSceneByName: () => Promise<void>;
  showCoverageFor: (datasetId: string) => void;
  hideCoverage: () => void;
  pinSearchCrops: () => void;
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
  coverageDatasetId: null,
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
  searchCrops: [],
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
  selectedDatasetIds: [],
  datasetId: null,
  sections: [],
  openSectionId: null,
  searchContext: null,
  loadingMore: false,
  loadMoreError: null,
  fallbackDatasetIds: [],
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
      set({
        datasets,
        selectedDatasetIds: firstViewable ? [firstViewable.id] : [],
        datasetId: firstViewable?.id ?? null,
      });
    } catch (e) {
      set({ error: `Backend not reachable: ${(e as Error).message}` });
    }
  },
  // The filter's tick box (M3-10). A dataset that cannot be shown is never
  // ticked. Whatever the last search found no longer matches the new selection,
  // so the results go, as they did when a single dataset was switched; pinned
  // layers stay (they carry their own dataset).
  toggleDatasetSelected: (id) => {
    const s = get();
    // Not while a search or a lookup is running: its answer would land on a
    // selection that is no longer the one it asked.
    if (s.searching || s.sceneLookupLoading) return;
    const dataset = s.datasets.find((d) => d.id === id);
    const ticked = s.selectedDatasetIds.includes(id);
    if (!dataset || (!ticked && !dataset.viewable)) return;
    const selectedDatasetIds = s.datasets
      .filter((d) => (d.id === id ? !ticked : s.selectedDatasetIds.includes(d.id)))
      .map((d) => d.id);
    const datasetId =
      s.datasetId && selectedDatasetIds.includes(s.datasetId) ? s.datasetId : (selectedDatasetIds[0] ?? null);
    set({
      selectedDatasetIds,
      datasetId,
      sections: [],
      openSectionId: null,
      ...forgetSearch(),
      items: [],
      groups: [],
      activeGroupIndex: 0,
      expandedGroupIndex: 0,
      selectedIds: [],
      error: null,
      notice: null,
      playing: false,
      ...LEAVE_FOCUS,
      searchCrops: [],
    });
    // The coverage map is for a dataset that is picked; dropping that one drops it.
    if (s.coverageDatasetId && !selectedDatasetIds.includes(s.coverageDatasetId)) get().hideCoverage();
  },
  // Shows one dataset's results — the dropdown of the results panel (M3-10) — and
  // makes that dataset the active one. Exactly one is shown while a search has
  // results; there is no "none". What the previous dataset had on screen in full
  // resolution goes with it; pinned layers do not. A dataset with nothing in the
  // searched date range gets its ±90-day fallback now (M3-10b); a scene found by
  // name in a dataset without browsable preview is shown in full resolution, as
  // the lookup does for the dataset it opens with.
  setOpenSection: (id) => {
    const s = get();
    const section = s.sections.find((x) => x.datasetId === id);
    if (!section || id === s.openSectionId) return;
    set({
      ...openSectionState(section),
      datasetId: section.datasetId,
      selectedIds: [],
      playing: false,
      ...LEAVE_FOCUS,
    });
    const dataset = s.datasets.find((d) => d.id === id);
    if (section.origin === 'name' && section.items.length > 0 && dataset?.viewable && dataset.browse === 'full_resolution') {
      void get().enterFocus(false);
    }
    void runFallback(set, get, id, false);
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
    dropPageToken(set, get);
    scheduleCoverageRefresh(set, get);
  },
  clearAoi: () => {
    set({ aoi: null, aoiPoint: null });
    dropPageToken(set, get);
    scheduleCoverageRefresh(set, get);
  },
  useLastAoi: () => {
    const { lastAoi: g, lastAoiPoint } = get();
    if (!g) return;
    const bb = polygonBbox(g);
    set({ aoi: g, aoiPoint: lastAoiPoint, toolMode: 'none', ...(bb ? { flyToBbox: bb } : {}) });
    dropPageToken(set, get);
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
      sections: [],
      openSectionId: null,
      ...forgetSearch(),
      // The crops a search drew go with it; what the user pinned stays.
      searchCrops: [],
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
    const batchId = nextBatchId();
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
  selectLayer: (id) => {
    const s = get();
    const l = s.layers.find((x) => x.id === id);
    if (!l) return;
    const r = l.restore;
    // A layer belongs to the dataset it was pinned from (F4): choosing it makes
    // that dataset the active one — and opens its section, if the last search
    // has one — so the list and the controls speak of the layer's own scenes. A
    // dataset that is not ticked (any more) is ticked by this, without touching
    // the results, so the active dataset stays one of the ticked ones.
    const section = r.datasetId ? s.sections.find((x) => x.datasetId === r.datasetId) : undefined;
    const dataset = r.datasetId ? s.datasets.find((d) => d.id === r.datasetId) : undefined;
    const tickable = !!dataset?.viewable && !s.selectedDatasetIds.includes(dataset.id);
    const becomesActive = dataset && (dataset.viewable || s.selectedDatasetIds.includes(dataset.id)) ? dataset.id : null;
    if (r.aoi !== s.aoi) dropPageToken(set, get);
    set({
      ...(tickable
        ? { selectedDatasetIds: s.datasets.filter((d) => d.id === dataset.id || s.selectedDatasetIds.includes(d.id)).map((d) => d.id) }
        : {}),
      ...(section ? openSectionState(section) : becomesActive && becomesActive !== s.datasetId ? openSectionState(null) : {}),
      ...(becomesActive ? { datasetId: becomesActive } : {}),
      focusMode: r.focusMode,
      downloaded: r.downloaded,
      appliedRender: r.appliedRender,
      activeGroupIndex: r.activeGroupIndex,
      expandedGroupIndex: r.activeGroupIndex,
      selectedIds: r.selectedIds,
      aoi: r.aoi,
      cropToAoi: r.cropToAoi,
      showDownloaded: true,
    });
  },

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
    dropPageToken(set, get);
    scheduleCoverageRefresh(set, get);
  },
  setDateTo: (dateTo) => {
    set({ dateTo });
    dropPageToken(set, get);
    scheduleCoverageRefresh(set, get);
  },
  // The "Coverage" button (M3-10): draws the coverage of one of the picked datasets.
  showCoverageFor: (datasetId) => {
    if (!get().selectedDatasetIds.includes(datasetId)) return;
    set({
      showCoverage: true,
      coverageDatasetId: datasetId,
      coverage: null,
      coverageFootprints: null,
      coverageError: null,
    });
    void refreshCoverage(set, get);
  },
  hideCoverage: () => {
    set({
      showCoverage: false,
      coverageDatasetId: null,
      coverage: null,
      coverageFootprints: null,
      coverageError: null,
      coverageLoading: false,
    });
  },
  // Copies the AOI crops of the dataset shown in the results into the layer
  // manager, where they stay whichever dataset is chosen next. The user's own
  // step: a search never pins anything by itself.
  pinSearchCrops: () => {
    const s = get();
    const crops = s.searchCrops.filter((c) => c.restore.datasetId === s.openSectionId);
    if (crops.length === 0) {
      set({ error: 'Nothing to pin — this dataset has no crop to show.' });
      return;
    }
    const batchId = nextBatchId();
    const pinned = crops.map((c, i) => ({ ...c, id: `L${batchId}${i}` }));
    set({
      layers: [...pinned, ...s.layers],
      layerManagerOpen: true,
      error: null,
      notice: `Pinned ${pinned.length} layer${pinned.length === 1 ? '' : 's'} (${pinned[0].name.split(' · ')[0]}).`,
    });
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
    const { aoi, aoiPoint, dateFrom, dateTo, selectedDatasetIds, datasets } = get();
    if (!aoi) {
      set({ error: 'Draw or search an area of interest first.' });
      return;
    }
    // M3-10: every ticked dataset is asked at once, in one mixed search (M3-13).
    const chosen = viewableDatasets(datasets, selectedDatasetIds);
    if (chosen.length === 0) {
      const blocked = datasets.find((d) => selectedDatasetIds.includes(d.id));
      set({ error: blocked && !blocked.viewable ? `This dataset cannot be shown yet: ${blocked.reason}` : 'Pick a dataset first.' });
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
    set({
      searching: true,
      error: null,
      notice: null,
      playing: false,
      panelCollapsed: true,
      ...forgetSearch(),
      ...LEAVE_FOCUS,
    });
    // "Clear all" or another step that drops the results may come before the answer.
    const gen = searchGen;
    try {
      const query = {
        collections: chosen.map((d) => d.id),
        bbox: area.bbox,
        intersects: area.intersects,
        datetime: buildDatetime(dateFrom, dateTo),
      };
      const page = await api.searchAllPages(query, MAX_SEARCH_ITEMS);
      if (gen !== searchGen) return;
      showSearchResults(
        set,
        get,
        {
          datasetIds: query.collections,
          query,
          dateFrom,
          dateTo,
          aoi,
          truncatedNotice: area.truncatedNotice ?? null,
          features: page.features,
          answer: {
            ignoredFilters: page.ignoredFilters,
            ignoredFiltersByCollection: page.ignoredFiltersByCollection,
            incompleteCollections: page.incompleteCollections,
          },
          numberMatched: page.numberMatched,
          nextToken: page.nextToken,
          openCollections: page.openCollections,
        },
        false,
      );
      // The dataset the dropdown opens with found nothing in the date range (so
      // did every other one, or it would not be open): its fallback is part of the
      // search. A dataset without a time axis never runs it (O2, Otto 26.09.2026).
      // Its failure fails the search only when it is the one dataset searched;
      // otherwise the other datasets' notes stay and its box says it.
      const { openSectionId } = get();
      if (openSectionId) await runFallback(set, get, openSectionId, chosen.length === 1);
    } catch (e) {
      if (gen !== searchGen) return;
      set({
        error: `Search failed: ${(e as Error).message}`,
        sections: [],
        searchCrops: [],
        searchContext: null,
        ...openSectionState(null),
        panelCollapsed: false,
      });
    } finally {
      set({ searching: false });
    }
  },

  // Continues the whole search with its page token (M3-10 F1): one more walk of
  // up to `MAX_SEARCH_ITEMS`, whichever dataset the dropdown shows. New scenes go
  // to their own dataset; the dataset and time step open stay open. A failure
  // keeps what is loaded, and the token with it goes: a token that failed once
  // (e.g. `400` after a deployment) is not worth a second try.
  loadMore: async () => {
    const s = get();
    const ctx = s.searchContext;
    if (!ctx?.nextToken || s.loadingMore || s.searching) return;
    const gen = searchGen;
    set({ loadingMore: true, loadMoreError: null });
    try {
      const page = await api.searchAllPages(ctx.query, MAX_SEARCH_ITEMS, ctx.nextToken);
      if (gen !== searchGen) return;
      const known = new Set(ctx.features.map(sceneKey));
      // The AOI or dates may have changed while this ran: then the search can
      // still show what it loaded, but not go on.
      const stillCurrent = get().searchContext?.nextToken === ctx.nextToken;
      showSearchResults(
        set,
        get,
        {
          ...ctx,
          features: [...ctx.features, ...page.features.filter((it) => !known.has(sceneKey(it)))],
          answer: combineAnswers(ctx.answer, page),
          nextToken: stillCurrent ? page.nextToken : null,
          openCollections: page.openCollections,
        },
        true,
      );
      // The chosen dataset may have been waiting on its source, which is done now.
      const { openSectionId } = get();
      if (openSectionId) void runFallback(set, get, openSectionId, false);
    } catch {
      if (gen !== searchGen) return;
      set({
        searchContext: { ...ctx, nextToken: null },
        loadMoreError: 'Could not load more results — search again.',
      });
    } finally {
      if (gen === searchGen) set({ loadingMore: false });
    }
  },

  setSceneNameQuery: (sceneNameQuery) => set({ sceneNameQuery }),

  // Looks up one scene by its exact name in every ticked dataset at once (M3-10
  // F8): the catalogues name the same scene differently (Otto, 23.09.2026), so a
  // name usually hits one of them — no dataset stands in for another. The first
  // with the scene opens in the dropdown; every other says in its box what it
  // answered. Unlike `runSearch`, this needs neither an AOI nor a date range and
  // leaves both untouched. When no dataset has the scene only `error` changes;
  // results, selection, AOI and date range stay exactly as they were (M2-17 F4).
  findSceneByName: async () => {
    const { sceneNameQuery, selectedDatasetIds, datasets } = get();
    const name = sceneNameQuery.trim();
    if (!name) return;
    const chosen = viewableDatasets(datasets, selectedDatasetIds);
    if (chosen.length === 0) {
      const blocked = datasets.find((d) => selectedDatasetIds.includes(d.id));
      set({ error: blocked && !blocked.viewable ? `This dataset cannot be shown yet: ${blocked.reason}` : 'Pick a dataset first.' });
      return;
    }
    set({ sceneLookupLoading: true, error: null });
    const gen = searchGen;
    const answers = await Promise.all(
      chosen.map((dataset) =>
        api.fetchItem(dataset.id, name).then(
          (item) => ({ item, failure: null }),
          (e: unknown) => ({ item: undefined, failure: e as Error }),
        ),
      ),
    );
    // A search, "Clear all" or a change of the ticks came first: this answer is stale.
    if (gen !== searchGen) {
      set({ sceneLookupLoading: false });
      return;
    }
    const invalid = (failure: Error | null) => failure instanceof api.HttpError && failure.status === 400;
    const sections = chosen.map((dataset, i): ResultSection => {
      const { item, failure } = answers[i];
      const section = { datasetId: dataset.id, origin: 'name' as const, incomplete: false, groupingError: null };
      if (!item) {
        const note = !failure
          ? `No scene named "${name}".`
          : invalid(failure)
            ? 'Not a valid scene name for this dataset.'
            : `Scene lookup failed: ${failure.message}`;
        return { ...section, items: [], groups: [], notes: [note] };
      }
      try {
        return { ...section, items: [item], groups: buildGroups([item], dataset.resultsGroupBy), notes: [] };
      } catch (e) {
        // `MissingProperty` in practice; anything else must not leave the lookup locked either.
        const message = (e as Error).message;
        return { ...section, items: [], groups: [], notes: [`Grouping failed: ${message}`], groupingError: message };
      }
    });
    const open = firstSectionWithItems(sections);
    if (!open) {
      const several = chosen.length > 1;
      const failed = answers.find(({ failure }) => failure && !invalid(failure));
      const grouping = sections.find((section) => section.groupingError);
      let error: string;
      if (failed) {
        const where = several ? ` (${chosen[answers.indexOf(failed)].title})` : '';
        error = `Scene lookup failed${where}: ${failed.failure?.message}`;
      } else if (grouping) {
        error = `Grouping failed: ${grouping.groupingError}`;
      } else if (answers.every(({ failure }) => invalid(failure))) {
        error = 'Not a valid scene name.';
      } else {
        error = several
          ? `No scene named "${name}" in the selected datasets — the catalogues name the same scene differently.`
          : `No scene named "${name}" in ${chosen[0].title} — the two catalogues name the same scene differently.`;
      }
      set({ error, sceneLookupLoading: false });
      return;
    }
    const item = open.items[0];
    const dataset = chosen.find((d) => d.id === open.datasetId);
    const foundIn = sections.filter((section) => section.items.length > 0);
    const where =
      chosen.length > 1 ? ` in ${foundIn.map((x) => chosen.find((d) => d.id === x.datasetId)?.title).join(', ')}` : '';
    const bbox = item.bbox ?? (item.geometry ? polygonBbox(item.geometry) : null);
    set({
      sections,
      ...openSectionState(open),
      ...forgetSearch(),
      datasetId: open.datasetId,
      // A lookup carries no AOI, so there is no crop of the last search to keep.
      searchCrops: [],
      selectedIds: [item.id],
      panelCollapsed: true,
      playing: false,
      ...LEAVE_FOCUS,
      error: null,
      notice: `Scene ${item.id}, found by name${where}.`,
      sceneLookupLoading: false,
      ...(bbox ? { flyToBbox: bbox } : {}),
    });
    // F7 (Otto, 26.09.2026): a dataset with no browsable quicklook and no
    // meaningful coarse-tile preview shows the found scene in full
    // resolution directly — a scene lookup carries no AOI, so this is
    // always "View full selection", never a crop.
    if (dataset?.browse === 'full_resolution') await get().enterFocus(false);
  },
}));
