// @vitest-environment jsdom
//
// "Delete (D)" and "Restore" in the processing manager (NM4-27): a job that is over is deleted on the server with a
// day to take it back, and an entry the server cannot hold any more is deleted here only; the tab "Deleted"; a job
// the server forgot (`404`) is kept as "No longer available" and never asked about again, a reload included.
// No backend: `fetch` answers by route.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { HttpError } from '../api';
import { batchEntry, finished, jobEntry, jobId, NOW, status } from '../fixtures/jobEntries';
import { SHELF_KEY } from '../jobShelf';
import { resetJobs, setTrackerOptions, useProcessingStore } from '../processingStore';
import ProcessingManager from './ProcessingManager';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const BATCH = 'b'.repeat(32);
const DAY = 86_400_000;

let container: HTMLDivElement;
let root: Root;
let routes: Record<string, (init?: RequestInit) => Response>;
let fetchMock: ReturnType<typeof vi.fn>;
let asked: string[];

const doc = (id: string, state: string, expires: number) => ({
  processID: 'recipe',
  type: 'process',
  jobID: id,
  status: state,
  message: '',
  progress: 100,
  created: '2026-10-10T10:00:00Z',
  expires: new Date(expires).toISOString(),
  recipeID: 'r',
  links: [],
});
const json = (body: unknown, code = 200) =>
  new Response(JSON.stringify(body), { status: code, headers: { 'Content-Type': code >= 400 ? 'application/problem+json' : 'application/json' } });
const problem = (code: number) => json({ type: 'about:blank', title: 'Not found', status: code, detail: 'there is no such job' }, code);

// What the server does for a job: deletes it for a day, takes it back, and has the results again.
function serverHolds(id: string) {
  routes[`DELETE /processing/jobs/${id}`] = () => json(doc(id, 'dismissed', NOW + DAY));
  routes[`POST /processing/jobs/${id}/restore`] = () => json(doc(id, 'successful', NOW + 7 * DAY));
  routes[`GET /processing/jobs/${id}/results`] = () => json({ result: { href: `/processing/jobs/${id}/results/result.tif` }, bundle: { href: `/processing/jobs/${id}/results/result.zip` } });
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers({ toFake: ['Date'], now: NOW });
  localStorage.clear();
  sessionStorage.clear();
  routes = {};
  asked = [];
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    asked.push(`${init?.method ?? 'GET'} ${url}`);
    const route = routes[`${init?.method ?? 'GET'} ${url}`];
    return route ? route(init) : problem(404);
  });
  vi.stubGlobal('fetch', fetchMock);
  setTrackerOptions({ EventSource: null, fetchJob: async (id) => status({ jobID: id }), pollMs: 60_000 });
  resetJobs();
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
const button = (label: string): HTMLButtonElement => {
  const found = [...container.querySelectorAll('button')].find((b) => b.textContent?.trim() === label);
  if (!found) throw new Error(`no button ${label} in ${container.textContent}`);
  return found;
};
const rows = () => [...container.querySelectorAll<HTMLElement>('.pm-rows > .pm-row')];
const titles = () => rows().map((r) => r.querySelector('.pm-title')?.textContent);
const states = () => rows().map((r) => r.querySelector('.pm-state')?.textContent);
const menuOf = (row: Element) => click(row.querySelector('button[aria-haspopup="menu"]'));
const closeMenu = () => act(() => document.body.dispatchEvent(new Event('pointerdown', { bubbles: true })));
const item = (label: string) => {
  const found = [...document.querySelectorAll<HTMLButtonElement>('[role="menu"] button')].find((b) => (b.querySelector('.pm-menu-label')?.textContent ?? b.textContent?.trim()) === label);
  if (!found) throw new Error(`no menu item ${label}`);
  return found;
};
const hasItem = (label: string) =>
  [...document.querySelectorAll<HTMLButtonElement>('[role="menu"] button')].some((b) => (b.querySelector('.pm-menu-label')?.textContent ?? b.textContent?.trim()) === label);
