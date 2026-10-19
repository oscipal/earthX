// @vitest-environment jsdom
//
// The processing panel (M4-13b) mounted for real, built from the fixtures of
// the process description (K3). No backend: `fetch` answers by route, jsdom
// has no `EventSource`, so a placed job is followed by polling.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import zarr from '../fixtures/processes/sentinel-2-l2a-zarr3.json';
import { bboxToPolygon } from '../geoUtils';
import { placeAoi } from '../placeSearch';
import { setTrackerOptions, useProcessingStore, type JobEntry } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection, StacItem } from '../types';
import JobList, { EXPIRED_TEXT, JobRow, MIN_REMAINING_MS } from './JobList';
import ProcessingPanel from './ProcessingPanel';
import ViewBar from './ViewBar';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const JOB = 'AbCdEfGhIjKlMnOpQrSt_-';
const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const AOI = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);

function scene(id: string, bbox: [number, number, number, number] = [10, 50, 11, 51]): StacItem {
  return {
    id,
    collection: 'sentinel-2-c1-l2a',
    bbox,
    geometry: bboxToPolygon(bbox),
    properties: { datetime: '2026-07-01T10:00:00Z' },
    assets: {
      red: { href: 'https://example.org/red.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
      nir: { href: 'https://example.org/nir.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
    },
  };
}

function dataset(tier: string, id = 'sentinel-2-c1-l2a', format = 'cog', interpolation = true): DatasetOption {
  return {
    id,
    title: 'Sentinel-2 L2A',
    viewable: true,
    groupBy: ['datetime'],
    zoom: { min: 8, max: 14 },
    browse: 'quicklook',
    quicklookNodataMax: null,
    resultsGroupBy: ['datetime'],
    hasTimeAxis: true,
    collection: {
      id,
      'earthx:format': format,
      'earthx:license_flags': { tier },
      'earthx:capabilities': { interpolation },
    } as unknown as Collection,
  };
}

function select(items: StacItem[], tier = 'processing', option: DatasetOption = dataset(tier)) {
  useAppStore.setState({
    datasets: [option],
    datasetId: option.id,
    items,
    groups: [{ key: ['2026-07-01'], label: '2026-07-01', items }],
    activeGroupIndex: 0,
    selectedIds: items.map((i) => i.id),
    aoi: AOI,
    aoiPoint: null,
  });
}

function json(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': status >= 400 ? 'application/problem+json' : 'application/json', ...headers },
  });
}

function problem(status: number, detail: string, headers: Record<string, string> = {}) {
  return json({ type: 'about:blank', title: 'Refused', status, detail }, status, headers);
}

const ESTIMATE = {
  estimate: {
    size: 4_000_000,
    duration: 'PT3.4S',
    outputPixels: 1_000_000,
    inputPixels: 2_000_000,
    inputBytes: 4_000_000,
    assets: 2,
    units: 1,
  },
  skippedItems: [],
};

function statusDoc(state: string, progress = 0) {
  return {
    processID: 'recipe',
    type: 'process',
    jobID: JOB,
    status: state,
    message: '',
    progress,
    created: '2026-10-10T10:00:00Z',
    expires: new Date(Date.now() + 7 * 86_400_000).toISOString(),
    recipeID: 'r',
    links: [],
  };
}

type Route = (init?: RequestInit) => Response | Promise<Response>;
let routes: Record<string, Route>;
let fetchMock: ReturnType<typeof vi.fn>;
let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  routes = {
    'GET /processing/processes/recipe?dataset=sentinel-2-c1-l2a': () => json(s2),
    'POST /processing/processes/recipe/estimate': () => json(ESTIMATE),
  };
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const route = routes[`${init?.method ?? 'GET'} ${url}`];
    if (!route) return problem(404, `no route ${url}`);
    return route(init);
  });
  vi.stubGlobal('fetch', fetchMock);
  useProcessingStore.getState().resetDraft();
  useProcessingStore.setState({ open: false, jobsOpen: false, descriptions: {}, crs: {}, jobs: [] });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  setTrackerOptions({});
  act(() => root.unmount());
  container.remove();
  for (const job of useProcessingStore.getState().jobs) useProcessingStore.getState().removeJob(job.jobID);
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

// Real time, short: the job is followed with real timers (fake ones race the
// reading of a `Response` body under load).
async function waitFor(check: () => boolean, ms = 3000) {
  const end = Date.now() + ms;
  while (!check()) {
    if (Date.now() > end) throw new Error(`timed out; panel: ${container.textContent}`);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 10));
    });
  }
}

async function flush() {
  await act(async () => {
    for (let i = 0; i < 5; i++) await Promise.resolve();
  });
}

