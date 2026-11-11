// @vitest-environment jsdom
//
// `openDownloadForView` (the settings bar, Otto, 2.11.2026): the download buttons of the view take the scenes of the image the view
// shows, not the ticks of the list; the refusals are those of `openDownloadForSelection`.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { useAppStore } from './store';
import type { Collection, DownloadedInfo, StacItem } from './types';

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[0, 40], [20, 40], [20, 55], [0, 55], [0, 40]]] };

const collection = (format: 'cog' | 'zarr'): Collection =>
  ({
    id: 'optical',
    title: 'Optical',
    'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
    'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 19, browse: 'quicklook', quicklook_nodata_max: 16, results_group_by: ['datetime'], overview: 'own' as const, overview_resampling: null },
    'earthx:format': format,
    'earthx:source': { asset_hosts: ['data.test'] },
    'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: null, colormap_name: null, expression: null, resampling: 'nearest' },
  }) as unknown as Collection;

const scene = (id: string, day: string): StacItem => ({ id, collection: 'optical', properties: { datetime: `${day}T10:00:00Z` }, assets: { visual: { href: `https://data.test/${id}.tif` } } });
const info: DownloadedInfo = { datasetId: 'optical', tileUrl: '/t/{z}/{x}/{y}', bounds: [0, 0, 1, 1], asset: 'visual', minZoom: 8, maxZoom: 14 };

const a = [scene('A1', '2026-07-24'), scene('A2', '2026-07-24')];
const b = [scene('B1', '2026-07-25')];
const state = () => useAppStore.getState();

// The view holds the scenes of both days; the first day is shown, the ticks are on the second.
function open(format: 'cog' | 'zarr' = 'cog', aoi: GeoJSON.Polygon | null = AOI) {
  useAppStore.setState({
    datasets: datasetsFrom([collection(format)]),
    datasetId: 'optical',
    items: [...a, ...b],
    groups: [
      { key: ['a'], label: 'Day A', items: a },
      { key: ['b'], label: 'Day B', items: b },
    ],
    activeGroupIndex: 1,
    selectedIds: ['B1'],
    downloaded: { A1: info, A2: info, B1: info },
    focusMode: true,
    shownImage: null,
    aoi,
    sections: [],
    openSectionId: null,
    error: null,
    downloadDialogLayerId: null,
    downloadSelection: false,
    downloadView: null,
    downloadOutcome: null,
    downloadOriginalLinks: null,
    downloadPasses: null,
  });
}

beforeEach(() => open());

describe('openDownloadForView', () => {
  it('crop: opens the dialog for the scenes of the shown image, not the ticks', () => {
    state().openDownloadForView('crop');
    expect(state().downloadSelection).toBe(true);
    expect(state().downloadOutcome).toBe('crop');
    expect(state().downloadView?.items.map((it) => it.id)).toEqual(['A1', 'A2']);
    expect(state().downloadView?.label).toBe('Day A');
    expect(state().error).toBeNull();
  });

  it('crop: the request of the dialog holds the one group of the image', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, status: 200, statusText: 'OK', headers: new Headers({ 'X-Total-Groups': '1', 'X-Skipped-Groups': '0' }), blob: async () => new Blob(['zip']) }) as unknown as Response),
    );
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() }));
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    state().openDownloadForView('crop');
    // The table of bands (here: none that reads) is asked for first.
    await vi.waitFor(() => expect(state().downloadBandsLoading).toBe(false));
    await state().confirmDownload();
    const sent = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith('/download'));
    const body = JSON.parse(String(sent?.[1]?.body));
    expect(body.groups).toEqual([['A1', 'A2']]);
    expect(state().downloadView).toBeNull();
    expect(state().downloadSelection).toBe(false);
  });

  it('the image that is stepped to is the one taken', () => {
    const image = state().shownImage;
    expect(image).toBeNull();
    state().stepImage(1);
    state().openDownloadForView('originals');
    expect(state().downloadPasses?.map((pass) => pass.items.map((it) => it.id))).toEqual([['B1']]);
  });

  it('originals: links and passes of the shown image only', () => {
    state().openDownloadForView('originals');
    expect(state().downloadOutcome).toBe('originals');
    expect(state().downloadOriginalLinks?.map((link) => link.itemId)).toEqual(['A1', 'A2']);
    expect(state().downloadPasses?.map((pass) => [pass.label, pass.items.length])).toEqual([['Day A', 2]]);
  });

  it('closing the dialog drops the view, so that the next download of the list takes its ticks', () => {
    state().openDownloadForView('crop');
    state().closeDownloadDialog();
    expect(state().downloadView).toBeNull();
    state().openDownloadForSelection('crop');
    expect(state().downloadView).toBeNull();
    expect(state().downloadSelection).toBe(true);
  });

  it('crop without an AOI: the reason of the selection, no dialog', () => {
    open('cog', null);
    state().openDownloadForView('crop');
    expect(state().downloadSelection).toBe(false);
    expect(state().error).toMatch(/AOI/);
    const asked = state().error;
    open('cog', null);
    state().openDownloadForSelection('crop');
    expect(state().error).toBe(asked);
  });

  it('originals of a dataset that is no COG: the reason of the selection, no dialog, with or without an AOI', () => {
    for (const aoi of [null, AOI]) {
      open('zarr', aoi);
      state().openDownloadForView('originals');
      expect(state().downloadSelection).toBe(false);
      expect(state().error).toMatch(/no single original file per scene/);
    }
  });

  it('a view without an image: an error, no dialog', () => {
    open();
    useAppStore.setState({ downloaded: {} });
    state().openDownloadForView('crop');
    expect(state().downloadSelection).toBe(false);
    expect(state().error).toMatch(/no image/);
  });

  it('an image whose scenes the list does not know: an error, no dialog', () => {
    open();
    useAppStore.setState({ downloaded: { X9: info }, items: [], groups: [] });
    state().openDownloadForView('originals');
    expect(state().downloadSelection).toBe(false);
    expect(state().error).toMatch(/no image/);
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