const press = (target: Element, name: string, init: KeyboardEventInit = {}) => {
  const event = new KeyboardEvent('keydown', { key: name, bubbles: true, cancelable: true, ...init });
  act(() => target.dispatchEvent(event));
  return event;
};
const openButton = (row: Element) => row.querySelector<HTMLButtonElement>('.pm-open')!;
const restoreIcon = (row: Element) => row.querySelector<HTMLButtonElement>('button[aria-label^="Restore"]');
const stored = () => JSON.parse(localStorage.getItem(SHELF_KEY)!);
const settle = () => act(async () => {
  await Promise.resolve();
  await Promise.resolve();
});
const job = (n: number) => useProcessingStore.getState().jobs.find((j) => j.jobID === jobId(n))!;

describe('Delete with D', () => {
  it('asks the server, takes the job out of "Active" and keeps it under "Deleted" with the day to restore it', async () => {
    serverHolds(jobId(1));
    put({ jobs: [finished(1)] });
    mount();
    const event = press(openButton(rows()[0]), 'd');
    expect(event.defaultPrevented).toBe(true);
    await settle();
    expect(asked).toEqual([`DELETE /processing/jobs/${jobId(1)}`]);
    expect(rows()).toHaveLength(0);
    click(button('Deleted'));
    expect(states()).toEqual(['Deleted']);
    expect(rows()[0].classList.contains('deleted')).toBe(true);
    expect(rows()[0].querySelector('.pm-until')?.textContent).toMatch(/^restore until 21 Oct, \d{2}:\d{2}$/u);
    expect(rows()[0].querySelector('.pm-until')?.getAttribute('title')).toBe(new Date(NOW + DAY).toISOString());
    expect(job(1)).toMatchObject({ phase: 'dismissed', serverDeleted: true, deletedUntil: new Date(NOW + DAY).toISOString() });
    expect(stored().jobs[0]).toMatchObject({ jobID: jobId(1), deletedUntil: new Date(NOW + DAY).toISOString(), serverDeleted: true });
  });

  it('asks for no confirmation and sends no body', async () => {
    serverHolds(jobId(1));
    put({ jobs: [finished(1)] });
    mount();
    press(openButton(rows()[0]), 'D');
    await settle();
    expect(document.querySelector('[role="dialog"], .dialog-backdrop')).toBeNull();
    expect(fetchMock.mock.calls[0][1]).toEqual({ method: 'DELETE' });
  });

  it('does nothing for a job that waits or runs: that one has "Cancel"', async () => {
    put({ jobs: [jobEntry(1), jobEntry(2, { status: null })] });
    mount();
    press(openButton(rows()[0]), 'd');
    press(openButton(rows()[1]), 'd');
    await settle();
    expect(asked).toEqual([]);
    expect(useProcessingStore.getState().jobs.every((j) => j.deletedUntil === null)).toBe(true);
  });

  it.each([['ctrlKey'], ['altKey'], ['metaKey']])('leaves a key with %s to the browser', async (modifier) => {
    put({ jobs: [finished(1)] });
    mount();
    const event = press(openButton(rows()[0]), 'd', { [modifier]: true });
    await settle();
    expect(event.defaultPrevented).toBe(false);
    expect(asked).toEqual([]);
  });

  it('is not a key in a field: a D typed while a title is renamed deletes nothing', async () => {
    put({ jobs: [finished(1)] });
    mount();
    press(openButton(rows()[0]), 'r');
    const field = container.querySelector<HTMLInputElement>('input.pm-rename')!;
    const event = press(field, 'd');
    await settle();
    expect(event.defaultPrevented).toBe(false);
    expect(asked).toEqual([]);
    expect(job(1).deletedUntil).toBeNull();
  });

  it('does not delete while a dialog is open', async () => {
    put({ jobs: [finished(1)] });
    mount();
    const backdrop = document.createElement('div');
    backdrop.className = 'dialog-backdrop';
    document.body.append(backdrop);
    press(openButton(rows()[0]), 'd');
    await settle();
    backdrop.remove();
    expect(asked).toEqual([]);
  });

  it('acts on the row under the pointer when none has the focus, no click first', async () => {
    serverHolds(jobId(2));
    put({ jobs: [finished(1), finished(2)] });
    mount();
    act(() => rows()[1].dispatchEvent(new PointerEvent('pointerenter')));
    press(document.body, 'd');
    await settle();
    expect(asked).toEqual([`DELETE /processing/jobs/${jobId(2)}`]);
  });

  it('leaves the key to a row that is deleted already: D does not restore', async () => {
    serverHolds(jobId(1));
    put({ jobs: [finished(1, { phase: 'dismissed', deletedUntil: new Date(NOW + DAY).toISOString(), serverDeleted: true })] });
    mount();
    click(button('Deleted'));
    press(openButton(rows()[0]), 'd');
    await settle();
    expect(asked).toEqual([]);
    expect(job(1).deletedUntil).not.toBeNull();
  });

  it('gives the focus to the next row once the row has left the list', async () => {
    serverHolds(jobId(1));
    put({ jobs: [finished(1), finished(2)] });
    mount();
    openButton(rows()[0]).focus();
    press(openButton(rows()[0]), 'd');
    await settle();
    await vi.waitFor(() => expect(document.activeElement).toBe(openButton(rows()[0])));
    expect(titles()).toEqual(['Band math · Sentinel-2 L2A · 2 Oct']);
  });

  it('shows the error and keeps the job where the server does not answer', async () => {
    routes[`DELETE /processing/jobs/${jobId(1)}`] = () => json({ type: 'about:blank', title: 'busy', status: 503, detail: 'try again' }, 503);
    put({ jobs: [finished(1)] });
    mount();
    press(openButton(rows()[0]), 'd');
    await settle();
    expect(job(1)).toMatchObject({ deletedUntil: null, deleting: false, error: 'The job could not be deleted. Try again.' });
    expect(rows()).toHaveLength(1);
  });

  it('sends one request for two presses in a row', async () => {
    serverHolds(jobId(1));
    put({ jobs: [finished(1)] });
    mount();
    press(openButton(rows()[0]), 'd');
    press(openButton(rows()[0]), 'd');
    await settle();
    expect(asked.filter((a) => a.startsWith('DELETE'))).toHaveLength(1);
  });

  it('keeps a job that the server answers `404` for as deleted here, and forgotten', async () => {
    put({ jobs: [finished(1)] });
    mount();
    press(openButton(rows()[0]), 'd');
    await settle();
    click(button('Deleted'));
    expect(states()).toEqual(['No longer available']);
    expect(job(1)).toMatchObject({ lost: true, serverDeleted: false });
    expect(stored().jobs[0]).toMatchObject({ lost: true });
  });
});

