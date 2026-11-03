// UI-03d: the histogram under the range of a band, as rio-tiler writes it (`[counts, edges]`, one edge more than counts), and the
// sliders on it. Tested here: that only a histogram which can be drawn is taken (the statistics come from outside and may be cut off
// or malformed), that a percentile and its value are the inverse of each other, and that the track and the rounding of a slider never
// leave the field with a number nobody typed.

import { describe, expect, it } from 'vitest';

import { HISTOGRAM_BINS, histogramOf, numberOf, percentAt, roundOnTrack, trackOf, valueAtPercentOf, type Histogram } from './histogram';

// Ten bins of ten values each over 0…10: every percentile is a tenth of the way along.
const UNIFORM: Histogram = { counts: Array(10).fill(10), edges: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10] };
const stats = (histogram: unknown) => ({ histogram });

describe('histogramOf', () => {
  it('takes the shape rio-tiler writes: counts, and one edge more', () => {
    expect(histogramOf(stats([[1, 2, 3], [0, 1, 2, 3]]))).toEqual({ counts: [1, 2, 3], edges: [0, 1, 2, 3] });
    expect(histogramOf(stats([[5], [-1, 1]]))).toEqual({ counts: [5], edges: [-1, 1] });
  });

  it('takes the 64 bins the page asks for', () => {
    const counts = Array.from({ length: HISTOGRAM_BINS }, (_, i) => i);
    const edges = Array.from({ length: HISTOGRAM_BINS + 1 }, (_, i) => i / 8);
    expect(histogramOf(stats([counts, edges]))).toEqual({ counts, edges });
  });

  it('takes empty bins and flat stretches of edges, as long as the whole range has a width', () => {
    expect(histogramOf(stats([[0, 0], [0, 1, 2]]))).not.toBeNull();
    expect(histogramOf(stats([[1, 2, 3], [0, 1, 1, 2]]))).not.toBeNull();
  });

  it('is null where the statistics have none', () => {
    expect(histogramOf(undefined)).toBeNull();
    expect(histogramOf(null)).toBeNull();
    expect(histogramOf({})).toBeNull();
    expect(histogramOf(stats(undefined))).toBeNull();
    expect(histogramOf(stats(null))).toBeNull();
  });

  it('is null where the histogram is no pair of lists', () => {
    for (const bad of ['text', 5, {}, [], [[1, 2]], [[1], [0, 1], [2]], [[1], 'edges'], ['counts', [0, 1]], [{}, {}]]) {
      expect(histogramOf(stats(bad)), JSON.stringify(bad)).toBeNull();
    }
  });

  it('is null where the lengths do not fit: no count, or not one edge more', () => {
    expect(histogramOf(stats([[], [0]]))).toBeNull();
    expect(histogramOf(stats([[], []]))).toBeNull();
    expect(histogramOf(stats([[1, 2], [0, 1]]))).toBeNull();
    expect(histogramOf(stats([[1, 2], [0, 1, 2, 3]]))).toBeNull();
    // A histogram cut off in transport: the edges are short by one.
    expect(histogramOf(stats([[1, 2, 3], [0, 1, 2]]))).toBeNull();
    // Gegenprobe: with the missing edge it is read.
    expect(histogramOf(stats([[1, 2, 3], [0, 1, 2, 3]]))).not.toBeNull();
  });

  it('is null where a number is none: not finite, or text', () => {
    for (const bad of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY, '1', null, undefined]) {
      expect(histogramOf(stats([[1, bad, 3], [0, 1, 2, 3]])), `count ${String(bad)}`).toBeNull();
      expect(histogramOf(stats([[1, 2, 3], [0, bad, 2, 3]])), `edge ${String(bad)}`).toBeNull();
    }
  });

  it('is null where the edges go down', () => {
    expect(histogramOf(stats([[1, 2, 3], [0, 2, 1, 3]]))).toBeNull();
    expect(histogramOf(stats([[1, 2], [2, 1, 0]]))).toBeNull();
  });

  it('is null where the whole range has no width', () => {
    expect(histogramOf(stats([[4], [3, 3]]))).toBeNull();
    expect(histogramOf(stats([[1, 2, 3], [7, 7, 7, 7]]))).toBeNull();
  });
});

