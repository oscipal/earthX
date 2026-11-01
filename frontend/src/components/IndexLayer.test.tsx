// @vitest-environment jsdom
//
// A layer that shows an index (NM4-14b, Otto 1.11.2026): the layer manager does not choose an index again (the view of a layer shows
// the one it was added with, and a layer without one has no dropdown), its ⇩ downloads the index as a Processing job would give it
// without a job to see, and the dialog says so.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from '../datasets';
import { SENTINEL_2_PRESETS } from '../fixtures/indexPresets';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import type { MapLayer } from '../layers';
import { useProcessingStore } from '../processingStore';
import { useAppStore, type AppState } from '../store';
import type { Collection, DownloadedInfo, StacItem } from '../types';
import DownloadDialog from './DownloadDialog';
import LayerManager from './LayerManager';
import ViewerControls from './ViewerControls';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const JOB = 'AAAAAAAAAAAAAAAAAAAAAA';
const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10.1, 50.1], [10.2, 50.1], [10.2, 50.2], [10.1, 50.2], [10.1, 50.1]]] };
const collection = {
  id: 'sentinel-2-c1-l2a',
  title: 'Sentinel-2 L2A',
  'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
  'earthx:license_flags': { tier: 'processing', license: 'CC-BY-4.0' },
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
  'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
  'earthx:band_units': { red: 'reflectance', green: 'reflectance', blue: 'reflectance', nir: 'reflectance', visual: null },
  'earthx:index_presets': SENTINEL_2_PRESETS,
} as unknown as Collection;
const info = (id: string): DownloadedInfo => ({ datasetId: 'sentinel-2-c1-l2a', tileUrl: `/t/${id}/{z}/{x}/{y}`, bounds: [10, 50, 11, 51], asset: 'visual', minZoom: 8, maxZoom: 14 });
const item = (id: string): StacItem => ({ id, collection: 'sentinel-2-c1-l2a', bbox: [10, 50, 11, 51], properties: { datetime: '2026-07-01T10:00:00Z' }, assets: {} });
const NDVI = { index: 'NDVI', colormapName: 'rdylgn', rescale: '-1,1' };

const layer = (look: object, over: Partial<MapLayer['restore']> = {}): MapLayer => ({
  id: 'L1',
  name: 'Sentinel-2 L2A · day',
  visible: true,
  opacity: 1,
  overlays: [{ kind: 'raster', tileUrl: '/t/S1/{z}/{x}/{y}', bounds: [10, 50, 11, 51], minZoom: 8, maxZoom: 14 }],
  restore: {
    focusMode: true,
    downloaded: { S1: info('S1') },
    appliedRender: look,
    activeGroupIndex: 0,
    selectedIds: ['S1'],
    itemIds: ['S1'],
    groupItemIds: [['S1']],
    aoi: AOI,
    cropToAoi: true,
    datasetId: 'sentinel-2-c1-l2a',
    ...over,
  },
});

let container: HTMLDivElement;
let root: Root;
let clicked: string[];

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const status = (state: string) => ({ jobID: JOB, status: state, progress: 100, message: '', expires: '2026-12-01T00:00:00Z' });
let fetchMock: ReturnType<typeof vi.fn>;
const ESTIMATE = { estimate: { size: 12_400_000, duration: 'PT9.2S', outputPixels: 1_000_000, inputPixels: 4_000_000, inputBytes: 8_000_000, assets: 2, units: 1 }, skippedItems: [] };

