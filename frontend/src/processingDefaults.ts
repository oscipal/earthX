// What the processing panel recommends where the order has a choice (Otto,
// 12.10.2026) — the one place both recommendations live. The API and the recipe
// keep `resampling` and the output type without a default (B10); the panel
// pre-selects the recommendation, marks it "(recommended)" and always sends the
// value explicitly.
//
// Resampling (plans/m4-13-processing-panel.md §12 for the sources):
//  - a dataset without the capability `interpolation` → nearest;
//  - a band the item marks as classes or bit fields (STAC classification
//    extension) → nearest, for the whole step, since one step has one method;
//  - anything else (continuous values) → bilinear.
//
// Output data type — what a run accepts, from `processing/core.py::_nodata_for`:
// a float type always (NaN is its nodata); an integer type only when every band
// of the result carries one finite nodata value. Band math ends in float32 with
// NaN, so an integer type after it is refused for sure and not offered. A
// reprojection keeps the nodata of its input, which the source file states and
// the item may; nearest on integer bands keeps their values, any interpolation
// does not.

import type { BandSource } from './processingOrder';

export interface Recommendation {
  value: string;
  // One English sentence for the form, saying why.
  reason: string;
}

export const INTEGER_TYPES: readonly string[] = ['uint8', 'uint16', 'int16', 'uint32', 'int32'];

export const isIntegerType = (dtype: string): boolean => INTEGER_TYPES.includes(dtype);

// --- resampling ------------------------------------------------------------------

export function recommendResampling(args: {
  interpolation: boolean | undefined;
  bands: readonly BandSource[];
}): Recommendation {
  if (!args.interpolation) {
    return { value: 'nearest', reason: 'This dataset does not allow interpolation.' };
  }
  if (args.bands.some((band) => band.classified)) {
    return { value: 'nearest', reason: 'A band in the order holds classes or bit fields; nearest keeps their values.' };
  }
  return { value: 'bilinear', reason: 'The bands hold continuous values.' };
}

// --- output data type --------------------------------------------------------------

export interface StepChoice {
  op: string;
  // The resampling the step will be sent with, where it has one.
  resampling?: string;
}

export const AFTER_BAND_MATH =
  'Band math ends in float32 with NaN as nodata, which an integer type cannot hold.';

export function recommendDtype(args: {
  steps: readonly StepChoice[];
  bands: readonly BandSource[];
  allowed: readonly string[];
}): Recommendation {
  const { steps, bands, allowed } = args;
  const float32 = (reason: string): Recommendation => ({ value: allowed.includes('float32') ? 'float32' : (allowed[0] ?? ''), reason });
  if (steps.some((s) => s.op === 'band_math')) return float32('Band math gives fractions.');
  const reprojections = steps.filter((s) => s.op === 'reproject');
  if (reprojections.some((s) => s.resampling !== 'nearest')) {
    return float32('Interpolating gives fractional values.');
  }
  // Nearest only: the values stay, so the type of the input can stay — when the
  // item says the run will take it.
  const types = new Set(bands.map((band) => band.dataType));
  const type = types.size === 1 ? [...types][0] : null;
  const nodata = new Set(bands.map((band) => band.nodata));
  const keeps =
    reprojections.length > 0 &&
    bands.length > 0 &&
    type !== null &&
    isIntegerType(type) &&
    allowed.includes(type) &&
    bands.every((band) => !band.scaled) &&
    nodata.size === 1 &&
    !nodata.has(null);
  if (keeps && type) {
    return { value: type, reason: `Nearest keeps the values of the ${type} input, and the item states its nodata value.` };
  }
  return float32('The source does not state that it can stay an integer type; float32 always works.');
}

export interface DtypeOption {
  value: string;
  label: string;
  recommended: boolean;
  // Why it cannot be chosen; the option is shown, disabled, with this text.
  disabledReason: string | null;
}

// The types of the schema as options: the recommended one marked, those a run
// refuses for sure disabled with the reason.
export function dtypeOptions(args: {
  dtypes: readonly string[];
  steps: readonly StepChoice[];
  recommended: Recommendation;
}): DtypeOption[] {
  const afterBandMath = args.steps.some((s) => s.op === 'band_math');
  return args.dtypes.map((value) => {
    const disabledReason = afterBandMath && isIntegerType(value) ? AFTER_BAND_MATH : null;
    const recommended = value === args.recommended.value;
    const label = recommended ? `${value} (recommended)` : disabledReason ? `${value} (not after band math)` : value;
    return { value, label, recommended, disabledReason };
  });
}

// The type the order is sent with: the user's choice while a run does not
// refuse it for sure, else the recommendation.
export function effectiveDtype(
  chosen: string | null,
  options: readonly DtypeOption[],
  recommended: Recommendation,
): string {
  const option = options.find((o) => o.value === chosen);
  return option && !option.disabledReason ? option.value : recommended.value;
}

// A note for an integer type that is not surely taken: the run needs one nodata
// value that every band states (`core._nodata_for`), which only the source file
// knows for sure.
export function integerNote(dtype: string, steps: readonly StepChoice[], bands: readonly BandSource[]): string | null {
  if (!isIntegerType(dtype) || steps.some((s) => s.op === 'band_math')) return null;
  const nodata = new Set(bands.map((band) => band.nodata));
  if (bands.length > 0 && nodata.size === 1 && !nodata.has(null)) return null;
  return `${dtype} needs a nodata value that the source file states for every band; the job fails otherwise. float32 always works.`;
}
