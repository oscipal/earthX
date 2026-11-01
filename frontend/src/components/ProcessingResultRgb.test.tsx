// @vitest-environment jsdom
//
// "RGB" in the dropdown "Band" of a result layer (NM4-64): the three bands of `earthx:true_color` as one colour picture, drawn
// from three `bidx` with one range for all of them and no colormap. No backend: `fetch` answers the TileJSON.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import { jobEntry, NOW } from '../fixtures/jobEntries';
import type { Order } from '../processing';
import { RGB } from '../processingBands';
import { setTrackerOptions, useProcessingStore, type JobEntry } from '../processingStore';
import { resultBands } from '../resultLayer';
import { useAppStore } from '../store';
import type { Collection } from '../types';
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
const RED = stat(0.01, 0.9, 0.05, 0.7);
const GREEN = stat(0.02, 0.8, 0.04, 0.5);
const BLUE = stat(0.005, 0.6, 0.02, 0.4);

// The file holds the bands in the order of the output: a result first, then the bands of the data in the order of the item.
const PROPERTIES = {
  'processing:expression': { format: 'numexpr', expression: '(nir - red) / (nir + red)', name: 'ndvi' },
  bands: [
    { name: 'ndvi', data_type: 'float32', statistics: NDVI },
    { name: 'blue', data_type: 'float32', statistics: BLUE },
    { name: 'green', data_type: 'float32', statistics: GREEN },
    { name: 'red', data_type: 'float32', statistics: RED },
  ],
};
const COLOUR_ONLY = { bands: PROPERTIES.bands.slice(1) };

const orderOf = (steps: unknown[], bands: string[]) =>
  ({
    recipe_version: 2,
    inputs: [{ name: 'in', dataset: 'sentinel-2-c1-l2a', groups: [['S2B_A']] }],
    steps,
    output: { kind: 'raster', format: 'cog', dtype: 'float32', bands },
  }) as unknown as Order;
const NDVI_STEP = { op: 'band_math', op_version: 2, params: { expression: '(nir - red) / (nir + red)', name: 'ndvi' } };
const WITH_RESULT = orderOf([NDVI_STEP], ['ndvi', 'blue', 'green', 'red']);
const WITHOUT_RESULT = orderOf([], ['blue', 'green', 'red']);

function dataset(trueColor: string[] | undefined): DatasetOption {
  return {
    id: 'sentinel-2-c1-l2a',
    title: 'Sentinel-2 L2A',
    viewable: true,
    groupBy: ['datetime'],
    zoom: { min: 8, max: 14 },
    browse: 'quicklook',
    quicklookNodataMax: null,
    resultsGroupBy: ['datetime'],
    hasTimeAxis: true,
    collection: { id: 'sentinel-2-c1-l2a', ...(trueColor ? { 'earthx:true_color': trueColor } : {}) } as Collection,
  };
}

function entry(over: Partial<JobEntry> = {}): JobEntry {
  return jobEntry(1, {
    jobID: JOB,
    phase: 'successful',
    tiles: { href: HREF, width: 1000, gsd: 10 },
    title: 'Band math · Sentinel-2 L2A',
    order: WITH_RESULT,
    bands: resultBands(PROPERTIES, WITH_RESULT),
    ...over,
  });
}

const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers({ toFake: ['Date'], now: NOW });
  sessionStorage.clear();
  localStorage.clear();
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => (url === HREF ? json(TILE_JSON) : json({ title: 'Not found' }))),
  );
  useProcessingStore.getState().resetDraft();
  useProcessingStore.setState({ jobs: [entry()] });
  useAppStore.setState({
    layers: [],
    dock: 'layers',
    mapZoom: 5,
    viewportBbox: null,
    notice: null,
    datasets: [dataset(['red', 'green', 'blue'])],
    resultViewLayerId: null,
  });
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
const colormapField = () => [...container.querySelectorAll('.vc-field')].find((f) => f.textContent?.startsWith('Colormap'));

