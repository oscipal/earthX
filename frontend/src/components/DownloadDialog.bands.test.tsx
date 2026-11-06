// @vitest-environment jsdom
//
// The choice of bands and files in the download dialog (NM4-75), mounted through the real dialog: the list comes from the scene and
// the collection, "None" locks "Download", there is no row of resolution factors, the common resolution for one multi-band file
// only, and whole scenes start with "Download" and load only what is ticked.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from '../datasets';
import { bandsCollection, bandsItem, bandsResponse } from '../fixtures/bandsScene';
import { useAppStore } from '../store';
import type { StacItem } from '../types';
import DownloadDialog from './DownloadDialog';

const page = vi.hoisted(() => ({ jobs: [] as { zipName: string; files: { name: string; url: string }[]; texts: { name: string; content: string }[] }[] }));
vi.mock('../originalsClient', () => ({
  canStream: () => true,
  browserDeps: () => ({
    deps: {
      fetch: async () => new Response(null, { headers: { 'content-length': '1000' } }),
      zip: {
        run: async (job: (typeof page.jobs)[number]) => {
          page.jobs.push(job);
        },
      },
      saveBlob: () => undefined,
      navigate: () => undefined,
      now: () => new Date('2026-10-30T12:00:00Z'),
    },
    dispose: () => undefined,
  }),
}));

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10.1, 50.1], [10.2, 50.1], [10.2, 50.2], [10.1, 50.2], [10.1, 50.1]]] };
const JOB = 'AAAAAAAAAAAAAAAAAAAAAA';
const ESTIMATE = { estimate: { size: 2_000_000, duration: 'PT5S', outputPixels: 1, inputPixels: 1, inputBytes: 1, assets: 1, units: 1 }, skippedItems: [] };

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

let container: HTMLDivElement;
let root: Root;
let calls: { method: string; url: string; body?: Record<string, unknown> }[];
let estimate: () => Response;
let bands: () => Response;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  page.jobs.length = 0;
  calls = [];
  estimate = () => json(ESTIMATE);
  bands = () => json(bandsResponse());
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ method: init?.method ?? 'GET', url, ...(init?.body ? { body: JSON.parse(String(init.body)) } : {}) });
      if (url.endsWith('/bands')) return bands();
      if (url.endsWith('/download')) return new Response(new Blob(['x']), { status: 200 });
      if (url.endsWith('/estimate')) return estimate();
      if (url.endsWith('/execution')) return json({ jobID: JOB, status: 'accepted', message: '', progress: 0, expires: '2026-12-01T00:00:00Z' });
      if (url.endsWith(`/jobs/${JOB}`)) return json({ jobID: JOB, status: 'successful', message: '', progress: 100, expires: '2026-12-01T00:00:00Z' });
      return json({ detail: 'not found' }, 404);
    }),
  );
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() }));
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  useAppStore.getState().closeDownloadDialog();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function flush() {
  await act(async () => {
    for (let i = 0; i < 10; i++) await Promise.resolve();
  });
}

async function open(kind: 'crop' | 'originals', items: StacItem[] = [bandsItem('S1')]) {
  useAppStore.setState({
    datasets: datasetsFrom([bandsCollection()]),
    datasetId: 'made-up-bands',
    items,
    groups: [{ key: ['g'], label: 'Pass', items }],
    activeGroupIndex: 0,
    selectedIds: items.map((it) => it.id),
    aoi: AOI,
    layers: [],
    downloadDialogLayerId: null,
    downloadSelection: false,
    downloading: false,
    error: null,
    notice: null,
  });
  act(() => useAppStore.getState().openDownloadForSelection(kind));
  act(() => root.render(<DownloadDialog />));
  await flush();
  await flush();
}

const button = (label: string) => [...container.querySelectorAll('button')].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;
const click = async (el: Element | undefined) => {
  await act(async () => {
    el!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    for (let i = 0; i < 10; i++) await Promise.resolve();
  });
};
const boxes = () => [...container.querySelectorAll<HTMLInputElement>('.dialog-band input[type="checkbox"]')];
const ticked = () => container.querySelectorAll('.dialog-band input:checked').length;
const bandNames = () => [...container.querySelectorAll('.dialog-band-name')].map((e) => e.textContent);
const resolutionRow = () => container.querySelector('.dialog-resolution');
const downloadCalls = () => calls.filter((c) => c.url.endsWith('/download'));

