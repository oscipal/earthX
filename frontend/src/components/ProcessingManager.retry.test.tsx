// @vitest-environment jsdom
//
// "Run again" in the processing manager (NM4-34): the kept order of a job that failed, was cancelled or has expired
// goes to the server once more; the new job takes the place of the old one, which stays archived and "Superseded";
// "Retry failed parts" does so for the parts of a batch, in the batch. Where the order cannot be sent again the
// symbol is not there. No backend: `fetch` answers by route.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { batchEntry, finished, jobEntry, jobId, NOW, status } from '../fixtures/jobEntries';
import { SHELF_KEY } from '../jobShelf';
import type { Order } from '../processing';
import { resetJobs, setTrackerOptions, useProcessingStore, type JobEntry } from '../processingStore';
import ProcessingManager from './ProcessingManager';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const BATCH = 'b'.repeat(32);
const GROUP = 'a'.repeat(32);
const DAY = 86_400_000;
const EXECUTION = 'POST /processing/processes/recipe/execution';
// Synthetic; the coordinates are made up.
const ORDER: Order = {
  recipe_version: 1,
  inputs: [{ name: 'a', dataset: 'sentinel-2-c1-l2a', groups: [['S1']], assets: ['red', 'nir'] }],
  aoi: { type: 'Polygon', coordinates: [[[10, 50], [10.1, 50], [10.1, 50.1], [10, 50]]] },
  steps: [],
  output: { kind: 'raster', format: 'cog', dtype: 'float32' },
};

let container: HTMLDivElement;
let root: Root;
let routes: Record<string, (init?: RequestInit) => Response | Promise<Response>>;
let fetchMock: ReturnType<typeof vi.fn>;
let asked: string[];
// The ids the server gives to the jobs it takes in, in order.
let next: number;

const json = (body: unknown, code = 200) =>
  new Response(JSON.stringify(body), { status: code, headers: { 'Content-Type': code >= 400 ? 'application/problem+json' : 'application/json' } });
const doc = (id: string, state: string) => ({
  processID: 'recipe',
  type: 'process',
  jobID: id,
  status: state,
  message: '',
  progress: 0,
  created: '2026-10-20T12:00:00Z',
  expires: new Date(NOW + 7 * DAY).toISOString(),
  recipeID: 'r',
  links: [],
});
const problem = (code: number, detail?: string) => json({ type: 'about:blank', title: 'No', status: code, ...(detail ? { detail } : {}) }, code);

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers({ toFake: ['Date'], now: NOW });
  localStorage.clear();
  sessionStorage.clear();
  next = 50;
  asked = [];
  routes = { [EXECUTION]: () => json(doc(jobId(next++), 'accepted'), 201) };
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    asked.push(`${init?.method ?? 'GET'} ${url}`);
    const route = routes[`${init?.method ?? 'GET'} ${url}`];
    return route ? route(init) : problem(404);
  });
  vi.stubGlobal('fetch', fetchMock);
  setTrackerOptions({ EventSource: null, fetchJob: async (id) => status({ jobID: id, status: 'accepted', progress: 0 }), pollMs: 60_000 });
  resetJobs();
  useProcessingStore.setState({ descriptions: {} });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  setTrackerOptions({});
  act(() => root.unmount());
  container.remove();
  resetJobs();
  localStorage.clear();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const mount = () => act(() => root.render(<ProcessingManager />));
const put = (patch: Partial<ReturnType<typeof useProcessingStore.getState>>) => act(() => useProcessingStore.setState(patch));
const click = (element: Element | null | undefined) => {
  if (!element) throw new Error(`nothing to click in ${container.textContent}`);
  act(() => element.dispatchEvent(new MouseEvent('click', { bubbles: true })));
};
const settle = () =>
  act(async () => {
    for (let i = 0; i < 6; i += 1) await Promise.resolve();
  });
