// @vitest-environment jsdom
//
// "Download crop" of a layer that shows an index (NM4-14b, Otto 1.11.2026): the result a Processing job would give, with no
// Processing panel and no job in the list of jobs. `fetch` answers the process description and the job API.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { SENTINEL_2_PRESETS } from './fixtures/indexPresets';
import s2 from './fixtures/processes/sentinel-2-c1-l2a.json';
import { canDownloadLayer, decideDownloadOutcomeForLayer } from './download';
import { downloadIndexCrop, estimateIndexDownload, indexDownloadBlock, indexOfLayer, indexOrdersOf, TOO_LARGE_TIP } from './indexDownload';
import type { MapLayer } from './layers';
import { canonicalJson } from './processing';
import { processInfo as infoOf } from './processingOrder';
import { orderView, useProcessingStore } from './processingStore';
import { useAppStore } from './store';
import type { Collection, DownloadedInfo, StacItem } from './types';

const JOB_A = 'AAAAAAAAAAAAAAAAAAAAAA';
const JOB_B = 'BBBBBBBBBBBBBBBBBBBBBB';
const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10.1, 50.1], [10.2, 50.1], [10.2, 50.2], [10.1, 50.2], [10.1, 50.1]]] };

const collection = (presets: unknown[], tier = 'processing') =>
  ({
    id: 'sentinel-2-c1-l2a',
    title: 'Sentinel-2 L2A',
    'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
    'earthx:license_flags': { tier },
    'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
    'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
    'earthx:band_units': { red: 'reflectance', green: 'reflectance', blue: 'reflectance', nir: 'reflectance', visual: null },
    'earthx:index_presets': presets,
  }) as unknown as Collection;
const datasets = (presets: unknown[] = SENTINEL_2_PRESETS, tier = 'processing') => datasetsFrom([collection(presets, tier)]);

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const asset = () => ({ href: 'https://example.org/b.tif', type: COG, 'raster:bands': [{ data_type: 'uint16', nodata: 0 }] });
const scene = (id: string): StacItem => ({
  id,
  collection: 'sentinel-2-c1-l2a',
  bbox: [10, 50, 11, 51],
  properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 },
  assets: { red: asset(), green: asset(), blue: asset(), nir: asset(), visual: asset() },
});
const info = (id: string): DownloadedInfo => ({ datasetId: 'sentinel-2-c1-l2a', tileUrl: `/t/${id}/{z}/{x}/{y}`, bounds: [10, 50, 11, 51], asset: 'visual', minZoom: 8, maxZoom: 14 });

const layerOf = (over: Partial<MapLayer['restore']> = {}): MapLayer => ({
  id: 'L1',
  name: 'Sentinel-2 L2A · day',
  visible: true,
  opacity: 1,
  overlays: [],
  restore: {
    focusMode: true,
    downloaded: { S1: info('S1'), S2: info('S2') },
    appliedRender: { index: 'NDVI', colormapName: 'rdylgn', rescale: '-1,1' },
    activeGroupIndex: 0,
    selectedIds: ['S1', 'S2'],
    itemIds: ['S1', 'S2'],
    groupItemIds: [['S1', 'S2']],
    aoi: AOI,
    cropToAoi: true,
    datasetId: 'sentinel-2-c1-l2a',
    ...over,
  },
});

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const status = (jobID: string, state: string, progress = 0, message = '') => ({ jobID, status: state, progress, message, expires: '2026-12-01T00:00:00Z' });

let calls: Array<{ method: string; url: string; body?: unknown }>;
// What the job API answers: the ids handed out in turn, and the states each job goes through.
let ids: string[];
let states: Record<string, Array<ReturnType<typeof status>>>;
let refuse: string | null;
// What the estimate route answers: a document, or a refusal with its status.
let estimate: { status: number; body: unknown };
const ESTIMATE = { estimate: { size: 12_400_000, duration: 'PT9.2S', outputPixels: 1_000_000, inputPixels: 4_000_000, inputBytes: 8_000_000, assets: 2, units: 1 }, skippedItems: [] };

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  calls = [];
  ids = [JOB_A, JOB_B];
  states = { [JOB_A]: [status(JOB_A, 'running', 40), status(JOB_A, 'successful', 100)], [JOB_B]: [status(JOB_B, 'successful', 100)] };
  refuse = null;
  estimate = { status: 200, body: ESTIMATE };
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      calls.push({ method, url, ...(init?.body ? { body: JSON.parse(String(init.body)) } : {}) });
      if (url.startsWith('/processing/processes/recipe?')) return json(s2);
      if (method === 'POST' && url === '/processing/processes/recipe/estimate') return json(estimate.body, estimate.status);
      if (method === 'POST' && url === '/processing/processes/recipe/execution') {
        if (refuse) return json({ detail: refuse }, 422);
        return json(status(ids.shift()!, 'accepted'));
      }
      if (method === 'POST' && url === '/processing/bundles') return json({ href: '/processing/bundles/ZZZZZZZZZZZZZZZZZZZZZZ', expires: '2026-12-01T00:00:00Z' });
      const job = /\/processing\/jobs\/([A-Za-z0-9_-]{22})$/u.exec(url);
      if (job && method === 'GET') {
        const list = states[job[1]];
        return json(list.length > 1 ? list.shift()! : list[0]);
      }
      if (job && method === 'DELETE') return json(status(job[1], 'dismissed'));
      return json({ detail: 'not found' }, 404);
    }),
  );
  useProcessingStore.getState().resetDraft();
  useProcessingStore.setState({ jobs: [], descriptions: {}, open: false });
});

