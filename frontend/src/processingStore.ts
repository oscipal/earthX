// The processing panel's state (M4-13 §3.5): the process description per
// dataset, the draft of an order, its estimate, and the jobs of this tab. A
// store of its own next to `store.ts`; it reads the selection (dataset,
// scenes, AOI) from there and never writes to it.
//
// The draft belongs to one dataset and one AOI: a change of either drops it.
// An estimate belongs to exactly one order (K4): any change to the order makes
// it disappear, and "Start job" waits for a new one.

import { create } from 'zustand';

import { HttpError } from './api';
import type { DatasetOption } from './datasets';
import { loadStoredJobs, saveStoredJobs, trackJob, type TrackerOptions } from './jobTracker';
import {
  canonicalJson,
  dismissJob,
  estimateOrder,
  fetchProcess,
  fetchResults,
  placeJob,
  type EstimateDocument,
  type StatusInfo,
} from './processing';
import {
  bandSources,
  buildOrder,
  candidateItems,
  defaultDtype,
  orderAssets,
  processInfo,
  stepOfRefusal,
  type BandSource,
  type BuiltOrder,
  type DraftStep,
  type ProcessInfo,
} from './processingOrder';
import { initialValues, type FieldValue } from './schemaForm';
import { selectionItemsFrom, useAppStore, type AppState } from './store';
import type { StacItem } from './types';

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
}

interface ProcessingState {
  open: boolean;
  descriptions: Record<string, Description>;
  itemId: string | null;
  steps: DraftStep[];
  picked: string[];
  dtype: string | null;
  activeStep: number | null;
  // "Review" was asked for this draft: empty required fields show their hint.
  reviewAsked: boolean;
  estimate: { key: string; doc: EstimateDocument } | null;
  reviewing: boolean;
  reviewError: Refusal | null;
  starting: boolean;
  startError: Refusal | null;
  jobs: JobEntry[];

  openProcessing: () => void;
  closeProcessing: () => void;
  ensureDescription: (datasetId: string) => void;
  resetDraft: () => void;
  chooseItem: (itemId: string) => void;
  addStep: (op: string, opVersion: number) => void;
  updateStep: (key: number, name: string, value: FieldValue) => void;
  moveStep: (key: number, direction: -1 | 1) => void;
  removeStep: (key: number) => void;
  setActiveStep: (key: number) => void;
  togglePick: (asset: string) => void;
  insertBand: (name: string) => void;
  setDtype: (dtype: string) => void;
  reviewOrder: () => Promise<void>;
  startJob: () => Promise<void>;
  cancelJob: (jobID: string) => Promise<void>;
  removeJob: (jobID: string) => void;
  resumeJobs: () => void;
}

// --- the order as the panel sees it --------------------------------------------

export interface OrderView {
  dataset: DatasetOption | undefined;
  info: ProcessInfo | null;
  candidates: StacItem[];
  item: StacItem | null;
  sources: BandSource[];
  assets: string[];
  dtype: string;
  built: BuiltOrder | null;
  key: string | null;
}

// The candidates only change with the selection and the AOI; the intersection
// is the one costly part of the view, so the last answer is kept.
let lastCandidates: { inputs: unknown[]; result: StacItem[] } | null = null;

function candidatesOf(app: SelectionState): StacItem[] {
  const inputs = [app.items, app.selectedIds, app.groups, app.activeGroupIndex, app.aoi];
  if (lastCandidates && lastCandidates.inputs.every((value, i) => value === inputs[i])) return lastCandidates.result;
  const result = app.aoi ? candidateItems(selectionItemsFrom(app), app.aoi) : [];
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

export function orderView(app: SelectionState, p: ProcessingState): OrderView {
  const dataset = app.datasets.find((d) => d.id === app.datasetId);
  const description = app.datasetId ? p.descriptions[app.datasetId] : undefined;
  const info = description?.state === 'ready' ? description.info : null;
  const candidates = candidatesOf(app);
  const item = candidates.find((c) => c.id === p.itemId) ?? (candidates.length === 1 ? candidates[0] : null);
  const format = dataset?.collection['earthx:format'] ?? null;
  const sources = item ? bandSources(item, format, info?.variableSeparator ?? null) : [];
  const assets = orderAssets(sources, p.picked, bandMathExpressions(p.steps));
  const dtype = p.dtype ?? (info ? defaultDtype(p.steps, sources, assets, info.dtypes) : '');
  const built =
    info && dataset
      ? buildOrder({ datasetId: dataset.id, itemId: item?.id ?? null, aoi: app.aoi, steps: p.steps, assets, dtype, info })
      : null;
  return { dataset, info, candidates, item, sources, assets, dtype, built, key: built?.order ? canonicalJson(built.order) : null };
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
    return { key, message: `${text}${hint}`, step: stepOfRefusal(text, steps) };
  }
  return { key, message: error instanceof Error ? error.message : String(error), step: null };
}

