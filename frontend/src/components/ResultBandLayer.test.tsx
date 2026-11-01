// @vitest-environment jsdom
//
// NM4-65 part 2 (Otto, 31.10.2026): "ein band als eigenen layer speichere. Der layer name ist dann einfach der name des bandes."
// The band a result layer draws is pinned as a layer of its own, with the look of the band, and its settings and "Save" are
// its own afterwards. Set up like `ProcessingResultBands.test.tsx`; no backend: `fetch` answers the TileJSON.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { jobEntry, NOW } from '../fixtures/jobEntries';
import type { Order } from '../processing';
import { setTrackerOptions, useProcessingStore, type JobEntry } from '../processingStore';
import { resultBands } from '../resultLayer';
import { useAppStore } from '../store';
import { ADD_BAND_TIP } from './LayerManager';
import LayerManager from './LayerManager';
import ResultControls from './ResultControls';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const JOB = 'AbCdEfGhIjKlMnOpQrSt_-';
const RESULT = 'ZyXwVuTsRqPoNmLkJiHg_-';
const HREF = `/results/${RESULT}/WebMercatorQuad/tilejson.json`;
const TILE_JSON = { bounds: [10, 50, 11, 51], minzoom: 0, maxzoom: 19, data_type: 'float32', tiles: ['http://tiler/x'] };

const stat = (minimum: number, maximum: number, p2: number, p98: number) => ({ minimum, maximum, mean: 0, count: 1000, valid_percent: 100, percentile_2: p2, percentile_98: p98 });
const NDVI = stat(-0.3, 0.9, -0.05, 0.8);
// Reflectance within -1…1 as well: a band of the data is no index.
const RED = stat(0.01, 0.9, 0.05, 0.7);
const HEIGHT = stat(100, 2400, 180, 1900);

const PROPERTIES = {
  'processing:expression': { format: 'numexpr', expression: '(nir - red) / (nir + red)', name: 'ndvi' },
  bands: [
    { name: 'ndvi', data_type: 'float32', statistics: NDVI },
    { name: 'red', data_type: 'float32', statistics: RED },
    { name: 'height', data_type: 'float32', statistics: HEIGHT },
  ],
};

const ORDER = {
  recipe_version: 2,
  inputs: [{ name: 'in', dataset: 'sentinel-2-c1-l2a', groups: [['S2B_A']] }],
  steps: [{ op: 'band_math', op_version: 2, params: { expression: '(nir - red) / (nir + red)', name: 'ndvi' } }],
  output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['ndvi', 'red', 'height'] },
} as unknown as Order;

function entry(over: Partial<JobEntry> = {}): JobEntry {
  return jobEntry(1, {
    jobID: JOB,
    phase: 'successful',
    tiles: { href: HREF, width: 1000, gsd: 10 },
    title: 'Band math · Sentinel-2 L2A',
    order: ORDER,
    bands: resultBands(PROPERTIES, ORDER),
    ...over,
  });
}

const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  // The jobs of the fixture are dated by `NOW`.
  vi.useFakeTimers({ toFake: ['Date'], now: NOW });
  sessionStorage.clear();
  localStorage.clear();
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => (url === HREF ? json(TILE_JSON) : json({ title: 'Not found' }))),
  );
  useProcessingStore.getState().resetDraft();
  useProcessingStore.setState({ jobs: [entry()] });
  useAppStore.setState({ layers: [], dock: 'layers', mapZoom: 5, viewportBbox: null, notice: null, datasets: [], resultViewLayerId: null });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  setTrackerOptions({});
});

const layers = () => useAppStore.getState().layers;
const urlOf = (i: number) => (layers()[i].overlays[0] as { tileUrl: string }).tileUrl;
const query = (i: number) => new URL(urlOf(i), 'http://localhost').searchParams;
const select = () => container.querySelector<HTMLSelectElement>('.layer-row .lm-band select');

async function show(over: Partial<JobEntry> = {}) {
  useProcessingStore.setState({ jobs: [entry(over)] });
  await useProcessingStore.getState().showResultOnMap(JOB);
  act(() => root.render(<LayerManager />));
}

function choose(place: number) {
  act(() => {
    Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')!.set!.call(select(), String(place));
    select()!.dispatchEvent(new Event('change', { bubbles: true }));
  });
}


