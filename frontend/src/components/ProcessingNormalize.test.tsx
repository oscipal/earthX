// @vitest-environment jsdom
//
// The "Normalize" step of the processing panel (NM4-11b): the methods, the measure over the AOI before the order is whole,
// what "Review" and "Start job" say while it waits, and the locks. No backend: `fetch` answers the process description, the
// statistics over the AOI and the estimate.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import { bboxToPolygon } from '../geoUtils';
import { orderView, selectionState, useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection, StacItem } from '../types';
import ProcessingPanel from './ProcessingPanel';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const AOI = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);
const OTHER_AOI = bboxToPolygon([10.4, 50.4, 10.5, 50.5]);
const DESCRIPTION = '/processing/processes/recipe?dataset=sentinel-2-c1-l2a';
const STATISTICS_ROUTE = '/collections/sentinel-2-c1-l2a/statistics';
const band = { data_type: 'uint16', nodata: 0 };

function scene(id: string): StacItem {
  const bbox: [number, number, number, number] = [10, 50, 11, 51];
  return {
    id,
    collection: 'sentinel-2-c1-l2a',
    bbox,
    geometry: bboxToPolygon(bbox),
    properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 },
    assets: {
      red: { href: 'https://example.org/red.tif', type: COG, 'raster:bands': [band] },
      nir: { href: 'https://example.org/nir.tif', type: COG, 'raster:bands': [band] },
    },
  };
}

const dataset: DatasetOption = {
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
  } as unknown as Collection,
};

function select(items: StacItem[], aoi: GeoJSON.Geometry | null = AOI) {
  useAppStore.setState({
    datasets: [dataset],
    datasetId: dataset.id,
    items,
    groups: [{ key: ['2026-07-01'], label: '2026-07-01', items }],
    activeGroupIndex: 0,
    selectedIds: items.map((i) => i.id),
    aoi,
    aoiPoint: null,
    layers: [],
    mapZoom: 1.6,
    viewportBbox: null,
  });
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': status === 200 ? 'application/json' : 'application/problem+json' } });
}

const ESTIMATE = {
  estimate: { size: 4_000_000, duration: 'PT3.4S', outputPixels: 1_000_000, inputPixels: 2_000_000, inputBytes: 4_000_000, assets: 2, units: 1 },
  skippedItems: [],
};

// What the route measures of a band (`processing/statistics.py`).
const STATISTICS = {
  minimum: 100,
  maximum: 9000,
  mean: 2000,
  stddev: 500,
  count: 1000,
  valid_percent: 100,
  percentile_1: 150,
  percentile_2: 200,
  percentile_5: 300,
  percentile_25: 1500,
  percentile_50: 1900,
  percentile_75: 2400,
  percentile_95: 5000,
  percentile_98: 6000,
  percentile_99: 7000,
};