const rows = () => [...container.querySelectorAll<HTMLElement>('.pm-list .pm-row')];
const topRows = () => [...container.querySelectorAll<HTMLElement>('.pm-rows > .pm-row')];
const titles = () => topRows().map((r) => r.querySelector('.pm-title')?.textContent);
const states = () => topRows().map((r) => r.querySelector('.pm-state')?.textContent);
const retryIn = (row: Element) => row.querySelector<HTMLButtonElement>(':scope > .pm-line > button[aria-label^="Run again"], :scope > .pm-line > button[aria-label^="Retry failed parts"]');
const tab = (label: string) => click([...container.querySelectorAll('button')].find((b) => b.textContent === label));
const stored = () => JSON.parse(localStorage.getItem(SHELF_KEY)!);
const sent = () => fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST').map(([, init]) => JSON.parse(init.body as string));

const failed = (n: number, over: Partial<JobEntry> = {}): JobEntry =>
  jobEntry(n, {
    phase: 'failed',
    status: status({ jobID: jobId(n), status: 'failed', progress: 100 }),
    failure: 'The source failed',
    failureKind: 'source_5xx',
    order: ORDER,
    ...over,
  });
const cancelled = (n: number, over: Partial<JobEntry> = {}): JobEntry =>
  jobEntry(n, { phase: 'dismissed', status: status({ jobID: jobId(n), status: 'dismissed' }), order: ORDER, ...over });
const expiredJob = (n: number, over: Partial<JobEntry> = {}): JobEntry =>
  finished(n, { expires: new Date(NOW - DAY).toISOString(), expired: true, order: ORDER, ...over });

describe('the symbol', () => {
  it.each([
    ['a failed job', () => failed(1)],
    ['a cancelled job', () => cancelled(1)],
    ['an expired job', () => expiredJob(1)],
  ])('is on %s, with the tooltip "Run again"', (_, make) => {
    put({ jobs: [make()] });
    mount();
    tab('All');
    const symbol = retryIn(rows()[0])!;
    expect(symbol.textContent).toBe('↻');
    expect(symbol.title).toBe('Run again');
  });

  it.each([
    ['one that waits or runs', () => jobEntry(1, { order: ORDER })],
    ['a finished one', () => finished(1, { order: ORDER })],
    ['one that was deleted', () => failed(1, { deletedUntil: new Date(NOW + DAY).toISOString() })],
    ['one the server forgot', () => failed(1, { phase: 'gone', lost: true })],
    ['one that is replaced already', () => failed(1, { superseded: true, archived: true })],
  ])('is not on %s', (_, make) => {
    put({ jobs: [make()] });
    mount();
    tab('All');
    expect(rows()).toHaveLength(1);
    expect(retryIn(rows()[0])).toBeNull();
  });

  it('is not there without a copy of the order, and the other symbols stay where they were', () => {
    put({ jobs: [failed(1, { order: null }), failed(2)] });
    mount();
    expect(retryIn(rows()[0])).toBeNull();
    expect(retryIn(rows()[1])).not.toBeNull();
    // The place of the missing symbol stays: both rows hold the same number of symbols.
    expect(rows()[0].querySelectorAll('.pm-line > .pm-icon')).toHaveLength(rows()[1].querySelectorAll('.pm-line > .pm-icon').length);
  });

  it.each(['source_timeout', 'source_5xx', 'source_429', 'source_unreachable', 'out_of_memory', 'child_crashed', 'upload_failed', 'lease_lost', 'cancelled', 'unknown', 'a_kind_of_a_later_version'])(
    'is on a job that failed for %s, which may not repeat',
    (kind) => {
      put({ jobs: [failed(1, { failureKind: kind })] });
      mount();
      expect(retryIn(rows()[0])).not.toBeNull();
    },
  );

  it('is on a job whose kind is not known (yet)', () => {
    put({ jobs: [failed(1, { failureKind: null })] });
    mount();
    expect(retryIn(rows()[0])).not.toBeNull();
  });

  it.each(['recipe_invalid', 'unsupported_recipe', 'scaling_mismatch', 'grid_mismatch', 'aoi_outside_inputs', 'rejected', 'source_4xx', 'runtime_exceeded', 'disk_space'])(
    'is not on a job that failed for %s, which would end the same',
    (kind) => {
      put({ jobs: [failed(1, { failureKind: kind })] });
      mount();
      expect(retryIn(rows()[0])).toBeNull();
    },
  );

  it('is not on a job of a dataset the platform has said it no longer carries', () => {
    put({ jobs: [failed(1)], descriptions: { 'sentinel-2-c1-l2a': { state: 'error', message: 'Gone', retired: 'withdrawn' } } });
    mount();
    expect(retryIn(rows()[0])).toBeNull();
  });
});

