// Datums-Fallback (plan §4.5.1): finds the nearest date with results when a
// search comes back empty for the chosen time range, in two steps. A probe
// (one page, no paging) finds a *date*; the caller then runs a normal, full
// search for that one date. The probe's own result is never shown — only
// used to decide *which* day to search fully — so a probe that was itself
// truncated must say so in the notice rather than claim more than it saw
// (Prinzip 9, "Ehrlichkeit in der Anzeige").

import type { StacItem } from './types';

export const FALLBACK_STAGE_DAYS = [7, 30, 90] as const;

export interface FallbackWindow {
  stageDays: number;
  start: string; // YYYY-MM-DD
  end: string; // YYYY-MM-DD
}

export interface ProbePage {
  features: StacItem[];
  numberMatched: number | null;
  numberReturned: number;
}

function parseDateOnlyMs(value: string): number {
  return Date.parse(`${value}T00:00:00Z`);
}

function addDaysIso(ms: number, days: number): string {
  return new Date(ms + days * 86_400_000).toISOString().slice(0, 10);
}

// `null` when neither bound is set: there is no chosen time range to expand
// around, so there is nothing for the fallback to do.
export function fallbackWindows(dateFrom: string, dateTo: string): FallbackWindow[] | null {
  if (!dateFrom && !dateTo) return null;
  const fromMs = parseDateOnlyMs(dateFrom || dateTo);
  const toMs = parseDateOnlyMs(dateTo || dateFrom);
  return FALLBACK_STAGE_DAYS.map((stageDays) => ({
    stageDays,
    start: addDaysIso(fromMs, -stageDays),
    end: addDaysIso(toMs, stageDays),
  }));
}

// The instant "nearest" is measured from: the midpoint of the chosen range,
// or the one bound given when only one is set.
export function referencePointMs(dateFrom: string, dateTo: string): number | null {
  if (!dateFrom && !dateTo) return null;
  const fromMs = parseDateOnlyMs(dateFrom || dateTo);
  const toMs = parseDateOnlyMs(dateTo || dateFrom);
  return (fromMs + toMs) / 2;
}

export function itemDateMs(item: StacItem): number | null {
  const value = item.properties?.['datetime'];
  if (typeof value !== 'string') return null;
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? null : ms;
}

// The item closest to the reference instant; a broken `datetime` is skipped
// rather than crashing the fallback, and a tie goes to the older item
// (deterministic).
export function pickNearest(items: StacItem[], referenceMs: number): StacItem | null {
  let best: StacItem | null = null;
  let bestDiff = Infinity;
  let bestMs = Infinity;
  for (const item of items) {
    const ms = itemDateMs(item);
    if (ms === null) continue;
    const diff = Math.abs(ms - referenceMs);
    if (diff < bestDiff || (diff === bestDiff && ms < bestMs)) {
      best = item;
      bestDiff = diff;
      bestMs = ms;
    }
  }
  return best;
}

export interface FallbackResult {
  stageDays: number;
  item: StacItem;
  /** The probe itself was truncated (`numberMatched > numberReturned`): the
   *  nearest date found is not proven to be the nearest date there is. */
  capped: boolean;
  seen: number;
  matched: number | null;
}

// Runs `probe` for each stage window in turn (±7, ±30, ±90 days) until one
// finds an item, and returns the nearest one. `null` when all three stages
// are empty, or when there is no time range to expand around at all.
export async function findFallback(
  probe: (window: FallbackWindow) => Promise<ProbePage>,
  dateFrom: string,
  dateTo: string,
): Promise<FallbackResult | null> {
  const windows = fallbackWindows(dateFrom, dateTo);
  const reference = referencePointMs(dateFrom, dateTo);
  if (!windows || reference === null) return null;
  for (const window of windows) {
    const page = await probe(window);
    const nearest = pickNearest(page.features, reference);
    if (nearest) {
      return {
        stageDays: window.stageDays,
        item: nearest,
        capped: page.numberMatched !== null && page.numberMatched > page.numberReturned,
        seen: page.numberReturned,
        matched: page.numberMatched,
      };
    }
  }
  return null;
}

export const NO_FALLBACK_MESSAGE =
  'Kein Treffer im gewählten Zeitraum und auch nicht ±90 Tage daneben.';

function germanDate(ms: number): string {
  const d = new Date(ms);
  const dd = String(d.getUTCDate()).padStart(2, '0');
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
  return `${dd}.${mm}.${d.getUTCFullYear()}`;
}

export function fallbackNotice(result: FallbackResult): string {
  const ms = itemDateMs(result.item);
  const dateLabel = ms === null ? '?' : germanDate(ms);
  if (!result.capped) {
    return `Kein Treffer im gewählten Zeitraum — nächstgelegene Aufnahme: ${dateLabel}`;
  }
  return (
    `Kein Treffer im gewählten Zeitraum — nächstgelegene gefundene Aufnahme: ${dateLabel} ` +
    `(Stichprobe aus ${result.seen} von ${result.matched} Treffern ±${result.stageDays} Tagen)`
  );
}

// The full-day range to search once the fallback has picked a date.
export function fullDayRange(item: StacItem): string | null {
  const ms = itemDateMs(item);
  if (ms === null) return null;
  const date = new Date(ms).toISOString().slice(0, 10);
  return `${date}T00:00:00Z/${date}T23:59:59Z`;
}