let container: HTMLDivElement;
let root: Root;
let fetchMock: ReturnType<typeof vi.fn>;
// What the statistics route answers to the next question, by default every band of the question.
let statistics: (body: { output: { bands: string[] } }) => Response;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  localStorage.clear();
  statistics = (body) =>
    json({ bands: body.output.bands.map((name) => ({ name, unit: null, statistics: STATISTICS })), exact: true, factor: 1 });
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === DESCRIPTION) return json(s2);
    if (url === STATISTICS_ROUTE && init?.method === 'POST') return statistics(JSON.parse(String(init.body)));
    if (url === '/processing/processes/recipe/estimate' && init?.method === 'POST') return json(ESTIMATE);
    if (url.includes('/tilejson.json')) return json({ tilejson: '3.0.0' });
    return json({}, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  useProcessingStore.getState().resetDraft();
  useProcessingStore.setState({ open: false, descriptions: {}, jobs: [], preview: null, previewNote: null });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

async function flush() {
  await act(async () => {
    for (let i = 0; i < 30; i++) await Promise.resolve();
  });
}

async function openPanel() {
  act(() => root.render(<ProcessingPanel />));
  act(() => useProcessingStore.getState().openProcessing());
  await flush();
}

function button(label: string | RegExp): HTMLButtonElement {
  const found = [...container.querySelectorAll('button')].find((b) =>
    typeof label === 'string' ? b.textContent?.trim() === label : label.test(b.textContent ?? ''),
  );
  if (!found) throw new Error(`no button ${String(label)} in ${container.textContent}`);
  return found as HTMLButtonElement;
}

function click(element: HTMLElement) {
  act(() => element.dispatchEvent(new MouseEvent('click', { bubbles: true })));
}

function typeInto(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!;
  act(() => {
    setter.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

function choose(select: HTMLSelectElement, value: string) {
  act(() => {
    select.value = value;
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
}

const store = () => useProcessingStore.getState();
const step = (index = 0) => container.querySelectorAll('li.pp-step')[index];
const methodSelect = (index = 0) => step(index).querySelector<HTMLSelectElement>('select[id$="-method"]')!;
const rangeSelect = () => step().querySelector<HTMLSelectElement>('select[id$="-range"]')!;
const box = (label: string) => step().querySelector<HTMLInputElement>(`input[aria-label="${label}"]`)!;
const legends = () => [...step().querySelectorAll('legend, .pp-label')].map((l) => l.firstChild?.textContent ?? '');
const tipsOf = (element: Element) => [...element.querySelectorAll('[data-tip]')].map((tip) => tip.getAttribute('data-tip')).join('\n');
const bandChip = (name: string) => [...step().querySelectorAll<HTMLButtonElement>('fieldset .pp-chip')].find((c) => c.textContent === name)!;
const questions = () =>
  fetchMock.mock.calls.filter(([u, init]) => u === STATISTICS_ROUTE && init?.method === 'POST').map(([, init]) => JSON.parse(String(init.body)));
const estimates = () => fetchMock.mock.calls.filter(([u]) => String(u).endsWith('/estimate'));

async function withNormalize(options: { aoi?: GeoJSON.Geometry | null; area?: 'aoi' | 'scene'; bands?: string } = {}) {
  const { aoi = AOI, area = 'aoi', bands = 'red' } = options;
  select([scene('S2B_A')], aoi);
  await openPanel();
  store().setArea(area);
  click(button('＋ Normalize'));
  const key = store().steps[0].key;
  store().updateStep(key, 'bands', bands);
  store().setOutput(bands.split(', '));
  await flush();
  return key;
}

// The target range, which the fixed range and the percentiles need before the order is whole.
const fillTarget = () => {
  typeInto(box('Target min'), '0');
  typeInto(box('Target max'), '1');
};

const setMethod = async (method: string) => {
  choose(methodSelect(), method);
  await flush();
};

describe('the step', () => {
  it('starts as the fixed range, with the four methods named for people and the formula behind the (i)', async () => {
    await withNormalize();
    expect(methodSelect().value).toBe('linear');
    expect([...methodSelect().options].map((o) => o.textContent)).toEqual(['Fixed range', 'Percentile stretch', 'Z-score', 'Robust (median, IQR)']);
    expect(legends()).toEqual(expect.arrayContaining(['Method', 'Band', 'From', 'To']));
    const tip = tipsOf(step());
    expect(tip).toContain('NDVI −1…1 → 0…1');
    expect(tip).toContain('(x − from) / (to − from) × (max − min) + min');
    expect(questions()).toHaveLength(0);
  });

  it('lays the fields out by the method: from and to, the range of percentiles, or only the bands', async () => {
    await withNormalize();
    expect(box('From min')).not.toBeNull();
    expect(step().querySelector('select[id$="-range"]')).toBeNull();
    await setMethod('percentile');
    expect(rangeSelect().value).toBe('2–98 %');
    expect([...rangeSelect().options].map((o) => o.textContent)).toEqual(['0–100 %', '1–99 %', '2–98 %', '5–95 %']);
    expect(box('From min')).toBeNull();
    expect(box('Target min')).not.toBeNull();
    expect(tipsOf(step())).toContain('(x − p_low) / (p_high − p_low)');
    for (const method of ['zscore', 'robust']) {
      await setMethod(method);
      expect(step().querySelectorAll('input[type="text"]')).toHaveLength(0);
      expect(step().querySelector('select[id$="-range"]')).toBeNull();
      expect(step().querySelector('input[type="checkbox"]')).toBeNull();
    }
    expect(tipsOf(step())).toContain('(x − median) / (p75 − p25)');
  });

  it('keeps the numbers of one method when the method changes and back', async () => {
    await withNormalize();
    typeInto(box('From min'), '-1');
    await setMethod('zscore');
    await setMethod('linear');
    expect(box('From min').value).toBe('-1');
  });

  it('asks for decimals with a point, and tells a comma at once', async () => {
    await withNormalize();
    typeInto(box('From min'), '0,2');
    expect(step().textContent).toContain('Use . for decimals.');
    typeInto(box('From min'), '0.2');
    expect(step().textContent).not.toContain('Use . for decimals.');
  });

  it('shows no text besides the labels: the explanations are tooltips', async () => {
    await withNormalize();
    expect(step().querySelectorAll('p:not(.hint-text)')).toHaveLength(0);
  });

  it('sends version 3 with the fields of the fixed range and nothing measured, without a question to the route', async () => {
    await withNormalize();
    for (const [label, value] of [['From min', '0'], ['From max', '10000'], ['Target min', '0'], ['Target max', '1']] as const) typeInto(box(label), value);
    click(button('Review'));
    await flush();
    const sent = JSON.parse(String(estimates().at(-1)![1].body)).inputs.recipe.steps;
    expect(sent).toEqual([
      { op: 'normalize', op_version: 3, params: { method: 'linear', bands: ['red'], in_min: 0, in_max: 10000, out_min: 0, out_max: 1, clip: false } },
    ]);
    expect(questions()).toHaveLength(0);
  });
});

describe('the measure', () => {
  it('asks the route once for the bands over the AOI as float64, and sends the numbers in the recipe', async () => {
    await withNormalize();
    await setMethod('percentile');
    expect(questions()).toHaveLength(1);
    expect(questions()[0]).toMatchObject({
      recipe_version: 2,
      aoi: AOI,
      steps: [],
      output: { kind: 'raster', format: 'cog', dtype: 'float64', bands: ['red'] },
    });
    expect(step().textContent).toContain('Measured over the AOI ✓');
    expect(tipsOf(step())).toContain('red: p_low 200, p_high 6000');
    fillTarget();
    click(button('Review'));
    await flush();
    const sent = JSON.parse(String(estimates().at(-1)![1].body)).inputs.recipe.steps;
    expect(sent).toEqual([
      {
        op: 'normalize',
        op_version: 3,
        params: {
          method: 'percentile',
          bands: ['red'],
          low: 2,
          high: 98,
          out_min: 0,
          out_max: 1,
          clip: false,
          measured: { factor: 1, bands: { red: { p_low: 200, p_high: 6000 } } },
        },
      },
    ]);
  });

  it.each([
    ['percentile', { p_low: 200, p_high: 6000 }],
    ['zscore', { mean: 2000, stddev: 500 }],
    ['robust', { p25: 1500, median: 1900, p75: 2400 }],
  ])('%s: the numbers of each band chosen come from the answer', async (method, numbers) => {
    await withNormalize({ bands: 'red, nir' });
    await setMethod(method);
    if (method === 'percentile') fillTarget();
    click(button('Review'));
    await flush();
    const params = JSON.parse(String(estimates().at(-1)![1].body)).inputs.recipe.steps[0].params;
    expect(params.measured).toEqual({ factor: 1, bands: { red: numbers, nir: numbers } });
    expect(Object.keys(params).sort()).toEqual(
      method === 'percentile'
        ? ['bands', 'clip', 'high', 'low', 'measured', 'method', 'out_max', 'out_min']
        : ['bands', 'measured', 'method'],
    );
  });

  it('takes the minimum and the maximum for 0–100 %', async () => {
    await withNormalize();
    await setMethod('percentile');
    choose(rangeSelect(), '0–100 %');
    fillTarget();
    click(button('Review'));
    await flush();
    const params = JSON.parse(String(estimates().at(-1)![1].body)).inputs.recipe.steps[0].params;
    expect(params).toMatchObject({ low: 0, high: 100, measured: { bands: { red: { p_low: 100, p_high: 9000 } } } });
    expect(questions()).toHaveLength(1);
  });

  it('holds "Review" and "Start job" with the reason as their tooltip while the route has not answered', async () => {
    let answer!: () => void;
    const gate = new Promise<void>((resolve) => (answer = resolve));
    const before = statistics;
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === STATISTICS_ROUTE) {
        await gate;
        return before(JSON.parse(String(init!.body)));
      }
      if (url === DESCRIPTION) return json(s2);
      return json({}, 404);
    });
    await withNormalize();
    await setMethod('zscore');
    expect(step().textContent).toContain('Measuring…');
    for (const label of ['Review', 'Start job']) {
      expect(button(label).disabled).toBe(true);
      expect(button(label).title).toBe('Normalize: measuring the bands…');
    }
    click(button('Review'));
    expect(estimates()).toHaveLength(0);
    answer();
    await flush();
    expect(step().textContent).not.toContain('Measuring…');
    expect(button('Review').disabled).toBe(false);
    expect(button('Review').title).not.toContain('measuring');
  });

  it('says that the measurement failed, with the reason of the route, and asks again on "Retry"', async () => {
    statistics = () => json({ detail: 'The area is too large to measure.' }, 422);
    await withNormalize();
    await setMethod('zscore');
    expect(step().textContent).toContain('Not measured.');
    expect(button('Review').disabled).toBe(true);
    expect(button('Review').title).toMatch(/^Normalize: the measurement failed: .*The area is too large to measure\./u);
    expect(button('Start job').title).toBe(button('Review').title);
    expect(questions()).toHaveLength(1);
    statistics = (body) => json({ bands: body.output.bands.map((name) => ({ name, unit: null, statistics: STATISTICS })), exact: true, factor: 1 });
    click(button('Retry'));
    await flush();
    expect(questions()).toHaveLength(2);
    expect(step().textContent).toContain('Measured over the AOI ✓');
    expect(button('Review').disabled).toBe(false);
  });

  it('names the bands that have no valid value over the AOI, and does not wait', async () => {
    statistics = (body) => json({ bands: body.output.bands.map((name) => ({ name, unit: null, statistics: { count: 0, valid_percent: 0 } })), exact: true, factor: 1 });
    await withNormalize();
    await setMethod('zscore');
    expect(step().textContent).toContain('No valid values over the AOI in red.');
    expect(button('Review').disabled).toBe(false);
    click(button('Review'));
    await flush();
    expect(estimates()).toHaveLength(0);
  });

  it('says a coarser read in the tooltip of the numbers and carries the factor into the recipe', async () => {
    statistics = (body) => json({ bands: body.output.bands.map((name) => ({ name, unit: null, statistics: STATISTICS })), exact: false, factor: 3 });
    await withNormalize();
    await setMethod('zscore');
    expect(tipsOf(step())).toContain('3 times coarser');
    click(button('Review'));
    await flush();
    expect(JSON.parse(String(estimates().at(-1)![1].body)).inputs.recipe.steps[0].params.measured.factor).toBe(3);
  });

  it('measures again when the AOI, the bands, the scene or a step before the step changes, and not otherwise', async () => {
    await withNormalize();
    await setMethod('zscore');
    expect(questions()).toHaveLength(1);
    // Nothing changes: nothing is asked.
    await flush();
    expect(questions()).toHaveLength(1);
    // Another method of the same data: the same question is not asked again.
    await setMethod('robust');
    expect(questions()).toHaveLength(1);
    await setMethod('percentile');
    choose(rangeSelect(), '5–95 %');
    expect(questions()).toHaveLength(1);
    // The AOI.
    act(() => useAppStore.setState({ aoi: OTHER_AOI }));
    await flush();
    expect(questions()).toHaveLength(2);
    expect(questions()[1].aoi).toEqual(OTHER_AOI);
    // The bands.
    click(bandChip('nir'));
    await flush();
    expect(questions()).toHaveLength(3);
    expect(questions()[2].output.bands).toEqual(['red', 'nir']);
    // A step before it.
    click(button('＋ Mask by value'));
    const key = store().steps[1].key;
    store().moveStep(key, -1);
    store().updateStep(key, 'band', 'red');
    store().updateStep(key, 'condition', 'lt');
    store().updateStep(key, 'values', '10');
    await flush();
    expect(questions().at(-1).steps.map((s: { op: string }) => s.op)).toEqual(['mask_values']);
  });

  it('measures a second step on the first one, after the first has its numbers', async () => {
    await withNormalize();
    await setMethod('zscore');
    click(button('＋ Normalize'));
    const second = store().steps[1].key;
    store().updateStep(second, 'bands', 'red');
    store().updateStep(second, 'method', 'robust');
    await flush();
    expect(questions()).toHaveLength(2);
    expect(questions()[1].steps.map((s: { op: string }) => s.op)).toEqual(['normalize']);
    expect(questions()[1].steps[0].params.measured.bands.red).toEqual({ mean: 2000, stddev: 500 });
    click(button('Review'));
    await flush();
    const sent = JSON.parse(String(estimates().at(-1)![1].body)).inputs.recipe.steps;
    expect(sent.map((s: { params: { method: string } }) => s.params.method)).toEqual(['zscore', 'robust']);
  });

  it('puts the AOI into no address: the questions are POSTs to the dataset, with the AOI in the body only', async () => {
    await withNormalize();
    await setMethod('zscore');
    click(button('Review'));
    await flush();
    const addresses = fetchMock.mock.calls.map(([u]) => String(u));
    const aoi = JSON.stringify(AOI.coordinates[0][0]);
    expect(addresses.filter((u) => u.includes(aoi) || u.includes('50.4'))).toEqual([]);
    expect(addresses).toContain(STATISTICS_ROUTE);
    expect(JSON.stringify(questions()[0])).toContain('50.4');
  });

  it('has the same question in the view as the one asked', async () => {
    const key = await withNormalize();
    await setMethod('zscore');
    const view = orderView(selectionState(useAppStore.getState()), store());
    expect(view.needs.map((need) => need.body)).toEqual(questions());
    expect(view.measureBlock).toBeNull();
    expect(store().steps[0].key).toBe(key);
  });
});

describe('the preview', () => {
  const afterDebounce = async () => {
    act(() => {
      vi.advanceTimersByTime(400);
    });
    await flush();
  };

  it('draws the step with the numbers measured, takes no part of it before, and puts the AOI into no tile address', async () => {
    await withNormalize();
    vi.useFakeTimers();
    try {
      await setMethod('zscore');
      await afterDebounce();
      const preview = store().preview;
      expect(preview?.title).toBe('Normalize');
      const url = new URL(preview!.scenes[0].url, 'http://localhost');
      expect(url.searchParams.getAll('op_version')).toEqual(['3']);
      expect(JSON.parse(url.searchParams.get('params')!)).toEqual({
        method: 'zscore',
        bands: ['red'],
        measured: { factor: 1, bands: { red: { mean: 2000, stddev: 500 } } },
      });
      expect(preview!.scenes[0].url).not.toContain('50.4');
      expect(preview!.scenes[0].url).not.toContain('10.4');
    } finally {
      vi.useRealTimers();
    }
  });

  it('shows nothing while the numbers are missing, and says why', async () => {
    statistics = () => json({ detail: 'The area is too large to measure.' }, 422);
    await withNormalize();
    vi.useFakeTimers();
    try {
      await setMethod('zscore');
      await afterDebounce();
      expect(store().preview).toBeNull();
      expect(container.textContent).toContain('Normalize has no measured numbers yet.');
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('several jobs (Run as)', () => {
  const sceneOf = (body: { inputs: { groups: string[][] }[] }) => body.inputs[0].groups[0][0];
  const mean = (id: string) => Number(id.slice(1)) * 1000;
  const bandsOf = (body: { output: { bands: string[] } }, id: string) =>
    body.output.bands.map((name) => ({ name, unit: null, statistics: { ...STATISTICS, mean: mean(id) } }));

  async function withScenes() {
    select([scene('S1'), scene('S2'), scene('S3')]);
    await openPanel();
    store().setArea('aoi');
    store().setRunAs('scene');
    click(button('＋ Normalize'));
    const key = store().steps[0].key;
    store().updateStep(key, 'bands', 'red');
    store().setOutput(['red']);
    await flush();
    await setMethod('zscore');
  }

  it('measures each job over its own scene, in the recipe of that job', async () => {
    statistics = (body) => json({ bands: bandsOf(body as never, sceneOf(body as never)), exact: true, factor: 1 });
    await withScenes();
    expect(questions().map(sceneOf).sort()).toEqual(['S1', 'S2', 'S3']);
    expect(button('Review').disabled).toBe(false);
    click(button('Review'));
    await flush();
    const sent = estimates().map(([, init]) => JSON.parse(String(init.body)).inputs.recipe);
    expect(sent.map((r) => [sceneOf(r), r.steps[0].params.measured.bands.red.mean]).sort()).toEqual([
      ['S1', 1000],
      ['S2', 2000],
      ['S3', 3000],
    ]);
  });

  it('holds all jobs while one is measured, and names the job whose measurement failed, with "Retry"', async () => {
    statistics = (body) =>
      sceneOf(body as never) === 'S2'
        ? json({ detail: 'The area is too large to measure.' }, 422)
        : json({ bands: bandsOf(body as never, sceneOf(body as never)), exact: true, factor: 1 });
    await withScenes();
    expect(questions()).toHaveLength(3);
    expect(button('Review').disabled).toBe(true);
    expect(button('Review').title).toMatch(/^S2: Normalize: the measurement failed: .*The area is too large to measure\./u);
    expect(button('Start 3 jobs').title).toBe(button('Review').title);
    expect(step().textContent).toContain('Not measured.');
    expect(tipsOf(step())).toContain('S2: The measurement failed');
    statistics = (body) => json({ bands: bandsOf(body as never, sceneOf(body as never)), exact: true, factor: 1 });
    click(button('Retry'));
    await flush();
    // Only the failed question is asked again.
    expect(questions()).toHaveLength(4);
    expect(button('Review').disabled).toBe(false);
  });

  it('asks a few at a time, as the estimates are', async () => {
    let running = 0;
    let most = 0;
    const waiters: Array<() => void> = [];
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === DESCRIPTION) return json(s2);
      if (url === STATISTICS_ROUTE) {
        const body = JSON.parse(String(init!.body));
        running += 1;
        most = Math.max(most, running);
        await new Promise<void>((resolve) => waiters.push(resolve));
        running -= 1;
        return json({ bands: bandsOf(body, sceneOf(body)), exact: true, factor: 1 });
      }
      return json({}, 404);
    });
    select(Array.from({ length: 6 }, (_, i) => scene(`S${i + 1}`)));
    await openPanel();
    store().setArea('aoi');
    store().setRunAs('scene');
    click(button('＋ Normalize'));
    store().updateStep(store().steps[0].key, 'bands', 'red');
    await setMethod('zscore');
    for (let i = 0; i < 12 && waiters.length < 6; i++) {
      waiters.splice(0).forEach((resolve) => resolve());
      await flush();
    }
    expect(most).toBeLessThanOrEqual(4);
    expect(most).toBeGreaterThan(1);
  });
});

describe('a recipe.json that is loaded', () => {
  const recipe = (step: Record<string, unknown>) =>
    JSON.stringify({
      recipe_version: 2,
      inputs: [{ name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['S2B_A']] }],
      steps: [step],
      output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['red'] },
    });
  const load = (text: string) => act(() => useProcessingStore.getState().loadRecipe(text));

  it('does not take the numbers it holds: the panel measures for the selection in front of it', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    const stale = { factor: 1, bands: { red: { mean: 1, stddev: 2 } } };
    const result = await load(recipe({ op: 'normalize', op_version: 3, params: { method: 'zscore', bands: ['red'], measured: stale } }));
    expect(result).toEqual({ ok: true, notes: [] });
    expect(store().steps[0]).toMatchObject({ op: 'normalize', opVersion: 3, values: { method: 'zscore', bands: 'red' } });
    expect(JSON.stringify(store().steps)).not.toContain('stddev');
    // The file leaves the area alone: whole scene, so the method waits for an AOI, and nothing is asked.
    expect(questions()).toHaveLength(0);
    store().setArea('aoi');
    await flush();
    expect(questions()).toHaveLength(1);
    click(button('Review'));
    await flush();
    const params = JSON.parse(String(estimates().at(-1)![1].body)).inputs.recipe.steps[0].params;
    expect(params.measured).toEqual({ factor: 1, bands: { red: { mean: 2000, stddev: 500 } } });
  });

  it('takes a file with version 2 as the fixed range with the same numbers, and says so', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    const result = await load(
      recipe({ op: 'normalize', op_version: 2, params: { bands: ['red'], in_min: 0, in_max: 10000, out_min: 0, out_max: 1, clip: true } }),
    );
    expect(result).toEqual({ ok: true, notes: ['Step 1 (normalize): version 2 is taken as version 3.'] });
    expect(store().steps[0]).toMatchObject({ opVersion: 3, values: { method: 'linear', in_min: '0', in_max: '10000', out_min: '0', out_max: '1', clip: true } });
    expect(methodSelect().value).toBe('linear');
    expect(box('From max').value).toBe('10000');
    store().setArea('aoi');
    click(button('Review'));
    await flush();
    expect(JSON.parse(String(estimates().at(-1)![1].body)).inputs.recipe.steps[0]).toEqual({
      op: 'normalize',
      op_version: 3,
      params: { method: 'linear', bands: ['red'], in_min: 0, in_max: 10000, out_min: 0, out_max: 1, clip: true },
    });
    expect(questions()).toHaveLength(0);
  });

  it('refuses a method the panel does not know, with the step named', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    const result = await load(recipe({ op: 'normalize', op_version: 3, params: { method: 'median', bands: ['red'] } }));
    expect(result).toMatchObject({ ok: false });
    expect(JSON.stringify(result)).toContain('Step 1 (normalize)');
  });
});