async function show(over: Partial<JobEntry> = {}) {
  useProcessingStore.setState({ jobs: [entry(over)] });
  await useProcessingStore.getState().showResultOnMap(JOB);
  act(() => root.render(<LayerManager />));
}

function choose(value: string) {
  act(() => {
    Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')!.set!.call(select(), value);
    select()!.dispatchEvent(new Event('change', { bubbles: true }));
  });
}

const colourOnly = (over: Partial<JobEntry> = {}) => show({ order: WITHOUT_RESULT, bands: resultBands(COLOUR_ONLY, WITHOUT_RESULT), ...over });

describe('the choice "RGB" in the row of a result layer', () => {
  it('is on top of the bands of the file, where the result has the three bands and the dataset a colour picture', async () => {
    await show();
    expect(names()).toEqual(['RGB', 'ndvi', 'blue', 'green', 'red']);
  });

  it('is not offered where the result lacks one of the three bands', async () => {
    await show({ order: orderOf([NDVI_STEP], ['ndvi', 'green', 'red']), bands: resultBands({ bands: [PROPERTIES.bands[0], PROPERTIES.bands[2], PROPERTIES.bands[3]] }, WITH_RESULT) });
    expect(names()).toEqual(['ndvi', 'green', 'red']);
  });

  it('is not offered where the dataset has no colour picture, nor where it is not known', async () => {
    act(() => useAppStore.setState({ datasets: [dataset(undefined)] }));
    await show();
    expect(names()).toEqual(['ndvi', 'blue', 'green', 'red']);
    act(() => useAppStore.setState({ layers: [], datasets: [] }));
    await show();
    expect(names()).toEqual(['ndvi', 'blue', 'green', 'red']);
  });

  it('is not offered where the registry names bands the file does not have', async () => {
    act(() => useAppStore.setState({ datasets: [dataset(['red', 'green', 'ghost'])] }));
    await show();
    expect(names()).not.toContain('RGB');
  });
});

describe('where the layer starts', () => {
  it('draws the result of a Band math step, not RGB, where the order has one', async () => {
    await show({ shownBand: null });
    expect(layers()[0].result).toMatchObject({ band: 0 });
    expect(query().getAll('bidx')).toEqual(['1']);
  });

  it('draws RGB where the result has none of a Band math step', async () => {
    await colourOnly({ shownBand: null });
    expect(layers()[0].result).toMatchObject({ band: RGB, colour: [2, 1, 0] });
    expect(select()!.value).toBe(RGB);
  });

  it('draws what the preview showed: RGB, a result, or a band', async () => {
    await show({ shownBand: RGB });
    expect(layers()[0].result).toMatchObject({ band: RGB });
    act(() => useAppStore.setState({ layers: [] }));
    await show({ shownBand: 'red' });
    expect(layers()[0].result).toMatchObject({ band: 3 });
  });

  it('falls back to the default where the preview showed RGB and the result cannot', async () => {
    act(() => useAppStore.setState({ datasets: [dataset(undefined)] }));
    await show({ shownBand: RGB });
    expect(layers()[0].result).toMatchObject({ band: 0 });
  });
});

