import { afterEach, describe, expect, it, vi } from 'vitest';

import { HttpError } from './api';
import {
  canonicalJson,
  dismissJob,
  estimateOrder,
  eventsUrl,
  fetchJob,
  fetchProcess,
  fetchResults,
  isJobId,
  parseStatusInfo,
  placeJob,
  resultUrl,
  type Order,
} from './processing';

const JOB = 'AbCdEfGhIjKlMnOpQrSt_-';

const ORDER: Order = {
  recipe_version: 1,
  inputs: [{ name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['S2B_X']], assets: ['red', 'nir'] }],
  aoi: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]] },
  steps: [{ op: 'band_math', op_version: 1, params: { expression: '(nir - red) / (nir + red)' } }],
  output: { kind: 'raster', format: 'cog', dtype: 'float32' },
};

const ESTIMATE = {
  size: 1,
  duration: 'PT1.0S',
  outputPixels: 1,
  inputPixels: 1,
  inputBytes: 1,
  assets: 1,
  units: 0.1,
};

function status(extra: Record<string, unknown> = {}) {
  return {
    processID: 'recipe',
    type: 'process',
    jobID: JOB,
    status: 'running',
    message: 'The job is running.',
    created: '2026-10-10T10:00:00Z',
    progress: 40,
    expires: '2026-10-17T10:00:00Z',
    recipeID: 'r',
    links: [],
    ...extra,
  };
}

function respond(body: unknown, init: { status?: number; headers?: Record<string, string> } = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json', ...init.headers },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('canonicalJson', () => {
  it('sorts keys at every level and writes no whitespace', () => {
    expect(canonicalJson({ b: 1, a: { d: [2, { z: 1, y: 'x' }], c: true } })).toBe(
      '{"a":{"c":true,"d":[2,{"y":"x","z":1}]},"b":1}',
    );
  });

  it('gives two orders that differ only in key order one text', () => {
    const a = { steps: [{ params: { expression: 'a' }, op: 'band_math' }], aoi: null };
    const b = { aoi: null, steps: [{ op: 'band_math', params: { expression: 'a' } }] };
    expect(canonicalJson(a)).toBe(canonicalJson(b));
  });

  it('escapes the text as JSON does and leaves undefined members out', () => {
    expect(canonicalJson({ e: 'a "b" & ü', u: undefined })).toBe('{"e":"a \\"b\\" & ü"}');
  });
});

describe('parseStatusInfo', () => {
  it('reads a status document', () => {
    expect(parseStatusInfo(status(), JOB)).toMatchObject({ jobID: JOB, status: 'running', progress: 40 });
  });

  it.each([
    ['another job', { jobID: 'ZZZZZZZZZZZZZZZZZZZZZZ' }],
    ['a job id of the wrong form', { jobID: '../../etc' }],
    ['an unknown state', { status: 'paused' }],
    ['no progress', { progress: 'half' }],
    ['no expiry', { expires: 'soon' }],
  ])('drops %s', (_, extra) => {
    expect(parseStatusInfo(status(extra), JOB)).toBeNull();
  });

  it('drops what is no object', () => {
    expect(parseStatusInfo('running')).toBeNull();
    expect(parseStatusInfo(null)).toBeNull();
  });
});

describe('the job API client', () => {
  it('asks for the schema of one dataset', async () => {
    const fetchMock = vi.fn(async () => respond({ id: 'recipe', inputs: {} }));
    vi.stubGlobal('fetch', fetchMock);
    await fetchProcess('sentinel-2-c1-l2a');
    expect(fetchMock).toHaveBeenCalledWith('/processing/processes/recipe?dataset=sentinel-2-c1-l2a', {
      signal: undefined,
    });
  });

  it('wraps the order for the estimate as the execution does', async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => respond({ estimate: ESTIMATE, skippedItems: ['x'] }));
    vi.stubGlobal('fetch', fetchMock);
    const doc = await estimateOrder(ORDER);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/processing/processes/recipe/estimate');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual({ inputs: { recipe: ORDER } });
    expect(doc.skippedItems).toEqual(['x']);
  });

  it.each([
    ['an empty body', {}],
    ['a page of another shape', '<html>'],
    ['a number that is no number', { estimate: { ...ESTIMATE, units: 'many' } }],
    ['no duration', { estimate: { ...ESTIMATE, duration: 3 } }],
  ])('refuses an estimate with %s instead of showing it', async (_, body) => {
    vi.stubGlobal('fetch', vi.fn(async () => respond(body)));
    await expect(estimateOrder(ORDER)).rejects.toThrow('cannot read');
  });

  it('places a job and reads its status', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => respond(status({ status: 'accepted' }), { status: 201 })));
    await expect(placeJob(ORDER)).resolves.toMatchObject({ jobID: JOB, status: 'accepted' });
  });

  it('turns a problem document into an HttpError with title, detail and Retry-After', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        respond(
          { type: 'about:blank', title: 'Service Unavailable', status: 503, detail: 'the job queue is not reachable; try again' },
          { status: 503, headers: { 'Retry-After': '5' } },
        ),
      ),
    );
    const error = await placeJob(ORDER).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(HttpError);
    expect(error).toMatchObject({
      status: 503,
      title: 'Service Unavailable',
      detail: 'the job queue is not reachable; try again',
      retryAfter: '5',
    });
  });

  it('never puts a malformed job id into a URL', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    await expect(fetchJob('../processes')).rejects.toThrow('not a job id');
    await expect(dismissJob('a/b')).rejects.toThrow('not a job id');
    await expect(fetchResults('')).rejects.toThrow('not a job id');
    expect(() => eventsUrl('x?y')).toThrow('not a job id');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('refuses a status of another job', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => respond(status({ jobID: 'ZZZZZZZZZZZZZZZZZZZZZZ' }))));
    await expect(fetchJob(JOB)).rejects.toThrow('cannot read');
  });

  it('dismisses with DELETE', async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => respond(status({ status: 'dismissed' })));
    vi.stubGlobal('fetch', fetchMock);
    await dismissJob(JOB);
    expect(fetchMock.mock.calls[0]).toEqual([`/processing/jobs/${JOB}`, { method: 'DELETE' }]);
  });

  it('links a result file under the job', () => {
    expect(resultUrl(JOB, 'result.tif')).toBe(`/processing/jobs/${JOB}/results/result.tif`);
    expect(resultUrl(JOB, 'a b')).toBe(`/processing/jobs/${JOB}/results/a%20b`);
    expect(isJobId(JOB)).toBe(true);
  });
});