afterEach(() => vi.unstubAllGlobals());

const run = (layer = layerOf(), list = datasets()) => {
  const saved: string[] = [];
  const text: string[] = [];
  const controller = new AbortController();
  const done = downloadIndexCrop({ layer, datasets: list, signal: controller.signal, onStatus: (t) => text.push(t), save: (url) => saved.push(url), pollMs: 1 });
  return { done, saved, text, controller };
};

describe('which layers are downloaded as an index', () => {
  it('are those whose look names an index the dataset offers', () => {
    expect(indexOfLayer(layerOf(), datasets())?.name).toBe('NDVI');
    expect(indexOfLayer(layerOf({ appliedRender: { rescale: '0,3000' } }), datasets())).toBeNull();
    expect(indexOfLayer(layerOf({ appliedRender: { index: 'SAVI' } }), datasets())).toBeNull();
    expect(indexOfLayer(layerOf(), datasets([]))).toBeNull();
    expect(indexOfLayer(layerOf({ appliedRender: undefined as never }), datasets())).toBeNull();
  });

  it('go as an AOI crop; the button of the layer manager is for the crop and is open', () => {
    expect(indexDownloadBlock(layerOf(), datasets())).toBeNull();
    expect(decideDownloadOutcomeForLayer(layerOf(), datasets())).toBe('crop');
    expect(canDownloadLayer(layerOf(), datasets())).toBe(true);
  });

  it.each([
    ['whole scenes', { cropToAoi: false }, /whole scenes is computed by a job: start one in Processing/u],
    ['a layer with no AOI', { aoi: null }, /whole scenes is computed by a job/u],
    ['a layer that is not of a view', { focusMode: false }, /whole scenes is computed by a job/u],
  ])('are not downloaded for %s: locked, with what to do', (_, over, reason) => {
    const layer = layerOf(over as never);
    expect(indexDownloadBlock(layer, datasets())).toMatch(reason);
    expect(decideDownloadOutcomeForLayer(layer, datasets())).toBe('disabled');
    expect(canDownloadLayer(layer, datasets())).toBe(false);
  });

  it('are not downloaded where the licence does not allow processing', () => {
    const list = datasets(SENTINEL_2_PRESETS, 'display');
    expect(indexDownloadBlock(layerOf(), list)).toContain('does not allow processing');
    expect(canDownloadLayer(layerOf(), list)).toBe(false);
  });

  it('leave a layer without an index to the crop of the raw scenes, as before', () => {
    const raw = layerOf({ appliedRender: { rescale: '0,3000' } });
    expect(decideDownloadOutcomeForLayer(raw, datasets())).toBe('crop');
    expect(canDownloadLayer(raw, datasets())).toBe(true);
  });
});

