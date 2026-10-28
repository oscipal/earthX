// @vitest-environment jsdom
//
// The map preview of the processing panel (M4-13c-2): the section of the panel,
// the "Preview" badge, the preview as a layer, and the ways into the panel from
// the layer manager and the full-resolution view. No backend: `fetch` answers the
// process description only; the tiles are never requested (the map is not here).

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import type { MapLayer } from '../layers';
import { layerProcessBlock, orderView, useProcessingStore } from '../processingStore';
import { bboxToPolygon } from '../geoUtils';
import { useAppStore } from '../store';
import type { Collection, DownloadedInfo, StacItem } from '../types';
import LayerManager from './LayerManager';
import PreviewBadge from './PreviewBadge';
import ProcessingPanel from './ProcessingPanel';
import ViewBar from './ViewBar';
import ViewerControls from './ViewerControls';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const AOI = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);

function scene(id: string, gsd: number | null = 10): StacItem {
  const bbox: [number, number, number, number] = [10, 50, 11, 51];
  return {
    id,
    collection: 'sentinel-2-c1-l2a',
    bbox,
    geometry: bboxToPolygon(bbox),
    properties: { datetime: '2026-07-01T10:00:00Z', ...(gsd ? { gsd } : {}) },
    assets: {
      red: { href: 'https://example.org/red.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
      nir: { href: 'https://example.org/nir.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
    },
  };
}

function dataset(tier = 'processing'): DatasetOption {
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
      'earthx:license_flags': { tier },
      'earthx:capabilities': { interpolation: true },
    } as unknown as Collection,
  };
}

function select(items: StacItem[], tier = 'processing') {
  useAppStore.setState({
    datasets: [dataset(tier)],
    datasetId: 'sentinel-2-c1-l2a',
    items,
    groups: [{ key: ['2026-07-01'], label: '2026-07-01', items }],
    activeGroupIndex: 0,
    selectedIds: items.map((i) => i.id),
    aoi: AOI,
    aoiPoint: null,
    layers: [],
    focusMode: false,
    error: null,
  });
}

