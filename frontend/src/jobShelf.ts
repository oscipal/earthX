// The jobs of this browser (UI-01 §6.4): the title, group, batch and archive of every job, and a copy of
// its order, in one key of `localStorage` until there are accounts (M6). Never the AOI apart from the
// order's own, never a result. The job API is unchanged: a job is reached by its `jobID` alone, and
// what is lost here (private window, cleared browser data) cannot be listed again (adr/0013).
//
// - Format `{ v: 1, jobs, batches, groups }`. A value of another `v` is kept as it is: the shelf then
//   works in memory only. A value that is no JSON is overwritten. Every entry is read on its own, and a
//   malformed one is dropped without the rest.
// - Nothing is ever removed from the shelf but an empty group, so a write is a union with what is stored:
//   another tab's jobs stay, and for one entry the latest write wins. A removed group is named in the
//   write, or the union would give it back.
// - When the browser is full the copies of the oldest orders go first, never an entry; the result says
//   so. When even that does not fit, the shelf is in memory only.
// - The jobs of the `sessionStorage` list of M4-13 are taken over once.

import { isJobId, type Order } from './processing';
import type { PreviewRange } from './processingPreview';

export const SHELF_KEY = 'earthx.processing.manager';
export const LEGACY_KEY = 'earthx.processing.jobs';
export const SHELF_VERSION = 1;
export const MAX_ORDER_BYTES = 64 * 1024;
export const MAX_TITLE_LENGTH = 200;
export const MAX_NAME_LENGTH = 100;
const MAX_REFUSED = 25;
const MAX_MESSAGE_LENGTH = 500;

export interface ShelfJob {
  jobID: string;
  expires: string;
  // What the user calls the job (K5); renamed in the manager (UI-01c).
  title: string | null;
  // What the panel called it when it was placed: an empty name in the manager brings it back.
  titleDefault: string | null;
  createdAt: string;
  archived: boolean;
  groupId: string | null;
  batchId: string | null;
  // What the job is of its batch: the pass or the scene (`BatchUnit.label`).
  part: string | null;
  // The range and colormap the user had set by hand in the panel when the job was started (M4-32b); its
  // result is drawn with them and no other result is. `null` for the default range and for a job of the
  // download dialog.
  range: PreviewRange | null;
  // The order as it was sent, up to `MAX_ORDER_BYTES`; the way to start the job again.
  order: Order | null;
  // The end of the day in which the job, deleted, can be restored (NM4-27); `null` for a job that is not deleted. A
  // deleted job is not followed, and after this time it stays in the list for good as deleted.
  deletedUntil: string | null;
  // The server deleted the job as well (it answered `200`), so "Restore" asks it; `false` for an entry that was only
  // deleted here (one that had expired, was cancelled or was no longer known).
  serverDeleted: boolean;
  // The server answered `404` once: it does not know the job any more (cancelled, a reset database, expired). It is
  // never asked about it again, not after a reload either.
  lost: boolean;
}

export interface ShelfBatch {
  id: string;
  title: string;
  titleDefault: string;
  createdAt: string;
  archived: boolean;
  groupId: string | null;
  // The parts the server refused to start.
  refused: { label: string; message: string }[];
}

export interface ShelfGroup {
  id: string;
  name: string;
}

export interface Shelf {
  jobs: ShelfJob[];
  batches: ShelfBatch[];
  groups: ShelfGroup[];
}

// `ok`: kept. `trimmed`: kept, but copies of orders were dropped. `memory`: not kept.
export type ShelfState = 'ok' | 'trimmed' | 'memory';

export interface ShelfLoad {
  shelf: Shelf;
  state: ShelfState;
  // The stored value is of a version this build does not know: it is never written.
  locked: boolean;
}

export interface ShelfSave {
  state: ShelfState;
  // The jobs whose order copy had to go.
  dropped: string[];
}

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const text = (value: unknown, max: number): string | null =>
  typeof value === 'string' && value !== '' && value.length <= max ? value : null;
const time = (value: unknown): string | null => (typeof value === 'string' && !Number.isNaN(Date.parse(value)) ? value : null);
const ID = /^[0-9a-f]{32}$/u;

// A random id for a batch or a group; it never leaves the browser. Not `crypto.randomUUID`, which a page
// served over plain HTTP does not have.
export function newId(): string {
  return Array.from(globalThis.crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('');
}

function local(): Storage | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null; // blocked storage throws on access
  }
}

// The order as far as a copy of it is kept: a recipe with its inputs and steps, and not too large.
export function orderCopy(order: unknown): Order | null {
  if (!record(order) || order.recipe_version !== 1 || !Array.isArray(order.inputs) || !Array.isArray(order.steps)) return null;
  return JSON.stringify(order).length <= MAX_ORDER_BYTES ? (order as unknown as Order) : null;
}

function rangeOf(value: unknown): PreviewRange | null {
  if (!record(value) || typeof value.vmin !== 'string' || typeof value.vmax !== 'string' || typeof value.colormap !== 'string') return null;
  return { vmin: value.vmin, vmax: value.vmax, colormap: value.colormap };
}

