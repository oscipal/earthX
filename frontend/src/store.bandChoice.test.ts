// @vitest-environment jsdom
//
// The choice of bands and files in the download dialog (NM4-75) as the store carries it into the request of a crop and into the job of
// whole scenes. `fetch` answers by route; the browser's own save is replaced by a spy.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { bandsCollection, bandsItem } from './fixtures/bandsScene';
import { useAppStore } from './store';
import type { StacItem } from './types';

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10.1, 50.1], [10.2, 50.1], [10.2, 50.2], [10.1, 50.2], [10.1, 50.1]]] };
const DEFAULT_BANDS = ['a_blue', 'a_red', 'a_edge', 'a_coast', 'scl'];
const JOB = 'AAAAAAAAAAAAAAAAAAAAAA';
const ESTIMATE = { estimate: { size: 2_000_000, duration: 'PT5S', outputPixels: 1, inputPixels: 1, inputBytes: 1, assets: 1, units: 1 }, skippedItems: [] };
const RESAMPLING = { grid: { resolution: 10, crs: null }, method: 'nearest', bands: [{ band: 'B05', resolution: 20, crs: null }], scenes: null };

const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });
const zip = () => new Response(new Blob(['zip-bytes']), { status: 200, headers: { 'X-Total-Groups': '1', 'X-Skipped-Groups': '0' } });

interface Call {
  method: string;
  url: string;
  body?: Record<string, unknown>;
}
let calls: Call[];
let routes: { estimate: () => Response; download: () => Response };
const downloads = () => calls.filter((c) => c.url.endsWith('/download'));
const estimates = () => calls.filter((c) => c.url.endsWith('/estimate'));
const placed = () => calls.filter((c) => c.url.endsWith('/execution'));

function open(kind: 'crop' | 'originals', groups?: StacItem[][]) {
  const lists = groups ?? [[bandsItem('S1')]];
  const items = lists.flat();
  useAppStore.setState({
    datasets: datasetsFrom([bandsCollection()]),
    datasetId: 'made-up-bands',
    items,
    groups: lists.map((list, i) => ({ key: [`g${i}`], label: `Pass ${i + 1}`, items: list })),
    activeGroupIndex: 0,
    selectedIds: items.map((it) => it.id),
    aoi: AOI,
    layers: [],
    downloadDialogLayerId: null,
    downloadSelection: false,
    downloadOutcome: null,
    downloading: false,
    error: null,
    notice: null,
  });
  useAppStore.getState().openDownloadForSelection(kind);
}

beforeEach(() => {
  calls = [];
  routes = { estimate: () => json(ESTIMATE), download: () => zip() };
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      calls.push({ method, url, ...(init?.body ? { body: JSON.parse(String(init.body)) } : {}) });
      if (url.endsWith('/download')) return routes.download();
      if (url.endsWith('/estimate')) return routes.estimate();
      if (url.endsWith('/execution')) return json({ jobID: JOB, status: 'accepted', message: '', progress: 0, expires: '2026-12-01T00:00:00Z' });
      if (url.endsWith(`/jobs/${JOB}`)) return json({ jobID: JOB, status: 'successful', message: '', progress: 100, expires: '2026-12-01T00:00:00Z' });
      return json({ detail: 'not found' }, 404);
    }),
  );
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() }));
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
});