describe('the kind of a failure', () => {
  // As a reload does: the browser remembers the job, the server says it failed, the results name the kind.
  async function failsWith(kind: string | null) {
    setTrackerOptions({ EventSource: null, fetchJob: async (id) => status({ jobID: id, status: 'failed', progress: 100 }), pollMs: 60_000 });
    routes[`GET /processing/jobs/${jobId(1)}/results`] = () =>
      json({ type: kind ? `urn:earthx:job-failed:${kind}` : 'about:blank', title: 'The source failed', status: 502, detail: 'x' }, 502);
    put({ jobs: [jobEntry(1, { status: null, order: ORDER })] });
    mount();
    await settle();
  }

  it('is read from the results of a failed job, and a kind that may pass keeps the symbol', async () => {
    await failsWith('source_timeout');
    expect(useProcessingStore.getState().jobs[0]).toMatchObject({ phase: 'failed', failureKind: 'source_timeout', failure: 'The source failed' });
    expect(retryIn(rows()[0])).not.toBeNull();
  });

  it('takes the symbol away for a kind that would fail again', async () => {
    await failsWith('aoi_outside_inputs');
    expect(useProcessingStore.getState().jobs[0].failureKind).toBe('aoi_outside_inputs');
    expect(retryIn(rows()[0])).toBeNull();
  });

  it('is unknown where the results name none, and the symbol stays', async () => {
    await failsWith(null);
    expect(useProcessingStore.getState().jobs[0].failureKind).toBeNull();
    expect(retryIn(rows()[0])).not.toBeNull();
  });
});

