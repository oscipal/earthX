// @vitest-environment jsdom
//
// The index in the look of the view (NM4-14b): choosing it, taking it away, "Apply to all", the step to the next image, "Add to layers",
// and the measure of "auto-scale". The view draws it (`mapLayers.index.test.ts`); the dropdown is `ViewIndex.test.tsx`.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { SENTINEL_2_PRESETS } from './fixtures/indexPresets';
import { mosaicTemplateOf } from './mosaic';
import { useAppStore } from './store';
import type { Collection, DownloadedInfo, StacItem } from './types';

const collection = (id: string, presets: unknown[]): Collection =>
  ({
    id,
    title: id,
    'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
    'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
    'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
    'earthx:index_presets': presets,
  }) as unknown as Collection;

const item = (id: string, day: string, dataset = 's2'): StacItem => ({ id, collection: dataset, bbox: [10, 47, 11, 48], properties: { datetime: `${day}T10:00:00Z` }, assets: {} });
const info = (id: string, dataset = 's2'): DownloadedInfo => ({
  datasetId: dataset,
  tileUrl: `/collections/${dataset}/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`,
  bounds: [10, 47, 11, 48],
  asset: 'visual',
  minZoom: 8,
  maxZoom: 14,
});

const state = () => useAppStore.getState();
const DEFAULT = { rescale: '0,3000' };
const NDWI = { index: 'NDWI', colormapName: 'rdbu', rescale: '-1,1' };
const NDVI = { index: 'NDVI', colormapName: 'rdylgn', rescale: '-1,1' };

// A view of two time steps of Sentinel-2 (one scene each) and one scene of the DEM.
function openView(presets: unknown[] = SENTINEL_2_PRESETS) {
  const items = [item('a1', '2026-07-01'), item('b1', '2026-07-06')];
  useAppStore.setState({
    datasets: datasetsFrom([collection('s2', presets), collection('dem', [])]),
    datasetId: 's2',
    sections: [],
    openSectionId: null,
    items,
    groups: [
      { key: ['2026-07-01'], label: '2026-07-01', items: [items[0]] },
      { key: ['2026-07-06'], label: '2026-07-06', items: [items[1]] },
    ],
    selectedIds: ['a1', 'b1'],
    downloaded: { a1: info('a1'), b1: info('b1') },
    focusMode: true,
    cropToAoi: true,
    viewAoi: { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 47]]] },
    shownImage: null,
    viewLooks: {},
    savedLooks: {},
    appliedRender: DEFAULT,
    pendingColormapName: '',
    pendingVmin: '0',
    pendingVmax: '3000',
    layers: [],
    mosaics: {},
    mapZoom: 12,
    error: null,
    notice: null,
  });
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 404 })));
  openView();
});
afterEach(() => vi.unstubAllGlobals());

describe('choosing the index', () => {
  it('sets the look to the index at once, with its range and colormap, and the fields of the view follow', () => {
    state().chooseViewIndex('NDWI');
    expect(state().appliedRender).toEqual(NDWI);
    expect([state().pendingColormapName, state().pendingVmin, state().pendingVmax]).toEqual(['rdbu', '-1', '1']);
  });

  it('changes from one index to the other', () => {
    state().chooseViewIndex('NDWI');
    state().chooseViewIndex('NDVI');
    expect(state().appliedRender).toEqual(NDVI);
  });

  it('brings the standard look back with "none"', () => {
    state().chooseViewIndex('NDWI');
    state().chooseViewIndex(null);
    expect(state().appliedRender).toEqual({ rescale: '0,3000' });
    expect(state().pendingVmax).toBe('3000');
  });

  it('brings back the look saved for the dataset, unless that is an index', () => {
    useAppStore.setState({ savedLooks: { s2: { rescale: '0,1000', colormapName: 'viridis' } } });
    state().chooseViewIndex('NDWI');
    state().chooseViewIndex(null);
    expect(state().appliedRender).toEqual({ rescale: '0,1000', colormapName: 'viridis' });
    useAppStore.setState({ savedLooks: { s2: NDVI } });
    state().chooseViewIndex(null);
    expect(state().appliedRender).toEqual(DEFAULT);
  });

  it('does nothing for an index the dataset does not offer, or without a view', () => {
    state().chooseViewIndex('SAVI');
    expect(state().appliedRender).toEqual(DEFAULT);
    useAppStore.setState({ focusMode: false });
    state().chooseViewIndex('NDWI');
    expect(state().appliedRender).toEqual(DEFAULT);
  });

  it('does nothing for a dataset without presets (the DEM): the index is of the dataset of the image shown', () => {
    useAppStore.setState({ datasetId: 'dem', items: [item('d1', '2026-07-01', 'dem')], groups: [], downloaded: { d1: info('d1', 'dem') }, selectedIds: ['d1'] });
    state().chooseViewIndex('NDWI');
    expect(state().appliedRender).toEqual(DEFAULT);
  });

  it('keeps the index while the range is changed by hand ("Apply")', () => {
    state().chooseViewIndex('NDWI');
    state().setPendingVmin('-0.5');
    state().setPendingVmax('0.5');
    state().applyRender();
    expect(state().appliedRender).toEqual({ index: 'NDWI', colormapName: 'rdbu', rescale: '-0.5,0.5' });
  });
});

