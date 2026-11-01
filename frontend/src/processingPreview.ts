// The preview of the steps on the map (M4-13c-2, plan §3.3): which steps can be
// shown as tiles, the tile URLs of the scenes of an order, when the map says
// "Preview", and the layer a preview becomes. Pure functions; the state lives in
// `processingStore.ts`.

import { clipTileUrl } from './aoiClip';
import {
  buildMosaicOperatorTileJsonUrl,
  buildMosaicOperatorTileTemplate,
  buildOperatorStatisticsUrl,
  buildOperatorTileJsonUrl,
  buildOperatorTileTemplate,
  MOSAIC_TILEJSON_TIMEOUT_MS,
  type AreaStatistics,
  type BandStatistics,
  type ShownBands,
} from './api';
import type { DatasetOption } from './datasets';
import { unionBbox } from './geoUtils';
import type { LayerOverlay } from './layers';
import { buildTileUrl } from './mapLayers';
import {
  MAX_MOSAIC_OPERATOR_ASSETS,
  MAX_MOSAIC_REQUEST_BYTES,
  MAX_MOSAIC_SCENES,
  MIN_MOSAIC_SCENES,
  MIN_MOSAIC_ZOOM,
  mosaicRequestBytes,
} from './mosaic';
import { MOSAIC_TILE_SIZE, TILE_SIZE, tileLevelAhead, tileMetres } from './tileSize';
import { canonicalJson, type Order } from './processing';
import { indexPresetsOf, presetFor, presetRange } from './indexPresets';
import { assetsCarrying, bandLabel, isBandMath, resultNameOf, resultsOf, RGB, startBand } from './processingBands';
import {
  bandsOf,
  namesInExpression,
  shownUnit,
  type Area,
  type BandSource,
  type DraftStep,
  type Operator,
  type ProcessInfo,
} from './processingOrder';
import type { Percent } from './percentRange';
import { INDEX_COLORMAP, INDEX_RANGE, scaleOf, statsFrom, type BandStats, type ResultStats } from './render';
import { NORMALIZE_VERSION, TILE_VERSION, isStatistical, type Measured } from './normalizeMethods';
import { paramsFrom, type Field } from './schemaForm';
import type { Bbox, StacItem } from './types';

// As many scenes as the full-resolution view draws (`mapLayers.ts`).
export const MAX_PREVIEW_SCENES = 40;
// The tile route takes at most this many assets with an operator (`api/tiler.py`).
export const MAX_PREVIEW_ASSETS = 16;
// And at most this many steps in a chain (`api/tiler.py::MAX_OPERATOR_STEPS`).
export const MAX_PREVIEW_STEPS = 4;

// Why the first step has no picture, one text for each reason: it must say what is true of that
// step (a mask runs as a tile, and was once called job-only for want of a form).
export const NO_PREVIEW = 'No preview: the first step runs only as a job.';
export const NO_PREVIEW_FORM = 'No preview: this panel has no form for the first step yet.';
export const NO_PREVIEW_UNLISTED = 'No preview: the first step is not available for this dataset.';

// The tooltip of "Preview" while a pass the job mosaics is drawn scene by scene: the tiler would not take its mosaic.
export const SCENE_PREVIEW_HINT = 'Preview per scene – may differ from the job where scenes overlap';

// The tooltip of "Preview" when the range of "AOI only" is not the one the job counts (NM4-19): the measure fell back
// to the first whole scene, or the tiler read the AOI on a coarser raster (a window above 2048² pixels).
export const SCENE_MEASURE_HINT = 'Range measured over the first whole scene';
export const COARSE_MEASURE_HINT = 'Range measured on a coarser read; the result may differ';

// --- range and colormap ------------------------------------------------------

// What the preview is drawn with (F3 (1)): the range and colormap of an index such as NDVI to begin with,
// by hand once the user applies one, and the measure of the steps (M4-19c, `measureOf`) while they have not.
export interface PreviewRange {
  vmin: string;
  vmax: string;
  // `''`: no colormap.
  colormap: string;
  // What the range was typed as where it was typed in percentiles (NM4-65 part 4): `vmin`/`vmax` hold the values they gave.
  percent?: Percent;
}

export const DEFAULT_RANGE: PreviewRange = {
  vmin: String(INDEX_RANGE[0]),
  vmax: String(INDEX_RANGE[1]),
  colormap: INDEX_COLORMAP,
};

export function rescaleOf(range: PreviewRange): { rescale: string } | { problem: string } {
  const number = (text: string) => (text.trim() === '' ? NaN : Number(text));
  const low = number(range.vmin);
  const high = number(range.vmax);
  if (!Number.isFinite(low) || !Number.isFinite(high)) return { problem: 'Enter a number for both ends of the range.' };
  if (low >= high) return { problem: 'The lower end of the range must be below the upper end.' };
  return { rescale: `${low},${high}` };
}

