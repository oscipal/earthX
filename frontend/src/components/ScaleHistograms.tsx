// The histograms of the row "Scale" (UI-03d): one for a band, three for a colour picture (red, green, blue), each with its sliders.
// The sliders and the fields are one thing: a slider writes the field, a field moves the slider, and "auto-scale" or "Enhance
// contrast" move both. In values a slider writes the value; in percentiles it writes the whole percent of the band's histogram at
// that place, and a colour picture has one pair of percentiles for its three channels (each at its own values).

import type { ChannelRange } from '../channels';
import { CHANNEL_NAMES } from '../channels';
import { numberOf, percentAt, roundOnTrack, trackOf, valueAtPercentOf, type Histogram } from '../histogram';
import type { RangeUnit } from '../percentRange';
import RangeHistogram from './RangeHistogram';

interface Props {
  histograms: readonly Histogram[];
  unit: RangeUnit;
  // The two fields as they stand: values, or percentiles.
  vmin: string;
  vmax: string;
  onVmin: (text: string) => void;
  onVmax: (text: string) => void;
  // A colour picture in values: the range of each channel.
  channels?: { values: readonly ChannelRange[]; onChange: (channel: number, end: 'vmin' | 'vmax', text: string) => void };
}

const PERCENT_TIP = 'In percentiles one pair holds for the three channels, each at its own values';

export default function ScaleHistograms({ histograms, unit, vmin, vmax, onVmin, onVmax, channels }: Props) {
  const colour = histograms.length === CHANNEL_NAMES.length;
  return (
    <div className="range-hists">
      {histograms.map((histogram, index) => {
        const channel = colour ? CHANNEL_NAMES[index] : undefined;
        if (unit === 'percent') {
          const lowPercent = numberOf(vmin);
          const highPercent = numberOf(vmax);
          return (
            <RangeHistogram
              key={index}
              histogram={histogram}
              channel={channel}
              title={colour ? PERCENT_TIP : undefined}
              low={lowPercent === null ? null : valueAtPercentOf(histogram, lowPercent)}
              high={highPercent === null ? null : valueAtPercentOf(histogram, highPercent)}
              onLow={(value) => onVmin(String(Math.round(percentAt(histogram, value))))}
              onHigh={(value) => onVmax(String(Math.round(percentAt(histogram, value))))}
            />
          );
        }
        const own = colour && channels ? channels.values[index] : undefined;
        const [low, high] = own ? [numberOf(own.vmin), numberOf(own.vmax)] : [numberOf(vmin), numberOf(vmax)];
        const track = trackOf(histogram, [low, high]);
        const write = (end: 'vmin' | 'vmax', value: number) => {
          const text = roundOnTrack(value, track);
          if (colour && channels) channels.onChange(index, end, text);
          else if (end === 'vmin') onVmin(text);
          else onVmax(text);
        };
        return (
          <RangeHistogram
            key={index}
            histogram={histogram}
            channel={channel}
            low={low}
            high={high}
            onLow={(value) => write('vmin', value)}
            onHigh={(value) => write('vmax', value)}
          />
        );
      })}
    </div>
  );
}