describe('percentAt and valueAtPercentOf', () => {
  it('counts a negative bin as empty in the share as in the total', () => {
    const h = { counts: [-5, 10], edges: [0, 1, 2] };
    expect(percentAt(h, 2)).toBe(100);
    expect(percentAt(h, 1)).toBe(0);
  });

  it('are the inverse of each other on a uniform histogram, within a tolerance', () => {
    for (const percent of [0, 1, 2, 10, 25, 33.3, 50, 75, 90, 98, 100]) {
      const value = valueAtPercentOf(UNIFORM, percent);
      expect(value, `value at ${percent}`).toBeCloseTo(percent / 10, 9);
      expect(percentAt(UNIFORM, value), `percent at ${value}`).toBeCloseTo(percent, 9);
    }
    for (const value of [0, 0.5, 2, 3.7, 5, 9.99, 10]) expect(valueAtPercentOf(UNIFORM, percentAt(UNIFORM, value))).toBeCloseTo(value, 9);
  });

  it('counts a bin evenly over its width, the bins of different widths too', () => {
    const wide: Histogram = { counts: [5, 5], edges: [0, 1, 11] };
    expect(percentAt(wide, 1)).toBeCloseTo(50, 9);
    expect(percentAt(wide, 6)).toBeCloseTo(75, 9);
    expect(valueAtPercentOf(wide, 75)).toBeCloseTo(6, 9);
    // Gegenprobe: not the middle of the value axis (5.5) but the middle of the counts (1) holds half of the values.
    expect(percentAt(wide, 5.5)).not.toBeCloseTo(50, 1);
  });

  it('puts a skewed histogram where its values are', () => {
    const skewed: Histogram = { counts: [90, 10], edges: [0, 1, 2] };
    expect(percentAt(skewed, 1)).toBeCloseTo(90, 9);
    expect(valueAtPercentOf(skewed, 45)).toBeCloseTo(0.5, 9);
    expect(valueAtPercentOf(skewed, 95)).toBeCloseTo(1.5, 9);
  });

  it('stays in 0…100 for a value below or above the histogram', () => {
    expect(percentAt(UNIFORM, -5)).toBe(0);
    expect(percentAt(UNIFORM, 0)).toBe(0);
    expect(percentAt(UNIFORM, 10)).toBe(100);
    expect(percentAt(UNIFORM, 1e9)).toBe(100);
    expect(percentAt(UNIFORM, Number.NEGATIVE_INFINITY)).toBe(0);
    expect(percentAt(UNIFORM, Number.POSITIVE_INFINITY)).toBe(100);
  });

  it('stays inside the histogram for a percent below 0 or above 100', () => {
    expect(valueAtPercentOf(UNIFORM, -20)).toBe(0);
    expect(valueAtPercentOf(UNIFORM, 0)).toBe(0);
    expect(valueAtPercentOf(UNIFORM, 100)).toBe(10);
    expect(valueAtPercentOf(UNIFORM, 250)).toBe(10);
    // Gegenprobe: inside, the value moves.
    expect(valueAtPercentOf(UNIFORM, 50)).not.toBe(valueAtPercentOf(UNIFORM, 51));
  });

  it('reads an empty histogram (no value counted) as 0 percent, and the first edge for any percent', () => {
    const empty: Histogram = { counts: [0, 0, 0], edges: [2, 4, 6, 8] };
    expect(percentAt(empty, 5)).toBe(0);
    expect(percentAt(empty, 100)).toBe(0);
    for (const percent of [0, 50, 100]) expect(valueAtPercentOf(empty, percent)).toBe(2);
  });

  it('does not stop at an empty bin: the value at a percent lies in the next bin with values', () => {
    const gap: Histogram = { counts: [10, 0, 0, 10], edges: [0, 1, 2, 3, 4] };
    expect(valueAtPercentOf(gap, 50)).toBeCloseTo(1, 9);
    expect(valueAtPercentOf(gap, 75)).toBeCloseTo(3.5, 9);
    expect(percentAt(gap, 2.5)).toBeCloseTo(50, 9);
  });

  it('gives a number, not NaN, where edges repeat (a bin of no width)', () => {
    const flat: Histogram = { counts: [5, 5, 5], edges: [0, 1, 1, 2] };
    for (const percent of [0, 20, 50, 80, 100]) expect(Number.isFinite(valueAtPercentOf(flat, percent)), `value ${percent}`).toBe(true);
    for (const value of [-1, 0, 1, 1.5, 2, 3]) expect(Number.isFinite(percentAt(flat, value)), `percent ${value}`).toBe(true);
  });
});

