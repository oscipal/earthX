// NM4-65 part 4: percentiles as the ends of the range.

import { describe, expect, it } from 'vitest';

import { checkPercent, DEFAULT_PERCENT, percentOf, PERCENT_PROBLEMS, rescaleAtPercent, samePercent, valueAtPercent } from './percentRange';

describe('checkPercent', () => {
  it('takes whole percents from 0 to 100, the low one below the high one', () => {
    expect(checkPercent({ low: '2', high: '98' })).toEqual({ low: 2, high: 98 });
    expect(checkPercent({ low: '0', high: '100' })).toEqual({ low: 0, high: 100 });
    expect(checkPercent({ low: ' 5 ', high: '95 ' })).toEqual({ low: 5, high: 95 });
    expect(checkPercent(DEFAULT_PERCENT)).toEqual({ low: 2, high: 98 });
  });

  it('refuses what is no whole percent: empty, decimals, signs, text, exponents, more than 100', () => {
    for (const bad of ['', ' ', '2.5', '-1', '+3', 'abc', '1e1', '101', '1000', '0x10', '２']) {
      expect(checkPercent({ low: bad, high: '98' }), bad).toEqual({ problem: PERCENT_PROBLEMS.number });
      expect(checkPercent({ low: '2', high: bad }), bad).toEqual({ problem: PERCENT_PROBLEMS.number });
    }
  });

  it('refuses a low end that is not below the high end', () => {
    expect(checkPercent({ low: '98', high: '2' })).toEqual({ problem: PERCENT_PROBLEMS.order });
    expect(checkPercent({ low: '50', high: '50' })).toEqual({ problem: PERCENT_PROBLEMS.order });
  });
});

describe('percentOf and samePercent', () => {
  it('keeps a valid pair as whole numbers and drops anything else', () => {
    expect(percentOf({ low: '02', high: '098' })).toEqual({ low: '2', high: '98' });
    expect(percentOf({ low: 'x', high: '98' })).toBeNull();
    expect(percentOf(undefined)).toBeNull();
    expect(percentOf(null)).toBeNull();
  });

  it('compares what was typed, a missing pair as empty', () => {
    expect(samePercent({ low: '2', high: '98' }, { low: '2', high: '98' })).toBe(true);
    expect(samePercent({ low: '2', high: '98' }, { low: '2', high: '99' })).toBe(false);
    expect(samePercent(null, undefined)).toBe(true);
    expect(samePercent(null, { low: '2', high: '98' })).toBe(false);
  });
});

describe('valueAtPercent', () => {
  const stats = { min: 1, max: 9, percentile_3: 2, percentile_97: 8 };
  it('reads 0 and 100 as the minimum and the maximum, in either spelling', () => {
    expect(valueAtPercent(stats, 0)).toBe(1);
    expect(valueAtPercent(stats, 100)).toBe(9);
    expect(valueAtPercent({ minimum: -4, maximum: 4 }, 0)).toBe(-4);
    expect(valueAtPercent({ minimum: -4, maximum: 4 }, 100)).toBe(4);
  });

  it('reads the others from `percentile_N`, and is null where the statistics do not have them or hold no number', () => {
    expect(valueAtPercent(stats, 3)).toBe(2);
    expect(valueAtPercent(stats, 50)).toBeNull();
    expect(valueAtPercent({ percentile_3: 'two', min: Number.NaN }, 3)).toBeNull();
    expect(valueAtPercent({ min: Number.NaN }, 0)).toBeNull();
  });
});

describe('rescaleAtPercent', () => {
  const band = (lo: number, hi: number, extra: object = {}) => ({ percentile_2: lo, percentile_98: hi, count: 10, ...extra });

  it('is the one range the bands share: the lowest low up to the highest high', () => {
    expect(rescaleAtPercent([band(1, 5), band(0, 4), band(2, 9)], { low: 2, high: 98 })).toEqual([0, 9]);
    expect(rescaleAtPercent([band(1, 5)], { low: 2, high: 98 })).toEqual([1, 5]);
  });

  it('leaves out a band without a valid pixel, and is null where none is left', () => {
    expect(rescaleAtPercent([band(1, 5), band(0, 0, { count: 0 })], { low: 2, high: 98 })).toEqual([1, 5]);
    expect(rescaleAtPercent([band(0, 0, { count: 0 })], { low: 2, high: 98 })).toBeNull();
    expect(rescaleAtPercent([], { low: 2, high: 98 })).toBeNull();
  });

  it('is null where a band does not name the percentile, and where the range would be empty', () => {
    expect(rescaleAtPercent([band(1, 5), { count: 10 }], { low: 2, high: 98 })).toBeNull();
    expect(rescaleAtPercent([band(3, 3)], { low: 2, high: 98 })).toBeNull();
    expect(rescaleAtPercent([band(1, 5)], { low: 40, high: 60 })).toBeNull();
  });

  it('takes the minimum and the maximum for 0 and 100', () => {
    expect(rescaleAtPercent([{ minimum: -1, maximum: 7, count: 5 }], { low: 0, high: 100 })).toEqual([-1, 7]);
  });
});
