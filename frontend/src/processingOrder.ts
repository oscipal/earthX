// What the processing panel reads off a process description and a selection,
// and how it builds an order from them (M4-13 §3.3–§3.5). Pure functions; the
// panel's state lives in `processingStore.ts`.

import { intersection } from 'polyclip-ts';
import type { Geom } from 'polyclip-ts';

import { footprintOf, polygonBbox } from './geoUtils';
import { bboxesOverlap } from './aoiClip';
import { groupIndexOfItem } from './grouping';
import type { AoiProvenance, JsonSchema, Order, OrderStep, ProcessDescription } from './processing';
import { bandNamesOf, isBandMath, nameProblem, ownersOf, resultNameOf } from './processingBands';
import { initialValues, paramsForm, paramsFrom, type FieldValue, type ParamsForm } from './schemaForm';
import type { Collection, EarthxMask, StacAsset, StacBand, StacItem, TimeStepGroup } from './types';

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
  // The unit of each of `names`, in step with them (the item's own, else the registry's); `unit` is the one of an
  // asset with no names. `null` where nobody states one (M4-19b).
  units: Array<string | null>;
  unit: string | null;
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

// The registry's unit for an asset key (`earthx:band_units`): the exact key, else a key with a `*` that matches. The
// same lookup as `DatasetConfig.band_unit`.
export function registryUnit(collection: Collection | undefined, key: string): string | null {
  const units = collection?.['earthx:band_units'];
  if (!isObject(units)) return null;
  const entry = (value: unknown) => (typeof value === 'string' && value ? value : null);
  if (Object.hasOwn(units, key)) return entry(units[key]);
  for (const [pattern, unit] of Object.entries(units)) {
    if (!pattern.includes('*')) continue;
    const parts = pattern.split('*').map((part) => part.replace(/[.+?^${}()|[\]\\]/gu, '\\$&'));
    if (new RegExp(`^${parts.join('.*')}$`, 'su').test(key)) return entry(unit);
  }
  return null;
}

// The unit to write beside a band: none for "1", the unit of a dimensionless quantity (Otto, 24.10.2026). The data
// keep "1" (`bands[].unit`, `earthx:band_units`); this is the one place a frontend display turns a unit into text,
// so that the chips of the panel and whatever shows units later (M4-19c) agree.
export function shownUnit(unit: string | null | undefined): string | null {
  return typeof unit === 'string' && unit !== '' && unit !== '1' ? unit : null;
}

