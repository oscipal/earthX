// "vmin" and "vmax" as percentiles (NM4-65 part 4, Otto, 31.10.2026): next to the fields a small switch "value / %". With "%"
// the person types percentiles (2 and 98, say); the values come from the statistics of the band, and what is drawn is always
// the values (a tile asks for `rescale`). Whole percents from 0 to 100: 0 is the minimum, 100 the maximum, the rest the
// `percentile_N` of the statistics (the tiler measures all whole percents, `adr/0006` Nachtrag NM4-65).

export type RangeUnit = 'value' | 'percent';

// What was typed, as typed: the look keeps it, so that the settings show "%" again where they were saved with it.
export interface Percent {
  low: string;
  high: string;
}

// The usual stretch: the 2nd to the 98th percentile.
export const DEFAULT_PERCENT: Percent = { low: '2', high: '98' };

export const PERCENT_PROBLEMS = {
  number: 'Enter whole percents from 0 to 100 for both ends.',
  order: 'The lower percentile must be below the upper one.',
};

const WHOLE = /^\d{1,3}$/u;

// The two percentiles as numbers, or the reason they are none.
export function checkPercent(percent: Percent): { low: number; high: number } | { problem: string } {
  const low = percent.low.trim();
  const high = percent.high.trim();
  if (!WHOLE.test(low) || !WHOLE.test(high)) return { problem: PERCENT_PROBLEMS.number };
  const [a, b] = [Number(low), Number(high)];
  if (a > 100 || b > 100) return { problem: PERCENT_PROBLEMS.number };
  if (a >= b) return { problem: PERCENT_PROBLEMS.order };
  return { low: a, high: b };
}

// The same two, kept as a look: `null` where they are not a valid pair.
export function percentOf(text: Percent | undefined | null): Percent | null {
  if (!text) return null;
  const checked = checkPercent(text);
  return 'problem' in checked ? null : { low: String(checked.low), high: String(checked.high) };
}

export const samePercent = (a: Percent | null | undefined, b: Percent | null | undefined): boolean => (a?.low ?? '') === (b?.low ?? '') && (a?.high ?? '') === (b?.high ?? '');

const finite = (value: unknown): number | null => (typeof value === 'number' && Number.isFinite(value) ? value : null);

// The value at whole percent `n` of one band's statistics, in either of the two spellings (`min`/`max` of the tiler,
// `minimum`/`maximum` of a results document); `null` where the statistics do not name it.
export function valueAtPercent(stats: Record<string, unknown>, n: number): number | null {
  if (n === 0) return finite(stats.minimum) ?? finite(stats.min);
  if (n === 100) return finite(stats.maximum) ?? finite(stats.max);
  return finite(stats[`percentile_${n}`]);
}

// One range for the bands a picture draws (one shared stretch, as `render.ts::autoRescale`): the lowest of the low
// percentiles up to the highest of the high ones. `null` where a band does not name a value or the range would be empty.
export function rescaleAtPercent(bands: readonly Record<string, unknown>[], percent: { low: number; high: number }): [number, number] | null {
  const usable = bands.filter((band) => (finite(band.count) ?? 1) > 0);
  if (usable.length === 0) return null;
  const lows = usable.map((band) => valueAtPercent(band, percent.low));
  const highs = usable.map((band) => valueAtPercent(band, percent.high));
  if (lows.some((v) => v === null) || highs.some((v) => v === null)) return null;
  const low = Math.min(...(lows as number[]));
  const high = Math.max(...(highs as number[]));
  return low < high ? [low, high] : null;
}

// Said where the statistics have no range for the percentiles: a constant band, or one without a valid pixel.
export const NO_RANGE_AT_PERCENT = 'The statistics give no range for these percentiles.';
