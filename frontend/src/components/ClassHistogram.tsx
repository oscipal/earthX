// The histogram of a band of classes (M5-60, Otto F9 = 1): what the statistics count, each bar in the colour of its class, and no sliders,
// since a layer of classes has no range. From the same measure as the histogram of any band.

import type { BandClass } from '../bandClasses';
import type { Histogram } from '../histogram';
import { classColours } from '../histogramColours';
import { HistogramBars } from './RangeHistogram';

export default function ClassHistogram({ histogram, classes }: { histogram: Histogram; classes: readonly BandClass[] }) {
  const track: [number, number] = [histogram.edges[0], histogram.edges[histogram.edges.length - 1]];
  return (
    <div className="range-hists">
      <div className="range-hist class-hist">
        <HistogramBars histogram={histogram} track={track} colours={classColours(histogram, classes)} inside={() => true} />
      </div>
    </div>
  );
}