describe('the picture of RGB', () => {
  it('asks for the three bands in the order red, green, blue, with one range and no colormap', async () => {
    await colourOnly();
    expect(query().getAll('bidx')).toEqual(['3', '2', '1']);
    expect(query().has('colormap_name')).toBe(false);
    // The scale of all three: the lowest 2 % and the highest 98 % of the three bands.
    expect(query().getAll('rescale')).toEqual(['0.02,0.7']);
  });

  it('is drawn with the range saved for it, without its colormap', async () => {
    await colourOnly({ bandRanges: { [RGB]: { vmin: '0', vmax: '0.4', colormap: 'terrain' } } });
    expect(query().getAll('rescale')).toEqual(['0,0.4']);
    expect(query().has('colormap_name')).toBe(false);
  });

  it('is chosen from the dropdown, and a band after it draws one bidx with its colormap again', async () => {
    await show();
    choose(RGB);
    expect(layers()[0].result).toMatchObject({ band: RGB });
    expect(query().getAll('bidx')).toEqual(['4', '3', '2']);
    expect(query().has('colormap_name')).toBe(false);
    expect(query().get('rescale')).toBe('0.02,0.7');
    choose('3');
    expect(layers()[0].result).toMatchObject({ band: 3 });
    expect(query().getAll('bidx')).toEqual(['4']);
    expect([query().get('rescale'), query().get('colormap_name')]).toEqual(['0.05,0.7', 'viridis']);
  });

  it('asks nothing of the server when RGB is chosen, and keeps the tiles of the result', async () => {
    await show();
    const calls = vi.mocked(fetch).mock.calls.length;
    choose(RGB);
    expect(vi.mocked(fetch).mock.calls.length).toBe(calls);
    expect(urlOf().startsWith(`/results/${RESULT}/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=256`)).toBe(true);
  });

  it('does nothing for RGB where the layer has no colour picture', async () => {
    act(() => useAppStore.setState({ datasets: [dataset(undefined)] }));
    await show();
    useProcessingStore.getState().chooseResultBand(layers()[0].id, RGB);
    expect(layers()[0].result).toMatchObject({ band: 0 });
  });
});

describe('"Apply" and "Save" of RGB', () => {
  const input = (label: string) => [...container.querySelectorAll('.vc-field')].find((f) => f.textContent?.startsWith(label))!.querySelector('input')!;
  const type = (label: string, value: string) =>
    act(() => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!.call(input(label), value);
      input(label).dispatchEvent(new Event('input', { bubbles: true }));
    });
  const button = (label: string) => [...container.querySelectorAll('button')].find((b) => b.textContent === label)!;

  async function openControls() {
    await colourOnly();
    act(() => useAppStore.setState({ resultViewLayerId: layers()[0].id }));
    act(() => root.render(<ResultControls />));
  }

  it('keeps the colormap field in its place, locked at "RGB", and shows the range of the three bands in vmin and vmax', async () => {
    await openControls();
    const select = colormapField()!.querySelector('select')!;
    expect(select.disabled).toBe(true);
    expect(select.selectedOptions[0].textContent).toBe('RGB');
    expect([input('vmin').value, input('vmax').value]).toEqual(['0.02', '0.7']);
  });

  it('draws the three bands with the typed range and still no colormap', async () => {
    await openControls();
    type('vmin', '0');
    type('vmax', '0.5');
    act(() => button('Apply').dispatchEvent(new MouseEvent('click', { bubbles: true })));
    expect(query().getAll('bidx')).toEqual(['3', '2', '1']);
    expect(query().getAll('rescale')).toEqual(['0,0.5']);
    expect(query().has('colormap_name')).toBe(false);
  });

  it('keeps the range for RGB, as for a band, and for no other band', async () => {
    await openControls();
    type('vmin', '0');
    type('vmax', '0.5');
    expect(button('Save').title).toContain('this band');
    act(() => button('Save').dispatchEvent(new MouseEvent('click', { bubbles: true })));
    const job = useProcessingStore.getState().jobs[0];
    expect(job.bandRanges[RGB]).toMatchObject({ vmin: '0', vmax: '0.5', colormap: '' });
    expect(Object.keys(job.bandRanges)).toEqual([RGB]);
    expect(job.range).toBeNull();
  });

  it('puts the range of the three bands back with the auto button', async () => {
    await openControls();
    type('vmin', '5');
    type('vmax', '6');
    const auto = [...container.querySelectorAll('button')].find((b) => /auto/i.test(b.textContent ?? '') || /auto/i.test(b.title))!;
    act(() => auto.dispatchEvent(new MouseEvent('click', { bubbles: true })));
    expect([input('vmin').value, input('vmax').value]).toEqual(['0.02', '0.7']);
  });

  it('shows the colormap field again for a single band', async () => {
    await show();
    act(() => useAppStore.setState({ resultViewLayerId: layers()[0].id }));
    act(() => root.render(<ResultControls />));
    expect(colormapField()).toBeDefined();
  });
});
