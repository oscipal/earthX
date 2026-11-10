// The bars under the coverage map (Otto, 10.11.2026): a fixed row, coarser where there are many months. Synthetic only.

import { describe, expect, it } from 'vitest';

import type { CoverageHistogramPoint } from './api';
import { barInRange, histogramBars, MAX_HISTOGRAM_BARS } from './coverageHistogram';

// One point per month from `start` (`YYYY-MM`) on, `count` of them, each with `n`.
function months(start: string, count: number, n = 1): CoverageHistogramPoint[] {
  const [year, month] = start.split('-').map(Number);
  return Array.from({ length: count }, (_, i) => {
    const total = year * 12 + month - 1 + i;
    return { t: `${Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, '0')}-01T00:00:00Z`, n };
  });
}

describe('histogramBars', () => {
  it('keeps one bar per month while they fit', () => {
    const { step, bars } = histogramBars(months('2024-01', MAX_HISTOGRAM_BARS, 2));
    expect(step).toBe('month');
    expect(bars).toHaveLength(MAX_HISTOGRAM_BARS);
    expect(bars[0]).toEqual({ label: '2024-01', from: '2024-01', to: '2024-01', n: 2 });
  });

  it('counts quarters where the months would not fit, and sums the months of each', () => {
    const { step, bars } = histogramBars(months('2020-01', MAX_HISTOGRAM_BARS + 1, 3));
    expect(step).toBe('quarter');
    expect(bars[0]).toEqual({ label: '2020 Q1', from: '2020-01', to: '2020-03', n: 9 });
    expect(bars.at(-1)).toEqual({ label: '2023 Q1', from: '2023-01', to: '2023-03', n: 3 });
    expect(bars.length).toBeLessThanOrEqual(MAX_HISTOGRAM_BARS);
  });

  it('counts years for a long series such as Sentinel-1 since 2014, never more bars', () => {
    const { step, bars } = histogramBars(months('2014-10', 146, 1000));
    expect(step).toBe('year');
    expect(bars.map((bar) => bar.label)).toEqual(Array.from({ length: 13 }, (_, i) => String(2014 + i)));
    expect(bars[0].n).toBe(3000);
    expect(bars.reduce((sum, bar) => sum + bar.n, 0)).toBe(146_000);
  });

  it('takes years even where they are more than fit: the row then thins its bars, it does not grow', () => {
    const points = Array.from({ length: 50 }, (_, i) => ({ t: `${1980 + i}-06-01T00:00:00Z`, n: 1 }));
    const { step, bars } = histogramBars(points, 10);
    expect(step).toBe('year');
    expect(bars).toHaveLength(50);
  });

  it('keeps the order of time whatever order the points come in', () => {
    const points = [...months('2024-01', 3)].reverse();
    expect(histogramBars(points).bars.map((bar) => bar.label)).toEqual(['2024-01', '2024-02', '2024-03']);
  });

  it('leaves out a point that is no date or no count', () => {
    const points = [{ t: 'soon', n: 1 }, { t: '2024-05-01T00:00:00Z', n: Number.NaN }, { t: '2024-05-01T00:00:00Z', n: -1 }, { t: '2024-05-01T00:00:00Z', n: 4 }];
    expect(histogramBars(points).bars).toEqual([{ label: '2024-05', from: '2024-05', to: '2024-05', n: 4 }]);
    expect(histogramBars([]).bars).toEqual([]);
  });
});

describe('barInRange', () => {
  const quarter = { label: '2024 Q3', from: '2024-07', to: '2024-09', n: 1 };

  it('counts a bar as in range where any of its months is', () => {
    expect(barInRange(quarter, '2024-09-15', '2025-01-01')).toBe(true);
    expect(barInRange(quarter, '2024-01-01', '2024-07-01')).toBe(true);
    expect(barInRange(quarter, '2024-10-01', '')).toBe(false);
    expect(barInRange(quarter, '', '2024-06-30')).toBe(false);
  });

  it('takes an empty date as an open end', () => {
    expect(barInRange(quarter, '', '')).toBe(true);
  });
});
