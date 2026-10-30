// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { browserDeps, canStream } from './originalsClient';
import { ZipError, type ZipCommand, type ZipJob, type ZipReply } from './originalsZip';

vi.mock('./originalsWorkerUrl', () => ({ workerUrl: '/assets/originalsWorker-abc.js' }));

const JOB: ZipJob = {
  zipName: 'S2_A.zip',
  texts: [{ name: 'ATTRIBUTION.txt', content: 'text' }],
  files: [{ name: 'S2_A_red.tif', url: 'https://data.test/red.tif', size: 10 }],
};

// A stand-in for the service worker: remembers the job and the port it came with, and lets a test answer on it.
class FakeWorker {
  jobs: { command: ZipCommand; port: MessagePort }[] = [];
  received: ZipCommand[] = [];
  postMessage(command: ZipCommand, transfer: MessagePort[]) {
    const port = transfer[0];
    this.jobs.push({ command, port });
    port.onmessage = (event: MessageEvent<ZipCommand>) => this.received.push(event.data);
    port.start?.();
  }
  reply(reply: ZipReply) {
    this.jobs[0].port.postMessage(reply);
  }
}

let worker: FakeWorker;
let register: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] });
  worker = new FakeWorker();
  register = vi.fn(async () => ({ active: worker, installing: null, waiting: null }));
  Object.defineProperty(navigator, 'serviceWorker', { value: { register }, configurable: true });
  Object.defineProperty(globalThis, 'isSecureContext', { value: true, configurable: true });
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = '';
  Reflect.deleteProperty(navigator, 'serviceWorker');
});

describe('can the page stream a ZIP', () => {
  it('yes with a service worker in a secure context', () => {
    expect(canStream()).toBe(true);
  });
  it('no without service workers, and no outside a secure context', () => {
    Reflect.deleteProperty(navigator, 'serviceWorker');
    expect(canStream()).toBe(false);
    Object.defineProperty(navigator, 'serviceWorker', { value: { register }, configurable: true });
    Object.defineProperty(globalThis, 'isSecureContext', { value: false, configurable: true });
    expect(canStream()).toBe(false);
    expect(browserDeps().deps.zip).toBeNull();
  });
});

describe('the files the page saves and hands over', () => {
  let revoked: string[];
  let clicked: HTMLAnchorElement[];
  beforeEach(() => {
    revoked = [];
    clicked = [];
    let n = 0;
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: () => `blob:file-${(n += 1)}`, revokeObjectURL: (href: string) => revoked.push(href) }));
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this);
    });
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('saveBlob clicks a link that names the file, and leaves nothing in the page', () => {
    const { deps } = browserDeps();
    deps.saveBlob('S2_A_red.tif', new Blob(['x']));
    expect(clicked).toHaveLength(1);
    expect(clicked[0].download).toBe('S2_A_red.tif');
    expect(clicked[0].href).toBe('blob:file-1');
    expect(document.querySelector('a')).toBeNull();
  });

  it('a saved file is freed 30 seconds later, not sooner', () => {
    const { deps } = browserDeps();
    deps.saveBlob('a', new Blob(['x']));
    vi.advanceTimersByTime(29_000);
    expect(revoked).toEqual([]);
    vi.advanceTimersByTime(1_500);
    expect(revoked).toEqual(['blob:file-1']);
  });

  it('dispose frees what is not yet freed, once, and removes the frames', () => {
    const { deps, dispose } = browserDeps();
    deps.saveBlob('a', new Blob(['x']));
    deps.saveBlob('b', new Blob(['y']));
    deps.navigate('https://data.test/red.tif');
    expect(document.querySelectorAll('iframe')).toHaveLength(1);
    dispose();
    expect(revoked.sort()).toEqual(['blob:file-1', 'blob:file-2']);
    expect(document.querySelector('iframe')).toBeNull();
    vi.advanceTimersByTime(60_000);
    expect(revoked).toHaveLength(2);
  });

  it('navigate adds a hidden frame at the address of the file', () => {
    const { deps } = browserDeps();
    deps.navigate('https://data.test/red.tif');
    const frame = document.querySelector('iframe');
    expect(frame?.hidden).toBe(true);
    expect(frame?.getAttribute('src')).toBe('https://data.test/red.tif');
  });
});

