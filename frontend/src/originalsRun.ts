// The run of "Download full scenes" (NM4-33, plan section 6.14.5): one scene after the other, each by the way
// `originals.ts::chooseWay` names, with whatever the page can do (`RunDeps`) handed in, so that the same code runs in
// the browser and in the tests. Failures are told as plain sentences that carry no address, scene id or token.

import {
  ATTRIBUTION_FILENAME,
  MAX_FILE_BYTES,
  attributionBlocker,
  attributionFileText,
  chooseWay,
  safeName,
  savedFilesOf,
  sceneItemJson,
  sourceFileName,
  zipJobOf,
  type OriginalEntry,
  type OriginalScene,
  type Way,
} from './originals';
import { ZipError, type ZipJob } from './originalsZip';
import type { Collection } from './types';

export type SceneState =
  | { status: 'waiting' }
  | { status: 'running'; loaded: number; total: number | null }
  | { status: 'done' }
  // Every file was handed to the browser as a download of its own; it is no longer in our sight.
  | { status: 'started' }
  | { status: 'failed'; reason: string }
  | { status: 'cancelled' };

export interface ZipChannel {
  // Resolves once the ZIP has been read to its end by the browser; rejects with a `ZipError`.
  run(job: ZipJob, onLoaded: (loaded: number) => void, signal: AbortSignal): Promise<void>;
}

export interface RunDeps {
  fetch: typeof fetch;
  // `null`: this browser cannot stream a ZIP (no service worker, no secure context).
  zip: ZipChannel | null;
  saveBlob(name: string, blob: Blob): void;
  // A download the browser makes itself, under the name the source gives the file.
  navigate(href: string): void;
  now(): Date;
}

export interface RunArgs {
  collection: Collection;
  datasetId: string;
  scenes: readonly OriginalScene[];
  // Which scenes to run, by index; all when left out ("Retry failed" passes the ones that did not finish).
  only?: readonly number[];
  years: string | null;
  deps: RunDeps;
  signal: AbortSignal;
  onScene(index: number, state: SceneState): void;
  // The way the run goes, and why it is not the first choice, when it is not.
  onWay(way: Way, reason: string | null): void;
}

// A failure with its own sentence.
class Failure extends Error {}

export function failureText(error: unknown): string {
  if (error instanceof Failure) return error.message;
  if (error instanceof ZipError) {
    if (error.code === 'http') return `The source answered ${error.status ?? 'with an error'}.`;
    if (error.code === 'size') return 'A file is not as long as the source announced.';
    if (error.code === 'network') return 'The connection to the source failed.';
    if (error.code === 'cancelled') return 'The download was cancelled in your browser.';
  }
  return error instanceof TypeError ? 'The connection to the source failed.' : 'The download failed.';
}

async function lengthOf(deps: RunDeps, href: string, signal: AbortSignal): Promise<number | null> {
  const response = await deps.fetch(href, { method: 'HEAD', mode: 'cors', credentials: 'omit', signal });
  if (!response.ok) throw new ZipError('http', response.status);
  const length = Number(response.headers.get('content-length'));
  return Number.isFinite(length) && length > 0 ? length : null;
}

async function sizesOf(scene: OriginalScene, deps: RunDeps, signal: AbortSignal, strict: boolean) {
  const sizes = new Map<string, number>();
  for (const entry of scene.entries) {
    const size = entry.size ?? (await lengthOf(deps, entry.href, signal));
    if (size !== null) sizes.set(entry.href, size);
    else if (strict) throw new Failure('The source does not tell how large a file is.');
  }
  return sizes;
}

async function readBlob(deps: RunDeps, href: string, signal: AbortSignal, onBytes: (n: number) => void): Promise<Blob> {
  const response = await deps.fetch(href, { mode: 'cors', credentials: 'omit', signal });
  if (!response.ok || !response.body) throw new ZipError('http', response.status);
  const reader = response.body.getReader();
  const chunks: Uint8Array<ArrayBuffer>[] = [];
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value as Uint8Array<ArrayBuffer>);
    onBytes(value.byteLength);
  }
  return new Blob(chunks, { type: response.headers.get('content-type') ?? 'application/octet-stream' });
}

function textBlob(text: string, type: string): Blob {
  return new Blob([text], { type: `${type};charset=utf-8` });
}

