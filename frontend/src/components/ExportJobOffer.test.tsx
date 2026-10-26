// @vitest-environment jsdom
//
// "Export as job" in the download dialog (M4-11b-2), mounted through the real
// dialog. No backend: `fetch` answers by route; jsdom has no `EventSource`, so
// a placed job is followed by polling.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import type { ExportOffer } from '../download';
import { bboxToPolygon } from '../geoUtils';
import { placeAoi } from '../placeSearch';
import { resetJobs, useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection, StacItem } from '../types';
import DownloadDialog from './DownloadDialog';
import { TOO_LARGE_FOR_A_JOB } from './ExportJobOffer';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const JOB = 'AbCdEfGhIjKlMnOpQrSt_-';
const EXPORT = 'Export as job';
const MESSAGE = 'This download would be about 1.8 GB, more than the 500 MB limit.';
const AOI = bboxToPolygon([10.2, 50.2, 10.4, 50.4]);
const PLACE = {
  name: 'Somewhere',
  display_name: 'Somewhere',
  kind: 'city',
  bbox: [10.2, 50.2, 10.4, 50.4] as [number, number, number, number],
  outline: null,
  outline_simplified: false,
};

const ESTIMATE = {
  estimate: {
    size: 1_800_000_000,
    duration: 'PT240S',
    outputPixels: 1,
    inputPixels: 1,
    inputBytes: 1,
    assets: 1,
    units: 2,
  },
  skippedItems: [],
};

function scene(id: string): StacItem {
  return {
    id,
    collection: 'sentinel-2-c1-l2a',
    bbox: [10, 50, 11, 51],
    properties: { datetime: '2026-07-01T10:00:00Z' },
    assets: { visual: { href: `https://data.test/${id}.tif` } },
  };
}

const DATASET: DatasetOption = {
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
    'earthx:license_flags': { tier: 'processing' },
  } as unknown as Collection,
};

let offers = 0;

function offer(exportJob: ExportOffer['exportJob'] = 'available', aoi: GeoJSON.Polygon = AOI): ExportOffer {
  return {
    id: ++offers,
    request: { datasetId: DATASET.id, groups: [['S2_A', 'S2_B']], assets: ['visual'], aoi },
    message: MESSAGE,
    exportJob,
  };
}

function open(exportOffer: ExportOffer = offer()) {
  const items = [scene('S2_A'), scene('S2_B')];
  useAppStore.setState({
    datasets: [DATASET],
    datasetId: DATASET.id,
    items,
    groups: [{ key: ['2026-07-01'], label: '2026-07-01', items }],
    selectedIds: items.map((i) => i.id),
    activeGroupIndex: 0,
    aoi: exportOffer.request.aoi,
    downloadDialogLayerId: null,
    downloadSelection: true,
    downloadOutcome: 'crop',
    downloadExportOffer: exportOffer,
    error: null,
  });
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': status >= 400 ? 'application/problem+json' : 'application/json' },
  });
}

function problem(status: number, detail: string, type = 'about:blank') {
  return json({ type, title: 'Refused', status, detail }, status);
}

function statusDoc(state: string, progress = 0) {
  return {
    processID: 'recipe',
    type: 'process',
    jobID: JOB,
    status: state,
    message: '',
    progress,
    created: '2026-10-14T10:00:00Z',
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
  localStorage.clear();
  routes = {
    'POST /processing/processes/recipe/estimate': () => json(ESTIMATE),
    'POST /processing/processes/recipe/execution': () => json(statusDoc('accepted'), 201),
    [`GET /processing/jobs/${JOB}`]: () => json(statusDoc('running', 40)),
  };
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const route = routes[`${init?.method ?? 'GET'} ${url}`];
    if (!route) return problem(404, `no route ${url}`);
    return route(init);
  });
  vi.stubGlobal('fetch', fetchMock);
  useProcessingStore.setState({ jobs: [] });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  resetJobs();
  localStorage.clear();
  sessionStorage.clear();
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

const section = () => container.querySelector('.dialog-export-job');
const button = (label: string) =>
  [...container.querySelectorAll('button')].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;

async function click(label: string) {
  act(() => button(label)?.dispatchEvent(new MouseEvent('click', { bubbles: true })));
  await flush();
}

const calls = (path: string) =>
  fetchMock.mock.calls.filter(([u, init]) => String(u) === path && init?.method === 'POST') as [string, RequestInit][];