// --- the planner (adr/0014 §6.1) ---------------------------------------------

// One step the map can draw: the draft, its operator and its complete parameters.
export interface PlannedStep {
  step: DraftStep;
  operator: Operator;
  params: Record<string, unknown>;
  // The version the tile takes: `normalize` of version 4 (job only) goes to the tile as version 3 (NM4-71).
  version: number;
}

export type PreviewPlan =
  | { state: 'off'; reason: string | null }
  | {
      state: 'ready';
      // The longest start of the steps that runs as tiles, in order, at least one.
      steps: PlannedStep[];
      // Steps after that start: the map shows the start, the job runs them all.
      further: boolean;
    };

// The operator of a step that can be a tile and the fields of its form, or the text why
// there is no picture: the operator is not on the dataset's list, it does not run as a tile
// (`T1`, `pixel`), or the panel has no form for it. `normalize` of version 4 runs only as a job; its tile is version 3.
function tileStep(step: DraftStep, info: ProcessInfo): { operator: Operator; fields: Field[]; version: number } | { reason: string } {
  const operator = info.operators.find((o) => o.op === step.op && o.opVersion === step.opVersion);
  if (!operator) return { reason: NO_PREVIEW_UNLISTED };
  const asVersion3 = operator.op === 'normalize' && operator.opVersion === NORMALIZE_VERSION;
  if (!asVersion3 && (!operator.tiers.includes('T1') || operator.kind !== 'pixel')) return { reason: NO_PREVIEW };
  if (!operator.form.supported) return { reason: NO_PREVIEW_FORM };
  return { operator, fields: operator.form.fields, version: asVersion3 ? TILE_VERSION : operator.opVersion };
}

// What the tile route takes of the parameters of one step, in characters (`MAX_OPERATOR_PARAMS_CHARS` of the backend).
export const MAX_OPERATOR_PARAMS_CHARS = 2048;
export const NO_NUMBERS_YET = 'Normalize has no measured numbers yet.';

// A statistical `normalize` step: the tile needs the numbers measured for it.
const waitsForNumbers = (step: DraftStep, params: Record<string, unknown>): boolean => step.op === 'normalize' && isStatistical(params.method);

// The preview is the longest start of the steps in which every one runs as a tile
// (`T1`, a pixel operator) and has its fields complete, at most `MAX_PREVIEW_STEPS`
// of them (adr/0014 §6.1); the tile URL takes the steps in that order. Nothing after
// a step that cannot be drawn is shown. Without steps there is nothing to say.
//
// A statistical `normalize` step is drawn with the numbers measured for it (`numbers`, by step key, NM4-11b): the tile
// takes them in its parameters, as version 3. Without them, or with parameters longer than the tile route takes, the start ends before it.
export function planPreview(steps: readonly DraftStep[], info: ProcessInfo | null, numbers: ReadonlyMap<number, Measured> = new Map()): PreviewPlan {
  const first = steps[0];
  if (!info || !first) return { state: 'off', reason: null };
  const planned: PlannedStep[] = [];
  for (const step of steps.slice(0, MAX_PREVIEW_STEPS)) {
    const found = tileStep(step, info);
    if ('reason' in found) break;
    const { params, errors } = paramsFrom(found.fields, step.values, step.op);
    if (Object.keys(errors).length > 0) break;
    if (waitsForNumbers(step, params)) {
      const measured = numbers.get(step.key);
      if (!measured) break;
      params.measured = measured;
    }
    if (canonicalJson(params).length > MAX_OPERATOR_PARAMS_CHARS) break;
    planned.push({ step, operator: found.operator, params, version: found.version });
  }
  if (planned.length === 0) {
    const found = tileStep(first, info);
    if ('reason' in found) return { state: 'off', reason: found.reason };
    const { params, errors } = paramsFrom(found.fields, first.values, first.op);
    return { state: 'off', reason: Object.keys(errors).length === 0 && waitsForNumbers(first, params) ? NO_NUMBERS_YET : 'Complete the step to see the preview.' };
  }
  return { state: 'ready', steps: planned, further: planned.length < steps.length };
}

// What the panel says under the preview when the map shows less than the job runs.
export function furtherNote(plan: Extract<PreviewPlan, { state: 'ready' }>): string {
  const shown = plan.steps.length === 1 ? 'the first step' : `the first ${plan.steps.length} steps`;
  return `The map shows ${shown}; the job runs all steps.`;
}

// --- the band the map shows (NM4-43e PR 2, adr/0020 §10) ---------------------------------

