// A small histogram of one band with two sliders on it, vmin and vmax (UI-03d, Otto, 2.11.2026). The bars are what the statistics
// count, the part between the sliders is drawn full, the rest faint. The sliders are two range inputs over one track, so the keys
// move them and a finger can take them; the lower never passes the upper.

import { trackOf, type Histogram } from '../histogram';

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
  title?: string;
}

const STEPS = 1000;

export default function RangeHistogram({ histogram, low, high, onLow, onHigh, channel, title }: Props) {
  const track = trackOf(histogram, [low, high]);
  const span = track[1] - track[0];
  const at = (value: number) => (span > 0 ? ((value - track[0]) / span) * 100 : 0);
  const from = low ?? histogram.edges[0];
  const to = high ?? histogram.edges[histogram.edges.length - 1];
  const peak = Math.max(...histogram.counts, 0);
  const name = channel ? `${channel} ` : '';
  const step = span > 0 ? span / STEPS : 'any';
  return (
    <div className={`range-hist${channel ? ` range-hist-${channel}` : ''}`} title={title}>
      <svg className="range-hist-bars" viewBox="0 0 100 1" preserveAspectRatio="none" aria-hidden="true">
        {histogram.counts.map((count, index) => {
          const x = at(histogram.edges[index]);
          const width = Math.max(at(histogram.edges[index + 1]) - x, 0.2);
          const height = peak > 0 ? Math.sqrt(Math.max(0, count) / peak) : 0;
          const inside = histogram.edges[index + 1] > from && histogram.edges[index] < to;
          return <rect key={index} className={inside ? 'in' : 'out'} x={x} y={1 - height} width={width} height={height} />;
        })}
      </svg>
      <input
        type="range"
        className="range-hist-low"
        aria-label={`${name}vmin`}
        min={track[0]}
        max={track[1]}
        step={step}
        value={from}
        onChange={(e) => onLow(Math.min(Number(e.target.value), to))}
      />
      <input
        type="range"
        className="range-hist-high"
        aria-label={`${name}vmax`}
        min={track[0]}
        max={track[1]}
        step={step}
        value={to}
        onChange={(e) => onHigh(Math.max(Number(e.target.value), from))}
      />
    </div>
  );
}
