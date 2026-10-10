// What the processing panel reads off a process description and a selection,
// and how it builds an order from them (M4-13 §3.3–§3.5). Pure functions; the
// panel's state lives in `processingStore.ts`.

import { intersection } from 'polyclip-ts';
import type { Geom } from 'polyclip-ts';

import { footprintOf, polygonBbox } from './geoUtils';
import { bboxesOverlap } from './aoiClip';
import type { JsonSchema, Order, OrderStep, ProcessDescription } from './processing';
import { paramsForm, paramsFrom, type FieldValue, type ParamsForm } from './schemaForm';
import type { Collection, StacAsset, StacItem } from './types';

// K10: the one input of an order is always called this.
export const INPUT_NAME = 'input';

export interface Operator {
  op: string;
  opVersion: number;
  title: string;
  description?: string;
  // `x-earthx-tiers`/`x-earthx-kind` (K1): what M4-13c's preview reads.
  tiers: string[];
  kind: string | null;
  form: ParamsForm;
}

export interface ProcessInfo {
  operators: Operator[];
  maxSteps: number;
  maxAssets: number;
  dtypes: string[];
  // `x-earthx-variable-separator` (F9); `null` where the dataset has none.
  variableSeparator: string | null;
}

const isObject = (value: unknown): value is JsonSchema =>
  !!value && typeof value === 'object' && !Array.isArray(value);

function defOf(defs: JsonSchema, ref: unknown): JsonSchema | null {
  if (typeof ref !== 'string' || !ref.startsWith('#/$defs/')) return null;
  const def = defs[ref.slice('#/$defs/'.length)];
  return isObject(def) ? def : null;
}

function constOf(schema: unknown): unknown {
  return isObject(schema) ? schema.const : undefined;
}

// The operators of the order's `steps` (`oneOf` over `step_<op>_v<n>`), in the
// order the schema lists them. Only what `?dataset=` declared applicable is
// there; the panel adds nothing of its own.
export function processInfo(description: ProcessDescription): ProcessInfo {
  const schema = description.inputs?.recipe?.schema;
  const defs = isObject(schema?.$defs) ? schema.$defs : {};
  const properties = isObject(schema?.properties) ? schema.properties : {};
  const steps = isObject(properties.steps) ? properties.steps : {};
  const variants = isObject(steps.items) && Array.isArray(steps.items.oneOf) ? steps.items.oneOf : [];
  const operators: Operator[] = [];
  for (const variant of variants) {
    const def = isObject(variant) ? defOf(defs, variant.$ref) : null;
    const stepProps = def && isObject(def.properties) ? def.properties : null;
    const op = constOf(stepProps?.op);
    const opVersion = constOf(stepProps?.op_version);
    if (!def || typeof op !== 'string' || typeof opVersion !== 'number') continue;
    operators.push({
      op,
      opVersion,
      title: typeof def.title === 'string' ? def.title : op,
      ...(typeof def.description === 'string' ? { description: def.description } : {}),
      tiers: Array.isArray(def['x-earthx-tiers']) ? def['x-earthx-tiers'].filter((t) => typeof t === 'string') : [],
      kind: typeof def['x-earthx-kind'] === 'string' ? def['x-earthx-kind'] : null,
      form: paramsForm(stepProps?.params, defs),
    });
  }
  const inputDef = defOf(defs, '#/$defs/InputRequest');
  const assets = inputDef && isObject(inputDef.properties) && isObject(inputDef.properties.assets)
    ? inputDef.properties.assets
    : {};
  const output = defOf(defs, '#/$defs/RasterOutput');
  const dtype = output && isObject(output.properties) && isObject(output.properties.dtype) ? output.properties.dtype : {};
  return {
    operators,
    maxSteps: typeof steps.maxItems === 'number' ? steps.maxItems : 16,
    maxAssets: typeof assets.maxItems === 'number' ? assets.maxItems : 16,
    dtypes: Array.isArray(dtype.enum) ? dtype.enum.filter((d) => typeof d === 'string') : [],
    variableSeparator:
      typeof assets['x-earthx-variable-separator'] === 'string' ? assets['x-earthx-variable-separator'] : null,
  };
}

// --- bands (K7) ----------------------------------------------------------------

// One asset key an order can name, and the names its bands carry in an
// expression — the rule of `processing.source.expected_band_names`. `names` is
// empty where the item does not describe the bands; such an asset can still
// go into the order, it just offers no chip to insert.
export interface BandSource {
  asset: string;
  names: string[];
  dataType: string | null;
}

function bandCount(asset: StacAsset): number | null {
  const bands = asset['raster:bands'] ?? asset.bands;
  return Array.isArray(bands) && bands.length > 0 ? bands.length : null;
}

