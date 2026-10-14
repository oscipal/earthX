// @vitest-environment jsdom
//
// "Merge scenes of this pass (job)" in the download dialog (M4-12b), mounted
// through the real dialog. No backend: `fetch` answers by route; jsdom has no
// `EventSource`, so a placed job is followed by polling.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import { setTrackerOptions, useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection, StacItem } from '../types';
import DownloadDialog from './DownloadDialog';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const JOB = 'AbCdEfGhIjKlMnOpQrSt_-';
const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const MERGE = 'Merge scenes of this pass (job)';

function scene(id: string, band: Record<string, unknown> = { data_type: 'uint8', nodata: 0 }): StacItem {
  return {
    id,
    collection: 'sentinel-2-c1-l2a',
    bbox: [10, 50, 11, 51],
    properties: { datetime: '2026-07-01T10:00:00Z' },
    assets: { visual: { href: `https://data.test/${id}.tif`, type: COG, 'raster:bands': [band, band, band] } },
  };
}

function dataset(tier: string): DatasetOption {
  return {
    id: 'sentinel-2-c1-l2a',
    title: 'Sentinel-2 L2A',
    viewable: true,
    groupBy: ['datetime'],
    zoom: { min: 8, max: 14 },
    browse: 'quicklook',
    quicklookNodataMax: null,
    resultsGroupBy: ['datetime'],
    hasTimeAxis: true,
    collection: {
      id: 'sentinel-2-c1-l2a',
      'earthx:format': 'cog',
      'earthx:default_render': { assets: ['visual'] },
      'earthx:source': { asset_hosts: ['data.test'] },
      'earthx:license_flags': {
        tier,
        attribution_modified: 'Contains modified Copernicus Sentinel data {year}',
        attribution_unmodified: 'Copernicus Sentinel data {year}',
      },
    } as unknown as Collection,
  };
}

// Two passes: a mosaic of three scenes and a lone scene.
function open(tier = 'processing', band?: Record<string, unknown>) {
  const first = [scene('S2_C', band), scene('S2_A', band), scene('S2_B', band)];
  const second = [scene('S2_D', band)];
  useAppStore.setState({
    datasets: [dataset(tier)],
    datasetId: 'sentinel-2-c1-l2a',
    items: [...first, ...second],
    groups: [
      { key: ['2026-07-02'], label: '2026-07-02', items: second },
      { key: ['2026-07-01'], label: '2026-07-01', items: first },
    ],
    selectedIds: [...first, ...second].map((i) => i.id),
    activeGroupIndex: 0,
    aoi: null,
    downloadDialogLayerId: null,
    downloadSelection: false,
    downloadOutcome: null,
    downloadOriginalLinks: null,
    downloadPasses: null,
    error: null,
  });
  useAppStore.getState().openDownloadForSelection();
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': status >= 400 ? 'application/problem+json' : 'application/json' },
  });
}

function statusDoc(state: string, progress = 0) {
  return {
    processID: 'recipe',
    type: 'process',
    jobID: JOB,
    status: state,
    message: '',
    progress,
    created: '2026-10-10T10:00:00Z',
    expires: new Date(Date.now() + 7 * 86_400_000).toISOString(),
    recipeID: 'r',
    links: [],
  };
}

type Route = (init?: RequestInit) => Response | Promise<Response>;
let routes: Record<string, Route>;
let fetchMock: ReturnType<typeof vi.fn>;
let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  routes = {
    'GET /processing/processes/recipe?dataset=sentinel-2-c1-l2a': () => json(s2),
    'POST /processing/processes/recipe/execution': () => json(statusDoc('accepted'), 201),
    [`GET /processing/jobs/${JOB}`]: () => json(statusDoc('running', 40)),
  };
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const route = routes[`${init?.method ?? 'GET'} ${url}`];
    if (!route) return json({ type: 'about:blank', title: 'Not found', status: 404, detail: `no route ${url}` }, 404);
    return route(init);
  });
  vi.stubGlobal('fetch', fetchMock);
  useProcessingStore.getState().resetDraft();
  useProcessingStore.setState({ open: false, descriptions: {}, jobs: [] });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  setTrackerOptions({});
  act(() => root.unmount());
  container.remove();
  for (const job of useProcessingStore.getState().jobs) useProcessingStore.getState().removeJob(job.jobID);
  useAppStore.getState().closeDownloadDialog();
  vi.unstubAllGlobals();
});

async function flush() {
  await act(async () => {
    for (let i = 0; i < 5; i++) await Promise.resolve();
  });
}

async function show() {
  act(() => root.render(<DownloadDialog />));
  await flush();
}

const buttons = (label: string) =>
  [...container.querySelectorAll('button')].filter((b) => b.textContent?.trim() === label) as HTMLButtonElement[];

async function merge() {
  act(() => buttons(MERGE)[0].dispatchEvent(new MouseEvent('click', { bubbles: true })));
  await flush();
}

const placed = () => fetchMock.mock.calls.filter(([u, init]) => String(u).endsWith('/execution') && init?.method === 'POST');

