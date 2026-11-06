// @vitest-environment jsdom
//
// Whole scenes in one file per resolution or one multi-band file (NM4-75): the order, the estimate before it, and the job that is placed,
// waited for and downloaded with nothing in the list of jobs. `fetch` answers the job API.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { downloadSceneJob, estimateSceneJob, resamplingOfOrder, sceneJobOrder } from './downloadJob';
import type { Order } from './processing';
import { useProcessingStore } from './processingStore';
import type { StacItem } from './types';

const JOB = 'AAAAAAAAAAAAAAAAAAAAAA';
const item = (id: string): StacItem => ({ id, properties: {}, assets: {} });
const ESTIMATE = { estimate: { size: 3_400_000_000, duration: 'PT95S', outputPixels: 1, inputPixels: 1, inputBytes: 1, assets: 3, units: 2 }, skippedItems: [] };
const RESAMPLING = {
  grid: { resolution: 10, crs: 'EPSG:32632' },
  method: 'nearest',
  bands: [{ band: 'B05', resolution: 20, crs: 'EPSG:32632' }],
  scenes: { count: 1, of: 3, crs: 'EPSG:32632' },
};

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const status = (state: string, progress = 0, message = '') => ({ jobID: JOB, status: state, progress, message, expires: '2026-12-01T00:00:00Z' });

let calls: Array<{ method: string; url: string; body?: { inputs: { recipe: Order; aoiProvenance?: unknown } } }>;
let estimate: { status: number; body: unknown };
let states: ReturnType<typeof status>[];

beforeEach(() => {
  calls = [];
  estimate = { status: 200, body: ESTIMATE };
  states = [status('running', 40), status('successful', 100)];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      calls.push({ method, url, ...(init?.body ? { body: JSON.parse(String(init.body)) } : {}) });
      if (method === 'POST' && url === '/processing/processes/recipe/estimate') return json(estimate.body, estimate.status);
      if (method === 'POST' && url === '/processing/processes/recipe/execution') return json(status('accepted'));
      if (method === 'GET' && url.endsWith(`/jobs/${JOB}`)) return json(states.length > 1 ? states.shift()! : states[0]);
      if (method === 'DELETE') return json(status('dismissed'));
      return json({ detail: 'not found' }, 404);
    }),
  );
  useProcessingStore.setState({ jobs: [] });
});

afterEach(() => vi.unstubAllGlobals());

const passes = [
  { label: 'one', items: [item('S1'), item('S2')] },
  { label: 'two', items: [item('S3')] },
  { label: 'empty', items: [] },
];

describe('the order', () => {
  it('names the passes as groups, the ticked assets and the layout, and no AOI', () => {
    const order = sceneJobOrder({ datasetId: 'd', passes, assets: ['b1', 'b2'], layout: { form: 'multi_band', resolution_m: 20 } })!;
    expect(order.inputs).toEqual([{ name: 'input', dataset: 'd', groups: [['S1', 'S2'], ['S3']], assets: ['b1', 'b2'] }]);
    expect(order).not.toHaveProperty('aoi');
    expect(order.output).toMatchObject({ kind: 'crop', resolution_factor: 1, layout: { form: 'multi_band', resolution_m: 20 } });
  });

  it('carries no resolution for one file per resolution', () => {
    const order = sceneJobOrder({ datasetId: 'd', passes, assets: ['b1'], layout: { form: 'per_resolution' } })!;
    expect(order.output).toMatchObject({ layout: { form: 'per_resolution' } });
    expect(JSON.stringify(order)).not.toContain('resolution_m');
  });

  it('is none where there is no scene or no asset', () => {
    expect(sceneJobOrder({ datasetId: 'd', passes: [passes[2]], assets: ['b1'], layout: { form: 'per_resolution' } })).toBeNull();
    expect(sceneJobOrder({ datasetId: 'd', passes, assets: [], layout: { form: 'per_resolution' } })).toBeNull();
  });
});

