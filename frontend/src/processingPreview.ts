// The preview of the steps on the map (M4-13c-2, plan §3.3): which steps can be
// shown as tiles, the tile URLs of the scenes of an order, when the map says
// "Preview", and the layer a preview becomes. Pure functions; the state lives in
// `processingStore.ts`.

import { clipTileUrl } from './aoiClip';
import { buildOperatorTileJsonUrl, buildOperatorTileTemplate } from './api';
import type { DatasetOption } from './datasets';
import type { LayerOverlay } from './layers';
import { buildTileUrl } from './mapLayers';
import { canonicalJson } from './processing';
import { bandsOf, type Area, type DraftStep, type Operator, type ProcessInfo } from './processingOrder';
import { paramsFrom, type Field } from './schemaForm';
import type { Bbox, StacItem } from './types';

// As many scenes as the full-resolution view draws (`mapLayers.ts`).
export const MAX_PREVIEW_SCENES = 40;
// The tile route takes at most this many assets with an operator (`api/tiler.py`).
export const MAX_PREVIEW_ASSETS = 16;
// And at most this many steps in a chain (`api/tiler.py::MAX_OPERATOR_STEPS`).
export const MAX_PREVIEW_STEPS = 4;

export const NO_PREVIEW = 'No preview: the first step runs only as a job.';

// --- range and colormap ------------------------------------------------------

// What the preview is drawn with (F3 (1)): a range and a colormap by hand, the
// start values for an index such as NDVI. "Auto stretch" is not offered: the
// statistics route takes no operator.
export interface PreviewRange {
  vmin: string;
  vmax: string;
  // `''`: no colormap.
  colormap: string;
}

export const DEFAULT_RANGE: PreviewRange = { vmin: '-1', vmax: '1', colormap: 'rdylgn' };

export const AUTO_STRETCH_REASON = 'Not for a preview: the statistics of a tile cannot be measured through an operator. Set the range by hand.';

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

// The operator of a step that can be a tile and the fields of its form, or `null`:
// the operator is not on the dataset's list, the panel has no form for it, or it does
// not run as a tile (`T1`, `pixel`).
function tileStep(step: DraftStep, info: ProcessInfo): { operator: Operator; fields: Field[] } | null {
  const operator = info.operators.find((o) => o.op === step.op && o.opVersion === step.opVersion);
  if (!operator || !operator.form.supported || !operator.tiers.includes('T1') || operator.kind !== 'pixel') return null;
  return { operator, fields: operator.form.fields };
}

// The preview is the longest start of the steps in which every one runs as a tile
// (`T1`, a pixel operator) and has its fields complete, at most `MAX_PREVIEW_STEPS`
// of them (adr/0014 §6.1); the tile URL takes the steps in that order. Nothing after
// a step that cannot be drawn is shown. Without steps there is nothing to say.
export function planPreview(steps: readonly DraftStep[], info: ProcessInfo | null): PreviewPlan {
  const first = steps[0];
  if (!info || !first) return { state: 'off', reason: null };
  const planned: PlannedStep[] = [];
  for (const step of steps.slice(0, MAX_PREVIEW_STEPS)) {
    const found = tileStep(step, info);
    if (!found) break;
    const { params, errors } = paramsFrom(found.fields, step.values);
    if (Object.keys(errors).length > 0) break;
    planned.push({ step, operator: found.operator, params });
  }
  if (planned.length === 0) {
    return tileStep(first, info) === null
      ? { state: 'off', reason: NO_PREVIEW }
      : { state: 'off', reason: 'Complete the step to see the preview.' };
  }
  return { state: 'ready', steps: planned, further: planned.length < steps.length };
}

