// A range for each channel of a colour picture (UI-03d, Otto, 2.11.2026): red, green and blue are stretched each on its own. The
// tile URL carries one `rescale` per channel, in this order; the look keeps them as one text, the pairs joined by `;`. Three equal
// pairs are written as one, as before, so that a picture drawn alike is the same look and the same URL.

import { valueAtPercent } from './percentRange';

export const CHANNEL_NAMES = ['red', 'green', 'blue'] as const;
export const CHANNEL_COUNT = CHANNEL_NAMES.length;

export interface ChannelRange {
  vmin: string;
  vmax: string;
}

const SEPARATOR = ';';

// The `rescale` of each tile parameter: one pair, or three.
export const rescaleParams = (rescale: string): string[] => rescale.split(SEPARATOR);

// The three pairs of a look with a range for each channel; `null` for one shared range or none.
export function channelsOfRescale(rescale: string | undefined): ChannelRange[] | null {
  if (!rescale || !rescale.includes(SEPARATOR)) return null;
  const pairs = rescaleParams(rescale);
  if (pairs.length !== CHANNEL_COUNT) return null;
  return pairs.map((pair) => {
    const [vmin = '', vmax = ''] = pair.split(',');
    return { vmin, vmax };
  });
}

// The `rescale` of three ranges, once all six ends are typed; three equal ones are one pair.
export function rescaleOfChannels(channels: readonly ChannelRange[]): string | undefined {
  if (channels.length !== CHANNEL_COUNT) return undefined;
  const pairs = channels.map(({ vmin, vmax }) => [vmin.trim(), vmax.trim()]);
  if (pairs.some(([low, high]) => low === '' || high === '')) return undefined;
  const texts = pairs.map((pair) => pair.join(','));
  return texts.every((text) => text === texts[0]) ? texts[0] : texts.join(SEPARATOR);
}

// The same three ranges, each end as a number; the reason where one is not a range.
export function checkChannels(channels: readonly ChannelRange[]): { rescale: string } | { problem: string } {
  for (const [index, { vmin, vmax }] of channels.entries()) {
    const low = vmin.trim() === '' ? NaN : Number(vmin);
    const high = vmax.trim() === '' ? NaN : Number(vmax);
    if (!Number.isFinite(low) || !Number.isFinite(high)) return { problem: `Enter a number for both ends of ${CHANNEL_NAMES[index]}.` };
    if (low >= high) return { problem: `The lower end of ${CHANNEL_NAMES[index]} must be below the upper end.` };
  }
  const rescale = rescaleOfChannels(channels.map(({ vmin, vmax }) => ({ vmin: String(Number(vmin)), vmax: String(Number(vmax)) })));
  return rescale ? { rescale } : { problem: 'Enter a range for each channel.' };
}

// Three copies of one range: where a picture drawn with one range for all is set channel by channel.
export const channelsOf = (vmin: string, vmax: string): ChannelRange[] => CHANNEL_NAMES.map(() => ({ vmin, vmax }));

// Each channel at the same two percentiles of its own values ("Enhance contrast": the 2nd and the 98th). `null` where the statistics
// do not have three bands or one of them has no range there.
export function channelsAtPercent(bands: readonly Record<string, unknown>[], percent: { low: number; high: number }): ChannelRange[] | null {
  if (bands.length !== CHANNEL_COUNT) return null;
  const ranges = bands.map((band) => [valueAtPercent(band, percent.low), valueAtPercent(band, percent.high)] as const);
  if (ranges.some(([low, high]) => low === null || high === null || !(low < high))) return null;
  return ranges.map(([low, high]) => ({ vmin: String(low), vmax: String(high) }));
}
