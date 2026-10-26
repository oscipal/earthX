// @vitest-environment jsdom
//
// The processing manager (UI-01 §6.10): rows, rename, archive, groups, filter, a batch as one row, what the
// browser kept, and what it says when it kept less. No backend: `fetch` answers by route.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { HttpError } from '../api';
import { batchEntry, finished, jobEntry, jobId, NOW, status } from '../fixtures/jobEntries';
import { SHELF_KEY } from '../jobShelf';
import { resetJobs, setTrackerOptions, useProcessingStore } from '../processingStore';
import css from '../index.css?raw';
import ProcessingManager, { GROUP_NOT_EMPTY_TIP, NOT_KEPT_TEXT, STORAGE_FULL_TIP } from './ProcessingManager';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const BATCH = 'b'.repeat(32);
const GROUP = 'a'.repeat(32);
const OTHER_GROUP = 'c'.repeat(32);

let container: HTMLDivElement;
let root: Root;
let routes: Record<string, (init?: RequestInit) => Response>;
let fetchMock: ReturnType<typeof vi.fn>;

const doc = (jobID: string, state: string, progress = 0) => ({
  processID: 'recipe',
  type: 'process',
  jobID,
  status: state,
  message: '',
  progress,
  created: '2026-10-10T10:00:00Z',
  expires: new Date(Date.now() + 7 * 86_400_000).toISOString(),
  recipeID: 'r',
  links: [],
});
const json = (body: unknown, code = 200) =>
  new Response(JSON.stringify(body), { status: code, headers: { 'Content-Type': code >= 400 ? 'application/problem+json' : 'application/json' } });

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers({ toFake: ['Date'], now: NOW });
  localStorage.clear();
  sessionStorage.clear();
  routes = {};
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const route = routes[`${init?.method ?? 'GET'} ${url}`];
    return route ? route(init) : json({ type: 'about:blank', title: 'Not found', status: 404 }, 404);
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
const button = (label: string | RegExp, within: ParentNode = container): HTMLButtonElement => {
  const found = [...within.querySelectorAll('button')].find((b) => (typeof label === 'string' ? b.textContent?.trim() === label : label.test(b.textContent ?? '')));
  if (!found) throw new Error(`no button ${String(label)} in ${container.textContent}`);
  return found;
};
const rows = () => [...container.querySelectorAll<HTMLElement>('.pm-rows > .pm-row')];
const titles = () => rows().map((r) => r.querySelector('.pm-title')?.textContent);
const menuOf = (row: Element) => click(row.querySelector('button[aria-haspopup="menu"]'));
const item = (label: string) => button(label, document.querySelector('[role="menu"]')!);
const stored = () => JSON.parse(localStorage.getItem(SHELF_KEY)!);
const type = (input: HTMLInputElement, value: string) => {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!;
  act(() => {
    setter.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
};
const key = (target: Element, name: string) => act(() => target.dispatchEvent(new KeyboardEvent('keydown', { key: name, bubbles: true, cancelable: true })));
const field = () => container.querySelector<HTMLInputElement>('input.pm-rename')!;

describe('the rows', () => {
  it('says "No jobs yet." where there is none, and "No active jobs." where all are archived', () => {
    mount();
    expect(container.querySelector('.pm-empty')?.textContent).toBe('No jobs yet.');
    put({ jobs: [jobEntry(1, { archived: true })] });
    expect(container.querySelector('.pm-empty')?.textContent).toBe('No active jobs.');
  });

  it('lists a job with its title, progress and expiry, the newest first', () => {
    put({ jobs: [jobEntry(2), jobEntry(1, { status: status({ progress: 70 }) })] });
    mount();
    expect(titles()).toEqual(['Band math · Sentinel-2 L2A · 1 Oct', 'Band math · Sentinel-2 L2A · 2 Oct']);
    const first = rows()[0];
    expect(first.querySelector('.pm-state')?.textContent).toBe('70%');
    expect(first.querySelector('progress')?.getAttribute('value')).toBe('70');
    expect(first.querySelector('.pm-until')?.textContent).toMatch(/^until 27 Oct, \d{2}:\d{2}$/u);
  });

  it('shows a finished job as such, with "Download (ZIP)" at the end of the row and nothing else', () => {
    put({ jobs: [finished(1)] });
    mount();
    const row = rows()[0];
    expect(row.querySelector('.pm-state')?.textContent).toBe('Finished');
    expect(row.querySelector('progress')).toBeNull();
    const link = row.querySelector<HTMLAnchorElement>('a[aria-label="Download (ZIP)"]')!;
    expect(link.getAttribute('href')).toBe(`/processing/jobs/${jobId(1)}/results/result.zip`);
    expect(row.querySelectorAll('a')).toHaveLength(1);
  });

  it('keeps the place of the download when there is none, so no other symbol moves', () => {
    put({ jobs: [finished(1), jobEntry(2)] });
    mount();
    const [done, running] = rows();
    const line = (row: Element) => [...row.querySelector('.pm-line')!.children].map((c) => c.className.split(' ')[0]);
    expect(line(running)).toEqual(line(done));
    expect(running.querySelector('a')).toBeNull();
  });

  it('shows a finished job past its expiry as expired, with the reason as the tooltip of the dimmed symbol', () => {
    put({ jobs: [finished(1, { expires: new Date(NOW - 1000).toISOString() })] });
    mount();
    click(button('Expired'));
    expect(rows()[0].querySelector('.pm-state')?.textContent).toBe('Expired');
    expect(rows()[0].querySelector('a')).toBeNull();
    // Off, but reachable by keyboard, so that the reason shows on focus as well as on hover.
    const off = rows()[0].querySelector<HTMLButtonElement>('button.pm-icon[aria-disabled="true"]')!;
    expect(off.getAttribute('data-tip')).toBe('Expired: results are kept for 7 days.');
    expect(off.disabled).toBe(false);
    // The date stays, so the user can see when it went.
    expect(rows()[0].querySelector('.pm-until')?.textContent).toMatch(/^until \d+ Oct, \d{2}:\d{2}$/u);
  });

  it('shows a failed job with its reason, and a cancelled one as cancelled', () => {
    put({ jobs: [jobEntry(1, { phase: 'failed', failure: 'The source failed' }), jobEntry(2, { phase: 'dismissed' })] });
    mount();
    expect(rows()[0].querySelector('.pm-state')?.textContent).toBe('Failed');
    expect(rows()[0].querySelector('.pm-fault')?.textContent).toBe('The source failed');
    expect(rows()[1].querySelector('.pm-state')?.textContent).toBe('Cancelled');
  });

  it('names a job without a title, and cuts a long one to the line with the whole name as the tooltip', () => {
    const long = 'x'.repeat(200);
    put({ jobs: [jobEntry(1, { title: null, titleDefault: null }), jobEntry(2, { title: long })] });
    mount();
    expect(titles()[0]).toBe('Untitled job');
    expect(rows()[1].querySelector('.pm-open')?.getAttribute('title')).toBe(long);
  });

  it('opens the details of a job in the processing window with a click on the row', () => {
    put({ jobs: [jobEntry(1)] });
    mount();
    click(rows()[0].querySelector('.pm-open'));
    expect(useProcessingStore.getState()).toMatchObject({ open: true, detailJobID: jobId(1) });
  });

  it('has nothing to delete a job and no "Methods" or "Copy" in any state', () => {
    put({ jobs: [finished(1), jobEntry(2), jobEntry(3, { phase: 'failed' }), jobEntry(4, { phase: 'gone' })] });
    mount();
    for (const row of rows()) menuOf(row);
    const text = container.textContent ?? '';
    for (const word of ['Methods', 'Copy', 'Remove', 'Delete']) expect(text).not.toContain(word);
    expect(container.querySelector('[title*="Remove"], [aria-label*="Remove"]')).toBeNull();
  });
});

describe('the menu of a row', () => {
  it('offers rename, move, archive and, for a running job, cancel; for a finished one no cancel', () => {
    put({ jobs: [jobEntry(1), finished(2)] });
    mount();
    menuOf(rows()[0]);
    expect([...document.querySelectorAll('[role="menu"] button')].map((b) => b.textContent)).toEqual(['Rename (R)', 'Move to group… (G)', 'Archive (A)', 'Cancel']);
    // A real click begins with a press beside the open menu, which closes it.
    act(() => document.body.dispatchEvent(new Event('pointerdown', { bubbles: true })));
    menuOf(rows()[1]);
    expect([...document.querySelectorAll('[role="menu"] button')].map((b) => b.textContent)).toEqual(['Rename (R)', 'Move to group… (G)', 'Archive (A)']);
  });

  it('closes on Escape and gives the focus back to its button', () => {
    put({ jobs: [jobEntry(1)] });
    mount();
    menuOf(rows()[0]);
    key(document.querySelector('[role="menu"] button')!, 'Escape');
    expect(document.querySelector('[role="menu"]')).toBeNull();
    expect(document.activeElement).toBe(container.querySelector('button[aria-haspopup="menu"]'));
  });

  it('lies outside the scrolling list, over the whole window, so the panel cannot cut it off', () => {
    put({ jobs: [jobEntry(1)] });
    mount();
    menuOf(rows()[0]);
    const menu = document.querySelector<HTMLElement>('[role="menu"]')!;
    expect(container.contains(menu)).toBe(false);
    expect(menu.closest('.pm-list')).toBeNull();
    expect(menu.style.position).toBe('fixed');
  });

  it('puts the focus in the menu when it opens, keeps it there for the list of groups, and moves it with the arrow keys', () => {
    put({ jobs: [jobEntry(1)], groups: [{ id: GROUP, name: 'Field 7' }] });
    mount();
    menuOf(rows()[0]);
    const items = () => [...document.querySelectorAll<HTMLElement>('[role="menu"] button')];
    expect(document.activeElement).toBe(items()[0]);
    key(items()[0], 'ArrowDown');
    expect(document.activeElement).toBe(items()[1]);
    key(items()[1], 'ArrowUp');
    key(items()[0], 'ArrowUp');
    expect(document.activeElement).toBe(items().at(-1));
    key(items().at(-1)!, 'Home');
    expect(document.activeElement).toBe(items()[0]);
    key(items()[0], 'End');
    click(items()[1]);
    expect(items().map((b) => b.textContent)).toEqual(['Ungrouped', 'Field 7']);
    expect(document.activeElement).toBe(items()[0]);
    // Escape still works from there.
    key(items()[0], 'Escape');
    expect(document.querySelector('[role="menu"]')).toBeNull();
  });

  it('closes with a click beside it', () => {
    put({ jobs: [jobEntry(1)] });
    mount();
    menuOf(rows()[0]);
    act(() => document.body.dispatchEvent(new Event('pointerdown', { bubbles: true })));
    expect(document.querySelector('[role="menu"]')).toBeNull();
  });
});

describe('rename', () => {
  it('keeps a new title, in the list and in the browser', () => {
    put({ jobs: [jobEntry(1)] });
    mount();
    menuOf(rows()[0]);
    click(item('Rename (R)'));
    type(field(), 'Field 7 · NDVI');
    key(field(), 'Enter');
    expect(titles()).toEqual(['Field 7 · NDVI']);
    expect(stored().jobs[0].title).toBe('Field 7 · NDVI');
  });

  it('brings the default title back for an empty name', () => {
    put({ jobs: [jobEntry(1, { title: 'Mine', titleDefault: 'Band math · Sentinel-2 L2A · 1 Oct' })] });
    mount();
    menuOf(rows()[0]);
    click(item('Rename (R)'));
    type(field(), '   ');
    key(field(), 'Enter');
    expect(titles()).toEqual(['Band math · Sentinel-2 L2A · 1 Oct']);
  });

  it('drops the edit on Escape and keeps the title', () => {
    put({ jobs: [jobEntry(1)] });
    mount();
    menuOf(rows()[0]);
    click(item('Rename (R)'));
    type(field(), 'Other');
    key(field(), 'Escape');
    expect(container.querySelector('input.pm-rename')).toBeNull();
    expect(titles()).toEqual(['Band math · Sentinel-2 L2A · 1 Oct']);
  });

  it('cuts a title at 200 characters', () => {
    put({ jobs: [jobEntry(1)] });
    mount();
    menuOf(rows()[0]);
    click(item('Rename (R)'));
    expect(field().maxLength).toBe(200);
    useProcessingStore.getState().renameJob(jobId(1), 'y'.repeat(500));
    expect(useProcessingStore.getState().jobs[0].title).toHaveLength(200);
  });
});

describe('archive and the filter', () => {
  it('moves a job out of "Active" and into "All", marked, and back', () => {
    put({ jobs: [jobEntry(1), jobEntry(2)] });
    mount();
    menuOf(rows()[0]);
    click(item('Archive (A)'));
    expect(titles()).toEqual(['Band math · Sentinel-2 L2A · 2 Oct']);
    expect(stored().jobs.find((j: { jobID: string }) => j.jobID === jobId(1)).archived).toBe(true);
    click(button('All'));
    expect(titles()).toHaveLength(2);
    expect(rows()[0].classList.contains('archived')).toBe(true);
    expect(rows()[0].querySelector('.pm-tag')?.textContent).toBe('Archived');
    menuOf(rows()[0]);
    click(item('Unarchive (A)'));
    click(button('Active'));
    expect(titles()).toHaveLength(2);
  });

  it('keeps finished and failed jobs under "Active", and lets the expired ones go to "Expired"', () => {
    put({ jobs: [finished(1), jobEntry(2, { phase: 'failed' }), jobEntry(3, { phase: 'gone' }), finished(4, { expired: true })] });
    mount();
    expect(titles()).toEqual(['Band math · Sentinel-2 L2A · 1 Oct', 'Band math · Sentinel-2 L2A · 2 Oct']);
    click(button('Expired'));
    expect(titles()).toEqual(['Band math · Sentinel-2 L2A · 3 Oct', 'Band math · Sentinel-2 L2A · 4 Oct']);
    click(button('All'));
    expect(rows()).toHaveLength(4);
  });

  it('lists an expired job that is archived under "Expired" and "All", not under "Active"', () => {
    put({ jobs: [jobEntry(1, { phase: 'gone', archived: true }), jobEntry(2, { archived: true })] });
    mount();
    expect(rows()).toHaveLength(0);
    click(button('Expired'));
    expect(titles()).toEqual(['Band math · Sentinel-2 L2A · 1 Oct']);
    expect(rows()[0].querySelector('.pm-tag')?.textContent).toBe('Archived');
    click(button('All'));
    expect(rows()).toHaveLength(2);
  });

  it('calls a batch expired when all its parts are, and a batch with one part that still stands active', () => {
    const other = 'c'.repeat(32);
    put({
      jobs: [
        jobEntry(1, { batchId: BATCH, part: 'S1', phase: 'gone' }),
        jobEntry(2, { batchId: BATCH, part: 'S2', phase: 'gone' }),
        jobEntry(3, { batchId: other, part: 'S1', phase: 'gone' }),
        finished(4, { batchId: other, part: 'S2' }),
      ],
      batches: [batchEntry(BATCH, { title: 'Gone batch' }), batchEntry(other, { title: 'Mixed batch', createdAt: new Date(NOW - 120_000).toISOString() })],
    });
    mount();
    expect(titles()).toEqual(['Mixed batch']);
    click(button('Expired'));
    expect(titles()).toEqual(['Gone batch']);
  });

  it('says which kind of job is missing where a filter shows none', () => {
    put({ jobs: [finished(1)] });
    mount();
    click(button('Expired'));
    expect(container.querySelector('.pm-empty')?.textContent).toBe('No expired jobs.');
    click(button('Active'));
    put({ jobs: [jobEntry(1, { phase: 'gone' })] });
    expect(container.querySelector('.pm-empty')?.textContent).toBe('No active jobs.');
  });

  it('has the three tabs in the order Active, Expired, All, with "Active" first', () => {
    mount();
    expect([...container.querySelectorAll('.pm-filter button')].map((b) => b.textContent)).toEqual(['Active', 'Expired', 'All']);
    expect(button('Active').getAttribute('aria-pressed')).toBe('true');
  });

  it('remembers the filter for the next time', () => {
    put({ jobs: [jobEntry(1, { archived: true })] });
    mount();
    expect(button('Active').getAttribute('aria-pressed')).toBe('true');
    click(button('Expired'));
    expect(localStorage.getItem('earthx.jobfilter')).toBe('expired');
    click(button('All'));
    expect(localStorage.getItem('earthx.jobfilter')).toBe('all');
    act(() => root.unmount());
    root = createRoot(container);
    mount();
    expect(button('All').getAttribute('aria-pressed')).toBe('true');
    expect(rows()).toHaveLength(1);
  });

  it('falls back to "Active" for a stored filter it does not know', () => {
    localStorage.setItem('earthx.jobfilter', 'everything');
    mount();
    expect(button('Active').getAttribute('aria-pressed')).toBe('true');
  });
});

describe('groups', () => {
  it('makes a group with "New group" and shows it, empty, under its name', () => {
    put({ jobs: [jobEntry(1)] });
    mount();
    click(button('＋ New group'));
    type(field(), 'Field 7');
    key(field(), 'Enter');
    const sections = [...container.querySelectorAll('.pm-group')].map((s) => s.getAttribute('aria-label'));
    expect(sections).toEqual(['Ungrouped', 'Field 7']);
    expect(stored().groups).toEqual([{ id: expect.stringMatching(/^[0-9a-f]{32}$/u), name: 'Field 7' }]);
  });

  it('makes no group of an empty name', () => {
    mount();
    click(button('＋ New group'));
    type(field(), '  ');
    key(field(), 'Enter');
    expect(useProcessingStore.getState().groups).toEqual([]);
    expect(container.querySelector('input.pm-rename')).toBeNull();
  });

  it('moves a job to a group, and out of it, from the menu', () => {
    put({ jobs: [jobEntry(1), jobEntry(2)], groups: [{ id: GROUP, name: 'Field 7' }] });
    mount();
    menuOf(rows()[0]);
    click(item('Move to group… (G)'));
    expect([...document.querySelectorAll('[role="menuitemradio"]')].map((b) => [b.textContent, b.getAttribute('aria-checked')])).toEqual([
      ['Ungrouped', 'true'],
      ['Field 7', 'false'],
    ]);
    click(item('Field 7'));
    const group = container.querySelector('.pm-group[aria-label="Field 7"]')!;
    expect(group.querySelectorAll('.pm-row')).toHaveLength(1);
    expect(stored().jobs.find((j: { jobID: string }) => j.jobID === jobId(1)).groupId).toBe(GROUP);
    menuOf(group.querySelector('.pm-row')!);
    click(item('Move to group… (G)'));
    click(item('Ungrouped'));
    expect(group.querySelectorAll('.pm-row')).toHaveLength(0);
  });

  it('does not move a job to a group that does not exist', () => {
    put({ jobs: [jobEntry(1)] });
    useProcessingStore.getState().moveToGroup({ jobID: jobId(1) }, OTHER_GROUP);
    expect(useProcessingStore.getState().jobs[0].groupId).toBeNull();
  });

  it('renames a group, and keeps its jobs', () => {
    put({ jobs: [jobEntry(1, { groupId: GROUP })], groups: [{ id: GROUP, name: 'Field 7' }] });
    mount();
    click(container.querySelector('button[aria-label="Rename Field 7"]'));
    type(field(), 'Field 8');
    key(field(), 'Enter');
    expect(container.querySelector('.pm-group-name + button, .pm-group-head h3')?.textContent).toBe('Field 8');
    expect(container.querySelector('.pm-group[aria-label="Field 8"] .pm-row')).not.toBeNull();
    expect(stored().groups[0].name).toBe('Field 8');
  });

  it('lets only an empty group go, and a group that holds an archived job is not empty', () => {
    put({ jobs: [jobEntry(1, { groupId: GROUP, archived: true })], groups: [{ id: GROUP, name: 'Field 7' }, { id: OTHER_GROUP, name: 'Empty' }] });
    mount();
    const full = container.querySelector<HTMLButtonElement>('button[aria-label^="Remove Field 7"]')!;
    expect(full.getAttribute('aria-disabled')).toBe('true');
    expect(full.getAttribute('data-tip')).toBe(GROUP_NOT_EMPTY_TIP);
    click(full);
    expect(useProcessingStore.getState().groups).toHaveLength(2);
    expect(useProcessingStore.getState().removeGroup(GROUP)).toBe(false);
    click(container.querySelector('button[aria-label="Remove Empty"]'));
    expect(useProcessingStore.getState().groups.map((g) => g.name)).toEqual(['Field 7']);
  });

  it('stays removed after a reload: the union with the browser does not give it back', () => {
    put({ groups: [{ id: GROUP, name: 'Field 7' }] });
    act(() => {
      useProcessingStore.getState().createGroup('Other');
    });
    expect(stored().groups).toHaveLength(2);
    act(() => {
      useProcessingStore.getState().removeGroup(GROUP);
    });
    expect(stored().groups.map((g: { name: string }) => g.name)).toEqual(['Other']);
    act(() => resetJobs());
    act(() => useProcessingStore.getState().resumeJobs());
    expect(useProcessingStore.getState().groups.map((g) => g.name)).toEqual(['Other']);
  });

  it('shows a job whose group is gone as ungrouped', () => {
    put({ jobs: [jobEntry(1, { groupId: OTHER_GROUP })], groups: [] });
    mount();
    expect(titles()).toHaveLength(1);
    expect(container.querySelectorAll('.pm-group')).toHaveLength(1);
  });

  it('puts the ungrouped first, then the groups in the order they were made', () => {
    put({ jobs: [jobEntry(1, { groupId: OTHER_GROUP }), jobEntry(2), jobEntry(3, { groupId: GROUP })], groups: [{ id: GROUP, name: 'First' }, { id: OTHER_GROUP, name: 'Second' }] });
    mount();
    expect([...container.querySelectorAll('.pm-group')].map((s) => s.getAttribute('aria-label'))).toEqual(['Ungrouped', 'First', 'Second']);
  });
});

const press = (target: Element, name: string, init: KeyboardEventInit = {}) => {
  const event = new KeyboardEvent('keydown', { key: name, bubbles: true, cancelable: true, ...init });
  act(() => target.dispatchEvent(event));
  return event;
};
const openButton = (row: Element) => row.querySelector<HTMLButtonElement>('.pm-open')!;

describe('the keys of a focused row (R, G, A)', () => {
  it('rename with R, and the key is not typed into the field that opens', () => {
    put({ jobs: [jobEntry(1)] });
    mount();
    const event = press(openButton(rows()[0]), 'r');
    expect(event.defaultPrevented).toBe(true);
    expect(field().value).toBe('Band math · Sentinel-2 L2A · 1 Oct');
    key(field(), 'Escape');
    expect(titles()).toEqual(['Band math · Sentinel-2 L2A · 1 Oct']);
  });

  it('take the capital letters as well', () => {
    put({ jobs: [jobEntry(1)] });
    mount();
    press(openButton(rows()[0]), 'R', { shiftKey: true });
    expect(container.querySelector('input.pm-rename')).not.toBeNull();
  });

  it('open the list of groups with G, with the focus in it', () => {
    put({ jobs: [jobEntry(1)], groups: [{ id: GROUP, name: 'Field 7' }] });
    mount();
    press(openButton(rows()[0]), 'g');
    expect([...document.querySelectorAll('[role="menuitemradio"]')].map((b) => b.textContent)).toEqual(['Ungrouped', 'Field 7']);
    expect(document.activeElement).toBe(document.querySelector('[role="menuitemradio"]'));
    click(item('Field 7'));
    expect(useProcessingStore.getState().jobs[0].groupId).toBe(GROUP);
  });

  it('archive with A, and bring back with A from "All"', () => {
    put({ jobs: [jobEntry(1)] });
    mount();
    press(openButton(rows()[0]), 'a');
    expect(rows()).toHaveLength(0);
    expect(stored().jobs[0].archived).toBe(true);
    click(button('All'));
    press(openButton(rows()[0]), 'A');
    expect(useProcessingStore.getState().jobs[0].archived).toBe(false);
  });

  it('work from every symbol of the row, not only from its title', () => {
    put({ jobs: [finished(1)] });
    mount();
    press(rows()[0].querySelector('a[aria-label="Download (ZIP)"]')!, 'a');
    expect(rows()).toHaveLength(0);
  });

  it('act on a batch as a whole: rename, move, archive with its parts', () => {
    put({ jobs: [jobEntry(1, { batchId: BATCH, part: 'S1' }), jobEntry(2, { batchId: BATCH, part: 'S2' })], batches: [batchEntry(BATCH)], groups: [{ id: GROUP, name: 'Field 7' }] });
    mount();
    press(openButton(rows()[0]), 'r');
    expect(container.querySelector('input.pm-rename')).not.toBeNull();
    key(field(), 'Escape');
    press(openButton(rows()[0]), 'g');
    click(item('Field 7'));
    expect(useProcessingStore.getState().jobs.map((j) => j.groupId)).toEqual([GROUP, GROUP]);
    press(openButton(container.querySelector('.pm-group[aria-label="Field 7"] .pm-row')!), 'a');
    expect(useProcessingStore.getState().jobs.every((j) => j.archived)).toBe(true);
  });

  it('do nothing for a part of a batch: its keys are the batch\'s', () => {
    put({ jobs: [jobEntry(1, { batchId: BATCH, part: 'S1' })], batches: [batchEntry(BATCH)] });
    mount();
    click(button('▸'));
    const part = container.querySelector<HTMLElement>('.pm-parts .pm-row')!;
    const event = press(openButton(part), 'a');
    expect(event.defaultPrevented).toBe(false);
    expect(useProcessingStore.getState().jobs[0].archived).toBe(false);
    expect(useProcessingStore.getState().batches[0].archived).toBe(false);
    expect(part.hasAttribute('aria-keyshortcuts')).toBe(false);
  });

  it('are never taken in a field: the rename field, the name of a new group', () => {
    put({ jobs: [jobEntry(1)] });
    mount();
    press(openButton(rows()[0]), 'r');
    for (const letter of ['a', 'g', 'r']) expect(press(field(), letter).defaultPrevented).toBe(false);
    expect(rows()).toHaveLength(1);
    key(field(), 'Escape');
    click(button('＋ New group'));
    expect(press(field(), 'a').defaultPrevented).toBe(false);
    expect(useProcessingStore.getState().jobs[0].archived).toBe(false);
  });

  it('are never taken in the menu, where a letter belongs to the menu', () => {
    put({ jobs: [jobEntry(1)] });
    mount();
    menuOf(rows()[0]);
    const event = press(document.querySelector('[role="menu"] button')!, 'a');
    expect(event.defaultPrevented).toBe(false);
    expect(useProcessingStore.getState().jobs[0].archived).toBe(false);
  });

  it.each([['ctrlKey'], ['altKey'], ['metaKey']])('leave a key with %s to the browser', (modifier) => {
    put({ jobs: [jobEntry(1)] });
    mount();
    const event = press(openButton(rows()[0]), 'a', { [modifier]: true });
    expect(event.defaultPrevented).toBe(false);
    expect(useProcessingStore.getState().jobs[0].archived).toBe(false);
  });

  it('leave every other key alone', () => {
    put({ jobs: [jobEntry(1)] });
    mount();
    for (const other of ['b', 'd', 'Delete', 'Enter', 'ArrowDown']) expect(press(openButton(rows()[0]), other).defaultPrevented).toBe(false);
    expect(useProcessingStore.getState().jobs).toHaveLength(1);
  });

  it('do not reach a row that has not the focus: a key on the list does nothing', () => {
    put({ jobs: [jobEntry(1)] });
    mount();
    press(container.querySelector('.pm-list')!, 'a');
    expect(useProcessingStore.getState().jobs[0].archived).toBe(false);
  });

  it('are shown in the menu, and named on the row for a screen reader', () => {
    put({ jobs: [jobEntry(1)] });
    mount();
    expect(rows()[0].getAttribute('aria-keyshortcuts')).toBe('R G A');
    menuOf(rows()[0]);
    const entries = [...document.querySelectorAll('[role="menu"] button')];
    expect(entries.map((b) => [b.textContent, b.getAttribute('aria-keyshortcuts')])).toEqual([
      ['Rename (R)', 'R'],
      ['Move to group… (G)', 'G'],
      ['Archive (A)', 'A'],
      ['Cancel', null],
    ]);
  });

  it('have no key for deleting: that is a task of its own', () => {
    put({ jobs: [finished(1)] });
    mount();
    press(openButton(rows()[0]), 'd');
    press(openButton(rows()[0]), 'Delete');
    expect(useProcessingStore.getState().jobs).toHaveLength(1);
    expect(container.textContent).not.toContain('(D)');
  });

  it('give the focus back to the row once a rename ends, by Enter or by Escape', () => {
    put({ jobs: [jobEntry(1)] });
    mount();
    press(openButton(rows()[0]), 'r');
    type(field(), 'New');
    key(field(), 'Enter');
    expect(document.activeElement).toBe(openButton(rows()[0]));
    press(openButton(rows()[0]), 'r');
    key(field(), 'Escape');
    expect(document.activeElement).toBe(openButton(rows()[0]));
  });
});

describe('the focus of a row', () => {
  const down = (target: Element) => act(() => target.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true })));

  it('is set by a click on the row\'s button, which some browsers do not do themselves', () => {
    put({ jobs: [jobEntry(1)] });
    mount();
    expect(document.activeElement).not.toBe(openButton(rows()[0]));
    click(openButton(rows()[0]));
    expect(document.activeElement).toBe(openButton(rows()[0]));
  });

  it('is set by a press on the row beside its button too, so the keys have a row to act on', () => {
    put({ jobs: [jobEntry(1), jobEntry(2)] });
    mount();
    down(rows()[1]);
    expect(document.activeElement).toBe(openButton(rows()[1]));
    down(rows()[1].querySelector('.pm-line')!);
    expect(document.activeElement).toBe(openButton(rows()[1]));
  });

  it('is not taken from a button, a link or a field that was pressed', () => {
    put({ jobs: [finished(1)] });
    mount();
    const link = rows()[0].querySelector('a')!;
    link.focus();
    down(link);
    expect(document.activeElement).toBe(link);
    const more = rows()[0].querySelector<HTMLButtonElement>('button[aria-haspopup]')!;
    more.focus();
    down(more);
    expect(document.activeElement).toBe(more);
  });

  it('is not set on the row of a part of a batch: its keys are the batch\'s', () => {
    put({ jobs: [jobEntry(1, { batchId: BATCH, part: 'S1' })], batches: [batchEntry(BATCH)] });
    mount();
    click(button('▸'));
    const part = container.querySelector<HTMLElement>('.pm-parts .pm-row')!;
    (document.activeElement as HTMLElement | null)?.blur();
    down(part);
    expect(document.activeElement).not.toBe(openButton(part));
  });

  it('goes to the row below when A takes a row out of "Active", so the next key still has a row', async () => {
    put({ jobs: [jobEntry(1), jobEntry(2), jobEntry(3)] });
    mount();
    openButton(rows()[1]).focus();
    press(openButton(rows()[1]), 'a');
    expect(rows()).toHaveLength(2);
    await vi.waitFor(() => expect(document.activeElement).toBe(openButton(rows()[1])));
    expect(titles()[1]).toBe('Band math · Sentinel-2 L2A · 3 Oct');
    // and the next A acts on that row
    press(openButton(rows()[1]), 'a');
    expect(rows()).toHaveLength(1);
  });

  it('goes to the row above when the last row is taken out', async () => {
    put({ jobs: [jobEntry(1), jobEntry(2)] });
    mount();
    openButton(rows()[1]).focus();
    press(openButton(rows()[1]), 'a');
    await vi.waitFor(() => expect(document.activeElement).toBe(openButton(rows()[0])));
  });

  it('stays on the row where A leaves it in the list (under "All")', async () => {
    put({ jobs: [jobEntry(1), jobEntry(2)] });
    mount();
    click(button('All'));
    openButton(rows()[0]).focus();
    press(openButton(rows()[0]), 'a');
    await new Promise((resolve) => setTimeout(resolve, 5));
    expect(document.activeElement).toBe(openButton(rows()[0]));
  });

  it('follows the row to its new group, from the menu as from the keys', async () => {
    put({ jobs: [jobEntry(1), jobEntry(2)], groups: [{ id: GROUP, name: 'Field 7' }] });
    mount();
    openButton(rows()[0]).focus();
    press(openButton(rows()[0]), 'g');
    click(item('Field 7'));
    const moved = () => container.querySelector<HTMLElement>('.pm-group[aria-label="Field 7"] .pm-row .pm-open');
    await vi.waitFor(() => expect(document.activeElement).toBe(moved()));
  });

  it('is not taken back from a field the user went to meanwhile', async () => {
    put({ jobs: [jobEntry(1), jobEntry(2)] });
    mount();
    openButton(rows()[0]).focus();
    press(openButton(rows()[0]), 'a');
    click(button('＋ New group'));
    await new Promise((resolve) => setTimeout(resolve, 5));
    expect(document.activeElement).toBe(field());
  });

  it('is shown on the row: the stylesheet marks the row that has the focus', () => {
    expect(css).toMatch(/\.pm-line:focus-within\s*\{[^}]*background/u);
  });
});