// What the panel says under the preview when the map shows less than the job runs.
export function furtherNote(plan: Extract<PreviewPlan, { state: 'ready' }>): string {
  const shown = plan.steps.length === 1 ? 'the first step' : `the first ${plan.steps.length} steps`;
  return `The map shows ${shown}; the job runs all steps.`;
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

// Asks the TileJSON of a chain. `null`: the tiler takes it, or the answer names no step
// (an unreachable source, a refusal of the whole URL) — then the map is left as it is.
export async function probeChain(url: string, fetchImpl: typeof fetch = fetch): Promise<RefusedStep | null> {
  try {
    const response = await fetchImpl(url);
    if (response.ok || response.status >= 500) return null;
    const body: unknown = await response.json();
    return refusedStepOf((body as { detail?: unknown } | null)?.detail);
  } catch {
    return null;
  }
}

// The plan cut to its first `count` steps, the ones before a refused step; `null` for none.
export function shortenPlan(plan: Extract<PreviewPlan, { state: 'ready' }>, count: number): Extract<PreviewPlan, { state: 'ready' }> | null {
  if (count < 1) return null;
  return { state: 'ready', steps: plan.steps.slice(0, count), further: true };
}

// "Preview shows step 1 of 2. Step 2: band red is not available after step 1." — for people the first step is 1.
export function refusedNote(shown: number, total: number, refused: RefusedStep): string {
  const reason = `Step ${refused.step + 1}: ${refused.reason.replace(/\.?$/, '.')}`;
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
}

export interface PreviewSpec {
  // Changes whenever the picture does; the map and the debounce compare it.
  key: string;
  title: string;
  // How many steps the picture is made of.
  stepCount: number;
  // The TileJSON of the first scene with the same steps: what `probeChain` asks.
  probe: string;
  scenes: PreviewScene[];
  minZoom: number;
  // Capped so that no tile is as fine as the data (`previewMaxZoom`).
  maxZoom: number;
  // "AOI only": the tiles are cut to the AOI in the browser (`aoiClip.ts`).
  clipToAoi: boolean;
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

export function previewSpec(args: {
  dataset: DatasetOption | undefined;
  items: readonly StacItem[];
  assets: readonly string[];
  info: ProcessInfo;
  plan: Extract<PreviewPlan, { state: 'ready' }>;
  range: PreviewRange;
  area: Area;
}): PreviewSpec | null {
  const { dataset, items, assets, info, plan, range, area } = args;
  if (!dataset?.viewable || assets.length === 0 || assets.length > MAX_PREVIEW_ASSETS) return null;
  const rescale = rescaleOf(range);
  if ('problem' in rescale) return null;
  const chain = plan.steps.map(({ step, params }) => ({ op: step.op, opVersion: step.opVersion, paramsJson: canonicalJson(params) }));
  const scenes: PreviewScene[] = [];
  let probe = '';
  for (const item of items.slice(0, MAX_PREVIEW_SCENES)) {
    if (!item.bbox) continue;
    const template = buildOperatorTileTemplate(dataset.id, item.id, assets, chain);
    scenes.push({
      id: item.id,
      bbox: item.bbox,
      url: buildTileUrl(template, { rescale: rescale.rescale, colormapName: range.colormap || undefined }),
    });
    if (!probe) probe = buildOperatorTileJsonUrl(dataset.id, item.id, assets, chain);
  }
  if (scenes.length === 0) return null;
  // Without a pixel size there is no level to hold the preview under: it is drawn
  // as before, up to the last released level, and "Preview" says what it is (Otto,
  // 19.10.2026).
  const gsd = finestGsd(items, assets, info.variableSeparator);
  const maxZoom = gsd === null ? dataset.zoom.max : previewMaxZoom(scenes.map((s) => s.bbox), gsd, dataset.zoom);
  const clipToAoi = area === 'aoi';
  return {
    key: canonicalJson({ urls: scenes.map((s) => s.url), minZoom: dataset.zoom.min, maxZoom, clipToAoi }),
    title: plan.steps.map(({ operator }) => operator.title).join(' → '),
    stepCount: plan.steps.length,
    probe,
    scenes,
    minZoom: dataset.zoom.min,
    maxZoom,
    clipToAoi,
  };
}

// The overlays of a preview, as the map and a layer hold them.
export function previewOverlays(spec: PreviewSpec, aoi: GeoJSON.Geometry | null): LayerOverlay[] {
  const clip = spec.clipToAoi ? aoi : null;
  return spec.scenes.map((scene) => ({
    kind: 'raster' as const,
    tileUrl: clipTileUrl(scene.url, clip),
    bounds: scene.bbox,
    minZoom: spec.minZoom,
    maxZoom: spec.maxZoom,
    preview: true as const,
  }));
}

// --- never as fine as the data (Otto, 19.10.2026) ---------------------------

// Metres per pixel of a 256-pixel Web Mercator tile at `latitude`.
export function tileResolution(latitude: number, zoom: number): number {
  return (156543.03392 * Math.cos((latitude * Math.PI) / 180)) / 2 ** zoom;
}

// The last tile level the preview asks for. A tile is the finest where the scene
// lies farthest from the equator, so the level is chosen there: every tile is
// coarser than `gsd` (strictly), everywhere in the scenes. Above it the map
// stretches the last level, the picture gets blurry and no finer. Held within the
// released levels; a dataset whose lowest level is already finer than the data
// cannot be held under it, and keeps that level.
export function previewMaxZoom(bboxes: readonly Bbox[], gsd: number, zoom: { min: number; max: number }): number {
  const farthest = Math.max(0, ...bboxes.flatMap(([, south, , north]) => [Math.abs(south), Math.abs(north)]));
  const coarsest = (156543.03392 * Math.cos((Math.min(farthest, 89) * Math.PI) / 180)) / gsd;
  // The largest whole level below log2(coarsest): its tiles are still coarser than `gsd`.
  const level = Math.ceil(Math.log2(coarsest)) - 1;
  return Math.max(zoom.min, Math.min(zoom.max, level));
}
