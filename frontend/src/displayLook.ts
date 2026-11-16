// How the band a step makes is drawn (M5-10, Otto, 16.11.2026): a colormap and where the colours start and end, told by the registry of the
// operator in the process description (`x-earthx-looks`, `operators/base.py::Looks`). Nothing here knows a product or a dataset: a terrain
// product is drawn as the registry says, in a preview, a result layer and a pinned layer alike.

import { DEFAULT_PERCENT, type Percent } from './percentRange';
import type { PreviewRange } from './processingPreview';
import { scaleOf, type ResultStats } from './render';

export interface DisplayLook {
  colormap: string;
  // `measured`: the usual scale of the measure (2nd to 98th percentile); `percentiles`: `low` to `high` percent of it; `fixed`: the same
  // numbers everywhere.
  scale: 'measured' | 'percentiles' | 'fixed';
  low?: number;
  high?: number;
}

// The looks of an operator by the value of one of the parameters of its step (`terrain`: `product`).
export interface OperatorLooks {
  param: string;
  by: Record<string, DisplayLook>;
}

const isObject = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const isNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);

function lookOf(value: unknown): DisplayLook | null {
  if (!isObject(value) || typeof value.colormap !== 'string' || value.colormap === '') return null;
  if (value.scale === 'measured') return { colormap: value.colormap, scale: 'measured' };
  const { low, high } = value;
  if ((value.scale !== 'fixed' && value.scale !== 'percentiles') || !isNumber(low) || !isNumber(high) || !(low < high)) return null;
  if (value.scale === 'percentiles' && (low < 0 || high > 100)) return null;
  return { colormap: value.colormap, scale: value.scale, low, high };
}

// `x-earthx-looks` of a step; `null` where the description says none. A look that is not complete is left out: one with a made-up range
// would draw a wrong picture.
export function looksOfOperator(value: unknown): OperatorLooks | null {
  if (!isObject(value) || typeof value.param !== 'string' || !isObject(value.by)) return null;
  const by = Object.fromEntries(Object.entries(value.by).flatMap(([name, look]) => {
    const read = lookOf(look);
    return read ? [[name, read] as const] : [];
  }));
  return Object.keys(by).length > 0 ? { param: value.param, by } : null;
}

// The look of the band a step makes, from the parameters of the step; `null` where the operator has none or does not know the value.
export function lookOfStep(looks: OperatorLooks | null | undefined, params: Record<string, unknown>): DisplayLook | null {
  const value = looks ? params[looks.param] : undefined;
  return looks && typeof value === 'string' ? (Object.hasOwn(looks.by, value) ? looks.by[value] : null) : null;
}

const same = (a: number | undefined, b: number): boolean => a !== undefined && Math.abs(a - b) < 1e-9;

// The range and colormap the look draws a band with, given what was measured of it. `fixed` needs no measure; the others `null` without
// one. Of a measure only the minimum, the 2nd and the 98th percentile and the maximum are known, so `percentiles` is 0–100 or 2–98 (the
// other pairs fall back to the usual scale).
export function lookRange(look: DisplayLook, stats: ResultStats | null): PreviewRange | null {
  if (look.scale === 'fixed') return { vmin: String(look.low), vmax: String(look.high), colormap: look.colormap };
  const present = stats?.bands.filter((band) => band.minimum !== null && band.maximum !== null) ?? [];
  if (look.scale === 'percentiles' && same(look.low, 0) && same(look.high, 100) && present.length > 0) {
    const low = Math.min(...present.map((band) => band.minimum!));
    const high = Math.max(...present.map((band) => band.maximum!));
    if (low < high) return { vmin: String(low), vmax: String(high), colormap: look.colormap };
  }
  const usual = scaleOf(stats ? { ...stats, expression: false } : null);
  return usual ? { vmin: String(usual.low), vmax: String(usual.high), colormap: look.colormap } : null;
}

// What "Auto-scale" puts in the fields of a range typed in percentiles: the percentiles of the look, else the usual 2 to 98. A fixed range
// is no percentiles: it is the values.
export function percentOfLook(look: DisplayLook | null): Percent {
  return look?.scale === 'percentiles' ? { low: String(look.low), high: String(look.high) } : DEFAULT_PERCENT;
}