describe('the menu', () => {
  it('has "Delete" with its key for a job that is over, in the list and for a part, and not for one that runs', () => {
    put({
      jobs: [
        finished(1),
        jobEntry(2),
        jobEntry(3, { batchId: BATCH, part: 'S1', phase: 'successful', archive: 'result.zip' }),
        jobEntry(4, { batchId: BATCH, part: 'S2', phase: 'failed' }),
      ],
      batches: [batchEntry(BATCH)],
    });
    mount();
    const row = (id: string) => container.querySelector<HTMLElement>(`[data-row-id="${id}"]`)!;
    menuOf(row(jobId(1)));
    expect(item('Delete').getAttribute('aria-keyshortcuts')).toBe('D');
    expect(item('Delete').querySelector('.pm-key')?.textContent).toBe('D');
    closeMenu();
    menuOf(row(jobId(2)));
    expect(hasItem('Delete')).toBe(false);
    closeMenu();
    // Both parts are over, so the batch can be deleted and so can each part.
    menuOf(row(BATCH));
    expect(hasItem('Delete')).toBe(true);
    closeMenu();
    click(row(BATCH).querySelector('button[aria-expanded]'));
    const [one, two] = [...container.querySelectorAll<HTMLElement>('.pm-parts .pm-row')];
    for (const part of [one, two]) {
      menuOf(part);
      expect(item('Delete').getAttribute('aria-keyshortcuts')).toBe('D');
      closeMenu();
    }
    expect(one.getAttribute('aria-keyshortcuts')).toBeNull();
  });

  it('deletes with a click on "Delete" and with the letter D in the open menu', async () => {
    serverHolds(jobId(1));
    serverHolds(jobId(2));
    put({ jobs: [finished(1), finished(2)] });
    mount();
    menuOf(rows()[0]);
    click(item('Delete'));
    await settle();
    expect(asked).toEqual([`DELETE /processing/jobs/${jobId(1)}`]);
    menuOf(rows()[0]);
    press(document.querySelector('.pm-menu-items')!, 'd');
    await settle();
    expect(asked).toEqual([`DELETE /processing/jobs/${jobId(1)}`, `DELETE /processing/jobs/${jobId(2)}`]);
    expect(rows()).toHaveLength(0);
  });

  it('has "Restore" for a deleted job whose day lasts, and neither "Delete" nor "Restore" once it is over', () => {
    put({
      jobs: [
        finished(1, { phase: 'dismissed', deletedUntil: new Date(NOW + 3_600_000).toISOString(), serverDeleted: true }),
        finished(2, { phase: 'dismissed', deletedUntil: new Date(NOW - 1000).toISOString(), serverDeleted: true }),
      ],
    });
    mount();
    click(button('Deleted'));
    menuOf(rows()[0]);
    expect(hasItem('Restore')).toBe(true);
    expect(hasItem('Delete')).toBe(false);
    closeMenu();
    menuOf(rows()[1]);
    expect(hasItem('Restore')).toBe(false);
    expect(hasItem('Delete')).toBe(false);
  });
});

