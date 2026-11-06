// @vitest-environment jsdom
//
// NM4-50 (Otto, 28.10.2026): the ticks of scenes stay over a change of the time step and of the dataset in the results,
// until the user takes them off or presses "Clear search results". The map follows the rules of `mapResults.ts`: the
// ticked scenes of every dataset lie on it in the order they were ticked, and "Hide results" takes them all off.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { resultsOnMapOf } from './mapResults';
import { useAppStore } from './store';
import type { Collection, StacItem } from './types';

const CAPABILITIES = { roi: true, time_range: true, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, single_coverage_product: false };

const collection = (id: string, browse: 'quicklook' | 'full_resolution', groupBy: string, timeRange: boolean): Collection => ({
  id,
  title: id,
  'earthx:capabilities': { ...CAPABILITIES, time_range: timeRange },
  'earthx:viewer': { group_by: [groupBy], min_zoom: browse === 'quicklook' ? 8 : 0, max_zoom: 14, browse, quicklook_nodata_max: browse === 'quicklook' ? 16 : null, results_group_by: [groupBy] },
  'earthx:default_render': { title: 'Standard', assets: ['visual'], rescale: [[0, 255]], colormap_name: null, expression: null, resampling: 'nearest' },
});

const S2 = collection('s2', 'quicklook', 'datetime', true);
const DEM = collection('dem', 'full_resolution', 'start_datetime', false);

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 47]]] };
const s2Scene = (id: string, day: string): StacItem => ({ id, collection: 's2', bbox: [10, 47, 11, 48], properties: { datetime: `${day}T10:00:00Z` }, assets: {} });
const demTile = (id: string): StacItem => ({ id, collection: 'dem', bbox: [10, 47, 11, 48], properties: { start_datetime: '2011-01-01T00:00:00Z' }, assets: {} });

const FEATURES = [s2Scene('a1', '2026-07-01'), s2Scene('a2', '2026-07-01'), s2Scene('b1', '2026-07-06'), demTile('d1'), demTile('d2')];

const state = () => useAppStore.getState();

async function searched() {
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
  });
  const answer = (body: object) => ({ ok: true, status: 200, statusText: '', json: async () => body }) as Response;
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValueOnce(answer({ features: FEATURES, numberReturned: FEATURES.length, links: [{ rel: 'next', href: '/stac/search?token=T' }] }))
      .mockResolvedValue(answer({ features: [], numberReturned: 0, links: [] })),
  );
  await state().runSearch();
}

// What the map is told to show for the state now.
const onMap = () => {
  const s = state();
  return resultsOnMapOf(s);
};
const ids = (items: StacItem[]) => items.map((it) => it.id);

beforeEach(searched);
afterEach(() => vi.unstubAllGlobals());

describe('ticks over a change of the time step', () => {
  it('keeps the tick of a scene when another time step of the dataset is opened', () => {
    expect(state().openSectionId).toBe('s2');
    state().toggleSelected('a1');
    state().setActiveGroupIndex(1);
    expect(state().selectedIds).toEqual(['a1']);
    state().setActiveGroupIndex(0);
    expect(state().selectedIds).toEqual(['a1']);
  });

  it('draws the ticked scene of the closed time step with the open one, in the order they were ticked', () => {
    const groupOf = (id: string) => state().groups.findIndex((g) => g.items.some((it) => it.id === id));
    state().setActiveGroupIndex(groupOf('b1'));
    state().toggleSelected('b1');
    state().setActiveGroupIndex(groupOf('a1'));
    state().toggleSelected('a2');
    expect(ids(onMap().highlight)).toEqual(['b1', 'a2']);
    expect(ids(onMap().quicklooks).sort()).toEqual(['a1', 'a2', 'b1']);
    state().setActiveGroupIndex(groupOf('b1'));
    expect(ids(onMap().quicklooks).sort()).toEqual(['a2', 'b1']);
  });
});

describe('ticks over a change of the dataset', () => {
  it('keeps the ticks of the dataset left, and adds those of the one opened', () => {
    state().toggleSelected('a1');
    state().setOpenSection('dem');
    expect(state().selectedIds).toEqual(['a1']);
    state().toggleSelected('d1');
    expect(state().selectedIds).toEqual(['a1', 'd1']);
    state().setOpenSection('s2');
    expect(state().selectedIds).toEqual(['a1', 'd1']);
  });

  it('draws the ticked scenes of both datasets, the last ticked on top, and hides them all with "Hide results"', () => {
    state().toggleSelected('d1');
    state().setOpenSection('s2');
    state().toggleSelected('a1');
    expect(ids(onMap().highlight)).toEqual(['d1', 'a1']);
    expect(ids(onMap().quicklooks)).toContain('d1');
    expect(ids(onMap().quicklooks)).toContain('a1');
    state().toggleResultsOnMap();
    expect(onMap().quicklooks).toEqual([]);
    expect(onMap().highlight).toEqual([]);
    // The ticks stay; ticking a scene shows the results again (#221).
    expect(state().selectedIds).toEqual(['d1', 'a1']);
    state().toggleSelected('a2');
    expect(state().resultsOnMap).toBe(true);
    expect(ids(onMap().highlight)).toEqual(['d1', 'a1', 'a2']);
  });

  it('counts only the ticks of the open dataset for the scenes the bar of the selection acts on', () => {
    state().toggleSelected('d1');
    state().setOpenSection('s2');
    expect(state().items.filter((it) => state().selectedIds.includes(it.id))).toEqual([]);
    expect(onMap().clickable.map((it) => it.id)).toContain('d1');
  });

  it('keeps the ticks of the other dataset over "Load more"', async () => {
    state().toggleSelected('d1');
    state().setOpenSection('s2');
    state().toggleSelected('a1');
    await state().loadMore();
    expect(state().selectedIds).toEqual(['d1', 'a1']);
  });

  it('takes the ticks of the open dataset off with the box of the list, and no others', () => {
    state().toggleSelected('d1');
    state().setOpenSection('s2');
    state().selectAllLoaded();
    expect(state().selectedIds).toEqual(['d1', 'a1', 'a2', 'b1']);
    state().clearSelection();
    expect(state().selectedIds).toEqual(['d1']);
  });

  it('drops every tick with "Clear search results"', () => {
    state().toggleSelected('d1');
    state().setOpenSection('s2');
    state().toggleSelected('a1');
    state().clearSearchResults();
    expect(state().selectedIds).toEqual([]);
  });

  // Nachtrag NM4-53: a view takes the ticks of every dataset, so a crop takes all of them off.
  it('takes the ticks of every dataset off when a crop is made of their scenes', async () => {
    state().toggleSelected('d1');
    state().setOpenSection('s2');
    state().toggleSelected('a1');
    await state().enterFocus(true);
    expect(state().selectedIds).toEqual([]);
    expect(Object.keys(state().downloaded).sort()).toEqual(['a1', 'd1']);
  });
});
