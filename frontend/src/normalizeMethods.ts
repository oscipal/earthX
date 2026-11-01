// The methods of a `normalize` step, version 3 (NM4-11b): the form the schema cannot give (its fields depend on the
// method), the rules between the fields, and how the numbers the route of NM4-19 measured become the `measured` of the
// step. The server decides (`422`); this is the help while typing. Pure functions; the state lives in `processingStore.ts`.

import type { AreaStatistics } from './api';
import type { Field, FieldValue, ParamsForm } from './schemaForm';

export type Method = 'linear' | 'percentile' | 'zscore' | 'robust';

export const METHODS: ReadonlyArray<{ value: Method; label: string; help: string; formula: string }> = [
  {
    value: 'linear',
    label: 'Fixed range',
    help: 'Your own start and end values become the target range.',
    formula: '(x − from) / (to − from) × (max − min) + min',
  },
  {
    value: 'percentile',
    label: 'Percentile stretch',
    help: 'The values at the chosen percentiles of the AOI become the target range.',
    formula: '(x − p_low) / (p_high − p_low) × (max − min) + min, with the values at the percentiles, measured over the AOI',
  },
  {
    value: 'zscore',
    label: 'Z-score',
    help: 'Mean 0 and standard deviation 1 over the AOI.',
    formula: '(x − mean) / standard deviation, measured over the AOI (population standard deviation)',
  },
  {
    value: 'robust',
    label: 'Robust (median, IQR)',
    help: 'Median 0 and interquartile range 1 over the AOI; outliers weigh little.',
    formula: '(x − median) / (p75 − p25), measured over the AOI',
  },
];

export const EXAMPLE = 'Rescale values, e.g. NDVI −1…1 → 0…1.';

export const BAND_TIP = 'The bands to rescale, each with numbers of its own. The others stay as they are.';

// The tooltip of "Method": what the step is for, then the chosen method with its formula, then one sentence per method.
export function methodTip(method: string): string {
  const chosen = METHODS.find((m) => m.value === method);
  return [EXAMPLE, chosen && `${chosen.label}: ${chosen.formula}.`, METHODS.map((m) => `${m.label}: ${m.help}`).join('\n')]
    .filter(Boolean)
    .join('\n\n');
}

// The pairs of percentiles the panel offers (plan KE1); 0 and 100 are the minimum and the maximum of the AOI.
export const RANGES: ReadonlyArray<{ low: number; high: number }> = [
  { low: 0, high: 100 },
  { low: 1, high: 99 },
  { low: 2, high: 98 },
  { low: 5, high: 95 },
];
export const DEFAULT_RANGE = RANGES[2];
export const rangeLabel = (range: { low: number; high: number }): string => `${range.low}–${range.high} %`;

export const isMethod = (value: unknown): value is Method => METHODS.some((m) => m.value === value);
export const isStatistical = (method: unknown): boolean => isMethod(method) && method !== 'linear';
export const methodOf = (values: Readonly<Record<string, FieldValue>>): Method | null => (isMethod(values.method) ? values.method : null);

// What each method takes besides `method` and `bands`, in the order the form shows them.
const FIELDS: Readonly<Record<Method, readonly string[]>> = {
  linear: ['in_min', 'in_max', 'out_min', 'out_max', 'clip'],
  percentile: ['low', 'high', 'out_min', 'out_max', 'clip'],
  zscore: [],
  robust: [],
};

export function fieldsOfMethod(fields: readonly Field[], method: unknown): Field[] {
  const wanted = isMethod(method) ? FIELDS[method] : [];
  return fields
    .filter((f) => f.name === 'method' || f.name === 'bands' || wanted.includes(f.name))
    .map((f) => (wanted.includes(f.name) ? { ...f, required: true } : f));
}

// The values a fresh step starts with, over the empty ones of the form: a fixed range as before, 2–98 % ready for the stretch.
export function startValues(): Record<string, FieldValue> {
  return { method: 'linear', low: String(DEFAULT_RANGE.low), high: String(DEFAULT_RANGE.high) };
}

// A step taken from an older version: version 2 was the fixed range, with the fields of `linear` and nothing measured.
export const upgradedValues = (values: Record<string, FieldValue>): Record<string, FieldValue> => ({
  ...values,
  method: 'linear',
  low: values.low || String(DEFAULT_RANGE.low),
  high: values.high || String(DEFAULT_RANGE.high),
});

// Rules between the fields the schema cannot say.
export function refineNormalize(params: Record<string, unknown>, errors: Record<string, string>): void {
  const { method, in_min: inMin, in_max: inMax, out_min: outMin, out_max: outMax, low, high } = params;
  if (method === 'linear' && typeof inMin === 'number' && typeof inMax === 'number' && !(inMin < inMax) && !errors.in_max) {
    errors.in_max = '“From” must be below “to”.';
  }
  if ((method === 'linear' || method === 'percentile') && typeof outMin === 'number' && outMin === outMax && !errors.out_max) {
    errors.out_max = 'The two ends of the target range differ.';
  }
  if (method === 'percentile') {
    if (typeof low === 'number' && !RANGES.some((r) => r.low === low) && !errors.low) errors.low = 'Pick one of the ranges.';
    if (typeof high === 'number' && !RANGES.some((r) => r.high === high) && !errors.high) errors.high = 'Pick one of the ranges.';
  }
}

