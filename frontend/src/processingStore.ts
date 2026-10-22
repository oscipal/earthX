// The processing panel's state (M4-13 §3.5): the process description per
// dataset, the draft of an order, its estimate, and the jobs of this tab. A
// store of its own next to `store.ts`; it reads the selection (dataset,
// scenes, AOI) from there and never writes to it.
//
// An order names the scenes of one pass (M4-12b); the pass is the one the
// selection has (in the AOI, for "AOI only"), or the one the user picks. It
// covers the whole scenes by default, or only the AOI (M4-13c §3.2). "Run as"
// makes one order per pass or per scene instead (M4-13c-4, §3.6).
//
// The map preview of the first steps (M4-13c-2, M4-18b) is computed from the draft and
// the selection; it follows 400 ms after the last change (K7).
//
// The draft belongs to one dataset: a new dataset drops it. A new AOI drops
// nothing but the estimate (M4-13c K3). An estimate belongs to exactly one
// order (K4): any change to the order makes it disappear, and "Start job"
// waits for a new one.

import { create } from 'zustand';

import { fetchItem, HttpError } from './api';
import { crsBlockReason, type CrsEntry } from './crsUnit';
import type { DatasetOption } from './datasets';
import { loadStoredJobs, saveStoredJobs, trackJob, type TrackerOptions } from './jobTracker';
import {
  batchPass,
  effectiveRunAs,
  ESTIMATE_PARALLEL,
  foreignReason,
  foreignScenes,
  jobTitle,
  runChoices,
  runPool,
  unitsOf,
  type BatchUnit,
  type RunAs,
  type RunChoice,
} from './processingBatch';
import {
  canonicalJson,
  dismissJob,
  estimateOrder,
  fetchCrs,
  fetchProcess,
  fetchResults,
  fetchResultTileJson,
  placeJob,
  type AoiProvenance,
  type EstimateDocument,
  type Order,
  type ResultTileJson,
  type StatusInfo,
} from './processing';
import {
  handRange,
  isResultExpired,
  positive,
  resultGsd,
  resultLayerName,
  resultRender,
  resultStats,
  type ResultStats,
  resultTileTemplate,
  tilesHref,
} from './resultLayer';
import {
  aoiProvenanceFor,
  bandSources,
  buildOrder,
  candidateItems,
  draftFromOrder,
  isArea,
  namesInExpression,
  orderAssets,
  passesOf,
  processBlockReason,
  processInfo,
  stepOfRefusal,
  type Area,
  type BandSource,
  type BuiltOrder,
  type DraftStep,
  type Pass,
  type ProcessInfo,
} from './processingOrder';
import {
  DEFAULT_RANGE,
  planPreview,
  probeChain,
  previewOverlays,
  previewSpec,
  refusedNote,
  shortenPlan,
  type RefusedStep,
  rescaleOf,
  type PreviewRange,
  type PreviewSpec,
} from './processingPreview';
import { chooseDtype, dtypeOptions, effectiveDtype, integerNote, type Choice, type DtypeOption } from './processingDefaults';
import { buildTileUrl } from './mapLayers';
import { readRecipe } from './recipeFile';
import { initialValues, type FieldValue } from './schemaForm';
import type { MapLayer } from './layers';
import { selectionItemsFrom, useAppStore, type AppState } from './store';
import { buildGroups } from './grouping';
import type { StacItem, TimeStepGroup } from './types';

// Where a panel opens from: the "Area" it starts with, and the scenes the
// results on screen lack.
export interface ProcessingEntry {
  area?: Area;
  // Scenes of the entry that the results on screen do not hold (see `ExtraScenes`);
  // `null` drops those of an earlier entry. Left out: they stay.
  extraScenes?: ExtraScenes | null;
}

// Scenes fetched one by one because a layer or the full-resolution view names them
// but the results on screen do not (M4-13c-2, Otto 19.10.2026), with the passes
// the results list would have put them in. `orderView` reads them next to the
// results; nothing else does.
export interface ExtraScenes {
  // The dataset they were fetched under.
  datasetId: string | null;
  items: StacItem[];
  groups: TimeStepGroup[];
}

export type Description =
  | { state: 'loading' }
  | { state: 'ready'; info: ProcessInfo }
  | { state: 'error'; message: string };

export interface Refusal {
  // The order it refused (canonical JSON); shown only while the draft is
  // still that order.
  key: string;
  message: string;
  // The step the server named (0-based), shown at that step; `null` for the
  // order as a whole.
  step: number | null;
  // The HTTP status of the refusal (a `413` suggests "AOI only", K2); `null`
  // when there was no answer.
  status: number | null;
}

export type JobPhase = 'active' | 'successful' | 'failed' | 'dismissed' | 'gone';

export interface ResultFile {
  file: string;
  label: string;
}

export interface JobEntry {
  jobID: string;
  expires: string;
  status: StatusInfo | null;
  phase: JobPhase;
  files: ResultFile[] | null;
  // `earthx:resampled` of the result (Prinzip 2.9); `null` until the results are read.
  resampled: boolean | null;
  failure: string | null;
  error: string | null;
  cancelling: boolean;
  // `/results` answered `410`: the result is gone before the row's own clock says so.
  expired: boolean;
  // What the panel called the job (K5); `null` for a job of the download dialog.
  title: string | null;
  // The tiles of a raster result (the link `tiles` of the results document, M4-13c-5);
  // `null` until the results are read, for an export, and for a result before this link existed.
  tiles: JobTiles | null;
  // The statistics of the AOI per band, for the colour scale of the layer (M4-32b); `null` until the
  // results are read, and for a result from before they were written.
  statistics: ResultStats | null;
  // The range and colormap the user had set by hand in the panel when the job was started; its
  // result is drawn with them and no other result is. `null` for the default range, for a job of
  // the download dialog, and for one taken up again after a reload (it is not kept in the tab).
  range: PreviewRange | null;
}

export interface JobTiles {
  // `/results/{result_id}/WebMercatorQuad/tilejson.json`, already checked (`resultLayer.ts::tilesHref`).
  href: string;
  // The columns of the raster and its stated pixel size in metres (projected CRS only):
  // what "Overview" needs to know about the data.
  width: number | null;
  gsd: number | null;
}

// What the review made of one job of a batch: its estimate, or the reason the
// server gave for refusing it.
export interface PartOutcome {
  unit: BatchUnit;
  doc: EstimateDocument | null;
  refusal: Refusal | null;
}