const click = (el: Element | null | undefined) => {
  if (!el) throw new Error(`nothing to click in ${container.textContent}`);
  act(() => el.dispatchEvent(new MouseEvent('click', { bubbles: true })));
};
const addButton = (row = 0) => container.querySelectorAll('.layer-row')[row]?.querySelector<HTMLButtonElement>('.lm-add-band') ?? null;
const rowNames = () => [...container.querySelectorAll('.layer-row .lm-name')].map((n) => n.textContent);

describe('"Add band as layer"', () => {
  it('is a button at the end of the line of the band, with a tooltip, for a result of several bands only', async () => {
    await show();
    expect(addButton()!.title).toBe(ADD_BAND_TIP);
    expect(addButton()!.getAttribute('aria-label')).toBe(ADD_BAND_TIP);
    await act(async () => {
      useAppStore.setState({ layers: [] });
    });
    await show({ bands: [entry().bands[0]] });
    expect(addButton()).toBeNull();
  });

  it('is not offered once the results are gone or while the job is deleted (nothing can be drawn from them)', async () => {
    await show();
    act(() => useAppStore.getState().expireResultLayers(Date.parse(layers()[0].result!.expires) + 1));
    act(() => root.render(<LayerManager />));
    expect(addButton()).toBeNull();
  });

  it('adds the band that is drawn, named after it, just above the layer it comes from', async () => {
    await show({ shownBand: 'red' });
    click(addButton());
    expect(layers()).toHaveLength(2);
    expect(rowNames()).toEqual(['red', 'Result · Band math']);
    const [added, origin] = layers();
    expect(added.id).not.toBe(origin.id);
    expect(added.derived).toBe('result');
    expect(added.result).toMatchObject({ jobID: JOB, own: true, dataType: 'float32' });
    // It draws that one band and has no list to choose from.
    expect(added.result).not.toHaveProperty('bands');
    expect(added.result).not.toHaveProperty('band');
    expect(container.querySelectorAll('.layer-row')[0].querySelector('.lm-band')).toBeNull();
    expect(container.querySelectorAll('.layer-row')[0].querySelector('.lm-add-band')).toBeNull();
    // The layer it comes from is as it was.
    expect(origin.result).toMatchObject({ band: 1, bands: [{ name: 'ndvi' }, { name: 'red' }, { name: 'height' }] });
  });

  it('draws the band the way the band is drawn now: its tiles, its range and its colormap', async () => {
    await show({ shownBand: 'red' });
    click(addButton());
    expect(query(0).get('bidx')).toBe('2');
    expect([query(0).get('rescale'), query(0).get('colormap_name')]).toEqual(['0.05,0.7', 'viridis']);
    expect(urlOf(0)).toBe(urlOf(1));
  });

  it('takes a look that is applied and not saved as the look of the new layer, and leaves the origin unsaved', async () => {
    await show({ shownBand: 'red' });
    act(() => useAppStore.getState().restyleResultLayer(layers()[0].id, { rescale: '0.1,0.5', colormapName: 'turbo' }));
    expect(layers()[0].result!.savedTileUrl).toBeDefined();
    click(addButton());
    const [added, origin] = layers();
    expect(query(0).get('rescale')).toBe('0.1,0.5');
    expect(added.result).not.toHaveProperty('savedTileUrl');
    expect(origin.result!.savedTileUrl).toBeDefined();
  });

  it('adds the colour picture as "RGB", with the three bands and no colormap, where the band is "RGB"', async () => {
    const bands = [{ name: 'red', stats: null }, { name: 'green', stats: null }, { name: 'blue', stats: null }];
    await show({ bands: bands as never, order: { ...ORDER, output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['red', 'green', 'blue'] } } as unknown as Order });
    act(() => useAppStore.setState({ layers: layers().map((l) => ({ ...l, result: { ...l.result!, colour: [0, 1, 2], band: '@rgb' } })) as never }));
    act(() => root.render(<LayerManager />));
    click(addButton());
    expect(rowNames()[0]).toBe('RGB');
    expect(layers()[0].result).toMatchObject({ band: '@rgb', colour: [0, 1, 2], own: true });
    expect(layers()[0].result).not.toHaveProperty('bands');
  });

  it('takes the date, the opacity and the visibility of the layer it comes from', async () => {
    await show();
    act(() => useAppStore.setState({ layers: layers().map((l) => ({ ...l, date: '2026-07-01', opacity: 0.4, visible: false })) }));
    click(addButton());
    expect(layers()[0]).toMatchObject({ date: '2026-07-01', opacity: 0.4, visible: false });
  });

  it('can be added again, once more for every band, each a layer of its own', async () => {
    await show();
    click(addButton());
    choose(2);
    click(addButton(1));
    expect(rowNames()).toEqual(['ndvi', 'height', 'Result · Band math']);
    expect(new Set(layers().map((l) => l.id)).size).toBe(3);
  });

  it('keeps the entry "Results" where it was: under the layers it had above it, and on top where it was on top', async () => {
    await show();
    // "Results" under the layer: the new layer is above it too, so two layers lie over "Results" now.
    act(() => useAppStore.setState({ resultsAt: 1 }));
    click(addButton());
    expect(useAppStore.getState().resultsAt).toBe(2);
    // "Results" on top: it stays on top, the new layer is under it.
    act(() => useAppStore.setState({ layers: layers().slice(1), resultsAt: 0 }));
    click(addButton());
    expect(useAppStore.getState().resultsAt).toBe(0);
    expect(layers()).toHaveLength(2);
  });

  it('says it in a notice', async () => {
    await show();
    click(addButton());
    expect(useAppStore.getState().notice).toBe('Added "ndvi" to layers.');
  });

  it('ignores an id that is no layer, and a layer that is no result of several bands', async () => {
    await show();
    act(() => useAppStore.getState().addBandAsLayer('nothing'));
    expect(layers()).toHaveLength(1);
    act(() => useAppStore.setState({ layers: [{ ...layers()[0], derived: 'preview', result: undefined }] }));
    act(() => useAppStore.getState().addBandAsLayer(layers()[0].id));
    expect(layers()).toHaveLength(1);
  });
});