describe('the offer', () => {
  it('is not there without a 413 that names a job', async () => {
    open();
    useAppStore.setState({ downloadExportOffer: null });
    await show();
    expect(section()).toBeNull();
    expect(calls('/processing/processes/recipe/estimate')).toHaveLength(0);
  });

  it("shows the server's text and the estimate, asked once for the crop as an export order", async () => {
    open();
    await show();
    expect(section()?.textContent).toContain('Too large for a direct download');
    expect(section()?.textContent).toContain(MESSAGE);
    expect(section()?.textContent).toContain('About 1.8 GB · about 4 min');
    expect(button(EXPORT)?.disabled).toBe(false);
    const estimates = calls('/processing/processes/recipe/estimate');
    expect(estimates).toHaveLength(1);
    expect(JSON.parse(estimates[0][1].body as string)).toEqual({
      inputs: {
        recipe: {
          recipe_version: 1,
          inputs: [{ name: 'input', dataset: DATASET.id, groups: [['S2_A', 'S2_B']], assets: ['visual'] }],
          aoi: AOI,
          steps: [],
          output: { kind: 'crop', format: 'cog', resolution_factor: 1, extent: 'bbox(aoi ∩ footprints)', mask: 'file' },
        },
      },
    });
  });

  it('waits for the estimate before the button can start a job', async () => {
    let answer!: (r: Response) => void;
    routes['POST /processing/processes/recipe/estimate'] = () =>
      new Promise((resolve) => {
        answer = resolve;
      });
    open();
    await show();
    expect(section()?.textContent).toContain('Estimating the export');
    expect(button(EXPORT)?.disabled).toBe(true);
    answer(json(ESTIMATE));
    await flush();
    expect(button(EXPORT)?.disabled).toBe(false);
  });

  it('is locked with the reason for X-Export-Job: too-large, without asking for an estimate', async () => {
    open(offer('too-large'));
    await show();
    expect(section()?.textContent).toContain(TOO_LARGE_FOR_A_JOB);
    expect(button(EXPORT)?.disabled).toBe(true);
    expect(button(EXPORT)?.title).toBe(TOO_LARGE_FOR_A_JOB);
    expect(calls('/processing/processes/recipe/estimate')).toHaveLength(0);
  });

  it('is locked with the reason when the estimate is over 5 GB (413)', async () => {
    routes['POST /processing/processes/recipe/estimate'] = () =>
      problem(413, 'the estimated size is over the cap of 5 GB', 'urn:earthx:order-refused:size');
    open();
    await show();
    expect(section()?.textContent).toContain(TOO_LARGE_FOR_A_JOB);
    expect(button(EXPORT)?.disabled).toBe(true);
  });

  it('shows the text of another failed estimate and tries again on request', async () => {
    let first = true;
    routes['POST /processing/processes/recipe/estimate'] = () => {
      if (!first) return json(ESTIMATE);
      first = false;
      return problem(503, 'the catalogue is not reachable');
    };
    open();
    await show();
    expect(section()?.querySelector('[role="alert"]')?.textContent).toContain(
      'the catalogue is not reachable Try again in a moment.',
    );
    expect(button(EXPORT)?.disabled).toBe(true);
    await click('Try again');
    expect(calls('/processing/processes/recipe/estimate')).toHaveLength(2);
    expect(section()?.textContent).toContain('About 1.8 GB');
    expect(button(EXPORT)?.disabled).toBe(false);
  });

  it('drops an estimate still on its way when the dialog closes', async () => {
    let answer!: (r: Response) => void;
    routes['POST /processing/processes/recipe/estimate'] = () =>
      new Promise((resolve) => {
        answer = resolve;
      });
    open();
    await show();
    const signal = calls('/processing/processes/recipe/estimate')[0][1].signal;
    act(() => useAppStore.getState().closeDownloadDialog());
    await flush();
    expect(signal?.aborted).toBe(true);
    answer(json(ESTIMATE));
    await flush();
    expect(container.textContent).toBe('');
  });

  it('starts afresh for a new offer: its own estimate, no job of the last one', async () => {
    open();
    await show();
    await click(EXPORT);
    expect(button(EXPORT)?.disabled).toBe(true);
    act(() => useAppStore.setState({ downloadExportOffer: offer() }));
    await flush();
    expect(calls('/processing/processes/recipe/estimate')).toHaveLength(2);
    expect(section()?.querySelector('.pp-job')).toBeNull();
    expect(button(EXPORT)?.disabled).toBe(false);
  });

  it("shows a Zarr dataset's 422 as the backend words it", async () => {
    const detail = 'an export job reads COG assets only; synthetic-zarr is a Zarr store';
    routes['POST /processing/processes/recipe/estimate'] = () => problem(422, detail, 'urn:earthx:order-refused:scope');
    open();
    await show();
    expect(section()?.querySelector('[role="alert"]')?.textContent).toContain(detail);
  });
});