describe('the list of bands', () => {
  it('is the bands of the scene as it describes them, with common name, wavelength and resolution', async () => {
    await open('crop');
    expect(bandNames()).toEqual(['B02', 'B04', 'B05', 'B01', 'scl', 'AOT']);
    const red = container.querySelectorAll('.dialog-band')[1];
    expect(red.textContent).toContain('red · 0.665 µm');
    expect(red.querySelector('.dialog-band-res')?.textContent).toBe('10 m');
    expect(red.getAttribute('data-tip')).toBe('a_red');
  });

  it('has the spectral bands and the layer of the mask ticked, and a band with no wavelength not', async () => {
    await open('crop');
    expect(boxes().map((b) => b.checked)).toEqual([true, true, true, true, true, false]);
    expect(container.textContent).toContain('5 of 6');
  });

  it('"None" locks "Download" and says why; "All" and a single tick open it again', async () => {
    await open('crop');
    expect(button('Download')!.disabled).toBe(false);
    await click(button('None'));
    expect(ticked()).toBe(0);
    expect(button('Download')!.disabled).toBe(true);
    expect(container.textContent).toContain('Tick at least one band.');
    await click(button('Download'));
    expect(downloadCalls()).toHaveLength(0);
    await click(button('All'));
    expect(ticked()).toBe(6);
    expect(button('Download')!.disabled).toBe(false);
    await click(button('None'));
    await click(boxes()[1]);
    expect(button('Download')!.disabled).toBe(false);
  });

  it('shows no list, says why, and still downloads as before where the platform cannot give the table', async () => {
    bands = () => json({ detail: 'down' }, 503);
    await open('crop');
    expect(container.querySelector('.dialog-bands')).toBeNull();
    expect(useAppStore.getState().error).toMatch(/Could not load the bands/);
    expect(button('Download')!.disabled).toBe(false);
  });

  it('locks "Download" while the table is on its way, and says so', async () => {
    let answer!: (r: Response) => void;
    bands = () => new Promise<Response>((resolve) => (answer = resolve)) as never;
    vi.mocked(fetch).mockImplementation(async (url) => {
      if (String(url).endsWith('/bands')) return new Promise<Response>((resolve) => (answer = resolve));
      return new Response(new Blob(['x']), { status: 200, headers: { 'x-total-groups': '1' } });
    });
    await open('crop');
    expect(container.textContent).toContain('Loading the bands');
    expect(button('Download')!.disabled).toBe(true);
    await act(async () => {
      answer(json(bandsResponse()));
      for (let i = 0; i < 10; i++) await Promise.resolve();
    });
    expect(container.textContent).not.toContain('Loading the bands');
    expect(button('Download')!.disabled).toBe(false);
  });

  it('shows no list for a dataset whose scenes list no band, and "Download" still works as before', async () => {
    bands = () => json({ bands: [] });
    await open('crop');
    expect(container.querySelector('.dialog-bands')).toBeNull();
    expect(container.querySelector('.dialog-forms')).toBeNull();
    expect(container.textContent).toContain('asset visual');
    expect(button('Download')!.disabled).toBe(false);
  });
});