describe('Restore', () => {
  const deleted = (n: number, over = {}) =>
    finished(n, { phase: 'dismissed', deletedUntil: new Date(NOW + 3_600_000).toISOString(), serverDeleted: true, ...over });

  it('asks the server with the ↺ of the row, and the job is back under "Active" with its first expiry', async () => {
    serverHolds(jobId(1));
    put({ jobs: [deleted(1)] });
    mount();
    click(button('Deleted'));
    expect(restoreIcon(rows()[0])?.getAttribute('title')).toMatch(/^Restore \(possible until 20 Oct, \d{2}:\d{2}\)$/u);
    click(restoreIcon(rows()[0]));
    await settle();
    expect(asked[0]).toBe(`POST /processing/jobs/${jobId(1)}/restore`);
    expect(fetchMock.mock.calls[0][1]).toEqual({ method: 'POST' });
    expect(rows()).toHaveLength(0);
    click(button('Active'));
    expect(states()).toEqual(['Finished']);
    expect(rows()[0].querySelector('.pm-until')?.textContent).toMatch(/^until 27 Oct, \d{2}:\d{2}$/u);
    expect(job(1)).toMatchObject({ deletedUntil: null, serverDeleted: false, phase: 'successful' });
    expect(stored().jobs[0].deletedUntil).toBeUndefined();
    // The results are read again: the download is back.
    await vi.waitFor(() => expect(rows()[0].querySelector('a[aria-label="Download (ZIP)"]')).not.toBeNull());
  });

  it('restores from the menu as well', async () => {
    serverHolds(jobId(1));
    put({ jobs: [deleted(1)] });
    mount();
    click(button('Deleted'));
    menuOf(rows()[0]);
    click(item('Restore'));
    await settle();
    expect(asked[0]).toBe(`POST /processing/jobs/${jobId(1)}/restore`);
    expect(job(1).deletedUntil).toBeNull();
  });

  it('has no ↺, no day and no Restore once the day is over: the job is deleted for good', () => {
    put({ jobs: [deleted(1, { deletedUntil: new Date(NOW - 1000).toISOString() })] });
    mount();
    click(button('Deleted'));
    expect(states()).toEqual(['Deleted']);
    expect(restoreIcon(rows()[0])).toBeNull();
    expect(rows()[0].querySelector('.pm-until')).toBeNull();
  });

  it('does not ask once the day is over, whatever the screen still shows', async () => {
    put({ jobs: [deleted(1, { deletedUntil: new Date(NOW - 1000).toISOString() })] });
    mount();
    await act(async () => {
      await useProcessingStore.getState().restoreTarget({ jobID: jobId(1) });
    });
    expect(asked).toEqual([]);
    expect(job(1).deletedUntil).not.toBeNull();
  });

  it('loses ↺ at the moment the day is over', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout'], now: NOW });
    put({ jobs: [deleted(1, { deletedUntil: new Date(NOW + 5000).toISOString() })] });
    mount();
    click(button('Deleted'));
    expect(restoreIcon(rows()[0])).not.toBeNull();
    await act(async () => {
      vi.advanceTimersByTime(5200);
    });
    expect(restoreIcon(rows()[0])).toBeNull();
  });

  it('answers `404` of the server with a job that is not there any more, under "Expired"', async () => {
    put({ jobs: [deleted(1)] });
    mount();
    click(button('Deleted'));
    click(restoreIcon(rows()[0]));
    await settle();
    expect(job(1)).toMatchObject({ deletedUntil: null, lost: true, phase: 'gone', error: 'The job could not be restored.' });
    click(button('Expired'));
    expect(states()).toEqual(['No longer available']);
  });

  it('keeps the job deleted and shows the error where the server does not answer', async () => {
    routes[`POST /processing/jobs/${jobId(1)}/restore`] = () => json({ type: 'about:blank', title: 'busy', status: 503, detail: 'x' }, 503);
    put({ jobs: [deleted(1)] });
    mount();
    click(button('Deleted'));
    click(restoreIcon(rows()[0]));
    await settle();
    expect(job(1)).toMatchObject({ deleting: false, error: 'The job could not be restored. Try again.' });
    expect(job(1).deletedUntil).not.toBeNull();
    expect(container.querySelector('.pm-fault')?.textContent).toBe('The job could not be restored. Try again.');
  });
});