const isAbort = (error: unknown) => error instanceof DOMException && error.name === 'AbortError';

const FILE_LABELS: Record<string, string> = {
  'result.tif': 'Result (COG)',
  'mask.tif': 'Mask',
  'recipe.json': 'Recipe',
  'export.zip': 'Export (ZIP)',
};

// The files of a results document, by the last segment of each link — only
// the names the job API serves (`/results/{name}`), each once.
function resultFiles(doc: Record<string, { href?: unknown }>): ResultFile[] {
  const files: ResultFile[] = [];
  for (const link of Object.values(doc)) {
    if (!link || typeof link.href !== 'string') continue;
    const file = decodeURIComponent(link.href.split('/').pop() ?? '');
    if (FILE_LABELS[file] && !files.some((f) => f.file === file)) files.push({ file, label: FILE_LABELS[file] });
  }
  return files;
}

const EMPTY_DRAFT = {
  itemId: null,
  steps: [] as DraftStep[],
  picked: [] as string[],
  dtype: null,
  activeStep: null,
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
      if (status.status === 'failed') {
        updateJob(jobID, { failure: (error instanceof HttpError && error.title) || status.message || 'The job failed' });
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
    };
    set((s) => ({ jobs: [entry, ...s.jobs] }));
    persist();
    follow(jobID);
  };

  return {
    open: false,
    descriptions: {},
    ...EMPTY_DRAFT,
    jobs: [],

    openProcessing: () => {
      set({ open: true });
      const datasetId = useAppStore.getState().datasetId;
      if (datasetId) get().ensureDescription(datasetId);
    },
    closeProcessing: () => {
      abortEstimate();
      set({ open: false, reviewing: false });
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
      set({ ...EMPTY_DRAFT });
    },
    chooseItem: (itemId) => set({ itemId, picked: [], reviewError: null, startError: null }),
    addStep: (op, opVersion) => {
      const datasetId = useAppStore.getState().datasetId;
      const description = datasetId ? get().descriptions[datasetId] : undefined;
      if (description?.state !== 'ready') return;
      const operator = description.info.operators.find((o) => o.op === op && o.opVersion === opVersion);
      if (!operator?.form.supported || get().steps.length >= description.info.maxSteps) return;
      const key = nextStepKey++;
      set((s) => ({
        steps: [...s.steps, { key, op, opVersion, values: initialValues(operator.form.supported ? operator.form.fields : []) }],
        activeStep: op === 'band_math' ? key : s.activeStep,
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
        activeStep: s.activeStep === key ? null : s.activeStep,
        reviewError: null,
        startError: null,
      })),
    setActiveStep: (activeStep) => set({ activeStep }),
    togglePick: (asset) =>
      set((s) => ({
        picked: s.picked.includes(asset) ? s.picked.filter((a) => a !== asset) : [...s.picked, asset],
        reviewError: null,
        startError: null,
      })),
    // A chip click with a band-math step: the name goes at the end of the
    // expression last worked on, or of the first one.
    insertBand: (name) => {
      const s = get();
      const bandMath = s.steps.filter((step) => step.op === 'band_math');
      const target = bandMath.find((step) => step.key === s.activeStep) ?? bandMath[0];
      if (!target) return;
      const current = typeof target.values.expression === 'string' ? target.values.expression : '';
      const joiner = current === '' || /[\s(]$/u.test(current) ? '' : ' ';
      s.updateStep(target.key, 'expression', `${current}${joiner}${name}`);
    },
    setDtype: (dtype) => set({ dtype, reviewError: null, startError: null }),

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
        const status = await placeJob(order);
        // One estimate, one job: a second identical job needs its own review.
        set({ starting: false, estimate: null });
        addJob(status.jobID, status.expires, status);
      } catch (error) {
        set({ starting: false, startError: refusalOf(error, view.key, s.steps) });
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

// A new dataset or AOI drops the draft; any change of the selection drops an
// estimate still on its way (its answer would belong to another order).
useAppStore.subscribe((s, prev) => {
  const processing = useProcessingStore.getState();
  if (s.datasetId !== prev.datasetId || s.aoi !== prev.aoi) {
    processing.resetDraft();
    if (s.datasetId && processing.open) processing.ensureDescription(s.datasetId);
  } else if (
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