async function openPanel() {
  act(() =>
    root.render(
      <>
        <ProcessingPanel />
        <JobList />
      </>,
    ),
  );
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

async function ndvi() {
  click(button('＋ Band math'));
  typeInto(container.querySelector('textarea[id$="-expression"]')!, '(nir - red) / (nir + red)');
}

async function review() {
  click(button('Review'));
  await flush();
}

describe('the panel built from the schema', () => {
  it('offers the operators of the Sentinel-2 fixture and the bands of the scene', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    expect(button('＋ Band math').disabled).toBe(false);
    expect(button('＋ Reproject and resample').disabled).toBe(false);
    const chips = [...container.querySelectorAll('.pp-chip')].map((c) => c.textContent);
    expect(chips).toEqual(['red', 'nir']);
    expect(container.textContent).toContain('Sentinel-2 L2A · 2026-07-01 · S2B_A');
  });

  it('heads the list of steps "Processing steps"', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    const headings = [...container.querySelectorAll('h3')].map((h) => h.textContent);
    expect(headings).toContain('Processing steps');
    expect(headings).not.toContain('Steps');
    expect(container.querySelector('section[aria-label="Processing steps"]')).not.toBeNull();
  });

  it('leaves out an operator the description does not list', async () => {
    const onlyBandMath = structuredClone(s2) as typeof s2;
    onlyBandMath.inputs.recipe.schema.properties.steps.items.oneOf = [{ $ref: '#/$defs/step_band_math_v1' }];
    routes['GET /processing/processes/recipe?dataset=sentinel-2-c1-l2a'] = () => json(onlyBandMath);
    select([scene('S2B_A')]);
    await openPanel();
    expect(container.textContent).toContain('Band math');
    expect(container.textContent).not.toContain('Reproject');
  });

  describe('a band chip (Otto, 12.10.2026)', () => {
    const expression = () => container.querySelector<HTMLTextAreaElement>('textarea[id$="-expression"]')!;
    const pressed = (name: string) => button(name).getAttribute('aria-pressed');

    function focusExpression(value: string, caret: number, end = caret) {
      typeInto(expression(), value);
      act(() => {
        expression().focus();
        expression().setSelectionRange(caret, end);
      });
    }

    async function withBandMath() {
      select([scene('S2B_A')]);
      await openPanel();
      click(button('＋ Band math'));
    }

    it('inserts its name where the cursor is in an expression, and the bands follow the expression', async () => {
      await withBandMath();
      focusExpression('(  - red)', 2);
      const press = new MouseEvent('mousedown', { bubbles: true, cancelable: true });
      act(() => {
        button('nir').dispatchEvent(press);
      });
      expect(press.defaultPrevented).toBe(true); // the click does not take the cursor away
      click(button('nir'));
      expect(expression().value).toBe('( nir - red)');
      expect(document.activeElement).toBe(expression());
      expect(expression().selectionStart).toBe(5); // behind the name
      expect([pressed('nir'), pressed('red')]).toEqual(['true', 'true']);
    });

    it('puts a space where the name would run into its neighbours', async () => {
      await withBandMath();
      focusExpression('a+b', 2);
      click(button('red'));
      expect(expression().value).toBe('a+ red b');
    });

    it('replaces what is selected in the expression', async () => {
      await withBandMath();
      focusExpression('x + y', 4, 5);
      click(button('nir'));
      expect(expression().value).toBe('x + nir');
    });

    it('only adds the band to the order, and changes no expression, without the cursor in one', async () => {
      await withBandMath();
      typeInto(expression(), 'red * 2');
      act(() => expression().blur());
      click(button('nir'));
      expect(expression().value).toBe('red * 2');
      expect(pressed('nir')).toBe('true');
      click(button('nir'));
      expect(expression().value).toBe('red * 2');
      expect(pressed('nir')).toBe('false');
    });

    it('does not insert while the cursor is in another field', async () => {
      select([scene('S2B_A')]);
      await openPanel();
      click(button('＋ Band math'));
      click(button('＋ Reproject and resample'));
      const resolution = container.querySelector<HTMLInputElement>('input[id$="-resolution"]')!;
      act(() => resolution.focus());
      click(button('nir'));
      expect(resolution.value).toBe('');
      expect(expression().value).toBe('');
      expect(pressed('nir')).toBe('true');
    });

    it('leaves a band out only where no expression names it', async () => {
      await withBandMath();
      typeInto(expression(), 'red + nir');
      act(() => expression().blur());
      const before = useProcessingStore.getState().picked;
      click(button('red'));
      expect(pressed('red')).toBe('true');
      expect(useProcessingStore.getState().picked).toBe(before);
      expect(expression().value).toBe('red + nir');
      expect(button('red').title).toContain('named in an expression');
    });

    it('works without a band-math step: a click adds or leaves out', async () => {
      select([scene('S2B_A')]);
      await openPanel();
      click(button('red'));
      expect(pressed('red')).toBe('true');
      click(button('red'));
      expect(pressed('red')).toBe('false');
    });

    it('says under the chips what a click does', async () => {
      select([scene('S2B_A')]);
      await openPanel();
      const hint = () => container.querySelector('section[aria-label="Bands"] .pp-help')!.textContent;
      expect(hint()).toContain('A click adds a band to the order or leaves it out.');
      expect(hint()).not.toContain('cursor');
      click(button('＋ Band math'));
      expect(hint()).toContain(
        "with the cursor in a band-math expression, it inserts the band's name there instead and changes nothing else",
      );
    });
  });

  it('shows only a reason when nothing is selected', async () => {
    select([]);
    await openPanel();
    expect(container.textContent).toContain('Select a scene first.');
    expect(container.querySelector('.pp-chip')).toBeNull();
  });
});

describe('review before start (K4)', () => {
  it('"Start job" waits for an estimate of exactly this order', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    await ndvi();
    expect(button('Start job').disabled).toBe(true);
    await review();
    expect(container.textContent).toContain('about 1.0 MP, 4.0 MB, about 3 s, 1.0 units');
    expect(container.textContent).toContain('An estimate, not a promise.');
    expect(button('Start job').disabled).toBe(false);
    const body = JSON.parse(fetchMock.mock.calls.find(([u]) => String(u).endsWith('/estimate'))![1].body);
    expect(body.inputs.recipe.inputs).toEqual([
      { name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['S2B_A']], assets: ['red', 'nir'] },
    ]);
    expect(body.inputs.recipe.output).toEqual({ kind: 'raster', format: 'cog', dtype: 'float32' });

    typeInto(container.querySelector('textarea[id$="-expression"]')!, 'nir / red');
    expect(container.textContent).not.toContain('An estimate, not a promise.');
    expect(button('Start job').disabled).toBe(true);
  });

  it('sends the AOI of a place search as a bare geometry, without its properties', async () => {
    select([scene('S2B_A')]);
    useAppStore.setState({ aoi: placeAoi({ name: 'x', display_name: 'x', kind: 'x', bbox: [10.4, 50.4, 10.6, 50.6], outline: AOI, outline_simplified: false }) });
    await openPanel();
    click(button('AOI only'));
    await ndvi();
    await review();
    const body = JSON.parse(fetchMock.mock.calls.find(([u]) => String(u).endsWith('/estimate'))![1].body);
    expect(Object.keys(body.inputs.recipe.aoi).sort()).toEqual(['coordinates', 'type']);
    expect(useAppStore.getState().aoi).toHaveProperty('properties');
  });

  it('shows a refusal of a step at that step', async () => {
    routes['POST /processing/processes/recipe/estimate'] = () =>
      problem(422, 'expression names unknown band(s): nir_2; the input has: red, nir');
    select([scene('S2B_A')]);
    await openPanel();
    await ndvi();
    await review();
    const step = container.querySelector('.pp-step')!;
    expect(step.textContent).toContain('expression names unknown band(s): nir_2');
    expect(button('Start job').disabled).toBe(true);
  });

  it('hides a refusal once the order changed, also one that arrives after the change', async () => {
    let answer!: (r: Response) => void;
    routes['POST /processing/processes/recipe/estimate'] = () => new Promise((resolve) => (answer = resolve));
    select([scene('S2B_A')]);
    await openPanel();
    await ndvi();
    click(button('Review'));
    await flush();
    typeInto(container.querySelector('textarea[id$="-expression"]')!, 'nir / red');
    answer(problem(422, 'expression names unknown band(s): nir_2; the input has: red, nir'));
    await flush();
    expect(container.textContent).not.toContain('unknown band');
  });

  it('shows an error, not a crash, for an estimate it cannot read', async () => {
    routes['POST /processing/processes/recipe/estimate'] = () => json({});
    select([scene('S2B_A')]);
    await openPanel();
    await ndvi();
    await review();
    expect(container.querySelector('[role="alert"]')?.textContent).toContain('cannot read');
    expect(button('Start job').disabled).toBe(true);
  });

  it('says "try again" on a 503', async () => {
    routes['POST /processing/processes/recipe/estimate'] = () =>
      problem(503, 'the job API is not available', { 'Retry-After': '5' });
    select([scene('S2B_A')]);
    await openPanel();
    await ndvi();
    await review();
    expect(container.textContent).toContain('the job API is not available Try again in a moment.');
  });

  it('disables adding a step once the schema maximum is reached', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    for (let i = 0; i < 16; i++) click(button('＋ Band math'));
    expect(button('＋ Band math').disabled).toBe(true);
    expect(button('＋ Band math').title).toBe('At most 16 steps');
    expect(container.querySelectorAll('.pp-step')).toHaveLength(16);
  });

  it('a band picked before the band-math step can be left out again', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    click(button('red'));
    expect(button('red').getAttribute('aria-pressed')).toBe('true');
    click(button('＋ Band math'));
    click(button('red'));
    expect(button('red').getAttribute('aria-pressed')).toBe('false');
    expect(container.querySelector<HTMLTextAreaElement>('textarea[id$="-expression"]')!.value).toBe('');
  });

  it('blocks review with a message while the order is incomplete', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    click(button('＋ Band math'));
    await review();
    expect(container.textContent).toContain('Required.');
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/estimate'))).toBe(false);
  });

  it('drops an estimate still on its way when the selection changes', async () => {
    let answer!: (r: Response) => void;
    routes['POST /processing/processes/recipe/estimate'] = (init) =>
      new Promise((resolve, reject) => {
        answer = resolve;
        init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
      });
    const a = scene('S2B_A');
    select([a, scene('S2B_B', [12, 50, 13, 51])]);
    useAppStore.setState({ selectedIds: ['S2B_A'] });
    await openPanel();
    await ndvi();
    click(button('Review'));
    await flush();
    const signal = fetchMock.mock.calls.find(([u]) => String(u).endsWith('/estimate'))![1].signal as AbortSignal;
    act(() => useAppStore.setState({ selectedIds: ['S2B_A', 'S2B_B'] }));
    expect(signal.aborted).toBe(true);
    answer(json(ESTIMATE));
    await flush();
    expect(container.textContent).not.toContain('An estimate, not a promise.');
    expect(button('Review').disabled).toBe(false);
  });

  const newAoi = () => useAppStore.setState({ aoi: bboxToPolygon([10.45, 50.45, 10.55, 50.55]) });

  async function estimateOnItsWay(area: 'scene' | 'aoi'): Promise<AbortSignal> {
    routes['POST /processing/processes/recipe/estimate'] = (init) =>
      new Promise((_resolve, reject) =>
        init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError'))),
      );
    select([scene('S2B_A')]);
    await openPanel();
    if (area === 'aoi') click(button('AOI only'));
    await ndvi();
    click(button('Review'));
    await flush();
    return fetchMock.mock.calls.find(([u]) => String(u).endsWith('/estimate'))![1].signal as AbortSignal;
  }

  it.each([
    ['the AOI of "AOI only" changes', 'aoi', newAoi],
    ['the panel closes', 'scene', () => useProcessingStore.getState().closeProcessing()],
  ] as const)('aborts an estimate on its way when %s', async (_, area, change) => {
    const signal = await estimateOnItsWay(area);
    act(() => change());
    expect(signal.aborted).toBe(true);
  });

  it('lets an estimate of "Whole scene" finish when the AOI changes: the order is the same', async () => {
    const signal = await estimateOnItsWay('scene');
    act(() => newAoi());
    expect(signal.aborted).toBe(false);
    expect(button('Reviewing…').disabled).toBe(true);
  });

  it('keeps the steps when the AOI changes, and drops the estimate of "AOI only" (M4-13c K3)', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    click(button('AOI only'));
    await ndvi();
    await review();
    expect(button('Start job').disabled).toBe(false);
    act(() => useAppStore.setState({ aoi: bboxToPolygon([10.45, 50.45, 10.55, 50.55]) }));
    expect(container.querySelector('.pp-step')).not.toBeNull();
    expect(container.textContent).not.toContain('An estimate, not a promise.');
    expect(button('Start job').disabled).toBe(true);
  });

  it('keeps the estimate of "Whole scene" when the AOI changes: the order is the same text', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    await ndvi();
    await review();
    act(() => useAppStore.setState({ aoi: bboxToPolygon([10.45, 50.45, 10.55, 50.55]) }));
    expect(container.textContent).toContain('An estimate, not a promise.');
    expect(button('Start job').disabled).toBe(false);
  });

  it('drops the draft when the dataset changes', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    await ndvi();
    act(() => useAppStore.setState({ datasetId: null }));
    expect(useProcessingStore.getState().steps).toEqual([]);
  });
});

