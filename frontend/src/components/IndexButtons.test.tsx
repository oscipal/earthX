// @vitest-environment jsdom
//
// The row "Index" of the processing panel (NM4-14b, plan §15): one button for each index the dataset offers, which adds an
// ordinary Band math step; and the look of the preview for a band with the expression of a preset (D2). No backend: `fetch`
// answers the process description, the TileJSON and the statistics.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import { SENTINEL_2_PRESETS } from '../fixtures/indexPresets';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import { bboxToPolygon } from '../geoUtils';
import { canonicalJson } from '../processing';
import { orderView, useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection, StacItem } from '../types';
import ProcessingPanel from './ProcessingPanel';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const AOI = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);
const NDVI = '(nir - red) / (nir + red)';
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
const row = () => container.querySelector<HTMLElement>('[role="group"][aria-label="Add index"]');
const buttons = () => [...(row()?.querySelectorAll('button') ?? [])];
const index = (name: string) => buttons().find((b) => b.textContent === `＋ ${name}`)!;
const bandMath = () => [...container.querySelectorAll('button')].find((b) => b.textContent?.trim() === '＋ Band math')!;
const click = (element: HTMLElement) => act(() => element.dispatchEvent(new MouseEvent('click', { bubbles: true })));
const expression = (at: number) => container.querySelectorAll<HTMLTextAreaElement>('textarea[id$="-expression"]')[at]!;
const section = () => container.querySelector('section[aria-label="Preview on the map"]')!;
const fields = () => [...section().querySelectorAll<HTMLInputElement>('input[type="number"]')];
const tiles = () => new URL(store().preview!.scenes[0].url, 'http://localhost').searchParams;
const order = () => orderView(useAppStore.getState(), store()).parts[0].order;

