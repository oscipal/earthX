// @vitest-environment jsdom
//
// The details of a job in the processing window (UI-01 §6.8): title, state, expiry, the steps of the
// order, the failure, and one action per state.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { finished, jobEntry, jobId, NOW, status } from '../fixtures/jobEntries';
import type { Order } from '../processing';
import { resetJobs, setTrackerOptions, useProcessingStore, type JobEntry } from '../processingStore';
import { MIN_REMAINING_MS } from '../resultLayer';
import { useAppStore } from '../store';
import JobDetails, { NO_COPY_TIP } from './JobDetails';
import ProcessingPanel from './ProcessingPanel';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

// A polygon with coordinates that must not show up on screen.
const ORDER: Order = {
  recipe_version: 1,
  inputs: [{ name: 'a', dataset: 'sentinel-2-c1-l2a', groups: [['S1', 'S2']], assets: ['red', 'nir'] }],
  aoi: { type: 'Polygon', coordinates: [[[10.4123, 50.4123], [10.6, 50.4123], [10.6, 50.6], [10.4123, 50.4123]]] },
  steps: [
    { op: 'band_math', op_version: 1, params: { expression: '(nir - red) / (nir + red)', output: 'ndvi', nodata: 0 } },
    { op: 'reproject', op_version: 1, params: { crs: 'EPSG:3035', geometry: { type: 'Point', coordinates: [1.23456, 2.34567] }, bands: ['a', 'b'] } },
  ],
  output: { kind: 'raster', format: 'cog', dtype: 'float32' },
};

// The actions a test replaces by a spy, put back after it.
const { cancelJob, ensureDescription, restoreOrder, showResultOnMap } = useProcessingStore.getState();

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers({ toFake: ['Date'], now: NOW });
  localStorage.clear();
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 404 })));
  setTrackerOptions({ EventSource: null, fetchJob: async (id) => status({ jobID: id }), pollMs: 60_000 });
  resetJobs();
  useProcessingStore.setState({ open: false, cancelJob, ensureDescription, restoreOrder, showResultOnMap });
  useAppStore.setState({ datasetId: null, datasets: [], viewportBbox: [5, 45, 15, 55], mapZoom: 6 });
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

function show(job: JobEntry, element = <JobDetails />) {
  act(() => useProcessingStore.setState({ open: true, jobs: [job], detailJobID: job.jobID }));
  act(() => root.render(element));
}
const click = (el: Element | null | undefined) => {
  if (!el) throw new Error(`nothing to click in ${container.textContent}`);
  act(() => el.dispatchEvent(new MouseEvent('click', { bubbles: true })));
};
const button = (label: string | RegExp) =>
  [...container.querySelectorAll('button')].find((b) => (typeof label === 'string' ? b.textContent?.trim() === label : label.test(b.textContent ?? ''))) as HTMLButtonElement | undefined;
