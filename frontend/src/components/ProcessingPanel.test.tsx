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
import { bboxToPolygon } from '../geoUtils';
import { setTrackerOptions, useProcessingStore, type JobEntry } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection, StacItem } from '../types';
import { JobRow, MIN_REMAINING_MS } from './JobList';
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

function dataset(tier: string): DatasetOption {
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
  useProcessingStore.setState({ open: false, descriptions: {}, jobs: [] });
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

async function ndvi() {
  click(button('＋ Band math'));
  typeInto(container.querySelector('input[id$="-expression"]')!, '(nir - red) / (nir + red)');
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

  it('leaves out an operator the description does not list', async () => {
    const onlyBandMath = structuredClone(s2) as typeof s2;
    onlyBandMath.inputs.recipe.schema.properties.steps.items.oneOf = [{ $ref: '#/$defs/step_band_math_v1' }];
    routes['GET /processing/processes/recipe?dataset=sentinel-2-c1-l2a'] = () => json(onlyBandMath);
    select([scene('S2B_A')]);
    await openPanel();
    expect(container.textContent).toContain('Band math');
    expect(container.textContent).not.toContain('Reproject');
  });

  it('a chip inserts its name into the expression and the bands follow it', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    click(button('＋ Band math'));
    click(button('nir'));
    const input = container.querySelector<HTMLInputElement>('input[id$="-expression"]')!;
    expect(input.value).toBe('nir');
    expect(button('nir').getAttribute('aria-pressed')).toBe('true');
    expect(button('red').getAttribute('aria-pressed')).toBe('false');
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

    typeInto(container.querySelector('input[id$="-expression"]')!, 'nir / red');
    expect(container.textContent).not.toContain('An estimate, not a promise.');
    expect(button('Start job').disabled).toBe(true);
  });

  it('shows a refusal of a step at that step', async () => {
    routes['POST /processing/processes/recipe/estimate'] = () =>
      problem(400, 'the order is not valid: parameters of step 0 (band_math): the expression names nir_2');
    select([scene('S2B_A')]);
    await openPanel();
    await ndvi();
    await review();
    const step = container.querySelector('.pp-step')!;
    expect(step.textContent).toContain('the expression names nir_2');
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

  it('drops the draft when the AOI changes', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    await ndvi();
    act(() => useAppStore.setState({ aoi: bboxToPolygon([10.45, 50.45, 10.55, 50.55]) }));
    expect(container.querySelector('.pp-step')).toBeNull();
  });
});

describe('one scene per job (F8)', () => {
  it('asks for one scene when several meet the AOI, and says the result covers only it', async () => {
    select([scene('S2B_A'), scene('S2B_B', [10.5, 50.5, 11.5, 51.5])]);
    await openPanel();
    expect(container.textContent).toContain('The result covers only this scene');
    expect(container.querySelector('.pp-chip')).toBeNull();
    const picker = container.querySelector<HTMLSelectElement>('select')!;
    act(() => {
      picker.value = 'S2B_B';
      picker.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(container.textContent).toContain('S2B_B');
    expect([...container.querySelectorAll('.pp-chip')].map((c) => c.textContent)).toEqual(['red', 'nir']);
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

  it('shows the title of a failed job', async () => {
    routes[`GET /processing/jobs/${JOB}`] = () => json({ ...statusDoc('failed'), message: 'The source failed' });
    routes[`GET /processing/jobs/${JOB}/results`] = () =>
      json({ type: 'urn:earthx:job-failed:source_5xx', title: 'The source failed', status: 502, detail: 'x' }, 502);
    sessionStorage.setItem(
      'earthx.processing.jobs',
      JSON.stringify([{ jobID: JOB, expires: new Date(Date.now() + 86_400_000).toISOString() }]),
    );
    act(() => root.render(<ProcessingPanel />));
    act(() => {
      useProcessingStore.getState().resumeJobs();
      useProcessingStore.setState({ open: true });
    });
    await waitFor(() => container.textContent?.includes('Failed: The source failed') ?? false);
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
    expect(container.textContent).toContain('Expired');
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

  it('is disabled without an AOI', () => {
    select([scene('S2B_A')]);
    useAppStore.setState({ aoi: null });
    showBar();
    expect(button(/Process/).disabled).toBe(true);
  });

  it('opens the panel', () => {
    select([scene('S2B_A')]);
    showBar();
    click(button(/Process/));
    expect(useProcessingStore.getState().open).toBe(true);
  });
});
