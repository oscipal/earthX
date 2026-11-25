// UI-12 (8): the days of a date field, independent of the browser's language.

import { describe, expect, it } from 'vitest';

import { dayAllowed, isDay, monthAllowed, monthCells, monthToShow, shiftMonth } from './dayCalendar';
import { formatMonth, weekdayHeads } from './numberFormat';

describe('a day', () => {
  it('is a day of the calendar written "YYYY-MM-DD"', () => {
    expect(isDay('2026-12-03')).toBe(true);
    expect(isDay('2024-02-29')).toBe(true);
  });

  it.each(['2026-02-30', '2025-02-29', '2026-13-01', '03.12.2026', '12/03/2026', '2026-12-3', '', '2026-12-03T00:00:00Z'])(
    'is not "%s"',
    (text) => expect(isDay(text)).toBe(false),
  );
});

describe('the calendar of a month', () => {
  it('starts on a Monday, with gaps before the first and after the last day', () => {
    // 1 Dec 2026 is a Tuesday, the 31st a Thursday.
    const cells = monthCells({ year: 2026, month: 11 });
    expect(cells.length % 7).toBe(0);
    expect(cells.slice(0, 2)).toEqual([null, '2026-12-01']);
    expect(cells.filter((c) => c !== null)).toHaveLength(31);
    expect(cells.slice(-4)).toEqual(['2026-12-31', null, null, null]);
  });

  it('has its heads and its name in English, Monday first', () => {
    expect(weekdayHeads()).toEqual(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']);
    expect(formatMonth(2026, 10)).toBe('November 2026');
  });

  it('opens on the day of the field, else the latest day allowed, else today', () => {
    expect(monthToShow('2020-03-15', null, '2026-11-25')).toEqual({ year: 2020, month: 2 });
    expect(monthToShow('', { min: null, max: '2021-12-23' }, '2026-11-25')).toEqual({ year: 2021, month: 11 });
    expect(monthToShow('not a day', null, '2026-11-25')).toEqual({ year: 2026, month: 10 });
  });

  it('turns over the turn of the year both ways', () => {
    expect(shiftMonth({ year: 2026, month: 11 }, 1)).toEqual({ year: 2027, month: 0 });
    expect(shiftMonth({ year: 2026, month: 0 }, -1)).toEqual({ year: 2025, month: 11 });
  });

  it('offers only the days and months inside the bounds', () => {
    const bounds = { min: '2014-10-03', max: '2021-12-23' };
    expect(dayAllowed('2014-10-02', bounds)).toBe(false);
    expect(dayAllowed('2014-10-03', bounds)).toBe(true);
    expect(dayAllowed('2021-12-24', bounds)).toBe(false);
    expect(dayAllowed('1900-01-01', null)).toBe(true);
    expect(monthAllowed({ year: 2014, month: 9 }, bounds)).toBe(true);
    expect(monthAllowed({ year: 2014, month: 8 }, bounds)).toBe(false);
    expect(monthAllowed({ year: 2022, month: 0 }, bounds)).toBe(false);
  });
});
