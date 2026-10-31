// @vitest-environment jsdom
//
// ⚙ at the layer of a result (NM4-05b, adr/0019 option 2): the order of the job with its steps locked at the start, new
// steps behind them, and one ordinary order for all of it. No backend: `fetch` answers the process description, the estimate
// and the placing of a job.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import { bboxToPolygon } from '../geoUtils';
import type { MapLayer } from '../layers';
import type { Order } from '../processing';
import { orderAoi } from '../processingOrder';
import {
  EXPIRED_PROCESS_TEXT,
  clipAoiOf,
  layerProcessBlock,
  NO_COPY_TEXT,
  orderView,
  PROCESS_RESULT_TEXT,
  resetJobs,
  selectionState,
  setTrackerOptions,
  useProcessingStore,
  type JobEntry,
} from '../processingStore';
import { useAppStore } from '../store';
import type { Collection, EarthxMask, StacItem } from '../types';
import LayerManager from './LayerManager';
import ProcessingPanel from './ProcessingPanel';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const JOB = 'AbCdEfGhIjKlMnOpQrSt_-';
const NEW_JOB = 'ZyXwVuTsRqPoNmLkJiHg_-';
const GROUP = 'a'.repeat(32);
const DATASET = 'sentinel-2-c1-l2a';
const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const AOI = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);
const OTHER_AOI = bboxToPolygon([10.1, 50.1, 10.2, 50.2]);
// Inside the area of the job, and one that straddles its edge.
const INNER_AOI = bboxToPolygon([10.45, 50.45, 10.5, 50.5]);
const EDGE_AOI = bboxToPolygon([10.5, 50.5, 10.7, 50.7]);
const SCL: EarthxMask = { asset: 'scl', band: 'scl', classes: [{ value: 3, label: 'CLOUD_SHADOWS' }], suggested: [3], reference: 'https://example.org/scl', note: '' };

const band = { data_type: 'uint16', nodata: 0 };
const asset = (extra: object = {}) => ({ href: 'https://example.org/b.tif', type: COG, 'raster:bands': [band], ...extra });

function scene(id: string): StacItem {
  const bbox: [number, number, number, number] = [10, 50, 11, 51];
  return {
    id,
    collection: DATASET,
    bbox,
    geometry: bboxToPolygon(bbox),
    properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 },
    assets: { red: asset(), green: asset(), blue: asset(), nir: asset(), scl: asset({ gsd: 20, 'raster:bands': [{ data_type: 'uint8', nodata: 0 }] }) },
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
      'earthx:format': 'cog',
      'earthx:license_flags': { tier },
      'earthx:capabilities': { interpolation: true },
      'earthx:mask': SCL,
      'earthx:true_color': ['red', 'green', 'blue'],
    } as unknown as Collection,
  };
}

// The order of a job: NDVI from the red and the near infrared, and the result and the red band as the output.
const NDVI_STEP = { op: 'band_math', op_version: 2, params: { expression: '(nir - red) / (nir + red)', name: 'NDVI' } };
function parent(over: Partial<Order> = {}): Order {
  return {
    recipe_version: 2,
    inputs: [{ name: 'input', dataset: DATASET, groups: [['S2B_A']] }],
    aoi: orderAoi(AOI),
    steps: [NDVI_STEP],
    output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['NDVI', 'red'] },
    ...over,
  } as Order;
}

function entry(over: Partial<JobEntry> = {}): JobEntry {
  return {
    jobID: JOB,
    expires: new Date(Date.now() + 86_400_000).toISOString(),
    status: null,
    phase: 'successful',
    archive: 'result.zip',
    bytes: null,
    resampled: false,
    failure: null,
    failureKind: null,
    error: null,
    cancelling: false,
    retrying: false,
    retryRefused: false,
    retryError: null,
    deleting: false,
    deletedUntil: null,
    serverDeleted: false,
    lost: false,
    superseded: false,
    expired: false,
    title: 'NDVI of a field',
    tiles: null,
    statistics: null,
    bands: [],
    range: null,
    bandRanges: {},
    shownBand: null,
    archived: false,
    groupId: GROUP,
    batchId: null,
    part: null,
    order: parent(),
    createdAt: '2026-10-10T12:00:00Z',
    titleDefault: null,
    ...over,
  };
}