describe('folding a group up', () => {
  const two = () => put({ jobs: [jobEntry(1, { groupId: GROUP }), jobEntry(2, { groupId: GROUP }), jobEntry(3)], groups: [{ id: GROUP, name: 'Field 7' }] });
  const fold = (name: string) => container.querySelector<HTMLButtonElement>(`.pm-fold[aria-label$="${name}"], .pm-fold[aria-label^="Show ${name}"]`)!;
  const group = (name: string) => container.querySelector<HTMLElement>(`.pm-group[aria-label="${name}"]`)!;

  it('hides its rows and says how many there are, and opens again', () => {
    two();
    mount();
    expect(group('Field 7').querySelectorAll('.pm-row')).toHaveLength(2);
    click(fold('Field 7'));
    expect(group('Field 7').querySelectorAll('.pm-row')).toHaveLength(0);
    expect(group('Field 7').querySelector('.pm-group-name')?.textContent).toBe('Field 7 (2)');
    expect(fold('Field 7').getAttribute('aria-expanded')).toBe('false');
    click(fold('Field 7'));
    expect(group('Field 7').querySelectorAll('.pm-row')).toHaveLength(2);
    expect(group('Field 7').querySelector('.pm-group-name')?.textContent).toBe('Field 7');
  });

  it('says what the arrow controls, while the rows are there', () => {
    two();
    mount();
    const arrow = container.querySelector<HTMLButtonElement>('.pm-fold')!;
    expect(arrow.getAttribute('aria-expanded')).toBe('true');
    expect(container.querySelector(`#${arrow.getAttribute('aria-controls')}`)).not.toBeNull();
  });

  it('keeps the state for the next time the page is loaded', () => {
    two();
    mount();
    click(fold('Field 7'));
    expect(JSON.parse(localStorage.getItem('earthx.jobgroups.collapsed')!)).toEqual([GROUP]);
    act(() => root.unmount());
    root = createRoot(container);
    mount();
    expect(group('Field 7').querySelectorAll('.pm-row')).toHaveLength(0);
    expect(fold('Field 7').getAttribute('aria-expanded')).toBe('false');
  });

  it('folds the ungrouped jobs too, once there is a group to tell them from', () => {
    two();
    mount();
    expect(group('Ungrouped').querySelectorAll('.pm-row')).toHaveLength(1);
    click(fold('Ungrouped'));
    expect(group('Ungrouped').querySelectorAll('.pm-row')).toHaveLength(0);
    expect(JSON.parse(localStorage.getItem('earthx.jobgroups.collapsed')!)).toEqual(['ungrouped']);
  });

  it('has no arrow where there is no group: the jobs are all there is', () => {
    put({ jobs: [jobEntry(1)] });
    mount();
    expect(container.querySelector('.pm-fold')).toBeNull();
    expect(container.querySelectorAll('.pm-row')).toHaveLength(1);
  });

  it('counts the rows under the filter, and a folded group shows that count', () => {
    put({ jobs: [jobEntry(1, { groupId: GROUP }), jobEntry(2, { groupId: GROUP, archived: true })], groups: [{ id: GROUP, name: 'Field 7' }] });
    mount();
    click(fold('Field 7'));
    expect(group('Field 7').querySelector('.pm-group-name')?.textContent).toBe('Field 7 (1)');
    click(button('All'));
    expect(group('Field 7').querySelector('.pm-group-name')?.textContent).toBe('Field 7 (2)');
  });

  it('does not stop a group from being renamed or removed while it is folded', () => {
    put({ groups: [{ id: GROUP, name: 'Empty' }] });
    mount();
    click(fold('Empty'));
    click(container.querySelector('button[aria-label="Remove Empty"]'));
    expect(useProcessingStore.getState().groups).toEqual([]);
  });

  it('drops the ids of groups that are gone from what it keeps, at the next change', () => {
    localStorage.setItem('earthx.jobgroups.collapsed', JSON.stringify(['d'.repeat(32)]));
    two();
    mount();
    click(fold('Field 7'));
    expect(JSON.parse(localStorage.getItem('earthx.jobgroups.collapsed')!)).toEqual([GROUP]);
  });

  it.each([['{broken'], ['"text"'], ['{"a":1}'], ['[1,null,"x"]']])('reads %s as what it can: no folded group, or the texts in it', (value) => {
    localStorage.setItem('earthx.jobgroups.collapsed', value);
    two();
    expect(() => mount()).not.toThrow();
    expect(group('Field 7').querySelectorAll('.pm-row')).toHaveLength(2);
  });

  it('works where the browser keeps nothing: the state holds for the page', () => {
    two();
    mount();
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    click(fold('Field 7'));
    expect(group('Field 7').querySelectorAll('.pm-row')).toHaveLength(0);
    vi.restoreAllMocks();
  });
});

