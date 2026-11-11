// @vitest-environment jsdom
//
// The datasets of "Search and area" in the store (UI-05 §4.5): the saved list or the first visit's at the start, and a
// layer's dataset that was removed comes back with the layer. Synthetic collections; the server is a stand-in.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useAppStore } from './store';
import type { Collection } from './types';

const VIEWER = { group_by: ['datetime'], min_zoom: 0, max_zoom: 14, browse: 'preview_tiles' as const, quicklook_nodata_max: null, results_group_by: ['datetime'], overview: 'own' as const, overview_resampling: null, overview_substitute: null };
const CAPABILITIES = { roi: true, time_range: true, band_math: true, interpolation: false, quad_pol: false, single_coverage_product: false, ml_processing: false };
const collection = (id: string, category: string, extra: Partial<Collection> = {}): Collection =>
  ({ id, title: id, 'earthx:category': category, 'earthx:viewer': VIEWER, 'earthx:capabilities': CAPABILITIES, ...extra }) as Collection;

function serve(collections: Collection[]) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ collections }), { status: 200 })));
}

const added = () => useAppStore.getState().addedDatasetIds;

beforeEach(() => {
  localStorage.clear();
  useAppStore.setState({ datasets: [], addedDatasetIds: [], selectedDatasetIds: [], datasetId: null, searching: false, sceneLookupLoading: false });
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe('loadDatasets', () => {
  it('adds the first visit\'s datasets and saves nothing, so that the first visit follows the registry', async () => {
    serve([collection('dem', 'elevation'), collection('s2', 'optical')]);
    await useAppStore.getState().loadDatasets();
    expect(added()).toEqual(['s2', 'dem']);
    expect(localStorage.getItem('earthx.datasets')).toBeNull();
  });

  it('takes the first six in the order of the groups where there are more (F3)', async () => {
    serve(Array.from({ length: 8 }, (_, i) => collection(`d${i}`, i % 2 === 0 ? 'radar' : 'optical')));
    await useAppStore.getState().loadDatasets();
    expect(added()).toEqual(['d1', 'd3', 'd5', 'd7', 'd0', 'd2']);
  });

  it('takes the saved list, without unknown and retired ids, in its order', async () => {
    localStorage.setItem('earthx.datasets', JSON.stringify(['s2', 'sentinel-2-l2a-zarr3', 'dem', 'gone']));
    serve([collection('dem', 'elevation'), collection('s2', 'optical'), collection('wc', 'land_cover')]);
    await useAppStore.getState().loadDatasets();
    expect(added()).toEqual(['s2', 'dem']);
  });

  it('keeps a list the user emptied empty', async () => {
    localStorage.setItem('earthx.datasets', '[]');
    serve([collection('s2', 'optical')]);
    await useAppStore.getState().loadDatasets();
    expect(added()).toEqual([]);
  });

  it('falls back to the first visit for a saved value that is broken', async () => {
    localStorage.setItem('earthx.datasets', '{not json');
    serve([collection('s2', 'optical')]);
    await useAppStore.getState().loadDatasets();
    expect(added()).toEqual(['s2']);
  });

  it('works with a storage that throws', async () => {
    const throwing = { getItem: () => { throw new Error('blocked'); }, setItem: () => { throw new Error('blocked'); } };
    vi.stubGlobal('localStorage', throwing);
    serve([collection('s2', 'optical')]);
    await useAppStore.getState().loadDatasets();
    expect(added()).toEqual(['s2']);
    expect(() => useAppStore.getState().removeDataset('s2')).not.toThrow();
    expect(added()).toEqual([]);
  });
});

describe('adding and removing', () => {
  beforeEach(async () => {
    serve([collection('s2', 'optical'), collection('dem', 'elevation'), collection('closed', 'radar', { 'earthx:access': { cors: null, account: 'free_account' } })]);
    await useAppStore.getState().loadDatasets();
  });

  it('adds a dataset once, and an unknown or closed one never', () => {
    const { addDataset } = useAppStore.getState();
    useAppStore.getState().removeDataset('dem');
    addDataset('dem');
    addDataset('dem');
    addDataset('nope');
    addDataset('closed');
    expect(added()).toEqual(['s2', 'dem']);
  });

  it('turns the panel to an added dataset each time, also to one that is there already', () => {
    useAppStore.getState().addDataset('s2');
    const first = useAppStore.getState().revealedDataset!;
    useAppStore.getState().addDataset('s2');
    expect(useAppStore.getState().revealedDataset!.seq).toBe(first.seq + 1);
  });

  it('removing one that is not there changes nothing', () => {
    useAppStore.getState().removeDataset('nope');
    expect(added()).toEqual(['s2', 'dem']);
    expect(localStorage.getItem('earthx.datasets')).toBeNull();
  });

  it('a permalink\'s dataset is added where it is not, and nothing else', () => {
    useAppStore.getState().removeDataset('dem');
    useAppStore.getState().ensureDatasetAdded('dem');
    useAppStore.getState().ensureDatasetAdded('closed');
    expect(added()).toEqual(['s2', 'dem']);
  });

  it('a layer brings its dataset back into the panel when it ticks it', () => {
    useAppStore.getState().removeDataset('dem');
    useAppStore.setState({
      layers: [{ id: 'l1', name: 'L', visible: true, opacity: 1, overlays: [], restore: { datasetId: 'dem', itemIds: [] } } as never],
    });
    useAppStore.getState().activateLayerContext('l1');
    expect(useAppStore.getState().selectedDatasetIds).toContain('dem');
    expect(added()).toEqual(['s2', 'dem']);
  });
});