function pinned(id: string, over: Partial<MapLayer['restore']> = {}, layer: Partial<MapLayer> = {}): MapLayer {
  return {
    id,
    name: `Layer ${id}`,
    visible: true,
    opacity: 1,
    overlays: [],
    restore: {
      focusMode: false,
      downloaded: {},
      appliedRender: {},
      activeGroupIndex: 0,
      selectedIds: ['S2B_A'],
      itemIds: ['S2B_A'],
      groupItemIds: [['S2B_A']],
      aoi: AOI,
      cropToAoi: false,
      datasetId: 'sentinel-2-c1-l2a',
      ...over,
    },
    ...layer,
  };
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

let container: HTMLDivElement;
let root: Root;
// The catalog behind `/stac/.../items/<id>`: a scene, or the status it answers with.
let catalog: Record<string, StacItem | number>;
// Requests held back until a test answers them.
let pending: Record<string, Promise<Response> | undefined>;
let fetchMock: ReturnType<typeof vi.fn>;
// What the tiler answers to the TileJSON of a chain (the question of `probeChain`): the chain is fine by default.
let tilejson: (url: string) => Response;
// What it answers to the statistics of the steps (the measure of the preview): the values of an index by default.
let statistics: (url: string) => Response;
const INDEX_VALUES = { count: 900, min: -0.2, max: 0.9, percentile_2: -0.1, percentile_98: 0.8, unit: null };
// Answers at once, with no stream to wait for: a test settles the preview in microtasks.
const measured = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as Response;
const ITEM_URL = '/stac/collections/sentinel-2-c1-l2a/items/';

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  localStorage.clear();
  catalog = {};
  pending = {};
  tilejson = () => json({ tilejson: '3.0.0' });
  statistics = () => measured({ b1: INDEX_VALUES });
  fetchMock = vi.fn(async (url: string) => {
    if (url === '/processing/processes/recipe?dataset=sentinel-2-c1-l2a') return json(s2);
    if (url.includes('/tilejson.json')) return tilejson(url);
    if (url.includes('/statistics?')) return statistics(url);
    if (pending[url]) return pending[url];
    if (url.startsWith(ITEM_URL)) {
      const entry = catalog[decodeURIComponent(url.slice(ITEM_URL.length))];
      if (typeof entry === 'object') return json(entry);
      return new Response(JSON.stringify({ title: 'Refused', detail: 'the catalog is down' }), {
        status: entry ?? 404,
        headers: { 'Content-Type': 'application/problem+json' },
      });
    }
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

function mount(node = <ProcessingPanel />) {
  act(() => root.render(node));
}

async function openPanel() {
  mount();
  act(() => useProcessingStore.getState().openProcessing());
  await flush();
}

function button(label: string | RegExp, within: Element = container): HTMLButtonElement {
  const found = [...within.querySelectorAll('button')].find((b) =>
    typeof label === 'string' ? b.textContent?.trim() === label : label.test(b.textContent ?? ''),
  );
  if (!found) throw new Error(`no button ${String(label)} in ${container.textContent}`);
  return found as HTMLButtonElement;
}

function click(element: HTMLElement) {
  act(() => element.dispatchEvent(new MouseEvent('click', { bubbles: true })));
}

function typeInto(input: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const prototype = input instanceof HTMLTextAreaElement ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, 'value')!.set!;
  act(() => {
    setter.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

const expression = (index = 0) => container.querySelectorAll<HTMLTextAreaElement>('textarea[id$="-expression"]')[index]!;
const section = () => container.querySelector('section[aria-label="Preview on the map"]')!;
const store = () => useProcessingStore.getState();

// The preview follows 400 ms after the last change: real timers up to here (the
// description is fetched), fake ones for the wait.
async function afterDebounce() {
  act(() => {
    vi.advanceTimersByTime(400);
  });
  await flush();
}

async function withNdvi(items = [scene('S2B_A')]) {
  select(items);
  await openPanel();
  vi.useFakeTimers();
  click(button('＋ Band math'));
  typeInto(expression(), '(nir - red) / (nir + red)');
  await afterDebounce();
}

describe('the preview section', () => {
  it('says nothing before there is a step, and asks to complete the first one', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    expect(section().querySelector('.hint-text')).toBeNull();
    expect(section().querySelector('.pp-range')).toBeNull();
    click(button('＋ Band math'));
    expect(section().textContent).toContain('Complete the step to see the preview.');
    expect(store().preview).toBeNull();
  });

  it('shows the first step on every scene of the order, 400 ms after the last input', async () => {
    select([scene('S2B_A'), scene('S2B_B')]);
    await openPanel();
    vi.useFakeTimers();
    click(button('＋ Band math'));
    typeInto(expression(), 'nir / red');
    act(() => {
      vi.advanceTimersByTime(399);
    });
    expect(store().preview).toBeNull();
    typeInto(expression(), '(nir - red) / (nir + red)');
    act(() => {
      vi.advanceTimersByTime(399);
    });
    expect(store().preview).toBeNull(); // the typing started the wait again
    act(() => {
      vi.advanceTimersByTime(1);
    });
    await flush();
    const preview = store().preview!;
    expect(preview.scenes.map((s) => s.id)).toEqual(['S2B_A', 'S2B_B']);
    const params = new URL(preview.scenes[0].url, 'http://localhost').searchParams;
    expect(params.getAll('asset')).toEqual(['red', 'nir']);
    expect(params.get('op')).toBe('band_math');
    expect(JSON.parse(params.get('params')!)).toEqual({ expression: '(nir - red) / (nir + red)' });
    expect(params.get('rescale')).toBe('-1,1');
    expect(params.get('colormap_name')).toBe('rdylgn');
    expect(section().textContent).toContain('Where scenes overlap');
  });

  it('is cut to the AOI only for "AOI only"', async () => {
    await withNdvi();
    expect(store().preview!.clipToAoi).toBe(false);
    click(button('AOI only'));
    await afterDebounce();
    expect(store().preview!.clipToAoi).toBe(true);
    expect(store().preview!.scenes[0].url).not.toContain('10.4');
  });

  it('takes the picture away at once when the step is taken out or the panel closes', async () => {
    await withNdvi();
    expect(store().preview).not.toBeNull();
    typeInto(expression(), '');
    expect(store().preview).toBeNull();
    typeInto(expression(), 'nir / red');
    await afterDebounce();
    expect(store().preview).not.toBeNull();
    act(() => store().closeProcessing());
    expect(store().preview).toBeNull();
  });

  it('draws no picture of the draft while the details of a job are shown, and draws it again with the order', async () => {
    await withNdvi();
    act(() => useProcessingStore.setState({ jobs: [{ jobID: 'Job0000000000000000001' } as never] }));
    act(() => store().openJobDetails('Job0000000000000000001'));
    expect(store().preview).toBeNull();
    act(() => store().closeJobDetails());
    await afterDebounce();
    expect(store().preview).not.toBeNull();
  });

  it('drops the picture with the draft when the dataset changes', async () => {
    await withNdvi();
    act(() => useAppStore.setState({ datasetId: 'other' }));
    expect(store().preview).toBeNull();
    expect(store().steps).toEqual([]);
  });

  it('does not draw a picture that was still due when the panel closes or the dataset changes', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    vi.useFakeTimers();
    click(button('＋ Band math'));
    typeInto(expression(), 'nir / red');
    act(() => store().closeProcessing());
    await afterDebounce();
    expect(store().preview).toBeNull();

    act(() => store().openProcessing());
    typeInto(expression(), 'nir / red');
    act(() => useAppStore.setState({ datasetId: 'other' }));
    await afterDebounce();
    expect(store().preview).toBeNull();
  });

  it('keeps the picture it has when the input comes back to it within 400 ms', async () => {
    await withNdvi();
    const before = store().preview;
    typeInto(expression(), 'nir / red');
    act(() => {
      vi.advanceTimersByTime(300);
    });
    typeInto(expression(), '(nir - red) / (nir + red)');
    await afterDebounce();
    expect(store().preview).toBe(before);
  });

  it('takes the picture away at once when the AOI of "AOI only" goes, and leaves it for "Whole scene"', async () => {
    await withNdvi();
    const before = store().preview;
    act(() => useAppStore.setState({ aoi: bboxToPolygon([10.1, 50.1, 10.2, 50.2]) }));
    await afterDebounce();
    expect(store().preview).toBe(before); // "Whole scene" does not read the AOI
    click(button('AOI only'));
    await afterDebounce();
    expect(store().preview!.clipToAoi).toBe(true);
    act(() => useAppStore.setState({ aoi: null }));
    expect(store().preview).toBeNull();
  });

  it('says why there is no picture for more bands than the map takes', async () => {
    const wide = scene('S2B_A');
    for (let i = 1; i <= 17; i++) wide.assets[`b${i}`] = { href: 'https://example.org/b.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] };
    select([wide]);
    await openPanel();
    click(button('＋ Band math'));
    typeInto(expression(), Array.from({ length: 17 }, (_, i) => `b${i + 1}`).join(' + '));
    expect(section().textContent).toContain('No preview: the map takes at most 16 bands.');
    expect(store().preview).toBeNull();
  });

  it('asks for a pass while the scenes belong to several', async () => {
    const a = scene('S2B_A');
    const b = scene('S2B_B');
    select([a, b]);
    useAppStore.setState({
      groups: [
        { key: ['2026-07-02'], label: '2026-07-02', items: [b] },
        { key: ['2026-07-01'], label: '2026-07-01', items: [a] },
      ],
    });
    await openPanel();
    click(button('＋ Band math'));
    typeInto(expression(), 'nir / red');
    expect(section().textContent).toContain('Choose a pass to see the preview.');
    expect(store().preview).toBeNull();
  });

  it('shows a reason, no controls and no picture when the first step runs only as a job', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    vi.useFakeTimers();
    click(button('＋ Reproject and resample'));
    click(button('＋ Band math'));
    typeInto(expression(), 'nir / red');
    await afterDebounce();
    expect(section().textContent).toContain('No preview: the first step runs only as a job.');
    expect(section().querySelector('.pp-range')).toBeNull();
    expect(store().preview).toBeNull();
  });

  it('says the job runs all steps while the map shows the first', async () => {
    await withNdvi();
    expect(section().textContent).not.toContain('the job runs all steps');
    click(button('＋ Band math'));
    expect(section().textContent).toContain('The map shows the first step; the job runs all steps.');
    expect(store().preview!.title).toBe('Band math');
  });

  async function chainOfTwo(): Promise<void> {
    await withNdvi();
    click(button('＋ Band math'));
    typeInto(expression(1), 'red + 1');
    await afterDebounce();
    await flush();
  }

  const refusal = (detail: string) => () =>
    new Response(JSON.stringify({ detail }), { status: 422, headers: { 'Content-Type': 'application/json' } });

  it('draws a chain of tile steps and counts what the map leaves out', async () => {
    await withNdvi();
    const normalize = { key: 900, op: 'normalize', opVersion: 1, values: { in_min: '-1', in_max: '1', out_min: '0', out_max: '255', clip: true } };
    act(() => useProcessingStore.setState({ steps: [...store().steps, normalize] }));
    await afterDebounce();
    await flush();
    expect(store().preview!.title).toBe('Band math → Normalize');
    expect(store().previewNote).toBeNull();
    const url = new URL(store().preview!.scenes[0].url, 'http://localhost');
    expect(url.searchParams.getAll('op')).toEqual(['band_math', 'normalize']);
    expect(section().textContent).not.toContain('the job runs all steps');
    click(button('＋ Band math'));
    expect(section().textContent).toContain('The map shows the first 2 steps; the job runs all steps.');
    expect(store().preview!.title).toBe('Band math → Normalize');
  });

  const asks = (part: string) => fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.includes(part));
  const refusal400 = (detail: unknown) => () =>
    new Response(JSON.stringify({ detail }), { status: 400, headers: { 'Content-Type': 'application/json' } });
  const NOT_VALID = 'params: expression: Value error, expression: not a valid expression';

  it('asks the tiler about a chain with the TileJSON of the same chain, one step as well as several', async () => {
    await withNdvi();
    expect(asks('/tilejson.json')).toHaveLength(1);
    expect(new URL(asks('/tilejson.json')[0], 'http://localhost').searchParams.getAll('op')).toEqual(['band_math']);
    await chainOfTwo();
    const asked = asks('/tilejson.json');
    expect(asked).toHaveLength(2);
    const query = new URL(asked[1], 'http://localhost').searchParams;
    expect(query.getAll('op')).toEqual(['band_math', 'band_math']);
    expect(query.getAll('params')).toHaveLength(2);
    expect(store().preview!.stepCount).toBe(2);
  });

  it('asks the TileJSON of a single step before its statistics, and goes on to both when the tiler takes it', async () => {
    await withNdvi();
    expect(asks('/tilejson.json')).toHaveLength(1);
    expect(asks('/statistics?')).toHaveLength(1);
    expect(fetchMock.mock.calls.findIndex(([u]) => String(u).includes('/tilejson.json'))).toBeLessThan(
      fetchMock.mock.calls.findIndex(([u]) => String(u).includes('/statistics?')),
    );
    expect(store().preview!.scenes).toHaveLength(1);
    expect(store().previewNote).toBeNull();
  });

  it('asks neither the statistics nor the tiles of a single step the tiler refuses, and shows why', async () => {
    tilejson = refusal400(NOT_VALID);
    await withNdvi();
    expect(asks('/tilejson.json')).toHaveLength(1);
    expect(asks('/statistics?')).toHaveLength(0);
    expect(store().preview).toBeNull();
    expect(store().previewNote).toBe(`No preview: ${NOT_VALID}.`);
    expect(section().textContent).toContain(`No preview: ${NOT_VALID}.`);
  });

  it('shows a refusal of a single step with status 422 as well', async () => {
    tilejson = refusal("the operator 'band_math' does not apply to this input");
    await withNdvi();
    expect(asks('/statistics?')).toHaveLength(0);
    expect(store().preview).toBeNull();
    expect(store().previewNote).toBe("No preview: the operator 'band_math' does not apply to this input.");
  });

  it('draws the single step again, with no note, once the expression is fixed', async () => {
    tilejson = refusal400(NOT_VALID);
    await withNdvi();
    tilejson = () => json({ tilejson: '3.0.0' });
    typeInto(expression(), 'nir / red');
    await afterDebounce();
    expect(store().preview).not.toBeNull();
    expect(store().previewNote).toBeNull();
    expect(asks('/tilejson.json')).toHaveLength(2);
    expect(asks('/statistics?')).toHaveLength(1);
  });

  it('keeps no answer for a single step the source fails on, draws it and asks again on the next change', async () => {
    tilejson = () => new Response('{"detail":"the asset could not be read from the source"}', { status: 502 });
    await withNdvi();
    expect(store().preview).not.toBeNull();
    expect(store().previewNote).toBeNull();
    expect(asks('/statistics?')).toHaveLength(1);
    act(() => useProcessingStore.setState({ range: { vmin: '0', vmax: '1', colormap: 'viridis' }, rangeByHand: true }));
    await afterDebounce();
    expect(asks('/tilejson.json')).toHaveLength(2);
  });

  it('draws a single step with no answer to go by when the text of the refusal is no text', async () => {
    tilejson = () => new Response('{"detail":[{"msg":"x"}]}', { status: 422 });
    await withNdvi();
    expect(store().preview).not.toBeNull();
    expect(store().previewNote).toBeNull();
  });

  it('does not ask the tiler again when only the colour range changes, for a chain it takes or one it refuses', async () => {
    await withNdvi();
    act(() => useProcessingStore.setState({ range: { vmin: '0', vmax: '1', colormap: 'viridis' }, rangeByHand: true }));
    await afterDebounce();
    expect(new URL(store().preview!.scenes[0].url, 'http://localhost').searchParams.get('colormap_name')).toBe('viridis');
    expect(asks('/tilejson.json')).toHaveLength(1);

    tilejson = refusal400(NOT_VALID);
    typeInto(expression(), 'nir / red');
    await afterDebounce();
    expect(asks('/tilejson.json')).toHaveLength(2);
    expect(store().previewNote).toBe(`No preview: ${NOT_VALID}.`);
    act(() => useProcessingStore.setState({ range: { vmin: '-1', vmax: '1', colormap: 'rdylgn' }, rangeByHand: true }));
    await afterDebounce();
    expect(asks('/tilejson.json')).toHaveLength(2);
    expect(asks('/statistics?')).toHaveLength(1);
    expect(store().previewNote).toBe(`No preview: ${NOT_VALID}.`);
  });

  it('shows the steps before the one the tiler refuses, and its reason', async () => {
    tilejson = refusal('step 1: expression names unknown band(s): red; the input has: band_math');
    await chainOfTwo();
    expect(store().preview!.stepCount).toBe(1);
    expect(store().previewNote).toBe(
      'Preview shows step 1 of 2. Step 2: expression names unknown band(s): red; the input has: band_math.',
    );
    expect(section().textContent).toContain('Preview shows step 1 of 2. Step 2: expression names unknown band(s): red');
    const url = new URL(store().preview!.scenes[0].url, 'http://localhost');
    expect(url.searchParams.getAll('op')).toEqual(['band_math']);
  });

  it('shows no picture, and the reason, when the tiler refuses the first step of a chain', async () => {
    tilejson = refusal('step 0: expression names unknown band(s): green; the input has: red, nir');
    await chainOfTwo();
    expect(store().preview).toBeNull();
    expect(store().previewNote).toBe('No preview. Step 1: expression names unknown band(s): green; the input has: red, nir.');
  });

  it('keeps the whole chain when the answer names no step, and drops the note when the chain is fixed', async () => {
    tilejson = () => new Response('{"detail":"the asset could not be read from the source"}', { status: 502 });
    await chainOfTwo();
    expect(store().preview!.stepCount).toBe(2);
    expect(store().previewNote).toBeNull();
    tilejson = refusal('step 1: expression names unknown band(s): red; the input has: band_math');
    typeInto(expression(1), 'red + 2');
    await afterDebounce();
    await flush();
    expect(store().previewNote).toContain('Preview shows step 1 of 2');
    tilejson = () => json({ tilejson: '3.0.0' });
    typeInto(expression(1), 'band_math + 1');
    await afterDebounce();
    await flush();
    expect(store().preview!.stepCount).toBe(2);
    expect(store().previewNote).toBeNull();
  });

  it('asks for a band when none is named', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    click(button('＋ Band math'));
    typeInto(expression(), '1 + 1');
    expect(section().textContent).toContain('Pick a band, or name it in the expression, to see the preview.');
    expect(store().preview).toBeNull();
  });

  describe('range and colormap (F3 (1))', () => {
    const inputs = () => [...section().querySelectorAll<HTMLInputElement>('input[type="number"]')];

    it('starts at -1 to 1 with rdylgn and draws a new range only after "Apply"', async () => {
      await withNdvi();
      expect(inputs().map((i) => i.value)).toEqual(['-1', '1']);
      expect(section().querySelector('select')!.value).toBe('rdylgn');
      typeInto(inputs()[1], '0.8');
      await afterDebounce();
      expect(new URL(store().preview!.scenes[0].url, 'http://localhost').searchParams.get('rescale')).toBe('-1,1');
      click(button('Apply'));
      await afterDebounce();
      expect(new URL(store().preview!.scenes[0].url, 'http://localhost').searchParams.get('rescale')).toBe('-1,0.8');
    });

    it('refuses a range that is no range, and keeps the picture it has', async () => {
      await withNdvi();
      typeInto(inputs()[0], '2');
      expect(section().textContent).toContain('The lower end of the range must be below the upper end.');
      expect(button('Apply').disabled).toBe(true);
      typeInto(inputs()[0], '');
      expect(section().textContent).toContain('Enter a number for both ends of the range.');
      expect(store().range).toEqual({ vmin: '-1', vmax: '1', colormap: 'rdylgn' });
      expect(store().preview).not.toBeNull();
    });

    it('takes another colormap, or none', async () => {
      await withNdvi();
      const select_ = section().querySelector('select')!;
      act(() => {
        const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')!.set!;
        setter.call(select_, '');
        select_.dispatchEvent(new Event('change', { bubbles: true }));
      });
      click(button('Apply'));
      await afterDebounce();
      expect(new URL(store().preview!.scenes[0].url, 'http://localhost').searchParams.has('colormap_name')).toBe(false);
    });

  });

  // M4-19c: the range of a preview is measured once, on the first scene, and chosen by the rule of a result's.
  describe('the measured range and the unit (M4-19c)', () => {
    const inputs = () => [...section().querySelectorAll<HTMLInputElement>('input[type="number"]')];
    const asked = () => fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.includes('/statistics?'));
    const rescale = () => new URL(store().preview!.scenes[0].url, 'http://localhost').searchParams.get('rescale');
    const colormap = () => new URL(store().preview!.scenes[0].url, 'http://localhost').searchParams.get('colormap_name');
    const unit = () => section().querySelector('.pp-unit')?.textContent ?? null;
    const DEM_VALUES = { count: 900, min: 100, max: 2500, percentile_2: 120, percentile_98: 2400, unit: 'm' };

    it('asks the statistics of the first scene with the steps of the preview, once, and draws a flat index at -1 to 1', async () => {
      await withNdvi([scene('S2B_A'), scene('S2B_B')]);
      expect(asked()).toHaveLength(1);
      const query = new URL(asked()[0], 'http://localhost');
      expect(query.pathname).toBe('/collections/sentinel-2-c1-l2a/items/S2B_A/statistics');
      expect(query.searchParams.getAll('asset')).toEqual(['red', 'nir']);
      expect(query.searchParams.get('op')).toBe('band_math');
      expect(query.searchParams.has('rescale')).toBe(false);
      expect([rescale(), colormap()]).toEqual(['-1,1', 'rdylgn']);
    });

    it('draws other values at their 2nd to 98th percentile in viridis, and shows that in the fields', async () => {
      statistics = () => measured({ b1: DEM_VALUES });
      await withNdvi();
      expect([rescale(), colormap()]).toEqual(['120,2400', 'viridis']);
      expect(inputs().map((i) => i.value)).toEqual(['120', '2400']);
      expect(section().querySelector('select')!.value).toBe('viridis');
      expect(store().range).toEqual({ vmin: '-1', vmax: '1', colormap: 'rdylgn' }); // no choice of the user's
    });

    it('draws a preview once, with the measure, and not first with the start range', async () => {
      statistics = () => measured({ b1: DEM_VALUES });
      await withNdvi();
      const seen: Array<string | null> = [];
      useProcessingStore.subscribe((s) => seen.push(s.preview && new URL(s.preview.scenes[0].url, 'http://localhost').searchParams.get('rescale')));
      typeInto(expression(), 'nir / red');
      await afterDebounce();
      expect(new Set(seen.filter((r) => r !== null))).toEqual(new Set(['120,2400']));
    });

    it('measures a state once: a range typed, applied or an expression typed back asks for no new measure', async () => {
      await withNdvi();
      typeInto(inputs()[1], '0.8');
      click(button('Apply'));
      await afterDebounce();
      typeInto(expression(), 'nir / red');
      await afterDebounce();
      expect(asked()).toHaveLength(2);
      typeInto(expression(), '(nir - red) / (nir + red)');
      await afterDebounce();
      expect(asked()).toHaveLength(2);
    });

    it('holds the range the user applied against the measure, and shows its picture at once', async () => {
      await withNdvi();
      typeInto(inputs()[1], '0.8');
      click(button('Apply'));
      statistics = () => new Promise<Response>(() => {}) as unknown as Response; // a measure that does not come
      typeInto(expression(), 'nir / red');
      await afterDebounce();
      expect(rescale()).toBe('-1,0.8');
      expect(store().range).toEqual({ vmin: '-1', vmax: '0.8', colormap: 'rdylgn' });
    });

    it('keeps the range of the user across expressions, and "Auto stretch" gives the measure back', async () => {
      statistics = () => measured({ b1: DEM_VALUES });
      await withNdvi();
      typeInto(inputs()[0], '0');
      typeInto(inputs()[1], '5');
      click(button('Apply'));
      await afterDebounce();
      typeInto(expression(), 'nir / red');
      await afterDebounce();
      expect(rescale()).toBe('0,5');
      click(button('Auto stretch'));
      await afterDebounce();
      expect([rescale(), colormap()]).toEqual(['120,2400', 'viridis']);
      expect(inputs().map((i) => i.value)).toEqual(['120', '2400']);
      expect(button('Auto stretch').disabled).toBe(true);
    });

    it('does not write over what the user is typing when the measure arrives', async () => {
      let answer!: (response: Response) => void;
      statistics = () => new Promise<Response>((resolve) => (answer = resolve)) as unknown as Response;
      select([scene('S2B_A')]);
      await openPanel();
      vi.useFakeTimers();
      click(button('＋ Band math'));
      typeInto(expression(), 'nir / red');
      act(() => {
        vi.advanceTimersByTime(400);
      });
      await flush(); // the TileJSON first, then the statistics
      typeInto(inputs()[1], '3');
      await act(async () => answer(measured({ b1: DEM_VALUES })));
      await flush();
      expect(inputs().map((i) => i.value)).toEqual(['-1', '3']);
      expect(rescale()).toBe('120,2400');
    });

    it('draws the start range once the user applies it against a measure, and lets Auto stretch take it back', async () => {
      statistics = () => measured({ b1: DEM_VALUES });
      await withNdvi();
      expect(rescale()).toBe('120,2400');
      typeInto(inputs()[0], '-1');
      typeInto(inputs()[1], '1');
      const select_ = section().querySelector('select')!;
      act(() => {
        const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')!.set!;
        setter.call(select_, 'rdylgn');
        select_.dispatchEvent(new Event('change', { bubbles: true }));
      });
      click(button('Apply'));
      await afterDebounce();
      expect([rescale(), colormap()]).toEqual(['-1,1', 'rdylgn']);
      expect(button('Auto stretch').disabled).toBe(false);
      click(button('Auto stretch'));
      await afterDebounce();
      expect(rescale()).toBe('120,2400');
    });

    it('does not take the measure of the formula before for the one typed while the 400 ms run', async () => {
      let answer!: (response: Response) => void;
      statistics = () => new Promise<Response>((resolve) => (answer = resolve)) as unknown as Response;
      select([scene('S2B_A')]);
      await openPanel();
      vi.useFakeTimers();
      click(button('＋ Band math'));
      typeInto(expression(), 'nir - red');
      await afterDebounce();
      typeInto(expression(), 'nir / red'); // inside the 400 ms of the next picture
      await act(async () => answer(measured({ b1: DEM_VALUES })));
      await flush();
      expect(store().preview).toBeNull();
      expect(store().measure).toBeNull();
      expect(inputs().map((i) => i.value)).toEqual(['-1', '1']);
    });

    describe('a measure that is slow (the longest wait is 5 s)', () => {
      let answer!: (response: Response) => void;
      const slow = () => {
        statistics = () => new Promise<Response>((resolve) => (answer = resolve)) as unknown as Response;
      };
      const drawn = () => {
        const seen: Array<string | null> = [];
        useProcessingStore.subscribe((s, prev) => {
          if (s.preview !== prev.preview) seen.push(s.preview && new URL(s.preview.scenes[0].url, 'http://localhost').searchParams.get('rescale'));
        });
        return seen;
      };
      const start = async () => {
        select([scene('S2B_A')]);
        await openPanel();
        vi.useFakeTimers();
        const seen = drawn();
        click(button('＋ Band math'));
        typeInto(expression(), 'nir / red');
        await afterDebounce();
        return seen;
      };

      it('draws nothing before the wait is over, then the start range', async () => {
        slow();
        const seen = await start();
        act(() => {
          vi.advanceTimersByTime(4999);
        });
        expect(seen).toEqual([]);
        act(() => {
          vi.advanceTimersByTime(1);
        });
        await flush();
        expect(seen).toEqual(['-1,1']);
      });

      it('takes the measure in afterwards with exactly one redraw', async () => {
        slow();
        const seen = await start();
        act(() => {
          vi.advanceTimersByTime(5000);
        });
        await flush();
        await act(async () => answer(measured({ b1: DEM_VALUES })));
        await flush();
        expect(seen).toEqual(['-1,1', '120,2400']);
        expect(inputs().map((i) => i.value)).toEqual(['120', '2400']);
        expect(unit()).toBe('m');
      });

      it('does not redraw when the late measure calls for the same range', async () => {
        slow();
        const seen = await start();
        act(() => {
          vi.advanceTimersByTime(5000);
        });
        await flush();
        await act(async () => answer(measured({ b1: INDEX_VALUES })));
        await flush();
        expect(seen).toEqual(['-1,1']);
      });

      it('says so when the late measure is a failure, and draws nothing again', async () => {
        slow();
        const seen = await start();
        act(() => {
          vi.advanceTimersByTime(5000);
        });
        await flush();
        await act(async () => answer(new Response('{}', { status: 502 })));
        await flush();
        expect(seen).toEqual(['-1,1']);
        expect(section().textContent).toContain('The range could not be measured');
      });

      it('lets a newer picture win over a measure of an older one that comes late', async () => {
        slow();
        const seen = await start();
        act(() => {
          vi.advanceTimersByTime(5000);
        });
        await flush();
        const first = answer;
        statistics = () => measured({ b1: INDEX_VALUES });
        typeInto(expression(), 'nir / blue');
        await afterDebounce();
        await act(async () => first(measured({ b1: DEM_VALUES })));
        await flush();
        expect(seen.at(-1)).toBe('-1,1');
        expect(inputs().map((i) => i.value)).toEqual(['-1', '1']);
      });
    });

    it('keeps the start range, says so and does not ask again when the measure fails; "Auto stretch" asks again', async () => {
      statistics = () => new Response('{}', { status: 502 });
      await withNdvi();
      expect(rescale()).toBe('-1,1');
      expect(section().textContent).toContain('The range could not be measured');
      typeInto(expression(), 'nir / red');
      await afterDebounce();
      typeInto(expression(), '(nir - red) / (nir + red)');
      await afterDebounce();
      expect(asked()).toHaveLength(2);
      statistics = () => measured({ b1: DEM_VALUES });
      expect(button('Auto stretch').disabled).toBe(false);
      click(button('Auto stretch'));
      await afterDebounce();
      expect(asked()).toHaveLength(3);
      expect(rescale()).toBe('120,2400');
      expect(section().textContent).not.toContain('could not be measured');
    });

    it('stays at -1 to 1 when no pixel is valid, with no note of a failure', async () => {
      statistics = () => measured({ b1: { count: 0, min: null, max: null, percentile_2: null, percentile_98: null, unit: null } });
      await withNdvi();
      expect(rescale()).toBe('-1,1');
      expect(section().textContent).not.toContain('could not be measured');
    });

    it('writes the unit beside the range, where the steps leave one', async () => {
      statistics = () => measured({ b1: DEM_VALUES });
      await withNdvi();
      expect(unit()).toBe('m');
    });

    it('puts the unit in an element of its own beside the max field, never inside a field', async () => {
      statistics = () => measured({ b1: DEM_VALUES });
      await withNdvi();
      const element = section().querySelector('.pp-unit')!;
      expect(element.closest('label')).toBeNull();
      expect(element.previousElementSibling?.matches('label.vc-num')).toBe(true);
      expect(element.previousElementSibling?.textContent).toContain('max');
    });

    it.each([['1'], [null], ['']])('writes no unit beside the range for %j', async (value) => {
      statistics = () => measured({ b1: { ...DEM_VALUES, unit: value } });
      await withNdvi();
      expect(unit()).toBeNull();
    });

    it('writes no unit where the bands of the result differ in theirs', async () => {
      statistics = () => measured({ b1: DEM_VALUES, b2: { ...DEM_VALUES, unit: 'K' } });
      await withNdvi();
      expect(unit()).toBeNull();
    });

    it('shows the unit of a hand range as soon as the measure is in, and drops that of a former preview', async () => {
      statistics = () => measured({ b1: DEM_VALUES });
      await withNdvi();
      typeInto(inputs()[1], '5');
      click(button('Apply'));
      statistics = () => measured({ b1: { ...DEM_VALUES, unit: null } });
      typeInto(expression(), 'nir / red');
      await afterDebounce();
      expect(unit()).toBeNull();
    });

    it('puts the unit into no layer: the preview pinned to the layer manager shows none', async () => {
      statistics = () => measured({ b1: DEM_VALUES });
      await withNdvi();
      expect(unit()).toBe('m');
      click(button('＋ Add preview to layers'));
      expect(useAppStore.getState().layers[0]).not.toHaveProperty('unit');
      const manager = document.createElement('div');
      document.body.append(manager);
      const managerRoot = createRoot(manager);
      act(() => managerRoot.render(<LayerManager />));
      expect(manager.querySelector('.layer-row')).not.toBeNull();
      expect(manager.textContent).not.toMatch(/\bm\b/u);
      act(() => managerRoot.unmount());
      manager.remove();
    });
  });
});

