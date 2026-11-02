// @vitest-environment jsdom
//
// The "Normalize" step of the processing panel (NM4-11b, NM4-71): the methods, the job's order (version 4, no numbers), the
// measure for the preview alone (the tile gets version 3 with the numbers), what the (i) says of it, and the locks. No backend:
// `fetch` answers the process description, the statistics and the estimate.

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
    // The target range starts at 0 to 1 (Otto, 01.11.2026); the range to measure is not filled in.
    expect([box('Target min').value, box('Target max').value, box('From min').value, box('From max').value]).toEqual(['0', '1', '', '']);
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


  it('sends version 4 with the fields of the fixed range and nothing measured, without a question to the route', async () => {
    await withNormalize();
    for (const [label, value] of [['From min', '0'], ['From max', '10000'], ['Target min', '0'], ['Target max', '1']] as const) typeInto(box(label), value);
    click(button('Review'));
    await flush();
    const sent = JSON.parse(String(estimates().at(-1)![1].body)).inputs.recipe.steps;
    expect(sent).toEqual([
      { op: 'normalize', op_version: 4, params: { method: 'linear', bands: ['red'], in_min: 0, in_max: 10000, out_min: 0, out_max: 1, clip: false } },
    ]);
    expect(questions()).toHaveLength(0);
  });

  it('tells at "Z-score" that outliers weigh, and where to go instead', async () => {
    await withNormalize();
    expect(tipsOf(step())).toContain('Sensitive to outliers, e.g. in indices; prefer Robust (median, IQR) there.');
    await setMethod('zscore');
    expect(tipsOf(step())).toContain('Sensitive to outliers, e.g. in indices; prefer Robust (median, IQR) there.');
  });
});

