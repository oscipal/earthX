// @vitest-environment jsdom
//
// "Run as" in the processing panel (M4-13c-4, §3.6): one order per pass or per
// scene with the same steps, the estimate as a sum, the start of the parts the
// server took, and the title of each job. No backend: `fetch` answers by route;
// jsdom has no `EventSource`, so a placed job is followed by polling.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import { bboxToPolygon } from '../geoUtils';
import { resetJobs, setTrackerOptions, useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection, StacItem } from '../types';
import ProcessingManager from './ProcessingManager';
import ProcessingPanel from './ProcessingPanel';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const AOI = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);
const NEAR: [number, number, number, number] = [10, 50, 11, 51];
const FAR: [number, number, number, number] = [20, 50, 21, 51];

function scene(id: string, bbox = NEAR, collection = 'sentinel-2-c1-l2a'): StacItem {
  return {
    id,
    collection,
    bbox,
    geometry: bboxToPolygon(bbox),
    properties: { datetime: '2026-07-01T10:00:00Z' },
    assets: {
      red: { href: 'https://example.org/red.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
      nir: { href: 'https://example.org/nir.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
    },
  };
}

const DATASET: DatasetOption = {
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

// Each inner list is one pass of the results list; every scene is selected.
function selectPasses(passes: StacItem[][], aoi: GeoJSON.Geometry | null = AOI) {
  const items = passes.flat();
  useAppStore.setState({
    datasets: [DATASET],
    datasetId: DATASET.id,
    items,
    groups: passes.map((list, i) => ({ key: [`2026-07-0${i + 1}`], label: `2026-07-0${i + 1}`, items: list })),
    activeGroupIndex: 0,
    selectedIds: items.map((i) => i.id),
    aoi,
    aoiPoint: null,
  });
}

function sceneIds(count: number, prefix = 'S'): StacItem[] {
  return Array.from({ length: count }, (_, i) => scene(`${prefix}${i + 1}`));
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': status >= 400 ? 'application/problem+json' : 'application/json' },
  });
}

function problem(status: number, detail: string) {
  return json({ type: 'about:blank', title: 'Refused', status, detail }, status);
}

function estimateOf(units = 1, pixels = 1_000_000, size = 4_000_000, duration = 'PT3.5S') {
  return { estimate: { size, duration, outputPixels: pixels, inputPixels: 1, inputBytes: 1, assets: 2, units }, skippedItems: [] };
}

function statusDoc(jobID: string) {
  return {
    processID: 'recipe',
    type: 'process',
    jobID,
    status: 'running',
    message: '',
    progress: 10,
    created: '2026-10-10T10:00:00Z',
    expires: new Date(Date.now() + 7 * 86_400_000).toISOString(),
    recipeID: 'r',
    links: [],
  };
}

interface Sent {
  url: string;
  body: { inputs: { recipe: { inputs: { groups: string[][]; assets?: string[] }[]; aoi?: unknown; steps: unknown[]; output: { dtype: string; bands?: string[] } } } };
}

let estimateFor: (ids: string[]) => Response | Promise<Response>;
let placeFor: (ids: string[], n: number) => Response | Promise<Response>;
let estimates: Sent[];
let placed: Sent[];
let container: HTMLDivElement;
let root: Root;

const idsOf = (sent: Sent) => sent.body.inputs.recipe.inputs[0].groups[0];

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  localStorage.clear();
  estimates = [];
  placed = [];
  estimateFor = () => json(estimateOf());
  placeFor = (_ids, n) => json(statusDoc(`Job${String(n).padStart(19, '0')}`));
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      if (method === 'GET' && url === '/processing/processes/recipe?dataset=sentinel-2-c1-l2a') return json(s2);
      const job = /^\/processing\/jobs\/(Job\d{19})$/u.exec(url);
      if (method === 'GET' && job) return json(statusDoc(job[1]));
      if (method === 'POST' && url === '/processing/processes/recipe/estimate') {
        const sent: Sent = { url, body: JSON.parse(init!.body as string) };
        estimates.push(sent);
        return estimateFor(idsOf(sent));
      }
      if (method === 'POST' && url === '/processing/processes/recipe/execution') {
        const sent: Sent = { url, body: JSON.parse(init!.body as string) };
        placed.push(sent);
        return placeFor(idsOf(sent), placed.length);
      }
      return problem(404, `no route ${method} ${url}`);
    }),
  );
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
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