// The names the stock must hold before the first step for `band` to come out: the planner's trace from the end
// (`processing/plan.py::_trace`, adr/0020 §4). A `band_math` step whose result nobody needs is not run, and a result
// that is needed is replaced by the names its expression reads. `normalize` and `reproject` keep the names they are given; `mask_values` reads the band it looks at.
export function namesNeeded(steps: readonly DraftStep[], band: string): Set<string> {
  const needed = new Set([band]);
  for (const step of [...steps].reverse()) {
    // A mask by value always reads the band that decides (`BandUse(reads={band})`), whichever band is shown.
    if (step.op === 'mask_values' && typeof step.values.band === 'string' && step.values.band !== '') needed.add(step.values.band);
    if (!isBandMath(step) || !needed.delete(resultNameOf(step))) continue;
    for (const name of namesInExpression(typeof step.values.expression === 'string' ? step.values.expression : '')) needed.add(name);
  }
  return needed;
}

// Which band the map shows and what it has to read for it.
export interface PreviewRead {
  // Every band of the output the map can draw, the results of the steps it draws above the bands of the data. "RGB" is
  // on top where the dataset has a colour picture and its three bands are in the output (NM4-64).
  choices: string[];
  // The band the tile shows: the one the person picked while it is among the choices, else the result added last (the
  // step created last, not the last of the chain), else the first choice (RGB, where it is offered); `null` for an empty
  // output, where the tiler shows what it shows by itself.
  band: string | null;
  // The bands the tile is asked for (`band=`): that one, the three of the colour picture for "RGB", none without a band.
  bands: string[];
  // The assets those bands need, in the order of the item: the planner's strike (`processing/tile.py::plan_band`).
  assets: string[];
}

export function previewRead(args: {
  output: readonly string[];
  dataNames: readonly string[];
  sources: readonly BandSource[];
  // The asset of the layer a mask step reads, `null` without a mask step in the order.
  maskAsset: string | null;
  // The assets of the whole order: what is read where no band is shown.
  all: readonly string[];
  // The steps the map draws, in order.
  steps: readonly DraftStep[];
  pick: string | null;
  // `earthx:true_color` of the dataset (red, green, blue), `null` where it has none.
  trueColor: readonly string[] | null;
}): PreviewRead {
  const { output, dataNames, sources, maskAsset, all, steps, pick, trueColor } = args;
  const kept = new Set(output);
  const results = resultsOf(steps).filter((result) => kept.has(result.name));
  const colour = trueColor !== null && trueColor.length === 3 && trueColor.every((name) => kept.has(name) && dataNames.includes(name));
  const choices = [...(colour ? [RGB] : []), ...results.map((result) => result.name), ...output.filter((name) => dataNames.includes(name))];
  const band = pick !== null && choices.includes(pick) ? pick : startBand(choices, results.map((r) => ({ name: r.name, created: r.key })));
  if (band === null) return { choices, band, bands: [], assets: [...all] };
  const bands = band === RGB ? [...trueColor!] : [band];
  const carried = new Set(assetsCarrying(sources, bands.flatMap((name) => [...namesNeeded(steps, name)])));
  if (maskAsset !== null && steps.some((step) => step.op === 'mask')) carried.add(maskAsset);
  return { choices, band, bands, assets: sources.map((source) => source.asset).filter((asset) => carried.has(asset)) };
}

// --- a chain the tiler refuses (Otto, 22.10.2026) ------------------------------------

// A chain can name a band that an earlier step removed. The panel does not know the bands
// each operator leaves: it asks the tiler and shows the steps before the one it refuses.
export interface RefusedStep {
  // Counted from 0, as every refusal of an order is (`stepOfRefusal`); the first step is 0.
  step: number;
  reason: string;
}

// `step 1: expression names unknown band(s): red; …` → `{ step: 1, reason: '…' }`, the second step.
export function refusedStepOf(detail: unknown): RefusedStep | null {
  if (typeof detail !== 'string') return null;
  const found = /^step (\d+): ([\s\S]+)$/.exec(detail);
  return found ? { step: Number(found[1]), reason: found[2].trim() } : null;
}

// What the tiler said to the TileJSON of a chain: it takes it, it refuses a step, or it gave no answer to go by.
export type ChainAnswer = { state: 'taken' } | { state: 'refused'; refused: RefusedStep } | { state: 'none' };

// Asks the TileJSON of a chain of `steps` steps, one step as well as several: it is the cheap question, and it
// has the same refusals as the tiles and the statistics. A refusal (400, 422) of several steps names its step; the
// refusal of a single step has none to name, so its text is the reason for step 0. `none`: the answer is
// of no use (a failing source, a network that fails, a refusal of several steps without a step) — then the map
// is left as it is.
export async function probeChain(url: string, steps: number, fetchImpl: typeof fetch = fetch): Promise<ChainAnswer> {
  try {
    const response = await fetchImpl(url);
    if (response.ok) return { state: 'taken' };
    // Only the refusals of the chain itself: a missing scene (404) or a busy tiler (429) says nothing about the steps.
    if (response.status !== 400 && response.status !== 422) return { state: 'none' };
    const body: unknown = await response.json();
    const detail = (body as { detail?: unknown } | null)?.detail;
    const refused = refusedStepOf(detail) ?? (steps === 1 && typeof detail === 'string' ? { step: 0, reason: detail.trim() } : null);
    return refused ? { state: 'refused', refused } : { state: 'none' };
  } catch {
    return { state: 'none' };
  }
}

