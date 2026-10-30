// @vitest-environment jsdom
//
// A result layer of several bands (NM4-43e PR 2, adr/0020 §10): the dropdown "Band" in the row of the layer manager,
// the band the tiles are asked for (`bidx`), the colour scale of each band from its statistics, and "Save" for a band.
// No backend: `fetch` answers the TileJSON and the results document.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { jobEntry, NOW } from '../fixtures/jobEntries';
import type { Order } from '../processing';
import { setTrackerOptions, useProcessingStore, type JobEntry } from '../processingStore';
import { resultBands } from '../resultLayer';
import { useAppStore } from '../store';
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
const urlOf = () => (layers()[0].overlays[0] as { tileUrl: string }).tileUrl;
const query = () => new URL(urlOf(), 'http://localhost').searchParams;
const select = () => container.querySelector<HTMLSelectElement>('.layer-row .lm-band select');
const names = () => [...(select()?.options ?? [])].map((o) => o.textContent);

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

describe('the bands of a result, as the layer holds them', () => {
  it('are the bands of the results document in the order of the file, each with its own statistics', () => {
    expect(entry().bands.map((b) => b.name)).toEqual(['ndvi', 'red', 'height']);
    expect(entry().bands.map((b) => b.stats?.bands[0].maximum)).toEqual([0.9, 0.9, 2400]);
  });

  it('judges a band as an index only if a Band math step of the order made it', () => {
    const [ndvi, red] = entry().bands;
    expect(ndvi.stats?.expression).toBe(true);
    expect(red.stats?.expression).toBe(false);
  });

  it('judges by the property of the results alone where the order is not kept', () => {
    const bands = resultBands(PROPERTIES, null);
    expect(bands.map((b) => b.stats?.expression)).toEqual([true, true, true]);
    expect(resultBands({ bands: PROPERTIES.bands }, null).map((b) => b.stats?.expression)).toEqual([false, false, false]);
  });
});

describe('the layer of a result of several bands', () => {
  it('draws the first band of the file by its `bidx`, with the scale of that band', async () => {
    await show();
    const layer = layers()[0];
    expect(layer.result).toMatchObject({ band: 0, bands: [{ name: 'ndvi' }, { name: 'red' }, { name: 'height' }] });
    expect(query().get('bidx')).toBe('1');
    expect([query().get('rescale'), query().get('colormap_name')]).toEqual(['-1,1', 'rdylgn']);
  });

  it('has no `bidx`, no bands and no dropdown for a result of one band', async () => {
    await show({ bands: resultBands({ bands: [PROPERTIES.bands[0]] }, ORDER), statistics: null });
    expect(layers()[0].result?.bands).toBeUndefined();
    expect(urlOf()).not.toContain('bidx');
    expect(select()).toBeNull();
  });

  it('has the dropdown "Band" in its row, with the names of the bands in the order of the file', async () => {
    await show();
    expect(container.querySelector('.layer-row .lm-band > span')!.textContent).toBe('Band');
    expect(names()).toEqual(['ndvi', 'red', 'height']);
    expect(select()!.value).toBe('0');
  });

  it('has no dropdown on the row of a layer that is no result', async () => {
    useAppStore.setState({
      layers: [{ id: 'x', name: 'Scenes', visible: true, opacity: 1, overlays: [], restore: { datasetId: 'd', itemIds: [] } as never }],
    });
    act(() => root.render(<LayerManager />));
    expect(select()).toBeNull();
  });

  it('draws another band from its `bidx` and its statistics when it is chosen', async () => {
    await show();
    choose(2);
    expect(query().get('bidx')).toBe('3');
    expect([query().get('rescale'), query().get('colormap_name')]).toEqual(['180,1900', 'viridis']);
    expect(layers()[0].result).toMatchObject({ band: 2 });
    expect(select()!.value).toBe('2');
  });

  it('takes a band of the data for no index, however small its values are', async () => {
    await show();
    choose(1);
    expect(query().get('bidx')).toBe('2');
    expect([query().get('rescale'), query().get('colormap_name')]).toEqual(['0.05,0.7', 'viridis']);
  });

  it('keeps the tiles of the result, the opacity and the place of the layer when the band changes', async () => {
    await show();
    useAppStore.getState().setLayerOpacity(layers()[0].id, 0.4);
    const before = layers()[0];
    choose(2);
    const after = layers()[0];
    expect(after.id).toBe(before.id);
    expect(after.opacity).toBe(0.4);
    expect(urlOf().split('?')[0]).toBe(`/results/${RESULT}/tiles/WebMercatorQuad/{z}/{x}/{y}`);
    expect(query().get('tilesize')).toBe('256');
  });

  it('keeps the band when the look of the layer is applied: "Apply" draws the same band another way', async () => {
    await show();
    choose(1);
    useAppStore.getState().restyleResultLayer(layers()[0].id, { rescale: '0,0.5', colormapName: 'greys' });
    expect(query().get('bidx')).toBe('2');
    expect([query().get('rescale'), query().get('colormap_name')]).toEqual(['0,0.5', 'greys']);
  });

  it('lets what was applied and not saved go with the band', async () => {
    await show();
    useAppStore.getState().restyleResultLayer(layers()[0].id, { rescale: '0,0.5', colormapName: 'greys' });
    expect(layers()[0].result?.savedTileUrl).toBeDefined();
    choose(2);
    expect(layers()[0].result?.savedTileUrl).toBeUndefined();
    expect(query().get('rescale')).toBe('180,1900');
  });

  it('asks nothing of the server when the band is chosen', async () => {
    await show();
    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.length;
    choose(1);
    expect((fetch as unknown as ReturnType<typeof vi.fn>).mock.calls).toHaveLength(calls);
  });

  it.each([
    ['expired', { expired: true }],
    ['deleted', { deleted: true }],
  ])('has the dropdown disabled for a layer that is %s', async (_, info) => {
    await show();
    act(() => useAppStore.setState({ layers: layers().map((l) => ({ ...l, result: { ...l.result!, ...info } })) }));
    expect(select()!.disabled).toBe(true);
  });

  it('does nothing for a place the result does not have, or for another layer', async () => {
    await show();
    const before = urlOf();
    act(() => useProcessingStore.getState().chooseResultBand(layers()[0].id, 7));
    act(() => useProcessingStore.getState().chooseResultBand('nothing', 1));
    act(() => useProcessingStore.getState().chooseResultBand(layers()[0].id, -1));
    expect(urlOf()).toBe(before);
  });

  it('has no look of the job in the URL, only the band and the style', async () => {
    await show();
    choose(1);
    expect(urlOf()).not.toContain(JOB);
    expect([...query().keys()].sort()).toEqual(['bidx', 'colormap_name', 'rescale', 'tilesize']);
  });
});