describe('an entry the server cannot hold any more', () => {
  it.each([
    ['an expired job', () => finished(1, { expired: true })],
    ['a cancelled job', () => jobEntry(1, { phase: 'dismissed' })],
    ['a job the server forgot', () => jobEntry(1, { phase: 'gone', lost: true })],
    ['a job past its time', () => jobEntry(1, { phase: 'gone', expires: new Date(NOW - 1000).toISOString() })],
  ])('is deleted here only for a day, asking nobody: %s', async (_, make) => {
    put({ jobs: [make()] });
    mount();
    click(button('All'));
    press(openButton(rows()[0]), 'd');
    await settle();
    expect(asked).toEqual([]);
    expect(job(1)).toMatchObject({ serverDeleted: false, deletedUntil: new Date(NOW + DAY).toISOString() });
    click(button('Deleted'));
    expect(rows()[0].querySelector('.pm-until')?.textContent).toMatch(/^restore until 21 Oct/u);
    click(restoreIcon(rows()[0]));
    await settle();
    expect(asked).toEqual([]);
    expect(job(1).deletedUntil).toBeNull();
  });

  it('is back where it was after a restore: an expired one under "Expired"', async () => {
    put({ jobs: [finished(1, { expired: true })] });
    mount();
    click(button('Expired'));
    press(openButton(rows()[0]), 'd');
    await settle();
    expect(rows()).toHaveLength(0);
    click(button('Deleted'));
    click(restoreIcon(rows()[0]));
    await settle();
    click(button('Expired'));
    expect(states()).toEqual(['Expired']);
  });
});

