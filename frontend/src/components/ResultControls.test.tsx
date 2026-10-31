// @vitest-environment jsdom
//
// The result layer in the layer manager (UI-01 §6.11): "Download (ZIP)" in its row, and a click on it that
// opens how it is drawn — range, colormap, opacity — in place of the search results, with the default of the
// statistics and a range kept for the job. No backend: `fetch` answers the TileJSON of the tiler only.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from '../App';
import { finished, jobId, NOW } from '../fixtures/jobEntries';
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
  // The job of the fixture expires 7 days after `NOW`; "Show on map" refuses an expired job by the clock.
  vi.useFakeTimers({ toFake: ['Date'], now: NOW });
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
// The small red x of the settings (NM4-65 part 8), what "‹ Close" was.
const closeX = () => container.querySelector('.result-controls .close-x');
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
    expect(button('auto-scale')).toBeDefined();
  });

  it('shows no unit, in the row or in the view', async () => {
    await openView();
    expect(layers()[0].result).not.toHaveProperty('unit');
    expect(container.textContent).not.toMatch(/furlong|\bunit/iu);
    expect(container.innerHTML).not.toMatch(/furlong/u);
  });

  it('puts the search results back when the view is closed, the layer removed or a search made', async () => {
    await openView();
    click(closeX());
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
  const unsaved = () => layers()[0].result?.savedTileUrl;
  const keptRange = () => useProcessingStore.getState().jobs[0].range;

  it('"Apply" draws the result with what is typed, and keeps nothing: layer and job are as they were saved', async () => {
    await openView();
    type(field('Colormap'), 'terrain');
    type(field('vmin'), '0');
    type(field('vmax'), '3000');
    // Typing alone changes nothing on the map.
    expect(urlOf()).toContain('colormap_name=viridis&rescale=180%2C1900');
    click(button('Apply'));
    expect(urlOf()).toContain('colormap_name=terrain&rescale=0%2C3000');
    expect(unsaved()).toContain('colormap_name=viridis&rescale=180%2C1900');
    expect(keptRange()).toBeNull();
    expect(loadShelf().shelf.jobs.find((j) => j.jobID === JOB)?.range ?? null).toBeNull();
    // The fields show what the layer draws now.
    expect(field('vmax').value).toBe('3000');
  });

  it('"Save" keeps the applied look for the layer and for the job, also in the browser', async () => {
    await openView();
    type(field('Colormap'), 'terrain');
    type(field('vmin'), '0');
    type(field('vmax'), '3000');
    click(button('Apply'));
    click(button('Save'));
    expect(unsaved()).toBeUndefined();
    expect(urlOf()).toContain('colormap_name=terrain&rescale=0%2C3000');
    expect(keptRange()).toEqual({ vmin: '0', vmax: '3000', colormap: 'terrain' });
    expect(loadShelf().shelf.jobs.find((j) => j.jobID === JOB)?.range).toEqual({ vmin: '0', vmax: '3000', colormap: 'terrain' });
  });

  it('"Save" also draws what is typed and not applied yet, and keeps it', async () => {
    await openView();
    type(field('vmin'), '50');
    click(button('Save'));
    expect(urlOf()).toContain('rescale=50%2C1900');
    expect(unsaved()).toBeUndefined();
    expect(keptRange()).toEqual({ vmin: '50', vmax: '1900', colormap: 'viridis' });
  });

  it('holds for every later layer of the same job once it is saved', async () => {
    await openView();
    type(field('vmin'), '50');
    click(button('Apply'));
    click(button('Save'));
    click(container.querySelector('button[title="Remove layer"]'));
    expect(layers()).toEqual([]);
    await showOnMap();
    expect(urlOf()).toContain('colormap_name=viridis&rescale=50%2C1900');
  });

  it('is not held for a later layer when it was only applied', async () => {
    await openView();
    type(field('vmin'), '50');
    click(button('Apply'));
    click(container.querySelector('button[title="Remove layer"]'));
    await showOnMap();
    expect(urlOf()).toContain('rescale=180%2C1900');
  });

  it('"auto-scale" puts the default of the statistics in the fields and changes nothing else', async () => {
    await openView();
    type(field('vmin'), '50');
    type(field('vmax'), '60');
    click(button('Apply'));
    click(button('Save'));
    click(button('auto-scale'));
    expect(field('vmin').value).toBe('180');
    expect(field('vmax').value).toBe('1900');
    expect(urlOf()).toContain('rescale=50%2C60');
    expect(keptRange()).toEqual({ vmin: '50', vmax: '60', colormap: 'viridis' });
  });

  it('"auto-scale", applied and saved, goes back to the default and forgets the range of the job', async () => {
    await openView();
    type(field('vmin'), '50');
    type(field('vmax'), '60');
    click(button('Apply'));
    click(button('Save'));
    click(button('auto-scale'));
    click(button('Save'));
    expect(urlOf()).toContain('colormap_name=viridis&rescale=180%2C1900');
    expect(keptRange()).toBeNull();
    expect(loadShelf().shelf.jobs.find((j) => j.jobID === JOB)?.range ?? null).toBeNull();
    expect(unsaved()).toBeUndefined();
  });

  it('"auto-scale" also drops what was typed and not applied', async () => {
    await openView();
    type(field('vmin'), '7');
    click(button('auto-scale'));
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
    click(button('Save'));
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
    click(button('Save'));
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

// Otto, 29.10.2026 (zu #234): "Apply" and "Save" are locked while there is nothing to do, and say why; what was applied and
// not saved goes without asking when the settings are closed.
describe('"Apply" and "Save" of a result layer', () => {
  const disabled = (label: string) => button(label)?.getAttribute('aria-disabled') === 'true';

  it('stand under "auto-scale" and beside each other, in one cluster', async () => {
    await openView();
    const cluster = container.querySelector('.result-controls .vc-buttons')!;
    expect([...cluster.children].map((el) => el.textContent?.trim())).toEqual(['auto-scale', 'Apply', 'Save']);
  });

  it('have one format for "auto-scale" and "Apply", and only "Save" is blue', async () => {
    await openView();
    const [auto, apply, save] = [...container.querySelector('.result-controls .vc-buttons')!.children] as HTMLElement[];
    const format = (el: HTMLElement) => [...el.classList].filter((c) => !c.startsWith('vc-')).sort();
    expect(format(apply)).toEqual(format(auto));
    expect(format(apply)).toEqual(['ghost-btn']);
    expect(format(save)).toEqual(['primary-btn']);
  });

  it('are both locked while the fields hold what the layer draws and is saved with, with the reason as the tooltip', async () => {
    await openView();
    expect(disabled('Apply')).toBe(true);
    expect(disabled('Save')).toBe(true);
    expect(button('Apply')?.title).toBe('Nothing to apply: the map shows these values');
    expect(button('Save')?.title).toBe('Nothing to save: the layer is saved as it is drawn');
  });

  it('are both open once something is typed, and do nothing when they are locked and clicked', async () => {
    await openView();
    click(button('Apply'));
    click(button('Save'));
    expect(urlOf()).toContain('rescale=180%2C1900');
    type(field('vmax'), '2000');
    expect(disabled('Apply')).toBe(false);
    expect(disabled('Save')).toBe(false);
    expect(button('Apply')?.title).not.toMatch(/Nothing/u);
  });

  it('lock "Apply" after it was used, and keep "Save" open until the look is saved', async () => {
    await openView();
    type(field('vmax'), '2000');
    click(button('Apply'));
    expect(disabled('Apply')).toBe(true);
    expect(disabled('Save')).toBe(false);
    click(button('Save'));
    expect(disabled('Save')).toBe(true);
  });

  it('lock "Save" when what is typed is what the layer is saved with, though another look is applied', async () => {
    await openView();
    type(field('vmax'), '2000');
    click(button('Apply'));
    type(field('vmax'), '1900');
    expect(disabled('Save')).toBe(true);
    expect(disabled('Apply')).toBe(false);
    click(button('Apply'));
    expect(unsavedUrl()).toBeUndefined();
  });

  const unsavedUrl = () => layers()[0].result?.savedTileUrl;

  it.each([
    ['the close x is pressed', () => click(closeX())],
    ['the view of scenes is left', () => useAppStore.getState().exitFocus()],
    ['the layer is chosen away from', () => useAppStore.getState().selectLayer('other')],
  ])('lose what was applied and not saved, without asking, when %s', async (_when, close) => {
    const other: MapLayer = {
      id: 'other',
      name: 'Optical · scene',
      visible: true,
      opacity: 1,
      overlays: [{ kind: 'raster', tileUrl: 'https://t/{z}/{x}/{y}', bounds: [0, 0, 1, 1], minZoom: 0, maxZoom: 12 }],
      restore: { focusMode: false, downloaded: {}, appliedRender: {}, activeGroupIndex: 0, selectedIds: [], itemIds: [], groupItemIds: [], aoi: null, cropToAoi: false, datasetId: null },
    };
    await openView();
    useAppStore.setState({ layers: [...layers(), other] });
    const saved = urlOf();
    type(field('vmax'), '2000');
    click(button('Apply'));
    expect(urlOf()).not.toBe(saved);
    close();
    expect(urlOf()).toBe(saved);
    expect(layers()[0].result?.savedTileUrl).toBeUndefined();
    expect(useAppStore.getState().resultViewLayerId).toBeNull();
    // Opened again, the layer shows the saved look.
    click(container.querySelector('.layer-row .lm-name'));
    expect(field('vmax').value).toBe('1900');
  });

  it('keep what was saved when the settings are closed', async () => {
    await openView();
    type(field('vmax'), '2000');
    click(button('Apply'));
    click(button('Save'));
    click(closeX());
    expect(urlOf()).toContain('rescale=180%2C2000');
  });

  it('go back to the saved look, not to the first one, when something was saved and then applied again', async () => {
    await openView();
    type(field('vmax'), '2000');
    click(button('Apply'));
    click(button('Save'));
    type(field('vmax'), '2500');
    click(button('Apply'));
    click(closeX());
    expect(urlOf()).toContain('rescale=180%2C2000');
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
    expect(button('auto-scale')).toBeUndefined();
    expect(container.querySelector('.vc-head .tip')?.getAttribute('data-tip')).toMatch(/whole numbers/u);
    // The opacity stays, and the way out.
    expect(field('Opacity').disabled).toBe(false);
    expect(closeX()).not.toBeNull();
  });

  it('shows no range, colormap or "Apply" once it expired', async () => {
    await openView();
    expect(button('Apply')).toBeDefined();
    act(() => useAppStore.getState().expireResultLayers(Date.parse(layers()[0].result!.expires) + 1));
    expect(container.querySelector('.vc-num')).toBeNull();
    expect(container.querySelector('select')).toBeNull();
    expect(button('Apply')).toBeUndefined();
    expect(button('auto-scale')).toBeUndefined();
    expect(field('Opacity').disabled).toBe(false);
  });
});

describe('on the page', () => {
  it('takes the place of the bar of the view, and the results list stays (Otto, 26.10.2026)', async () => {
    const section = (datasetId: string) => ({ datasetId, items: [], groups: [], notes: [], groupingError: null, origin: 'search' as const, incomplete: false });
    useAppStore.setState({ sections: [section('one'), section('two')], dock: 'results' });
    await showOnMap();
    act(() => root.render(<App />));
    expect(container.querySelector('.results-list')).not.toBeNull();
    expect(container.querySelector('.result-controls')).toBeNull();
    act(() => useAppStore.getState().selectLayer(layers()[0].id));
    expect(container.querySelector('.results-list')).not.toBeNull();
    expect(container.querySelector('.result-controls')).not.toBeNull();
    click(closeX());
    expect(container.querySelector('.results-list')).not.toBeNull();
    expect(container.querySelector('.result-controls')).toBeNull();
  });
});
