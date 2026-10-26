// @vitest-environment jsdom
//
// The result layer in the layer manager (UI-01 §6.11): "Download (ZIP)" in its row, and a click on it that
// opens how it is drawn — range, colormap, opacity — in place of the search results, with the default of the
// statistics and a range kept for the job. No backend: `fetch` answers the TileJSON of the tiler only.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from '../App';
import { finished, jobId } from '../fixtures/jobEntries';
import { loadShelf } from '../jobShelf';
import type { MapLayer } from '../layers';
import { resultUrl } from '../processing';
import { resetJobs, useProcessingStore, type JobEntry } from '../processingStore';
import { resultStats } from '../resultLayer';
import { useAppStore } from '../store';
import JobDetails from './JobDetails';
import LayerManager from './LayerManager';
import ResultControls from './ResultControls';

vi.mock('./MapView', () => ({ default: () => null }));

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const JOB = jobId(1);
const RESULT = 'ZyXwVuTsRqPoNmLkJiHg_-';
const HREF = `/results/${RESULT}/WebMercatorQuad/tilejson.json`;
const TILE_JSON = { bounds: [10, 50, 11, 51], minzoom: 0, maxzoom: 19, data_type: 'float32', tiles: ['http://tiler/x'] };
const DEM = { minimum: 100, maximum: 2400, mean: 900, count: 1000, valid_percent: 100, percentile_2: 180, percentile_98: 1900 };
// A result with a unit in its bands: it must show nowhere (Otto, 24.10.2026).
const DEM_STATS = resultStats({ bands: [{ name: 'data', unit: 'furlong', data_type: 'float32', statistics: DEM }] });

function entry(over: Partial<JobEntry> = {}): JobEntry {
  return finished(1, { tiles: { href: HREF, width: 1000, gsd: 10 }, statistics: DEM_STATS, ...over });
}

const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });

let container: HTMLDivElement;
let root: Root;
let tileJsonBody: object;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  tileJsonBody = TILE_JSON;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => (url === HREF ? json(tileJsonBody) : new Response('{}', { status: 404 }))));
  resetJobs();
  useProcessingStore.getState().resetDraft();
  useProcessingStore.setState({ open: false, detailJobID: null, jobs: [entry()] });
  useAppStore.setState({ layers: [], dock: 'layers', datasets: [], sections: [], resultViewLayerId: null, focusMode: false, notice: null });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  resetJobs();
  localStorage.clear();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const layers = () => useAppStore.getState().layers;
const urlOf = () => (layers()[0].overlays[0] as { tileUrl: string }).tileUrl;
const click = (el: Element | null | undefined) => {
  if (!el) throw new Error(`nothing to click in ${container.textContent}`);
  act(() => el.dispatchEvent(new MouseEvent('click', { bubbles: true })));
};
const button = (label: string) => [...container.querySelectorAll('button')].find((b) => b.textContent?.trim() === label);
const field = (label: string) =>
  [...container.querySelectorAll<HTMLElement>('.result-controls label')].find((l) => l.textContent?.startsWith(label))!.querySelector<HTMLInputElement | HTMLSelectElement>('input, select')!;

function type(input: HTMLInputElement | HTMLSelectElement, value: string) {
  const proto = input instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  act(() => {
    Object.getOwnPropertyDescriptor(proto, 'value')!.set!.call(input, value);
    input.dispatchEvent(new Event(input instanceof HTMLSelectElement ? 'change' : 'input', { bubbles: true }));
  });
}

async function flush() {
  await act(async () => {
    for (let i = 0; i < 5; i++) await Promise.resolve();
  });
}

async function showOnMap() {
  await useProcessingStore.getState().showResultOnMap(JOB);
  await flush();
}

// The layer of the result, its manager and its view side by side, as the page has them.
async function openView() {
  await showOnMap();
  act(() => root.render(<><LayerManager /><ResultControls /></>));
  click(container.querySelector('.layer-row .lm-name'));
}