async function flush() {
  await act(async () => {
    for (let i = 0; i < 8; i++) await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

async function openPanel() {
  act(() =>
    root.render(
      <>
        <ProcessingPanel />
        <ProcessingManager />
      </>,
    ),
  );
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

const hasButton = (label: string | RegExp) =>
  [...container.querySelectorAll('button')].some((b) =>
    typeof label === 'string' ? b.textContent?.trim() === label : label.test(b.textContent ?? ''),
  );

function click(element: HTMLElement) {
  act(() => element.dispatchEvent(new MouseEvent('click', { bubbles: true })));
}

function typeInto(input: HTMLTextAreaElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')!.set!;
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

async function start(label: string | RegExp) {
  click(button(label));
  await flush();
}

const runAs = () => container.querySelector('[aria-label="Run as"]');
const text = () => container.textContent ?? '';

describe('what "Run as" offers', () => {
  it('is missing for a single scene', async () => {
    selectPasses([[scene('S1')]]);
    await openPanel();
    expect(runAs()).toBeNull();
    expect(button('Start job')).toBeDefined();
  });

  it('offers a job per scene, not per pass, for the scenes of one pass', async () => {
    selectPasses([sceneIds(3)]);
    await openPanel();
    const labels = [...runAs()!.querySelectorAll('button')].map((b) => b.textContent);
    expect(labels).toEqual(['One job', 'One job per scene (3)']);
  });

  it('offers both for several passes', async () => {
    selectPasses([sceneIds(2, 'A'), sceneIds(1, 'B')]);
    await openPanel();
    const labels = [...runAs()!.querySelectorAll('button')].map((b) => b.textContent);
    expect(labels).toEqual(['One job', 'One job per pass (2)', 'One job per scene (3)']);
  });

  it('greys out a choice over 25 jobs with the reason', async () => {
    selectPasses([sceneIds(26)]);
    await openPanel();
    const perScene = button('One job per scene (26)');
    expect(perScene.disabled).toBe(true);
    expect(perScene.title).toBe('At most 25 jobs at once');
    // not only in the tooltip: a touch screen has none
    expect(text()).toContain('At most 25 jobs at once.');
  });

  it('takes 25 jobs', async () => {
    selectPasses([sceneIds(25)]);
    await openPanel();
    expect(button('One job per scene (25)').disabled).toBe(false);
  });

  it('goes back to one job when the choice is gone', async () => {
    selectPasses([sceneIds(3)]);
    await openPanel();
    click(button('One job per scene (3)'));
    expect(button('One job per scene (3)').getAttribute('aria-pressed')).toBe('true');
    act(() => useAppStore.setState({ selectedIds: ['S1'] }));
    expect(runAs()).toBeNull();
    expect(hasButton('Start job')).toBe(true);
  });

  it('does not keep the choice for the next draft', async () => {
    selectPasses([sceneIds(3)]);
    await openPanel();
    click(button('One job per scene (3)'));
    act(() => useProcessingStore.getState().resetDraft());
    expect(button('One job').getAttribute('aria-pressed')).toBe('true');
  });
});

describe('reviewing a batch', () => {
  it('asks for an estimate of every scene with the same steps, bands and data type, and no AOI', async () => {
    selectPasses([sceneIds(3)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (3)'));
    await review();
    expect(estimates.map(idsOf)).toEqual([['S1'], ['S2'], ['S3']]);
    const [first, ...rest] = estimates.map((e) => e.body.inputs.recipe);
    expect(first.aoi).toBeUndefined();
    expect(first.inputs[0].assets).toBeUndefined();
    expect(first.output.bands).toEqual(['Band_Math_1']);
    for (const other of rest) {
      expect(other.steps).toEqual(first.steps);
      expect(other.inputs[0].assets).toBeUndefined();
      expect(other.output.bands).toEqual(first.output.bands);
      expect(other.output).toEqual(first.output);
    }
  });

  it('asks for an estimate of every pass, the scenes of a pass in one order', async () => {
    selectPasses([sceneIds(2, 'A'), sceneIds(1, 'B')]);
    await openPanel();
    await ndvi();
    click(button('One job per pass (2)'));
    await review();
    expect(estimates.map(idsOf)).toEqual([['A1', 'A2'], ['B1']]);
  });

  it('shows the sum, the work and the rule of the queue', async () => {
    selectPasses([sceneIds(3)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (3)'));
    await review();
    expect(text()).toContain('3 jobs · about 3.0 MP, 12.0 MB, 3.0 units in total');
    expect(text()).toContain('about 11 s of work');
    expect(text()).toContain('Jobs run 2 at a time per source; the rest wait.');
    expect(button('Start 3 jobs').disabled).toBe(false);
  });

  it('keeps the start shut until the batch is reviewed', async () => {
    selectPasses([sceneIds(3)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (3)'));
    expect(button('Start 3 jobs').disabled).toBe(true);
    expect(button('Start 3 jobs').title).toBe('Review the order first');
  });

  it('asks for four estimates at a time at most', async () => {
    let running = 0;
    let peak = 0;
    estimateFor = async () => {
      running += 1;
      peak = Math.max(peak, running);
      await new Promise((resolve) => setTimeout(resolve, 5));
      running -= 1;
      return json(estimateOf());
    };
    selectPasses([sceneIds(10)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (10)'));
    click(button('Review'));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 150));
    });
    expect(estimates).toHaveLength(10);
    expect(peak).toBe(4);
    expect(text()).toContain('10 jobs');
  });

  it('shows what the server refused one by one, and starts the rest', async () => {
    estimateFor = (ids) => (ids[0] === 'S2' ? problem(413, 'the job is larger than 5 GB') : json(estimateOf()));
    selectPasses([sceneIds(3)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (3)'));
    await review();
    const alerts = [...container.querySelectorAll('[role="alert"]')].map((a) => a.textContent);
    expect(alerts).toEqual(['S2: the job is larger than 5 GB']);
    expect(text()).toContain('2 jobs · about 2.0 MP');
    expect(button('Start 2 of 3 jobs').disabled).toBe(false);
    // 413 under "Whole scene": the suggestion of K2
    expect(text()).toContain('The whole scene is too large for one job.');
  });

  it('does not start when the server refused every part', async () => {
    estimateFor = () => problem(422, 'no good');
    selectPasses([sceneIds(2)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (2)'));
    await review();
    expect(button('Start 0 of 2 jobs').disabled).toBe(true);
    expect([...container.querySelectorAll('[role="alert"]')]).toHaveLength(2);
  });

  it('shows the scenes the AOI misses that the server left out', async () => {
    estimateFor = () => json({ ...estimateOf(), skippedItems: ['S2'] });
    selectPasses([sceneIds(2)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (2)'));
    await review();
    expect(text()).toContain('Left out (the AOI misses them): S2');
    expect(text()).not.toContain('S2, S2');
  });

  it('drops the sum when a step changes, and asks again', async () => {
    selectPasses([sceneIds(2)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (2)'));
    await review();
    expect(text()).toContain('2 jobs');
    typeInto(container.querySelector('textarea[id$="-expression"]')!, 'nir - red');
    expect(text()).not.toContain('in total');
    expect(button('Start 2 jobs').disabled).toBe(true);
  });

  it('drops the sum when "Run as" changes', async () => {
    selectPasses([sceneIds(2)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (2)'));
    await review();
    click(button('One job'));
    expect(text()).not.toContain('in total');
  });

  it('lets a late answer of a dropped review go', async () => {
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => (release = resolve));
    estimateFor = async () => {
      await held;
      return json(estimateOf());
    };
    selectPasses([sceneIds(2)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (2)'));
    click(button('Review'));
    await flush();
    act(() => useAppStore.setState({ selectedIds: ['S1'] }));
    release();
    await flush();
    expect(useProcessingStore.getState().batch).toBeNull();
    expect(useProcessingStore.getState().reviewing).toBe(false);
  });
});

describe('"AOI only" in a batch', () => {
  it('makes jobs only for the scenes the AOI meets', async () => {
    selectPasses([[scene('IN1'), scene('FAR', FAR), scene('IN2')]]);
    await openPanel();
    await ndvi();
    click(button('AOI only'));
    expect(button('One job per scene (2)')).toBeDefined();
    click(button('One job per scene (2)'));
    await review();
    expect(estimates.map(idsOf)).toEqual([['IN1'], ['IN2']]);
    expect(estimates[0].body.inputs.recipe.aoi).toBeDefined();
  });
});

describe('starting a batch', () => {
  it('starts one job for each part, each with its own scenes, and opens no panel', async () => {
    selectPasses([sceneIds(3)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (3)'));
    await review();
    await start('Start 3 jobs');
    expect(placed.map(idsOf)).toEqual([['S1'], ['S2'], ['S3']]);
    expect(useProcessingStore.getState().jobs).toHaveLength(3);
    expect(useAppStore.getState().dock).toBe('controls');
    // one review, these jobs: the next start needs a new review
    expect(button('Start 3 jobs').disabled).toBe(true);
  });

  it('starts them one after the other', async () => {
    let running = 0;
    let peak = 0;
    placeFor = async (_ids, n) => {
      running += 1;
      peak = Math.max(peak, running);
      await new Promise((resolve) => setTimeout(resolve, 5));
      running -= 1;
      return json(statusDoc(`Job${String(n).padStart(19, '0')}`));
    };
    selectPasses([sceneIds(4)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (4)'));
    await review();
    click(button('Start 4 jobs'));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 100));
    });
    expect(placed).toHaveLength(4);
    expect(peak).toBe(1);
  });

  it('does not start the parts whose review the server refused, and says so on the button', async () => {
    estimateFor = (ids) => (ids[0] === 'S2' ? problem(422, 'no good') : json(estimateOf()));
    selectPasses([sceneIds(3)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (3)'));
    await review();
    await start('Start 2 of 3 jobs');
    expect(placed.map(idsOf)).toEqual([['S1'], ['S3']]);
  });

  it('goes on after a start the server refuses, and says which', async () => {
    placeFor = (ids, n) => (ids[0] === 'S2' ? problem(503, 'the queue is full') : json(statusDoc(`Job${String(n).padStart(19, '0')}`)));
    selectPasses([sceneIds(3)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (3)'));
    await review();
    await start('Start 3 jobs');
    expect(placed.map(idsOf)).toEqual([['S1'], ['S2'], ['S3']]);
    expect(useProcessingStore.getState().jobs).toHaveLength(2);
    const alerts = [...container.querySelectorAll('[role="alert"]')].map((a) => a.textContent);
    expect(alerts).toEqual(['S2: the queue is full Try again in a moment.']);
  });

  it('starts nothing when a new AOI sends the batch back to one job after the review', async () => {
    selectPasses([[scene('IN1'), scene('IN2')]]);
    await openPanel();
    await ndvi();
    click(button('AOI only'));
    click(button('One job per scene (2)'));
    await review();
    act(() => useAppStore.setState({ aoi: bboxToPolygon([10.1, 50.1, 10.2, 50.2]) }));
    await flush();
    expect(button('Start job').disabled).toBe(true);
    await act(async () => {
      await useProcessingStore.getState().startJob();
    });
    expect(placed).toHaveLength(0);
  });

  it('starts nothing when the order changes between review and start, even when the store is asked directly', async () => {
    selectPasses([sceneIds(2)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (2)'));
    await review();
    typeInto(container.querySelector('textarea[id$="-expression"]')!, 'nir - red');
    expect(button('Start 2 jobs').disabled).toBe(true);
    // the button is shut, but the store must hold the line on its own
    await act(async () => {
      await useProcessingStore.getState().startJob();
    });
    expect(placed).toHaveLength(0);
  });
});

describe('the title and the entry of a batch (K5, UI-01 §6.4, §6.5)', () => {
  const TITLE = /^Band math · Sentinel-2 L2A · 1 Jul( 2026)?$/;
  const shelf = () => JSON.parse(localStorage.getItem('earthx.processing.manager')!);

  it('gives the jobs of a batch one title and the batch one entry, the parts told apart by their label', async () => {
    selectPasses([sceneIds(3)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (3)'));
    await review();
    await start('Start 3 jobs');
    const { jobs, batches } = useProcessingStore.getState();
    expect(batches).toHaveLength(1);
    expect(batches[0].title).toMatch(TITLE);
    expect(jobs.map((j) => j.title)).toEqual([batches[0].title, batches[0].title, batches[0].title]);
    expect(jobs.map((j) => j.batchId)).toEqual([batches[0].id, batches[0].id, batches[0].id]);
    expect(jobs.map((j) => j.part).sort()).toEqual(['S1', 'S2', 'S3']);
    expect(batches[0].id).toMatch(/^[0-9a-f]{32}$/);
    // One row for the batch, folded; the parts show when it is opened.
    expect(container.querySelectorAll('.pm-row')).toHaveLength(1);
  });

  it('keeps the batch in the browser with the title, the batch and the part of every job, and its order', async () => {
    selectPasses([sceneIds(2)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (2)'));
    await review();
    await start('Start 2 jobs');
    const stored = shelf();
    const { batches } = useProcessingStore.getState();
    expect(stored.v).toBe(1);
    expect(stored.batches).toEqual([{ id: batches[0].id, title: batches[0].title, createdAt: expect.any(String), refused: [] }]);
    expect(stored.jobs).toHaveLength(2);
    for (const job of stored.jobs) {
      expect(Object.keys(job).sort()).toEqual(['batchId', 'createdAt', 'expires', 'jobID', 'order', 'part', 'title']);
      expect(job.batchId).toBe(batches[0].id);
      expect(job.order.steps).toHaveLength(1);
    }
    expect(stored.jobs.map((j: { part: string }) => j.part).sort()).toEqual(['S1', 'S2']);
  });

  it('numbers nothing, and records the part the server refused, with its reason', async () => {
    placeFor = (ids, n) => (ids[0] === 'S2' ? problem(422, 'no good') : json(statusDoc(`Job${String(n).padStart(19, '0')}`)));
    selectPasses([sceneIds(3)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (3)'));
    await review();
    await start('Start 3 jobs');
    const { jobs, batches } = useProcessingStore.getState();
    expect(jobs.map((j) => j.part).sort()).toEqual(['S1', 'S3']);
    expect(jobs.every((j) => !/\d\/\d/.test(j.title ?? ''))).toBe(true);
    expect(batches).toHaveLength(1);
    expect(batches[0].refused).toEqual([{ label: 'S2', message: expect.stringContaining('no good') }]);
    expect(shelf().batches[0].refused).toEqual(batches[0].refused);
  });

  it('makes no entry for a batch the server refused whole', async () => {
    placeFor = () => problem(422, 'no good');
    selectPasses([sceneIds(2)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (2)'));
    await review();
    click(button('Start 2 jobs'));
    await flush();
    expect(useProcessingStore.getState().batches).toEqual([]);
    expect(useProcessingStore.getState().jobs).toEqual([]);
    expect(localStorage.getItem('earthx.processing.manager')).toBeNull();
  });

  it('is taken up again after a reload, the batch with its parts', async () => {
    selectPasses([sceneIds(2)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (2)'));
    await review();
    await start('Start 2 jobs');
    const before = useProcessingStore.getState();
    resetJobs();
    expect(useProcessingStore.getState().jobs).toHaveLength(0);
    act(() => useProcessingStore.getState().resumeJobs());
    const after = useProcessingStore.getState();
    expect(after.batches).toEqual(before.batches);
    expect(after.jobs.map((j) => [j.jobID, j.title, j.batchId, j.part, j.order !== null]).sort()).toEqual(
      before.jobs.map((j) => [j.jobID, j.title, j.batchId, j.part, true]).sort(),
    );
  });

  it('names a single job by operators, dataset and day, and makes no batch', async () => {
    selectPasses([sceneIds(3)]);
    await openPanel();
    await ndvi();
    await review();
    await start('Start job');
    const { jobs, batches } = useProcessingStore.getState();
    expect(jobs.map((j) => j.title)).toEqual([expect.stringMatching(TITLE)]);
    expect(jobs[0].batchId).toBeNull();
    expect(batches).toEqual([]);
  });
});

describe('a draft that changes while the batch is on its way', () => {
  it('names the jobs after the order that was started, not the draft as it is by then', async () => {
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => (release = resolve));
    placeFor = async (_ids, n) => {
      if (n === 1) await held;
      return json(statusDoc(`Job${String(n).padStart(19, '0')}`));
    };
    selectPasses([sceneIds(2)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (2)'));
    await review();
    click(button('Start 2 jobs'));
    await flush();
    click(button('＋ Reproject and resample'));
    release();
    await flush();
    expect(useProcessingStore.getState().jobs.map((j) => j.title)).toEqual([
      expect.stringMatching(/^Band math · Sentinel-2 L2A · 1 Jul/),
      expect.stringMatching(/^Band math · Sentinel-2 L2A · 1 Jul/),
    ]);
  });

  it('does not review while the jobs are being started', async () => {
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => (release = resolve));
    placeFor = async (_ids, n) => {
      if (n === 1) await held;
      return json(statusDoc(`Job${String(n).padStart(19, '0')}`));
    };
    selectPasses([sceneIds(2)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (2)'));
    await review();
    const before = estimates.length;
    click(button('Start 2 jobs'));
    await flush();
    expect(button('Review').disabled).toBe(true);
    await act(async () => {
      await useProcessingStore.getState().reviewOrder();
    });
    expect(estimates).toHaveLength(before);
    release();
    await flush();
  });

  it('lets a start that was overtaken by a new draft leave the new draft alone', async () => {
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => (release = resolve));
    placeFor = async (_ids, n) => {
      if (n === 1) await held;
      return json(statusDoc(`Job${String(n).padStart(19, '0')}`));
    };
    selectPasses([sceneIds(2)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (2)'));
    await review();
    click(button('Start 2 jobs'));
    await flush();
    act(() => useProcessingStore.getState().resetDraft());
    expect(useProcessingStore.getState().starting).toBe(false);
    act(() => useProcessingStore.setState({ starting: true }));
    release();
    await flush();
    // the old start ended; the flag of the draft that began meanwhile is not its to clear
    expect(useProcessingStore.getState().starting).toBe(true);
  });

  it('stops asking for estimates when a step changes', async () => {
    let calls = 0;
    estimateFor = async () => {
      calls += 1;
      await new Promise((resolve) => setTimeout(resolve, 20));
      return json(estimateOf());
    };
    selectPasses([sceneIds(12)]);
    await openPanel();
    await ndvi();
    // The clock is the test's: with the real one, a wait that ran long on a busy machine let all twelve estimates
    // (four at a time, 20 ms each) finish before the step changed.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    try {
      click(button('One job per scene (12)'));
      click(button('Review'));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(30);
      });
      expect(calls).toBe(8); // two rounds of four have been asked, the first answered
      typeInto(container.querySelector('textarea[id$="-expression"]')!, 'nir - red');
      await act(async () => {
        await vi.advanceTimersByTimeAsync(150);
      });
      expect(calls).toBeLessThanOrEqual(8 + 4);
      expect(calls).toBeLessThan(12);
      expect(useProcessingStore.getState().reviewing).toBe(false);
      expect(useProcessingStore.getState().batch).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('stops asking for estimates when "Run as" changes', async () => {
    estimateFor = async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
      return json(estimateOf());
    };
    selectPasses([sceneIds(12)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (12)'));
    click(button('Review'));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30));
    });
    click(button('One job'));
    expect(useProcessingStore.getState().reviewing).toBe(false);
  });

  it('drops a batch review when the dataset changes', async () => {
    selectPasses([sceneIds(2)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (2)'));
    await review();
    expect(useProcessingStore.getState().batch).not.toBeNull();
    act(() => useAppStore.setState({ datasetId: 'cop-dem-glo-30' }));
    expect(useProcessingStore.getState().batch).toBeNull();
    expect(useProcessingStore.getState().runAs).toBe('one');
  });

  it('shows a part that could not be reached as a line of its own and starts the rest', async () => {
    estimateFor = (ids) => {
      if (ids[0] === 'S2') throw new TypeError('Failed to fetch');
      return json(estimateOf());
    };
    selectPasses([sceneIds(3)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (3)'));
    await review();
    const alerts = [...container.querySelectorAll('[role="alert"]')].map((a) => a.textContent);
    expect(alerts).toEqual(['S2: Failed to fetch']);
    expect(button('Start 2 of 3 jobs').disabled).toBe(false);
  });
});

describe('the buttons of a reviewed batch', () => {
  it('says that the server refused every job, with the count on the button', async () => {
    estimateFor = () => problem(422, 'no good');
    selectPasses([sceneIds(2)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (2)'));
    await review();
    const startButton = button('Start 0 of 2 jobs');
    expect(startButton.disabled).toBe(true);
    expect(startButton.title).toBe('The server refused every job');
  });

  it('takes no panel away from the user, however many jobs are started', async () => {
    selectPasses([sceneIds(3)]);
    await openPanel();
    await ndvi();
    click(button('One job per scene (3)'));
    await review();
    const docks: unknown[] = [];
    const unsubscribe = useAppStore.subscribe((s) => docks.push(s.dock));
    await start('Start 3 jobs');
    unsubscribe();
    expect(placed).toHaveLength(3);
    expect(docks).toEqual([]);
  });
});

describe('one dataset', () => {
  // The scenes of the results on screen were found under the open section; the
  // extra scenes of a layer entry under the dataset they were fetched for.
  function withExtraFrom(datasetId: string | null) {
    selectPasses([[scene('S1'), scene('S3')]]);
    const extra = scene('S2');
    useProcessingStore.setState({
      extraScenes: { datasetId, items: [extra], groups: [{ key: ['2026-07-01'], label: '2026-07-01', items: [extra] }] },
    });
    useAppStore.setState({ selectedIds: ['S1', 'S2', 'S3'] });
  }

  it('refuses a batch with a scene that was found under another dataset, with the reason, and sends nothing', async () => {
    withExtraFrom('cop-dem-glo-30');
    await openPanel();
    await ndvi();
    click(button('One job per scene (3)'));
    await review();
    expect(estimates).toHaveLength(0);
    expect(text()).toContain('The selection holds scenes of another dataset (S2); a job takes one dataset.');
    expect(button('Start 3 jobs').disabled).toBe(true);
  });

  it('refuses a single job with scenes of another open section, too', async () => {
    selectPasses([[scene('S1'), scene('S2')]]);
    useAppStore.setState({ openSectionId: 'cop-dem-glo-30' });
    await openPanel();
    await ndvi();
    await review();
    expect(estimates).toHaveLength(0);
    expect(text()).toContain('another dataset (S1, S2)');
  });

  it('takes scenes whose collection is not the id of the dataset when they were found under it', async () => {
    selectPasses([[scene('S1', NEAR, 'upstream-collection'), scene('S2', NEAR, 'other-upstream-name')]]);
    useAppStore.setState({ openSectionId: DATASET.id });
    await openPanel();
    await ndvi();
    click(button('One job per scene (2)'));
    await review();
    expect(estimates.map(idsOf)).toEqual([['S1'], ['S2']]);
    expect(text()).not.toContain('another dataset');
    expect(button('Start 2 jobs').disabled).toBe(false);
  });

  it('takes the extra scenes of a layer when they were fetched under the dataset of the order', async () => {
    withExtraFrom(DATASET.id);
    await openPanel();
    await ndvi();
    click(button('One job per scene (3)'));
    await review();
    expect(estimates.map(idsOf).sort()).toEqual([['S1'], ['S2'], ['S3']]);
  });
});

describe('"Run as" and the selection (Otto, 20.10.2026)', () => {
  it('goes back to one job as soon as the selection changes, and stays there', async () => {
    selectPasses([sceneIds(5)]);
    await openPanel();
    click(button('One job per scene (5)'));
    expect(useProcessingStore.getState().runAs).toBe('scene');
    act(() => useAppStore.setState({ selectedIds: ['S1', 'S2', 'S3', 'S4'] }));
    expect(useProcessingStore.getState().runAs).toBe('one');
    act(() => useAppStore.setState({ selectedIds: ['S1', 'S2', 'S3', 'S4', 'S5'] }));
    expect(button('One job').getAttribute('aria-pressed')).toBe('true');
    expect(button('One job per scene (5)').getAttribute('aria-pressed')).toBe('false');
  });

  it('goes back to one job when the scenes of the results change', async () => {
    selectPasses([sceneIds(3)]);
    await openPanel();
    click(button('One job per scene (3)'));
    const more = sceneIds(3);
    act(() => useAppStore.setState({ items: more, groups: [{ key: ['2026-07-01'], label: '2026-07-01', items: more }] }));
    expect(useProcessingStore.getState().runAs).toBe('one');
  });

  it('goes back to one job when the AOI changes under "AOI only", not under "Whole scene"', async () => {
    selectPasses([sceneIds(3)]);
    await openPanel();
    click(button('One job per scene (3)'));
    act(() => useAppStore.setState({ aoi: bboxToPolygon([10.1, 50.1, 10.2, 50.2]) }));
    expect(useProcessingStore.getState().runAs).toBe('scene');
    click(button('AOI only'));
    act(() => useAppStore.setState({ aoi: bboxToPolygon([10.3, 50.3, 10.4, 50.4]) }));
    expect(useProcessingStore.getState().runAs).toBe('one');
  });

  it('keeps the choice when something else changes', async () => {
    selectPasses([sceneIds(3)]);
    await openPanel();
    click(button('One job per scene (3)'));
    await ndvi();
    expect(useProcessingStore.getState().runAs).toBe('scene');
  });
});