// The unit an item states for one of its bands, if it does.
function itemUnit(band: StacBand | undefined): string | null {
  return band && typeof band.unit === 'string' && band.unit ? band.unit : null;
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
export function bandSources(
  item: StacItem,
  format: string | null | undefined,
  separator: string | null,
  collection?: Collection,
): BandSource[] {
  const sources: BandSource[] = [];
  for (const [key, asset] of Object.entries(item.assets ?? {})) {
    if (format === 'cog') {
      if (!isGeoTiff(asset)) continue;
      const count = bandCount(asset);
      const names = count === null ? [] : count === 1 ? [key] : Array.from({ length: count }, (_, i) => `${key}_${i + 1}`);
      const registry = registryUnit(collection, key);
      const described = bandsOf(asset);
      const units = names.map((_, i) => itemUnit(described?.[i]) ?? registry);
      sources.push({ asset: key, names, units, unit: registry, dataType: firstDataType(asset), ...bandFacts(asset) });
    } else if (format === 'zarr') {
      const bands = asset.bands;
      if (!separator || !Array.isArray(bands)) continue;
      const dataType = firstDataType(asset);
      for (const band of bands) {
        if (band && typeof band.name === 'string' && band.name) {
          const unit = itemUnit(band) ?? registryUnit(collection, `${key}${separator}${band.name}`);
          sources.push({
            asset: `${key}${separator}${band.name}`,
            names: [band.name],
            units: [unit],
            unit,
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

// --- which assets are bands (NM4-07) ----------------------------------------------

// `earthx:auxiliary_assets` of the collection: what the registry says is no band. Nothing guessed from the names.
export function auxiliaryAssetsOf(collection: Collection | undefined): string[] {
  const raw: unknown = collection?.['earthx:auxiliary_assets'];
  return Array.isArray(raw) ? raw.filter((key): key is string => typeof key === 'string') : [];
}

// The assets that are bands of the data, in the item's order — not the auxiliary assets of the registry and not the layer
// of the mask: those are in the output list, but not part of "All" and not checked for the person.
export function selectableAssets(
  sources: readonly BandSource[],
  auxiliary: readonly string[],
  maskLayerAsset: string | null,
): string[] {
  return sources.map((s) => s.asset).filter((asset) => asset !== maskLayerAsset && !auxiliary.includes(asset));
}

// The one band of a dataset that has only one, so the panel can check it on opening; `null` otherwise. An asset with
// several bands is not "one band", even where it is the only asset.
export function lonelyBand(selectable: readonly string[], sources: readonly BandSource[]): string | null {
  const only = selectable.length === 1 ? sources.find((s) => s.asset === selectable[0]) : undefined;
  return only && only.names.length <= 1 ? bandNamesOf(only)[0] : null;
}

// A band of the data as the output list and the chips show it (adr/0020 §14).
export interface DataBand {
  name: string;
  asset: string;
  // The unit to write beside the name, `null` for none (`shownUnit`).
  unit: string | null;
  // What the registry says is no band (`visual`, `preview`): offered only where the order has it already.
  auxiliary: boolean;
  // The layer of the mask: in the list, never checked for the person.
  layer: boolean;
}

// Every band of the data, in the item's order; a name two assets carry is left out, the order cannot name it.
export function dataBandsOf(
  sources: readonly BandSource[],
  auxiliary: readonly string[],
  maskLayerAsset: string | null,
): DataBand[] {
  const owners = ownersOf(sources);
  return sources.flatMap((source) =>
    bandNamesOf(source).flatMap((name, index) =>
      owners.get(name) === source.asset
        ? [{
            name,
            asset: source.asset,
            unit: shownUnit(source.names.length === 0 ? source.unit : source.units[index]),
            auxiliary: auxiliary.includes(source.asset),
            layer: source.asset === maskLayerAsset,
          }]
        : [],
    ),
  );
}

// --- the layer a mask reads (M4-18c) ----------------------------------------------

const isInteger = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value);

// `earthx:mask` of the collection, or `null` where the dataset has none or the field is
// not what the registry writes. Only https references are kept: the panel links to it.
export function maskLayerOf(collection: Collection | undefined): EarthxMask | null {
  const raw: unknown = collection?.['earthx:mask'];
  if (!isObject(raw)) return null;
  const { asset, band, classes, suggested, reference, note } = raw;
  if (typeof asset !== 'string' || !asset || typeof band !== 'string' || !band) return null;
  if (!Array.isArray(classes) || classes.length === 0) return null;
  const known = classes.flatMap((entry: unknown) =>
    isObject(entry) && isInteger(entry.value) && typeof entry.label === 'string' ? [{ value: entry.value, label: entry.label }] : [],
  );
  if (known.length !== classes.length) return null;
  const values = new Set(known.map((entry) => entry.value));
  return {
    asset,
    band,
    classes: known,
    suggested: Array.isArray(suggested) ? suggested.filter((v): v is number => isInteger(v) && values.has(v)) : [],
    reference: typeof reference === 'string' && reference.startsWith('https://') ? reference : '',
    note: typeof note === 'string' ? note : '',
  };
}

// What a new mask step starts with: the layer's band, which the recipe names but the user does
// not type, and the classes the dataset suggests — ticked, not decided: the recipe lists exactly
// the classes ticked when it is sent (K6).
export function maskStepValues(layer: EarthxMask): Record<string, FieldValue> {
  return { source: layer.band, classes: [...layer.suggested].sort((a, b) => a - b).join(', ') };
}

// The asset the order has to read for its mask steps, or `null` without one.
export function maskAssetOf(steps: readonly Pick<DraftStep, 'op'>[], layer: EarthxMask | null): string | null {
  return layer && steps.some((step) => step.op === 'mask') ? layer.asset : null;
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

// Why the job cannot start while the output holds no band (adr/0020 §9).
export const EMPTY_OUTPUT = 'Pick at least one band for the output.';

// The scenes of a group in one fixed order, so that the same selection is the
// same order text (an estimate belongs to exactly one order, K4). The server
// sorts the list for the mosaic itself (`mosaic_order`).
const orderedIds = (ids: readonly string[]): string[] => [...ids].sort();

// What a step reads that is no band at its place: the field and a short hint, or `null`. An expression may name the bands
// of the data and the results of the steps before it, nothing else; a `normalize` step likewise names only such bands
// (review of #250). Where the data list no bands there is nothing to compare with.
export function readProblem(
  step: DraftStep,
  index: number,
  steps: readonly DraftStep[],
  data: readonly string[],
): { field: 'expression' | 'bands'; message: string } | null {
  const field = step.op === 'normalize' ? 'bands' : 'expression';
  const names =
    step.op === 'band_math' && typeof step.values.expression === 'string'
      ? namesInExpression(step.values.expression)
      : step.op === 'normalize' && typeof step.values.bands === 'string'
        ? new Set(step.values.bands.split(/[\s,;]+/u).filter((n) => n !== ''))
        : new Set<string>();
  const results = steps.flatMap((s, i) => (isBandMath(s) ? [{ index: i, name: resultNameOf(s) }] : []));
  for (const result of results) {
    if (result.index < index || !names.has(result.name) || data.includes(result.name)) continue;
    return { field, message: result.index === index ? `'${result.name}' is the band this step adds` : `'${result.name}' is added by a later step` };
  }
  if (step.op !== 'band_math' || data.length === 0) return null;
  const known = new Set([...data, ...results.filter((r) => r.index < index).map((r) => r.name)]);
  const unknown = [...names].find((name) => !known.has(name));
  return unknown === undefined ? null : { field, message: `'${unknown}' is not a band name` };
}

// What is wrong with a step beyond its form fields, by field (adr/0020 §6): the name of the band a `band_math` step adds,
// and what the step reads that is no band at its place.
function bandProblems(step: DraftStep, index: number, steps: readonly DraftStep[], data: readonly string[]): Record<string, string> {
  const errors: Record<string, string> = {};
  if (isBandMath(step)) {
    const others = steps.flatMap((s, i) => (i !== index && isBandMath(s) ? [resultNameOf(s)] : []));
    const problem = nameProblem(resultNameOf(step), others, data);
    if (problem) errors.name = problem;
  }
  const read = readProblem(step, index, steps, data);
  if (read) errors[read.field] = read.message;
  return errors;
}

export function buildOrder(args: {
  datasetId: string;
  itemIds: readonly string[];
  area: Area;
  aoi: GeoJSON.Geometry | null;
  steps: readonly DraftStep[];
  // The bands of the output in the order of the file, and every band of the data (the names a result may not take).
  bands: readonly string[];
  data: readonly string[];
  dtype: string;
  info: ProcessInfo;
}): BuiltOrder {
  const { datasetId, itemIds, area, aoi, steps, bands, data, dtype, info } = args;
  const problems: string[] = [];
  const built: OrderStep[] = [];
  const stepProblems: StepProblem[] = steps.map((step, index) => {
    const operator = info.operators.find((o) => o.op === step.op && o.opVersion === step.opVersion);
    if (!operator) return { errors: {}, unsupported: 'this operator is not available for this dataset' };
    if (!operator.form.supported) return { errors: {}, unsupported: operator.form.reason };
    const { params, errors } = paramsFrom(operator.form.fields, step.values);
    built.push({ op: step.op, op_version: step.opVersion, params });
    return { errors: { ...errors, ...bandProblems(step, index, steps, data) } };
  });
  if (itemIds.length === 0) problems.push('Pick a pass.');
  if (area === 'aoi' && !isArea(aoi)) problems.push('Draw an area as AOI.');
  if (steps.length === 0) problems.push('Add a step.');
  if (steps.length > info.maxSteps) problems.push(`At most ${info.maxSteps} steps.`);
  if (bands.length === 0) problems.push(EMPTY_OUTPUT);
  if (!dtype) problems.push('Pick an output data type.');
  const stepsOk = stepProblems.every((p) => !p.unsupported && Object.keys(p.errors).length === 0);
  if (problems.length > 0 || !stepsOk) return { order: null, stepProblems, problems };
  return {
    order: {
      recipe_version: 2,
      inputs: [{ name: INPUT_NAME, dataset: datasetId, groups: [orderedIds(itemIds)] }],
      ...(area === 'aoi' && isArea(aoi) ? { aoi: orderAoi(aoi) } : {}),
      steps: built,
      output: { kind: 'raster', format: 'cog', dtype, bands: [...bands] },
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
  // The bands of the output; empty for a crop, which names assets.
  bands: string[];
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
      // The classes of a mask: the order holds them as a list, the form as the text it would have been typed as.
      else if (field.kind === 'integers' && Array.isArray(raw) && raw.every((n) => typeof n === 'number')) values[field.name] = raw.join(', ');
      // The bands of a normalize step, likewise.
      else if (field.kind === 'names' && Array.isArray(raw) && raw.every((n) => typeof n === 'string')) values[field.name] = raw.join(', ');
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
      bands: order.output.kind === 'raster' ? [...order.output.bands] : [],
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
  bands: readonly string[];
  dtype: string;
}): Order {
  const { datasetId, itemIds, bands, dtype } = args;
  return {
    recipe_version: 2,
    inputs: [{ name: INPUT_NAME, dataset: datasetId, groups: [orderedIds(itemIds)] }],
    steps: [],
    output: { kind: 'raster', format: 'cog', dtype, bands: [...bands] },
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
    recipe_version: 2,
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