function firstDataType(asset: StacAsset): string | null {
  const bands = asset['raster:bands'] ?? asset.bands;
  const first = Array.isArray(bands) ? bands[0] : undefined;
  return first && typeof first.data_type === 'string' ? first.data_type : null;
}

function isGeoTiff(asset: StacAsset): boolean {
  return typeof asset.type === 'string' && asset.type.toLowerCase().startsWith('image/tiff')
    && !(asset.roles ?? []).includes('thumbnail');
}

// What the item offers for an order. A COG asset: one band named like the asset,
// or `<asset>_1` … per band. A Zarr asset: one order asset per variable named
// in `eo:bands`, as `<asset><separator><variable>` — none without a separator
// (F9: nothing guessed).
export function bandSources(item: StacItem, format: string | null | undefined, separator: string | null): BandSource[] {
  const sources: BandSource[] = [];
  for (const [key, asset] of Object.entries(item.assets ?? {})) {
    if (format === 'cog') {
      if (!isGeoTiff(asset)) continue;
      const count = bandCount(asset);
      const names = count === null ? [] : count === 1 ? [key] : Array.from({ length: count }, (_, i) => `${key}_${i + 1}`);
      sources.push({ asset: key, names, dataType: firstDataType(asset) });
    } else if (format === 'zarr') {
      const bands = asset['eo:bands'];
      if (!separator || !Array.isArray(bands)) continue;
      const dataType = firstDataType(asset);
      for (const band of bands) {
        if (band && typeof band.name === 'string' && band.name) {
          sources.push({ asset: `${key}${separator}${band.name}`, names: [band.name], dataType });
        }
      }
    }
  }
  return sources;
}

