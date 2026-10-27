// The kind of a full-resolution view, as short as it goes, for its head: "AOI crop", "whole scene", and with several
// scenes how many are merged (Otto, 27.10.2026).

export function viewKind(cropToAoi: boolean, scenes: number): string {
  const kind = cropToAoi ? 'AOI crop' : 'whole scene';
  return scenes > 1 ? `${cropToAoi ? 'AOI crop · ' : ''}${scenes} scenes merged` : kind;
}

// The acquisition date of the scenes of a view, in UTC as YYYY-MM-DD: one date when they share it, else the span
// "2025-07-29 – 2025-08-03". Null for scenes without an instant (a product with a period, like the elevation model).
export function viewDates(items: readonly { properties?: { datetime?: unknown } | null }[]): string | null {
  const days = items
    .map((item) => item.properties?.datetime)
    .filter((value): value is string => typeof value === 'string')
    .map((value) => new Date(value))
    .filter((date) => !Number.isNaN(date.getTime()))
    .map((date) => date.toISOString().slice(0, 10))
    .sort();
  if (days.length === 0) return null;
  const [first, last] = [days[0], days[days.length - 1]];
  return first === last ? first : `${first} – ${last}`;
}