describe('the tabs', () => {
  it('keep a deleted job out of "Active" and "Expired" and list it under "Deleted" and "All"', () => {
    put({
      jobs: [
        finished(1),
        finished(2, { phase: 'dismissed', deletedUntil: new Date(NOW + 3_600_000).toISOString(), serverDeleted: true }),
        finished(3, { expired: true }),
        jobEntry(4, { phase: 'gone', lost: true }),
      ],
    });
    mount();
    expect(titles()).toEqual(['Band math · Sentinel-2 L2A · 1 Oct']);
    click(button('Expired'));
    expect(states()).toEqual(['Expired', 'No longer available']);
    click(button('Deleted'));
    expect(titles()).toEqual(['Band math · Sentinel-2 L2A · 2 Oct']);
    click(button('All'));
    expect(rows()).toHaveLength(4);
  });

  it('say what is missing under "Deleted"', () => {
    put({ jobs: [finished(1)] });
    mount();
    click(button('Deleted'));
    expect(container.querySelector('.pm-empty')?.textContent).toBe('No deleted jobs.');
  });

  it('remember "Deleted" for the next time', () => {
    mount();
    click(button('Deleted'));
    expect(localStorage.getItem('earthx.jobfilter')).toBe('deleted');
  });

  it('show an archived job that was deleted under "Deleted" only', () => {
    put({ jobs: [finished(1, { archived: true, phase: 'dismissed', deletedUntil: new Date(NOW + 3_600_000).toISOString(), serverDeleted: true })] });
    mount();
    expect(rows()).toHaveLength(0);
    click(button('Deleted'));
    expect(rows()).toHaveLength(1);
  });

  it('are four, and may wrap in a narrow panel', async () => {
    const css = (await import('../index.css?raw')).default;
    expect(css).toMatch(/\.pm-filter\s*\{[^}]*flex-wrap:\s*wrap/u);
    expect(css).toMatch(/\.pm-tools\s*\{[^}]*flex-wrap:\s*wrap/u);
  });
});

describe('a batch', () => {
  const part = (n: number, over: Parameters<typeof finished>[1] = {}) => finished(n, { batchId: BATCH, part: `S${n}`, ...over });
  const deletedPart = (n: number, over = {}) =>
    part(n, { phase: 'dismissed', deletedUntil: new Date(NOW + 3_600_000).toISOString(), serverDeleted: true, ...over });
  const withBatch = (jobs: Parameters<typeof put>[0]['jobs']) => put({ jobs, batches: [batchEntry(BATCH)] });

  it('is deleted as a whole with D: every part asks the server, the row waits under "Deleted"', async () => {
    for (const n of [1, 2, 3]) serverHolds(jobId(n));
    withBatch([part(1), part(2), part(3)]);
    mount();
    press(openButton(rows()[0]), 'd');
    await settle();
    expect(asked.sort()).toEqual([1, 2, 3].map((n) => `DELETE /processing/jobs/${jobId(n)}`));
    expect(rows()).toHaveLength(0);
    click(button('Deleted'));
    expect(rows()[0].querySelector('.pm-state')?.textContent).toBe('3 deleted');
    expect(rows()[0].querySelector('.pm-until')?.textContent).toMatch(/^restore until 21 Oct/u);
  });

  it('is deleted by a key pressed on one of its parts: the part has no key of its own', async () => {
    for (const n of [1, 2]) serverHolds(jobId(n));
    withBatch([part(1), part(2)]);
    mount();
    click(button('▸'));
    press(openButton(container.querySelector<HTMLElement>('.pm-parts .pm-row')!), 'd');
    await settle();
    expect(asked).toHaveLength(2);
  });

  it('has no "Delete" while a part waits or runs: the batch has "Cancel all"', async () => {
    withBatch([part(1), jobEntry(2, { batchId: BATCH, part: 'S2' })]);
    mount();
    menuOf(rows()[0]);
    expect(hasItem('Delete')).toBe(false);
    expect(hasItem('Cancel all')).toBe(true);
    closeMenu();
    press(openButton(rows()[0]), 'd');
    await settle();
    expect(asked).toEqual([]);
  });

  it('deletes one part and leaves the others and the batch where they are', async () => {
    serverHolds(jobId(2));
    withBatch([part(1), part(2), part(3)]);
    mount();
    click(button('▸'));
    const second = container.querySelectorAll<HTMLElement>('.pm-parts .pm-row')[1];
    menuOf(second);
    click(item('Delete'));
    await settle();
    expect(asked).toEqual([`DELETE /processing/jobs/${jobId(2)}`]);
    expect(rows()[0].querySelector('.pm-state')?.textContent).toBe('2 done · 1 deleted');
    // Not every part is deleted, so the batch stays under "Active".
    expect(titles()).toHaveLength(1);
    expect(job(1).deletedUntil).toBeNull();
    expect(job(3).deletedUntil).toBeNull();
    expect(job(2).deletedUntil).not.toBeNull();
    // And that part can be restored by itself.
    const parts = container.querySelectorAll<HTMLElement>('.pm-parts .pm-row');
    expect(restoreIcon(parts[1])).not.toBeNull();
    expect(restoreIcon(parts[0])).toBeNull();
  });

  it('is restored as a whole with the ↺ of its row, and from the menu', async () => {
    for (const n of [1, 2]) serverHolds(jobId(n));
    withBatch([deletedPart(1), deletedPart(2)]);
    mount();
    click(button('Deleted'));
    click(restoreIcon(rows()[0]));
    await settle();
    expect(asked.filter((a) => a.startsWith('POST')).sort()).toEqual([1, 2].map((n) => `POST /processing/jobs/${jobId(n)}/restore`));
    expect(useProcessingStore.getState().jobs.every((j) => j.deletedUntil === null)).toBe(true);
    click(button('Active'));
    expect(rows()).toHaveLength(1);
  });

  it('is deleted for good when its day is over: no ↺, no day', () => {
    withBatch([deletedPart(1, { deletedUntil: new Date(NOW - 1000).toISOString() }), deletedPart(2, { deletedUntil: new Date(NOW - 1000).toISOString() })]);
    mount();
    click(button('Deleted'));
    expect(restoreIcon(rows()[0])).toBeNull();
    expect(rows()[0].querySelector('.pm-until')).toBeNull();
  });

  it('names the soonest end of the days when the parts were deleted at different times', () => {
    withBatch([
      deletedPart(1, { deletedUntil: new Date(NOW + 2 * 3_600_000).toISOString() }),
      deletedPart(2, { deletedUntil: new Date(NOW + 3_600_000).toISOString() }),
    ]);
    mount();
    click(button('Deleted'));
    expect(rows()[0].querySelector('.pm-until')?.getAttribute('title')).toBe(new Date(NOW + 3_600_000).toISOString());
  });

  it('is "Expired" when the parts that are not deleted have expired, and "Deleted" only when all are deleted', () => {
    withBatch([deletedPart(1), part(2, { expired: true })]);
    mount();
    expect(rows()).toHaveLength(0);
    click(button('Expired'));
    expect(rows()).toHaveLength(1);
    click(button('Deleted'));
    expect(rows()).toHaveLength(0);
  });
});