describe('the process description', () => {
  it.each([
    ['cannot be loaded', () => problem(503, 'the job API is not available')],
    ['cannot be read', () => json(null)],
  ])('shows an error with Retry when it %s', async (_, failing) => {
    routes['GET /processing/processes/recipe?dataset=sentinel-2-c1-l2a'] = failing;
    select([scene('S2B_A')]);
    await openPanel();
    expect(container.textContent).toContain('The operators could not be loaded');
    routes['GET /processing/processes/recipe?dataset=sentinel-2-c1-l2a'] = () => json(s2);
    click(button('Retry'));
    await flush();
    expect(button('＋ Band math').disabled).toBe(false);
  });
});

describe('resampling and data type (Otto, 12.10.2026)', () => {
  const resampling = () => container.querySelector<HTMLSelectElement>('select[id$="-resampling"]')!;
  const dtypeSelect = () => container.querySelector<HTMLSelectElement>('section[aria-label="Output"] select')!;
  const dtypeLine = () => container.querySelector('section[aria-label="Output"] [aria-label="Data type"]')!.textContent;

  function choose(element: HTMLSelectElement, value: string) {
    act(() => {
      element.value = value;
      element.dispatchEvent(new Event('change', { bubbles: true }));
    });
  }

  function fill(label: string, value: string) {
    typeInto(container.querySelector<HTMLInputElement>(`input[id$="-${label}"]`)!, value);
  }

  const asset = (extra: Record<string, unknown> = {}) => ({ href: 'https://example.org/a.tif', type: COG, ...extra });
  const dem = (): StacItem => ({ ...scene('DEM_A'), assets: { data: asset() } });
  const sent = () => JSON.parse(fetchMock.mock.calls.find(([u]) => String(u).endsWith('/estimate'))![1].body).inputs.recipe;

  async function reprojectDem() {
    select([dem()]);
    await openPanel();
    click(button('data'));
    click(button('＋ Reproject and resample'));
    fill('crs', 'EPSG:3035');
    fill('resolution', '30');
  }

  it('the resampling method is nobody\'s recommendation: nothing is pre-selected, the user chooses', async () => {
    await reprojectDem();
    expect(resampling().value).toBe('');
    expect(container.textContent).not.toContain('recommended');
    await review();
    expect(container.querySelector('.pp-step')!.textContent).toContain('Required.');
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/estimate'))).toBe(false);
    choose(resampling(), 'bilinear');
    await review();
    expect(sent().steps[0].params).toMatchObject({ crs: 'EPSG:3035', resolution: 30, resampling: 'bilinear' });
  });

  it('the data type is chosen by the panel and said so, with the reason; it is sent explicitly', async () => {
    await reprojectDem();
    choose(resampling(), 'bilinear');
    expect(dtypeLine()).toBe('Data type: float32 (chosen automatically)');
    expect(container.textContent).toContain('Interpolating gives fractional values, which an integer type would cut off.');
    await review();
    expect(sent().output.dtype).toBe('float32');
  });

  it('the same type as the source for nearest on integers whose nodata the item states', async () => {
    const item: StacItem = {
      ...scene('LC_A'),
      assets: { lc: asset({ 'raster:bands': [{ data_type: 'uint8', nodata: 255 }] }) },
    };
    select([item]);
    await openPanel();
    click(button('lc'));
    click(button('＋ Reproject and resample'));
    fill('crs', 'EPSG:3035');
    fill('resolution', '30');
    expect(dtypeLine()).toContain('float32'); // no resampling chosen yet
    choose(resampling(), 'nearest');
    expect(dtypeLine()).toBe('Data type: uint8 (chosen automatically)');
    expect(container.textContent).toContain('Same type as the source data (uint8)');
    choose(resampling(), 'bilinear');
    expect(dtypeLine()).toContain('float32');
    choose(resampling(), 'nearest');
    await review();
    expect(sent().output.dtype).toBe('uint8');
  });

  it('a float source keeps its type, also interpolated', async () => {
    const item: StacItem = {
      ...scene('DEM_B'),
      assets: { data: asset({ 'raster:bands': [{ data_type: 'float64' }] }) },
    };
    select([item]);
    await openPanel();
    click(button('data'));
    click(button('＋ Reproject and resample'));
    choose(resampling(), 'bilinear');
    expect(dtypeLine()).toBe('Data type: float64 (chosen automatically)');
  });

  it('band math: float32, integer types not offered, a type chosen before is given up', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    click(button('red'));
    const details = container.querySelector('details')!;
    act(() => details.setAttribute('open', ''));
    choose(dtypeSelect(), 'uint16');
    expect(dtypeLine()).toBe('Data type: uint16 (your choice)');
    click(button('＋ Band math'));
    expect(dtypeLine()).toBe('Data type: float32 (chosen automatically)');
    const disabled = [...dtypeSelect().options].filter((o) => o.disabled).map((o) => o.value);
    expect(disabled).toEqual(['uint8', 'uint16', 'int16', 'uint32', 'int32']);
    expect(container.textContent).toContain('Band math ends in float32 with NaN as nodata');
    expect(container.textContent).toContain('These types are not offered.');
  });

  it('the user can change the type and go back to the automatic one', async () => {
    await reprojectDem();
    choose(resampling(), 'bilinear');
    choose(dtypeSelect(), 'float64');
    expect(dtypeLine()).toBe('Data type: float64 (your choice)');
    await review();
    expect(sent().output.dtype).toBe('float64');
    choose(dtypeSelect(), '');
    expect(dtypeLine()).toBe('Data type: float32 (chosen automatically)');
    expect([...dtypeSelect().options][0].textContent).toBe('Automatic: float32');
  });

  it('warns for an integer type on a source that states no nodata (the DEM with uint16)', async () => {
    await reprojectDem();
    choose(dtypeSelect(), 'uint16');
    expect(container.textContent).toContain('uint16 needs a nodata value that the source file states for every band');
    choose(dtypeSelect(), 'float32');
    expect(container.textContent).not.toContain('needs a nodata value');
  });
});

