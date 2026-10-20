// The processing panel's state (M4-13 §3.5): the process description per
// dataset, the draft of an order, its estimate, and the jobs of this tab. A
// store of its own next to `store.ts`; it reads the selection (dataset,
// scenes, AOI) from there and never writes to it.
//
// An order names the scenes of one pass (M4-12b); the pass is the one the
// selection has (in the AOI, for "AOI only"), or the one the user picks. It
// covers the whole scenes by default, or only the AOI (M4-13c §3.2).
//
// The map preview of the first step (M4-13c-2) is computed from the draft and
// the selection; it follows 400 ms after the last change (K7).
//
// The draft belongs to one dataset: a new dataset drops it. A new AOI drops
// nothing but the estimate (M4-13c K3). An estimate belongs to exactly one
// order (K4): any change to the order makes it disappear, and "Start job"
// waits for a new one.

import { create } from 'zustand';

import { fetchItem, HttpError } from './api';
import type { DatasetOption } from './datasets';
import { loadStoredJobs, saveStoredJobs, trackJob, type TrackerOptions } from './jobTracker';
import {
  canonicalJson,
  dismissJob,
  estimateOrder,
  fetchProcess,
  fetchResults,
  placeJob,
  type AoiProvenance,
  type EstimateDocument,
  type Order,
  type StatusInfo,
} from './processing';
import {
  aoiProvenanceFor,
  bandSources,
  buildOrder,
  candidateItems,
  isArea,
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
  previewOverlays,
  previewSpec,
  rescaleOf,
  type PreviewRange,
  type PreviewSpec,
} from './processingPreview';
import { chooseDtype, dtypeOptions, effectiveDtype, integerNote, type Choice, type DtypeOption } from './processingDefaults';
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
}

interface ProcessingState {
  open: boolean;
  // The window of the jobs of this tab (M4-13c §3.1), apart from the panel.
  jobsOpen: boolean;
  descriptions: Record<string, Description>;
  // `Pass.key` of the pass the user picked; `null` until then (a lone pass needs no pick).
  passKey: string | null;
  area: Area;
  extraScenes: ExtraScenes | null;
  steps: DraftStep[];
  picked: string[];
  dtype: string | null;
  // The range and colormap of the map preview: applied, and as edited (F3 (1)).
  range: PreviewRange;
  rangeDraft: PreviewRange;
  // What the map shows of the first step; `null` for none.
  preview: PreviewSpec | null;
  // "Review" was asked for this draft: empty required fields show their hint.
  reviewAsked: boolean;
  estimate: { key: string; doc: EstimateDocument } | null;
  reviewing: boolean;
  reviewError: Refusal | null;
  starting: boolean;
  startError: Refusal | null;
  jobs: JobEntry[];

  openProcessing: (entry?: ProcessingEntry) => void;
  processLayer: (layerId: string) => Promise<void>;
  processFocusView: () => Promise<void>;
  setRangeDraft: (patch: Partial<PreviewRange>) => void;
  applyRange: () => void;
  pinPreview: () => void;
  closeProcessing: () => void;
  openJobs: () => void;
  closeJobs: () => void;
  ensureDescription: (datasetId: string) => void;
  resetDraft: () => void;
  choosePass: (passKey: string) => void;
  setArea: (area: Area) => void;
  addStep: (op: string, opVersion: number) => void;
  updateStep: (key: number, name: string, value: FieldValue) => void;
  moveStep: (key: number, direction: -1 | 1) => void;
  removeStep: (key: number) => void;
  togglePick: (asset: string) => void;
  setDtype: (dtype: string) => void;
  reviewOrder: () => Promise<void>;
  startJob: () => Promise<void>;
  placeOrder: (order: Order, options?: { aoiProvenance?: AoiProvenance }) => Promise<{ jobID: string } | { message: string }>;
  cancelJob: (jobID: string) => Promise<void>;
  removeJob: (jobID: string) => void;
  resumeJobs: () => void;
}

// --- the order as the panel sees it --------------------------------------------

