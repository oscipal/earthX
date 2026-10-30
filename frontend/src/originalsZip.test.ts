// @vitest-environment node
import { describe, expect, it, vi } from 'vitest';

import { zipResponse, type ZipDeps, type ZipFailure, type ZipJob } from './originalsZip';

// CRC-32 as the ZIP format defines it (polynomial 0xEDB88320), written out so that the test checks client-zip against
// the definition and not against itself.
const CRC_TABLE = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

interface Entry {
  name: string;
  method: number;
  bytes: Uint8Array;
  crcOk: boolean;
}

// Reads a ZIP from its central directory, as an extraction tool does, and checks every CRC.
function readZip(zip: Uint8Array): Entry[] {
  const view = new DataView(zip.buffer, zip.byteOffset, zip.byteLength);
  let eocd = zip.length - 22;
  while (view.getUint32(eocd, true) !== 0x06054b50) eocd -= 1;
  const count = view.getUint16(eocd + 10, true);
  let at = view.getUint32(eocd + 16, true);
  const entries: Entry[] = [];
  for (let i = 0; i < count; i += 1) {
    expect(view.getUint32(at, true)).toBe(0x02014b50);
    const method = view.getUint16(at + 10, true);
    const crc = view.getUint32(at + 16, true);
    const size = view.getUint32(at + 24, true);
    const nameLength = view.getUint16(at + 28, true);
    const extraLength = view.getUint16(at + 30, true);
    const commentLength = view.getUint16(at + 32, true);
    const local = view.getUint32(at + 42, true);
    const name = new TextDecoder().decode(zip.subarray(at + 46, at + 46 + nameLength));
    const start = local + 30 + view.getUint16(local + 26, true) + view.getUint16(local + 28, true);
    const bytes = zip.subarray(start, start + size);
    entries.push({ name, method, bytes, crcOk: crc32(bytes) === crc });
    at += 46 + nameLength + extraLength + commentLength;
  }
  return entries;
}

function body(bytes: Uint8Array, chunk = 1024): ReadableStream<Uint8Array> {
  let at = 0;
  return new ReadableStream({
    pull(controller) {
      if (at >= bytes.length) return controller.close();
      controller.enqueue(bytes.slice(at, at + chunk));
      at += chunk;
    },
  });
}

function sourceOf(files: Record<string, Uint8Array>, options: { status?: number; announce?: number } = {}) {
  return vi.fn(async (url: string | URL | Request) => {
    const data = files[String(url).split('/').pop() ?? ''];
    if (!data || options.status) return new Response('no', { status: options.status ?? 404 });
    return new Response(body(data), { headers: { 'content-length': String(options.announce ?? data.length) } });
  }) as unknown as typeof fetch & ReturnType<typeof vi.fn>;
}

function bytesOf(length: number, fill: number): Uint8Array {
  return new Uint8Array(length).fill(fill);
}

const JOB: ZipJob = {
  zipName: 'SCENE.zip',
  texts: [
    { name: 'ATTRIBUTION.txt', content: 'Copernicus Sentinel data 2026\n' },
    { name: 'item.json', content: '{"id": "SCENE"}\n' },
  ],
  files: [
    { name: 'SCENE_red.tif', url: 'https://data.test/red.tif', size: 5000 },
    { name: 'SCENE_green.tif', url: 'https://data.test/green.tif', size: 2500 },
  ],
};
const FILES = { 'red.tif': bytesOf(5000, 1), 'green.tif': bytesOf(2500, 2) };

function deps(fetchFn: typeof fetch, signal = new AbortController().signal) {
  const events: string[] = [];
  const progress: number[] = [];
  const real: ZipDeps = {
    fetch: fetchFn,
    signal,
    onProgress: (loaded) => progress.push(loaded),
    onDone: () => events.push('done'),
    onError: (code: ZipFailure, status?: number) => events.push(`error ${code}${status ? ` ${status}` : ''}`),
  };
  return { real, events, progress };
}

async function bodyOf(response: Response): Promise<Uint8Array> {
  return new Uint8Array(await response.arrayBuffer());
}

