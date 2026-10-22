// What the processing panel reads off a process description and a selection,
// and how it builds an order from them (M4-13 §3.3–§3.5). Pure functions; the
// panel's state lives in `processingStore.ts`.

import { intersection } from 'polyclip-ts';
import type { Geom } from 'polyclip-ts';

import { footprintOf, polygonBbox } from './geoUtils';
import { bboxesOverlap } from './aoiClip';
import { groupIndexOfItem } from './grouping';
import type { AoiProvenance, JsonSchema, Order, OrderStep, ProcessDescription } from './processing';
import { initialValues, paramsForm, paramsFrom, type FieldValue, type ParamsForm } from './schemaForm';
import type { Collection, StacAsset, StacBand, StacItem, TimeStepGroup } from './types';

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
  // What the item says about the values, for the output type in
  // `processingDefaults.ts`; `false`/`null` mean "the item does not say".
  //  - `scaled`: some band has a `scale` other than 1 or an `offset` other than 0
  //    (the core applies it, and the values are no longer the stored integers).
  //  - `nodata`: the one finite nodata value all its bands state, if they do.
  scaled: boolean;
  nodata: number | null;
}

// `raster:bands`, or STAC 1.1 `bands` where that is missing or empty — the
// order `api/intake.py` reads them in.
export function bandsOf(asset: StacAsset): StacBand[] | null {
  const raster = asset['raster:bands'];
  if (Array.isArray(raster) && raster.length > 0) return raster;
  return Array.isArray(asset.bands) && asset.bands.length > 0 ? asset.bands : null;
}

function bandCount(asset: StacAsset): number | null {
  return bandsOf(asset)?.length ?? null;
}

function bandFacts(asset: StacAsset): Pick<BandSource, 'scaled' | 'nodata'> {
  const bands = bandsOf(asset) ?? [];
  const scaled = bands.some((b) => (b.scale != null && b.scale !== 1) || (b.offset != null && b.offset !== 0));
  const values = new Set(bands.map((b) => (typeof b.nodata === 'number' && Number.isFinite(b.nodata) ? b.nodata : null)));
  const nodata = values.size === 1 ? [...values][0] : null;
  return { scaled, nodata };
}

function firstDataType(asset: StacAsset): string | null {
  const first = bandsOf(asset)?.[0];
  return first && typeof first.data_type === 'string' ? first.data_type : null;
}

function isGeoTiff(asset: StacAsset): boolean {
  return typeof asset.type === 'string' && asset.type.toLowerCase().startsWith('image/tiff')
    && !(asset.roles ?? []).includes('thumbnail');
}

