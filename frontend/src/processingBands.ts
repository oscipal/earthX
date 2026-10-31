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

// Why `name` cannot be the name of a band a step adds, or `null`: a short hint for the field, with the name quoted.
// `others` are the other results of the chain, `data` every band of the data, the ones nobody reads included; both ignore
// case, as the server does.
export function nameProblem(name: string, others: readonly string[], data: readonly string[]): string | null {
  if (name === '') return 'Enter a name';
  if (!NAME.test(name)) return `Use letters, digits and _, a letter first, at most ${MAX_NAME_LENGTH} characters`;
  if (PYTHON_KEYWORDS.has(name)) return `'${name}' cannot be used in an expression`;
  if (FUNCTIONS.has(name)) return `'${name}' is the name of a function`;
  const folded = name.toLowerCase();
  if (data.some((d) => d.toLowerCase() === folded)) return `'${name}' is already a band name`;
  if (others.some((o) => o.toLowerCase() === folded)) return `'${name}' is already used by another step`;
  return null;
}

// The default name of the band a new `band_math` step adds: `result`, and `result_1`, `result_2` … where that is taken
// (adr/0020 §6, Otto 30.10.2026), the first one that is free among the bands of the data and the other results.
export function defaultName(taken: readonly string[]): string {
  const folded = new Set(taken.map((name) => name.toLowerCase()));
  if (!folded.has('result')) return 'result';
  let n = 1;
  while (folded.has(`result_${n}`)) n += 1;
  return `result_${n}`;
}

export const isBandMath = (step: Pick<DraftStep, 'op'>): boolean => step.op === 'band_math';

// The name a `band_math` step adds, as typed.
export function resultNameOf(step: DraftStep): string {
  return typeof step.values.name === 'string' ? step.values.name : '';
}

// The results of the chain: the name of each `band_math` step, in step order, with the step's key.
export function resultsOf(steps: readonly DraftStep[]): Array<{ key: number; name: string }> {
  return steps.filter(isBandMath).map((step) => ({ key: step.key, name: resultNameOf(step) }));
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

// --- the colour picture (NM4-64) ---------------------------------------------------------

// The entry "RGB" of the dropdowns "Show" and "Band": the three bands of `earthx:true_color` as one colour picture. Its
// value is no band name (a name starts with a letter), so that it cannot be taken for a band.
export const RGB = '@rgb';
export const RGB_LABEL = 'RGB';

// The text of a band of the dropdowns and of a preview's name: a band is called by its name, the colour picture "RGB".
export const bandLabel = (band: string): string => (band === RGB ? RGB_LABEL : band);

// --- the band a picture starts with --------------------------------------------------------

// The band the preview and a result layer start with (Otto, 31.10.2026): the result created last, else the first band.
// `results` are the results among `choices`, `created` says which was created later (the larger number).
export function startBand(choices: readonly string[], results: ReadonlyArray<{ name: string; created: number }>): string | null {
  const last = results.reduce<{ name: string; created: number } | null>((a, r) => (a === null || r.created > a.created ? r : a), null);
  return last?.name ?? choices[0] ?? null;
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

// --- the shape of an expression ----------------------------------------------------------

// What an expression of band math may be made of (`band_math.py`: numbers, bands, `+ - * / **`, comparisons, `& | ~`, and
// calls such as `where(c, a, b)`). Only the shape is checked here, so that a text like "red red" or "nir -" is told at once; which
// names are bands, and whether the types fit, `readProblem` and the server say.
const TOKEN = /\s*(?:(\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+)|([A-Za-z_][A-Za-z0-9_]*)|(\*\*|<=|>=|==|!=|[-+*/<>&|~(),]))/uy;

type Token = { kind: 'number' | 'name' | 'op'; text: string };

function tokens(text: string): Token[] | null {
  const found: Token[] = [];
  TOKEN.lastIndex = 0;
  while (TOKEN.lastIndex < text.length) {
    if (/^\s*$/u.test(text.slice(TOKEN.lastIndex))) break;
    const match = TOKEN.exec(text);
    if (!match) return null;
    found.push(match[1] !== undefined ? { kind: 'number', text: match[1] } : match[2] !== undefined ? { kind: 'name', text: match[2] } : { kind: 'op', text: match[3] });
  }
  return found;
}

// The tokens of an expression as text, whitespace left out; `null` where the text has something that is no token.
export function expressionTokens(text: string): string[] | null {
  return tokens(text)?.map((token) => token.text) ?? null;
}

const BINARY = new Set(['+', '-', '*', '/', '**', '<', '<=', '>', '>=', '==', '!=', '&', '|']);
const UNARY = new Set(['+', '-', '~']);

// Whether `text` is built like an expression: operands joined by binary operators, signs and `~` in front of an operand,
// parentheses and calls that close, and nothing left over. An empty text is not one.
export function isExpression(text: string): boolean {
  const all = tokens(text);
  if (!all || all.length === 0) return false;
  let at = 0;
  const is = (op: string) => all[at]?.kind === 'op' && all[at].text === op;
  const operand = (): boolean => {
    while (all[at]?.kind === 'op' && UNARY.has(all[at].text)) at += 1;
    const token = all[at];
    if (!token) return false;
    if (token.kind === 'number') {
      at += 1;
      return true;
    }
    if (token.kind === 'name') {
      at += 1;
      if (!is('(')) return true;
      at += 1;
      if (!sum()) return false;
      while (is(',')) {
        at += 1;
        if (!sum()) return false;
      }
      if (!is(')')) return false;
      at += 1;
      return true;
    }
    if (token.text !== '(') return false;
    at += 1;
    if (!sum()) return false;
    if (!is(')')) return false;
    at += 1;
    return true;
  };
  const sum = (): boolean => {
    if (!operand()) return false;
    while (all[at]?.kind === 'op' && BINARY.has(all[at].text)) {
      at += 1;
      if (!operand()) return false;
    }
    return true;
  };
  return sum() && at === all.length;
}