describe('a COG asset without band descriptions (K7, Otto 10.10.2026)', () => {
  it('gets a chip with the asset name, which puts the asset into the order', async () => {
    const dem: StacItem = {
      ...scene('DEM_A'),
      assets: { data: { href: 'https://example.org/dem.tif', type: COG } },
    };
    select([dem]);
    await openPanel();
    expect([...container.querySelectorAll('.pp-chip')].map((c) => c.textContent)).toEqual(['data']);
    click(button('data'));
    expect(button('data').getAttribute('aria-pressed')).toBe('true');
  });
});

describe('a Zarr dataset (K7, Otto 10.10.2026)', () => {
  const ID = 'sentinel-2-l2a-zarr3';

  function zarrScene(bands: { name: string }[] | undefined): StacItem {
    return {
      ...scene('S2_Z'),
      assets: {
        SR_10m: {
          href: 'https://example.org/r10m',
          type: 'application/vnd+zarr',
          ...(bands ? { bands } : {}),
          // an extension field the panel must not read
          ...({ 'eo:bands': [{ name: 'b99' }] } as object),
        },
      },
    };
  }

  beforeEach(() => {
    routes[`GET /processing/processes/recipe?dataset=${ID}`] = () => json(zarr);
  });

  it('offers one chip per variable named in bands, as <asset>:<variable>', async () => {
    select([zarrScene([{ name: 'b04' }, { name: 'b08' }])], 'processing', dataset('processing', ID, 'zarr'));
    await openPanel();
    expect([...container.querySelectorAll('.pp-chip')].map((c) => c.textContent)).toEqual(['b04', 'b08']);
    click(button('＋ Band math'));
    click(button('b08'));
    click(button('b04'));
    typeInto(container.querySelector('textarea[id$="-expression"]')!, 'b08 - b04');
    await review();
    const body = JSON.parse(fetchMock.mock.calls.find(([u]) => String(u).endsWith('/estimate'))![1].body);
    expect(body.inputs.recipe.inputs[0].assets).toEqual(['SR_10m:b04', 'SR_10m:b08']);
  });

  it('offers no chip and says so when the asset lists no band names, whatever an extension field says', async () => {
    select([zarrScene(undefined)], 'processing', dataset('processing', ID, 'zarr'));
    await openPanel();
    expect(container.querySelector('.pp-chip')).toBeNull();
    expect(container.textContent).toContain('This dataset does not list band names yet.');
    expect(container.textContent).not.toContain('b99');
  });
});