describe('the settings and "Save" of a layer made from a band', () => {
  const open = (i: number) => {
    act(() => root.render(<><LayerManager /><ResultControls /></>));
    act(() => useAppStore.getState().selectLayer(layers()[i].id));
  };
  const typeInto = (input: HTMLInputElement, value: string) =>
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value);
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
  const button = (label: string) => [...container.querySelectorAll('.result-controls button')].find((b) => b.textContent?.trim() === label) as HTMLButtonElement;
  const vmax = () => container.querySelectorAll<HTMLInputElement>('.result-controls .vc-num input')[1];

  it('read vmin · vmax · Colormap without a Band dropdown, and "Save" says it keeps the look for this layer only', async () => {
    await show();
    click(addButton());
    open(0);
    expect([...container.querySelectorAll('.result-controls .vc-field > span')].map((s) => s.textContent)).toEqual(['vmin', 'vmax', 'Colormap', 'Opacity']);
    expect(button('Save').title).toBe('Nothing to save: the layer is saved as it is drawn');
    typeInto(vmax(), '0.5');
    expect(button('Save').title).toBe('Keep these values for this layer only');
  });

  it('are independent: "Apply" draws the new layer and not the one it comes from', async () => {
    await show();
    click(addButton());
    open(0);
    typeInto(vmax(), '0.5');
    click(button('Apply'));
    expect(query(0).get('rescale')).toBe('-1,0.5');
    expect(query(1).get('rescale')).toBe('-1,1');
  });

  it('"Save" keeps the look for the layer only: the job and the layer it comes from keep theirs', async () => {
    await show();
    const before = JSON.stringify(useProcessingStore.getState().jobs[0].bandRanges) + JSON.stringify(useProcessingStore.getState().jobs[0].range);
    click(addButton());
    open(0);
    typeInto(vmax(), '0.5');
    click(button('Save'));
    expect(query(0).get('rescale')).toBe('-1,0.5');
    expect(layers()[0].result).not.toHaveProperty('savedTileUrl');
    const job = useProcessingStore.getState().jobs[0];
    expect(JSON.stringify(job.bandRanges) + JSON.stringify(job.range)).toBe(before);
    expect(query(1).get('rescale')).toBe('-1,1');
    // Closing the settings does not take it back: it is saved.
    act(() => useAppStore.getState().closeResultView());
    expect(query(0).get('rescale')).toBe('-1,0.5');
  });

  it('are not touched by a "Save" on the layer it comes from', async () => {
    await show();
    click(addButton());
    // The layer it comes from is the second row.
    open(1);
    typeInto(vmax(), '0.7');
    click(button('Save'));
    expect(query(1).get('rescale')).toBe('-1,0.7');
    expect(query(0).get('rescale')).toBe('-1,1');
    expect(useProcessingStore.getState().jobs[0].bandRanges).toEqual({ ndvi: expect.objectContaining({ vmax: '0.7' }) });
  });
});
