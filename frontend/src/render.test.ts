import { describe, expect, it } from 'vitest';

import type { BandStatistics } from './api';
import { autoRescale, scaleOf, type BandStats } from './render';

function stats(...bands: Array<Pick<BandStatistics, 'percentile_2' | 'percentile_98'>>): Record<string, BandStatistics> {
  const out: Record<string, BandStatistics> = {};
  bands.forEach((b, i) => {
    out[`b${i + 1}`] = { min: 0, max: 255, ...b };
  });
  return out;
}

describe('autoRescale', () => {
  it('is the band\'s own percentile range for a single-band asset', () => {
    expect(autoRescale(stats({ percentile_2: 12, percentile_98: 240 }))).toEqual([12, 240]);
  });

  it('spans the min-of-2/max-of-98 across a multi-band asset (rescale broadcasts one pair)', () => {
    expect(
      autoRescale(
        stats(
          { percentile_2: 10, percentile_98: 200 },
          { percentile_2: 5, percentile_98: 220 },
          { percentile_2: 8, percentile_98: 180 },
        ),
      ),
    ).toEqual([5, 220]);
  });

  it('is null for an empty statistics answer', () => {
    expect(autoRescale({})).toBeNull();
  });

  it('ignores a band whose percentiles are not finite numbers', () => {
    const withNaN = stats({ percentile_2: Number.NaN, percentile_98: 240 }, { percentile_2: 10, percentile_98: 250 });
    expect(autoRescale(withNaN)).toEqual([10, 250]);
  });
});

// The one rule of a preview and a result (M4-19c): the same numbers give the same scale in both.
describe('scaleOf', () => {
  const band = (minimum: number, maximum: number, percentile2: number | null = minimum, percentile98: number | null = maximum): BandStats => ({
    minimum,
    maximum,
    percentile2,
    percentile98,
  });

  it('is -1 to 1 in rdylgn for an index, however its percentiles lie', () => {
    expect(scaleOf({ bands: [band(-0.3, 0.9, 0, 0.5)], expression: true })).toEqual({ low: -1, high: 1, colormap: 'rdylgn' });
  });

  it('is the percentiles in viridis for values outside -1 to 1, or that are no expression', () => {
    expect(scaleOf({ bands: [band(0, 4, 0.5, 3)], expression: true })).toEqual({ low: 0.5, high: 3, colormap: 'viridis' });
    expect(scaleOf({ bands: [band(-0.3, 0.9, 0, 0.5)], expression: false })).toEqual({ low: 0, high: 0.5, colormap: 'viridis' });
  });

  it('spans the lowest and the highest percentile of several bands', () => {
    expect(scaleOf({ bands: [band(0, 9, 1, 8), band(0, 9, 2, 9)], expression: false })).toMatchObject({ low: 1, high: 9 });
  });

  it('takes the minimum and maximum where there are no percentiles or they are no range', () => {
    expect(scaleOf({ bands: [band(5, 50, null, null)], expression: false })).toMatchObject({ low: 5, high: 50 });
    expect(scaleOf({ bands: [band(5, 50, 20, 20)], expression: false })).toMatchObject({ low: 5, high: 50 });
  });

  it('is none for no values, for a flat range and for a band with no valid pixel', () => {
    expect(scaleOf(null)).toBeNull();
    expect(scaleOf({ bands: [], expression: false })).toBeNull();
    expect(scaleOf({ bands: [band(3, 3)], expression: false })).toBeNull();
    expect(scaleOf({ bands: [{ minimum: null, maximum: null, percentile2: null, percentile98: null }], expression: false })).toBeNull();
  });
});
