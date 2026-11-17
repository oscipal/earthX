// @vitest-environment jsdom
//
// "Process" at a layer that shows a composite or a step of "Quick processing" (M5-14 PR B), as at a layer of an index (NM4-14b): the panel
// opens on the order the preset would be a job with, its steps first and locked, the band or the three bands they add the whole stock. A
// composite is previewed as the colour picture of its three channels with their fixed ranges; a step with the values chosen for it. No
// backend: `fetch` answers the process descriptions, the statistics, the estimate and the placing of a job.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import dem from '../fixtures/processes/cop-dem-glo-30.json';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import { bboxToPolygon } from '../geoUtils';
import type { MapLayer } from '../layers';
import type { Order } from '../processing';
import { RGB } from '../processingBands';
import { resetJobs, useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection, StacItem } from '../types';
import LayerManager from './LayerManager';
import ProcessingPanel from './ProcessingPanel';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const NEW_JOB = 'ZyXwVuTsRqPoNmLkJiHg_-';
const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const AOI = bboxToPolygon([7.4, 46.4, 7.6, 46.6]);
const FALSE_COLOUR = { name: 'false_colour_ir', title: 'False colour (IR)', expressions: ['nir', 'red', 'green'], rescale: [[0, 0.5], [0, 0.3], [0, 0.3]], reference: 'https://example.org/fc' };
const HILLSHADE = {
  name: 'hillshade',
  title: 'Hillshade',
  op: 'terrain',
  op_version: 1,
  params: { product: 'hillshade', bands: ['data'], method: 'horn', azimuth: 315, altitude: 45, z_factor: 1, multidirectional: false, name: 'hillshade' },
  adjustable: ['azimuth', 'altitude'],
};

const asset = (data_type: string) => ({ href: 'https://example.org/b.tif', type: COG, 'raster:bands': [{ data_type, nodata: 0 }] });
const scene = (id: string, collection: string, assets: string[], dataType: string): StacItem => ({
  id,
  collection,
  bbox: [7, 46, 8, 47],
  geometry: bboxToPolygon([7, 46, 8, 47]),
  properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 },
  assets: Object.fromEntries(assets.map((name) => [name, asset(dataType)])),
});

function datasetOf(id: string, units: Record<string, string | null>, presets: object): DatasetOption {
  return {
    id,
    title: id,
    viewable: true,
    groupBy: ['datetime'],
    zoom: { min: 7, max: 14 },
    browse: 'quicklook',
    quicklookNodataMax: null,
    resultsGroupBy: ['datetime'],
    hasTimeAxis: true,
    collection: {
      id,
      title: id,
      'earthx:format': 'cog',
      'earthx:license_flags': { tier: 'processing' },
      'earthx:capabilities': { interpolation: true, band_math: true, terrain: true },
      'earthx:band_units': units,
      'earthx:index_presets': [],
      'earthx:composite_presets': [],
      'earthx:step_presets': [],
      ...presets,
    } as unknown as Collection,
  };
}

const OPTICAL = datasetOf('sentinel-2-c1-l2a', { red: 'reflectance', green: 'reflectance', blue: 'reflectance', nir: 'reflectance' }, {
  'earthx:true_color': ['red', 'green', 'blue'],
  'earthx:composite_presets': [FALSE_COLOUR],
});
const HEIGHTS = datasetOf('cop-dem-glo-30', { data: 'm' }, { 'earthx:step_presets': [HILLSHADE] });