interface ProcessingState {
  open: boolean;
  // The window of the jobs of this tab (M4-13c §3.1), apart from the panel.
  jobsOpen: boolean;
  descriptions: Record<string, Description>;
  // What the server said about the target CRS codes typed so far (M4-13c-3); kept
  // across drafts, since a code means the same for every dataset.
  crs: Record<string, CrsEntry>;
  // `Pass.key` of the pass the user picked; `null` until then (a lone pass needs no pick).
  passKey: string | null;
  area: Area;
  // One job, or one per pass or per scene (M4-13c-4); the choice in force is `OrderView.runAs`.
  runAs: RunAs;
  extraScenes: ExtraScenes | null;
  steps: DraftStep[];
  picked: string[];
  dtype: string | null;
  // The range and colormap of the map preview: applied, and as edited (F3 (1)).
  range: PreviewRange;
  rangeDraft: PreviewRange;
  // What the map shows of the steps (their longest start that runs as tiles); `null` for none.
  preview: PreviewSpec | null;
  // Why the preview shows fewer steps than the draft chains, or none: the tiler's reason.
  previewNote: string | null;
  // "Review" was asked for this draft: empty required fields show their hint.
  reviewAsked: boolean;
  estimate: { key: string; doc: EstimateDocument } | null;
  // The review of a batch: one outcome per job, for the batch it was asked for.
  batch: { key: string; parts: PartOutcome[] } | null;
  reviewing: boolean;
  reviewError: Refusal | null;
  starting: boolean;
  startError: Refusal | null;
  // The jobs of a batch the server refused to start, for the batch they were started from.
  batchStartRefusals: { key: string; refusals: { label: string; message: string }[] } | null;
  jobs: JobEntry[];

  openProcessing: (entry?: ProcessingEntry) => void;
  processLayer: (layerId: string) => Promise<void>;
  processFocusView: () => Promise<void>;
  setRangeDraft: (patch: Partial<PreviewRange>) => void;
  applyRange: () => void;
  pinPreview: () => void;
  closeProcessing: () => void;
  // A finished job's result as a layer of its own on the map (M4-13c-5, plan §3.4).
  showResultOnMap: (jobID: string) => Promise<void>;
  openJobs: () => void;
  closeJobs: () => void;
  ensureDescription: (datasetId: string) => void;
  lookupCrs: (code: string, signal: AbortSignal) => Promise<void>;
  resetDraft: () => void;
  choosePass: (passKey: string) => void;
  setArea: (area: Area) => void;
  setRunAs: (runAs: RunAs) => void;
  addStep: (op: string, opVersion: number) => void;
  updateStep: (key: number, name: string, value: FieldValue) => void;
  moveStep: (key: number, direction: -1 | 1) => void;
  removeStep: (key: number) => void;
  togglePick: (asset: string) => void;
  setDtype: (dtype: string) => void;
  loadRecipe: (text: string, mode: LoadMode) => Promise<LoadResult>;
  reviewOrder: () => Promise<void>;
  startJob: () => Promise<void>;
  placeOrder: (order: Order, options?: { aoiProvenance?: AoiProvenance }) => Promise<{ jobID: string } | { message: string }>;
  cancelJob: (jobID: string) => Promise<void>;
  removeJob: (jobID: string) => void;
  resumeJobs: () => void;
}

// "Load recipe…" (M4-19d): the steps on the current selection, or the whole recipe.
export type LoadMode = 'steps' | 'everything';
export type LoadResult = { ok: true; notes: string[] } | { ok: false; reason: string };

// --- the order as the panel sees it --------------------------------------------

export interface OrderView {
  dataset: DatasetOption | undefined;
  info: ProcessInfo | null;
  // The scenes the order can be for — all selected ones, or those the AOI meets
  // for "AOI only" — split into passes, and the pass the order is for.
  candidates: StacItem[];
  passes: Pass[];
  // The pass of one job; for a batch, all the scenes of the batch in one piece.
  pass: Pass | null;
  // "Run as": what is offered, what is in force, and the jobs it makes. `parts`
  // has one entry per job, with its order once the draft is complete.
  runChoices: RunChoice[];
  runAs: RunAs;
  parts: OrderPart[];
  sources: BandSource[];
  assets: string[];
  // The type the order is sent with, and the options and notes around the choice.
  dtype: string;
  dtypeOptions: DtypeOption[];
  dtypeAutomatic: Choice | null;
  // The user changed it (and the choice stands); else the automatic type is sent.
  dtypeChosen: boolean;
  dtypeNote: string | null;
  built: BuiltOrder | null;
  // The text of the order, or of all orders of a batch; `null` while one is missing.
  key: string | null;
}

export interface OrderPart {
  unit: BatchUnit;
  order: Order | null;
}

// The candidates only change with the selection and the AOI; the intersection
// is the one costly part of the view, so the last answer is kept.
let lastCandidates: { inputs: unknown[]; result: { items: StacItem[]; passes: Pass[] } } | null = null;

function candidatesOf(app: SelectionState, area: Area): { items: StacItem[]; passes: Pass[] } {
  const inputs = [app.items, app.selectedIds, app.groups, app.activeGroupIndex, app.aoi, area];
  if (lastCandidates && lastCandidates.inputs.every((value, i) => value === inputs[i])) return lastCandidates.result;
  const selected = selectionItemsFrom(app);
  const items = area === 'scene' ? selected : isArea(app.aoi) ? candidateItems(selected, app.aoi) : [];
  const result = { items, passes: passesOf(items, app.groups) };
  lastCandidates = { inputs, result };
  return result;
}

export function bandMathExpressions(steps: readonly DraftStep[]): string[] {
  return steps
    .filter((step) => step.op === 'band_math' && typeof step.values.expression === 'string')
    .map((step) => step.values.expression as string);
}

// What the panel reads from the selection; a selector on these keeps the
// panel from rendering on every map move.
export type SelectionState = Pick<
  AppState,
  'datasets' | 'datasetId' | 'openSectionId' | 'items' | 'selectedIds' | 'groups' | 'activeGroupIndex' | 'aoi'
>;

export function selectionState(s: AppState): SelectionState {
  const { datasets, datasetId, openSectionId, items, selectedIds, groups, activeGroupIndex, aoi } = s;
  return { datasets, datasetId, openSectionId, items, selectedIds, groups, activeGroupIndex, aoi };
}

