// The colours of the bars of the histogram of one band (M5-60 §12, Otto 21.11.2026): each bar in the colour its value has on the map. The
// middle of a bar finds its place in the range and so its colour on the colormap; below and above the range the colours of the ends. The
// colours of a colormap are the few the tiler lists for its preview (`GET /colormaps`), the same the legend draws its bar with; between
// two of them the colour runs straight, as the bar of the legend does.

import { entryOf, isReversed, type ColormapGroup } from './colormaps';
import type { Histogram } from './histogram';

// The colormap a band is drawn with where the fields name none: the grey scale of the tiler.
const GREY = 'gray';

const channels = (hex: string): number[] => [1, 3, 5].map((at) => parseInt(hex.slice(at, at + 2), 16));
const hexOf = (rgb: readonly number[]): string => `#${rgb.map((c) => Math.round(c).toString(16).padStart(2, '0')).join('')}`;

// The colour at `t` (0…1) along `colors`.
export function colourAt(colors: readonly string[], t: number): string {
  if (colors.length === 1) return colors[0];
  const at = Math.max(0, Math.min(1, t)) * (colors.length - 1);
  const below = Math.min(Math.floor(at), colors.length - 2);
  const [from, to] = [channels(colors[below]), channels(colors[below + 1])];
  return hexOf(from.map((c, i) => c + (to[i] - c) * (at - below)));
}

// The colour of each bar of `histogram` drawn with `colormap` (the tiler's name, `_r` reversed, '' grey) from `low` to `high`; `null`
// where the colormap is not known (the bars keep the colour of the page).
export function barColours(histogram: Histogram, groups: readonly ColormapGroup[] | null, colormap: string, low: number, high: number): string[] | null {
  const entry = entryOf(groups, colormap || GREY);
  if (!entry || entry.colors.length === 0) return null;
  const colors = isReversed(colormap) ? [...entry.colors].reverse() : entry.colors;
  return histogram.counts.map((_, index) => {
    const middle = (histogram.edges[index] + histogram.edges[index + 1]) / 2;
    const t = high > low ? (middle - low) / (high - low) : middle < low ? 0 : 1;
    return colourAt(colors, t);
  });
}