afterEach(() => {
  useAppStore.getState().closeDownloadDialog();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('opening the dialog', () => {
  it('reads the table from the first scene and ticks the spectral bands and the mask layer, one file per band', () => {
    open('crop');
    const s = useAppStore.getState();
    expect(s.downloadItem?.id).toBe('S1');
    expect(s.downloadBands).toEqual(DEFAULT_BANDS);
    expect(s.downloadForm).toBe('per_band');
    expect(s.downloadCommonResolution).toBeNull();
  });

  it('starts afresh each time: the choice of the last dialog is not kept', () => {
    open('crop');
    useAppStore.getState().setDownloadBands(['a_red']);
    useAppStore.getState().setDownloadForm('multi_band');
    useAppStore.getState().closeDownloadDialog();
    expect(useAppStore.getState().downloadBands).toEqual([]);
    open('crop');
    expect(useAppStore.getState().downloadBands).toEqual(DEFAULT_BANDS);
    expect(useAppStore.getState().downloadForm).toBe('per_band');
  });

  it('a switch to another form puts the coarser factor back to native: only one file per band has it', () => {
    open('crop');
    useAppStore.getState().setDownloadResolution(4);
    useAppStore.getState().setDownloadForm('per_resolution');
    expect(useAppStore.getState().downloadResolution).toBe(1);
    useAppStore.getState().setDownloadForm('per_band');
    useAppStore.getState().setDownloadResolution(4);
    useAppStore.getState().setDownloadForm('per_band');
    expect(useAppStore.getState().downloadResolution).toBe(4);
  });
});

describe('the crop request', () => {
  it('one file per band: the form, the ticked assets in the order of the item, the factor; no common resolution', async () => {
    open('crop');
    useAppStore.getState().setDownloadBands(['scl', 'a_red']);
    useAppStore.getState().setDownloadResolution(2);
    await useAppStore.getState().confirmDownload();
    expect(downloads()).toHaveLength(1);
    expect(downloads()[0].body).toEqual({ groups: [['S1']], assets: ['a_red', 'scl'], aoi: AOI, resolution: 2, form: 'per_band' });
  });

  it('one file per resolution: the form and a factor of 1, no common resolution', async () => {
    open('crop');
    useAppStore.getState().setDownloadResolution(4);
    useAppStore.getState().setDownloadForm('per_resolution');
    await useAppStore.getState().confirmDownload();
    expect(downloads()[0].body).toEqual({ groups: [['S1']], assets: DEFAULT_BANDS, aoi: AOI, resolution: 1, form: 'per_resolution' });
    expect(downloads()[0].body).not.toHaveProperty('common_resolution');
  });

  it('one multi-band file: the common resolution, by default the finest of the ticked bands', async () => {
    open('crop');
    useAppStore.getState().setDownloadForm('multi_band');
    await useAppStore.getState().confirmDownload();
    expect(downloads()[0].body).toMatchObject({ form: 'multi_band', common_resolution: 10, resolution: 1, assets: DEFAULT_BANDS });
  });

  it('the default follows the ticks, and a resolution that was picked stays picked', async () => {
    open('crop');
    useAppStore.getState().setDownloadForm('multi_band');
    useAppStore.getState().setDownloadBands(['a_edge', 'a_coast']);
    await useAppStore.getState().confirmDownload();
    expect(downloads()[0].body?.common_resolution).toBe(20);
    useAppStore.getState().setDownloadCommonResolution(60);
    await useAppStore.getState().confirmDownload();
    expect(downloads()[1].body?.common_resolution).toBe(60);
  });

  it('with no band ticked nothing is sent, and the reason is told', async () => {
    open('crop');
    useAppStore.getState().setDownloadBands([]);
    await useAppStore.getState().confirmDownload();
    expect(downloads()).toHaveLength(0);
    expect(useAppStore.getState().error).toBe('Tick at least one band.');
  });

  it('one multi-band file with a band of no known pixel size sends nothing', async () => {
    const item = bandsItem('S1');
    delete item.assets.aerosol.gsd;
    open('crop', [[item]]);
    useAppStore.getState().setDownloadForm('multi_band');
    useAppStore.getState().setDownloadBands(['a_red', 'aerosol']);
    await useAppStore.getState().confirmDownload();
    expect(downloads()).toHaveLength(0);
    expect(useAppStore.getState().error).toMatch(/no known pixel size/);
    useAppStore.getState().setDownloadForm('per_band');
    await useAppStore.getState().confirmDownload();
    expect(downloads()).toHaveLength(1);
  });

  it('a dataset whose scenes list no GeoTIFF band sends the request of before: its default asset, no form', async () => {
    const plain: StacItem = { id: 'S1', properties: {}, assets: { visual: { href: 'https://data.test/S1.tif' } } };
    open('crop', [[plain]]);
    expect(useAppStore.getState().downloadBands).toEqual([]);
    await useAppStore.getState().confirmDownload();
    expect(downloads()[0].body).toEqual({ groups: [['S1']], assets: ['visual'], aoi: AOI, resolution: 1 });
  });

  it('the layout goes with the offer of an export job when the crop is too large, for every form', async () => {
    routes.download = () => json({ detail: 'This download would be about 1.8 GB.' }, 413, { 'X-Export-Job': 'available' });
    open('crop');
    useAppStore.getState().setDownloadForm('multi_band');
    await useAppStore.getState().confirmDownload();
    expect(useAppStore.getState().downloadExportOffer?.request).toMatchObject({ assets: DEFAULT_BANDS, layout: { form: 'multi_band', resolution_m: 10 } });
    useAppStore.getState().setDownloadForm('per_band');
    expect(useAppStore.getState().downloadExportOffer).toBeNull();
    await useAppStore.getState().confirmDownload();
    expect(useAppStore.getState().downloadExportOffer?.request.layout).toEqual({ form: 'per_band' });
  });
});

describe('the resampling warning before a crop (NM4-65 part 7)', () => {
  it('is asked only where something may be resampled: another form than one file per band, or a mosaic', async () => {
    open('crop');
    await useAppStore.getState().confirmDownload();
    expect(estimates()).toHaveLength(0);
    useAppStore.getState().setDownloadForm('per_resolution');
    await useAppStore.getState().confirmDownload();
    expect(estimates()).toHaveLength(1);
    expect(downloads()).toHaveLength(2);
    expect((estimates()[0].body as { inputs: { recipe: { output: object } } }).inputs.recipe.output).toMatchObject({ layout: { form: 'per_resolution' } });
  });

  it('a mosaic of one file per band is asked too; a single scene is not', async () => {
    open('crop', [[bandsItem('S1'), bandsItem('S2')]]);
    await useAppStore.getState().confirmDownload();
    expect(estimates()).toHaveLength(1);
  });

  it('waits for "Continue" when the platform says something is resampled, and sends nothing before', async () => {
    routes.estimate = () => json({ ...ESTIMATE, resampling: RESAMPLING });
    open('crop');
    useAppStore.getState().setDownloadForm('multi_band');
    await useAppStore.getState().confirmDownload();
    expect(useAppStore.getState().downloadResampling).toHaveLength(1);
    expect(downloads()).toHaveLength(0);
    useAppStore.getState().confirmResampling();
    await vi.waitFor(() => expect(downloads()).toHaveLength(1));
    expect(useAppStore.getState().downloadResampling).toBeNull();
    expect(downloads()[0].body).toMatchObject({ form: 'multi_band', common_resolution: 10 });
  });

  it('"Cancel" sends nothing and leaves the dialog as it was, free to try again', async () => {
    routes.estimate = () => json({ ...ESTIMATE, resampling: RESAMPLING });
    open('crop');
    useAppStore.getState().setDownloadForm('multi_band');
    await useAppStore.getState().confirmDownload();
    useAppStore.getState().declineResampling();
    expect(downloads()).toHaveLength(0);
    expect(useAppStore.getState().downloadResampling).toBeNull();
    expect(useAppStore.getState().downloading).toBe(false);
    expect(useAppStore.getState().downloadSelection).toBe(true);
  });

  it('a refused estimate does not stop the download: the server has the last word', async () => {
    routes.estimate = () => json({ detail: 'no' }, 500);
    open('crop');
    useAppStore.getState().setDownloadForm('per_resolution');
    await useAppStore.getState().confirmDownload();
    expect(downloads()).toHaveLength(1);
  });
});

describe('whole scenes', () => {
  it('one file per band is loaded in the browser: "Download" sets it going and asks the platform for nothing', async () => {
    open('originals');
    expect(useAppStore.getState().downloadStarted).toBe(false);
    await useAppStore.getState().confirmDownload();
    expect(useAppStore.getState().downloadStarted).toBe(true);
    expect(calls).toEqual([]);
  });

  it('with no band ticked nothing starts', async () => {
    open('originals');
    useAppStore.getState().setDownloadBands([]);
    await useAppStore.getState().confirmDownload();
    expect(useAppStore.getState().downloadStarted).toBe(false);
  });

  it('another form asks what the job will cost once the choice has rested, and for each change anew', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    open('originals');
    useAppStore.getState().setDownloadForm('per_resolution');
    expect(useAppStore.getState().downloadJobNote).toEqual({ state: 'estimating' });
    useAppStore.getState().setDownloadBands(['a_red', 'a_blue']);
    await vi.advanceTimersByTimeAsync(400);
    expect(estimates()).toHaveLength(1);
    expect(useAppStore.getState().downloadJobNote).toMatchObject({ state: 'ready', text: 'About 2.0 MB · about 5 s' });
    useAppStore.getState().setDownloadForm('per_band');
    expect(useAppStore.getState().downloadJobNote).toBeNull();
    await vi.advanceTimersByTimeAsync(400);
    expect(estimates()).toHaveLength(1);
  });

  it('one file per resolution is a job with the layout, the ticked assets, the passes, and no AOI; the browser downloads its ZIP', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    open('originals', [[bandsItem('S1'), bandsItem('S2')], [bandsItem('S3')]]);
    useAppStore.getState().setDownloadForm('per_resolution');
    await vi.advanceTimersByTimeAsync(400);
    await useAppStore.getState().confirmDownload();
    expect(placed()).toHaveLength(1);
    const recipe = (placed()[0].body as { inputs: { recipe: Record<string, unknown> } }).inputs.recipe;
    expect(recipe).not.toHaveProperty('aoi');
    expect(recipe.inputs).toEqual([{ name: 'input', dataset: 'made-up-bands', groups: [['S1', 'S2'], ['S3']], assets: DEFAULT_BANDS }]);
    expect(recipe.output).toMatchObject({ kind: 'crop', layout: { form: 'per_resolution' } });
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
    expect(useAppStore.getState().downloadSelection).toBe(false);
    expect(useAppStore.getState().notice).toMatch(/^Downloaded /);
  });

  it('one multi-band file carries the common resolution into the job', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    open('originals');
    useAppStore.getState().setDownloadForm('multi_band');
    useAppStore.getState().setDownloadCommonResolution(20);
    await vi.advanceTimersByTimeAsync(400);
    await useAppStore.getState().confirmDownload();
    const recipe = (placed()[0].body as { inputs: { recipe: { output: object } } }).inputs.recipe;
    expect(recipe.output).toMatchObject({ layout: { form: 'multi_band', resolution_m: 20 } });
  });

  it('nothing is placed before the estimate is in, nor when the platform refuses the estimate', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    open('originals');
    useAppStore.getState().setDownloadForm('per_resolution');
    await useAppStore.getState().confirmDownload();
    expect(placed()).toHaveLength(0);
    routes.estimate = () => json({ detail: 'at most 25 items' }, 413);
    useAppStore.getState().setDownloadBands(['a_red']);
    await vi.advanceTimersByTimeAsync(400);
    expect(useAppStore.getState().downloadJobNote).toMatchObject({ state: 'blocked' });
    await useAppStore.getState().confirmDownload();
    expect(placed()).toHaveLength(0);
  });

  it('asks the person first where the platform resamples, and places the job on "Continue" only', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    routes.estimate = () => json({ ...ESTIMATE, resampling: RESAMPLING });
    open('originals');
    useAppStore.getState().setDownloadForm('multi_band');
    await vi.advanceTimersByTimeAsync(400);
    await useAppStore.getState().confirmDownload();
    expect(useAppStore.getState().downloadResampling).toHaveLength(1);
    expect(placed()).toHaveLength(0);
    useAppStore.getState().declineResampling();
    expect(placed()).toHaveLength(0);
    await useAppStore.getState().confirmDownload();
    useAppStore.getState().confirmResampling();
    await vi.advanceTimersByTimeAsync(10);
    await vi.waitFor(() => expect(placed()).toHaveLength(1));
  });

  it('closing the dialog drops the estimate that is on its way', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    open('originals');
    useAppStore.getState().setDownloadForm('per_resolution');
    useAppStore.getState().closeDownloadDialog();
    await vi.advanceTimersByTimeAsync(400);
    expect(estimates()).toHaveLength(0);
    expect(useAppStore.getState().downloadJobNote).toBeNull();
  });
});
