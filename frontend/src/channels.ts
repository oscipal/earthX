// A range for each channel of a colour picture (UI-03d, Otto, 2.11.2026): red, green and blue are stretched each on its own. The
// tile URL carries one `rescale` per channel, in this order; the look keeps them as one text, the pairs joined by `;`. Three equal
// pairs are written as one, as before, so that a picture drawn alike is the same look and the same URL.

import { DEFAULT_PERCENT, percentOf, samePercent, valueAtPercent, type Percent } from './percentRange';

export const CHANNEL_NAMES = ['red', 'green', 'blue'] as const;
export const CHANNEL_COUNT = CHANNEL_NAMES.length;

export interface ChannelRange {
  vmin: string;
  vmax: string;
  // Set where this channel is typed in percentiles (UI-03e): the pair as typed; `vmin`/`vmax` then hold the values it gave when it was
  // applied. A channel without it is typed in values.
  percent?: Percent;
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

// A range without the ranges of single channels: where it is drawn on one band, only the first of them was ever meant for it.
export function withoutChannels<T extends { channels?: unknown }>(range: T): Omit<T, 'channels'> {
  const { channels: _channels, ...rest } = range;
  return rest;
}

// The three ranges a colour picture shows for a range: its own where it has them, else the one range three times. A pair typed in
// percentiles for all of them (a look of before UI-03e) stands on every channel until one is changed.
export function channelsOfRange(range: { vmin: string; vmax: string; percent?: Percent; channels?: readonly ChannelRange[] }): ChannelRange[] {
  const base = range.channels?.length === CHANNEL_COUNT ? [...range.channels] : channelsOf(range.vmin, range.vmax);
  return range.percent && !base.some((channel) => channel.percent) ? base.map((channel) => ({ ...channel, percent: range.percent })) : base;
}

// "Auto-scale" of a colour picture: each channel typed in percentiles takes the usual pair, the others the measured range where there is one.
export const channelsAutoScaled = (channels: readonly ChannelRange[], measured: { vmin: string; vmax: string } | null): ChannelRange[] =>
  channels.map((channel) => (channel.percent ? { ...channel, percent: { ...DEFAULT_PERCENT } } : measured ? { vmin: measured.vmin, vmax: measured.vmax } : channel));

// Each channel at the same two percentiles of its own values ("Enhance contrast": the 2nd and the 98th). `null` where the statistics
// do not have three bands or one of them has no range there.
export function channelsAtPercent(bands: readonly Record<string, unknown>[], percent: { low: number; high: number }): ChannelRange[] | null {
  if (bands.length !== CHANNEL_COUNT) return null;
  const ranges = bands.map((band) => [valueAtPercent(band, percent.low), valueAtPercent(band, percent.high)] as const);
  if (ranges.some(([low, high]) => low === null || high === null || !(low < high))) return null;
  return ranges.map(([low, high]) => ({ vmin: String(low), vmax: String(high) }));
}

// The pair of each channel typed in percentiles, `null` for the others; `undefined` where none is. A pair that is none counts as a
// channel in values here (`badChannelPercent` says it is still to be corrected).
export function percentsOfChannels(channels: readonly ChannelRange[]): (Percent | null)[] | undefined {
  if (!channels.some((channel) => channel.percent)) return undefined;
  const pairs = channels.map((channel) => (channel.percent ? percentOf(channel.percent) : null));
  return pairs.some((pair) => pair !== null) ? pairs : undefined;
}

// Whether a channel is typed in percentiles with a pair that is none.
export const badChannelPercent = (channels: readonly ChannelRange[]): boolean => channels.some((channel) => channel.percent !== undefined && percentOf(channel.percent) === null);

export function samePercents(a: readonly (Percent | null)[] | undefined, b: readonly (Percent | null)[] | undefined): boolean {
  if (!a || !b) return !a && !b;
  return a.length === b.length && a.every((pair, index) => (pair === null || b[index] === null ? pair === b[index] : samePercent(pair, b[index])));
}

// Each channel typed in percentiles at its own pair and its own values; the others as they are. `null` where the statistics do not have
// three bands or a channel has no range at its percentiles.
export function channelsAtOwnPercent(bands: readonly Record<string, unknown>[], channels: readonly ChannelRange[]): ChannelRange[] | null {
  if (bands.length !== CHANNEL_COUNT || channels.length !== CHANNEL_COUNT) return null;
  const made: ChannelRange[] = [];
  for (const [index, channel] of channels.entries()) {
    const pair = channel.percent ? percentOf(channel.percent) : null;
    if (!channel.percent) {
      made.push(channel);
      continue;
    }
    if (!pair) return null;
    const [low, high] = [valueAtPercent(bands[index], Number(pair.low)), valueAtPercent(bands[index], Number(pair.high))];
    if (low === null || high === null || !(low < high)) return null;
    made.push({ vmin: String(low), vmax: String(high), percent: pair });
  }
  return made;
}