// What the tiler said to the TileJSON of a mosaic with steps (NM4-04): it takes it and names the scenes in the order a tile
// reads them, it refuses a step (the same words as for one scene), or it does not take the mosaic as such — too long
// a request, a pass it cannot mosaic, a failing source, a network that fails — and the scenes are drawn one by one.
// `retry`: the question failed on the way (a busy tiler, a failing source, a network that fails, no answer in time) and
// says nothing about the mosaic: the scenes are drawn for now and the mosaic is asked again at the next change.
export type MosaicAnswer =
  | { state: 'taken'; order: string[] }
  | { state: 'refused'; refused: RefusedStep }
  | { state: 'scenes'; retry?: true };

export async function probeMosaic(url: string, fetchImpl: typeof fetch = fetch): Promise<MosaicAnswer> {
  try {
    const response = await fetchImpl(url, { signal: AbortSignal.timeout(MOSAIC_TILEJSON_TIMEOUT_MS) });
    const body: unknown = await response.json().catch(() => null);
    if (response.ok) {
      const order = (body as Record<string, unknown> | null)?.['earthx:order'];
      const named = Array.isArray(order) && order.length > 0 && order.every((id) => typeof id === 'string');
      return named ? { state: 'taken', order: order as string[] } : { state: 'scenes' };
    }
    const refused = refusedStepOf((body as { detail?: unknown } | null)?.detail);
    if (refused && (response.status === 400 || response.status === 422)) return { state: 'refused', refused };
    return [400, 414, 422, 501].includes(response.status) ? { state: 'scenes' } : { state: 'scenes', retry: true };
  } catch {
    return { state: 'scenes', retry: true };
  }
}

// The plan cut to its first `count` steps, the ones before a refused step; `null` for none.
export function shortenPlan(plan: Extract<PreviewPlan, { state: 'ready' }>, count: number): Extract<PreviewPlan, { state: 'ready' }> | null {
  if (count < 1) return null;
  return { state: 'ready', steps: plan.steps.slice(0, count), further: true };
}

// "Preview shows step 1 of 2. Step 2: band red is not available after step 1." — for people the first step is 1.
// A single step has no number to name: "No preview: the expression is not valid."
export function refusedNote(shown: number, total: number, refused: RefusedStep): string {
  const text = refused.reason.replace(/\.?$/, '.');
  if (total === 1 && shown < 1) return `No preview: ${text}`;
  const reason = `Step ${refused.step + 1}: ${text}`;
  if (shown < 1) return `No preview. ${reason}`;
  const which = shown === 1 ? 'step 1' : `steps 1 to ${shown}`;
  return `Preview shows ${which} of ${total}. ${reason}`;
}

// --- what the map draws -----------------------------------------------------

export interface PreviewScene {
  id: string;
  bbox: Bbox;
  // The tile template of the scene, without any AOI clip.
  url: string;
  // Set for a scene of a mosaic: the first level of the mosaic. The scene is drawn below it, stacked in the order of
  // the mosaic, and steps aside for the mosaic from there (`mosaic.ts::viewOfPass`).
  below?: number;
}

// The pass of one job drawn as one surface, the mosaic the job makes (NM4-04): the tiler reads its scenes, the first
// valid pixel of each band wins and the steps run over the result.
export interface PreviewMosaic {
  // The scenes of the pass, in the order the tiler reads them.
  order: string[];
  bounds: Bbox;
  // The tile template, without any AOI clip.
  url: string;
  // Its TileJSON: what `probeMosaic` asks.
  probe: string;
  // Its first and its last level: its tiles are 512 px (`tileSize.ts`), so a level is as fine as the next one of a scene's,
  // and the last is one lower than the scenes' (`previewMaxZoom`).
  minZoom: number;
  maxZoom: number;
}

