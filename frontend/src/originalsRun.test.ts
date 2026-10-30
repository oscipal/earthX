// @vitest-environment node
import { describe, expect, it, vi } from 'vitest';

import { collection, HOST, item } from './fixtures/originalsScene';
import { MAX_FILE_BYTES, scenesOf, type Way } from './originals';
import { failureText, runOriginals, type RunDeps, type SceneState, type ZipChannel } from './originalsRun';
import { ZipError, type ZipJob } from './originalsZip';
import type { Collection, StacItem } from './types';

const NOW = new Date('2026-10-30T12:00:00Z');

interface Harness {
  deps: RunDeps;
  states: Map<number, SceneState[]>;
  ways: { way: Way; reason: string | null }[];
  jobs: ZipJob[];
  saved: { name: string; text: Promise<string> }[];
  navigated: string[];
  requests: { method: string; file: string }[];
  fetchFn: ReturnType<typeof vi.fn>;
}

interface Options {
  zip?: ZipChannel | null;
  // What the source answers to a request for a file name: a status, or a length for the HEAD; `throw` for a TypeError.
  answer?: (method: string, file: string) => number | 'throw' | { length: number | null } | undefined;
}

function harness(options: Options = {}): Harness {
  const requests: Harness['requests'] = [];
  const jobs: ZipJob[] = [];
  const fetchFn = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    const file = url.split('/').slice(-2).join('/');
    requests.push({ method, file });
    const answer = options.answer?.(method, file);
    if (answer === 'throw') throw new TypeError('Failed to fetch');
    if (typeof answer === 'number') return new Response('no', { status: answer });
    const headers: Record<string, string> = {};
    const length = answer && 'length' in answer ? answer.length : 1000;
    if (length !== null) headers['content-length'] = String(length);
    return method === 'HEAD'
      ? new Response(null, { headers })
      : new Response(new Uint8Array(length ?? 1000).fill(3), { headers: { ...headers, 'content-type': 'image/tiff' } });
  });
  const zip: ZipChannel | null =
    options.zip === undefined
      ? {
          run: async (job, onLoaded) => {
            jobs.push(job);
            onLoaded(job.files.reduce((sum, file) => sum + file.size, 0));
          },
        }
      : options.zip;
  const saved: Harness['saved'] = [];
  const navigated: string[] = [];
  const deps: RunDeps = {
    fetch: fetchFn as unknown as typeof fetch,
    zip,
    saveBlob: (name, blob) => saved.push({ name, text: blob.text() }),
    navigate: (href) => navigated.push(href),
    now: () => NOW,
  };
  return { deps, states: new Map(), ways: [], jobs, saved, navigated, requests, fetchFn };
}

function run(h: Harness, args: { collection?: Collection; items?: StacItem[]; only?: number[]; years?: string | null; signal?: AbortSignal } = {}) {
  const c = args.collection ?? collection();
  const items = args.items ?? [item('A'), item('B')];
  const scenes = scenesOf(c, [{ label: 'P', items }]);
  return {
    scenes,
    done: runOriginals({
      collection: c,
      datasetId: 'sentinel-2-c1-l2a',
      scenes,
      only: args.only,
      years: args.years === undefined ? '2026' : args.years,
      deps: h.deps,
      signal: args.signal ?? new AbortController().signal,
      onScene: (index, state) => h.states.set(index, [...(h.states.get(index) ?? []), state]),
      onWay: (way, reason) => h.ways.push({ way, reason }),
    }),
  };
}

const last = (h: Harness, index: number) => h.states.get(index)?.at(-1);

