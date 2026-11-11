import { create } from 'zustand';

import * as api from './api';
import type { CoverageResponse, DownloadForm, PagesSoFar } from './api';
import { chosenBands, commonResolutionOf, defaultBandKeys, DEFAULT_FORM, effectiveForm, layoutBlock, layoutOf, withBandChoice, type DownloadBand } from './bandChoice';
import { downloadSceneJob, estimateSceneJob, resamplingOfOrder, sceneJobOrder, type JobNote } from './downloadJob';
import type { ResamplingPart } from './resamplingWarning';
import {
  anyMeasuresAoi,
  coverageLock,
  DEFAULT_EVALUATE,
  limitNote,
  measuresAoi,
  needsAoiBody,
  NONE_WITHIN_NOTE,
  unreadableNote,
  withinAoiLock,
  type Evaluate,
} from './aoiFilter';
import {
  bandViewportBbox,
  bboxContains,
  FOOTPRINT_FETCH_LIMIT,
  FOOTPRINT_MIN_ZOOM,
  levelForViewport,
  roundBboxToGrid,
  showFootprints,
  VIEWPORT_ROUND_LEVELS,
} from './coverage';
import type { DatasetOption } from './datasets';
import { firstVisitDatasets, knownDatasets, notAddableReason } from './catalogue';
import { prefilledDays, todayUtc } from './dateBounds';
import { acquisitionNote, datasetsFrom, defaultRenderOf, preferredGeoreferencedAsset, quicklookPlan, standardAssetsOf } from './datasets';
import { fallbackNotice, findFallback, fullDayRange, NO_FALLBACK_MESSAGE } from './dateFallback';
import {
  assetHostsOf,
  cropAssetsOf,
  decideDownloadOutcomeForLayer,
  downloadRequestFor,
  downloadRequestForSelection,
  DRAW_AOI_TO_CROP,
  isCogFormat,
  mixedBandsNote,
  noOriginalsReason,
  originalFileLinks,
  type DownloadPass,
  type ExportOffer,
  type OriginalFileLink,
} from './download';
import { polygonBbox, quicklookCoords, searchArea } from './geoUtils';
import { buildGroups, groupIndexOfItem, groupItemIdsFor } from './grouping';
import { datesOfIds, dateOf, knownItems } from './layerDate';
import { flipNext, flipStart } from './layerFlip';
import type { LayerOverlay, LayerRestore, MapLayer, ResultLayerInfo } from './layers';
import { bandLayerOf, isResultExpired, restyledTileUrl } from './resultLayer';
import { buildTileUrl, footprintsFC } from './mapLayers';
import { assetOfLook, bandAssetsOf, withAsset } from './viewBand';
import { indexKeyOf, mosaicKeyOf, MAX_MOSAIC_OPERATOR_ASSETS, orderedPass, orderKeyOf, passesOf, stackLikeView } from './mosaic';
import type { Mosaics, SceneEntry } from './mosaic';
import { ensureSelection, withSelection } from './mosaicSelection';
import type { IndexPreset } from './indexPresets';
import type { BasemapId } from './basemaps';
import type { OverlayId, Overlays } from './overlays';
import type { Appearance, Projection, Theme } from './preferences';
import { loadAddedDatasets, loadAppearance, loadBasemap, loadOverlays, loadProjection, loadResultsOnMap, loadTerrain, loadTipLevel, migrateReliefBasemap, saveAddedDatasets, saveAppearance, saveBasemap, saveOverlays, saveProjection, saveResultsOnMap, saveTerrain, saveTipLevel, themeOf } from './preferences';
import { setTipLevel, type TipLevel } from './tipLevel';
import { zoomTarget } from './zoomSelection';
import type { Percent } from './percentRange';
import { checkPercent, DEFAULT_PERCENT, NO_RANGE_AT_PERCENT, rescaleAtPercent, samePercent, type RangeUnit } from './percentRange';
import { channelsAtOwnPercent, samePercents, CHANNEL_COUNT, CHANNEL_NAMES, type ChannelRange } from './channels';
import { buildExportOrder, isArea, trueColorOf } from './processingOrder';
import { appliedRenderFrom, autoRescale, colourChannelsOf, colourInPercent, lookChanged, lookOfPendingFields, pendingFieldsOf } from './render';
import type { ResultSection, SectionSearchAnswer } from './sections';
import {
  buildSections,
  combineAnswers,
  firstSectionWithItems,
  hasResultsPanel,
  LOAD_MORE_NOTE,
  NO_SCENES_NOTE,
  needsFallback,
  withSourceState,
} from './sections';
import { overlaysOfPass, substituteOverlaysOf, underlaysOf } from './searchLayers';
import { clampResultsAt, moveEntry, moveEntryTo, resultsAtAfterAdding, resultsAtAfterRemoving } from './resultsEntry';
import {
  filterQuery,
  hasFilterError,
  isEmptyQuery,
  isSet,
  searchCapabilitiesOf,
  searchFiltersOf,
  type FilterInput,
  type FilterInputs,
  type FilterQuery,
  type FilterQueryByCollection,
} from './searchFilters';
import { imagesOf, satellitesOf, sectionsForView, type ViewImage } from './viewImages';
import { viewDates } from './viewKind';
import { layerOfView, sameRender } from './viewLayer';
import { downloadIndexCrop, estimateIndexDownload, indexOfferedFor, type IndexNote } from './indexDownload';
import { assetsOfExpression, indexBlockOf, indexLookOf, indexNote, indexStatisticsUrl, viewIndexOf } from './viewIndex';
import { canonicalJson } from './processing';
import { areaQuestionOf, measureView, type ViewMeasure } from './viewMeasure';
import type { AppliedRender, Bbox, DownloadedInfo, StacItem, TimeStepGroup, ToolMode } from './types';
import { counted } from './plural';
import { fieldNumber } from './numberFormat';

const PAGE_LIMIT = 100;

// Numbers the export offers of the download dialog (`ExportOffer.id`).
let exportOffers = 0;
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
export function selectionItemsFrom(s: Pick<AppState, 'groups' | 'activeGroupIndex' | 'selectedIds' | 'items'>): StacItem[] {
  const group = s.groups[s.activeGroupIndex];
  const picked = s.items.filter((it) => s.selectedIds.includes(it.id));
  return picked.length ? picked : (group?.items ?? []);
}

// The scenes of the image the view shows, when a download is asked for it and not for the ticks of the list (`openDownloadForView`).
export interface DownloadView {
  datasetId: string;
  items: StacItem[];
  label: string;
}

// The ticks that are not on scenes of another dataset of the search (NM4-50): the ticks stay over a change of the
// dataset, and what acts on the picked scenes — the bar of the selection, a view, a job — acts on the open one's.
export function ticksOfOpen(s: Pick<AppState, 'sections' | 'openSectionId' | 'selectedIds'>): string[] {
  if (s.selectedIds.length === 0) return s.selectedIds;
  const others = s.sections.filter((section) => section.datasetId !== s.openSectionId);
  if (others.length === 0) return s.selectedIds;
  const elsewhere = new Set(others.flatMap((section) => section.items.map((it) => it.id)));
  return s.selectedIds.filter((id) => !elsewhere.has(id));
}

// Every tick on a scene of the last search, whatever dataset it is in (NM4-53): what the buttons that start a view take.
export function ticksOfSearch(s: Pick<AppState, 'sections' | 'openSectionId' | 'datasetId' | 'items' | 'groups' | 'selectedIds'>): string[] {
  if (s.selectedIds.length === 0 || s.sections.length === 0) return s.selectedIds;
  const known = new Set(sectionsForView(s).flatMap((section) => section.items.map((it) => it.id)));
  return s.selectedIds.filter((id) => known.has(id));
}

// The scenes a view is made of, by dataset: the ticked ones of every dataset of the search, or with nothing ticked the
// time step that is open.
export function viewSelectionFrom(
  s: Pick<AppState, 'sections' | 'openSectionId' | 'datasetId' | 'items' | 'groups' | 'activeGroupIndex' | 'selectedIds'>,
): { datasetId: string; items: StacItem[] }[] {
  const ticked = new Set(ticksOfSearch(s));
  const picked = sectionsForView(s)
    .map((section) => ({ datasetId: section.datasetId, items: section.items.filter((it) => ticked.has(it.id)) }))
    .filter((section) => section.items.length > 0);
  if (picked.length > 0) return picked;
  const open = s.openSectionId ?? s.datasetId;
  const group = s.groups[s.activeGroupIndex];
  return open && group ? [{ datasetId: open, items: group.items }] : [];
}

// The images of the view as it is now.
export function viewImagesOf(s: Pick<AppState, 'downloaded' | 'sections' | 'openSectionId' | 'datasetId' | 'items' | 'groups' | 'datasets'>): ViewImage[] {
  return imagesOf(s.downloaded, sectionsForView(s), s.datasets);
}

// The image the view shows: the one chosen, else the first (a view opened from a layer chooses none).
export function shownImageOf(images: readonly ViewImage[], key: string | null): ViewImage | null {
  return images.find((image) => image.key === key) ?? images[0] ?? null;
}

// What the map draws of the view: the scenes of the image that is shown, in the dataset of that image, with the scenes
// and the time steps of the whole search for the quicklook under them and for the outlines.
export function shownViewOf(
  s: Pick<AppState, 'downloaded' | 'sections' | 'openSectionId' | 'datasetId' | 'items' | 'groups' | 'datasets' | 'shownImage'>,
) {
  const sections = sectionsForView(s);
  const image = shownImageOf(imagesOf(s.downloaded, sections, s.datasets), s.shownImage);
  const datasetId = image?.datasetId ?? s.datasetId;
  return {
    downloaded: image ? Object.fromEntries(image.ids.map((id) => [id, s.downloaded[id]])) : s.downloaded,
    dataset: s.datasets.find((d) => d.id === datasetId) ?? null,
    items: sections.flatMap((section) => section.items),
    groups: sections.flatMap((section) => section.groups),
  };
}

