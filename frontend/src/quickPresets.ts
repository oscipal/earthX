// What "Quick processing" offers for a dataset (NM4-14, adr/0030 F7, M5-14): its indices, its composites (three expressions as red,
// green and blue) and its steps of an operator with fixed parameters (a hillshade), all read from the registry (`earthx:index_presets`,
// `earthx:composite_presets`, `earthx:step_presets` of the collection) and checked entry by entry like the search filters.
//
// Nothing here knows a dataset, an index or a product. A preset is the steps the tile runs, the assets they read and the bands the tile
// shows; it fills the view like an index did, and `AppliedRender.index` names it whatever its kind. A step preset is drawn as the
// operator says (adr/0035, `displayLook.ts`), so its look comes from the process description, not from here.

import type { TileStep } from './api';
import { CHANNEL_COUNT, rescaleOfChannels } from './channels';
import { lookRange, type DisplayLook } from './displayLook';
import { indexPresetsOf, presetRange, presetTip, type IndexPreset } from './indexPresets';
import { canonicalJson } from './processing';
import { isExpression } from './processingBands';
import type { ResultStats } from './render';
import type { AppliedRender, Collection } from './types';

export type PresetKind = 'index' | 'composite' | 'step';

// One step of a preset, as a recipe names it.
export interface PresetStep {
  op: string;
  opVersion: number;
  params: Record<string, unknown>;
}

export interface QuickPreset {
  kind: PresetKind;
  // The key of the preset in the look (`AppliedRender.index`): the name of the index, of the composite, of the band a step adds.
  name: string;
  // The text of the button: the name of an index (`NDVI`), the title of the others (`Hillshade`).
  label: string;
  // The tooltip of the button and of the field "Band" while it is shown.
  tip: string;
  steps: PresetStep[];
  // The assets the steps read, in the order they first name them.
  assets: string[];
  // The band the tile shows, or three for red, green and blue.
  bands: string[];
  // The index this preset is (its expression, range and colormap), `null` for a composite or a step.
  index: IndexPreset | null;
  // The range of each channel of a composite, red, green, blue; `null` for the others.
  channels: [number, number][] | null;
}

// The names an expression reads, in the order it first names them (a preset names no function). The registry checks that each is a band
// of the dataset, and the assets are called like their bands.
const IDENTIFIER = /(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*/gu;
export function assetsOfExpression(expression: string): string[] {
  return [...new Set(expression.match(IDENTIFIER) ?? [])];
}

// The steps of a preset as the tile route takes them.
export const tileStepsOf = (preset: QuickPreset): TileStep[] =>
  preset.steps.map((step) => ({ op: step.op, opVersion: step.opVersion, paramsJson: canonicalJson(step.params) }));

// The band or bands the tile shows: one name, or three for a colour picture.
export const shownBandsOf = (preset: QuickPreset): string | string[] => (preset.bands.length === 1 ? preset.bands[0] : preset.bands);

const CHANNEL_ENDS = ['_r', '_g', '_b'];
const isText = (value: unknown): value is string => typeof value === 'string' && value.trim() !== '';
const isObject = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);
const isPair = (value: unknown): value is [number, number] =>
  Array.isArray(value) && value.length === 2 && value.every((n) => typeof n === 'number' && Number.isFinite(n)) && value[0] < value[1];

export function presetOfIndex(index: IndexPreset): QuickPreset {
  return {
    kind: 'index',
    name: index.name,
    label: index.name,
    tip: presetTip(index),
    steps: [{ op: 'band_math', opVersion: 2, params: { expression: index.expression, name: index.name } }],
    assets: assetsOfExpression(index.expression),
    bands: [index.name],
    index,
    channels: null,
  };
}

function ofComposite(entry: unknown): QuickPreset | null {
  if (!isObject(entry)) return null;
  const { name, title, expressions, rescale } = entry;
  if (!isText(name) || !isText(title) || !Array.isArray(expressions) || expressions.length !== CHANNEL_COUNT) return null;
  if (!expressions.every((e): e is string => isText(e) && isExpression(e))) return null;
  if (!Array.isArray(rescale) || rescale.length !== CHANNEL_COUNT || !rescale.every(isPair)) return null;
  const bands = CHANNEL_ENDS.map((end) => `${name}${end}`);
  return {
    kind: 'composite',
    name,
    label: title,
    tip: `${title}: ${expressions.join(', ')} as red, green and blue.`,
    steps: expressions.map((expression, at) => ({ op: 'band_math', opVersion: 2, params: { expression, name: bands[at] } })),
    assets: [...new Set(expressions.flatMap(assetsOfExpression))],
    bands,
    index: null,
    channels: rescale.map((pair) => [pair[0], pair[1]] as [number, number]),
  };
}