function resultLayer(over: Partial<NonNullable<MapLayer['result']>> = {}): MapLayer {
  return {
    id: 'R1',
    name: 'NDVI of a field',
    visible: true,
    opacity: 1,
    overlays: [],
    derived: 'result',
    restore: { focusMode: false, downloaded: {}, appliedRender: {}, activeGroupIndex: 0, selectedIds: [], itemIds: [], groupItemIds: [], aoi: null, cropToAoi: false, datasetId: null },
    result: { jobID: JOB, expires: new Date(Date.now() + 86_400_000).toISOString(), gsd: 10, resampled: false, expired: false, dataType: 'float32', stats: null, ...over },
  } as MapLayer;
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': status >= 400 ? 'application/problem+json' : 'application/json' } });

const ESTIMATE = {
  estimate: { size: 4_000_000, duration: 'PT3.4S', outputPixels: 1_000_000, inputPixels: 2_000_000, inputBytes: 4_000_000, assets: 2, units: 1 },
  skippedItems: [],
};

let container: HTMLDivElement;
let root: Root;
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  localStorage.clear();
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === `/processing/processes/recipe?dataset=${DATASET}`) return json(s2);
    if (init?.method === 'POST' && url.endsWith('/estimate')) return json(ESTIMATE);
    if (init?.method === 'POST' && url.endsWith('/execution')) {
      return json({ processID: 'recipe', type: 'process', jobID: NEW_JOB, status: 'accepted', message: '', progress: 0, created: '2026-10-31T10:00:00Z', expires: new Date(Date.now() + 7 * 86_400_000).toISOString(), recipeID: 'r', links: [] }, 201);
    }
    return json({ title: 'Not found' }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  useProcessingStore.getState().resetDraft();
  useProcessingStore.setState({ open: false, descriptions: {}, crs: {}, jobs: [entry()], groups: [{ id: GROUP, name: 'Work' }], preview: null });
  const items = [scene('S2B_A'), scene('S2B_B')];
  useAppStore.setState({
    datasets: [dataset()],
    datasetId: DATASET,
    items,
    groups: [{ key: ['2026-07-01'], label: '2026-07-01', items }],
    activeGroupIndex: 0,
    selectedIds: ['S2B_B'],
    aoi: OTHER_AOI,
    aoiPoint: null,
    layers: [resultLayer()],
    error: null,
    dock: 'layers',
  });
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
  vi.useRealTimers();
});

async function flush() {
  await act(async () => {
    for (let i = 0; i < 10; i++) await Promise.resolve();
  });
}

const store = () => useProcessingStore.getState();
const button = (label: string | RegExp, within: Element = container) =>
  [...within.querySelectorAll('button')].find((b) => (typeof label === 'string' ? b.textContent?.trim() === label : label.test(b.textContent ?? '')));