describe('one ZIP per scene', () => {
  it('goes scene by scene, each with the names and the sizes of the scene and its own ATTRIBUTION.txt', async () => {
    const h = harness();
    await run(h).done;
    expect(h.ways).toEqual([{ way: 'zip', reason: null }]);
    expect(h.jobs.map((job) => job.zipName)).toEqual(['A.zip', 'B.zip']);
    expect(h.jobs[0].files).toHaveLength(21);
    expect(h.jobs[0].files[0]).toEqual({ name: 'A_coastal.tif', url: `https://${HOST}/A/coastal.tif`, size: 1000 });
    const attribution = h.jobs[0].texts.find((t) => t.name === 'ATTRIBUTION.txt')!.content;
    expect(attribution).toContain('Copernicus Sentinel data 2026');
    expect(attribution).toContain('Scene: A');
    expect(attribution).not.toContain('Scene: A, B');
    expect(h.jobs[0].texts.map((t) => t.name)).toEqual(['ATTRIBUTION.txt', 'item.json']);
    expect(h.saved).toEqual([]);
    expect(h.navigated).toEqual([]);
  });

  it('the rows go from waiting to running to done, and the second scene waits for the first', async () => {
    const h = harness();
    await run(h).done;
    expect(h.states.get(0)?.map((s) => s.status)).toEqual(['waiting', 'running', 'running', 'done']);
    expect(last(h, 1)).toEqual({ status: 'done' });
    expect(h.states.get(0)?.at(-2)).toEqual({ status: 'running', loaded: 19_500, total: 19_500 });
  });

  it('asks the source once with HEAD that the page may read it, and nothing more where file:size is known', async () => {
    const h = harness();
    await run(h).done;
    expect(h.requests).toEqual([{ method: 'HEAD', file: 'A/coastal.tif' }]);
  });

  it('asks for the size of a file that has none, with HEAD, and a source that gives none fails that scene alone', async () => {
    const noSize = item('A', { red: { href: `https://${HOST}/A/red.tif` } });
    const h = harness({ answer: (method, file) => (method === 'HEAD' && file === 'A/red.tif' ? { length: null } : undefined) });
    await run(h, { items: [noSize, item('B')] }).done;
    expect(last(h, 0)).toEqual({ status: 'failed', reason: 'The source does not tell how large a file is.' });
    expect(last(h, 1)).toEqual({ status: 'done' });
    expect(h.jobs.map((job) => job.zipName)).toEqual(['B.zip']);
  });

  it('a size taken from HEAD goes into the job', async () => {
    const noSize = item('A', { red: { href: `https://${HOST}/A/red.tif` } });
    const h = harness({ answer: (method, file) => (method === 'HEAD' && file === 'A/red.tif' ? { length: 4321 } : undefined) });
    await run(h, { items: [noSize] }).done;
    expect(h.jobs[0].files.find((file) => file.name === 'A_red.tif')?.size).toBe(4321);
  });

  it('a scene that fails does not stop the next one, and the reason names no address', async () => {
    const h = harness();
    const original = h.deps.zip!.run;
    let count = 0;
    h.deps.zip = { run: async (job, onLoaded, signal) => (count++ === 0 ? Promise.reject(new ZipError('http', 403)) : original(job, onLoaded, signal)) };
    await run(h).done;
    expect(last(h, 0)).toEqual({ status: 'failed', reason: 'The source answered 403.' });
    expect(last(h, 1)).toEqual({ status: 'done' });
    expect(JSON.stringify([...h.states.values()])).not.toContain(HOST);
  });

  it('a scene without a direct link for any file fails with its own sentence; the others go on', async () => {
    const h = harness();
    const bare: StacItem = { id: 'C', properties: { datetime: '2026-07-02T00:00:00Z' }, assets: {} };
    await run(h, { items: [bare, item('B')] }).done;
    expect(last(h, 0)).toEqual({ status: 'failed', reason: 'The source gives no direct link for this scene.' });
    expect(last(h, 1)).toEqual({ status: 'done' });
  });
});

