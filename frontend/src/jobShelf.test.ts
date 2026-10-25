// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  LEGACY_KEY,
  loadShelf,
  MAX_ORDER_BYTES,
  newId,
  orderCopy,
  readShelf,
  saveShelf,
  SHELF_KEY,
  type Shelf,
  type ShelfJob,
} from './jobShelf';

const JOB = 'AbCdEfGhIjKlMnOpQrSt_-';
const OTHER = 'ZZZZZZZZZZZZZZZZZZZZZZ';
const THIRD = 'YYYYYYYYYYYYYYYYYYYYYY';
const now = Date.parse('2026-10-10T12:00:00Z');
const ORDER = { recipe_version: 1, inputs: [{ name: 'a', dataset: 'd', groups: [['s']], assets: ['red'] }], steps: [] };

function job(jobID: string, over: Partial<ShelfJob> = {}): ShelfJob {
  return {
    jobID,
    expires: '2026-10-17T12:00:00Z',
    title: null,
    createdAt: '2026-10-10T10:00:00Z',
    archived: false,
    groupId: null,
    batchId: null,
    part: null,
    range: null,
    order: null,
    ...over,
  };
}

const shelfOf = (jobs: ShelfJob[], rest: Partial<Shelf> = {}): Shelf => ({ jobs, batches: [], groups: [], ...rest });
const stored = () => JSON.parse(localStorage.getItem(SHELF_KEY)!);
const GROUP = 'a'.repeat(32);
const BATCH = 'b'.repeat(32);

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('what the shelf writes', () => {
  it('is one key of version 1 with the jobs, the batches and the groups', () => {
    const batch = { id: BATCH, title: 'Band math · DEM', createdAt: '2026-10-10T10:00:00Z', archived: true, groupId: GROUP, refused: [{ label: 'S2', message: 'no' }] };
    const saved = saveShelf(
      shelfOf(
        [
          job(JOB, {
            title: 'Band math · DEM',
            archived: true,
            groupId: GROUP,
            batchId: BATCH,
            part: 'S1',
            range: { vmin: '0', vmax: '1', colormap: 'viridis' },
            order: ORDER as never,
          }),
        ],
        { batches: [batch], groups: [{ id: GROUP, name: 'Field 7' }] },
      ),
    );
    expect(saved).toEqual({ state: 'ok', dropped: [] });
    expect(stored()).toEqual({
      v: 1,
      jobs: [
        {
          jobID: JOB,
          expires: '2026-10-17T12:00:00Z',
          createdAt: '2026-10-10T10:00:00Z',
          title: 'Band math · DEM',
          archived: true,
          groupId: GROUP,
          batchId: BATCH,
          part: 'S1',
          range: { vmin: '0', vmax: '1', colormap: 'viridis' },
          order: ORDER,
        },
      ],
      batches: [batch],
      groups: [{ id: GROUP, name: 'Field 7' }],
    });
    expect(readShelf()).toEqual({ shelf: expect.objectContaining({ batches: [batch] }), state: 'ok', locked: false });
  });

  it('leaves out what a job knows only from the server: its state, its files, its tiles', () => {
    saveShelf(shelfOf([{ ...job(JOB), status: { status: 'running' }, files: [{ file: 'result.tif' }], tiles: { href: '/x' }, failure: 'no' } as never]));
    expect(Object.keys(stored().jobs[0]).sort()).toEqual(['createdAt', 'expires', 'jobID']);
  });

  it('writes the refused parts of a batch as far as they are read back, and the fields of a group it knows', () => {
    const refused = Array.from({ length: 30 }, (_, i) => ({ label: `S${i}`, message: 'm'.repeat(600) }));
    const batch = { id: BATCH, title: 'T', createdAt: '2026-10-10T10:00:00Z', archived: false, groupId: null, refused };
    saveShelf(shelfOf([], { batches: [batch], groups: [{ id: GROUP, name: 'G', extra: 1 } as never] }));
    expect(stored().groups).toEqual([{ id: GROUP, name: 'G' }]);
    expect(stored().batches[0].refused).toHaveLength(25);
    expect(stored().batches[0].refused[0].message).toHaveLength(500);
    expect(readShelf().shelf.batches[0].refused).toHaveLength(25);
  });

  it('writes nothing for a shelf that is empty', () => {
    expect(saveShelf(shelfOf([]))).toEqual({ state: 'ok', dropped: [] });
    expect(localStorage.getItem(SHELF_KEY)).toBeNull();
  });

  it('adds to what another tab wrote and lets the latest write win for one entry', () => {
    saveShelf(shelfOf([job(OTHER, { title: 'from the other tab' }), job(JOB, { title: 'old' })], { groups: [{ id: GROUP, name: 'G' }] }));
    saveShelf(shelfOf([job(JOB, { title: 'new' })]));
    const { jobs, groups } = stored();
    expect(jobs.map((j: { jobID: string; title: string }) => [j.jobID, j.title]).sort()).toEqual([
      [JOB, 'new'],
      [OTHER, 'from the other tab'],
    ]);
    expect(groups).toEqual([{ id: GROUP, name: 'G' }]);
  });
});

