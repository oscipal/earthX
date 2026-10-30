// The ZIP of one original scene (NM4-33, plan section 6.14): built in the browser from the files of the source,
// without compression (STORE), and handed to the browser as a download while it is still being made. The service
// worker (`originalsWorker.ts`) answers the request of the download with this stream; the page talks to the worker
// over a `MessageChannel` with the messages below. No address, scene id or token is ever written to a log here.

import { downloadZip, predictLength } from 'client-zip';

// What the page hands the worker for one ZIP. `files` are fetched one after the other, in this order, straight from
// the source (CORS, no credentials); `size` is the length the source gave (`file:size` or a `HEAD`), the sum of
// which makes the `Content-Length` of the ZIP.
export interface ZipJob {
  zipName: string;
  texts: { name: string; content: string }[];
  files: { name: string; url: string; size: number }[];
}

export type ZipCommand = { type: 'job'; id: string; job: ZipJob } | { type: 'cancel' } | { type: 'ping' };

// `started`: the browser asked for the download (so the worker is the one answering). `progress`: bytes of the
// files read so far. A failure names a code, never an address: `http` with the status the source answered, `size`
// (a file is not as long as announced), `network` (the connection broke), `cancelled`, `other`; `unavailable` is told
// by the page itself when no worker answered the request of the download.
export type ZipFailure = 'http' | 'size' | 'network' | 'cancelled' | 'unavailable' | 'other';
export type ZipReply =
  | { type: 'ready' }
  | { type: 'started' }
  | { type: 'progress'; loaded: number }
  | { type: 'done' }
  | { type: 'error'; code: ZipFailure; status?: number };

export class ZipError extends Error {
  readonly code: ZipFailure;
  readonly status: number | undefined;
  constructor(code: ZipFailure, status?: number) {
    super(`zip ${code}${status ? ` ${status}` : ''}`);
    this.code = code;
    this.status = status;
  }
}

export interface ZipDeps {
  fetch: typeof fetch;
  signal: AbortSignal;
  onProgress: (loaded: number) => void;
  onDone: () => void;
  onError: (failure: ZipFailure, status?: number) => void;
}

function failureOf(error: unknown, signal: AbortSignal): { code: ZipFailure; status?: number } {
  if (error instanceof ZipError) return { code: error.code, status: error.status };
  if (signal.aborted) return { code: 'cancelled' };
  return error instanceof TypeError ? { code: 'network' } : { code: 'other' };
}

const PROGRESS_STEP_MS = 250;

async function* entriesOf(job: ZipJob, deps: ZipDeps, now: Date) {
  for (const text of job.texts) yield { name: text.name, input: text.content, lastModified: now };
  let loaded = 0;
  let reported = 0;
  for (const file of job.files) {
    const response = await deps.fetch(file.url, { mode: 'cors', credentials: 'omit', signal: deps.signal });
    if (!response.ok || !response.body) throw new ZipError('http', response.status);
    // The length of the ZIP was announced from these sizes; a file of another length would end as a broken download.
    const announced = response.headers.get('content-length');
    if (announced !== null && Number(announced) !== file.size) throw new ZipError('size');
    const counted = response.body.pipeThrough(
      new TransformStream<Uint8Array, Uint8Array>({
        transform(chunk, controller) {
          loaded += chunk.byteLength;
          if (Date.now() - reported >= PROGRESS_STEP_MS) {
            reported = Date.now();
            deps.onProgress(loaded);
          }
          controller.enqueue(chunk);
        },
      }),
    );
    yield { name: file.name, input: counted, size: file.size, lastModified: now };
  }
  deps.onProgress(loaded);
}

// The answer to the request of the download: the ZIP as a stream with its length and name. Whatever ends the stream
// (all read, a failure, the browser dropping the download) is reported once through `deps`.
export function zipResponse(job: ZipJob, deps: ZipDeps): Response {
  const now = new Date();
  const metadata = [
    ...job.texts.map((text) => ({ name: text.name, input: text.content })),
    ...job.files.map((file) => ({ name: file.name, size: file.size })),
  ];
  const zip = downloadZip(entriesOf(job, deps, now), { length: predictLength(metadata) });
  const reader = zip.body!.getReader();
  let ended = false;
  const end = (report: () => void) => {
    if (ended) return;
    ended = true;
    report();
  };
  const body = new ReadableStream<Uint8Array>({
    async pull(controller) {
      try {
        const { done, value } = await reader.read();
        if (done) {
          controller.close();
          end(deps.onDone);
        } else {
          controller.enqueue(value);
        }
      } catch (error) {
        const { code, status } = failureOf(error, deps.signal);
        controller.error(error);
        end(() => deps.onError(code, status));
      }
    },
    cancel(reason) {
      end(() => deps.onError('cancelled'));
      // client-zip throws the reason into its generator, which ends the promise with it; nobody is left to read it.
      return reader.cancel(reason).catch(() => undefined);
    },
  });
  const headers = new Headers(zip.headers);
  headers.set('Content-Disposition', `attachment; filename="${job.zipName}"`);
  headers.set('Cache-Control', 'no-store');
  return new Response(body, { headers });
}
