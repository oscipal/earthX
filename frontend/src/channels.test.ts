// UI-03d: a range for each channel of a colour picture. The look keeps the three pairs as one text joined by `;`, and three equal
// pairs are written as one, so that a picture drawn alike stays the same look and the same URL. Tested here: the splitting, joining
// and checking of that text, and the percentiles of three bands. What matters is that a half-typed or malformed range never becomes
// a `rescale` the tiler would refuse, and that every problem names the channel it is about.

import { describe, expect, it } from 'vitest';

import { CHANNEL_NAMES, channelsAtPercent, channelsOf, channelsOfRescale, checkChannels, rescaleOfChannels, rescaleParams } from './channels';

const range = (vmin: string, vmax: string) => ({ vmin, vmax });
const THREE = [range('1', '2'), range('3', '4'), range('5', '6')];

describe('CHANNEL_NAMES', () => {
  it('are red, green and blue, in the order of the tile parameters', () => {
    expect([...CHANNEL_NAMES]).toEqual(['red', 'green', 'blue']);
  });
});

describe('rescaleParams', () => {
  it('splits at `;`, one text for each tile parameter', () => {
    expect(rescaleParams('a,b;c,d;e,f')).toEqual(['a,b', 'c,d', 'e,f']);
    expect(rescaleParams('10,2900')).toEqual(['10,2900']);
  });

  it('does not judge what it gets: an empty text is one empty parameter, a stray `;` leaves empty ones', () => {
    expect(rescaleParams('')).toEqual(['']);
    expect(rescaleParams(';')).toEqual(['', '']);
    expect(rescaleParams('1,2;')).toEqual(['1,2', '']);
  });
});

describe('channelsOfRescale', () => {
  it('reads three pairs as the ranges of red, green and blue', () => {
    expect(channelsOfRescale('1,2;3,4;5,6')).toEqual(THREE);
    expect(channelsOfRescale('-1,1;0,0.5;10,2900')).toEqual([range('-1', '1'), range('0', '0.5'), range('10', '2900')]);
  });

  it('is null for one shared pair, as the look was before', () => {
    expect(channelsOfRescale('1,2')).toBeNull();
    expect(channelsOfRescale('10,2900')).toBeNull();
  });

  it('is null for two or four pairs: only three channels make a colour picture', () => {
    expect(channelsOfRescale('1,2;3,4')).toBeNull();
    expect(channelsOfRescale('1,2;3,4;5,6;7,8')).toBeNull();
    expect(channelsOfRescale('1,2;3,4;5,6;')).toBeNull();
    // Gegenprobe: the same pairs, three of them, are read.
    expect(channelsOfRescale('1,2;3,4;5,6')).not.toBeNull();
  });

  it('is null for no range at all', () => {
    expect(channelsOfRescale(undefined)).toBeNull();
    expect(channelsOfRescale('')).toBeNull();
  });

  it('fills an end that is missing with an empty text instead of throwing', () => {
    expect(channelsOfRescale('1;3,4;5,6')).toEqual([range('1', ''), range('3', '4'), range('5', '6')]);
    expect(channelsOfRescale(';;')).toEqual([range('', ''), range('', ''), range('', '')]);
    expect(channelsOfRescale('1,2,9;3,4;5,6')?.[0]).toEqual(range('1', '2'));
  });
});