describe('what the shelf reads', () => {
  const write = (value: unknown) => localStorage.setItem(SHELF_KEY, typeof value === 'string' ? value : JSON.stringify(value));
  const entry = (over: Record<string, unknown> = {}) => ({ jobID: JOB, expires: '2026-10-17T12:00:00Z', ...over });

  it('is empty where nothing was kept', () => {
    expect(readShelf()).toEqual({ shelf: { jobs: [], batches: [], groups: [] }, state: 'ok', locked: false });
  });

  it('keeps a job past its expiry: it stays in the list as expired', () => {
    write({ v: 1, jobs: [entry({ expires: '2026-10-01T12:00:00Z' })], batches: [], groups: [] });
    expect(readShelf().shelf.jobs.map((j) => j.jobID)).toEqual([JOB]);
  });

  it('drops a malformed entry on its own and keeps the rest', () => {
    write({
      v: 1,
      jobs: [
        entry(),
        entry({ jobID: '../x' }),
        entry({ jobID: OTHER, expires: 'tomorrow' }),
        entry({ jobID: THIRD, expires: undefined }),
        'nonsense',
        null,
        entry({ expires: '2026-10-18T12:00:00Z' }),
      ],
      batches: [{ id: BATCH }, 7],
      groups: [{ id: 'short', name: 'x' }, { id: GROUP }],
    });
    const { shelf } = readShelf();
    expect(shelf.jobs.map((j) => [j.jobID, j.expires])).toEqual([[JOB, '2026-10-17T12:00:00Z']]);
    expect(shelf.batches).toEqual([]);
    expect(shelf.groups).toEqual([]);
  });

  it('drops a title that is no text, empty or too long, and keeps the job', () => {
    write({
      v: 1,
      jobs: [entry({ title: { html: '<b>x</b>' } }), entry({ jobID: OTHER, title: 'x'.repeat(201) }), entry({ jobID: THIRD, title: '' })],
    });
    expect(readShelf().shelf.jobs.map((j) => j.title)).toEqual([null, null, null]);
  });

  it('points a job only at a group or batch that exists', () => {
    write({
      v: 1,
      jobs: [entry({ groupId: GROUP, batchId: BATCH, part: 'S1' }), entry({ jobID: OTHER, groupId: 'c'.repeat(32), batchId: 'd'.repeat(32), part: 'S1' })],
      batches: [{ id: BATCH, title: 'T', createdAt: '2026-10-10T10:00:00Z' }],
      groups: [{ id: GROUP, name: 'G' }],
    });
    expect(readShelf().shelf.jobs.map((j) => [j.groupId, j.batchId, j.part])).toEqual([
      [GROUP, BATCH, 'S1'],
      [null, null, null],
    ]);
  });

  it('keeps a copy of the order only where it is a recipe of at most 64 KB', () => {
    const large = { ...ORDER, aoi: { type: 'Polygon', coordinates: [[[0, 0]], 'x'.repeat(MAX_ORDER_BYTES)] } };
    write({
      v: 1,
      jobs: [entry({ order: ORDER }), entry({ jobID: OTHER, order: large }), entry({ jobID: THIRD, order: { recipe_version: 2 } }), entry({ jobID: 'X'.repeat(22), order: 'text' })],
    });
    expect(readShelf().shelf.jobs.map((j) => j.order !== null)).toEqual([true, false, false, false]);
    expect(orderCopy(large)).toBeNull();
    expect(orderCopy(ORDER)).toEqual(ORDER);
  });

  it('keeps a range only with its three texts', () => {
    write({ v: 1, jobs: [entry({ range: { vmin: '0', vmax: '1', colormap: '' } }), entry({ jobID: OTHER, range: { vmin: 0, vmax: 1, colormap: 'x' } })] });
    expect(readShelf().shelf.jobs.map((j) => j.range)).toEqual([{ vmin: '0', vmax: '1', colormap: '' }, null]);
  });

  it('is not written over when its version is not known, and works in memory', () => {
    write({ v: 2, jobs: [entry()], future: true });
    const before = localStorage.getItem(SHELF_KEY);
    expect(readShelf()).toEqual({ shelf: { jobs: [], batches: [], groups: [] }, state: 'memory', locked: true });
    expect(saveShelf(shelfOf([job(OTHER)])).state).toBe('memory');
    write({});
    expect(readShelf().locked).toBe(true);
    write({ v: 2, jobs: [entry()], future: true });
    expect(localStorage.getItem(SHELF_KEY)).toBe(before);
  });

  it('is written over where it is no JSON, and the shelf is empty until then', () => {
    write('[');
    expect(readShelf()).toEqual({ shelf: { jobs: [], batches: [], groups: [] }, state: 'ok', locked: false });
    write('[1,2]');
    expect(readShelf().locked).toBe(false);
    expect(saveShelf(shelfOf([job(JOB)])).state).toBe('ok');
    expect(stored().jobs).toHaveLength(1);
  });

  it('works in memory where the browser blocks its storage', () => {
    vi.spyOn(globalThis, 'localStorage', 'get').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    expect(readShelf().state).toBe('memory');
    expect(() => saveShelf(shelfOf([job(JOB)]))).not.toThrow();
    expect(saveShelf(shelfOf([job(JOB)])).state).toBe('memory');
  });

  it('works in memory where reading it throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    expect(readShelf().state).toBe('memory');
    expect(saveShelf(shelfOf([job(JOB)])).state).toBe('memory');
  });
});