function setState(over: Partial<AppState> = {}) {
  act(() => {
    useAppStore.setState({
      datasets: datasetsFrom([collection]),
      datasetId: 'sentinel-2-c1-l2a',
      items: [item('S1')],
      groups: [{ key: ['a'], label: 'a', items: [item('S1')] }],
      downloaded: { S1: info('S1') },
      focusMode: true,
      cropToAoi: true,
      viewAoi: AOI,
      showDownloaded: true,
      shownImage: null,
      viewLooks: {},
      savedLooks: {},
      appliedRender: NDVI,
      pendingColormapName: 'rdylgn',
      pendingVmin: '-1',
      pendingVmax: '1',
      pendingIndex: (over.appliedRender ?? NDVI).index ?? '',
      mosaics: {},
      mapZoom: 12,
      selectedIds: [],
      layers: [],
      viewLayerId: null,
      viewOfLayer: false,
      dock: 'layers',
      downloadDialogLayerId: null,
      downloadSelection: false,
      downloadOutcome: null,
      downloading: false,
      error: null,
      notice: null,
      ...over,
    });
  });
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  clicked = [];
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.startsWith('/processing/processes/recipe?')) return json(s2);
    if (init?.method === 'POST' && url.endsWith('/estimate')) return json(ESTIMATE);
    if (init?.method === 'POST' && url.endsWith('/execution')) return json({ ...status('accepted'), progress: 0 });
    if (url === `/processing/jobs/${JOB}`) return json(status('successful'));
    return json({ detail: 'not found' }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    clicked.push(this.getAttribute('href') ?? '');
  });
  useProcessingStore.setState({ jobs: [], open: false });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const indexField = () => [...container.querySelectorAll<HTMLLabelElement>('.vc-render label')].find((l) => l.querySelector('span')?.textContent === 'Band') ?? null;

describe('the view of a layer of the layer manager', () => {
  // Otto, 1.11.2026 (NM4-54, zu #272): a layer that was pinned with a band or an index has the dropdown free, as the view it came from;
  // this replaces the lock of NM4-14b ("a layer keeps the index it was added with").
  it('has the dropdown free, showing the picture of the layer', () => {
    setState({ viewOfLayer: true, layers: [layer(NDVI)], viewLayerId: 'L1', pendingIndex: 'NDVI' });
    act(() => root.render(<ViewerControls />));
    expect(indexField()!.querySelector('select')!.disabled).toBe(false);
    expect(indexField()!.querySelector('select')!.value).toBe('index:NDVI');
    expect(container.querySelector('.vc-render')!.classList.contains('has-index')).toBe(true);
  });

  it('has it free for a layer without an index too, showing the standard picture', () => {
    setState({ viewOfLayer: true, appliedRender: { rescale: '0,3000' }, layers: [layer({ rescale: '0,3000' })], viewLayerId: 'L1' });
    act(() => root.render(<ViewerControls />));
    expect(indexField()!.querySelector('select')!.disabled).toBe(false);
    expect(indexField()!.querySelector('select')!.value).toBe('');
  });

  it('keeps the dropdown open in the live view of the search, even after the view was added as a layer', () => {
    setState({ viewOfLayer: false, layers: [layer(NDVI)], viewLayerId: 'L1' });
    act(() => root.render(<ViewerControls />));
    expect(indexField()!.querySelector('select')!.disabled).toBe(false);
  });

  it('changes the picture of the layer at once, as the same layer: another index, then the standard picture again', async () => {
    setState({ viewOfLayer: true, layers: [layer(NDVI)], viewLayerId: 'L1' });
    useAppStore.getState().chooseViewIndex('NDWI');
    await act(async () => { await Promise.resolve(); });
    expect(useAppStore.getState().layers.map((l) => l.id)).toEqual(['L1']);
    const kept = useAppStore.getState().layers[0];
    expect(kept.restore.appliedRender).toMatchObject({ index: 'NDWI', colormapName: 'rdbu', rescale: '-1,1' });
    expect(kept.overlays.filter((o) => o.kind === 'raster').every((o) => o.kind === 'raster' && o.tileUrl.includes('NDWI'))).toBe(true);
    useAppStore.getState().chooseViewIndex(null);
    await act(async () => { await Promise.resolve(); });
    const plain = useAppStore.getState().layers[0];
    expect(plain.restore.appliedRender.index).toBeUndefined();
    expect(plain.overlays.filter((o) => o.kind === 'raster').every((o) => o.kind === 'raster' && !o.tileUrl.includes('band_math'))).toBe(true);
    // Closed without "Save": the layer is the one it was.
    useAppStore.getState().exitFocus();
    expect(useAppStore.getState().layers[0].restore.appliedRender).toEqual(NDVI);
  });

  it('is entered from the layer manager only by choosing the layer, and left with the view', () => {
    setState({ layers: [layer(NDVI)], focusMode: false, downloaded: {}, appliedRender: {} });
    useAppStore.getState().selectLayer('L1');
    expect(useAppStore.getState().viewOfLayer).toBe(true);
    expect(useAppStore.getState().appliedRender).toEqual(NDVI);
    useAppStore.getState().exitFocus();
    expect(useAppStore.getState().viewOfLayer).toBe(false);
  });

  it('is not the view a new search makes: its index can be chosen', async () => {
    setState({ viewOfLayer: true, layers: [layer(NDVI)], viewLayerId: 'L1', downloaded: {}, focusMode: false });
    useAppStore.setState({ selectedIds: ['S1'], aoi: AOI, items: [item('S1')] });
    useProcessingStore.setState({ open: false });
    await useAppStore.getState().enterFocus(true).catch(() => undefined);
    expect(useAppStore.getState().viewOfLayer).toBe(false);
  });
});