describe('"Download (ZIP)" in the row of a result layer', () => {
  it('is the link of the details: the same archive of the same job', async () => {
    await showOnMap();
    act(() => root.render(<LayerManager />));
    const link = container.querySelector<HTMLAnchorElement>('.layer-row a[data-col="download"]')!;
    expect(link.getAttribute('href')).toBe(resultUrl(JOB, 'result.zip'));
    expect(link.hasAttribute('download')).toBe(true);
    expect(link.getAttribute('aria-label')).toBe('Download (ZIP)');

    useProcessingStore.setState({ open: true, detailJobID: JOB });
    act(() => root.render(<JobDetails />));
    const inDetails = [...container.querySelectorAll('a')].find((a) => a.textContent?.trim() === 'Download (ZIP)');
    expect(inDetails?.getAttribute('href')).toBe(link.getAttribute('href'));
  });

  // Otto, 26.10.2026: what cannot be done at all is not shown; the reason is the ⚠ of the row.
  it('is not shown once the results are gone: the place stays empty and the ⚠ says why', async () => {
    await showOnMap();
    act(() => useAppStore.getState().expireResultLayers(Date.parse(layers()[0].result!.expires) + 1));
    act(() => root.render(<LayerManager />));
    const row = container.querySelector('.layer-row')!;
    const empty = row.querySelector<HTMLElement>('[data-col="download"]')!;
    expect(empty.tagName).toBe('SPAN');
    expect(empty.getAttribute('aria-hidden')).toBe('true');
    expect(row.querySelector('a')).toBeNull();
    expect(row.querySelector('.lm-note .tip')?.getAttribute('data-tip')).toContain('Expired: results are kept for 7 days.');
    expect([...row.children].map((c) => c.getAttribute('data-col'))).toHaveLength(9);
  });

  it('is not made of a job id that is none', () => {
    const layer: MapLayer = {
      id: 'odd',
      name: 'Result · odd',
      visible: true,
      opacity: 1,
      derived: 'result',
      result: { jobID: '../../etc', expires: new Date(Date.now() + 86_400_000).toISOString(), gsd: null, resampled: null, expired: false, dataType: null, stats: null },
      overlays: [],
      restore: { datasetId: null, itemIds: [] } as never,
    };
    useAppStore.setState({ layers: [layer] });
    act(() => root.render(<LayerManager />));
    expect(container.querySelector('a')).toBeNull();
    expect(container.querySelector('.layer-row [data-col="download"]')?.getAttribute('aria-hidden')).toBe('true');
  });
});

describe('a click on a result layer', () => {
  it('opens how it is drawn, not the search results', async () => {
    useAppStore.setState({ selectedIds: ['scene'], focusMode: true, downloaded: { scene: {} as never } });
    await openView();
    expect(useAppStore.getState().resultViewLayerId).toBe(layers()[0].id);
    // The view of scenes is left; the selection of the search stays.
    expect(useAppStore.getState().focusMode).toBe(false);
    expect(useAppStore.getState().downloaded).toEqual({});
    expect(useAppStore.getState().selectedIds).toEqual(['scene']);
    expect(container.querySelector('.result-controls')).not.toBeNull();
    expect(container.querySelector('.vc-title')?.textContent).toBe('RESULT · BAND MATH');
    expect(layers().map((l) => l.id)).toEqual([layers()[0].id]);
  });

  it('shows the default of the statistics, with the fields of the full-resolution view', async () => {
    await openView();
    expect(field('Colormap').value).toBe('viridis');
    expect(field('vmin').value).toBe('180');
    expect(field('vmax').value).toBe('1900');
    expect(button('Apply')).toBeDefined();
    expect(button('auto')).toBeDefined();
  });

  it('shows no unit, in the row or in the view', async () => {
    await openView();
    expect(layers()[0].result).not.toHaveProperty('unit');
    expect(container.textContent).not.toMatch(/furlong|\bunit/iu);
    expect(container.innerHTML).not.toMatch(/furlong/u);
  });

  it('puts the search results back when the view is closed, the layer removed or a search made', async () => {
    await openView();
    click(button('‹ Close'));
    expect(useAppStore.getState().resultViewLayerId).toBeNull();
    expect(container.querySelector('.result-controls')).toBeNull();

    click(container.querySelector('.layer-row .lm-name'));
    expect(useAppStore.getState().resultViewLayerId).toBe(layers()[0].id);
    click(container.querySelector('button[title="Remove layer"]'));
    expect(useAppStore.getState().resultViewLayerId).toBeNull();

    await showOnMap();
    useAppStore.getState().selectLayer(layers()[0].id);
    expect(useAppStore.getState().resultViewLayerId).not.toBeNull();
    useAppStore.getState().exitFocus();
    expect(useAppStore.getState().resultViewLayerId).toBeNull();
  });

  it('is left for the view of scenes by a click on another layer', async () => {
    await showOnMap();
    const scene: MapLayer = {
      id: 'scene-layer',
      name: 'Optical · scene',
      visible: true,
      opacity: 1,
      overlays: [{ kind: 'raster', tileUrl: 'https://t/{z}/{x}/{y}', bounds: [0, 0, 1, 1], minZoom: 0, maxZoom: 12 }],
      restore: { focusMode: false, downloaded: {}, appliedRender: {}, activeGroupIndex: 0, selectedIds: [], itemIds: [], groupItemIds: [], aoi: null, cropToAoi: false, datasetId: null },
    };
    useAppStore.setState({ layers: [scene, ...layers()] });
    useAppStore.getState().selectLayer(layers()[1].id);
    expect(useAppStore.getState().resultViewLayerId).toBe(layers()[1].id);
    useAppStore.getState().selectLayer('scene-layer');
    expect(useAppStore.getState().resultViewLayerId).toBeNull();
    expect(useAppStore.getState().viewLayerId).toBe('scene-layer');
  });
});