describe('the scenes of one pass are one mosaic (M4-12b, lifting F8)', () => {
  const NEAR = [10.2, 50.2, 10.8, 50.8] as [number, number, number, number];

  // Passes as the results list groups them: one group per label.
  function selectPasses(passes: Record<string, StacItem[]>) {
    const items = Object.values(passes).flat();
    select(items);
    useAppStore.setState({
      groups: Object.entries(passes).map(([label, group]) => ({ key: [label], label, items: group })),
    });
  }

  const passPicker = () =>
    [...container.querySelectorAll('label')].find((l) => l.textContent?.startsWith('Pass'))?.querySelector('select') ?? null;

  async function estimateBody() {
    await ndvi();
    await review();
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith('/estimate'))!;
    return JSON.parse(call[1].body).inputs.recipe;
  }

  it('sends every selected scene of the pass for "Whole scene", without an AOI', async () => {
    select([scene('S2B_B', NEAR), scene('S2B_A', [10, 50, 11, 51]), scene('S2B_FAR', [12, 50, 13, 51])]);
    await openPanel();
    expect(container.textContent).toContain('3 scenes');
    const recipe = await estimateBody();
    expect(recipe.inputs[0].groups).toEqual([['S2B_A', 'S2B_B', 'S2B_FAR']]);
    expect(recipe).not.toHaveProperty('aoi');
  });

  it('sends every scene the AOI meets in one group for "AOI only", and asks for no pick', async () => {
    select([scene('S2B_B', NEAR), scene('S2B_A', [10, 50, 11, 51]), scene('S2B_FAR', [12, 50, 13, 51])]);
    await openPanel();
    click(button('AOI only'));
    expect(container.textContent).toContain('2 scenes');
    expect(container.textContent).toContain('merged into one mosaic');
    expect(passPicker()).toBeNull();
    const recipe = await estimateBody();
    expect(recipe.inputs[0].groups).toEqual([['S2B_A', 'S2B_B']]);
    expect(recipe.aoi.type).toBe('Polygon');
  });

  it('sends the same text however the scenes were selected', async () => {
    select([scene('S2B_B', NEAR), scene('S2B_A')]);
    await openPanel();
    const forward = await estimateBody();
    act(() => useAppStore.setState({ selectedIds: ['S2B_A', 'S2B_B'] }));
    await review();
    const call = fetchMock.mock.calls.filter(([u]) => String(u).endsWith('/estimate')).at(-1)!;
    expect(JSON.parse(call[1].body).inputs.recipe).toEqual(forward);
  });

  it('asks for a pass when the selection has scenes of two, and says one job covers one', async () => {
    selectPasses({
      '2026-07-02': [scene('S2B_C', NEAR)],
      '2026-07-01': [scene('S2B_A'), scene('S2B_B', NEAR)],
    });
    await openPanel();
    expect(container.textContent).toContain('One job covers the scenes of one pass');
    expect(container.querySelector('.pp-chip')).toBeNull();
    expect([...passPicker()!.querySelectorAll('option')].map((o) => o.textContent)).toEqual([
      '— choose one pass —',
      '2026-07-02 (1 scene)',
      '2026-07-01 (2 scenes)',
    ]);
    const picker = passPicker()!;
    act(() => {
      picker.value = '2026-07-01';
      picker.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect([...container.querySelectorAll('.pp-chip')].map((c) => c.textContent)).toEqual(['red', 'nir']);
    expect(container.textContent).toContain('2 scenes');
    const recipe = await estimateBody();
    expect(recipe.inputs[0].groups).toEqual([['S2B_A', 'S2B_B']]);
  });

  it('does not review while no pass is picked', async () => {
    selectPasses({ '2026-07-02': [scene('S2B_C', NEAR)], '2026-07-01': [scene('S2B_A')] });
    await openPanel();
    click(button('Review'));
    await flush();
    expect(container.textContent).toContain('Pick a pass.');
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/estimate'))).toBe(false);
  });

  it('shows the refusal of a mosaic the server turns away', async () => {
    routes['POST /processing/processes/recipe/estimate'] = () =>
      problem(422, 'scenes of another pass: S2B_B; a mosaic is made of one pass');
    select([scene('S2B_A'), scene('S2B_B', NEAR)]);
    await openPanel();
    await ndvi();
    await review();
    expect(container.querySelector('[role="alert"]')?.textContent).toContain('scenes of another pass: S2B_B');
  });
});

describe('starting and following a job', () => {
  it('shows the error of the start after a good estimate', async () => {
    routes['POST /processing/processes/recipe/execution'] = () =>
      problem(502, 'an input of the order is no longer at its source (sentinel-2-c1-l2a/S2B_A)');
    select([scene('S2B_A')]);
    await openPanel();
    await ndvi();
    await review();
    click(button('Start job'));
    await flush();
    expect(container.querySelector('[role="alert"]')?.textContent).toContain('no longer at its source');
    expect(useProcessingStore.getState().jobs).toEqual([]);
  });

  it('starts, follows by polling and offers the files when the job is done', async () => {
    let polls = 0;
    routes['POST /processing/processes/recipe/execution'] = () => json(statusDoc('accepted'), 201);
    routes[`GET /processing/jobs/${JOB}`] = () => json(statusDoc(++polls < 2 ? 'running' : 'successful', 100));
    routes[`GET /processing/jobs/${JOB}/results`] = () =>
      json({
        result: {
          href: `/processing/jobs/${JOB}/results/result.tif`,
          properties: { 'earthx:resampled': true },
        },
        mask: { href: `/processing/jobs/${JOB}/results/mask.tif` },
        recipe: { href: `/processing/jobs/${JOB}/results/recipe.json` },
      });
    select([scene('S2B_A')]);
    await openPanel();
    await ndvi();
    await review();
    setTrackerOptions({ pollMs: 5 });
    click(button('Start job'));
    await waitFor(() => container.querySelectorAll('.pp-links a').length > 0);
    setTrackerOptions({});
    expect(polls).toBe(2);
    const links = [...container.querySelectorAll('.pp-links a')].map((a) => [a.textContent, a.getAttribute('href')]);
    expect(links).toEqual([
      ['Result (COG)', `/processing/jobs/${JOB}/results/result.tif`],
      ['Mask', `/processing/jobs/${JOB}/results/mask.tif`],
      ['Recipe', `/processing/jobs/${JOB}/results/recipe.json`],
    ]);
    expect(container.textContent).toContain('Resampled to a common grid');
    const stored = sessionStorage.getItem('earthx.processing.jobs')!;
    expect(JSON.parse(stored)).toEqual([{ jobID: JOB, expires: expect.any(String) }]);
    expect(stored).not.toContain('10.4');
  });

  it('needs a new review for a second job of the same order', async () => {
    routes['POST /processing/processes/recipe/execution'] = () => json(statusDoc('accepted'), 201);
    routes[`GET /processing/jobs/${JOB}`] = () => json(statusDoc('running', 10));
    select([scene('S2B_A')]);
    await openPanel();
    await ndvi();
    await review();
    click(button('Start job'));
    await flush();
    expect(useProcessingStore.getState().jobs).toHaveLength(1);
    expect(button('Start job').disabled).toBe(true);
  });

  it('follows a job by server-sent events through the store', async () => {
    const sources: { url: string; emit: (data: unknown) => void; closed: boolean }[] = [];
    class Source {
      readyState = 1;
      onerror = null;
      closed = false;
      private listener: ((e: { data: string }) => void) | null = null;
      readonly url: string;
      constructor(url: string) {
        this.url = url;
        sources.push(this);
      }
      addEventListener(_type: string, listener: (e: { data: string }) => void) {
        this.listener = listener;
      }
      close() {
        this.closed = true;
      }
      emit(data: unknown) {
        act(() => this.listener?.({ data: JSON.stringify(data) }));
      }
    }
    setTrackerOptions({ EventSource: Source as never });
    routes['POST /processing/processes/recipe/execution'] = () => json(statusDoc('accepted'), 201);
    routes[`GET /processing/jobs/${JOB}/results`] = () =>
      json({ result: { href: `/processing/jobs/${JOB}/results/result.tif`, properties: { 'earthx:resampled': false } } });
    select([scene('S2B_A')]);
    await openPanel();
    await ndvi();
    await review();
    click(button('Start job'));
    await flush();
    expect(sources[0].url).toBe(`/processing/jobs/${JOB}/events`);
    sources[0].emit(statusDoc('running', 70));
    expect(container.textContent).toContain('Running · 70%');
    sources[0].emit(statusDoc('successful', 100));
    await flush();
    expect(sources[0].closed).toBe(true);
    expect(container.querySelector('.pp-links a')?.textContent).toBe('Result (COG)');
    expect(container.textContent).not.toContain('Resampled');
    expect(fetchMock.mock.calls.some(([u]) => String(u) === `/processing/jobs/${JOB}`)).toBe(false);
  });

  it('shows the title of a failed job', async () => {
    routes[`GET /processing/jobs/${JOB}`] = () => json({ ...statusDoc('failed'), message: 'The source failed' });
    routes[`GET /processing/jobs/${JOB}/results`] = () =>
      json({ type: 'urn:earthx:job-failed:source_5xx', title: 'The source failed', status: 502, detail: 'x' }, 502);
    sessionStorage.setItem(
      'earthx.processing.jobs',
      JSON.stringify([{ jobID: JOB, expires: new Date(Date.now() + 86_400_000).toISOString() }]),
    );
    act(() => root.render(<JobList />));
    act(() => {
      useProcessingStore.getState().resumeJobs();
      useProcessingStore.getState().openJobs();
    });
    await waitFor(() => container.textContent?.includes('Failed: The source failed') ?? false);
  });

  // M4-11b-2 (plan §3.3): one archive where the result has one; the wording of failures and expiry.
  async function resume(results: () => Response, state = 'successful') {
    routes[`GET /processing/jobs/${JOB}`] = () => json(statusDoc(state, 100));
    routes[`GET /processing/jobs/${JOB}/results`] = results;
    sessionStorage.setItem(
      'earthx.processing.jobs',
      JSON.stringify([{ jobID: JOB, expires: new Date(Date.now() + 86_400_000).toISOString() }]),
    );
    act(() => root.render(<JobList />));
    act(() => {
      useProcessingStore.getState().resumeJobs();
      useProcessingStore.getState().openJobs();
    });
  }

  const link = (name: string) => ({ href: `/processing/jobs/${JOB}/results/${name}`, type: 'application/octet-stream' });

  it.each([
    ['a raster job', { result: link('result.tif'), mask: link('mask.tif'), recipe: link('recipe.json'), bundle: link('result.zip') }, 'result.zip'],
    ['an export', { export: link('export.zip'), recipe: link('recipe.json') }, 'export.zip'],
  ])('offers %s as one link "Download (ZIP)"', async (_, doc, file) => {
    await resume(() => json(doc));
    await waitFor(() => container.querySelectorAll('.pp-links a').length > 0);
    const links = [...container.querySelectorAll('.pp-links a')] as HTMLAnchorElement[];
    expect(links.map((a) => a.textContent)).toEqual(['Download (ZIP)']);
    expect(links[0].getAttribute('href')).toBe(`/processing/jobs/${JOB}/results/${file}`);
  });

  it('keeps the single links of a result from before archives existed', async () => {
    await resume(() => json({ result: link('result.tif'), mask: link('mask.tif'), recipe: link('recipe.json') }));
    await waitFor(() => container.querySelectorAll('.pp-links a').length > 0);
    expect([...container.querySelectorAll('.pp-links a')].map((a) => a.textContent)).toEqual([
      'Result (COG)',
      'Mask',
      'Recipe',
    ]);
  });

  it.each([
    ['runtime_exceeded', 'The job took longer than allowed', 'The job took longer than allowed. Choose a smaller area or fewer assets.'],
    [
      'disk_space',
      'The worker has too little disk space for this job; choose a smaller area or fewer assets, or try later',
      'The worker has too little disk space for this job; choose a smaller area or fewer assets, or try later',
    ],
  ])('words a failure of kind %s for the user', async (kind, title, text) => {
    await resume(() => json({ type: `urn:earthx:job-failed:${kind}`, title, status: 500, detail: 'x' }, 500), 'failed');
    await waitFor(() => container.textContent?.includes(`Failed: ${text}`) ?? false);
  });

  it('says the result expired when /results answers 410, before the row\'s own clock does', async () => {
    await resume(() => json({ type: 'urn:earthx:gone', title: 'Gone', status: 410, detail: 'the result has expired' }, 410));
    await waitFor(() => container.textContent?.includes(EXPIRED_TEXT) ?? false);
    expect(container.querySelector('.pp-links a')).toBeNull();
    expect(container.querySelector('.hint-text.error')).toBeNull();
  });
});

describe('a finished job row (K6)', () => {
  function entry(expiresIn: number, resampled: boolean | null): JobEntry {
    return {
      jobID: JOB,
      expires: new Date(Date.now() + expiresIn).toISOString(),
      status: null,
      phase: 'successful',
      files: [{ file: 'result.tif', label: 'Result (COG)' }],
      resampled,
      failure: null,
      error: null,
      cancelling: false,
      expired: false,
    };
  }

  it('links the files until a minute before expiry, then says "Expired"', () => {
    vi.useFakeTimers();
    act(() => root.render(<ul><JobRow job={entry(MIN_REMAINING_MS + 5000, false)} /></ul>));
    expect(container.querySelector('.pp-links a')).not.toBeNull();
    expect(container.textContent).not.toContain('Resampled');
    act(() => {
      vi.advanceTimersByTime(5100);
    });
    expect(container.querySelector('.pp-links a')).toBeNull();
    expect(container.textContent).toContain(EXPIRED_TEXT);
  });

  it('shows "Expired" at once inside the last minute', () => {
    act(() => root.render(<ul><JobRow job={entry(MIN_REMAINING_MS - 1000, true)} /></ul>));
    expect(container.querySelector('.pp-links a')).toBeNull();
    expect(container.textContent).toContain('Expired');
  });
});

describe('the Process button (B11, K12)', () => {
  function showBar() {
    act(() => root.render(<ViewBar />));
  }

  it('is disabled with the reason when the licence tier is below processing', () => {
    select([scene('S2B_A')], 'display');
    showBar();
    const process = button(/Process/);
    expect(process.disabled).toBe(true);
    expect(process.title).toContain('tier: display');
  });

  it('needs no AOI: "Whole scene" sends none (M4-13c K1)', () => {
    select([scene('S2B_A')]);
    useAppStore.setState({ aoi: null });
    showBar();
    expect(button(/Process/).disabled).toBe(false);
  });

  it('opens the panel', () => {
    select([scene('S2B_A')]);
    showBar();
    click(button(/Process/));
    expect(useProcessingStore.getState().open).toBe(true);
  });
});

describe('cancelling and losing a job', () => {
  function resume() {
    sessionStorage.setItem(
      'earthx.processing.jobs',
      JSON.stringify([{ jobID: JOB, expires: new Date(Date.now() + 86_400_000).toISOString() }]),
    );
    act(() => root.render(<JobList />));
    act(() => {
      useProcessingStore.getState().resumeJobs();
      useProcessingStore.getState().openJobs();
    });
  }

  beforeEach(() => {
    setTrackerOptions({ pollMs: 60_000 });
    routes[`GET /processing/jobs/${JOB}`] = () => json(statusDoc('running', 20));
  });

  it('cancels with DELETE and drops the job from sessionStorage', async () => {
    routes[`DELETE /processing/jobs/${JOB}`] = () => json(statusDoc('dismissed'));
    resume();
    await waitFor(() => container.textContent?.includes('Running · 20%') ?? false);
    click(button('Cancel'));
    await waitFor(() => container.textContent?.includes('Cancelled') ?? false);
    expect(sessionStorage.getItem('earthx.processing.jobs')).toBeNull();
  });

  it('says "Gone" when the job is no longer there at cancel', async () => {
    routes[`DELETE /processing/jobs/${JOB}`] = () => problem(404, 'there is no such job');
    resume();
    await waitFor(() => container.textContent?.includes('Running') ?? false);
    click(button('Cancel'));
    await waitFor(() => container.textContent?.includes('Gone') ?? false);
  });

  it('keeps the job and shows the error when cancel fails', async () => {
    routes[`DELETE /processing/jobs/${JOB}`] = () => problem(503, 'the job queue is not reachable; try again');
    resume();
    await waitFor(() => container.textContent?.includes('Running') ?? false);
    click(button('Cancel'));
    await waitFor(() => container.textContent?.includes('not reachable') ?? false);
    expect(button('Cancel').disabled).toBe(false);
    expect(sessionStorage.getItem('earthx.processing.jobs')).toContain(JOB);
  });

  it('says "Gone" and forgets the job when polling finds it no more', async () => {
    routes[`GET /processing/jobs/${JOB}`] = () => problem(404, 'there is no such job');
    resume();
    await waitFor(() => container.textContent?.includes('Gone (expired or dismissed)') ?? false);
    expect(sessionStorage.getItem('earthx.processing.jobs')).toBeNull();
  });
});

describe('the area of the order (M4-13c §3.2)', () => {
  const recipeOf = (call: unknown[]) => JSON.parse((call[1] as RequestInit).body as string).inputs.recipe;
  const lastEstimate = () => recipeOf(fetchMock.mock.calls.filter(([u]) => String(u).endsWith('/estimate')).at(-1)!);

  it('starts on "Whole scene", sends no AOI and says what the mask covers', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    expect(button('Whole scene').getAttribute('aria-pressed')).toBe('true');
    expect(container.textContent).toContain('The result covers the whole scene; the mask marks where they have data.');
    await ndvi();
    await review();
    expect(lastEstimate()).not.toHaveProperty('aoi');
  });

  it('sends the AOI for "AOI only"', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    click(button('AOI only'));
    await ndvi();
    await review();
    expect(lastEstimate().aoi).toEqual(AOI);
  });

  it('works without an AOI, and offers "AOI only" only with one', async () => {
    select([scene('S2B_A')]);
    useAppStore.setState({ aoi: null });
    await openPanel();
    expect(button('AOI only').disabled).toBe(true);
    expect(button('AOI only').title).toBe('Draw an AOI first');
    await ndvi();
    await review();
    expect(button('Start job').disabled).toBe(false);
  });

  it('blocks "AOI only" once the AOI is gone, and says so', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    click(button('AOI only'));
    await ndvi();
    act(() => useAppStore.setState({ aoi: null }));
    expect(container.textContent).toContain('Draw an AOI first, or choose “Whole scene”.');
    await review();
    expect(container.textContent).toContain('Draw an area as AOI.');
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/estimate'))).toBe(false);
  });

  describe('a whole scene over the cap of one job (K2)', () => {
    beforeEach(() => {
      routes['POST /processing/processes/recipe/estimate'] = () =>
        problem(413, 'the job would write 6200 MB; 5000 MB a job may write');
    });

    it('shows the reason and switches to "AOI only" on request', async () => {
      select([scene('S2B_A')]);
      await openPanel();
      await ndvi();
      await review();
      expect(container.textContent).toContain('5000 MB a job may write');
      expect(container.textContent).toContain('The whole scene is too large for one job. Try “AOI only”.');
      click(button('Use AOI only'));
      expect(useProcessingStore.getState().area).toBe('aoi');
      expect(container.textContent).not.toContain('too large for one job');
    });

    it('asks for an AOI when there is none', async () => {
      select([scene('S2B_A')]);
      useAppStore.setState({ aoi: null });
      await openPanel();
      await ndvi();
      await review();
      expect(container.textContent).toContain('Draw an AOI to process a part of the scene.');
      expect([...container.querySelectorAll('button')].some((b) => b.textContent === 'Use AOI only')).toBe(false);
    });

    it('suggests nothing for "AOI only": the server says what is too large', async () => {
      select([scene('S2B_A')]);
      await openPanel();
      click(button('AOI only'));
      await ndvi();
      await review();
      expect(container.textContent).toContain('5000 MB a job may write');
      expect(container.textContent).not.toContain('too large for one job');
    });
  });
});