const actions = () => [...container.querySelectorAll('.vc-actions > *')].map((el) => el.textContent?.trim());
const fact = (name: string) => {
  const dt = [...container.querySelectorAll('.pm-facts dt')].find((d) => d.textContent === name);
  return dt?.nextElementSibling?.textContent ?? null;
};
const type = (input: HTMLInputElement, value: string) => {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!;
  act(() => {
    setter.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
};
const key = (target: Element, name: string) => act(() => target.dispatchEvent(new KeyboardEvent('keydown', { key: name, bubbles: true, cancelable: true })));

describe('the window', () => {
  it('takes the place of the order in the processing window, and "‹ Order" brings the order back, unchanged', () => {
    act(() => useProcessingStore.setState({ steps: [{ key: 1, op: 'band_math', opVersion: 1, values: { expression: 'a' } }] }));
    show(jobEntry(1), <ProcessingPanel />);
    expect(container.querySelector('[aria-label="Job"]')).not.toBeNull();
    expect(container.querySelector('[aria-label="Processing"]')).toBeNull();
    click(button('‹ Order'));
    expect(useProcessingStore.getState().detailJobID).toBeNull();
    expect(container.querySelector('[aria-label="Processing"]')).not.toBeNull();
    expect(useProcessingStore.getState().steps).toHaveLength(1);
  });

  it('folds down to its head and opens again, as the order does (narrow screens)', () => {
    show(jobEntry(1));
    const panel = container.querySelector('.processing-panel')!;
    click(button('▾'));
    expect(panel.classList.contains('folded')).toBe(true);
    click(button('▴'));
    expect(panel.classList.contains('folded')).toBe(false);
  });

  it('reads the operators of the dataset when it opens over a closed panel, as the order does', () => {
    const ensure = vi.fn();
    act(() => useAppStore.setState({ datasetId: 'sentinel-2-c1-l2a' }));
    act(() => useProcessingStore.setState({ open: false, jobs: [jobEntry(1)], ensureDescription: ensure }));
    act(() => useProcessingStore.getState().openJobDetails(jobId(1)));
    expect(ensure).toHaveBeenCalledWith('sentinel-2-c1-l2a');
  });

  it('closes the whole window with the cross', () => {
    show(jobEntry(1));
    click(button('✕'));
    expect(useProcessingStore.getState()).toMatchObject({ open: false, detailJobID: null });
  });

  it('is opened by `openJobDetails` for a job of the list only', () => {
    act(() => useProcessingStore.setState({ jobs: [jobEntry(1)], open: false }));
    act(() => useProcessingStore.getState().openJobDetails(jobId(9)));
    expect(useProcessingStore.getState()).toMatchObject({ open: false, detailJobID: null });
    act(() => useProcessingStore.getState().openJobDetails(jobId(1)));
    expect(useProcessingStore.getState()).toMatchObject({ open: true, detailJobID: jobId(1) });
  });

  it('is left when the order is opened again from the selection', () => {
    act(() => useProcessingStore.setState({ jobs: [jobEntry(1)] }));
    act(() => useProcessingStore.getState().openJobDetails(jobId(1)));
    act(() => useProcessingStore.getState().openProcessing());
    expect(useProcessingStore.getState().detailJobID).toBeNull();
  });

  it('says so where the job is not in the list any more', () => {
    show(jobEntry(1));
    act(() => useProcessingStore.setState({ jobs: [] }));
    expect(container.textContent).toContain('This job is not in the list.');
  });
});

describe('what it says of the job', () => {
  it('names the title, the state and, for a running job, the progress and when it expires', () => {
    show(jobEntry(1, { status: status({ progress: 65 }) }));
    expect(container.querySelector('.pm-title-text')?.textContent).toBe('Band math · Sentinel-2 L2A · 1 Oct');
    expect(fact('State')).toBe('Running · 65%');
    expect(fact('Expires')).toMatch(/^27 Oct, \d{2}:\d{2}$/u);
    expect(container.querySelector('progress')?.getAttribute('value')).toBe('65');
  });

  it.each([
    ['finished', () => finished(1), 'Finished'],
    ['failed', () => jobEntry(1, { phase: 'failed', failure: 'x' }), 'Failed'],
    ['cancelled', () => jobEntry(1, { phase: 'dismissed' }), 'Cancelled'],
    ['expired', () => jobEntry(1, { phase: 'gone' }), 'Expired'],
  ])('names a %s job', (_, make, text) => {
    show(make());
    expect(fact('State')).toBe(text);
    expect(container.querySelector('progress')).toBeNull();
  });

  it('gives no expiry for a cancelled job, and keeps the date of an expired one', () => {
    show(jobEntry(1, { phase: 'dismissed' }));
    expect(fact('Expires')).toBeNull();
    show(jobEntry(1, { phase: 'gone' }));
    expect(fact('Expires')).toMatch(/^27 Oct, \d{2}:\d{2}$/u);
  });

  it('shows the reason of a failed job, and an error of its own, as alerts', () => {
    show(jobEntry(1, { phase: 'failed', failure: 'The source failed', error: 'The result could not be shown on the map.' }));
    expect([...container.querySelectorAll('[role="alert"]')].map((a) => a.textContent)).toEqual(['The source failed', 'The result could not be shown on the map.']);
  });

  it('marks a finished result that was resampled, as a symbol with the text as its tooltip', () => {
    show(finished(1, { resampled: true }));
    expect(container.querySelector('.tip.warn')?.getAttribute('data-tip')).toBe('Resampled to a common grid');
    show(finished(1, { resampled: false }));
    expect(container.querySelector('.tip')).toBeNull();
  });

  it('turns "Expired" at the minute the links stop, with the clock running', () => {
    vi.useFakeTimers({ now: NOW });
    show(finished(1, { expires: new Date(NOW + MIN_REMAINING_MS + 2000).toISOString() }));
    expect(fact('State')).toBe('Finished');
    act(() => {
      vi.advanceTimersByTime(2100);
    });
    expect(fact('State')).toBe('Expired');
    expect(container.querySelector('a')).toBeNull();
  });

  it('names a part of a batch with its batch and its label', () => {
    const batch = 'b'.repeat(32);
    act(() => useProcessingStore.setState({ batches: [{ id: batch, title: 'Field 7', titleDefault: 'Field 7', createdAt: new Date(NOW).toISOString(), archived: false, groupId: null, refused: [] }] }));
    show(jobEntry(1, { batchId: batch, part: 'S2' }));
    expect(container.querySelector('.pm-detail-title .pp-help')?.textContent).toBe('Field 7 · S2');
  });
});

describe('the title', () => {
  it('is renamed in place, and an empty name brings the default back', () => {
    show(jobEntry(1, { title: 'Mine', titleDefault: 'Band math · Sentinel-2 L2A · 1 Oct' }));
    click(container.querySelector('button[aria-label="Rename this job"]'));
    type(container.querySelector('input.pm-rename')!, 'Field 7');
    key(container.querySelector('input.pm-rename')!, 'Enter');
    expect(container.querySelector('.pm-title-text')?.textContent).toBe('Field 7');
    click(container.querySelector('button[aria-label="Rename this job"]'));
    type(container.querySelector('input.pm-rename')!, '');
    key(container.querySelector('input.pm-rename')!, 'Enter');
    expect(container.querySelector('.pm-title-text')?.textContent).toBe('Band math · Sentinel-2 L2A · 1 Oct');
  });

  it('keeps the old title when the edit is dropped', () => {
    show(jobEntry(1, { title: 'Mine' }));
    click(container.querySelector('button[aria-label="Rename this job"]'));
    type(container.querySelector('input.pm-rename')!, 'Other');
    key(container.querySelector('input.pm-rename')!, 'Escape');
    expect(container.querySelector('.pm-title-text')?.textContent).toBe('Mine');
  });
});

describe('the steps', () => {
  it('come from the copy of the order: the operator and its values', () => {
    show(jobEntry(1, { order: ORDER }));
    const lines = [...container.querySelectorAll('.pm-step')].map((l) => [l.querySelector('strong')?.textContent, l.querySelector('.pm-step-values')?.textContent]);
    expect(lines).toEqual([
      ['Band math', 'expression: (nir - red) / (nir + red) · output: ndvi · nodata: 0'],
      ['Reproject', 'crs: EPSG:3035 · bands: a, b'],
    ]);
    expect(container.querySelector('.pp-summary')?.textContent).toBe('sentinel-2-c1-l2a · 2 scenes · AOI only');
  });

  it('never show the coordinates of the area, in a step or elsewhere', () => {
    show(jobEntry(1, { order: ORDER }));
    for (const part of ['10.4123', '50.4123', '1.23456', 'Polygon', 'coordinates']) expect(container.textContent).not.toContain(part);
  });

  it('say "Whole scenes" for an order without an area, and name the dataset by its title where it is known', () => {
    const { aoi: _aoi, ...whole } = ORDER;
    useAppStore.setState({ datasets: [{ id: 'sentinel-2-c1-l2a', title: 'Sentinel-2 L2A' } as never] });
    show(jobEntry(1, { order: whole as Order }));
    expect(container.querySelector('.pp-summary')?.textContent).toBe('Sentinel-2 L2A · 2 scenes · Whole scenes');
  });

  it('cut a long value and leave out what is not plain text', () => {
    const long: Order = { ...ORDER, steps: [{ op: 'band_math', op_version: 1, params: { expression: 'x'.repeat(300), nested: { a: 1 }, mixed: [1, { b: 2 }] } }] };
    show(jobEntry(1, { order: long }));
    const values = container.querySelector('.pm-step-values')!.textContent!;
    expect(values).toBe(`expression: ${'x'.repeat(120)}…`);
  });

  it('are not shown where the copy of the order is gone', () => {
    show(jobEntry(1, { order: null }));
    expect(container.querySelector('.pm-steps')).toBeNull();
  });
});

describe('the actions', () => {
  it('of a finished job are "Download (ZIP)" and "Show on map", and no other file, no "Methods", no "Copy"', () => {
    show(finished(1, { tiles: { href: '/results/x/WebMercatorQuad/tilejson.json', width: 10, gsd: 10 }, order: ORDER }));
    expect(actions()).toEqual(['Download (ZIP)', 'Show on map']);
    const link = container.querySelector<HTMLAnchorElement>('.vc-actions a')!;
    expect(link.getAttribute('href')).toBe(`/processing/jobs/${jobId(1)}/results/result.zip`);
    expect(link.hasAttribute('download')).toBe(true);
    for (const word of ['Methods', 'Copy', 'Remove', 'Delete', 'Open in panel']) expect(container.textContent).not.toContain(word);
  });

  it('of a finished job without tiles (an export) is "Download (ZIP)"', () => {
    show(finished(1, { archive: 'export.zip' }));
    expect(actions()).toEqual(['Download (ZIP)']);
    expect(container.querySelector('a')?.getAttribute('href')).toBe(`/processing/jobs/${jobId(1)}/results/export.zip`);
  });

  it('of a finished job whose results are not read yet are none: there is no file to take', () => {
    show(finished(1, { archive: null }));
    expect(actions()).toEqual([]);
  });

  it('of a running job is "Cancel", off until its state is known, and "Cancelling…" while it goes', () => {
    show(jobEntry(1));
    expect(actions()).toEqual(['Cancel']);
    expect(button('Cancel')!.disabled).toBe(false);
    show(jobEntry(1, { status: null }));
    expect(button('Cancel')!.disabled).toBe(true);
    show(jobEntry(1, { cancelling: true }));
    expect(button('Cancelling…')!.disabled).toBe(true);
  });

  it('sends one DELETE for a double click on "Cancel", and shows the job as cancelled', async () => {
    const calls: string[] = [];
    const running = { processID: 'recipe', type: 'process', jobID: jobId(1), status: 'running', message: '', progress: 5, created: '2026-10-10T10:00:00Z', expires: new Date(NOW + 86_400_000).toISOString(), recipeID: 'r', links: [] };
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? 'GET'} ${url}`);
      const state = init?.method === 'DELETE' ? 'dismissed' : 'running';
      return new Response(JSON.stringify({ ...running, status: state }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));
    show(jobEntry(1));
    await act(async () => {
      button('Cancel')!.click();
      button('Cancel')?.click();
    });
    await vi.waitFor(() => expect(useProcessingStore.getState().jobs[0].phase).toBe('dismissed'));
    expect(calls.filter((c) => c.startsWith('DELETE'))).toEqual([`DELETE /processing/jobs/${jobId(1)}`]);
    expect(fact('State')).toBe('Cancelled');
  });

  it('of a failed or cancelled job are none', () => {
    show(jobEntry(1, { phase: 'failed', failure: 'x', order: ORDER }));
    expect(actions()).toEqual([]);
    show(jobEntry(1, { phase: 'dismissed', order: ORDER }));
    expect(actions()).toEqual([]);
  });

  it('of an expired job is "Open in panel", and nothing to download', () => {
    show(jobEntry(1, { phase: 'gone', order: ORDER }));
    expect(actions()).toEqual(['Open in panel']);
    expect(button('Open in panel')!.getAttribute('aria-disabled')).toBe('false');
    show(finished(1, { expired: true, order: ORDER }));
    expect(actions()).toEqual(['Open in panel']);
  });

  it('draws the result on the map from "Show on map"', () => {
    const showOnMap = vi.fn(async () => undefined);
    act(() => useProcessingStore.setState({ showResultOnMap: showOnMap }));
    show(finished(1, { tiles: { href: '/results/x/WebMercatorQuad/tilejson.json', width: 10, gsd: 10 } }));
    click(button('Show on map'));
    expect(showOnMap).toHaveBeenCalledWith(jobId(1));
  });
});

describe('"Open in panel"', () => {
  const gone = () => jobEntry(1, { phase: 'gone', order: ORDER, range: { vmin: '0', vmax: '1', colormap: 'viridis' } });

  it('takes the order back into the panel, with the map as it is and the range the job had', async () => {
    const restore = vi.fn(async () => ({ ok: true as const, notes: [] }));
    act(() => useProcessingStore.setState({ restoreOrder: restore }));
    show(gone());
    await act(async () => {
      button('Open in panel')!.click();
    });
    expect(restore).toHaveBeenCalledTimes(1);
    const [order, view] = restore.mock.calls[0] as unknown as [Order, { center: number[]; zoom: number; range: unknown }];
    expect(order).toEqual(ORDER);
    expect(view).toEqual({ center: [10, 50], zoom: 6, range: { vmin: 0, vmax: 1, colormap: 'viridis' } });
  });

  it('says why where the order cannot be taken back, and stays in the details', async () => {
    const restore = vi.fn(async () => ({ ok: false as const, reason: 'The scenes could not be loaded.' }));
    act(() => useProcessingStore.setState({ restoreOrder: restore }));
    show(gone());
    await act(async () => {
      button('Open in panel')!.click();
    });
    expect(container.querySelector('[role="alert"]')?.textContent).toBe('The scenes could not be loaded.');
    expect(useProcessingStore.getState().detailJobID).toBe(jobId(1));
  });

  it('is off where no copy of the order is kept, and the reason is its tooltip', () => {
    show(jobEntry(1, { phase: 'gone', order: null }));
    const off = button('Open in panel')!;
    // Off but reachable by keyboard, with the reason as a tooltip that shows on focus.
    expect(off.getAttribute('aria-disabled')).toBe('true');
    expect(off.getAttribute('data-tip')).toBe(NO_COPY_TIP);
    expect(off.getAttribute('aria-label')).toBe(`Open in panel: ${NO_COPY_TIP}`);
  });

  it('does nothing for a click on it where there is no copy', () => {
    const restore = vi.fn(async () => ({ ok: true as const, notes: [] }));
    act(() => useProcessingStore.setState({ restoreOrder: restore }));
    show(jobEntry(1, { phase: 'gone', order: null }));
    click(button('Open in panel'));
    expect(restore).not.toHaveBeenCalled();
  });
});