describe('trackOf', () => {
  it('is the histogram where the ends lie within it', () => {
    expect(trackOf(UNIFORM, [2, 8])).toEqual([0, 10]);
    expect(trackOf(UNIFORM, [])).toEqual([0, 10]);
  });

  it('widens to take in an end beyond it, on either side', () => {
    expect(trackOf(UNIFORM, [-1, 5])).toEqual([-1, 10]);
    expect(trackOf(UNIFORM, [2, 20])).toEqual([0, 20]);
    expect(trackOf(UNIFORM, [-1, 1])).toEqual([-1, 10]);
    expect(trackOf(UNIFORM, [-3, 40])).toEqual([-3, 40]);
  });

  it('does not narrow: an end inside leaves the histogram whole', () => {
    expect(trackOf(UNIFORM, [4, 6])).not.toEqual([4, 6]);
  });

  it('leaves out an end that is empty or no number', () => {
    expect(trackOf(UNIFORM, [null, null])).toEqual([0, 10]);
    expect(trackOf(UNIFORM, [null, 20])).toEqual([0, 20]);
    expect(trackOf(UNIFORM, [Number.NaN, Number.POSITIVE_INFINITY])).toEqual([0, 10]);
    expect(trackOf(UNIFORM, [Number.NEGATIVE_INFINITY, 5])).toEqual([0, 10]);
  });
});

describe('roundOnTrack', () => {
  it('is a thousandth of the track, no finer', () => {
    expect(roundOnTrack(3.14159, [0, 10])).toBe('3.14');
    expect(roundOnTrack(0.123456, [-1, 1])).toBe('0.123');
    expect(roundOnTrack(1234.567, [0, 1000])).toBe('1235');
    expect(roundOnTrack(12345.6, [0, 100000])).toBe('12346');
    // Gegenprobe: a finer track takes finer digits.
    expect(roundOnTrack(3.14159, [0, 1])).toBe('3.142');
  });

  it('leaves no trailing digits', () => {
    expect(roundOnTrack(2.5, [0, 10])).toBe('2.5');
    expect(roundOnTrack(2, [0, 10])).toBe('2');
    expect(roundOnTrack(2.0004, [0, 10])).toBe('2');
    expect(roundOnTrack(-0.0001, [0, 10])).toBe('0');
  });

  it('keeps negative values and a sign', () => {
    expect(roundOnTrack(-0.4567, [-1, 1])).toBe('-0.457');
  });

  it('writes whole numbers for a track of a thousand or more, whatever its offset', () => {
    expect(roundOnTrack(2900.4, [10, 5000])).toBe('2900');
    expect(roundOnTrack(7.6, [0, 1000])).toBe('8');
  });

  it('takes at most 10 digits on a track narrower than a billionth', () => {
    expect(roundOnTrack(1.23456789012345, [0, 1e-9])).toBe('1.2345678901');
  });

  it('takes no digits where the track has no width or is reversed', () => {
    expect(roundOnTrack(5.7, [5, 5])).toBe('6');
    expect(roundOnTrack(5.7, [10, 0])).toBe('6');
  });
});

describe('numberOf', () => {
  it('reads a number as it is typed, with blanks around it', () => {
    expect(numberOf('5')).toBe(5);
    expect(numberOf(' 5 ')).toBe(5);
    expect(numberOf('-0.5')).toBe(-0.5);
    expect(numberOf('1e3')).toBe(1000);
    expect(numberOf('010')).toBe(10);
  });

  it('reads 0 as 0, not as nothing', () => {
    expect(numberOf('0')).toBe(0);
    expect(numberOf('0')).not.toBeNull();
  });

  it('is null for an empty field', () => {
    expect(numberOf('')).toBeNull();
    expect(numberOf('   ')).toBeNull();
  });

  it('is null for what is no number: text, a comma, more than one number, not finite', () => {
    for (const bad of ['abc', '1,5', '1 2', '1;2', '-', '.', '1e', 'NaN', 'Infinity', '-Infinity', '1e999']) expect(numberOf(bad), bad).toBeNull();
  });
});