describe('bands named in an expression go into the order by themselves (M4-13c point 5)', () => {
  const sentAssets = () =>
    JSON.parse(fetchMock.mock.calls.filter(([u]) => String(u).endsWith('/estimate')).at(-1)![1].body).inputs.recipe
      .inputs[0].assets;

  it('takes the bands of a typed expression, without a click on a chip, and drops one taken out', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    click(button('＋ Band math'));
    const field = container.querySelector<HTMLTextAreaElement>('textarea[id$="-expression"]')!;
    typeInto(field, 'nir * 2');
    await review();
    expect(sentAssets()).toEqual(['nir']);
    typeInto(field, '(nir - red) / (nir + red)');
    await review();
    expect(sentAssets()).toEqual(['red', 'nir']);
    typeInto(field, 'red + 1');
    await review();
    expect(sentAssets()).toEqual(['red']);
  });
});

describe('the expression field (M4-13c §3.1)', () => {
  it('stays one line: Enter adds none, a pasted line break becomes a space', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    click(button('＋ Band math'));
    const field = container.querySelector<HTMLTextAreaElement>('textarea[id$="-expression"]')!;
    const enter = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
    act(() => field.dispatchEvent(enter));
    expect(enter.defaultPrevented).toBe(true);
    typeInto(field, 'nir -\nred');
    expect(useProcessingStore.getState().steps[0].values.expression).toBe('nir - red');
  });
});