function layerOf(dataset: DatasetOption, look: object): MapLayer {
  return {
    id: 'L1',
    name: `${dataset.title} · day`,
    visible: true,
    opacity: 1,
    overlays: [],
    restore: {
      focusMode: true,
      downloaded: {},
      appliedRender: look,
      activeGroupIndex: 0,
      selectedIds: ['A'],
      itemIds: ['A'],
      groupItemIds: [['A']],
      aoi: AOI,
      cropToAoi: true,
      datasetId: dataset.id,
      indexOnly: true,
    },
  };
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': status >= 400 ? 'application/problem+json' : 'application/json' } });
const measured = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as Response;
const ESTIMATE = { estimate: { size: 4_000_000, duration: 'PT3.4S', outputPixels: 1_000_000, inputPixels: 2_000_000, inputBytes: 4_000_000, assets: 2, units: 1 }, skippedItems: [] };
const VALUES = { count: 900, min: 0, max: 200, percentile_2: 10, percentile_98: 190, unit: null };

let container: HTMLDivElement;
let root: Root;
let fetchMock: ReturnType<typeof vi.fn>;

function setApp(dataset: DatasetOption, look: object) {
  const items = dataset === OPTICAL ? [scene('A', dataset.id, ['red', 'green', 'blue', 'nir'], 'uint16')] : [scene('A', dataset.id, ['data'], 'float32')];
  useAppStore.setState({
    datasets: [dataset],
    datasetId: dataset.id,
    items,
    groups: [{ key: ['2026-07-01'], label: '2026-07-01', items }],
    activeGroupIndex: 0,
    selectedIds: [],
    aoi: AOI,
    aoiPoint: null,
    layers: [layerOf(dataset, look)],
    focusMode: false,
    downloaded: {},
    error: null,
    dock: 'layers',
  });
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  localStorage.clear();
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/processing/processes/recipe?dataset=sentinel-2-c1-l2a') return json(s2);
    if (url === '/processing/processes/recipe?dataset=cop-dem-glo-30') return json(dem);
    if (init?.method === 'POST' && url.endsWith('/estimate')) return json(ESTIMATE);
    if (init?.method === 'POST' && url.endsWith('/statistics')) return measured({ bands: [], exact: true, factor: 1 });
    if (url.includes('/statistics?')) return measured(Object.fromEntries(new URL(url, 'http://localhost').searchParams.getAll('band').map((_, i) => [`b${i + 1}`, VALUES])));
    if (init?.method === 'POST' && url.endsWith('/execution')) {
      return json({ processID: 'recipe', type: 'process', jobID: NEW_JOB, status: 'accepted', message: '', progress: 0, created: '2026-11-17T10:00:00Z', expires: new Date(Date.now() + 7 * 86_400_000).toISOString(), recipeID: 'r', links: [] }, 201);
    }
    return json({ title: 'Not found' }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  useProcessingStore.getState().resetDraft();
  useProcessingStore.setState({ open: false, descriptions: {}, crs: {}, jobs: [], groups: [], preview: null });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  vi.useRealTimers();
  act(() => root.unmount());
  container.remove();
  resetJobs();
  localStorage.clear();
  vi.unstubAllGlobals();
});

async function flush() {
  await act(async () => {
    for (let i = 0; i < 12; i++) await Promise.resolve();
  });
}

const store = () => useProcessingStore.getState();
const infoChips = () => [...container.querySelectorAll('section[aria-label="Bands"] .pp-chips .seg')].map((c) => c.textContent);
const stepForms = () => container.querySelectorAll('.pp-steps > li').length;
const show = () => container.querySelector<HTMLSelectElement>('section[aria-label="Preview on the map"] .pp-show select');

// "Process" in the row of the layer, then the preview after its pause.
async function processLayer() {
  act(() => root.render(<><LayerManager /><ProcessingPanel /></>));
  act(() => container.querySelector<HTMLButtonElement>('.layer-row [data-col="process"]')!.dispatchEvent(new MouseEvent('click', { bubbles: true })));
  await flush();
  vi.useFakeTimers();
  act(() => {
    vi.advanceTimersByTime(400);
  });
  await flush();
}

async function placedOrder(): Promise<Order> {
  await act(async () => { await store().reviewOrder(); });
  await flush();
  await act(async () => { await store().startJob(); });
  const execution = fetchMock.mock.calls.find(([u, init]) => String(u).endsWith('/execution') && (init as RequestInit)?.method === 'POST');
  return JSON.parse((execution![1] as RequestInit).body as string).inputs.recipe as Order;
}

describe('"Process" at a layer of a composite', () => {
  beforeEach(() => setApp(OPTICAL, { index: 'false_colour_ir', rescale: '0,0.5;0,0.3;0,0.3' }));

  it('opens on its three channels, their Band math steps first and locked, and none of the raw bands', async () => {
    await processLayer();
    expect(infoChips()).toEqual(['false_colour_ir_r', 'false_colour_ir_g', 'false_colour_ir_b']);
    expect(stepForms()).toBe(0);
    expect(store().steps.map((step) => step.values)).toEqual([
      expect.objectContaining({ expression: 'nir', name: 'false_colour_ir_r' }),
      expect.objectContaining({ expression: 'red', name: 'false_colour_ir_g' }),
      expect.objectContaining({ expression: 'green', name: 'false_colour_ir_b' }),
    ]);
    expect(store().fixed?.result).toMatchObject({ locked: 3, bands: ['false_colour_ir_r', 'false_colour_ir_g', 'false_colour_ir_b'] });
  });

  it('previews the colour picture of the three channels with the range of each, as "Quick processing" draws it', async () => {
    await processLayer();
    act(() => store().setOutput(['false_colour_ir_r', 'false_colour_ir_g', 'false_colour_ir_b']));
    act(() => {
      vi.advanceTimersByTime(400);
    });
    await flush();
    expect(show()?.value).toBe(RGB);
    const tiles = new URL(store().preview!.scenes[0].url, 'http://localhost').searchParams;
    expect(tiles.getAll('band')).toEqual(['false_colour_ir_r', 'false_colour_ir_g', 'false_colour_ir_b']);
    expect(tiles.getAll('rescale')).toEqual(['0,0.5', '0,0.3', '0,0.3']);
    expect(tiles.get('colormap_name')).toBeNull();
  });

  it('runs as one ordinary order of the three steps', async () => {
    await processLayer();
    act(() => store().setOutput(['false_colour_ir_r', 'false_colour_ir_g', 'false_colour_ir_b']));
    vi.useRealTimers();
    const order = await placedOrder();
    expect(order.steps.map((step) => step.params)).toEqual([
      { expression: 'nir', name: 'false_colour_ir_r' },
      { expression: 'red', name: 'false_colour_ir_g' },
      { expression: 'green', name: 'false_colour_ir_b' },
    ]);
    expect(order.output).toMatchObject({ bands: ['false_colour_ir_r', 'false_colour_ir_g', 'false_colour_ir_b'] });
  });
});

describe('"Process" at a layer of a step', () => {
  it('opens on the band it adds, the step locked, with the values chosen for its parameters', async () => {
    setApp(HEIGHTS, { index: 'hillshade', presetParams: { azimuth: 90 }, colormapName: 'greys_r', rescale: '0,255' });
    await processLayer();
    expect(infoChips()).toEqual(['hillshade']);
    expect(stepForms()).toBe(0);
    expect(store().steps).toHaveLength(1);
    expect(store().steps[0]).toMatchObject({ op: 'terrain', opVersion: 1, values: expect.objectContaining({ product: 'hillshade', azimuth: '90', altitude: '45' }) });
    act(() => store().setOutput(['hillshade']));
    vi.useRealTimers();
    const order = await placedOrder();
    expect(order.steps).toEqual([{ op: 'terrain', op_version: 1, params: { ...HILLSHADE.params, azimuth: 90 } }]);
    expect(order.output).toMatchObject({ bands: ['hillshade'] });
  });

  it('opens a layer whose step the dataset no longer offers as a layer of the raw bands', async () => {
    setApp(HEIGHTS, { index: 'slope', colormapName: 'rdylgn_r', rescale: '0,60' });
    await processLayer();
    expect(store().fixed?.result ?? null).toBeNull();
    expect(infoChips().some((chip) => chip?.startsWith('data'))).toBe(true);
  });
});