describe('rescaleOfChannels', () => {
  it('joins three different pairs with `;`, in the order red, green, blue', () => {
    expect(rescaleOfChannels(THREE)).toBe('1,2;3,4;5,6');
    expect(rescaleOfChannels([THREE[2], THREE[1], THREE[0]])).toBe('5,6;3,4;1,2');
  });

  it('writes three equal pairs as one: "a,b"', () => {
    expect(rescaleOfChannels(channelsOf('0', '255'))).toBe('0,255');
    // Gegenprobe: one channel differing keeps all three.
    expect(rescaleOfChannels([range('0', '255'), range('0', '255'), range('0', '254')])).toBe('0,255;0,255;0,254');
  });

  it('trims what was typed before it compares and joins', () => {
    expect(rescaleOfChannels([range(' 1 ', '2 '), range('1', ' 2'), range(' 1', '2')])).toBe('1,2');
  });

  it('is undefined while one end of one channel is not typed', () => {
    for (const index of [0, 1, 2]) {
      expect(rescaleOfChannels(THREE.map((r, i) => (i === index ? range('', r.vmax) : r))), `vmin ${index}`).toBeUndefined();
      expect(rescaleOfChannels(THREE.map((r, i) => (i === index ? range(r.vmin, '') : r))), `vmax ${index}`).toBeUndefined();
      expect(rescaleOfChannels(THREE.map((r, i) => (i === index ? range('  ', '  ') : r))), `blank ${index}`).toBeUndefined();
    }
  });

  it('is undefined for any count but three', () => {
    expect(rescaleOfChannels([])).toBeUndefined();
    expect(rescaleOfChannels(THREE.slice(0, 1))).toBeUndefined();
    expect(rescaleOfChannels(THREE.slice(0, 2))).toBeUndefined();
    expect(rescaleOfChannels([...THREE, range('7', '8')])).toBeUndefined();
  });

  it('is the inverse of channelsOfRescale', () => {
    for (const rescale of ['1,2;3,4;5,6', '-1,1;0,0.5;10,2900']) expect(rescaleOfChannels(channelsOfRescale(rescale)!)).toBe(rescale);
  });
});

describe('checkChannels', () => {
  it('gives the rescale of three valid ranges', () => {
    expect(checkChannels(THREE)).toEqual({ rescale: '1,2;3,4;5,6' });
    expect(checkChannels(channelsOf('0', '255'))).toEqual({ rescale: '0,255' });
  });

  it('writes the numbers the way a number is written: "010" becomes "10", "1e2" becomes "100", " 5 " becomes "5"', () => {
    expect(checkChannels([range('010', '020'), range('1.50', '2.0'), range(' 5 ', '1e2')])).toEqual({ rescale: '10,20;1.5,2;5,100' });
    // Three equal after the writing are one pair.
    expect(checkChannels([range('010', '20'), range('10', '20.0'), range(' 10', '2e1')])).toEqual({ rescale: '10,20' });
  });

  it('keeps negative ends and decimals', () => {
    expect(checkChannels(channelsOf('-1', '0.5'))).toEqual({ rescale: '-1,0.5' });
  });

  it('refuses what is no number and names the channel', () => {
    for (const [index, name] of CHANNEL_NAMES.entries()) {
      for (const bad of ['', '  ', 'abc', '1,5', 'Infinity', '-Infinity', 'NaN', '1;2']) {
        const low = checkChannels(THREE.map((r, i) => (i === index ? range(bad, '9') : r)));
        const high = checkChannels(THREE.map((r, i) => (i === index ? range('0', bad) : r)));
        for (const result of [low, high]) {
          expect(result, `${name} "${bad}"`).toEqual({ problem: `Enter a number for both ends of ${name}.` });
        }
      }
    }
  });

  it('refuses a low end that is not below the high end, and names the channel', () => {
    expect(checkChannels([range('1', '2'), range('4', '3'), range('5', '6')])).toEqual({ problem: 'The lower end of green must be below the upper end.' });
    expect(checkChannels([range('1', '2'), range('3', '4'), range('5', '5')])).toEqual({ problem: 'The lower end of blue must be below the upper end.' });
    expect(checkChannels([range('9', '2'), range('3', '4'), range('5', '6')])).toEqual({ problem: 'The lower end of red must be below the upper end.' });
    // Gegenprobe: the order is compared as numbers, not as text ("9" is above "10" as text only).
    expect(checkChannels(channelsOf('9', '10'))).toEqual({ rescale: '9,10' });
  });

  it('says the first problem it meets, the channels taken in order', () => {
    expect(checkChannels([range('', '2'), range('4', '3'), range('x', '6')])).toEqual({ problem: 'Enter a number for both ends of red.' });
    expect(checkChannels([range('1', '2'), range('4', '3'), range('x', '6')])).toEqual({ problem: 'The lower end of green must be below the upper end.' });
  });

  it('asks for a range for each channel where there are not three', () => {
    const problem = { problem: 'Enter a range for each channel.' };
    expect(checkChannels([])).toEqual(problem);
    expect(checkChannels(THREE.slice(0, 2))).toEqual(problem);
    expect(checkChannels([...THREE, range('7', '8')])).toEqual(problem);
  });
});