describe('the range of a result layer', () => {
  it('"Apply" draws the result with what is typed and keeps it for the job', async () => {
    await openView();
    type(field('Colormap'), 'terrain');
    type(field('vmin'), '0');
    type(field('vmax'), '3000');
    // Typing alone changes nothing on the map.
    expect(urlOf()).toContain('colormap_name=viridis&rescale=180%2C1900');
    click(button('Apply'));
    expect(urlOf()).toContain('colormap_name=terrain&rescale=0%2C3000');
    expect(useProcessingStore.getState().jobs[0].range).toEqual({ vmin: '0', vmax: '3000', colormap: 'terrain' });
    // Kept in the browser, with the job.
    expect(loadShelf().shelf.jobs.find((j) => j.jobID === JOB)?.range).toEqual({ vmin: '0', vmax: '3000', colormap: 'terrain' });
    // The fields show what the layer draws now.
    expect(field('vmax').value).toBe('3000');
  });

  it('holds for every later layer of the same job', async () => {
    await openView();
    type(field('vmin'), '50');
    click(button('Apply'));
    click(container.querySelector('button[title="Remove layer"]'));
    expect(layers()).toEqual([]);
    await showOnMap();
    expect(urlOf()).toContain('colormap_name=viridis&rescale=50%2C1900');
  });

  it('"auto" goes back to the default of the statistics and forgets the range of the job', async () => {
    await openView();
    type(field('vmin'), '50');
    type(field('vmax'), '60');
    click(button('Apply'));
    expect(urlOf()).toContain('rescale=50%2C60');
    click(button('auto'));
    expect(urlOf()).toContain('colormap_name=viridis&rescale=180%2C1900');
    expect(useProcessingStore.getState().jobs[0].range).toBeNull();
    expect(loadShelf().shelf.jobs.find((j) => j.jobID === JOB)?.range ?? null).toBeNull();
    expect(field('vmin').value).toBe('180');
  });

  it('"auto" also drops what was typed and not applied', async () => {
    await openView();
    type(field('vmin'), '7');
    click(button('auto'));
    expect(field('vmin').value).toBe('180');
  });

  it.each([
    ['an empty end', '', '1900'],
    ['no number', 'abc', '1900'],
    ['a lower end above the upper', '2000', '1900'],
    ['both ends equal', '5', '5'],
  ])('refuses %s, says so and leaves the map and the job alone', async (_, vmin, vmax) => {
    await openView();
    const before = urlOf();
    type(field('vmin'), vmin);
    type(field('vmax'), vmax);
    click(button('Apply'));
    expect(urlOf()).toBe(before);
    expect(useProcessingStore.getState().jobs[0].range).toBeNull();
    expect(container.querySelector('[role="alert"]')?.textContent).toMatch(/range/u);
    // The message goes with the next edit.
    type(field('vmin'), '1');
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });

  it('is applied with no colormap when none is chosen', async () => {
    await openView();
    type(field('Colormap'), '');
    click(button('Apply'));
    expect(urlOf()).not.toContain('colormap_name');
    expect(urlOf()).toContain('rescale=180%2C1900');
  });

  it('keeps the opacity apart from "Apply": it follows the slider at once', async () => {
    await openView();
    type(field('Opacity'), '0.4');
    expect(layers()[0].opacity).toBeCloseTo(0.4);
    expect(urlOf()).toContain('rescale=180%2C1900');
  });

  it('changes nothing for a job the browser does not know any more', async () => {
    await openView();
    useProcessingStore.setState({ jobs: [] });
    type(field('vmin'), '1');
    click(button('Apply'));
    expect(urlOf()).toContain('rescale=1%2C1900');
    expect(useProcessingStore.getState().jobs).toEqual([]);
  });

  it('restyles only a result layer', () => {
    const scene: MapLayer = {
      id: 'scene-layer',
      name: 'Optical',
      visible: true,
      opacity: 1,
      overlays: [{ kind: 'raster', tileUrl: 'https://t/{z}?tilesize=256&rescale=0%2C1', bounds: [0, 0, 1, 1], minZoom: 0, maxZoom: 12 }],
      restore: { datasetId: null, itemIds: [] } as never,
    };
    useAppStore.setState({ layers: [scene] });
    useAppStore.getState().restyleResultLayer('scene-layer', { rescale: '5,6' });
    expect(useAppStore.getState().layers[0]).toBe(scene);
  });
});