// The assets a step reads: the bands it names (`bands`, `band`), which are assets of the data where the step stands first.
function assetsOfParams(params: Record<string, unknown>): string[] {
  const named = [...(Array.isArray(params.bands) ? params.bands : []), params.band];
  return [...new Set(named.filter(isText))];
}

function ofStep(entry: unknown): QuickPreset | null {
  if (!isObject(entry)) return null;
  const { name, title, op, op_version: opVersion, params } = entry;
  if (!isText(name) || !isText(title) || !isText(op) || typeof opVersion !== 'number' || !Number.isInteger(opVersion) || !isObject(params)) return null;
  if (params.name !== name) return null;
  const assets = assetsOfParams(params);
  if (assets.length === 0) return null;
  return {
    kind: 'step',
    name,
    label: title,
    tip: `${title} of ${assets.join(', ')}.`,
    steps: [{ op, opVersion, params: { ...params } }],
    assets,
    bands: [name],
    index: null,
    channels: null,
  };
}

// A collection is not changed once it is loaded, and the view reads its presets on every change of state: read each once.
const read = new WeakMap<Collection, QuickPreset[]>();

// The presets of a dataset: its indices, then its composites, then its steps, each in the order of the registry. An entry that is not
// complete is left out with one line on the console that names no data: a preset with a made-up range would draw a wrong picture.
export function quickPresetsOf(collection: Collection | undefined): QuickPreset[] {
  if (!collection) return [];
  const known = read.get(collection);
  if (known) return known;
  const found: QuickPreset[] = indexPresetsOf(collection).map(presetOfIndex);
  const seen = new Set(found.map((preset) => preset.name.toLowerCase()));
  const take = (raw: unknown, describe: (entry: unknown) => QuickPreset | null) => {
    for (const entry of Array.isArray(raw) ? raw : []) {
      const preset = describe(entry);
      if (!preset || seen.has(preset.name.toLowerCase())) {
        console.warn('A preset of the dataset was left out: it is not complete.');
        continue;
      }
      seen.add(preset.name.toLowerCase());
      found.push(preset);
    }
  };
  take(collection['earthx:composite_presets'], ofComposite);
  take(collection['earthx:step_presets'], ofStep);
  read.set(collection, found);
  return found;
}

// The preset a look names, among the presets of the dataset; `null` for a look without one (or one the dataset lacks).
export function presetOfLook(look: Pick<AppliedRender, 'index'>, collection: Collection | undefined): QuickPreset | null {
  if (!look.index) return null;
  return quickPresetsOf(collection).find((preset) => preset.name === look.index) ?? null;
}

// The look the fields take when the preset is chosen. An index and a composite bring their ranges; a step brings the look of its
// operator (`look`), its range from what was measured of the band where the look is not fixed. `null` where the range is not known yet:
// the look of a step whose band has not been measured, or that the description has not told.
export function lookOfPreset(preset: QuickPreset, look: DisplayLook | null = null, stats: ResultStats | null = null): AppliedRender | null {
  if (preset.index) {
    const { vmin, vmax, colormap } = presetRange(preset.index);
    return { index: preset.name, colormapName: colormap, rescale: `${vmin},${vmax}` };
  }
  if (preset.channels) {
    const rescale = rescaleOfChannels(preset.channels.map(([low, high]) => ({ vmin: String(low), vmax: String(high) })));
    return rescale ? { index: preset.name, rescale } : null;
  }
  const range = look ? lookRange(look, stats) : null;
  return range ? { index: preset.name, colormapName: range.colormap, rescale: `${range.vmin},${range.vmax}` } : null;
}

// Whether the preset is drawn as a colour picture.
export const isComposite = (preset: QuickPreset | null): boolean => preset?.kind === 'composite';