describe('where the page may not read the source', () => {
  it('a HEAD that fails like a missing CORS header sends every file to the browser, once, for the whole run', async () => {
    const h = harness({ answer: () => 'throw' });
    await run(h).done;
    expect(h.ways.map((w) => w.way)).toEqual(['zip', 'navigate']);
    expect(h.ways[1].reason).toContain('does not allow the page');
    expect(h.requests).toHaveLength(1);
    expect(h.jobs).toEqual([]);
    // The metadata files are not sent to the browser as downloads: it would show them instead of saving them.
    expect(h.navigated).toHaveLength(2 * 18);
    expect(h.navigated.every((href) => /\.tif$/.test(href))).toBe(true);
    expect(last(h, 0)).toEqual({ status: 'started' });
  });

  it('then ATTRIBUTION.txt comes once, named after the dataset, with the names the source gives', async () => {
    const h = harness({ answer: () => 'throw' });
    await run(h).done;
    expect(h.saved.map((file) => file.name)).toEqual(['sentinel-2-c1-l2a_ATTRIBUTION.txt']);
    const text = await h.saved[0].text;
    expect(text).toContain('Scenes: A, B');
    expect(text).toContain('red.tif (A, asset red)');
    expect(text).not.toContain('granule_metadata');
  });

  it('a dataset without CORS never asks the source at all', async () => {
    const h = harness();
    await run(h, { collection: collection({ 'earthx:access': { cors: false } }) }).done;
    expect(h.fetchFn).not.toHaveBeenCalled();
    expect(h.ways).toEqual([{ way: 'navigate', reason: null }]);
    expect(h.saved).toHaveLength(1);
    expect(h.navigated).toHaveLength(2 * 18);
  });

  it('a source that answers an error to the first HEAD is not a CORS matter: the ZIP goes on and fails there', async () => {
    const h = harness({ answer: (method) => (method === 'HEAD' ? 403 : undefined) });
    await run(h, { items: [item('A', { coastal: { href: `https://${HOST}/A/coastal.tif` } })] }).done;
    expect(h.ways.map((w) => w.way)).toEqual(['zip']);
    expect(last(h, 0)).toEqual({ status: 'failed', reason: 'The source answered 403.' });
  });
});

describe('where the browser cannot stream a ZIP', () => {
  it('saves ATTRIBUTION.txt, then every file under its name, then item.json, for each scene', async () => {
    const h = harness({ zip: null });
    await run(h, { items: [item('A', {}, ['red', 'nir'])] }).done;
    expect(h.ways).toEqual([{ way: 'files', reason: null }]);
    expect(h.saved.map((file) => file.name)).toEqual([
      'sentinel-2-c1-l2a_ATTRIBUTION.txt',
      'A_red.tif',
      'A_nir.tif',
      'A_granule_metadata.xml',
      'A_product_metadata.xml',
      'A_tileinfo_metadata.json',
      'A_item.json',
    ]);
    expect(JSON.parse(await h.saved.at(-1)!.text)).toMatchObject({ id: 'A' });
    expect(last(h, 0)).toEqual({ status: 'done' });
  });

  it('ATTRIBUTION.txt comes once for all scenes', async () => {
    const h = harness({ zip: null });
    await run(h, { items: [item('A', {}, ['red']), item('B', {}, ['red'])] }).done;
    expect(h.saved.filter((file) => file.name.endsWith('_ATTRIBUTION.txt'))).toHaveLength(1);
    expect(await h.saved[0].text).toContain('Scenes: A, B');
  });

  it(`a file over ${MAX_FILE_BYTES / 1024 / 1024} MB goes to the browser instead of through the page`, async () => {
    const big = item('A', { red: { href: `https://${HOST}/A/red.tif`, 'file:size': MAX_FILE_BYTES + 1 } }, ['red', 'nir']);
    const h = harness({ zip: null });
    await run(h, { items: [big] }).done;
    expect(h.navigated).toEqual([`https://${HOST}/A/red.tif`]);
    expect(h.saved.map((file) => file.name)).not.toContain('A_red.tif');
    expect(h.saved.map((file) => file.name)).toContain('A_nir.tif');
    expect(h.requests.filter((r) => r.method === 'GET' && r.file === 'A/red.tif')).toEqual([]);
  });

  it('a file the source refuses fails the scene, and the next scene goes on', async () => {
    const h = harness({ zip: null, answer: (method, file) => (method === 'GET' && file === 'A/red.tif' ? 404 : undefined) });
    await run(h, { items: [item('A', {}, ['red']), item('B', {}, ['red'])] }).done;
    expect(last(h, 0)).toEqual({ status: 'failed', reason: 'The source answered 404.' });
    expect(last(h, 1)).toEqual({ status: 'done' });
  });

  it('the page is told how far it is', async () => {
    // The source sends as many bytes as `file:size` says: 1000 for the band, 500 for each metadata file.
    const h = harness({ zip: null, answer: (method, file) => (method === 'GET' ? { length: file.endsWith('red.tif') ? 1000 : 500 } : undefined) });
    await run(h, { items: [item('A', {}, ['red'])] }).done;
    const running = h.states.get(0)!.filter((state): state is Extract<SceneState, { status: 'running' }> => state.status === 'running');
    expect(running.at(-1)).toEqual({ status: 'running', loaded: 2500, total: 2500 });
  });
});