function parseShelf(raw: string): Shelf | 'foreign' | 'broken' {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return 'broken';
  }
  if (!record(data)) return 'broken';
  if (data.v !== SHELF_VERSION) return 'foreign';
  const list = (value: unknown): Record<string, unknown>[] => (Array.isArray(value) ? value.filter(record) : []);
  const groups: ShelfGroup[] = [];
  for (const g of list(data.groups)) {
    const name = text(g.name, MAX_NAME_LENGTH);
    if (typeof g.id === 'string' && ID.test(g.id) && name && !groups.some((x) => x.id === g.id)) groups.push({ id: g.id, name });
  }
  const known = (id: unknown): string | null => (typeof id === 'string' && groups.some((g) => g.id === id) ? id : null);
  const batches: ShelfBatch[] = [];
  for (const b of list(data.batches)) {
    const title = text(b.title, MAX_TITLE_LENGTH);
    const createdAt = time(b.createdAt);
    if (typeof b.id !== 'string' || !ID.test(b.id) || batches.some((x) => x.id === b.id) || !title || !createdAt) continue;
    const refused = list(b.refused)
      .map((r) => ({ label: text(r.label, MAX_TITLE_LENGTH), message: text(r.message, MAX_MESSAGE_LENGTH) }))
      .filter((r): r is { label: string; message: string } => r.label !== null && r.message !== null)
      .slice(0, MAX_REFUSED);
    batches.push({
      id: b.id, title, titleDefault: text(b.titleDefault, MAX_TITLE_LENGTH) ?? title, createdAt,
      archived: b.archived === true, groupId: known(b.groupId), refused,
    });
  }
  const jobs: ShelfJob[] = [];
  for (const j of list(data.jobs)) {
    const expires = time(j.expires);
    if (!isJobId(j.jobID) || !expires || jobs.some((x) => x.jobID === j.jobID)) continue;
    const batchId = typeof j.batchId === 'string' && batches.some((b) => b.id === j.batchId) ? j.batchId : null;
    const title = text(j.title, MAX_TITLE_LENGTH);
    const deletedUntil = time(j.deletedUntil);
    jobs.push({
      jobID: j.jobID,
      expires,
      title,
      titleDefault: text(j.titleDefault, MAX_TITLE_LENGTH) ?? title,
      createdAt: time(j.createdAt) ?? expires,
      archived: j.archived === true,
      groupId: known(j.groupId),
      batchId,
      part: batchId ? text(j.part, MAX_TITLE_LENGTH) : null,
      range: rangeOf(j.range),
      order: orderCopy(j.order),
      deletedUntil,
      serverDeleted: deletedUntil !== null && j.serverDeleted === true,
      lost: j.lost === true,
    });
  }
  return { jobs, batches, groups };
}

// Only what belongs on disk: a job entry carries more in memory (status, files), and none of it is kept.
function serialize(shelf: Shelf, without: ReadonlySet<string>): string {
  const jobs = shelf.jobs.map((j) => ({
    jobID: j.jobID,
    expires: j.expires,
    createdAt: j.createdAt,
    ...(j.title ? { title: j.title } : {}),
    ...(j.titleDefault && j.titleDefault !== j.title ? { titleDefault: j.titleDefault } : {}),
    ...(j.archived ? { archived: true } : {}),
    ...(j.groupId ? { groupId: j.groupId } : {}),
    ...(j.batchId ? { batchId: j.batchId, ...(j.part ? { part: j.part } : {}) } : {}),
    ...(j.range ? { range: { vmin: j.range.vmin, vmax: j.range.vmax, colormap: j.range.colormap } } : {}),
    ...(j.order && !without.has(j.jobID) ? { order: j.order } : {}),
    ...(j.deletedUntil ? { deletedUntil: j.deletedUntil, ...(j.serverDeleted ? { serverDeleted: true } : {}) } : {}),
    ...(j.lost ? { lost: true } : {}),
  }));
  const batches = shelf.batches.map((b) => ({
    id: b.id,
    title: b.title,
    ...(b.titleDefault !== b.title ? { titleDefault: b.titleDefault } : {}),
    createdAt: b.createdAt,
    ...(b.archived ? { archived: true } : {}),
    ...(b.groupId ? { groupId: b.groupId } : {}),
    refused: b.refused.slice(0, MAX_REFUSED).map((r) => ({ label: r.label.slice(0, MAX_TITLE_LENGTH), message: r.message.slice(0, MAX_MESSAGE_LENGTH) })),
  }));
  const groups = shelf.groups.map((g) => ({ id: g.id, name: g.name }));
  return JSON.stringify({ v: SHELF_VERSION, jobs, batches, groups });
}

// The union of what is stored and what this tab holds; for one entry this tab's wins.
function union<T>(stored: readonly T[], mine: readonly T[], idOf: (item: T) => string): T[] {
  const ids = new Set(mine.map(idOf));
  return [...mine, ...stored.filter((item) => !ids.has(idOf(item)))];
}