describe('a batch', () => {
  const parts = (n: number) =>
    Array.from({ length: n }, (_, i) => jobEntry(i + 1, { batchId: BATCH, part: `S${i + 1}`, title: 'Band math · Sentinel-2 L2A · 12 Oct' }));
  const withBatch = (jobs = parts(3), over = {}) => put({ jobs, batches: [batchEntry(BATCH, over)] });

  it('is one row with the common title, however many jobs it has, and its parts only when opened', () => {
    withBatch(parts(4));
    mount();
    expect(rows()).toHaveLength(1);
    expect(titles()).toEqual(['Band math · Sentinel-2 L2A · 12 Oct']);
    expect(container.querySelectorAll('.pm-parts')).toHaveLength(0);
    click(button('▸'));
    const list = container.querySelector('.pm-parts')!;
    expect([...list.querySelectorAll('.pm-title')].map((t) => t.textContent)).toEqual(['S1', 'S2', 'S3', 'S4']);
    click(button('▾'));
    expect(container.querySelector('.pm-parts')).toBeNull();
  });

  it('can be opened by the arrow or by the row, and says which list the arrow opens', () => {
    withBatch();
    mount();
    const arrow = container.querySelector<HTMLButtonElement>('.pm-chevron')!;
    expect(arrow.getAttribute('aria-expanded')).toBe('false');
    click(container.querySelector('.pm-open'));
    expect(arrow.getAttribute('aria-expanded')).toBe('true');
    expect(container.querySelector(`#${arrow.getAttribute('aria-controls')}`)).not.toBeNull();
  });

  it('counts the parts by state and shows the earliest expiry', () => {
    const early = new Date(NOW + 2 * 86_400_000).toISOString();
    const jobs = [
      finished(1, { batchId: BATCH, part: 'S1' }),
      finished(2, { batchId: BATCH, part: 'S2', expires: early }),
      jobEntry(3, { batchId: BATCH, part: 'S3', status: status({ progress: 50 }) }),
      jobEntry(4, { batchId: BATCH, part: 'S4', phase: 'failed' }),
    ];
    withBatch(jobs, { refused: [{ label: 'S5', message: 'no good' }] });
    mount();
    const row = rows()[0];
    expect(row.querySelector('.pm-state')?.textContent).toBe('2 done · 1 running · 1 refused · 1 failed');
    expect(row.querySelector('.pm-until')?.getAttribute('title')).toBe(early);
    // 100 + 100 + 50 + 100 + 100 (refused) over five parts
    expect(row.querySelector('.pm-line + progress')?.getAttribute('value')).toBe('90');
  });

  it('shows no progress bar once nothing runs any more', () => {
    withBatch([finished(1, { batchId: BATCH, part: 'S1' })]);
    mount();
    expect(rows()[0].querySelector('.pm-line + progress')).toBeNull();
  });

  it('lists a part the server refused, without a job, with the reason as its tooltip', () => {
    withBatch(parts(1), { refused: [{ label: 'S2', message: 'no good' }] });
    mount();
    click(button('▸'));
    const refused = container.querySelector('.pm-row.refused')!;
    expect(refused.querySelector('.pm-title')?.textContent).toBe('S2');
    expect(refused.querySelector('.pm-state')?.textContent).toBe('Refused');
    // The reason is a symbol that the keyboard reaches, not a title on text.
    expect(refused.querySelector('.tip')?.getAttribute('data-tip')).toBe('no good');
    expect(refused.querySelector('[title], [aria-label]:not(.tip)')).toBeNull();
    expect(refused.querySelector('a, [role="menu"], button[aria-haspopup]')).toBeNull();
  });

  it('gives a part its download and a menu with nothing but "Cancel" while it runs', () => {
    withBatch([finished(1, { batchId: BATCH, part: 'S1' }), jobEntry(2, { batchId: BATCH, part: 'S2' })]);
    mount();
    click(button('▸'));
    const [done, running] = [...container.querySelectorAll<HTMLElement>('.pm-parts .pm-row')];
    expect(done.querySelector('a[aria-label="Download (ZIP)"]')).not.toBeNull();
    expect(done.querySelector('button[aria-haspopup]')).toBeNull();
    menuOf(running);
    expect([...document.querySelectorAll('[role="menu"] button')].map((b) => b.textContent)).toEqual(['Cancel']);
  });

  it('has no "Download all (ZIP)" yet: that is UI-01f', () => {
    withBatch();
    mount();
    expect(container.textContent).not.toContain('Download all');
  });

  it('is renamed as a whole, and the parts that carried the title follow, one named by hand does not', () => {
    const jobs = parts(3);
    jobs[1] = { ...jobs[1], title: 'By hand' };
    withBatch(jobs);
    mount();
    menuOf(rows()[0]);
    click(item('Rename (R)'));
    type(field(), 'Field 7');
    key(field(), 'Enter');
    expect(titles()).toEqual(['Field 7']);
    expect(useProcessingStore.getState().jobs.map((j) => j.title)).toEqual(['Field 7', 'By hand', 'Field 7']);
    expect(stored().batches[0].title).toBe('Field 7');
  });

  it('is archived with all its parts and comes back with them', () => {
    withBatch();
    mount();
    menuOf(rows()[0]);
    click(item('Archive (A)'));
    expect(rows()).toHaveLength(0);
    expect(useProcessingStore.getState().jobs.every((j) => j.archived)).toBe(true);
    expect(stored().batches[0].archived).toBe(true);
    click(button('All'));
    menuOf(rows()[0]);
    click(item('Unarchive (A)'));
    expect(useProcessingStore.getState().jobs.some((j) => j.archived)).toBe(false);
  });

  it('moves with all its parts into a group', () => {
    put({ jobs: parts(2), batches: [batchEntry(BATCH)], groups: [{ id: GROUP, name: 'Field 7' }] });
    mount();
    menuOf(rows()[0]);
    click(item('Move to group… (G)'));
    click(item('Field 7'));
    expect(container.querySelectorAll('.pm-group[aria-label="Field 7"] .pm-rows > .pm-row')).toHaveLength(1);
    expect(useProcessingStore.getState().jobs.map((j) => j.groupId)).toEqual([GROUP, GROUP]);
  });

  describe('"Cancel all"', () => {
    let deleted: string[];
    beforeEach(() => {
      deleted = [];
      for (let n = 1; n <= 3; n += 1) {
        routes[`GET /processing/jobs/${jobId(n)}`] = () => json(doc(jobId(n), 'running', 20));
        routes[`DELETE /processing/jobs/${jobId(n)}`] = () => {
          deleted.push(jobId(n));
          return json(doc(jobId(n), 'dismissed'));
        };
      }
    });

    it('cancels the waiting and running parts, one after the other, and leaves the finished one', async () => {
      withBatch([finished(1, { batchId: BATCH, part: 'S1' }), jobEntry(2, { batchId: BATCH, part: 'S2' }), jobEntry(3, { batchId: BATCH, part: 'S3' })]);
      mount();
      menuOf(rows()[0]);
      await act(async () => {
        item('Cancel all').click();
      });
      await act(async () => {
        await vi.waitFor(() => expect(deleted).toEqual([jobId(2), jobId(3)]));
      });
      expect(useProcessingStore.getState().jobs.map((j) => j.phase)).toEqual(['successful', 'dismissed', 'dismissed']);
      expect(rows()[0].querySelector('.pm-state')?.textContent).toBe('1 done · 2 cancelled');
    });

    it('is offered only while a part runs', () => {
      withBatch([finished(1, { batchId: BATCH, part: 'S1' })]);
      mount();
      menuOf(rows()[0]);
      expect([...document.querySelectorAll('[role="menu"] button')].map((b) => b.textContent)).not.toContain('Cancel all');
    });

    it('does not start a second round for a second click', async () => {
      withBatch([jobEntry(2, { batchId: BATCH, part: 'S2' }), jobEntry(3, { batchId: BATCH, part: 'S3' })].map((j) => ({ ...j })));
      mount();
      await act(async () => {
        void useProcessingStore.getState().cancelBatch(BATCH);
        void useProcessingStore.getState().cancelBatch(BATCH);
        await vi.waitFor(() => expect(deleted).toHaveLength(2));
      });
      expect(deleted).toEqual([jobId(2), jobId(3)]);
    });

    it('asks again for the state of a part before it cancels, as "Cancel" does: a part that ended meanwhile is left', async () => {
      routes[`GET /processing/jobs/${jobId(3)}`] = () => json(doc(jobId(3), 'successful', 100));
      withBatch([jobEntry(2, { batchId: BATCH, part: 'S2' }), jobEntry(3, { batchId: BATCH, part: 'S3' })]);
      mount();
      await act(async () => {
        await useProcessingStore.getState().cancelBatch(BATCH);
      });
      expect(deleted).toEqual([jobId(2)]);
    });
  });
});