describe('the index and the images of the view', () => {
  it('is the look of the image it was chosen for; the next image keeps what it had, and the index is back on return', () => {
    state().chooseViewIndex('NDWI');
    state().stepImage(1);
    expect(state().appliedRender).toEqual(DEFAULT);
    state().stepImage(-1);
    expect(state().appliedRender).toEqual(NDWI);
  });

  it('is taken by every image of the dataset with "Apply to all"', () => {
    state().chooseViewIndex('NDWI');
    state().saveViewLook();
    expect(state().savedLooks.s2).toEqual(NDWI);
    state().stepImage(1);
    expect(state().appliedRender).toEqual(NDWI);
  });

  it('is taken off all images again by "none" and "Apply to all"', () => {
    state().chooseViewIndex('NDWI');
    state().saveViewLook();
    state().chooseViewIndex(null);
    expect(state().appliedRender).toEqual(DEFAULT);
    state().saveViewLook();
    state().stepImage(1);
    expect(state().appliedRender).toEqual(DEFAULT);
  });
});

describe('"Add to layers" with an index', () => {
  it('pins the image as a layer that computes the index and keeps it in its look, with no quicklook under it', () => {
    state().chooseViewIndex('NDVI');
    state().addCurrentToLayers();
    const [layer] = state().layers;
    expect(layer.restore.appliedRender).toEqual(NDVI);
    expect(layer.overlays.every((o) => o.kind === 'raster')).toBe(true);
    const query = new URL((layer.overlays[0] as { tileUrl: string }).tileUrl, 'http://x').searchParams;
    expect(query.getAll('op')).toEqual(['band_math']);
    expect(query.get('band')).toBe('NDVI');
    expect(query.get('rescale')).toBe('-1,1');
    expect(state().error).toBeNull();
  });

  it('pins every image with the look each has: the index for one, the standard look for the other', () => {
    state().chooseViewIndex('NDVI');
    state().addAllToLayers();
    const looks = Object.fromEntries(state().layers.map((l) => [l.restore.itemIds[0], l.restore.appliedRender]));
    expect(looks).toEqual({ a1: NDVI, b1: DEFAULT });
  });

  it('is not pinned where the tile route cannot take the index: an error with what to do, no empty layer', () => {
    const many = Object.fromEntries(Array.from({ length: 64 }, (_, i) => [`S2_${'x'.repeat(110)}${i}`, undefined]));
    const ids = Object.keys(many);
    const items = ids.map((id) => item(id, '2026-07-01'));
    const downloaded = Object.fromEntries(ids.map((id) => [id, info(id)]));
    const entries = ids.map((id) => [id, downloaded[id]] as [string, DownloadedInfo]);
    useAppStore.setState({
      items,
      groups: [{ key: ['a'], label: 'a', items }],
      downloaded,
      selectedIds: ids,
      mosaics: { [mosaicTemplateOf('s2', entries)!]: { tileUrl: '/m/{z}/{x}/{y}', bounds: [10, 47, 11, 48], minZoom: 8, maxZoom: 14, order: ids } },
    });
    state().chooseViewIndex('EVI');
    state().addCurrentToLayers();
    expect(state().layers).toEqual([]);
    expect(state().error).toBe('EVI cannot be computed here. Start a job in Processing for the whole scenes.');
  });

  it('is pinned at any map zoom: the layer draws from the level the scenes start at', () => {
    useAppStore.setState({ mapZoom: 3 });
    state().chooseViewIndex('NDVI');
    state().addCurrentToLayers();
    expect(state().layers).toHaveLength(1);
  });
});

describe('"auto-scale" with an index', () => {
  it('measures the index as it is drawn: the statistics of the tile route with the step, not of the asset', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ NDWI: { percentile_2: -0.6, percentile_98: 0.3, min: -1, max: 1 } }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    state().chooseViewIndex('NDWI');
    await state().autoStretch();
    const url = new URL(String((fetchMock.mock.calls[0] as unknown[])[0]), 'http://x');
    expect(url.pathname).toBe('/collections/s2/items/a1/statistics');
    expect(url.searchParams.getAll('asset')).toEqual(['green', 'nir']);
    expect(url.searchParams.get('band')).toBe('NDWI');
    expect([state().pendingVmin, state().pendingVmax]).toEqual(['-0.6', '0.3']);
    // Nothing is drawn differently until "Apply".
    expect(state().appliedRender).toEqual(NDWI);
  });

  it('measures the asset of the scene without an index, as before', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ '1': { percentile_2: 5, percentile_98: 250, min: 0, max: 255 } }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    await state().autoStretch();
    const url = new URL(String((fetchMock.mock.calls[0] as unknown[])[0]), 'http://x');
    expect(url.searchParams.getAll('asset')).toEqual(['visual']);
    expect(url.searchParams.has('op')).toBe(false);
  });
});
