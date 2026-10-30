// The service worker that streams the ZIP of a scene into a download (NM4-33, plan section 6.14.5). It handles
// nothing but the one request the page makes for the download, `<scope>__originals/<random id>`; the page hands it
// the job (names, addresses, sizes) over a `MessageChannel` first, and gets progress and the end over the same
// channel. It keeps no log and stores nothing: the job is used once and dropped.

import { zipResponse, type ZipCommand, type ZipFailure, type ZipJob, type ZipReply } from './originalsZip';

// The few parts of the service worker scope used here; the project's `lib` is `DOM`, which has no worker types.
interface WorkerEvent {
  waitUntil(promise: Promise<unknown>): void;
}
interface WorkerMessage {
  data: ZipCommand;
  ports: readonly MessagePort[];
}
interface WorkerFetch {
  request: Request;
  respondWith(response: Response | Promise<Response>): void;
}
interface WorkerScope {
  addEventListener(type: 'install', listener: () => void): void;
  addEventListener(type: 'activate', listener: (event: WorkerEvent) => void): void;
  addEventListener(type: 'message', listener: (event: WorkerMessage) => void): void;
  addEventListener(type: 'fetch', listener: (event: WorkerFetch) => void): void;
  skipWaiting(): Promise<void>;
  clients: { claim(): Promise<void> };
}

const scope = self as unknown as WorkerScope;

interface Pending {
  job: ZipJob;
  port: MessagePort;
  abort: AbortController;
}

const pending = new Map<string, Pending>();
const DOWNLOAD_PATH = /\/__originals\/([A-Za-z0-9-]{8,64})$/;

scope.addEventListener('install', () => void scope.skipWaiting());
scope.addEventListener('activate', (event) => event.waitUntil(scope.clients.claim()));

scope.addEventListener('message', (event) => {
  const command = event.data;
  const port = event.ports[0];
  if (command.type !== 'job' || !port) return;
  const abort = new AbortController();
  pending.set(command.id, { job: command.job, port, abort });
  port.onmessage = (message: MessageEvent<ZipCommand>) => {
    if (message.data.type === 'cancel') abort.abort();
  };
  port.postMessage({ type: 'ready' } satisfies ZipReply);
});

scope.addEventListener('fetch', (event) => {
  const match = DOWNLOAD_PATH.exec(new URL(event.request.url).pathname);
  if (!match) return;
  const entry = pending.get(match[1]);
  if (!entry) {
    event.respondWith(new Response('This download is gone.', { status: 404, headers: { 'Cache-Control': 'no-store' } }));
    return;
  }
  pending.delete(match[1]);
  const { job, port, abort } = entry;
  const tell = (reply: ZipReply) => port.postMessage(reply);
  const end = (reply: ZipReply) => {
    tell(reply);
    port.close();
  };
  tell({ type: 'started' });
  event.respondWith(
    zipResponse(job, {
      fetch: (input, init) => fetch(input, init),
      signal: abort.signal,
      onProgress: (loaded) => tell({ type: 'progress', loaded }),
      onDone: () => end({ type: 'done' }),
      onError: (code: ZipFailure, status?: number) => {
        // The browser dropped the download: nothing is read from the source any more.
        if (code === 'cancelled') abort.abort();
        end({ type: 'error', code, status });
      },
    }),
  );
});