describe('the ZIP of a scene', () => {
  it('holds every file, stored without compression, with a correct CRC, the texts first', async () => {
    const { real } = deps(sourceOf(FILES));
    const zip = await bodyOf(zipResponse(JOB, real));
    const entries = readZip(zip);
    expect(entries.map((entry) => entry.name)).toEqual(['ATTRIBUTION.txt', 'item.json', 'SCENE_red.tif', 'SCENE_green.tif']);
    expect(entries.every((entry) => entry.method === 0 && entry.crcOk)).toBe(true);
    expect(new TextDecoder().decode(entries[0].bytes)).toBe('Copernicus Sentinel data 2026\n');
    expect(entries[2].bytes).toEqual(FILES['red.tif']);
    expect(entries[3].bytes).toEqual(FILES['green.tif']);
  });

  it('announces its length beforehand, and it is the length of the ZIP', async () => {
    const { real } = deps(sourceOf(FILES));
    const response = zipResponse(JOB, real);
    const announced = Number(response.headers.get('content-length'));
    expect(announced).toBeGreaterThan(7500);
    expect((await bodyOf(response)).length).toBe(announced);
  });

  it('is an attachment named as the job says, and is not cached', () => {
    const response = zipResponse(JOB, deps(sourceOf(FILES)).real);
    expect(response.headers.get('content-disposition')).toBe('attachment; filename="SCENE.zip"');
    expect(response.headers.get('content-type')).toBe('application/zip');
    expect(response.headers.get('cache-control')).toBe('no-store');
  });

  it('reads the files one after the other, in order, from the source and without credentials', async () => {
    const fetchFn = sourceOf(FILES);
    const { real } = deps(fetchFn);
    await bodyOf(zipResponse(JOB, real));
    expect(fetchFn.mock.calls.map((call: unknown[]) => String(call[0]).split('/').pop())).toEqual(['red.tif', 'green.tif']);
    for (const call of fetchFn.mock.calls as [string, RequestInit][]) {
      expect(call[1]).toMatchObject({ mode: 'cors', credentials: 'omit' });
    }
  });

  it('tells the end once, and progress that ends at the sum of the file sizes', async () => {
    const { real, events, progress } = deps(sourceOf(FILES));
    await bodyOf(zipResponse(JOB, real));
    expect(events).toEqual(['done']);
    expect(progress.at(-1)).toBe(7500);
    expect([...progress].sort((a, b) => a - b)).toEqual(progress);
  });

  it('a ZIP with no file is still a ZIP', async () => {
    const { real } = deps(sourceOf({}));
    const entries = readZip(await bodyOf(zipResponse({ ...JOB, files: [] }, real)));
    expect(entries.map((entry) => entry.name)).toEqual(['ATTRIBUTION.txt', 'item.json']);
  });
});

describe('when the ZIP cannot be finished', () => {
  it('a source that answers 404: the download fails and says so with the status, once, never with an address', async () => {
    const { real, events } = deps(sourceOf({ 'red.tif': FILES['red.tif'] }));
    await expect(bodyOf(zipResponse(JOB, real))).rejects.toThrow();
    expect(events).toEqual(['error http 404']);
    expect(events.join()).not.toContain('data.test');
  });

  it('a file of another length than announced: the download fails rather than ends as a broken ZIP', async () => {
    const { real, events } = deps(sourceOf(FILES, { announce: 4999 }));
    await expect(bodyOf(zipResponse(JOB, real))).rejects.toThrow();
    expect(events).toEqual(['error size']);
  });

  it('a connection that breaks is told as network', async () => {
    const broken = vi.fn(async () => {
      throw new TypeError('Failed to fetch');
    }) as unknown as typeof fetch;
    const { real, events } = deps(broken);
    await expect(bodyOf(zipResponse(JOB, real))).rejects.toThrow();
    expect(events).toEqual(['error network']);
  });

  it('a stop from the page ends the download as cancelled, and reads nothing more', async () => {
    const abort = new AbortController();
    const fetchFn = vi.fn((_url: string, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
      }),
    ) as unknown as typeof fetch;
    const { real, events } = deps(fetchFn, abort.signal);
    const reading = bodyOf(zipResponse(JOB, real));
    await new Promise((resolve) => setTimeout(resolve, 20));
    abort.abort();
    await expect(reading).rejects.toThrow();
    expect(events).toEqual(['error cancelled']);
  });

  it('the browser dropping the download is told as cancelled, and a late end does not follow', async () => {
    const { real, events } = deps(sourceOf(FILES));
    const reader = zipResponse(JOB, real).body!.getReader();
    await reader.read();
    await reader.cancel();
    expect(events).toEqual(['error cancelled']);
  });
});
