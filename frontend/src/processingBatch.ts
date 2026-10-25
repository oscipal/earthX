// A batch of orders (M4-13c-4, §3.6): the same steps, bands and data type for
// every pass or every scene of the selection, one job each. Pure functions; the
// panel's state lives in `processingStore.ts`. No backend: a job of a batch is a
// job like any other.

import { MAX_TITLE_LENGTH } from './jobShelf';
import type { EstimateDocument } from './processing';
import type { Pass } from './processingOrder';
import type { StacItem } from './types';

// As many jobs as one order can name scenes (`MAX_ORDER_ITEMS` of `api/intake.py`).
export const MAX_BATCH_JOBS = 25;
// Estimates asked at once; the starts follow one after the other.
export const ESTIMATE_PARALLEL = 4;

export const TOO_MANY_JOBS = `At most ${MAX_BATCH_JOBS} jobs at once`;

export type RunAs = 'one' | 'pass' | 'scene';

// What one job of a batch is made of.
export interface BatchUnit {
  key: string;
  label: string;
  items: StacItem[];
}

export interface RunChoice {
  value: RunAs;
  label: string;
  count: number;
  // Why the choice cannot be taken, or `null`.
  disabled: string | null;
}

// The choices for "Run as": one job (the pass the user picked), one per pass and
// one per scene. A choice that would make a single job is left out.
export function runChoices(passes: readonly Pass[], scenes: readonly StacItem[]): RunChoice[] {
  const choices: RunChoice[] = [{ value: 'one', label: 'One job', count: 1, disabled: null }];
  const batch = (value: RunAs, noun: string, count: number) => {
    if (count > 1) {
      choices.push({
        value,
        label: `One job per ${noun} (${count})`,
        count,
        disabled: count > MAX_BATCH_JOBS ? TOO_MANY_JOBS : null,
      });
    }
  };
  batch('pass', 'pass', passes.length);
  batch('scene', 'scene', scenes.length);
  return choices;
}

// The choice in force: the wanted one if it is still offered and allowed, else one job.
export function effectiveRunAs(wanted: RunAs, choices: readonly RunChoice[]): RunAs {
  return choices.some((c) => c.value === wanted && c.disabled === null) ? wanted : 'one';
}

export function unitsOf(
  runAs: RunAs,
  pass: Pass | null,
  passes: readonly Pass[],
  scenes: readonly StacItem[],
): BatchUnit[] {
  if (runAs === 'pass') return passes.map((p) => ({ key: p.key, label: p.label, items: p.items }));
  if (runAs === 'scene') return scenes.map((item) => ({ key: item.id, label: item.id, items: [item] }));
  return pass ? [{ key: pass.key, label: pass.label, items: pass.items }] : [];
}

// The pass the panel reads bands, summary and preview from when there are many jobs:
// all the scenes of the batch, in one piece.
export function batchPass(runAs: RunAs, units: readonly BatchUnit[]): Pass | null {
  if (units.length === 0) return null;
  return {
    key: 'batch',
    label: runAs === 'pass' ? `${units.length} passes` : '',
    items: units.flatMap((u) => u.items),
  };
}

// The scenes that were found under another dataset than the order's. Where a
// scene was found is the context of the search (the results section it is in, or
// the dataset it was fetched under), not its `collection`: a federated source may
// name its collection otherwise than the platform names the dataset. The
// selection has one dataset today; the order refuses a stranger all the same.
export function foreignScenes(
  datasetId: string,
  items: readonly StacItem[],
  foundUnder: (item: StacItem) => string | null,
): StacItem[] {
  return items.filter((item) => {
    const found = foundUnder(item);
    return found !== null && found !== datasetId;
  });
}

export function foreignReason(foreign: readonly StacItem[]): string {
  return `The selection holds scenes of another dataset (${foreign.map((i) => i.id).join(', ')}); a job takes one dataset.`;
}

// --- the estimate as a sum ---------------------------------------------------------

export interface EstimateTotal {
  jobs: number;
  outputPixels: number;
  size: number;
  units: number;
  // `PT<seconds>S`, the form the route writes; `null` when a job names its
  // duration in another form (the sum would be a guess).
  duration: string | null;
}

// `PT12.3S` → 12.3; anything else is `null`.
export function secondsOf(duration: string): number | null {
  const match = /^PT(\d+(?:\.\d+)?)S$/u.exec(duration);
  return match ? Number(match[1]) : null;
}

export function totalOf(docs: readonly EstimateDocument[]): EstimateTotal {
  const seconds = docs.map((doc) => secondsOf(doc.estimate.duration));
  const known = seconds.every((value): value is number => value !== null);
  const sum = known ? seconds.reduce((a, b) => a + b, 0) : 0;
  return {
    jobs: docs.length,
    outputPixels: docs.reduce((sum, doc) => sum + doc.estimate.outputPixels, 0),
    size: docs.reduce((sum, doc) => sum + doc.estimate.size, 0),
    units: docs.reduce((sum, doc) => sum + doc.estimate.units, 0),
    duration: known ? `PT${Math.round(sum * 10) / 10}S` : null,
  };
}

// --- the title of a job (K5, UI-01 §6.5) ----------------------------------------------

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// "12 Oct", with the year when it is not the current one.
function dayText(year: number, month: number, day: number, now: Date): string {
  return `${day} ${MONTHS[month]}${year === now.getFullYear() ? '' : ` ${year}`}`;
}

// The day in a title: the day the scenes were acquired (UTC) where they share one — as the name of a
// download does — else the day the job is started (the local one). Only a dataset whose results are
// grouped by the instant `datetime` has a day of acquisition (`registry.acquisition_day`).
export function titleDay(items: readonly StacItem[], resultsGroupBy: readonly string[] | null, now: Date = new Date()): string {
  const days = new Set<string>();
  if (resultsGroupBy?.includes('datetime')) {
    for (const item of items) {
      const instant = item.properties?.datetime;
      const time = typeof instant === 'string' ? Date.parse(instant) : NaN;
      days.add(Number.isNaN(time) ? '' : new Date(time).toISOString().slice(0, 10));
    }
  }
  const [day] = days;
  if (days.size === 1 && day) {
    const [y, m, d] = day.split('-').map(Number);
    return dayText(y, m - 1, d, now);
  }
  return dayText(now.getFullYear(), now.getMonth(), now.getDate(), now);
}

// "<operators> · <dataset> · <day>": "Band math · Sentinel-2 L2A · 12 Oct". A batch has one title; its
// parts are told apart by their label.
export function jobTitle(args: { operators: readonly string[]; dataset: string; day?: string }): string {
  const names = [...new Set(args.operators)].join(', ');
  return [names, args.dataset, args.day].filter(Boolean).join(' · ').slice(0, MAX_TITLE_LENGTH);
}

// --- a few at a time ----------------------------------------------------------------

// Runs `work` for every item, at most `limit` at once, in the order given. Stops
// handing out items once `signal` has aborted; the results of those are missing.
export async function runPool<T, R>(
  items: readonly T[],
  limit: number,
  signal: AbortSignal,
  work: (item: T, index: number) => Promise<R>,
): Promise<(R | undefined)[]> {
  const results: (R | undefined)[] = new Array<R | undefined>(items.length).fill(undefined);
  let next = 0;
  const lane = async () => {
    while (!signal.aborted && next < items.length) {
      const index = next++;
      results[index] = await work(items[index], index);
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, lane));
  return results;
}
