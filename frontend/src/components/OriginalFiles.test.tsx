// @vitest-environment jsdom
//
// The rows of "Download full scenes" (NM4-33) as the component runs them: what the page would do is replaced by
// `page` (the ZIP channel, the source, the saved files); the logic of a run is tested in `originalsRun.test.ts`.

import { StrictMode, act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import type { DownloadPass } from '../download';
import { collection as makeCollection, item } from '../fixtures/originalsScene';
import type { ZipChannel } from '../originalsRun';
import { ZipError, type ZipJob } from '../originalsZip';
import type { Collection } from '../types';
import OriginalFiles from './OriginalFiles';

const page = vi.hoisted(() => ({
  zip: null as unknown,
  created: 0,
  disposed: 0,
  saved: [] as string[],
  navigated: [] as string[],
}));

vi.mock('../originalsClient', () => ({
  canStream: () => true,
  browserDeps: () => {
    page.created += 1;
    return {
      deps: {
        fetch: async () => new Response(null, { headers: { 'content-length': '1000' } }),
        zip: page.zip,
        saveBlob: (name: string) => page.saved.push(name),
        navigate: (href: string) => page.navigated.push(href),
        now: () => new Date('2026-10-30T12:00:00Z'),
      },
      dispose: () => {
        page.disposed += 1;
      },
    };
  },
}));

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  page.zip = null;
  page.created = 0;
  page.disposed = 0;
  page.saved = [];
  page.navigated = [];
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function dataset(collection: Collection): DatasetOption {
  return { id: 'made-up-scenes', title: 'Made-up scenes', viewable: true, groupBy: ['datetime'], zoom: { min: 0, max: 19 }, browse: 'quicklook', quicklookNodataMax: null, resultsGroupBy: ['datetime'], hasTimeAxis: true, collection };
}

const passes = (...ids: string[]): DownloadPass[] => [{ label: 'Pass', items: ids.map((id) => item(id, {}, ['red'])) }];

async function flush() {
  await act(async () => {
    for (let i = 0; i < 10; i += 1) await Promise.resolve();
  });
}

async function show(element: React.ReactElement) {
  act(() => root.render(element));
  await flush();
}

const rows = () => [...container.querySelectorAll('.dialog-original-state')].map((e) => e.textContent);
const button = (label: string) => [...container.querySelectorAll('button')].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;
async function press(label: string) {
  act(() => button(label)!.dispatchEvent(new MouseEvent('click', { bubbles: true })));
  await flush();
}

// A channel that finishes a scene at once, or one that waits until it is stopped.
function channel(hang: (job: ZipJob) => boolean) {
  const jobs: string[] = [];
  const signals: AbortSignal[] = [];
  const zip: ZipChannel = {
    run: (job, onLoaded, signal) => {
      jobs.push(job.zipName);
      signals.push(signal);
      if (!hang(job)) {
        onLoaded(2500);
        return Promise.resolve();
      }
      onLoaded(1000);
      return new Promise<void>((_resolve, reject) => signal.addEventListener('abort', () => reject(new ZipError('cancelled'))));
    },
  };
  return { zip, jobs, signals };
}

describe('the rows', () => {
  it('start by themselves and go to Done, one ZIP name per row', async () => {
    const ch = channel(() => false);
    page.zip = ch.zip;
    await show(<OriginalFiles dataset={dataset(makeCollection())} links={[]} passes={passes('A', 'B')} />);
    expect(rows()).toEqual(['Done', 'Done']);
    expect([...container.querySelectorAll('.dialog-original-name')].map((e) => e.textContent)).toEqual(['A.zip', 'B.zip']);
    expect(ch.jobs).toEqual(['A.zip', 'B.zip']);
    expect(button('Cancel')).toBeUndefined();
    expect(button('Retry failed')).toBeUndefined();
  });

  it('names the scenes and the size above the rows, as the tooltip of the button did', async () => {
    page.zip = channel(() => false).zip;
    await show(<OriginalFiles dataset={dataset(makeCollection())} links={[]} passes={passes('A', 'B')} />);
    expect(container.querySelector('.dialog-originals > .hint-text')?.textContent).toBe('2 scenes · 5 kB');
  });

  it('React starting and stopping the run at once (StrictMode) does no download twice', async () => {
    await show(
      <StrictMode>
        <OriginalFiles dataset={dataset(makeCollection({ 'earthx:access': { cors: false } }))} links={[]} passes={passes('A', 'B')} />
      </StrictMode>,
    );
    expect(page.saved).toEqual(['made-up-scenes_ATTRIBUTION.txt']);
    expect(page.navigated).toEqual(['https://data.test/A/red.tif', 'https://data.test/B/red.tif']);
    expect(rows()).toEqual(['Started in your browser', 'Started in your browser']);
  });

  it('Cancel stops the scene that runs and the ones that wait; Retry failed loads only those, once', async () => {
    const ch = channel((job) => job.zipName === 'B.zip' && ch.jobs.filter((name) => name === 'B.zip').length === 1);
    page.zip = ch.zip;
    await show(<OriginalFiles dataset={dataset(makeCollection())} links={[]} passes={passes('A', 'B', 'C')} />);
    expect(rows()).toEqual(['Done', 'Loading 40 %', 'Waiting']);
    expect(button('Retry failed')).toBeUndefined();
    await press('Cancel');
    expect(rows()).toEqual(['Done', 'Cancelled', 'Cancelled']);
    expect(button('Cancel')).toBeUndefined();
    await press('Retry failed');
    expect(rows()).toEqual(['Done', 'Done', 'Done']);
    expect(ch.jobs).toEqual(['A.zip', 'B.zip', 'B.zip', 'C.zip']);
    expect(button('Retry failed')).toBeUndefined();
  });

  it('a failed scene shows its reason and the others go on', async () => {
    const zip: ZipChannel = { run: async (job) => (job.zipName === 'A.zip' ? Promise.reject(new ZipError('http', 503)) : undefined) };
    page.zip = zip;
    await show(<OriginalFiles dataset={dataset(makeCollection())} links={[]} passes={passes('A', 'B')} />);
    expect(rows()).toEqual(['Failed: The source answered 503.', 'Done']);
    expect(button('Retry failed')).toBeDefined();
  });

  it('closing the dialog stops what runs and frees what the page put into itself', async () => {
    const ch = channel(() => true);
    page.zip = ch.zip;
    await show(<OriginalFiles dataset={dataset(makeCollection())} links={[]} passes={passes('A', 'B')} />);
    expect(ch.signals[0].aborted).toBe(false);
    act(() => root.unmount());
    expect(ch.signals[0].aborted).toBe(true);
    expect(page.disposed).toBe(1);
    root = createRoot(container);
  });

  it('the same scenes in new objects (the datasets loaded again) start no second run', async () => {
    const ch = channel(() => false);
    page.zip = ch.zip;
    await show(<OriginalFiles dataset={dataset(makeCollection())} links={[]} passes={passes('A', 'B')} />);
    expect(page.created).toBe(1);
    await show(<OriginalFiles dataset={dataset(makeCollection())} links={[]} passes={passes('A', 'B')} />);
    expect(page.created).toBe(1);
    expect(ch.jobs).toEqual(['A.zip', 'B.zip']);
  });

  it('another selection starts a run of its own', async () => {
    const ch = channel(() => false);
    page.zip = ch.zip;
    await show(<OriginalFiles dataset={dataset(makeCollection())} links={[]} passes={passes('A')} />);
    await show(<OriginalFiles dataset={dataset(makeCollection())} links={[]} passes={passes('C')} />);
    expect(ch.jobs).toEqual(['A.zip', 'C.zip']);
  });

  it('a note names the way where it is not the ZIP', async () => {
    await show(<OriginalFiles dataset={dataset(makeCollection({ 'earthx:access': { cors: false } }))} links={[]} passes={passes('A')} />);
    expect(container.textContent).toContain('Your browser downloads each file.');
    expect(container.querySelector('.hint-text[title]')?.getAttribute('title')).toContain('under the name the source gives it');
  });
});
