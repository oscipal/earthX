// An order or recipe of version 1 written as version 2 (adr/0020 §11, NM4-43e): the rule of
// `backend/earthx/processing/upgrade.py`, in the browser, for a `recipe.json` the user picks, a permalink and the
// copies of the orders a browser keeps.
//
// Version 2 has a stock of named bands that `band_math` adds to and `output.bands` that says what the result holds.
// Version 1 had no stock: `band_math` replaced all bands by one, `mask` removed its layer, `normalize` took every band,
// and what was left at the end was the output. The rewrite follows the bands through the steps and writes down what
// version 1 did implicitly:
//
// 1. Every `band_math` gets a name: the last one `band_math` as before, the earlier ones `band_math_<n>`. An expression
//    that names `band_math` meant the result of the step before, and now names it.
// 2. `normalize` gets as `bands` the bands it saw. `mask` keeps its parameters; `output.bands` leaves its layer out, as
//    the end of version 1 did.
// 3. `output.bands` is the stock at the end of the chain.
// 4. An order for a raster loses `assets` (the platform derives them).
//
// The values are those of version 1 except after `reproject` version 2 or 3, which warped all bands in one go and see
// fewer bands now (the runner says so, adr/0016). A pure function over JSON data: it reads no registry and no value of
// the document goes into a refusal.

import { renameInExpression } from './processingBands';

export const CONVERTED_NOTE = 'Converted from recipe version 1.';

type Document = Record<string, unknown>;

// The names of the bands of one asset key, as far as the caller knows them.
export type NamesOf = (key: string) => readonly string[];

const record = (value: unknown): value is Document => typeof value === 'object' && value !== null && !Array.isArray(value);

// Whether `document` says `recipe_version` 1 (a number, as the server reads it).
export function isVersion1(document: unknown): boolean {
  return record(document) && typeof document.recipe_version === 'number' && document.recipe_version === 1;
}

// The names an asset key carries when nothing else is known: itself, or the variables of a Zarr key
// `<asset><separator><variables>`, separated by commas.
export function keyNames(separator: string | null): NamesOf {
  return (key) => {
    if (separator !== null && key.includes(separator)) {
      const variables = key.slice(key.indexOf(separator) + separator.length).split(',').filter((v) => v !== '');
      return variables.length > 0 ? variables : [key];
    }
    return [key];
  };
}

const BANDS_STEPS = ['band_math', 'mask', 'normalize'];

// The steps of version 2 and the stock after them, or `null` for a document that is no version 1.
function chain(document: Document, stock: string[]): { steps: Document[]; stock: string[] } | null {
  const steps = document.steps;
  if (!Array.isArray(steps)) return null;
  const total = steps.filter((step) => record(step) && step.op === 'band_math').length;
  let seen = 0;
  let previous: string | null = null;
  let current = stock;
  const rewritten: Document[] = [];
  for (const raw of steps) {
    if (!record(raw)) return null;
    const step: Document = { ...raw };
    const { op, op_version: version, params } = step;
    if (typeof op === 'string' && BANDS_STEPS.includes(op) && (version !== 1 || !record(params))) return null;
    if (version !== 1 || !record(params)) {
      rewritten.push(step);
      continue;
    }
    if (op === 'band_math') {
      seen += 1;
      const name = seen === total ? 'band_math' : `band_math_${seen}`;
      let expression = params.expression;
      if (previous !== null && typeof expression === 'string') expression = renameInExpression(expression, 'band_math', previous);
      step.op_version = 2;
      step.params = { expression, name };
      current = [name];
      previous = name;
    } else if (op === 'mask') {
      current = current.filter((name) => name !== params.source);
      step.op_version = 2;
    } else if (op === 'normalize') {
      step.op_version = 2;
      step.params = { ...params, bands: [...current] };
    }
    rewritten.push(step);
  }
  return { steps: rewritten, stock: current };
}

// An order of version 1 as an order of version 2, or `null` for a document that is no order of version 1.
// `namesOf` gives the band names of an asset key; without it every asset is one band named like its key, which holds for
// the datasets of the platform. An order for a crop has no stock and only changes its version.
export function upgradeOrder(document: unknown, namesOf: NamesOf = keyNames(null)): Document | null {
  if (!isVersion1(document) || !record(document)) return null;
  const { inputs, output } = document;
  if (!Array.isArray(inputs) || inputs.length === 0 || !inputs.every(record) || !record(output)) return null;
  if (output.kind !== 'raster') return { ...document, recipe_version: 2 };
  const stock: string[] = [];
  for (const input of inputs) {
    const assets = input.assets;
    if (!Array.isArray(assets) || !assets.every((asset) => typeof asset === 'string')) return null;
    for (const asset of assets as string[]) {
      for (const name of namesOf(asset)) if (!stock.includes(name)) stock.push(name);
    }
  }
  const built = chain(document, stock);
  if (!built) return null;
  return {
    ...document,
    recipe_version: 2,
    inputs: inputs.map(({ assets: _assets, ...rest }) => rest),
    steps: built.steps,
    output: { ...output, bands: built.stock },
  };
}