const click = (element: HTMLElement | undefined) => {
  if (!element) throw new Error(`nothing to click in ${container.textContent}`);
  act(() => element.dispatchEvent(new MouseEvent('click', { bubbles: true })));
};
function typeInto(input: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const prototype = input instanceof HTMLTextAreaElement ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  act(() => {
    Object.getOwnPropertyDescriptor(prototype, 'value')!.set!.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}
const gear = () => container.querySelector<HTMLButtonElement>('.layer-row [data-col="process"]')!;
const execution = () => fetchMock.mock.calls.filter(([u, init]) => String(u).endsWith('/execution') && init?.method === 'POST');
const sent = () => JSON.parse(execution()[0][1].body).inputs.recipe as Order;
const output = () => store().output;
const infoChips = () => [...container.querySelectorAll('section[aria-label="Bands"] .pp-chip')].map((c) => c.textContent);
const dataGroup = () => container.querySelector('section[aria-label="Output"] [aria-label="Bands of the data"]')!;
const dataChips = () => [...dataGroup().querySelectorAll('.pp-chip')].map((c) => c.textContent);
const pressed = () => [...dataGroup().querySelectorAll('.pp-chip')].filter((c) => c.getAttribute('aria-pressed') === 'true').map((c) => c.textContent);

// ⚙ at the layer, then the panel.
async function process() {
  act(() =>
    root.render(
      <>
        <LayerManager />
        <ProcessingPanel />
      </>,
    ),
  );
  click(gear());
  await flush();
}

describe('whether a result layer can be processed further', () => {
  const layer = () => resultLayer();
  const jobs = (order: Order | null = parent()) => [{ jobID: JOB, order }];
  const datasets = () => [dataset()];

  it('can, where the browser keeps the order of its job', () => {
    expect(layerProcessBlock(layer(), datasets(), jobs())).toBeNull();
  });

  it('cannot without the order: no job in the list, or a job whose copy is gone', () => {
    expect(layerProcessBlock(layer(), datasets(), [])).toBe(NO_COPY_TEXT);
    expect(layerProcessBlock(layer(), datasets(), jobs(null))).toBe(NO_COPY_TEXT);
    expect(layerProcessBlock(layer(), datasets())).toBe(NO_COPY_TEXT);
  });

  it('can when the result has expired: the chain runs from the scenes all the same', () => {
    expect(layerProcessBlock(resultLayer({ expired: true }), datasets(), jobs())).toBeNull();
  });

  it('cannot where the dataset does not allow processing or is not there', () => {
    expect(layerProcessBlock(layer(), [dataset('view')], jobs())).toMatch(/does not allow processing/u);
    expect(layerProcessBlock(layer(), [], jobs())).toBe('Pick a dataset first.');
  });

  it('cannot for the copy of an export, which has no bands', () => {
    const crop = { ...parent(), steps: [], output: { kind: 'crop', format: 'cog', resolution_factor: 1, extent: 'bbox(aoi ∩ footprints)', mask: 'file' } } as Order;
    expect(layerProcessBlock(layer(), datasets(), jobs(crop))).toBe('An export has no bands to process further.');
  });

  it('still cannot for a preview layer', () => {
    expect(layerProcessBlock({ ...layer(), derived: 'preview', result: undefined }, datasets(), jobs())).toBe('A result cannot be processed further yet.');
  });
});

describe('the ⚙ of a result layer', () => {
  it('is there and active with the order of the job, and the row keeps its nine places', () => {
    act(() => root.render(<LayerManager />));
    expect(gear().tagName).toBe('BUTTON');
    expect(gear().disabled).toBe(false);
    expect(gear().title).toBe(PROCESS_RESULT_TEXT);
    expect(container.querySelector('.layer-row')?.children).toHaveLength(9);
  });

  it('is active for an expired result, and says that everything runs again from the scenes', () => {
    useAppStore.setState({ layers: [resultLayer({ expired: true })] });
    act(() => root.render(<LayerManager />));
    expect(gear().disabled).toBe(false);
    expect(gear().title).toBe(EXPIRED_PROCESS_TEXT);
  });

  it('is not there without the order of its job: the place stays empty, and nothing brings the order back', async () => {
    useProcessingStore.setState({ jobs: [entry({ order: null })] });
    act(() => root.render(<LayerManager />));
    expect(gear().tagName).toBe('SPAN');
    expect(gear().getAttribute('aria-hidden')).toBe('true');
    expect(container.querySelector('.layer-row')?.children).toHaveLength(9);
    // A call that bypasses the row does nothing, and says why.
    await store().extendResult('R1');
    expect(store().open).toBe(false);
    expect(useAppStore.getState().error).toBe(NO_COPY_TEXT);
  });

  it('is not there for a result whose job is not in the list of this browser', () => {
    useProcessingStore.setState({ jobs: [] });
    act(() => root.render(<LayerManager />));
    expect(gear().tagName).toBe('SPAN');
  });

  it('tells why it did not open, when the licence changed since', async () => {
    useAppStore.setState({ datasets: [dataset('view')] });
    act(() => root.render(<LayerManager />));
    expect(gear().disabled).toBe(true);
    expect(gear().title).toMatch(/does not allow processing/u);
    // A call that bypasses the button does nothing either, and says why.
    await store().extendResult('R1');
    expect(store().open).toBe(false);
    expect(useAppStore.getState().error).toMatch(/does not allow processing/u);
  });

  it('tells why the panel did not open when the scenes of the job are no longer in the catalog', async () => {
    useProcessingStore.setState({ jobs: [entry({ order: parent({ inputs: [{ name: 'input', dataset: DATASET, groups: [['S2B_GONE']] }] }) })] });
    await process();
    expect(store().open).toBe(false);
    expect(store().fixed).toBeNull();
    expect(useAppStore.getState().error).toMatch(/S2B_GONE/u);
  });
});

describe('the panel from a result', () => {
  it('opens on the order of the job: its steps locked, its output as the output, its scenes and area fixed', async () => {
    await process();
    expect(store().open).toBe(true);
    expect(store().steps.map((s) => s.op)).toEqual(['band_math']);
    expect(store().fixed?.result?.locked).toBe(1);
    expect(store().fixed?.result?.bands).toEqual(['NDVI', 'red']);
    expect(output()).toEqual(['NDVI', 'red']);
    // "Whole scene" is the area of the result; the job's AOI is the area of the order.
    expect(store().area).toBe('scene');
    expect(store().fixed?.aoi).toEqual(AOI);
    // The scenes and the AOI of the job, not those the map and the list hold now.
    expect(useAppStore.getState().selectedIds).toEqual(['S2B_A']);
    expect(container.querySelector('section[aria-label="Selection"]')?.textContent).toContain('S2B_A');
  });

  it('does not show the steps of the job as steps, and has no line for the origin', async () => {
    await process();
    expect(container.querySelector('.pp-step')).toBeNull();
    expect(container.querySelector('section[aria-label="Processing steps"] ol')).toBeNull();
    expect(container.textContent).not.toContain('From result');
    expect(container.querySelector('.pp-area .tip')).toBeNull();
  });

  it('offers the output of the job as its bands, and no other: the stock it did not keep is out of sight', async () => {
    await process();
    expect(infoChips()).toEqual(['NDVI', 'red']);
    expect(dataChips()).toEqual(['NDVI', 'red']);
    expect(container.querySelector('section[aria-label="Output"] [aria-label="New bands"]')).toBeNull();
    expect(pressed()).toEqual(['NDVI', 'red']);
  });

  it('has the same area choice as the panel of a scene: "Whole scene" is the result, "AOI only" an AOI inside it', async () => {
    await process();
    const selection = container.querySelector('section[aria-label="Selection"]')!;
    expect(button('Whole scene', selection)?.getAttribute('aria-pressed')).toBe('true');
    expect(button('AOI only', selection)?.getAttribute('aria-pressed')).toBe('false');
    expect(button('AOI only', selection)?.disabled).toBe(false);
    expect(button('Whole scene', selection)?.title).toBe('Process the area of the result');
    expect(selection.querySelector('[aria-label="Run as"]')).toBeNull();
    expect(selection.querySelector('.pp-fixed')).toBeNull();
    expect(selection.textContent).toContain('Load recipe');
  });

  it('"AOI only" is locked until the map has an AOI', async () => {
    await process();
    act(() => useAppStore.getState().clearAoi());
    expect(button('AOI only')?.disabled).toBe(true);
    expect(button('AOI only')?.title).toBe('Draw an AOI first');
  });

  it('sends the area of the result for "Whole scene", whatever AOI the map holds', async () => {
    await process();
    act(() => useAppStore.setState({ aoi: INNER_AOI }));
    click(button('Review'));
    await flush();
    click(button('Start job'));
    await flush();
    expect(sent().aoi).toEqual(orderAoi(AOI));
  });

  it('sends the AOI of the map for "AOI only", where it lies inside the result', async () => {
    await process();
    act(() => useAppStore.setState({ aoi: INNER_AOI }));
    click(button('AOI only'));
    expect(store().area).toBe('aoi');
    const view = orderView(selectionState(useAppStore.getState()), store());
    expect(view.inner).toBe(true);
    expect(view.outside).toBe(false);
    click(button('Review'));
    await flush();
    click(button('Start job'));
    await flush();
    expect(sent().aoi).toEqual(orderAoi(INNER_AOI));
    expect(sent().inputs[0].groups).toEqual([['S2B_A']]);
  });

  it('turns an AOI away that misses the result, and starts nothing, though the scene under it is there', async () => {
    await process();
    act(() => useAppStore.setState({ aoi: OTHER_AOI }));
    click(button('AOI only'));
    const view = orderView(selectionState(useAppStore.getState()), store());
    expect(view.outside).toBe(true);
    expect(view.built?.order).toBeNull();
    expect(container.querySelector('.hint-text.error')?.textContent).toBe('The AOI does not meet the result.');
    expect((button('Start job') as HTMLButtonElement).disabled).toBe(true);
    click(button('Review'));
    await flush();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/estimate'))).toBe(false);
  });

  it('computes only the part of an AOI that lies in the result', async () => {
    await process();
    act(() => useAppStore.setState({ aoi: EDGE_AOI }));
    click(button('AOI only'));
    const view = orderView(selectionState(useAppStore.getState()), store());
    expect(view.outside).toBe(false);
    // [10.5, 50.5]–[10.7, 50.7] of the map, [10.4, 50.4]–[10.6, 50.6] of the result: what they share is a square of a tenth.
    const box = (view.aoi as GeoJSON.Polygon).coordinates[0].reduce(
      (b, [x, y]) => ({ x0: Math.min(b.x0, x), x1: Math.max(b.x1, x), y0: Math.min(b.y0, y), y1: Math.max(b.y1, y) }),
      { x0: 99, x1: -99, y0: 99, y1: -99 },
    );
    expect(box).toEqual({ x0: 10.5, x1: 10.6, y0: 50.5, y1: 50.6 });
    click(button('Review'));
    await flush();
    click(button('Start job'));
    await flush();
    expect(sent().aoi).toEqual(view.aoi && orderAoi(view.aoi as GeoJSON.Polygon));
    expect(sent().aoi).not.toEqual(orderAoi(EDGE_AOI));
    expect(container.querySelector('.hint-text.error')).toBeNull();
  });

  it('draws no preview for an AOI that misses the result, and one cut to the part that is inside otherwise', async () => {
    vi.useFakeTimers();
    await process();
    const settle = async () => {
      await act(async () => {
        vi.advanceTimersByTime(500);
        for (let i = 0; i < 10; i++) await Promise.resolve();
      });
    };
    act(() => useAppStore.setState({ aoi: INNER_AOI }));
    click(button('AOI only'));
    await settle();
    expect(store().preview?.clipToAoi).toBe(true);
    expect(store().preview?.clipAoi).toEqual(INNER_AOI);
    act(() => useAppStore.setState({ aoi: EDGE_AOI }));
    await settle();
    const cut = store().preview?.clipAoi as GeoJSON.Polygon | undefined;
    expect(cut).toBeDefined();
    expect(cut?.coordinates[0]).not.toEqual(EDGE_AOI.coordinates[0]);
    act(() => useAppStore.setState({ aoi: OTHER_AOI }));
    await settle();
    expect(store().preview).toBeNull();
  });

  it('puts the preview above the result: the entry "Results" goes to the top of the layers', async () => {
    useAppStore.setState({ layers: [resultLayer(), { ...resultLayer(), id: 'R2' }], resultsAt: 2 });
    await process();
    expect(useAppStore.getState().resultsAt).toBe(0);
  });

  it('goes back to the area of the result with "Whole scene"', async () => {
    await process();
    act(() => useAppStore.setState({ aoi: EDGE_AOI }));
    click(button('AOI only'));
    click(button('Whole scene'));
    const view = orderView(selectionState(useAppStore.getState()), store());
    expect(view.outside).toBe(false);
    expect(view.aoi).toEqual(AOI);
  });

  it('for a result of whole scenes, "AOI only" has to lie inside the scenes', async () => {
    const whole = parent();
    delete whole.aoi;
    useProcessingStore.setState({ jobs: [entry({ order: whole })] });
    await process();
    act(() => useAppStore.setState({ aoi: INNER_AOI }));
    click(button('AOI only'));
    expect(orderView(selectionState(useAppStore.getState()), store()).outside).toBe(false);
    act(() => useAppStore.setState({ aoi: bboxToPolygon([20, 60, 21, 61]) }));
    expect(orderView(selectionState(useAppStore.getState()), store()).outside).toBe(true);
  });

  it('cuts the preview to the area of the result, and to the AOI of the map only for "AOI only"', async () => {
    await process();
    expect(clipAoiOf(store(), INNER_AOI)).toEqual(AOI);
    click(button('AOI only'));
    expect(clipAoiOf(store(), INNER_AOI)).toEqual(INNER_AOI);
  });

  it('does not let the store change the locked steps: not their values, name, place, or the step itself', async () => {
    await process();
    const [locked] = store().steps;
    const before = JSON.stringify(store().steps);
    store().updateStep(locked.key, 'expression', 'red');
    store().renameResult(locked.key, 'NDWI');
    store().setNameProblem(locked.key, 'broken');
    store().moveStep(locked.key, 1);
    store().removeStep(locked.key);
    expect(JSON.stringify(store().steps)).toBe(before);
    expect(store().nameProblems).toEqual({});
    expect(output()).toEqual(['NDVI', 'red']);
  });

  it('loads a recipe behind the steps of the job: they stay in front, and the recipe\'s come after', async () => {
    await process();
    const recipe = parent({
      steps: [{ op: 'band_math', op_version: 2, params: { expression: 'NDVI * 2', name: 'double' } }],
      output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['double', 'NDVI'] },
    });
    const loaded = await store().loadRecipe(JSON.stringify(recipe));
    expect(loaded.ok).toBe(true);
    expect(store().steps.map((s) => s.values.name)).toEqual(['NDVI', 'double']);
    expect(store().fixed?.result?.locked).toBe(1);
    expect(output()).toEqual(['double', 'NDVI']);
    const view = orderView(selectionState(useAppStore.getState()), store());
    expect(view.fresh.map((r) => r.name)).toEqual(['double']);
    expect(view.nameBlock).toBeNull();
    expect(view.built?.order?.steps.map((s) => s.params.name)).toEqual(['NDVI', 'double']);
  });

  it('puts a new step behind the locked ones, and nothing in front of them', async () => {
    await process();
    click(button('＋ Band math'));
    click(button('＋ Normalize'));
    expect(store().steps.map((s) => s.op)).toEqual(['band_math', 'band_math', 'normalize']);
    const [, added, normalize] = store().steps;
    store().moveStep(added.key, -1);
    expect(store().steps.map((s) => s.key)).toEqual([store().steps[0].key, added.key, normalize.key]);
    store().moveStep(added.key, 1);
    expect(store().steps.map((s) => s.op)).toEqual(['band_math', 'normalize', 'band_math']);
    // The first step shown has nothing to move up to, and the steps of the job are not among them.
    const forms = [...container.querySelectorAll('.pp-step')];
    expect(forms).toHaveLength(2);
    expect((button(/Up/u, forms[0]) as HTMLButtonElement).disabled).toBe(true);
    expect(forms[0].getAttribute('aria-label')).toBe('Step 1: Band math');
  });

  it('keeps the bands of the job in the stock: a new step reads them, and so does the output', async () => {
    await process();
    click(button('＋ Band math'));
    const field = container.querySelector<HTMLTextAreaElement>('textarea[id$="-expression"]')!;
    typeInto(field, 'NDVI * 2 + red');
    // The result of the job is a chip of the new step, and the expression naming it is no problem.
    const chips = container.querySelectorAll('[aria-label="Results of earlier steps"] .pp-chip');
    expect([...chips].map((c) => c.textContent)).toEqual(['NDVI']);
    expect(container.querySelector('.pp-step .hint-text.error')).toBeNull();
    const view = orderView(selectionState(useAppStore.getState()), store());
    expect(view.results.map((r) => r.name)).toEqual(['NDVI', 'result']);
    expect(view.inherited).toEqual(['NDVI']);
    expect(view.fresh.map((r) => r.name)).toEqual(['result']);
    expect(view.nameBlock).toBeNull();
    // Only the new result is "New"; the new result comes into the output ticked, the output of the job stays; the file holds the
    // results first.
    expect([...container.querySelectorAll('[aria-label="New bands"] .pp-chip')].map((c) => c.textContent)).toEqual(['result']);
    expect(output()).toEqual(['NDVI', 'red', 'result']);
    expect(view.output).toEqual(['NDVI', 'result', 'red']);
    expect(view.built?.order?.output.kind === 'raster' && view.built.order.output.bands).toEqual(['NDVI', 'result', 'red']);
  });

  it('does not let a new step read a band the job did not keep, nor take its name', async () => {
    await process();
    click(button('＋ Band math'));
    const field = container.querySelector<HTMLTextAreaElement>('textarea[id$="-expression"]')!;
    // `nir` is in the data and was read by the job, but it is not in the output.
    typeInto(field, 'nir * 2');
    expect(container.querySelector('.pp-step .hint-text.error')?.textContent).toBe("'nir' is not a band name");
    expect(orderView(selectionState(useAppStore.getState()), store()).nameBlock).toBe("Step 2: 'nir' is not a band name");
    expect(orderView(selectionState(useAppStore.getState()), store()).built?.order).toBeNull();
    expect((button('Review') as HTMLButtonElement).disabled).toBe(true);
    // Its name is taken all the same: a result of that name would hide the band in the chain.
    store().renameResult(store().steps[1].key, 'nir');
    expect(store().steps[1].values.name).toBe('result');
    typeInto(field, 'red * 2');
    expect(orderView(selectionState(useAppStore.getState()), store()).nameBlock).toBeNull();
  });

  it('keeps a result of the job that its output did not keep out of sight, too, but its name is taken', async () => {
    const order = parent({
      steps: [NDVI_STEP, { op: 'band_math', op_version: 2, params: { expression: '(green - nir) / (green + nir)', name: 'NDWI' } }],
      output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['NDVI'] },
    });
    useProcessingStore.setState({ jobs: [entry({ order })] });
    await process();
    expect(infoChips()).toEqual(['NDVI']);
    click(button('＋ Band math'));
    const field = container.querySelector<HTMLTextAreaElement>('textarea[id$="-expression"]')!;
    typeInto(field, 'NDWI + 1');
    expect(container.querySelector('.pp-step .hint-text.error')?.textContent).toBe("'NDWI' is not a band name");
    expect([...container.querySelectorAll('[aria-label="Results of earlier steps"] .pp-chip')].map((c) => c.textContent)).toEqual(['NDVI']);
    // The name of the hidden result is used in the chain.
    store().renameResult(store().steps[2].key, 'ndwi');
    expect(store().steps[2].values.name).toBe('result');
    typeInto(field, 'NDVI + 1');
    expect(orderView(selectionState(useAppStore.getState()), store()).nameBlock).toBeNull();
  });

  it('"All" takes the bands of the job and the new results, and nothing hidden', async () => {
    const order = parent({
      steps: [NDVI_STEP, { op: 'band_math', op_version: 2, params: { expression: '(green - nir) / (green + nir)', name: 'NDWI' } }],
      output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['NDVI', 'red'] },
    });
    useProcessingStore.setState({ jobs: [entry({ order })] });
    await process();
    click(button('＋ Band math'));
    act(() => store().setOutput([]));
    click(button('All'));
    expect(orderView(selectionState(useAppStore.getState()), store()).output).toEqual(['NDVI', 'result', 'red']);
  });

  it('offers no mask where the job did not keep the layer the mask reads', async () => {
    await process();
    expect(button('＋ Mask')).toBeUndefined();
    expect(button('＋ Normalize')).toBeDefined();
    expect(button('＋ Band math')).toBeDefined();
  });

  it('offers a mask where the layer is part of the output of the job', async () => {
    useProcessingStore.setState({ jobs: [entry({ order: parent({ steps: [], output: { kind: 'raster', format: 'cog', dtype: 'uint16', bands: ['red', 'scl'] } }) })] });
    await process();
    expect(button('＋ Mask')).toBeDefined();
  });

  it('lets the person take a band of the locked steps out of the output', async () => {
    await process();
    click(button('NDVI', dataGroup()));
    expect(output()).toEqual(['red']);
  });

  it('sends one ordinary order with all the steps in order, and starts a new job', async () => {
    await process();
    click(button('＋ Band math'));
    typeInto(container.querySelector('li:not(.pp-locked) textarea[id$="-expression"]')!, 'NDVI * 2');
    click(button('Review'));
    await flush();
    click(button('Start job'));
    await flush();
    expect(execution()).toHaveLength(1);
    const order = sent();
    expect(order.recipe_version).toBe(2);
    expect(order.steps.map((s) => [s.op, s.params.name])).toEqual([['band_math', 'NDVI'], ['band_math', 'result']]);
    expect(order.steps[0]).toEqual(NDVI_STEP);
    expect(order.steps[1].params.expression).toBe('NDVI * 2');
    expect(order.inputs).toEqual([{ name: 'input', dataset: DATASET, groups: [['S2B_A']] }]);
    expect(order.aoi).toEqual(orderAoi(AOI));
    expect(order.output).toEqual({ kind: 'raster', format: 'cog', dtype: 'float32', bands: ['NDVI', 'result', 'red'] });
    // A job of its own beside the old one, in the same group, called after it and what was added.
    const jobs = store().jobs;
    expect(jobs.map((j) => j.jobID)).toEqual([NEW_JOB, JOB]);
    expect(jobs[0].title).toBe('NDVI of a field → Band math');
    expect(jobs[0].groupId).toBe(GROUP);
    expect(jobs[0].order?.steps).toHaveLength(2);
    expect(jobs[1].order).toEqual(parent());
    expect(jobs[1].title).toBe('NDVI of a field');
  });

  it('names the job after the operators added, each once', async () => {
    await process();
    click(button('＋ Band math'));
    click(button('＋ Band math'));
    click(button('＋ Normalize'));
    const [, first, second] = store().steps;
    for (const [step, name] of [[first, 'a'], [second, 'b']] as const) {
      store().updateStep(step.key, 'expression', 'red');
      store().renameResult(step.key, name);
    }
    const normalize = store().steps[3];
    store().updateStep(normalize.key, 'bands', 'NDVI');
    for (const [name, value] of [['in_min', '-1'], ['in_max', '1'], ['out_min', '0'], ['out_max', '1']] as const) store().updateStep(normalize.key, name, value);
    click(button('Review'));
    await flush();
    click(button('Start job'));
    await flush();
    expect(store().jobs[0].title).toBe('NDVI of a field → Band math, Normalize');
  });

  it('keeps the title of the job when nothing is added, and starts a job that only chooses other bands', async () => {
    await process();
    store().toggleOutput('green');
    click(button('Review'));
    await flush();
    click(button('Start job'));
    await flush();
    expect(sent().steps).toEqual([NDVI_STEP]);
    expect(sent().output).toMatchObject({ bands: ['NDVI', 'red', 'green'] });
    expect(store().jobs[0].title).toBe('NDVI of a field');
  });

  it('puts a job that goes on from a batch part into the group of its batch', async () => {
    useProcessingStore.setState({
      jobs: [entry({ groupId: null, batchId: 'b'.repeat(32) })],
      batches: [{ id: 'b'.repeat(32), title: 'Batch', titleDefault: 'Batch', createdAt: '2026-10-10T12:00:00Z', archived: false, groupId: GROUP, refused: [] }],
    });
    await process();
    click(button('Review'));
    await flush();
    click(button('Start job'));
    await flush();
    expect(store().jobs[0].groupId).toBe(GROUP);
    expect(store().jobs[0].batchId).toBeNull();
  });

  it('leaves a job in no group when the group is gone', async () => {
    await process();
    useProcessingStore.setState({ groups: [] });
    click(button('Review'));
    await flush();
    click(button('Start job'));
    await flush();
    expect(store().jobs[0].groupId).toBeNull();
  });

  it('keeps the scenes of the result whatever the list does, and its area whatever the map does', async () => {
    await process();
    act(() => useAppStore.setState({ selectedIds: ['S2B_B'], aoi: OTHER_AOI }));
    click(button('Review'));
    await flush();
    click(button('Start job'));
    await flush();
    expect(sent().inputs[0].groups).toEqual([['S2B_A']]);
    expect(sent().aoi).toEqual(orderAoi(AOI));
    // There is no "Run as".
    store().setRunAs('scene');
    expect(store().runAs).toBe('one');
  });

  it('takes the whole scene for an order that has no area', async () => {
    const whole = parent();
    delete whole.aoi;
    useProcessingStore.setState({ jobs: [entry({ order: whole })] });
    await process();
    expect(store().area).toBe('scene');
    expect(store().fixed?.aoi).toBeNull();
    expect(button('Whole scene')?.getAttribute('aria-pressed')).toBe('true');
    click(button('Review'));
    await flush();
    click(button('Start job'));
    await flush();
    expect(sent().aoi).toBeUndefined();
  });

  it('opens for an expired result, and runs it from the scenes all the same', async () => {
    useAppStore.setState({ layers: [resultLayer({ expired: true })] });
    useProcessingStore.setState({ jobs: [entry({ expired: true, phase: 'gone' })] });
    await process();
    expect(store().open).toBe(true);
    click(button('Review'));
    await flush();
    click(button('Start job'));
    await flush();
    expect(execution()).toHaveLength(1);
  });

  it('drops the steps of the result when the panel is opened from the selection', async () => {
    await process();
    act(() => store().openProcessing());
    expect(store().fixed).toBeNull();
    expect(store().steps).toEqual([]);
    expect(store().output).toEqual([]);
  });

  it('drops them with a new dataset as it does any draft', async () => {
    await process();
    act(() => useAppStore.setState({ datasetId: 'other' }));
    expect(store().fixed).toBeNull();
    expect(store().steps).toEqual([]);
  });

  it('is not entered by a step of an operator the dataset no longer lists', async () => {
    useProcessingStore.setState({ jobs: [entry({ order: parent({ steps: [{ op: 'decompose', op_version: 1, params: {} }] }) })] });
    await process();
    expect(store().open).toBe(false);
    expect(useAppStore.getState().error).toMatch(/decompose/u);
  });
});

