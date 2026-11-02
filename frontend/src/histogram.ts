// The histogram under the range of a band (UI-03d, Otto, 2.11.2026): what the statistics route counts, as rio-tiler writes it
// (`[counts, edges]`, one edge more than counts), and the two ends of the range on it. In percentiles a slider stands where that
// percentile of the histogram lies, and moving it gives the percentile back; both are read from the histogram, so they are close to,
// not exactly, the percentiles of the statistics.

// Bins the page asks the tiler for (`histogram_bins`); the result route always has 64 (`processing/statistics.py::DISPLAY_BINS`).
export const HISTOGRAM_BINS = 64;

export interface Histogram {
  counts: number[];
  edges: number[];
}

const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);

// The histogram of one band's statistics, `null` where they have none or one that cannot be read.
export function histogramOf(stats: Record<string, unknown> | null | undefined): Histogram | null {
  const raw = stats?.histogram;
  if (!Array.isArray(raw) || raw.length !== 2) return null;
  const [counts, edges] = raw as unknown[];
  if (!Array.isArray(counts) || !Array.isArray(edges) || counts.length === 0 || edges.length !== counts.length + 1) return null;
  if (!counts.every(finite) || !edges.every(finite)) return null;
  for (let i = 1; i < edges.length; i += 1) if (!(edges[i] >= edges[i - 1])) return null;
  if (!(edges[edges.length - 1] > edges[0])) return null;
  return { counts: counts as number[], edges: edges as number[] };
}

const total = (h: Histogram) => h.counts.reduce((sum, n) => sum + Math.max(0, n), 0);

// The share of the values at or below `value`, in percent (0…100), counting a bin evenly over its width.
export function percentAt(h: Histogram, value: number): number {
  const all = total(h);
  if (all <= 0) return 0;
  let below = 0;
  for (let i = 0; i < h.counts.length; i += 1) {
    const [low, high] = [h.edges[i], h.edges[i + 1]];
    if (value >= high) below += h.counts[i];
    else if (value > low) below += (h.counts[i] * (value - low)) / (high - low);
  }
  return Math.max(0, Math.min(100, (100 * below) / all));
}

// The value at `percent` (0…100) of the histogram, the other way round.
export function valueAtPercentOf(h: Histogram, percent: number): number {
  const all = total(h);
  const wanted = (Math.max(0, Math.min(100, percent)) / 100) * all;
  if (all <= 0 || wanted <= 0) return h.edges[0];
  let below = 0;
  for (let i = 0; i < h.counts.length; i += 1) {
    const count = Math.max(0, h.counts[i]);
    if (count > 0 && below + count >= wanted) return h.edges[i] + ((wanted - below) / count) * (h.edges[i + 1] - h.edges[i]);
    below += count;
  }
  return h.edges[h.edges.length - 1];
}

// The track of the sliders: the histogram, widened to take in ends that lie beyond it (an index drawn at −1…1, a range typed by hand).
export function trackOf(h: Histogram, ends: readonly (number | null)[]): [number, number] {
  const known = ends.filter(finite);
  return [Math.min(h.edges[0], ...known), Math.max(h.edges[h.edges.length - 1], ...known)];
}

// What a slider writes into a field: a thousandth of the track, no finer, without trailing digits.
export function roundOnTrack(value: number, track: readonly [number, number]): string {
  const step = (track[1] - track[0]) / 1000;
  const digits = step > 0 ? Math.max(0, Math.min(10, -Math.floor(Math.log10(step)))) : 0;
  return String(Number(value.toFixed(digits)));
}

// A number typed into a field, `null` where it is none.
export function numberOf(text: string): number | null {
  if (text.trim() === '') return null;
  const n = Number(text);
  return Number.isFinite(n) ? n : null;
}