describe('the measure (for the preview alone)', () => {
  const sentSteps = () => JSON.parse(String(estimates().at(-1)![1].body)).inputs.recipe.steps;
  const previewSteps = () => orderView(selectionState(useAppStore.getState()), store()).built?.previewOrder?.steps;

  it('asks the route once for the bands over the AOI as float64, and the order the job gets holds no numbers', async () => {
    await withNormalize();
    await setMethod('percentile');
    expect(questions()).toHaveLength(1);
    expect(questions()[0]).toMatchObject({
      recipe_version: 2,
      aoi: AOI,
      steps: [],
      output: { kind: 'raster', format: 'cog', dtype: 'float64', bands: ['red'] },
    });
    expect(step().textContent).toContain('Preview measured ✓');
    expect(tipsOf(step())).toContain('red: p_low 200, p_high 6000');
    fillTarget();
    click(button('Review'));
    await flush();
    expect(sentSteps()).toEqual([
      {
        op: 'normalize',
        op_version: 4,
        params: { method: 'percentile', bands: ['red'], low: 2, high: 98, out_min: 0, out_max: 1, clip: false },
      },
    ]);
    // The tile gets version 3 with the numbers.
    expect(previewSteps()).toEqual([
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
    ['linear', undefined, ['bands', 'clip', 'in_max', 'in_min', 'method', 'out_max', 'out_min']],
    ['percentile', { p_low: 200, p_high: 6000 }, ['bands', 'clip', 'high', 'low', 'method', 'out_max', 'out_min']],
    ['zscore', { mean: 2000, stddev: 500 }, ['bands', 'method']],
    ['robust', { p25: 1500, median: 1900, p75: 2400 }, ['bands', 'method']],
  ])('%s: the job gets version 4 without `measured`; the tile gets version 3, with the numbers of each band chosen', async (method, numbers, keys) => {
    await withNormalize({ bands: 'red, nir' });
    await setMethod(method);
    if (method === 'linear') {
      typeInto(box('From min'), '0');
      typeInto(box('From max'), '10000');
    }
    if (method === 'percentile' || method === 'linear') fillTarget();
    click(button('Review'));
    await flush();
    const [job] = sentSteps();
    expect(job.op_version).toBe(4);
    expect(Object.keys(job.params).sort()).toEqual(keys);
    const [tile] = previewSteps()!;
    expect(tile.op_version).toBe(3);
    if (numbers) expect(tile.params.measured).toEqual({ factor: 1, bands: { red: numbers, nir: numbers } });
    else expect(Object.keys(tile.params).sort()).toEqual(keys);
  });

  it('takes the minimum and the maximum for 0–100 % into the tile', async () => {
    await withNormalize();
    await setMethod('percentile');
    choose(rangeSelect(), '0–100 %');
    fillTarget();
    expect(previewSteps()![0].params).toMatchObject({ low: 0, high: 100, measured: { bands: { red: { p_low: 100, p_high: 9000 } } } });
    click(button('Review'));
    await flush();
    expect(sentSteps()[0].params).toMatchObject({ low: 0, high: 100 });
    expect(questions()).toHaveLength(1);
  });

  it('does not hold "Review" and "Start job" while the route has not answered', async () => {
    let answer!: () => void;
    const gate = new Promise<void>((resolve) => (answer = resolve));
    const before = statistics;
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === STATISTICS_ROUTE) {
        await gate;
        return before(JSON.parse(String(init!.body)));
      }
      if (url === DESCRIPTION) return json(s2);
      if (url === '/processing/processes/recipe/estimate') return json(ESTIMATE);
      return json({}, 404);
    });
    await withNormalize();
    await setMethod('zscore');
    expect(step().textContent).toContain('Measuring…');
    expect(button('Review').disabled).toBe(false);
    expect(button('Review').title).not.toContain('measuring');
    expect(button('Start job').title).not.toContain('measuring');
    click(button('Review'));
    await flush();
    expect(estimates()).toHaveLength(1);
    expect(sentSteps()).toEqual([{ op: 'normalize', op_version: 4, params: { method: 'zscore', bands: ['red'] } }]);
    expect(button('Start job').disabled).toBe(false);
    answer();
    await flush();
    expect(step().textContent).not.toContain('Measuring…');
  });

  it('says at the step that the measurement failed, with the reason of the route, asks again on "Retry", and holds nothing back', async () => {
    statistics = () => json({ detail: 'The area is too large to measure.' }, 422);
    await withNormalize();
    await setMethod('zscore');
    expect(step().textContent).toContain('Not measured.');
    expect(tipsOf(step())).toMatch(/The measurement failed: .*The area is too large to measure\./u);
    expect(button('Review').disabled).toBe(false);
    click(button('Review'));
    await flush();
    expect(estimates()).toHaveLength(1);
    expect(button('Start job').disabled).toBe(false);
    expect(questions()).toHaveLength(1);
    // The tile has no numbers, so the map ends before the step.
    expect(previewSteps()).toBeUndefined();
    statistics = (body) => json({ bands: body.output.bands.map((name) => ({ name, unit: null, statistics: STATISTICS })), exact: true, factor: 1 });
    click(button('Retry'));
    await flush();
    expect(questions()).toHaveLength(2);
    expect(step().textContent).toContain('Preview measured ✓');
    expect(previewSteps()).toHaveLength(1);
  });

  it('names the bands that have no valid value, without "Retry", and the job is still sent (it fails with its reason)', async () => {
    statistics = (body) => json({ bands: body.output.bands.map((name) => ({ name, unit: null, statistics: { count: 0, valid_percent: 0 } })), exact: true, factor: 1 });
    await withNormalize();
    await setMethod('zscore');
    expect(step().textContent).toContain('Not measured.');
    expect(tipsOf(step())).toContain('No valid values in red to measure.');
    expect([...step().querySelectorAll('button')].map((b) => b.textContent)).not.toContain('Retry');
    expect(button('Review').disabled).toBe(false);
    click(button('Review'));
    await flush();
    expect(estimates()).toHaveLength(1);
  });

  it.each([
    [false, 3, 'Preview estimated on a coarser read; the job measures exactly.'],
    [true, 1, 'Preview measured exactly over the AOI.'],
  ])('says behind the (i) what the route read, exact %s', async (exact, factor, note) => {
    statistics = (body) => json({ bands: body.output.bands.map((name) => ({ name, unit: null, statistics: STATISTICS })), exact, factor });
    await withNormalize();
    await setMethod('zscore');
    expect(tipsOf(step())).toContain(note);
    expect(tipsOf(step()).includes('coarser')).toBe(!exact);
    // A line of text beside the (i) there is none.
    expect(step().textContent).not.toContain(note);
    // The factor goes into the tile; the job measures exactly itself.
    expect(previewSteps()![0].params.measured).toMatchObject({ factor });
    click(button('Review'));
    await flush();
    expect(JSON.stringify(sentSteps())).not.toContain('measured');
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

  it('measures a second step on the first one as the tile takes it (version 3 with its numbers); the job gets version 4 for both', async () => {
    await withNormalize();
    await setMethod('zscore');
    click(button('＋ Normalize'));
    const second = store().steps[1].key;
    store().updateStep(second, 'bands', 'red');
    store().updateStep(second, 'method', 'robust');
    await flush();
    expect(questions()).toHaveLength(2);
    expect(questions()[1].steps.map((s: { op: string }) => s.op)).toEqual(['normalize']);
    expect(questions()[1].steps[0]).toMatchObject({ op_version: 3, params: { measured: { bands: { red: { mean: 2000, stddev: 500 } } } } });
    click(button('Review'));
    await flush();
    expect(sentSteps().map((s: { op_version: number; params: { method: string } }) => [s.op_version, s.params.method])).toEqual([[4, 'zscore'], [4, 'robust']]);
    expect(JSON.stringify(sentSteps())).not.toContain('measured');
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

  it('has the same question in the view as the one asked, and nothing that holds the order back', async () => {
    const key = await withNormalize();
    await setMethod('zscore');
    const view = orderView(selectionState(useAppStore.getState()), store());
    expect(view.needs.map((need) => need.body)).toEqual(questions());
    expect(view.built?.order).not.toBeNull();
    expect(view).not.toHaveProperty('measureBlock');
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

  it('draws the step with the numbers measured as version 3, takes no part of it before, and puts the AOI into no tile address', async () => {
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

  it('draws the fixed range as version 3 with the same fields, without asking the route', async () => {
    await withNormalize();
    vi.useFakeTimers();
    try {
      typeInto(box('From min'), '0');
      typeInto(box('From max'), '10000');
      await afterDebounce();
      const url = new URL(store().preview!.scenes[0].url, 'http://localhost');
      expect(url.searchParams.getAll('op_version')).toEqual(['3']);
      expect(JSON.parse(url.searchParams.get('params')!)).toEqual({ method: 'linear', bands: ['red'], in_min: 0, in_max: 10000, out_min: 0, out_max: 1, clip: false });
      // No question for numbers; the range of the picture over the AOI (NM4-19) is asked on the order as the route takes it, version 3.
      expect(questions().filter((q) => q.output.dtype === 'float64')).toEqual([]);
      for (const q of questions()) expect(q.steps.map((s: { op_version: number }) => s.op_version)).toEqual([3]);
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

describe('without an AOI', () => {
  it('lets the methods that measure be chosen, and asks the route for the whole scenes: the body holds no AOI', async () => {
    await withNormalize({ area: 'scene', aoi: null });
    expect([...methodSelect().options].map((o) => [o.value, o.disabled])).toEqual([
      ['linear', false],
      ['percentile', false],
      ['zscore', false],
      ['robust', false],
    ]);
    expect(tipsOf(step())).not.toContain('Draw an AOI');
    await setMethod('zscore');
    expect(questions()).toHaveLength(1);
    expect(questions()[0]).not.toHaveProperty('aoi');
    expect(questions()[0]).toMatchObject({ steps: [], output: { dtype: 'float64', bands: ['red'] } });
    expect(step().textContent).toContain('Preview measured ✓');
  });

  it('sends the job without an AOI and without numbers, and says the preview is an estimate where the route says so', async () => {
    statistics = (body) => json({ bands: body.output.bands.map((name) => ({ name, unit: null, statistics: STATISTICS })), exact: false, factor: 6 });
    await withNormalize({ area: 'scene', aoi: null });
    await setMethod('robust');
    expect(tipsOf(step())).toContain('Preview estimated on a coarser read; the job measures exactly.');
    expect(button('Review').disabled).toBe(false);
    click(button('Review'));
    await flush();
    const recipe = JSON.parse(String(estimates().at(-1)![1].body)).inputs.recipe;
    expect(recipe).not.toHaveProperty('aoi');
    expect(recipe.steps).toEqual([{ op: 'normalize', op_version: 4, params: { method: 'robust', bands: ['red'] } }]);
  });

  it('puts nothing of an area into an address', async () => {
    await withNormalize({ area: 'scene', aoi: null });
    await setMethod('percentile');
    click(button('Review'));
    await flush();
    for (const [url] of fetchMock.mock.calls) expect(String(url)).not.toMatch(/aoi|coordinates|50\.4/u);
  });

  it('measures the whole scenes when the AOI goes away, and does not hold the order back', async () => {
    await withNormalize();
    await setMethod('zscore');
    expect(questions()).toHaveLength(1);
    act(() => useAppStore.setState({ aoi: null }));
    store().setArea('scene');
    await flush();
    expect(questions()).toHaveLength(2);
    expect(questions()[1]).not.toHaveProperty('aoi');
    expect(step().textContent).not.toContain('Draw an AOI');
    expect(button('Review').disabled).toBe(false);
    click(button('Review'));
    await flush();
    expect(estimates()).toHaveLength(1);
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

  it('measures only the area shown, one question however many jobs, and every job gets version 4 without numbers', async () => {
    statistics = (body) => json({ bands: bandsOf(body as never, sceneOf(body as never)), exact: true, factor: 1 });
    await withScenes();
    expect(questions()).toHaveLength(1);
    expect(['S1', 'S2', 'S3']).toContain(sceneOf(questions()[0]));
    expect(button('Review').disabled).toBe(false);
    click(button('Review'));
    await flush();
    const sent = estimates().map(([, init]) => JSON.parse(String(init.body)).inputs.recipe);
    expect(sent.map((r) => sceneOf(r)).sort()).toEqual(['S1', 'S2', 'S3']);
    for (const recipe of sent) expect(recipe.steps).toEqual([{ op: 'normalize', op_version: 4, params: { method: 'zscore', bands: ['red'] } }]);
    expect(questions()).toHaveLength(1);
  });

  it('holds no job back when the measurement of the shown area fails, and says it at the step with "Retry"', async () => {
    statistics = () => json({ detail: 'The area is too large to measure.' }, 422);
    await withScenes();
    expect(questions()).toHaveLength(1);
    expect(button('Review').disabled).toBe(false);
    expect(button('Start 3 jobs').title).not.toContain('measurement');
    expect(step().textContent).toContain('Not measured.');
    expect(tipsOf(step())).toContain('The measurement failed');
    statistics = (body) => json({ bands: bandsOf(body as never, sceneOf(body as never)), exact: true, factor: 1 });
    click(button('Retry'));
    await flush();
    expect(questions()).toHaveLength(2);
    expect(step().textContent).toContain('Preview measured ✓');
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

  it('takes a statistical step of version 3 as version 4 without its numbers: the job measures', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    const stale = { factor: 1, bands: { red: { mean: 1, stddev: 2 } } };
    const result = await load(recipe({ op: 'normalize', op_version: 3, params: { method: 'zscore', bands: ['red'], measured: stale } }));
    expect(result).toEqual({ ok: true, notes: ['Step 1 (normalize): version 3 is taken as version 4.'] });
    expect(store().steps[0]).toMatchObject({ op: 'normalize', opVersion: 4, values: { method: 'zscore', bands: 'red' } });
    expect(JSON.stringify(store().steps)).not.toContain('stddev');
    // The file leaves the area alone: whole scene. The preview is measured over the whole scenes, without an AOI.
    await flush();
    expect(questions()).toHaveLength(1);
    expect(questions()[0]).not.toHaveProperty('aoi');
    store().setArea('aoi');
    await flush();
    expect(questions()).toHaveLength(2);
    click(button('Review'));
    await flush();
    const params = JSON.parse(String(estimates().at(-1)![1].body)).inputs.recipe.steps[0];
    expect(params).toEqual({ op: 'normalize', op_version: 4, params: { method: 'zscore', bands: ['red'] } });
  });

  it('takes version 3 with the fixed range as version 4 with the same numbers', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    const fixed = { method: 'linear', bands: ['red'], in_min: 0, in_max: 10000, out_min: 0, out_max: 1, clip: true };
    const result = await load(recipe({ op: 'normalize', op_version: 3, params: fixed }));
    expect(result).toEqual({ ok: true, notes: ['Step 1 (normalize): version 3 is taken as version 4.'] });
    click(button('Review'));
    await flush();
    expect(JSON.parse(String(estimates().at(-1)![1].body)).inputs.recipe.steps[0]).toEqual({ op: 'normalize', op_version: 4, params: fixed });
    expect(questions()).toHaveLength(0);
  });

  it('takes a file with version 4 as it is, without a note', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    const result = await load(recipe({ op: 'normalize', op_version: 4, params: { method: 'robust', bands: ['red'] } }));
    expect(result).toEqual({ ok: true, notes: [] });
    expect(store().steps[0]).toMatchObject({ opVersion: 4, values: { method: 'robust', bands: 'red' } });
  });

  it('takes a file with version 2 as the fixed range with the same numbers, and says so', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    const result = await load(
      recipe({ op: 'normalize', op_version: 2, params: { bands: ['red'], in_min: 0, in_max: 10000, out_min: 0, out_max: 1, clip: true } }),
    );
    expect(result).toEqual({ ok: true, notes: ['Step 1 (normalize): version 2 is taken as version 4.'] });
    expect(store().steps[0]).toMatchObject({ opVersion: 4, values: { method: 'linear', in_min: '0', in_max: '10000', out_min: '0', out_max: '1', clip: true } });
    expect(methodSelect().value).toBe('linear');
    expect(box('From max').value).toBe('10000');
    store().setArea('aoi');
    click(button('Review'));
    await flush();
    expect(JSON.parse(String(estimates().at(-1)![1].body)).inputs.recipe.steps[0]).toEqual({
      op: 'normalize',
      op_version: 4,
      params: { method: 'linear', bands: ['red'], in_min: 0, in_max: 10000, out_min: 0, out_max: 1, clip: true },
    });
    expect(questions()).toHaveLength(0);
  });

  it('refuses a method the panel does not know, and numbers in version 4, with the step named', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    const unknown = await load(recipe({ op: 'normalize', op_version: 4, params: { method: 'median', bands: ['red'] } }));
    expect(unknown).toMatchObject({ ok: false });
    expect(JSON.stringify(unknown)).toContain('Step 1 (normalize)');
    const numbers = await load(recipe({ op: 'normalize', op_version: 4, params: { method: 'zscore', bands: ['red'], measured: { factor: 1, bands: {} } } }));
    expect(numbers).toMatchObject({ ok: false });
    expect(JSON.stringify(numbers)).toContain('unknown parameter measured');
  });
});

describe('the locks', () => {
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

  it('keeps a step that holds a method after a reprojection out of the order, with the reason at the method', async () => {
    await withNormalize();
    await setMethod('zscore');
    click(button(/＋ Reproject/u));
    store().moveStep(store().steps[1].key, -1);
    await flush();
    expect(tipsOf(step(1))).toContain('Move Normalize above Reproject');
    expect(orderView(selectionState(useAppStore.getState()), store()).built?.order).toBeNull();
  });
});
