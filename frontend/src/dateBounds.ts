// The days the date fields of the search offer (UI-05 §3.3, Otto 06.11.2026): the temporal extent of the chosen datasets
// that have a time axis, from the earliest start to the latest end, an open end being today. Days are UTC, in the form a
// date field holds ("2015-06-27"). An extent this cannot read leaves that side open rather than guessing a bound.

import type { DatasetOption } from './datasets';

export interface DayBounds {
  min: string | null;
  max: string | null;
}

const DAY = /^\d{4}-\d{2}-\d{2}$/u;

// The UTC day of an instant, or `null` for what is not one.
export function utcDay(iso: string): string | null {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  const day = date.toISOString().slice(0, 10);
  return DAY.test(day) ? day : null;
}

export function todayUtc(): string {
  return new Date().toISOString().slice(0, 10);
}

// One dataset's days: `null` on a side the extent leaves open or does not say; an end that is open is today, and an
// extent that ends before it starts says nothing.
function boundsOf(dataset: DatasetOption, today: string): DayBounds {
  const interval = dataset.collection.extent?.temporal?.interval?.[0];
  if (!Array.isArray(interval)) return { min: null, max: null };
  const [start, end] = interval;
  const min = typeof start === 'string' ? utcDay(start) : null;
  const max = end === null ? today : typeof end === 'string' ? utcDay(end) : null;
  if (min && max && min > max) return { min: null, max: null };
  return { min, max };
}

// The bounds over the chosen datasets with a time axis, or `null` where none of them has one (the fields are free, or
// locked when every chosen one lacks an axis).
export function dateBounds(datasets: DatasetOption[], selectedIds: readonly string[], today: string): DayBounds | null {
  const timed = datasets.filter((d) => d.viewable && d.hasTimeAxis && selectedIds.includes(d.id));
  if (timed.length === 0) return null;
  const each = timed.map((d) => boundsOf(d, today));
  const min = each.every((b) => b.min) ? each.map((b) => b.min!).sort()[0] : null;
  const max = each.every((b) => b.max) ? each.map((b) => b.max!).sort().at(-1)! : null;
  return { min, max };
}

// A day of a field moved onto the nearest bound; an empty field, or one this cannot read, stays as it is.
export function clampDay(value: string, bounds: DayBounds | null): string {
  if (!bounds || !DAY.test(value)) return value;
  if (bounds.min && value < bounds.min) return bounds.min;
  if (bounds.max && value > bounds.max) return bounds.max;
  return value;
}