export interface PreviewSpec {
  // Changes whenever the picture does; the map and the debounce compare it.
  key: string;
  title: string;
  // How many steps the picture is made of.
  stepCount: number;
  // The band the tiles show; `null` where the tiler chooses by itself. "RGB" (`RGB`) for the colour picture.
  band: string | null;
  // The bands the tiles are asked for (`band=`): that one, or the three of the colour picture; `null` with no band.
  bands: string[] | null;
  // The TileJSON of the first scene with the same steps: what `probeChain` asks.
  probe: string;
  // What the measure is called: the statistics of the first scene with the same steps (of a mosaic: the first it
  // reads, the one that wins where scenes overlap), as `sceneMeasure` asks them; for "AOI only" with a complete order
  // the order text instead (`areaOrder`), which carries the AOI and so stays in memory. It does not depend on the
  // range, so a new range is no new measure.
  measure: string;
  // The statistics of the first scene as a GET: the measure of "Whole scene", and the fall-back of the other.
  sceneMeasure: string;
  // "AOI only", whole chain, complete order of the first job: the tiler counts the statistics over the AOI as the job
  // does (`postAreaStatistics`). `null`: the measure is the first scene's.
  areaOrder: { datasetId: string; order: Order } | null;
  // Whether the band shown is a Band math result (with no band chosen: whether a Band math step is among the steps):
  // what the values of an index are judged by.
  expression: boolean;
  // The range and colormap of the preset (NM4-14) whose expression the band shown has, in the presets of the dataset; `null`
  // for any other band. It goes before the measure: an index is drawn alike wherever it is made.
  preset: PreviewRange | null;
  // The passes drawn as a mosaic from their first level up, and the scenes: those below a mosaic, those of a pass
  // that is drawn scene by scene.
  mosaics: PreviewMosaic[];
  scenes: PreviewScene[];
  // A pass the job makes a mosaic of is drawn scene by scene: the tiler would not take its mosaic.
  perScene: boolean;
  minZoom: number;
  // Capped so that no tile is as fine as the data (`previewMaxZoom`).
  maxZoom: number;
  // "AOI only": the tiles are cut to the AOI in the browser (`aoiClip.ts`).
  clipToAoi: boolean;
  // The AOI they are cut to where it is not the map's: the part of it that lies in a result.
  clipAoi?: GeoJSON.Geometry;
}

const positive = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null;

// The order `access/download.py::asset_gsd` reads them in: the asset's own `gsd`,
// the first band's `spatial_resolution`, the item's `gsd`.
export function assetGsd(item: StacItem, key: string): number | null {
  const asset = item.assets?.[key];
  return positive(asset?.gsd) ?? positive((asset ? bandsOf(asset) : null)?.[0]?.spatial_resolution) ?? positive(item.properties?.gsd);
}

// The asset of the item an order asset reads: its own key, or — a variable of a
// Zarr group, `<asset><separator><variable>` — the key of the group.
function itemAssetKey(item: StacItem, orderAsset: string, separator: string | null): string {
  if (item.assets?.[orderAsset]) return orderAsset;
  if (separator) {
    const group = Object.keys(item.assets ?? {}).find((key) => orderAsset.startsWith(`${key}${separator}`));
    if (group) return group;
  }
  return orderAsset;
}

// The finest pixel size among the assets of the order; where only some state
// one, those count.
export function finestGsd(items: readonly StacItem[], assets: readonly string[], separator: string | null): number | null {
  const known = items.flatMap((item) =>
    assets.map((asset) => assetGsd(item, itemAssetKey(item, asset, separator))).filter((gsd): gsd is number => gsd !== null),
  );
  return known.length === 0 ? null : Math.min(...known);
}

// The scenes of a mosaic in the order the tiler named, those it did not name last and by id: the order of the pass
// is the tiler's, and an answer that lacks a scene or knows an unknown one does not unmake the picture.
function readOrder(named: readonly string[], ids: readonly string[]): string[] {
  const known = new Set(ids);
  const order = [...new Set(named.filter((id) => known.has(id)))];
  return [...order, ...[...ids].sort().filter((id) => !order.includes(id))];
}