describe('a browser that is full', () => {
  // Refuses a value longer than `limit`, as the quota does.
  function limit(characters: number) {
    const set = Storage.prototype.setItem;
    return vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (this: Storage, key: string, value: string) {
      if (value.length > characters) throw new DOMException('full', 'QuotaExceededError');
      set.call(this, key, value);
    });
  }
  const idOf = (i: number) => `J${String(i).padStart(21, '0')}`;
  const withOrders = (count: number) =>
    shelfOf(
      Array.from({ length: count }, (_, i) =>
        job(idOf(i), {
          createdAt: new Date(Date.parse('2026-10-10T10:00:00Z') + i * 60_000).toISOString(),
          order: { ...ORDER, pad: 'x'.repeat(1000) } as never,
        }),
      ),
    );

  it('drops the copies of the oldest orders first, as few as will do, and never an entry', () => {
    limit(3500);
    const saved = saveShelf(withOrders(5));
    expect(saved.state).toBe('trimmed');
    expect(saved.dropped).toEqual([idOf(0), idOf(1), idOf(2)]);
    const { jobs } = stored();
    expect(jobs.map((j: { jobID: string }) => j.jobID)).toEqual([0, 1, 2, 3, 4].map(idOf));
    expect(jobs.map((j: { order?: unknown }) => j.order !== undefined)).toEqual([false, false, false, true, true]);
  });

  it('keeps every copy that fits', () => {
    limit(100_000);
    expect(saveShelf(withOrders(5))).toEqual({ state: 'ok', dropped: [] });
  });

  it('works in memory where not even the entries fit', () => {
    limit(10);
    const saved = saveShelf(withOrders(3));
    expect(saved).toEqual({ state: 'memory', dropped: [] });
  });

  it('works in memory where there is no copy to drop and the write fails', () => {
    limit(10);
    expect(saveShelf(shelfOf([job(JOB)])).state).toBe('memory');
  });
});

