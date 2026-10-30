// @vitest-environment jsdom
//
// "Show": the band of the output the preview draws (NM4-43e PR 2, adr/0020 §10). The dropdown beside the range, the
// band the picture starts with, the assets it reads for a band, and a scale of its own for every band. No backend:
// `fetch` answers the process description, the TileJSON and the statistics.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import { bboxToPolygon } from '../geoUtils';
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
const NDWI = '(green - nir) / (green + nir)';
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
      nir: asset(),
      scl: asset({ gsd: 20, 'raster:bands': [{ data_type: 'uint8', nodata: 0 }] }),
      ...extra,
    },
  };
}

function dataset(): DatasetOption {
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
    } as unknown as Collection,
  };
}

function select(items: StacItem[]) {
  useAppStore.setState({
    datasets: [dataset()],
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
// Reflectance in a range that lies within -1…1 too: it must not be taken for an index.
const REFLECTANCE: Values = { count: 900, min: 0.01, max: 0.9, percentile_2: 0.05, percentile_98: 0.7, unit: null };
const DEM: Values = { count: 900, min: 100, max: 2500, percentile_2: 120, percentile_98: 2400, unit: 'm' };

let container: HTMLDivElement;
let root: Root;
let fetchMock: ReturnType<typeof vi.fn>;
// What the statistics of a scene say, by the band asked.
let statistics: (band: string | null) => Record<string, unknown>;
// What the statistics over the AOI of the order say.
let areaStatistics: (order: { output: { bands: string[] } }) => unknown[];

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  localStorage.clear();
  statistics = () => ({ band: INDEX });
  areaStatistics = () => [];
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/processing/processes/recipe?dataset=sentinel-2-c1-l2a') return json(s2);
    if (init?.method === 'POST' && url.endsWith('/statistics')) {
      const order = JSON.parse(String(init.body));
      return measured({ bands: areaStatistics(order), exact: true, factor: 1 });
    }
    if (url.includes('/tilejson.json')) return json({ tilejson: '3.0.0' });
    if (url.includes('/statistics?')) return measured(statistics(new URL(url, 'http://localhost').searchParams.get('band')));
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

async function openWith(items: StacItem[]) {
  select(items);
  act(() => root.render(<ProcessingPanel />));
  act(() => store().openProcessing());
  await flush();
  vi.useFakeTimers();
}

// One Band math step (NDVI), and the output: the result alone, or with more bands.
async function ndvi(items = [scene('S2B_A')], output: string[] = ['result']) {
  await openWith(items);
  click(button('＋ Band math'));
  typeInto(expression(0), NDVI);
  act(() => store().setOutput(output));
  await afterDebounce();
}

describe('the dropdown "Show"', () => {
  it('is not there while the output holds one band', async () => {
    await ndvi();
    expect(store().preview).not.toBeNull();
    expect(show()).toBeNull();
    expect(section().textContent).not.toContain('Show');
  });

  it('is not there without a picture to choose for', async () => {
    await openWith([scene('S2B_A')]);
    expect(show()).toBeNull();
    act(() => store().setOutput(['red', 'nir']));
    expect(show()).toBeNull();
  });

  it('stands left of min and max, which keep to one row with it', async () => {
    await ndvi(undefined, ['result', 'red']);
    const row = section().querySelector('.pp-range')!;
    expect(row.firstElementChild!.classList.contains('pp-show')).toBe(true);
    expect([...row.querySelectorAll('.vc-field > span')].slice(0, 3).map((s) => s.textContent)).toEqual(['Show', 'min', 'max']);
  });

  it('lists every band of the output, the results above the bands of the data', async () => {
    await openWith([scene('S2B_A')]);
    click(button('＋ Band math'));
    typeInto(expression(0), NDVI);
    click(button('＋ Band math'));
    typeInto(expression(1), NDWI);
    act(() => store().setOutput(['red', 'result_1', 'green', 'result']));
    await afterDebounce();
    expect(options()).toEqual(['result', 'result_1', 'red', 'green']); // the bands of the data in the order of the item
  });

  it('does not list a result that is not in the output, nor a band of the data that is not', async () => {
    await ndvi(undefined, ['result', 'green']);
    click(button('＋ Band math'));
    typeInto(expression(1), NDWI);
    await afterDebounce();
    expect(store().output).toEqual(expect.arrayContaining(['result', 'result_1', 'green']));
    act(() => store().toggleOutput('result_1'));
    await afterDebounce();
    expect(options()).toEqual(['result', 'green']);
  });

  it('starts with the result added last, not the last of the chain', async () => {
    await openWith([scene('S2B_A')]);
    click(button('＋ Band math'));
    typeInto(expression(0), NDVI);
    click(button('＋ Band math'));
    typeInto(expression(1), NDWI);
    act(() => store().setOutput(['result', 'result_1', 'red']));
    await afterDebounce();
    expect(show()!.value).toBe('result_1');
    // The first step moves behind the second: the last of the chain is `result` now, the one added last is still `result_1`.
    act(() => store().moveStep(store().steps[0].key, 1));
    await afterDebounce();
    expect(store().steps.map((s) => s.values.name)).toEqual(['result_1', 'result']);
    expect(show()!.value).toBe('result_1');
    expect(tiles().get('band')).toBe('result_1');
  });

  it('starts with the first band of the output where it holds no result', async () => {
    await openWith([scene('S2B_A')]);
    click(button('＋ Band math'));
    typeInto(expression(0), NDVI);
    act(() => store().setOutput(['red', 'green']));
    await afterDebounce();
    expect(options()).toEqual(['red', 'green']);
    expect(show()!.value).toBe('red');
    expect(tiles().get('band')).toBe('red');
    expect(tiles().getAll('asset')).toEqual(['red']);
  });
});

describe('what the picture reads for the band (adr/0020 §4)', () => {
  it('asks for the band by its name, in the tiles, the TileJSON and the statistics', async () => {
    await ndvi(undefined, ['result', 'red']);
    expect(tiles().get('band')).toBe('result');
    expect(store().preview!.probe).toContain('band=result');
    expect(asked().at(-1)).toContain('band=result');
  });

  it('reads two assets for NDVI from an order of 20 bands, and the picture is there in spite of the limit of the map', async () => {
    const wide = scene('S2B_A', 17);
    await ndvi([wide], ['result', 'red', 'green', 'nir', ...Array.from({ length: 17 }, (_, i) => `b${i + 1}`)]);
    expect(store().output).toHaveLength(21);
    expect(store().preview).not.toBeNull();
    expect(tiles().getAll('asset')).toEqual(['red', 'nir']);
    expect(section().textContent).not.toContain('at most 16');
  });

  it('adds the layer of a mask, and nothing else, to NDVI with a mask (three assets)', async () => {
    const wide = scene('S2B_A', 17);
    await openWith([wide]);
    click(button('＋ Mask'));
    click(button('＋ Band math'));
    typeInto(expression(0), NDVI);
    act(() => store().setOutput(['result', 'red', 'green', ...Array.from({ length: 17 }, (_, i) => `b${i + 1}`)]));
    await afterDebounce();
    expect(tiles().getAll('asset')).toEqual(['red', 'nir', 'scl']);
    expect(tiles().getAll('op')).toEqual(['mask', 'band_math']);
  });

  it('still says there is no picture where one band needs more assets than the map takes', async () => {
    const wide = scene('S2B_A', 17);
    await openWith([wide]);
    click(button('＋ Band math'));
    typeInto(expression(0), Array.from({ length: 17 }, (_, i) => `b${i + 1}`).join(' + '));
    await afterDebounce();
    expect(section().textContent).toContain('No preview: the map takes at most 16 bands.');
    expect(store().preview).toBeNull();
  });

  it('shows a band of the data with the assets of that band alone', async () => {
    await ndvi(undefined, ['result', 'red', 'green']);
    choose(show()!, 'green');
    await afterDebounce();
    expect(tiles().get('band')).toBe('green');
    expect(tiles().getAll('asset')).toEqual(['green']);
    expect(store().preview!.sceneMeasure).toContain('band=green');
  });

  it('shows the band of the second step with the assets of that step', async () => {
    await openWith([scene('S2B_A')]);
    click(button('＋ Band math'));
    typeInto(expression(0), NDVI);
    click(button('＋ Band math'));
    typeInto(expression(1), NDWI);
    act(() => store().setOutput(['result', 'result_1']));
    await afterDebounce();
    expect(tiles().get('band')).toBe('result_1');
    expect(tiles().getAll('asset')).toEqual(['green', 'nir']);
    choose(show()!, 'result');
    await afterDebounce();
    expect(tiles().get('band')).toBe('result');
    expect(tiles().getAll('asset')).toEqual(['red', 'nir']);
  });
});

describe('a scale of its own for every band', () => {
  const rescale = () => tiles().get('rescale');
  const colormap = () => tiles().get('colormap_name');

  beforeEach(() => {
    statistics = (name) => ({ [name ?? 'x']: name === 'result' ? INDEX : name === 'green' ? DEM : REFLECTANCE });
  });

  it('measures and draws again when the band changes, and shows the range of the picture in the fields', async () => {
    await ndvi(undefined, ['result', 'red', 'green']);
    expect([rescale(), colormap()]).toEqual(['-1,1', 'rdylgn']);
    expect(fields().map((f) => f.value)).toEqual(['-1', '1']);
    choose(show()!, 'green');
    await afterDebounce();
    expect([rescale(), colormap()]).toEqual(['120,2400', 'viridis']);
    expect(fields().map((f) => f.value)).toEqual(['120', '2400']);
    expect(section().querySelector('.pp-unit')!.textContent).toBe('m');
  });

  it('takes a band of the data for no index, however small its values are', async () => {
    await ndvi(undefined, ['result', 'red']);
    choose(show()!, 'red');
    await afterDebounce();
    expect([rescale(), colormap()]).toEqual(['0.05,0.7', 'viridis']);
  });

  it('remembers what it measured: back to the first band asks for nothing new', async () => {
    await ndvi(undefined, ['result', 'red']);
    choose(show()!, 'red');
    await afterDebounce();
    const before = asked().length;
    choose(show()!, 'result');
    await afterDebounce();
    expect(asked()).toHaveLength(before);
    expect([rescale(), colormap()]).toEqual(['-1,1', 'rdylgn']);
  });

  it('gives up the range set by hand for another band: "Apply" holds for the band it was made for', async () => {
    await ndvi(undefined, ['result', 'green']);
    typeInto(fields()[0], '0');
    typeInto(fields()[1], '0.5');
    click(button('Apply'));
    await afterDebounce();
    expect(rescale()).toBe('0,0.5');
    choose(show()!, 'green');
    await afterDebounce();
    expect(rescale()).toBe('120,2400');
    expect(store().rangeByHand).toBe(false);
    expect((button('Auto stretch') as HTMLButtonElement).disabled).toBe(true);
  });

  it('measures over the AOI for "AOI only", takes the band from the answer by its name, and asks the order once for all bands', async () => {
    const entry = (name: string, values: Values) => ({
      name,
      unit: null,
      statistics: { count: values.count, minimum: values.min, maximum: values.max, percentile_2: values.percentile_2, percentile_98: values.percentile_98 },
    });
    areaStatistics = () => [entry('result', INDEX), entry('green', DEM), entry('red', REFLECTANCE)];
    await ndvi(undefined, ['result', 'red', 'green']);
    click(button('AOI only'));
    await afterDebounce();
    const posts = () => fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST');
    expect(store().measure).toMatchObject({ source: 'area' });
    expect(rescale()).toBe('-1,1');
    choose(show()!, 'green');
    await afterDebounce();
    expect(store().measure).toMatchObject({ source: 'area' });
    expect(rescale()).toBe('120,2400');
    choose(show()!, 'red');
    await afterDebounce();
    expect(rescale()).toBe('0.05,0.7');
    expect(posts()).toHaveLength(1);
  });

  it('falls back to the first whole scene where the statistics over the AOI do not name the band', async () => {
    areaStatistics = () => [{ name: 'other', unit: null, statistics: { count: 9, minimum: 0, maximum: 1 } }];
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    await ndvi(undefined, ['result', 'red']);
    click(button('AOI only'));
    await afterDebounce();
    expect(store().measure).toMatchObject({ source: 'fallback' });
    warn.mockRestore();
  });
});

describe('what follows from a change of the output', () => {
  it('takes the dropdown away with the second-to-last band, and shows the band that is left', async () => {
    await ndvi(undefined, ['result', 'red']);
    choose(show()!, 'red');
    await afterDebounce();
    expect(tiles().get('band')).toBe('red');
    act(() => store().toggleOutput('red'));
    await afterDebounce();
    expect(show()).toBeNull();
    expect(tiles().get('band')).toBe('result');
  });

  it('falls back to the band added last when the band picked leaves the output, and takes the pick up again if it returns', async () => {
    await ndvi(undefined, ['result', 'red', 'green']);
    choose(show()!, 'red');
    await afterDebounce();
    act(() => store().toggleOutput('red'));
    await afterDebounce();
    expect(show()!.value).toBe('result');
    act(() => store().toggleOutput('red'));
    await afterDebounce();
    expect(show()!.value).toBe('red');
  });

  it('starts over with a new draft', async () => {
    await ndvi(undefined, ['result', 'red']);
    choose(show()!, 'red');
    expect(store().shown).toBe('red');
    act(() => store().resetDraft());
    expect(store().shown).toBeNull();
  });

  it('does not offer a band the map cannot draw: the result of a step after a step that is no tile', async () => {
    await ndvi(undefined, ['result', 'red']);
    expect(store().steps.map((s) => s.op)).toEqual(['band_math']);
    act(() => store().addStep('reproject', 4));
    click(button('＋ Band math'));
    typeInto(expression(1), NDWI);
    act(() => store().setOutput(['result', 'result_1', 'red']));
    await afterDebounce();
    expect(options()).toEqual(['result', 'red']);
    expect(tiles().get('band')).toBe('result');
  });
});