export function previewSpec(args: {
  dataset: DatasetOption | undefined;
  items: readonly StacItem[];
  assets: readonly string[];
  info: ProcessInfo;
  plan: Extract<PreviewPlan, { state: 'ready' }>;
  range: PreviewRange;
  area: Area;
  // The scenes of each job of the order: a job of several scenes is a mosaic (NM4-04), and the preview draws it
  // as one where the tiler takes it. Without them every scene is drawn alone.
  jobs?: readonly (readonly StacItem[])[];
  // What the tiler said of the mosaics asked so far, by TileJSON URL; one not asked yet is taken to be taken.
  answers?: ReadonlyMap<string, MosaicAnswer>;
  // The order of the first job, `null` while it is not complete: with "AOI only" it is what the range is measured on.
  order?: Order | null;
  // The band the tiles show and, where the output has more than one, the preview is named after it. For "RGB" the three
  // bands of the colour picture are `bands`; else that one band is.
  band?: string | null;
  bands?: readonly string[];
  named?: boolean;
  // The AOI the tiles are cut to where it is not the map's (the part of it in a result), for "AOI only".
  clipAoi?: GeoJSON.Geometry;
}): PreviewSpec | null {
  const { dataset, items, assets, info, plan, range, area, jobs = [], answers, order = null, band = null, named = false } = args;
  const clipAoi = area === 'aoi' ? args.clipAoi : undefined;
  if (!dataset?.viewable || assets.length === 0 || assets.length > MAX_PREVIEW_ASSETS) return null;
  if (band === RGB && args.bands?.length !== 3) return null;
  const rescale = rescaleOf(range);
  if ('problem' in rescale) return null;
  // The tiles ask for the band, or the three of the colour picture, which takes one range for all of them and no colormap.
  const shown: string[] | null = band === null ? null : band === RGB ? [...args.bands!] : [band];
  const asked: ShownBands = shown === null ? null : shown.length === 1 ? shown[0] : shown;
  const render = { rescale: rescale.rescale, colormapName: band === RGB ? undefined : range.colormap || undefined };
  const chain = plan.steps.map(({ step, params, version }) => ({ op: step.op, opVersion: version, paramsJson: canonicalJson(params) }));
  // Without a pixel size there is no level to hold the preview under: it is drawn
  // as before, up to the last released level, and "Preview" says what it is (Otto,
  // 19.10.2026).
  const gsd = finestGsd(items, assets, info.variableSeparator);
  const bboxes = items.flatMap((item) => (item.bbox ? [item.bbox] : []));
  const maxZoomOf = (tileSize: number) => (gsd === null ? dataset.zoom.max : previewMaxZoom(bboxes, gsd, dataset.zoom, tileSize));
  const maxZoom = maxZoomOf(TILE_SIZE);
  // The mosaic's tiles are 512 px, a level finer than the scenes' at the same level.
  const mosaicMaxZoom = maxZoomOf(MOSAIC_TILE_SIZE);
  // The levels from which a pass is one mosaic: the tiler takes none below `MIN_MOSAIC_ZOOM`.
  const firstLevel = Math.max(MIN_MOSAIC_ZOOM, dataset.zoom.min);

  // The mosaic of one job, or `null` for the scenes one by one: not a pass of several scenes, more than the tile route
  // takes (scenes, assets, bytes of the request, levels), or a mosaic the tiler did not take.
  const mosaicOf = (unit: readonly StacItem[]): PreviewMosaic | null => {
    const bounds = unionBbox(unit.map((item) => item.bbox));
    if (
      !bounds ||
      unit.length < MIN_MOSAIC_SCENES ||
      unit.length > MAX_MOSAIC_SCENES ||
      assets.length > MAX_MOSAIC_OPERATOR_ASSETS ||
      mosaicMaxZoom < MIN_MOSAIC_ZOOM
    ) {
      return null;
    }
    const ids = unit.map((item) => item.id);
    const url = buildTileUrl(buildMosaicOperatorTileTemplate(dataset.id, ids, assets, chain, asked), render);
    if (mosaicRequestBytes(url, mosaicMaxZoom) > MAX_MOSAIC_REQUEST_BYTES) return null;
    const probe = buildMosaicOperatorTileJsonUrl(dataset.id, ids, assets, chain, asked);
    const answer = answers?.get(probe);
    if (answer?.state === 'scenes') return null;
    return { order: readOrder(answer?.state === 'taken' ? answer.order : [], ids), bounds, url, probe, minZoom: firstLevel, maxZoom: mosaicMaxZoom };
  };
  const mosaics = jobs.flatMap((unit) => mosaicOf(unit) ?? []);
  const mosaicked = new Set(mosaics.flatMap((mosaic) => mosaic.order));

  // The scenes below a mosaic come first, in the order the mosaic reads them, then the scenes drawn alone. The map
  // draws so many rasters and no more: the scenes drawn alone have their places first, for they are the only picture
  // of their scene at every level, the ones below a mosaic take what is left.
  const known = new Map([...items, ...jobs.flat()].map((item) => [item.id, item]));
  const below = dataset.zoom.min < firstLevel ? firstLevel : undefined;
  const places = Math.max(0, MAX_PREVIEW_SCENES - mosaics.length);
  const alone: { item: StacItem; below?: number }[] = items.filter((item) => !mosaicked.has(item.id)).slice(0, places).map((item) => ({ item }));
  const under: { item: StacItem; below?: number }[] =
    below === undefined ? [] : mosaics.flatMap((mosaic) => mosaic.order.map((id) => ({ item: known.get(id)!, below }))).slice(0, places - alone.length);
  const scenes: PreviewScene[] = [];
  let probe = '';
  for (const { item, below: underLevel } of [...under, ...alone]) {
    if (!item.bbox) continue;
    scenes.push({
      id: item.id,
      bbox: item.bbox,
      url: buildTileUrl(buildOperatorTileTemplate(dataset.id, item.id, assets, chain, asked), render),
      ...(underLevel === undefined ? {} : { below: underLevel }),
    });
    if (!probe) probe = buildOperatorTileJsonUrl(dataset.id, item.id, assets, chain, asked);
  }
  // The scene that wins where the scenes of the first mosaic overlap is the one measured.
  const measured = mosaics[0]?.order[0] ?? scenes[0]?.id;
  if (measured === undefined) return null;
  const clipToAoi = area === 'aoi';
  // The chain must be whole: the order runs all its steps, and a preview of a start of them would be measured on more.
  const areaOrder = clipToAoi && order !== null && !plan.further ? { datasetId: dataset.id, order } : null;
  const sceneMeasure = buildOperatorStatisticsUrl(dataset.id, measured, assets, chain, asked);
  return {
    key: canonicalJson({
      urls: scenes.map((s) => s.url),
      ...(mosaics.length > 0 ? { mosaics: mosaics.map((m) => [m.url, m.order, m.maxZoom]), below: scenes.map((s) => s.below ?? null) } : {}),
      minZoom: dataset.zoom.min,
      maxZoom,
      clipToAoi,
      ...(clipAoi ? { clipAoi } : {}),
    }),
    title: [plan.steps.map(({ operator }) => operator.title).join(' → '), ...(named && band !== null ? [bandLabel(band)] : [])].join(' · '),
    stepCount: plan.steps.length,
    band,
    bands: shown,
    probe,
    measure: areaOrder ? (band === null ? canonicalJson(areaOrder.order) : `${canonicalJson(areaOrder.order)}\n${band}`) : sceneMeasure,
    sceneMeasure,
    areaOrder,
    expression: plan.steps.some(({ step }) => isBandMath(step) && (band === null || resultNameOf(step) === band)),
    preset: presetOfBand(dataset, plan, band),
    mosaics,
    scenes,
    perScene: jobs.some((unit) => unit.length >= MIN_MOSAIC_SCENES && !mosaicked.has(unit[0].id)),
    minZoom: dataset.zoom.min,
    maxZoom,
    clipToAoi,
    ...(clipAoi ? { clipAoi } : {}),
  };
}