describe('the estimate', () => {
  const order = sceneJobOrder({ datasetId: 'd', passes, assets: ['b1'], layout: { form: 'per_resolution' } })!;

  it('says the size and the time in one line, and carries what is resampled for the warning', async () => {
    estimate = { status: 200, body: { ...ESTIMATE, resampling: RESAMPLING } };
    const note = await estimateSceneJob(order, new AbortController().signal);
    expect(note).toMatchObject({ state: 'ready', text: 'About 3.4 GB · about 95 s' });
    expect(note.state === 'ready' && note.parts).toHaveLength(1);
    expect(calls[0].body?.inputs.recipe.output).toMatchObject({ layout: { form: 'per_resolution' } });
  });

  it('has nothing to warn of where the platform resamples nothing', async () => {
    const note = await estimateSceneJob(order, new AbortController().signal);
    expect(note.state === 'ready' && note.parts).toEqual([]);
  });

  it('is blocked, with the reason, where the platform refuses the order', async () => {
    estimate = { status: 413, body: { detail: 'too big' } };
    expect(await estimateSceneJob(order, new AbortController().signal)).toMatchObject({ state: 'blocked', text: 'Too large for one job' });
    estimate = { status: 422, body: { detail: 'a band without a pixel size' } };
    expect(await estimateSceneJob(order, new AbortController().signal)).toMatchObject({ state: 'blocked', text: 'a band without a pixel size' });
  });

  it('the resampling alone is empty where the estimate cannot be had: the server has the last word', async () => {
    estimate = { status: 500, body: { detail: 'x' } };
    expect(await resamplingOfOrder(order, new AbortController().signal)).toEqual([]);
    estimate = { status: 200, body: { ...ESTIMATE, resampling: RESAMPLING } };
    expect(await resamplingOfOrder(order, new AbortController().signal)).toHaveLength(1);
  });
});

describe('the download', () => {
  const order = sceneJobOrder({ datasetId: 'd', passes, assets: ['b1'], layout: { form: 'multi_band', resolution_m: 10 } })!;
  const run = () => {
    const saved: string[] = [];
    const text: string[] = [];
    const controller = new AbortController();
    const done = downloadSceneJob({ order, signal: controller.signal, onStatus: (t) => text.push(t), save: (url) => saved.push(url), pollMs: 1 });
    return { done, saved, text, controller };
  };

  it('places the order as it is, with no AOI and no origin, waits, and starts the download of the result ZIP; no job enters the list', async () => {
    const { done, saved, text } = run();
    expect(await done).toBeNull();
    const placed = calls.filter((c) => c.url.endsWith('/execution'));
    expect(placed).toHaveLength(1);
    expect(placed[0].body?.inputs.recipe).toEqual(order);
    expect(placed[0].body?.inputs.recipe).not.toHaveProperty('aoi');
    expect(placed[0].body?.inputs).not.toHaveProperty('aoiProvenance');
    expect(saved).toEqual([`/processing/jobs/${JOB}/results/result.zip`]);
    expect(text[0]).toBe('Preparing…');
    expect(text.some((t) => /Preparing… 40%/.test(t))).toBe(true);
    expect(useProcessingStore.getState().jobs).toEqual([]);
  });

  it('tells why the job failed and downloads nothing', async () => {
    states = [status('failed', 10, 'A band could not be read.')];
    const { done, saved } = run();
    expect(await done).toEqual({ text: 'A band could not be read.', tip: 'A band could not be read.' });
    expect(saved).toEqual([]);
  });

  it('tells what the platform refuses', async () => {
    vi.mocked(fetch).mockImplementation(async (url, init) =>
      init?.method === 'POST' && String(url).endsWith('/execution') ? json({ detail: 'not allowed' }, 403) : json({}, 404),
    );
    const { done, saved } = run();
    expect(await done).toMatchObject({ text: 'not allowed' });
    expect(saved).toEqual([]);
  });

  it('dismisses the job it placed when it is stopped, and downloads nothing', async () => {
    states = [status('running', 40)];
    const { done, saved, controller } = run();
    await vi.waitFor(() => expect(calls.some((c) => c.method === 'GET' && c.url.endsWith(JOB))).toBe(true));
    controller.abort();
    expect(await done).toEqual({ text: 'Cancelled.', tip: 'Cancelled.' });
    await vi.waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true));
    expect(saved).toEqual([]);
  });
});
