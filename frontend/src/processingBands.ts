// The stock of bands the panel works with (adr/0020 §4, §6, §9): the bands of the data, the bands that
// `band_math` steps add, and the choice of those that go into the result. Pure functions; the state lives in
// `processingStore.ts`, the order is built in `processingOrder.ts`.

import type { BandSource, DraftStep } from './processingOrder';
import { namesIn } from './schemaForm';

// The longest name of a band a step adds (`band_math.MAX_NAME_CHARS`): it fits on a chip.
export const MAX_NAME_LENGTH = 32;

const NAME = /^[A-Za-z][A-Za-z0-9_]{0,31}$/u;

// `keyword.kwlist` of Python 3.12: `ast.parse` reads these as syntax, so an expression could not name such a band.
const PYTHON_KEYWORDS = new Set(
  ('False None True and as assert async await break class continue def del elif else except finally for from global if ' +
    'import in is lambda nonlocal not or pass raise return try while with yield').split(' '),
);

// The functions of an expression (`band_math.FUNCTIONS`).
const FUNCTIONS = new Set(['where', 'abs', 'minimum', 'maximum', 'sqrt']);

// The names a source offers in an expression: its band names, or its own key where the item does not describe the
// bands (the platform then counts the asset as one band named like the key).
export function bandNamesOf(source: BandSource): string[] {
  return source.names.length > 0 ? source.names : [source.asset];
}

// Which asset carries a band name; a name two assets carry (two Zarr groups can both have `b04`) belongs to none: the
// order does not choose for the person.
export function ownersOf(sources: readonly BandSource[]): Map<string, string> {
  const owners = new Map<string, string | null>();
  for (const source of sources) {
    for (const name of bandNamesOf(source)) owners.set(name, owners.has(name) ? null : source.asset);
  }
  const unique = new Map<string, string>();
  for (const [name, asset] of owners) if (asset !== null) unique.set(name, asset);
  return unique;
}

// The assets that carry `names`, in the item's order. A name no asset carries (a result, a typo) is left out.
export function assetsCarrying(sources: readonly BandSource[], names: Iterable<string>): string[] {
  const owners = ownersOf(sources);
  const wanted = new Set<string>();
  for (const name of names) {
    const asset = owners.get(name);
    if (asset !== undefined) wanted.add(asset);
  }
  return sources.map((s) => s.asset).filter((asset) => wanted.has(asset));
}

// --- the names of results -------------------------------------------------------------

// Why `name` cannot be the name of a band a step adds, or `null`. `others` are the other results of the chain,
// `data` every band of the data, the ones nobody reads included; both ignore case, as the server does.
export function nameProblem(name: string, others: readonly string[], data: readonly string[]): string | null {
  if (name === '') return 'Enter a name.';
  if (!NAME.test(name)) return `A letter, then letters, digits or _, at most ${MAX_NAME_LENGTH} characters.`;
  if (PYTHON_KEYWORDS.has(name)) return `${name} is a Python keyword, so an expression cannot use it.`;
  if (FUNCTIONS.has(name)) return `${name} is a function, so an expression cannot use it as a band.`;
  const folded = name.toLowerCase();
  if (data.some((d) => d.toLowerCase() === folded)) return `${name} is a band of the data.`;
  if (others.some((o) => o.toLowerCase() === folded)) return `${name} is used twice.`;
  return null;
}

// The default name of the band a new `band_math` step adds: `Band_Math_<n>`, `n` the place of the step in the chain
// from 1, the next free number from there if that name is taken.
export function defaultName(place: number, taken: readonly string[]): string {
  const folded = new Set(taken.map((name) => name.toLowerCase()));
  let n = place;
  while (folded.has(`band_math_${n}`)) n += 1;
  return `Band_Math_${n}`;
}

export const isBandMath = (step: Pick<DraftStep, 'op'>): boolean => step.op === 'band_math';

// The name a `band_math` step adds, as typed.
export function resultNameOf(step: DraftStep): string {
  return typeof step.values.name === 'string' ? step.values.name : '';
}

// The results of the chain: the name of each `band_math` step, in step order, with the step's key.
export function resultsOf(steps: readonly DraftStep[]): Array<{ key: number; name: string }> {
  return steps.filter(isBandMath).map((step) => ({ key: step.key, name: step.applied ?? resultNameOf(step) }));
}

// The names an expression mentions that are not followed by `(`: the same reading the chips use.
const IDENTIFIER = /(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*/gu;

// `expression` with the band `from` called `to`, token by token (a longer name that contains it stays).
export function renameInExpression(expression: string, from: string, to: string): string {
  return expression.replace(IDENTIFIER, (token) => (token === from ? to : token));
}

// `steps` after the band `from`, which the step `key` adds, has been renamed `to`: the later expressions and the
// `bands` of later `normalize` steps name it anew. Earlier steps cannot see the band and stay as they are.
export function renameResult(steps: readonly DraftStep[], key: number, from: string, to: string): DraftStep[] {
  const at = steps.findIndex((step) => step.key === key);
  return steps.map((step, index) => {
    if (index <= at) return step;
    if (isBandMath(step) && typeof step.values.expression === 'string') {
      const expression = renameInExpression(step.values.expression, from, to);
      return expression === step.values.expression ? step : { ...step, values: { ...step.values, expression } };
    }
    if (step.op === 'normalize' && typeof step.values.bands === 'string') {
      const names = namesIn(step.values.bands);
      if (!names.includes(from)) return step;
      return { ...step, values: { ...step.values, bands: names.map((name) => (name === from ? to : name)).join(', ') } };
    }
    return step;
  });
}

// `normalize` steps without the band `name`, which a removed step added.
export function dropFromNormalize(steps: readonly DraftStep[], name: string): DraftStep[] {
  return steps.map((step) => {
    if (step.op !== 'normalize' || typeof step.values.bands !== 'string') return step;
    const names = namesIn(step.values.bands);
    return names.includes(name) ? { ...step, values: { ...step.values, bands: names.filter((n) => n !== name).join(', ') } } : step;
  });
}

// --- the output ---------------------------------------------------------------------------

// The bands of the result in the order of the file: the results of the steps in step order, then the bands of the
// data in the order of the item, then whatever else was asked for (a loaded recipe can name a band this selection lacks;
// the server says so). One order for one choice, so that one choice is one order (an estimate belongs to exactly one).
export function outputBands(checked: readonly string[], results: readonly string[], data: readonly string[]): string[] {
  const wanted = new Set(checked);
  const known = new Set([...results, ...data]);
  return [
    ...results.filter((name) => wanted.has(name)),
    ...data.filter((name) => wanted.has(name) && !results.includes(name)),
    ...checked.filter((name) => !known.has(name)),
  ];
}