describe('the list of jobs of this tab before UI-01', () => {
  const legacy = (list: unknown[]) => sessionStorage.setItem(LEGACY_KEY, JSON.stringify(list));
  const entry = (jobID: string, extra: Record<string, unknown> = {}) => ({ jobID, expires: '2026-10-17T12:00:00Z', ...extra });

  it('is taken over once, with its titles, and removed', () => {
    legacy([entry(JOB, { title: 'Band math · DEM' }), entry(OTHER)]);
    const loaded = loadShelf(now);
    expect(loaded.shelf.jobs.map((j) => [j.jobID, j.title])).toEqual([
      [JOB, 'Band math · DEM'],
      [OTHER, null],
    ]);
    expect(sessionStorage.getItem(LEGACY_KEY)).toBeNull();
    expect(stored().jobs).toHaveLength(2);
    expect(loadShelf(now).shelf.jobs).toHaveLength(2);
  });

  it('does not double a job the shelf holds, and does not take an expired or malformed one', () => {
    saveShelf(shelfOf([job(JOB, { title: 'kept' })]));
    legacy([entry(JOB, { title: 'old' }), entry(OTHER, { expires: '2026-10-10T11:59:59Z' }), entry('../x'), entry(THIRD, { expires: 'tomorrow' }), 'nonsense']);
    expect(loadShelf(now).shelf.jobs.map((j) => [j.jobID, j.title])).toEqual([[JOB, 'kept']]);
  });

  it('stays where the shelf cannot be written, so that a reload of the tab finds it', () => {
    legacy([entry(JOB)]);
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError');
    });
    const loaded = loadShelf(now);
    expect(loaded.shelf.jobs).toHaveLength(1);
    expect(loaded.state).toBe('memory');
    expect(sessionStorage.getItem(LEGACY_KEY)).not.toBeNull();
  });

  it('stays where the shelf is of a version this build does not know', () => {
    localStorage.setItem(SHELF_KEY, JSON.stringify({ v: 9 }));
    legacy([entry(JOB)]);
    const loaded = loadShelf(now);
    expect(loaded).toEqual({ shelf: expect.objectContaining({ jobs: [expect.objectContaining({ jobID: JOB })] }), state: 'memory', locked: true });
    expect(sessionStorage.getItem(LEGACY_KEY)).not.toBeNull();
    expect(JSON.parse(localStorage.getItem(SHELF_KEY)!)).toEqual({ v: 9 });
  });

  it('is read as nothing where it is no list', () => {
    sessionStorage.setItem(LEGACY_KEY, '{"jobID":"x"}');
    expect(loadShelf(now).shelf.jobs).toEqual([]);
    sessionStorage.setItem(LEGACY_KEY, '[');
    expect(loadShelf(now).shelf.jobs).toEqual([]);
  });
});

describe('an id', () => {
  it('is 32 hexadecimal characters and differs every time', () => {
    const ids = new Set(Array.from({ length: 50 }, newId));
    expect(ids.size).toBe(50);
    for (const id of ids) expect(id).toMatch(/^[0-9a-f]{32}$/);
  });
});