export interface OrderView {
  dataset: DatasetOption | undefined;
  info: ProcessInfo | null;
  // The scenes the order can be for — all selected ones, or those the AOI meets
  // for "AOI only" — split into passes, and the pass the order is for.
  candidates: StacItem[];
  passes: Pass[];
  pass: Pass | null;
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
  key: string | null;
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
  'datasets' | 'datasetId' | 'items' | 'selectedIds' | 'groups' | 'activeGroupIndex' | 'aoi'
>;

export function selectionState(s: AppState): SelectionState {
  const { datasets, datasetId, items, selectedIds, groups, activeGroupIndex, aoi } = s;
  return { datasets, datasetId, items, selectedIds, groups, activeGroupIndex, aoi };
}

export function orderView(selection: SelectionState, p: ProcessingState): OrderView {
  const app = withExtraScenes(selection, p.extraScenes);
  const dataset = app.datasets.find((d) => d.id === app.datasetId);
  const description = app.datasetId ? p.descriptions[app.datasetId] : undefined;
  const info = description?.state === 'ready' ? description.info : null;
  const { items: candidates, passes } = candidatesOf(app, p.area);
  const pass = passes.find((c) => c.key === p.passKey) ?? (passes.length === 1 ? passes[0] : null);
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
  const built =
    info && dataset
      ? buildOrder({
          datasetId: dataset.id,
          itemIds: pass?.items.map((i) => i.id) ?? [],
          area: p.area,
          aoi: app.aoi,
          steps: p.steps,
          assets,
          dtype,
          info,
        })
      : null;
  return {
    dataset,
    info,
    candidates,
    passes,
    pass,
    sources,
    assets,
    dtype,
    dtypeOptions: options,
    dtypeAutomatic: automatic,
    dtypeChosen: p.dtype !== null && p.dtype === dtype,
    dtypeNote: integerNote(dtype, choices, inOrder),
    built,
    key: built?.order ? canonicalJson(built.order) : null,
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
  let extra: ExtraScenes = { items: [], groups: [] };
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
      extra = { items, groups: buildGroups(items, dataset.resultsGroupBy) };
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

const FILE_LABELS: Record<string, string> = {
  'result.tif': 'Result (COG)',
  'mask.tif': 'Mask',
  'recipe.json': 'Recipe',
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
  if (zip) return [{ file: zip, label: ZIP_LABEL }];
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
  extraScenes: null as ExtraScenes | null,
  steps: [] as DraftStep[],
  picked: [] as string[],
  dtype: null,
  range: DEFAULT_RANGE,
  rangeDraft: DEFAULT_RANGE,
  preview: null as PreviewSpec | null,
  reviewAsked: false,
  estimate: null,
  reviewing: false,
  reviewError: null,
  starting: false,
  startError: null,
};

export const useProcessingStore = create<ProcessingState>((set, get) => {
  const updateJob = (jobID: string, patch: Partial<JobEntry>) => {
    set((s) => ({ jobs: s.jobs.map((j) => (j.jobID === jobID ? { ...j, ...patch } : j)) }));
  };

  const persist = () => {
    saveStoredJobs(
      get()
        .jobs.filter((j) => j.phase !== 'gone' && j.phase !== 'dismissed')
        .map(({ jobID, expires }) => ({ jobID, expires })),
    );
  };

  const readResults = async (jobID: string, status: StatusInfo) => {
    try {
      const doc = await fetchResults(jobID);
      const properties = doc.result?.properties;
      updateJob(jobID, {
        files: resultFiles(doc),
        resampled: properties ? properties['earthx:resampled'] === true : null,
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

  const addJob = (jobID: string, expires: string, status: StatusInfo | null) => {
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
    };
    set((s) => ({ jobs: [entry, ...s.jobs] }));
    persist();
    follow(jobID);
  };

  return {
    open: false,
    jobsOpen: false,
    descriptions: {},
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
    openJobs: () => set({ jobsOpen: true }),
    closeJobs: () => set({ jobsOpen: false }),
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
      set({ ...EMPTY_DRAFT });
    },
    choosePass: (passKey) => set({ passKey, picked: [], reviewError: null, startError: null }),
    setArea: (area) => set({ area, reviewError: null, startError: null }),
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
      }));
    },
    updateStep: (key, name, value) =>
      set((s) => ({
        steps: s.steps.map((step) => (step.key === key ? { ...step, values: { ...step.values, [name]: value } } : step)),
        reviewError: null,
        startError: null,
      })),
    moveStep: (key, direction) =>
      set((s) => {
        const index = s.steps.findIndex((step) => step.key === key);
        const target = index + direction;
        if (index < 0 || target < 0 || target >= s.steps.length) return {};
        const steps = [...s.steps];
        [steps[index], steps[target]] = [steps[target], steps[index]];
        return { steps, reviewError: null, startError: null };
      }),
    removeStep: (key) =>
      set((s) => ({
        steps: s.steps.filter((step) => step.key !== key),
        reviewError: null,
        startError: null,
      })),
    togglePick: (asset) =>
      set((s) => ({
        picked: s.picked.includes(asset) ? s.picked.filter((a) => a !== asset) : [...s.picked, asset],
        reviewError: null,
        startError: null,
      })),
    setDtype: (dtype) => set({ dtype: dtype || null, reviewError: null, startError: null }),

    reviewOrder: async () => {
      const view = orderView(useAppStore.getState(), get());
      const order = view.built?.order;
      set({ reviewAsked: true });
      if (!order || !view.key) return;
      abortEstimate();
      const controller = new AbortController();
      estimating = controller;
      const key = view.key;
      set({ reviewing: true, reviewError: null, startError: null, estimate: null });
      try {
        const doc = await estimateOrder(order, controller.signal);
        set({ estimate: { key, doc }, reviewing: false });
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
      if (!order || !view.key || s.estimate?.key !== view.key || s.starting) return;
      set({ starting: true, startError: null });
      try {
        const status = await placeJob(order, {
          aoiProvenance: aoiProvenanceFor(order, useAppStore.getState().aoi),
        });
        // One estimate, one job: a second identical job needs its own review.
        set({ starting: false, estimate: null, jobsOpen: true });
        addJob(status.jobID, status.expires, status);
      } catch (error) {
        set({ starting: false, startError: refusalOf(error, view.key, s.steps) });
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
      for (const { jobID, expires } of loadStoredJobs().reverse()) addJob(jobID, expires, null);
    },
  };
});

// A new dataset drops the draft; any other change of the selection drops only
// an estimate still on its way (its answer would belong to another order). A
// new AOI does so only for "AOI only" (K3): "Whole scene" does not send it, the
// order stays the same text, and so does an estimate already shown.
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
  }
});