describe('the ZIP through the service worker', () => {
  async function started(signal = new AbortController().signal) {
    const { deps, dispose } = browserDeps();
    const loaded: number[] = [];
    const run = deps.zip!.run(JOB, (n) => loaded.push(n), signal);
    const outcome = run.then(() => 'done', (error: ZipError) => `error ${error.code}${error.status ? ` ${error.status}` : ''}`);
    await vi.waitFor(() => expect(worker.jobs).toHaveLength(1));
    return { run, outcome, loaded, dispose };
  }

  it('registers the worker as a module below the folder it is served from', async () => {
    await started();
    expect(register).toHaveBeenCalledWith(expect.stringMatching(/\/assets\/originalsWorker-abc\.js$/), { type: 'module', scope: '/assets/' });
  });

  it('hands over the job with a port, and opens the download only once the worker has it', async () => {
    await started();
    const sent = worker.jobs[0].command;
    expect(sent).toMatchObject({ type: 'job', job: JOB });
    expect(document.querySelector('iframe')).toBeNull();
    worker.reply({ type: 'ready' });
    await vi.waitFor(() => expect(document.querySelector('iframe')).not.toBeNull());
    const id = (sent as { id: string }).id;
    expect(document.querySelector('iframe')?.getAttribute('src')).toBe(`/assets/__originals/${id}`);
    expect(id).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('tells the progress, and ends when the worker says so', async () => {
    const { outcome, loaded } = await started();
    worker.reply({ type: 'ready' });
    worker.reply({ type: 'started' });
    worker.reply({ type: 'progress', loaded: 4 });
    worker.reply({ type: 'progress', loaded: 10 });
    worker.reply({ type: 'done' });
    expect(await outcome).toBe('done');
    expect(loaded).toEqual([4, 10]);
  });

  it('a failure the worker names comes out as that failure, with the status', async () => {
    const { outcome } = await started();
    worker.reply({ type: 'ready' });
    worker.reply({ type: 'error', code: 'http', status: 503 });
    expect(await outcome).toBe('error http 503');
  });

  it('tells the worker every ten seconds that the download is still wanted, and stops when it ends', async () => {
    const { outcome } = await started();
    worker.reply({ type: 'ready' });
    worker.reply({ type: 'started' });
    await vi.advanceTimersByTimeAsync(25_000);
    await vi.waitFor(() => expect(worker.received.filter((c) => c.type === 'ping')).toHaveLength(2));
    worker.reply({ type: 'done' });
    await outcome;
    const before = worker.received.length;
    await vi.advanceTimersByTimeAsync(60_000);
    expect(worker.received).toHaveLength(before);
  });

  it('a worker that never asks for the download is unavailable after ten seconds, and is told to drop the job', async () => {
    const { outcome } = await started();
    worker.reply({ type: 'ready' });
    await vi.waitFor(() => expect(document.querySelector('iframe')).not.toBeNull());
    await vi.advanceTimersByTimeAsync(10_500);
    expect(await outcome).toBe('error unavailable');
    await vi.waitFor(() => expect(worker.received.some((c) => c.type === 'cancel')).toBe(true));
  });

  it('a worker that says it has started is not given up on', async () => {
    const { outcome } = await started();
    worker.reply({ type: 'ready' });
    worker.reply({ type: 'started' });
    await vi.advanceTimersByTimeAsync(60_000);
    worker.reply({ type: 'done' });
    expect(await outcome).toBe('done');
  });

  it('a stop from the page tells the worker to cancel and ends as cancelled', async () => {
    const abort = new AbortController();
    const { outcome } = await started(abort.signal);
    worker.reply({ type: 'ready' });
    abort.abort();
    expect(await outcome).toBe('error cancelled');
    await vi.waitFor(() => expect(worker.received.some((c) => c.type === 'cancel')).toBe(true));
  });

  it('a page whose worker cannot be registered finds no worker: unavailable, and no frame', async () => {
    register.mockRejectedValue(new Error('blocked'));
    const { deps } = browserDeps();
    await expect(deps.zip!.run(JOB, () => undefined, new AbortController().signal)).rejects.toMatchObject({ code: 'unavailable' });
    expect(document.querySelector('iframe')).toBeNull();
  });

  it('waits for a worker that is still installing, and gives up when it never becomes active', async () => {
    let listener: () => void = () => undefined;
    const installing = { state: 'installing', addEventListener: (_: string, fn: () => void) => (listener = fn) };
    register.mockResolvedValue({ active: null, installing, waiting: null });
    const { deps } = browserDeps();
    const waiting = deps.zip!.run(JOB, () => undefined, new AbortController().signal);
    const outcome = waiting.then(() => 'done', (error: ZipError) => error.code);
    await vi.advanceTimersByTimeAsync(10_500);
    expect(await outcome).toBe('unavailable');
    expect(listener).toBeTypeOf('function');
  });
});

