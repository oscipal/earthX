// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ZipCommand, ZipJob, ZipReply } from './originalsZip';

// The worker registers its handlers on `self` when it is loaded: here `self` is a stand-in that keeps them.
type Handler = (event: unknown) => void;
const handlers: Record<string, Handler> = {};

const JOB: ZipJob = {
  zipName: 'S2_A.zip',
  texts: [{ name: 'ATTRIBUTION.txt', content: 'text' }],
  files: [{ name: 'S2_A_red.tif', url: 'https://data.test/red.tif', size: 4 }],
};
const ID = 'b3b0c442-98fc-4c1a-9c1a-000000000001';

function port() {
  const sent: ZipReply[] = [];
  return { sent, closed: false, onmessage: null as ((event: { data: ZipCommand }) => void) | null, postMessage: (reply: ZipReply) => sent.push(reply), close() { this.closed = true; } };
}

function fetchEvent(url: string) {
  let answer: Response | Promise<Response> | undefined;
  return { request: { url }, respondWith: (response: Response | Promise<Response>) => (answer = response), get answer() { return answer; } };
}

const ORIGIN = 'https://app.test';
const sendJob = (id = ID, p = port()) => {
  handlers.message({ data: { type: 'job', id, job: JOB } satisfies ZipCommand, ports: [p] });
  return p;
};

beforeEach(async () => {
  vi.resetModules();
  for (const key of Object.keys(handlers)) delete handlers[key];
  vi.stubGlobal('self', { location: { origin: ORIGIN }, addEventListener: (type: string, fn: Handler) => (handlers[type] = fn), skipWaiting: async () => undefined, clients: { claim: async () => undefined } });
  vi.stubGlobal('fetch', async () => new Response(new Uint8Array(4).fill(5), { headers: { 'content-length': '4' } }));
  await import('./originalsWorker');
});

afterEach(() => vi.unstubAllGlobals());

describe('the service worker of the download', () => {
  it('takes over at once: it skips waiting and claims the pages', async () => {
    const skip = vi.fn(async () => undefined);
    vi.stubGlobal('self', { location: { origin: ORIGIN }, addEventListener: (type: string, fn: Handler) => (handlers[type] = fn), skipWaiting: skip, clients: { claim: async () => undefined } });
    vi.resetModules();
    await import('./originalsWorker');
    handlers.install({});
    expect(skip).toHaveBeenCalled();
    const waits: Promise<unknown>[] = [];
    handlers.activate({ waitUntil: (p: Promise<unknown>) => waits.push(p) });
    expect(waits).toHaveLength(1);
  });

  it('answers a job with "ready" over the port it came with', () => {
    expect(sendJob().sent).toEqual([{ type: 'ready' }]);
  });

  it('ignores a message that is no job, a ping included, and a job without a port', () => {
    expect(() => handlers.message({ data: { type: 'ping' }, ports: [] })).not.toThrow();
    expect(() => handlers.message({ data: { type: 'job', id: ID, job: JOB }, ports: [] })).not.toThrow();
    const event = fetchEvent(`${ORIGIN}/assets/__originals/${ID}`);
    handlers.fetch(event);
    expect(event.answer).toBeDefined();
  });

  it('answers the request of the download with the ZIP, and tells "started", progress and the end', async () => {
    const p = sendJob();
    const event = fetchEvent(`${ORIGIN}/assets/__originals/${ID}`);
    handlers.fetch(event);
    const response = (await event.answer) as Response;
    expect(response.headers.get('content-disposition')).toBe('attachment; filename="S2_A.zip"');
    expect(response.status).toBe(200);
    await response.arrayBuffer();
    const types = p.sent.map((reply) => reply.type);
    expect(types[0]).toBe('ready');
    expect(types[1]).toBe('started');
    expect(types.at(-1)).toBe('done');
    expect(p.closed).toBe(true);
  });

  it('uses a job once: the same request again finds nothing', async () => {
    sendJob();
    handlers.fetch(fetchEvent(`${ORIGIN}/assets/__originals/${ID}`));
    const again = fetchEvent(`${ORIGIN}/assets/__originals/${ID}`);
    handlers.fetch(again);
    expect(((await again.answer) as Response).status).toBe(404);
  });

  it('a request for an unknown id is a plain 404 that is not cached', async () => {
    const event = fetchEvent(`${ORIGIN}/assets/__originals/b3b0c442-98fc-4c1a-9c1a-0000000000ff`);
    handlers.fetch(event);
    const response = (await event.answer) as Response;
    expect(response.status).toBe(404);
    expect(response.headers.get('cache-control')).toBe('no-store');
  });

  it('lets every other request go its way: another path, a malformed id, another origin', () => {
    for (const url of [`${ORIGIN}/assets/index.js`, `${ORIGIN}/assets/__originals/`, `${ORIGIN}/assets/__originals/short`, `${ORIGIN}/assets/__originals/${ID}/more`, `https://elsewhere.test/assets/__originals/${ID}`]) {
      sendJob();
      const event = fetchEvent(url);
      handlers.fetch(event);
      expect(event.answer, url).toBeUndefined();
    }
  });

  it('a job cancelled before the browser asks is dropped: the late request finds nothing', async () => {
    const p = sendJob();
    p.onmessage?.({ data: { type: 'cancel' } });
    const event = fetchEvent(`${ORIGIN}/assets/__originals/${ID}`);
    handlers.fetch(event);
    expect(((await event.answer) as Response).status).toBe(404);
  });

  it('a cancel during the download stops reading the source and tells it as cancelled', async () => {
    let signal: AbortSignal | undefined;
    vi.stubGlobal('fetch', (_url: string, init?: RequestInit) => {
      signal = init?.signal ?? undefined;
      return new Promise<Response>((_resolve, reject) => init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError'))));
    });
    const p = sendJob();
    const event = fetchEvent(`${ORIGIN}/assets/__originals/${ID}`);
    handlers.fetch(event);
    const reading = ((await event.answer) as Response).arrayBuffer().catch(() => 'broken');
    await new Promise((resolve) => setTimeout(resolve, 10));
    p.onmessage?.({ data: { type: 'cancel' } });
    expect(await reading).toBe('broken');
    expect(signal?.aborted).toBe(true);
    expect(p.sent.at(-1)).toEqual({ type: 'error', code: 'cancelled', status: undefined });
  });

  it('keeps nothing in the log', async () => {
    const log = vi.spyOn(console, 'log');
    const error = vi.spyOn(console, 'error');
    sendJob();
    const event = fetchEvent(`${ORIGIN}/assets/__originals/${ID}`);
    handlers.fetch(event);
    await ((await event.answer) as Response).arrayBuffer();
    expect(log).not.toHaveBeenCalled();
    expect(error).not.toHaveBeenCalled();
  });
});