export async function runOriginals(args: RunArgs): Promise<void> {
  const { collection, datasetId, scenes, years, deps, signal } = args;
  const order = args.only ?? scenes.map((_, index) => index);
  const set = args.onScene;
  for (const index of order) set(index, { status: 'waiting' });

  // A run does nothing in the page before the next tick: React may start a run and stop it in the same breath (in
  // development, `StrictMode` does), and a run that is stopped must not have saved or started a download by then.
  await Promise.resolve();
  if (signal.aborted) {
    for (const index of order) set(index, { status: 'cancelled' });
    return;
  }

  const blocker = attributionBlocker(collection['earthx:license_flags'], years);
  if (blocker) {
    for (const index of order) set(index, { status: 'failed', reason: blocker });
    return;
  }

  let way = chooseWay(collection['earthx:access']?.cors, deps.zip !== null);
  args.onWay(way, null);
  const chosen = order.map((index) => scenes[index]);

  // One request decides whether the page may read the source at all: where it cannot (a `TypeError`, which is what
  // a missing CORS header looks like), every file is a download of the browser, for the rest of the run.
  if (way !== 'navigate') {
    const first = chosen.flatMap((scene) => scene.entries)[0];
    if (first) {
      try {
        await lengthOf(deps, first.href, signal);
      } catch (error) {
        if (error instanceof TypeError && !signal.aborted) {
          way = 'navigate';
          args.onWay(way, 'The source does not allow the page to read its files.');
        }
      }
    }
  }

  const allScenes = chosen;
  let attributionSaved = false;
  const saveAttribution = (named: (entry: OriginalEntry) => string, only?: (entry: OriginalEntry) => boolean) => {
    if (attributionSaved) return;
    attributionSaved = true;
    const text = attributionFileText({
      collection,
      scenes: allScenes,
      files: savedFilesOf(
        allScenes.map((scene) => (only ? { ...scene, entries: scene.entries.filter(only) } : scene)),
        named,
      ),
      years,
      now: deps.now(),
    });
    deps.saveBlob(`${safeName(datasetId)}_${ATTRIBUTION_FILENAME}`, textBlob(text, 'text/plain'));
  };

  for (let k = 0; k < order.length; k += 1) {
    const index = order[k];
    const scene = scenes[index];
    if (signal.aborted) {
      for (const rest of order.slice(k)) set(rest, { status: 'cancelled' });
      return;
    }
    if (scene.entries.length === 0) {
      set(index, { status: 'failed', reason: 'The source gives no direct link for this scene.' });
      continue;
    }
    try {
      if (way === 'zip') {
        const sizes = await sizesOf(scene, deps, signal, true);
        const total = [...sizes.values()].reduce((sum, size) => sum + size, 0);
        const attribution = attributionFileText({
          collection,
          scenes: [scene],
          files: savedFilesOf([scene], (entry) => entry.name),
          years,
          now: deps.now(),
        });
        set(index, { status: 'running', loaded: 0, total });
        await deps.zip!.run(
          zipJobOf(scene, attribution, sizes),
          (loaded) => set(index, { status: 'running', loaded, total }),
          signal,
        );
        set(index, { status: 'done' });
      } else if (way === 'files') {
        saveAttribution((entry) => entry.name);
        const sizes = await sizesOf(scene, deps, signal, false);
        const total = sizes.size === scene.entries.length ? [...sizes.values()].reduce((sum, s) => sum + s, 0) : null;
        let loaded = 0;
        set(index, { status: 'running', loaded, total });
        for (const entry of scene.entries) {
          const size = sizes.get(entry.href) ?? null;
          if (size !== null && size > MAX_FILE_BYTES) {
            deps.navigate(entry.href);
            continue;
          }
          const blob = await readBlob(deps, entry.href, signal, (n) => {
            loaded += n;
            set(index, { status: 'running', loaded, total });
          });
          deps.saveBlob(entry.name, blob);
        }
        deps.saveBlob(`${safeName(scene.item.id)}_item.json`, textBlob(sceneItemJson(scene.item), 'application/json'));
        set(index, { status: 'done' });
      } else {
        // Files a browser would show instead of saving (XML, JSON) are not sent to it as downloads.
        const data = (entry: OriginalEntry) => entry.kind === 'data';
        saveAttribution((entry) => sourceFileName(entry.href), data);
        for (const entry of scene.entries.filter(data)) deps.navigate(entry.href);
        set(index, { status: 'started' });
      }
    } catch (error) {
      if (signal.aborted) {
        set(index, { status: 'cancelled' });
      } else if (error instanceof ZipError && error.code === 'unavailable') {
        // The service worker did not answer, though the browser said it has one: the files come one by one instead.
        way = 'files';
        args.onWay(way, 'This browser could not start the ZIP.');
        k -= 1;
      } else {
        set(index, { status: 'failed', reason: failureText(error) });
      }
    }
  }
}
