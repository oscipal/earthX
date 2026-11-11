// The bars under the coverage map (D22): the acquisitions per month the source counts, and coarser where there are many
// months (Otto, 10.11.2026). The row keeps its width and its small height; a long time series takes quarters, then
// years, instead of more bars, so the panel never scrolls for it (Leitfaden §9).

import type { CoverageHistogramPoint } from './api';

export type HistogramStep = 'month' | 'quarter' | 'year';

export interface HistogramBar {
  // What the tooltip names: "2024-07", "2024 Q3", "2024".
  label: string;
  // The first and last month of the bar, `YYYY-MM`, for "in range".
  from: string;
  to: string;
  n: number;
}

// As many as fit the narrowest panel with a bar of at least a few pixels and the gap between them.
export const MAX_HISTOGRAM_BARS = 36;

const STEPS: readonly HistogramStep[] = ['month', 'quarter', 'year'];

const monthOf = (instant: string): string | null => (/^\d{4}-\d{2}/.test(instant) ? instant.slice(0, 7) : null);

function barOf(month: string, step: HistogramStep): Omit<HistogramBar, 'n'> {
  const [year, m] = [month.slice(0, 4), Number(month.slice(5, 7))];
  if (step === 'month') return { label: month, from: month, to: month };
  if (step === 'year') return { label: year, from: `${year}-01`, to: `${year}-12` };
  const quarter = Math.ceil(m / 3);
  const first = String(quarter * 3 - 2).padStart(2, '0');
  const last = String(quarter * 3).padStart(2, '0');
  return { label: `${year} Q${quarter}`, from: `${year}-${first}`, to: `${year}-${last}` };
}

// The bars of the histogram and the step they are counted in: the finest step with at most `max` bars, else years.
// A point whose instant is no date, or whose count is no number of at least 0, is left out.
export function histogramBars(points: readonly CoverageHistogramPoint[], max = MAX_HISTOGRAM_BARS): { step: HistogramStep; bars: HistogramBar[] } {
  const usable = points.flatMap((point) => {
    const month = monthOf(point.t);
    return month && Number.isFinite(point.n) && point.n >= 0 ? [{ month, n: point.n }] : [];
  });
  let result: { step: HistogramStep; bars: HistogramBar[] } = { step: 'month', bars: [] };
  for (const step of STEPS) {
    const byLabel = new Map<string, HistogramBar>();
    for (const { month, n } of usable) {
      const bar = barOf(month, step);
      const held = byLabel.get(bar.label);
      byLabel.set(bar.label, held ? { ...held, n: held.n + n } : { ...bar, n });
    }
    result = { step, bars: [...byLabel.values()].sort((a, b) => a.from.localeCompare(b.from)) };
    if (result.bars.length <= max) break;
  }
  return result;
}

// Whether a bar lies in the chosen dates (`YYYY-MM-DD` or empty for an open end): any of its months does.
export function barInRange(bar: HistogramBar, dateFrom: string, dateTo: string): boolean {
  const from = dateFrom.slice(0, 7);
  const to = dateTo.slice(0, 7);
  return (!from || bar.to >= from) && (!to || bar.from <= to);
}
