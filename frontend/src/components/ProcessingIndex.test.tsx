// @vitest-environment jsdom
//
// "Process" at a layer or a view that shows an index (NM4-14b, Otto 1.11.2026): the panel opens with the index as the one band, named like
// the index, and not the raw bands of the scenes; its Band math step stands first, locked, as the steps of a result do. No backend:
// `fetch` answers the process description, the estimate and the placing of a job.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import { SENTINEL_2_PRESETS } from '../fixtures/indexPresets';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import { bboxToPolygon } from '../geoUtils';
import type { MapLayer } from '../layers';
import type { Order } from '../processing';
import { resetJobs, setTrackerOptions, useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection, DownloadedInfo, StacItem } from '../types';
import LayerManager from './LayerManager';
import ProcessingPanel from './ProcessingPanel';
import ViewerControls from './ViewerControls';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const DATASET = 'sentinel-2-c1-l2a';
const NEW_JOB = 'ZyXwVuTsRqPoNmLkJiHg_-';
const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const AOI = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);
const band = { data_type: 'uint16', nodata: 0 };
const asset = (extra: object = {}) => ({ href: 'https://example.org/b.tif', type: COG, 'raster:bands': [band], ...extra });
const NDVI = { index: 'NDVI', colormapName: 'rdylgn', rescale: '-1,1' };

function scene(id: string): StacItem {
  const bbox: [number, number, number, number] = [10, 50, 11, 51];
  return {
    id,
    collection: DATASET,
    bbox,
    geometry: bboxToPolygon(bbox),
    properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 },
    assets: { red: asset(), green: asset(), blue: asset(), nir: asset(), swir16: asset(), swir22: asset(), scl: asset({ gsd: 20, 'raster:bands': [{ data_type: 'uint8', nodata: 0 }] }) },
  };
}

function dataset(tier = 'processing'): DatasetOption {
  return {
    id: DATASET,
    title: 'Sentinel-2 L2A',
    viewable: true,
    groupBy: ['datetime'],
    zoom: { min: 8, max: 14 },
    browse: 'quicklook',
    quicklookNodataMax: null,
    resultsGroupBy: ['datetime'],
    hasTimeAxis: true,
    collection: {
      id: DATASET,
      title: 'Sentinel-2 L2A',
      'earthx:format': 'cog',
      'earthx:license_flags': { tier },
      'earthx:capabilities': { interpolation: true },
      'earthx:true_color': ['red', 'green', 'blue'],
      'earthx:band_units': { red: 'reflectance', green: 'reflectance', blue: 'reflectance', nir: 'reflectance', swir16: 'reflectance', swir22: 'reflectance', visual: null },
      'earthx:index_presets': SENTINEL_2_PRESETS,
    } as unknown as Collection,
  };
}

const info = (id: string): DownloadedInfo => ({ datasetId: DATASET, tileUrl: `/t/${id}/{z}/{x}/{y}`, bounds: [10, 50, 11, 51], asset: 'visual', minZoom: 8, maxZoom: 14 });

