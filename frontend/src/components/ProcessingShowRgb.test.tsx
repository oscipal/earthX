// @vitest-environment jsdom
//
// "RGB" in the dropdown "Show" (NM4-64): the three bands of `earthx:true_color` as one colour picture of the preview, with
// one range for all of them and no colormap. No backend: `fetch` answers the process description, the TileJSON and the
// statistics.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import { bboxToPolygon } from '../geoUtils';
import { RGB } from '../processingBands';
import { useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection, EarthxMask, StacItem } from '../types';
import ProcessingPanel from './ProcessingPanel';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const AOI = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);
const NDVI = '(nir - red) / (nir + red)';
const SCL: EarthxMask = { asset: 'scl', band: 'scl', classes: [{ value: 3, label: 'CLOUD_SHADOWS' }], suggested: [3], reference: 'https://example.org/scl', note: '' };

const band = { data_type: 'uint16', nodata: 0 };
const asset = (extra: object = {}) => ({ href: 'https://example.org/b.tif', type: COG, 'raster:bands': [band], ...extra });

// Sentinel-2 like: a few bands, the classification layer, and `more` bands besides.
function scene(id: string, more = 0): StacItem {
  const bbox: [number, number, number, number] = [10, 50, 11, 51];
  const extra = Object.fromEntries(Array.from({ length: more }, (_, i) => [`b${i + 1}`, asset()]));
  return {
    id,
    collection: 'sentinel-2-c1-l2a',
    bbox,
    geometry: bboxToPolygon(bbox),
    properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 },
    assets: {
      red: asset(),
      green: asset(),
      blue: asset(),
      nir: asset(),
      scl: asset({ gsd: 20, 'raster:bands': [{ data_type: 'uint8', nodata: 0 }] }),
      ...extra,
    },
  };
}

function dataset(trueColor: string[] | null = ['red', 'green', 'blue']): DatasetOption {
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
    collection: {
      id: 'sentinel-2-c1-l2a',
      'earthx:format': 'cog',
      'earthx:license_flags': { tier: 'processing' },
      'earthx:capabilities': { interpolation: true },
      'earthx:mask': SCL,
      ...(trueColor ? { 'earthx:true_color': trueColor } : {}),
    } as unknown as Collection,
  };
}

function select(items: StacItem[], trueColor?: string[] | null) {
  useAppStore.setState({
    datasets: [dataset(trueColor)],
    datasetId: 'sentinel-2-c1-l2a',
    items,
    groups: [{ key: ['2026-07-01'], label: '2026-07-01', items }],
    activeGroupIndex: 0,
    selectedIds: items.map((i) => i.id),
    aoi: AOI,
    aoiPoint: null,
    layers: [],
    mapZoom: 1.6,
    viewportBbox: null,
  });
}

const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
// Answers at once, with no stream to wait for.
const measured = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as Response;

interface Values {
  count: number;
  min: number;
  max: number;
  percentile_2: number;
  percentile_98: number;
  unit: string | null;
}
const INDEX: Values = { count: 900, min: -0.2, max: 0.9, percentile_2: -0.1, percentile_98: 0.8, unit: null };

let container: HTMLDivElement;
let root: Root;
let fetchMock: ReturnType<typeof vi.fn>;
// What the statistics of a scene say, by the band asked.
let statistics: (bands: string[]) => Record<string, unknown>;
// What the statistics over the AOI of the order say.
let areaStatistics: (order: { output: { bands: string[] } }) => unknown[];

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  localStorage.clear();
  statistics = () => ({ b1: INDEX });
  areaStatistics = () => [];
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/processing/processes/recipe?dataset=sentinel-2-c1-l2a') return json(s2);
    if (init?.method === 'POST' && url.endsWith('/statistics')) {
      const order = JSON.parse(String(init.body));
      return measured({ bands: areaStatistics(order), exact: true, factor: 1 });
    }
    if (url.includes('/tilejson.json')) return json({ tilejson: '3.0.0' });
    if (url.includes('/statistics?')) return measured(statistics(new URL(url, 'http://localhost').searchParams.getAll('band')));
    return new Response('{}', { status: 404, headers: { 'Content-Type': 'application/problem+json' } });
  });
  vi.stubGlobal('fetch', fetchMock);
  useProcessingStore.getState().resetDraft();
  useProcessingStore.setState({ open: false, descriptions: {}, jobs: [], preview: null, previewNote: null });
  useAppStore.setState({ mapZoom: 1.6, viewportBbox: null, layers: [], dock: null });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

