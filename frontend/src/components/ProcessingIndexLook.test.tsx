// @vitest-environment jsdom
//
// The look of the preview of the processing panel for a band with the expression of an index preset of the dataset (NM4-14b,
// D2): the range and colormap of the preset, whatever was measured. The panel has no index buttons (Otto, 31.10.2026: the
// quick calculation is in the view, `ViewIndex.test.tsx`); an expression typed by hand that is the preset's is drawn alike.
// No backend: `fetch` answers the process description, the TileJSON and the statistics.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import { SENTINEL_2_PRESETS } from '../fixtures/indexPresets';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import { bboxToPolygon } from '../geoUtils';
import { useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection, StacItem } from '../types';
import ProcessingPanel from './ProcessingPanel';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const AOI = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);
const band = { data_type: 'uint16', nodata: 0 };
const asset = () => ({ href: 'https://example.org/b.tif', type: COG, 'raster:bands': [band] });

const scene = (id: string): StacItem => {
  const bbox: [number, number, number, number] = [10, 50, 11, 51];
  return {
    id,
    collection: 'sentinel-2-c1-l2a',
    bbox,
    geometry: bboxToPolygon(bbox),
    properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 },
    assets: { blue: asset(), green: asset(), red: asset(), nir: asset(), swir16: asset(), swir22: asset() },
  };
};

function dataset(presets: unknown): DatasetOption {
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
      ...(presets === undefined ? {} : { 'earthx:index_presets': presets }),
    } as unknown as Collection,
  };
}

function select(presets: unknown) {
  const items = [scene('S2B_A')];
  useAppStore.setState({
    datasets: [dataset(presets)],
    datasetId: 'sentinel-2-c1-l2a',
    items,
    groups: [{ key: ['2026-07-01'], label: '2026-07-01', items }],
    activeGroupIndex: 0,
    selectedIds: ['S2B_A'],
    aoi: AOI,
    aoiPoint: null,
    layers: [],
    mapZoom: 1.6,
    viewportBbox: null,
  });
}

const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
const measured = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as Response;
const stats = (values: object) => ({ count: 900, min: -0.2, max: 0.9, percentile_2: -0.1, percentile_98: 0.8, unit: null, ...values });

let container: HTMLDivElement;
let root: Root;
let fetchMock: ReturnType<typeof vi.fn>;
// What the statistics of a scene say.
let values: object;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  localStorage.clear();
  values = {};
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/processing/processes/recipe?dataset=sentinel-2-c1-l2a') return json(s2);
    if (init?.method === 'POST' && url.endsWith('/statistics')) return measured({ bands: [], exact: true, factor: 1 });
    if (url.includes('/tilejson.json')) return json({ tilejson: '3.0.0' });
    if (url.includes('/statistics?')) return measured({ band: stats(values) });
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

async function openWith(presets: unknown) {
  select(presets);
  act(() => root.render(<ProcessingPanel />));
  act(() => useProcessingStore.getState().openProcessing());
  await flush();
  vi.useFakeTimers();
}

const store = () => useProcessingStore.getState();
const bandMath = () => [...container.querySelectorAll('button')].find((b) => b.textContent?.trim() === '＋ Band math')!;
const click = (element: HTMLElement) => act(() => element.dispatchEvent(new MouseEvent('click', { bubbles: true })));
const expression = (at: number) => container.querySelectorAll<HTMLTextAreaElement>('textarea[id$="-expression"]')[at]!;
const section = () => container.querySelector('section[aria-label="Preview on the map"]')!;
const fields = () => [...section().querySelectorAll<HTMLInputElement>('input[type="number"]')];
const tiles = () => new URL(store().preview!.scenes[0].url, 'http://localhost').searchParams;

function typeInto(input: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const prototype = input instanceof HTMLTextAreaElement ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  act(() => {
    Object.getOwnPropertyDescriptor(prototype, 'value')!.set!.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

describe('the preview of an index (D2)', () => {
  const colormap = () => tiles().get('colormap_name');
  const rescale = () => tiles().get('rescale');

  beforeEach(() => {
    // The values of the scene lie outside −1…1: the rule of an index would not apply, the 2–98 % would be drawn in viridis.
    values = { min: -3, max: 8, percentile_2: -2.5, percentile_98: 6 };
  });

  it('draws the preview of a preset in the range and colormap of the preset, whatever was measured', async () => {
    await openWith(SENTINEL_2_PRESETS);
    click(bandMath());
    typeInto(expression(0), '(green - nir) / (green + nir)');
    await afterDebounce();
    expect([rescale(), colormap()]).toEqual(['-1,1', 'rdbu']);
    expect(fields().map((f) => f.value)).toEqual(['-1', '1']);
  });

  it('is the same for the expression typed by hand, in other spaces', async () => {
    await openWith(SENTINEL_2_PRESETS);
    click(bandMath());
    typeInto(expression(0), '(green-nir)/(green+nir)');
    await afterDebounce();
    expect([rescale(), colormap()]).toEqual(['-1,1', 'rdbu']);
  });

  it('draws a changed expression by the rule it had', async () => {
    await openWith(SENTINEL_2_PRESETS);
    click(bandMath());
    typeInto(expression(0), '(green - nir) / (green + nir)');
    await afterDebounce();
    typeInto(expression(0), '(nir - green) / (nir + green)');
    await afterDebounce();
    expect([rescale(), colormap()]).toEqual(['-2.5,6', 'viridis']);
    expect(fields().map((f) => f.value)).toEqual(['-2.5', '6']);
  });

  it('lets the range of the user go first', async () => {
    await openWith(SENTINEL_2_PRESETS);
    click(bandMath());
    typeInto(expression(0), '(green - nir) / (green + nir)');
    await afterDebounce();
    typeInto(fields()[0], '0');
    typeInto(fields()[1], '0.5');
    click([...container.querySelectorAll('button')].find((b) => b.textContent?.trim() === 'Apply')!);
    await afterDebounce();
    expect(rescale()).toBe('0,0.5');
  });

  it('is nothing for the expression of a preset in a dataset that has none', async () => {
    await openWith([]);
    click(bandMath());
    typeInto(expression(0), '(green - nir) / (green + nir)');
    await afterDebounce();
    expect([rescale(), colormap()]).toEqual(['-2.5,6', 'viridis']);
  });
});