// --- the form ------------------------------------------------------------------------------------------------------

const isObject = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);

// The fields of `normalize` version 3, if the schema is the one this panel knows (the properties and the methods);
// else the operator stays in the menu, disabled, with the reason, like any schema the panel cannot read.
export function normalizeForm(schema: unknown): ParamsForm {
  const properties = isObject(schema) && isObject(schema.properties) ? schema.properties : {};
  const method = properties.method;
  const known = METHODS.map((m) => m.value) as string[];
  const methods = isObject(method) && Array.isArray(method.enum) ? method.enum : [];
  if (!known.every((m) => methods.includes(m)) || methods.length !== known.length) {
    return { supported: false, reason: 'not supported by this panel: the methods of normalize' };
  }
  const missing = ['bands', 'measured', 'in_min', 'in_max', 'out_min', 'out_max', 'low', 'high', 'clip'].find((name) => !(name in properties));
  if (missing) return { supported: false, reason: `not supported by this panel: ${missing} of normalize` };
  const text = (name: string): { description?: string } => {
    const d = isObject(properties[name]) ? properties[name].description : undefined;
    return typeof d === 'string' ? { description: d } : {};
  };
  const optionHelp = Object.fromEntries(METHODS.map((m) => [m.value, m.help]));
  const field = (name: string, title: string, kind: Field['kind'], extra: Partial<Field> = {}): Field => ({
    name,
    kind,
    title,
    required: false,
    ...text(name),
    ...extra,
  });
  return {
    supported: true,
    fields: [
      field('method', 'Method', 'enum', { required: true, options: METHODS.map((m) => m.value), optionHelp }),
      field('bands', 'Bands', 'names', { required: true, minItems: 1 }),
      field('in_min', 'From', 'number'),
      field('in_max', 'To', 'number'),
      field('low', 'Range', 'integer', { minimum: 0, maximum: 5 }),
      field('high', 'Range', 'integer', { minimum: 95, maximum: 100 }),
      field('out_min', 'Min', 'number'),
      field('out_max', 'Max', 'number'),
      field('clip', 'Clip', 'boolean'),
    ],
  };
}

// --- the measure ---------------------------------------------------------------------------------------------------

// The numbers of one band, as the recipe holds them (`measured.bands.<name>`).
export type BandNumbers = Record<string, number>;
export interface Measured {
  factor: number;
  bands: Record<string, BandNumbers>;
}

const number = (statistics: Record<string, unknown>, key: string): number | null => {
  const value = statistics[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
};

// The numbers a method takes from the statistics of a band, or `null` where the band has none (no valid value, or a
// standard deviation that is not finite).
export function bandNumbers(method: Method, low: number, high: number, statistics: Record<string, unknown>): BandNumbers | null {
  const pick = (names: Record<string, string>): BandNumbers | null => {
    const result: BandNumbers = {};
    for (const [target, source] of Object.entries(names)) {
      const value = number(statistics, source);
      if (value === null) return null;
      result[target] = value;
    }
    return result;
  };
  if (method === 'percentile') {
    return pick({ p_low: low === 0 ? 'minimum' : `percentile_${low}`, p_high: high === 100 ? 'maximum' : `percentile_${high}` });
  }
  if (method === 'zscore') return pick({ mean: 'mean', stddev: 'stddev' });
  if (method === 'robust') return pick({ p25: 'percentile_25', median: 'percentile_50', p75: 'percentile_75' });
  return null;
}

// `measured` of a step from the answer of the route, or the bands it has no numbers for.
export function measuredFrom(
  method: Method,
  low: number,
  high: number,
  bands: readonly string[],
  answer: AreaStatistics,
): { measured: Measured } | { without: string[] } {
  const result: Record<string, BandNumbers> = {};
  const without: string[] = [];
  for (const name of bands) {
    const found = answer.bands.find((band) => band.name === name);
    const numbers = found ? bandNumbers(method, low, high, found.statistics) : null;
    if (numbers) result[name] = numbers;
    else without.push(name);
  }
  return without.length > 0 ? { without } : { measured: { factor: Math.max(1, Math.round(answer.factor)), bands: result } };
}

// --- what is said ------------------------------------------------------------------------------------------------

export const NO_AOI = 'Draw an AOI; the values are measured over it';
export const AFTER_REPROJECT = 'Move Normalize above Reproject; the values are measured before a reprojection';
export const MEASURING = 'Measuring…';

export const coarserNote = (factor: number): string => `measured on a read ${factor} times coarser`;

const shortNumber = (value: number): string => String(Number(value.toPrecision(4)));

// The tooltip of the measured values: the formula of the method with the numbers of each band.
export function measuredText(method: Method, measured: Measured): string {
  const lines = Object.entries(measured.bands).map(([name, n]) => {
    if (method === 'percentile') return `${name}: p_low ${shortNumber(n.p_low)}, p_high ${shortNumber(n.p_high)}`;
    if (method === 'zscore') return `${name}: mean ${shortNumber(n.mean)}, standard deviation ${shortNumber(n.stddev)}`;
    return `${name}: p25 ${shortNumber(n.p25)}, median ${shortNumber(n.median)}, p75 ${shortNumber(n.p75)}`;
  });
  return [...lines, ...(measured.factor > 1 ? [`${coarserNote(measured.factor)[0].toUpperCase()}${coarserNote(measured.factor).slice(1)}.`] : [])].join('\n');
}
