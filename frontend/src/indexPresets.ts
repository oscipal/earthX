// The index presets of a dataset (NM4-14): what the registry offers as one click each (`earthx:index_presets` of the
// collection), read and checked entry by entry like the search filters (`searchFilters.ts`).
//
// Nothing here knows a dataset or an index. A preset fills an ordinary Band math step (`addStep`) and says how a band
// with the same expression is drawn (`presetFor`, D2 of the plan); the server checks the expression and the name when the
// order comes in, as for one typed by hand.

import type { PreviewRange } from './processingPreview';
import { expressionTokens, isExpression } from './processingBands';
import type { Collection } from './types';

export interface IndexPreset {
  // The name of the band the step adds, and the text of the button (`NDVI`).
  name: string;
  title: string;
  // In the band names of the dataset, as a person types it.
  expression: string;
  // How a band with this expression is drawn.
  rescale: [number, number];
  colormapName: string;
  // The formula in the words of Awesome Spectral Indices, and where it comes from.
  formula: string;
  reference: string;
}

// A collection is not changed once it is loaded, and the panel reads its presets on every change of state: read each once.
const read = new WeakMap<Collection, IndexPreset[]>();

// The presets of a dataset, in the order of the registry. An entry that is not complete is left out, with one line on the
// console that names no data: a preset with a made-up range would draw a wrong picture. A backend before NM4-14a sends
// none, which is no preset.
export function indexPresetsOf(collection: Collection | undefined): IndexPreset[] {
  if (!collection) return [];
  const known = read.get(collection);
  if (known) return known;
  const raw = collection['earthx:index_presets'];
  const seen = new Set<string>();
  const found: IndexPreset[] = [];
  for (const entry of Array.isArray(raw) ? raw : []) {
    const preset = describe(entry);
    if (!preset || seen.has(preset.name.toLowerCase())) {
      console.warn('An index preset of the dataset was left out: it is not complete.');
      continue;
    }
    seen.add(preset.name.toLowerCase());
    found.push(preset);
  }
  read.set(collection, found);
  return found;
}

const isText = (value: unknown): value is string => typeof value === 'string' && value.trim() !== '';

function rangeOf(value: unknown): [number, number] | null {
  // `[[low, high]]`, as `earthx:default_render` has it.
  const pair = Array.isArray(value) && value.length === 1 ? value[0] : null;
  if (!Array.isArray(pair) || pair.length !== 2) return null;
  const [low, high] = pair;
  return typeof low === 'number' && typeof high === 'number' && Number.isFinite(low) && Number.isFinite(high) && low < high ? [low, high] : null;
}

function describe(entry: unknown): IndexPreset | null {
  if (typeof entry !== 'object' || entry === null || Array.isArray(entry)) return null;
  const { name, title, expression, rescale, colormap_name: colormapName, formula, reference } = entry as Record<string, unknown>;
  const range = rangeOf(rescale);
  if (!isText(name) || !isText(title) || !isText(expression) || !isText(colormapName) || !isText(formula) || !isText(reference)) return null;
  if (!range || !isExpression(expression)) return null;
  return { name, title, expression, rescale: range, colormapName, formula, reference };
}

// What the button says in its tooltip and to a screen reader (KE2); the source of the formula is in the collection.
export const presetTip = (preset: IndexPreset): string => `${preset.title}: ${preset.formula}. Formula: Awesome Spectral Indices.`;

// The range and colormap a band with the preset's expression is drawn with.
export const presetRange = (preset: IndexPreset): PreviewRange => ({
  vmin: String(preset.rescale[0]),
  vmax: String(preset.rescale[1]),
  colormap: preset.colormapName,
});

// The preset whose expression `expression` is: the same tokens, whatever the spaces (`(nir-red)/(nir+red)` is the same as
// `(nir - red) / (nir + red)`; `(red-nir)/(red+nir)` is not). `null` where no preset of the dataset is.
export function presetFor(presets: readonly IndexPreset[], expression: string | null | undefined): IndexPreset | null {
  const wanted = typeof expression === 'string' ? expressionTokens(expression) : null;
  if (!wanted || wanted.length === 0) return null;
  const key = wanted.join(' ');
  return presets.find((preset) => expressionTokens(preset.expression)?.join(' ') === key) ?? null;
}
