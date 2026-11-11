// The output type of an order (Otto, 12.10.2026): the panel takes the best one
// itself, as the tools of GDAL do — the type of the source data wherever the
// platform can write it — and says which and why. The resampling method is no
// recommendation: it changes the values, the user chooses it (B10).
//
// The nodata of a result (`processing/nodata.py`, plan M5-28): a float type takes
// NaN; an integer type keeps the source's nodata where the steps only pass the
// source's integer values on (`nearest`, `mode`, masks), else it takes an edge of
// the type (`max` unsigned, `min` signed), and a value that would land on it is
// moved by one. A source nodata an integer type cannot hold (swissALTI3D −9999 in
// `uint16`) is refused, so that type is not offered (Otto, 11.11.2026, F7).
// Band math and normalize end in float32 with NaN (Otto, 22.10.2026); an integer
// type after them is offered, not recommended. The process description does not
// state an operator's output type, so the two are named here.

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

// The operators whose result is float32 with NaN as nodata, whatever goes in: why float32 is recommended after them.
const FLOAT_RESULT: Record<string, { gives: string }> = {
  band_math: { gives: 'Band math gives fractions.' },
  normalize: { gives: 'Normalize gives fractions.' },
};

// The values each integer type holds.
const RANGE: Record<string, readonly [number, number]> = {
  uint8: [0, 255],
  uint16: [0, 65535],
  int16: [-32768, 32767],
  uint32: [0, 4294967295],
  int32: [-2147483648, 2147483647],
};

// The nodata of an integer type whose source gives none it can keep.
export const edgeNodata = (dtype: string): number => (RANGE[dtype][0] === 0 ? RANGE[dtype][1] : RANGE[dtype][0]);

// Why `dtype` cannot hold the nodata the source states, or `null` where it can (F7).
export function nodataMisfit(dtype: string, bands: readonly BandSource[]): string | null {
  if (!isIntegerType(dtype)) return null;
  const [low, high] = RANGE[dtype];
  const value = bands.map((band) => band.nodata).find((v) => v !== null && !(Number.isInteger(v) && v >= low && v <= high));
  return value === undefined || value === null ? null : `The source marks missing pixels with ${value}, which ${dtype} cannot hold.`;
}

// The first step of the order that ends in float32, or `undefined`.
const floatResultOf = (steps: readonly StepChoice[]) => {
  const found = steps.find((s) => s.op in FLOAT_RESULT);
  return found ? FLOAT_RESULT[found.op] : undefined;
};

// Whether an integer result keeps the source's nodata: integer bands, unscaled, one nodata, steps that only pick.
const keepsSourceNodata = (steps: readonly StepChoice[], bands: readonly BandSource[]): boolean => {
  const types = new Set(bands.map((band) => band.dataType));
  const type = types.size === 1 ? [...types][0] : null;
  const nodata = new Set(bands.map((band) => band.nodata));
  return (
    bands.length > 0 &&
    type !== null &&
    isIntegerType(type) &&
    !bands.some((band) => band.scaled) &&
    nodata.size === 1 &&
    !nodata.has(null) &&
    !floatResultOf(steps) &&
    !steps.some((s) => s.op === 'reproject' && !PICKING.includes(s.resampling ?? ''))
  );
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

// The types of the schema as options; those a run refuses for sure disabled with the reason. After band math or
// normalize the result bands carry NaN, not the source's nodata, so no type is refused for it.
export function dtypeOptions(args: {
  dtypes: readonly string[];
  steps: readonly StepChoice[];
  bands: readonly BandSource[];
}): DtypeOption[] {
  const floating = floatResultOf(args.steps);
  return args.dtypes.map((value) => {
    const disabledReason = floating ? null : nodataMisfit(value, args.bands);
    return { value, label: disabledReason ? `${value} (nodata does not fit)` : value, disabledReason };
  });
}

// The type the order is sent with: the user's choice while a run does not
// refuse it for sure, else the automatic one.
export function effectiveDtype(chosen: string | null, options: readonly DtypeOption[], automatic: Choice): string {
  const option = options.find((o) => o.value === chosen);
  return option && !option.disabledReason ? option.value : automatic.value;
}

// A note for an integer type that does not keep the source's nodata: which value marks a missing pixel instead.
export function integerNote(dtype: string, steps: readonly StepChoice[], bands: readonly BandSource[]): string | null {
  if (!isIntegerType(dtype) || keepsSourceNodata(steps, bands)) return null;
  return `${dtype} marks missing pixels with ${edgeNodata(dtype)}; a value that would land on it is moved by one. float32 keeps every value.`;
}