function typeInto(input: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const prototype = input instanceof HTMLTextAreaElement ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  act(() => {
    Object.getOwnPropertyDescriptor(prototype, 'value')!.set!.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

describe('the row "Index"', () => {
  it('has a button for each preset of the dataset, in the order of the registry, under "Add step"', async () => {
    await openWith(SENTINEL_2_PRESETS);
    expect(buttons().map((b) => b.textContent)).toEqual(['＋ NDVI', '＋ NDWI', '＋ NDSI', '＋ NBR', '＋ EVI']);
    const add = container.querySelector('[role="group"][aria-label="Add step"]')!;
    expect(add.nextElementSibling).toBe(row());
  });

  it.each([
    ['an empty list (the DEM)', []],
    ['no field (a backend before NM4-14a)', undefined],
    ['a field that is no list', 'NDVI'],
    ['entries that are all broken', [{ name: 'NDVI' }, null]],
  ])('is not there for %s', async (_, presets) => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    await openWith(presets);
    expect(row()).toBeNull();
    expect(container.textContent).not.toContain('Index:');
    expect(container.querySelector('[role="group"][aria-label="Add step"]')).not.toBeNull();
  });

  it('is not there where the description has no Band math of version 2', async () => {
    const without = JSON.parse(JSON.stringify(s2));
    const steps = without.inputs.recipe.schema.properties.steps;
    steps.items.oneOf = steps.items.oneOf.filter((o: { $ref: string }) => !o.$ref.endsWith('step_band_math_v2'));
    fetchMock.mockImplementation(async (url: string) => (url.startsWith('/processing/processes/') ? json(without) : new Response('{}', { status: 404 })));
    await openWith(SENTINEL_2_PRESETS);
    expect(container.querySelector('[role="group"][aria-label="Add step"]')).not.toBeNull();
    expect(row()).toBeNull();
  });

  it('says what an index is in the tooltip and to a screen reader, and writes no text beside the buttons', async () => {
    await openWith(SENTINEL_2_PRESETS);
    const tip = 'Normalized Difference Vegetation Index: (N - R)/(N + R). Formula: Awesome Spectral Indices.';
    expect(index('NDVI').title).toBe(tip);
    expect(index('NDVI').getAttribute('aria-label')).toBe(`NDVI. ${tip}`);
    expect(index('NDWI').title).toContain('(McFeeters 1996)');
    // The label and the buttons: nothing else, and the source is no link.
    expect(row()!.textContent).toBe('Index:＋ NDVI＋ NDWI＋ NDSI＋ NBR＋ EVI');
    expect(row()!.querySelector('a')).toBeNull();
  });
});

describe('a click', () => {
  it('adds the same Band math step as the expression typed by hand, and the same order', async () => {
    await openWith(SENTINEL_2_PRESETS);
    click(index('NDVI'));
    await flush();
    const clicked = order();
    expect(store().steps).toHaveLength(1);
    expect(store().steps[0]).toMatchObject({ op: 'band_math', opVersion: 2, values: { expression: NDVI, name: 'NDVI' } });

    store().resetDraft();
    click(bandMath());
    typeInto(expression(0), NDVI);
    act(() => store().renameResult(store().steps[0].key, 'NDVI'));
    await flush();
    expect(store().steps[0].values).toEqual(expect.objectContaining({ expression: NDVI, name: 'NDVI' }));
    expect(clicked).not.toBeNull();
    expect(canonicalJson(clicked)).toBe(canonicalJson(order()));
  });

  it('puts the new band into the output and shows it', async () => {
    await openWith(SENTINEL_2_PRESETS);
    click(index('NDWI'));
    await afterDebounce();
    expect(store().output).toContain('NDWI');
    expect(store().preview!.band).toBe('NDWI');
    expect(tiles().get('band')).toBe('NDWI');
  });

  it('is an ordinary step afterwards: the expression and the name can be changed', async () => {
    await openWith(SENTINEL_2_PRESETS);
    click(index('NDVI'));
    typeInto(expression(0), '(nir - red) / (nir + red + 0.5)');
    act(() => store().renameResult(store().steps[0].key, 'SAVI'));
    expect(store().steps[0].values).toMatchObject({ expression: '(nir - red) / (nir + red + 0.5)', name: 'SAVI' });
    expect(store().output).toContain('SAVI');
    expect(store().output).not.toContain('NDVI');
  });

  it('numbers the name on a second click: two clicks are two steps and two bands', async () => {
    await openWith(SENTINEL_2_PRESETS);
    click(index('NDVI'));
    click(index('NDVI'));
    click(index('NDWI'));
    click(index('NDVI'));
    await afterDebounce();
    expect(store().steps.map((s) => s.values.name)).toEqual(['NDVI', 'NDVI_2', 'NDWI', 'NDVI_3']);
    expect(store().output).toEqual(expect.arrayContaining(['NDVI', 'NDVI_2', 'NDWI', 'NDVI_3']));
    expect(store().preview!.band).toBe('NDVI_3');
  });

  it('numbers the name where a step was renamed to it in another case', async () => {
    await openWith(SENTINEL_2_PRESETS);
    click(bandMath());
    act(() => store().renameResult(store().steps[0].key, 'ndvi'));
    click(index('NDVI'));
    expect(store().steps.map((s) => s.values.name)).toEqual(['ndvi', 'NDVI_2']);
  });

  it('is locked where the steps are full, with the reason, and adds nothing', async () => {
    await openWith(SENTINEL_2_PRESETS);
    const { maxSteps } = orderView(useAppStore.getState(), store()).info!;
    for (let n = 0; n < maxSteps; n++) click(index('NDVI'));
    expect(store().steps).toHaveLength(maxSteps);
    expect(buttons().every((b) => b.disabled)).toBe(true);
    expect(index('EVI').title).toBe(`At most ${maxSteps} steps`);
    expect(index('EVI').getAttribute('aria-label')).toBe(`EVI. At most ${maxSteps} steps`);
    click(index('EVI'));
    expect(store().steps).toHaveLength(maxSteps);
  });

  it('is locked while a name breaks a rule, as "＋ Band math" is', async () => {
    await openWith(SENTINEL_2_PRESETS);
    click(index('NDVI'));
    act(() => store().setNameProblem(store().steps[0].key, 'Use letters, digits and _'));
    expect(bandMath().hasAttribute('disabled')).toBe(true);
    expect(buttons().every((b) => b.disabled)).toBe(true);
    expect(index('NDVI').title).toBe(orderView(useAppStore.getState(), store()).nameBlock);
  });
});
