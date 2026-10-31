// @vitest-environment jsdom
//
// NM4-53: the view holds images — one time step of one dataset each — and shows one at a time. What the store does
// when a view is made of scenes of several groups and datasets, and when it steps from image to image.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { shownImageOf, shownViewOf, useAppStore, viewImagesOf, viewSelectionFrom } from './store';
import type { Collection, StacItem } from './types';

const CAPABILITIES = { roi: true, time_range: true, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, single_coverage_product: false };

const collection = (id: string, groupBy: string, timeRange: boolean): Collection => ({
  id,
  title: id === 's2' ? 'Sentinel-2 L2A' : 'Copernicus DEM',
  'earthx:capabilities': { ...CAPABILITIES, time_range: timeRange },
  'earthx:viewer': { group_by: [groupBy], min_zoom: 0, max_zoom: 14, browse: 'preview_tiles', quicklook_nodata_max: null, results_group_by: [groupBy] },
  'earthx:default_render': { title: 'Standard', assets: ['visual'], rescale: [[0, 255]], colormap_name: null, expression: null, resampling: 'nearest' },
});

const S2 = collection('s2', 'datetime', true);
const DEM = collection('dem', 'start_datetime', false);
const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 47]]] };
const s2Scene = (id: string, day: string, platform = 'sentinel-2a'): StacItem => ({ id, collection: 's2', bbox: [10, 47, 11, 48], properties: { datetime: `${day}T10:00:00Z`, platform }, assets: {} });
const demTile = (id: string): StacItem => ({ id, collection: 'dem', bbox: [10, 47, 11, 48], properties: { start_datetime: '2011-01-01T00:00:00Z' }, assets: {} });

const FEATURES = [s2Scene('a1', '2026-07-01'), s2Scene('a2', '2026-07-01'), s2Scene('b1', '2026-07-06', 'sentinel-2b'), demTile('d1'), demTile('d2')];
const state = () => useAppStore.getState();
const json = (body: unknown, status = 200) => ({ ok: status < 300, status, statusText: '', json: async () => body }) as Response;

// The search answers once; later requests are the tiler's: statistics, and the TileJSON of a mosaic.
async function searched(features: StacItem[] = FEATURES) {
  useAppStore.setState({
    datasets: datasetsFrom([S2, DEM]),
    selectedDatasetIds: ['s2', 'dem'],
    multiSelect: true,
    datasetId: 's2',
    sections: [],
    selectedIds: [],
    layers: [],
    aoi: AOI,
    dateFrom: '',
    dateTo: '',
    focusMode: false,
    resultsOnMap: true,
    mosaics: {},
    downloaded: {},
    shownImage: null,
  });
  const fetchMock = vi.fn(async (url: string) => {
    if (url.includes('/statistics')) return json({ '1': { min: 0, max: 255, percentile_2: 5, percentile_98: 250 } });
    if (url.includes('/mosaic/')) return json({ detail: 'no' }, 422);
    return json({ features, numberReturned: features.length, links: [] });
  });
  vi.stubGlobal('fetch', fetchMock);
  await state().runSearch();
  return fetchMock;
}

const statisticsCalls = (f: ReturnType<typeof vi.fn>) => f.mock.calls.map(([url]) => String(url)).filter((url) => url.includes('/statistics'));

afterEach(() => vi.unstubAllGlobals());

describe('a view over several groups and datasets', () => {
  beforeEach(async () => {
    await searched();
    state().toggleSelected('a1');
    state().toggleSelected('a2');
    state().toggleSelected('b1');
    state().setOpenSection('dem');
    state().toggleSelected('d1');
    state().setOpenSection('s2');
  });

  it('takes the ticks of every dataset of the search', () => {
    expect(viewSelectionFrom(state()).map((p) => [p.datasetId, p.items.map((it) => it.id)])).toEqual([
      ['s2', ['a1', 'a2', 'b1']],
      ['dem', ['d1']],
    ]);
  });

  it('holds every scene with the dataset it belongs to, and one image per group and dataset', async () => {
    await state().enterFocus(true);
    const { downloaded } = state();
    expect(Object.fromEntries(Object.entries(downloaded).map(([id, info]) => [id, info.datasetId]))).toEqual({ a1: 's2', a2: 's2', b1: 's2', d1: 'dem' });
    expect(downloaded.d1.tileUrl).toContain('/collections/dem/');
    expect(viewImagesOf(state()).map((i) => [i.datasetId, i.ids])).toEqual([
      ['s2', ['a1', 'a2']],
      ['s2', ['b1']],
      ['dem', ['d1']],
    ]);
  });

  it('starts with the image of the group that is open, and with the earliest where the view has none of it', async () => {
    state().setActiveGroupIndex(state().groups.findIndex((g) => g.items.some((it) => it.id === 'a1')));
    await state().enterFocus(true);
    expect(shownImageOf(viewImagesOf(state()), state().shownImage)?.ids).toEqual(['a1', 'a2']);

    state().exitFocus();
    state().setActiveGroupIndex(state().groups.findIndex((g) => g.items.some((it) => it.id === 'b1')));
    await state().enterFocus(true);
    expect(shownImageOf(viewImagesOf(state()), state().shownImage)?.ids).toEqual(['b1']);

    // A dataset whose open group is not in the view: the earliest of the dataset that is open.
    state().exitFocus();
    state().setOpenSection('dem');
    state().toggleSelected('d1');
    state().toggleSelected('a1');
    state().toggleSelected('a2');
    state().toggleSelected('b1');
    state().setActiveGroupIndex(0);
    await state().enterFocus(false);
    expect(shownImageOf(viewImagesOf(state()), state().shownImage)?.datasetId).toBe('dem');
  });

  it('takes the ticks of the scenes off a crop, in every dataset, and keeps them in a whole-scene view', async () => {
    await state().enterFocus(false);
    expect(state().selectedIds.sort()).toEqual(['a1', 'a2', 'b1', 'd1']);
    state().exitFocus();
    await state().enterFocus(true);
    expect(state().selectedIds).toEqual([]);
  });

  it('draws only the scenes of the image that is shown, in the dataset of that image', async () => {
    await state().enterFocus(true);
    state().chooseViewDataset('dem');
    const view = shownViewOf(state());
    expect(Object.keys(view.downloaded)).toEqual(['d1']);
    expect(view.dataset?.id).toBe('dem');
    expect(view.groups.length).toBeGreaterThan(1);
  });
});