// The image to start with (NM4-53, Otto): that of the time step open in the results where the view has it, else the
// earliest of the open dataset, else the first of all.
export function firstImageOf(images: readonly ViewImage[], s: Pick<AppState, 'openSectionId' | 'datasetId' | 'groups' | 'activeGroupIndex'>): ViewImage | null {
  const open = s.openSectionId ?? s.datasetId;
  const here = images.filter((image) => image.datasetId === open);
  const label = s.groups[s.activeGroupIndex]?.label;
  return here.find((image) => image.groupLabel === label) ?? here[0] ?? images[0] ?? null;
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
// The last question `refreshCoverage` sent (dataset, level, area, dates, filters), to leave out its repeats.
let coverageQuestion = '';

// M3-19 §3: the last few viewport answers, so a pan/zoom that stays inside a bbox already asked for skips the request instead of
// repeating it. Keyed on dataset/level/datetime/filters. Module-level like `coverageGen` above: it holds no more than the interaction
// needs to feel warm, nothing a reload should have to restore.
interface ViewportCoverageEntry {
  datasetId: string;
  level: number;
  datetime: string | undefined;
  // The search filters it was asked with (DS-02c), `JSON.stringify` of the query: another filter is another map.
  filters: string;
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
  filters: string,
  viewport: Bbox,
): ViewportCoverageEntry | undefined {
  return viewportCoverageCache.find(
    (e) =>
      e.datasetId === datasetId &&
      e.level === level &&
      e.datetime === datetime &&
      e.filters === filters &&
      bboxContains(e.bbox, viewport),
  );
}

function rememberViewportCoverage(entry: ViewportCoverageEntry): void {
  viewportCoverageCache = [entry, ...viewportCoverageCache].slice(0, VIEWPORT_CACHE_SIZE);
}

function scheduleCoverageRefresh(set: SetState, get: GetState): void {
  window.clearTimeout(coverageDebounceHandle);
  coverageDebounceHandle = window.setTimeout(() => void refreshCoverage(set, get), COVERAGE_DEBOUNCE_MS);
}

// Fetches the density grid for the current dataset and date filter over what is in view (M2-07c), and — only once the backend's
// `footprints_advised` and the frontend's own zoom brake (coverage.ts) both agree — the real scene footprints to replace it with.
//
// UI-04 part 4 (Otto, 4.11.2026, replacing the rule of M3-19 "with an AOI, over the AOI"): the coverage map does not depend on the AOI. It
// always shows the coverage of the visible map extent — the whole world at a small zoom — whether an AOI is drawn or not, and the request
// carries no AOI (`api.fetchCoverage` has no way to). The extent is banded across the antimeridian and rounded outward to a coarser block
// (`coverage.ts`) so nearby viewports ask the same question; the level is derived from the viewport's own size so that roughly the same
// number of cells always covers the screen (`levelForViewport`, the rule of #286). The filters of "Advanced search" count as before.
//
// A failed density fetch clears the layer (nothing to fall back to); a failed *footprints* fetch instead leaves `coverage` in place and
// `coverageFootprints` at `null`, so `MapView`'s `coverageDisplayFor` falls back to the density it already has rather than losing the
// whole layer over a second, optional request.
async function refreshCoverage(set: SetState, get: GetState): Promise<void> {
  const s = get();
  // The coverage map has a dataset of its own (chosen at the "Coverage" button,
  // M3-10), independent of the dataset whose results the map shows.
  const datasetId = s.coverageDatasetId ?? s.datasetId;
  if (!s.showCoverage || !datasetId) {
    set({ coverage: null, coverageFootprints: null, coverageError: null, coverageLoading: false });
    return;
  }
  const datetime = buildDatetime(s.dateFrom, s.dateTo);
  // The filters of the coverage's dataset (DS-02c, adr/0004 K1): the map counts what the search would find.
  // "AOI coverage" is judged from the outlines of scenes the search found; the map counts at the source and cannot (DS-03c).
  const query = filterQueryOf(s, datasetId, withinFor(s, datasetId, 'coverage'), true);
  const filters = JSON.stringify(query);

  if (s.viewportBbox === null || s.viewportSize === null) return; // map not ready yet
  const level = levelForViewport(s.mapZoom, s.viewportSize.width, s.viewportSize.height);
  const viewport = bandViewportBbox(s.viewportBbox); // the raw (unrounded) extent, for the reuse check
  const bbox = roundBboxToGrid(viewport, level - VIEWPORT_ROUND_LEVELS);

  // The same question as the one on its way or on the map is not sent again (#286). Whether the zoom allows footprints is part of it, since
  // the level can stay the same across that brake. The AOI is no part of it: drawing, changing or clearing it asks nothing new.
  const question = JSON.stringify([datasetId, level, bbox, datetime, filters, s.mapZoom >= FOOTPRINT_MIN_ZOOM]);
  if (question === coverageQuestion && (s.coverageLoading || s.coverage !== null)) return;
  coverageQuestion = question;

  const gen = ++coverageGen;

  // An answer kept without footprints is no answer once the zoom allows them and the source advises them: it is asked again.
  const cached = cachedViewportCoverage(datasetId, level, datetime, filters, viewport);
  if (cached && (cached.footprints !== null || !showFootprints(cached.coverage, s.mapZoom))) {
    set({ coverage: cached.coverage, coverageFootprints: cached.footprints, coverageLoading: false, coverageError: null });
    return;
  }

  set({ coverageLoading: true, coverageError: null });
  let coverage: CoverageResponse;
  try {
    coverage = await api.fetchCoverage({ datasetId, zoom: level, bbox, datetime, query });
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
      const { features } = await api.searchAllPages(
        { collections: [datasetId], bbox, datetime, ...queryByCollectionOf({ [datasetId]: query }) },
        FOOTPRINT_FETCH_LIMIT,
      );
      if (gen === coverageGen) {
        footprints = footprintsFC(features);
        set({ coverageFootprints: footprints });
      }
    } catch {
      // Left at `null` — the density fill this dataset/viewport already has
      // stays on screen (E5: a failed extra fetch degrades, it doesn't 404).
    }
  }
  if (gen === coverageGen) {
    rememberViewportCoverage({ datasetId, level, datetime, filters, bbox, coverage, footprints });
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
  const base = `${counted(features.length, 'scene')} in ${counted(groups.length, 'time step')}.`;
  if (numberMatched !== null && numberMatched > features.length) {
    return canLoadMore
      ? `${base} ${numberMatched} matched in total.`
      : `${base} ${numberMatched} matched in total — narrow the area or date range to see the rest.`;
  }
  return base;
}

// A layer the processing panel pins (M4-13c-2): a picture made from scenes, not
// the scenes themselves.
export interface DerivedLayer {
  name: string;
  derived: NonNullable<MapLayer['derived']>;
  note?: string;
  result?: ResultLayerInfo;
  overlays: LayerOverlay[];
  // The scenes the picture was made from.
  itemIds: string[];
  cropToAoi: boolean;
  // The acquisition date it shows; where it is left out, the scenes are looked up (NM4-65 part 3).
  date?: string | null;
}

// A layer belongs to the dataset it was pinned from (F4): choosing it makes that
// dataset the active one — and opens its section, if the last search has one — so
// the list and the controls speak of the layer's own scenes. A dataset that is not
// ticked (any more) is ticked by this, without touching the results, so the active
// dataset stays one of the ticked ones.
function layerDatasetState(s: AppState, r: LayerRestore) {
  return datasetState(s, r.datasetId);
}

// The same for a dataset by its id: what the view's processing job needs of the open section (NM4-53).
function datasetState(s: AppState, datasetId: string | null) {
  const r = { datasetId };
  const section = r.datasetId ? s.sections.find((x) => x.datasetId === r.datasetId) : undefined;
  const dataset = r.datasetId ? s.datasets.find((d) => d.id === r.datasetId) : undefined;
  const tickable = !!dataset?.viewable && !s.selectedDatasetIds.includes(dataset.id);
  // A ticked dataset is one of "Search and area" (UI-05): a layer's dataset that was removed comes back.
  if (tickable) addToPanel(dataset.id);
  const becomesActive = dataset && (dataset.viewable || s.selectedDatasetIds.includes(dataset.id)) ? dataset.id : null;
  return {
    ...(tickable
      ? { selectedDatasetIds: s.datasets.filter((d) => d.id === dataset.id || s.selectedDatasetIds.includes(d.id)).map((d) => d.id) }
      : {}),
    ...(section ? openSectionState(section) : becomesActive && becomesActive !== s.datasetId ? openSectionState(null) : {}),
    ...(becomesActive ? { datasetId: becomesActive } : {}),
  };
}

// Puts a dataset at the end of "Search and area" and saves the list (UI-05 §4.2, F4): only one that can be added, once.
// Returns whether it is there now.
function addToPanel(datasetId: string): boolean {
  const s = useAppStore.getState();
  const dataset = s.datasets.find((d) => d.id === datasetId);
  if (!dataset || notAddableReason(dataset) !== null) return false;
  if (s.addedDatasetIds.includes(datasetId)) return true;
  const addedDatasetIds = [...s.addedDatasetIds, datasetId];
  useAppStore.setState({ addedDatasetIds });
  saveAddedDatasets(addedDatasetIds);
  return true;
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

// What leaving the full-resolution view resets — the same set `exitFocus` clears. The view of a
// result goes with it: both stand in the place of the search results.
const LEAVE_FOCUS = {
  focusMode: false,
  viewOpacity: 1,
  viewLayerId: null,
  viewOfLayer: false,
  resultViewLayerId: null,
  cropToAoi: false,
  viewAoi: null,
  downloaded: {},
  shownImage: null,
  viewLooks: {},
  savedLooks: {},
  appliedRender: {},
  pendingColormapName: '',
  pendingVmin: '',
  pendingVmax: '',
  pendingChannels: [] as ChannelRange[],
  pendingIndex: '',
  pendingBand: '',
  pendingUnit: 'value' as RangeUnit,
  pendingPercentLow: DEFAULT_PERCENT.low,
  pendingPercentHigh: DEFAULT_PERCENT.high,
  enhance: null,
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

// The search filters the user has set and got right, for one dataset or for these datasets (DS-02c). A filter with a
// wrong field is not sent: the search is held back until it is right (`searchFiltersInvalid`), the coverage map
// goes without it meanwhile.
type FilterState = Pick<AppState, 'datasets' | 'searchFilters'>;

function filterQueryOf(s: FilterState, datasetId: string, within?: 'aoi' | 'skip', withoutArea = false): FilterQuery {
  const dataset = s.datasets.find((d) => d.id === datasetId);
  return dataset ? filterQuery(searchFiltersOf(dataset.collection), s.searchFilters[datasetId], within, withoutArea) : {};
}

// What the switch "Filter within AOI only" does to a request (DS-03b): where it is on and can be used (an area and a date
// range with both ends) the search asks the filters that depend on the area inside the AOI, and the coverage map leaves
// them out, which it cannot measure; where it cannot be used, it counts for nothing and the ranges are the scene's.
type WithinState = Pick<AppState, 'aoi' | 'dateFrom' | 'dateTo' | 'searchWithin'>;

const withinFor = (s: WithinState, datasetId: string, request: 'search' | 'coverage'): 'aoi' | 'skip' | undefined =>
  s.searchWithin[datasetId] === true && withinAoiLock(s) === null ? (request === 'search' ? 'aoi' : 'skip') : undefined;

// What each of these datasets is asked with, `{}` where nothing is set. "AOI coverage" goes only with an AOI it can use.
function filterQueriesOf(s: FilterState & WithinState, ids: readonly string[]): FilterQueryByCollection {
  const withoutArea = coverageLock(s) !== null;
  return Object.fromEntries(ids.map((id) => [id, filterQueryOf(s, id, withinFor(s, id, 'search'), withoutArea)]));
}

// What a search on screen was asked with, to tell whether it still is what the fields say.
function askedState(s: FilterState & WithinState & Pick<AppState, 'searchEvaluate'>, ids: readonly string[]): string {
  const asked = filterQueriesOf(s, ids);
  // The raw settings too: a change of "Evaluate" or of the switch with no filter set is a change of the fields as well.
  return JSON.stringify([asked, evaluationOf(s, asked), s.searchEvaluate, s.searchWithin]);
}

// How the search judges the filters (DS-03c): the datasets whose registry offers judging per pass and that are asked something
// are judged per pass when the user chose it. They are sent as `earthx:evaluate`, once for the whole search; a search per scene
// sends nothing, which is what the server does without it.
function evaluationOf(
  s: Pick<AppState, 'datasets' | 'searchEvaluate'>,
  asked: FilterQueryByCollection,
): { evaluate?: 'pass'; judgedByPass?: string[] } {
  if (s.searchEvaluate !== 'pass') return {};
  const judged = Object.entries(asked)
    .filter(([id, query]) => !isEmptyQuery(query) && s.datasets.some((d) => d.id === id && searchCapabilitiesOf(d.collection).evaluate))
    .map(([id]) => id);
  return judged.length > 0 ? { evaluate: 'pass', judgedByPass: judged } : {};
}

// `{queryByCollection}` for a request, or nothing when no dataset has a filter set: a search without filters
// keeps the body it always had.
function queryByCollectionOf(queries: FilterQueryByCollection): { queryByCollection?: FilterQueryByCollection } {
  const named = Object.entries(queries).filter(([, query]) => !isEmptyQuery(query));
  return named.length > 0 ? { queryByCollection: Object.fromEntries(named) } : {};
}

// Whether a ticked dataset has a filter with a wrong field. "Search" waits for it (plan §6.7).
export function searchFiltersInvalid(s: Pick<AppState, 'datasets' | 'selectedDatasetIds' | 'searchFilters'>): boolean {
  return s.datasets.some(
    (d) => s.selectedDatasetIds.includes(d.id) && hasFilterError(searchFiltersOf(d.collection), s.searchFilters[d.id]),
  );
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

// The walk of a search that asks for the cloud share in the AOI (DS-03b), while it runs: "Stop" ends it, and so does
// everything that makes the search on screen something the control panel no longer asks (`dropPageToken`, `forgetSearch`).
let walk: AbortController | null = null;
const stopWalk = () => walk?.abort();

const isAbort = (e: unknown): boolean => e instanceof DOMException && e.name === 'AbortError';

// Item ids are unique only within a collection.
const sceneKey = (item: StacItem) => `${item.collection ?? ''}\u0000${item.id}`;

// The overlays for these scenes, split by time step and stacked the way the view draws them
// (`stackLikeView`); `null` while the mosaic of one is not known.
function overlaysOfEntries(
  s: AppState,
  entries: SceneEntry[],
  clip: GeoJSON.Geometry | null,
  look: AppliedRender = s.appliedRender,
): LayerOverlay[] | null {
  const sections = sectionsForView(s);
  const groups = sections.flatMap((section) => section.groups);
  const items = sections.flatMap((section) => section.items);
  const passList = passesOf(entries, groups);
  const overlays = passList.map((first) => {
    const datasetId = first[0][1].datasetId;
    const pass = orderedPass(datasetId, first, s.mosaics);
    const dataset = s.datasets.find((d) => d.id === datasetId);
    return overlaysOfPass(datasetId, pass, s.mosaics, look, clip, underlaysOf(pass, items, dataset, clip), viewIndexOf(look, dataset?.collection));
  });
  if (overlays.some((o) => o === null)) return null;
  // The substitute of a dataset below its first level lies under everything the layer draws of its own.
  const datasetIds = passList.map((first) => first[0][1].datasetId);
  const substitutes = substituteOverlaysOf(datasetIds, s.datasets, look, clip);
  return [...substitutes, ...stackLikeView(overlays).flatMap((o) => o ?? [])];
}

// The computing of the index of a download, which closing the dialog stops (`indexDownload.ts`).
let indexDownloadAbort: AbortController | null = null;

// The estimate and the run of the job of whole scenes (NM4-75, `downloadJob.ts`), which closing the dialog stops, and the wait before
// an estimate is asked for after a change of the choice.
let downloadJobAbort: AbortController | null = null;
let downloadEstimateAbort: AbortController | null = null;
let downloadJobTimer: ReturnType<typeof setTimeout> | undefined;
const DOWNLOAD_ESTIMATE_DELAY_MS = 300;
// What goes on once the person has confirmed the resampling warning of a download.
let afterResampling: (() => void) | null = null;

// Numbers the requests for a table of bands: only the answer to the last one is taken, and none after the dialog is closed.
let bandsRequest = 0;

// The fields of the choice of bands for a dialog that opens: no table yet, `loading` while the platform is asked for it
// (`loadDownloadBands`).
function bandChoiceFor(loading: boolean) {
  // An answer still on its way is for a dialog that is no more.
  bandsRequest += 1;
  return {
    downloadTable: [] as DownloadBand[],
    downloadBandsLoading: loading,
    downloadBands: [] as string[],
    downloadForm: DEFAULT_FORM,
    downloadCommonResolution: null,
    downloadJobNote: null,
    downloadResampling: null,
    downloadStarted: false,
  };
}

// Asks the platform for the bands of the scenes the dialog is about (the first few of them). "Download" stays locked until the table is
// in; where it cannot be had the dialog says so and offers no list, as for a dataset with no file per band.
async function loadDownloadBands(datasetId: string, itemIds: readonly string[]): Promise<void> {
  const request = ++bandsRequest;
  try {
    const table = await api.fetchBands(datasetId, itemIds);
    if (request === bandsRequest) {
      useAppStore.setState({ downloadTable: table, downloadBands: defaultBandKeys(table), downloadBandsLoading: false });
      // Bands of one resolution are a job from the start: what it costs is asked for at once.
      refreshJobEstimate();
    }
  } catch (e) {
    if (request === bandsRequest) useAppStore.setState({ downloadBandsLoading: false, error: `Could not load the bands: ${(e as Error).message}` });
  }
}

function stopDownloadJob(): void {
  clearTimeout(downloadJobTimer);
  downloadEstimateAbort?.abort();
  downloadEstimateAbort = null;
  downloadJobAbort?.abort();
  downloadJobAbort = null;
}

// The dataset the open download dialog is about.
function downloadDatasetOf(s: AppState): DatasetOption | undefined {
  const layer = s.layers.find((l) => l.id === s.downloadDialogLayerId);
  const id = s.downloadSelection ? (s.downloadView?.datasetId ?? s.datasetId) : layer?.restore.datasetId;
  return s.datasets.find((d) => d.id === id);
}

// What a pin is made from, to tell on arrival whether the view is still the one it was asked in.
const pinKey = (s: AppState) =>
  JSON.stringify([s.datasetId, s.cropToAoi, s.selectedIds, Object.keys(s.downloaded), s.layers.length, s.shownImage]);

// A selection inside the view is another mosaic than the one the view loaded (a part of its scenes), and
// one the view has not loaded yet is still on its way. Pinning waits for it ("Loading…") and then pins by
// itself; if the tiler cannot give it, `fetchMosaics` has said why and nothing is pinned. A pin made
// meanwhile from another selection, or another pin that changed the list, is not repeated.
function pinWhenLoaded(set: SetState, get: GetState, lists: { entries: SceneEntry[]; index: IndexPreset | null }[], again: () => void): void {
  const s = get();
  const key = pinKey(s);
  const groups = sectionsForView(s).flatMap((section) => section.groups);
  const requests = lists.flatMap(({ entries, index }) => passesOf(entries, groups).map((pass) => ({ datasetId: pass[0][1].datasetId, entries: pass, index })));
  set({ pinLoading: true, error: null });
  void fetchMosaics(set, get, requests).then(() => {
    const now = get();
    set({ pinLoading: false });
    if (pinKey(now) !== key) return;
    // An index whose selection the tiler did not take is not a failure here: pinning again says why it cannot be pinned.
    const failed = requests.some((r) => {
      const mosaic = mosaicKeyOf(r.datasetId, r.entries);
      return mosaic !== null && !now.mosaics[mosaic];
    });
    if (!failed) again();
  });
}

type LookSource = Pick<AppState, 'datasets' | 'sections' | 'openSectionId' | 'datasetId' | 'items' | 'groups'>;

// The standard visualisation of a dataset as the look of one of its images ("RGB without colormap" for Sentinel-2, Otto
// 31.10.2026). Read off the image's first scene: with `first_present` an image of HH scenes has the stretch of `hh`, not of
// the first band of the list (DS-04c); the scenes of one image are one pass and carry the same bands.
function defaultLookOf(s: LookSource, image: Pick<ViewImage, 'datasetId' | 'ids'>): AppliedRender {
  const dataset = s.datasets.find((d) => d.id === image.datasetId);
  const item = sectionsForView(s).flatMap((section) => section.items).find((it) => it.id === image.ids[0]);
  const render = dataset ? defaultRenderOf(dataset.collection, item) : null;
  return render ? appliedRenderFrom(render) : {};
}

// The look an image is drawn with: for the one that is shown, what the map shows; for another, the first it has of
// its own unsaved look, the look saved for its dataset and the standard one.
export function lookOfImage(
  s: LookSource & Pick<AppState, 'appliedRender' | 'shownImage' | 'viewLooks' | 'savedLooks'>,
  image: ViewImage,
  shown: ViewImage | null,
): AppliedRender {
  if (shown && image.key === shown.key) return s.appliedRender;
  return s.viewLooks[image.key] ?? s.savedLooks[image.datasetId] ?? defaultLookOf(s, image);
}

// Moves the view to another image: what the one left shows is kept when it differs from what its dataset would show
// without it, and the fields and the map take the look of the one reached.
function moveToImage(s: AppState, target: ViewImage, from: ViewImage | null): Partial<AppState> {
  const viewLooks = { ...s.viewLooks };
  if (from) {
    const baseline = s.savedLooks[from.datasetId] ?? defaultLookOf(s, from);
    if (sameRender(s.appliedRender, baseline)) delete viewLooks[from.key];
    else viewLooks[from.key] = s.appliedRender;
  }
  const look = viewLooks[target.key] ?? s.savedLooks[target.datasetId] ?? defaultLookOf(s, target);
  return { shownImage: target.key, viewLooks, appliedRender: look, ...pendingFieldsOf(look) };
}

// Whether "Save" would change anything: another image of the dataset shown does not look like the fields ask for.
export function datasetSavable(s: AppState): boolean {
  const images = viewImagesOf(s);
  const shown = shownImageOf(images, s.shownImage);
  if (!shown) return false;
  return images.some((image) => image.datasetId === shown.datasetId && image.key !== shown.key && lookChanged(lookOfImage(s, image, shown), s));
}

// The first scene of the image the view shows (of the view where nothing is shown yet): the one its range is measured on.
// Whether the fields stand for the colour picture of the dataset ("RGB"): no band, no index, and a dataset with a true-colour one.
export function colourView(s: AppState): boolean {
  if (s.pendingBand || s.pendingIndex) return false;
  const { info } = firstSceneOfView(s);
  return trueColorOf(s.datasets.find((d) => d.id === info?.datasetId)?.collection) !== null;
}

// Whether "Enhance contrast" is on: the fields still ask for what it put in them, the usual pair in percentiles (in every channel of a
// colour picture) for the picture it was pressed for. The values those percentiles give do not count: they come with "Apply".
export function enhanceOn(s: AppState): boolean {
  if (!s.enhance) return false;
  const asked = lookOfPendingFields(s);
  const kept = s.enhance.look;
  if ((kept.colormapName || undefined) !== asked.colormapName || (kept.index || undefined) !== asked.index || (kept.band || undefined) !== asked.band) return false;
  return asked.percentChannels ? asked.percentChannels.length === CHANNEL_COUNT && asked.percentChannels.every((pair) => samePercent(pair, DEFAULT_PERCENT)) : samePercent(asked.percent, DEFAULT_PERCENT);
}

// What the fields of the view are measured with (`autoStretch`, "Enhance contrast", the histograms of "Scale"): the area of the crop where
// the view is cropped to the AOI and the tiler takes it (UI-03e), else the first scene of the image shown, the index of the fields as the
// tile route computes it, else the asset of the band in the fields. `null` before a scene is open. One object for one state of its inputs,
// so that a component can select it.
let measureKept: { inputs: unknown[]; value: ViewMeasure | null } | null = null;

export function viewMeasure(s: AppState): ViewMeasure | null {
  const inputs = [s.shownImage, s.downloaded, s.sections, s.openSectionId, s.datasetId, s.items, s.groups, s.datasets, s.pendingBand, s.pendingIndex, s.cropToAoi, s.viewAoi];
  if (measureKept && measureKept.inputs.every((input, i) => Object.is(input, inputs[i]))) return measureKept.value;
  const value = measureOfView(s);
  measureKept = { inputs, value };
  return value;
}

function measureOfView(s: AppState): ViewMeasure | null {
  const { itemId, info } = firstSceneOfView(s);
  if (!info || itemId === undefined) return null;
  const collection = s.datasets.find((d) => d.id === info.datasetId)?.collection;
  const index = viewIndexOf({ index: s.pendingIndex }, collection);
  const asset = assetOfLook(info, { band: s.pendingBand || undefined });
  const sceneUrl = index ? indexStatisticsUrl(info.datasetId, itemId, index) : api.buildStatisticsUrl(info.datasetId, itemId, asset);
  const shown = shownImageOf(viewImagesOf(s), s.shownImage);
  const ids = shown?.ids ?? [itemId];
  const known = new Map(sectionsForView(s).flatMap((section) => section.items).map((item) => [item.id, item]));
  const items = ids.flatMap((id) => known.get(id) ?? []);
  const asked = areaQuestionOf({ datasetId: info.datasetId, collection, items: items.length === ids.length ? items : [], aoi: s.cropToAoi ? s.viewAoi : null, index, asset });
  const area = asked && 'order' in asked ? asked : null;
  const skipped = asked && 'reason' in asked ? asked.reason : null;
  return { sceneUrl, area, skipped, key: area ? `${sceneUrl}\n${canonicalJson(area.order)}` : sceneUrl };
}

function firstSceneOfView(s: AppState): { itemId: string | undefined; info: DownloadedInfo | undefined } {
  const shown = shownImageOf(viewImagesOf(s), s.shownImage);
  const itemId = shown?.ids[0] ?? Object.keys(s.downloaded)[0];
  return { itemId, info: itemId === undefined ? undefined : s.downloaded[itemId] };
}

// The layer drawn with a look (NM4-45, NM4-54): its scenes from the asset of the band the look names (or the index it computes), its
// rasters made again, its quicklook underlays kept where the look has none. `{ problem }` where that cannot be done now.
type LayerDrawn = { overlays: LayerOverlay[]; restore: { downloaded: MapLayer['restore']['downloaded']; appliedRender: AppliedRender } };

// The layer drawn with a look, at once where the mosaics of its bands are known: `{ need }` names the passes whose mosaic has to be
// asked for first, `{ problem }` says why it cannot be done.
function layerDraw(
  get: GetState,
  layer: MapLayer,
  render: AppliedRender,
): LayerDrawn | { problem: string } | { need: MosaicRequest[] } {
  const s = get();
  const clip = layer.restore.cropToAoi ? layer.restore.aoi : null;
  const entries = Object.entries(layer.restore.downloaded).map(([id, info]): SceneEntry => [id, withAsset(id, info, assetOfLook(info, render))]);
  const collection = s.datasets.find((d) => d.id === layer.restore.datasetId)?.collection;
  const index = viewIndexOf(render, collection);
  const groups = sectionsForView(s).flatMap((section) => section.groups);
  const block = index && layer.restore.datasetId ? indexBlockOf({ datasetId: layer.restore.datasetId, entries, groups, mosaics: s.mosaics, preset: index, mapZoom: Infinity }) : null;
  if (index && block) return { problem: `${indexNote(block, index.name)}. Start a job in Processing for the whole scenes.` };
  const fresh = overlaysOfEntries({ ...s, appliedRender: render }, entries, clip);
  if (fresh === null) return { need: passesOf(entries, groups).map((pass) => ({ datasetId: pass[0][1].datasetId, entries: pass, index })) };
  const current = s.layers.find((l) => l.id === layer.id) ?? layer;
  const quicklooks = index ? [] : current.overlays.some((o) => o.kind === 'image') ? current.overlays.filter((o) => o.kind === 'image') : fresh.filter((o) => o.kind === 'image');
  return { overlays: [...quicklooks, ...fresh.filter((o) => o.kind === 'raster')], restore: { downloaded: Object.fromEntries(entries), appliedRender: { ...render } } };
}

// The same, asking for the mosaic of another band first where it has to (NM4-45).
async function layerDrawnWith(set: SetState, get: GetState, layer: MapLayer, render: AppliedRender): Promise<LayerDrawn | { problem: string }> {
  let drawn = layerDraw(get, layer, render);
  if ('need' in drawn) {
    await fetchMosaics(set, get, drawn.need);
    drawn = layerDraw(get, layer, render);
  }
  if ('need' in drawn) return { problem: 'The layer cannot be saved yet: its scenes are still loading.' };
  return drawn;
}

// "Apply" with percentiles in the fields (NM4-65 part 4): the tiler measures the two percentiles on the first scene of the image
// shown (the index of the fields as it will be drawn), the values go into the fields and the look. What is drawn is the values;
// the look keeps the percentiles for the fields to show "%" again.
async function applyPercentRender(set: SetState, get: GetState): Promise<void> {
  const s = get();
  // A colour picture keeps a unit for each channel (UI-03e): each channel typed in percentiles is taken at its own pair and its own values.
  const own = colourView(s) ? colourChannelsOf(s) : null;
  const pairs: { low: number; high: number }[] = [];
  for (const [index, channel] of (own ?? [{ percent: { low: s.pendingPercentLow, high: s.pendingPercentHigh } }]).entries()) {
    if (!channel.percent) continue;
    const checked = checkPercent(channel.percent);
    if ('problem' in checked) {
      set({ notice: own ? `${CHANNEL_NAMES[index]}: ${checked.problem}` : checked.problem });
      return;
    }
    pairs.push(checked);
  }
  const measure = viewMeasure(s);
  if (!measure) return;
  const asked = [...new Set(pairs.flatMap(({ low, high }) => [low, high]))].filter((n) => n !== 0 && n !== 100);
  set({ focusLoading: true });
  try {
    const { statistics: stats } = await measureView(measure, { percentiles: asked });
    if (own) {
      const made = channelsAtOwnPercent(Object.values(stats), own);
      if (!made) {
        set({ notice: NO_RANGE_AT_PERCENT });
        return;
      }
      set({ pendingVmin: made[0].vmin, pendingVmax: made[0].vmax, pendingChannels: made, pendingUnit: 'value' });
    } else {
      const range = rescaleAtPercent(Object.values(stats), pairs[0]);
      if (!range) {
        set({ notice: NO_RANGE_AT_PERCENT });
        return;
      }
      set({ pendingVmin: fieldNumber(range[0]), pendingVmax: fieldNumber(range[1]), pendingChannels: [] });
    }
    const now = get();
    set({ appliedRender: { ...now.appliedRender, ...lookOfPendingFields(now) } });
  } catch (e) {
    set({ notice: `Could not measure the percentiles: ${(e as Error).message}` });
  } finally {
    set({ focusLoading: false });
  }
}

// Whether the fields ask for a range in percentiles, in the shared pair or in any channel of a colour picture.
const inPercent = (s: AppState): boolean => (colourView(s) ? colourInPercent(s) : s.pendingUnit === 'percent');

// "Add to layers" and "Add all to layers" in the view: the image that is shown, or every image, one layer each, all in one
// step with the first on the bottom of the new ones, so that the last image of the list lies on top (NM4-53). A layer
// takes the look its image is drawn with. Where a mosaic is not known yet it waits for it, as it always did.
function pinViewImages(set: SetState, get: GetState, which: 'shown' | 'all'): void {
  const s = get();
  if (s.pinLoading) return; // already waiting for a mosaic; it pins when it is here
  const images = viewImagesOf(s);
  const shown = shownImageOf(images, s.shownImage);
  const clip = s.cropToAoi && s.viewAoi ? s.viewAoi : null;
  const picked = (which === 'all' ? images : shown ? [shown] : []).flatMap((image) => {
    // A selection inside the image is another mosaic than the one the view loaded (a part of its scenes).
    const ticked = which === 'shown' ? image.ids.filter((id) => s.selectedIds.includes(id)) : [];
    const ids = ticked.length > 0 ? ticked : image.ids;
    const entries: SceneEntry[] = ids.flatMap((id) => (s.downloaded[id] ? [[id, s.downloaded[id]] as SceneEntry] : []));
    return entries.length > 0 ? [{ image, entries }] : [];
  });
  if (picked.length === 0) {
    set({ error: 'Nothing to add — search and pick a time step first.' });
    return;
  }
  // An index the tile route cannot take would be a layer with nothing in it: it is not pinned (zooming mends nothing here; the
  // layer draws from the zoom the scenes start at, whatever the map shows now).
  const groupsOfView = sectionsForView(s).flatMap((section) => section.groups);
  for (const { image, entries } of picked) {
    const look = lookOfImage(s, image, shown);
    const preset = viewIndexOf(look, s.datasets.find((d) => d.id === image.datasetId)?.collection);
    const block = preset && indexBlockOf({ datasetId: image.datasetId, entries, groups: groupsOfView, mosaics: s.mosaics, preset, mapZoom: Infinity });
    if (preset && block) {
      set({ error: `${indexNote(block, preset.name)}. Start a job in Processing for the whole scenes.` });
      return;
    }
  }
  const built = picked.map((pick) => ({ ...pick, overlays: overlaysOfEntries(s, pick.entries, clip, lookOfImage(s, pick.image, shown)) }));
  const waiting = built.filter((b) => b.overlays === null);
  if (waiting.length > 0) {
    pinWhenLoaded(
      set,
      get,
      waiting.map((b) => ({ entries: b.entries, index: viewIndexOf(lookOfImage(s, b.image, shown), s.datasets.find((d) => d.id === b.image.datasetId)?.collection) })),
      () => pinViewImages(set, get, which),
    );
    return;
  }
  const groups = sectionsForView(s).flatMap((section) => section.groups);
  const known = knownItems(s);
  const batchId = nextBatchId();
  const layers = built.map(({ image, entries, overlays }, i): MapLayer => {
    const itemIds = entries.map(([id]) => id);
    const title = s.datasets.find((d) => d.id === image.datasetId)?.title ?? image.datasetId;
    const name = [title, image.groupLabel || (s.groups[s.activeGroupIndex]?.label ?? ''), satellitesOf(image)].filter(Boolean).join(' · ');
    const look = lookOfImage(s, image, shown);
    return {
      id: `L${batchId}${i}`,
      name,
      visible: true,
      // The view's own opacity goes with its picture into the layer (Otto, 2.11.2026).
      opacity: s.viewOpacity,
      overlays: overlays ?? [],
      ...dateOf(datesOfIds(itemIds, known)),
      restore: {
        focusMode: true,
        downloaded: Object.fromEntries(entries),
        appliedRender: { ...look },
        activeGroupIndex: s.activeGroupIndex,
        selectedIds: clip ? itemIds : ticksOfOpen(s),
        itemIds,
        // One image is one group already; a single-element list, not `groupItemIdsFor`, which would rediscover the split.
        groupItemIds: clip ? [itemIds] : groupItemIdsFor(itemIds, groups),
        aoi: clip ?? s.aoi,
        cropToAoi: clip !== null,
        datasetId: image.datasetId,
        // An index chosen in "Quick processing" is pinned alone, not the whole view (UI-03d, Otto, 2.11.2026).
        ...(viewIndexOf(look, s.datasets.find((d) => d.id === image.datasetId)?.collection) ? { indexOnly: true as const } : {}),
      },
    };
  });
  const everything = layers.length === 1 && layers[0].restore.itemIds.length === Object.keys(s.downloaded).length;
  set({
    layers: [...[...layers].reverse(), ...s.layers],
    resultsAt: resultsAtAfterAdding(s.resultsAt, layers.length),
    // The layer is the view's picture, so it takes the view's place in the list (`viewLayer.ts`), unless it holds only
    // some of the scenes the view draws.
    ...(everything ? { viewLayerId: layers[0].id } : {}),
    error: null,
    notice: layers.length === 1 ? `Added "${layers[0].name}" to layers.` : `Added ${layers.length} layers (one per image).`,
  });
}

// In flight, by the mosaic's key (or the key of an order, or of an index's selection): two views that want one mosaic ask once.
const mosaicLoads = new Map<string, Promise<void>>();

// A pass the view or a layer draws, and the index the look computes over it, if any: its tiles are asked from the selection for
// the assets that index reads.
type MosaicRequest = { datasetId: string; entries: SceneEntry[]; index?: IndexPreset | null };

// Creates the selection of each pass that a mosaic would draw, once, and loads its TileJSON. The map learns the surface and the
// levels from it, and the tiler answers it from what it stored at the creation (`mosaic.ts`). A mosaic the tiler cannot give is
// kept as `null` and its pass is drawn scene by scene; asking again after a `null` asks the tiler again.
async function fetchMosaics(set: SetState, get: GetState, requests: MosaicRequest[]): Promise<void> {
  const failures: string[] = [];
  const orderFailures: string[] = [];
  await Promise.all(
    requests.map(async ({ datasetId, entries, index }) => {
      const key = mosaicKeyOf(datasetId, entries);
      if (key) {
        await loadMosaic(set, get, datasetId, entries, key, failures);
        if (index) await loadIndexSelection(set, get, datasetId, entries, index);
      }
      // A pass drawn scene by scene (more scenes than a selection takes, other assets, a mosaic the tiler refused)
      // lies in the order of the mosaic, the crop and the export, which only the tiler knows (NM4-24).
      if (key === null || get().mosaics[key] === null) await loadOrder(set, get, datasetId, entries, orderFailures);
    }),
  );
  if (failures.length > 0) set({ notice: `Could not load the mosaic (${failures[0]}); its scenes are drawn one by one.` });
  else if (orderFailures.length > 0) {
    set({ notice: `Could not read the stacking order of the scenes (${orderFailures[0]}); they lie in the order of the selection.` });
  }
}

// The order of the scenes of one pass, once, kept under `orderKeyOf`; `null` where the tiler could not give it (the scenes then
// lie in the order of the selection, as before) so that it is not asked again until the search is made anew.
async function loadOrder(
  set: SetState,
  get: GetState,
  datasetId: string,
  entries: SceneEntry[],
  failures: string[],
): Promise<void> {
  const key = orderKeyOf(datasetId, entries);
  if (!key || get().mosaics[key] !== undefined) return;
  let load = mosaicLoads.get(key);
  if (!load) {
    load = (async () => {
      let order: string[] | null = null;
      try {
        order = await api.fetchSceneOrder(datasetId, entries.map(([id]) => id), entries[0][1].asset);
      } catch (e) {
        failures.push((e as Error).message);
      }
      set({ mosaics: { ...get().mosaics, [key]: order ? { order } : null } });
    })().finally(() => mosaicLoads.delete(key));
    mosaicLoads.set(key, load);
  }
  await load;
}

async function loadMosaic(
  set: SetState,
  get: GetState,
  datasetId: string,
  entries: SceneEntry[],
  key: string,
  failures: string[],
): Promise<void> {
  if (get().mosaics[key]) return;
  let load = mosaicLoads.get(key);
  if (!load) {
    load = (async () => {
      let info: Mosaics[string] = null;
      try {
        const selection = await ensureSelection(datasetId, entries.map(([id]) => id), [entries[0][1].asset]);
        const json = await withSelection(selection, api.fetchMosaicTileJson);
        info = { tileUrl: api.buildMosaicTileTemplate(selection), bounds: json.bounds, minZoom: json.minzoom, maxZoom: json.maxzoom, order: json.order };
      } catch (e) {
        failures.push((e as Error).message);
      }
      if (info || get().mosaics[key] === undefined) set({ mosaics: { ...get().mosaics, [key]: info } });
    })().finally(() => mosaicLoads.delete(key));
    mosaicLoads.set(key, load);
  }
  await load;
}

// The selection of a pass for the assets an index reads (the tile of the index is a mosaic with a step). One that the tiler does not
// take, or an index of more assets than a selection holds, stays `null`, and the view says that the index cannot be computed here.
async function loadIndexSelection(set: SetState, get: GetState, datasetId: string, entries: SceneEntry[], index: IndexPreset): Promise<void> {
  const assets = assetsOfExpression(index.expression);
  if (assets.length > MAX_MOSAIC_OPERATOR_ASSETS) return;
  const key = indexKeyOf(datasetId, assets, entries);
  if (get().mosaics[key]) return;
  let load = mosaicLoads.get(key);
  if (!load) {
    load = (async () => {
      let info: Mosaics[string] = null;
      try {
        info = { selection: await ensureSelection(datasetId, entries.map(([id]) => id), assets) };
      } catch {
        // The tiler's words are for the panel of the mosaic; the index says only that it cannot be computed here.
      }
      set({ mosaics: { ...get().mosaics, [key]: info } });
    })().finally(() => mosaicLoads.delete(key));
    mosaicLoads.set(key, load);
  }
  await load;
}

function resultsNotice(ctx: SearchContext, datasets: ViewableDataset[], sections: ResultSection[]): string {
  if (ctx.features.length === 0) {
    // The limit on the clouds inside the AOI is what leaves nothing (DS-03b); the notice of a search over one dataset
    // says it (`aoiHints` adds how far it got).
    if (datasets.length === 1 && measuresAoi(ctx.query, datasets[0].id)) {
      // A search that was stopped (a token is left) has no verdict; its list says how far it got.
      if (ctx.nextToken !== null) return '';
      const counts = ctx.answer?.aoiFilter?.[datasets[0].id];
      return `${NONE_WITHIN_NOTE}${counts ? ` (${counts.checked} checked)` : ''}.`;
    }
    const base =
      datasets.length === 1 || (!ctx.dateFrom && !ctx.dateTo)
        ? 'No scenes found for this area.'
        : 'No scenes found for this area and date range.';
    // A filter may be what leaves nothing (DS-02c); the notice says that one is set, not which.
    return ctx.query.queryByCollection ? `${base} Search filters are set.` : base;
  }
  if (datasets.length === 1) {
    return foundNotice(sections[0].items, sections[0].groups, ctx.numberMatched, ctx.nextToken !== null);
  }
  // What the search found in its date range: a fallback's scenes are not counted.
  const own = sections.filter((section) => section.origin === 'search');
  const steps = own.reduce((sum, section) => sum + section.groups.length, 0);
  const found = own.reduce((sum, section) => sum + section.items.length, 0);
  return `${counted(found, 'scene')} in ${counted(steps, 'time step')} across ${datasets.length} datasets.`;
}

// What the search notice adds when the one dataset searched was asked for the cloud share in the AOI and found nothing
// within the limit, so that there is no list to say it: that the limit of scenes it checks is reached, and how many it
// could not read (DS-03b). Otherwise the head of the dataset in the list says it.
function aoiHints(ctx: SearchContext, datasets: ViewableDataset[]): string[] {
  const [only] = datasets;
  const counts = datasets.length === 1 && ctx.features.length === 0 ? ctx.answer?.aoiFilter?.[only.id] : undefined;
  if (!counts) return [];
  return [counts.limitReached ? limitNote(counts) : null, counts.unreadable > 0 ? `${unreadableNote(counts)}.` : null].filter(
    (hint): hint is string => hint !== null,
  );
}

// Lays out the scenes a search has loaded: one section per dataset asked and
// the search notice. A new search opens the first dataset with
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
      selectedIds: [],
      searchContext: null,
      dock: withoutResults(s.dock),
      error: `Grouping failed: ${failed}`,
      notice: null,
    });
    return;
  }
  const sections = built.map((fresh) => {
    const waiting = withSourceState(fresh, sourceOpen(ctx, fresh.datasetId));
    // Stopped before a scene was found (DS-03b, Otto 31.10.2026): the list is there, with how far it got and "Load more".
    const section =
      !s.aoiWalking && waiting.items.length === 0 && waiting.origin === 'search' && sourceOpen(ctx, waiting.datasetId) && measuresAoi(ctx.query, waiting.datasetId)
        ? { ...waiting, keepList: true }
        : waiting;
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
  // A search that is still walking has no verdict yet; the list says how far it is (DS-03b).
  const notice = s.aoiWalking
    ? null
    : [
        resultsNotice(ctx, datasets, sections),
        ...aoiHints(ctx, datasets),
        ctx.truncatedNotice,
        timeNote && `${timeNote}.`,
        stray > 0 ? `${counted(stray, 'scene')} of other datasets ${stray === 1 ? 'was' : 'were'} left out.` : null,
      ]
        .filter(Boolean)
        .join(' ');
  set({
    sections,
    ...(keepOpen ? reopenedSectionState(s, open) : openSectionState(open)),
    ...(open ? { datasetId: open.datasetId } : {}),
    selectedIds: keepOpen ? s.selectedIds.filter((id) => sections.some((section) => section.items.some((it) => it.id === id))) : [],
    searchContext: ctx,
    // A new search shows its results; "Load more" leaves the panels as they are. A search stopped without a scene shows
    // its list, since "Stop" was pressed where there was none.
    ...((!keepOpen && hasResultsPanel(sections)) || sections.some((x) => x.keepList) ? { dock: 'results' as const } : {}),
    error: null,
    notice: notice || null,
  });
}

// A new set of ticked datasets (M4-29): the results of the last search go, the
// active dataset stays if it is still ticked, pinned layers are untouched.
function applyDatasetSelection(
  set: SetState,
  get: GetState,
  selectedDatasetIds: string[],
  lastPickedDatasetId: string | null,
): void {
  const s = get();
  const datasetId =
    s.datasetId && selectedDatasetIds.includes(s.datasetId) ? s.datasetId : (selectedDatasetIds[0] ?? null);
  // A new choice fills the dates anew with the days of the chosen datasets (UI-05 §3.3, Otto 06.11.2026); what the user
  // types stays until the next choice.
  const days = prefilledDays(s.datasets, selectedDatasetIds, todayUtc());
  set({
    selectedDatasetIds,
    dateFrom: days.from,
    dateTo: days.to,
    lastPickedDatasetId: lastPickedDatasetId && selectedDatasetIds.includes(lastPickedDatasetId) ? lastPickedDatasetId : null,
    datasetId,
    sections: [],
    openSectionId: null,
    dock: withoutResults(s.dock),
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
  });
  // The coverage map is for a dataset that is picked; dropping that one drops it.
  if (s.coverageDatasetId && !selectedDatasetIds.includes(s.coverageDatasetId)) get().hideCoverage();
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
  // The limit on the clouds inside the AOI searches the date range asked and nothing around it (DS-03b, KE4).
  if (measuresAoi(ctx.query, datasetId)) return;
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
    // Only the dataset's own filters: the server refuses a filter for a collection the search does not name.
    const { queryByCollection, aoi: _aoi, ...rest } = ctx.query;
    const query = { ...rest, collections: [datasetId], ...queryByCollectionOf({ [datasetId]: queryByCollection?.[datasetId] ?? {} }) };
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
    const singleNotice = replacement.groupingError
      ? { error: `Grouping failed: ${replacement.groupingError}`, notice: null }
      : { notice: [replacement.notes[0], ctx.truncatedNotice].filter(Boolean).join(' ') };
    set({
      sections,
      ...(now.openSectionId === datasetId ? openSectionState(replacement) : {}),
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

// The walk of a search that asks for the cloud share in the AOI (DS-03b, plan §6.17). The server checks a few scenes per
// answer and says how far it got, so this goes on with the page token by itself, shows what each answer brings and ends
// when the page is full (`MAX_SEARCH_ITEMS` found), the server has nothing more or says the limit is reached, "Stop" is
// pressed, or the search is no longer the one on screen. What is found stays, and the token with it unless the search
// itself changed: "Load more" goes on from there. An answer without a scene is no end and no page of its own.
async function walkAoiSearch(
  set: SetState,
  get: GetState,
  options: { base: SearchContext; token?: string; fresh: boolean; unchanged: () => boolean },
): Promise<void> {
  const { base, token, fresh, unchanged } = options;
  const gen = searchGen;
  const controller = new AbortController();
  walk = controller;
  set({ aoiWalking: true });
  // The list is laid out as a new search until scenes are in it; from then on the scenes, ticks and open time step stay.
  let laidOut = !fresh;
  let stopped = false;
  let failed = false;
  const show = (soFar: PagesSoFar) => {
    if (gen !== searchGen) return;
    const kept = unchanged();
    // One of a scene, whichever answer brings it again.
    const features = new Map(base.features.map((it) => [sceneKey(it), it] as const));
    for (const it of soFar.features) if (!features.has(sceneKey(it))) features.set(sceneKey(it), it);
    const ctx: SearchContext = {
      ...base,
      features: [...features.values()],
      answer: combineAnswers(base.answer, soFar),
      numberMatched: base.numberMatched ?? soFar.numberMatched,
      nextToken: kept ? soFar.nextToken : null,
      openCollections: soFar.openCollections,
    };
    showSearchResults(set, get, ctx, laidOut);
    // A list of several datasets is there from the first answer on; it is not laid out again for each of them.
    laidOut = ctx.features.length > 0 || !fresh || hasResultsPanel(get().sections);
    // The filters or the area changed before the first answer: the search on screen cannot be continued.
    if (!kept) controller.abort();
  };
  try {
    await api.searchAllPages(base.query, MAX_SEARCH_ITEMS, token, { signal: controller.signal, onPage: show });
  } catch (e) {
    if (gen !== searchGen) return;
    if (isAbort(e)) {
      stopped = true;
      return;
    }
    // Nothing is found yet: the search failed. Otherwise what is found stays.
    const now = get().searchContext;
    if (fresh && (now === null || now.features.length === 0)) {
      failed = true;
      throw e;
    }
    if (now) set({ searchContext: { ...now, nextToken: null }, loadMoreError: 'Could not load more results — search again.' });
  } finally {
    if (walk === controller) walk = null;
    if (gen === searchGen) {
      set({ aoiWalking: false });
      // The verdict the list could not give while it walked.
      const now = get().searchContext;
      if (now && !failed) showSearchResults(set, get, now, true);
      // Stopped, or the search changed, before there was anything to show: it would end without a word.
      else if (stopped && !failed) set({ notice: 'Search stopped.' });
    }
  }
}

// A search on screen that the control panel would no longer run the same way
// (another AOI, other dates) cannot be continued: "Load more" would add scenes of
// the old one (M3-10 §4.4). The results themselves stay.
function dropPageToken(set: SetState, get: GetState): void {
  stopWalk();
  const ctx = get().searchContext;
  if (ctx?.nextToken) set({ searchContext: { ...ctx, nextToken: null } });
}

// The filters of one dataset changed (DS-02c). Like the dates they are read at the next "Search", so a search on
// screen that ran with others cannot be continued; the coverage map of this dataset follows at once, debounced.
function changeSearchFilters(set: SetState, get: GetState, datasetId: string, inputs: FilterInputs): void {
  const { searchFilters, searchContext } = get();
  // A change that changes nothing (a wrong field made wrong another way, a box ticked and unticked) leaves the search
  // and the map alone.
  if (JSON.stringify(searchFilters[datasetId] ?? {}) === JSON.stringify(inputs)) return;
  const { [datasetId]: _before, ...others } = searchFilters;
  set({ searchFilters: Object.keys(inputs).length > 0 ? { ...others, [datasetId]: inputs } : others });
  if (searchContext?.datasetIds.includes(datasetId)) dropPageToken(set, get);
  const { showCoverage, coverageDatasetId } = get();
  if (showCoverage && datasetId === (coverageDatasetId ?? get().datasetId)) scheduleCoverageRefresh(set, get);
}

// The switch "Filter within AOI only" of one dataset changed (DS-03b): like the filters it is read at the next "Search", and
// the coverage map follows (it leaves the filters of the switch out).
function changeSearchWithin(set: SetState, get: GetState, datasetId: string, on: boolean): void {
  const { searchWithin, searchContext } = get();
  if ((searchWithin[datasetId] ?? false) === on) return;
  const { [datasetId]: _before, ...others } = searchWithin;
  set({ searchWithin: on ? { ...others, [datasetId]: true } : others });
  if (searchContext?.datasetIds.includes(datasetId)) dropPageToken(set, get);
  const { showCoverage, coverageDatasetId } = get();
  if (showCoverage && datasetId === (coverageDatasetId ?? get().datasetId)) scheduleCoverageRefresh(set, get);
}

// Show or hide of the results is the switch's, with three exceptions (Otto, 27.10.2026 and 28.10.2026): a new search shows them, a ticked scene shows them (`ticking`), and a
// crop of the chosen scenes ("Crop to AOI", "Crop & merge to AOI") hides them. Kept in the browser like the switch.
function setResultsOnMap(on: boolean) {
  saveResultsOnMap(on);
  return { resultsOnMap: on };
}

// A scene ticked while the results are hidden shows them (Otto, 28.10.2026, zu #221): the third exception, besides a
// search and a crop. Unticking changes nothing.
// Any change of the ticks by a click, of a scene, a group or "Select all", ends the playing of the timeline (NM4-18, Otto,
// 30.10.2026).
// A scene ticked while a layer is open from the layer manager closes the box of that layer: the box of the search results takes
// its place (NM4-65, Otto, 1.11.2026). A view that is still open from the search stays, with the ticks beside it.
function ticking(s: Pick<AppState, 'selectedIds' | 'resultsOnMap' | 'viewOfLayer'>, selectedIds: string[]) {
  const ticked = selectedIds.some((id) => !s.selectedIds.includes(id));
  return {
    selectedIds,
    playing: false,
    selectionBlockClosed: false,
    ...(ticked && !s.resultsOnMap ? setResultsOnMap(true) : {}),
    ...(ticked && s.viewOfLayer ? LEAVE_FOCUS : {}),
  };
}

// What every replacement of the results resets besides the results themselves.
function forgetSearch() {
  searchGen += 1;
  stopWalk();
  return {
    aoiWalking: false,
    // New results, or none, show the block at the bottom again (NM4-66).
    selectionBlockClosed: false,
    // Every search, and every step that drops the results, puts "Results" on top of the layer manager (NM4-59, Otto,
    // 30.10.2026).
    resultsAt: 0,
    searchContext: null,
    loadingMore: false,
    loadMoreError: null,
    loadMoreUsed: false,
    fallbackDatasetIds: [],
  };
}

// The panels beside the rail (UI-01 §6.9). One is open at a time, or none.
export type DockPanel = 'controls' | 'layers' | 'jobs' | 'results' | 'settings';

// Sliding the control panel away leaves another panel where it is.
const withoutControls = (dock: DockPanel | null): DockPanel | null => (dock === 'controls' ? null : dock);

// The results panel has nothing left to show once the results go: the control menu, where the search
// settings are, takes its place. A closed dock stays closed.
const withoutResults = (dock: DockPanel | null): DockPanel | null => (dock === 'results' ? 'controls' : dock);

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
  // A camera to jump to as it is (a permalink's view, M4-19e): centre [lon, lat] and zoom.
  flyToView: { center: [number, number]; zoom: number } | null;
  // --- view preferences (V-1, the "Settings" menu), saved per browser (preferences.ts) ---
  // What the user chose, and the theme that is drawn: they differ while the choice is "system" (it follows the system's).
  appearance: Appearance;
  theme: Theme;
  // The step of the tooltips (`tipLevel.ts`).
  tipLevel: TipLevel;
  projection: Projection;
  basemap: BasemapId;
  overlays: Overlays;
  // The map lies over the terrain and may turn and tilt (UI-06, the button "3D"); in 2D it only pans and zooms (D27).
  terrain: boolean;
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
  // The panel beside the rail (UI-01 §6.9): one at a time, or none.
  dock: DockPanel | null;
  // The search results (quicklooks) are drawn on the map (UI-01g). Off, only the scenes ticked in the
  // list are; the list itself is the same. Every new search starts with it on.
  resultsOnMap: boolean;
  // Viewing a full-resolution raster (M2-07b) instead of browsing quicklooks —
  // swaps ViewBar for ViewerControls (App.tsx); the results list stays whatever the view.
  focusMode: boolean;
  showDownloaded: boolean;
  // The opacity of the view of the search, which is no layer (Otto, 2.11.2026); 1 for every new view.
  viewOpacity: number;
  // The image of the view that is drawn (`viewImages.ts`); null draws the first. The others are not on the map.
  shownImage: string | null;
  // The look of the images of the view (NM4-53, Otto 29.10.2026), for the length of the view only: what "Apply" drew on
  // one image and nobody saved (`viewLooks`, by the key of the image), and what "Save" fixed for all images of a dataset
  // (`savedLooks`, by dataset). An image has the first of these it finds, else the standard visualisation of its dataset.
  viewLooks: Record<string, AppliedRender>;
  savedLooks: Record<string, AppliedRender>;
  focusLoading: boolean; // fetching statistics while entering focus / "auto"
  // Whether the current focus view is cropped to `aoi` ("Crop to AOI") or
  // shows the whole selection uncropped ("View full selection", M3-09) —
  // meaningless while `focusMode` is false. Drives the map's AOI clipping
  // (`mapLayers.ts::syncFocusRaster`) and, once pinned, the layer's own
  // download (`download.ts::downloadRequestFor`, P19).
  cropToAoi: boolean;
  // The area a cropped view was opened with (Otto, 27.10.2026): it keeps it. Drawing, changing or clearing the area in the
  // control menu does not touch the view. Null for every view that is not cropped.
  viewAoi: GeoJSON.Geometry | null;

  // --- layer manager ---
  layers: MapLayer[]; // pinned images (top of list = top of map)
  // How many of `layers` lie above the entry "Results" (`resultsEntry.ts`, NM4-59): 0 is on top.
  resultsAt: number;
  // The layer whose scenes `selectLayer` put into the full-resolution view. While
  // the view still shows exactly what it pinned (`viewLayer.ts::viewLayerOf`), that
  // layer draws the picture, at its place in the list and with its eye.
  viewLayerId: string | null;
  // The view was opened from a layer of the layer manager, not made by the search: the index of such a layer is the one it was added
  // with and is not chosen again there (NM4-14b, Otto 1.11.2026).
  viewOfLayer: boolean;
  // The layer of a job's result whose range and colormap the bottom of the map shows (UI-01 §6.11):
  // `selectLayer` sets it for a result layer. The results list is folded away meanwhile, as in the
  // full-resolution view, which this is not (`focusMode` stays off).
  resultViewLayerId: string | null;
  // The layer the download dialog (M2-07d) is open for, `null` when closed.
  downloadDialogLayerId: string | null;
  // The dialog open for the current selection (V-4) rather than a pinned
  // layer — downloading a selected quicklook's original data straight from
  // the results list, before "Add to layers"/"View full resolution".
  downloadSelection: boolean;
  // With `downloadSelection`: the dialog is for the image the view shows (`openDownloadForView`), not for the ticks of the list.
  downloadView: DownloadView | null;
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
  // The scenes behind those links, by group (M4-12b): what the dialog offers a
  // merged mosaic job for. Set together with the links, `null` otherwise.
  downloadPasses: DownloadPass[] | null;
  // Set once a crop download has actually answered with at least one group
  // dropped for not touching the AOI at all (review finding on M3-17: the
  // user has to see this, not just find fewer files than requested in the
  // ZIP's ATTRIBUTION.txt). The dialog stays open to show this English
  // sentence instead of closing on a successful download, same as any other
  // outcome the user needs to read before moving on. `null` otherwise.
  downloadSkippedGroupsNotice: string | null;
  // The crop was too large for a direct download and its `413` offers an
  // export job (M4-11b-2); the dialog shows the offer instead of an error.
  // Dropped with the dialog and with any change of the choice.
  downloadExportOffer: ExportOffer | null;
  // The choice of bands and files (NM4-75). The table of bands is the platform's answer for the scenes of the dialog; empty where the
  // scenes have no file per band to choose from. `downloadBandsLoading`: the answer is still on its way.
  downloadTable: DownloadBand[];
  downloadBandsLoading: boolean;
  // The asset keys ticked.
  downloadBands: string[];
  downloadForm: DownloadForm;
  // The common resolution picked, in metres; `null`: the finest of the ticked bands.
  downloadCommonResolution: number | null;
  // Whole scenes in a form that is a job: what the server expects it to cost, or why it refuses.
  downloadJobNote: JobNote | null;
  // The resampling a download will do, asked of the person before it starts (`ResamplingDialog`); `null` when nothing is asked.
  downloadResampling: ResamplingPart[] | null;
  // Whole scenes, one file per band: "Download" was pressed and the scenes are being loaded in the browser.
  downloadStarted: boolean;

  // --- render params for a full-res raster, committed via "Apply" (F18) ---
  appliedRender: AppliedRender;
  // Pending stretch/colormap edits, not yet committed to `appliedRender`.
  pendingColormapName: string; // '' = none
  pendingVmin: string;
  pendingVmax: string;
  // The three ranges of a colour picture, set channel by channel (UI-03d); empty while `pendingVmin`/`pendingVmax` hold for all three.
  pendingChannels: ChannelRange[];
  // The index the fields stand for, drawn once "Apply" is pressed (NM4-14b); '' = none.
  pendingIndex: string;
  // The single band the fields stand for, drawn once "Apply" is pressed (NM4-45); '' = the standard picture.
  pendingBand: string;
  // "vmin"/"vmax" as values or as percentiles (NM4-65 part 4); with "percent" the fields show the two percentiles, and
  // `pendingVmin`/`pendingVmax` hold the values they gave at the last "Apply".
  pendingUnit: RangeUnit;
  pendingPercentLow: string;
  pendingPercentHigh: string;
  // "Enhance contrast" of "Quick processing" (UI-03d): the look it drew and the one drawn before it, which a second click puts back. It
  // is on while the fields ask for what it drew.
  enhance: { look: AppliedRender; before: AppliedRender } | null;

  // --- data ---
  config: { point_buffer_deg: number } | null; // no server config endpoint any more; the client default (0.05) applies
  datasets: DatasetOption[];
  // M3-10: what the dataset filter has ticked — a search asks all of them at once.
  selectedDatasetIds: string[];
  // M4-29: more than one dataset may be ticked only while this switch is on.
  multiSelect: boolean;
  // The dataset ticked last; "Select multiple datasets" ending keeps this one.
  lastPickedDatasetId: string | null;
  // The datasets of "Search and area", in the order they were added (UI-05 §4): from the Data catalogue, saved per
  // browser; on a first visit those of `firstVisitDatasets`. Every ticked dataset is one of them.
  addedDatasetIds: string[];
  // A dataset whose page "Search and area" turns to (UI-05 A5, after "Add"); `seq` tells two requests for one apart.
  revealedDataset: { id: string; seq: number } | null;
  // Whether the Data catalogue is open (UI-05 §4.1).
  catalogueOpen: boolean;
  // The *active* dataset: the one the map, time slider, heatmap, full-resolution
  // view and download follow. It is the open results section's dataset, or the
  // one picked in the heatmap legend; one of `selectedDatasetIds`, unless "Remove" in the Data catalogue unticked it and
  // kept its results (UI-05 A6) until the next choice.
  datasetId: string | null;
  // One entry per dataset the last search asked, in filter order (M3-10). `items`,
  // `groups` and the two indices below mirror the *open* section only.
  sections: ResultSection[];
  openSectionId: string | null;
  searchContext: SearchContext | null;
  // "Load more" (M3-10b): running, and why it last failed.
  loadingMore: boolean;
  loadMoreError: string | null;
  // "Load more" has been pressed in this search (its notes then say which dataset has nothing further).
  loadMoreUsed: boolean;
  // The datasets whose ±90-day fallback is running.
  fallbackDatasetIds: string[];
  // DS-03b: a search that asks for the filters in the AOI is going on page by page (`walkAoiSearch`).
  aoiWalking: boolean;
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
  // The block at the bottom of the map (the bar of the selection and the timeline) was closed with its "x" (NM4-66).
  // Nothing else changes with it; a click on a scene, a tick, or an opened group, or new results, bring it back.
  selectionBlockClosed: boolean;
  selectedIds: string[];
  downloaded: Record<string, DownloadedInfo>;
  // What the mosaics of the time steps in view look like, by tile template (`mosaic.ts`). Kept for
  // the session: the same scenes are the same URL, so one answer serves a later view of them.
  mosaics: Mosaics;
  // "Add to layers" is waiting for a mosaic (`pinWhenLoaded`).
  pinLoading: boolean;

  // --- filters ---
  dateFrom: string;
  dateTo: string;
  // The search filters of each dataset (DS-02c), by dataset and then by property: what stands in the fields of
  // "Advanced search". A search setting like the dates: it stays when a dataset is unticked (and does nothing
  // until it is ticked again), when the results are cleared and when the page is not reloaded; it is not kept in
  // the browser and not in the permalink.
  searchFilters: Record<string, FilterInputs>;
  // The switch "Filter within AOI only" of each dataset (DS-03b): the user's choice, whether or not it can be used right now.
  searchWithin: Record<string, boolean>;
  // "Evaluate: per pass / per scene" of "Advanced search" (DS-03c): how every filter is judged, for the whole search. Per
  // pass until the user chooses otherwise; it counts for the datasets that offer it and is read at the next "Search".
  searchEvaluate: Evaluate;

  // --- scene lookup by name (M2-17) ---
  sceneNameQuery: string;
  sceneLookupLoading: boolean;

  // --- ui ---
  searching: boolean;
  downloading: boolean; // no operation in 07a sets this; 07d's download will
  playing: boolean;
  // While playing (`playback.ts`): the time step on the map, which is behind `activeGroupIndex` while the next one
  // loads, and the earliest time the next may be shown (ms since the epoch).
  shownGroupIndex: number | null;
  revealNotBefore: number;
  error: string | null;
  notice: string | null;

  // --- actions ---
  loadDatasets: () => Promise<void>;
  toggleDatasetSelected: (id: string) => void;
  setMultiSelect: (on: boolean) => void;
  toggleCatalogue: () => void;
  // "Add" in the Data catalogue (UI-05 A5): at the end of "Search and area", which turns to its page; not ticked.
  addDataset: (id: string) => void;
  // "Remove" in the Data catalogue (UI-05 A6): out of "Search and area", unticked if it was; results, view and layers stay.
  removeDataset: (id: string) => void;
  // A permalink's dataset (UI-05 A7): added where it is not, so that view and panel agree.
  ensureDatasetAdded: (id: string) => void;
  setOpenSection: (id: string) => void;
  setToolMode: (m: ToolMode) => void;
  setAoi: (g: GeoJSON.Geometry | null, point?: GeoJSON.Point | null) => void;
  clearAoi: () => void;
  useLastAoi: () => void;
  flyTo: (b: Bbox) => void;
  clearFly: () => void;
  clearFlyView: () => void;
  // A second click on the open panel's symbol closes it.
  toggleDock: (panel: DockPanel) => void;
  closeDock: () => void;
  toggleResultsOnMap: () => void;
  // The control panel slides away for a draw or a search (`withoutControls`) and comes back when that is over,
  // unless another panel took its place meanwhile.
  reopenControls: () => void;
  clearAll: () => void;
  // The list of results, and nothing else: no AOI, dates, dataset choice or filter, no pinned layer, no job.
  clearSearchResults: () => void;
  addCurrentToLayers: () => void;
  pinDerivedLayer: (layer: DerivedLayer) => void;
  // Marks the result layers whose job's results are about to go (M4-13c-5).
  expireResultLayers: (now: number) => void;
  // The result layers of deleted jobs (`until`: job to the end of its day, in ms): locked while the day lasts, gone
  // when it is over, as before once the job is restored (NM4-27).
  syncDeletedResults: (until: ReadonlyMap<string, number>, now: number) => void;
  // Draws a result layer another way: the tile URL is rebuilt, so the map makes a new source of it.
  restyleResultLayer: (id: string, render: AppliedRender, percent?: Percent | null, percentChannels?: (Percent | null)[]) => void;
  // "Save" of a result's settings: what "Apply" draws is the layer's own look from now on.
  saveResultLayer: (id: string) => void;
  // The settings are closed: a look that was applied and not saved goes, the layer is drawn as saved again.
  revertResultLayer: (id: string) => void;
  closeResultView: () => void;
  removeLayer: (id: string) => void;
  // A new name for a layer, in the settings bar and the layer manager alike (UI-03d); an empty one is refused (`false`).
  renameLayer: (id: string, name: string) => boolean;
  // "Add current view to layers" of a layer (Otto, 2.11.2026): a copy of the layer as it is drawn now becomes a new layer, the layer
  // itself stays as it was saved.
  copyLayerAsShown: (id: string) => void;
  toggleLayerVisible: (id: string) => void;
  setLayerOpacity: (id: string, v: number) => void;
  moveLayer: (id: string, dir: 'up' | 'down') => void;
  // "Flip through layers" (NM4-65 part 9): on, the layer `flipLayerId` is drawn over all the others and the list stays as it is.
  flipThrough: boolean;
  flipLayerId: string | null;
  setFlipThrough: (on: boolean) => void;
  // The layer to draw on top, by a click on its row; only while flipping is on.
  flipTo: (id: string) => void;
  // One step down (1) or up (-1) the list; stops at the ends.
  flipStep: (dir: 1 | -1) => void;
  // The band a result layer draws as a layer of its own, named after the band and drawn as the band is now (NM4-65 part 2).
  addBandAsLayer: (id: string) => void;
  // A layer (or "Results", `null`) to a place of the list as it is drawn, by the grip of its row (NM4-65).
  moveRowTo: (id: string | null, to: number) => void;
  // The entry "Results" one step up or down among the layers (NM4-59).
  moveResults: (dir: 'up' | 'down') => void;
  // The entry "Results" on top of the layer manager, over every layer (Otto, 30.10.2026, zu #249).
  resultsToTop: () => void;
  selectLayer: (id: string) => void;
  activateLayerContext: (id: string) => void;
  activateViewContext: () => void;
  openDownloadDialog: (id: string) => Promise<void>;
  openDownloadForSelection: (kind: 'crop' | 'originals') => void;
  openDownloadForView: (kind: 'crop' | 'originals') => void;
  closeDownloadDialog: () => void;
  setDownloadBands: (keys: string[]) => void;
  setDownloadForm: (form: DownloadForm) => void;
  setDownloadCommonResolution: (metres: number | null) => void;
  // "Continue" and "Cancel" of the resampling warning that comes before a download.
  confirmResampling: () => void;
  declineResampling: () => void;
  confirmDownload: () => Promise<void>;
  // How far the download of an index is (NM4-14b): `null` for any other download.
  downloadStatus: string | null;
  // What the dialog says of the download of an index: the estimate, or the limit that stops it (NM4-14b); `null` for any other.
  downloadIndexNote: IndexNote | null;
  // What the dialog of a layer that shows an index downloads (Otto, 1.11.2026): its raw bands, or the index as a job would give it.
  downloadAs: 'raw' | 'index';
  setDownloadAs: (what: 'raw' | 'index') => void;
  // `merge` (the default): with a view open, the scenes picked are added to it, as if its scenes and the new ones were ticked together (UI-03e).
  enterFocus: (cropToAoi: boolean, merge?: boolean) => Promise<void>;
  loadMosaics: () => Promise<void>;
  addAllToLayers: () => void;
  exitFocus: () => void;
  changeImage: () => void;
  // The view steps from image to image (NM4-53): to the one with this key, one image on in the dataset shown
  // (−1 before, 1 after; no wrap), or to the first image of another dataset.
  showImage: (key: string) => void;
  stepImage: (delta: -1 | 1) => void;
  chooseViewDataset: (datasetId: string) => void;
  // Puts an index of the dataset the image shows into the fields, with its range and colormap (NM4-14b); `null` puts the standard look of
  // the dataset there. Nothing is drawn until "Apply".
  chooseViewIndex: (name: string | null) => void;
  // The single band the fields stand for (NM4-45); `null` goes back to the standard picture.
  chooseViewBand: (band: string | null) => void;
  toggleDownloaded: () => void;
  setViewOpacity: (opacity: number) => void;
  setPendingColormapName: (v: string) => void;
  setPendingVmin: (v: string) => void;
  setPendingVmax: (v: string) => void;
  setPendingChannel: (channel: number, end: 'vmin' | 'vmax', text: string) => void;
  setPendingChannelUnit: (channel: number, unit: RangeUnit) => void;
  setPendingChannelPercent: (channel: number, end: 'low' | 'high', text: string) => void;
  // "Quick processing" (UI-03d): an index into the fields, drawn without a job once "Apply" is pressed (Otto, 3.11.2026); a second click
  // puts the picture of the dataset back into the fields.
  quickIndex: (name: string) => Promise<void>;
  // "Enhance contrast": each band (each channel of a colour picture) stretched from its 2nd to its 98th percentile and drawn at once;
  // a second click puts back what was drawn before.
  enhanceContrast: () => Promise<void>;
  applyRender: () => void | Promise<void>;
  // Puts back what a pinned layer was saved with, when its settings are closed without "Save" (NM4-54, Otto, 1.11.2026).
  revertViewLayer: (id: string) => void;
  setPendingUnit: (unit: RangeUnit) => void;
  setPendingPercent: (end: 'low' | 'high', text: string) => void;
  // "Save" in the view of a pinned layer: the look typed and applied becomes the layer's own (NM4-50).
  saveViewLook: () => void | Promise<void>;
  autoStretch: () => Promise<void>;
  zoomToView: () => void;
  setActiveGroupIndex: (i: number) => void;
  toggleResultsGroup: (i: number) => void;
  closeSelectionBlock: () => void;
  focusItem: (id: string) => void;
  toggleSelected: (id: string) => void;
  selectAllInActiveGroup: () => void;
  selectAllLoaded: () => void;
  toggleGroupSelected: (index: number) => void;
  clearSelection: () => void;
  setDateFrom: (v: string) => void;
  setDateTo: (v: string) => void;
  // Puts what is in the fields of one filter of a dataset; an input with nothing in it takes the filter away.
  setSearchFilter: (datasetId: string, property: string, input: FilterInput) => void;
  // The switch "Filter within AOI only" of a dataset.
  setSearchWithin: (datasetId: string, on: boolean) => void;
  setSearchEvaluate: (evaluate: Evaluate) => void;
  // "Reset filters" of a dataset: the filters and the switch.
  resetSearchFilters: (datasetId: string) => void;
  setPlaying: (v: boolean) => void;
  setError: (v: string | null) => void;
  setNotice: (v: string | null) => void;
  runSearch: () => Promise<void>;
  loadMore: () => Promise<void>;
  // "Stop" beside the progress of a search that checks the clouds inside the AOI (DS-03b).
  stopSearch: () => void;
  setSceneNameQuery: (v: string) => void;
  findSceneByName: () => Promise<void>;
  showCoverageFor: (datasetId: string) => void;
  hideCoverage: () => void;
  setMapViewport: (zoom: number, bbox: Bbox, size: { width: number; height: number }) => void;
  setAppearance: (appearance: Appearance) => void;
  // The system's colour scheme changed: the theme follows it while the choice is "system".
  followSystemTheme: (systemDark: boolean) => void;
  setTipLevel: (level: TipLevel) => void;
  setProjection: (projection: Projection) => void;
  // Saved per browser unless `keep` is false (a permalink opens flat for its view only, UI-06 F11; a lost graphics context).
  setTerrain: (on: boolean, keep?: boolean) => void;
  setBasemap: (basemap: BasemapId) => void;
  // The basemap and projection of an opened permalink (UI-02c): they hold for this view and are not written to the
  // browser, so the next visit opens with what the user chose in the menu.
  // `relief`: the link was made when Relief was a basemap; it opens with the overlay on (for this view only, like the rest).
  // A link opens flat, without 3D (UI-06 F11), for this view only as well.
  showSharedLook: (look: { basemap: BasemapId; projection: Projection; relief?: boolean }) => void;
  setOverlay: (overlay: OverlayId, on: boolean) => void;
}

// "Relief" is no basemap any more: a browser that kept it as its basemap gets the overlay, before the first read.
migrateReliefBasemap();
const firstAppearance = loadAppearance();
const firstTipLevel = loadTipLevel();
setTipLevel(firstTipLevel);

export const useAppStore = create<AppState>((set, get) => ({
  toolMode: 'none',
  aoi: null,
  aoiPoint: null,
  lastAoi: null,
  lastAoiPoint: null,
  flyToBbox: null,
  flyToView: null,
  appearance: firstAppearance,
  theme: themeOf(firstAppearance),
  tipLevel: firstTipLevel,
  projection: loadProjection(),
  basemap: loadBasemap(),
  overlays: loadOverlays(),
  terrain: loadTerrain(),
  showCoverage: false,
  coverageDatasetId: null,
  coverage: null,
  coverageLoading: false,
  coverageError: null,
  coverageFootprints: null,
  mapZoom: 1.6,
  viewportBbox: null,
  viewportSize: null,

  dock: 'controls',
  // Kept in the browser (Otto, 27.10.2026); "Show" when nothing is stored or the storage cannot be used.
  resultsOnMap: loadResultsOnMap(),
  focusMode: false,
  showDownloaded: true,
  viewOpacity: 1,
  shownImage: null,
  viewLooks: {},
  savedLooks: {},
  focusLoading: false,
  cropToAoi: false,
  viewAoi: null,

  layers: [],
  resultsAt: 0,
  viewLayerId: null,
  viewOfLayer: false,
  resultViewLayerId: null,
  downloadDialogLayerId: null,
  downloadSelection: false,
  downloadView: null,
  downloadOutcome: null,
  downloadOriginalLinks: null,
  downloadPasses: null,
  downloadSkippedGroupsNotice: null,
  downloadExportOffer: null,
  downloadTable: [],
  downloadBandsLoading: false,
  downloadBands: [],
  downloadForm: DEFAULT_FORM,
  downloadCommonResolution: null,
  downloadJobNote: null,
  downloadResampling: null,
  downloadStarted: false,

  appliedRender: {},
  pendingColormapName: '',
  pendingVmin: '',
  pendingVmax: '',
  pendingChannels: [],
  pendingIndex: '',
  pendingBand: '',
  pendingUnit: 'value',
  pendingPercentLow: DEFAULT_PERCENT.low,
  pendingPercentHigh: DEFAULT_PERCENT.high,
  enhance: null,

  config: null,
  datasets: [],
  selectedDatasetIds: [],
  multiSelect: false,
  lastPickedDatasetId: null,
  addedDatasetIds: [],
  revealedDataset: null,
  catalogueOpen: false,
  datasetId: null,
  sections: [],
  openSectionId: null,
  searchContext: null,
  loadingMore: false,
  loadMoreError: null,
  loadMoreUsed: false,
  fallbackDatasetIds: [],
  aoiWalking: false,
  items: [],
  groups: [],
  activeGroupIndex: 0,
  expandedGroupIndex: 0,
  selectionBlockClosed: false,
  selectedIds: [],
  downloaded: {},
  mosaics: {},
  pinLoading: false,

  dateFrom: '',
  dateTo: '',
  searchFilters: {},
  searchWithin: {},
  searchEvaluate: DEFAULT_EVALUATE,

  sceneNameQuery: '',
  sceneLookupLoading: false,

  searching: false,
  downloading: false,
  downloadStatus: null,
  downloadIndexNote: null,
  downloadAs: 'raw',
  playing: false,
  shownGroupIndex: null,
  revealNotBefore: 0,
  error: null,
  notice: null,

  loadDatasets: async () => {
    try {
      const collections = await api.fetchCollections();
      const datasets = datasetsFrom(collections);
      // The saved list as it is, or the first visit's (F3); the first visit is not saved, so that it follows the registry
      // until the user adds or removes a dataset.
      const saved = loadAddedDatasets();
      const addedDatasetIds = saved === null ? firstVisitDatasets(datasets) : knownDatasets(saved, datasets);
      set({ datasets, addedDatasetIds, selectedDatasetIds: [], lastPickedDatasetId: null, datasetId: null });
    } catch (e) {
      set({ error: `Backend not reachable: ${(e as Error).message}` });
    }
  },
  // The dataset buttons (M3-10, M4-29). Nothing is ticked at the start. A click
  // picks exactly that dataset and drops the one before, a click on the chosen one drops it; only with "Select
  // multiple datasets" on does a click switch its dataset on or off. A dataset
  // that cannot be shown is never ticked. Whatever the last search found no
  // longer matches the new selection, so the results go; pinned layers stay (they
  // carry their own dataset).
  toggleDatasetSelected: (id) => {
    const s = get();
    // Not while a search or a lookup is running: its answer would land on a
    // selection that is no longer the one it asked.
    if (s.searching || s.sceneLookupLoading) return;
    const dataset = s.datasets.find((d) => d.id === id);
    const ticked = s.selectedDatasetIds.includes(id);
    if (!dataset || (!ticked && !dataset.viewable)) return;
    const keep = s.multiSelect ? s.selectedDatasetIds : [];
    const selectedDatasetIds = s.datasets
      .filter((d) => (d.id === id ? !ticked : keep.includes(d.id)))
      .map((d) => d.id);
    applyDatasetSelection(set, get, selectedDatasetIds, ticked ? s.lastPickedDatasetId : id);
  },
  // "Select multiple datasets" (M4-29). Switching it off keeps only the dataset
  // ticked last (or, if that one was switched off again, the active one) and
  // drops the rest; with nothing ticked nothing stays ticked.
  setMultiSelect: (on) => {
    const s = get();
    if (s.searching || s.sceneLookupLoading || on === s.multiSelect) return;
    if (on || s.selectedDatasetIds.length <= 1) {
      set({ multiSelect: on });
      return;
    }
    const keepId =
      s.lastPickedDatasetId && s.selectedDatasetIds.includes(s.lastPickedDatasetId)
        ? s.lastPickedDatasetId
        : s.datasetId && s.selectedDatasetIds.includes(s.datasetId)
          ? s.datasetId
          : s.selectedDatasetIds[0];
    set({ multiSelect: false });
    applyDatasetSelection(set, get, [keepId], keepId);
  },
  toggleCatalogue: () => set((s) => ({ catalogueOpen: !s.catalogueOpen })),
  addDataset: (id) => {
    if (!addToPanel(id)) return;
    set((s) => ({ revealedDataset: { id, seq: (s.revealedDataset?.seq ?? 0) + 1 } }));
  },
  // Unticking here keeps what the last search found and the active dataset (A6): they are things of their own, unlike a
  // new choice in the panel, which starts a new search. Not while a search or a lookup runs on the dataset.
  removeDataset: (id) => {
    const s = get();
    if (!s.addedDatasetIds.includes(id)) return;
    const ticked = s.selectedDatasetIds.includes(id);
    if (ticked && (s.searching || s.sceneLookupLoading)) return;
    const addedDatasetIds = s.addedDatasetIds.filter((x) => x !== id);
    set({
      addedDatasetIds,
      ...(ticked
        ? {
            selectedDatasetIds: s.selectedDatasetIds.filter((x) => x !== id),
            lastPickedDatasetId: s.lastPickedDatasetId === id ? null : s.lastPickedDatasetId,
          }
        : {}),
    });
    saveAddedDatasets(addedDatasetIds);
    if (s.coverageDatasetId === id) get().hideCoverage();
  },
  ensureDatasetAdded: (id) => {
    addToPanel(id);
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
      playing: false,
      ...LEAVE_FOCUS,
    });
    const dataset = s.datasets.find((d) => d.id === id);
    if (section.origin === 'name' && section.items.length > 0 && dataset?.viewable && dataset.browse === 'full_resolution') {
      void get().enterFocus(false, false);
    }
    void runFallback(set, get, id, false);
  },

  // Activating a draw tool slides the control panel away so it can't block the
  // map while you draw; finishing a draw re-opens it (see MapView).
  setToolMode: (toolMode) =>
    set((s) => (toolMode === 'none' ? { toolMode } : { toolMode, dock: withoutControls(s.dock) })),
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
  clearFlyView: () => set({ flyToView: null }),
  // The results panel opens only while there are results.
  toggleDock: (panel) =>
    set((s) => {
      if (s.dock === panel) return { dock: null };
      return panel === 'results' && !hasResultsPanel(s.sections) ? {} : { dock: panel };
    }),
  closeDock: () => set({ dock: null }),
  toggleResultsOnMap: () => {
    const resultsOnMap = !get().resultsOnMap;
    saveResultsOnMap(resultsOnMap);
    // Nothing of the timeline is on the map with the results off it: the playing ends (NM4-18, Otto, 30.10.2026).
    set(resultsOnMap ? { resultsOnMap } : { resultsOnMap, playing: false });
  },
  reopenControls: () => set((s) => ({ dock: s.dock ?? 'controls' })),
  clearSearchResults: () => {
    set({
      sections: [],
      openSectionId: null,
      ...forgetSearch(),
      items: [],
      groups: [],
      activeGroupIndex: 0,
      expandedGroupIndex: 0,
      selectedIds: [],
      dock: 'controls',
      playing: false,
      error: null,
      notice: null,
      ...LEAVE_FOCUS,
    });
  },
  clearAll: () => {
    set({
      aoi: null,
      aoiPoint: null,
      sections: [],
      openSectionId: null,
      ...forgetSearch(),
      items: [],
      groups: [],
      activeGroupIndex: 0,
      expandedGroupIndex: 0,
      selectedIds: [],
      dock: withoutResults(get().dock) ?? 'controls',
      playing: false,
      error: null,
      notice: null,
      ...LEAVE_FOCUS,
    });
    scheduleCoverageRefresh(set, get);
  },

  // "Add to layers" (NM4-53): in the view the image that is shown becomes a layer, and "Add all to layers" every image of
  // the view, one layer each (`pinViewImages`); a layer is one image of one dataset, which is also what a group's download
  // has always merged into one file (P19). In browse mode the selection becomes one layer, as before.
  addAllToLayers: () => pinViewImages(set, get, 'all'),
  addCurrentToLayers: () => {
    const s = get();
    if (s.pinLoading) return; // already waiting for a mosaic; it pins when it is here
    const activeGroup = s.groups[s.activeGroupIndex];
    const dataset = s.datasets.find((d) => d.id === s.datasetId);
    const batchId = nextBatchId();
    const makeLayer = (name: string, overlays: LayerOverlay[], restore: LayerRestore, salt: number, date: string | null): MapLayer => ({
      id: `L${batchId}${salt}`,
      name,
      visible: true,
      opacity: 1,
      overlays,
      ...dateOf(date),
      restore,
    });

    if (s.focusMode) {
      pinViewImages(set, get, 'shown');
      return;
    }

    const items = selectionItemsFrom(s);
    const itemIds = items.map((it) => it.id);
    const overlays: LayerOverlay[] = [];
    const browsed = s.datasets.find((d) => d.id === s.datasetId);
    for (const it of items) {
      const plan = browsed ? quicklookPlan(it, browsed) : null;
      if (!plan) continue;
      if (plan.kind === 'image') {
        const coords = quicklookCoords(it, browsed && preferredGeoreferencedAsset(browsed, it));
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
      // The preview substitute (M2-10): pinned at the levels it is read on,
      // so a pinned preview stays a preview and never turns into a full-
      // resolution read when the map zooms in on it (the whole scene of a
      // `full_resolution` dataset is read at every level already).
      // `browsed` is already non-null here (a plan needs one), named again so
      // TypeScript can narrow it for the call below.
      if (!it.bbox || !browsed) continue;
      overlays.push({
        kind: 'raster',
        tileUrl: buildTileUrl(api.buildTileTemplate(browsed.id, it.id, plan.asset), plan.render),
        bounds: it.bbox,
        minZoom: plan.minZoom,
        maxZoom: plan.maxZoom,
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
        selectedIds: ticksOfOpen(s),
        itemIds,
        groupItemIds: groupItemIdsFor(itemIds, s.groups),
        aoi: s.aoi,
        cropToAoi: false,
        datasetId: s.datasetId,
        ...(browsed?.viewable && browsed.collection['earthx:default_render']?.asset_selection === 'first_present'
          ? { assets: cropAssetsOf(browsed, items) }
          : {}),
      },
      0,
      viewDates(items),
    );
    set({ layers: [layer, ...s.layers], resultsAt: resultsAtAfterAdding(s.resultsAt, 1), notice: `Added "${name}" to layers.` });
  },
  // Pins a derived picture at the top of the list.
  pinDerivedLayer: (input) => {
    const s = get();
    const layer: MapLayer = {
      id: `P${nextBatchId()}0`,
      name: input.name,
      visible: true,
      opacity: 1,
      overlays: input.overlays,
      derived: input.derived,
      ...dateOf(input.date === undefined ? datesOfIds(input.itemIds, knownItems(s)) : input.date),
      ...(input.note ? { note: input.note } : {}),
      ...(input.result ? { result: input.result } : {}),
      restore: {
        focusMode: false,
        downloaded: {},
        appliedRender: {},
        activeGroupIndex: s.activeGroupIndex,
        selectedIds: [...input.itemIds],
        itemIds: input.itemIds,
        groupItemIds: groupItemIdsFor(input.itemIds, s.groups),
        aoi: s.aoi,
        cropToAoi: input.cropToAoi,
        datasetId: s.datasetId,
      },
    };
    set({ layers: [layer, ...s.layers], resultsAt: resultsAtAfterAdding(s.resultsAt, 1), notice: `Added "${input.name}" to layers.` });
  },
  expireResultLayers: (now) =>
    set((s) => {
      const due = (l: MapLayer) => l.result && !l.result.expired && isResultExpired(l.result.expires, now);
      if (!s.layers.some(due)) return {};
      return { layers: s.layers.map((l) => (due(l) && l.result ? { ...l, result: { ...l.result, expired: true } } : l)) };
    }),
  syncDeletedResults: (until, now) =>
    set((s) => {
      const end = (l: MapLayer) => (l.result ? until.get(l.result.jobID) : undefined);
      const locked = (l: MapLayer) => end(l) !== undefined && (end(l) as number) > now;
      const gone = (l: MapLayer) => end(l) !== undefined && !locked(l);
      const changed = s.layers.some((l) => l.result && (gone(l) || locked(l) !== (l.result.deleted === true)));
      if (!changed) return {};
      const kept = s.layers.filter((l) => !gone(l));
      const removed = new Set(s.layers.filter(gone).map((l) => l.id));
      return {
        layers: kept.map((l) => (l.result && locked(l) !== (l.result.deleted === true) ? { ...l, result: { ...l.result, deleted: locked(l) } } : l)),
        resultsAt: resultsAtAfterRemoving(s.layers, s.resultsAt, (l) => !gone(l)),
        ...(s.resultViewLayerId !== null && removed.has(s.resultViewLayerId) ? { resultViewLayerId: null } : {}),
      };
    }),
  // "Apply": draws the result with this look. The look it was saved with is kept until "Save" or until the settings close.
  restyleResultLayer: (id, render, percent, percentChannels) =>
    set((s) => ({
      layers: s.layers.map((l) => {
        if (l.id !== id || l.derived !== 'result' || !l.result) return l;
        const was = l.overlays.find((o) => o.kind === 'raster')?.tileUrl;
        const overlays = l.overlays.map((o) => (o.kind === 'raster' ? { ...o, tileUrl: restyledTileUrl(o.tileUrl, render) } : o));
        const now = overlays.find((o) => o.kind === 'raster')?.tileUrl;
        const saved = l.result.savedTileUrl ?? was;
        // What the saved look was typed as, kept while another is applied (NM4-65 part 4).
        const savedPercent = l.result.savedTileUrl !== undefined ? l.result.savedPercent : (l.result.percent ?? null);
        const savedChannels = l.result.savedTileUrl !== undefined ? l.result.savedPercentChannels : (l.result.percentChannels ?? null);
        // Back at the saved look: nothing is unsaved.
        const { savedTileUrl: _kept, savedPercent: _keptPercent, savedPercentChannels: _keptChannels, percent: _percent, percentChannels: _channels, ...info } = l.result;
        const typed = { ...(percent ? { percent } : {}), ...(percentChannels ? { percentChannels } : {}) };
        return {
          ...l,
          overlays,
          result:
            saved === undefined || saved === now
              ? { ...info, ...typed }
              : { ...info, ...typed, savedTileUrl: saved, savedPercent: savedPercent ?? null, savedPercentChannels: savedChannels ?? null },
        };
      }),
    })),
  saveResultLayer: (id) =>
    set((s) => ({
      layers: s.layers.map((l) => {
        if (l.id !== id || !l.result) return l;
        const { savedTileUrl: _saved, savedPercent: _savedPercent, savedPercentChannels: _savedChannels, ...info } = l.result;
        return { ...l, result: info, saved: undefined };
      }),
    })),
  revertResultLayer: (id) =>
    set((s) => ({
      layers: s.layers.map((l) => {
        // The opacity set aside goes back first; the look has its own record (`savedTileUrl`).
        const withOpacity = l.id === id && l.saved ? { ...l, opacity: l.saved.opacity, saved: undefined } : l;
        const saved = withOpacity.id === id ? withOpacity.result?.savedTileUrl : undefined;
        if (!withOpacity.result || saved === undefined) return withOpacity;
        const { savedTileUrl: _saved, savedPercent, savedPercentChannels, percent: _percent, percentChannels: _channels, ...info } = withOpacity.result;
        l = withOpacity;
        let first = true;
        const overlays = l.overlays.map((o) => {
          if (o.kind !== 'raster' || !first) return o;
          first = false;
          return { ...o, tileUrl: saved };
        });
        return { ...l, overlays, result: { ...info, ...(savedPercent ? { percent: savedPercent } : {}), ...(savedPercentChannels ? { percentChannels: savedPercentChannels } : {}) } };
      }),
    })),
  closeResultView: () => set({ resultViewLayerId: null }),
  // The same from the layer manager and from the settings bar (UI-03d): a result's settings close, the view of a pinned layer stays
  // as a temporary picture.
  removeLayer: (id) =>
    set((s) => ({
      layers: s.layers.filter((l) => l.id !== id),
      resultsAt: resultsAtAfterRemoving(s.layers, s.resultsAt, (l) => l.id !== id),
      ...(s.resultViewLayerId === id ? { resultViewLayerId: null } : {}),
    })),
  renameLayer: (id, name) => {
    const text = name.trim();
    if (text === '' || !get().layers.some((l) => l.id === id)) return false;
    set((s) => ({ layers: s.layers.map((l) => (l.id === id ? { ...l, name: text } : l)) }));
    return true;
  },
  copyLayerAsShown: (id) => {
    const s = get();
    const at = s.layers.findIndex((l) => l.id === id);
    if (at < 0) return;
    const { saved: _saved, ...source } = s.layers[at];
    // A copy that shows an index is the index alone, as "Add to layers" of the view pins it (Otto, 3.11.2026).
    const { indexOnly: _whole, ...restore } = source.restore;
    const shows = !source.derived && viewIndexOf(restore.appliedRender ?? {}, s.datasets.find((d) => d.id === restore.datasetId)?.collection);
    const copy: MapLayer = {
      ...source,
      id: `C${nextBatchId()}0`,
      name: `${source.name} (copy)`,
      restore: shows ? { ...restore, indexOnly: true } : restore,
      ...(source.result ? { result: { ...source.result, savedTileUrl: undefined, savedPercent: undefined, savedPercentChannels: undefined } } : {}),
    };
    // Just above the layer it is copied from, as a layer made from a band; then its settings are the ones open, and the layer it
    // comes from goes back to what it was saved with (closing its settings without "Save").
    const layers = [...s.layers.slice(0, at), copy, ...s.layers.slice(at)];
    set({ layers, resultsAt: at < clampResultsAt(s.resultsAt, s.layers) ? s.resultsAt + 1 : s.resultsAt, notice: `Added "${copy.name}" to layers.` });
    if (s.resultViewLayerId === id) set({ resultViewLayerId: copy.id });
    else if (s.viewOfLayer && s.viewLayerId === id) get().selectLayer(copy.id);
  },
  toggleLayerVisible: (id) =>
    set((s) => ({ layers: s.layers.map((l) => (l.id === id ? { ...l, visible: !l.visible } : l)) })),
  // The opacity is part of what the settings of a layer keep with "Save": while they are open it is set aside once (NM4-54, Otto, 1.11.2026).
  setLayerOpacity: (id, opacity) =>
    set((s) => {
      const open = (s.viewOfLayer && s.viewLayerId === id) || s.resultViewLayerId === id;
      return { layers: s.layers.map((l) => (l.id === id ? { ...l, opacity, ...(open && !l.saved ? { saved: { opacity: l.opacity } } : {}) } : l)) };
    }),
  moveLayer: (id, dir) => set((s) => moveEntry(s.layers, s.resultsAt, id, dir, hasResultsPanel(s.sections)) ?? {}),
  flipThrough: false,
  flipLayerId: null,
  setFlipThrough: (on) =>
    set((s) => {
      if (!on) return { flipThrough: false, flipLayerId: null };
      // One layer has nothing to flip through.
      // It starts with the layer that was worked on last: the one whose settings are open, else the one of the view.
      return s.layers.length < 2 ? {} : { flipThrough: true, flipLayerId: flipStart(s.layers, s.flipLayerId ?? s.resultViewLayerId ?? s.viewLayerId) };
    }),
  flipTo: (id) =>
    set((s) => (s.flipThrough && s.layers.some((l) => l.id === id) ? { flipLayerId: id } : {})),
  flipStep: (dir) =>
    set((s) => {
      if (!s.flipThrough) return {};
      const next = flipNext(s.layers, s.flipLayerId, dir);
      return next === null || next === s.flipLayerId ? {} : { flipLayerId: next };
    }),
  addBandAsLayer: (id) => {
    const s = get();
    const at = s.layers.findIndex((l) => l.id === id);
    const made = at < 0 ? null : bandLayerOf(s.layers[at], `P${nextBatchId()}0`);
    if (!made) return;
    // Just above the layer it comes from; "Results" keeps its layers, so it moves down by one where the new layer is over it.
    const layers = [...s.layers.slice(0, at), made, ...s.layers.slice(at)];
    set({ layers, resultsAt: at < clampResultsAt(s.resultsAt, s.layers) ? s.resultsAt + 1 : s.resultsAt, notice: `Added "${made.name}" to layers.` });
  },
  moveResults: (dir) => set((s) => moveEntry(s.layers, s.resultsAt, null, dir, hasResultsPanel(s.sections)) ?? {}),
  moveRowTo: (id, to) => set((s) => moveEntryTo(s.layers, s.resultsAt, id, to, hasResultsPanel(s.sections)) ?? {}),
  resultsToTop: () => set({ resultsAt: 0 }),
  // Only what the processing panel needs of a layer (M4-13c-2, Otto 19.10.2026):
  // its dataset, if it is not the active one, and — for a layer cut to its AOI,
  // which "AOI only" sends — that AOI. The view stays as it is: the full-
  // resolution view of the layer is not entered, the results list not hidden. The
  // scenes are the panel's own business (`processingStore`).
  activateLayerContext: (id) => {
    const s = get();
    const l = s.layers.find((x) => x.id === id);
    if (!l) return;
    const r = l.restore;
    const aoi = r.cropToAoi && r.aoi ? r.aoi : s.aoi;
    if (aoi !== s.aoi) dropPageToken(set, get);
    set({ ...(r.datasetId && r.datasetId !== s.datasetId ? layerDatasetState(s, r) : {}), aoi });
  },
  // What the processing panel needs of a cropped view: the area the view was opened with, which is the order's area
  // ("AOI only"), whatever the area in the control menu has become since.
  activateViewContext: () => {
    const s = get();
    if (!s.focusMode) return;
    // The dataset of the image that is shown, and for a crop the area the view was opened with (NM4-53).
    const shown = shownImageOf(viewImagesOf(s), s.shownImage);
    const aoi = s.cropToAoi && s.viewAoi ? s.viewAoi : s.aoi;
    if (aoi !== s.aoi) dropPageToken(set, get);
    set({ ...(shown && shown.datasetId !== s.datasetId ? datasetState(s, shown.datasetId) : {}), aoi });
  },
  selectLayer: (id) => {
    const s = get();
    const l = s.layers.find((x) => x.id === id);
    if (!l) return;
    // The result of a job holds no scenes to go back to: the bottom of the map shows how it is drawn,
    // and the view of scenes, if there was one, is left.
    if (l.derived === 'result') {
      set({ ...LEAVE_FOCUS, resultViewLayerId: id });
      return;
    }
    // Layer and search results are apart (Otto, 26.10.2026): the click shows the controls and the picture of
    // this layer and touches nothing the list holds — no tick, no open section, no choice of datasets. Only
    // what the view cannot do without follows: the dataset of its controls, and the AOI of a cropped view.
    const r = l.restore;
    const dataset = r.datasetId ? s.datasets.find((d) => d.id === r.datasetId) : undefined;
    const aoi = r.cropToAoi && r.aoi ? r.aoi : s.aoi;
    if (aoi !== s.aoi) dropPageToken(set, get);
    set({
      resultViewLayerId: null,
      ...(dataset && (dataset.viewable || s.selectedDatasetIds.includes(dataset.id)) ? { datasetId: dataset.id } : {}),
      focusMode: r.focusMode,
      downloaded: r.downloaded,
      appliedRender: r.appliedRender,
      // The controls show what the layer was made with, not what the last view had in them.
      ...pendingFieldsOf(r.appliedRender),
      aoi,
      cropToAoi: r.cropToAoi,
      viewAoi: r.cropToAoi && r.aoi ? r.aoi : null,
      showDownloaded: true,
      shownImage: null,
      viewLooks: {},
      savedLooks: {},
      viewLayerId: id,
      viewOfLayer: true,
      focusLoading: true,
    });
    void get().loadMosaics().finally(() => set({ focusLoading: false }));
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
      downloadView: null,
          downloadOutcome: null,
      downloadOriginalLinks: null,
      downloadPasses: null,
      downloadSkippedGroupsNotice: null,
      downloadExportOffer: null,
      ...bandChoiceFor(false),
      error: null,
    });
    const s = get();
    const layer = s.layers.find((l) => l.id === id);
    if (!layer) return;
    const outcome = decideDownloadOutcomeForLayer(layer, s.datasets);
    set({ downloadOutcome: outcome, downloadAs: 'raw', downloadIndexNote: null });
    // A layer of an index alone is downloaded as that index (UI-03d, as in NM4-14b): there are no raw bands to choose.
    if (layer.restore.indexOnly && indexOfferedFor(layer, s.datasets)) void get().setDownloadAs('index');
    // The bands to choose from are those of the layer's scenes (NM4-75); the layer of an index alone has none to choose.
    const bandsOf = layer.restore.datasetId;
    if ((outcome === 'crop' || outcome === 'originals') && !layer.restore.indexOnly && bandsOf && layer.restore.itemIds.length > 0) {
      set({ downloadBandsLoading: true });
      void loadDownloadBands(bandsOf, layer.restore.itemIds);
    }
    if (outcome === 'crop') return;
    if (outcome !== 'originals') return;
    const datasetId = layer.restore.datasetId;
    const dataset = s.datasets.find((d) => d.id === datasetId);
    const assets = dataset?.viewable ? standardAssetsOf(dataset.collection) : [];
    if (!datasetId || !dataset || assets.length === 0) {
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
        set({ downloadOriginalLinks: originalFileLinks(groups, assets, hosts), downloadPasses: groups });
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
  openDownloadForSelection: (kind) => {
    const s = get();
    const dataset = s.datasets.find((d) => d.id === s.datasetId);
    if (kind === 'crop' && !s.aoi) {
      set({ error: DRAW_AOI_TO_CROP });
      return;
    }
    if (kind === 'originals' && !isCogFormat(dataset)) {
      set({ error: noOriginalsReason(dataset) });
      return;
    }
    const items = selectionItemsFrom(s);
    if (items.length === 0) {
      set({ error: 'Nothing to download — pick a time step or select scenes first.' });
      return;
    }
    if (kind === 'crop') {
      const req = downloadRequestForSelection(dataset, groupItemIdsFor(items.map((it) => it.id), s.groups), s.aoi, items);
      if (!req) {
        set({ error: 'Nothing to download — pick a time step or select scenes first.' });
        return;
      }
      set({
        downloadDialogLayerId: null,
        downloadSelection: true,
              downloadOutcome: 'crop',
        downloadOriginalLinks: null,
        downloadPasses: null,
        downloadSkippedGroupsNotice: null,
        downloadExportOffer: null,
        ...bandChoiceFor(true),
        error: null,
      });
      if (dataset) void loadDownloadBands(dataset.id, items.map((it) => it.id));
      return;
    }
    // Originals: the dataset's default asset, straight from the source — also
    // with an AOI drawn (the AOI plays no part), Zusatz 1a.
    const assets = dataset?.viewable ? standardAssetsOf(dataset.collection) : [];
    const groupItemIds = groupItemIdsFor(
      items.map((it) => it.id),
      s.groups,
    );
    const groups = groupItemIds.map((ids, i) => ({
      label: s.groups[groupIndexOfItem(s.groups, ids[0])]?.label ?? `Group ${i + 1}`,
      items: items.filter((it) => ids.includes(it.id)),
    }));
    const links = originalFileLinks(groups, assets, assetHostsOf(dataset));
    set({
      downloadDialogLayerId: null,
      downloadSelection: true,
          downloadOutcome: 'originals',
      downloadOriginalLinks: links,
      downloadPasses: groups,
      downloadSkippedGroupsNotice: null,
      downloadExportOffer: null,
      ...bandChoiceFor(true),
      error: null,
    });
    if (dataset) void loadDownloadBands(dataset.id, items.map((it) => it.id));
  },
  // The same dialog for the image the view shows (the settings bar, Otto, 2.11.2026): its scenes, not the ticks of the list, with
  // the same refusals as `openDownloadForSelection`.
  openDownloadForView: (kind) => {
    const s = get();
    const image = shownImageOf(viewImagesOf(s), s.shownImage);
    const dataset = s.datasets.find((d) => d.id === image?.datasetId);
    if (kind === 'crop' && !s.aoi) {
      set({ error: DRAW_AOI_TO_CROP });
      return;
    }
    if (kind === 'originals' && !isCogFormat(dataset)) {
      set({ error: noOriginalsReason(dataset) });
      return;
    }
    if (!image) {
      set({ error: 'Nothing to download — the view shows no image.' });
      return;
    }
    const items = sectionsForView(s)
      .filter((section) => section.datasetId === image.datasetId)
      .flatMap((section) => section.items)
      .filter((it) => image.ids.includes(it.id));
    if (items.length === 0) {
      set({ error: 'Nothing to download — the view shows no image.' });
      return;
    }
    const open = {
      downloadDialogLayerId: null,
      downloadSelection: true,
      downloadView: { datasetId: image.datasetId, items, label: image.groupLabel },
      downloadSkippedGroupsNotice: null,
      downloadExportOffer: null,
      ...bandChoiceFor(true),
      error: null,
    };
    if (kind === 'crop') {
      set({ ...open, downloadOutcome: 'crop', downloadOriginalLinks: null, downloadPasses: null });
      void loadDownloadBands(image.datasetId, items.map((it) => it.id));
      return;
    }
    const assets = dataset?.viewable ? standardAssetsOf(dataset.collection) : [];
    const groups = [{ label: image.groupLabel || 'Group 1', items }];
    set({ ...open, downloadOutcome: 'originals', downloadOriginalLinks: originalFileLinks(groups, assets, assetHostsOf(dataset)), downloadPasses: groups });
    void loadDownloadBands(image.datasetId, items.map((it) => it.id));
  },
  closeDownloadDialog: () => {
    // Closing the dialog stops the computing of an index or of the files of whole scenes (what it placed is dismissed).
    indexDownloadAbort?.abort();
    stopDownloadJob();
    afterResampling = null;
    set({
      downloadDialogLayerId: null,
      downloadSelection: false,
      downloadView: null,
      downloadOutcome: null,
      downloadOriginalLinks: null,
      downloadPasses: null,
      downloadSkippedGroupsNotice: null,
      downloadExportOffer: null,
      downloadIndexNote: null,
      downloadAs: 'raw',
      downloadStatus: null,
      ...bandChoiceFor(false),
    });
  },
  // The dialog of a layer that shows an index offers its raw bands and the index; the index asks what its job will cost when it is chosen.
  setDownloadAs: async (what) => {
    const s = get();
    const layer = s.layers.find((l) => l.id === s.downloadDialogLayerId);
    indexDownloadAbort?.abort();
    if (!layer || (what === 'index' && !indexOfferedFor(layer, s.datasets))) {
      set({ downloadAs: 'raw', downloadIndexNote: null });
      return;
    }
    if (what === 'raw') {
      set({ downloadAs: 'raw', downloadIndexNote: null });
      return;
    }
    // What the job of an index will cost, asked as "Review" asks it; a limit that applies stops the download here, with its reason.
    const controller = new AbortController();
    indexDownloadAbort = controller;
    set({ downloadAs: 'index', downloadIndexNote: { state: 'estimating' } });
    const note = await estimateIndexDownload({ layer, datasets: s.datasets, signal: controller.signal });
    if (!controller.signal.aborted && get().downloadDialogLayerId === layer.id) set({ downloadIndexNote: note });
  },
  // The bands ticked, the form of the files and the common resolution (NM4-75). Any of them asks the job of whole scenes anew what it costs.
  setDownloadBands: (keys) => {
    set({ downloadBands: keys, downloadExportOffer: null });
    refreshJobEstimate();
  },
  setDownloadForm: (form) => {
    set({ downloadForm: form, downloadExportOffer: null });
    refreshJobEstimate();
  },
  setDownloadCommonResolution: (metres) => {
    set({ downloadCommonResolution: metres, downloadExportOffer: null });
    refreshJobEstimate();
  },
  confirmResampling: () => {
    const go = afterResampling;
    afterResampling = null;
    set({ downloadResampling: null });
    go?.();
  },
  declineResampling: () => {
    afterResampling = null;
    set({ downloadResampling: null, downloading: false, downloadStatus: null });
  },

  // Download what the dialog is open for. The AOI crop (M2-06's `POST /collections/{dataset}/download`, M2-07d; V-4 added the
  // selection case) is one request. For whole scenes (the 'originals' outcome) it starts what the choice says (NM4-75): one file per
  // band is loaded in the browser from the source (`OriginalFiles` runs once `downloadStarted` is set), the other forms are a job on
  // the platform, placed, waited for and downloaded here with no job in the list. `downloadRequestFor`/`downloadRequestForSelection`
  // already refused anything incomplete, so a missing request here only means the layer was removed, or the selection/AOI changed,
  // while the dialog was open.
  confirmDownload: async () => {
    const s = get();
    // The table of bands is not in yet: what is asked for is not known.
    if (s.downloadBandsLoading) return;
    if (s.downloadOutcome === 'originals') {
      await startWholeScenes(s);
      return;
    }
    const layer = s.layers.find((l) => l.id === s.downloadDialogLayerId);
    const view = s.downloadSelection ? s.downloadView : null;
    const dataset = s.datasets.find((d) => d.id === (view?.datasetId ?? s.datasetId));
    const sceneItems = view ? view.items : selectionItemsFrom(s);
    const sceneIds = view ? [sceneItems.map((it) => it.id)] : groupItemIdsFor(sceneItems.map((it) => it.id), s.groups);
    const asked = s.downloadSelection ? downloadRequestForSelection(dataset, sceneIds, s.aoi, sceneItems) : layer && downloadRequestFor(layer, s.datasets);
    const name = s.downloadSelection
      ? `${dataset?.title ?? s.datasetId ?? '?'} · ${view?.label ?? s.groups[s.activeGroupIndex]?.label ?? ''}`
      : (layer?.name ?? '');
    if (!asked) {
      set({ downloadDialogLayerId: null, downloadSelection: false, downloadView: null, downloadOutcome: null });
      return;
    }
    // A layer that shows an index is downloaded as that index, computed as a job would, with no job in the list (NM4-14b).
    if (layer && s.downloadAs === 'index' && indexOfferedFor(layer, s.datasets)) {
      // Only what the estimate let through (or a try that failed, which may be tried again).
      const note = s.downloadIndexNote;
      if (note?.state !== 'ready' && note?.state !== 'failed') return;
      const controller = new AbortController();
      indexDownloadAbort = controller;
      set({ downloading: true, error: null, downloadExportOffer: null, downloadStatus: 'Computing…' });
      const problem = await downloadIndexCrop({
        layer,
        datasets: s.datasets,
        signal: controller.signal,
        onStatus: (text) => set({ downloadStatus: text }),
      });
      if (indexDownloadAbort === controller) indexDownloadAbort = null;
      if (controller.signal.aborted) {
        set({ downloading: false, downloadStatus: null });
      } else if (problem) {
        // The reason stays in the dialog, which may try again.
        set({ downloading: false, downloadStatus: null, downloadIndexNote: { state: 'failed', ...problem } });
      } else {
        set({ downloading: false, downloadStatus: null, downloadDialogLayerId: null, downloadSelection: false, downloadView: null, downloadOutcome: null, notice: `Downloaded "${name}".` });
      }
      return;
    }
    // The bands, the form and the common resolution of the dialog (NM4-75).
    const table = s.downloadTable;
    const bands = chosenBands(table, s.downloadBands);
    const picked = commonResolutionOf(bands, s.downloadCommonResolution);
    if (table.length > 0) {
      const block = layoutBlock(effectiveForm(bands, s.downloadForm), bands, picked);
      if (block) {
        set({ error: block });
        return;
      }
    }
    const mixed = table.length === 0 ? mixedBandsNote(downloadDatasetOf(s), asked.assets) : null;
    if (mixed) {
      set({ error: mixed });
      return;
    }
    const req = withBandChoice(asked, table, s.downloadBands, s.downloadForm, s.downloadCommonResolution);
    const send = async () => {
      set({ downloading: true, error: null, downloadExportOffer: null });
      try {
        const result = await api.downloadCrop({
          datasetId: req.datasetId,
          groups: req.groups,
          assets: req.assets,
          aoi: req.aoi,
          ...(req.layout ? { form: req.layout.form, commonResolution: req.layout.resolution_m } : {}),
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
            downloadView: null,
            downloadOutcome: null,
            notice: `Downloaded "${name}".`,
          });
        }
      } catch (e) {
        const { aoi } = req;
        if (
          e instanceof api.HttpError &&
          e.exportJob &&
          (aoi.type === 'Polygon' || aoi.type === 'MultiPolygon')
        ) {
          set({
            downloadExportOffer: { id: ++exportOffers, request: { ...req, aoi }, message: e.message, exportJob: e.exportJob },
          });
        } else {
          set({ error: `Download failed: ${(e as Error).message}` });
        }
      } finally {
        set({ downloading: false });
      }
    };
    // Scenes of a mosaic may lie in different UTM zones, and a form other than one file per band may bring bands to one grid: the
    // platform says whether anything is resampled, and the person confirms before the download (NM4-65 part 7).
    const mayResample = req.layout !== undefined && (req.layout.form !== 'per_band' || req.groups.some((group) => group.length > 1));
    if (mayResample && isArea(req.aoi)) {
      set({ downloading: true, error: null, downloadExportOffer: null });
      const controller = new AbortController();
      downloadJobAbort = controller;
      const order = buildExportOrder({ datasetId: req.datasetId, groups: req.groups, assets: req.assets, aoi: req.aoi, layout: req.layout });
      const parts = await resamplingOfOrder(order, controller.signal);
      if (downloadJobAbort === controller) downloadJobAbort = null;
      if (controller.signal.aborted) {
        set({ downloading: false });
        return;
      }
      if (parts.length > 0) {
        afterResampling = () => void send();
        set({ downloadResampling: parts });
        return;
      }
    }
    await send();
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
  // "Crop to AOI" and "View whole scene" with a view open (Otto, 3.11.2026, zu #282): no second view. The scenes picked join the open one, exactly
  // as if its scenes and the new ones were ticked together and the button pressed (NM4-53): the same pass is merged into the same image,
  // another day is a new step, another dataset an entry of the dataset dropdown. The look of the view stays; the layer that held the
  // view no longer holds it as it is, so the image is "Temporary".
  enterFocus: async (cropToAoi, merge = true) => {
    const s = get();
    const open = merge && s.focusMode && s.resultViewLayerId === null && Object.keys(s.downloaded).length > 0;
    const picked = viewSelectionFrom(s);
    if (picked.length === 0) {
      set({ error: 'Nothing to view — pick a time step or select scenes first.' });
      return;
    }
    if (cropToAoi && !s.aoi) {
      set({ error: 'Draw or search an area of interest first.' });
      return;
    }
    // The scenes of every dataset that is ticked (NM4-53), each with the standard visualisation of its own dataset. A
    // dataset that cannot be viewed is left out and said so; a scene id two datasets share keeps its first owner.
    const downloaded: Record<string, DownloadedInfo> = {};
    let problem: string | null = null;
    for (const { datasetId, items } of picked) {
      const dataset = s.datasets.find((d) => d.id === datasetId);
      if (!dataset || !dataset.viewable) {
        problem ??= 'Choose a dataset to search.';
        continue;
      }
      const render = defaultRenderOf(dataset.collection);
      if (!render || render.assets.length === 0) {
        problem ??= `${dataset.title} has no default visualisation yet (earthx:default_render).`;
        continue;
      }
      for (const it of items) {
        if (!it.bbox) continue;
        // The asset the scene is drawn with: for `first_present` the one it carries (DS-04 F2), else the dataset's.
        const own = defaultRenderOf(dataset.collection, it);
        if (!own) {
          problem ??= `Scene ${it.id} carries none of the assets ${dataset.title} is drawn from.`;
          continue;
        }
        const asset = own.assets[0];
        // A scene the open view has already is not added again.
        if (open && it.id in s.downloaded) continue;
        if (it.id in downloaded) {
          problem ??= `Scene ${it.id} is in two datasets; the view shows it once.`;
          continue;
        }
        downloaded[it.id] = {
          datasetId: dataset.id,
          tileUrl: api.buildTileTemplate(dataset.id, it.id, asset),
          bounds: it.bbox,
          asset,
          minZoom: dataset.zoom.min,
          maxZoom: dataset.zoom.max,
        };
      }
    }
    if (Object.keys(downloaded).length === 0 && !open) {
      set({ error: problem ?? 'None of the selected scenes carry a bounding box to render.' });
      return;
    }
    if (open && Object.keys(downloaded).length === 0 && problem) {
      set({ error: problem });
      return;
    }
    const added = downloaded;
    const all = open ? { ...s.downloaded, ...added } : added;
    const images = viewImagesOf({ ...s, downloaded: all });
    // With a view open the image shown stays, unless a scene made an image of its own (another day, another dataset): that one is shown.
    const shownBefore = open ? shownImageOf(viewImagesOf(s), s.shownImage) : null;
    const newImage = open ? images.find((image) => image.ids.some((id) => id in added) && !viewImagesOf(s).some((old) => old.key === image.key)) : undefined;
    const first = open ? (newImage ?? images.find((image) => image.key === shownBefore?.key) ?? firstImageOf(images, s)) : firstImageOf(images, s);
    const applied = first ? defaultLookOf(s, first) : {};
    set({
      error: null,
      ...(problem ? { notice: problem } : {}),
      focusMode: true,
      viewOfLayer: false,
      resultViewLayerId: null,
      cropToAoi,
      // The view keeps the area it is opened with.
      viewAoi: cropToAoi ? s.aoi : null,
      // A crop takes the results off the map and drops the tick of the scenes it was made of, so that their quicklooks
      // do not lie beside the crop; the view does not hang on the choice any more, and a scene ticked again shows like any
      // other (Otto, 27.10.2026). The whole scene keeps the tick and the switch.
      ...(cropToAoi ? { selectedIds: s.selectedIds.filter((id) => !(id in all)), ...setResultsOnMap(false) } : {}),
      showDownloaded: true,
      downloaded: all,
      ...(open
        ? first && shownBefore && first.key !== shownBefore.key
          ? moveToImage(s, first, shownBefore)
          : {}
        : { shownImage: first?.key ?? null, viewLooks: {}, savedLooks: {}, appliedRender: applied, ...pendingFieldsOf(applied) }),
    });
    // The stretch and the mosaics are asked for together; the view says "Loading…" until both are here,
    // because a time step draws nothing until its mosaic has answered.
    const mosaics = get().loadMosaics();
    // A view that stays keeps the fields it has: the range measured at the start is the new view's.
    if (!open) await get().autoStretch();
    set({ focusLoading: true });
    await mosaics;
    set({ focusLoading: false });
  },
  // The mosaics of the time steps the view holds, which the map draws once they are here.
  loadMosaics: async () => {
    const s = get();
    if (!s.focusMode) return;
    const groups = sectionsForView(s).flatMap((section) => section.groups);
    await fetchMosaics(
      set,
      get,
      passesOf(Object.entries(s.downloaded), groups).map((entries) => ({
        datasetId: entries[0][1].datasetId,
        entries,
        index: viewIndexOf(s.appliedRender, s.datasets.find((d) => d.id === entries[0][1].datasetId)?.collection),
      })),
    );
  },
  // "Clear" in the view: takes the view off the map, nothing else. The choice of scenes, what was pinned and show or hide
  // of the results stay.
  exitFocus: () => set({ ...LEAVE_FOCUS }),
  // "Change image": takes the view off the map and opens the results to choose another scene. Show or hide stays.
  // "Change image" goes back to the search results: they are shown and their row goes on top of the layer manager (Otto, 2.11.2026).
  changeImage: () => set((s) => ({ ...LEAVE_FOCUS, ...setResultsOnMap(true), resultsAt: 0, ...(hasResultsPanel(s.sections) ? { dock: 'results' as const } : {}) })),
  showImage: (key) =>
    set((s) => {
      const images = viewImagesOf(s);
      const shown = shownImageOf(images, s.shownImage);
      const image = images.find((x) => x.key === key);
      return image && s.focusMode && image.key !== shown?.key ? moveToImage(s, image, shown) : {};
    }),
  stepImage: (delta) =>
    set((s) => {
      const images = viewImagesOf(s);
      const shown = shownImageOf(images, s.shownImage);
      if (!shown || !s.focusMode) return {};
      const here = images.filter((image) => image.datasetId === shown.datasetId);
      const next = here[here.indexOf(shown) + delta];
      return next ? moveToImage(s, next, shown) : {};
    }),
  chooseViewDataset: (datasetId) =>
    set((s) => {
      const images = viewImagesOf(s);
      const shown = shownImageOf(images, s.shownImage);
      const first = images.find((image) => image.datasetId === datasetId);
      return first && s.focusMode && first.key !== shown?.key ? moveToImage(s, first, shown) : {};
    }),
  chooseViewIndex: (name) => {
    set((s) => {
      const shown = shownImageOf(viewImagesOf(s), s.shownImage);
      if (!shown || !s.focusMode) return {};
      const collection = s.datasets.find((d) => d.id === shown.datasetId)?.collection;
      // Without an index the image goes back to what the dataset shows: the look saved for it ("Apply to all") unless that
      // names an index too, else the standard one.
      const saved = s.savedLooks[shown.datasetId];
      const plain = saved && !saved.index && !saved.band ? saved : defaultLookOf(s, shown);
      const preset = name === null ? null : viewIndexOf({ index: name }, collection);
      if (name !== null && !preset) return {};
      // Only the fields change: the map draws it once "Apply" is pressed, like the colormap and the range.
      return pendingFieldsOf(preset ? indexLookOf(preset) : plain);
    });
  },
  // One band of the data in place of the standard picture or an index: only the fields change, and the range is measured for the
  // band as for any other pick, so that "Apply" has values to draw (NM4-45). The image is drawn from the asset of the band once
  // "Apply" is pressed (`reconcileBands`).
  chooseViewBand: (band) => {
    const s = get();
    const shown = shownImageOf(viewImagesOf(s), s.shownImage);
    if (!shown || !s.focusMode) return;
    const collection = s.datasets.find((d) => d.id === shown.datasetId)?.collection;
    if (band === null) {
      const saved = s.savedLooks[shown.datasetId];
      set(pendingFieldsOf(saved && !saved.index && !saved.band ? saved : defaultLookOf(s, shown)));
      return;
    }
    const item = sectionsForView(s).flatMap((x) => x.items).find((it) => it.id === shown.ids[0]);
    if (!bandAssetsOf(item, collection).includes(band)) return;
    set({ pendingBand: band, pendingIndex: '', pendingColormapName: '', pendingVmin: '', pendingVmax: '', pendingChannels: [] });
    void get().autoStretch();
  },
  toggleDownloaded: () => set((s) => ({ showDownloaded: !s.showDownloaded })),
  setViewOpacity: (opacity) => set({ viewOpacity: Number.isFinite(opacity) ? Math.max(0, Math.min(1, opacity)) : 1 }),
  setPendingColormapName: (pendingColormapName) => set({ pendingColormapName }),
  setPendingVmin: (pendingVmin) => set({ pendingVmin }),
  setPendingVmax: (pendingVmax) => set({ pendingVmax }),
  // One end of one channel: the first change splits the shared range into three.
  setPendingChannel: (channel, end, text) =>
    set((s) => ({ pendingChannels: colourChannelsOf(s).map((range, index) => (index === channel ? { ...range, [end]: text } : range)), pendingUnit: 'value' })),
  // The unit of one channel of a colour picture, and the pair typed in it (UI-03e); the others keep theirs.
  setPendingChannelUnit: (channel, unit) =>
    set((s) => ({
      pendingChannels: colourChannelsOf(s).map((range, index) => {
        if (index !== channel) return range;
        const { percent, ...values } = range;
        return unit === 'percent' ? { ...values, percent: percent ?? { ...DEFAULT_PERCENT } } : values;
      }),
      pendingUnit: 'value',
    })),
  setPendingChannelPercent: (channel, end, text) =>
    set((s) => ({
      pendingChannels: colourChannelsOf(s).map((range, index) => (index === channel ? { ...range, percent: { ...(range.percent ?? DEFAULT_PERCENT), [end]: text } } : range)),
      pendingUnit: 'value',
    })),
  // Into the fields, drawn with "Apply" like a band (Otto, 3.11.2026), in the view and in the settings of a layer.
  quickIndex: async (name) => {
    const s = get();
    s.chooseViewIndex(s.pendingIndex === name ? null : name);
    set({ enhance: null });
  },
  // Into the fields, drawn with "Apply" like an index (Otto, 3.11.2026, zu #282): every channel of a colour picture at the usual pair, each in
  // percentiles on its own (UI-03e); one band as the shared pair. A second click puts the fields back as they were, also without "Apply".
  enhanceContrast: async () => {
    const s = get();
    if (enhanceOn(s)) {
      set({ ...pendingFieldsOf(s.enhance!.before), enhance: null });
      return;
    }
    const before = lookOfPendingFields(s);
    if (colourView(s)) set({ pendingChannels: colourChannelsOf(s).map(({ vmin, vmax }) => ({ vmin, vmax, percent: { ...DEFAULT_PERCENT } })), pendingUnit: 'value' });
    else set({ pendingUnit: 'percent', pendingPercentLow: DEFAULT_PERCENT.low, pendingPercentHigh: DEFAULT_PERCENT.high });
    set({ enhance: { look: lookOfPendingFields(get()), before } });
  },
  // Commits the pending fields (F18) — nothing renders differently until this
  // runs, which is the point of an explicit "Apply".
  // "Apply" draws the shown image with the fields and nothing else (NM4-53); other images keep their look.
  applyRender: async () => {
    const s = get();
    // Typed in percentiles, the values come from the statistics first (NM4-65 part 4).
    if (inPercent(s)) {
      await applyPercentRender(set, get);
    } else {
      set({ appliedRender: { ...s.appliedRender, ...lookOfPendingFields(s) } });
    }
    // The settings of a pinned layer change the layer itself, at its place in the list (Otto, 1.11.2026): what is applied is seen, as in
    // the view, once "Apply" is pressed (also a band); it is kept only with "Save", and closing the settings puts the saved look back
    // (`revertViewLayer`).
    const now = get();
    const layer = now.viewOfLayer ? layerOfView(now.layers, { ...now, aoi: now.viewAoi }) : null;
    if (!layer) return;
    const render = { ...now.appliedRender };
    let drawn = layerDraw(get, layer, render);
    if ('need' in drawn) drawn = await layerDrawnWith(set, get, layer, render);
    if ('problem' in drawn) {
      set({ error: drawn.problem });
      return;
    }
    set((t) => ({
      layers: t.layers.map((l) =>
        l.id === layer.id
          ? { ...l, ...drawn, restore: { ...l.restore, ...drawn.restore }, saved: l.saved ?? { opacity: l.opacity, overlays: l.overlays, downloaded: l.restore.downloaded, appliedRender: l.restore.appliedRender } }
          : l,
      ),
    }));
  },
  revertViewLayer: (id) =>
    set((s) => ({
      layers: s.layers.map((l) => {
        if (l.id !== id || !l.saved) return l;
        const { opacity, overlays, downloaded, appliedRender } = l.saved;
        return { ...l, opacity, overlays: overlays ?? l.overlays, restore: { ...l.restore, downloaded: downloaded ?? l.restore.downloaded, appliedRender: appliedRender ?? l.restore.appliedRender }, saved: undefined };
      }),
    })),
  setPendingUnit: (pendingUnit) => set({ pendingUnit }),
  setPendingPercent: (end, text) => set(end === 'low' ? { pendingPercentLow: text } : { pendingPercentHigh: text }),
  // "Save" (NM4-53, Otto 29.10.2026): the fields become the look of every image of the dataset that is shown, for the
  // length of the view. If the view is the picture of a pinned layer, the layer keeps the look too (NM4-50).
  saveViewLook: async () => {
    // Percentiles that are not applied yet give their values first, so that what is kept is what is drawn; only then is it
    // asynchronous, any other "Save" is done when the call returns.
    const percentsApplied = () => {
      const asked = lookOfPendingFields(get());
      const applied = get().appliedRender;
      return samePercent(applied.percent, asked.percent) && samePercents(applied.percentChannels, asked.percentChannels);
    };
    if (inPercent(get()) && !percentsApplied()) {
      return applyPercentRender(set, get).then(() => {
        if (percentsApplied()) return get().saveViewLook();
      });
    }
    let s = get();
    const render = { ...s.appliedRender, ...lookOfPendingFields(s) };
    const layer = layerOfView(s.layers, { ...s, aoi: s.viewAoi });
    let layers = s.layers;
    if (layer) {
      let drawn = layerDraw(get, layer, render);
      if ('need' in drawn) drawn = await layerDrawnWith(set, get, layer, render);
      if ('problem' in drawn) {
        set({ error: drawn.problem });
        return;
      }
      s = get();
      // "Save" in the view of a layer keeps the layer as it is drawn: what was set aside for the settings to be closed is not wanted any more.
      layers = s.layers.map((l) => (l.id === layer.id ? { ...l, ...drawn, saved: undefined, restore: { ...l.restore, ...drawn.restore } } : l));
    }
    const images = viewImagesOf(s);
    const shown = shownImageOf(images, s.shownImage);
    if (!shown) {
      set({ appliedRender: render, layers });
      return;
    }
    const viewLooks = { ...s.viewLooks };
    for (const image of images) if (image.datasetId === shown.datasetId) delete viewLooks[image.key];
    set({ appliedRender: render, layers, viewLooks, savedLooks: { ...s.savedLooks, [shown.datasetId]: render } });
  },
  // Re-measures the stretch from `/statistics` (adr/0006 §3.4) and writes it into
  // the pending fields only — still needs "Apply" to take effect on the map.
  autoStretch: async () => {
    const s = get();
    // In percentiles the usual stretch is the 2nd to the 98th (NM4-65 part 4): nothing to measure, "Apply" takes the values. A colour
    // picture does that for each channel typed in percentiles and measures the others (UI-03e).
    const channels = colourView(s) ? colourChannelsOf(s) : null;
    const usual = (channel: ChannelRange): ChannelRange => (channel.percent ? { ...channel, percent: { ...DEFAULT_PERCENT } } : channel);
    if (channels?.length && channels.every((channel) => channel.percent)) {
      set({ pendingChannels: channels.map(usual), pendingUnit: 'value' });
      return;
    }
    if (!channels && s.pendingUnit === 'percent') {
      set({ pendingPercentLow: DEFAULT_PERCENT.low, pendingPercentHigh: DEFAULT_PERCENT.high });
      return;
    }
    // The area of the crop, else the first scene of the image that is shown (the first of the view where nothing is shown yet); the
    // index in the fields is measured as it will be drawn: the tile route with the same step, not the asset of the scene.
    const measure = viewMeasure(s);
    if (!measure) return;
    set({ focusLoading: true });
    try {
      const { statistics: stats } = await measureView(measure);
      const range = autoRescale(stats);
      if (range && channels?.some((channel) => channel.percent)) {
        const measured = { vmin: fieldNumber(range[0]), vmax: fieldNumber(range[1]) };
        set({ pendingVmin: measured.vmin, pendingVmax: measured.vmax, pendingChannels: channels.map((channel) => (channel.percent ? usual(channel) : measured)), pendingUnit: 'value' });
      } else if (range) set({ pendingVmin: fieldNumber(range[0]), pendingVmax: fieldNumber(range[1]), pendingChannels: [] });
    } catch (e) {
      set({ notice: `Could not measure a stretch automatically: ${(e as Error).message}` });
    } finally {
      set({ focusLoading: false });
    }
  },
  // Zoom to everything that is chosen at once: the AOI, the open view and the layers that are shown (`zoomSelection.ts`). With none of
  // them the button is locked (App.tsx) and this is never called.
  zoomToView: () => {
    const bb = zoomTarget(get());
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
  // A click on a group's head, open or close, ends the playing of the timeline (NM4-18, Otto, 30.10.2026); the playing itself
  // moves the step with `setActiveGroupIndex`.
  toggleResultsGroup: (index) => {
    const s = get();
    if (index === s.expandedGroupIndex) set({ expandedGroupIndex: null, playing: false });
    // In one change with the step, or the playing would take the step it is at for one that has arrived.
    // An opened group, like a clicked scene, shows the block at the bottom again (NM4-66); a closed one does not.
    else set({ activeGroupIndex: index, expandedGroupIndex: index, playing: false, selectionBlockClosed: false });
  },
  // The "x" of the block at the bottom (NM4-66). It has the play button, so closing it ends the playing; the ticks, the
  // results on the map and the layers stay as they are.
  closeSelectionBlock: () => set({ selectionBlockClosed: true, playing: false }),
  focusItem: (id) => {
    const idx = groupIndexOfItem(get().groups, id);
    if (idx >= 0) set({ activeGroupIndex: idx, expandedGroupIndex: idx, selectionBlockClosed: false });
  },
  toggleSelected: (id) =>
    set((s) => ticking(s, s.selectedIds.includes(id) ? s.selectedIds.filter((x) => x !== id) : [...s.selectedIds, id])),
  selectAllInActiveGroup: () =>
    set((s) => {
      const group = s.groups[s.activeGroupIndex];
      if (!group) return {};
      const merged = new Set([...s.selectedIds, ...group.items.map((it) => it.id)]);
      return ticking(s, [...merged]);
    }),
  // M4-29: "Select all" takes the loaded scenes only — never more pages — and
  // the limits (merge, job size, batch) still answer where they always did.
  selectAllLoaded: () =>
    set((s) => {
      const here = new Set(s.items.map((it) => it.id));
      return ticking(s, [...s.selectedIds.filter((id) => !here.has(id)), ...here]);
    }),
  toggleGroupSelected: (index) =>
    set((s) => {
      const ids = s.groups[index]?.items.map((it) => it.id) ?? [];
      if (ids.length === 0) return {};
      const all = ids.every((id) => s.selectedIds.includes(id));
      return ticking(
        s,
        all ? s.selectedIds.filter((id) => !ids.includes(id)) : [...s.selectedIds, ...ids.filter((id) => !s.selectedIds.includes(id))],
      );
    }),
  // The ticks of the scenes the list shows; those on other datasets stay (NM4-50).
  clearSelection: () =>
    set((s) => {
      const here = new Set(s.items.map((it) => it.id));
      return { selectedIds: s.selectedIds.filter((id) => !here.has(id)), playing: false };
    }),
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
  setSearchFilter: (datasetId, property, input) => {
    const { [property]: _before, ...others } = get().searchFilters[datasetId] ?? {};
    changeSearchFilters(set, get, datasetId, isSet(input) ? { ...others, [property]: input } : others);
  },
  setSearchWithin: (datasetId, on) => changeSearchWithin(set, get, datasetId, on),
  setSearchEvaluate: (evaluate) => {
    if (get().searchEvaluate === evaluate) return;
    set({ searchEvaluate: evaluate });
    // Only a search that was, or now would be, judged per pass cannot go on with its token.
    const ctx = get().searchContext;
    if (ctx && (ctx.query.evaluate !== undefined || evaluationOf(get(), ctx.query.queryByCollection ?? {}).evaluate)) {
      dropPageToken(set, get);
    }
  },
  resetSearchFilters: (datasetId) => {
    changeSearchFilters(set, get, datasetId, {});
    changeSearchWithin(set, get, datasetId, false);
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
  setMapViewport: (mapZoom, viewportBbox, viewportSize) => {
    set({ mapZoom, viewportBbox, viewportSize });
    scheduleCoverageRefresh(set, get);
  },
  setPlaying: (playing) => set({ playing }),
  setError: (error) => set({ error }),
  setNotice: (notice) => set({ notice }),
  setAppearance: (appearance) => {
    saveAppearance(appearance);
    set({ appearance, theme: themeOf(appearance) });
  },
  followSystemTheme: (systemDark) => {
    const { appearance, theme } = get();
    if (appearance !== 'system') return;
    const next = themeOf(appearance, systemDark);
    if (next !== theme) set({ theme: next });
  },
  setTipLevel: (level) => {
    saveTipLevel(level);
    setTipLevel(level);
    set({ tipLevel: level });
  },
  setProjection: (projection) => {
    saveProjection(projection);
    set({ projection });
  },
  setTerrain: (terrain, keep = true) => {
    if (keep) saveTerrain(terrain);
    set({ terrain });
  },
  setBasemap: (basemap) => {
    saveBasemap(basemap);
    set({ basemap });
  },
  showSharedLook: ({ basemap, projection, relief }) =>
    set((s) => ({ basemap, projection, terrain: false, ...(relief ? { overlays: { ...s.overlays, relief: true } } : {}) })),
  setOverlay: (overlay, on) => {
    const overlays = { ...get().overlays, [overlay]: on };
    saveOverlays(overlays);
    set({ overlays });
  },

  runSearch: async () => {
    // One walk at a time (NM4-26): a second one would ask every page again while the first one goes on.
    if (get().searching) return;
    const { aoi, aoiPoint, dateFrom, dateTo, selectedDatasetIds, datasets } = get();
    if (!aoi) {
      set({ error: 'Draw or search an area of interest first.' });
      return;
    }
    // M3-10: every ticked dataset is asked at once, in one mixed search (M3-13).
    const chosen = viewableDatasets(datasets, selectedDatasetIds);
    if (chosen.length === 0) {
      const blocked = datasets.find((d) => selectedDatasetIds.includes(d.id));
      set({ error: blocked && !blocked.viewable ? `This dataset cannot be shown yet: ${blocked.reason}` : 'Choose a dataset to search.' });
      return;
    }
    if (searchFiltersInvalid(get())) {
      set({ error: 'Correct the marked search filters first.' });
      return;
    }
    // M3-08 F2a/F5a: a point AOI searches by the point itself, a polygon by its
    // true shape, a rectangle by its bbox — `aoiPoint` is only ever read here,
    // never for display or the download crop, which stay on `aoi`.
    // A filter of the platform, or a search per pass, works on the AOI, the square around a point: that search is asked with the
    // square too, the point would let scenes through that it cannot measure (Otto, 06.11.2026: a point is an area as well).
    const wanted = filterQueriesOf(get(), chosen.map((d) => d.id));
    const measuresArea = anyMeasuresAoi({ queryByCollection: wanted, ...evaluationOf(get(), wanted) });
    const area = searchArea(aoi, measuresArea ? null : aoiPoint);
    if (!area.bbox && !area.intersects) {
      set({ error: 'Could not compute a search area for the area of interest.' });
      return;
    }
    set({
      searching: true,
      error: null,
      notice: null,
      playing: false,
      dock: withoutControls(get().dock),
      ...forgetSearch(),
      ...LEAVE_FOCUS,
      ...setResultsOnMap(true),
    });
    // "Clear all" or another step that drops the results may come before the answer.
    const gen = searchGen;
    try {
      const ids = chosen.map((d) => d.id);
      const asked = filterQueriesOf(get(), ids);
      const query = {
        collections: ids,
        bbox: area.bbox,
        intersects: area.intersects,
        datetime: buildDatetime(dateFrom, dateTo),
        ...queryByCollectionOf(asked),
        ...evaluationOf(get(), asked),
        // A long AOI is searched by its box; the clouds are measured in the AOI itself (plan §6.5, KE1).
        ...(area.truncatedNotice && needsAoiBody({ queryByCollection: asked }) ? { aoi } : {}),
      };
      // What this search is asked with, kept as it starts: a later change of the fields or of "Evaluate" is compared to it.
      const startedWith = askedState(get(), ids);
      if (anyMeasuresAoi(query)) {
        await walkAoiSearch(set, get, {
          base: {
            datasetIds: ids,
            query,
            dateFrom,
            dateTo,
            aoi,
            truncatedNotice: area.truncatedNotice ?? null,
            features: [],
            answer: NO_ANSWER_FILTERS,
            numberMatched: null,
            nextToken: null,
            openCollections: null,
          },
          fresh: true,
          // Filters or area changed while the first answer was on its way.
          unchanged: () => askedState(get(), ids) === startedWith,
        });
        // A dataset searched without the limit gets its nearest date as always; one searched with it does not (KE4).
        const { openSectionId } = get();
        if (openSectionId && get().searchContext) await runFallback(set, get, openSectionId, false);
        return;
      }
      const page = await api.searchAllPages(query, MAX_SEARCH_ITEMS);
      if (gen !== searchGen) return;
      // Filters changed while the search ran (the page token cannot be dropped yet, there is no search on screen):
      // "Load more" would go on with filters the fields no longer show.
      const filtersKept = askedState(get(), ids) === startedWith;
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
          nextToken: filtersKept ? page.nextToken : null,
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
        notice: null,
        sections: [],
        searchContext: null,
        ...openSectionState(null),
        dock: withoutResults(get().dock) ?? 'controls',
      });
    } finally {
      set({ searching: false });
    }
  },

  stopSearch: () => stopWalk(),

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
    if (anyMeasuresAoi(ctx.query)) {
      try {
        await walkAoiSearch(set, get, { base: ctx, token: ctx.nextToken, fresh: false, unchanged: () => true });
        if (gen === searchGen) {
          set({ loadMoreUsed: true });
          const { openSectionId } = get();
          if (openSectionId) void runFallback(set, get, openSectionId, false);
        }
      } finally {
        if (gen === searchGen) set({ loadingMore: false });
      }
      return;
    }
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
      set({ loadMoreUsed: true });
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
      set({ error: blocked && !blocked.viewable ? `This dataset cannot be shown yet: ${blocked.reason}` : 'Choose a dataset to search.' });
      return;
    }
    set({ sceneLookupLoading: true, error: null, ...setResultsOnMap(true) });
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
      selectedIds: [item.id],
      dock: 'results',
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
    if (dataset?.browse === 'full_resolution') await get().enterFocus(false, false);
  },
}));

// The settings of a result are closed — another layer chosen, the view left, the panel shut: what was applied and not saved
// goes without asking, and the layer is drawn as saved again (NM4-50).
useAppStore.subscribe((s, prev) => {
  if (prev.resultViewLayerId !== null && prev.resultViewLayerId !== s.resultViewLayerId) s.revertResultLayer(prev.resultViewLayerId);
});

// The scenes of each image of the view are drawn from the asset its look names (NM4-45): a band is a look like the colormap, and the
// store keeps the two together in one place, whatever changed the look (applying, "Apply to all", stepping to another image, a layer
// opened again). Only a look with a band, or a scene already moved to one, is touched. The mosaic of the new asset is asked for.
function reconcileBands(): void {
  const s = useAppStore.getState();
  if (!s.focusMode || Object.keys(s.downloaded).length === 0) return;
  const images = viewImagesOf(s);
  const shown = shownImageOf(images, s.shownImage);
  let downloaded = s.downloaded;
  for (const image of images) {
    const look = lookOfImage(s, image, shown);
    for (const id of image.ids) {
      const info = downloaded[id];
      if (!info) continue;
      const moved = withAsset(id, info, assetOfLook(info, look));
      if (moved !== info) downloaded = { ...downloaded, [id]: moved };
    }
  }
  if (downloaded === s.downloaded) return;
  useAppStore.setState({ downloaded });
  void s.loadMosaics();
}

// The tile of an index is a mosaic with a step, asked from the selection of the assets the index reads: another index, or the image
// of another look, asks for it.
useAppStore.subscribe((s, prev) => {
  if (s.focusMode && (s.appliedRender.index !== prev.appliedRender.index || s.shownImage !== prev.shownImage)) void s.loadMosaics();
});

useAppStore.subscribe((s, prev) => {
  if (s.appliedRender !== prev.appliedRender || s.viewLooks !== prev.viewLooks || s.savedLooks !== prev.savedLooks || s.shownImage !== prev.shownImage) {
    reconcileBands();
  }
});

// The settings of a pinned layer are closed — the red x, Esc, another layer chosen, the view left: what was applied and not saved goes
// without asking, and the layer is drawn as saved again (NM4-54, Otto, 1.11.2026).
useAppStore.subscribe((s, prev) => {
  if (prev.viewOfLayer && prev.viewLayerId !== null && (!s.viewOfLayer || s.viewLayerId !== prev.viewLayerId)) s.revertViewLayer(prev.viewLayerId);
});

// What the job of whole scenes will cost, asked of the platform after the choice has rested a moment; only for a form that is a job.
function refreshJobEstimate(): void {
  clearTimeout(downloadJobTimer);
  downloadEstimateAbort?.abort();
  downloadEstimateAbort = null;
  const s = useAppStore.getState();
  const dataset = downloadDatasetOf(s);
  const bands = chosenBands(s.downloadTable, s.downloadBands);
  const common = commonResolutionOf(bands, s.downloadCommonResolution);
  const form = effectiveForm(bands, s.downloadForm);
  const order =
    s.downloadOutcome === 'originals' && bands.length > 0 && form !== 'per_band' && dataset && layoutBlock(form, bands, common) === null
      ? sceneJobOrder({ datasetId: dataset.id, passes: s.downloadPasses ?? [], assets: bands.map((band) => band.asset), layout: layoutOf(form, common) })
      : null;
  if (!order) {
    useAppStore.setState({ downloadJobNote: null });
    return;
  }
  useAppStore.setState({ downloadJobNote: { state: 'estimating' } });
  const controller = new AbortController();
  downloadEstimateAbort = controller;
  downloadJobTimer = setTimeout(() => {
    void estimateSceneJob(order, controller.signal).then((note) => {
      if (!controller.signal.aborted) useAppStore.setState({ downloadJobNote: note });
    });
  }, DOWNLOAD_ESTIMATE_DELAY_MS);
}

// "Download" of whole scenes. One file per band (and a dataset whose items list no bands) is loaded in the browser from the source:
// `OriginalFiles` starts once `downloadStarted` is set. One file per resolution and one multi-band file are a job on the platform, placed,
// waited for and downloaded here; the person never sees it in the list of jobs.
async function startWholeScenes(s: AppState): Promise<void> {
  const dataset = downloadDatasetOf(s);
  const table = s.downloadTable;
  const bands = chosenBands(table, s.downloadBands);
  if (table.length > 0 && bands.length === 0) return;
  const form = effectiveForm(bands, s.downloadForm);
  if (table.length === 0 || form === 'per_band') {
    useAppStore.setState({ downloadStarted: true, error: null });
    return;
  }
  const common = commonResolutionOf(bands, s.downloadCommonResolution);
  const block = layoutBlock(form, bands, common);
  const order = dataset
    ? sceneJobOrder({ datasetId: dataset.id, passes: s.downloadPasses ?? [], assets: bands.map((band) => band.asset), layout: layoutOf(form, common) })
    : null;
  const note = s.downloadJobNote;
  // Only what the estimate let through (or a try that failed, which may be tried again).
  if (block || !order || (note?.state !== 'ready' && note?.state !== 'failed')) return;
  const run = async () => {
    const controller = new AbortController();
    downloadJobAbort = controller;
    useAppStore.setState({ downloading: true, error: null, downloadStatus: 'Preparing…' });
    const problem = await downloadSceneJob({ order, signal: controller.signal, onStatus: (text) => useAppStore.setState({ downloadStatus: text }) });
    if (downloadJobAbort === controller) downloadJobAbort = null;
    if (controller.signal.aborted) {
      useAppStore.setState({ downloading: false, downloadStatus: null });
    } else if (problem) {
      // The reason stays in the dialog, which may try again.
      useAppStore.setState({ downloading: false, downloadStatus: null, downloadJobNote: { state: 'failed', ...problem, parts: note.parts } });
    } else {
      useAppStore.setState({
        downloading: false,
        downloadStatus: null,
        downloadDialogLayerId: null,
        downloadSelection: false,
        downloadView: null,
        downloadOutcome: null,
        notice: `Downloaded "${dataset?.title ?? ''}".`,
      });
    }
  };
  if (note.parts.length > 0) {
    afterResampling = () => void run();
    useAppStore.setState({ downloadResampling: note.parts });
    return;
  }
  await run();
}