async function flush() {
  await act(async () => {
    for (let i = 0; i < 20; i++) await Promise.resolve();
  });
}

async function afterDebounce() {
  act(() => {
    vi.advanceTimersByTime(400);
  });
  await flush();
}

const store = () => useProcessingStore.getState();
const section = () => container.querySelector('section[aria-label="Preview on the map"]')!;
const show = () => section().querySelector<HTMLSelectElement>('.pp-show select');
const options = () => [...(show()?.options ?? [])].map((o) => o.value);
const labels = () => [...(show()?.options ?? [])].map((o) => o.textContent);
const colormapField = () => [...section().querySelectorAll('.pp-range .vc-field')].find((f) => f.textContent?.startsWith('Colormap'));
const fields = () => [...section().querySelectorAll<HTMLInputElement>('input[type="number"]')];
const button = (label: string) => [...container.querySelectorAll('button')].find((b) => b.textContent?.trim() === label)!;
const expression = (index: number) => container.querySelectorAll<HTMLTextAreaElement>('textarea[id$="-expression"]')[index]!;
const click = (element: HTMLElement) => act(() => element.dispatchEvent(new MouseEvent('click', { bubbles: true })));

function typeInto(input: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const prototype = input instanceof HTMLTextAreaElement ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  act(() => {
    Object.getOwnPropertyDescriptor(prototype, 'value')!.set!.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

function choose(select: HTMLSelectElement, value: string) {
  act(() => {
    Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')!.set!.call(select, value);
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
}

// The address of the first scene's tiles, and the statistics asked.
const tiles = () => new URL(store().preview!.scenes[0].url, 'http://localhost').searchParams;
const asked = () => fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.includes('/statistics?'));

async function openWith(items: StacItem[], trueColor?: string[] | null) {
  select(items, trueColor);
  act(() => root.render(<ProcessingPanel />));
  act(() => store().openProcessing());
  await flush();
  vi.useFakeTimers();
}

// One Band math step (NDVI), and the output: the result alone, or with more bands.
async function ndvi(output: string[] = ['result'], trueColor?: string[] | null, items = [scene('S2B_A')]) {
  await openWith(items, trueColor);
  click(button('＋ Band math'));
  typeInto(expression(0), NDVI);
  act(() => store().setOutput(output));
  await afterDebounce();
}


const RED = { count: 900, min: 0.01, max: 0.9, percentile_2: 0.05, percentile_98: 0.7, unit: null };
const GREEN = { count: 900, min: 0.02, max: 0.8, percentile_2: 0.04, percentile_98: 0.5, unit: null };
const BLUE = { count: 900, min: 0.005, max: 0.6, percentile_2: 0.02, percentile_98: 0.4, unit: null };
const BY_NAME: Record<string, Values> = { red: RED, green: GREEN, blue: BLUE, result: INDEX };

beforeEach(() => {
  // The statistics of the bands asked, in the order asked, each under the name of its channel (`b1`, `b2` …).
  statistics = (bands) => Object.fromEntries(bands.map((name, i) => [`b${i + 1}`, BY_NAME[name] ?? RED]));
});

const ALL = ['result', 'red', 'green', 'blue'];
const COLOUR = ['red', 'green', 'blue'];
const rescale = () => tiles().get('rescale');

describe('the choice "RGB" in "Show"', () => {
  it('is on top, called RGB, where the three bands are in the output', async () => {
    await ndvi(ALL);
    expect(options()).toEqual([RGB, 'result', 'red', 'green', 'blue']);
    expect(labels()).toEqual(['RGB', 'result', 'red', 'green', 'blue']);
  });

  it('is not offered where a band of the colour picture is not in the output', async () => {
    await ndvi(['result', 'red', 'green']);
    expect(options()).toEqual(['result', 'red', 'green']);
  });

  it('is not offered for a dataset that has no colour picture', async () => {
    await ndvi(ALL, null);
    expect(options()).toEqual(['result', 'red', 'green', 'blue']);
  });

  it('makes a dropdown of an output of the three bands alone', async () => {
    await ndvi(COLOUR);
    expect(options()).toEqual([RGB, 'red', 'green', 'blue']);
  });
});

describe('where the preview starts', () => {
  it('shows the result of a Band math step where the output has one: it stays the default', async () => {
    await ndvi(ALL);
    expect(show()!.value).toBe('result');
    expect(tiles().getAll('band')).toEqual(['result']);
  });

  it('shows RGB where the output has no result of a Band math step', async () => {
    await ndvi(COLOUR);
    expect(show()!.value).toBe(RGB);
    expect(tiles().getAll('band')).toEqual(['red', 'green', 'blue']);
    expect(store().preview).toMatchObject({ band: RGB, bands: COLOUR });
  });

  it('shows the first band, as before, where the dataset has no colour picture', async () => {
    await ndvi(COLOUR, null);
    expect(show()!.value).toBe('red');
    expect(tiles().getAll('band')).toEqual(['red']);
  });
});

describe('the picture of RGB', () => {
  it('reads the three assets and no more, in the order of the item', async () => {
    await ndvi(COLOUR);
    expect(tiles().getAll('asset')).toEqual(['red', 'green', 'blue']);
  });

  it('has no colormap in the tiles and no field for one', async () => {
    await ndvi(COLOUR);
    expect(tiles().has('colormap_name')).toBe(false);
    expect(colormapField()).toBeUndefined();
    expect(fields()).toHaveLength(2);
  });

  it('is named RGB when it is added to the layers', async () => {
    await ndvi(COLOUR);
    expect(store().preview!.title).toBe('Band math · RGB');
  });

  it('asks the TileJSON and the statistics for the three bands', async () => {
    await ndvi(COLOUR);
    expect(new URL(store().preview!.probe, 'http://localhost').searchParams.getAll('band')).toEqual(COLOUR);
    expect(asked().at(-1)).toContain('band=red&band=green&band=blue');
  });

  it('takes one range from all three bands: the lowest 2 % and the highest 98 %', async () => {
    await ndvi(COLOUR);
    // red 0.05…0.7, green 0.04…0.5, blue 0.02…0.4
    expect(rescale()).toBe('0.02,0.7');
    expect(fields().map((f) => f.value)).toEqual(['0.02', '0.7']);
    expect(tiles().getAll('rescale')).toHaveLength(1);
  });

  it('takes an index for no index: three bands that lie in -1…1 are drawn with their measured range', async () => {
    statistics = () => ({ b1: INDEX, b2: INDEX, b3: INDEX });
    await ndvi(COLOUR);
    expect(rescale()).toBe('-0.1,0.8');
  });

  it('draws the range applied by hand, also without a colormap', async () => {
    await ndvi(COLOUR);
    typeInto(fields()[0], '0');
    typeInto(fields()[1], '0.3');
    click(button('Apply'));
    await afterDebounce();
    expect(rescale()).toBe('0,0.3');
    expect(tiles().has('colormap_name')).toBe(false);
  });

  it('measures over the AOI for "AOI only" from the three bands of the answer', async () => {
    const entry = (name: string, values: Values) => ({
      name,
      unit: null,
      statistics: { count: values.count, minimum: values.min, maximum: values.max, percentile_2: values.percentile_2, percentile_98: values.percentile_98 },
    });
    areaStatistics = () => [entry('red', { ...RED, percentile_2: 0.1, percentile_98: 0.6 }), entry('green', GREEN), entry('blue', BLUE), entry('result', INDEX)];
    await ndvi(COLOUR);
    click(button('AOI only'));
    await afterDebounce();
    expect(store().measure).toMatchObject({ source: 'area' });
    expect(rescale()).toBe('0.02,0.6');
  });
});

describe('from RGB to a band and back', () => {
  it('draws one band with its colormap, and RGB without one again', async () => {
    await ndvi(ALL);
    choose(show()!, RGB);
    await afterDebounce();
    expect(tiles().getAll('band')).toEqual(COLOUR);
    expect(colormapField()).toBeUndefined();
    choose(show()!, 'red');
    await afterDebounce();
    expect(tiles().getAll('band')).toEqual(['red']);
    expect(tiles().get('colormap_name')).toBe('viridis');
    expect(colormapField()).toBeDefined();
    choose(show()!, RGB);
    await afterDebounce();
    expect(tiles().has('colormap_name')).toBe(false);
    expect(colormapField()).toBeUndefined();
  });

  it('gives up the range set by hand for RGB when the band changes', async () => {
    await ndvi(COLOUR);
    typeInto(fields()[0], '0');
    typeInto(fields()[1], '0.3');
    click(button('Apply'));
    await afterDebounce();
    choose(show()!, 'red');
    await afterDebounce();
    expect(rescale()).toBe('0.05,0.7');
    expect(store().rangeByHand).toBe(false);
  });

  it('falls back to the default when a band of the colour picture leaves the output', async () => {
    await ndvi(ALL);
    choose(show()!, RGB);
    await afterDebounce();
    act(() => store().toggleOutput('blue'));
    await afterDebounce();
    expect(options()).toEqual(['result', 'red', 'green']);
    expect(show()!.value).toBe('result');
  });
});