describe('the ⇩ of a layer that shows an index', () => {
  const button = () => container.querySelector<HTMLButtonElement>('[data-col="download"]')!;

  it('says what it downloads: the raw crop, and the index besides, as a Processing job would give it', () => {
    setState({ layers: [layer(NDVI)] });
    act(() => root.render(<LayerManager />));
    expect(button().disabled).toBe(false);
    expect(button().title).toBe('Download the AOI crop, one file per group; the NDVI too, computed as a Processing job would');
  });

  it('offers no index for whole scenes (a job of Processing does that), only the crop, and keeps its old words for a layer without an index', () => {
    setState({ layers: [layer(NDVI, { cropToAoi: false })] });
    act(() => root.render(<LayerManager />));
    expect(button().disabled).toBe(false);
    expect(button().title).toBe('Download the AOI crop, one file per group');
    setState({ layers: [layer({ rescale: '0,3000' })] });
    expect(button().title).toBe('Download the AOI crop, one file per group');
  });
});

describe('the dialog of the download', () => {
  const settle = () => act(async () => { for (let i = 0; i < 40; i++) await Promise.resolve(); await new Promise((resolve) => setTimeout(resolve, 5)); });
  // Opens the dialog; `as` is what is chosen in it (the raw bands are what it starts with).
  const open = async (as: 'raw' | 'index' = 'index') => {
    setState({ layers: [layer(NDVI)] });
    act(() => root.render(<DownloadDialog />));
    await act(async () => { await useAppStore.getState().openDownloadDialog('L1'); });
    await settle();
    if (as === 'index') {
      await act(async () => { await useAppStore.getState().setDownloadAs('index'); });
      await settle();
    }
  };
  const primary = () => container.querySelector<HTMLButtonElement>('.dialog-actions .primary')!;
  const line = () => container.querySelector<HTMLElement>('.dialog-body .hint-text')!;
  const press = async () => {
    await act(async () => {
      primary().dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await settle();
  };
  const answers = (over: (url: string, init?: RequestInit) => Response | undefined) =>
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const own = over(url, init);
      if (own) return own;
      if (url.startsWith('/processing/processes/recipe?')) return json(s2);
      if (init?.method === 'POST' && url.endsWith('/estimate')) return json(ESTIMATE);
      if (init?.method === 'POST' && url.endsWith('/execution')) return json({ ...status('accepted'), progress: 0 });
      if (url === `/processing/jobs/${JOB}`) return json(status('successful'));
      return json({ detail: 'not found' }, 404);
    });

  it('starts with the raw bands, as for any layer: the resolution, the assets of the scenes, no estimate asked for', async () => {
    await open('raw');
    expect(container.textContent).toContain('asset visual');
    expect(container.querySelector('.dialog-resolution input[name="download-resolution"]')).not.toBeNull();
    expect([...container.querySelectorAll<HTMLInputElement>('input[name="download-as"]')].map((i) => [i.closest('label')?.textContent?.trim(), i.checked])).toEqual([['Raw bands', true], ['NDVI', false]]);
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/estimate'))).toBe(false);
    expect(primary().disabled).toBe(false);
  });

  it('downloads the raw crop by the crop route when it is not asked for the index', async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) =>
      init?.method === 'POST' && url.endsWith('/download') ? new Response(new Blob(['PK']), { status: 200, headers: { 'x-skipped-groups': '0', 'x-total-groups': '1' } }) : json({ detail: 'x' }, 404),
    );
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: () => 'blob:x', revokeObjectURL: () => undefined }));
    await open('raw');
    await press();
    const urls = fetchMock.mock.calls.map(([u, i]) => `${(i as RequestInit | undefined)?.method ?? 'GET'} ${u}`);
    expect(urls.some((u) => u.startsWith('POST /collections/') && u.endsWith('/download'))).toBe(true);
    expect(urls).not.toContain('POST /processing/processes/recipe/execution');
  });

  it('offers the index only where it can be computed: a crop; not for whole scenes', async () => {
    setState({ layers: [layer(NDVI, { cropToAoi: false })] });
    act(() => root.render(<DownloadDialog />));
    await act(async () => { await useAppStore.getState().openDownloadDialog('L1'); });
    await settle();
    expect(container.querySelector('input[name="download-as"]')).toBeNull();
  });

  it('names the index and its formula, offers no resolution and says what it will cost, with the limits in the tooltip', async () => {
    await open();
    expect(container.textContent).toContain('NDVI ((N - R)/(N + R))');
    expect(container.querySelector('.dialog-resolution')).toBeNull();
    expect(line().textContent).toBe('About 12.4 MB · about 9 s');
    expect(line().title).toContain('same limits as a job of Processing');
    expect(container.textContent).not.toContain('asset');
    expect(primary().disabled).toBe(false);
  });

  it('waits for the estimate: "Download" is locked and the line says so', async () => {
    let release: (value: Response) => void = () => undefined;
    fetchMock.mockImplementation(
      (url: string, init?: RequestInit) =>
        init?.method === 'POST' && url.endsWith('/estimate')
          ? new Promise<Response>((resolve) => (release = resolve))
          : Promise.resolve(url.startsWith('/processing/processes/recipe?') ? json(s2) : json({ detail: 'x' }, 404)),
    );
    setState({ layers: [layer(NDVI)] });
    act(() => root.render(<DownloadDialog />));
    await act(async () => { await useAppStore.getState().openDownloadDialog('L1'); });
    await act(async () => { void useAppStore.getState().setDownloadAs('index'); });
    await settle();
    expect(line().textContent).toBe('Estimating…');
    expect(primary().disabled).toBe(true);
    await act(async () => { release(json(ESTIMATE)); });
    await settle();
    expect(line().textContent).toBe('About 12.4 MB · about 9 s');
    expect(primary().disabled).toBe(false);
  });

  it('stops at a limit before any job is placed: the reason in one line, the limit as its tooltip, "Download" locked', async () => {
    answers((url, init) => (init?.method === 'POST' && url.endsWith('/estimate') ? json({ detail: 'the order would write more than 5 GB' }, 413) : undefined));
    await open();
    expect(line().textContent).toBe('Too large for one job');
    expect(line().title).toBe('An export job may write at most 5 GB. Choose a smaller area or fewer scenes.');
    expect(line().classList.contains('warn')).toBe(true);
    expect(primary().disabled).toBe(true);
    await press();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/execution'))).toBe(false);
  });

  it('computes the index as a job nobody sees, then downloads its result and closes; the raw crop route is not called', async () => {
    await open();
    await press();
    const urls = fetchMock.mock.calls.map(([u, i]) => `${(i as RequestInit | undefined)?.method ?? 'GET'} ${u}`);
    expect(urls.some((u) => u.startsWith('POST /collections/') && u.endsWith('/download'))).toBe(false);
    expect(urls).toContain('POST /processing/processes/recipe/execution');
    expect(clicked).toEqual([`/processing/jobs/${JOB}/results/result.zip`]);
    expect(useProcessingStore.getState().jobs).toEqual([]);
    expect(useProcessingStore.getState().open).toBe(false);
    expect(useAppStore.getState()).toMatchObject({ downloading: false, downloadDialogLayerId: null, error: null, notice: 'Downloaded "Sentinel-2 L2A · day".' });
  });

  it('tells a limit of the job API in the dialog, not in a toast, and may try again', async () => {
    let refused = true;
    answers((url, init) => (init?.method === 'POST' && url.endsWith('/execution') && refused ? json({ detail: 'at most 4 jobs may run at a time' }, 429) : undefined));
    await open();
    await press();
    expect(clicked).toEqual([]);
    expect(line().textContent).toBe('at most 4 jobs may run at a time');
    expect(line().title).toBe('at most 4 jobs may run at a time');
    expect(useAppStore.getState()).toMatchObject({ downloading: false, downloadDialogLayerId: 'L1', error: null });
    expect(primary().disabled).toBe(false);
    refused = false;
    await press();
    expect(clicked).toEqual([`/processing/jobs/${JOB}/results/result.zip`]);
  });

  it('says why the job failed, in the dialog', async () => {
    answers((url) => (url === `/processing/jobs/${JOB}` ? json({ ...status('failed'), message: 'The source failed' }) : undefined));
    await open();
    await press();
    expect(clicked).toEqual([]);
    expect(line().textContent).toBe('The source failed');
    expect(useAppStore.getState()).toMatchObject({ downloading: false, downloadDialogLayerId: 'L1', error: null });
  });

  it('cancels the job when the dialog is closed while it runs (as a job of Processing is cancelled), and downloads nothing', async () => {
    answers((url, init) => {
      if (init?.method === 'DELETE') return json({ ...status('dismissed') });
      if (url === `/processing/jobs/${JOB}`) return json({ ...status('running'), progress: 30 });
      return undefined;
    });
    await open();
    await act(async () => { primary().dispatchEvent(new MouseEvent('click', { bubbles: true })); });
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)); });
    expect(useAppStore.getState().downloading).toBe(true);
    expect(line().textContent).toMatch(/^Computing NDVI… \d+ %$/u);
    act(() => useAppStore.getState().closeDownloadDialog());
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 2300)); });
    const methods = fetchMock.mock.calls.map(([u, i]) => `${(i as RequestInit | undefined)?.method ?? 'GET'} ${u}`);
    expect(methods.filter((m) => m === `DELETE /processing/jobs/${JOB}`)).toHaveLength(1);
    expect(methods.filter((m) => m === `GET /processing/jobs/${JOB}`).length).toBeGreaterThan(0);
    expect(clicked).toEqual([]);
    expect(useAppStore.getState()).toMatchObject({ downloading: false, error: null, downloadIndexNote: null });
    // Nothing keeps asking after the cancel.
    const asked = methods.length;
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 2300)); });
    expect(fetchMock.mock.calls).toHaveLength(asked);
  });

  it('cancels the job when the dialog is closed while the estimate is still on its way: no job is placed', async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      init?.method === 'POST' && url.endsWith('/estimate') ? new Promise<Response>(() => undefined) : Promise.resolve(url.startsWith('/processing/processes/recipe?') ? json(s2) : json({ detail: 'x' }, 404)),
    );
    setState({ layers: [layer(NDVI)] });
    act(() => root.render(<DownloadDialog />));
    await act(async () => { void useAppStore.getState().openDownloadDialog('L1'); });
    await settle();
    act(() => useAppStore.getState().closeDownloadDialog());
    await settle();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/execution'))).toBe(false);
    expect(useAppStore.getState().downloadIndexNote).toBeNull();
  });
});
