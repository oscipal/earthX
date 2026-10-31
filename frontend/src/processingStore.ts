// The processing panel's state (M4-13 §3.5): the process description per
// dataset, the draft of an order, its estimate, and the jobs of this browser. A
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

import { fetchItem, fetchStatisticsAt, HttpError, postAreaStatistics, withPercentiles, type AreaStatistics } from './api';
import { checkPercent, NO_RANGE_AT_PERCENT, rescaleAtPercent, type Percent } from './percentRange';
import { crsBlockReason, type CrsEntry } from './crsUnit';
import { resultsGroupByOfOption, type DatasetOption } from './datasets';
import { indexPresetsOf } from './indexPresets';
import {
  loadShelf,
  MAX_NAME_LENGTH,
  MAX_TITLE_LENGTH,
  newId,
  orderCopy,
  readShelf,
  saveShelf,
  SHELF_KEY,
  type ShelfBatch,
  type ShelfGroup,
  type ShelfJob,
  type ShelfState,
} from './jobShelf';
import { canDelete, canRestore, canRetry, deletableParts, retryableParts } from './jobState';
import { trackJob, type TrackerOptions } from './jobTracker';
import {
  batchPass,
  effectiveRunAs,
  ESTIMATE_PARALLEL,
  foreignReason,
  foreignScenes,
  jobTitle,
  passChoices,
  titleDay,
  runChoices,
  runPool,
  unitsOf,
  type BatchUnit,
  type RunAs,
  type RunChoice,
} from './processingBatch';
import {
  canonicalJson,
  deleteJob,
  dismissJob,
  estimateOrder,
  fetchCrs,
  fetchJob,
  fetchProcess,
  fetchResults,
  fetchResultTileJson,
  placeJob,
  restoreJob,
  type AoiProvenance,
  type EstimateDocument,
  type Order,
  type ResultTileJson,
  type StatusInfo,
} from './processing';
import {
  bandTileUrl,
  colourPlacesOf,
  colourStats,
  colourTileUrl,
  isResultExpired,
  ownRangeOf,
  positive,
  resultBands,
  resultGsd,
  resultLayerName,
  presetOfResultBand,
  resultRender,
  resultStats,
  resultTileTemplate,
  startPlaceOf,
  tilesHref,
  type ResultBand,
} from './resultLayer';
import {
  assetsCarrying,
  bandNamesOf,
  defaultName,
  dropFromNormalize,
  isBandMath,
  nameProblem,
  outputBands,
  renameResult,
  resultNameOf,
  resultsOf,
  RGB,
} from './processingBands';
import {
  aoiProvenanceFor,
  auxiliaryAssetsOf,
  trueColorOf,
  bandSources,
  buildOrder,
  candidateItems,
  dataBandsOf,
  draftFromOrder,
  isArea,
  clipArea,
  lonelyBand,
  maskAssetOf,
  maskLayerOf,
  maskStepValues,
  namesInExpression,
  passesOf,
  processBlockReason,
  processInfo,
  readProblem,
  resultArea,
  selectableAssets,
  stepOfRefusal,
  type Area,
  type BandSource,
  type BuiltOrder,
  type DataBand,
  type Draft,
  type DraftStep,
  type Pass,
  type ProcessInfo,
} from './processingOrder';
import {
  areaMeasureOf,
  DEFAULT_RANGE,
  measuredRange,
  measureOf,
  NO_MEASURE,
  planPreview,
  previewRead,
  type PreviewPlan,
  type PreviewRead,
  probeChain,
  probeMosaic,
  previewOverlays,
  previewSpec,
  refusedNote,
  shortenPlan,
  type RefusedStep,
  rescaleOf,
  type PreviewMeasure,
  type PreviewRange,
  type MosaicAnswer,
  SCENE_PREVIEW_HINT,
  type PreviewSpec,
} from './processingPreview';
import type { ResultStats } from './render';
import { chooseDtype, dtypeOptions, effectiveDtype, integerNote, type Choice, type DtypeOption } from './processingDefaults';
import { buildTileUrl } from './mapLayers';
import type { PermalinkView } from './permalink';
import { readRecipe } from './recipeFile';
import { keyNames } from './recipeUpgrade';
import { initialValues, namesIn, type FieldValue } from './schemaForm';
import { datesOfIds, knownItems } from './layerDate';
import type { MapLayer } from './layers';
import { indexOfLayer, indexOrdersOfScenes } from './indexDownload';
import type { IndexPreset } from './indexPresets';
import { selectionItemsFrom, shownImageOf, ticksOfOpen, useAppStore, viewImagesOf, type AppState } from './store';
import { buildGroups } from './grouping';
import { stackLikeView } from './mosaic';
import type { EarthxMask, StacItem, TimeStepGroup } from './types';

// Where a panel opens from: the "Area" it starts with, and the scenes the
// results on screen lack.
export interface ProcessingEntry {
  area?: Area;
  // The pass a job is for, where the entry holds several (`Pass.key`); left out: none picked.
  passKey?: string;
  // Scenes of the entry that the results on screen do not hold (see `ExtraScenes`);
  // `null` drops those of an earlier entry. Left out: they stay.
  extraScenes?: ExtraScenes | null;
  // What the entry fixes; left out: nothing, and the panel is the selection's.
  fixed?: Fixed;
}

// What an entry fixes about the order (NM4-05b): the scenes, the area and that it is one job. The panel shows them locked,
// and the order keeps them whatever the selection and the map do afterwards.
export interface Fixed {
  // The scenes of the order.
  itemIds: string[];
  // The area, whatever the map holds; `null`: the whole scenes. A result's own area is "Whole scene" in its panel; "AOI only" is
  // another AOI inside it (the map's).
  aoi: GeoJSON.Polygon | GeoJSON.MultiPolygon | null;
  // Set when the entry is "process further" of a result: its steps stand first, locked.
  result: FixedResult | null;
}

export interface FixedResult {
  // What the job was called and the group it lies in: the new job gets the title plus its own steps, and the same group.
  title: string;
  groupId: string | null;
  // The first `locked` steps of the draft are those of the result: the order runs them again first, the panel does not show them
  // as steps, and they cannot be changed, moved or removed.
  locked: number;
  // The bands of the result's output: all the panel offers of the result, as bands of its own (adr/0019, Nachtrag NM4-05b). What the job did not
  // keep cannot be read by a step of the person, though the chain still holds it.
  bands: string[];
  // What the process description made of the steps (an older version taken as the listed one).
  notes: string[];
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
  // `retired`: the server answered `410` for the dataset, with its reason.
  | { state: 'error'; message: string; retired?: string };

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
  // `retired`: the order names a dataset the platform no longer carries (a `410`
  // problem document on the order routes); `reason` is the server's text, shown
  // as the tooltip of the short message.
  kind?: 'retired';
  reason?: string;
}

export type JobPhase = 'active' | 'successful' | 'failed' | 'dismissed' | 'gone';

export interface JobEntry extends ShelfJob {
  status: StatusInfo | null;
  phase: JobPhase;
  // The ZIP of the results document (`archiveOf`); `null` until the results are read.
  archive: string | null;
  // The bytes of the raster (`length` of the link `result`); `null` until the results are read, and for an export.
  bytes: number | null;
  // `earthx:resampled` of the result (Prinzip 2.9); `null` until the results are read.
  resampled: boolean | null;
  failure: string | null;
  // The kind of a failure, the end of the `type` of its problem (`failureKindOf`); `null` while unknown. It decides
  // whether "Run again" is offered (`jobState.ts`).
  failureKind: string | null;
  error: string | null;
  cancelling: boolean;
  // "Run again" is under way (NM4-34): a second press does not send the order a second time.
  retrying: boolean;
  // The server answered `410` to the order: the dataset has left, so the order cannot be sent again. Not kept.
  retryRefused: boolean;
  // Why "Run again" did not work; shown in the row and in the details.
  retryError: string | null;
  // "Delete" or "Restore" is under way (NM4-27): a second press does not start a second request.
  deleting: boolean;
  // `/results` answered `410`: the result is gone before the row's own clock says so.
  expired: boolean;
  // The tiles of a raster result (the link `tiles` of the results document, M4-13c-5);
  // `null` until the results are read, for an export, and for a result before this link existed.
  tiles: JobTiles | null;
  // The statistics of the AOI per band, for the colour scale of the layer (M4-32b); `null` until the
  // results are read, and for a result from before they were written.
  statistics: ResultStats | null;
  // The bands of the raster in the order of the file, each with its statistics, for the colour scale of the layer
  // (NM4-43e PR 2); empty until the results are read, and for a result from before the bands were named.
  bands: ResultBand[];
}

// The jobs of one batch (M4-13c-4) are one entry of the manager (UI-01 §6.10).
export type BatchEntry = ShelfBatch;

// What the manager acts on: a job, or a batch with all of its parts.
export type ManagerTarget = { jobID: string } | { batchId: string };

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
  // The job whose details the processing window shows instead of the order (UI-01 §6.8), or `null`.
  detailJobID: string | null;
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
  // What the entry fixed (`Fixed`); `null` for an order of the selection.
  fixed: Fixed | null;
  steps: DraftStep[];
  // The bands the person wants in the output, by name: results of `band_math` steps and bands of the data
  // (adr/0020 §9). `OrderView.output` is the same in the order of the file.
  output: string[];
  // The reason a name field holds a name that breaks a rule, by step: only what the person has typed and not left yet or
  // a name a loaded recipe brought; never a name the steps and the output use (review of #250).
  nameProblems: Record<number, string>;
  // The one band of a dataset that has only one, while it is in the output because the panel put it there on opening and
  // the person has not touched the choice: the first result of a band math step takes its place (review of #250).
  lonelyAuto: string | null;
  dtype: string | null;
  // The band of the output the person picked to see on the map; the preview falls back to the result added last while it
  // is not among the bands the map can show (`previewRead`).
  shown: string | null;
  // The range and colormap of the map preview: applied, and as edited (F3 (1)).
  range: PreviewRange;
  rangeDraft: PreviewRange;
  // What the map shows of the steps (their longest start that runs as tiles); `null` for none.
  preview: PreviewSpec | null;
  // Why the preview shows fewer steps than the draft chains, or none: the tiler's reason.
  previewNote: string | null;
  // The panel asks the tiler about the preview, or the map is still loading its tiles: the first tile of a mosaic
  // can take seconds when the scenes are cold, and the map says so instead of looking broken (`PreviewBadge`).
  previewSettling: boolean;
  previewTilesLoading: boolean;
  // What the tiler measured of the preview (M4-19c): the numbers its colour scale comes from, and its unit.
  measure: PreviewMeasure | null;
  // Why the preview has no measured range: the measure could not be had.
  rangeNote: string | null;
  // The user applied the range in `range` (also when it is the start range): it holds against a measure.
  rangeByHand: boolean;
  // The range fields hold what the user typed and did not apply; a measure does not write over them.
  rangeEdited: boolean;
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
  batches: BatchEntry[];
  groups: ShelfGroup[];
  // Whether the browser keeps the jobs, and all of them (UI-01 §6.4).
  shelf: ShelfState;

  openProcessing: (entry?: ProcessingEntry) => void;
  processLayer: (layerId: string) => Promise<void>;
  // ⚙ of a result layer (NM4-05b, adr/0019 option 2): the order of its job with the steps locked at the start, the output of
  // the job as the output; what is added is run with them as one order.
  extendResult: (layerId: string) => Promise<void>;
  // "Process" at a layer that shows an index (NM4-14b): the panel opens on the index as the one band of an entity of its own. The view of
  // scenes does not: its "Process" opens on the bands of the scenes, the index there is only a picture (Otto, 1.11.2026).
  extendIndexLayer: (layerId: string) => Promise<void>;
  processFocusView: () => Promise<void>;
  setRangeDraft: (patch: Partial<PreviewRange>) => void;
  applyRange: () => void;
  // "Apply" with percentiles in the fields (NM4-65 part 4): the values come from the measure of the preview, or, where it does not
  // name those percentiles (the measure of a scene), from the tiler on the first scene of the preview. Resolves to the reason
  // there is none, or `null` once the range is applied.
  applyRangePercent: (percent: Percent) => Promise<string | null>;
  // Back to the range the measure calls for (M4-19c), measured again where the measure failed.
  autoStretch: () => void;
  pinPreview: () => void;
  closeProcessing: () => void;
  // A finished job's result as a layer of its own on the map (M4-13c-5, plan §3.4).
  showResultOnMap: (jobID: string) => Promise<void>;
  openJobDetails: (jobID: string) => void;
  closeJobDetails: () => void;
  // The range and colormap set by hand in the view of a result (UI-01 §6.11): they hold for this job and for
  // every layer made of it later; `null` goes back to the default of the statistics. Kept in the browser.
  // For a result of several bands the range is that of the band `band`, saved by its name.
  setJobRange: (jobID: string, range: PreviewRange | null, band?: string) => void;
  // The band a result layer draws, by its place in the file (NM4-43e PR 2): the layer is drawn from that band, with the scale
  // the person saved for it or else the one its statistics call for.
  // `RGB` draws the three bands of the colour picture as one (NM4-64).
  chooseResultBand: (layerId: string, place: number | typeof RGB) => void;
  // The manager of the jobs (UI-01 §6.10). A job is never deleted, only archived and put in a group.
  renameJob: (jobID: string, title: string) => void;
  renameBatch: (batchId: string, title: string) => void;
  setArchived: (target: ManagerTarget, archived: boolean) => void;
  createGroup: (name: string) => string | null;
  renameGroup: (groupId: string, name: string) => void;
  // Only a group without entries goes; `false` for any other.
  removeGroup: (groupId: string) => boolean;
  moveToGroup: (target: ManagerTarget, groupId: string | null) => void;
  // "Cancel all" of a batch: its waiting and running parts, one after the other.
  cancelBatch: (batchId: string) => Promise<void>;
  // "Run again" (NM4-34): the kept order of a job that failed, was cancelled or expired goes to the server once more.
  // The new job takes the place of the old one, which stays archived and "Superseded".
  retryJob: (jobID: string) => Promise<void>;
  // "Run the failed parts again": the parts of a batch that failed or were cancelled, one after the other, in the batch.
  retryBatch: (batchId: string) => Promise<void>;
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
  // The name a `band_math` step gives its band, taken over once the person has left the field with a name that breaks no
  // rule: the later steps and the output follow. A name that breaks one is not taken (`nameProblem`).
  renameResult: (key: number, name: string) => void;
  setNameProblem: (key: number, reason: string | null) => void;
  toggleOutput: (name: string) => void;
  // Checks the one band of a dataset that has only one, on opening; `toggleOutput` and `setOutput` are the person's.
  checkLonely: (name: string) => void;
  setOutput: (names: string[]) => void;
  setDtype: (dtype: string) => void;
  // "Show": the band the preview draws. Its range is its own, so a range applied by hand for another band goes.
  setShown: (name: string) => void;
  loadRecipe: (text: string) => Promise<LoadResult>;
  restoreOrder: (order: Order, view: PermalinkView, options?: { converted?: boolean }) => Promise<LoadResult>;
  reviewOrder: () => Promise<void>;
  startJob: () => Promise<void>;
  placeOrder: (
    order: Order,
    options?: { aoiProvenance?: AoiProvenance; title?: string },
  ) => Promise<{ jobID: string } | { message: string }>;
  // Dismisses a job that is waiting or running; any other is left alone (a finished job has "Delete").
  cancelJob: (jobID: string) => Promise<void>;
  // "Delete" (NM4-27): a job that is over, or every such part of a batch. A finished one is deleted on the server with
  // a day to restore it; an entry the server cannot hold any more (expired, cancelled, forgotten) goes from the list
  // for the same day, here only.
  deleteTarget: (target: ManagerTarget) => Promise<void>;
  // "Restore": the deleted jobs of the target whose day is not over.
  restoreTarget: (target: ManagerTarget) => Promise<void>;
  // Takes the jobs kept in this browser up again, and follows those that have not expired.
  resumeJobs: () => void;
  // Follows a job that is not followed yet (one from another tab, an archived one) because its row is shown.
  followJob: (jobID: string) => void;
}

