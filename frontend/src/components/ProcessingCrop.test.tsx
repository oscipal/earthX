// @vitest-environment jsdom
//
// A layer or a view merged and cut to its AOI is one object (NM4-06): the panel has no "Run as", the area is fixed to the AOI
// of the crop, and one job is sent. A crop of several passes is turned away with the reason. An entry from the selection or
// from another layer is as it was. No backend: `fetch` answers the process description, the estimate and the placing of a job.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import { bboxToPolygon } from '../geoUtils';
import type { MapLayer } from '../layers';
import type { Order } from '../processing';
import { orderAoi } from '../processingOrder';
import { orderView, resetJobs, selectionState, setTrackerOptions, useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection, StacItem } from '../types';
import LayerManager from './LayerManager';
import ProcessingPanel from './ProcessingPanel';
import ViewBar from './ViewBar';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const DATASET = 'sentinel-2-c1-l2a';
const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const AOI = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);
const OTHER_AOI = bboxToPolygon([10.1, 50.1, 10.2, 50.2]);

function scene(id: string, day = '2026-07-01'): StacItem {
  const bbox: [number, number, number, number] = [10, 50, 11, 51];
  const asset = () => ({ href: 'https://example.org/b.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] });
  return { id, collection: DATASET, bbox, geometry: bboxToPolygon(bbox), properties: { datetime: `${day}T10:00:00Z` }, assets: { red: asset(), nir: asset() } };
}

const dataset: DatasetOption = {
  id: DATASET,
  title: 'Sentinel-2 L2A',
  viewable: true,
  groupBy: ['datetime'],
  zoom: { min: 8, max: 14 },
  browse: 'quicklook',
  quicklookNodataMax: null,
  resultsGroupBy: ['datetime'],
  hasTimeAxis: true,
  collection: { id: DATASET, 'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' }, 'earthx:capabilities': { interpolation: true } } as unknown as Collection,
};

// A layer pinned from a view: the scenes it was made of, and whether it was cut to its AOI.
function layer(ids: string[], over: Partial<MapLayer['restore']> = {}): MapLayer {
  return {
    id: 'L1',
    name: 'Crop',
    visible: true,
    opacity: 1,
    overlays: [],
    restore: { focusMode: true, downloaded: {}, appliedRender: {}, activeGroupIndex: 0, selectedIds: ids, itemIds: ids, groupItemIds: [ids], aoi: AOI, cropToAoi: true, datasetId: DATASET, ...over },
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
// The jobs the platform has taken in, to give each its own id.
let placed = 0;

// The scenes of the search: A and B of one day (one pass), C of another.
function search(layers: MapLayer[] = []) {
  const one = [scene('S2B_A'), scene('S2B_B')];
  const two = [scene('S2B_C', '2026-07-02')];
  const items = [...one, ...two];
  useAppStore.setState({
    datasets: [dataset],
    datasetId: DATASET,
    items,
    groups: [
      { key: ['2026-07-01'], label: '2026-07-01', items: one },
      { key: ['2026-07-02'], label: '2026-07-02', items: two },
    ],
    activeGroupIndex: 0,
    selectedIds: ['S2B_A'],
    aoi: OTHER_AOI,
    aoiPoint: null,
    layers,
    focusMode: false,
    cropToAoi: false,
    viewAoi: null,
    downloaded: {},
    error: null,
    dock: 'layers',
  });
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  localStorage.clear();
  placed = 0;
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === `/processing/processes/recipe?dataset=${DATASET}`) return json(s2);
    if (init?.method === 'POST' && url.endsWith('/estimate')) return json(ESTIMATE);
    if (init?.method === 'POST' && url.endsWith('/execution')) {
      return json({ processID: 'recipe', type: 'process', jobID: ['ZyXwVuTsRqPoNmLkJiHg_-', 'AaBbCcDdEeFfGgHhIiJj_-'][placed++ % 2], status: 'accepted', message: '', progress: 0, created: '2026-10-31T10:00:00Z', expires: new Date(Date.now() + 7 * 86_400_000).toISOString(), recipeID: 'r', links: [] }, 201);
    }
    return json({ title: 'Not found' }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  useProcessingStore.getState().resetDraft();
  useProcessingStore.setState({ open: false, descriptions: {}, crs: {}, jobs: [] });
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
    for (let i = 0; i < 10; i++) await Promise.resolve();
  });
}

const store = () => useProcessingStore.getState();
const app = () => useAppStore.getState();
const button = (label: string | RegExp, within: Element = container) =>
  [...within.querySelectorAll('button')].find((b) => (typeof label === 'string' ? b.textContent?.trim() === label : label.test(b.textContent ?? '')));
const click = (element: HTMLElement | undefined) => {
  if (!element) throw new Error(`nothing to click in ${container.textContent}`);
  act(() => element.dispatchEvent(new MouseEvent('click', { bubbles: true })));
};
function typeInto(input: HTMLTextAreaElement, value: string) {
  act(() => {
    Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')!.set!.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}
const selection = () => container.querySelector('section[aria-label="Selection"]')!;
const execution = () => fetchMock.mock.calls.filter(([u, init]) => String(u).endsWith('/execution') && init?.method === 'POST');
const sent = () => JSON.parse(execution()[0][1].body).inputs.recipe as Order;
const runAs = () => selection().querySelector('[aria-label="Run as"]');

async function render() {
  act(() =>
    root.render(
      <>
        <LayerManager />
        <ProcessingPanel />
      </>,
    ),
  );
}
const gear = () => container.querySelector<HTMLButtonElement>('.layer-row [data-col="process"]')!;

async function ndviAndStart() {
  click(button('＋ Band math'));
  typeInto(container.querySelector('textarea[id$="-expression"]')!, '(nir - red) / (nir + red)');
  click(button('Review', container));
  await flush();
  click(button(/^Start /u));
  await flush();
}

describe('the gear of a layer merged and cut to its AOI', () => {
  it('opens a panel of one object: no "Run as", the area fixed to the AOI of the crop with a lock', async () => {
    search([layer(['S2B_A', 'S2B_B'])]);
    // The setting "Run as" of an earlier draft does not carry over.
    useProcessingStore.setState({ runAs: 'scene' });
    await render();
    click(gear());
    await flush();
    expect(store().open).toBe(true);
    expect(store().fixed).toEqual({ itemIds: ['S2B_A', 'S2B_B'], aoi: AOI, result: null });
    expect(store().area).toBe('aoi');
    expect(runAs()).toBeNull();
    expect(button('Whole scene', selection())).toBeUndefined();
    expect(button('AOI only', selection())).toBeUndefined();
    expect(selection().querySelector('.pp-fixed')?.textContent).toContain('AOI only');
    expect(selection().querySelector('.pp-fixed')?.getAttribute('title')).toBe('Fixed by the crop.');
    expect(selection().textContent).not.toContain('From result');
    expect(app().error).toBeNull();
  });

  it('sends one order, the merged scenes of the crop on the AOI of the crop', async () => {
    search([layer(['S2B_A', 'S2B_B'])]);
    useProcessingStore.setState({ runAs: 'scene' });
    await render();
    click(gear());
    await flush();
    const view = orderView(selectionState(app()), store());
    expect(view.runAs).toBe('one');
    expect(view.parts).toHaveLength(1);
    await ndviAndStart();
    expect(execution()).toHaveLength(1);
    expect(sent().inputs[0].groups).toEqual([['S2B_A', 'S2B_B']]);
    expect(sent().aoi).toEqual(orderAoi(AOI));
    expect(store().jobs).toHaveLength(1);
  });

  it('keeps the area of the crop when the map gets another one, and the scenes when the list ticks others', async () => {
    search([layer(['S2B_A', 'S2B_B'])]);
    await render();
    click(gear());
    await flush();
    act(() => useAppStore.setState({ aoi: OTHER_AOI, selectedIds: ['S2B_C'] }));
    await ndviAndStart();
    expect(sent().inputs[0].groups).toEqual([['S2B_A', 'S2B_B']]);
    expect(sent().aoi).toEqual(orderAoi(AOI));
    store().setArea('scene');
    store().setRunAs('scene');
    expect(store().area).toBe('aoi');
  });

  it('takes the scenes of the layer when the results on screen do not hold them', async () => {
    search([layer(['S2B_A', 'S2B_B'])]);
    useAppStore.setState({ items: [scene('S2B_A')], groups: [{ key: ['2026-07-01'], label: '2026-07-01', items: [scene('S2B_A')] }] });
    const item = scene('S2B_B');
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === `/processing/processes/recipe?dataset=${DATASET}`) return json(s2);
      if (String(url).includes('/S2B_B')) return json(item);
      if (init?.method === 'POST' && url.endsWith('/estimate')) return json(ESTIMATE);
      return json({ title: 'Not found' }, 404);
    });
    await render();
    click(gear());
    await flush();
    expect(store().open).toBe(true);
    expect(orderView(selectionState(app()), store()).candidates.map((i) => i.id).sort()).toEqual(['S2B_A', 'S2B_B']);
  });

  describe('a crop of several passes', () => {
    const passesGroup = () => selection().querySelector('[aria-label="Passes"]');
    const labels = () => [...(passesGroup()?.querySelectorAll('button') ?? [])].map((b) => b.textContent);
    const pickedPass = () => (container.querySelector('.processing-panel select') as HTMLSelectElement | null)?.selectedOptions[0]?.textContent;

    async function open(selected: string[]) {
      search([layer(['S2B_A', 'S2B_B', 'S2B_C'], { selectedIds: selected })]);
      await render();
      click(gear());
      await flush();
    }

    it('is not turned away: a small choice of the pass takes the place of "Run as"', async () => {
      await open(['S2B_A']);
      expect(store().open).toBe(true);
      expect(app().error).toBeNull();
      expect(runAs()).toBeNull();
      expect(labels()).toEqual(['This pass only', 'All passes (2 jobs)']);
      expect(passesGroup()?.querySelector('[aria-pressed="true"]')?.textContent).toBe('This pass only');
      expect(selection().textContent).not.toContain('Run as');
      expect(selection().querySelector('.pp-fixed')?.textContent).toContain('AOI only');
    });

    it('has the pass in view as the one a job is for', async () => {
      await open(['S2B_C']);
      expect(pickedPass()).toContain('2026-07-02');
      expect(orderView(selectionState(app()), store()).pass?.items.map((i) => i.id)).toEqual(['S2B_C']);
      await open(['S2B_B']);
      expect(orderView(selectionState(app()), store()).pass?.items.map((i) => i.id).sort()).toEqual(['S2B_A', 'S2B_B']);
    });

    it('sends one job for the pass in view, on the AOI of the crop, with "This pass only"', async () => {
      await open(['S2B_C']);
      await ndviAndStart();
      expect(execution()).toHaveLength(1);
      expect(sent().inputs[0].groups).toEqual([['S2B_C']]);
      expect(sent().aoi).toEqual(orderAoi(AOI));
      expect(store().jobs).toHaveLength(1);
    });

    it('sends a job for every pass, the same steps on the AOI of the crop, with "All passes"', async () => {
      await open(['S2B_C']);
      click(button('All passes (2 jobs)'));
      expect(store().runAs).toBe('pass');
      await ndviAndStart();
      // The jobs start one after the other.
      for (let i = 0; i < 100 && execution().length < 2; i++) {
        await act(async () => {
          await new Promise((resolve) => setTimeout(resolve, 10));
        });
      }
      expect(execution()).toHaveLength(2);
      const orders = execution().map(([, init]) => JSON.parse(init.body).inputs.recipe as Order);
      expect(orders.map((o) => o.inputs[0].groups).sort()).toEqual([[['S2B_A', 'S2B_B']], [['S2B_C']]]);
      for (const order of orders) {
        expect(order.aoi).toEqual(orderAoi(AOI));
        expect(order.steps).toEqual(orders[0].steps);
        expect(order.output).toEqual(orders[0].output);
      }
      expect(store().jobs).toHaveLength(2);
      expect(store().batches).toHaveLength(1);
    });

    it('offers no job per scene, and the choice does not come back as "Run as"', async () => {
      await open(['S2B_A']);
      store().setRunAs('scene');
      expect(orderView(selectionState(app()), store()).runAs).toBe('one');
      expect(labels().join()).not.toMatch(/scene/u);
    });

    it('says nothing of passes when only one pass meets the AOI of the crop', async () => {
      // The scene of the other day lies elsewhere: the AOI does not meet it, so the crop holds one pass.
      const far = scene('S2B_C', '2026-07-02');
      far.bbox = [20, 60, 21, 61];
      far.geometry = bboxToPolygon([20, 60, 21, 61]);
      search([layer(['S2B_A', 'S2B_C'])]);
      useAppStore.setState({
        items: [scene('S2B_A'), far],
        groups: [
          { key: ['2026-07-01'], label: '2026-07-01', items: [scene('S2B_A')] },
          { key: ['2026-07-02'], label: '2026-07-02', items: [far] },
        ],
      });
      await render();
      click(gear());
      await flush();
      expect(store().open).toBe(true);
      expect(passesGroup()).toBeNull();
      expect(app().error).toBeNull();
    });
  });
});

describe('the other entries are as they were', () => {
  it('a layer that is not cut to its AOI starts on "Whole scene", with "Run as" for scenes of several passes', async () => {
    search([layer(['S2B_A', 'S2B_B'], { cropToAoi: false, aoi: null })]);
    await render();
    click(gear());
    await flush();
    expect(store().open).toBe(true);
    expect(store().fixed).toBeNull();
    expect(store().area).toBe('scene');
    expect(button('Whole scene', selection())).toBeDefined();
    expect(runAs()).not.toBeNull();
  });

  it('a layer whose scenes make several passes, not cut to its AOI, is not turned away', async () => {
    search([layer(['S2B_A', 'S2B_C'], { cropToAoi: false })]);
    await render();
    click(gear());
    await flush();
    expect(store().open).toBe(true);
    expect(app().error).toBeNull();
  });

  it('the selection opens the panel with the choice of the area and "Run as"', async () => {
    search();
    useAppStore.setState({ selectedIds: ['S2B_A', 'S2B_B'] });
    act(() =>
      root.render(
        <>
          <ViewBar />
          <ProcessingPanel />
        </>,
      ),
    );
    click(button(/Process/u));
    await flush();
    expect(store().open).toBe(true);
    expect(store().fixed).toBeNull();
    expect(button('Whole scene', selection())).toBeDefined();
    expect(button('AOI only', selection())).toBeDefined();
    expect(runAs()).not.toBeNull();
  });

  it('a new opening from the selection lets go of what a crop had fixed', async () => {
    search([layer(['S2B_A', 'S2B_B'])]);
    await render();
    click(gear());
    await flush();
    expect(store().fixed).not.toBeNull();
    act(() => store().openProcessing());
    expect(store().fixed).toBeNull();
    expect(store().area).toBe('scene');
  });
});

describe('the cropped view', () => {
  // The images of the view: a pass each, by the dataset and the group; the one the head shows is the key of `shownImage`.
  const viewOf = (ids: string[], shown: string | null = null) =>
    useAppStore.setState({
      focusMode: true,
      cropToAoi: true,
      viewAoi: AOI,
      downloaded: Object.fromEntries(ids.map((id) => [id, { datasetId: DATASET }])) as never,
      shownImage: shown,
    });

  it('is one object as the layer is, and takes the area it was opened with', async () => {
    search();
    viewOf(['S2B_A', 'S2B_B']);
    await render();
    await store().processFocusView();
    await flush();
    expect(store().fixed).toEqual({ itemIds: ['S2B_A', 'S2B_B'], aoi: AOI, result: null });
    expect(runAs()).toBeNull();
    expect(selection().querySelector('.pp-fixed')?.textContent).toContain('AOI only');
  });

  it('offers the passes of its dataset, with the pass the head shows as the one a job is for', async () => {
    search();
    viewOf(['S2B_A', 'S2B_B', 'S2B_C'], `${DATASET}\u00002026-07-02`);
    await render();
    await store().processFocusView();
    await flush();
    expect(store().open).toBe(true);
    expect([...(selection().querySelector('[aria-label="Passes"]')?.querySelectorAll('button') ?? [])].map((b) => b.textContent)).toEqual([
      'This pass only',
      'All passes (2 jobs)',
    ]);
    expect(orderView(selectionState(app()), store()).pass?.items.map((i) => i.id)).toEqual(['S2B_C']);
    expect(app().error).toBeNull();
  });

  it('a view of the whole scene is as it was', async () => {
    search();
    useAppStore.setState({ focusMode: true, cropToAoi: false, viewAoi: null, downloaded: { S2B_A: { datasetId: DATASET }, S2B_C: { datasetId: DATASET } } as never });
    await store().processFocusView();
    expect(store().open).toBe(true);
    expect(store().fixed).toBeNull();
    expect(store().area).toBe('scene');
  });
});