export function orderView(selection: SelectionState, p: ProcessingState): OrderView {
  const app = withExtraScenes(selection, p.extraScenes);
  const dataset = app.datasets.find((d) => d.id === app.datasetId);
  const description = app.datasetId ? p.descriptions[app.datasetId] : undefined;
  const info = description?.state === 'ready' ? description.info : null;
  const { items: candidates, passes } = candidatesOf(app, p.area);
  const runOptions = runChoices(passes, candidates);
  const runAs = effectiveRunAs(p.runAs, runOptions);
  const chosen = passes.find((c) => c.key === p.passKey) ?? (passes.length === 1 ? passes[0] : null);
  const units = unitsOf(runAs, chosen, passes, candidates);
  const pass = runAs === 'one' ? chosen : batchPass(runAs, units);
  const format = dataset?.collection['earthx:format'] ?? null;
  // The scenes of a pass agree on the assets and bands (the server checks it, M4-12a).
  const sources = pass ? bandSources(pass.items[0], format, info?.variableSeparator ?? null) : [];
  const assets = orderAssets(sources, p.picked, bandMathExpressions(p.steps));
  // The output type follows the data and the steps as they will be sent (Otto,
  // 12.10.2026); the resampling is the user's own choice and recommended nowhere.
  const inOrder = sources.filter((s) => assets.includes(s.asset));
  const choices = p.steps.map((step) => ({
    op: step.op,
    ...(typeof step.values.resampling === 'string' ? { resampling: step.values.resampling } : {}),
  }));
  const dtypes = info?.dtypes ?? [];
  const automatic = info ? chooseDtype({ steps: choices, bands: inOrder, allowed: dtypes }) : null;
  const options = automatic ? dtypeOptions({ dtypes, steps: choices }) : [];
  const dtype = automatic ? effectiveDtype(p.dtype, options, automatic) : '';
  // The results on screen are those of the open section; the extra scenes were fetched under the active dataset.
  const extraIds = new Set(p.extraScenes?.items.map((item) => item.id));
  const foundUnder = (item: StacItem) =>
    extraIds.has(item.id) ? (p.extraScenes?.datasetId ?? null) : (selection.openSectionId ?? selection.datasetId);
  const foreign = dataset ? foreignScenes(dataset.id, pass?.items ?? [], foundUnder) : [];
  const buildFor = (itemIds: string[]): BuiltOrder | null => {
    if (!info || !dataset) return null;
    const result = buildOrder({ datasetId: dataset.id, itemIds, area: p.area, aoi: app.aoi, steps: p.steps, assets, dtype, info });
    return foreign.length === 0 ? result : { ...result, order: null, problems: [...result.problems, foreignReason(foreign)] };
  };
  const builtParts = units.map((unit) => ({ unit, built: buildFor(unit.items.map((i) => i.id)) }));
  const built = builtParts[0]?.built ?? buildFor([]);
  const parts: OrderPart[] = builtParts.map(({ unit, built: b }) => ({ unit, order: b?.order ?? null }));
  // The text of the order, or of all orders of a batch: one serialisation either way.
  const key =
    parts.length > 0 && parts.every((part) => part.order)
      ? canonicalJson(runAs === 'one' ? parts[0].order : parts.map((part) => part.order))
      : null;
  return {
    dataset,
    info,
    candidates,
    passes,
    pass,
    runChoices: runOptions,
    runAs,
    parts,
    sources,
    assets,
    dtype,
    dtypeOptions: options,
    dtypeAutomatic: automatic,
    dtypeChosen: p.dtype !== null && p.dtype === dtype,
    dtypeNote: integerNote(dtype, choices, inOrder),
    built,
    key,
  };
}

// --- source layer and entries (M4-13c-2) ------------------------------------

// Why a layer cannot be the start of an order, or `null`. A picture made from
// scenes is no scene; the licence is the dataset's, as for the selection.
export function layerProcessBlock(layer: MapLayer, datasets: readonly DatasetOption[]): string | null {
  if (layer.derived) return 'A result cannot be processed further yet.';
  const dataset = datasets.find((d) => d.id === layer.restore.datasetId);
  return processBlockReason(dataset, layer.restore.itemIds.length);
}

// The latest entry that is fetching scenes: an older one that answers late
// finds itself superseded and does nothing.
let entryGeneration = 0;