describe('the panel and the window of the jobs (M4-13c §3.1)', () => {
  it('opens the window of the jobs when a job starts; the panel holds no job rows', async () => {
    routes['POST /processing/processes/recipe/execution'] = () => json(statusDoc('accepted'), 201);
    routes[`GET /processing/jobs/${JOB}`] = () => json(statusDoc('running', 5));
    setTrackerOptions({ pollMs: 60_000 });
    select([scene('S2B_A')]);
    await openPanel();
    expect(container.querySelector('[aria-label="Jobs"]')).toBeNull();
    await ndvi();
    await review();
    click(button('Start job'));
    await flush();
    expect(useProcessingStore.getState().jobsOpen).toBe(true);
    const jobs = container.querySelector('[aria-label="Jobs"]')!;
    expect(jobs.querySelector('.pp-job')).not.toBeNull();
    expect(container.querySelector('[aria-label="Processing"] .pp-job')).toBeNull();
    click(button('✕', jobs));
    expect(container.querySelector('[aria-label="Jobs"]')).toBeNull();
  });

  it('folds the sheet down to its head and opens it again (narrow screens)', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    const panel = container.querySelector('.processing-panel')!;
    click(button('▾'));
    expect(panel.classList.contains('folded')).toBe(true);
    click(button('▴'));
    expect(panel.classList.contains('folded')).toBe(false);
  });
});