describe('the form of the files', () => {
  const pressed = () => [...container.querySelectorAll('.dialog-forms button')].filter((b) => b.getAttribute('aria-pressed') === 'true').map((b) => b.textContent);

  it('starts with one file per band, which has no common resolution and no factor', async () => {
    await open('crop');
    expect([...container.querySelectorAll('.dialog-forms button')].map((b) => b.textContent)).toEqual(['One file per band', 'One file per resolution', 'One multi-band file']);
    expect(pressed()).toEqual(['One file per band']);
    expect(resolutionRow()).toBeNull();
    expect(container.querySelector('.dialog-common')).toBeNull();
  });

  it('one file per resolution has no factor and no common resolution', async () => {
    await open('crop');
    await click(button('One file per resolution'));
    expect(pressed()).toEqual(['One file per resolution']);
    expect(resolutionRow()).toBeNull();
    expect(container.querySelector('.dialog-common')).toBeNull();
  });

  it('one multi-band file has the common resolution, from the resolutions of the dataset, the finest of the ticked bands first, and no factor', async () => {
    await open('crop');
    await click(button('One multi-band file'));
    expect(resolutionRow()).toBeNull();
    const select = container.querySelector<HTMLSelectElement>('.dialog-common select')!;
    expect([...select.options].map((o) => o.textContent)).toEqual(['10 m', '20 m', '60 m']);
    expect(select.value).toBe('10');
    await click(button('None'));
    await click(boxes()[2]);
    await click(boxes()[3]);
    expect(container.querySelector<HTMLSelectElement>('.dialog-common select')!.value).toBe('20');
  });

  it('names behind (i) which ticked bands are converted and how, and follows the resolution picked', async () => {
    await open('crop');
    await click(button('One multi-band file'));
    const tip = () => container.querySelector('.dialog-common .tip')?.getAttribute('data-tip') ?? '';
    expect(tip()).toContain('Converted to 10 m');
    expect(tip()).toContain('nearest neighbour (values stay): B05 (20 m), B01 (60 m), scl (20 m)');
    const select = container.querySelector<HTMLSelectElement>('.dialog-common select')!;
    await act(async () => {
      select.value = '60';
      select.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(useAppStore.getState().downloadCommonResolution).toBe(60);
    expect(tip()).toContain('To a coarser grid, average: B02 (10 m), B04 (10 m), B05 (20 m)');
    expect(tip()).toContain('most frequent class: scl (20 m)');
  });

  it('has no row of resolution factors in any form, and none of the requests carries one', async () => {
    await open('crop');
    for (const form of ['One file per band', 'One file per resolution', 'One multi-band file']) {
      await click(button(form));
      expect(resolutionRow()).toBeNull();
      expect(container.querySelector('input[name="download-resolution"]')).toBeNull();
      expect(container.textContent).not.toMatch(/Native|2×|4×|10×/);
      await click(button('Download'));
    }
    expect(downloadCalls()).toHaveLength(3);
    for (const call of downloadCalls()) expect(call.body).not.toHaveProperty('resolution');
    expect(downloadCalls().map((c) => c.body?.form)).toEqual(['per_band', 'per_resolution', 'multi_band']);
    expect(downloadCalls().map((c) => 'common_resolution' in (c.body ?? {}))).toEqual([false, false, true]);
  });

  it('"Download" of one multi-band file sends the common resolution', async () => {
    await open('crop');
    await click(button('One multi-band file'));
    await click(button('Download'));
    expect(downloadCalls()[0].body).toMatchObject({ form: 'multi_band', common_resolution: 10 });
  });
});

describe('the form is asked only for bands of different resolutions', () => {
  const forms = () => container.querySelector('.dialog-forms');
  const pressed = () => [...container.querySelectorAll('.dialog-forms button[aria-pressed="true"]')].map((b) => b.textContent);

  it('shows the form (and for one multi-band file the common resolution) while the ticked bands differ, and hides them at one resolution', async () => {
    await open('crop');
    expect(forms()).not.toBeNull();
    expect(resolutionRow()).toBeNull();
    // B02 and B04: both 10 m.
    await click(button('None'));
    await click(boxes()[0]);
    await click(boxes()[1]);
    expect(forms()).toBeNull();
    expect(resolutionRow()).toBeNull();
    expect(container.querySelector('.dialog-common')).toBeNull();
    expect(button('Download')!.disabled).toBe(false);
    await click(boxes()[2]);
    expect(forms()).not.toBeNull();
    expect(resolutionRow()).toBeNull();
  });

  it('a single band has no form either, and ticking a band of another resolution brings it back at once', async () => {
    await open('crop');
    await click(button('None'));
    await click(boxes()[2]);
    expect(forms()).toBeNull();
    await click(boxes()[3]);
    expect(forms()).not.toBeNull();
    expect(pressed()).toEqual(['One file per band']);
    expect(resolutionRow()).toBeNull();
  });

  it('keeps the form that was chosen while it is hidden, and shows it again with its resolution', async () => {
    await open('crop');
    await click(button('One multi-band file'));
    await click(button('None'));
    await click(boxes()[0]);
    expect(forms()).toBeNull();
    expect(container.querySelector('.dialog-common')).toBeNull();
    await click(boxes()[4]);
    expect(pressed()).toEqual(['One multi-band file']);
    expect(container.querySelector('.dialog-common select')).not.toBeNull();
  });

  it('sends one file per resolution, no factor and no common resolution, for the bands of one resolution', async () => {
    await open('crop');
    await click(button('One multi-band file'));
    await click(button('None'));
    await click(boxes()[0]);
    await click(button('Download'));
    expect(downloadCalls()[0].body).toMatchObject({ form: 'per_resolution', assets: ['a_blue'] });
    expect(downloadCalls()[0].body).not.toHaveProperty('common_resolution');
  });

  it('whole scenes of one resolution show the estimate of the job and no choice; mixed ones list the bands for the browser', async () => {
    await open('originals');
    expect(forms()).not.toBeNull();
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    await click(button('None'));
    await click(boxes()[1]);
    expect(forms()).toBeNull();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    vi.useRealTimers();
    await flush();
    expect(container.textContent).toContain('About 2 MB · about 5 s');
    expect(container.querySelector('.dialog-originals')).toBeNull();
    await click(button('Download'));
    const recipe = (calls.find((c) => c.url.endsWith('/execution'))!.body as { inputs: { recipe: { output: object } } }).inputs.recipe;
    expect(recipe.output).toMatchObject({ layout: { form: 'per_resolution' } });
  });
});

describe('closing', () => {
  it('Escape closes nothing; the red x does', async () => {
    await open('crop');
    act(() => {
      container.querySelector('.dialog-panel')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });
    expect(useAppStore.getState().downloadSelection).toBe(true);
    expect(container.querySelector('.dialog-panel')).not.toBeNull();
    await click(container.querySelector('.results-head .close-x')!);
    expect(useAppStore.getState().downloadSelection).toBe(false);
  });

  // Otto, 03.11.2026 (UI-04 answer 2): a click beside a dialog closes nothing; it used to close it and stop a download in flight.
  it.each(['crop', 'originals'] as const)('a click beside the dialog of the %s closes nothing', async (kind) => {
    await open(kind);
    const panel = container.querySelector('.dialog-panel')!;
    await click(container.querySelector('.dialog-backdrop')!);
    expect(container.querySelector('.dialog-panel')).toBe(panel);
  });
});

describe('the resampling warning', () => {
  const RESAMPLING = { grid: { resolution: 10, crs: null }, method: 'nearest', bands: [{ band: 'B05', resolution: 20, crs: null }], scenes: null };

  it('comes before a crop that the platform resamples: "Cancel" sends nothing, "Continue" sends the crop', async () => {
    estimate = () => json({ ...ESTIMATE, resampling: RESAMPLING });
    await open('crop');
    await click(button('One multi-band file'));
    await click(button('Download'));
    expect(container.querySelector('[role="alertdialog"]')?.textContent).toContain('Values are resampled');
    expect(downloadCalls()).toHaveLength(0);
    await click([...container.querySelectorAll('[role="alertdialog"] button')].find((b) => b.textContent === 'Cancel'));
    expect(container.querySelector('[role="alertdialog"]')).toBeNull();
    expect(downloadCalls()).toHaveLength(0);
    expect(container.querySelector('.dialog-panel')).not.toBeNull();
    await click(button('Download'));
    await click([...container.querySelectorAll('[role="alertdialog"] button')].find((b) => b.textContent === 'Continue'));
    expect(downloadCalls()).toHaveLength(1);
  });

  it('is not shown where nothing is resampled', async () => {
    await open('crop');
    await click(button('One multi-band file'));
    await click(button('Download'));
    expect(container.querySelector('[role="alertdialog"]')).toBeNull();
    expect(downloadCalls()).toHaveLength(1);
  });
});

describe('whole scenes', () => {
  it('start with "Download", not by themselves, and list what they will load', async () => {
    await open('originals');
    expect(container.querySelector('h2')?.textContent).toBe('Download full scene');
    expect(container.querySelector('.dialog-original-row')).toBeNull();
    expect(page.jobs).toEqual([]);
    expect(container.querySelector('.dialog-originals > .hint')?.textContent).toBe('1 scene · 6 kB');
    expect(resolutionRow()).toBeNull();
  });

  it('one file per band loads only the ticked bands, in exports/ under the name of their content, with BANDS.txt', async () => {
    await open('originals');
    await click(button('None'));
    await click(boxes()[1]);
    await click(boxes()[4]);
    expect(container.querySelector('.dialog-originals > .hint')?.textContent).toBe('1 scene · 3 kB');
    await click(button('Download'));
    expect(page.jobs).toHaveLength(1);
    expect(page.jobs[0].zipName).toBe('S1.zip');
    expect(page.jobs[0].files.map((f) => f.name)).toEqual(['exports/B04_red_10m.tif', 'exports/scl_20m.tif', 'S1_granule_metadata.xml']);
    expect(page.jobs[0].texts.map((t) => t.name)).toEqual(['ATTRIBUTION.txt', 'item.json', 'exports/BANDS.txt']);
    expect(container.querySelector('.dialog-original-row')?.textContent).toContain('Done');
    // The list is gone once it runs, and "Download" with it.
    expect(container.querySelector('.dialog-bands')).toBeNull();
    expect(button('Download')).toBeUndefined();
  });

  it('one file per resolution starts a job with the layout and no AOI, after an estimate shown in the dialog', async () => {
    await open('originals');
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    await click(button('One file per resolution'));
    expect(container.querySelector('.dialog-originals')).toBeNull();
    expect(button('Download')!.disabled).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    vi.useRealTimers();
    await flush();
    expect(container.textContent).toContain('About 2 MB · about 5 s');
    expect(button('Download')!.disabled).toBe(false);
    await click(button('Download'));
    const placed = calls.filter((c) => c.url.endsWith('/execution'));
    expect(placed).toHaveLength(1);
    const recipe = (placed[0].body as { inputs: { recipe: { aoi?: unknown; output: object } } }).inputs.recipe;
    expect(recipe).not.toHaveProperty('aoi');
    expect(recipe.output).toMatchObject({ layout: { form: 'per_resolution' } });
    expect(page.jobs).toEqual([]);
  });

  it('a refusal of the estimate is told and locks "Download"', async () => {
    estimate = () => json({ detail: 'This order names 30 items; at most 25 fit in one order' }, 413);
    await open('originals');
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    await click(button('One multi-band file'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    vi.useRealTimers();
    await flush();
    expect(container.querySelector('[role="alert"]')?.textContent).toBe('Too large for one job');
    expect(button('Download')!.disabled).toBe(true);
  });
});

describe('a layer of the layer manager', () => {
  const layer = (itemIds: string[]) => ({
    id: 'L1',
    name: 'Made-up multispectral · day',
    visible: true,
    opacity: 1,
    overlays: [],
    restore: {
      focusMode: true,
      downloaded: { S1: { datasetId: 'made-up-bands', tileUrl: '/t/{z}/{x}/{y}', bounds: [10, 50, 11, 51], asset: 'a_red', baseAsset: 'a_red', minZoom: 0, maxZoom: 14 } },
      appliedRender: {},
      activeGroupIndex: 0,
      selectedIds: [],
      itemIds,
      groupItemIds: [itemIds],
      aoi: AOI,
      cropToAoi: true,
      datasetId: 'made-up-bands',
    },
  });

  async function openLayer(answer: Promise<Response>) {
    vi.mocked(fetch).mockImplementation(async (url, init) => {
      calls.push({ method: init?.method ?? 'GET', url: String(url), ...(init?.body ? { body: JSON.parse(String(init.body)) } : {}) });
      if (String(url).endsWith('/bands')) return answer;
      return new Response(new Blob(['x']), { status: 200 });
    });
    useAppStore.setState({ datasets: datasetsFrom([bandsCollection()]), layers: [layer(['S1', 'S2'])] as never });
    act(() => root.render(<DownloadDialog />));
    let opening!: Promise<void>;
    act(() => {
      opening = useAppStore.getState().openDownloadDialog('L1');
    });
    await flush();
    return { opening };
  }

  it('asks the platform for the bands of the layer\'s scenes; "Download" waits until the table is there', async () => {
    let answer!: (r: Response) => void;
    const { opening } = await openLayer(new Promise<Response>((resolve) => (answer = resolve)));
    expect(container.textContent).toContain('Loading the bands');
    expect(button('Download')!.disabled).toBe(true);
    await act(async () => {
      answer(json(bandsResponse()));
      await opening;
      for (let i = 0; i < 10; i++) await Promise.resolve();
    });
    expect(container.textContent).not.toContain('Loading the bands');
    expect(bandNames()).toEqual(['B02', 'B04', 'B05', 'B01', 'scl', 'AOT']);
    expect(button('Download')!.disabled).toBe(false);
    await click(button('Download'));
    expect(downloadCalls()[0].body).toMatchObject({ groups: [['S1', 'S2']], assets: ['a_blue', 'a_red', 'a_edge', 'a_coast', 'scl'], form: 'per_band' });
    const asked = calls.filter((c) => c.url.endsWith('/bands'));
    expect(asked).toHaveLength(1);
    expect(asked[0].body).toEqual({ items: ['S1', 'S2'] });
    // No scene is fetched for it: the platform tells.
    expect(calls.some((c) => c.url.startsWith('/stac/'))).toBe(false);
  });

  it('says so when the table cannot be had, and offers no list', async () => {
    const { opening } = await openLayer(Promise.resolve(json({ detail: 'down' }, 503)));
    await act(async () => {
      await opening;
      for (let i = 0; i < 10; i++) await Promise.resolve();
    });
    expect(useAppStore.getState().error).toMatch(/Could not load the bands/);
    expect(container.querySelector('.dialog-bands')).toBeNull();
  });
});
