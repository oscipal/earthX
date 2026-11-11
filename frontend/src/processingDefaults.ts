// The output type of an order (Otto, 12.10.2026; offered only where it makes sense, Otto, 11.11.2026). Which types make sense follows from
// one rule, whether the steps only pass the values of the source on, and that rule is the operator registry's: each step of the process
// description says it (`x-earthx-passes-values`, `operators/base.py::PassesValues`); the panel has no list of its own.
//  - Values unchanged (choosing bands, a crop, a mask, a reprojection with `nearest` or `mode`, the mosaic of whole scenes): the type of
//    the source and float32; the type of the source first.
//  - Values computed anew (Band math, an index, Normalize, an interpolating reprojection, a source whose scale the core applies): float32
//    only, an integer type would round them away (a ratio of 0.25 to 1 becomes 0 and 1); a source of float64 offers float64 first and
//    float32 (Otto, 11.11.2026).
// A type the chain no longer allows gives way to float32, without a word. What the server accepts is unchanged (M5-28): the nodata of an
// integer result is the source's where the values pass, which the type of the source always holds.

import type { BandSource, Operator } from './processingOrder';

export interface Choice {
  value: string;
  // One English sentence for the form, saying why.
  reason: string;
}

export const INTEGER_TYPES: readonly string[] = ['uint8', 'uint16', 'int16', 'uint32', 'int32'];

export const isIntegerType = (dtype: string): boolean => INTEGER_TYPES.includes(dtype);

const FLOAT32 = 'float32';
const FLOAT64 = 'float64';

export interface StepChoice {
  op: string;
  // The values of the step as they will be sent: what a rule of a parameter reads (`resampling`).
  values?: Record<string, unknown>;
}

// `x-earthx-passes-values` of a step: always, never, or while a parameter is one of the values.
export type PassesRule = boolean | { param: string; in: readonly string[] };

// Whether every step writes only values it read, by the rule of its operator; a step the description does not know does not.
export function passesValues(steps: readonly StepChoice[], operators: readonly Pick<Operator, 'op' | 'passesValues'>[]): boolean {
  return steps.every((step) => {
    const rule = operators.find((operator) => operator.op === step.op)?.passesValues ?? false;
    return typeof rule === 'boolean' ? rule : rule.in.includes(String(step.values?.[rule.param] ?? ''));
  });
}

export interface DtypeOption {
  value: string;
  label: string;
}

interface Args {
  steps: readonly StepChoice[];
  bands: readonly BandSource[];
  allowed: readonly string[];
  operators: readonly Pick<Operator, 'op' | 'passesValues'>[];
}

// The type of the source the result can keep, with the reason; `null` with the reason where only float32 makes sense.
function sourceType({ steps, bands, allowed, operators }: Args): { type: string | null; reason: string } {
  const types = new Set(bands.map((band) => band.dataType));
  const type = types.size === 1 ? [...types][0] : null;
  const scaled = bands.some((band) => band.scaled);
  if (!passesValues(steps, operators)) {
    // A source of float64 keeps its type for values computed anew too (Otto, 11.11.2026); every other one takes float32.
    if (type === FLOAT64 && !scaled && allowed.includes(FLOAT64)) return { type, reason: 'Same type as the source data (float64); the steps compute new values.' };
    return { type: null, reason: 'The steps compute new values; float32 keeps them.' };
  }
  if (scaled) return { type: null, reason: 'The source values are scaled to physical values; float32 keeps them.' };
  if (types.size > 1) return { type: null, reason: 'The bands have different types; float32 holds them all.' };
  if (type === null || !allowed.includes(type)) return { type: null, reason: 'The item does not state a type the result can keep; float32 always works.' };
  return { type, reason: `Same type as the source data (${type}).` };
}

// The types that make sense for the order: the type of the source first where the values pass, and float32.
export function dtypeOptions(args: Args): DtypeOption[] {
  const { type } = sourceType(args);
  const float = args.allowed.includes(FLOAT32) ? FLOAT32 : (args.allowed[0] ?? '');
  return [...new Set([type, float].filter((value): value is string => !!value))].map((value) => ({ value, label: value }));
}

// The type the order is sent with unless the user changes it: the first that makes sense.
export function chooseDtype(args: Args): Choice {
  const { reason } = sourceType(args);
  return { value: dtypeOptions(args)[0]?.value ?? '', reason };
}

// The type the order is sent with: the user's choice while it makes sense, else float32 (the last of the options).
export function effectiveDtype(chosen: string | null, options: readonly DtypeOption[], automatic: Choice): string {
  if (chosen === null) return automatic.value;
  return options.some((o) => o.value === chosen) ? chosen : (options.at(-1)?.value ?? automatic.value);
}