describe('a reload', () => {
  const saved = (jobs: object[]) =>
    localStorage.setItem(SHELF_KEY, JSON.stringify({ v: 1, jobs, batches: [], groups: [] }));
  const stub = (id: string, extra: object = {}) => ({ jobID: id, expires: new Date(NOW + 7 * DAY).toISOString(), createdAt: new Date(NOW - 60_000).toISOString(), title: 'Kept', ...extra });

  it('does not ask the server again about a job it answered `404` for: it is "No longer available" under "Expired"', async () => {
    saved([stub(jobId(1), { lost: true })]);
    act(() => useProcessingStore.getState().resumeJobs());
    mount();
    await settle();
    expect(asked).toEqual([]);
    expect(rows()).toHaveLength(0);
    click(button('Expired'));
    expect(states()).toEqual(['No longer available']);
    expect(rows()[0].querySelector('.pm-state')?.getAttribute('title')).toBe('The server does not know this job any more.');
    expect(rows()[0].querySelector('.pm-until')).toBeNull();
  });

  it('asks about a job once, writes the answer down, and does not ask after the next reload', async () => {
    const polls: string[] = [];
    setTrackerOptions({
      EventSource: null,
      fetchJob: async (id) => {
        polls.push(id);
        throw new HttpError(404, 'there is no such job', 'there is no such job');
      },
      pollMs: 60_000,
    });
    saved([stub(jobId(1))]);
    act(() => useProcessingStore.getState().resumeJobs());
    mount();
    await vi.waitFor(() => expect(job(1).lost).toBe(true));
    expect(polls).toEqual([jobId(1)]);
    expect(stored().jobs[0]).toMatchObject({ jobID: jobId(1), lost: true });
    // The next page: nothing is asked.
    act(() => root.unmount());
    resetJobs();
    root = createRoot(container);
    act(() => useProcessingStore.getState().resumeJobs());
    mount();
    await settle();
    expect(polls).toEqual([jobId(1)]);
    click(button('Expired'));
    expect(states()).toEqual(['No longer available']);
  });

  it('does not ask about a deleted job either, and offers ↺ for the rest of its day', async () => {
    saved([stub(jobId(1), { deletedUntil: new Date(NOW + 3_600_000).toISOString(), serverDeleted: true })]);
    act(() => useProcessingStore.getState().resumeJobs());
    mount();
    await settle();
    expect(asked).toEqual([]);
    click(button('Deleted'));
    expect(states()).toEqual(['Deleted']);
    expect(restoreIcon(rows()[0])).not.toBeNull();
  });

  it('restores a deleted job after the reload: the server takes it back and its results are read again', async () => {
    serverHolds(jobId(1));
    saved([stub(jobId(1), { deletedUntil: new Date(NOW + 3_600_000).toISOString(), serverDeleted: true })]);
    act(() => useProcessingStore.getState().resumeJobs());
    mount();
    click(button('Deleted'));
    click(restoreIcon(rows()[0]));
    await settle();
    expect(job(1)).toMatchObject({ phase: 'successful', deletedUntil: null });
    click(button('Active'));
    expect(states()).toEqual(['Finished']);
  });

  it('reads a shelf with a bad deletion as a job that is not deleted, and keeps the job', () => {
    saved([stub(jobId(1), { deletedUntil: 'tomorrow', serverDeleted: true, lost: 'yes' })]);
    act(() => useProcessingStore.getState().resumeJobs());
    expect(job(1)).toMatchObject({ deletedUntil: null, serverDeleted: false, lost: false });
  });
});