// The band names an expression mentions: words of letters, digits and `_`
// that are not followed by `(` (a function) — a help to pick the assets, the
// server checks the expression itself (R5).
export function namesInExpression(expression: string): Set<string> {
  const names = new Set<string>();
  for (const match of expression.matchAll(/\b[A-Za-z_][A-Za-z0-9_]*\b(?!\s*\()/gu)) names.add(match[0]);
  return names;
}

// A name maps to an asset only if exactly one source carries it (two Zarr
// groups can both carry `b04`; the panel does not choose for the user).
export function uniqueNames(sources: readonly BandSource[]): Map<string, string> {
  const owners = new Map<string, string | null>();
  for (const source of sources) {
    for (const name of source.names) owners.set(name, owners.has(name) ? null : source.asset);
  }
  const unique = new Map<string, string>();
  for (const [name, asset] of owners) if (asset !== null) unique.set(name, asset);
  return unique;
}

// The assets of the order: those the user picked and those an expression
// names, in the item's own order.
export function orderAssets(
  sources: readonly BandSource[],
  picked: readonly string[],
  expressions: readonly string[],
): string[] {
  const unique = uniqueNames(sources);
  const wanted = new Set(picked);
  for (const expression of expressions) {
    for (const name of namesInExpression(expression)) {
      const asset = unique.get(name);
      if (asset) wanted.add(asset);
    }
  }
  return sources.map((s) => s.asset).filter((asset) => wanted.has(asset));
}

// --- item (F8) -----------------------------------------------------------------

function toGeom(geometry: GeoJSON.Geometry): Geom | null {
  if (geometry.type === 'Polygon' || geometry.type === 'MultiPolygon') return geometry.coordinates as unknown as Geom;
  return null;
}

// Whether a scene's footprint meets the AOI. Without a footprint, or where the
// geometry cannot be computed, the scene stays a candidate: the server says
// which items the AOI misses (`skippedItems`).
export function touchesAoi(item: StacItem, aoi: GeoJSON.Geometry): boolean {
  const footprint = footprintOf(item);
  if (!footprint) return true;
  const a = polygonBbox(footprint);
  const b = polygonBbox(aoi);
  if (a && b && !bboxesOverlap(a, b)) return false;
  const fg = toGeom(footprint);
  const ag = toGeom(aoi);
  if (!fg || !ag) return true;
  try {
    return intersection(fg, ag).length > 0;
  } catch {
    return true;
  }
}

// The scenes one job can be ordered for: those of the selection the AOI meets.
export function candidateItems(items: readonly StacItem[], aoi: GeoJSON.Geometry): StacItem[] {
  return items.filter((item) => touchesAoi(item, aoi));
}

export function isArea(aoi: GeoJSON.Geometry | null): aoi is GeoJSON.Polygon | GeoJSON.MultiPolygon {
  return !!aoi && (aoi.type === 'Polygon' || aoi.type === 'MultiPolygon');
}

// B11: a job hands out derived data of the source; only the tier *processing*
// allows it. The server refuses below that (`403`) as well.
export function processingAllowed(collection: Collection | undefined): boolean {
  return collection?.['earthx:license_flags']?.tier === 'processing';
}

// Why "Process" cannot open for this selection, or `null` when it can.
export function processBlockReason(
  dataset: { viewable: boolean; collection: Collection } | undefined,
  aoi: GeoJSON.Geometry | null,
  sceneCount: number,
): string | null {
  if (!dataset?.viewable) return 'Pick a dataset first.';
  if (!processingAllowed(dataset.collection)) {
    const tier = dataset.collection['earthx:license_flags']?.tier ?? 'unknown';
    return `The licence of this dataset does not allow processing (tier: ${tier}).`;
  }
  if (!isArea(aoi)) return 'Draw an AOI first: a job needs an area.';
  if (sceneCount === 0) return 'Select a scene first.';
  return null;
}

// --- steps and the order -------------------------------------------------------

export interface DraftStep {
  key: number;
  op: string;
  opVersion: number;
  values: Record<string, FieldValue>;
}

export interface StepProblem {
  errors: Record<string, string>;
  unsupported?: string;
}

export interface BuiltOrder {
  order: Order | null;
  stepProblems: StepProblem[];
  problems: string[];
}

// K9: `float32` once a band-math step is there (a ratio is a fraction), else
// the data type of the first band; empty where nothing tells it.
export function defaultDtype(steps: readonly DraftStep[], sources: readonly BandSource[], assets: readonly string[], dtypes: readonly string[]): string {
  if (steps.some((s) => s.op === 'band_math') && dtypes.includes('float32')) return 'float32';
  const first = sources.find((s) => s.asset === assets[0]);
  return first?.dataType && dtypes.includes(first.dataType) ? first.dataType : '';
}

export function buildOrder(args: {
  datasetId: string;
  itemId: string | null;
  aoi: GeoJSON.Geometry | null;
  steps: readonly DraftStep[];
  assets: readonly string[];
  dtype: string;
  info: ProcessInfo;
}): BuiltOrder {
  const { datasetId, itemId, aoi, steps, assets, dtype, info } = args;
  const problems: string[] = [];
  const built: OrderStep[] = [];
  const stepProblems: StepProblem[] = steps.map((step) => {
    const operator = info.operators.find((o) => o.op === step.op && o.opVersion === step.opVersion);
    if (!operator) return { errors: {}, unsupported: 'this operator is not available for this dataset' };
    if (!operator.form.supported) return { errors: {}, unsupported: operator.form.reason };
    const { params, errors } = paramsFrom(operator.form.fields, step.values);
    built.push({ op: step.op, op_version: step.opVersion, params });
    return { errors };
  });
  if (!itemId) problems.push('Pick a scene.');
  if (!isArea(aoi)) problems.push('Draw an area as AOI.');
  if (steps.length === 0) problems.push('Add a step.');
  if (steps.length > info.maxSteps) problems.push(`At most ${info.maxSteps} steps.`);
  if (assets.length === 0) problems.push('Pick at least one band.');
  if (assets.length > info.maxAssets) problems.push(`At most ${info.maxAssets} bands.`);
  if (!dtype) problems.push('Pick an output data type.');
  const stepsOk = stepProblems.every((p) => !p.unsupported && Object.keys(p.errors).length === 0);
  if (problems.length > 0 || !stepsOk || !isArea(aoi) || !itemId) return { order: null, stepProblems, problems };
  return {
    order: {
      recipe_version: 1,
      inputs: [{ name: INPUT_NAME, dataset: datasetId, groups: [[itemId]], assets: [...assets] }],
      aoi,
      steps: built,
      output: { kind: 'raster', format: 'cog', dtype },
    },
    stepProblems,
    problems,
  };
}

// The step a refusal is about: the server names it as "step <n>" (0-based,
// `processing/recipe.py`, `api/intake.py`), else the order as a whole.
export function stepOfRefusal(detail: string): number | null {
  const match = /\bstep (\d+)\b/u.exec(detail);
  return match ? Number(match[1]) : null;
}

// --- numbers for the review (K4) ---------------------------------------------

export function formatBytes(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(1)} MB`;
  if (bytes >= 1e3) return `${Math.round(bytes / 1e3)} kB`;
  return `${bytes} B`;
}

// `PT12.3S` (the only form the route writes) → "about 12 s"; anything else is
// shown as it came.
export function formatDuration(duration: string): string {
  const match = /^PT(\d+(?:\.\d+)?)S$/u.exec(duration);
  if (!match) return duration;
  const seconds = Number(match[1]);
  if (seconds < 1) return 'under 1 s';
  if (seconds < 120) return `about ${Math.round(seconds)} s`;
  return `about ${Math.round(seconds / 60)} min`;
}

export function formatMegapixels(pixels: number): string {
  const mp = pixels / 1e6;
  return mp >= 10 ? `${Math.round(mp)} MP` : `${mp.toFixed(1)} MP`;
}
