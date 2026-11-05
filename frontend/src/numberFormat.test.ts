// NM4-21 (UI-04 part 6): the one way a number is shown.

import { describe, expect, it } from 'vitest';

import { fieldNumber, formatBytes, formatDay, formatLatitude, formatMegapixels, formatMoment, formatNumber, formatPercent, formatPlain, roundTo } from './numberFormat';

describe('formatNumber', () => {
  it.each([
    [0, '0'],
    [-0, '0'],
    [1, '1'],
    [-1, '-1'],
    [12.3456, '12.346'],
    [12.3454, '12.345'],
    [-0.123456789, '-0.123'],
    [0.5, '0.5'],
    [2.5000001, '2.5'],
    [1000, '1000'],
    [123456, '123456'],
    [999999, '999999'],
  ])('shows %s as %s: at most three decimals, none trailing', (value, text) => expect(formatNumber(value)).toBe(text));

  it('keeps 0.001 and turns 0.0009 scientific: the threshold is below one thousandth', () => {
    expect(formatNumber(0.001)).toBe('0.001');
    expect(formatNumber(0.0009)).toBe('9e-4');
    expect(formatNumber(-0.0009)).toBe('-9e-4');
    expect(formatNumber(0.000000052)).toBe('5.2e-8');
    expect(formatNumber(-0.000000052)).toBe('-5.2e-8');
  });

  it('turns a million and more scientific, with up to three significant digits and no plus', () => {
    expect(formatNumber(1e6)).toBe('1e6');
    expect(formatNumber(1234567)).toBe('1.23e6');
    expect(formatNumber(-1234567)).toBe('-1.23e6');
    expect(formatNumber(2.5e12)).toBe('2.5e12');
    expect(formatNumber(1e21)).toBe('1e21');
  });

  it('does not show an amount that rounds up to a threshold as if it were below it', () => {
    expect(formatNumber(999999.9996)).toBe('1e6');
    expect(formatNumber(0.00099996)).toBe('1e-3');
    expect(formatNumber(0.9996)).toBe('1');
  });

  it('shows what is no number as a dash and the infinities as themselves', () => {
    expect(formatNumber(Number.NaN)).toBe('—');
    expect(formatNumber(Number.POSITIVE_INFINITY)).toBe('∞');
    expect(formatNumber(Number.NEGATIVE_INFINITY)).toBe('-∞');
  });

  it('writes what Number() reads back, so that a shown value can be typed into a field', () => {
    for (const value of [0.0009, 5.2e-8, 1234567, -42.125, 0.5]) expect(Number(formatNumber(value))).toBeCloseTo(value, 1 - Math.floor(Math.log10(Math.abs(value))));
  });
});

describe('fieldNumber', () => {
  it('is the shown text, and empty for what is no number (an empty field is "not set")', () => {
    expect(fieldNumber(-0.123456789)).toBe('-0.123');
    expect(fieldNumber(Number.NaN)).toBe('');
    expect(fieldNumber(Number.POSITIVE_INFINITY)).toBe('');
  });
});

describe('formatPlain', () => {
  it('gives back a typed number as digits, without an exponent', () => {
    expect(formatPlain(0.0003)).toBe('0.0003');
    expect(formatPlain(0.0000001)).toBe('0.0000001');
    expect(formatPlain(10)).toBe('10');
    expect(formatPlain(-2.5)).toBe('-2.5');
  });

  it('drops the noise of a float and the minus of a zero, and shows what is no number as formatNumber does', () => {
    expect(formatPlain(0.30000000000000004)).toBe('0.3');
    expect(formatPlain(-0)).toBe('0');
    expect(formatPlain(Number.NaN)).toBe('—');
  });
});

describe('roundTo', () => {
  it('rounds to the digits and stays a number', () => {
    expect(roundTo(3.14159, 2)).toBe(3.14);
    expect(roundTo(1234.567, 0)).toBe(1235);
    expect(roundTo(-0.0001, 1)).toBe(-0);
  });
});

describe('formatPercent', () => {
  it('has no space before the sign', () => {
    expect(formatPercent(50)).toBe('50%');
    expect(formatPercent(42.5)).toBe('42.5%');
    expect(formatPercent(0)).toBe('0%');
  });

  it('does not put a sign after a dash', () => {
    expect(formatPercent(Number.NaN)).toBe('—');
  });
});

describe('sizes', () => {
  it('formatBytes: bytes, whole kB, MB and GB with one decimal', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(4_200)).toBe('4 kB');
    expect(formatBytes(4_200_000)).toBe('4.2 MB');
    expect(formatBytes(3_400_000_000)).toBe('3.4 GB');
  });

  it('formatBytes: gives a size that is none as the dash and does not invent a unit', () => {
    expect(formatBytes(Number.NaN)).toBe('—');
    expect(formatBytes(-5)).toBe('-5');
  });

  it('formatMegapixels: whole from ten, one decimal below', () => {
    expect(formatMegapixels(2_345_000)).toBe('2.3 MP');
    expect(formatMegapixels(12_400_000)).toBe('12 MP');
    expect(formatMegapixels(Number.NaN)).toBe('—');
  });

  it('formatLatitude: one decimal and the hemisphere', () => {
    expect(formatLatitude(52.46)).toBe('52.5° N');
    expect(formatLatitude(-33.9)).toBe('33.9° S');
    expect(formatLatitude(0)).toBe('0.0° N');
  });
});

describe('formatMoment', () => {
  const NOW = Date.parse('2026-11-04T12:00:00Z');

  it('is day, month, hour and minute, without a year in this year', () => {
    expect(formatMoment('2026-10-31T14:02:00Z', NOW)).toMatch(/^31 Oct, \d{2}:\d{2}$/u);
  });

  it('names the year when it is not this one', () => {
    expect(formatMoment('2027-01-05T14:02:00Z', NOW)).toMatch(/^5 Jan 2027, \d{2}:\d{2}$/u);
  });

  it('is the same shape in the line of a job and in its details: no "08OCT-12:34"', () => {
    expect(formatMoment(new Date(2026, 9, 8, 12, 34).toISOString(), NOW)).toBe('8 Oct, 12:34');
    expect(formatMoment(new Date(2026, 11, 31, 0, 0).toISOString(), NOW)).toBe('31 Dec, 00:00');
  });

  it('shows what it cannot read as it is', () => {
    expect(formatMoment('soon', NOW)).toBe('soon');
    expect(formatMoment('', NOW)).toBe('');
  });
});

describe('formatDay', () => {
  it('is year-month-day with two digits each, whatever the language of the browser', () => {
    expect(formatDay(new Date(2026, 11, 3, 15, 0).toISOString())).toBe('2026-12-03');
    expect(formatDay(new Date(2027, 0, 5, 1, 0).toISOString())).toBe('2027-01-05');
  });

  it('shows what is no date as it is', () => {
    expect(formatDay('never')).toBe('never');
  });
});