describe('a click', () => {
  it('sends the kept order, and nothing else, as the order is accepted', async () => {
    put({ jobs: [failed(1)] });
    mount();
    click(retryIn(rows()[0]));
    await settle();
    expect(asked).toEqual([`POST /processing/processes/recipe/execution`]);
    expect(sent()).toEqual([{ inputs: { recipe: ORDER } }]);
    expect(fetchMock.mock.calls[0][1].headers).toMatchObject({ Prefer: 'respond-async' });
  });

  it('starts an expired job again just the same', async () => {
    put({ jobs: [expiredJob(1)] });
    mount();
    tab('Expired');
    expect(states()).toEqual(['Expired']);
    click(retryIn(rows()[0]));
    await settle();
    expect(sent()).toEqual([{ inputs: { recipe: ORDER } }]);
    // The old one is still listed as expired, set aside.
    expect(states()).toEqual(['Expired']);
    expect(rows()[0].querySelector('.pm-tag')?.textContent).toBe('Archived');
    expect(retryIn(rows()[0])).toBeNull();
    tab('Active');
    expect(states()).toEqual(['Waiting']);
  });

  it('puts the new job where the old one stood, with its title and group, and sets the old one aside', async () => {
    const groups = [{ id: GROUP, name: 'Fields' }];
    put({
      groups,
      jobs: [
        jobEntry(1, { title: 'Newest', groupId: GROUP }),
        failed(2, { title: 'Mine', titleDefault: 'Default', groupId: GROUP, createdAt: '2026-10-20T11:00:00Z', range: { vmin: '0', vmax: '1', colormap: 'viridis' } }),
        jobEntry(3, { title: 'Oldest', groupId: GROUP, createdAt: '2026-10-20T10:00:00Z' }),
      ],
    });
    mount();
    expect(titles()).toEqual(['Newest', 'Mine', 'Oldest']);
    click(retryIn(rows()[1]));
    await settle();
    expect(titles()).toEqual(['Newest', 'Mine', 'Oldest']);
    expect(states()).toEqual(['40%', 'Waiting', '40%']);
    const jobs = useProcessingStore.getState().jobs;
    expect(jobs.map((j) => j.jobID)).toEqual([jobId(1), jobId(50), jobId(2), jobId(3)]);
    expect(jobs[1]).toMatchObject({
      title: 'Mine',
      titleDefault: 'Default',
      groupId: GROUP,
      createdAt: '2026-10-20T11:00:00Z',
      range: { vmin: '0', vmax: '1', colormap: 'viridis' },
      order: ORDER,
      archived: false,
      superseded: false,
    });
    expect(jobs[2]).toMatchObject({ jobID: jobId(2), archived: true, superseded: true, phase: 'failed' });
  });

  it('keeps the old job: archived and "Superseded" under "All", and in the browser', async () => {
    put({ jobs: [failed(1, { title: 'Mine' })] });
    mount();
    click(retryIn(rows()[0]));
    await settle();
    expect(titles()).toEqual(['Mine']);
    tab('All');
    expect(titles()).toEqual(['Mine', 'Mine']);
    const old = rows()[1];
    expect(old.querySelector('.pm-state')?.textContent).toBe('Failed');
    expect([...old.querySelectorAll('.pm-tag')].map((t) => t.textContent)).toEqual(['Archived', 'Superseded']);
    expect(retryIn(old)).toBeNull();
    expect(stored().jobs.map((j: { jobID: string; archived?: boolean; superseded?: boolean }) => [j.jobID, j.archived, j.superseded])).toEqual([
      [jobId(50), undefined, undefined],
      [jobId(1), true, true],
    ]);
  });

  it('is one request for two clicks in a row', async () => {
    put({ jobs: [failed(1)] });
    mount();
    const symbol = retryIn(rows()[0])!;
    click(symbol);
    click(symbol);
    await settle();
    expect(sent()).toHaveLength(1);
    expect(useProcessingStore.getState().jobs.filter((j) => !j.superseded)).toHaveLength(1);
  });

  it('is one request for a second press that comes from the store while the first is on its way', async () => {
    put({ jobs: [failed(1)] });
    mount();
    await act(async () => {
      await Promise.all([useProcessingStore.getState().retryJob(jobId(1)), useProcessingStore.getState().retryJob(jobId(1))]);
    });
    expect(sent()).toHaveLength(1);
  });

  it('shows the reason when the server refuses, and leaves the old job as it was', async () => {
    routes[EXECUTION] = () => problem(422, 'step 0 is not valid');
    put({ jobs: [failed(1)] });
    mount();
    click(retryIn(rows()[0]));
    await settle();
    expect(container.querySelector('.pm-fault[role="alert"]')?.textContent).toContain('step 0 is not valid');
    expect(titles()).toHaveLength(1);
    expect(useProcessingStore.getState().jobs[0]).toMatchObject({ jobID: jobId(1), superseded: false, archived: false, retrying: false });
    expect(retryIn(rows()[0])).not.toBeNull();
  });

  it('takes the symbol away when the dataset has left (410)', async () => {
    routes[EXECUTION] = () => problem(410, 'retired in 2026');
    put({ jobs: [failed(1)] });
    mount();
    click(retryIn(rows()[0]));
    await settle();
    expect(container.querySelector('.pm-fault[role="alert"]')?.textContent).toBe('Dataset retired: retired in 2026');
    expect(retryIn(rows()[0])).toBeNull();
    expect(sent()).toHaveLength(1);
  });

  it('keeps the symbol when the server cannot be reached', async () => {
    routes[EXECUTION] = () => {
      throw new TypeError('network down');
    };
    put({ jobs: [failed(1)] });
    mount();
    click(retryIn(rows()[0]));
    await settle();
    expect(container.querySelector('.pm-fault[role="alert"]')?.textContent).toContain('network down');
    expect(retryIn(rows()[0])).not.toBeNull();
  });

  it('does nothing for a job that cannot be started again, whoever asks', async () => {
    put({ jobs: [failed(1, { failureKind: 'recipe_invalid' }), failed(2, { order: null }), finished(3, { order: ORDER })] });
    for (const n of [1, 2, 3]) await act(() => useProcessingStore.getState().retryJob(jobId(n)));
    expect(asked).toEqual([]);
  });
});

