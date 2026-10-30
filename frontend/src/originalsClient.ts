// What the page does for "Download full scenes" (NM4-33): registers the service worker that streams a ZIP into a
// download, talks to it, and saves or hands over single files. The decisions are `originals.ts`'s and the order of
// things `originalsRun.ts`'s; this file is only the browser.

import type { RunDeps, ZipChannel } from './originalsRun';
import { ZipError, type ZipCommand, type ZipReply, type ZipJob } from './originalsZip';
import { workerUrl } from './originalsWorkerUrl';

// A request for the download has to reach the worker within this time, else there is none to answer it.
const START_TIMEOUT_MS = 10_000;
// The worker is told every so often that the download is still wanted: some browsers end a worker that has heard
// nothing for about half a minute, in the middle of a download (client-zip, "Known issues").
const KEEP_ALIVE_MS = 10_000;
const ACTIVATION_TIMEOUT_MS = 10_000;
// A file saved by the page is freed this long after the click. Chromium starts a download that waits for the answer
// to "download several files?" even when its blob address has been freed meanwhile (measured with a real click on
// "Allow", plan section 6.11), so the files of a whole run do not pile up in memory.
const FREE_SAVED_AFTER_MS = 30_000;

export function canStream(): boolean {
  return typeof navigator !== 'undefined' && 'serviceWorker' in navigator && globalThis.isSecureContext === true;
}

// The service worker handles requests below the folder it is served from, so the request of the download goes to
// `__originals/<id>` in that folder; no page of the app is below it.
function scopeOf(script: URL): string {
  return new URL('./', script).pathname;
}

function waitActive(registration: ServiceWorkerRegistration): Promise<ServiceWorker> {
  const worker = registration.active;
  if (worker) return Promise.resolve(worker);
  const installing = registration.installing ?? registration.waiting;
  return new Promise((resolve, reject) => {
    if (!installing) {
      reject(new ZipError('unavailable'));
      return;
    }
    const timer = setTimeout(() => reject(new ZipError('unavailable')), ACTIVATION_TIMEOUT_MS);
    installing.addEventListener('statechange', () => {
      if (installing.state === 'activated') {
        clearTimeout(timer);
        resolve(installing);
      } else if (installing.state === 'redundant') {
        clearTimeout(timer);
        reject(new ZipError('unavailable'));
      }
    });
  });
}

async function activeWorker(): Promise<{ worker: ServiceWorker; scope: string }> {
  const script = new URL(workerUrl, location.href);
  const scope = scopeOf(script);
  try {
    const registration = await navigator.serviceWorker.register(script.href, { type: 'module', scope });
    return { worker: await waitActive(registration), scope };
  } catch (error) {
    throw error instanceof ZipError ? error : new ZipError('unavailable');
  }
}

function zipChannel(hidden: HTMLIFrameElement[]): ZipChannel {
  return {
    async run(job: ZipJob, onLoaded, signal) {
      const { worker, scope } = await activeWorker();
      if (signal.aborted) throw new ZipError('cancelled');
      const id = crypto.randomUUID();
      const channel = new MessageChannel();
      const send = (command: ZipCommand) => channel.port1.postMessage(command);
      return new Promise<void>((resolve, reject) => {
        let startTimer: ReturnType<typeof setTimeout> | undefined;
        const keepAlive = setInterval(() => send({ type: 'ping' }), KEEP_ALIVE_MS);
        const finish = (error?: ZipError) => {
          clearInterval(keepAlive);
          clearTimeout(startTimer);
          signal.removeEventListener('abort', onAbort);
          channel.port1.close();
          if (error) reject(error);
          else resolve();
        };
        const onAbort = () => {
          send({ type: 'cancel' });
          finish(new ZipError('cancelled'));
        };
        signal.addEventListener('abort', onAbort);
        channel.port1.onmessage = (event: MessageEvent<ZipReply>) => {
          const reply = event.data;
          if (reply.type === 'ready') {
            const frame = document.createElement('iframe');
            frame.hidden = true;
            frame.src = `${scope}__originals/${id}`;
            document.body.append(frame);
            hidden.push(frame);
            startTimer = setTimeout(() => {
              send({ type: 'cancel' });
              finish(new ZipError('unavailable'));
            }, START_TIMEOUT_MS);
          } else if (reply.type === 'started') {
            clearTimeout(startTimer);
          } else if (reply.type === 'progress') {
            onLoaded(reply.loaded);
          } else if (reply.type === 'done') {
            finish();
          } else if (reply.type === 'error') {
            finish(new ZipError(reply.code, reply.status));
          }
        };
        worker.postMessage({ type: 'job', id, job } satisfies ZipCommand, [channel.port2]);
      });
    },
  };
}

// The things a run needs from the page. `dispose` removes what it put into the page and frees the files it saved that
// are not yet freed: it is called when the dialog closes, which also ends the run.
export function browserDeps(): { deps: RunDeps; dispose(): void } {
  const urls = new Set<string>();
  const timers = new Set<ReturnType<typeof setTimeout>>();
  const frames: HTMLIFrameElement[] = [];
  const deps: RunDeps = {
    fetch: (input, init) => fetch(input, init),
    zip: canStream() ? zipChannel(frames) : null,
    saveBlob(name, blob) {
      const href = URL.createObjectURL(blob);
      urls.add(href);
      const timer = setTimeout(() => {
        timers.delete(timer);
        urls.delete(href);
        URL.revokeObjectURL(href);
      }, FREE_SAVED_AFTER_MS);
      timers.add(timer);
      const link = Object.assign(document.createElement('a'), { href, download: name, hidden: true });
      document.body.append(link);
      link.click();
      link.remove();
    },
    navigate(href) {
      const frame = Object.assign(document.createElement('iframe'), { hidden: true, src: href });
      document.body.append(frame);
      frames.push(frame);
    },
    now: () => new Date(),
  };
  return {
    deps,
    dispose() {
      for (const timer of timers) clearTimeout(timer);
      timers.clear();
      for (const url of urls) URL.revokeObjectURL(url);
      urls.clear();
      for (const frame of frames.splice(0)) frame.remove();
    },
  };
}