describe('the target CRS and the resolution of a reproject step (M4-13c-3)', () => {
  const crsDoc = (code: string, unit: Record<string, unknown>, kind = 'projected') => ({
    code,
    name: `CRS ${code}`,
    kind,
    unit,
  });
  const METRE = { name: 'metre', kind: 'linear', toBase: 1 };
  const FOOT = { name: 'US survey foot', kind: 'linear', toBase: 1200 / 3937 };
  const DEGREE = { name: 'degree', kind: 'angular', toBase: 1 };
  const UNKNOWN = 'EPSG:99999 is not a CRS this platform knows';

  // A scene at 46.8–47.8° N (middle 47.3); the AOI of the suite lies at 50.4–50.6° N.
  const southern = (): StacItem => ({
    ...scene('DEM_S', [10, 46.8, 11, 47.8]),
    assets: { data: { href: 'https://example.org/a.tif', type: COG } },
  });

  const crsCalls = () => fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.startsWith('/processing/crs/'));
  const cellSize = () => container.querySelector('[aria-label="Cell size"]')?.textContent ?? null;
  const input = (name: string) => container.querySelector<HTMLInputElement>(`input[id$="-${name}"]`)!;

  async function openStep(items: StacItem[] = [southern()]) {
    select(items);
    await openPanel();
    click(button('data'));
    click(button('＋ Reproject and resample'));
  }

  // Past the rest of the field (300 ms) and the answer.
  async function answered(text: string) {
    await waitFor(() => container.textContent?.includes(text) ?? false);
  }

  function chooseResampling(value: string) {
    const element = container.querySelector<HTMLSelectElement>('select[id$="-resampling"]')!;
    act(() => {
      element.value = value;
      element.dispatchEvent(new Event('change', { bubbles: true }));
    });
  }

  beforeEach(() => {
    routes['GET /processing/crs/EPSG%3A3035'] = () => json(crsDoc('EPSG:3035', METRE));
    routes['GET /processing/crs/EPSG%3A2227'] = () => json(crsDoc('EPSG:2227', FOOT));
    routes['GET /processing/crs/EPSG%3A4326'] = () => json(crsDoc('EPSG:4326', DEGREE, 'geographic'));
    routes['GET /processing/crs/EPSG%3A99999'] = () => problem(422, UNKNOWN);
  });

  it('shows nothing about a unit before the CRS is a code', async () => {
    await openStep();
    typeInto(input('crs'), 'EPSG:30');
    typeInto(input('resolution'), '10');
    await flush();
    expect(cellSize()).toBeNull();
    expect(container.textContent).not.toContain('Looking up');
    expect(crsCalls()).toEqual([]);
  });

  it('metres: "Cell size: 10 m × 10 m", after the field has rested', async () => {
    await openStep();
    typeInto(input('crs'), 'EPSG:3035');
    typeInto(input('resolution'), '10');
    expect(container.textContent).toContain('Looking up the unit of EPSG:3035…');
    expect(crsCalls()).toEqual([]);
    await answered('Cell size: 10 m × 10 m');
    expect(crsCalls()).toEqual(['/processing/crs/EPSG%3A3035']);
  });

  it('follows the resolution as it is typed, without asking again', async () => {
    await openStep();
    typeInto(input('crs'), 'EPSG:3035');
    typeInto(input('resolution'), '10');
    await answered('Cell size: 10 m');
    typeInto(input('resolution'), '30');
    expect(cellSize()).toBe('Cell size: 30 m × 30 m');
    typeInto(input('resolution'), '');
    expect(cellSize()).toBe('The resolution is in metre.');
    expect(crsCalls()).toHaveLength(1);
  });

  it('another linear unit: its name and the metres', async () => {
    await openStep();
    typeInto(input('crs'), 'EPSG:2227');
    typeInto(input('resolution'), '10');
    await answered('Cell size: 10 US survey foot × 10 US survey foot (≈ 3.05 m)');
  });

  it('degrees: the size on the ground at the middle latitude of the scenes (Whole scene)', async () => {
    await openStep();
    typeInto(input('crs'), 'EPSG:4326');
    typeInto(input('resolution'), '0.0003');
    await answered('Cell size: 0.0003° × 0.0003° ≈ 33 m (N–S) × 23 m (E–W) at 47.3° N');
  });

  it('recalculates at once when the area changes, with no new question', async () => {
    await openStep();
    typeInto(input('crs'), 'EPSG:4326');
    typeInto(input('resolution'), '0.0003');
    await answered('at 47.3° N');
    click(button('AOI only'));
    expect(cellSize()).toBe('Cell size: 0.0003° × 0.0003° ≈ 33 m (N–S) × 21 m (E–W) at 50.5° N');
    click(button('Whole scene'));
    expect(cellSize()).toContain('at 47.3° N');
    expect(crsCalls()).toHaveLength(1);
  });

  it('a new AOI moves the latitude under "AOI only"', async () => {
    await openStep();
    typeInto(input('crs'), 'EPSG:4326');
    typeInto(input('resolution'), '0.0003');
    click(button('AOI only'));
    await answered('at 50.5° N');
    act(() => useAppStore.setState({ aoi: bboxToPolygon([10.4, 40.0, 10.6, 40.2]) }));
    expect(cellSize()).toContain('at 40.1° N');
  });

  it('without an AOI under "AOI only" the degrees stay degrees', async () => {
    await openStep();
    typeInto(input('crs'), 'EPSG:4326');
    typeInto(input('resolution'), '0.0003');
    click(button('AOI only'));
    await answered('Cell size');
    act(() => useAppStore.setState({ aoi: null }));
    expect(cellSize()).toBe('Cell size: 0.0003° × 0.0003°');
  });

  it('typing on drops the question: only the code it rests on is asked for', async () => {
    await openStep();
    typeInto(input('crs'), 'EPSG:2227');
    await new Promise((resolve) => setTimeout(resolve, 100));
    typeInto(input('crs'), 'EPSG:3035');
    typeInto(input('resolution'), '10');
    await answered('Cell size: 10 m');
    expect(crsCalls()).toEqual(['/processing/crs/EPSG%3A3035']);
  });

  it('a code already known is not asked again', async () => {
    await openStep();
    typeInto(input('crs'), 'EPSG:3035');
    typeInto(input('resolution'), '10');
    await answered('Cell size: 10 m');
    typeInto(input('crs'), 'EPSG:2227');
    await answered('US survey foot');
    typeInto(input('crs'), 'EPSG:3035');
    expect(cellSize()).toBe('Cell size: 10 m × 10 m');
    await flush();
    expect(crsCalls()).toHaveLength(2);
  });

  describe('a code the server turns away (422)', () => {
    async function refused() {
      await openStep();
      typeInto(input('crs'), 'EPSG:99999');
      typeInto(input('resolution'), '10');
      chooseResampling('bilinear');
      await answered(UNKNOWN);
    }

    it('says why at the field, shows no cell size, and holds the review back', async () => {
      await refused();
      const alert = [...container.querySelectorAll('[role="alert"]')].map((e) => e.textContent);
      expect(alert).toContain(UNKNOWN);
      expect(cellSize()).toBeNull();
      expect(button('Review').disabled).toBe(true);
      expect(button('Review').title).toBe(UNKNOWN);
      expect(button('Start job').disabled).toBe(true);
    });

    it('sends no estimate even when asked directly', async () => {
      await refused();
      await act(async () => useProcessingStore.getState().reviewOrder());
      expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/estimate'))).toBe(false);
    });

    it('lets the review go on once the code is another', async () => {
      await refused();
      typeInto(input('crs'), 'EPSG:3035');
      await answered('Cell size: 10 m');
      expect(button('Review').disabled).toBe(false);
      await review();
      expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/estimate'))).toBe(true);
    });

    it('does not hold back a step that is not a reproject', async () => {
      await refused();
      click(button(/Remove/, container.querySelector('.pp-step')!));
      await ndvi();
      expect(button('Review').disabled).toBe(false);
    });
  });

  it('an answer that cannot be fetched is a hint, and the review is not held back', async () => {
    routes['GET /processing/crs/EPSG%3A3035'] = () => problem(503, 'the service is busy');
    await openStep();
    typeInto(input('crs'), 'EPSG:3035');
    typeInto(input('resolution'), '10');
    chooseResampling('bilinear');
    await answered('The unit of EPSG:3035 could not be looked up: the service is busy');
    expect(cellSize()).toBeNull();
    expect(button('Review').disabled).toBe(false);
  });

  it('asks again after a failure when the code is typed anew', async () => {
    let calls = 0;
    routes['GET /processing/crs/EPSG%3A3035'] = () => (++calls === 1 ? problem(503, 'busy') : json(crsDoc('EPSG:3035', METRE)));
    await openStep();
    typeInto(input('crs'), 'EPSG:3035');
    typeInto(input('resolution'), '10');
    await answered('could not be looked up');
    typeInto(input('crs'), 'EPSG:303');
    typeInto(input('crs'), 'EPSG:3035');
    await answered('Cell size: 10 m × 10 m');
    expect(calls).toBe(2);
  });

  it('leaves the order as it was: the resolution is still a plain number in the unit of the CRS', async () => {
    await openStep();
    typeInto(input('crs'), 'EPSG:4326');
    typeInto(input('resolution'), '0.0003');
    chooseResampling('bilinear');
    await answered('Cell size');
    await review();
    const body = JSON.parse(fetchMock.mock.calls.find(([u]) => String(u).endsWith('/estimate'))![1].body);
    expect(body.inputs.recipe.steps[0].params).toMatchObject({ crs: 'EPSG:4326', resolution: 0.0003, resampling: 'bilinear' });
  });

  it('a step that is no reproject asks nothing', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    await ndvi();
    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(crsCalls()).toEqual([]);
  });
});