// The look of the preset whose expression the band `band` has, if it is a result of a Band math step of the chain.
function presetOfBand(dataset: DatasetOption, plan: Extract<PreviewPlan, { state: 'ready' }>, band: string | null): PreviewRange | null {
  if (band === null || band === RGB) return null;
  const made = plan.steps.find(({ step }) => isBandMath(step) && resultNameOf(step) === band);
  const preset = presetFor(indexPresetsOf(dataset.collection), made?.params.expression as string | undefined);
  return preset ? presetRange(preset) : null;
}

// --- the measure of a preview (M4-19c) ---------------------------------------

// What the tiler said of the values the steps make: the numbers the colour scale is chosen from, and the unit of
// the result. `key` is the `PreviewSpec.measure` it answers.
export interface PreviewMeasure {
  key: string;
  stats: ResultStats | null;
  // As the data say it; "1" is shown as nothing (`shownUnit`).
  unit: string | null;
  // Over what it was measured: the AOI as the job counts it, the first whole scene, or — `fallback` — the first
  // whole scene because the measure over the AOI was not to be had.
  source: 'area' | 'scene' | 'fallback';
  // Over the AOI: the values are the result's; else the tiler read a coarser raster. Always `true` for a scene.
  exact: boolean;
  // What the statistics named of each band that has a valid pixel, whole: where "vmin"/"vmax" typed in percentiles are read
  // from, if they name them (NM4-65 part 4).
  raw?: Record<string, unknown>[];
}

const finite = (value: unknown): number | null => (typeof value === 'number' && Number.isFinite(value) ? value : null);

// The one unit all bands have, where they have one.
function commonUnit(units: readonly (string | null)[]): string | null {
  const distinct = new Set(units);
  return distinct.size === 1 ? [...distinct][0] : null;
}

// `/statistics` with the steps, as a measure: per band the minimum, maximum and 2/98 percentiles of the valid
// pixels (none with `count` 0), and the one unit all bands have, where they have one.
export function measureOf(
  key: string,
  statistics: Record<string, BandStatistics>,
  expression: boolean,
  source: 'scene' | 'fallback' = 'scene',
): PreviewMeasure {
  const bands = Object.values(statistics);
  const read = bands.map((band): BandStats => {
    const usable = (finite(band.count) ?? 0) > 0;
    return {
      minimum: usable ? finite(band.min) : null,
      maximum: usable ? finite(band.max) : null,
      percentile2: usable ? finite(band.percentile_2) : null,
      percentile98: usable ? finite(band.percentile_98) : null,
    };
  });
  const unit = commonUnit(bands.map((band) => (typeof band.unit === 'string' ? band.unit : null)));
  const named = read.some((band) => band.minimum !== null && band.maximum !== null);
  return { key, stats: named ? { bands: read, expression } : null, unit, source, exact: true, raw: bands.filter((band) => (finite(band.count) ?? 0) > 0) };
}

