// @vitest-environment jsdom
//
// The original files in the download dialog (M3-17, Zusatz 1a): the choice
// between "Each scene separately" and "Merged per pass (job)" (M4-12b), mounted
// through the real dialog. No backend: `fetch` answers by route; jsdom has no
// `EventSource`, so a placed job is followed by polling.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import { bboxToPolygon } from '../geoUtils';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import { setTrackerOptions, useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection, StacItem } from '../types';
import DownloadDialog from './DownloadDialog';
import { TOO_MANY_SCENES } from './MosaicJobs';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const JOB = 'AbCdEfGhIjKlMnOpQrSt_-';
const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const EACH = 'Each scene separately';
const MERGED = 'Merged per pass (job)';
const START = 'Start job';

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

// Two passes: three scenes and a lone scene.
function open(tier = 'processing', band?: Record<string, unknown>, aoi: GeoJSON.Polygon | null = null) {
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
    aoi,
    downloadDialogLayerId: null,
    downloadSelection: false,
    downloadOutcome: null,
    downloadOriginalLinks: null,
    downloadPasses: null,
    error: null,
  });
  useAppStore.getState().openDownloadForSelection('originals');
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

async function press(label: string) {
  act(() => buttons(label)[0].dispatchEvent(new MouseEvent('click', { bubbles: true })));
  await flush();
}

async function showMerged() {
  await show();
  await press(MERGED);
}

const placed = () => fetchMock.mock.calls.filter(([u, init]) => String(u).endsWith('/execution') && init?.method === 'POST');
const linksShown = () => [...container.querySelectorAll('.dialog-original-links a')].map((a) => a.textContent).sort();