describe('a result of several bands, and RGB', () => {
  const colour = (): Order =>
    parent({
      steps: [{ op: 'normalize', op_version: 2, params: { bands: ['red', 'green', 'blue'], in_min: 0, in_max: 10000, out_min: 0, out_max: 1, clip: true } }],
      output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['red', 'green', 'blue'] },
    });
  const show = () => container.querySelector<HTMLSelectElement>('section[aria-label="Preview on the map"] .pp-show select');

  it('opens with the bands of the job as the output and offers RGB in "Show"', async () => {
    useProcessingStore.setState({ jobs: [entry({ order: colour() })] });
    await process();
    expect(output()).toEqual(['red', 'green', 'blue']);
    expect([...(show()?.options ?? [])].map((o) => o.value)).toEqual(['@rgb', 'red', 'green', 'blue']);
  });

  it('shows the result added last, with RGB still on offer, and puts the new band beside the three', async () => {
    useProcessingStore.setState({ jobs: [entry({ order: colour() })] });
    await process();
    click(button('＋ Band math'));
    typeInto(container.querySelector<HTMLTextAreaElement>('li:not(.pp-locked) textarea[id$="-expression"]')!, '(nir - red) / (nir + red)');
    expect(output()).toEqual(['red', 'green', 'blue', 'result']);
    expect(orderView(selectionState(useAppStore.getState()), store()).output).toEqual(['result', 'red', 'green', 'blue']);
    const options = [...(show()?.options ?? [])].map((o) => o.value);
    expect(options).toEqual(['@rgb', 'result', 'red', 'green', 'blue']);
    expect(show()?.value).toBe('result');
  });

  it('shows RGB first where the job has the three bands and adds no result', async () => {
    useProcessingStore.setState({ jobs: [entry({ order: colour() })] });
    await process();
    expect(show()?.value).toBe('@rgb');
  });

  it('offers no RGB when the job left a colour band out of its output', async () => {
    useProcessingStore.setState({
      jobs: [entry({ order: parent({ steps: colour().steps, output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['red', 'green'] } }) })],
    });
    await process();
    expect([...(show()?.options ?? [])].map((o) => o.value)).toEqual(['red', 'green']);
  });
});