// The statistics over the AOI as a measure: the object of the results document per band, read as a result's are.
export function areaMeasureOf(key: string, answer: AreaStatistics, expression: boolean): PreviewMeasure {
  return {
    key,
    stats: statsFrom(answer.bands, expression),
    unit: commonUnit(answer.bands.map((band) => band.unit)),
    source: 'area',
    exact: answer.exact,
    raw: answer.bands.map((band) => band.statistics).filter((stats) => (finite(stats.count) ?? 0) > 0),
  };
}

// What the tooltip of "Preview" says of the range, where it is not the job's: only for "AOI only", and only of the
// measure of this very preview.
export function measureHint(preview: PreviewSpec | null, measure: PreviewMeasure | null): string | null {
  if (!preview || !preview.clipToAoi || !measure || measure.key !== preview.measure) return null;
  if (measure.source === 'area') return measure.exact ? null : COARSE_MEASURE_HINT;
  return SCENE_MEASURE_HINT;
}

// The tooltip of "Preview", on the map and in the panel.
export function previewTitle(preview: PreviewSpec | null, measure: PreviewMeasure | null): string | undefined {
  const lines = [preview?.perScene ? SCENE_PREVIEW_HINT : null, measureHint(preview, measure)].filter((line) => line !== null);
  return lines.length > 0 ? lines.join('\n') : undefined;
}

// The range the measure calls for as the panel holds it (the same rule as a result's, `scaleOf`), or `null`.
export function measuredRange(measure: PreviewMeasure | null): PreviewRange | null {
  const scale = scaleOf(measure?.stats ?? null);
  return scale ? { vmin: String(scale.low), vmax: String(scale.high), colormap: scale.colormap } : null;
}

// The unit beside the range of the preview: that of the measure of this very preview, and nothing for a
// dimensionless quantity ("1") or an unknown one.
export function previewUnit(preview: PreviewSpec | null, measure: PreviewMeasure | null): string | null {
  return preview && measure && measure.key === preview.measure ? shownUnit(measure.unit) : null;
}

// What the panel says when the measure could not be had: the preview then keeps the start range.
export const NO_MEASURE = 'The range could not be measured, so the preview uses its start range. Set it by hand or try Auto stretch.';

// The overlays of a preview, as the map and a layer hold them, the first on top: the mosaics, then the scenes. A scene
// below a mosaic is drawn up to the level before it and steps aside for it (`hideFrom`, as in `mosaic.ts::viewOfPass`).
export function previewOverlays(spec: PreviewSpec, aoi: GeoJSON.Geometry | null): LayerOverlay[] {
  const clip = spec.clipToAoi ? (spec.clipAoi ?? aoi) : null;
  const mosaics = spec.mosaics.map((mosaic) => ({
    kind: 'raster' as const,
    tileUrl: clipTileUrl(mosaic.url, clip),
    bounds: mosaic.bounds,
    minZoom: mosaic.minZoom,
    maxZoom: mosaic.maxZoom,
    preview: true as const,
  }));
  const scenes = spec.scenes.map((scene) => ({
    kind: 'raster' as const,
    tileUrl: clipTileUrl(scene.url, clip),
    bounds: scene.bbox,
    minZoom: spec.minZoom,
    maxZoom: scene.below === undefined ? spec.maxZoom : Math.min(spec.maxZoom, scene.below - 1),
    ...(scene.below === undefined ? {} : { hideFrom: scene.below - tileLevelAhead(MOSAIC_TILE_SIZE) }),
    preview: true as const,
  }));
  return [...mosaics, ...scenes];
}

// --- never as fine as the data (Otto, 19.10.2026) ---------------------------

// The last tile level the preview asks for. A tile is the finest where the scene
// lies farthest from the equator, so the level is chosen there: every tile is
// coarser than `gsd` (strictly), everywhere in the scenes. Above it the map
// stretches the last level, the picture gets blurry and no finer. Held within the
// released levels; a dataset whose lowest level is already finer than the data
// cannot be held under it, and keeps that level. A tile of 512 px is as fine as the next level's of 256 px, so the
// last level for it is one lower.
export function previewMaxZoom(
  bboxes: readonly Bbox[],
  gsd: number,
  zoom: { min: number; max: number },
  tileSize: number = TILE_SIZE,
): number {
  const farthest = Math.max(0, ...bboxes.flatMap(([, south, , north]) => [Math.abs(south), Math.abs(north)]));
  const coarsest = tileMetres(Math.min(farthest, 89), 0, tileSize) / gsd;
  // The largest whole level below log2(coarsest): its tiles are still coarser than `gsd`.
  const level = Math.ceil(Math.log2(coarsest)) - 1;
  return Math.max(zoom.min, Math.min(zoom.max, level));
}
