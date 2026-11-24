// A small histogram of one band with two sliders on it, vmin and vmax (UI-03d, Otto, 2.11.2026). The bars are what the statistics
// count. A band drawn with a colormap has each bar in the colour its value has on the map (M5-60 §12, `histogramColours.ts`), and the
// colours follow the sliders and the colormap as they change; a channel of a colour picture is drawn in its colour, the bars in the range
// full, the rest faint. A bar is in the range where its middle is, and the sliders stand outside the bars in it (`histogram.ts::sliderPlaces`,
// Otto 24.11.2026), while the fields keep the values. The sliders are two range inputs over one track, so the keys move them and a finger
// can take them; the lower never passes the upper.

import type { ColormapGroup } from '../colormaps';
import { barInRange, sliderPlaces, trackOf, type Histogram } from '../histogram';
import { barColours } from '../histogramColours';

export type Channel = 'red' | 'green' | 'blue';

interface Props {
  histogram: Histogram;
  // Where the two sliders stand, as values of the band; `null` puts a slider at its end of the histogram.
  low: number | null;
  high: number | null;
  onLow: (value: number) => void;
  onHigh: (value: number) => void;
  // The channel of a colour picture, for the colour of its bars and the names of its sliders.
  channel?: Channel;
  // The colormap one band is drawn with ('' grey) and the colormaps of the tiler, for the colours of the bars.
  paint?: { colormap: string; groups: readonly ColormapGroup[] | null };
  title?: string;
}

const STEPS = 1000;
const KEYS: Record<string, number> = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1 };

// The bars of a histogram over `track`: in the colour given for each, else in the colour of the page, faint where `inside` says not.
export function HistogramBars({ histogram, track, colours, inside }: { histogram: Histogram; track: readonly [number, number]; colours: readonly (string | null)[] | null; inside: (bar: number) => boolean }) {
  const span = track[1] - track[0];
  const at = (value: number) => (span > 0 ? ((value - track[0]) / span) * 100 : 0);
  const peak = Math.max(...histogram.counts, 0);
  return (
    <svg className="range-hist-bars" viewBox="0 0 100 1" preserveAspectRatio="none" aria-hidden="true">
      {histogram.counts.map((count, index) => {
        const x = at(histogram.edges[index]);
        const width = Math.max(at(histogram.edges[index + 1]) - x, 0.2);
        const height = peak > 0 ? Math.sqrt(Math.max(0, count) / peak) : 0;
        const colour = colours?.[index];
        if (colour) return <rect key={index} className="hist-bar" style={{ fill: colour }} x={x} y={1 - height} width={width} height={height} />;
        return <rect key={index} className={inside(index) ? 'in' : 'out'} x={x} y={1 - height} width={width} height={height} />;
      })}
    </svg>
  );
}

export default function RangeHistogram({ histogram, low, high, onLow, onHigh, channel, paint, title }: Props) {
  const track = trackOf(histogram, [low, high]);
  const span = track[1] - track[0];
  const from = low ?? histogram.edges[0];
  const to = high ?? histogram.edges[histogram.edges.length - 1];
  const [lowAt, highAt] = sliderPlaces(histogram, from, to);
  const name = channel ? `${channel} ` : '';
  // The keys move by a thousandth of the track; the inputs take any value, so that a slider stands exactly on the edge of a bar.
  const step = span > 0 ? span / STEPS : null;
  const colours = paint && !channel ? barColours(histogram, paint.groups, paint.colormap, from, to) : null;
  // The keys move the value, not the place the slider is drawn at: from a slider at the edge of a bar they would not move it.
  const nudge = (end: 'low' | 'high') => (e: React.KeyboardEvent) => {
    const delta = KEYS[e.key];
    if (delta === undefined || step === null) return;
    e.preventDefault();
    if (end === 'low') onLow(Math.min(from + delta * step, to));
    else onHigh(Math.max(to + delta * step, from));
  };
  return (
    <div className={`range-hist${channel ? ` range-hist-${channel}` : ''}`} data-tip-level="advanced" data-tip={title}>
      <HistogramBars histogram={histogram} track={track} colours={colours} inside={(bar) => barInRange(histogram, bar, from, to)} />
      <input
        type="range"
        className="range-hist-low"
        aria-label={`${name}vmin`}
        aria-valuetext={String(from)}
        min={track[0]}
        max={track[1]}
        step="any"
        value={lowAt}
        onKeyDown={nudge('low')}
        onChange={(e) => onLow(Math.min(Number(e.target.value), to))}
      />
      <input
        type="range"
        className="range-hist-high"
        aria-label={`${name}vmax`}
        aria-valuetext={String(to)}
        min={track[0]}
        max={track[1]}
        step="any"
        value={highAt}
        onKeyDown={nudge('high')}
        onChange={(e) => onHigh(Math.max(Number(e.target.value), from))}
      />
    </div>
  );
}