describe('the order', () => {
  const list = datasets();
  const dataset = list[0];

  it('is the order the Processing panel builds for the same scenes, area and index: one recipe, one hash', async () => {
    // The panel: the same scenes and AOI, a Band math step with the expression and the name of the preset, that band as the output.
    const items = [scene('S1'), scene('S2')];
    useAppStore.setState({
      datasets: list, datasetId: dataset.id, items, groups: [{ key: ['d'], label: 'd', items }], activeGroupIndex: 0, selectedIds: ['S1', 'S2'], aoi: AOI,
      layers: [], focusMode: false, sections: [], openSectionId: null,
    });
    useProcessingStore.setState({ descriptions: { [dataset.id]: { state: 'ready', info: infoOf(s2 as never) } } });
    useProcessingStore.getState().openProcessing();
    useProcessingStore.getState().setArea('aoi');
    useProcessingStore.getState().addStep('band_math', 2);
    const [step] = useProcessingStore.getState().steps;
    useProcessingStore.getState().updateStep(step.key, 'expression', '(nir - red) / (nir + red)');
    useProcessingStore.getState().renameResult(step.key, 'NDVI');
    useProcessingStore.getState().setOutput(['NDVI']);
    const byHand = orderView(useAppStore.getState(), useProcessingStore.getState()).parts[0].order;
    expect(byHand).not.toBeNull();

    const made = indexOrdersOf({ layer: layerOf(), preset: indexOfLayer(layerOf(), list)!, dataset, info: infoOf(s2 as never) });
    expect('orders' in made && made.orders).toHaveLength(1);
    expect(canonicalJson((made as { orders: unknown[] }).orders[0])).toBe(canonicalJson(byHand));
  });

  it('has one order for each group of the layer', () => {
    const layer = layerOf({ itemIds: ['S1', 'S2', 'S3'], groupItemIds: [['S1', 'S2'], ['S3']], downloaded: { S1: info('S1'), S2: info('S2'), S3: info('S3') } });
    const made = indexOrdersOf({ layer, preset: indexOfLayer(layer, list)!, dataset, info: infoOf(s2 as never) });
    expect('orders' in made && made.orders.map((o) => o.inputs[0].groups)).toEqual([[['S1', 'S2']], [['S3']]]);
  });

  it('is an order for whole scenes, with no AOI, for a layer that is not a crop (the panel, not the download, takes it)', () => {
    const whole = layerOf({ cropToAoi: false, aoi: null });
    const made = indexOrdersOf({ layer: whole, preset: indexOfLayer(layerOf(), list)!, dataset, info: infoOf(s2 as never) });
    expect('orders' in made && made.orders[0].aoi).toBeUndefined();
    expect('orders' in made && made.orders[0].output).toMatchObject({ bands: ['NDVI'] });
  });

  it('says why it cannot be built, where it cannot', () => {
    const none = layerOf({ itemIds: [], groupItemIds: [] });
    expect(indexOrdersOf({ layer: none, preset: indexOfLayer(layerOf(), list)!, dataset, info: infoOf(s2 as never) })).toEqual({ problem: 'The layer has no scenes left.' });
  });
});

describe('the download', () => {
  it('places the order as a job, waits for it, and starts the download of its result ZIP; nothing enters the list of jobs', async () => {
    const { done, saved, text } = run();
    expect(await done).toBeNull();
    const placed = calls.filter((c) => c.method === 'POST' && c.url.endsWith('/execution'));
    expect(placed).toHaveLength(1);
    expect(JSON.stringify(placed[0].body)).toContain('"band_math"');
    expect(JSON.stringify(placed[0].body)).toContain('(nir - red) / (nir + red)');
    expect(saved).toEqual([`/processing/jobs/${JOB_A}/results/result.zip`]);
    expect(text[0]).toBe('Computing NDVI…');
    expect(text.some((t) => t.includes('40 %'))).toBe(true);
    // No Processing panel, no job in its list, nothing kept in the browser.
    expect(useProcessingStore.getState().jobs).toEqual([]);
    expect(useProcessingStore.getState().open).toBe(false);
    expect(JSON.stringify([...Object.entries(localStorage), ...Object.entries(sessionStorage)])).not.toContain(JOB_A);
    // The job is neither cancelled nor deleted: the file is fetched from it.
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false);
  });

  it('is one bundle for several groups: a job each, one ZIP', async () => {
    const layer = layerOf({ itemIds: ['S1', 'S2', 'S3'], groupItemIds: [['S1', 'S2'], ['S3']], downloaded: { S1: info('S1'), S2: info('S2'), S3: info('S3') } });
    const { done, saved } = run(layer);
    expect(await done).toBeNull();
    expect(calls.filter((c) => c.url.endsWith('/execution'))).toHaveLength(2);
    expect(calls.find((c) => c.url === '/processing/bundles')?.body).toEqual({ jobs: [JOB_A, JOB_B] });
    expect(saved).toEqual(['/processing/bundles/ZZZZZZZZZZZZZZZZZZZZZZ']);
  });

  it('says what the job said where it fails, and downloads nothing', async () => {
    states[JOB_A] = [status(JOB_A, 'failed', 10, 'The source failed')];
    const { done, saved } = run();
    expect(await done).toEqual({ text: 'The source failed', tip: 'The source failed' });
    expect(saved).toEqual([]);
  });

  it('says what the server said where it refuses the order', async () => {
    refuse = 'the AOI is outside the scenes';
    const { done, saved } = run();
    expect(await done).toEqual({ text: 'the AOI is outside the scenes', tip: 'the AOI is outside the scenes' });
    expect(saved).toEqual([]);
  });

  it('dismisses what it placed where one of several fails: no job is left that nobody sees', async () => {
    const layer = layerOf({ itemIds: ['S1', 'S2', 'S3'], groupItemIds: [['S1', 'S2'], ['S3']], downloaded: { S1: info('S1'), S2: info('S2'), S3: info('S3') } });
    states[JOB_A] = [status(JOB_A, 'failed', 10, 'The source failed')];
    states[JOB_B] = [status(JOB_B, 'running', 20)];
    const { done } = run(layer);
    expect(await done).toMatchObject({ text: 'The source failed' });
    await Promise.resolve();
    expect(calls.filter((c) => c.method === 'DELETE').map((c) => c.url)).toEqual([`/processing/jobs/${JOB_B}`]);
  });

  it('dismisses the job and downloads nothing when it is cancelled (the dialog is closed)', async () => {
    states[JOB_A] = [status(JOB_A, 'running', 10)];
    const { done, saved, controller } = run();
    await new Promise((resolve) => setTimeout(resolve, 20));
    controller.abort();
    expect(await done).toMatchObject({ text: 'Cancelled.' });
    expect(saved).toEqual([]);
    await Promise.resolve();
    expect(calls.some((c) => c.method === 'DELETE' && c.url.endsWith(JOB_A))).toBe(true);
  });

  it('refuses a layer that shows no index, a whole scene, or a licence below processing, before it asks the server anything', async () => {
    expect(await run(layerOf({ appliedRender: {} })).done).toMatchObject({ tip: 'This layer shows no index.' });
    expect((await run(layerOf({ cropToAoi: false })).done)?.tip).toContain('start one in Processing');
    expect((await run(layerOf(), datasets(SENTINEL_2_PRESETS, 'display')).done)?.tip).toContain('does not allow processing');
    expect(calls).toEqual([]);
  });
});