describe('"Preview" (Otto, 19.10.2026: always coarser than the data)', () => {
  it('stands in the panel and over the map whenever there is a preview, whatever the zoom', async () => {
    mount(
      <>
        <ProcessingPanel />
        <PreviewBadge />
      </>,
    );
    select([scene('S2B_A', 10)]);
    act(() => store().openProcessing());
    await flush();
    expect(container.querySelector('.preview-badge')).toBeNull();
    vi.useFakeTimers();
    click(button('＋ Band math'));
    typeInto(expression(), 'nir / red');
    await afterDebounce();
    for (const zoom of [3, 12.5, 18, 22]) {
      act(() => useAppStore.setState({ mapZoom: zoom, viewportBbox: [10, 50, 11, 51] }));
      expect(section().querySelector('.pp-badge')?.textContent).toBe('Preview');
      expect(container.querySelector('.preview-badge')?.textContent).toBe('Preview');
    }
    act(() => store().closeProcessing());
    expect(container.querySelector('.preview-badge')).toBeNull();
  });

  it('holds the tiles of the preview under the pixel size of the data', async () => {
    await withNdvi([scene('S2B_A', 10)]);
    // 10 m at 51° N: level 13 is the last, and the released levels reach 14.
    expect(store().preview!.maxZoom).toBe(13);
    expect(store().preview!.maxZoom).toBeLessThan(14);
  });

  it('draws as before, with the badge at every zoom, when the data names no pixel size', async () => {
    mount(
      <>
        <ProcessingPanel />
        <PreviewBadge />
      </>,
    );
    select([scene('S2B_A', null)]);
    act(() => store().openProcessing());
    await flush();
    vi.useFakeTimers();
    click(button('＋ Band math'));
    typeInto(expression(), 'nir / red');
    await afterDebounce();
    expect(store().preview).toMatchObject({ minZoom: 8, maxZoom: 14 });
    expect(container.textContent).not.toContain('pixel size');
    for (const zoom of [3, 12.5, 22]) {
      act(() => useAppStore.setState({ mapZoom: zoom }));
      expect(container.querySelector('.preview-badge')?.textContent).toBe('Preview');
      expect(section().querySelector('.pp-badge')?.textContent).toBe('Preview');
    }
  });

  it('stands for a pinned preview that is switched on, and not for one that is hidden', () => {
    const layer = (id: string, visible: boolean): MapLayer => ({
      ...pinned(id),
      visible,
      derived: 'preview',
      overlays: [{ kind: 'raster', tileUrl: 'u', bounds: [10, 50, 11, 51], minZoom: 0, maxZoom: 13, preview: true }],
    });
    useAppStore.setState({ layers: [layer('P1', false)] });
    mount(<PreviewBadge />);
    expect(container.querySelector('.preview-badge')).toBeNull();
    act(() => useAppStore.setState({ layers: [layer('P1', true)] }));
    expect(container.querySelector('.preview-badge')).not.toBeNull();
    act(() => useAppStore.setState({ mapZoom: 20 }));
    expect(container.querySelector('.preview-badge')).not.toBeNull();
  });

  it('does not stand for an ordinary layer', () => {
    useAppStore.setState({
      layers: [{ ...pinned('L1'), overlays: [{ kind: 'raster', tileUrl: 'u', bounds: [10, 50, 11, 51], minZoom: 0, maxZoom: 14 }] }],
    });
    mount(<PreviewBadge />);
    expect(container.querySelector('.preview-badge')).toBeNull();
  });
});

