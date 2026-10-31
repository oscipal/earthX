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
const ORDER = {
  recipe_version: 2,
  inputs: [{ name: 'a', dataset: 'd', groups: [['s']] }],
  steps: [],
  output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['red'] },
};
// A copy a browser kept before version 2 (adr/0020 §11).
const ORDER_V1 = {
  recipe_version: 1,
  inputs: [{ name: 'a', dataset: 'd', groups: [['s']], assets: ['red'] }],
  steps: [],
  output: { kind: 'raster', format: 'cog', dtype: 'float32' },
};

function job(jobID: string, over: Partial<ShelfJob> = {}): ShelfJob {
  return {
    jobID,
    expires: '2026-10-17T12:00:00Z',
    title: null,
    titleDefault: null,
    createdAt: '2026-10-10T10:00:00Z',
    archived: false,
    groupId: null,
    batchId: null,
    part: null,
    range: null,
    bandRanges: {},
    shownBand: null,
    dates: null,
    order: null,
    deletedUntil: null,
    serverDeleted: false,
    lost: false,
    superseded: false,
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
    const batch = { id: BATCH, title: 'Band math · DEM', titleDefault: 'Band math · DEM', createdAt: '2026-10-10T10:00:00Z', archived: true, groupId: GROUP, refused: [{ label: 'S2', message: 'no' }] };
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
      // The default title is written only where it differs from the title.
      batches: [{ ...batch, titleDefault: undefined }],
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
    const batch = { id: BATCH, title: 'T', titleDefault: 'T', createdAt: '2026-10-10T10:00:00Z', archived: false, groupId: null, refused };
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

describe('a deleted job and one the server forgot (NM4-27)', () => {
  const until = '2026-10-11T12:00:00Z';

  it('is written with the end of its day and who deleted it, and read back', () => {
    saveShelf(shelfOf([job(JOB, { deletedUntil: until, serverDeleted: true }), job(OTHER, { deletedUntil: until }), job(THIRD, { lost: true })]));
    expect(stored().jobs[0]).toMatchObject({ deletedUntil: until, serverDeleted: true });
    expect(stored().jobs[1]).toMatchObject({ deletedUntil: until });
    expect(stored().jobs[1]).not.toHaveProperty('serverDeleted');
    expect(stored().jobs[2]).toMatchObject({ lost: true });
    expect(readShelf().shelf.jobs).toEqual([
      job(JOB, { deletedUntil: until, serverDeleted: true }),
      job(OTHER, { deletedUntil: until }),
      job(THIRD, { lost: true }),
    ]);
  });

  it('writes nothing for a job that is neither', () => {
    saveShelf(shelfOf([job(JOB)]));
    expect(stored().jobs[0]).not.toHaveProperty('deletedUntil');
    expect(stored().jobs[0]).not.toHaveProperty('serverDeleted');
    expect(stored().jobs[0]).not.toHaveProperty('lost');
  });

  it('reads a day that is no time as no deletion, and "deleted on the server" only with a day', () => {
    localStorage.setItem(
      SHELF_KEY,
      JSON.stringify({
        v: 1,
        jobs: [
          { jobID: JOB, expires: '2026-10-17T12:00:00Z', deletedUntil: 'tomorrow', serverDeleted: true },
          { jobID: OTHER, expires: '2026-10-17T12:00:00Z', serverDeleted: true, lost: 1 },
          { jobID: THIRD, expires: '2026-10-17T12:00:00Z', deletedUntil: 5, lost: 'true' },
        ],
        batches: [],
        groups: [],
      }),
    );
    expect(readShelf().shelf.jobs.map((j) => [j.deletedUntil, j.serverDeleted, j.lost])).toEqual([
      [null, false, false],
      [null, false, false],
      [null, false, false],
    ]);
  });

  it('is what the latest write says for one job: a restore in another tab takes the deletion away', () => {
    saveShelf(shelfOf([job(JOB, { deletedUntil: until, serverDeleted: true })]));
    saveShelf(shelfOf([job(JOB)]));
    expect(readShelf().shelf.jobs[0]).toMatchObject({ deletedUntil: null, serverDeleted: false });
  });

  it('is kept in the format of version 1: an older build reads the job and ignores the rest', () => {
    saveShelf(shelfOf([job(JOB, { deletedUntil: until, serverDeleted: true, lost: true })]));
    expect(stored().v).toBe(1);
    expect(Object.keys(stored().jobs[0]).sort()).toEqual(['createdAt', 'deletedUntil', 'expires', 'jobID', 'lost', 'serverDeleted']);
  });
});

describe('a job that was started again (NM4-34)', () => {
  it('is written as superseded and read back, in version 1; a job that is not writes no such key', () => {
    saveShelf(shelfOf([job(JOB, { superseded: true, archived: true }), job(OTHER)]));
    expect(stored().v).toBe(1);
    expect(stored().jobs[0]).toMatchObject({ superseded: true, archived: true });
    expect(stored().jobs[1]).not.toHaveProperty('superseded');
    expect(readShelf().shelf.jobs).toEqual([job(JOB, { superseded: true, archived: true }), job(OTHER)]);
  });

  it('is read as not superseded where the value is not `true`', () => {
    localStorage.setItem(SHELF_KEY, JSON.stringify({ v: 1, jobs: [{ jobID: JOB, expires: '2026-10-17T12:00:00Z', superseded: 'yes' }], batches: [], groups: [] }));
    expect(readShelf().shelf.jobs[0].superseded).toBe(false);
  });
});

describe('the default title (UI-01 §6.5)', () => {
  it('is written only where the user named the job or the batch otherwise, and read back', () => {
    const batch = { id: BATCH, title: 'Field 7', titleDefault: 'Band math · DEM', createdAt: '2026-10-10T10:00:00Z', archived: false, groupId: null, refused: [] };
    saveShelf(shelfOf([job(JOB, { title: 'Mine', titleDefault: 'Band math · DEM' }), job(OTHER, { title: 'Same', titleDefault: 'Same' })], { batches: [batch] }));
    expect(stored().jobs.map((j: Record<string, unknown>) => [j.title, j.titleDefault])).toEqual([
      ['Mine', 'Band math · DEM'],
      ['Same', undefined],
    ]);
    expect(stored().batches[0].titleDefault).toBe('Band math · DEM');
    const read = readShelf().shelf;
    expect(read.jobs.map((j) => [j.title, j.titleDefault])).toEqual([
      ['Mine', 'Band math · DEM'],
      ['Same', 'Same'],
    ]);
    expect(read.batches[0]).toMatchObject({ title: 'Field 7', titleDefault: 'Band math · DEM' });
  });

  it('is the title where an older write did not keep one, and nothing where there is no title', () => {
    localStorage.setItem(
      SHELF_KEY,
      JSON.stringify({
        v: 1,
        jobs: [{ jobID: JOB, expires: '2026-10-17T12:00:00Z', title: 'Old' }, { jobID: OTHER, expires: '2026-10-17T12:00:00Z', titleDefault: 'x'.repeat(201) }],
        batches: [{ id: BATCH, title: 'B', createdAt: '2026-10-10T10:00:00Z', titleDefault: 7 }],
      }),
    );
    const { jobs, batches } = readShelf().shelf;
    expect(jobs.map((j) => j.titleDefault)).toEqual(['Old', null]);
    expect(batches[0].titleDefault).toBe('B');
  });
});

describe('a group that is removed', () => {
  it('is taken out of what is stored as well, where the union would give it back', () => {
    const groups = [{ id: GROUP, name: 'A' }, { id: 'c'.repeat(32), name: 'B' }];
    saveShelf(shelfOf([], { groups }));
    saveShelf(shelfOf([], { groups: [groups[1]] }));
    expect(stored().groups.map((g: { name: string }) => g.name).sort()).toEqual(['A', 'B']);
    saveShelf(shelfOf([], { groups: [groups[1]] }), [GROUP]);
    expect(stored().groups.map((g: { name: string }) => g.name)).toEqual(['B']);
  });

  it('removes the key when it was the last thing the shelf held', () => {
    saveShelf(shelfOf([], { groups: [{ id: GROUP, name: 'A' }] }));
    saveShelf(shelfOf([]), [GROUP]);
    expect(localStorage.getItem(SHELF_KEY)).toBeNull();
  });

  it('does not touch a shelf of a version it does not know', () => {
    localStorage.setItem(SHELF_KEY, JSON.stringify({ v: 2, groups: [] }));
    expect(saveShelf(shelfOf([]), [GROUP])).toEqual({ state: 'memory', dropped: [] });
    expect(JSON.parse(localStorage.getItem(SHELF_KEY)!)).toEqual({ v: 2, groups: [] });
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

  it('writes a copy kept in version 1 as version 2, and refuses one it cannot rewrite or does not know', () => {
    expect(orderCopy(ORDER_V1)).toEqual(ORDER);
    const { output: _output, ...headless } = ORDER_V1;
    expect(orderCopy(headless)).toBeNull();
    expect(orderCopy({ ...ORDER_V1, inputs: [{ name: 'a', dataset: 'd', groups: [['s']] }] })).toBeNull();
    expect(orderCopy({ ...ORDER, recipe_version: 3 })).toBeNull();
    expect(orderCopy({ ...ORDER, recipe_version: '2' })).toBeNull();
    expect(orderCopy({ ...ORDER_V1, steps: 'x' })).toBeNull();
    const crop = { ...ORDER_V1, output: { kind: 'crop', format: 'cog' } };
    expect(orderCopy(crop)).toEqual({ ...crop, recipe_version: 2 });
  });

  it('reads a copy kept in version 1 from the shelf as version 2', () => {
    write({ v: 1, jobs: [entry({ order: ORDER_V1 })] });
    expect(readShelf().shelf.jobs[0].order).toEqual(ORDER);
  });

  it('keeps a range only with its three texts', () => {
    write({ v: 1, jobs: [entry({ range: { vmin: '0', vmax: '1', colormap: '' } }), entry({ jobID: OTHER, range: { vmin: 0, vmax: 1, colormap: 'x' } })] });
    expect(readShelf().shelf.jobs.map((j) => j.range)).toEqual([{ vmin: '0', vmax: '1', colormap: '' }, null]);
  });

  it('keeps the ranges of the bands of a result by name, each with its three texts, and drops what is not one', () => {
    const hand = { vmin: '0', vmax: '1', colormap: 'greys' };
    write({
      v: 1,
      jobs: [
        entry({ bandRanges: { ndvi: hand, red: { vmin: 0, vmax: 1, colormap: 'x' }, ['x'.repeat(200)]: hand } }),
        entry({ jobID: OTHER, bandRanges: 'nonsense' }),
        entry({ jobID: 'C'.repeat(22), bandRanges: [hand] }),
      ],
    });
    expect(readShelf().shelf.jobs.map((j) => j.bandRanges)).toEqual([{ ndvi: hand }, {}, {}]);
  });

  // NM4-65 part 4: a range typed in percentiles keeps them, so that the settings show "%" again.
  it('keeps the percentiles a range was typed as, and drops a pair that is none', () => {
    const hand = { vmin: '3', vmax: '97', colormap: 'viridis' };
    write({
      v: 1,
      jobs: [
        entry({ range: { ...hand, percent: { low: '3', high: '97' } } }),
        entry({ jobID: OTHER, range: { ...hand, percent: { low: '97', high: '3' } } }),
        entry({ jobID: 'C'.repeat(22), range: { ...hand, percent: { low: 3, high: '97' } } }),
        entry({ jobID: 'D'.repeat(22), bandRanges: { ndvi: { ...hand, percent: { low: '1', high: '99' } } } }),
      ],
    });
    const jobs = readShelf().shelf.jobs;
    expect(jobs[0].range).toEqual({ ...hand, percent: { low: '3', high: '97' } });
    expect(jobs[1].range).toEqual(hand);
    expect(jobs[2].range).toEqual(hand);
    expect(jobs[3].bandRanges).toEqual({ ndvi: { ...hand, percent: { low: '1', high: '99' } } });
    saveShelf(shelfOf([job('A'.repeat(22), { range: { ...hand, percent: { low: '3', high: '97' } } }), job('B'.repeat(22), { range: hand })]));
    const written = Object.fromEntries(stored().jobs.map((j: { jobID: string; range?: object }) => [j.jobID, j.range]));
    expect(written['A'.repeat(22)]).toEqual({ ...hand, percent: { low: '3', high: '97' } });
    expect(written['B'.repeat(22)]).toEqual(hand);
  });

  // NM4-65 part 3: the layer of a result shows the day of the scenes of its job.
  it('keeps the day of the scenes as text of that shape, and nothing else', () => {
    write({
      v: 1,
      jobs: [
        entry({ dates: '2026-07-01' }),
        entry({ jobID: OTHER, dates: '2026-07-01 – 2026-07-06' }),
        entry({ jobID: 'C'.repeat(22), dates: 'yesterday' }),
        entry({ jobID: 'D'.repeat(22), dates: 20260701 }),
        entry({ jobID: 'E'.repeat(22), dates: '2026-07-01<script>' }),
      ],
    });
    expect(readShelf().shelf.jobs.map((j) => j.dates)).toEqual(['2026-07-01', '2026-07-01 – 2026-07-06', null, null, null]);
    saveShelf(shelfOf([job('A'.repeat(22), { dates: '2026-07-01' }), job('B'.repeat(22))]));
    const written = Object.fromEntries(stored().jobs.map((j: { jobID: string; dates?: string }) => [j.jobID, j.dates]));
    expect([written['A'.repeat(22)], written['B'.repeat(22)]]).toEqual(['2026-07-01', undefined]);
  });

  it('keeps the band the preview showed as text, and nothing else', () => {
    write({ v: 1, jobs: [entry({ shownBand: 'ndvi' }), entry({ jobID: OTHER, shownBand: 7 }), entry({ jobID: 'C'.repeat(22), shownBand: 'x'.repeat(200) })] });
    expect(readShelf().shelf.jobs.map((j) => j.shownBand)).toEqual(['ndvi', null, null]);
    saveShelf(shelfOf([job('A'.repeat(22), { shownBand: 'ndvi' }), job('B'.repeat(22))]));
    const written = Object.fromEntries(stored().jobs.map((j: { jobID: string; shownBand?: string }) => [j.jobID, j.shownBand]));
    expect([written['A'.repeat(22)], written['B'.repeat(22)]]).toEqual(['ndvi', undefined]);
  });

  it('writes the ranges of the bands, and writes none for a job that has none', () => {
    const hand = { vmin: '0', vmax: '1', colormap: 'greys' };
    saveShelf(shelfOf([job('A'.repeat(22), { bandRanges: { red: hand } }), job('B'.repeat(22))]));
    const jobs = stored().jobs;
    expect(jobs[0].bandRanges).toEqual({ red: hand });
    expect('bandRanges' in jobs[1]).toBe(false);
    expect(readShelf().shelf.jobs.map((j) => j.bandRanges)).toEqual([{ red: hand }, {}]);
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