describe('the range saved for a band', () => {
  const HAND = { vmin: '0', vmax: '3000', colormap: 'terrain' };

  it('is the job\'s own for a band, by its name, and no other band is drawn with it', async () => {
    useProcessingStore.getState().setJobRange(JOB, HAND, 'height');
    expect(useProcessingStore.getState().jobs[0].bandRanges).toEqual({ height: HAND });
    expect(useProcessingStore.getState().jobs[0].range).toBeNull();
    await show({ bandRanges: { height: HAND } });
    expect(query().get('rescale')).toBe('-1,1'); // the first band: no range of its own
    choose(2);
    expect([query().get('rescale'), query().get('colormap_name')]).toEqual(['0,3000', 'terrain']);
    choose(1);
    expect(query().get('rescale')).toBe('0.05,0.7');
  });

  it('is drawn with the range saved for the first band from the start', async () => {
    await show({ bandRanges: { ndvi: HAND } });
    expect([query().get('rescale'), query().get('colormap_name')]).toEqual(['0,3000', 'terrain']);
  });

  it('is taken away with `null`, and the others stay', () => {
    const store = useProcessingStore.getState();
    store.setJobRange(JOB, HAND, 'height');
    store.setJobRange(JOB, { vmin: '1', vmax: '2', colormap: '' }, 'red');
    useProcessingStore.getState().setJobRange(JOB, null, 'height');
    expect(Object.keys(useProcessingStore.getState().jobs[0].bandRanges)).toEqual(['red']);
  });

  it('is not the range of the job: a result of one band keeps the range as before', () => {
    useProcessingStore.getState().setJobRange(JOB, HAND);
    expect(useProcessingStore.getState().jobs[0].range).toEqual(HAND);
    expect(useProcessingStore.getState().jobs[0].bandRanges).toEqual({});
  });

  it('is kept by "Save" of the view of the layer, for the band it draws', async () => {
    await show();
    choose(2);
    act(() => useAppStore.setState({ resultViewLayerId: layers()[0].id }));
    act(() => root.render(<ResultControls />));
    const input = (label: string) => [...container.querySelectorAll('.vc-field')].find((f) => f.textContent?.startsWith(label))!.querySelector('input')!;
    for (const [label, value] of [['vmin', '10'], ['vmax', '20']] as const) {
      act(() => {
        Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!.call(input(label), value);
        input(label).dispatchEvent(new Event('input', { bubbles: true }));
      });
    }
    const save = [...container.querySelectorAll('button')].find((b) => b.textContent === 'Save')!;
    expect(save.title).toContain('this band');
    act(() => save.dispatchEvent(new MouseEvent('click', { bubbles: true })));
    expect(useProcessingStore.getState().jobs[0].bandRanges.height).toMatchObject({ vmin: '10', vmax: '20' });
    expect(useProcessingStore.getState().jobs[0].range).toBeNull();
  });
});
