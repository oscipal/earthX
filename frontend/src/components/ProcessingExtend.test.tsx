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
const lockedSteps = () => [...container.querySelectorAll('.pp-locked')];
const output = () => store().output;

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

  it('is locked without the order, and the reason points to the recipe.json', async () => {
    useProcessingStore.setState({ jobs: [entry({ order: null })] });
    act(() => root.render(<LayerManager />));
    expect(gear().disabled).toBe(true);
    expect(gear().title).toBe(NO_COPY_TEXT);
    click(gear());
    await flush();
    expect(store().open).toBe(false);
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
    expect(output()).toEqual(['NDVI', 'red']);
    expect(store().area).toBe('aoi');
    // The scenes and the AOI of the job, not those the map and the list hold now.
    expect(useAppStore.getState().selectedIds).toEqual(['S2B_A']);
    expect(container.querySelector('section[aria-label="Selection"]')?.textContent).toContain('S2B_A');
  });

  it('shows the steps of the result locked, and no way to change, move or remove them', async () => {
    await process();
    expect(lockedSteps()).toHaveLength(1);
    const step = lockedSteps()[0];
    expect(step.getAttribute('aria-label')).toBe('Step 1: Band math (locked)');
    expect(step.textContent).toContain('NDVI');
    expect(step.querySelector('textarea, input')).toBeNull();
    expect(button(/Remove|Up|Down/u, step)).toBeUndefined();
    // Folded to its title; what the step was given is behind it.
    expect(step.querySelector('details')?.hasAttribute('open')).toBe(false);
    expect(step.textContent).toContain('(nir - red) / (nir + red)');
  });

  it('has nothing to choose about the scenes and the area, and does not load a recipe', async () => {
    await process();
    const selection = container.querySelector('section[aria-label="Selection"]')!;
    expect(button('AOI only', selection)).toBeUndefined();
    expect(button('Whole scene', selection)).toBeUndefined();
    expect(selection.querySelector('[aria-label="Run as"]')).toBeNull();
    expect(selection.textContent).toContain('AOI only');
    expect(selection.querySelector('.pp-fixed')?.getAttribute('title')).toBe('Fixed by the result.');
    expect(selection.textContent).not.toContain('Load recipe');
    expect(selection.textContent).toContain('From result: NDVI of a field');
  });

  it('says in a tooltip that the chain is run again, and that the last bit can differ', async () => {
    await process();
    const tip = container.querySelector('.pp-area .tip')?.getAttribute('data-tip') ?? '';
    expect(tip).toMatch(/run again from the scenes/u);
    expect(tip).toMatch(/last bit/u);
    expect(tip).toMatch(/float64/u);
    expect(tip).not.toMatch(/Expired/u);
  });

  it('says in the tooltip that the result has expired', async () => {
    useAppStore.setState({ layers: [resultLayer({ expired: true })] });
    await process();
    expect(container.querySelector('.pp-area .tip')?.getAttribute('data-tip')).toContain(EXPIRED_PROCESS_TEXT);
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

  it('does not take a recipe over the locked steps', async () => {
    await process();
    const loaded = await store().loadRecipe(JSON.stringify(parent()));
    expect(loaded).toEqual({ ok: false, reason: 'The steps of a result stay as they are.' });
    expect(store().steps).toHaveLength(1);
  });

  it('puts a new step behind the locked ones, and nothing in front of them', async () => {
    await process();
    click(button('＋ Band math'));
    click(button('＋ Normalize'));
    const names = store().steps.map((s) => s.op);
    expect(names).toEqual(['band_math', 'band_math', 'normalize']);
    const [, added, normalize] = store().steps;
    store().moveStep(added.key, -1);
    expect(store().steps.map((s) => s.key)).toEqual([store().steps[0].key, added.key, normalize.key]);
    store().moveStep(added.key, 1);
    expect(store().steps.map((s) => s.op)).toEqual(['band_math', 'normalize', 'band_math']);
    // The first new step has nothing to move up to.
    const forms = [...container.querySelectorAll('.pp-step:not(.pp-locked)')];
    expect((button(/Up/u, forms[0]) as HTMLButtonElement).disabled).toBe(true);
    expect(container.querySelector('.pp-step-sep')?.textContent).toBe('your steps');
  });

  it('keeps the bands of the locked steps in the stock: a new step reads them, and so does the output', async () => {
    await process();
    click(button('＋ Band math'));
    const field = container.querySelector<HTMLTextAreaElement>('li:not(.pp-locked) textarea[id$="-expression"]')!;
    typeInto(field, 'NDVI * 2');
    // The result of the locked step is a chip of the new one, and the expression naming it is no problem.
    const chips = container.querySelectorAll('li:not(.pp-locked) [aria-label="Results of earlier steps"] .pp-chip');
    expect([...chips].map((c) => c.textContent)).toEqual(['NDVI']);
    expect(container.querySelector('li:not(.pp-locked) .hint-text.error')).toBeNull();
    const view = orderView(selectionState(useAppStore.getState()), store());
    expect(view.results.map((r) => r.name)).toEqual(['NDVI', 'result']);
    expect(view.nameBlock).toBeNull();
    // The new result comes into the output ticked, the output of the job stays; the file holds the results first.
    expect(output()).toEqual(['NDVI', 'red', 'result']);
    expect(view.output).toEqual(['NDVI', 'result', 'red']);
    expect(view.built?.order?.output.kind === 'raster' && view.built.order.output.bands).toEqual(['NDVI', 'result', 'red']);
  });

  it('lets the person take a band of the locked steps out of the output', async () => {
    await process();
    click(button('NDVI', container.querySelector('section[aria-label="Output"] [aria-label="New bands"]')!));
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

  it('keeps the scenes and the area of the result whatever the map and the list do', async () => {
    await process();
    act(() => useAppStore.setState({ selectedIds: ['S2B_B'], aoi: OTHER_AOI }));
    click(button('Review'));
    await flush();
    click(button('Start job'));
    await flush();
    expect(sent().inputs[0].groups).toEqual([['S2B_A']]);
    expect(sent().aoi).toEqual(orderAoi(AOI));
    // The area stays too when the person asks for the other one.
    store().setArea('scene');
    store().setRunAs('scene');
    expect(store().area).toBe('aoi');
    expect(store().runAs).toBe('one');
  });

  it('takes the whole scene for an order that has no area', async () => {
    const whole = parent();
    delete whole.aoi;
    useProcessingStore.setState({ jobs: [entry({ order: whole })] });
    await process();
    expect(store().area).toBe('scene');
    expect(store().fixed?.aoi).toBeNull();
    expect(container.querySelector('.pp-fixed')?.textContent).toContain('Whole scene');
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
    expect(store().fixed?.result?.expired).toBe(true);
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