// The scenes of the entry become the selection the panel reads. Those the results
// on screen lack are fetched one by one from the catalog (no new search, Otto
// 19.10.2026); they come back as the extra scenes of the entry. `null` when it
// cannot go on — the reason is in `error` — or when a newer entry took over.
async function selectScenes(ids: readonly string[], whose: string): Promise<ExtraScenes | null> {
  const generation = ++entryGeneration;
  const app = useAppStore.getState();
  const fail = (message: string) => {
    if (generation === entryGeneration) useAppStore.setState({ error: message });
    return null;
  };
  if (ids.length === 0) return fail(`There are no scenes in ${whose}.`);
  const missing = ids.filter((id) => !app.items.some((item) => item.id === id));
  let extra: ExtraScenes = { datasetId: app.datasetId, items: [], groups: [] };
  if (missing.length > 0) {
    const dataset = app.datasets.find((d) => d.id === app.datasetId);
    if (!app.datasetId || !dataset?.viewable) return fail('Pick a dataset first.');
    const datasetId = app.datasetId;
    const answers = await Promise.allSettled(missing.map((id) => fetchItem(datasetId, id)));
    if (generation !== entryGeneration) return null;
    const problems = answers.flatMap((answer, i) =>
      answer.status === 'rejected'
        ? [`${missing[i]}: ${answer.reason instanceof Error ? answer.reason.message : String(answer.reason)}`]
        : answer.value === undefined
          ? [`${missing[i]}: not found in the catalog`]
          : [],
    );
    if (problems.length > 0) return fail(`Could not load the scenes of ${whose}. ${problems.join('; ')}`);
    const items = answers.flatMap((answer) => (answer.status === 'fulfilled' && answer.value ? [answer.value] : []));
    try {
      extra = { datasetId, items, groups: buildGroups(items, dataset.resultsGroupBy) };
    } catch (error) {
      return fail(`Could not group the scenes of ${whose}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  useAppStore.setState({ selectedIds: [...ids] });
  return extra;
}

// The results on screen with the extra scenes beside them: a scene whose pass
// the results already hold joins that pass, any other pass is added at the end.
// The same arrays for the same inputs, so the candidates stay cached.
let lastWithScenes: { items: StacItem[]; groups: TimeStepGroup[]; extra: ExtraScenes; result: SelectionState } | null = null;

function withExtraScenes(app: SelectionState, extra: ExtraScenes | null): SelectionState {
  if (!extra) return app;
  if (lastWithScenes && lastWithScenes.items === app.items && lastWithScenes.groups === app.groups && lastWithScenes.extra === extra) {
    return { ...app, items: lastWithScenes.result.items, groups: lastWithScenes.result.groups };
  }
  const keyOf = (group: TimeStepGroup) => group.key.join('\u0000');
  const joined = new Map(extra.groups.map((group) => [keyOf(group), group]));
  const groups = [
    ...app.groups.map((group) => {
      const more = joined.get(keyOf(group));
      return more ? { ...group, items: [...group.items, ...more.items] } : group;
    }),
    ...extra.groups.filter((group) => !app.groups.some((g) => keyOf(g) === keyOf(group))),
  ];
  const result = { ...app, items: [...app.items, ...extra.items], groups };
  lastWithScenes = { items: app.items, groups: app.groups, extra, result };
  return result;
}

// --- requests that a change of the selection drops ----------------------------

let describing: AbortController | null = null;
let estimating: AbortController | null = null;
// The latest start; a start that finds another has taken over leaves the state alone.
let startGeneration = 0;
const trackers = new Map<string, () => void>();
let nextStepKey = 1;
let trackerOptions: TrackerOptions = {};

// Tests hand the tracker their own `EventSource`/`fetchJob`.
export function setTrackerOptions(options: TrackerOptions): void {
  trackerOptions = options;
}

function abortEstimate(): void {
  estimating?.abort();
  estimating = null;
}

// A change of the draft drops the review on its way: the answers would belong to
// another order, and a batch would go on asking the source for them.
function dropReview(): { reviewing: false } | Record<string, never> {
  if (!estimating) return {};
  abortEstimate();
  return { reviewing: false };
}

function refusalOf(error: unknown, key: string, steps: readonly DraftStep[]): Refusal {
  if (error instanceof HttpError) {
    const text = error.detail ?? error.message;
    const hint = error.status === 503 && !/try again/iu.test(text) ? ' Try again in a moment.' : '';
    return { key, message: `${text}${hint}`, step: stepOfRefusal(text, steps), status: error.status };
  }
  return { key, message: error instanceof Error ? error.message : String(error), step: null, status: null };
}

// The text of a refusal outside the panel's draft (the download dialog's jobs).
export function refusalMessage(error: unknown): string {
  return refusalOf(error, '', []).message;
}

const isAbort = (error: unknown) => error instanceof DOMException && error.name === 'AbortError';

// A paragraph for a methods section, written by the backend from the recipe (M4-19a).
export const METHODS_FILE = 'methods.txt';

const FILE_LABELS: Record<string, string> = {
  'result.tif': 'Result (COG)',
  'mask.tif': 'Mask',
  'recipe.json': 'Recipe',
  [METHODS_FILE]: 'Methods',
};

// The one archive of a result (M4-11b-2): an export's `export.zip`, or a raster
// job's `result.zip` (output `bundle`, M4-11b-1).
const ZIP_FILES = ['export.zip', 'result.zip'];
export const ZIP_LABEL = 'Download (ZIP)';

// The files of a results document, by the last segment of each link — only
// the names the job API serves (`/results/{name}`), each once. Where the
// document names an archive, that is the one link (Zusatz §1); a result from
// before archives existed keeps its single links.
export function resultFiles(doc: Record<string, { href?: unknown }>): ResultFile[] {
  const names: string[] = [];
  for (const link of Object.values(doc)) {
    if (!link || typeof link.href !== 'string') continue;
    const file = decodeURIComponent(link.href.split('/').pop() ?? '');
    if (!names.includes(file)) names.push(file);
  }
  const zip = ZIP_FILES.find((file) => names.includes(file));
  if (zip) {
    // The archive holds the text too; it stays a link of its own for the one who wants to paste it.
    return [{ file: zip, label: ZIP_LABEL }, ...(names.includes(METHODS_FILE) ? [{ file: METHODS_FILE, label: 'Methods' }] : [])];
  }
  return names.filter((file) => FILE_LABELS[file]).map((file) => ({ file, label: FILE_LABELS[file] }));
}

// What a failed job's row says (K8): the backend's fixed title, except where a
// shorter hint of what to do helps; the kind is the end of the problem's `type`.
const FAILURE_TEXTS: Record<string, string> = {
  runtime_exceeded: 'The job took longer than allowed. Choose a smaller area or fewer assets.',
};

export function failureText(error: unknown, fallback: string): string {
  if (!(error instanceof HttpError)) return fallback;
  const kind = error.type?.startsWith('urn:earthx:job-failed:') ? error.type.slice('urn:earthx:job-failed:'.length) : '';
  return FAILURE_TEXTS[kind] ?? error.title ?? fallback;
}

const EMPTY_DRAFT = {
  passKey: null,
  // "Whole scene" first (Otto, 12.10.2026).
  area: 'scene' as Area,
  runAs: 'one' as RunAs,
  extraScenes: null as ExtraScenes | null,
  steps: [] as DraftStep[],
  picked: [] as string[],
  dtype: null,
  range: DEFAULT_RANGE,
  rangeDraft: DEFAULT_RANGE,
  preview: null as PreviewSpec | null,
  previewNote: null as string | null,
  reviewAsked: false,
  estimate: null,
  batch: null as { key: string; parts: PartOutcome[] } | null,
  reviewing: false,
  reviewError: null,
  starting: false,
  startError: null,
  batchStartRefusals: null as ProcessingState['batchStartRefusals'],
};

export const useProcessingStore = create<ProcessingState>((set, get) => {
  const updateJob = (jobID: string, patch: Partial<JobEntry>) => {
    set((s) => ({ jobs: s.jobs.map((j) => (j.jobID === jobID ? { ...j, ...patch } : j)) }));
  };

  const persist = () => {
    saveStoredJobs(
      get()
        .jobs.filter((j) => j.phase !== 'gone' && j.phase !== 'dismissed')
        .map(({ jobID, expires, title }) => ({ jobID, expires, title: title ?? undefined })),
    );
  };

  const readResults = async (jobID: string, status: StatusInfo) => {
    try {
      const doc = await fetchResults(jobID);
      const properties = doc.result?.properties;
      const href = tilesHref(doc);
      updateJob(jobID, {
        files: resultFiles(doc),
        resampled: properties ? properties['earthx:resampled'] === true : null,
        tiles: href
          ? { href, width: typeof doc.result?.width === 'number' ? doc.result.width : null, gsd: positive(properties?.gsd) }
          : null,
        statistics: resultStats(properties),
      });
    } catch (error) {
      if (error instanceof HttpError && error.status === 410) {
        updateJob(jobID, { expired: true });
      } else if (status.status === 'failed') {
        updateJob(jobID, { failure: failureText(error, status.message || 'The job failed') });
      } else {
        updateJob(jobID, { error: error instanceof Error ? error.message : String(error) });
      }
    }
  };

  const follow = (jobID: string) => {
    trackers.get(jobID)?.();
    const stop = trackJob(
      jobID,
      {
        onStatus: (status) => {
          const before = get().jobs.find((j) => j.jobID === jobID);
          if (!before) return;
          const phase = status.status === 'accepted' || status.status === 'running' ? 'active' : status.status;
          updateJob(jobID, { status, phase, expires: status.expires });
          if (before.expires !== status.expires) persist();
          if (phase === 'successful' || phase === 'failed') {
            trackers.delete(jobID);
            if (phase === 'failed') updateJob(jobID, { failure: status.message || null });
            void readResults(jobID, status);
          }
          if (phase === 'dismissed') {
            trackers.delete(jobID);
            persist();
          }
        },
        onGone: () => {
          trackers.delete(jobID);
          updateJob(jobID, { phase: 'gone' });
          persist();
        },
      },
      trackerOptions,
    );
    trackers.set(jobID, stop);
  };

  const addJob = (
    jobID: string,
    expires: string,
    status: StatusInfo | null,
    title: string | null = null,
    range: PreviewRange | null = null,
  ) => {
    if (get().jobs.some((j) => j.jobID === jobID)) return;
    const entry: JobEntry = {
      jobID,
      expires,
      status,
      phase: 'active',
      files: null,
      resampled: null,
      failure: null,
      error: null,
      cancelling: false,
      expired: false,
      title,
      tiles: null,
      statistics: null,
      range,
    };
    set((s) => ({ jobs: [entry, ...s.jobs] }));
    persist();
    follow(jobID);
  };

  // "<operators> · <dataset>", with the place in the batch for one of many.
  // Made before the first job is placed: the draft may change while they are.
  const titler = (view: OrderView) => {
    const operators = get().steps.map(
      (step) => view.info?.operators.find((o) => o.op === step.op && o.opVersion === step.opVersion)?.title ?? step.op,
    );
    const dataset = view.dataset?.title ?? view.dataset?.id ?? '';
    return (position?: { index: number; total: number }) => jobTitle({ operators, dataset, position });
  };

  // The jobs of the reviewed batch the server took in; one after the other, and a
  // refused start does not hold back the rest (§3.6). A job whose review the
  // server refused is not started.
  const startBatch = async (view: OrderView) => {
    const batch = get().batch;
    if (!view.key || batch?.key !== view.key) return;
    const total = view.parts.length;
    const titleOf = titler(view);
    const own = handRange(get().range);
    const mine = ++startGeneration;
    set({ starting: true, startError: null, batchStartRefusals: null });
    let opened = false;
    const refusals: { label: string; message: string }[] = [];
    for (const [index, outcome] of batch.parts.entries()) {
      const part = view.parts[index];
      if (!outcome.doc || !part?.order) continue;
      try {
        const status = await placeJob(part.order);
        if (!opened) set({ jobsOpen: true });
        opened = true;
        addJob(status.jobID, status.expires, status, titleOf({ index, total }), own);
      } catch (error) {
        refusals.push({ label: part.unit.label, message: refusalMessage(error) });
      }
    }
    // A draft dropped meanwhile (`resetDraft`) has its own state by now.
    if (mine !== startGeneration) return;
    // One review, these jobs: starting again needs a new review.
    set({ starting: false, batch: null, batchStartRefusals: refusals.length > 0 ? { key: view.key, refusals } : null });
  };

  return {
    open: false,
    jobsOpen: false,
    descriptions: {},
    crs: {},
    ...EMPTY_DRAFT,
    jobs: [],

    // Opened from the selection (`ViewBar`), a layer or the full-resolution view.
    // Every entry sets the area: "Whole scene" unless the entry says otherwise
    // (Otto 19.10.2026).
    openProcessing: (entry = {}) => {
      set({
        open: true,
        area: entry.area ?? 'scene',
        ...(entry.extraScenes !== undefined ? { extraScenes: entry.extraScenes } : {}),
      });
      const datasetId = useAppStore.getState().datasetId;
      if (datasetId) get().ensureDescription(datasetId);
    },
    // F3 (1): the selection is made again from the layer, then the panel opens and
    // reads the selection as ever. "AOI only" if the layer was cut to its AOI.
    // The view stays as it is (Otto 19.10.2026): no full-resolution view of the
    // layer, the results list stays. Scenes the results on screen lack are fetched
    // first, one by one.
    processLayer: async (layerId) => {
      const layer = useAppStore.getState().layers.find((l) => l.id === layerId);
      if (!layer || layerProcessBlock(layer, useAppStore.getState().datasets) !== null) return;
      useAppStore.getState().activateLayerContext(layerId);
      const extraScenes = await selectScenes(layer.restore.itemIds, 'this layer');
      if (!extraScenes) return;
      get().openProcessing({
        area: layer.restore.cropToAoi && isArea(layer.restore.aoi) ? 'aoi' : 'scene',
        extraScenes: extraScenes.items.length > 0 ? extraScenes : null,
      });
    },
    processFocusView: async () => {
      const app = useAppStore.getState();
      const extraScenes = await selectScenes(Object.keys(app.downloaded), 'this view');
      if (!extraScenes) return;
      get().openProcessing({
        area: app.cropToAoi && isArea(app.aoi) ? 'aoi' : 'scene',
        extraScenes: extraScenes.items.length > 0 ? extraScenes : null,
      });
    },
    setRangeDraft: (patch) => set((s) => ({ rangeDraft: { ...s.rangeDraft, ...patch } })),
    applyRange: () => {
      if ('rescale' in rescaleOf(get().rangeDraft)) set((s) => ({ range: s.rangeDraft }));
    },
    // The preview on screen becomes a layer of its own.
    pinPreview: () => {
      const { preview } = get();
      const app = useAppStore.getState();
      if (!preview) return;
      app.pinDerivedLayer({
        name: `Preview · ${preview.title}`,
        derived: 'preview',
        overlays: previewOverlays(preview, app.aoi),
        itemIds: preview.scenes.map((scene) => scene.id),
        cropToAoi: preview.clipToAoi,
      });
    },
    closeProcessing: () => {
      abortEstimate();
      set({ open: false, reviewing: false });
    },
    // The layer reads the tiles from the tiler, which knows nothing of the job: the link
    // of the results document is all there is (plan §3.4). Once the job's results are
    // about to go there are no tiles any more, and no layer is made of them.
    showResultOnMap: async (jobID) => {
      const job = get().jobs.find((j) => j.jobID === jobID);
      const app = useAppStore.getState();
      if (!job?.tiles || job.phase !== 'successful' || job.expired) return;
      if (isResultExpired(job.expires, Date.now())) {
        updateJob(jobID, { expired: true });
        return;
      }
      const shown = (layers: MapLayer[]) => layers.find((l) => l.result?.jobID === jobID);
      const already = shown(app.layers);
      if (already) {
        if (!already.visible) app.toggleLayerVisible(already.id);
        return;
      }
      const { href, width, gsd } = job.tiles;
      let tileJson: ResultTileJson;
      try {
        updateJob(jobID, { error: null });
        tileJson = await fetchResultTileJson(href);
      } catch (error) {
        if (error instanceof HttpError && error.status === 410) {
          updateJob(jobID, { expired: true });
        } else {
          const reason = error instanceof Error ? error.message : String(error);
          updateJob(jobID, { error: `The result could not be shown on the map. ${reason}` });
        }
        return;
      }
      // A second click while the TileJSON was coming: one layer.
      if (shown(useAppStore.getState().layers)) return;
      useAppStore.getState().pinDerivedLayer({
        name: resultLayerName(job.title),
        derived: 'result',
        result: {
          jobID,
          expires: job.expires,
          gsd: resultGsd(gsd, width, tileJson.bounds),
          resampled: job.resampled,
          expired: false,
        },
        overlays: [
          {
            kind: 'raster',
            tileUrl: buildTileUrl(resultTileTemplate(href), resultRender(tileJson.dataType, get().range, job.statistics, job.range)),
            bounds: tileJson.bounds,
            minZoom: tileJson.minZoom,
            // rio-tiler's `maxzoom` is the level nearest the data's pixel size, and often the coarser
            // one (10 m at 48° N: level 13, 12.8 m). One level more lets the map ask for the data
            // itself; the tiler reads the file at any level.
            maxZoom: tileJson.maxZoom + 1,
          },
        ],
        itemIds: [],
        cropToAoi: false,
      });
    },
    openJobs: () => set({ jobsOpen: true }),
    closeJobs: () => set({ jobsOpen: false }),
    // The unit of a target CRS (M4-13c-3). A refusal and an answer stay; an answer that
    // could not be fetched is asked again. A lookup the caller abandons leaves nothing.
    lookupCrs: async (code, signal) => {
      const known = get().crs[code];
      if (known && known.state !== 'error') return;
      const entryOf = async (): Promise<CrsEntry | null> => {
        try {
          return { state: 'ready', info: await fetchCrs(code, signal) };
        } catch (error) {
          if (signal.aborted || isAbort(error)) return null;
          if (error instanceof HttpError && error.status === 422) {
            return { state: 'refused', message: error.detail ?? error.message };
          }
          return { state: 'error', message: error instanceof Error ? error.message : String(error) };
        }
      };
      const entry = await entryOf();
      if (entry) set((s) => ({ crs: { ...s.crs, [code]: entry } }));
    },
    ensureDescription: (datasetId) => {
      const known = get().descriptions[datasetId];
      if (known && known.state !== 'error') return;
      describing?.abort();
      const controller = new AbortController();
      describing = controller;
      set((s) => ({ descriptions: { ...s.descriptions, [datasetId]: { state: 'loading' } } }));
      fetchProcess(datasetId, controller.signal)
        .then((description) => {
          const info = processInfo(description);
          set((s) => ({ descriptions: { ...s.descriptions, [datasetId]: { state: 'ready', info } } }));
        })
        .catch((error: unknown) => {
          const rest = { ...get().descriptions };
          delete rest[datasetId];
          if (controller.signal.aborted || isAbort(error)) {
            set({ descriptions: rest });
            return;
          }
          const message = error instanceof Error ? error.message : String(error);
          set({ descriptions: { ...rest, [datasetId]: { state: 'error', message } } });
        });
    },
    resetDraft: () => {
      abortEstimate();
      startGeneration += 1;
      set({ ...EMPTY_DRAFT });
    },
    choosePass: (passKey) => set({ passKey, picked: [], reviewError: null, startError: null, ...dropReview() }),
    setArea: (area) => set({ area, reviewError: null, startError: null, ...dropReview() }),
    setRunAs: (runAs) => set({ runAs, reviewError: null, startError: null, ...dropReview() }),
    addStep: (op, opVersion) => {
      const datasetId = useAppStore.getState().datasetId;
      const description = datasetId ? get().descriptions[datasetId] : undefined;
      if (description?.state !== 'ready') return;
      const operator = description.info.operators.find((o) => o.op === op && o.opVersion === opVersion);
      if (!operator?.form.supported || get().steps.length >= description.info.maxSteps) return;
      const key = nextStepKey++;
      set((s) => ({
        steps: [...s.steps, { key, op, opVersion, values: initialValues(operator.form.supported ? operator.form.fields : []) }],
        reviewError: null,
        startError: null,
        ...dropReview(),
      }));
    },
    updateStep: (key, name, value) =>
      set((s) => ({
        steps: s.steps.map((step) => (step.key === key ? { ...step, values: { ...step.values, [name]: value } } : step)),
        reviewError: null,
        startError: null,
        ...dropReview(),
      })),
    moveStep: (key, direction) =>
      set((s) => {
        const index = s.steps.findIndex((step) => step.key === key);
        const target = index + direction;
        if (index < 0 || target < 0 || target >= s.steps.length) return {};
        const steps = [...s.steps];
        [steps[index], steps[target]] = [steps[target], steps[index]];
        return { steps, reviewError: null, startError: null, ...dropReview() };
      }),
    removeStep: (key) =>
      set((s) => ({
        steps: s.steps.filter((step) => step.key !== key),
        reviewError: null,
        startError: null,
        ...dropReview(),
      })),
    togglePick: (asset) =>
      set((s) => ({
        picked: s.picked.includes(asset) ? s.picked.filter((a) => a !== asset) : [...s.picked, asset],
        reviewError: null,
        startError: null,
        ...dropReview(),
      })),
    setDtype: (dtype) => set({ dtype: dtype || null, reviewError: null, startError: null, ...dropReview() }),

    // "Load recipe…": a `recipe.json` becomes the draft. "Steps only" keeps the selection
    // and takes the steps and the data type; "Everything" makes the recipe's dataset,
    // scenes and area the selection first. Nothing is changed unless the recipe is taken
    // up as a whole; what cannot be checked here (band names of another dataset) comes
    // back as notes, the server decides on the order.
    loadRecipe: async (text, mode) => {
      const read = readRecipe(text);
      if (!read.ok) return { ok: false, reason: read.reason };
      const { order } = read;
      const app = useAppStore.getState();
      const datasetId = mode === 'steps' ? app.datasetId : order.inputs[0].dataset;
      if (!datasetId) return { ok: false, reason: 'Pick a dataset first.' };
      if (mode === 'steps' && order.steps.length === 0) return { ok: false, reason: 'This recipe has no steps.' };
      const dataset = app.datasets.find((d) => d.id === datasetId);
      if (mode === 'everything') {
        const block = processBlockReason(dataset, order.inputs[0].groups.flat().length);
        if (block) return { ok: false, reason: block };
      }
      get().ensureDescription(datasetId);
      const description = await new Promise<Description | undefined>((resolve) => {
        const settled = (s: ProcessingState) => (s.descriptions[datasetId]?.state === 'loading' ? undefined : s.descriptions[datasetId]);
        const now = settled(get());
        if (now) return resolve(now);
        const stop = useProcessingStore.subscribe((s) => {
          const done = settled(s);
          if (done) {
            stop();
            resolve(done);
          }
        });
      });
      if (description?.state !== 'ready') return { ok: false, reason: 'The process description of the dataset could not be loaded.' };
      const { info } = description;
      const { draft, problems } = draftFromOrder(order, info, () => nextStepKey++);
      if (problems.length > 0) return { ok: false, reason: problems.slice(0, 3).join(' ') };
      const notes: string[] = [];
      if (draft.dtype !== null && !info.dtypes.includes(draft.dtype)) notes.push(`Data type ${draft.dtype} is not offered for this dataset.`);
      const dtype = draft.dtype !== null && info.dtypes.includes(draft.dtype) ? draft.dtype : null;
      abortEstimate();
      startGeneration += 1;
      if (mode === 'steps') {
        set({ steps: draft.steps, dtype, reviewAsked: false, estimate: null, batch: null, reviewing: false, reviewError: null, startError: null, batchStartRefusals: null });
        const known = new Set(orderView(selectionState(useAppStore.getState()), get()).sources.flatMap((source) => source.names));
        const missing = new Set(
          bandMathExpressions(draft.steps).flatMap((expression) => [...namesInExpression(expression)].filter((name) => known.size > 0 && !known.has(name))),
        );
        for (const name of missing) notes.push(`Band ${name} is not in this selection.`);
        return { ok: true, notes };
      }
      useAppStore.setState({ datasetId, selectedDatasetIds: [datasetId] });
      const extraScenes = await selectScenes(draft.groups.flat(), 'this recipe');
      if (!extraScenes) return { ok: false, reason: useAppStore.getState().error ?? 'The scenes could not be loaded.' };
      if (draft.aoi) useAppStore.getState().setAoi(draft.aoi);
      set({
        ...EMPTY_DRAFT,
        open: true,
        area: draft.aoi ? 'aoi' : 'scene',
        extraScenes: extraScenes.items.length > 0 ? extraScenes : null,
        steps: draft.steps,
        picked: draft.assets,
        dtype,
      });
      return { ok: true, notes };
    },

    reviewOrder: async () => {
      const view = orderView(useAppStore.getState(), get());
      const order = view.built?.order;
      set({ reviewAsked: true });
      if (!order || !view.key || get().starting || crsBlockReason(get().steps, get().crs)) return;
      abortEstimate();
      const controller = new AbortController();
      estimating = controller;
      const key = view.key;
      set({ reviewing: true, reviewError: null, startError: null, batchStartRefusals: null, estimate: null, batch: null });
      try {
        if (view.runAs === 'one') {
          const doc = await estimateOrder(order, controller.signal);
          set({ estimate: { key, doc }, reviewing: false });
          return;
        }
        // A batch: every job asks for its own estimate, a few at a time; one the
        // server refuses stays a line of its own and does not hold the others back.
        const asked = view.parts.filter((part): part is OrderPart & { order: Order } => part.order !== null);
        const steps = get().steps;
        const outcomes = await runPool(asked, ESTIMATE_PARALLEL, controller.signal, async (part): Promise<PartOutcome> => {
          try {
            return { unit: part.unit, doc: await estimateOrder(part.order, controller.signal), refusal: null };
          } catch (error) {
            if (controller.signal.aborted || isAbort(error)) throw error;
            return { unit: part.unit, doc: null, refusal: refusalOf(error, key, steps) };
          }
        });
        if (controller.signal.aborted) return;
        set({ batch: { key, parts: outcomes.filter((o): o is PartOutcome => o !== undefined) }, reviewing: false });
      } catch (error) {
        if (controller.signal.aborted || isAbort(error)) return;
        set({ reviewing: false, reviewError: refusalOf(error, key, get().steps) });
      } finally {
        if (estimating === controller) estimating = null;
      }
    },

    startJob: async () => {
      const s = get();
      const view = orderView(useAppStore.getState(), s);
      const order = view.built?.order;
      if (!order || !view.key || s.starting || crsBlockReason(s.steps, s.crs)) return;
      if (view.runAs !== 'one') {
        await startBatch(view);
        return;
      }
      if (s.estimate?.key !== view.key) return;
      const title = titler(view)();
      const own = handRange(s.range);
      const mine = ++startGeneration;
      set({ starting: true, startError: null });
      try {
        const status = await placeJob(order, {
          aoiProvenance: aoiProvenanceFor(order, useAppStore.getState().aoi),
        });
        // One estimate, one job: a second identical job needs its own review.
        if (mine === startGeneration) set({ starting: false, estimate: null });
        set({ jobsOpen: true });
        addJob(status.jobID, status.expires, status, title, own);
      } catch (error) {
        if (mine === startGeneration) set({ starting: false, startError: refusalOf(error, view.key, s.steps) });
      }
    },

    // A job the download dialog starts (a mosaic, M4-12b; an export, M4-11b-2):
    // the order is built there, with no draft and no review; a refusal comes back
    // as text, the job as a row in the list.
    placeOrder: async (order, options) => {
      try {
        const status = await placeJob(order, options);
        addJob(status.jobID, status.expires, status);
        return { jobID: status.jobID };
      } catch (error) {
        return { message: refusalMessage(error) };
      }
    },

    cancelJob: async (jobID) => {
      updateJob(jobID, { cancelling: true, error: null });
      try {
        await dismissJob(jobID);
        trackers.get(jobID)?.();
        trackers.delete(jobID);
        updateJob(jobID, { cancelling: false, phase: 'dismissed' });
      } catch (error) {
        if (error instanceof HttpError && error.status === 404) {
          trackers.get(jobID)?.();
          trackers.delete(jobID);
          updateJob(jobID, { cancelling: false, phase: 'gone' });
        } else {
          updateJob(jobID, { cancelling: false, error: error instanceof Error ? error.message : String(error) });
        }
      }
      persist();
    },
    removeJob: (jobID) => {
      trackers.get(jobID)?.();
      trackers.delete(jobID);
      set((s) => ({ jobs: s.jobs.filter((j) => j.jobID !== jobID) }));
      persist();
    },
    resumeJobs: () => {
      for (const { jobID, expires, title } of loadStoredJobs().reverse()) addJob(jobID, expires, null, title ?? null);
    },
  };
});

// A new dataset drops the draft; any other change of the selection drops only
// an estimate still on its way (its answer would belong to another order) and
// sends "Run as" back to one job. A new AOI does so only for "AOI only" (K3):
// "Whole scene" does not send it, the order stays the same text, and so does an
// estimate already shown.
useAppStore.subscribe((s, prev) => {
  const processing = useProcessingStore.getState();
  if (s.datasetId !== prev.datasetId) {
    processing.resetDraft();
    if (s.datasetId && processing.open) processing.ensureDescription(s.datasetId);
  } else if (
    (s.aoi !== prev.aoi && processing.area === 'aoi') ||
    s.selectedIds !== prev.selectedIds ||
    s.items !== prev.items ||
    s.groups !== prev.groups ||
    s.activeGroupIndex !== prev.activeGroupIndex
  ) {
    if (estimating) {
      abortEstimate();
      useProcessingStore.setState({ reviewing: false });
    }
    // Another selection, another set of jobs: "Run as" starts from one job again (Otto, 20.10.2026).
    if (processing.runAs !== 'one') useProcessingStore.setState({ runAs: 'one' });
  }
});

// --- the map preview (K7) ----------------------------------------------------

const PREVIEW_DELAY_MS = 400;
let previewTimer: ReturnType<typeof setTimeout> | undefined;

// What the map should show now: the longest start of the draft's steps that runs as
// tiles, on the scenes of the order, while the panel is open and its steps are complete.
// `limit` cuts it to the first steps (what the tiler accepted of a chain).
function wantedPreview(limit?: number): PreviewSpec | null {
  const p = useProcessingStore.getState();
  if (!p.open) return null;
  const app = useAppStore.getState();
  const view = orderView(app, p);
  if (!view.info || !view.pass || processBlockReason(view.dataset, app.selectedIds.length) !== null) return null;
  const full = planPreview(p.steps, view.info);
  if (full.state !== 'ready') return null;
  const plan = limit === undefined ? full : shortenPlan(full, limit);
  if (plan === null) return null;
  return previewSpec({ dataset: view.dataset, items: view.pass.items, assets: view.assets, info: view.info, plan, range: p.range, area: p.area });
}

// The key of the whole chain the shown preview comes from: a preview cut by the tiler
// differs from it, and must not be asked for again on every change that leaves it alone.
let settledKey: string | null = null;
let settleRun = 0;
// What the tiler said of a chain, until there is nothing to show: asking again for a new range would give the same answer.
const probed = new Map<string, RefusedStep>();

// Shows `wanted`, or — for a chain of several steps the tiler refuses at step k — its first
// k − 1 steps and the reason. One step needs no question: its refusal has no step to name.
async function settle(wanted: PreviewSpec): Promise<void> {
  const run = ++settleRun;
  let refused: RefusedStep | null = null;
  if (wanted.stepCount > 1) {
    refused = probed.get(wanted.probe) ?? null;
    if (refused === null) {
      // Only a refusal is remembered: a question that failed on the way is asked again.
      refused = await probeChain(wanted.probe);
      if (run !== settleRun) return;
      if (refused) probed.set(wanted.probe, refused);
    }
  }
  settledKey = wanted.key;
  if (refused === null || refused.step >= wanted.stepCount) {
    useProcessingStore.setState({ preview: wanted, previewNote: null });
    return;
  }
  const shown = refused.step;
  useProcessingStore.setState({ preview: wantedPreview(shown), previewNote: refusedNote(shown, wanted.stepCount, refused) });
}

// A preview that goes away goes at once; a new or changed one 400 ms after the
// last change, so typing an expression asks for no tile per key.
function refreshPreview(): void {
  clearTimeout(previewTimer);
  const wanted = wantedPreview();
  const state = useProcessingStore.getState();
  if (wanted !== null && wanted.key === settledKey && (state.preview !== null || state.previewNote !== null)) return;
  if (wanted === null) {
    settleRun++;
    settledKey = null;
    probed.clear();
    if (state.preview !== null || state.previewNote !== null) useProcessingStore.setState({ preview: null, previewNote: null });
    return;
  }
  previewTimer = setTimeout(() => {
    const again = wantedPreview();
    if (again) void settle(again);
  }, PREVIEW_DELAY_MS);
}

useProcessingStore.subscribe((s, prev) => {
  if (
    s.open !== prev.open ||
    s.descriptions !== prev.descriptions ||
    s.passKey !== prev.passKey ||
    s.area !== prev.area ||
    s.runAs !== prev.runAs ||
    s.steps !== prev.steps ||
    s.picked !== prev.picked ||
    s.range !== prev.range
  ) {
    refreshPreview();
  }
});

useAppStore.subscribe((s, prev) => {
  if (
    s.datasets !== prev.datasets ||
    s.datasetId !== prev.datasetId ||
    s.items !== prev.items ||
    s.groups !== prev.groups ||
    s.activeGroupIndex !== prev.activeGroupIndex ||
    s.selectedIds !== prev.selectedIds ||
    (s.aoi !== prev.aoi && useProcessingStore.getState().area === 'aoi')
  ) {
    refreshPreview();
  }
});