describe('stepping through the images', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(async () => {
    fetchMock = await searched();
    state().toggleSelected('a1');
    state().toggleSelected('b1');
    state().setOpenSection('dem');
    state().toggleSelected('d1');
    state().setOpenSection('s2');
    state().setActiveGroupIndex(state().groups.findIndex((g) => g.items.some((it) => it.id === 'a1')));
    await state().enterFocus(true);
  });

  const shownIds = () => shownImageOf(viewImagesOf(state()), state().shownImage)?.ids;

  it('goes forward and back in time within the dataset, and does not wrap around', () => {
    expect(shownIds()).toEqual(['a1']);
    state().stepImage(-1);
    expect(shownIds()).toEqual(['a1']);
    state().stepImage(1);
    expect(shownIds()).toEqual(['b1']);
    state().stepImage(1);
    expect(shownIds()).toEqual(['b1']);
    state().stepImage(-1);
    expect(shownIds()).toEqual(['a1']);
  });

  it('never leaves the dataset that is shown', () => {
    state().chooseViewDataset('dem');
    state().stepImage(1);
    state().stepImage(-1);
    expect(shownIds()).toEqual(['d1']);
  });

  it('goes to the first image of another dataset, and ignores a dataset the view does not have', () => {
    state().chooseViewDataset('dem');
    expect(shownIds()).toEqual(['d1']);
    state().chooseViewDataset('s2');
    expect(shownIds()).toEqual(['a1']);
    state().chooseViewDataset('nowhere');
    expect(shownIds()).toEqual(['a1']);
  });

  it('shows an image by its key, and ignores a key that is no image of the view', () => {
    const key = viewImagesOf(state()).find((i) => i.ids.includes('b1'))!.key;
    state().showImage(key);
    expect(shownIds()).toEqual(['b1']);
    state().showImage('no such image');
    expect(shownIds()).toEqual(['b1']);
  });

  it('does nothing outside a view', () => {
    state().exitFocus();
    state().stepImage(1);
    state().chooseViewDataset('dem');
    expect(state().shownImage).toBeNull();
  });

  it('leaves "Hide image" and the ticks alone', () => {
    state().toggleDownloaded();
    const ticks = [...state().selectedIds];
    state().stepImage(1);
    expect(state().showDownloaded).toBe(false);
    expect(state().selectedIds).toEqual(ticks);
  });

  it('measures the stretch on the first scene of the image that is shown, in its own dataset', async () => {
    state().chooseViewDataset('dem');
    await state().autoStretch();
    expect(statisticsCalls(fetchMock).pop()).toContain('/collections/dem/items/d1/');
    state().chooseViewDataset('s2');
    await state().autoStretch();
    expect(statisticsCalls(fetchMock).pop()).toContain('/collections/s2/items/a1/');
  });
});

describe('scenes the view cannot hold', () => {
  it('keeps a scene id two datasets share with its first dataset and says so', async () => {
    await searched([s2Scene('x', '2026-07-01'), demTile('x')]);
    // A tick is the scene's id, so it stands for the scene of either dataset.
    state().toggleSelected('x');
    await state().enterFocus(false);
    expect(Object.keys(state().downloaded)).toEqual(['x']);
    expect(state().downloaded.x.datasetId).toBe('s2');
    expect(state().notice).toContain('in two datasets');
  });

  it('opens nothing and says so where nothing is ticked and nothing is open', async () => {
    await searched();
    useAppStore.setState({ openSectionId: null, sections: [], groups: [], items: [], datasetId: null });
    await state().enterFocus(true);
    expect(state().focusMode).toBe(false);
    expect(state().error).toContain('Nothing to view');
  });

  it('leaves out a dataset that cannot be viewed and shows the others', async () => {
    await searched();
    state().toggleSelected('a1');
    state().setOpenSection('dem');
    state().toggleSelected('d1');
    useAppStore.setState({ datasets: datasetsFrom([S2]) });
    await state().enterFocus(false);
    expect(Object.keys(state().downloaded)).toEqual(['a1']);
    expect(state().notice).toContain('Choose a dataset');
  });

  it('takes the images away with the view', async () => {
    await searched();
    state().toggleSelected('a1');
    await state().enterFocus(false);
    expect(state().shownImage).not.toBeNull();
    state().exitFocus();
    expect(state().shownImage).toBeNull();
    expect(viewImagesOf(state())).toEqual([]);
  });
});