describe('the offer', () => {
  it('is made for a pass of several scenes, not for a lone scene', async () => {
    open();
    await show();
    expect(buttons(MERGE)).toHaveLength(1);
    expect(container.querySelector('.dialog-mosaics')?.textContent).toContain('2026-07-01 · 3 scenes');
    expect(container.querySelector('.dialog-mosaics')?.textContent).not.toContain('2026-07-02');
  });

  it('is not made at all when every pass is one scene', async () => {
    open();
    useAppStore.setState({ downloadPasses: [{ label: 'x', items: [scene('S2_A')] }] });
    await show();
    expect(container.querySelector('.dialog-mosaics')).toBeNull();
  });

  it('is not made for the crop: with an AOI the crop merges by itself', async () => {
    open();
    useAppStore.setState({ downloadOutcome: 'crop' });
    await show();
    expect(container.querySelector('.dialog-mosaics')).toBeNull();
  });

  it('waits for what a job takes, then enables the button', async () => {
    let answer!: (r: Response) => void;
    routes['GET /processing/processes/recipe?dataset=sentinel-2-c1-l2a'] = () =>
      new Promise((resolve) => {
        answer = resolve;
      });
    open();
    await show();
    expect(buttons(MERGE)[0].disabled).toBe(true);
    expect(container.textContent).toContain('Loading what a job takes');
    answer(json(s2));
    await flush();
    expect(buttons(MERGE)[0].disabled).toBe(false);
  });

  it('says so when what a job takes cannot be loaded', async () => {
    routes['GET /processing/processes/recipe?dataset=sentinel-2-c1-l2a'] = () => json({ detail: 'down' }, 503);
    open();
    await show();
    expect(buttons(MERGE)[0].disabled).toBe(true);
    expect(container.textContent).toContain('could not be asked what a job takes');
  });

  it('is disabled below the licence tier processing, with the reason and without the modified-data notice', async () => {
    open('catalog');
    await show();
    expect(buttons(MERGE)[0].disabled).toBe(true);
    expect(container.querySelector('.dialog-mosaics')?.textContent).toContain('licence does not permit processing');
    expect(container.textContent).not.toContain('Contains modified');
    expect(placed()).toHaveLength(0);
  });

  it('shows the attribution for modified data under the offer', async () => {
    open();
    await show();
    expect(container.querySelector('.dialog-mosaics')?.textContent).toContain('Contains modified Copernicus Sentinel data');
  });
});

describe('starting the job', () => {
  it('sends the whole scenes of the pass: one sorted group, no AOI, no steps, the type the item states', async () => {
    open();
    await show();
    await merge();
    expect(placed()).toHaveLength(1);
    expect(JSON.parse(placed()[0][1].body)).toEqual({
      inputs: {
        recipe: {
          recipe_version: 1,
          inputs: [{ name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['S2_A', 'S2_B', 'S2_C']], assets: ['visual'] }],
          steps: [],
          output: { kind: 'raster', format: 'cog', dtype: 'uint8' },
        },
      },
    });
  });

  it('asks for float32 where the item does not state a nodata value', async () => {
    open('processing', { data_type: 'uint8' });
    await show();
    await merge();
    expect(JSON.parse(placed()[0][1].body).inputs.recipe.output.dtype).toBe('float32');
  });

  it('shows the job with the row of the processing panel, and the button waits for it', async () => {
    open();
    await show();
    await merge();
    expect(container.querySelector('.dialog-mosaics .pp-job')?.textContent).toMatch(/Waiting for a worker|Running/);
    expect(buttons(MERGE)[0].disabled).toBe(true);
    expect(useProcessingStore.getState().jobs.map((j) => j.jobID)).toEqual([JOB]);
  });

  it('can order the pass again once the row is removed', async () => {
    open();
    await show();
    await merge();
    act(() => useProcessingStore.getState().removeJob(JOB));
    await flush();
    expect(buttons(MERGE)[0].disabled).toBe(false);
  });

  it.each([
    [413, 'the estimated size is over the cap of 5 GB; order fewer scenes'],
    [422, 'scenes of another pass: S2_B; a mosaic is made of one pass'],
    [403, 'the licence of this dataset does not allow processing'],
  ])('shows a %i of the server as it is, adds no job, and lets the user try again', async (status, detail) => {
    routes['POST /processing/processes/recipe/execution'] = () =>
      json({ type: 'about:blank', title: 'Refused', status, detail }, status);
    open();
    await show();
    await merge();
    expect(container.querySelector('.dialog-mosaics [role="alert"]')?.textContent).toBe(detail);
    expect(useProcessingStore.getState().jobs).toEqual([]);
    expect(buttons(MERGE)[0].disabled).toBe(false);
  });

  it('shows a network failure instead of throwing', async () => {
    routes['POST /processing/processes/recipe/execution'] = () => {
      throw new TypeError('Failed to fetch');
    };
    open();
    await show();
    await merge();
    expect(container.querySelector('.dialog-mosaics [role="alert"]')?.textContent).toContain('Failed to fetch');
  });
});
