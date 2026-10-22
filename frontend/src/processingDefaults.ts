// The output type of an order (Otto, 12.10.2026): the panel takes the best one
// itself, as the tools of GDAL do — the type of the source data wherever the
// platform can write it — and says which and why. The resampling method is no
// recommendation: it changes the values, the user chooses it (B10).
//
// What a run accepts (`processing/core.py::_nodata_for`): a float type always
// (NaN is its nodata); an integer type only when every band of the result
// carries one finite nodata value. Band math ends in float32 with NaN, so an
// integer type after it is refused for sure and not offered. A reprojection
// keeps the nodata of its input, which the source *file* states and the item
// may; `nearest` and `mode` on integer bands keep their values (they only pick
// one), any interpolation does not (the core rounds a fraction when it writes an
// integer). `normalize` ends in float32 with NaN like band math (Otto, 22.10.2026); the
// process description does not state an operator's output type, so the two are named here.

import type { BandSource } from './processingOrder';

export interface Choice {
  value: string;
  // One English sentence for the form, saying why.
  reason: string;
}

export const INTEGER_TYPES: readonly string[] = ['uint8', 'uint16', 'int16', 'uint32', 'int32'];
export const FLOAT_TYPES: readonly string[] = ['float32', 'float64'];

export const isIntegerType = (dtype: string): boolean => INTEGER_TYPES.includes(dtype);

// The resampling methods that only pick a source value (M4-24, Otto 20.10.2026).
const PICKING: readonly string[] = ['nearest', 'mode'];

export interface StepChoice {
  op: string;
  // The resampling the step will be sent with, where it has one; empty while the user has chosen none.
  resampling?: string;
}

export const AFTER_BAND_MATH =
  'Band math ends in float32 with NaN as nodata, which an integer type cannot hold.';
export const AFTER_NORMALIZE =
  'Normalize ends in float32 with NaN as nodata, which an integer type cannot hold.';

// The operators whose result is float32 with NaN as nodata, whatever goes in: what they give,
// why no integer type is offered after them, and how the option is labelled.
const FLOAT_RESULT: Record<string, { gives: string; after: string; label: string }> = {
  band_math: { gives: 'Band math gives fractions.', after: AFTER_BAND_MATH, label: 'not after band math' },
  normalize: { gives: 'Normalize gives fractions.', after: AFTER_NORMALIZE, label: 'not after normalize' },
};

// The first step of the order that ends in float32, or `undefined`.
const floatResultOf = (steps: readonly StepChoice[]) => {
  const found = steps.find((s) => s.op in FLOAT_RESULT);
  return found ? FLOAT_RESULT[found.op] : undefined;
};

// The type the order is sent with unless the user changes it. An order without
// steps — the mosaic of whole scenes (M4-12b) — copies the source values, so it
// keeps an integer type under the same condition as `nearest` does.
export function chooseDtype(args: {
  steps: readonly StepChoice[];
  bands: readonly BandSource[];
  allowed: readonly string[];
}): Choice {
  const { steps, bands, allowed } = args;
  const float32 = (reason: string): Choice => ({
    value: allowed.includes('float32') ? 'float32' : (allowed[0] ?? ''),
    reason,
  });
  const floating = floatResultOf(steps);
  if (floating) return float32(floating.gives);
  const types = new Set(bands.map((band) => band.dataType));
  const type = types.size === 1 ? [...types][0] : null;
  const interpolating = steps.some((s) => s.op === 'reproject' && !PICKING.includes(s.resampling ?? ''));
  const scaled = bands.some((band) => band.scaled);
  // A float source stays what it is, interpolated or not.
  if (type !== null && FLOAT_TYPES.includes(type) && allowed.includes(type) && !scaled) {
    return { value: type, reason: `Same type as the source data (${type}).` };
  }
  if (interpolating) return float32('Interpolating gives fractional values, which an integer type would cut off.');
  const nodata = new Set(bands.map((band) => band.nodata));
  const keeps =
    bands.length > 0 &&
    type !== null &&
    isIntegerType(type) &&
    allowed.includes(type) &&
    !scaled &&
    nodata.size === 1 &&
    !nodata.has(null);
  if (keeps && type) return { value: type, reason: `Same type as the source data (${type}); the item states its nodata value.` };
  return float32('The item does not tell that the source can stay an integer type; float32 always works.');
}

export interface DtypeOption {
  value: string;
  label: string;
  // Why it cannot be chosen; the option is shown, disabled, with this text.
  disabledReason: string | null;
}

// The types of the schema as options; those a run refuses for sure disabled with the reason.
export function dtypeOptions(args: { dtypes: readonly string[]; steps: readonly StepChoice[] }): DtypeOption[] {
  const floating = floatResultOf(args.steps);
  return args.dtypes.map((value) => {
    const disabledReason = floating && isIntegerType(value) ? floating.after : null;
    return { value, label: floating && disabledReason ? `${value} (${floating.label})` : value, disabledReason };
  });
}

// The type the order is sent with: the user's choice while a run does not
// refuse it for sure, else the automatic one.
export function effectiveDtype(chosen: string | null, options: readonly DtypeOption[], automatic: Choice): string {
  const option = options.find((o) => o.value === chosen);
  return option && !option.disabledReason ? option.value : automatic.value;
}

// A note for an integer type that is not surely taken: the run needs one nodata
// value that every band states (`core._nodata_for`), which only the source file
// knows for sure.
export function integerNote(dtype: string, steps: readonly StepChoice[], bands: readonly BandSource[]): string | null {
  if (!isIntegerType(dtype) || floatResultOf(steps)) return null;
  const nodata = new Set(bands.map((band) => band.nodata));
  if (bands.length > 0 && nodata.size === 1 && !nodata.has(null)) return null;
  return `${dtype} needs a nodata value that the source file states for every band; the job fails otherwise. float32 always works.`;
}