describe('when the service worker does not answer', () => {
  it('the files come one by one, from this scene on, and the page says why', async () => {
    const h = harness();
    h.deps.zip = { run: async () => Promise.reject(new ZipError('unavailable')) };
    await run(h, { items: [item('A', {}, ['red']), item('B', {}, ['red'])] }).done;
    expect(h.ways.map((w) => w.way)).toEqual(['zip', 'files']);
    expect(h.ways[1].reason).toContain('could not start the ZIP');
    expect(h.saved.map((file) => file.name)).toContain('A_red.tif');
    expect(h.saved.map((file) => file.name)).toContain('B_red.tif');
    expect(last(h, 0)).toEqual({ status: 'done' });
    expect(last(h, 1)).toEqual({ status: 'done' });
  });
});

describe('stopping and trying again', () => {
  it('a stop during the first scene ends it and every scene after it as cancelled, and starts nothing more', async () => {
    const abort = new AbortController();
    const h = harness();
    h.deps.zip = {
      run: async (job, _onLoaded, signal) => {
        h.jobs.push(job);
        abort.abort();
        if (signal.aborted) throw new ZipError('cancelled');
      },
    };
    await run(h, { signal: abort.signal, items: [item('A'), item('B'), item('C')] }).done;
    expect(h.jobs.map((job) => job.zipName)).toEqual(['A.zip']);
    expect([0, 1, 2].map((index) => last(h, index)?.status)).toEqual(['cancelled', 'cancelled', 'cancelled']);
  });

  it('a stop before the start cancels everything and asks the source nothing', async () => {
    const abort = new AbortController();
    abort.abort();
    const h = harness({ answer: () => 'throw' });
    await run(h, { signal: abort.signal }).done;
    expect([0, 1].map((index) => last(h, index)?.status)).toEqual(['cancelled', 'cancelled']);
    expect(h.ways.map((w) => w.way)).toEqual(['zip']);
    expect(h.navigated).toEqual([]);
  });

  it('"Retry failed" runs only the scenes it is given and touches no other row', async () => {
    const h = harness();
    await run(h, { only: [1] }).done;
    expect(h.jobs.map((job) => job.zipName)).toEqual(['B.zip']);
    expect([...h.states.keys()]).toEqual([1]);
  });
});

describe('a scene without a date', () => {
  it('stops the whole run before anything is asked or downloaded, and says why on every row', async () => {
    const undated: StacItem = { ...item('A'), properties: {} };
    const h = harness();
    await run(h, { items: [undated, item('B')], years: null }).done;
    expect(h.fetchFn).not.toHaveBeenCalled();
    expect(h.jobs).toEqual([]);
    expect(h.ways).toEqual([]);
    expect(last(h, 0)).toMatchObject({ status: 'failed', reason: expect.stringContaining('no acquisition date') });
    expect(last(h, 1)).toMatchObject({ status: 'failed' });
  });

  it('is no matter for a dataset whose attribution names no year', async () => {
    const fixed = collection();
    fixed['earthx:license_flags'] = { ...fixed['earthx:license_flags']!, attribution_unmodified: 'Contains Copernicus data', attribution_modified: null };
    const h = harness();
    await run(h, { collection: fixed, years: null }).done;
    expect(last(h, 0)).toEqual({ status: 'done' });
  });
});

describe('failure texts', () => {
  it.each([
    [new ZipError('http', 503), 'The source answered 503.'],
    [new ZipError('size'), 'A file is not as long as the source announced.'],
    [new ZipError('network'), 'The connection to the source failed.'],
    [new ZipError('cancelled'), 'The download was cancelled in your browser.'],
    [new TypeError('Failed to fetch https://secret.test/x'), 'The connection to the source failed.'],
    [new Error('https://secret.test/x'), 'The download failed.'],
  ])('%#: a plain sentence that carries nothing of the error', (error, text) => {
    expect(failureText(error)).toBe(text);
  });
});