describe('starting the export', () => {
  const placed = () => calls('/processing/processes/recipe/execution');

  it('sends no aoiProvenance for a drawn AOI', async () => {
    open();
    await show();
    await click(EXPORT);
    expect(placed()).toHaveLength(1);
    expect(Object.keys(JSON.parse(placed()[0][1].body as string).inputs)).toEqual(['recipe']);
  });

  it("sends a place AOI's three fields as aoiProvenance, and its outline without them", async () => {
    open(offer('available', placeAoi(PLACE) as GeoJSON.Polygon));
    await show();
    await click(EXPORT);
    const inputs = JSON.parse(placed()[0][1].body as string).inputs;
    expect(inputs.aoiProvenance).toEqual({
      source: 'OpenStreetMap / Nominatim',
      attribution: '© OpenStreetMap contributors',
      license: 'ODbL-1.0',
    });
    expect('properties' in inputs.recipe.aoi).toBe(false);
  });

  it('shows the job with the row of the panel, keeps it in the panel list, and does not start it twice', async () => {
    open();
    await show();
    await click(EXPORT);
    expect(section()?.querySelector('.pp-job')?.textContent).toMatch(/Waiting for a worker|Running/);
    expect(button(EXPORT)?.disabled).toBe(true);
    expect(useProcessingStore.getState().jobs.map((j) => j.jobID)).toEqual([JOB]);
    act(() => useAppStore.getState().closeDownloadDialog());
    expect(useProcessingStore.getState().jobs.map((j) => j.jobID)).toEqual([JOB]);
  });

  it('names the job "Export · <dataset> · <day>", with the day the scenes share', async () => {
    open();
    await show();
    await click(EXPORT);
    expect(useProcessingStore.getState().jobs[0].title).toMatch(/^Export · Sentinel-2 L2A · 1 Jul( 2026)?$/);
  });

  it('names the day the job is started where the app does not hold the scenes of the export', async () => {
    open();
    useAppStore.setState({ items: [], groups: [] });
    await show();
    await click(EXPORT);
    expect(useProcessingStore.getState().jobs[0].title).toMatch(/^Export · Sentinel-2 L2A · \d{1,2} [A-Z][a-z]{2}( \d{4})?$/);
  });

  it('lets the export be ordered again once the job failed, and keeps the first job in the list', async () => {
    open();
    await show();
    await click(EXPORT);
    act(() => useProcessingStore.setState((s) => ({ jobs: s.jobs.map((j) => ({ ...j, phase: 'failed' as const })) })));
    expect(button(EXPORT)?.disabled).toBe(false);
    expect(useProcessingStore.getState().jobs.map((j) => j.jobID)).toEqual([JOB]);
  });

  it('places one job for a double click while it is starting', async () => {
    let answer!: (r: Response) => void;
    routes['POST /processing/processes/recipe/execution'] = () =>
      new Promise((resolve) => {
        answer = resolve;
      });
    open();
    await show();
    act(() => {
      button(EXPORT)?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    act(() => {
      button('Starting…')?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(button('Starting…')?.disabled).toBe(true);
    answer(json(statusDoc('accepted'), 201));
    await flush();
    expect(placed()).toHaveLength(1);
    expect(useProcessingStore.getState().jobs).toHaveLength(1);
  });

  it('shows a refusal of the start as the server words it and adds no job', async () => {
    routes['POST /processing/processes/recipe/execution'] = () => problem(422, 'the AOI lies outside the scenes');
    open();
    await show();
    await click(EXPORT);
    expect(section()?.querySelector('[role="alert"]')?.textContent).toBe('the AOI lies outside the scenes');
    expect(useProcessingStore.getState().jobs).toEqual([]);
    expect(button(EXPORT)?.disabled).toBe(false);
  });
});