describe('the preview as a layer (§3.4)', () => {
  it('"＋ Add preview to layers" pins it on top, with the badge right, and leaves the others', async () => {
    await withNdvi([scene('S2B_A'), scene('S2B_B')]);
    useAppStore.setState({ layers: [pinned('L1')] });
    click(button('＋ Add preview to layers'));
    const [layer, other] = useAppStore.getState().layers;
    expect(other.id).toBe('L1');
    expect(other.visible).toBe(true);
    expect(layer).toMatchObject({ name: 'Preview · Band math', derived: 'preview', visible: true, opacity: 1 });
    expect(layer.overlays).toHaveLength(2);
    expect(layer.overlays[0]).toMatchObject({ kind: 'raster', minZoom: 8, maxZoom: 13, preview: true });
    expect(layer.restore).toMatchObject({ itemIds: ['S2B_A', 'S2B_B'], datasetId: 'sentinel-2-c1-l2a', focusMode: false });
    // The layer counts up on the rail; the manager does not open over the control panel.
    expect(useAppStore.getState().dock).toBeNull();
  });

  it('keeps the tile URL of the preview, and the AOI out of it', async () => {
    await withNdvi();
    click(button('AOI only'));
    await afterDebounce();
    click(button('＋ Add preview to layers'));
    const layer = useAppStore.getState().layers[0];
    expect(layer.restore.cropToAoi).toBe(true);
    const url = (layer.overlays[0] as { tileUrl: string }).tileUrl;
    expect(url.startsWith('earthx-clip://')).toBe(true);
    expect(url).toContain('op=band_math');
    expect(url).not.toContain('10.4');
  });

  it('cannot be pinned before there is a picture', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    vi.useFakeTimers();
    click(button('＋ Band math'));
    typeInto(expression(), 'nir / red');
    // The step is complete, the picture follows in 400 ms.
    expect(button('＋ Add preview to layers').disabled).toBe(true);
    await afterDebounce();
    expect(button('＋ Add preview to layers').disabled).toBe(false);
  });

  it('leaves the other layers as they are, also when the panel was opened from one of them', async () => {
    select([scene('S2B_A')]);
    useAppStore.setState({ layers: [pinned('L0'), pinned('L1')] });
    mount(
      <>
        <ProcessingPanel />
        <LayerManager />
      </>,
    );
    click(button('⚙', container.querySelectorAll('.layer-row')[1] as HTMLElement));
    await flush();
    vi.useFakeTimers();
    click(button('＋ Band math'));
    typeInto(expression(), '(nir - red) / (nir + red)');
    await afterDebounce();
    click(button('＋ Add preview to layers'));
    expect(useAppStore.getState().layers.map((l) => [l.id.startsWith('P') ? 'preview' : l.id, l.visible])).toEqual([
      ['preview', true],
      ['L0', true],
      ['L1', true],
    ]);
  });
});