// What the item offers for an order. A COG asset: one band named like the asset,
// or `<asset>_1` … per band. A Zarr asset: one order asset per variable named
// in the STAC core field `bands`, as `<asset><separator><variable>` — none
// without a separator (F9) and none for an asset that names no variables
// (nothing guessed; Otto 10.10.2026).
export function bandSources(item: StacItem, format: string | null | undefined, separator: string | null): BandSource[] {
  const sources: BandSource[] = [];
  for (const [key, asset] of Object.entries(item.assets ?? {})) {
    if (format === 'cog') {
      if (!isGeoTiff(asset)) continue;
      const count = bandCount(asset);
      const names = count === null ? [] : count === 1 ? [key] : Array.from({ length: count }, (_, i) => `${key}_${i + 1}`);
      sources.push({ asset: key, names, dataType: firstDataType(asset), ...bandFacts(asset) });
    } else if (format === 'zarr') {
      const bands = asset.bands;
      if (!separator || !Array.isArray(bands)) continue;
      const dataType = firstDataType(asset);
      for (const band of bands) {
        if (band && typeof band.name === 'string' && band.name) {
          sources.push({
            asset: `${key}${separator}${band.name}`,
            names: [band.name],
            dataType,
            ...bandFacts(asset),
          });
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

// `name` put into `value` over the selection `start`–`end`, with a space where
// the neighbours would otherwise run into it; and where the caret goes after.
export function insertName(value: string, start: number, end: number, name: string): { text: string; caret: number } {
  const before = value.slice(0, start);
  const after = value.slice(end);
  const lead = before === '' || /[\s(]$/u.test(before) ? '' : ' ';
  const trail = after === '' || /^[\s),]/u.test(after) ? '' : ' ';
  return { text: `${before}${lead}${name}${trail}${after}`, caret: before.length + lead.length + name.length };
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

// --- scenes and passes (F8, M4-12b) ---------------------------------------------

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

// The scenes of one pass: a group of the results list (`results_group_by`), the
// unit a mosaic job takes (M4-12 F6: one pass, one group, one job).
export interface Pass {
  key: string;
  label: string;
  items: StacItem[];
}

const OTHER_SCENES = 'Other scenes';

// `items` split by the pass of the results list they belong to, in the order of
// the list (newest first). A scene the list does not know — should not happen
// for a live result — shares one pass with the others of its kind, last.
export function passesOf(items: readonly StacItem[], groups: readonly TimeStepGroup[]): Pass[] {
  const byIndex = new Map<number, StacItem[]>();
  for (const item of items) {
    const index = groupIndexOfItem(groups as TimeStepGroup[], item.id);
    byIndex.set(index, [...(byIndex.get(index) ?? []), item]);
  }
  return [...byIndex.entries()]
    .sort(([a], [b]) => (a < 0 ? Infinity : a) - (b < 0 ? Infinity : b))
    .map(([index, passItems]) =>
      index < 0
        ? { key: '', label: OTHER_SCENES, items: passItems }
        : { key: groups[index].key.join('\u0000'), label: groups[index].label, items: passItems },
    );
}

export function isArea(aoi: GeoJSON.Geometry | null): aoi is GeoJSON.Polygon | GeoJSON.MultiPolygon {
  return !!aoi && (aoi.type === 'Polygon' || aoi.type === 'MultiPolygon');
}

// The AOI as the order's schema takes it: `type` and `coordinates`, nothing
// else, every position as `[lon, lat]`. The AOI in the store can carry more — a
// place-search outline has `properties` for the provenance of a download's
// `aoi.geojson` (F3 of M3-07), a GeoJSON geometry may have a `bbox`, a
// position an altitude — and the job API forbids every member it does not
// name (`extra_forbidden`). Whether the shape is valid the server decides.
export function orderAoi(aoi: GeoJSON.Polygon | GeoJSON.MultiPolygon): GeoJSON.Polygon | GeoJSON.MultiPolygon {
  const position = (p: GeoJSON.Position): GeoJSON.Position => [p[0], p[1]];
  const ring = (r: GeoJSON.Position[]) => r.map(position);
  if (aoi.type === 'Polygon') return { type: 'Polygon', coordinates: aoi.coordinates.map(ring) };
  return { type: 'MultiPolygon', coordinates: aoi.coordinates.map((polygon) => polygon.map(ring)) };
}

// B11: a job hands out derived data of the source; only the tier *processing*
// allows it. The server refuses below that (`403`) as well.
export function processingAllowed(collection: Collection | undefined): boolean {
  return collection?.['earthx:license_flags']?.tier === 'processing';
}

// Why "Process" cannot open for this selection, or `null` when it can. No AOI
// is needed: "Whole scene" sends none (M4-13c K1).
export function processBlockReason(
  dataset: { viewable: boolean; collection: Collection } | undefined,
  sceneCount: number,
): string | null {
  if (!dataset?.viewable) return 'Pick a dataset first.';
  if (!processingAllowed(dataset.collection)) {
    const tier = dataset.collection['earthx:license_flags']?.tier ?? 'unknown';
    return `The licence of this dataset does not allow processing (tier: ${tier}).`;
  }
  if (sceneCount === 0) return 'Select a scene first.';
  return null;
}

// What an order covers (M4-13c §3.2): the whole scenes, without `aoi` (the
// server takes the union of their footprints), or only the drawn AOI.
export type Area = 'scene' | 'aoi';

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

// The scenes of a group in one fixed order, so that the same selection is the
// same order text (an estimate belongs to exactly one order, K4). The server
// sorts the list for the mosaic itself (`mosaic_order`).
const orderedIds = (ids: readonly string[]): string[] => [...ids].sort();

export function buildOrder(args: {
  datasetId: string;
  itemIds: readonly string[];
  area: Area;
  aoi: GeoJSON.Geometry | null;
  steps: readonly DraftStep[];
  assets: readonly string[];
  dtype: string;
  info: ProcessInfo;
}): BuiltOrder {
  const { datasetId, itemIds, area, aoi, steps, assets, dtype, info } = args;
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
  if (itemIds.length === 0) problems.push('Pick a pass.');
  if (area === 'aoi' && !isArea(aoi)) problems.push('Draw an area as AOI.');
  if (steps.length === 0) problems.push('Add a step.');
  if (steps.length > info.maxSteps) problems.push(`At most ${info.maxSteps} steps.`);
  if (assets.length === 0) problems.push('Pick at least one band.');
  if (assets.length > info.maxAssets) problems.push(`At most ${info.maxAssets} bands.`);
  if (!dtype) problems.push('Pick an output data type.');
  const stepsOk = stepProblems.every((p) => !p.unsupported && Object.keys(p.errors).length === 0);
  if (problems.length > 0 || !stepsOk) return { order: null, stepProblems, problems };
  return {
    order: {
      recipe_version: 1,
      inputs: [{ name: INPUT_NAME, dataset: datasetId, groups: [orderedIds(itemIds)], assets: [...assets] }],
      ...(area === 'aoi' && isArea(aoi) ? { aoi: orderAoi(aoi) } : {}),
      steps: built,
      output: { kind: 'raster', format: 'cog', dtype },
    },
    stepProblems,
    problems,
  };
}

// What the panel takes from a recipe or an order (M4-19d): the other way round
// from `buildOrder`, which builds the same order again from it.
export interface Draft {
  datasetId: string;
  // One list of scenes per group; the panel's own orders have one.
  groups: string[][];
  aoi: GeoJSON.Polygon | GeoJSON.MultiPolygon | null;
  steps: DraftStep[];
  assets: string[];
  // `null` for an output without a data type (a crop).
  dtype: string | null;
}

// The order as a draft, and what in it the process description does not accept:
// an operator it does not list for the dataset, a parameter its form does not
// know or refuses. `nextKey` hands out the keys of the steps.
export function draftFromOrder(
  order: Order,
  info: ProcessInfo,
  nextKey: () => number,
): { draft: Draft; problems: string[]; notes: string[] } {
  const problems: string[] = [];
  const notes: string[] = [];
  const steps: DraftStep[] = [];
  order.steps.forEach((step, index) => {
    const where = `Step ${index + 1} (${step.op})`;
    // The server still takes an older version of an operator but no longer lists it (M4-24):
    // the step is taken as the listed one, whose form accepts what the older one did.
    const operator =
      info.operators.find((o) => o.op === step.op && o.opVersion === step.op_version) ??
      info.operators.find((o) => o.op === step.op && o.opVersion > step.op_version);
    if (!operator) return void problems.push(`${where}: this operator is not available for this dataset.`);
    if (operator.opVersion !== step.op_version) {
      notes.push(`Step ${index + 1} (${step.op}): version ${step.op_version} is taken as version ${operator.opVersion}.`);
    }
    if (!operator.form.supported) return void problems.push(`${where}: ${operator.form.reason}`);
    const { fields } = operator.form;
    for (const name of Object.keys(step.params)) {
      if (!fields.some((f) => f.name === name)) problems.push(`${where}: unknown parameter ${name}.`);
    }
    const values = initialValues(fields);
    for (const field of fields) {
      const raw = step.params[field.name];
      if (raw === undefined || field.kind === 'const') continue;
      if (field.kind === 'boolean' && typeof raw === 'boolean') values[field.name] = raw;
      else if (field.kind !== 'boolean' && (typeof raw === 'string' || typeof raw === 'number')) values[field.name] = String(raw);
      else problems.push(`${where}: ${field.name} has the wrong type.`);
    }
    for (const [name, message] of Object.entries(paramsFrom(fields, values).errors)) problems.push(`${where}: ${name}: ${message}`);
    steps.push({ key: nextKey(), op: step.op, opVersion: operator.opVersion, values });
  });
  const input = order.inputs[0];
  return {
    draft: {
      datasetId: input.dataset,
      groups: input.groups.map((group) => [...group]),
      aoi: order.aoi ?? null,
      steps,
      assets: [...input.assets],
      dtype: order.output.kind === 'raster' ? order.output.dtype : null,
    },
    problems,
    notes,
  };
}

// A mosaic of the whole scenes of one pass, no steps and no AOI (M4-12 §3.1):
// `api` takes the union of the footprints as the area.
export function buildMosaicOrder(args: {
  datasetId: string;
  itemIds: readonly string[];
  assets: readonly string[];
  dtype: string;
}): Order {
  const { datasetId, itemIds, assets, dtype } = args;
  return {
    recipe_version: 1,
    inputs: [{ name: INPUT_NAME, dataset: datasetId, groups: [orderedIds(itemIds)], assets: [...assets] }],
    steps: [],
    output: { kind: 'raster', format: 'cog', dtype },
  };
}

// The crop of the download dialog as an export job (M4-11 §3.1): the same
// groups, assets and AOI as the refused request, no steps, factor 1 (only that
// factor is offered as a job, M4-11 K5).
export function buildExportOrder(args: {
  datasetId: string;
  groups: readonly (readonly string[])[];
  assets: readonly string[];
  aoi: GeoJSON.Polygon | GeoJSON.MultiPolygon;
}): Order {
  const { datasetId, groups, assets, aoi } = args;
  return {
    recipe_version: 1,
    inputs: [{ name: INPUT_NAME, dataset: datasetId, groups: groups.map((g) => [...g]), assets: [...assets] }],
    aoi: orderAoi(aoi),
    steps: [],
    output: { kind: 'crop', format: 'cog', resolution_factor: 1, extent: 'bbox(aoi ∩ footprints)', mask: 'file' },
  };
}

// The provenance of a place-search AOI (`placeSearch.ts`, M4-11 F4): the three
// fields as the AOI carries them, strings only; `undefined` for a drawn or
// uploaded AOI, which carries none.
export function aoiProvenanceOf(aoi: GeoJSON.Geometry | null): AoiProvenance | undefined {
  const properties = (aoi as { properties?: unknown } | null)?.properties;
  if (!properties || typeof properties !== 'object') return undefined;
  const provenance: AoiProvenance = {};
  for (const key of ['source', 'attribution', 'license'] as const) {
    const value = (properties as Record<string, unknown>)[key];
    if (typeof value === 'string') provenance[key] = value;
  }
  return Object.keys(provenance).length > 0 ? provenance : undefined;
}

// The origin to send with an order (M4-30): that of the AOI, but only where the
// order carries an area. "Whole scene" and a merged pass have none (the server
// takes the union of the footprints, no place-search geometry is in the result),
// and the server refuses an origin without one.
export function aoiProvenanceFor(order: Order, aoi: GeoJSON.Geometry | null): AoiProvenance | undefined {
  return order.aoi ? aoiProvenanceOf(aoi) : undefined;
}

// The step a refusal is about: the server names it as "step <n>" or
// "steps.<n>" (0-based, `processing/recipe.py`, `api/intake.py`). A text about
// the expression that names no step (band math's "expression names unknown
// band(s)") belongs to the band-math step when there is exactly one; anything
// else is about the order as a whole.
export function stepOfRefusal(detail: string, steps: readonly Pick<DraftStep, 'op'>[] = []): number | null {
  const match = /\bsteps?[ .](\d+)\b/u.exec(detail);
  if (match) return Number(match[1]);
  const bandMath = steps.flatMap((step, index) => (step.op === 'band_math' ? [index] : []));
  return bandMath.length === 1 && /\bexpression\b/u.test(detail) ? bandMath[0] : null;
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
