// The days of a date field (UI-12, Otto: the format does not depend on the browser's language): a day is written
// "2026-12-03" (`formatDay`), typed so, and chosen in a calendar of the month, Monday first. All in UTC, as the API counts days.

import type { DayBounds } from './dateBounds';

const DAY = /^(\d{4})-(\d{2})-(\d{2})$/u;

// Whether a text is a day of the calendar ("2026-02-30" is not).
export function isDay(text: string): boolean {
  const match = DAY.exec(text);
  if (!match) return false;
  const [year, month, day] = match.slice(1).map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

export interface Month {
  year: number;
  // 0 for January.
  month: number;
}

const two = (n: number): string => String(n).padStart(2, '0');

export const dayOf = (year: number, month: number, day: number): string => `${year}-${two(month + 1)}-${two(day)}`;

// The month a calendar opens with: that of the day in the field, else that of the latest day allowed, else of `today`.
export function monthToShow(value: string, bounds: DayBounds | null, today: string): Month {
  const day = isDay(value) ? value : bounds?.max && isDay(bounds.max) ? bounds.max : today;
  return { year: Number(day.slice(0, 4)), month: Number(day.slice(5, 7)) - 1 };
}

export function shiftMonth({ year, month }: Month, by: number): Month {
  const index = year * 12 + month + by;
  return { year: Math.floor(index / 12), month: ((index % 12) + 12) % 12 };
}

// The cells of a month in rows of seven, Monday first: `null` before the first day and after the last.
export function monthCells({ year, month }: Month): (string | null)[] {
  const first = new Date(Date.UTC(year, month, 1));
  const lead = (first.getUTCDay() + 6) % 7;
  const length = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const cells: (string | null)[] = [...Array<null>(lead).fill(null), ...Array.from({ length }, (_, i) => dayOf(year, month, i + 1))];
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
}

// Whether a day may be chosen: inside the bounds, where there are any.
export const dayAllowed = (day: string, bounds: DayBounds | null): boolean =>
  !(bounds?.min && day < bounds.min) && !(bounds?.max && day > bounds.max);

// Whether the month has any day that may be chosen (the arrows of the calendar stop at the bounds).
export function monthAllowed({ year, month }: Month, bounds: DayBounds | null): boolean {
  const first = dayOf(year, month, 1);
  const last = dayOf(year, month, new Date(Date.UTC(year, month + 1, 0)).getUTCDate());
  return !(bounds?.min && last < bounds.min) && !(bounds?.max && first > bounds.max);
}