describe('the ways into the panel (§3.5)', () => {
  it('"⚙" at a layer makes its selection again, then opens the panel on "Whole scene"', async () => {
    select([scene('S2B_A'), scene('S2B_B')]);
    useAppStore.setState({ layers: [pinned('L1', { selectedIds: [], itemIds: ['S2B_B'], groupItemIds: [['S2B_B']] })], selectedIds: ['S2B_A'] });
    mount(
      <>
        <LayerManager />
        <ProcessingPanel />
      </>,
    );
    expect(store().open).toBe(false);
    click(button('⚙'));
    await flush();
    expect(useAppStore.getState().selectedIds).toEqual(['S2B_B']);
    expect(useAppStore.getState().aoi).toBe(AOI);
    expect(store()).toMatchObject({ open: true, area: 'scene' });
    expect(container.textContent).toContain('S2B_B');
  });

  it('starts on "AOI only" for a layer that was cropped to its AOI', async () => {
    select([scene('S2B_A')]);
    useAppStore.setState({ layers: [pinned('L1', { cropToAoi: true, focusMode: true })] });
    mount(<LayerManager />);
    click(button('⚙'));
    await flush();
    expect(store()).toMatchObject({ open: true, area: 'aoi' });
  });

  it('starts on "Whole scene" for a layer cropped with no AOI left to it', async () => {
    select([scene('S2B_A')]);
    useAppStore.setState({ layers: [pinned('L1', { cropToAoi: true, aoi: null })] });
    mount(<LayerManager />);
    click(button('⚙'));
    await flush();
    expect(store().area).toBe('scene');
  });

  it('is locked for a preview, and says so', () => {
    select([scene('S2B_A')]);
    useAppStore.setState({ layers: [{ ...pinned('P1'), derived: 'preview' }] });
    mount(<LayerManager />);
    const gear = button('⚙');
    expect(gear.disabled).toBe(true);
    expect(gear.title).toBe('A result cannot be processed further yet.');
    click(gear);
    expect(store().open).toBe(false);
  });

  it('is locked for a dataset whose licence is below processing', () => {
    select([scene('S2B_A')], 'display');
    useAppStore.setState({ layers: [pinned('L1')] });
    mount(<LayerManager />);
    expect(button('⚙').disabled).toBe(true);
    expect(button('⚙').title).toContain('does not allow processing');
  });

  it('does not offer to download a preview, which is no scene file', () => {
    select([scene('S2B_A')]);
    useAppStore.setState({ layers: [pinned('L1'), { ...pinned('P1'), derived: 'preview' }] });
    mount(<LayerManager />);
    const rows = [...container.querySelectorAll('.layer-row')];
    expect(rows.map((row) => [...row.querySelectorAll('button')].some((b) => b.textContent === '⇩'))).toEqual([true, false]);
  });

  describe('the view stays as it is (Otto, 19.10.2026)', () => {
    const tile: DownloadedInfo = { tileUrl: 'u', bounds: [10, 50, 11, 51], asset: 'visual', minZoom: 8, maxZoom: 14 };
    const OTHER_AOI = bboxToPolygon([10.1, 50.1, 10.2, 50.2]);

    it('does not enter the full-resolution view of a layer, and keeps the results list', async () => {
      select([scene('S2B_A'), scene('S2B_B')]);
      const before = useAppStore.getState();
      const cropped = pinned('L1', {
        focusMode: true,
        cropToAoi: true,
        downloaded: { S2B_B: tile },
        itemIds: ['S2B_B'],
        selectedIds: ['S2B_B'],
        aoi: OTHER_AOI,
        appliedRender: { rescale: '0,1' },
      });
      useAppStore.setState({ layers: [cropped] });
      mount(<LayerManager />);
      click(button('⚙'));
      await flush();
      const after = useAppStore.getState();
      expect(store()).toMatchObject({ open: true, area: 'aoi' });
      expect(after.focusMode).toBe(false);
      expect(after.downloaded).toBe(before.downloaded);
      expect(after.appliedRender).toBe(before.appliedRender);
      expect(after.cropToAoi).toBe(before.cropToAoi);
      expect(after.items).toBe(before.items);
      expect(after.groups).toBe(before.groups);
      expect(after.activeGroupIndex).toBe(before.activeGroupIndex);
      expect(after.selectedIds).toEqual(['S2B_B']);
      // "AOI only" sends the AOI of the layer.
      expect(after.aoi).toBe(OTHER_AOI);
    });

    it('leaves the AOI the user drew when the layer is processed whole', async () => {
      select([scene('S2B_A')]);
      useAppStore.setState({ layers: [pinned('L1', { aoi: OTHER_AOI, cropToAoi: false })] });
      mount(<LayerManager />);
      click(button('⚙'));
      await flush();
      expect(store().area).toBe('scene');
      expect(useAppStore.getState().aoi).toBe(AOI);
    });

    it('leaves a full-resolution view that is open as it is', async () => {
      select([scene('S2B_A'), scene('S2B_B')]);
      useAppStore.setState({
        focusMode: true,
        downloaded: { S2B_B: tile },
        showDownloaded: true,
        layers: [pinned('L1', { focusMode: true, downloaded: { S2B_A: tile } })],
      });
      mount(<LayerManager />);
      click(button('⚙'));
      await flush();
      const after = useAppStore.getState();
      expect(after.focusMode).toBe(true);
      expect(Object.keys(after.downloaded)).toEqual(['S2B_B']);
      expect(after.selectedIds).toEqual(['S2B_A']);
    });

    it('makes the dataset of the layer the active one, and only that', async () => {
      const other = { ...dataset(), id: 'other-ds', title: 'Other' } as DatasetOption;
      select([scene('S2B_A')]);
      useAppStore.setState({
        datasets: [dataset(), other],
        datasetId: 'other-ds',
        selectedDatasetIds: ['sentinel-2-c1-l2a', 'other-ds'],
        layers: [pinned('L1', { focusMode: true })],
      });
      mount(<LayerManager />);
      click(button('⚙'));
      await flush();
      expect(useAppStore.getState().datasetId).toBe('sentinel-2-c1-l2a');
      expect(useAppStore.getState().focusMode).toBe(false);
    });
  });

  describe('scenes the results on screen lack (Otto, 19.10.2026)', () => {
    const itemRequests = () => fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.startsWith('/stac'));
    const layerOf = (...ids: string[]) =>
      pinned('L1', { itemIds: ids, selectedIds: ids, groupItemIds: [ids], cropToAoi: true, focusMode: true });

    it('fetches them one by one, with no search, and then opens the panel', async () => {
      select([scene('S2B_A')]);
      catalog.GONE = scene('GONE');
      useAppStore.setState({ layers: [layerOf('S2B_A', 'GONE')] });
      mount(
        <>
          <LayerManager />
          <ProcessingPanel />
        </>,
      );
      click(button('⚙'));
      await flush();
      expect(itemRequests()).toEqual([`${ITEM_URL}GONE`]);
      expect(useAppStore.getState().selectedIds).toEqual(['S2B_A', 'GONE']);
      expect(store()).toMatchObject({ open: true, area: 'aoi' });
      expect(store().extraScenes!.items.map((i) => i.id)).toEqual(['GONE']);
      // The results on screen stay as they are.
      expect(useAppStore.getState().items.map((i) => i.id)).toEqual(['S2B_A']);
      expect(container.textContent).toContain('2 scenes');
    });

    it('puts a fetched scene of a pass the results hold into that pass, and another one into a pass of its own', async () => {
      select([scene('S2B_A')]);
      catalog.SAME_DAY = scene('SAME_DAY');
      catalog.OTHER_DAY = { ...scene('OTHER_DAY'), properties: { datetime: '2026-06-01T10:00:00Z' } };
      useAppStore.setState({ layers: [pinned('L1', { itemIds: ['S2B_A', 'SAME_DAY'], selectedIds: ['S2B_A', 'SAME_DAY'] })] });
      mount(<LayerManager />);
      click(button('⚙'));
      await flush();
      const view = orderView(useAppStore.getState(), store());
      expect(view.passes.map((p) => p.items.map((i) => i.id))).toEqual([['S2B_A', 'SAME_DAY']]);

      act(() =>
        useAppStore.setState({ layers: [pinned('L2', { itemIds: ['S2B_A', 'OTHER_DAY'], selectedIds: ['S2B_A', 'OTHER_DAY'] })] }),
      );
      click(button('⚙'));
      await flush();
      const second = orderView(useAppStore.getState(), store());
      expect(second.passes.map((p) => p.items.map((i) => i.id))).toEqual([['S2B_A'], ['OTHER_DAY']]);
    });

    it('asks only for the scenes it lacks', async () => {
      select([scene('S2B_A'), scene('S2B_B')]);
      catalog.GONE = scene('GONE');
      useAppStore.setState({ layers: [layerOf('S2B_A', 'S2B_B', 'GONE')] });
      mount(<LayerManager />);
      click(button('⚙'));
      await flush();
      expect(itemRequests()).toEqual([`${ITEM_URL}GONE`]);
    });

    it('asks for nothing when the results hold every scene', async () => {
      select([scene('S2B_A')]);
      useAppStore.setState({ layers: [layerOf('S2B_A')] });
      mount(<LayerManager />);
      click(button('⚙'));
      await flush();
      expect(itemRequests()).toEqual([]);
      expect(store().extraScenes).toBeNull();
    });

    it('names the scene the catalog no longer has, and does not open the panel', async () => {
      select([scene('S2B_A')]);
      useAppStore.setState({ layers: [layerOf('S2B_A', 'GONE')] });
      mount(<LayerManager />);
      click(button('⚙'));
      await flush();
      expect(store().open).toBe(false);
      expect(useAppStore.getState().error).toBe('Could not load the scenes of this layer. GONE: not found in the catalog');
    });

    it('gives the reason when the catalog cannot be reached, and opens nothing', async () => {
      select([scene('S2B_A')]);
      catalog.GONE = 502;
      catalog.ALSO = scene('ALSO');
      useAppStore.setState({ layers: [layerOf('S2B_A', 'GONE', 'ALSO')] });
      mount(<LayerManager />);
      click(button('⚙'));
      await flush();
      expect(store().open).toBe(false);
      expect(store().extraScenes).toBeNull();
      expect(useAppStore.getState().error).toContain('Could not load the scenes of this layer. GONE:');
      expect(useAppStore.getState().error).toContain('the catalog is down');
      expect(useAppStore.getState().error).not.toContain('ALSO');
    });

    it('lets a newer entry win over one still waiting for the catalog', async () => {
      select([scene('S2B_A')]);
      let answer!: (r: Response) => void;
      pending[`${ITEM_URL}SLOW`] = new Promise<Response>((resolve) => (answer = resolve));
      useAppStore.setState({ layers: [layerOf('S2B_A', 'SLOW'), { ...layerOf('S2B_A'), id: 'L2' }] });
      mount(<LayerManager />);
      const gears = () => [...container.querySelectorAll<HTMLButtonElement>('.layer-row button')].filter((b) => b.textContent === '⚙');
      click(gears()[0]);
      await flush();
      click(gears()[1]);
      await flush();
      expect(store()).toMatchObject({ open: true, extraScenes: null });
      expect(useAppStore.getState().selectedIds).toEqual(['S2B_A']);
      answer(json(scene('SLOW')));
      await flush();
      expect(store().extraScenes).toBeNull();
      expect(useAppStore.getState().selectedIds).toEqual(['S2B_A']);
    });

    it('does the same for the full-resolution view, and says "view"', async () => {
      select([scene('S2B_A')]);
      catalog.GONE = scene('GONE');
      const tile: DownloadedInfo = { tileUrl: 'u', bounds: [10, 50, 11, 51], asset: 'visual', minZoom: 8, maxZoom: 14 };
      useAppStore.setState({ focusMode: true, downloaded: { S2B_A: tile, GONE: tile } });
      mount(<ViewerControls />);
      click(button('⚙ Process'));
      await flush();
      expect(itemRequests()).toEqual([`${ITEM_URL}GONE`]);
      expect(store().open).toBe(true);

      act(() => store().closeProcessing());
      delete catalog.GONE;
      click(button('⚙ Process'));
      await flush();
      expect(store().open).toBe(false);
      expect(useAppStore.getState().error).toBe('Could not load the scenes of this view. GONE: not found in the catalog');
    });

    it('lets the scenes of the entry go with the draft when the dataset changes', async () => {
      select([scene('S2B_A')]);
      catalog.GONE = scene('GONE');
      useAppStore.setState({ layers: [layerOf('S2B_A', 'GONE')] });
      mount(<LayerManager />);
      click(button('⚙'));
      await flush();
      expect(store().extraScenes).not.toBeNull();
      act(() => useAppStore.setState({ datasetId: 'other' }));
      expect(store().extraScenes).toBeNull();
    });
  });

  it('starts on "Whole scene" from the selection, whatever an entry from a layer chose before (Otto, 19.10.2026)', async () => {
    select([scene('S2B_A')]);
    useAppStore.setState({ layers: [pinned('L1', { cropToAoi: true, focusMode: true })] });
    mount(
      <>
        <LayerManager />
        <ProcessingPanel />
        <ViewBar />
      </>,
    );
    click(button('⚙', container.querySelector('.layer-row') as HTMLElement));
    await flush();
    expect(store()).toMatchObject({ open: true, area: 'aoi' });

    act(() => store().closeProcessing());
    click(button('⚙ Process'));
    expect(store()).toMatchObject({ open: true, area: 'scene' });

    // Also while the panel stays open: every entry sets the area.
    click(button('AOI only'));
    expect(store().area).toBe('aoi');
    click(button('⚙ Process'));
    expect(store().area).toBe('scene');
  });

  it('"⚙ Process" of the full-resolution view takes the scenes of the view, cropped or whole', async () => {
    select([scene('S2B_A'), scene('S2B_B')]);
    const tile: DownloadedInfo = { tileUrl: 'u', bounds: [10, 50, 11, 51], asset: 'visual', minZoom: 8, maxZoom: 14 };
    useAppStore.setState({ focusMode: true, cropToAoi: true, viewAoi: useAppStore.getState().aoi, downloaded: { S2B_B: tile }, selectedIds: ['S2B_A', 'S2B_B'] });
    mount(<ViewerControls />);
    click(button('⚙ Process'));
    await flush();
    expect(useAppStore.getState().selectedIds).toEqual(['S2B_B']);
    expect(store()).toMatchObject({ open: true, area: 'aoi' });

    act(() => store().closeProcessing());
    useAppStore.setState({ cropToAoi: false });
    click(button('⚙ Process'));
    await flush();
    expect(store().area).toBe('scene');
  });

  it('locks "⚙ Process" of the full-resolution view for a dataset below processing', () => {
    select([scene('S2B_A')], 'catalog');
    const tile: DownloadedInfo = { tileUrl: 'u', bounds: [10, 50, 11, 51], asset: 'visual', minZoom: 8, maxZoom: 14 };
    useAppStore.setState({ focusMode: true, downloaded: { S2B_A: tile } });
    mount(<ViewerControls />);
    expect(button('⚙ Process').disabled).toBe(true);
  });
});