describe('the locks', () => {
  it('has no method that measures without an AOI: the options are off, with the reason, and a step that holds one says so', async () => {
    await withNormalize({ area: 'scene', aoi: null });
    const options = [...methodSelect().options];
    expect(options.map((o) => [o.value, o.disabled])).toEqual([
      ['linear', false],
      ['percentile', true],
      ['zscore', true],
      ['robust', true],
    ]);
    expect(tipsOf(step())).toContain('Draw an AOI; the values are measured over it');
    expect(questions()).toHaveLength(0);
  });

  it('turns off the options for an AOI that is gone, and tells a step that has one chosen', async () => {
    await withNormalize();
    await setMethod('zscore');
    act(() => useAppStore.setState({ aoi: null }));
    store().setArea('scene');
    await flush();
    expect(step().textContent).toContain('Draw an AOI; the values are measured over it');
    expect(button('Review').disabled).toBe(false);
    click(button('Review'));
    await flush();
    expect(estimates()).toHaveLength(0);
  });

  it('turns off the options after a reprojection, with the reason, and measures above it', async () => {
    await withNormalize();
    click(button(/＋ Reproject/u));
    const reproject = store().steps[1].key;
    expect([...methodSelect().options].map((o) => o.disabled)).toEqual([false, false, false, false]);
    store().moveStep(reproject, -1);
    await flush();
    expect([...methodSelect(1).options].map((o) => o.disabled)).toEqual([false, true, true, true]);
    expect(tipsOf(step(1))).toContain('Move Normalize above Reproject; the values are measured before a reprojection');
    expect(questions()).toHaveLength(0);
  });
});