// --- the map preview (K7) ----------------------------------------------------

const PREVIEW_DELAY_MS = 400;
let previewTimer: ReturnType<typeof setTimeout> | undefined;

// What the map should show now: the first step of the draft on the scenes of the
// order, while the panel is open and the step is complete.
function wantedPreview(): PreviewSpec | null {
  const p = useProcessingStore.getState();
  if (!p.open) return null;
  const app = useAppStore.getState();
  const view = orderView(app, p);
  if (!view.info || !view.pass || processBlockReason(view.dataset, app.selectedIds.length) !== null) return null;
  const plan = planPreview(p.steps, view.info);
  if (plan.state !== 'ready') return null;
  return previewSpec({ dataset: view.dataset, items: view.pass.items, assets: view.assets, info: view.info, plan, range: p.range, area: p.area });
}

// A preview that goes away goes at once; a new or changed one 400 ms after the
// last change, so typing an expression asks for no tile per key.
function refreshPreview(): void {
  clearTimeout(previewTimer);
  const wanted = wantedPreview();
  if (wanted?.key === useProcessingStore.getState().preview?.key) return;
  if (wanted === null) {
    useProcessingStore.setState({ preview: null });
    return;
  }
  previewTimer = setTimeout(() => useProcessingStore.setState({ preview: wantedPreview() }), PREVIEW_DELAY_MS);
}

useProcessingStore.subscribe((s, prev) => {
  if (
    s.open !== prev.open ||
    s.descriptions !== prev.descriptions ||
    s.passKey !== prev.passKey ||
    s.area !== prev.area ||
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