describe('the preview of a mosaic job (NM4-04b)', () => {
  const HINT = 'Preview per scene – may differ from the job where scenes overlap';
  const asks = (part: string) => fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.includes(part));
  const query = (url: string) => new URL(url, 'http://localhost');
  const reply = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
  // The tiler takes a mosaic and names the order of its scenes; a scene it takes as it did.
  const taking = (order: string[]) => (url: string) =>
    url.includes('/mosaic/') ? json({ tilejson: '3.0.0', 'earthx:order': order }) : json({ tilejson: '3.0.0' });
  const mosaicRefused = (status: number, detail: string) => (url: string) =>
    url.includes('/mosaic/') ? reply(status, { detail }) : json({ tilejson: '3.0.0' });

  // A dataset released below the first level of a mosaic, so that scenes can stand under it.
  function selectWide(items: StacItem[]) {
    select(items);
    useAppStore.setState({ datasets: [{ ...(dataset() as Extract<DatasetOption, { viewable: true }>), zoom: { min: 5, max: 14 } }] });
  }

  async function typeNdvi(expressionText = '(nir - red) / (nir + red)') {
    await openPanel();
    mount(
      <>
        <ProcessingPanel />
        <PreviewBadge />
      </>,
    );
    vi.useFakeTimers();
    click(button('＋ Band math'));
    typeInto(expression(), expressionText);
    await afterDebounce();
    await flush();
  }

  const dockBadge = () => container.querySelector('.preview-badge-dock .preview-badge:not(.loading)');
  const panelBadge = () => section().querySelector('.pp-badge');

  it('draws one job over a pass as its mosaic with the steps, and the scenes below it in the order of the tiler', async () => {
    tilejson = taking(['S2B_B', 'S2B_C', 'S2B_A']);
    selectWide([scene('S2B_C'), scene('S2B_A'), scene('S2B_B')]);
    await typeNdvi();
    const preview = store().preview!;
    expect(preview.mosaics).toHaveLength(1);
    const url = query(preview.mosaics[0].url);
    expect(preview.mosaics[0].url.split('?')[0]).toBe('/collections/sentinel-2-c1-l2a/mosaic/tiles/WebMercatorQuad/{z}/{x}/{y}');
    expect(url.searchParams.getAll('item')).toEqual(['S2B_A', 'S2B_B', 'S2B_C']);
    expect(url.searchParams.getAll('asset')).toEqual(['red', 'nir']);
    expect(url.searchParams.getAll('op')).toEqual(['band_math']);
    expect(JSON.parse(url.searchParams.get('params')!)).toEqual({ expression: '(nir - red) / (nir + red)' });
    expect(preview.scenes.map((scene) => [scene.id, scene.below])).toEqual([['S2B_B', 8], ['S2B_C', 8], ['S2B_A', 8]]);
    expect(preview.perScene).toBe(false);
    // The tiler is asked about the mosaic, not about a scene; the colour scale is measured over the scene that wins.
    expect(asks('/mosaic/')).toHaveLength(1);
    expect(asks('/items/')).toHaveLength(asks('/statistics?').length);
    expect(asks('/statistics?').map((u) => query(u).pathname)).toEqual(['/collections/sentinel-2-c1-l2a/items/S2B_B/statistics']);
    expect(asks('/mosaic/').some((u) => u.includes('/statistics'))).toBe(false);
    expect(panelBadge()?.getAttribute('title')).toBeNull();
    expect(dockBadge()?.getAttribute('title')).toBeNull();
  });

  it('keeps the TileJSON of the mosaic and the measure when only the range changes', async () => {
    tilejson = taking(['S2B_B', 'S2B_A']);
    selectWide([scene('S2B_A'), scene('S2B_B')]);
    await typeNdvi();
    const inputs = [...section().querySelectorAll<HTMLInputElement>('input[type="number"]')];
    typeInto(inputs[0], '-0.5');
    click(button('Apply'));
    await afterDebounce();
    await flush();
    expect(query(store().preview!.mosaics[0].url).searchParams.get('rescale')).toBe('-0.5,1');
    expect(asks('/mosaic/')).toHaveLength(1);
    expect(asks('/statistics?')).toHaveLength(1);
  });

  it('draws the scenes one by one, with the hint in the tooltip and none in the panel, when the tiler refuses the mosaic', async () => {
    tilejson = mosaicRefused(422, "'sentinel-2-c1-l2a' does not allow reprojection, which a mosaic of scenes may need");
    selectWide([scene('S2B_A'), scene('S2B_B'), scene('S2B_C')]);
    await typeNdvi();
    const preview = store().preview!;
    expect(preview.mosaics).toEqual([]);
    expect(preview.scenes.map((s) => [s.id, s.below])).toEqual([['S2B_A', undefined], ['S2B_B', undefined], ['S2B_C', undefined]]);
    expect(preview.perScene).toBe(true);
    expect(panelBadge()?.getAttribute('title')).toBe(HINT);
    expect(dockBadge()?.getAttribute('title')).toBe(HINT);
    expect(section().textContent).not.toContain('per scene');
    expect(section().textContent).not.toContain('may differ');
    expect(store().previewNote).toBeNull();
    // Then the first scene is asked about the chain, as ever.
    expect(asks('/items/S2B_A/WebMercatorQuad/tilejson.json')).toHaveLength(1);
  });

  it.each([
    ['a request that is too long', 414, 'a mosaic request takes at most 7168 bytes, not 8000'],
    ['a pass the tiler cannot mosaic', 422, 'the scenes of the mosaic are not of one overpass'],
    ['scenes it cannot compare', 422, "the scenes of the mosaic scale 'red' differently"],
    ['a mosaic it does not serve', 501, 'this dataset has no mosaic'],
    ['a failing source', 502, 'the catalog is down'],
  ])('draws the scenes one by one for %s', async (_, status, detail) => {
    tilejson = mosaicRefused(status, detail);
    selectWide([scene('S2B_A'), scene('S2B_B')]);
    await typeNdvi();
    expect(store().preview).toMatchObject({ mosaics: [], perScene: true });
    expect(panelBadge()?.getAttribute('title')).toBe(HINT);
  });

  it('draws the scenes one by one when the network fails for the mosaic', async () => {
    tilejson = (url) => {
      if (url.includes('/mosaic/')) throw new TypeError('Failed to fetch');
      return json({ tilejson: '3.0.0' });
    };
    selectWide([scene('S2B_A'), scene('S2B_B')]);
    await typeNdvi();
    expect(store().preview).toMatchObject({ mosaics: [], perScene: true });
  });

  it('draws the scenes one by one for a mosaic with more bands than the tiler takes with steps', async () => {
    const wide = (id: string): StacItem => ({
      ...scene(id),
      assets: Object.fromEntries(['a', 'b', 'c', 'd', 'e'].map((key) => [key, scene(id).assets!.red])),
    });
    selectWide([wide('S2B_A'), wide('S2B_B')]);
    await typeNdvi('a + b + c + d + e');
    expect(store().preview).toMatchObject({ mosaics: [], perScene: true });
    expect(store().preview!.scenes).toHaveLength(2);
    expect(asks('/mosaic/')).toHaveLength(0);
  });

  it('shows the place of a step the tiler refuses for the mosaic, and asks the mosaic of the shorter chain', async () => {
    tilejson = (url) =>
      url.includes('/mosaic/')
        ? query(url).searchParams.getAll('op').length === 2
          ? reply(422, { detail: 'step 1: expression names unknown band(s): red; the input has: band_math' })
          : json({ tilejson: '3.0.0', 'earthx:order': ['S2B_B', 'S2B_A'] })
        : json({ tilejson: '3.0.0' });
    selectWide([scene('S2B_A'), scene('S2B_B')]);
    await typeNdvi();
    click(button('＋ Band math'));
    typeInto(expression(1), 'red + 1');
    await afterDebounce();
    await flush();
    const preview = store().preview!;
    expect(preview.stepCount).toBe(1);
    expect(preview.mosaics).toHaveLength(1);
    expect(preview.scenes.map((s) => s.id)).toEqual(['S2B_B', 'S2B_A']);
    expect(preview.perScene).toBe(false);
    expect(query(preview.mosaics[0].url).searchParams.getAll('op')).toEqual(['band_math']);
    expect(store().previewNote).toBe(
      'Preview shows step 1 of 2. Step 2: expression names unknown band(s): red; the input has: band_math.',
    );
    expect(section().textContent).toContain('Preview shows step 1 of 2. Step 2: expression names unknown band(s): red');
    // The answer for the first step alone is the one kept from before the second was added.
    expect(asks('/mosaic/').map((u) => query(u).searchParams.getAll('op').length)).toEqual([1, 2]);
  });

  it('shows no picture, and the reason, when the tiler refuses the first of two steps of the mosaic', async () => {
    tilejson = (url) =>
      url.includes('/mosaic/') && query(url).searchParams.getAll('op').length === 2
        ? reply(422, { detail: 'step 0: expression names unknown band(s): green; the input has: red, nir' })
        : json({ tilejson: '3.0.0', 'earthx:order': ['S2B_A', 'S2B_B'] });
    selectWide([scene('S2B_A'), scene('S2B_B')]);
    await typeNdvi();
    click(button('＋ Band math'));
    typeInto(expression(1), 'red + 1');
    await afterDebounce();
    await flush();
    expect(store().preview).toBeNull();
    expect(store().previewNote).toBe('No preview. Step 1: expression names unknown band(s): green; the input has: red, nir.');
  });

  it('leaves the refusal of a single step to the first scene, which names it as ever', async () => {
    tilejson = () => reply(422, { detail: 'expression: not a valid expression' });
    selectWide([scene('S2B_A'), scene('S2B_B')]);
    await typeNdvi();
    expect(store().preview).toBeNull();
    expect(store().previewNote).toBe('No preview: expression: not a valid expression.');
  });

  it('draws one mosaic for each pass with "One job per pass", and a pass of one scene alone', async () => {
    tilejson = (url) => (url.includes('/mosaic/') ? json({ tilejson: '3.0.0', 'earthx:order': query(url).searchParams.getAll('item').reverse() }) : json({ tilejson: '3.0.0' }));
    const items = ['S2B_A', 'S2B_B', 'S2B_C', 'S2B_D', 'S2B_E'].map((id) => scene(id));
    select(items);
    useAppStore.setState({
      groups: [
        { key: ['d1'], label: 'd1', items: items.slice(0, 2) },
        { key: ['d2'], label: 'd2', items: items.slice(2, 4) },
        { key: ['d3'], label: 'd3', items: items.slice(4) },
      ],
    });
    await openPanel();
    act(() => useProcessingStore.setState({ runAs: 'pass' }));
    mount(
      <>
        <ProcessingPanel />
        <PreviewBadge />
      </>,
    );
    vi.useFakeTimers();
    click(button('＋ Band math'));
    typeInto(expression(), 'nir / red');
    await afterDebounce();
    await flush();
    const preview = store().preview!;
    expect(preview.mosaics.map((m) => query(m.url).searchParams.getAll('item'))).toEqual([
      ['S2B_A', 'S2B_B'],
      ['S2B_C', 'S2B_D'],
    ]);
    expect(preview.mosaics.map((m) => m.order)).toEqual([['S2B_B', 'S2B_A'], ['S2B_D', 'S2B_C']]);
    expect(preview.scenes.map((s) => s.id)).toEqual(['S2B_E']);
    expect(preview.perScene).toBe(false);
    expect(asks('/mosaic/')).toHaveLength(2);
    expect(asks('/statistics?').map((u) => query(u).pathname)).toEqual(['/collections/sentinel-2-c1-l2a/items/S2B_B/statistics']);
  });

  it('draws a job of one scene, and "One job per scene", scene by scene with no hint and no question about a mosaic', async () => {
    selectWide([scene('S2B_A')]);
    await typeNdvi();
    expect(store().preview).toMatchObject({ mosaics: [], perScene: false });
    expect(panelBadge()?.getAttribute('title')).toBeNull();
    expect(asks('/mosaic/')).toHaveLength(0);

    act(() => store().closeProcessing());
    const items = [scene('S2B_A'), scene('S2B_B'), scene('S2B_C')];
    selectWide(items);
    act(() => useProcessingStore.setState({ runAs: 'scene' }));
    act(() => store().openProcessing());
    await afterDebounce();
    await flush();
    expect(store().preview).toMatchObject({ mosaics: [], perScene: false });
    expect(store().preview!.scenes).toHaveLength(3);
    expect(panelBadge()?.getAttribute('title')).toBeNull();
    expect(asks('/mosaic/')).toHaveLength(0);
  });

  it('puts the mosaic and the scenes under it into the layer it pins', async () => {
    tilejson = taking(['S2B_B', 'S2B_A']);
    selectWide([scene('S2B_A'), scene('S2B_B')]);
    await typeNdvi();
    click(button(/Add preview to layers/));
    const layer = useAppStore.getState().layers[0];
    expect(layer.overlays).toHaveLength(3);
    // Bottom to top: the scenes, the first one on top of them, then the mosaic.
    const tiles = layer.overlays.map((o) => (o.kind === 'raster' ? query(o.tileUrl).pathname.split('/')[3] : null));
    expect(tiles).toEqual(['items', 'items', 'mosaic']);
    const mosaic = layer.overlays[2];
    expect(mosaic).toMatchObject({ kind: 'raster', minZoom: 8, preview: true });
    expect(layer.overlays[0]).toMatchObject({ kind: 'raster', maxZoom: 7, hideFrom: 6.5, preview: true });
    expect(layer.restore.itemIds).toEqual(['S2B_B', 'S2B_A']);
  });

  describe('"Loading…" while the first tile is on its way (Otto, 28.10.2026: cold 6.0 s, warm 0.16 s)', () => {
    const loading = () => container.querySelector('.preview-badge-dock .preview-badge.loading');
    let release: (response: Response) => void;

    function holdTheMosaic() {
      const held = new Promise<Response>((resolve) => {
        release = resolve;
      });
      tilejson = (url) => (url.includes('/mosaic/') ? (held as unknown as Response) : json({ tilejson: '3.0.0' }));
    }

    it('shows a small badge with the explanation in its tooltip, once the wait lasts, and takes it away with the picture', async () => {
      holdTheMosaic();
      selectWide([scene('S2B_A'), scene('S2B_B')]);
      await typeNdvi();
      expect(store().previewSettling).toBe(true);
      expect(loading()).toBeNull();
      act(() => {
        vi.advanceTimersByTime(599);
      });
      expect(loading()).toBeNull();
      act(() => {
        vi.advanceTimersByTime(1);
      });
      expect(loading()?.textContent).toBe('Loading…');
      expect(loading()?.getAttribute('title')).toBe('Reading the scenes. The first tile of a mosaic can take several seconds.');
      expect(loading()?.getAttribute('role')).toBe('status');
      // The heading of the preview says it too, for a window in which the panel hides the map: a badge, no line of text.
      const inHeading = section().querySelector('.pp-heading .pp-badge.loading');
      expect(inHeading?.textContent).toBe('Loading…');
      expect(inHeading?.getAttribute('title')).toBe(loading()?.getAttribute('title'));
      expect(section().querySelector('p')?.textContent ?? '').not.toContain('Loading');
      release(json({ tilejson: '3.0.0', 'earthx:order': ['S2B_B', 'S2B_A'] }));
      await flush();
      expect(store().previewSettling).toBe(false);
      expect(store().preview).not.toBeNull();
      expect(loading()).toBeNull();
    });

    it('never shows for a warm answer', async () => {
      tilejson = taking(['S2B_A', 'S2B_B']);
      selectWide([scene('S2B_A'), scene('S2B_B')]);
      await typeNdvi();
      expect(store().previewSettling).toBe(false);
      act(() => {
        vi.advanceTimersByTime(5000);
      });
      expect(loading()).toBeNull();
    });

    it('shows while the map loads the tiles of the preview, and not before they are asked for', async () => {
      tilejson = taking(['S2B_A', 'S2B_B']);
      selectWide([scene('S2B_A'), scene('S2B_B')]);
      await typeNdvi();
      act(() => useProcessingStore.setState({ previewTilesLoading: true }));
      act(() => {
        vi.advanceTimersByTime(599);
      });
      expect(loading()).toBeNull();
      act(() => {
        vi.advanceTimersByTime(1);
      });
      expect(loading()).not.toBeNull();
      act(() => useProcessingStore.setState({ previewTilesLoading: false }));
      expect(loading()).toBeNull();
    });

    it('is not for tiles of a layer or a preview that is gone', async () => {
      tilejson = taking(['S2B_A', 'S2B_B']);
      selectWide([scene('S2B_A'), scene('S2B_B')]);
      await typeNdvi();
      act(() => store().closeProcessing());
      act(() => useProcessingStore.setState({ previewTilesLoading: true }));
      act(() => {
        vi.advanceTimersByTime(5000);
      });
      expect(store().preview).toBeNull();
      expect(loading()).toBeNull();
      expect(container.querySelector('.preview-badge-dock')).toBeNull();
    });

    it('stops with the panel: no badge for a question nobody waits for', async () => {
      holdTheMosaic();
      selectWide([scene('S2B_A'), scene('S2B_B')]);
      await typeNdvi();
      expect(store().previewSettling).toBe(true);
      act(() => store().closeProcessing());
      expect(store().previewSettling).toBe(false);
      act(() => {
        vi.advanceTimersByTime(5000);
      });
      expect(loading()).toBeNull();
    });

    it('does not stay when the answer comes for a draft that has changed', async () => {
      holdTheMosaic();
      selectWide([scene('S2B_A'), scene('S2B_B')]);
      await typeNdvi();
      typeInto(expression(), 'nir / red');
      release(json({ tilejson: '3.0.0', 'earthx:order': ['S2B_A', 'S2B_B'] }));
      await flush();
      expect(store().previewSettling).toBe(false);
      tilejson = taking(['S2B_A', 'S2B_B']);
      await afterDebounce();
      await flush();
      expect(store().previewSettling).toBe(false);
      expect(store().preview).not.toBeNull();
    });
  });
});

describe('layerProcessBlock', () => {
  it('names the reason, or none', () => {
    const datasets = [dataset()];
    expect(layerProcessBlock(pinned('L1'), datasets)).toBeNull();
    expect(layerProcessBlock({ ...pinned('P1'), derived: 'preview' }, datasets)).toBe('A result cannot be processed further yet.');
    expect(layerProcessBlock(pinned('L1', { datasetId: 'unknown' }), datasets)).toBe('Pick a dataset first.');
    expect(layerProcessBlock(pinned('L1', { itemIds: [] }), datasets)).toBe('Select a scene first.');
  });
});
