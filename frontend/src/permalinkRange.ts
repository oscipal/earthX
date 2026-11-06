// The range of the preview as a permalink keeps it (UI-04 part 5): the values as numbers, the percentiles a range was typed as, and for
// a colour picture a range with its own unit for each of red, green and blue. A link made before has neither and is read as it was.

import { CHANNEL_COUNT } from './channels';
import { checkPercent, type Percent } from './percentRange';
import type { PreviewRange } from './processingPreview';

// The percentiles a range was typed as (whole, 0 to 100); the values beside them are the ones they gave.
export interface ViewPercent {
  low: number;
  high: number;
}

export interface ViewRange {
  vmin: number;
  vmax: number;
  colormap: string;
  percent?: ViewPercent;
  // Exactly three, red, green, blue; `vmin`/`vmax` above are the first's.
  channels?: { vmin: number; vmax: number; percent?: ViewPercent }[];
}

const isObject = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const isNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);

// The percentiles of a pair that is one, as numbers; a pair typed wrongly is not kept (its values are).
const percentOfText = (percent: Percent | undefined): ViewPercent | undefined => {
  const checked = percent && checkPercent(percent);
  return checked && !('problem' in checked) ? checked : undefined;
};

const numbersOf = (vmin: string, vmax: string): [number, number] | null => {
  const [low, high] = [Number(vmin), Number(vmax)];
  return vmin.trim() !== '' && vmax.trim() !== '' && isNumber(low) && isNumber(high) ? [low, high] : null;
};

// The range as the link keeps it, or `null` where an end is none.
export function viewRangeOf(range: PreviewRange): ViewRange | null {
  const ends = numbersOf(range.vmin, range.vmax);
  if (range.channels?.length === CHANNEL_COUNT) {
    const channels = range.channels.map((channel) => {
      const own = numbersOf(channel.vmin, channel.vmax);
      const percent = percentOfText(channel.percent);
      return own && { vmin: own[0], vmax: own[1], ...(percent ? { percent } : {}) };
    });
    return ends && channels.every((channel) => channel !== null) ? { vmin: ends[0], vmax: ends[1], colormap: range.colormap, channels } : null;
  }
  const percent = percentOfText(range.percent);
  return ends ? { vmin: ends[0], vmax: ends[1], colormap: range.colormap, ...(percent ? { percent } : {}) } : null;
}

// The same range as the panel holds it.
const textOf = (percent: ViewPercent): Percent => ({ low: String(percent.low), high: String(percent.high) });
export const previewRangeOf = (range: ViewRange): PreviewRange => ({
  vmin: String(range.vmin),
  vmax: String(range.vmax),
  colormap: range.colormap,
  ...(range.percent ? { percent: textOf(range.percent) } : {}),
  ...(range.channels
    ? { channels: range.channels.map((c) => ({ vmin: String(c.vmin), vmax: String(c.vmax), ...(c.percent ? { percent: textOf(c.percent) } : {}) })) }
    : {}),
});

// Percentiles as the server keeps them: two whole numbers, the lower below the upper.
function parsePercent(value: unknown): ViewPercent | null {
  if (!isObject(value) || !Number.isInteger(value.low) || !Number.isInteger(value.high)) return null;
  const [low, high] = [value.low as number, value.high as number];
  return low >= 0 && high <= 100 && low < high ? { low, high } : null;
}

const absent = (value: unknown): boolean => value === undefined || value === null;

// A range with the members of a link from before and, where there, the unit(s) of this part; `null` for one that is none, as for any
// other member of the view. The server keeps `percent` and `channels` apart, and so is this.
export function parseViewRange(range: Record<string, unknown>): ViewRange | null {
  if (!isNumber(range.vmin) || !isNumber(range.vmax) || typeof range.colormap !== 'string') return null;
  const parsed: ViewRange = { vmin: range.vmin, vmax: range.vmax, colormap: range.colormap };
  if (!absent(range.percent)) {
    const percent = parsePercent(range.percent);
    if (!percent || !absent(range.channels)) return null;
    parsed.percent = percent;
  }
  if (!absent(range.channels)) {
    if (!Array.isArray(range.channels) || range.channels.length !== CHANNEL_COUNT) return null;
    parsed.channels = [];
    for (const channel of range.channels) {
      if (!isObject(channel) || !isNumber(channel.vmin) || !isNumber(channel.vmax)) return null;
      const percent = absent(channel.percent) ? undefined : parsePercent(channel.percent);
      if (percent === null) return null;
      parsed.channels.push({ vmin: channel.vmin, vmax: channel.vmax, ...(percent ? { percent } : {}) });
    }
  }
  return parsed;
}