describe('a result drawn as it is, or gone', () => {
  it('shows no range, colormap or "Apply" for whole numbers, and says why', async () => {
    tileJsonBody = { ...TILE_JSON, data_type: 'uint16' };
    await openView();
    expect(urlOf()).not.toContain('rescale');
    expect(container.querySelector('.vc-num')).toBeNull();
    expect(container.querySelector('select')).toBeNull();
    expect(button('Apply')).toBeUndefined();
    expect(button('auto')).toBeUndefined();
    expect(container.querySelector('.vc-head .tip')?.getAttribute('data-tip')).toMatch(/whole numbers/u);
    // The opacity stays, and the way out.
    expect(field('Opacity').disabled).toBe(false);
    expect(button('‹ Close')).toBeDefined();
  });

  it('shows no range, colormap or "Apply" once it expired', async () => {
    await openView();
    expect(button('Apply')).toBeDefined();
    act(() => useAppStore.getState().expireResultLayers(Date.parse(layers()[0].result!.expires) + 1));
    expect(container.querySelector('.vc-num')).toBeNull();
    expect(container.querySelector('select')).toBeNull();
    expect(button('Apply')).toBeUndefined();
    expect(button('auto')).toBeUndefined();
    expect(field('Opacity').disabled).toBe(false);
  });
});

describe('on the page', () => {
  it('takes the place of the bar of the view, and the results list gives way with a hint', async () => {
    const section = (datasetId: string) => ({ datasetId, items: [], groups: [], notes: [], groupingError: null, origin: 'search' as const, incomplete: false });
    useAppStore.setState({ sections: [section('one'), section('two')], dock: 'results' });
    await showOnMap();
    act(() => root.render(<App />));
    expect(container.querySelector('.results-list')).not.toBeNull();
    expect(container.querySelector('.result-controls')).toBeNull();
    act(() => useAppStore.getState().selectLayer(layers()[0].id));
    expect(container.querySelector('.results-list')).toBeNull();
    expect(container.querySelector('.results-view-hint')?.textContent).toBe('Close the view to browse the results.');
    expect(container.querySelector('.result-controls')).not.toBeNull();
    click(button('‹ Close'));
    expect(container.querySelector('.results-list')).not.toBeNull();
    expect(container.querySelector('.results-view-hint')).toBeNull();
    expect(container.querySelector('.result-controls')).toBeNull();
  });
});
