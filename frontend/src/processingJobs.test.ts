// @vitest-environment jsdom
// The jobs of this browser in the store (UI-01b, §6.4, §6.7): what is kept, what a reload and another
// tab bring back, and when a job is dismissed.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SHELF_KEY } from './jobShelf';
import type { Order, StatusInfo } from './processing';
import { resetJobs, setTrackerOptions, useProcessingStore } from './processingStore';

const JOB = 'AbCdEfGhIjKlMnOpQrSt_-';
const OTHER = 'ZZZZZZZZZZZZZZZZZZZZZZ';
const LATER = new Date(Date.now() + 7 * 86_400_000).toISOString();
const ORDER: Order = {
  recipe_version: 2,
  inputs: [{ name: 'a', dataset: 'd', groups: [['s']] }],
  steps: [],
  output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['red'] },
};

const statusDoc = (jobID: string, status = 'running', expires = LATER) => ({
  processID: 'recipe', type: 'process', jobID, status, message: '', progress: 10, created: '2026-10-10T10:00:00Z', expires, recipeID: 'r', links: [],
});
const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': status >= 400 ? 'application/problem+json' : 'application/json' } });

const store = () => useProcessingStore.getState();
const stored = () => JSON.parse(localStorage.getItem(SHELF_KEY)!);
let calls: string[];
// What the server says of the job when it is asked afresh.
let serverState: () => Response;
let fetchJob: ReturnType<typeof vi.fn<(jobID: string) => Promise<StatusInfo>>>;

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  calls = [];
  serverState = () => response(statusDoc(JOB));
  fetchJob = vi.fn(async (jobID: string) => statusDoc(jobID) as unknown as StatusInfo);
  setTrackerOptions({ EventSource: null, fetchJob, pollMs: 60_000 });
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? 'GET'} ${url}`);
      if (init?.method === 'POST') return response(statusDoc(JOB), 201);
      if (init?.method === 'DELETE') return response(statusDoc(JOB, 'dismissed'));
      if (url === `/processing/jobs/${JOB}`) return serverState();
      return response({ title: 'Not found' }, 404);
    }),
  );
});

afterEach(() => {
  setTrackerOptions({});
  resetJobs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function place(order: Order = ORDER, title?: string) {
  const answer = await store().placeOrder(order, title ? { title } : undefined);
  if (!('jobID' in answer)) throw new Error(answer.message);
}

describe('dismissing a job (§6.7)', () => {
  const states = ['successful', 'failed', 'dismissed'] as const;

  it('sends DELETE for a job last known to be running, and once for a double click', async () => {
    await place();
    await Promise.all([store().cancelJob(JOB), store().cancelJob(JOB)]);
    expect(calls.filter((c) => c.startsWith('DELETE'))).toEqual([`DELETE /processing/jobs/${JOB}`]);
    expect(store().jobs[0]).toMatchObject({ phase: 'dismissed', cancelling: false });
  });

  it('asks for the state afresh and sends no DELETE for a job that finished since its last status', async () => {
    await place();
    expect(store().jobs[0].status?.status).toBe('running');
    serverState = () => response(statusDoc(JOB, 'successful'));
    await store().cancelJob(JOB);
    expect(calls.filter((c) => c.startsWith('DELETE'))).toEqual([]);
    expect(calls).toContain(`GET /processing/jobs/${JOB}`);
    expect(store().jobs[0]).toMatchObject({ phase: 'successful', cancelling: false });
    expect(store().jobs[0].status?.status).toBe('successful');
  });

  it.each(['failed', 'dismissed'])('shows the fresh state and sends no DELETE for a job that is %s by now', async (state) => {
    await place();
    serverState = () => response(statusDoc(JOB, state));
    await store().cancelJob(JOB);
    expect(calls.filter((c) => c.startsWith('DELETE'))).toEqual([]);
    expect(store().jobs[0].phase).toBe(state);
  });

  it('says the job is gone, and sends no DELETE, when the fresh state is a 404', async () => {
    await place();
    serverState = () => response({ title: 'no such job' }, 404);
    await store().cancelJob(JOB);
    expect(calls.filter((c) => c.startsWith('DELETE'))).toEqual([]);
    expect(store().jobs[0]).toMatchObject({ phase: 'gone', cancelling: false });
  });

  it('cancels nothing and says so when the fresh state cannot be had', async () => {
    await place();
    serverState = () => response({ title: 'queue down' }, 503);
    await store().cancelJob(JOB);
    expect(calls.filter((c) => c.startsWith('DELETE'))).toEqual([]);
    expect(store().jobs[0]).toMatchObject({ phase: 'active', cancelling: false, error: expect.stringContaining('not cancelled') });
  });

  it('gives up on a fresh state that takes more than a few seconds, and cancels nothing', async () => {
    vi.useFakeTimers();
    try {
      await place();
      vi.mocked(fetch).mockImplementationOnce(
        (_url, init) =>
          new Promise((_resolve, reject) => {
            init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'TimeoutError')));
          }),
      );
      const cancelled = store().cancelJob(JOB);
      await vi.advanceTimersByTimeAsync(5000);
      await cancelled;
      expect(calls.filter((c) => c.startsWith('DELETE'))).toEqual([]);
      expect(store().jobs[0]).toMatchObject({ phase: 'active', cancelling: false, error: expect.any(String) });
    } finally {
      vi.useRealTimers();
    }
  });

  it.each(states)('never sends DELETE for a job that is %s', async (state) => {
    await place();
    useProcessingStore.setState((s) => ({
      jobs: s.jobs.map((j) => ({ ...j, phase: state, status: { ...j.status!, status: state } })),
    }));
    await store().cancelJob(JOB);
    expect(calls.filter((c) => c.startsWith('DELETE'))).toEqual([]);
    expect(store().jobs[0].phase).toBe(state);
  });

  it('never sends DELETE for a job that is gone or that is not in the list', async () => {
    await place();
    await store().cancelJob(OTHER);
    useProcessingStore.setState((s) => ({ jobs: s.jobs.map((j) => ({ ...j, phase: 'gone' as const })) }));
    await store().cancelJob(JOB);
    expect(calls.filter((c) => c.startsWith('DELETE'))).toEqual([]);
  });

  it('asks afresh for a job whose state is not yet known, and dismisses it only if it runs', async () => {
    localStorage.setItem(SHELF_KEY, JSON.stringify({ v: 1, jobs: [{ jobID: JOB, expires: LATER }], batches: [], groups: [] }));
    fetchJob.mockImplementation(() => new Promise(() => {}));
    store().resumeJobs();
    expect(store().jobs[0].status).toBeNull();
    serverState = () => response(statusDoc(JOB, 'successful'));
    await store().cancelJob(JOB);
    expect(calls.filter((c) => c.startsWith('DELETE'))).toEqual([]);
    expect(store().jobs[0].phase).toBe('successful');
  });

  it('keeps the job when the server says it is gone, and shows the error when the dismissal fails', async () => {
    await place();
    vi.mocked(fetch).mockImplementationOnce(async () => response({ title: 'queue down' }, 503));
    await store().cancelJob(JOB);
    expect(store().jobs[0]).toMatchObject({ phase: 'active', cancelling: false, error: expect.any(String) });
    vi.mocked(fetch).mockImplementationOnce(async () => response({ title: 'no such job' }, 404));
    await store().cancelJob(JOB);
    expect(store().jobs[0].phase).toBe('gone');
    expect(stored().jobs.map((j: { jobID: string }) => j.jobID)).toEqual([JOB]);
  });

  it('does not send DELETE again for a job it has dismissed', async () => {
    await place();
    await store().cancelJob(JOB);
    await store().cancelJob(JOB);
    expect(calls.filter((c) => c.startsWith('DELETE'))).toHaveLength(1);
  });

  it('has no way left to remove a job', () => {
    expect('removeJob' in store()).toBe(false);
  });
});

describe('a job that is placed', () => {
  it('is kept with its title, its order and when it was placed, and not with its state', async () => {
    await place(ORDER, 'Export · DEM · 12 Oct');
    expect(stored().jobs).toEqual([
      { jobID: JOB, expires: LATER, createdAt: expect.any(String), title: 'Export · DEM · 12 Oct', order: ORDER },
    ]);
    expect(store().shelf).toBe('ok');
  });

  it('is kept without a copy of an order over 64 KB, and the job is still there', async () => {
    await place({ ...ORDER, aoi: { type: 'Polygon', coordinates: [[[0, 0]], 'x'.repeat(70_000)] as never } });
    expect(stored().jobs[0].order).toBeUndefined();
    expect(store().jobs[0].order).toBeNull();
  });

  it('is not placed twice when the server answers with a job already in the list', async () => {
    await place();
    await place();
    expect(store().jobs).toHaveLength(1);
  });
});

describe('a reload', () => {
  const keep = (jobs: unknown[], rest: Record<string, unknown> = {}) =>
    localStorage.setItem(SHELF_KEY, JSON.stringify({ v: 1, jobs, batches: [], groups: [], ...rest }));

  it('brings the jobs back, newest first, and follows those that have not expired and are not archived', async () => {
    keep([
      { jobID: JOB, expires: LATER, createdAt: '2026-10-10T10:00:00Z', title: 'older' },
      { jobID: OTHER, expires: LATER, createdAt: '2026-10-11T10:00:00Z', title: 'newer', archived: true },
    ]);
    store().resumeJobs();
    expect(store().jobs.map((j) => [j.title, j.archived, j.phase])).toEqual([
      ['newer', true, 'active'],
      ['older', false, 'active'],
    ]);
    await vi.waitFor(() => expect(fetchJob).toHaveBeenCalledTimes(1));
    expect(fetchJob.mock.calls[0][0]).toBe(JOB);
  });

  it('does not follow an archived job until its row is shown', async () => {
    keep([{ jobID: JOB, expires: LATER, archived: true }, { jobID: OTHER, expires: LATER }]);
    store().resumeJobs();
    await vi.waitFor(() => expect(fetchJob).toHaveBeenCalledTimes(1));
    expect(fetchJob.mock.calls[0][0]).toBe(OTHER);
    store().followJob(JOB);
    await vi.waitFor(() => expect(fetchJob).toHaveBeenCalledTimes(2));
  });

  it('keeps a job past its expiry in the list as expired, and does not ask after it', async () => {
    keep([{ jobID: JOB, expires: '2026-10-01T10:00:00Z', title: 'old' }]);
    store().resumeJobs();
    expect(store().jobs[0]).toMatchObject({ phase: 'gone', expired: true, title: 'old' });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(fetchJob).not.toHaveBeenCalled();
    expect(calls).toEqual([]);
  });

  it('keeps a job the server no longer knows, with its title', async () => {
    keep([{ jobID: JOB, expires: LATER, title: 'cancelled before' }]);
    const { HttpError } = await import('./api');
    fetchJob.mockRejectedValue(new HttpError(404, 'gone', 'gone'));
    store().resumeJobs();
    await vi.waitFor(() => expect(store().jobs[0].phase).toBe('gone'));
    expect(stored().jobs[0].title).toBe('cancelled before');
  });

  it('is twice the same where it is called twice', () => {
    keep([{ jobID: JOB, expires: LATER }]);
    store().resumeJobs();
    store().resumeJobs();
    expect(store().jobs).toHaveLength(1);
  });

  it('takes up the batches and groups, and a job whose batch is gone is a job of its own', () => {
    const batch = 'b'.repeat(32);
    const group = 'a'.repeat(32);
    keep(
      [
        { jobID: JOB, expires: LATER, batchId: batch, part: 'S1', groupId: group },
        { jobID: OTHER, expires: LATER, batchId: 'c'.repeat(32), part: 'S2' },
      ],
      { batches: [{ id: batch, title: 'T', createdAt: '2026-10-10T10:00:00Z', refused: [] }], groups: [{ id: group, name: 'G' }] },
    );
    store().resumeJobs();
    expect(store().batches.map((b) => b.id)).toEqual([batch]);
    expect(store().groups).toEqual([{ id: group, name: 'G' }]);
    expect(store().jobs.map((j) => [j.jobID, j.batchId, j.part, j.groupId])).toEqual([
      [JOB, batch, 'S1', group],
      [OTHER, null, null, null],
    ]);
  });

  it('says so, and writes nothing, where the stored value is of a version this build does not know', async () => {
    localStorage.setItem(SHELF_KEY, JSON.stringify({ v: 2, jobs: [] }));
    store().resumeJobs();
    expect(store().shelf).toBe('memory');
    await place();
    expect(store().jobs).toHaveLength(1);
    expect(JSON.parse(localStorage.getItem(SHELF_KEY)!)).toEqual({ v: 2, jobs: [] });
    expect(store().shelf).toBe('memory');
  });

  it('takes over the list of this tab from before UI-01', () => {
    sessionStorage.setItem('earthx.processing.jobs', JSON.stringify([{ jobID: JOB, expires: LATER, title: 'Band math · DEM' }]));
    store().resumeJobs();
    expect(store().jobs.map((j) => j.title)).toEqual(['Band math · DEM']);
    expect(sessionStorage.getItem('earthx.processing.jobs')).toBeNull();
    expect(stored().jobs[0].jobID).toBe(JOB);
  });
});

describe('a browser that does not keep the jobs', () => {
  it('says so and goes on for the session where the storage is full', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError');
    });
    await place();
    expect(store().shelf).toBe('memory');
    expect(store().jobs).toHaveLength(1);
  });

  it('says so and goes on where the storage is blocked', async () => {
    vi.spyOn(globalThis, 'localStorage', 'get').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    store().resumeJobs();
    await place();
    expect(store().shelf).toBe('memory');
    expect(store().jobs).toHaveLength(1);
  });

  it('drops the oldest copies of orders where the storage fills, says so, and keeps saying so', async () => {
    const set = Storage.prototype.setItem;
    const room = { characters: 100_000 };
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (this: Storage, key: string, value: string) {
      if (value.length > room.characters) throw new DOMException('full', 'QuotaExceededError');
      set.call(this, key, value);
    });
    const pad = (n: number): Order => ({ ...ORDER, steps: [{ op: 'x', op_version: 1, params: { pad: 'x'.repeat(n) } }] });
    vi.mocked(fetch).mockImplementation(async (_url, init) => {
      if (init?.method !== 'POST') return response({ title: 'Not found' }, 404);
      const n = calls.filter((c) => c.startsWith('POST')).length;
      calls.push('POST');
      return response(statusDoc(`Job${String(n).padStart(19, '0')}`), 201);
    });
    await place(pad(1000));
    await place(pad(1000));
    expect(store().shelf).toBe('ok');
    room.characters = 2800;
    await place(pad(1000));
    expect(store().shelf).toBe('trimmed');
    // the newest job (first in the list) keeps its copy; the entries are all there
    expect(store().jobs.map((j) => j.order !== null)).toEqual([true, false, false]);
    expect(stored().jobs).toHaveLength(3);
    expect(stored().jobs.filter((j: { order?: unknown }) => j.order)).toHaveLength(1);
    // a write that needs no dropping does not take the notice back
    room.characters = 100_000;
    await place(pad(10));
    expect(store().shelf).toBe('trimmed');
  });
});

describe('another tab', () => {
  const tellStorage = (newValue: string | null) =>
    window.dispatchEvent(new StorageEvent('storage', { key: SHELF_KEY, newValue, storageArea: localStorage }));

  beforeEach(() => store().resumeJobs());

  it('brings in the jobs it placed, without following them until someone looks, and the changes it made to a known job', async () => {
    await place(ORDER, 'mine');
    const write = (jobs: unknown[]) => {
      localStorage.setItem(SHELF_KEY, JSON.stringify({ v: 1, jobs, batches: [], groups: [] }));
      tellStorage('changed');
    };
    write([
      { jobID: JOB, expires: LATER, title: 'renamed in the other tab', archived: true },
      { jobID: OTHER, expires: LATER, title: 'placed in the other tab' },
    ]);
    expect(store().jobs.map((j) => [j.jobID, j.title, j.archived])).toEqual([
      [OTHER, 'placed in the other tab', false],
      [JOB, 'renamed in the other tab', true],
    ]);
    expect(store().jobs[0]).toMatchObject({ phase: 'active', status: null });
    const asked = fetchJob.mock.calls.map(([id]) => id);
    expect(asked).not.toContain(OTHER);
    store().followJob(OTHER);
    store().followJob(OTHER);
    await vi.waitFor(() => expect(fetchJob.mock.calls.filter(([id]) => id === OTHER)).toHaveLength(1));
  });

  it('is not news when the other tab removed the value (the browser data was cleared)', async () => {
    await place();
    localStorage.clear();
    tellStorage(null);
    expect(store().jobs).toHaveLength(1);
  });

  it('does not follow a job that has expired or that is not in the list', async () => {
    localStorage.setItem(SHELF_KEY, JSON.stringify({ v: 1, jobs: [{ jobID: OTHER, expires: '2026-10-01T10:00:00Z' }], batches: [], groups: [] }));
    tellStorage('changed');
    store().followJob(OTHER);
    store().followJob(JOB);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(fetchJob).not.toHaveBeenCalled();
  });

  it('is written to without losing what it placed', async () => {
    localStorage.setItem(SHELF_KEY, JSON.stringify({ v: 1, jobs: [{ jobID: OTHER, expires: LATER }], batches: [], groups: [] }));
    await place();
    expect(stored().jobs.map((j: { jobID: string }) => j.jobID).sort()).toEqual([JOB, OTHER].sort());
  });
});