describe('what the browser kept', () => {
  it('says nothing where all is kept', () => {
    put({ jobs: [jobEntry(1)], shelf: 'ok' });
    mount();
    expect(container.querySelector('.tip.warn')).toBeNull();
    expect(container.querySelector('.pm-note')).toBeNull();
  });

  it('always tells in a tooltip that the jobs are kept in this browser only', () => {
    mount();
    const tip = container.querySelector('.pm-head .tip')!;
    expect(tip.getAttribute('data-tip')).toBe("Jobs are kept in this browser only: a private window or clearing the browser's data loses them.");
    expect(tip.getAttribute('aria-label')).toBe(tip.getAttribute('data-tip'));
    expect(tip.getAttribute('tabindex')).toBe('0');
  });

  it('says in a tooltip that copies of the oldest orders were dropped where the browser is full', () => {
    put({ jobs: [jobEntry(1)], shelf: 'trimmed' });
    mount();
    expect(container.querySelector('.pm-head .tip.warn')?.getAttribute('data-tip')).toBe(STORAGE_FULL_TIP);
    expect(container.querySelector('.pm-note')).toBeNull();
  });

  it('says in plain words that nothing is kept where the browser keeps nothing', () => {
    put({ jobs: [jobEntry(1)], shelf: 'memory' });
    mount();
    expect(container.querySelector('.pm-note')?.textContent).toBe(NOT_KEPT_TEXT);
    expect(container.querySelector('.pm-note')?.getAttribute('role')).toBe('status');
  });

  it('shows the state of the shelf after a write the browser refused', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError');
    });
    put({ jobs: [jobEntry(1)] });
    act(() => useProcessingStore.getState().renameJob(jobId(1), 'New'));
    mount();
    expect(container.querySelector('.pm-note')?.textContent).toBe(NOT_KEPT_TEXT);
    // The job and its new title stay for this page.
    expect(titles()).toEqual(['New']);
    vi.restoreAllMocks();
  });

  it('shows the jobs a reload finds in the browser, and follows the ones that still run', () => {
    localStorage.setItem(
      SHELF_KEY,
      JSON.stringify({
        v: 1,
        jobs: [
          { jobID: jobId(1), expires: new Date(NOW + 86_400_000).toISOString(), createdAt: new Date(NOW - 1000).toISOString(), title: 'Kept' },
          { jobID: jobId(2), expires: new Date(NOW - 1000).toISOString(), createdAt: new Date(NOW - 2000).toISOString(), title: 'Old', archived: true },
        ],
        batches: [],
        groups: [],
      }),
    );
    const fetched: string[] = [];
    setTrackerOptions({ EventSource: null, fetchJob: async (id) => (fetched.push(id), status({ jobID: id, progress: 33 })), pollMs: 60_000 });
    mount();
    act(() => useProcessingStore.getState().resumeJobs());
    expect(titles()).toEqual(['Kept']);
    // The expired one is past its time, not asked after; the archived one is out of "Active".
    expect(fetched).toEqual([jobId(1)]);
    click(button('All'));
    expect(titles()).toEqual(['Kept', 'Old']);
    expect(rows()[1].querySelector('.pm-state')?.textContent).toBe('Expired');
  });

  it('works with a shelf of a version it does not know: shows what this page holds and writes nothing', () => {
    localStorage.setItem(SHELF_KEY, JSON.stringify({ v: 2, jobs: [] }));
    mount();
    act(() => useProcessingStore.getState().resumeJobs());
    expect(container.querySelector('.pm-note')?.textContent).toBe(NOT_KEPT_TEXT);
    put({ jobs: [jobEntry(1)] });
    act(() => useProcessingStore.getState().renameJob(jobId(1), 'New'));
    expect(JSON.parse(localStorage.getItem(SHELF_KEY)!)).toEqual({ v: 2, jobs: [] });
  });

  it('reads a damaged value as an empty shelf and does not fail', () => {
    localStorage.setItem(SHELF_KEY, '{not json');
    mount();
    act(() => useProcessingStore.getState().resumeJobs());
    expect(container.querySelector('.pm-empty')?.textContent).toBe('No jobs yet.');
  });

  it('works where the browser blocks its storage', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    mount();
    act(() => useProcessingStore.getState().resumeJobs());
    expect(container.querySelector('.pm-note')?.textContent).toBe(NOT_KEPT_TEXT);
    vi.restoreAllMocks();
  });
});