describe('channelsOf', () => {
  it('is three copies of one range', () => {
    expect(channelsOf('0', '255')).toEqual([range('0', '255'), range('0', '255'), range('0', '255')]);
  });

  it('gives each channel an object of its own, so that setting one leaves the others', () => {
    const channels = channelsOf('0', '255');
    channels[1].vmax = '100';
    expect(channels[0].vmax).toBe('255');
    expect(channels[2].vmax).toBe('255');
  });

  it('takes what it is given as it is, empty too', () => {
    expect(channelsOf('', '')).toEqual([range('', ''), range('', ''), range('', '')]);
  });
});

describe('channelsAtPercent', () => {
  const band = (lo: number, hi: number, extra: Record<string, unknown> = {}) => ({ percentile_2: lo, percentile_98: hi, ...extra });
  const percent = { low: 2, high: 98 };

  it('reads each channel at the same two percentiles of its own values', () => {
    expect(channelsAtPercent([band(1, 5), band(2, 8), band(0.5, 9.5)], percent)).toEqual([range('1', '5'), range('2', '8'), range('0.5', '9.5')]);
  });

  it('takes the minimum and the maximum for 0 and 100, in either spelling', () => {
    const bands = [{ min: 0, max: 10 }, { minimum: -1, maximum: 1 }, { min: 3, max: 4 }];
    expect(channelsAtPercent(bands, { low: 0, high: 100 })).toEqual([range('0', '10'), range('-1', '1'), range('3', '4')]);
  });

  it('reads other percentiles from `percentile_N`', () => {
    const bands = [3, 3, 3].map(() => ({ percentile_5: 1, percentile_95: 2 }));
    expect(channelsAtPercent(bands, { low: 5, high: 95 })).toEqual(channelsOf('1', '2'));
    // Gegenprobe: the statistics have no 2nd and 98th percentile here.
    expect(channelsAtPercent(bands, percent)).toBeNull();
  });

  it('needs exactly three bands', () => {
    expect(channelsAtPercent([], percent)).toBeNull();
    expect(channelsAtPercent([band(1, 5)], percent)).toBeNull();
    expect(channelsAtPercent([band(1, 5), band(1, 5)], percent)).toBeNull();
    expect(channelsAtPercent([band(1, 5), band(1, 5), band(1, 5), band(1, 5)], percent)).toBeNull();
    expect(channelsAtPercent([band(1, 5), band(1, 5), band(1, 5)], percent)).not.toBeNull();
  });

  it('is null where one band lacks a percentile, or holds no number there', () => {
    expect(channelsAtPercent([band(1, 5), {}, band(1, 5)], percent)).toBeNull();
    expect(channelsAtPercent([band(1, 5), { percentile_2: 1 }, band(1, 5)], percent)).toBeNull();
    expect(channelsAtPercent([band(1, 5), band(1, 5), { percentile_2: 'one', percentile_98: 5 }], percent)).toBeNull();
    expect(channelsAtPercent([band(1, 5), band(Number.NaN, 5), band(1, 5)], percent)).toBeNull();
    expect(channelsAtPercent([band(1, 5), band(1, Number.POSITIVE_INFINITY), band(1, 5)], percent)).toBeNull();
    expect(channelsAtPercent([band(1, 5), band(1, 5), { percentile_2: null, percentile_98: 5 }], percent)).toBeNull();
  });

  it('is null where one channel would have an empty range: the low end not below the high end', () => {
    expect(channelsAtPercent([band(1, 5), band(3, 3), band(1, 5)], percent)).toBeNull();
    expect(channelsAtPercent([band(1, 5), band(1, 5), band(6, 5)], percent)).toBeNull();
    // Gegenprobe: one step wider is a range.
    expect(channelsAtPercent([band(1, 5), band(3, 3.5), band(1, 5)], percent)).not.toBeNull();
  });

  it('is null for a pair of percentiles the wrong way round', () => {
    expect(channelsAtPercent([band(1, 5), band(1, 5), band(1, 5)], { low: 98, high: 2 })).toBeNull();
  });
});