describe('a batch', () => {
  const part = (label: string, over: Partial<JobEntry>): Partial<JobEntry> => ({ ...over, batchId: BATCH, part: label, title: 'Batch' });

  function batch() {
    put({
      batches: [batchEntry(BATCH, { title: 'Batch', titleDefault: 'Batch' })],
      jobs: [
        failed(1, part('S1', {})),
        cancelled(2, part('S2', {})),
        finished(3, part('S3', { order: ORDER })),
        expiredJob(4, part('S4', {})),
        failed(5, part('S5', { failureKind: 'grid_mismatch' })),
      ],
    });
    mount();
  }
  const open = () => click(container.querySelector('.pm-chevron'));
  const partRows = () => [...container.querySelectorAll<HTMLElement>('.pm-parts > .pm-row')];

  it('has one symbol, "Retry failed parts", and it starts only the parts that failed or were cancelled', async () => {
    batch();
    const symbol = retryIn(topRows()[0])!;
    expect(symbol.title).toBe('Retry failed parts');
    click(symbol);
    await settle();
    // The failed part and the cancelled one; not the finished, the expired, nor the one that would fail again.
    expect(sent()).toHaveLength(2);
    expect(useProcessingStore.getState().jobs.filter((j) => j.superseded).map((j) => j.jobID)).toEqual([jobId(1), jobId(2)]);
  });

  it('keeps the new jobs in the batch, in the place of the old, and counts them once', async () => {
    batch();
    open();
    expect(partRows().map((r) => r.querySelector('.pm-title')?.textContent)).toEqual(['S1', 'S2', 'S3', 'S4', 'S5']);
    click(retryIn(topRows()[0]));
    await settle();
    expect(partRows().map((r) => [r.querySelector('.pm-title')?.textContent, r.querySelector('.pm-state')?.textContent])).toEqual([
      ['S1', 'Waiting'],
      ['S2', 'Waiting'],
      ['S3', 'Finished'],
      ['S4', 'Expired'],
      ['S5', 'Failed'],
    ]);
    expect(useProcessingStore.getState().jobs.filter((j) => j.batchId === BATCH && !j.superseded).map((j) => j.part)).toEqual(['S1', 'S2', 'S3', 'S4', 'S5']);
    expect(topRows()[0].querySelector('.pm-state')?.textContent).toBe('1 done · 2 running · 1 failed · 1 expired');
    // The symbol is gone with nothing left to start: the part that would fail again is not one of them.
    expect(retryIn(topRows()[0])).toBeNull();
  });

  it('is one round for two clicks in a row', async () => {
    batch();
    const symbol = retryIn(topRows()[0])!;
    click(symbol);
    click(symbol);
    await settle();
    expect(sent()).toHaveLength(2);
  });

  it('has no symbol when no part failed or was cancelled', () => {
    put({ batches: [batchEntry(BATCH)], jobs: [finished(1, part('S1', {})), expiredJob(2, part('S2', {}))] });
    mount();
    expect(retryIn(topRows()[0])).toBeNull();
  });

  it('lets a single part run again from its own row, an expired one included', async () => {
    batch();
    open();
    click(retryIn(partRows()[3]));
    await settle();
    expect(sent()).toHaveLength(1);
    expect(partRows().map((r) => r.querySelector('.pm-state')?.textContent)).toEqual(['Failed', 'Cancelled', 'Finished', 'Waiting', 'Failed']);
  });

  it('tells in the batch row when a part could not be started', async () => {
    routes[EXECUTION] = () => problem(422, 'step 0 is not valid');
    batch();
    click(retryIn(topRows()[0]));
    await settle();
    expect(topRows()[0].querySelector('.pm-fault[role="alert"]')?.textContent).toContain('step 0 is not valid');
  });
});