describe('another tab', () => {
  it('shows a job the other tab placed, once the browser says so, and follows it from its row', () => {
    act(() => useProcessingStore.getState().resumeJobs());
    const fetched: string[] = [];
    setTrackerOptions({ EventSource: null, fetchJob: async (id) => (fetched.push(id), status({ jobID: id })), pollMs: 60_000 });
    mount();
    expect(rows()).toHaveLength(0);
    const value = JSON.stringify({
      v: 1,
      jobs: [{ jobID: jobId(7), expires: new Date(NOW + 86_400_000).toISOString(), createdAt: new Date(NOW).toISOString(), title: 'From the other tab' }],
      batches: [],
      groups: [],
    });
    localStorage.setItem(SHELF_KEY, value);
    act(() => {
      window.dispatchEvent(new StorageEvent('storage', { key: SHELF_KEY, newValue: value }));
    });
    expect(titles()).toEqual(['From the other tab']);
    expect(fetched).toEqual([jobId(7)]);
  });

  it('takes its rename, its archive and its removal of a group', () => {
    put({ jobs: [jobEntry(1), jobEntry(2)], groups: [{ id: GROUP, name: 'Field 7' }, { id: OTHER_GROUP, name: 'Other' }] });
    act(() => useProcessingStore.getState().resumeJobs());
    act(() => useProcessingStore.getState().renameJob(jobId(1), 'Mine'));
    mount();
    const other = JSON.parse(localStorage.getItem(SHELF_KEY)!);
    other.jobs.find((j: { jobID: string }) => j.jobID === jobId(1)).title = 'Renamed there';
    other.jobs.find((j: { jobID: string }) => j.jobID === jobId(2)).archived = true;
    other.groups = other.groups.filter((g: { id: string }) => g.id !== OTHER_GROUP);
    const value = JSON.stringify(other);
    localStorage.setItem(SHELF_KEY, value);
    act(() => {
      window.dispatchEvent(new StorageEvent('storage', { key: SHELF_KEY, newValue: value }));
    });
    expect(titles()).toEqual(['Renamed there']);
    expect(useProcessingStore.getState().groups.map((g) => g.name)).toEqual(['Field 7']);
  });

  it('keeps the groups of this tab where the browser holds no readable shelf for them', () => {
    put({ jobs: [jobEntry(1, { groupId: GROUP })], groups: [{ id: GROUP, name: 'Field 7' }] });
    act(() => useProcessingStore.getState().resumeJobs());
    mount();
    localStorage.setItem(SHELF_KEY, '{damaged');
    act(() => {
      window.dispatchEvent(new StorageEvent('storage', { key: SHELF_KEY, newValue: '{damaged' }));
    });
    expect(useProcessingStore.getState().groups.map((g) => g.name)).toEqual(['Field 7']);
    expect(container.querySelector('.pm-group[aria-label="Field 7"] .pm-row')).not.toBeNull();
  });

  it('does not take it as news when the other tab clears the browser data', () => {
    put({ jobs: [jobEntry(1)] });
    mount();
    act(() => {
      window.dispatchEvent(new StorageEvent('storage', { key: SHELF_KEY, newValue: null }));
    });
    expect(titles()).toHaveLength(1);
  });
});

describe('a job the server no longer has', () => {
  it('shows "Expired" once the server answers 404 for it, keeps it in the list and in the browser', async () => {
    setTrackerOptions({
      EventSource: null,
      fetchJob: async () => {
        throw new HttpError(404, 'there is no such job', 'there is no such job');
      },
      pollMs: 60_000,
    });
    put({ jobs: [jobEntry(1, { status: null })] });
    act(() => useProcessingStore.getState().renameJob(jobId(1), 'Kept'));
    mount();
    click(button('Expired'));
    await vi.waitFor(() => expect(rows()[0].querySelector('.pm-state')?.textContent).toBe('Expired'));
    expect(titles()).toEqual(['Kept']);
    expect(stored().jobs[0].jobID).toBe(jobId(1));
  });
});