function indexLayer(look: object = NDVI, over: Partial<MapLayer['restore']> = {}): MapLayer {
  return {
    id: 'L1',
    name: 'Sentinel-2 L2A · day',
    visible: true,
    opacity: 1,
    overlays: [],
    restore: {
      focusMode: true,
      downloaded: { S2B_A: info('S2B_A'), S2B_B: info('S2B_B') },
      appliedRender: look,
      activeGroupIndex: 0,
      selectedIds: ['S2B_A', 'S2B_B'],
      itemIds: ['S2B_A', 'S2B_B'],
      groupItemIds: [['S2B_A', 'S2B_B']],
      aoi: AOI,
      cropToAoi: true,
      datasetId: DATASET,
      ...over,
    },
  };
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': status >= 400 ? 'application/problem+json' : 'application/json' } });
const ESTIMATE = { estimate: { size: 4_000_000, duration: 'PT3.4S', outputPixels: 1_000_000, inputPixels: 2_000_000, inputBytes: 4_000_000, assets: 2, units: 1 }, skippedItems: [] };

let container: HTMLDivElement;
let root: Root;
let fetchMock: ReturnType<typeof vi.fn>;

function setApp(over: object = {}) {
  const items = [scene('S2B_A'), scene('S2B_B')];
  useAppStore.setState({
    datasets: [dataset()],
    datasetId: DATASET,
    items,
    groups: [{ key: ['2026-07-01'], label: '2026-07-01', items }],
    activeGroupIndex: 0,
    selectedIds: [],
    aoi: AOI,
    aoiPoint: null,
    layers: [indexLayer()],
    focusMode: false,
    downloaded: {},
    error: null,
    dock: 'layers',
    ...over,
  });
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  localStorage.clear();
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === `/processing/processes/recipe?dataset=${DATASET}`) return json(s2);
    if (init?.method === 'POST' && url.endsWith('/estimate')) return json(ESTIMATE);
    if (init?.method === 'POST' && url.endsWith('/execution')) {
      return json({ processID: 'recipe', type: 'process', jobID: NEW_JOB, status: 'accepted', message: '', progress: 0, created: '2026-11-01T10:00:00Z', expires: new Date(Date.now() + 7 * 86_400_000).toISOString(), recipeID: 'r', links: [] }, 201);
    }
    return json({ title: 'Not found' }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  useProcessingStore.getState().resetDraft();
  useProcessingStore.setState({ open: false, descriptions: {}, crs: {}, jobs: [], groups: [], preview: null });
  setApp();
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  setTrackerOptions({});
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
const click = (element: HTMLElement | null | undefined) => {
  if (!element) throw new Error(`nothing to click in ${container.textContent}`);
  act(() => element.dispatchEvent(new MouseEvent('click', { bubbles: true })));
};
const gear = () => container.querySelector<HTMLButtonElement>('.layer-row [data-col="process"]')!;
const infoChips = () => [...container.querySelectorAll('section[aria-label="Bands"] .pp-chip')].map((c) => c.textContent);
const dataChips = () => [...container.querySelectorAll('section[aria-label="Output"] [aria-label="Bands of the data"] .pp-chip')].map((c) => c.textContent);
const stepForms = () => container.querySelectorAll('.pp-steps > li').length;

async function processLayer() {
  act(() => root.render(<><LayerManager /><ProcessingPanel /></>));
  click(gear());
  await flush();
}

describe('"Process" at a layer that shows an index', () => {
  it('opens the panel with the index as the one band, named like the index, and none of the raw bands', async () => {
    await processLayer();
    expect(store().open).toBe(true);
    expect(infoChips()).toEqual(['NDVI']);
    expect(dataChips()).toEqual(['NDVI']);
    expect(container.textContent).not.toMatch(/\b(red|green|blue|nir|swir16|swir22)\b/u);
    expect(store().fixed?.result).toMatchObject({ bands: ['NDVI'], locked: 1, title: 'Sentinel-2 L2A · day' });
  });

  it('keeps its Band math step first and locked: no step to see, change or remove', async () => {
    await processLayer();
    expect(stepForms()).toBe(0);
    expect(store().steps).toHaveLength(1);
    expect(store().steps[0]).toMatchObject({ op: 'band_math', opVersion: 2, values: { expression: '(nir - red) / (nir + red)', name: 'NDVI' } });
  });

  it('takes the scenes and the AOI of the layer, and has the one band in the output, as a dataset of one band has', async () => {
    await processLayer();
    expect(store().fixed).toMatchObject({ itemIds: ['S2B_A', 'S2B_B'] });
    expect(store().fixed?.aoi).toMatchObject({ type: 'Polygon' });
    expect(store().output).toEqual(['NDVI']);
  });

  it('runs as one ordinary order: the index step first, a new step behind it that reads the index', async () => {
    await processLayer();
    act(() => store().setOutput(['NDVI']));
    act(() => store().addStep('band_math', 2));
    const added = store().steps[1];
    act(() => store().updateStep(added.key, 'expression', 'NDVI * 2'));
    act(() => store().renameResult(added.key, 'Twice'));
    act(() => store().setOutput(['Twice']));
    await flush();
    await act(async () => { await store().reviewOrder(); });
    await flush();
    await act(async () => { await store().startJob(); });
    const execution = fetchMock.mock.calls.find(([u, init]) => String(u).endsWith('/execution') && (init as RequestInit)?.method === 'POST');
    const order = JSON.parse((execution![1] as RequestInit).body as string).inputs.recipe as Order;
    expect(order.steps.map((s) => s.params)).toEqual([
      { expression: '(nir - red) / (nir + red)', name: 'NDVI' },
      { expression: 'NDVI * 2', name: 'Twice' },
    ]);
    expect(order.output).toMatchObject({ bands: ['Twice'] });
    expect(order.inputs[0].groups).toEqual([['S2B_A', 'S2B_B']]);
  });

  it('cannot read a raw band in a new step: the pool is the index alone', async () => {
    await processLayer();
    act(() => store().addStep('band_math', 2));
    const added = store().steps[1];
    act(() => store().updateStep(added.key, 'expression', 'nir * 2'));
    await flush();
    expect(container.textContent).toMatch(/'nir' is not a band name/u);
  });

  it('opens on whole scenes for a layer that is not a crop, without an AOI', async () => {
    setApp({ layers: [indexLayer(NDVI, { cropToAoi: false, aoi: null })] });
    await processLayer();
    expect(infoChips()).toEqual(['NDVI']);
    expect(store().fixed?.aoi).toBeNull();
  });

  it('names the index it was added with, whichever it is', async () => {
    setApp({ layers: [indexLayer({ index: 'NDWI', colormapName: 'rdbu', rescale: '-1,1' })] });
    await processLayer();
    expect(infoChips()).toEqual(['NDWI']);
    expect(store().steps[0].values).toMatchObject({ expression: '(green - nir) / (green + nir)', name: 'NDWI' });
  });

  it('opens a layer without an index as before, on the raw bands of the scenes', async () => {
    setApp({ layers: [indexLayer({ rescale: '0,3000' })] });
    await processLayer();
    expect(store().open).toBe(true);
    expect(store().fixed?.result ?? null).toBeNull();
    expect(infoChips().length).toBeGreaterThan(1);
    expect(infoChips().some((chip) => chip?.startsWith('red'))).toBe(true);
  });

  it('tells why it did not open, where the licence does not allow processing', async () => {
    setApp({ datasets: [dataset('view')] });
    act(() => root.render(<LayerManager />));
    expect(gear().disabled).toBe(true);
    await store().extendIndexLayer('L1');
    expect(store().open).toBe(false);
    expect(useAppStore.getState().error).toMatch(/does not allow processing/u);
  });
});

describe('"Process" in the view that shows an index (Otto, 1.11.2026: the index is only a picture there)', () => {
  const showView = (look: object) => {
    const items = [scene('S2B_A'), scene('S2B_B')];
    setApp({
      layers: [],
      focusMode: true,
      cropToAoi: true,
      viewAoi: AOI,
      downloaded: { S2B_A: info('S2B_A'), S2B_B: info('S2B_B') },
      selectedIds: [],
      items,
      groups: [{ key: ['2026-07-01'], label: '2026-07-01', items }],
      appliedRender: look,
      pendingColormapName: '',
      pendingVmin: '',
      pendingVmax: '',
      pendingIndex: (look as { index?: string }).index ?? '',
      mosaics: {},
      shownImage: null,
    });
    act(() => root.render(<><ViewerControls /><ProcessingPanel /></>));
  };
  const processButton = () => [...container.querySelectorAll('button')].find((b) => b.textContent?.includes('Process'))!;

  it('opens on the raw bands of the scenes even where an index is applied: no step, no band of the index', async () => {
    showView(NDVI);
    click(processButton());
    await flush();
    expect(store().open).toBe(true);
    expect(store().fixed?.result ?? null).toBeNull();
    expect(store().steps).toEqual([]);
    expect(infoChips().length).toBeGreaterThan(1);
    expect(infoChips().some((chip) => chip?.startsWith('red'))).toBe(true);
    expect(infoChips()).not.toContain('NDVI');
  });

  it('opens on the raw bands where the view shows none, or only has an index chosen and not applied', async () => {
    showView({ rescale: '0,3000' });
    act(() => useAppStore.getState().chooseViewIndex('NDVI'));
    click(processButton());
    await flush();
    expect(store().fixed?.result ?? null).toBeNull();
    expect(infoChips().some((chip) => chip?.startsWith('red'))).toBe(true);
  });
});
