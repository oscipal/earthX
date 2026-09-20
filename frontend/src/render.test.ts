import { describe, expect, it } from 'vitest';

import type { BandStatistics } from './api';
import { autoRescale } from './render';

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