// "Load recipe…" (M4-19d): the steps of a recipe on the current selection. `converted`: the recipe was one of version 1,
// written as version 2 (adr/0020 §11); the message says so in a tooltip.
export type LoadResult = { ok: true; notes: string[]; converted?: boolean } | { ok: false; reason: string };

// --- the order as the panel sees it --------------------------------------------

export interface OrderView {
  dataset: DatasetOption | undefined;
  // What the entry fixed, and how many steps stand locked at the start (`ProcessingState.fixed`); 0 without.
  fixed: Fixed | null;
  locked: number;
  // The area the order has, and its AOI: the panel's choice and the map's AOI, or what the entry fixed. A result's own area is
  // an AOI where the job had one; `inner` is "AOI only" in the panel of a result, another AOI of which the part inside the result
  // is the area, and `outside` says that none of it is.
  area: Area;
  aoi: GeoJSON.Polygon | GeoJSON.MultiPolygon | null;
  inner: boolean;
  outside: boolean;
  // `earthx:true_color` of the dataset: red, green, blue; `null` where it has no colour picture (NM4-64).
  trueColor: [string, string, string] | null;
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
  // The bands of the data, the results of the steps and the choice of the output (adr/0020 §9, §14): every band of
  // the data by name (`dataNames`, for the rule that a result may not take one), those the output list offers, the
  // one a dataset with a single band has (`lonely`) and what "All" takes (`selectable`); the results in step order.
  dataNames: string[];
  dataBands: DataBand[];
  selectable: string[];
  lonely: string | null;
  results: Array<{ key: number; name: string }>;
  // The results the person's own steps add, and the bands of a result that stand in its place as bands of the data: the
  // results of its locked steps that its output kept (`inherited`), and the stock it did not (`hidden`; a step may not read them,
  // and they still count for a name). Both empty for an order of the selection (NM4-05b).
  fresh: Array<{ key: number; name: string }>;
  inherited: string[];
  hidden: string[];
  // The layer of the mask, which a result without it cannot mask by: there is no mask step to offer.
  maskHidden: boolean;
  // The output in the order of the file; what the order names as `output.bands`.
  output: string[];
  // Why steps, "Review" and "Start job" wait: a name field holds a name that breaks a rule. `null` for none.
  nameBlock: string | null;
  // The assets the order reads or the preview needs: those of the output, of the expressions, of `normalize` and the layer
  // of a mask, in the item's order.
  assets: string[];
  // The layer the mask steps read (`earthx:mask`), `null` for a dataset without one; and, once
  // there is a mask step, whether the scene offers its asset — the order then reads it, apart
  // from the bands the user picked, and the result leaves it out (M4-18c).
  maskLayer: EarthxMask | null;
  maskAsset: { asset: string; inOrder: boolean } | null;
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

// The scenes of the order and their passes: those the selection has, or, where the entry fixed them, those it named. The
// area is the fixed one then, not the map's.
function candidatesOf(app: SelectionState, area: Area, fixed: Fixed | null): { items: StacItem[]; passes: Pass[] } {
  const inputs = [app.items, app.selectedIds, app.groups, app.activeGroupIndex, app.aoi, area, fixed];
  if (lastCandidates && lastCandidates.inputs.every((value, i) => value === inputs[i])) return lastCandidates.result;
  const named = fixed ? new Set(fixed.itemIds) : null;
  const selected = named ? app.items.filter((item) => named.has(item.id)) : selectionItemsFrom(app);
  const items = area === 'scene' ? selected : isArea(app.aoi) ? candidateItems(selected, app.aoi) : [];
  const result = { items, passes: passesOf(items, app.groups) };
  lastCandidates = { inputs, result };
  return result;
}

// The scenes the panel can order: those ticked, or those the entry fixed.
export function sceneCountOf(app: SelectionState, p: Pick<ProcessingState, 'fixed'>): number {
  return p.fixed ? p.fixed.itemIds.length : ticksOfOpen(app).length;
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
  'datasets' | 'datasetId' | 'openSectionId' | 'sections' | 'items' | 'selectedIds' | 'groups' | 'activeGroupIndex' | 'aoi'
>;

export function selectionState(s: AppState): SelectionState {
  const { datasets, datasetId, openSectionId, sections, items, selectedIds, groups, activeGroupIndex, aoi } = s;
  return { datasets, datasetId, openSectionId, sections, items, selectedIds, groups, activeGroupIndex, aoi };
}

// The first thing a step has typed in that breaks a rule, as the tooltip of what waits for it says it: a name (what the name
// fields tell the store) or an expression that names something that is no band at its place.
function nameBlockOf(
  steps: readonly DraftStep[],
  problems: Readonly<Record<number, string>>,
  data: readonly string[],
  hidden: readonly string[],
  locked: number,
): string | null {
  for (const [index, step] of steps.entries()) {
    const reason =
      problems[step.key] ?? (isBandMath(step) ? readProblem(step, index, steps, data, index < locked ? [] : hidden)?.message : undefined);
    if (reason !== undefined) return `Step ${index + 1}: ${reason}`;
  }
  return null;
}

// The AOI a preview is cut to: the map's, or where an entry fixed one its own. A crop's own AOI is the one "AOI only" takes, and
// "Whole scene" cuts nothing (NM4-06, Otto 1.11.2026); on a result "AOI only" is the map's AOI inside the result's area.
export function clipAoiOf(p: Pick<ProcessingState, 'fixed' | 'area'>, mapAoi: GeoJSON.Geometry | null): GeoJSON.Geometry | null {
  if (!p.fixed) return mapAoi;
  if (p.fixed.result) return p.area === 'aoi' ? mapAoi : p.fixed.aoi;
  return p.area === 'aoi' ? p.fixed.aoi : null;
}

export const OUTSIDE_TEXT = 'The AOI does not meet the result.';

// The part of an AOI that lies in the area of a result: its AOI, or the scenes' footprints. The last answer is kept, since the
// clipping is the costly part of the view.
let lastClip: { inputs: unknown[]; result: GeoJSON.Polygon | GeoJSON.MultiPolygon | null } | null = null;

function clipToResult(aoi: GeoJSON.Polygon | GeoJSON.MultiPolygon, fixed: Fixed, items: readonly StacItem[]) {
  const inputs = [aoi, fixed, items];
  if (lastClip && lastClip.inputs.every((value, i) => value === inputs[i])) return lastClip.result;
  const named = new Set(fixed.itemIds);
  const outer = resultArea(fixed.aoi, items.filter((item) => named.has(item.id)));
  const result = outer === null ? aoi : clipArea(aoi, outer);
  lastClip = { inputs, result };
  return result;
}

export function orderView(selection: SelectionState, p: ProcessingState): OrderView {
  const scenes = withExtraScenes(selection, p.extraScenes);
  // What an entry fixed is the order's area, whatever the map holds; but in the panel of a result "AOI only" is the map's AOI, inside
  // the result's own area (NM4-05b).
  const inner = p.fixed?.result != null && p.area === 'aoi';
  const drawn = isArea(scenes.aoi) ? scenes.aoi : null;
  // Another AOI on a result covers part of it at most: only that part is the order's, and none of it where the AOI misses it.
  const clipped = inner && drawn !== null ? clipToResult(drawn, p.fixed!, scenes.items) : drawn;
  // A crop (an entry that fixed its scenes and an AOI, and no result) is one object whose area is chosen: "AOI only" is its own AOI, the
  // one the crop was made with, "Whole scene" the whole of its scenes (NM4-06, Otto 1.11.2026).
  const crop = p.fixed != null && p.fixed.result === null;
  const aoi = crop ? (p.area === 'aoi' ? p.fixed!.aoi : null) : p.fixed && !inner ? p.fixed.aoi : (clipped ?? drawn);
  const area: Area = crop ? p.area : p.fixed && !inner ? (p.fixed.aoi ? 'aoi' : 'scene') : p.area;
  const app = aoi === scenes.aoi ? scenes : { ...scenes, aoi };
  const dataset = app.datasets.find((d) => d.id === app.datasetId);
  const description = app.datasetId ? p.descriptions[app.datasetId] : undefined;
  const info = description?.state === 'ready' ? description.info : null;
  const { items: candidates, passes } = candidatesOf(app, area, p.fixed);
  // A result is one job. A crop is one object too, with "Run as" gone: its passes, if it has several, are the one in view or
  // every one as a job of its own (NM4-05b, NM4-06).
  const runOptions = p.fixed ? (p.fixed.result ? [] : passChoices(passes)) : runChoices(passes, candidates);
  const runAs = effectiveRunAs(p.runAs, runOptions);
  const chosen = passes.find((c) => c.key === p.passKey) ?? (passes.length === 1 ? passes[0] : null);
  const units = unitsOf(runAs, chosen, passes, candidates);
  const pass = runAs === 'one' ? chosen : batchPass(runAs, units);
  const format = dataset?.collection['earthx:format'] ?? null;
  // The scenes of a pass agree on the assets and bands (the server checks it, M4-12a).
  const sources = pass ? bandSources(pass.items[0], format, info?.variableSeparator ?? null, dataset?.collection) : [];
  const maskLayer = maskLayerOf(dataset?.collection);
  const maskAsset = maskAssetOf(p.steps, maskLayer);
  const auxiliary = auxiliaryAssetsOf(dataset?.collection);
  const stock = dataBandsOf(sources, auxiliary, maskLayer?.asset ?? null);
  const dataNames = sources.flatMap(bandNamesOf);
  const selectable = selectableAssets(sources, auxiliary, maskLayer?.asset ?? null);
  const results = resultsOf(p.steps);
  // A result offers its output and nothing else (adr/0019, Nachtrag NM4-05b): the bands of the data and the results of its steps that the job
  // kept stand as the bands of the data; the rest of the stock is hidden.
  const from = p.fixed?.result ?? null;
  const kept = new Set(from?.bands ?? []);
  const lockedResults = from ? resultsOf(p.steps.slice(0, from.locked)) : [];
  const inherited = lockedResults.filter((r) => kept.has(r.name)).map((r) => r.name);
  const hidden = from
    ? [...stock.map((b) => b.name).filter((name) => !kept.has(name)), ...lockedResults.map((r) => r.name).filter((name) => !kept.has(name))]
    : [];
  const dataBands: DataBand[] = from
    ? [
        ...inherited.map((name) => ({ name, asset: '', unit: null, auxiliary: false, layer: false })),
        ...stock.filter((band) => kept.has(band.name)),
      ]
    : stock;
  const onlyBand = dataBands.filter((b) => !b.auxiliary && !b.layer).map((b) => b.name);
  const output = outputBands(p.output, results.map((r) => r.name), dataBands.map((b) => b.name));
  const inOutput = new Set(output);
  // What the order reads: the bands of the output, those an expression or a `normalize` names, the layer of a mask.
  const named = [
    ...output,
    ...bandMathExpressions(p.steps).flatMap((expression) => [...namesInExpression(expression)]),
    ...p.steps.flatMap((step) => (step.op === 'normalize' && typeof step.values.bands === 'string' ? namesIn(step.values.bands) : [])),
  ];
  const carried = new Set([...assetsCarrying(sources, named), ...(maskAsset ? [maskAsset] : [])]);
  const assets = sources.map((s) => s.asset).filter((asset) => carried.has(asset));
  // The output type follows the data and the steps as they will be sent (Otto,
  // 12.10.2026); the resampling is the user's own choice and recommended nowhere.
  // A step that gives fractions counts only where its result is in the output (adr/0020 §8); the layer of a mask is
  // no band of the result unless it is in the output itself.
  const inOrder = sources.filter((s) => bandNamesOf(s).some((name) => inOutput.has(name)));
  const choices = p.steps
    .filter((step) =>
      isBandMath(step)
        ? inOutput.has(resultNameOf(step))
        : step.op !== 'normalize' || (typeof step.values.bands === 'string' && namesIn(step.values.bands).some((name) => inOutput.has(name))),
    )
    .map((step) => ({
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
  const outside = inner && drawn !== null && clipped === null;
  const buildFor = (itemIds: string[]): BuiltOrder | null => {
    if (!info || !dataset) return null;
    const result = buildOrder({ datasetId: dataset.id, itemIds, area, aoi, steps: p.steps, bands: output, data: dataNames, hidden, locked: from?.locked ?? 0, dtype, info });
    if (outside) return { ...result, order: null, problems: [...result.problems, OUTSIDE_TEXT] };
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
    fixed: p.fixed,
    locked: p.fixed?.result?.locked ?? 0,
    area,
    aoi,
    inner,
    outside,
    info,
    candidates,
    passes,
    trueColor: trueColorOf(dataset?.collection),
    pass,
    runChoices: runOptions,
    runAs,
    parts,
    sources,
    dataNames,
    dataBands,
    selectable: dataBands.filter((b) => !b.auxiliary && !b.layer).map((b) => b.name),
    // A result with one band to choose from has it checked once, as a scene with one band does.
    lonely: from ? (onlyBand.length === 1 ? onlyBand[0] : null) : lonelyBand(selectable, sources),
    results,
    fresh: results.slice(lockedResults.length),
    inherited,
    hidden,
    maskHidden: from !== null && maskLayer !== null && !kept.has(maskLayer.band),
    output,
    nameBlock: nameBlockOf(p.steps, p.nameProblems, dataNames, hidden, from?.locked ?? 0),
    assets,
    maskLayer,
    maskAsset: maskAsset ? { asset: maskAsset, inOrder: assets.includes(maskAsset) } : null,
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
// scenes is no scene; the licence is the dataset's, as for the selection. A result can be, where the browser keeps
// the order of its job (adr/0019: F2); it needs no more than that, an expired result is run from the scenes all the same (F4).
export const NO_COPY_TEXT = 'No copy of the original order is kept in this browser. Open its recipe.json instead.';
export const PROCESS_RESULT_TEXT = 'Process further';
export const EXPIRED_PROCESS_TEXT = 'Expired: runs everything again from the scenes.';

export function layerProcessBlock(
  layer: MapLayer,
  datasets: readonly DatasetOption[],
  jobs: ReadonlyArray<Pick<JobEntry, 'jobID' | 'order'>> = [],
): string | null {
  if (layer.derived === 'result') {
    const order = jobs.find((j) => j.jobID === layer.result?.jobID)?.order;
    if (!order) return NO_COPY_TEXT;
    if (order.output.kind !== 'raster') return 'An export has no bands to process further.';
    const input = order.inputs[0];
    return processBlockReason(datasets.find((d) => d.id === input.dataset), input.groups.flat().length);
  }
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

// Whether the shelf of this page may not be written: its stored value is of a version this build does not know.
let shelfLocked = false;
// A copy of an order went to make room, and the shelf goes on saying so for this page.
let copiesDropped = false;
let storageListening = false;

// Batches whose "Cancel all" is under way: a second click does not start a second round.
const cancellingBatches = new Set<string>();
// The same for "Run the failed parts again".
const retryingBatches = new Set<string>();

const inTarget = (job: ShelfJob, target: ManagerTarget): boolean =>
  'jobID' in target ? job.jobID === target.jobID : job.batchId === target.batchId;

// How long "Cancel" waits for the fresh state of the job before it gives up (and cancels nothing).
const CANCEL_CHECK_MS = 4000;

// How long an entry that only this browser deletes can be restored: as long as the server gives a job (NM4-27).
const DELETE_TERM_MS = 86_400_000;

const withOthers = <T extends { id: string }>(first: T[], rest: T[]): T[] => [
  ...first,
  ...rest.filter((r) => !first.some((f) => f.id === r.id)),
];

// Tests start from no jobs: the trackers stop and the list is empty. What the browser keeps is theirs to clear.
export function resetJobs(): void {
  for (const stop of trackers.values()) stop();
  trackers.clear();
  shelfLocked = false;
  copiesDropped = false;
  cancellingBatches.clear();
  retryingBatches.clear();
  useProcessingStore.setState({ jobs: [], batches: [], groups: [], shelf: 'ok', detailJobID: null });
}

// A job still stands for the order it was placed for: it runs, or its results are there. Another one may be
// placed once it failed, was cancelled or has expired — the way to "Start the job again".
export function orderStands(job: JobEntry | undefined): boolean {
  if (!job) return false;
  if (job.phase === 'active') return true;
  return job.phase === 'successful' && !job.expired && !isResultExpired(job.expires, Date.now());
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

// Whether the step with this key stands in the part that came with a result and is locked (NM4-05b).
function isLocked(s: Pick<ProcessingState, 'steps' | 'fixed'>, key: number): boolean {
  const at = s.steps.findIndex((step) => step.key === key);
  return at >= 0 && at < (s.fixed?.result?.locked ?? 0);
}

const RETIRED_TEXT = 'Dataset retired';

// Only the order routes (estimate, placing a job) end here. A `410` of a result
// (`readResults`, `showResultOnMap`) means "expired" and is handled there.
function refusalOf(error: unknown, key: string, steps: readonly DraftStep[]): Refusal {
  if (error instanceof HttpError) {
    if (error.status === 410 && error.detail !== undefined) {
      return { key, message: RETIRED_TEXT, step: null, status: 410, kind: 'retired', reason: error.detail };
    }
    const text = error.detail ?? error.message;
    const hint = error.status === 503 && !/try again/iu.test(text) ? ' Try again in a moment.' : '';
    return { key, message: `${text}${hint}`, step: stepOfRefusal(text, steps), status: error.status };
  }
  return { key, message: error instanceof Error ? error.message : String(error), step: null, status: null };
}

// The text of a refusal outside the panel's draft (the download dialog's jobs).
// Where there is no tooltip, the text carries the reason.
export function refusalMessage(error: unknown): string {
  const refusal = refusalOf(error, '', []);
  return refusal.reason ? `${refusal.message}: ${refusal.reason}` : refusal.message;
}

const isAbort = (error: unknown) => error instanceof DOMException && error.name === 'AbortError';

// The one archive of a result (M4-11b-2): an export's `export.zip`, or a raster
// job's `result.zip` (output `bundle`, M4-11b-1). It holds every file of the job; the
// manager offers it and nothing else (UI-01 §1 point 12).
const ZIP_FILES = ['export.zip', 'result.zip'];
export const ZIP_LABEL = 'Download (ZIP)';

// The file name of the archive a results document links, by the last segment of the link.
export function archiveOf(doc: Record<string, { href?: unknown }>): string | null {
  const names = Object.values(doc).flatMap((link) =>
    link && typeof link.href === 'string' ? [decodeURIComponent(link.href.split('/').pop() ?? '')] : [],
  );
  return ZIP_FILES.find((file) => names.includes(file)) ?? null;
}

// What a failed job's row says (K8): the backend's fixed title, except where a
// shorter hint of what to do helps; the kind is the end of the problem's `type`.
const FAILURE_TEXTS: Record<string, string> = {
  runtime_exceeded: 'The job took longer than allowed. Choose a smaller area or fewer assets.',
};

const FAILED_TYPE = 'urn:earthx:job-failed:';

// The kind of a failed job's problem document (`processing.failure_kind`); `null` for an answer that names none.
export function failureKindOf(error: unknown): string | null {
  return error instanceof HttpError && error.type?.startsWith(FAILED_TYPE) ? error.type.slice(FAILED_TYPE.length) : null;
}

export function failureText(error: unknown, fallback: string): string {
  if (!(error instanceof HttpError)) return fallback;
  return FAILURE_TEXTS[failureKindOf(error) ?? ''] ?? error.title ?? fallback;
}

// Whether the platform has said that it no longer carries the dataset of the job's order (a `410` of its description).
export function orderRetired(job: JobEntry, descriptions: Record<string, Description>): boolean {
  const description = job.order ? descriptions[job.order.inputs[0]?.dataset ?? ''] : undefined;
  return description?.state === 'error' && description.retired !== undefined;
}

// The names a draft uses that this selection has no band for: the notes of a loaded recipe. Where the data lists no
// bands at all there is nothing to compare with.
function missingBands(draft: { steps: readonly DraftStep[]; bands: readonly string[] }, view: OrderView): string[] {
  const known = new Set([...view.dataNames, ...view.results.map((result) => result.name)]);
  if (view.dataNames.length === 0) return [];
  const used = [
    ...draft.bands,
    ...bandMathExpressions(draft.steps).flatMap((expression) => [...namesInExpression(expression)]),
    ...draft.steps.flatMap((step) => (step.op === 'normalize' && typeof step.values.bands === 'string' ? namesIn(step.values.bands) : [])),
  ];
  return [...new Set(used.filter((name) => !known.has(name)))].map((name) => `Band ${name} is not in this selection.`);
}

const EMPTY_DRAFT = {
  passKey: null,
  // "Whole scene" first (Otto, 12.10.2026).
  area: 'scene' as Area,
  runAs: 'one' as RunAs,
  extraScenes: null as ExtraScenes | null,
  fixed: null as Fixed | null,
  steps: [] as DraftStep[],
  output: [] as string[],
  nameProblems: {} as Record<number, string>,
  lonelyAuto: null as string | null,
  dtype: null,
  shown: null as string | null,
  range: DEFAULT_RANGE,
  rangeDraft: DEFAULT_RANGE,
  preview: null as PreviewSpec | null,
  previewNote: null as string | null,
  previewSettling: false,
  previewTilesLoading: false,
  measure: null as PreviewMeasure | null,
  rangeNote: null as string | null,
  rangeByHand: false,
  rangeEdited: false,
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
  // The process description of a dataset once it has loaded (or failed to).
  const describe = (datasetId: string) => {
    get().ensureDescription(datasetId);
    return new Promise<Description | undefined>((resolve) => {
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
  };

  // The panel for a layer or a view: a crop merged and cut to its AOI is one object, so its scenes and area are fixed and
  // "Run as" is gone (NM4-06); anything else starts from the scenes and "Whole scene". Where the crop holds several passes, the
  // one in view (`preferred`, the scenes the view had chosen) is the one a job is for, the first one if it names none.
  const openCrop = (fixed: Fixed | null, extraScenes: ExtraScenes, preferred: readonly string[]) => {
    const scenes = extraScenes.items.length > 0 ? extraScenes : null;
    const passes = fixed ? orderView(selectionState(useAppStore.getState()), { ...get(), fixed, area: 'aoi', extraScenes: scenes }).passes : [];
    const inView = passes.find((pass) => pass.items.some((item) => preferred.includes(item.id))) ?? passes[0];
    get().openProcessing({
      area: fixed ? 'aoi' : 'scene',
      extraScenes: scenes,
      ...(fixed ? { fixed } : {}),
      ...(inView && passes.length > 1 ? { passKey: inView.key } : {}),
    });
  };

  // The order as the draft, on its scenes and area: what "Open in panel", a link and "process further" share (adr/0019). The
  // dataset first (a new dataset drops the draft), then the scenes (fetched one by one where the results lack them), the area
  // and the draft itself; `patch` adds what the caller keeps besides. Nothing changes unless the order is taken up as a whole.
  const takeOrder = async (
    order: Order,
    whose: string,
    patch: (draft: Draft, notes: string[]) => Partial<ProcessingState>,
  ): Promise<{ ok: true; notes: string[]; draft: Draft } | { ok: false; reason: string }> => {
    const datasetId = order.inputs[0].dataset;
    const dataset = useAppStore.getState().datasets.find((d) => d.id === datasetId);
    if (!dataset) {
      // A dataset the catalog does not list: the server says whether it left (`410`) or never was.
      const gone = await describe(datasetId);
      if (gone?.state === 'error' && gone.retired) return { ok: false, reason: `${RETIRED_TEXT}: ${gone.retired}` };
    }
    const block = processBlockReason(dataset, order.inputs[0].groups.flat().length);
    if (block) return { ok: false, reason: block };
    const description = await describe(datasetId);
    if (description?.state !== 'ready') return { ok: false, reason: 'The process description of the dataset could not be loaded.' };
    const { info } = description;
    const { draft, problems, notes } = draftFromOrder(order, info, () => nextStepKey++);
    if (problems.length > 0) return { ok: false, reason: problems.slice(0, 3).join(' ') };
    if (draft.dtype !== null && !info.dtypes.includes(draft.dtype)) notes.push(`Data type ${draft.dtype} is not offered for this dataset.`);
    const dtype = draft.dtype !== null && info.dtypes.includes(draft.dtype) ? draft.dtype : null;
    abortEstimate();
    startGeneration += 1;
    useAppStore.setState({ datasetId, selectedDatasetIds: [datasetId] });
    const extraScenes = await selectScenes(draft.groups.flat(), whose);
    if (!extraScenes) return { ok: false, reason: useAppStore.getState().error ?? 'The scenes could not be loaded.' };
    if (draft.aoi) useAppStore.getState().setAoi(draft.aoi);
    set({
      ...EMPTY_DRAFT,
      open: true,
      detailJobID: null,
      area: draft.aoi ? 'aoi' : 'scene',
      extraScenes: extraScenes.items.length > 0 ? extraScenes : null,
      steps: draft.steps,
      output: draft.bands,
      dtype,
      ...patch(draft, notes),
    });
    return { ok: true, notes, draft };
  };

  // The panel on an index as an entity of its own (`extendIndexLayer`): the order the index would be a job with, taken up like the
  // order of a result, its one step locked, its one band the whole stock.
  const openIndexPanel = async (args: {
    dataset: DatasetOption;
    preset: IndexPreset;
    groups: readonly (readonly string[])[];
    aoi: GeoJSON.Polygon | GeoJSON.MultiPolygon | null;
    title: string;
    whose: string;
  }) => {
    const { dataset, preset, groups, aoi, title, whose } = args;
    const block = processBlockReason(dataset, groups.flat().length);
    if (block) return void useAppStore.setState({ error: block });
    const description = await describe(dataset.id);
    if (description?.state !== 'ready') return void useAppStore.setState({ error: 'The process description of the dataset could not be loaded.' });
    const made = indexOrdersOfScenes({ datasetId: dataset.id, groups, aoi, preset, dataset, info: description.info });
    if ('problem' in made) return void useAppStore.setState({ error: made.problem });
    const taken = await takeOrder(made.orders[0], whose, (draft, notes) => ({
      // As the panel of a result: "Whole scene" of it; "AOI only" is another AOI inside it. The band is in the list of the output, not
      // checked, as the bands of a scene are.
      area: 'scene',
      output: [],
      fixed: {
        itemIds: draft.groups.flat(),
        aoi: draft.aoi,
        result: { title, groupId: null, locked: draft.steps.length, bands: [...draft.bands], notes },
      },
    }));
    if (!taken.ok) useAppStore.setState({ error: taken.reason });
    // The preview lies with the entry "Results", above the layer it is made from.
    else useAppStore.getState().resultsToTop();
  };

  const updateJob = (jobID: string, patch: Partial<JobEntry>) => {
    set((s) => ({ jobs: s.jobs.map((j) => (j.jobID === jobID ? { ...j, ...patch } : j)) }));
  };

  // The server answered `404`: it does not know the job. That is kept, so that a reload asks about it no more.
  const forget = (jobID: string) => {
    updateJob(jobID, { phase: 'gone', lost: true });
    persist();
  };

  // Keeps the jobs in the browser (UI-01 §6.4). Where the browser is full the oldest copies of orders go,
  // here as well as there, and the shelf says so; it does not say it less once it has.
  const persist = (removedGroups: string[] = []) => {
    if (shelfLocked) {
      set({ shelf: 'memory' });
      return;
    }
    const { jobs, batches, groups } = get();
    const saved = saveShelf({ jobs, batches, groups }, removedGroups);
    const dropped = new Set(saved.dropped);
    if (dropped.size > 0) copiesDropped = true;
    set((s) => ({
      jobs: dropped.size > 0 ? s.jobs.map((j) => (dropped.has(j.jobID) ? { ...j, order: null } : j)) : s.jobs,
      shelf: saved.state === 'ok' && copiesDropped ? 'trimmed' : saved.state,
    }));
  };

  const readResults = async (jobID: string, status: StatusInfo) => {
    try {
      const doc = await fetchResults(jobID);
      const properties = doc.result?.properties;
      const href = tilesHref(doc);
      updateJob(jobID, {
        archive: archiveOf(doc),
        bytes: typeof doc.result?.length === 'number' ? doc.result.length : null,
        resampled: properties ? properties['earthx:resampled'] === true : null,
        tiles: href
          ? { href, width: typeof doc.result?.width === 'number' ? doc.result.width : null, gsd: positive(properties?.gsd) }
          : null,
        statistics: resultStats(properties),
        bands: resultBands(properties, get().jobs.find((j) => j.jobID === jobID)?.order ?? null),
      });
    } catch (error) {
      if (error instanceof HttpError && error.status === 410) {
        updateJob(jobID, { expired: true });
      } else if (status.status === 'failed') {
        updateJob(jobID, { failure: failureText(error, status.message || 'The job failed'), failureKind: failureKindOf(error) });
      } else {
        updateJob(jobID, { error: error instanceof Error ? error.message : String(error) });
      }
    }
  };

  // What the server said of a job.
  const applyStatus = (jobID: string, status: StatusInfo) => {
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
    if (phase === 'dismissed') trackers.delete(jobID);
  };

  const follow = (jobID: string) => {
    trackers.get(jobID)?.();
    const stop = trackJob(
      jobID,
      {
        onStatus: (status) => applyStatus(jobID, status),
        onGone: () => {
          trackers.delete(jobID);
          forget(jobID);
        },
      },
      trackerOptions,
    );
    trackers.set(jobID, stop);
  };

  // A job as the list holds it: what the browser kept of it, and what is learnt from the server.
  const jobEntry = (job: ShelfJob, status: StatusInfo | null, now: number): JobEntry => {
    // A job past its expiry is not asked after; it stays in the list as expired.
    const over = Date.parse(job.expires) <= now;
    // A job the server forgot, or one that is deleted, is not asked about: its state is what it was kept as.
    const known = !job.lost && job.deletedUntil === null;
    return {
      ...job,
      status,
      phase: over || !known ? 'gone' : 'active',
      archive: null,
      bytes: null,
      resampled: null,
      failure: null,
      failureKind: null,
      error: null,
      cancelling: false,
      retrying: false,
      retryRefused: false,
      retryError: null,
      deleting: false,
      expired: over,
      tiles: null,
      statistics: null,
      bands: [],
    };
  };

  type NewJob = Pick<ShelfJob, 'jobID' | 'expires'> & Partial<ShelfJob> & { status: StatusInfo };

  const addJob = ({ status, ...job }: NewJob, replaces?: string) => {
    if (get().jobs.some((j) => j.jobID === job.jobID)) return;
    const blank: ShelfJob = {
      title: null,
      titleDefault: null,
      createdAt: new Date().toISOString(),
      archived: false,
      groupId: null,
      batchId: null,
      part: null,
      range: null,
      bandRanges: {},
      shownBand: null,
      dates: null,
      order: null,
      deletedUntil: null,
      serverDeleted: false,
      lost: false,
      superseded: false,
      ...job,
    };
    // The day of the scenes is read while they are known: the layer of the result shows it long after the search has moved on.
    if (job.dates === undefined && job.order) blank.dates = datesOfOrder(job.order);
    blank.titleDefault = job.titleDefault ?? job.title ?? null;
    const entry = jobEntry(blank, status, Date.now());
    set((s) => {
      // A job that replaces another stands where it stood, and the old one goes aside, archived.
      const at = replaces ? s.jobs.findIndex((j) => j.jobID === replaces) : -1;
      const jobs = s.jobs.map((j) => (j.jobID === replaces ? { ...j, archived: true, superseded: true, retrying: false, retryError: null } : j));
      return { jobs: at < 0 ? [entry, ...jobs] : [...jobs.slice(0, at), entry, ...jobs.slice(at)] };
    });
    persist();
    follow(job.jobID);
  };

  // "<operators> · <dataset> · <day>". Made before the first job is placed: the draft may change while they are. A job that
  // goes on from a result is called as that one was, and "→" the operators it adds (NM4-05b).
  const titleOf = (view: OrderView) => {
    const { steps, fixed } = get();
    const titleOfStep = (step: DraftStep) =>
      view.info?.operators.find((o) => o.op === step.op && o.opVersion === step.opVersion)?.title ?? step.op;
    const from = fixed?.result;
    if (from?.title) {
      const added = [...new Set(steps.slice(from.locked).map(titleOfStep))].join(', ');
      const tail = added ? ` → ${added}` : '';
      return `${from.title.slice(0, MAX_TITLE_LENGTH - tail.length)}${tail}`;
    }
    const resultsGroupBy = view.dataset ? resultsGroupByOfOption(view.dataset) : null;
    return jobTitle({
      operators: steps.map(titleOfStep),
      dataset: view.dataset?.title ?? '',
      day: titleDay(view.pass?.items ?? [], resultsGroupBy),
    });
  };

  // The group a job from a result lies in: that of the result, if it still exists.
  const groupOf = (): { groupId: string } | Record<string, never> => {
    const groupId = get().fixed?.result?.groupId;
    return groupId && get().groups.some((g) => g.id === groupId) ? { groupId } : {};
  };

  // The jobs of the reviewed batch the server took in; one after the other, and a
  // refused start does not hold back the rest (§3.6). A job whose review the
  // server refused is not started.
  const startBatch = async (view: OrderView) => {
    const batch = get().batch;
    if (!view.key || batch?.key !== view.key) return;
    const title = titleOf(view);
    const own = startLook(view, get());
    const mine = ++startGeneration;
    set({ starting: true, startError: null, batchStartRefusals: null });
    // One entry for the batch, made with its first job; the jobs themselves stay jobs of their own.
    const batchId = newId();
    const createdAt = new Date().toISOString();
    let opened = false;
    const refusals: { label: string; message: string }[] = [];
    for (const [index, outcome] of batch.parts.entries()) {
      const part = view.parts[index];
      if (!outcome.doc || !part?.order) continue;
      try {
        const status = await placeJob(part.order);
        if (!opened) {
          set((s) => ({
            batches: [{ id: batchId, title, titleDefault: title, createdAt, archived: false, groupId: null, refused: [] }, ...s.batches],
          }));
        }
        opened = true;
        addJob({
          jobID: status.jobID,
          expires: status.expires,
          status,
          title,
          ...own,
          batchId,
          part: part.unit.label,
          order: orderCopy(part.order),
        });
      } catch (error) {
        refusals.push({ label: part.unit.label, message: refusalMessage(error) });
      }
    }
    if (opened && refusals.length > 0) {
      set((s) => ({ batches: s.batches.map((b) => (b.id === batchId ? { ...b, refused: refusals } : b)) }));
    }
    if (opened) persist();
    // A draft dropped meanwhile (`resetDraft`) has its own state by now.
    if (mine !== startGeneration) return;
    // One review, these jobs: starting again needs a new review.
    set({ starting: false, batch: null, batchStartRefusals: refusals.length > 0 ? { key: view.key, refusals } : null });
  };

  // "Delete" of one job (NM4-27). What the server still holds is deleted there: it answers with the end of the
  // day in which "Restore" works. An entry it cannot hold any more is deleted here only, for the same day.
  const deleteOne = async (jobID: string) => {
    const job = get().jobs.find((j) => j.jobID === jobID);
    const now = Date.now();
    if (!job || !canDelete(job, now)) return;
    const onServer = (job.phase === 'successful' || job.phase === 'failed') && !job.lost && !job.expired && !isResultExpired(job.expires, now);
    const here = (extra: Partial<JobEntry> = {}) => {
      updateJob(jobID, { deleting: false, deletedUntil: new Date(now + DELETE_TERM_MS).toISOString(), serverDeleted: false, ...extra });
      persist();
    };
    if (!onServer) {
      here();
      return;
    }
    updateJob(jobID, { deleting: true, error: null });
    try {
      const status = await deleteJob(jobID);
      trackers.get(jobID)?.();
      trackers.delete(jobID);
      updateJob(jobID, { deleting: false, deletedUntil: status.expires, serverDeleted: true, phase: 'dismissed' });
      persist();
    } catch (error) {
      if (error instanceof HttpError && error.status === 404) {
        trackers.get(jobID)?.();
        trackers.delete(jobID);
        here({ phase: 'gone', lost: true });
      } else {
        updateJob(jobID, { deleting: false, error: 'The job could not be deleted. Try again.' });
      }
    }
  };

  // "Restore" of one deleted job. The server takes back what it holds; an entry that was deleted here only is
  // simply listed again.
  const restoreOne = async (jobID: string) => {
    const job = get().jobs.find((j) => j.jobID === jobID);
    if (!job || !canRestore(job, Date.now())) return;
    if (!job.serverDeleted) {
      updateJob(jobID, { deletedUntil: null });
      persist();
      return;
    }
    updateJob(jobID, { deleting: true, error: null });
    try {
      const status = await restoreJob(jobID);
      updateJob(jobID, { deleting: false, deletedUntil: null, serverDeleted: false });
      persist();
      applyStatus(jobID, status);
    } catch (error) {
      if (error instanceof HttpError && error.status === 404) {
        // The day is over for the server, or it forgot the job: nothing to take back.
        updateJob(jobID, { deleting: false, deletedUntil: null, serverDeleted: false, phase: 'gone', lost: true, error: 'The job could not be restored.' });
        persist();
      } else {
        updateJob(jobID, { deleting: false, error: 'The job could not be restored. Try again.' });
      }
    }
  };

  // The shelf as another tab last wrote it (`storage` event): its entries are this tab's too. A job this tab
  // does not know is not followed until `followJob`.
  const takeShelf = () => {
    const { shelf, state } = readShelf();
    // A shelf that cannot be read, or reads as empty, says nothing about the groups; the jobs of this tab
    // stay what they are.
    if (state === 'memory') return;
    const empty = shelf.jobs.length + shelf.batches.length + shelf.groups.length === 0;
    const stored = new Map(shelf.jobs.map((j) => [j.jobID, j]));
    set((s) => {
      const known = new Set(s.jobs.map((j) => j.jobID));
      const added = shelf.jobs.filter((j) => !known.has(j.jobID)).map((j) => jobEntry(j, null, Date.now()));
      // A job this tab holds as deleted and another tab restored is asked about again: its state is not known here.
      const merged = s.jobs.map((j) => {
        const other = stored.get(j.jobID);
        const back = other !== undefined && j.deletedUntil !== null && other.deletedUntil === null && !other.lost;
        return { ...j, ...other, ...(back ? { phase: 'active' as const, status: null } : {}) };
      });
      return {
        jobs: [...added, ...merged],
        batches: withOthers(shelf.batches, s.batches),
        // What is stored is the truth about groups: another tab may have removed an empty one.
        groups: empty ? s.groups : shelf.groups,
      };
    });
  };

  return {
    open: false,
    detailJobID: null,
    descriptions: {},
    crs: {},
    ...EMPTY_DRAFT,
    jobs: [],
    batches: [],
    groups: [],
    shelf: 'ok',

    // Opened from the selection (`ViewBar`), a layer or the full-resolution view.
    // Every entry sets the area: "Whole scene" unless the entry says otherwise
    // (Otto 19.10.2026).
    openProcessing: (entry = {}) => {
      set((s) => ({
        // Steps that came with a result stay with it: another entry starts a draft of its own.
        ...(s.fixed?.result && !entry.fixed?.result ? { ...EMPTY_DRAFT } : {}),
        open: true,
        detailJobID: null,
        area: entry.area ?? 'scene',
        fixed: entry.fixed ?? null,
        ...(entry.passKey !== undefined ? { passKey: entry.passKey } : {}),
        ...(entry.extraScenes !== undefined ? { extraScenes: entry.extraScenes } : {}),
      }));
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
      if (layer?.derived === 'result') return get().extendResult(layerId);
      if (layer && !layer.derived && indexOfLayer(layer, useAppStore.getState().datasets)) return get().extendIndexLayer(layerId);
      if (!layer || layerProcessBlock(layer, useAppStore.getState().datasets) !== null) return;
      // The preview lies with the entry "Results": above the layer it is made from, so that it can be seen.
      useAppStore.getState().resultsToTop();
      useAppStore.getState().activateLayerContext(layerId);
      const extraScenes = await selectScenes(layer.restore.itemIds, 'this layer');
      if (!extraScenes) return;
      // A layer merged and cut to its AOI is one object (NM4-06).
      const { cropToAoi, aoi } = layer.restore;
      openCrop(cropToAoi && isArea(aoi) ? { itemIds: layer.restore.itemIds, aoi, result: null } : null, extraScenes, layer.restore.selectedIds);
    },
    processFocusView: async () => {
      useAppStore.getState().activateViewContext();
      const app = useAppStore.getState();
      // A job has one dataset: the scenes of every image of the dataset that is shown (NM4-53).
      const images = viewImagesOf(app);
      const shown = shownImageOf(images, app.shownImage);
      const ids = shown ? images.filter((image) => image.datasetId === shown.datasetId).flatMap((image) => image.ids) : Object.keys(app.downloaded);
      const extraScenes = await selectScenes(ids, 'this view');
      if (!extraScenes) return;
      const { cropToAoi, viewAoi } = app;
      // The pass in view is the one of the image the head of the view shows.
      openCrop(cropToAoi && isArea(viewAoi) ? { itemIds: ids, aoi: viewAoi, result: null } : null, extraScenes, shown?.ids ?? []);
    },
    // Values typed by hand are no percentiles any more (NM4-65 part 4).
    setRangeDraft: (patch) =>
      set((s) => ({ rangeDraft: { ...s.rangeDraft, ...patch, ...('vmin' in patch || 'vmax' in patch ? { percent: undefined } : {}) }, rangeEdited: true })),
    applyRange: () => {
      if ('rescale' in rescaleOf(get().rangeDraft)) set((s) => ({ range: s.rangeDraft, rangeByHand: true, rangeEdited: false }));
    },
    applyRangePercent: async (percent) => {
      const checked = checkPercent(percent);
      if ('problem' in checked) return checked.problem;
      const spec = wantedPreview();
      const measure = get().measure;
      // The measure of this very preview, if it names every percentile asked for.
      const asked = [checked.low, checked.high].filter((n) => n !== 0 && n !== 100);
      const named = measure && spec && measure.key === spec.measure && measure.raw && measure.raw.length > 0 && measure.raw.every((band) => asked.every((n) => typeof band[`percentile_${n}`] === 'number'));
      let bands = named ? measure.raw! : null;
      if (!bands) {
        if (!spec) return 'There is no preview to take the percentiles from.';
        try {
          bands = Object.values(await fetchStatisticsAt(withPercentiles(spec.sceneMeasure, asked)));
        } catch (error) {
          return `Could not measure the percentiles: ${error instanceof Error ? error.message : String(error)}`;
        }
      }
      const range = rescaleAtPercent(bands, checked);
      if (!range) return NO_RANGE_AT_PERCENT;
      const look: PreviewRange = { ...get().rangeDraft, vmin: String(range[0]), vmax: String(range[1]), percent: { low: String(checked.low), high: String(checked.high) } };
      set({ rangeDraft: look, range: look, rangeByHand: true, rangeEdited: false });
      return null;
    },
    autoStretch: () => {
      failedMeasures.clear();
      measuring.clear();
      areaAnswers.clear();
      // The measure over the AOI is asked again where it fell back to the scene.
      for (const [key, measure] of measures) if (measure.source === 'fallback') measures.delete(key);
      settledKey = null;
      set({ range: DEFAULT_RANGE, rangeByHand: false, rangeEdited: false });
      refreshPreview();
    },
    // The preview on screen becomes a layer of its own.
    pinPreview: () => {
      const { preview } = get();
      const app = useAppStore.getState();
      if (!preview) return;
      app.pinDerivedLayer({
        name: `Preview · ${preview.title}`,
        derived: 'preview',
        ...(preview.perScene ? { note: SCENE_PREVIEW_HINT } : {}),
        overlays: stackLikeView(previewOverlays(preview, clipAoiOf(get(), app.aoi))),
        itemIds: [...new Set([...preview.mosaics.flatMap((mosaic) => mosaic.order), ...preview.scenes.map((scene) => scene.id)])],
        cropToAoi: preview.clipToAoi,
      });
    },
    closeProcessing: () => {
      abortEstimate();
      set({ open: false, reviewing: false, detailJobID: null });
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
      // A result of several bands starts with the band the preview showed; the layer says which bands it has.
      const several = job.bands.length > 1;
      const dataset = useAppStore.getState().datasets.find((d) => d.id === job.order?.inputs[0]?.dataset);
      const colour = several ? colourPlacesOf(job.bands, trueColorOf(dataset?.collection)) : null;
      const place = startPlaceOf(job.bands, job.order, job.shownBand, colour);
      const stats = place === RGB ? colourStats(job.bands, colour!) : several ? job.bands[place].stats : job.statistics;
      const preset = place === RGB ? null : presetOfResultBand(job.bands[several ? place : 0], indexPresetsOf(dataset?.collection));
      const render = resultRender(tileJson.dataType, get().range, stats, ownRangeOf(job, job.bands, place), place === RGB, preset);
      const template = resultTileTemplate(href);
      useAppStore.getState().pinDerivedLayer({
        name: resultLayerName(job.title),
        derived: 'result',
        result: {
          jobID,
          expires: job.expires,
          gsd: resultGsd(gsd, width, tileJson.bounds),
          resampled: job.resampled,
          expired: false,
          dataType: tileJson.dataType,
          stats,
          preset,
          ...(several ? { bands: job.bands, band: place, ...(colour ? { colour } : {}) } : {}),
          ...(ownRangeOf(job, job.bands, place)?.percent ? { percent: ownRangeOf(job, job.bands, place)!.percent } : {}),
        },
        overlays: [
          {
            kind: 'raster',
            tileUrl:
              place === RGB
                ? colourTileUrl(template, colour!, render)
                : several
                  ? bandTileUrl(template, place, render)
                  : buildTileUrl(template, render),
            bounds: tileJson.bounds,
            // The tiler names every level, from a tile of the coarsest overview to the finest source's
            // (`result_tiles.py::RESULT_MIN_ZOOM`/`RESULT_MAX_ZOOM`): the result stays on the map at every
            // zoom, and zooming in asks the tiler for the file's pixels instead of stretching a tile.
            minZoom: tileJson.minZoom,
            maxZoom: tileJson.maxZoom,
          },
        ],
        itemIds: [],
        cropToAoi: false,
        date: job.dates,
      });
    },
    // The order behind the details is read from the operators of the dataset, as `openProcessing` does.
    openJobDetails: (jobID) => {
      if (!get().jobs.some((j) => j.jobID === jobID)) return;
      set({ open: true, detailJobID: jobID });
      const datasetId = useAppStore.getState().datasetId;
      if (datasetId) get().ensureDescription(datasetId);
    },
    closeJobDetails: () => set({ detailJobID: null }),
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
          const retired = error instanceof HttpError && error.status === 410 ? error.detail : undefined;
          set({ descriptions: { ...rest, [datasetId]: { state: 'error', message, ...(retired ? { retired } : {}) } } });
        });
    },
    resetDraft: () => {
      abortEstimate();
      startGeneration += 1;
      measures.clear();
      failedMeasures.clear();
      measuring.clear();
      areaAnswers.clear();
      set({ ...EMPTY_DRAFT });
    },
    choosePass: (passKey) => set({ passKey, reviewError: null, startError: null, ...dropReview() }),
    setArea: (area) => set({ area, reviewError: null, startError: null, ...dropReview() }),
    setRunAs: (runAs) => set((s) => (s.fixed?.result ? {} : { runAs, reviewError: null, startError: null, ...dropReview() })),
    addStep: (op, opVersion) => {
      const { datasetId, datasets } = useAppStore.getState();
      const description = datasetId ? get().descriptions[datasetId] : undefined;
      if (description?.state !== 'ready') return;
      const operator = description.info.operators.find((o) => o.op === op && o.opVersion === opVersion);
      if (!operator?.form.supported || get().steps.length >= description.info.maxSteps) return;
      const layer = op === 'mask' ? maskLayerOf(datasets.find((d) => d.id === datasetId)?.collection) : null;
      const { steps, output } = get();
      const view = orderView(selectionState(useAppStore.getState()), get());
      // While a name breaks a rule no step is added (the button says why).
      if (view.nameBlock) return;
      const key = nextStepKey++;
      const values: Record<string, FieldValue> = { ...initialValues(operator.form.fields), ...(layer ? maskStepValues(layer) : {}) };
      // A band math step adds a band under a name of its own, and the band is in the output unless the person leaves it out
      // (adr/0020 §6, §9). A normalize step proposes the last result.
      let added: string | null = null;
      if (op === 'band_math') {
        added = defaultName([...view.dataNames, ...steps.filter(isBandMath).map(resultNameOf)]);
        values.name = added;
      } else if (op === 'normalize' && 'bands' in values) {
        values.bands = view.results.filter((result) => !view.hidden.includes(result.name)).at(-1)?.name ?? '';
      }
      set((s) => ({
        steps: [...s.steps, { key, op, opVersion, values }],
        // The band the panel checked on opening gives way to the first result; one the person chose stays.
        output: added ? [...output.filter((band) => band !== s.lonelyAuto), added] : output,
        lonelyAuto: added ? null : s.lonelyAuto,
        reviewError: null,
        startError: null,
        ...dropReview(),
      }));
    },
    updateStep: (key, name, value) =>
      set((s) =>
        isLocked(s, key)
          ? {}
          : {
              steps: s.steps.map((step) => (step.key === key ? { ...step, values: { ...step.values, [name]: value } } : step)),
              reviewError: null,
              startError: null,
              ...dropReview(),
            },
      ),
    renameResult: (key, name) =>
      set((s) => {
        const step = s.steps.find((candidate) => candidate.key === key);
        if (!step || !isBandMath(step) || isLocked(s, key)) return {};
        const from = resultNameOf(step);
        const view = orderView(selectionState(useAppStore.getState()), s);
        const others = s.steps.filter((candidate) => candidate.key !== key && isBandMath(candidate)).map(resultNameOf);
        // A name that breaks a rule is never taken; one that is the name already changes nothing.
        if (name === from || nameProblem(name, others, view.dataNames) !== null) return {};
        const steps = renameResult(s.steps, key, from, name).map((candidate) =>
          candidate.key === key ? { ...candidate, values: { ...candidate.values, name } } : candidate,
        );
        return {
          steps,
          output: s.output.map((band) => (band === from ? name : band)),
          reviewError: null,
          startError: null,
          ...dropReview(),
        };
      }),
    setNameProblem: (key, reason) =>
      set((s) => {
        if ((s.nameProblems[key] ?? null) === reason || isLocked(s, key)) return {};
        const { [key]: _gone, ...rest } = s.nameProblems;
        return { nameProblems: reason === null ? rest : { ...rest, [key]: reason } };
      }),
    moveStep: (key, direction) =>
      set((s) => {
        const index = s.steps.findIndex((step) => step.key === key);
        const target = index + direction;
        const locked = s.fixed?.result?.locked ?? 0;
        // A locked step stays where it is, and nothing is moved in front of it.
        if (index < locked || target < locked || target >= s.steps.length) return {};
        const steps = [...s.steps];
        [steps[index], steps[target]] = [steps[target], steps[index]];
        return { steps, reviewError: null, startError: null, ...dropReview() };
      }),
    removeStep: (key) =>
      set((s) => {
        if (isLocked(s, key)) return {};
        const step = s.steps.find((candidate) => candidate.key === key);
        const gone = step && isBandMath(step) ? resultNameOf(step) : null;
        const left = s.steps.filter((candidate) => candidate.key !== key);
        const { [key]: _problem, ...problems } = s.nameProblems;
        return {
          nameProblems: problems,
          steps: gone ? dropFromNormalize(left, gone) : left,
          output: gone ? s.output.filter((band) => band !== gone) : s.output,
          reviewError: null,
          startError: null,
          ...dropReview(),
        };
      }),
    checkLonely: (name) =>
      set((s) => (s.output.includes(name) ? {} : { output: [...s.output, name], lonelyAuto: name, reviewError: null, startError: null, ...dropReview() })),
    toggleOutput: (name) =>
      set((s) => ({
        lonelyAuto: null,
        output: s.output.includes(name) ? s.output.filter((band) => band !== name) : [...s.output, name],
        reviewError: null,
        startError: null,
        ...dropReview(),
      })),
    setOutput: (names) => set({ output: [...names], lonelyAuto: null, reviewError: null, startError: null, ...dropReview() }),
    setDtype: (dtype) => set({ dtype: dtype || null, reviewError: null, startError: null, ...dropReview() }),
    setShown: (name) => {
      if (get().shown === name) return;
      set({ shown: name, range: DEFAULT_RANGE, rangeByHand: false, rangeEdited: false });
    },

    // "Load recipe…": the steps and the data type of a `recipe.json` become the draft, on the
    // current selection, which stays as it is. Nothing is changed unless the recipe is taken up
    // as a whole; what cannot be checked here (band names of another dataset) comes back as
    // notes, the server decides on the order.
    loadRecipe: async (text) => {
      // A file of version 1 names assets, version 2 names bands: what an asset's bands are called, the selection knows.
      const current = orderView(selectionState(useAppStore.getState()), get());
      const named = new Map(current.sources.filter((source) => source.names.length > 0).map((source) => [source.asset, source.names]));
      const byKey = keyNames(current.info?.variableSeparator ?? null);
      const read = readRecipe(text, (key) => named.get(key) ?? byKey(key));
      if (!read.ok) return { ok: false, reason: read.reason };
      const { order } = read;
      const datasetId = useAppStore.getState().datasetId;
      if (!datasetId) return { ok: false, reason: 'Pick a dataset first.' };
      if (order.steps.length === 0) return { ok: false, reason: 'This recipe has no steps.' };
      const description = await describe(datasetId);
      if (description?.state !== 'ready') return { ok: false, reason: 'The process description of the dataset could not be loaded.' };
      const { info } = description;
      const { draft, problems, notes } = draftFromOrder(order, info, () => nextStepKey++);
      if (problems.length > 0) return { ok: false, reason: problems.slice(0, 3).join(' ') };
      if (draft.dtype !== null && !info.dtypes.includes(draft.dtype)) notes.push(`Data type ${draft.dtype} is not offered for this dataset.`);
      const dtype = draft.dtype !== null && info.dtypes.includes(draft.dtype) ? draft.dtype : null;
      abortEstimate();
      startGeneration += 1;
      // The steps of a result stay in front of the recipe's.
      const kept = get().steps.slice(0, get().fixed?.result?.locked ?? 0);
      set({ steps: [...kept, ...draft.steps], output: draft.bands, nameProblems: {}, dtype, reviewAsked: false, estimate: null, batch: null, reviewing: false, reviewError: null, startError: null, batchStartRefusals: null });
      const view = orderView(selectionState(useAppStore.getState()), get());
      return { ok: true, notes: [...notes, ...missingBands(draft, view)], ...(read.converted ? { converted: true } : {}) };
    },

    // A permalink (M4-19e): the order and the view come back as they were shared. Unlike "Load recipe…"
    // this replaces the selection: the dataset, the scenes (one by one if the results lack them), the
    // AOI and the steps. Several groups select all their scenes and the user picks the pass; an order
    // without an AOI keeps the AOI on the map and covers the whole scenes. Nothing is changed unless
    // the order is taken up as a whole.
    restoreOrder: async (order, view, options) => {
      const range = view.range && { vmin: String(view.range.vmin), vmax: String(view.range.vmax), colormap: view.range.colormap };
      const taken = await takeOrder(order, 'this link', () => ({
        ...(range ? { range, rangeDraft: range, rangeByHand: true } : {}),
      }));
      if (!taken.ok) return taken;
      useAppStore.setState({ flyToView: { center: view.center, zoom: view.zoom } });
      useAppStore.getState().showSharedLook(view);
      return { ok: true, notes: taken.notes, ...(options?.converted ? { converted: true } : {}) };
    },

    // ⚙ of a result layer: the order of its job, the steps locked, on the scenes and the area of the job. The job's own output
    // is the start of the output, and what the steps add comes in as always. A reason it cannot is told as an error.
    extendResult: async (layerId) => {
      const app = useAppStore.getState();
      const layer = app.layers.find((l) => l.id === layerId);
      const job = get().jobs.find((j) => j.jobID === layer?.result?.jobID);
      const block = layer ? layerProcessBlock(layer, app.datasets, get().jobs) : 'This layer is gone.';
      if (!layer?.result || block !== null || !job?.order) return void useAppStore.setState({ error: block ?? NO_COPY_TEXT });
      const { order } = job;
      const groupId = job.groupId ?? get().batches.find((b) => b.id === job.batchId)?.groupId ?? null;
      const taken = await takeOrder(order, 'this result', (draft, notes) => ({
        // The area of the result is "Whole scene" here; "AOI only" is another AOI inside it. Its bands are in the list of the output,
        // none of them checked, as the bands of a scene are (Otto, 2026-10-31).
        area: 'scene',
        output: [],
        fixed: {
          itemIds: draft.groups.flat(),
          aoi: draft.aoi,
          result: {
            title: job.title ?? job.titleDefault ?? '',
            groupId,
            locked: draft.steps.length,
            bands: [...draft.bands],
            notes,
          },
        },
      }));
      if (!taken.ok) useAppStore.setState({ error: taken.reason });
      // The preview lies with the entry "Results": above the result, which it would else be hidden by.
      else useAppStore.getState().resultsToTop();
    },

    // A layer that shows an index is processed as the index alone: the panel opens on the order that makes it (one Band math step,
    // locked) with that band as the whole stock of bands, as it opens on the result of a job (`extendResult`), so that the raw bands of
    // the scenes are not offered besides it (Otto, 1.11.2026). The first pass of the layer is the pass of the order.
    extendIndexLayer: async (layerId) => {
      const app = useAppStore.getState();
      const layer = app.layers.find((l) => l.id === layerId);
      const preset = layer && indexOfLayer(layer, app.datasets);
      const dataset = app.datasets.find((d) => d.id === layer?.restore.datasetId);
      if (!layer || !preset || !dataset) return;
      const { restore } = layer;
      useAppStore.getState().activateLayerContext(layerId);
      await openIndexPanel({
        dataset,
        preset,
        groups: restore.groupItemIds.length > 0 ? restore.groupItemIds : [restore.itemIds],
        aoi: restore.cropToAoi && isArea(restore.aoi) ? restore.aoi : null,
        title: layer.name,
        whose: 'this layer',
      });
    },

    reviewOrder: async () => {
      const view = orderView(useAppStore.getState(), get());
      const order = view.built?.order;
      set({ reviewAsked: true });
      if (!order || !view.key || get().starting || view.nameBlock || crsBlockReason(get().steps, get().crs)) return;
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
      if (!order || !view.key || s.starting || view.nameBlock || crsBlockReason(s.steps, s.crs)) return;
      if (view.runAs !== 'one') {
        await startBatch(view);
        return;
      }
      if (s.estimate?.key !== view.key) return;
      const title = titleOf(view);
      const own = startLook(view, s);
      const mine = ++startGeneration;
      set({ starting: true, startError: null });
      try {
        const status = await placeJob(order, {
          // A fixed area is the entry's, not the map's, and the map's provenance is not its own; another AOI on a result is the map's where nothing was cut off.
          aoiProvenance: s.fixed && !(view.inner && view.aoi === useAppStore.getState().aoi) ? undefined : aoiProvenanceFor(order, useAppStore.getState().aoi),
        });
        // One estimate, one job: a second identical job needs its own review.
        if (mine === startGeneration) set({ starting: false, estimate: null });
        addJob({ jobID: status.jobID, expires: status.expires, status, title, ...own, ...groupOf(), order: orderCopy(order) });
      } catch (error) {
        if (mine === startGeneration) set({ starting: false, startError: refusalOf(error, view.key, s.steps) });
      }
    },

    // A job the download dialog starts (a mosaic, M4-12b; an export, M4-11b-2):
    // the order is built there, with no draft and no review; a refusal comes back
    // as text, the job as a row in the list.
    placeOrder: async (order, options) => {
      try {
        const status = await placeJob(order, options && { aoiProvenance: options.aoiProvenance });
        addJob({ jobID: status.jobID, expires: status.expires, status, title: options?.title ?? null, order: orderCopy(order) });
        return { jobID: status.jobID };
      } catch (error) {
        return { message: refusalMessage(error) };
      }
    },

    cancelJob: async (jobID) => {
      const job = get().jobs.find((j) => j.jobID === jobID);
      if (!job || job.cancelling || job.phase !== 'active') return;
      updateJob(jobID, { cancelling: true, error: null });
      // `DELETE` also discards the result of a finished job, so a job that ended since its last status must
      // not get one: the state is asked for afresh, within a few seconds, and only a job that waits or runs
      // is dismissed. Any other answer is shown as it is.
      try {
        const fresh = await fetchJob(jobID, AbortSignal.timeout(CANCEL_CHECK_MS));
        if (fresh.status !== 'accepted' && fresh.status !== 'running') {
          trackers.get(jobID)?.();
          trackers.delete(jobID);
          updateJob(jobID, { cancelling: false });
          applyStatus(jobID, fresh);
          return;
        }
      } catch (error) {
        const gone = error instanceof HttpError && error.status === 404;
        if (gone) {
          trackers.get(jobID)?.();
          trackers.delete(jobID);
        }
        updateJob(jobID, {
          cancelling: false,
          ...(gone ? {} : { error: 'The state of the job could not be checked, so it was not cancelled. Try again.' }),
        });
        if (gone) forget(jobID);
        return;
      }
      try {
        await dismissJob(jobID);
        trackers.get(jobID)?.();
        trackers.delete(jobID);
        updateJob(jobID, { cancelling: false, phase: 'dismissed' });
      } catch (error) {
        if (error instanceof HttpError && error.status === 404) {
          trackers.get(jobID)?.();
          trackers.delete(jobID);
          updateJob(jobID, { cancelling: false });
          forget(jobID);
        } else {
          updateJob(jobID, { cancelling: false, error: error instanceof Error ? error.message : String(error) });
        }
      }
    },
    setJobRange: (jobID, range, band) => {
      const job = get().jobs.find((j) => j.jobID === jobID);
      if (!job) return;
      if (band === undefined) {
        updateJob(jobID, { range });
      } else {
        const { [band]: _dropped, ...others } = job.bandRanges;
        updateJob(jobID, { bandRanges: range ? { ...others, [band]: range } : others });
      }
      persist();
    },
    chooseResultBand: (layerId, place) => {
      const app = useAppStore.getState();
      const layer = app.layers.find((l) => l.id === layerId && l.derived === 'result');
      const info = layer?.result;
      const colour = place === RGB ? info?.colour : undefined;
      const band = place === RGB ? null : info?.bands?.[place];
      const job = info && get().jobs.find((j) => j.jobID === info.jobID);
      if (!layer || !info || !info.bands || !job || info.band === place) return;
      if (place === RGB ? !colour : !band) return;
      const stats = colour ? colourStats(info.bands, colour) : band!.stats;
      const dataset = app.datasets.find((d) => d.id === job.order?.inputs[0]?.dataset);
      const preset = colour ? null : presetOfResultBand(band ?? undefined, indexPresetsOf(dataset?.collection));
      const render = resultRender(info.dataType, get().range, stats, ownRangeOf(job, info.bands, place), colour !== undefined, preset);
      useAppStore.setState({
        layers: app.layers.map((l) => {
          if (l.id !== layerId || !l.result) return l;
          // What was applied and not saved belongs to the band it was applied to: it goes with it.
          const { savedTileUrl: _unsaved, savedPercent: _unsavedPercent, percent: _percent, ...kept } = l.result;
          let first = true;
          const overlays = l.overlays.map((o) => {
            if (o.kind !== 'raster' || !first) return o;
            first = false;
            return { ...o, tileUrl: colour ? colourTileUrl(o.tileUrl, colour, render) : bandTileUrl(o.tileUrl, place as number, render) };
          });
          const typed = ownRangeOf(job, info.bands!, place)?.percent;
          return { ...l, overlays, result: { ...kept, band: place, stats, preset, ...(typed ? { percent: typed } : {}) } };
        }),
      });
    },
    renameJob: (jobID, title) => {
      const name = title.trim().slice(0, MAX_TITLE_LENGTH);
      set((s) => ({ jobs: s.jobs.map((j) => (j.jobID === jobID ? { ...j, title: name || j.titleDefault } : j)) }));
      persist();
    },
    // The parts that still carry the batch's own title follow it; one named by hand keeps its name.
    renameBatch: (batchId, title) => {
      const name = title.trim().slice(0, MAX_TITLE_LENGTH);
      const before = get().batches.find((b) => b.id === batchId);
      if (!before) return;
      const next = name || before.titleDefault;
      set((s) => ({
        batches: s.batches.map((b) => (b.id === batchId ? { ...b, title: next } : b)),
        jobs: s.jobs.map((j) => (j.batchId === batchId && j.title === before.title ? { ...j, title: next } : j)),
      }));
      persist();
    },
    setArchived: (target, archived) => {
      set((s) => ({
        jobs: s.jobs.map((j) => (inTarget(j, target) ? { ...j, archived } : j)),
        batches: s.batches.map((b) => ('batchId' in target && b.id === target.batchId ? { ...b, archived } : b)),
      }));
      persist();
    },
    createGroup: (title) => {
      const name = title.trim().slice(0, MAX_NAME_LENGTH);
      if (!name) return null;
      const id = newId();
      set((s) => ({ groups: [...s.groups, { id, name }] }));
      persist();
      return id;
    },
    renameGroup: (groupId, title) => {
      const name = title.trim().slice(0, MAX_NAME_LENGTH);
      if (!name) return;
      set((s) => ({ groups: s.groups.map((g) => (g.id === groupId ? { ...g, name } : g)) }));
      persist();
    },
    removeGroup: (groupId) => {
      const s = get();
      if (s.jobs.some((j) => j.groupId === groupId) || s.batches.some((b) => b.groupId === groupId)) return false;
      set({ groups: s.groups.filter((g) => g.id !== groupId) });
      persist([groupId]);
      return true;
    },
    // A part follows its batch; the batch's group is the one the manager shows.
    moveToGroup: (target, groupId) => {
      if (groupId !== null && !get().groups.some((g) => g.id === groupId)) return;
      set((s) => ({
        jobs: s.jobs.map((j) => (inTarget(j, target) ? { ...j, groupId } : j)),
        batches: s.batches.map((b) => ('batchId' in target && b.id === target.batchId ? { ...b, groupId } : b)),
      }));
      persist();
    },
    cancelBatch: async (batchId) => {
      if (cancellingBatches.has(batchId)) return;
      cancellingBatches.add(batchId);
      try {
        const parts = get().jobs.filter((j) => j.batchId === batchId && j.phase === 'active');
        for (const part of parts) await get().cancelJob(part.jobID);
      } finally {
        cancellingBatches.delete(batchId);
      }
    },
    retryJob: async (jobID) => {
      const job = get().jobs.find((j) => j.jobID === jobID);
      if (!job?.order || job.retrying || !canRetry(job, Date.now(), orderRetired(job, get().descriptions))) return;
      updateJob(jobID, { retrying: true, retryError: null });
      try {
        // The order as it was kept: the server may know its result already (a cache hit).
        const status = await placeJob(job.order);
        addJob(
          {
            jobID: status.jobID,
            expires: status.expires,
            status,
            title: job.title,
            titleDefault: job.titleDefault,
            createdAt: job.createdAt,
            groupId: job.groupId,
            batchId: job.batchId,
            part: job.part,
            range: job.range,
            bandRanges: job.bandRanges,
            shownBand: job.shownBand,
            dates: job.dates,
            order: job.order,
          },
          jobID,
        );
      } catch (error) {
        // `410` with a reason: the dataset has left, so the order cannot be sent again and "Run again" goes.
        const retired = error instanceof HttpError && error.status === 410 && error.detail !== undefined;
        updateJob(jobID, { retrying: false, retryError: refusalMessage(error), ...(retired ? { retryRefused: true } : {}) });
      }
    },
    retryBatch: async (batchId) => {
      if (retryingBatches.has(batchId)) return;
      retryingBatches.add(batchId);
      try {
        const now = Date.now();
        const { jobs, descriptions } = get();
        const parts = retryableParts(
          jobs.filter((j) => j.batchId === batchId && !j.superseded),
          now,
          (part) => orderRetired(part, descriptions),
        );
        for (const part of parts) await get().retryJob(part.jobID);
      } finally {
        retryingBatches.delete(batchId);
      }
    },
    deleteTarget: async (target) => {
      const now = Date.now();
      const parts = 'jobID' in target ? get().jobs.filter((j) => j.jobID === target.jobID) : get().jobs.filter((j) => j.batchId === target.batchId);
      // A batch with a part that waits or runs is cancelled, not deleted.
      const due = 'jobID' in target ? parts.filter((j) => canDelete(j, now)) : deletableParts(parts, now);
      await Promise.all(due.map((job) => deleteOne(job.jobID)));
    },
    restoreTarget: async (target) => {
      const now = Date.now();
      const parts = get().jobs.filter((j) => inTarget(j, target) && !j.deleting && canRestore(j, now));
      await Promise.all(parts.map((job) => restoreOne(job.jobID)));
    },
    resumeJobs: () => {
      const { shelf, state, locked } = loadShelf();
      shelfLocked = locked;
      const now = Date.now();
      const known = new Set(get().jobs.map((j) => j.jobID));
      // Newest first, as the list is made when jobs are placed.
      const entries = shelf.jobs
        .filter((j) => !known.has(j.jobID))
        .sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt))
        .map((j) => jobEntry(j, null, now));
      set((s) => ({
        shelf: state,
        jobs: [...entries, ...s.jobs],
        batches: withOthers(shelf.batches, s.batches),
        groups: withOthers(shelf.groups, s.groups),
      }));
      // An archived job is not followed until its row is shown (`followJob`).
      for (const entry of entries) if (entry.phase === 'active' && !entry.archived) follow(entry.jobID);
      if (!storageListening && typeof window !== 'undefined') {
        storageListening = true;
        window.addEventListener('storage', (event) => {
          // A value removed by another tab (the browser's data cleared) is not news: this tab still holds its jobs.
          if (event.key === SHELF_KEY && event.newValue !== null) takeShelf();
        });
      }
    },
    followJob: (jobID) => {
      const job = get().jobs.find((j) => j.jobID === jobID);
      if (job && job.phase === 'active' && !trackers.has(jobID) && Date.parse(job.expires) > Date.now()) follow(jobID);
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
function previewReadOf(view: OrderView, plan: Extract<PreviewPlan, { state: 'ready' }>, pick: string | null): PreviewRead {
  return previewRead({
    output: view.output,
    dataNames: view.dataNames,
    sources: view.sources,
    maskAsset: view.maskAsset?.asset ?? null,
    all: view.assets,
    steps: plan.steps.map(({ step }) => step),
    pick,
    trueColor: view.trueColor,
  });
}

// The day of the scenes an order reads, among the scenes the page knows now (`layerDate.ts`); `null` where they are not known
// or have no instant.
function datesOfOrder(order: Order): string | null {
  return datesOfIds(order.inputs.flatMap((input) => input.groups.flat()), knownItems(useAppStore.getState()));
}

// What a job keeps of the preview it was started from (NM4-43e PR 2): the band the map showed, which the layer of a result of
// several bands starts with, and the range set by hand, which was set for that band. A result of one band keeps the
// range as the job's; of several, as the range of that band by its name.
function startLook(
  view: OrderView,
  p: ProcessingState,
): { range: PreviewRange | null; bandRanges: Record<string, PreviewRange>; shownBand: string | null } {
  const own = handRangeOf(p);
  if (view.output.length <= 1) return { range: own, bandRanges: {}, shownBand: null };
  const plan = planPreview(p.steps, view.info);
  const band = plan.state === 'ready' ? previewReadOf(view, plan, p.shown).band : null;
  // The colour picture has no colormap, whatever the fields of the range hold.
  const kept = own && band === RGB ? { ...own, colormap: '' } : own;
  return { range: null, bandRanges: kept && band !== null ? { [band]: kept } : {}, shownBand: band };
}

function wantedPreview(limit?: number): PreviewSpec | null {
  const p = useProcessingStore.getState();
  // The details of a job are not the order: the draft draws nothing while they are shown.
  if (!p.open || p.detailJobID) return null;
  const app = useAppStore.getState();
  const view = orderView(app, p);
  if (!view.info || !view.pass || view.outside || processBlockReason(view.dataset, sceneCountOf(app, p)) !== null) return null;
  const full = planPreview(p.steps, view.info);
  if (full.state !== 'ready') return null;
  const plan = limit === undefined ? full : shortenPlan(full, limit);
  if (plan === null) return null;
  const jobs = view.parts.map((part) => part.unit.items);
  const order = view.parts[0]?.order ?? null;
  // The map reads what the band it shows needs, not all that the order reads (adr/0020 §4, §10).
  const read = previewReadOf(view, plan, p.shown);
  const args = {
    dataset: view.dataset,
    items: view.pass.items,
    assets: read.assets,
    info: view.info,
    plan,
    area: view.area,
    jobs,
    answers: mosaicAnswers,
    order,
    band: read.band,
    bands: read.bands,
    named: read.choices.length > 1,
  };
  const spec = previewSpec({ ...args, range: p.range, ...(view.inner && view.aoi ? { clipAoi: view.aoi } : {}) });
  if (spec === null) return null;
  const range = drawnRange(p, spec);
  return range === p.range ? spec : previewSpec({ ...args, range });
}

// The range the user applied by hand, or `null`: the one a job keeps for its result (M4-32b), and the one the
// preview holds against a measure — the same switch, so that both are drawn alike (Otto, 24.10.2026). A range
// equal to the start range counts once the user applied it.
export function handRangeOf(p: Pick<ProcessingState, 'range' | 'rangeByHand'>): PreviewRange | null {
  return p.rangeByHand ? p.range : null;
}

// The range the preview is drawn with (M4-19c): the one the user applied; else the one the measure of this very
// preview calls for (the rule of a result's, `scaleOf`); else the start range. Between the two: the preset of an index (NM4-14, D2).
function drawnRange(p: Pick<ProcessingState, 'range' | 'rangeByHand' | 'measure'>, spec: Pick<PreviewSpec, 'measure' | 'preset'>): PreviewRange {
  if (handRangeOf(p)) return p.range;
  if (spec.preset) return spec.preset;
  return (p.measure?.key === spec.measure ? measuredRange(p.measure) : null) ?? p.range;
}

// One measure per state of the preview, which is the steps over the first scene (over the AOI, for "AOI only" with
// a complete order, NM4-19): remembered, and a failed one is not asked again before "Auto stretch" (so a typed
// expression asks for no measure per key, nor a refusal twice). The key of an area measure is the text of the order,
// which carries the AOI: it lives here in memory and goes into no URL, storage, log or message.
const MEASURES_KEPT = 50;
const measures = new Map<string, PreviewMeasure>();
const failedMeasures = new Set<string>();
const measuring = new Map<string, Promise<PreviewMeasure | null>>();

// The answer of the tiler for the statistics of an order, once per order: it holds every band, so that a change of the
// band shown asks nothing new. Like the keys of the measures, the text of the order lives here in memory only.
const AREA_ANSWERS_KEPT = 8;
const areaAnswers = new Map<string, Promise<AreaStatistics>>();

function areaStatisticsOf({ datasetId, order }: { datasetId: string; order: Order }): Promise<AreaStatistics> {
  const key = canonicalJson(order);
  let answer = areaAnswers.get(key);
  if (!answer) {
    if (areaAnswers.size >= AREA_ANSWERS_KEPT) areaAnswers.delete(areaAnswers.keys().next().value!);
    answer = postAreaStatistics(datasetId, order);
    areaAnswers.set(key, answer);
    // A failed question is asked again at the next measure.
    answer.catch(() => {
      if (areaAnswers.get(key) === answer) areaAnswers.delete(key);
    });
  }
  return answer;
}

// The measure over the AOI; where the tiler does not give it (an order it refuses, a source that fails, a network
// that fails, an answer the panel cannot read) the first whole scene as before, marked as the fall-back (KE1).
async function measureOver(spec: PreviewSpec): Promise<PreviewMeasure> {
  if (spec.areaOrder) {
    try {
      const answer = await areaStatisticsOf(spec.areaOrder);
      // The answer holds every band of the order; the colour scale is the one of the band the map shows.
      const bands = spec.bands === null ? answer.bands : answer.bands.filter((band) => spec.bands!.includes(band.name));
      if (bands.length === 0) throw new Error('the statistics do not name the band');
      return areaMeasureOf(spec.measure, { ...answer, bands }, spec.expression);
    } catch (error) {
      // The status alone: an order the panel built wrongly (422) must not pass unnoticed, but the text of an answer and
      // the order carry what was sent, the AOI among it.
      console.warn(`area statistics: ${error instanceof HttpError ? `status ${error.status}` : 'no readable answer'}; measuring the first whole scene`);
      return measureOf(spec.measure, await fetchStatisticsAt(spec.sceneMeasure), spec.expression, 'fallback');
    }
  }
  return measureOf(spec.measure, await fetchStatisticsAt(spec.sceneMeasure), spec.expression);
}

function measureFor(spec: PreviewSpec): Promise<PreviewMeasure | null> {
  const known = measures.get(spec.measure);
  if (known) return Promise.resolve(known);
  if (failedMeasures.has(spec.measure)) return Promise.resolve(null);
  let request = measuring.get(spec.measure);
  if (!request) {
    request = measureOver(spec)
      .then((measure) => {
        if (measures.size >= MEASURES_KEPT) measures.delete(measures.keys().next().value!);
        measures.set(spec.measure, measure);
        return measure;
      })
      .catch(() => {
        failedMeasures.add(spec.measure);
        return null;
      })
      .finally(() => {
        if (measuring.get(spec.measure) === request) measuring.delete(spec.measure);
      });
    measuring.set(spec.measure, request);
  }
  return request;
}

// The longest the picture waits for the measure (Otto, 24.10.2026, proposal 5 s).
export const MEASURE_WAIT_MS = 5000;
const TOO_LATE = Symbol('too late');

// `request`'s answer, or `TOO_LATE` once `ms` have passed; the request goes on either way.
function within<T>(request: Promise<T>, ms: number): Promise<T | typeof TOO_LATE> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(TOO_LATE), ms);
    void request.then((value) => {
      clearTimeout(timer);
      resolve(value);
    });
  });
}

// Whether `spec` is still what the panel asks for: no newer settle, and no change of the draft inside the 400 ms
// before one starts (`settleRun` rises only then), so that the measure of an older formula is not taken for the new one.
function stillWanted(run: number, spec: PreviewSpec | null, limit: number | undefined): boolean {
  return run === settleRun && spec !== null && wantedPreview(limit)?.measure === spec.measure;
}

// The fields of the range say what the picture is drawn with: where no range of the user's holds and the user is not typing
// in them, that is the range of the measure of this very picture, else the start range. A picture drawn while its measure
// is still on its way is drawn with the start range, and the fields must not keep the range of the formula before
// (review of #250).
function fieldsShow(spec: PreviewSpec | null): Partial<Pick<ProcessingState, 'rangeDraft'>> {
  const p = useProcessingStore.getState();
  return spec && !p.rangeByHand && !p.rangeEdited ? { rangeDraft: drawnRange(p, spec) } : {};
}

// Takes a measure into the state: with it the unit, and — where no range of the user's holds — the range it calls
// for in the fields, unless the user is typing in them. Without one the panel says so.
function adoptMeasure(measure: PreviewMeasure | null, preset: PreviewRange | null): void {
  const p = useProcessingStore.getState();
  const hand = p.rangeByHand;
  useProcessingStore.setState({
    measure,
    rangeNote: hand || measure !== null || preset !== null ? null : NO_MEASURE,
    ...(!hand && !p.rangeEdited ? { rangeDraft: preset ?? measuredRange(measure) ?? p.range } : {}),
  });
}

// The key of the whole chain the shown preview comes from: a preview cut by the tiler
// differs from it, and must not be asked for again on every change that leaves it alone.
let settledKey: string | null = null;
// Together with what the range is measured on: for "AOI only" that is the order, whose AOI and output type are no
// part of the tiles (`PreviewSpec.key`), so a change of either is a new measure over the same picture.
const settledOf = (spec: PreviewSpec): string => `${spec.key}\n${spec.measure}`;
let settleRun = 0;
// What the tiler said of a chain, taken (`null`) or refused, until there is nothing to show: asking again for a new
// range would give the same answer. Bounded like the measures; a question that failed on the way is not kept.
const PROBES_KEPT = 50;
const probed = new Map<string, RefusedStep | null>();

function rememberProbe(url: string, refused: RefusedStep | null): void {
  if (probed.size >= PROBES_KEPT) probed.delete(probed.keys().next().value!);
  probed.set(url, refused);
}

// What the tiler said of each mosaic of a preview (NM4-04), by its TileJSON: the order of its scenes, or that the
// scenes are drawn one by one. A failing source or network counts as that too, until the preview goes away.
// An answer that failed on the way (`retry`) is dropped with the next change (`refreshPreview`); one still on its way is
// not asked twice, and one that comes after the preview went away is not kept.
const mosaicAnswers = new Map<string, MosaicAnswer>();
const askingMosaics = new Map<string, Promise<void>>();
let mosaicEpoch = 0;

async function askMosaics(spec: PreviewSpec | null): Promise<void> {
  await Promise.all(
    (spec?.mosaics ?? [])
      .filter((mosaic) => !mosaicAnswers.has(mosaic.probe))
      .map(({ probe }) => {
        let request = askingMosaics.get(probe);
        if (!request) {
          const epoch = mosaicEpoch;
          request = probeMosaic(probe)
            .then((answer) => {
              if (epoch !== mosaicEpoch) return;
              if (mosaicAnswers.size >= PROBES_KEPT) mosaicAnswers.delete(mosaicAnswers.keys().next().value!);
              mosaicAnswers.set(probe, answer);
            })
            .finally(() => askingMosaics.delete(probe));
          askingMosaics.set(probe, request);
        }
        return request;
      }),
  );
}

// The step of the chain the tiler refuses, or `null`. The mosaics are asked first: one of them that takes the chain
// is answer enough. If none does, the scenes are drawn one by one and the first of them is asked, as ever.
async function chainRefusal(wanted: PreviewSpec): Promise<RefusedStep | null> {
  let spec: PreviewSpec | null = wanted;
  if (spec.mosaics.length > 0) {
    await askMosaics(spec);
    const answers = spec.mosaics.map((mosaic) => mosaicAnswers.get(mosaic.probe));
    const refused = answers.find((answer) => answer?.state === 'refused');
    if (refused?.state === 'refused') return refused.refused;
    if (answers.some((answer) => answer?.state === 'taken')) return null;
    spec = wantedPreview();
  }
  if (!spec) return null;
  let refused = probed.get(spec.probe);
  if (refused === undefined) {
    const answer = await probeChain(spec.probe, spec.stepCount);
    if (answer.state !== 'none') rememberProbe(spec.probe, answer.state === 'refused' ? answer.refused : null);
    refused = answer.state === 'refused' ? answer.refused : null;
  }
  return refused;
}

// Shows `wanted`, or — for a chain the tiler refuses at step k — its first k − 1 steps and the reason; for a
// refused single step nothing but the reason. Statistics and tiles of a refused chain are not asked.
async function settle(wanted: PreviewSpec): Promise<void> {
  const run = ++settleRun;
  useProcessingStore.setState({ previewSettling: true });
  try {
    await settleAs(run, wanted);
  } finally {
    // A newer run has its own say; a preview that went away cleared it already.
    if (run === settleRun && useProcessingStore.getState().previewSettling) useProcessingStore.setState({ previewSettling: false });
  }
}

async function settleAs(run: number, wanted: PreviewSpec): Promise<void> {
  const refused = await chainRefusal(wanted);
  if (run !== settleRun) return;
  // The steps the tiler takes: all of them, or the ones before the step it refuses.
  const cut = refused && refused.step < wanted.stepCount ? refused : null;
  const limit = cut ? cut.step : undefined;
  const note = cut ? refusedNote(cut.step, wanted.stepCount, cut) : null;
  // The order of a mosaic does not depend on the steps, but the tiler is asked about the chain that is drawn.
  if (cut) {
    await askMosaics(wantedPreview(limit));
    if (run !== settleRun) return;
  }
  const hand = useProcessingStore.getState().rangeByHand;
  let spec = wantedPreview(limit);
  // Without a range of the user's the picture waits for the measure, so that it is drawn once and not twice,
  // but not longer than `MEASURE_WAIT_MS`: then it is drawn with the start range.
  let late: Promise<PreviewMeasure | null> | null = null;
  if (spec && !hand) {
    const request = measureFor(spec);
    const measure = await within(request, MEASURE_WAIT_MS);
    if (!stillWanted(run, spec, limit)) return;
    if (measure === TOO_LATE) {
      late = request;
    } else {
      adoptMeasure(measure, spec.preset);
      spec = wantedPreview(limit);
    }
  }
  settledKey = settledOf(wantedPreview() ?? wanted);
  useProcessingStore.setState({ preview: spec, previewNote: note, previewSettling: false, ...fieldsShow(spec) });
  // A measure that comes after all is taken in with one redraw, and only if it changes the picture.
  if (late) {
    const measure = await late;
    if (!stillWanted(run, spec, limit)) return;
    adoptMeasure(measure, spec?.preset ?? null);
    const again = wantedPreview(limit);
    if (again && again.key !== spec?.key) {
      const now = wantedPreview();
      if (now) settledKey = settledOf(now);
      useProcessingStore.setState({ preview: again });
    }
  }
  // With one, the measure is for the unit alone, and the picture does not wait for it.
  if (spec && hand) {
    const measure = await measureFor(spec);
    if (stillWanted(run, spec, limit)) adoptMeasure(measure, spec.preset);
  }
}

// A preview that goes away goes at once; a new or changed one 400 ms after the
// last change, so typing an expression asks for no tile per key.
function refreshPreview(): void {
  clearTimeout(previewTimer);
  // A mosaic whose question failed on the way is asked again with the next change.
  for (const [probe, answer] of mosaicAnswers) if (answer.state === 'scenes' && answer.retry) mosaicAnswers.delete(probe);
  const wanted = wantedPreview();
  const state = useProcessingStore.getState();
  if (wanted !== null && settledOf(wanted) === settledKey && (state.preview !== null || state.previewNote !== null)) return;
  if (wanted === null) {
    settleRun++;
    settledKey = null;
    probed.clear();
    mosaicAnswers.clear();
    askingMosaics.clear();
    mosaicEpoch++;
    if (state.preview !== null || state.previewNote !== null || state.previewSettling) {
      useProcessingStore.setState({ preview: null, previewNote: null, previewSettling: false });
    }
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
    s.detailJobID !== prev.detailJobID ||
    s.descriptions !== prev.descriptions ||
    s.passKey !== prev.passKey ||
    s.area !== prev.area ||
    s.runAs !== prev.runAs ||
    s.steps !== prev.steps ||
    s.output !== prev.output ||
    s.dtype !== prev.dtype ||
    s.shown !== prev.shown ||
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