// What `sessionStorage` kept before UI-01: the jobs of this tab that have not expired, by `jobID`,
// `expires` and title.
function legacyJobs(now: number): ShelfJob[] {
  try {
    const parsed: unknown = JSON.parse(globalThis.sessionStorage?.getItem(LEGACY_KEY) ?? 'null');
    if (!Array.isArray(parsed)) return [];
    const jobs: ShelfJob[] = [];
    for (const entry of parsed.filter(record)) {
      const expires = time(entry.expires);
      const title = text(entry.title, MAX_TITLE_LENGTH);
      if (!isJobId(entry.jobID) || !expires || Date.parse(expires) <= now || jobs.some((j) => j.jobID === entry.jobID)) continue;
      jobs.push({
        jobID: entry.jobID, expires, title, titleDefault: title, createdAt: expires,
        archived: false, groupId: null, batchId: null, part: null, range: null, order: null,
        deletedUntil: null, serverDeleted: false, lost: false,
      });
    }
    return jobs;
  } catch {
    return [];
  }
}

const EMPTY: Shelf = { jobs: [], batches: [], groups: [] };

// What is stored, without taking anything over and without writing.
export function readShelf(): ShelfLoad {
  const target = local();
  if (!target) return { shelf: EMPTY, state: 'memory', locked: false };
  try {
    const raw = target.getItem(SHELF_KEY);
    const parsed = raw ? parseShelf(raw) : 'broken';
    if (parsed === 'foreign') return { shelf: EMPTY, state: 'memory', locked: true };
    return { shelf: raw && parsed !== 'broken' ? parsed : EMPTY, state: 'ok', locked: false };
  } catch {
    return { shelf: EMPTY, state: 'memory', locked: false };
  }
}

// At the start of the page: the shelf, with the jobs of the old list taken over. The old list goes once
// they are kept; where nothing can be kept it stays, so that a reload of the tab still finds them.
export function loadShelf(now: number = Date.now()): ShelfLoad {
  const loaded = readShelf();
  const adopted = legacyJobs(now).filter((j) => !loaded.shelf.jobs.some((k) => k.jobID === j.jobID));
  if (adopted.length === 0) return loaded;
  const shelf = { ...loaded.shelf, jobs: [...loaded.shelf.jobs, ...adopted] };
  if (loaded.locked) return { ...loaded, shelf };
  const saved = saveShelf(shelf);
  if (saved.state !== 'memory') {
    try {
      globalThis.sessionStorage?.removeItem(LEGACY_KEY);
    } catch {
      /* blocked: the old list stays, and is read as a repeat next time */
    }
  }
  return { shelf, state: saved.state, locked: false };
}

// Writes the shelf; see the head for what happens when it does not fit. A group named in `removedGroups`
// is taken out of what is stored as well: the union would give it back (UI-01 §6.10, only an empty group
// may go, which is the caller's rule).
export function saveShelf(mine: Shelf, removedGroups: readonly string[] = []): ShelfSave {
  const target = local();
  if (!target) return { state: 'memory', dropped: [] };
  let shelf = mine;
  try {
    const raw = target.getItem(SHELF_KEY);
    const stored = raw ? parseShelf(raw) : null;
    if (stored === 'foreign') return { state: 'memory', dropped: [] };
    if (stored && stored !== 'broken') {
      shelf = {
        jobs: union(stored.jobs, mine.jobs, (j) => j.jobID),
        batches: union(stored.batches, mine.batches, (b) => b.id),
        groups: union(stored.groups, mine.groups, (g) => g.id),
      };
    }
    if (removedGroups.length > 0) shelf = { ...shelf, groups: shelf.groups.filter((g) => !removedGroups.includes(g.id)) };
    if (shelf.jobs.length + shelf.batches.length + shelf.groups.length === 0) {
      target.removeItem(SHELF_KEY);
      return { state: 'ok', dropped: [] };
    }
    // The list is newest first, so of two placed in the same instant the later one in the list is the older.
    const oldest = [...shelf.jobs]
      .reverse()
      .filter((j) => j.order)
      .sort((a, b) => Date.parse(a.createdAt) - Date.parse(b.createdAt))
      .map((j) => j.jobID);
    const attempt = (count: number): Set<string> => {
      const without = new Set(oldest.slice(0, count));
      target.setItem(SHELF_KEY, serialize(shelf, without));
      return without;
    };
    try {
      attempt(0);
      return { state: 'ok', dropped: [] };
    } catch {
      /* too large: drop copies, the oldest first, as few as will do */
    }
    attempt(oldest.length);
    let low = 1;
    let high = oldest.length;
    while (low < high) {
      const middle = (low + high) >> 1;
      try {
        attempt(middle);
        high = middle;
      } catch {
        low = middle + 1;
      }
    }
    return { state: 'trimmed', dropped: [...attempt(low)] };
  } catch {
    return { state: 'memory', dropped: [] };
  }
}