describe('the choice (Zusatz 1a)', () => {
  it('asks how several scenes are loaded, preselects nothing and loads nothing before the answer', async () => {
    open();
    await show();
    expect(container.querySelector('[role="group"]')?.textContent).toContain('How do you want the original files?');
    expect(buttons(EACH)).toHaveLength(1);
    expect(buttons(MERGED)).toHaveLength(1);
    expect(container.querySelector('.dialog-original-links')).toBeNull();
    expect(container.querySelector('.dialog-mosaics')).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('does not ask for one scene: its link, no choice', async () => {
    open();
    useAppStore.setState({
      downloadPasses: [{ label: 'x', items: [scene('S2_A')] }],
      downloadOriginalLinks: [{ itemId: 'S2_A', groupLabel: 'x', asset: 'visual', href: 'https://data.test/S2_A.tif' }],
    });
    await show();
    expect(buttons(EACH)).toHaveLength(0);
    expect(linksShown()).toEqual(['S2_A · visual']);
    expect(container.textContent).not.toContain('Save link list');
  });

  it('asks with an AOI drawn too: the originals do not depend on it', async () => {
    open('processing', undefined, bboxToPolygon([10.2, 50.2, 10.4, 50.4]));
    await show();
    expect(buttons(MERGED)).toHaveLength(1);
    await press(MERGED);
    await press(START);
    expect(JSON.parse(placed()[0][1].body).inputs.recipe).not.toHaveProperty('aoi');
  });

  it('is not made for the crop: with an AOI the crop merges by itself', async () => {
    open();
    useAppStore.setState({ downloadOutcome: 'crop' });
    await show();
    expect(container.querySelector('.dialog-originals')).toBeNull();
    expect(buttons(MERGED)).toHaveLength(0);
  });

  it('"Each scene separately" lists the links by pass, with no job', async () => {
    open();
    await show();
    await press(EACH);
    expect(linksShown()).toEqual(['S2_A · visual', 'S2_B · visual', 'S2_C · visual', 'S2_D · visual']);
    expect(container.querySelector('.dialog-mosaics')).toBeNull();
    expect(placed()).toHaveLength(0);
  });

  it('"Change" goes back to the question, and a job started stays in sight', async () => {
    open();
    await showMerged();
    await press(START);
    expect(container.querySelector('.dialog-mosaics .pp-job')).not.toBeNull();
    await press('Change');
    expect(buttons(EACH)).toHaveLength(1);
    expect(container.querySelector('.dialog-mosaics')).toBeNull();
    await press(MERGED);
    expect(container.querySelector('.dialog-mosaics .pp-job')).not.toBeNull();
    expect(buttons(START)[0].disabled).toBe(true);
    expect(placed()).toHaveLength(1);
  });

  it('keeps "Each scene separately" below the licence tier processing, and says why the merge is not offered', async () => {
    open('catalog');
    await show();
    expect(buttons(MERGED)[0].disabled).toBe(true);
    expect(container.querySelector('[role="group"]')?.textContent).toContain('licence does not permit processing');
    expect(container.textContent).not.toContain('Contains modified');
    await press(EACH);
    expect(linksShown()).toHaveLength(4);
    expect(placed()).toHaveLength(0);
  });
});

describe('Save link list', () => {
  let blobs: Blob[];
  let clicked: HTMLAnchorElement[];

  beforeEach(() => {
    blobs = [];
    clicked = [];
    vi.stubGlobal(
      'URL',
      Object.assign(URL, {
        createObjectURL: vi.fn((blob: Blob) => {
          blobs.push(blob);
          return 'blob:x';
        }),
        revokeObjectURL: vi.fn(),
      }),
    );
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('saves one address per line, only the links the dialog shows, under a name without AOI or scene', async () => {
    open('processing', undefined, bboxToPolygon([10.2, 50.2, 10.4, 50.4]));
    await show();
    await press(EACH);
    await press('Save link list');
    expect(clicked).toHaveLength(1);
    expect(clicked[0].download).toBe('sentinel-2-c1-l2a-original-links.txt');
    const text = await blobs[0].text();
    expect(text.split('\n').slice(0, -1).sort()).toEqual(
      ['S2_A', 'S2_B', 'S2_C', 'S2_D'].map((id) => `https://data.test/${id}.tif`),
    );
    expect(text.endsWith('\n')).toBe(true);
    expect(text).not.toMatch(/50\.2|coordinates/);
  });

  it('leaves a link on a host the dataset does not name out of the file and the list', async () => {
    open();
    const stray = scene('S2_X');
    stray.assets.visual.href = 'https://elsewhere.invalid/x.tif';
    useAppStore.setState({
      downloadOriginalLinks: [
        { itemId: 'S2_A', groupLabel: 'a', asset: 'visual', href: 'https://data.test/S2_A.tif' },
        { itemId: 'S2_B', groupLabel: 'a', asset: 'visual', href: 'https://data.test/S2_B.tif' },
      ],
    });
    await show();
    await press(EACH);
    await press('Save link list');
    expect(await blobs[0].text()).toBe('https://data.test/S2_A.tif\nhttps://data.test/S2_B.tif\n');
  });

  it('is not offered with nothing, or one file, to save', async () => {
    open();
    useAppStore.setState({ downloadOriginalLinks: [] });
    await show();
    await press(EACH);
    expect(buttons('Save link list')).toHaveLength(0);
    expect(container.textContent).toContain('No original file of this selection could be linked');
  });
});

describe('Merged per pass (job)', () => {
  it('makes the offer for a pass of several scenes and links the file of a lone scene', async () => {
    open();
    await showMerged();
    expect(buttons(START)).toHaveLength(1);
    const text = container.querySelector('.dialog-mosaics')?.textContent ?? '';
    expect(text).toContain('2026-07-01 · 3 scenes');
    expect(text).toContain('2026-07-02 · 1 scene');
    const own = container.querySelector('.dialog-mosaics a') as HTMLAnchorElement;
    expect(own.textContent).toBe('S2_D · visual');
    expect(own.getAttribute('href')).toBe('https://data.test/S2_D.tif');
  });

  it('says so for a lone scene whose file cannot be linked', async () => {
    open();
    useAppStore.setState({ downloadOriginalLinks: [] });
    await showMerged();
    expect(container.querySelector('.dialog-mosaics')?.textContent).toContain('No direct link to this scene’s file');
  });

  it('waits for what a job takes, then enables the button', async () => {
    let answer!: (r: Response) => void;
    routes['GET /processing/processes/recipe?dataset=sentinel-2-c1-l2a'] = () =>
      new Promise((resolve) => {
        answer = resolve;
      });
    open();
    await showMerged();
    expect(buttons(START)[0].disabled).toBe(true);
    expect(container.textContent).toContain('Loading what a job takes');
    answer(json(s2));
    await flush();
    expect(buttons(START)[0].disabled).toBe(false);
  });

  it('says so when what a job takes cannot be loaded', async () => {
    routes['GET /processing/processes/recipe?dataset=sentinel-2-c1-l2a'] = () => json({ detail: 'down' }, 503);
    open();
    await showMerged();
    expect(buttons(START)[0].disabled).toBe(true);
    expect(container.textContent).toContain('could not be asked what a job takes');
  });

  it('shows the attribution for modified data under the offer', async () => {
    open();
    await showMerged();
    expect(container.querySelector('.dialog-mosaics')?.textContent).toContain('Contains modified Copernicus Sentinel data');
  });

  it('locks a pass over 25 scenes with the reason and starts nothing', async () => {
    open();
    const many = Array.from({ length: 26 }, (_, i) => scene(`S2_M${String(i).padStart(2, '0')}`));
    useAppStore.setState({ downloadPasses: [{ label: '2026-07-03', items: many }] });
    await showMerged();
    expect(buttons(START)[0].disabled).toBe(true);
    expect(buttons(START)[0].title).toBe(TOO_MANY_SCENES);
    expect(container.querySelector('.dialog-mosaics')?.textContent).toContain(TOO_MANY_SCENES);
    expect(placed()).toHaveLength(0);
  });

  it('takes a pass of exactly 25 scenes', async () => {
    open();
    const full = Array.from({ length: 25 }, (_, i) => scene(`S2_M${String(i).padStart(2, '0')}`));
    useAppStore.setState({ downloadPasses: [{ label: '2026-07-03', items: full }] });
    await showMerged();
    expect(buttons(START)[0].disabled).toBe(false);
  });
});

describe('starting the job', () => {
  it('sends the whole scenes of the pass: one sorted group, no AOI, no steps, the type the item states', async () => {
    open();
    await showMerged();
    await press(START);
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
    await showMerged();
    await press(START);
    expect(JSON.parse(placed()[0][1].body).inputs.recipe.output.dtype).toBe('float32');
  });

  it('shows the job with the row of the processing panel, and the button waits for it', async () => {
    open();
    await showMerged();
    await press(START);
    expect(container.querySelector('.dialog-mosaics .pp-job')?.textContent).toMatch(/Waiting for a worker|Running/);
    expect(buttons(START)[0].disabled).toBe(true);
    expect(useProcessingStore.getState().jobs.map((j) => j.jobID)).toEqual([JOB]);
  });

  it('can order the pass again once the row is removed', async () => {
    open();
    await showMerged();
    await press(START);
    act(() => useProcessingStore.getState().removeJob(JOB));
    await flush();
    expect(buttons(START)[0].disabled).toBe(false);
  });

  it.each([
    [413, 'the estimated size is over the cap of 5 GB; order fewer scenes'],
    [422, 'scenes of another pass: S2_B; a mosaic is made of one pass'],
    [403, 'the licence of this dataset does not allow processing'],
  ])('shows a %i of the server as it is, adds no job, and lets the user try again', async (status, detail) => {
    routes['POST /processing/processes/recipe/execution'] = () =>
      json({ type: 'about:blank', title: 'Refused', status, detail }, status);
    open();
    await showMerged();
    await press(START);
    expect(container.querySelector('.dialog-mosaics [role="alert"]')?.textContent).toBe(detail);
    expect(useProcessingStore.getState().jobs).toEqual([]);
    expect(buttons(START)[0].disabled).toBe(false);
  });

  it('shows a network failure instead of throwing', async () => {
    routes['POST /processing/processes/recipe/execution'] = () => {
      throw new TypeError('Failed to fetch');
    };
    open();
    await showMerged();
    await press(START);
    expect(container.querySelector('.dialog-mosaics [role="alert"]')?.textContent).toContain('Failed to fetch');
  });
});
