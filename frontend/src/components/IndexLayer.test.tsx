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
import { LAYER_INDEX_NOTE } from '../viewIndex';
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

const indexField = () => [...container.querySelectorAll<HTMLLabelElement>('.vc-render label')].find((l) => l.querySelector('span')?.textContent === 'Index') ?? null;

describe('the view of a layer of the layer manager', () => {
  it('shows the index the layer was added with, locked, and says so in its tooltip', () => {
    setState({ viewOfLayer: true, layers: [layer(NDVI)], viewLayerId: 'L1' });
    act(() => root.render(<ViewerControls />));
    const select = indexField()!.querySelector('select')!;
    expect(select.value).toBe('NDVI');
    expect(select.disabled).toBe(true);
    expect(indexField()!.title).toContain('Normalized Difference Vegetation Index: (N - R)/(N + R)');
    expect(indexField()!.title).toContain(LAYER_INDEX_NOTE);
  });

  it('has no dropdown for a layer without an index', () => {
    setState({ viewOfLayer: true, appliedRender: { rescale: '0,3000' }, layers: [layer({ rescale: '0,3000' })], viewLayerId: 'L1' });
    act(() => root.render(<ViewerControls />));
    expect(indexField()).toBeNull();
    expect(container.querySelector('.vc-render')!.classList.contains('has-index')).toBe(false);
  });

  it('keeps the dropdown open in the live view of the search, even after the view was added as a layer', () => {
    setState({ viewOfLayer: false, layers: [layer(NDVI)], viewLayerId: 'L1' });
    act(() => root.render(<ViewerControls />));
    expect(indexField()!.querySelector('select')!.disabled).toBe(false);
  });

  it('does not change the index of a layer, whatever asks to: the store holds it too', () => {
    setState({ viewOfLayer: true, layers: [layer(NDVI)], viewLayerId: 'L1' });
    useAppStore.getState().chooseViewIndex('NDWI');
    useAppStore.getState().chooseViewIndex(null);
    expect(useAppStore.getState().appliedRender).toEqual(NDVI);
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

  it('says what it downloads: the index of the crop, as a Processing job would give it', () => {
    setState({ layers: [layer(NDVI)] });
    act(() => root.render(<LayerManager />));
    expect(button().disabled).toBe(false);
    expect(button().title).toBe('Download the NDVI of the AOI crop, computed as a Processing job would');
  });

  it('is locked for whole scenes, with what to do, and keeps its old words for a layer without an index', () => {
    setState({ layers: [layer(NDVI, { cropToAoi: false })] });
    act(() => root.render(<LayerManager />));
    expect(button().disabled).toBe(true);
    expect(button().title).toBe('The index of whole scenes is computed by a job: start one in Processing.');
    setState({ layers: [layer({ rescale: '0,3000' })] });
    expect(button().title).toBe('Download the AOI crop, one file per group');
  });
});

describe('the dialog of the download', () => {
  const open = () => {
    setState({ layers: [layer(NDVI)], downloadDialogLayerId: 'L1', downloadOutcome: 'crop' });
    act(() => root.render(<DownloadDialog />));
  };
  const primary = () => container.querySelector<HTMLButtonElement>('.dialog-actions .primary')!;

  it('names the index and its formula, offers no resolution and says it is computed', () => {
    open();
    expect(container.textContent).toContain('NDVI ((N - R)/(N + R))');
    expect(container.querySelector('.dialog-resolution')).toBeNull();
    expect(container.querySelector('.dialog-body .hint-text')!.textContent).toBe('NDVI is computed from the scenes of this layer; this can take a moment.');
    expect(container.textContent).not.toContain('asset');
  });

  it('computes the index as a job nobody sees, then downloads its result and closes; the raw crop route is not called', async () => {
    open();
    await act(async () => {
      primary().dispatchEvent(new MouseEvent('click', { bubbles: true }));
      for (let i = 0; i < 40; i++) await Promise.resolve();
      await new Promise((resolve) => setTimeout(resolve, 5));
    });
    const urls = fetchMock.mock.calls.map(([u, i]) => `${(i as RequestInit | undefined)?.method ?? 'GET'} ${u}`);
    expect(urls.some((u) => u.startsWith('POST /collections/') && u.endsWith('/download'))).toBe(false);
    expect(urls).toContain('POST /processing/processes/recipe/execution');
    expect(clicked).toEqual([`/processing/jobs/${JOB}/results/result.zip`]);
    expect(useProcessingStore.getState().jobs).toEqual([]);
    expect(useProcessingStore.getState().open).toBe(false);
    expect(useAppStore.getState()).toMatchObject({ downloading: false, downloadDialogLayerId: null, error: null, notice: 'Downloaded "Sentinel-2 L2A · day".' });
  });

  it('leaves the dialog open with the reason when the job fails', async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.startsWith('/processing/processes/recipe?')) return json(s2);
      if (init?.method === 'POST' && url.endsWith('/execution')) return json({ ...status('accepted'), progress: 0 });
      if (url === `/processing/jobs/${JOB}`) return json({ ...status('failed'), message: 'The source failed' });
      return json({ detail: 'not found' }, 404);
    });
    open();
    await act(async () => {
      primary().dispatchEvent(new MouseEvent('click', { bubbles: true }));
      for (let i = 0; i < 40; i++) await Promise.resolve();
      await new Promise((resolve) => setTimeout(resolve, 5));
    });
    expect(clicked).toEqual([]);
    expect(useAppStore.getState()).toMatchObject({ downloading: false, downloadDialogLayerId: 'L1', error: 'The source failed' });
  });

  it('stops the computing when the dialog is closed, and the job placed is dismissed', async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.startsWith('/processing/processes/recipe?')) return json(s2);
      if (init?.method === 'POST' && url.endsWith('/execution')) return json({ ...status('accepted'), progress: 0 });
      if (init?.method === 'DELETE') return json({ ...status('dismissed') });
      return json({ ...status('running'), progress: 30 });
    });
    open();
    await act(async () => {
      primary().dispatchEvent(new MouseEvent('click', { bubbles: true }));
      await new Promise((resolve) => setTimeout(resolve, 30));
    });
    expect(useAppStore.getState().downloading).toBe(true);
    act(() => useAppStore.getState().closeDownloadDialog());
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 2300));
    });
    const methods = fetchMock.mock.calls.map(([u, i]) => `${(i as RequestInit | undefined)?.method ?? 'GET'} ${u}`);
    expect(methods).toContain(`DELETE /processing/jobs/${JOB}`);
    expect(clicked).toEqual([]);
    expect(useAppStore.getState()).toMatchObject({ downloading: false, error: null });
  });
});