describe('the estimate and the limits (Otto, 1.11.2026)', () => {
  const ask = (layer = layerOf(), list = datasets()) => estimateIndexDownload({ layer, datasets: list, signal: new AbortController().signal });

  it('says what the job will cost, as "Review" asks it, with the same limits named in the tooltip', async () => {
    const note = await ask();
    expect(note).toMatchObject({ state: 'ready', text: 'About 12.4 MB · about 9 s' });
    expect((note as { tip: string }).tip).toContain('same limits as a job of Processing');
    expect(calls.filter((c) => c.url.endsWith('/estimate'))).toHaveLength(1);
    expect(JSON.stringify(calls.find((c) => c.url.endsWith('/estimate'))!.body)).toContain('"band_math"');
    expect(calls.some((c) => c.url.endsWith('/execution'))).toBe(false);
  });

  it('adds up the groups: one size, as many jobs', async () => {
    const layer = layerOf({ itemIds: ['S1', 'S2', 'S3'], groupItemIds: [['S1', 'S2'], ['S3']], downloaded: { S1: info('S1'), S2: info('S2'), S3: info('S3') } });
    expect(await ask(layer)).toMatchObject({ state: 'ready', text: 'About 24.8 MB · 2 jobs' });
  });

  it('stops with the reason where the job would be too large (413): a short line, the limit in the tooltip', async () => {
    estimate = { status: 413, body: { detail: 'the order would write more than 5 GB' } };
    expect(await ask()).toEqual({ state: 'blocked', text: 'Too large for one job', tip: TOO_LARGE_TIP });
  });

  it.each([
    [429, 'too many jobs are running; try again later', 'too many jobs are running; try again later'],
    [403, 'the licence does not allow processing', 'the licence does not allow processing'],
  ])('stops with the reason of any other refusal (%s)', async (status, detail, text) => {
    estimate = { status, body: { detail } };
    expect(await ask()).toEqual({ state: 'blocked', text, tip: detail });
  });

  it('keeps a long reason to one line and the whole of it in the tooltip', async () => {
    const detail = `${'x'.repeat(100)}: why`;
    estimate = { status: 422, body: { detail } };
    const note = await ask();
    expect(note).toMatchObject({ state: 'blocked', tip: detail });
    expect((note as { text: string }).text.length).toBeLessThanOrEqual(70);
  });

  it('is blocked before the server is asked for a whole scene, a layer without an index and a licence below processing', async () => {
    expect(await ask(layerOf({ cropToAoi: false }))).toMatchObject({ state: 'blocked', text: 'The index of whole scenes is computed by a job' });
    expect(await ask(layerOf({ appliedRender: {} }))).toMatchObject({ state: 'blocked' });
    expect(await ask(layerOf(), datasets(SENTINEL_2_PRESETS, 'display'))).toMatchObject({ state: 'blocked' });
    expect(calls.filter((c) => c.url.endsWith('/estimate'))).toEqual([]);
  });

  it('says what the server said where it refuses the job itself (a limit of the number of jobs): the dialog may try again', async () => {
    refuse = 'at most 4 jobs may run at a time';
    const { done } = run();
    expect(await done).toEqual({ text: 'at most 4 jobs may run at a time', tip: 'at most 4 jobs may run at a time' });
  });
});