describe('only the route of the job is asked', () => {
  it('sends the jobID in the path of the job and nowhere else, and no body', async () => {
    serverHolds(jobId(1));
    put({ jobs: [finished(1)] });
    mount();
    press(openButton(rows()[0]), 'd');
    await settle();
    click(button('Deleted'));
    click(restoreIcon(rows()[0]));
    await settle();
    for (const call of fetchMock.mock.calls) {
      const [url, init] = call as [string, RequestInit | undefined];
      expect(url).toMatch(new RegExp(`^/processing/jobs/${jobId(1)}(/restore|/results)?$`, 'u'));
      expect(init?.body).toBeUndefined();
    }
  });
});

describe('another tab', () => {
  const write = (jobs: object[]) => {
    localStorage.setItem(SHELF_KEY, JSON.stringify({ v: 1, jobs, batches: [], groups: [] }));
    act(() => {
      window.dispatchEvent(new StorageEvent('storage', { key: SHELF_KEY, newValue: localStorage.getItem(SHELF_KEY) }));
    });
  };
  const stub = (extra: object = {}) => ({ jobID: jobId(1), expires: new Date(NOW + 7 * DAY).toISOString(), createdAt: new Date(NOW - 60_000).toISOString(), title: 'Kept', ...extra });

  it('deleted the job: this tab lists it as deleted and does not ask about it', async () => {
    put({ jobs: [finished(1)] });
    act(() => useProcessingStore.getState().resumeJobs());
    mount();
    write([stub({ deletedUntil: new Date(NOW + 3_600_000).toISOString(), serverDeleted: true })]);
    await settle();
    expect(rows()).toHaveLength(0);
    click(button('Deleted'));
    expect(states()).toEqual(['Deleted']);
    expect(asked).toEqual([]);
  });

  it('restored the job: this tab asks about it again, as it knows nothing of its state', async () => {
    const asks: string[] = [];
    setTrackerOptions({
      EventSource: null,
      fetchJob: async (id) => {
        asks.push(id);
        return status({ jobID: id, status: 'successful', progress: 100 });
      },
      pollMs: 60_000,
    });
    put({ jobs: [finished(1, { phase: 'dismissed', deletedUntil: new Date(NOW + 3_600_000).toISOString(), serverDeleted: true })] });
    mount();
    click(button('Deleted'));
    write([stub()]);
    click(button('Active'));
    await vi.waitFor(() => expect(asks).toEqual([jobId(1)]));
    expect(job(1)).toMatchObject({ deletedUntil: null, phase: 'successful' });
  });
});
