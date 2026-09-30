// @vitest-environment jsdom
//
// M3-10: the dataset filter's ticks, one search over every ticked dataset, the
// results split into one section per dataset, the active dataset, the crops a
// search pins for a dataset with no browsable preview (F5) and pinned layers of
// several datasets side by side (F4).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { layersOnMap } from './searchLayers';
import { useAppStore } from './store';
import type { Collection, StacItem } from './types';

const CAPABILITIES = {
  roi: true,
  time_range: true,
  band_math: true,
  interpolation: true,
  ml_processing: true,
  quad_pol: false,
  single_coverage_product: false,
};

function previewCollection(id: string, title: string): Collection {
  return {
    id,
    title,
    'earthx:capabilities': CAPABILITIES,
    'earthx:viewer': {
      group_by: ['datetime'],
      min_zoom: 8,
      max_zoom: 14,
      browse: 'preview_tiles',
      quicklook_nodata_max: null,
      results_group_by: ['datetime'],
    },
    'earthx:default_render': {
      title: 'True colour',
      assets: ['SR_10m:b04,b03,b02'],
      rescale: [[0, 0.3]],
      colormap_name: null,
      expression: null,
      resampling: 'nearest',
    },
  };
}

const OPTICAL = previewCollection('optical', 'Optical');
const OPTICAL_ZARR = previewCollection('optical-zarr', 'Optical (Zarr)');
const DEM: Collection = {
  id: 'dem',
  title: 'Elevation',
  extent: { temporal: { interval: [['2010-12-01T00:00:00Z', '2015-01-31T23:59:59Z']] } },
  'earthx:capabilities': { ...CAPABILITIES, time_range: false, single_coverage_product: true },
  'earthx:viewer': {
    group_by: ['start_datetime'],
    min_zoom: 0,
    max_zoom: 15,
    browse: 'full_resolution',
    quicklook_nodata_max: null,
    results_group_by: ['start_datetime'],
  },
  'earthx:default_render': {
    title: 'Elevation',
    assets: ['data'],
    rescale: [[0, 4000]],
    colormap_name: 'terrain',
    expression: null,
    resampling: 'nearest',
  },
};
const BROKEN: Collection = { id: 'broken', title: 'Broken', 'earthx:capabilities': CAPABILITIES };

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 47]]] };

function opticalScene(id: string, collection: string, day: string): StacItem {
  return { id, collection, bbox: [10, 47, 11, 48], properties: { datetime: `${day}T10:00:00Z` }, assets: {} };
}
function demTile(id: string, start = '2011-01-01T00:00:00Z'): StacItem {
  return { id, collection: 'dem', bbox: [10, 47, 11, 48], properties: { start_datetime: start }, assets: {} };
}

function jsonResponse(body: unknown): Response {
  return { ok: true, status: 200, statusText: '', json: async () => body } as Response;
}
function searchAnswer(features: StacItem[], extra: Record<string, unknown> = {}) {
  return { features, numberReturned: features.length, ...extra };
}
function searchBody(callIndex: number): Record<string, unknown> {
  const [, init] = vi.mocked(fetch).mock.calls[callIndex];
  return JSON.parse((init as RequestInit).body as string);
}

function reset(selected: string[] = ['optical', 'optical-zarr', 'dem']) {
  const datasets = datasetsFrom([OPTICAL, OPTICAL_ZARR, DEM, BROKEN]);
  useAppStore.setState({
    datasets,
    selectedDatasetIds: selected,
    datasetId: selected[0] ?? null,
    sections: [],
    openSectionId: null,
    items: [],
    groups: [],
    activeGroupIndex: 0,
    expandedGroupIndex: 0,
    selectedIds: [],
    layers: [],
    aoi: AOI,
    aoiPoint: null,
    dateFrom: '',
    dateTo: '',
    focusMode: false,
    cropToAoi: false,
    downloaded: {},
    appliedRender: {},
    showCoverage: false,
    coverageDatasetId: null,
    searchCrops: [],
    coverage: null,
    coverageFootprints: null,
    error: null,
    notice: null,
    searching: false,
    searchContext: null,
    loadingMore: false,
    loadMoreError: null,
    fallbackDatasetId: null,
    sceneNameQuery: '',
    sceneLookupLoading: false,
  });
}

beforeEach(() => reset());
afterEach(() => vi.unstubAllGlobals());

describe('toggleDatasetSelected', () => {
  it('ticks and unticks, keeping the list order whatever the order of the clicks', () => {
    reset([]);
    const { toggleDatasetSelected } = useAppStore.getState();
    toggleDatasetSelected('dem');
    toggleDatasetSelected('optical');
    expect(useAppStore.getState().selectedDatasetIds).toEqual(['optical', 'dem']);
    toggleDatasetSelected('optical');
    expect(useAppStore.getState().selectedDatasetIds).toEqual(['dem']);
  });

  it('never ticks a dataset that cannot be shown, nor an unknown one', () => {
    reset(['optical']);
    const { toggleDatasetSelected } = useAppStore.getState();
    toggleDatasetSelected('broken');
    toggleDatasetSelected('no-such-dataset');
    expect(useAppStore.getState().selectedDatasetIds).toEqual(['optical']);
  });

  it('lets an already-ticked dataset that turned unviewable be unticked', () => {
    reset(['optical', 'broken']);
    useAppStore.getState().toggleDatasetSelected('broken');
    expect(useAppStore.getState().selectedDatasetIds).toEqual(['optical']);
  });

  it('moves the active dataset to the first ticked one when it is unticked, and to none with the last', () => {
    reset(['optical', 'dem']);
    useAppStore.getState().toggleDatasetSelected('optical');
    expect(useAppStore.getState().datasetId).toBe('dem');
    useAppStore.getState().toggleDatasetSelected('dem');
    expect(useAppStore.getState().datasetId).toBeNull();
  });

  it('keeps the active dataset when another one is ticked', () => {
    reset(['dem']);
    useAppStore.getState().toggleDatasetSelected('optical');
    expect(useAppStore.getState().datasetId).toBe('dem');
  });

  it('drops the results, which no longer match, but not the pinned layers', () => {
    reset(['optical']);
    const layer = {
      id: 'L1',
      name: 'pinned',
      visible: true,
      opacity: 1,
      overlays: [],
      restore: { datasetId: 'optical' },
    } as never;
    useAppStore.setState({
      layers: [layer],
      sections: [{ datasetId: 'optical', items: [], groups: [], notes: [], groupingError: null, origin: 'search', incomplete: false }],
      openSectionId: 'optical',
      notice: 'x',
    });
    useAppStore.getState().toggleDatasetSelected('dem');
    const state = useAppStore.getState();
    expect(state.sections).toEqual([]);
    expect(state.openSectionId).toBeNull();
    expect(state.notice).toBeNull();
    expect(state.layers).toEqual([layer]);
  });
});

describe('runSearch over several datasets', () => {
  it('asks every ticked dataset in one request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer([]))));
    await useAppStore.getState().runSearch();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(searchBody(0).collections).toEqual(['optical', 'optical-zarr', 'dem']);
  });

  it('asks only viewable ticked datasets', async () => {
    reset(['optical', 'broken']);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer([]))));
    await useAppStore.getState().runSearch();
    expect(searchBody(0).collections).toEqual(['optical']);
  });

  it('refuses with a message when nothing is ticked, and asks nothing', async () => {
    reset([]);
    vi.stubGlobal('fetch', vi.fn());
    await useAppStore.getState().runSearch();
    expect(useAppStore.getState().error).toBe('Pick a dataset first.');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('names why a ticked dataset cannot be shown when it is the only one', async () => {
    reset(['broken']);
    vi.stubGlobal('fetch', vi.fn());
    await useAppStore.getState().runSearch();
    expect(useAppStore.getState().error).toMatch(/cannot be shown yet: earthx:viewer\.group_by/);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('splits the answer into sections, opens the first with scenes and makes it the active dataset', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          searchAnswer([
            demTile('d1'),
            opticalScene('z1', 'optical-zarr', '2026-07-24'),
            opticalScene('z2', 'optical-zarr', '2026-07-25'),
          ]),
        ),
      ),
    );
    await useAppStore.getState().runSearch();
    const state = useAppStore.getState();
    expect(state.sections.map((s) => [s.datasetId, s.items.length])).toEqual([
      ['optical', 0],
      ['optical-zarr', 2],
      ['dem', 1],
    ]);
    expect(state.openSectionId).toBe('optical-zarr');
    expect(state.datasetId).toBe('optical-zarr');
    expect(state.items.map((i) => i.id)).toEqual(['z1', 'z2']);
    expect(state.groups).toHaveLength(2);
    expect(state.activeGroupIndex).toBe(0);
    expect(state.notice).toBe('3 scene(s) in 3 time step(s) across 3 datasets.');
  });

  it("puts each dataset's dropped filters and outages in its own section", async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          searchAnswer([opticalScene('o1', 'optical', '2026-07-24'), demTile('d1')], {
            ignored_filters: ['datetime'],
            ignored_filters_by_collection: { dem: ['datetime'] },
            incomplete_collections: [{ collection: 'optical-zarr', reason: 'timeout' }],
          }),
        ),
      ),
    );
    await useAppStore.getState().runSearch();
    const byId = Object.fromEntries(useAppStore.getState().sections.map((s) => [s.datasetId, s.notes]));
    expect(byId['optical']).toEqual([]);
    expect(byId['optical-zarr']).toEqual(['Results incomplete: the source timed out.']);
    expect(byId['dem']).toEqual(['No time axis – acquired Dec 2010 to Jan 2015']);
  });

  it('leaves out an item of a dataset that was not asked, and says so', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(searchAnswer([opticalScene('o1', 'optical', '2026-07-24'), opticalScene('x', 'other', '2026-07-24')])),
      ),
    );
    await useAppStore.getState().runSearch();
    const state = useAppStore.getState();
    expect(state.sections.flatMap((s) => s.items).map((i) => i.id)).toEqual(['o1']);
    expect(state.notice).toContain('1 scene(s) of other datasets were left out.');
  });

  it('a grouping failure in one dataset leaves the others standing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          searchAnswer([opticalScene('o1', 'optical', '2026-07-24'), { ...demTile('d1'), properties: {} }]),
        ),
      ),
    );
    await useAppStore.getState().runSearch();
    const state = useAppStore.getState();
    expect(state.error).toBeNull();
    expect(state.sections.find((s) => s.datasetId === 'optical')?.items).toHaveLength(1);
    const dem = state.sections.find((s) => s.datasetId === 'dem');
    expect(dem?.items).toEqual([]);
    expect(dem?.notes[0]).toContain('Grouping failed');
  });

  it('a grouping failure in the only dataset is an error, as before', async () => {
    reset(['dem']);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer([{ ...demTile('d1'), properties: {} }]))));
    await useAppStore.getState().runSearch();
    const state = useAppStore.getState();
    expect(state.error).toContain('Grouping failed');
    expect(state.sections).toEqual([]);
  });

  it('no scenes anywhere: every section says so, nothing is open, the notice names the area', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer([]))));
    await useAppStore.getState().runSearch();
    const state = useAppStore.getState();
    expect(state.sections.map((s) => s.notes)).toEqual([
      ['No scenes for this area.'],
      ['No scenes for this area.'],
      ['No scenes for this area.'],
    ]);
    // The dropdown still shows a dataset — the one that was active.
    expect(state.openSectionId).toBe('optical');
    expect(state.items).toEqual([]);
    expect(state.notice).toBe('No scenes found for this area.');
    expect(state.datasetId).toBe('optical');
  });

  it('with several datasets and a date range, an empty answer runs the fallback for the dataset the dropdown opens with, only for it', async () => {
    useAppStore.setState({ dateFrom: '2026-07-01', dateTo: '2026-07-31' });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer([]))));
    await useAppStore.getState().runSearch();
    const probes = vi.mocked(fetch).mock.calls.slice(1).map((_, i) => searchBody(i + 1));
    expect(probes.length).toBeGreaterThan(0);
    expect(probes.every((body) => JSON.stringify(body.collections) === '["optical"]')).toBe(true);
    const state = useAppStore.getState();
    expect(state.notice).toBe('No scenes found for this area and date range.');
    expect(state.sections.map((s) => [s.datasetId, s.origin, s.notes[0]])).toEqual([
      ['optical', 'fallback', 'No results in the chosen time range, nor within ±90 days.'],
      ['optical-zarr', 'search', 'No scenes for this area.'],
      ['dem', 'search', 'No scenes for this area.'],
    ]);
    expect(state.searching).toBe(false);
  });

  it('with one dataset that has a time axis, an empty answer still runs the fallback', async () => {
    reset(['optical']);
    useAppStore.setState({ dateFrom: '2026-07-01', dateTo: '2026-07-31' });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer([]))));
    await useAppStore.getState().runSearch();
    expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThan(1);
    expect(useAppStore.getState().notice).toContain('±90 days');
  });

  it('with one dataset, keeps the old notice and reads a missing per-collection breakdown from the flat list', async () => {
    reset(['dem']);
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(searchAnswer([demTile('d1')], { ignored_filters: ['datetime'] }))),
    );
    await useAppStore.getState().runSearch();
    const state = useAppStore.getState();
    expect(state.notice).toBe('1 scene(s) in 1 time step(s). No time axis – acquired Dec 2010 to Jan 2015.');
    expect(state.sections[0].notes).toEqual(['No time axis – acquired Dec 2010 to Jan 2015']);
  });

  it('a failed search leaves no stale sections behind', async () => {
    useAppStore.setState({
      sections: [{ datasetId: 'optical', items: [], groups: [], notes: [], groupingError: null, origin: 'search', incomplete: false }],
      openSectionId: 'optical',
    });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')));
    await useAppStore.getState().runSearch();
    const state = useAppStore.getState();
    expect(state.error).toContain('Search failed');
    expect(state.sections).toEqual([]);
    expect(state.openSectionId).toBeNull();
    expect(state.searching).toBe(false);
  });
});

describe('changing the selection while a search runs', () => {
  it('is ignored: the answer would land on a selection it did not ask', () => {
    useAppStore.setState({ searching: true });
    useAppStore.getState().toggleDatasetSelected('optical');
    expect(useAppStore.getState().selectedDatasetIds).toEqual(['optical', 'optical-zarr', 'dem']);
  });
});

describe('setOpenSection: the dropdown of the results', () => {
  async function searched() {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          searchAnswer([
            opticalScene('o1', 'optical', '2026-07-24'),
            opticalScene('z1', 'optical-zarr', '2026-07-25'),
            opticalScene('z2', 'optical-zarr', '2026-07-26'),
            demTile('d1'),
          ]),
        ),
      ),
    );
    await useAppStore.getState().runSearch();
  }

  it('opens one section at a time and mirrors its scenes', async () => {
    await searched();
    useAppStore.getState().setOpenSection('optical-zarr');
    const state = useAppStore.getState();
    expect(state.openSectionId).toBe('optical-zarr');
    expect(state.datasetId).toBe('optical-zarr');
    expect(state.items.map((i) => i.id)).toEqual(['z1', 'z2']);
    expect(state.groups).toHaveLength(2);
  });

  it('there is no way to show no dataset: an empty dataset can be chosen, and it shows nothing', async () => {
    await searched();
    useAppStore.getState().setOpenSection('dem');
    useAppStore.getState().setOpenSection('optical-zarr');
    useAppStore.getState().setOpenSection('optical');
    const state = useAppStore.getState();
    expect(state.openSectionId).toBe('optical');
    expect(state.sections).toHaveLength(3);
  });

  it('choosing a dataset without scenes shows its notes and no scenes, and keeps the panel', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer([opticalScene('o1', 'optical', '2026-07-24')]))));
    await useAppStore.getState().runSearch();
    useAppStore.getState().setOpenSection('dem');
    const state = useAppStore.getState();
    expect(state.openSectionId).toBe('dem');
    expect(state.datasetId).toBe('dem');
    expect(state.items).toEqual([]);
    expect(state.groups).toEqual([]);
    expect(state.sections).toHaveLength(3);
  });

  it('opening the section that is already open is harmless', async () => {
    await searched();
    useAppStore.getState().setOpenSection('optical');
    useAppStore.getState().setOpenSection('optical');
    expect(useAppStore.getState().openSectionId).toBe('optical');
    expect(useAppStore.getState().items.map((i) => i.id)).toEqual(['o1']);
  });

  it('an unknown section changes nothing', async () => {
    await searched();
    const before = useAppStore.getState();
    useAppStore.getState().setOpenSection('nope');
    expect(useAppStore.getState().openSectionId).toBe(before.openSectionId);
    expect(useAppStore.getState().items).toBe(before.items);
  });

  it('opening a section clears the scene selection and leaves the full-resolution view', async () => {
    await searched();
    useAppStore.setState({
      selectedIds: ['o1'],
      focusMode: true,
      cropToAoi: true,
      downloaded: { o1: { tileUrl: 't', bounds: [0, 0, 1, 1], asset: 'a', minZoom: 0, maxZoom: 1 } },
      appliedRender: { rescale: '0,1' },
      playing: true,
    });
    useAppStore.getState().setOpenSection('optical-zarr');
    const state = useAppStore.getState();
    expect(state.selectedIds).toEqual([]);
    expect(state.focusMode).toBe(false);
    expect(state.cropToAoi).toBe(false);
    expect(state.downloaded).toEqual({});
    expect(state.appliedRender).toEqual({});
    expect(state.playing).toBe(false);
  });
});

// Otto, 30.09.2026 (replacing his F5 (2) of the same day): the map follows the
// dropdown. A dataset with browse=full_resolution has its AOI crop drawn as part of
// its results — on the map while it is the chosen dataset, not as a pinned layer.
describe('the map follows the dropdown (AOI crops)', () => {
  const MIXED = [opticalScene('o1', 'optical', '2026-07-24'), demTile('d1'), demTile('d2', '2012-06-01T00:00:00Z')];

  // What the map draws besides the browse view, for the current state.
  function onMap(): string[] {
    const s = useAppStore.getState();
    return layersOnMap(s.layers, s.searchCrops, s.openSectionId).map((l) => l.restore.datasetId ?? '');
  }

  async function searchMixed() {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer(MIXED))));
    await useAppStore.getState().runSearch();
  }

  it('keeps the DEM crop off the map while an optical dataset is the chosen one', async () => {
    await searchMixed();
    const state = useAppStore.getState();
    expect(state.openSectionId).toBe('optical');
    expect(state.searchCrops.filter((c) => c.restore.datasetId === 'dem')).toHaveLength(2);
    expect(onMap()).toEqual([]);
    // and nothing was pinned into the layer manager
    expect(state.layers).toEqual([]);
    expect(state.focusMode).toBe(false);
  });

  it('draws the crop as soon as the DEM is chosen, and takes it off again when another dataset is', async () => {
    await searchMixed();
    useAppStore.getState().setOpenSection('dem');
    expect(onMap()).toEqual(['dem', 'dem']);
    useAppStore.getState().setOpenSection('optical-zarr');
    expect(onMap()).toEqual([]);
    useAppStore.getState().setOpenSection('dem');
    expect(onMap()).toEqual(['dem', 'dem']);
  });

  it('shows the crop right after a search over the DEM alone, without the single full-resolution view', async () => {
    reset(['dem']);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer([demTile('d1')]))));
    await useAppStore.getState().runSearch();
    expect(useAppStore.getState().openSectionId).toBe('dem');
    expect(onMap()).toEqual(['dem']);
    expect(useAppStore.getState().focusMode).toBe(false);
    expect(useAppStore.getState().layers).toEqual([]);
  });

  it('a repeat search replaces the crops instead of stacking a second set', async () => {
    await searchMixed();
    await useAppStore.getState().runSearch();
    expect(useAppStore.getState().searchCrops).toHaveLength(2);
  });

  it('a repeat search that finds no DEM tiles takes the old crops away', async () => {
    await searchMixed();
    vi.mocked(fetch).mockResolvedValue(jsonResponse(searchAnswer([opticalScene('o1', 'optical', '2026-07-24')])));
    await useAppStore.getState().runSearch();
    expect(useAppStore.getState().searchCrops).toEqual([]);
  });

  it('changing the selection, a failed search and "Clear all" take the crops away', async () => {
    await searchMixed();
    useAppStore.getState().toggleDatasetSelected('optical-zarr');
    expect(useAppStore.getState().searchCrops).toEqual([]);
    await searchMixed();
    vi.mocked(fetch).mockRejectedValue(new Error('down'));
    await useAppStore.getState().runSearch();
    expect(useAppStore.getState().searchCrops).toEqual([]);
    vi.mocked(fetch).mockResolvedValue(jsonResponse(searchAnswer(MIXED)));
    await useAppStore.getState().runSearch();
    useAppStore.getState().clearAll();
    expect(useAppStore.getState().searchCrops).toEqual([]);
  });

  it('a layer the user pinned stays on the map whatever dataset is chosen; the crop comes and goes with the dropdown', async () => {
    const mine = { id: 'U', name: 'mine', visible: true, opacity: 1, overlays: [], restore: { datasetId: 'optical-zarr' } } as never;
    useAppStore.setState({ layers: [mine] });
    await searchMixed();
    for (const open of ['optical', 'dem', 'optical-zarr', 'dem', 'optical'] as const) {
      useAppStore.getState().setOpenSection(open);
      const drawn = onMap();
      expect(drawn).toContain('optical-zarr'); // the pinned one, always
      expect(drawn.filter((d) => d === 'dem')).toHaveLength(open === 'dem' ? 2 : 0);
    }
  });

  it('the user pins the crop of the chosen dataset themselves; it then stays when another is chosen', async () => {
    await searchMixed();
    useAppStore.getState().setOpenSection('dem');
    useAppStore.getState().pinSearchCrops();
    const state = useAppStore.getState();
    expect(state.layers).toHaveLength(2);
    expect(state.layers.every((l) => l.restore.datasetId === 'dem' && l.visible)).toBe(true);
    expect(state.layerManagerOpen).toBe(true);
    expect(new Set(state.layers.map((l) => l.id)).size).toBe(2);
    useAppStore.getState().setOpenSection('optical');
    expect(onMap()).toEqual(['dem', 'dem']); // the pinned copies, not the search crops
    expect(useAppStore.getState().searchCrops).toHaveLength(2);
  });

  it('pinning needs a crop: with an optical dataset chosen it says so and pins nothing', async () => {
    await searchMixed();
    useAppStore.getState().pinSearchCrops();
    expect(useAppStore.getState().layers).toEqual([]);
    expect(useAppStore.getState().error).toContain('Nothing to pin');
  });

  it('says something else when the visualisation exists but no scene has a bounding box', async () => {
    reset(['dem']);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer([{ ...demTile('d1'), bbox: null }]))));
    await useAppStore.getState().runSearch();
    const state = useAppStore.getState();
    expect(state.searchCrops).toEqual([]);
    expect(state.notice).toContain('none of its scenes carries a bounding box');
  });

  it('says so when the dataset has no standard visualisation to draw', async () => {
    reset(['dem']);
    useAppStore.setState({ datasets: datasetsFrom([{ ...DEM, 'earthx:default_render': null }]) });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer([demTile('d1')]))));
    await useAppStore.getState().runSearch();
    const state = useAppStore.getState();
    expect(state.searchCrops).toEqual([]);
    expect(state.notice).toContain('has no default visualisation yet');
  });

  it('"Clear all" keeps what the user pinned', async () => {
    const mine = { id: 'U', name: 'mine', visible: true, opacity: 1, overlays: [], restore: { datasetId: 'dem' } } as never;
    useAppStore.setState({ layers: [mine] });
    await searchMixed();
    useAppStore.getState().clearAll();
    expect(useAppStore.getState().layers.map((l) => l.id)).toEqual(['U']);
  });
});

// Otto, 30.09.2026: layers the user pinned — from any dataset — stay in the layer
// manager and on the map whichever dataset the dropdown shows.
describe('pinned layers of several datasets stay', () => {
  async function searchedAndPinned() {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          searchAnswer([
            opticalScene('o1', 'optical', '2026-07-24'),
            opticalScene('z1', 'optical-zarr', '2026-07-25'),
            demTile('d1'),
          ]),
        ),
      ),
    );
    await useAppStore.getState().runSearch();
    useAppStore.getState().addCurrentToLayers(); // optical
    useAppStore.getState().setOpenSection('optical-zarr');
    useAppStore.getState().addCurrentToLayers(); // optical-zarr
    useAppStore.getState().setOpenSection('dem');
    useAppStore.getState().pinSearchCrops(); // the DEM crop
  }

  function drawn(): string[] {
    const s = useAppStore.getState();
    return layersOnMap(s.layers, s.searchCrops, s.openSectionId)
      .filter((l) => l.visible)
      .map((l) => l.restore.datasetId ?? '');
  }

  it('keeps layers of three datasets on the map together, whichever dataset the dropdown shows', async () => {
    await searchedAndPinned();
    for (const open of ['optical', 'dem', 'optical-zarr'] as const) {
      useAppStore.getState().setOpenSection(open);
      expect(new Set(drawn())).toEqual(new Set(['optical', 'optical-zarr', 'dem']));
    }
    // the search crop of the chosen DEM is on top of that, not instead of it
    useAppStore.getState().setOpenSection('dem');
    expect(drawn().filter((d) => d === 'dem').length).toBe(2); // the pinned copy + the crop
  });

  it('gives every pinned layer its own id, also when several are pinned within one millisecond', async () => {
    await searchedAndPinned();
    const ids = useAppStore.getState().layers.map((l) => l.id);
    expect(ids).toHaveLength(3);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('keeps them when the selection changes and when the next search runs', async () => {
    await searchedAndPinned();
    const pinned = useAppStore.getState().layers.map((l) => l.id);
    useAppStore.getState().toggleDatasetSelected('optical');
    expect(useAppStore.getState().layers.map((l) => l.id)).toEqual(pinned);
    vi.mocked(fetch).mockResolvedValue(jsonResponse(searchAnswer([demTile('d1')])));
    await useAppStore.getState().runSearch();
    expect(useAppStore.getState().layers.map((l) => l.id)).toEqual(pinned);
  });

  it('hiding one layer leaves the others visible', async () => {
    await searchedAndPinned();
    const [first, ...rest] = useAppStore.getState().layers;
    useAppStore.getState().toggleLayerVisible(first.id);
    const state = useAppStore.getState();
    expect(state.layers.find((l) => l.id === first.id)?.visible).toBe(false);
    expect(state.layers.filter((l) => rest.some((r) => r.id === l.id)).every((l) => l.visible)).toBe(true);
  });

  it('choosing a layer makes its dataset the active one and opens its section', async () => {
    await searchedAndPinned();
    useAppStore.getState().setOpenSection('optical-zarr');
    const opticalLayer = useAppStore.getState().layers.find((l) => l.restore.datasetId === 'optical');
    expect(opticalLayer).toBeDefined();
    useAppStore.getState().selectLayer(opticalLayer!.id);
    const state = useAppStore.getState();
    expect(state.datasetId).toBe('optical');
    expect(state.openSectionId).toBe('optical');
    expect(state.items.map((i) => i.id)).toEqual(['o1']);
    expect(state.layers.filter((l) => l.visible)).toHaveLength(3);
  });

  it('choosing a layer of a dataset that is no longer ticked ticks it again; the list shows nothing of another dataset', async () => {
    await searchedAndPinned();
    useAppStore.getState().toggleDatasetSelected('optical'); // wipes sections, unticks it
    const layer = useAppStore.getState().layers.find((l) => l.restore.datasetId === 'optical')!;
    useAppStore.getState().selectLayer(layer.id);
    const state = useAppStore.getState();
    expect(state.selectedDatasetIds).toContain('optical');
    expect(state.datasetId).toBe('optical');
    expect(state.items).toEqual([]);
    expect(state.openSectionId).toBeNull();
  });
});

// Otto, 30.09.2026: the "Coverage" button draws the coverage of one picked
// dataset, independent of the dataset whose results the map shows.
describe('coverage of a chosen dataset', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ cells: [] })));
  });

  it('is off by default, and showCoverageFor turns it on for that dataset', () => {
    expect(useAppStore.getState().showCoverage).toBe(false);
    useAppStore.getState().showCoverageFor('dem');
    expect(useAppStore.getState().showCoverage).toBe(true);
    expect(useAppStore.getState().coverageDatasetId).toBe('dem');
  });

  it('follows its own choice, not the dropdown', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer([opticalScene('o1', 'optical', '2026-07-24'), demTile('d1')]))));
    await useAppStore.getState().runSearch();
    useAppStore.getState().showCoverageFor('dem');
    useAppStore.getState().setOpenSection('optical');
    useAppStore.getState().setOpenSection('optical-zarr');
    expect(useAppStore.getState().coverageDatasetId).toBe('dem');
    expect(useAppStore.getState().showCoverage).toBe(true);
  });

  it('refuses a dataset that is not picked', () => {
    reset(['optical']);
    useAppStore.getState().showCoverageFor('dem');
    expect(useAppStore.getState().showCoverage).toBe(false);
    expect(useAppStore.getState().coverageDatasetId).toBeNull();
  });

  it('hideCoverage clears it', () => {
    useAppStore.getState().showCoverageFor('dem');
    useAppStore.setState({ coverage: { dataset_id: 'dem' } as never });
    useAppStore.getState().hideCoverage();
    const state = useAppStore.getState();
    expect(state.showCoverage).toBe(false);
    expect(state.coverageDatasetId).toBeNull();
    expect(state.coverage).toBeNull();
  });

  it('unpicking that dataset switches it off; unpicking another leaves it', () => {
    useAppStore.getState().showCoverageFor('dem');
    useAppStore.getState().toggleDatasetSelected('optical');
    expect(useAppStore.getState().showCoverage).toBe(true);
    useAppStore.getState().toggleDatasetSelected('dem');
    expect(useAppStore.getState().showCoverage).toBe(false);
    expect(useAppStore.getState().coverageDatasetId).toBeNull();
  });

  it('asks the coverage route for that dataset', async () => {
    useAppStore.getState().showCoverageFor('dem');
    await new Promise((resolve) => setTimeout(resolve, 0));
    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toContain('/coverage/dem');
  });
});

// M3-10b: a mock backend answering by request body — one page per page token,
// probes and full-day searches of the fallback by their `datetime`.
function routed(answer: (body: Record<string, unknown>) => unknown | Promise<unknown>) {
  return vi.fn(async (_url: string, init?: RequestInit) =>
    jsonResponse(await answer(init?.body ? JSON.parse(init.body as string) : {})),
  );
}
function page(features: StacItem[], next: string | null, extra: Record<string, unknown> = {}) {
  const links = next ? [{ rel: 'next', href: '/stac/search', method: 'POST', body: { token: next } }] : [];
  return { ...searchAnswer(features, extra), links };
}
function scenes(prefix: string, collection: string, day: string, n = 100): StacItem[] {
  return Array.from({ length: n }, (_, i) => opticalScene(`${prefix}${i}`, collection, day));
}
const search = () => useAppStore.getState().runSearch();
const loadMore = () => useAppStore.getState().loadMore();
const count = (id: string) => useAppStore.getState().sections.find((s) => s.datasetId === id)?.items.length;

// The first walk stops at 300 scenes with token `p4` left; `p4` has five more.
const PAGES: Record<string, ReturnType<typeof page>> = {
  '': page(scenes('a', 'optical', '2026-07-24'), 'p2'),
  p2: page(scenes('b', 'optical', '2026-07-25'), 'p3'),
  p3: page(scenes('c', 'optical-zarr', '2026-07-20'), 'p4'),
  p4: page(
    [
      opticalScene('n1', 'optical', '2026-07-26'),
      opticalScene('n2', 'optical', '2026-07-24'),
      opticalScene('m1', 'optical-zarr', '2026-07-21'),
      opticalScene('m2', 'optical-zarr', '2026-07-21'),
      demTile('d1'),
    ],
    null,
  ),
};
const byToken = (body: Record<string, unknown>) => PAGES[(body.token as string | undefined) ?? ''];

describe('"Load more" (M3-10 F1)', () => {
  it('keeps the token the first 300 scenes left, and offers nothing more once the search is complete', async () => {
    vi.stubGlobal('fetch', routed(byToken));
    await search();
    expect(useAppStore.getState().searchContext?.nextToken).toBe('p4');
    await loadMore();
    expect(useAppStore.getState().searchContext?.nextToken).toBeNull();
    expect(useAppStore.getState().loadMoreError).toBeNull();
  });

  it('continues the same search with the token and puts each new scene in its own dataset', async () => {
    vi.stubGlobal('fetch', routed(byToken));
    await search();
    await loadMore();
    const calls = vi.mocked(fetch).mock.calls.length;
    const { token, ...rest } = searchBody(calls - 1);
    const { token: _first, ...firstRest } = searchBody(0);
    expect(token).toBe('p4');
    expect(rest).toEqual(firstRest);
    expect([count('optical'), count('optical-zarr'), count('dem')]).toEqual([202, 102, 1]);
    expect(useAppStore.getState().notice).toBe('305 scene(s) in 6 time step(s) across 3 datasets.');
  });

  it('keeps the dataset and the time step that are open, found by key, and the picked scenes', async () => {
    vi.stubGlobal('fetch', routed(byToken));
    await search();
    const { setActiveGroupIndex, toggleSelected } = useAppStore.getState();
    setActiveGroupIndex(1); // 2026-07-24; newest first
    toggleSelected('a3');
    expect(useAppStore.getState().groups[1].label).toBe('2026-07-24');
    await loadMore(); // adds 2026-07-26, which comes first now
    const state = useAppStore.getState();
    expect(state.openSectionId).toBe('optical');
    expect(state.items).toHaveLength(202);
    expect(state.groups[state.activeGroupIndex].label).toBe('2026-07-24');
    expect(state.expandedGroupIndex).toBe(state.activeGroupIndex);
    expect(state.selectedIds).toEqual(['a3']);
  });

  it('asks nothing without a token, and only once for a double click', async () => {
    vi.stubGlobal('fetch', routed(() => page([opticalScene('o1', 'optical', '2026-07-24')], null)));
    await search();
    await loadMore();
    expect(fetch).toHaveBeenCalledTimes(1);

    vi.stubGlobal('fetch', routed(byToken));
    await search();
    await Promise.all([loadMore(), loadMore()]);
    expect(vi.mocked(fetch).mock.calls.filter((_, i) => searchBody(i).token === 'p4')).toHaveLength(1);
  });

  it('a failure keeps what is loaded, says to search again and drops the token', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init?: RequestInit) => {
        const body = JSON.parse(init?.body as string);
        if (body.token === 'p4') return { ok: false, status: 400, statusText: 'Bad Request', json: async () => ({}) } as Response;
        return jsonResponse(byToken(body));
      }),
    );
    await search();
    await loadMore();
    const state = useAppStore.getState();
    expect(state.loadMoreError).toBe('Could not load more results — search again.');
    expect(state.searchContext?.nextToken).toBeNull();
    expect([count('optical'), count('optical-zarr')]).toEqual([200, 100]);
    expect(state.error).toBeNull();
    expect(state.loadingMore).toBe(false);
  });

  it('another AOI or other dates drop the token but keep the results', async () => {
    vi.stubGlobal('fetch', routed(byToken));
    for (const change of [
      () => useAppStore.getState().setDateFrom('2026-01-01'),
      () => useAppStore.getState().setDateTo('2026-12-31'),
      () => useAppStore.getState().setAoi({ ...AOI }),
      () => useAppStore.getState().clearAoi(),
    ]) {
      useAppStore.setState({ aoi: AOI });
      await search();
      change();
      expect(useAppStore.getState().searchContext?.nextToken).toBeNull();
      expect(count('optical')).toBe(200);
    }
  });

  it('an answer that comes after the selection changed is dropped', async () => {
    let answer: (value: unknown) => void = () => {};
    vi.stubGlobal(
      'fetch',
      routed((body) => (body.token === 'p4' ? new Promise((resolve) => (answer = resolve)) : byToken(body))),
    );
    await search();
    const pending = loadMore();
    useAppStore.getState().toggleDatasetSelected('dem');
    answer(PAGES.p4);
    await pending;
    const state = useAppStore.getState();
    expect(state.sections).toEqual([]);
    expect(state.loadingMore).toBe(false);
  });

  it('with one dataset, the notice counts the matches without telling to narrow the search', async () => {
    reset(['optical']);
    vi.stubGlobal('fetch', routed((body) => ({ ...byToken(body), numberMatched: 305 })));
    await search();
    expect(useAppStore.getState().notice).toBe('300 scene(s) in 3 time step(s). 305 matched in total.');
  });
});

describe('±90-day fallback for the dataset chosen in the dropdown (M3-10 F7)', () => {
  const RANGE = '2026-07-01T00:00:00Z/2026-07-31T23:59:59Z';
  const NEAREST_DAY = '2026-06-20T00:00:00Z/2026-06-20T23:59:59Z';
  // The search finds optical scenes and the DEM tile, nothing of the Zarr dataset;
  // a probe of the Zarr dataset finds a scene on 2026-06-20, which has two.
  function backend(extra: Record<string, unknown> = {}, probe?: () => unknown) {
    return routed((body) => {
      if (body.datetime === RANGE) {
        return page([opticalScene('o1', 'optical', '2026-07-24'), demTile('d1')], null, extra);
      }
      if (body.datetime === NEAREST_DAY) {
        return page([opticalScene('f1', 'optical-zarr', '2026-06-20'), opticalScene('f2', 'optical-zarr', '2026-06-20')], null);
      }
      return probe ? probe() : page([opticalScene('p1', 'optical-zarr', '2026-06-20')], null);
    });
  }
  const choose = (id: string) => useAppStore.getState().setOpenSection(id);
  const zarr = () => useAppStore.getState().sections.find((s) => s.datasetId === 'optical-zarr')!;

  beforeEach(() => useAppStore.setState({ dateFrom: '2026-07-01', dateTo: '2026-07-31' }));

  it('does not run at search time while another dataset has scenes', async () => {
    vi.stubGlobal('fetch', backend());
    await search();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(zarr().notes).toEqual(['No scenes for this area.']);
  });

  it('runs when an empty dataset with a time axis is chosen, asks only that dataset, and shows the nearest day', async () => {
    vi.stubGlobal('fetch', backend());
    await search();
    choose('optical-zarr');
    await vi.waitFor(() => expect(zarr().origin).toBe('fallback'));
    const later = vi.mocked(fetch).mock.calls.slice(1).map((_, i) => searchBody(i + 1));
    expect(later.every((body) => JSON.stringify(body.collections) === '["optical-zarr"]')).toBe(true);
    expect(later.every((body) => JSON.stringify(body.intersects) === JSON.stringify(searchBody(0).intersects))).toBe(true);
    const state = useAppStore.getState();
    expect(zarr().notes[0]).toBe('No results in the chosen time range — nearest scene: 2026-06-20');
    expect(state.items.map((i) => i.id)).toEqual(['f1', 'f2']);
    expect(state.fallbackDatasetId).toBeNull();
    expect(count('optical')).toBe(1);
    expect(state.notice).toBe('2 scene(s) in 2 time step(s) across 3 datasets.');
  });

  it('runs once per search: choosing the dataset again asks nothing', async () => {
    vi.stubGlobal('fetch', backend());
    await search();
    choose('optical-zarr');
    await vi.waitFor(() => expect(zarr().origin).toBe('fallback'));
    const asked = vi.mocked(fetch).mock.calls.length;
    choose('optical');
    choose('optical-zarr');
    await Promise.resolve();
    expect(fetch).toHaveBeenCalledTimes(asked);
  });

  it('does not run for a dataset without a time axis, a source that did not answer in full, or without dates', async () => {
    vi.stubGlobal('fetch', backend({ incomplete_collections: [{ collection: 'optical-zarr', reason: 'timeout' }] }));
    await search();
    choose('optical-zarr');
    await Promise.resolve();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(zarr().notes).toEqual(['Results incomplete: the source timed out.']);

    useAppStore.setState({ dateFrom: '', dateTo: '' });
    vi.stubGlobal('fetch', routed(() => page([opticalScene('o1', 'optical', '2026-07-24')], null)));
    await search();
    choose('optical-zarr');
    choose('dem');
    await Promise.resolve();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('says so in the box when there is nothing within ±90 days either', async () => {
    vi.stubGlobal('fetch', backend({}, () => page([], null)));
    await search();
    choose('optical-zarr');
    await vi.waitFor(() => expect(zarr().origin).toBe('fallback'));
    expect(zarr().notes).toEqual(['No results in the chosen time range, nor within ±90 days.']);
    expect(zarr().items).toEqual([]);
  });

  it('a failure is said in the box, not as an error of the whole search, and is not retried', async () => {
    vi.stubGlobal('fetch', backend({}, () => Promise.reject(new Error('source down'))));
    await search();
    choose('optical-zarr');
    await vi.waitFor(() => expect(zarr().origin).toBe('fallback'));
    expect(zarr().notes[0]).toBe('Could not look for the nearest date: source down');
    expect(useAppStore.getState().error).toBeNull();
    expect(useAppStore.getState().fallbackDatasetId).toBeNull();
  });

  it('an answer that comes after a new search is dropped', async () => {
    let answer: (value: unknown) => void = () => {};
    vi.stubGlobal('fetch', backend({}, () => new Promise((resolve) => (answer = resolve))));
    await search();
    choose('optical-zarr');
    expect(useAppStore.getState().fallbackDatasetId).toBe('optical-zarr');
    vi.stubGlobal('fetch', routed(() => page([opticalScene('o1', 'optical', '2026-07-24')], null)));
    await search();
    answer(page([opticalScene('p1', 'optical-zarr', '2026-06-20')], null));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(zarr().origin).toBe('search');
    expect(zarr().items).toEqual([]);
  });

  it('"Load more" leaves a dataset showing its fallback as it is while the search has nothing for it', async () => {
    vi.stubGlobal(
      'fetch',
      routed((body) => {
        if (body.datetime === NEAREST_DAY) return page([opticalScene('f1', 'optical-zarr', '2026-06-20')], null);
        if (JSON.stringify(body.collections) === '["optical-zarr"]') {
          return page([opticalScene('p1', 'optical-zarr', '2026-06-20')], null);
        }
        const answer = { '': 'q2', q2: 'q3', q3: 'q4' } as Record<string, string>;
        const token = (body.token as string | undefined) ?? '';
        return token === 'q4'
          ? page([opticalScene('n1', 'optical', '2026-07-30')], null)
          : page(scenes(token || 'a', 'optical', '2026-07-24'), answer[token]);
      }),
    );
    await search();
    choose('optical-zarr');
    await vi.waitFor(() => expect(zarr().origin).toBe('fallback'));
    await loadMore();
    expect(count('optical')).toBe(301);
    expect(zarr().items.map((i) => i.id)).toEqual(['f1']);
    expect(useAppStore.getState().openSectionId).toBe('optical-zarr');
  });
});

describe('looking up a scene by name in every ticked dataset (M3-10 F8)', () => {
  const NAME = 'S2B_42';
  function catalogues(answers: Record<string, number | StacItem>) {
    return vi.fn(async (url: string) => {
      const dataset = decodeURIComponent(String(url).split('/collections/')[1]?.split('/')[0] ?? '');
      if (String(url).includes('/statistics')) return jsonResponse({});
      const answer = answers[dataset] ?? 404;
      if (typeof answer !== 'number') return jsonResponse(answer);
      return { ok: false, status: answer, statusText: '', json: async () => ({ detail: `status ${answer}` }) } as Response;
    });
  }
  const lookUp = () => {
    useAppStore.setState({ sceneNameQuery: NAME });
    return useAppStore.getState().findSceneByName();
  };

  it('asks every ticked dataset; the scene opens in its dataset and every other says it has none', async () => {
    vi.stubGlobal('fetch', catalogues({ 'optical-zarr': opticalScene(NAME, 'optical-zarr', '2026-07-24') }));
    await lookUp();
    const asked = vi.mocked(fetch).mock.calls.map(([url]) => String(url).split('/collections/')[1]?.split('/')[0]);
    expect(asked).toEqual(['optical', 'optical-zarr', 'dem']);
    const state = useAppStore.getState();
    expect(state.openSectionId).toBe('optical-zarr');
    expect(state.datasetId).toBe('optical-zarr');
    expect(state.selectedIds).toEqual([NAME]);
    expect(state.sections.map((s) => [s.datasetId, s.items.length, s.notes])).toEqual([
      ['optical', 0, [`No scene named "${NAME}".`]],
      ['optical-zarr', 1, []],
      ['dem', 0, [`No scene named "${NAME}".`]],
    ]);
    expect(state.notice).toBe(`Scene ${NAME}, found by name in Optical (Zarr).`);
    expect(state.flyToBbox).toEqual([10, 47, 11, 48]);
  });

  it('has no page to load more and no crop of the last search left', async () => {
    vi.stubGlobal('fetch', routed(byToken));
    await search();
    useAppStore.setState({ searchCrops: [{ id: 'S1', restore: { datasetId: 'dem' } } as never] });
    vi.stubGlobal('fetch', catalogues({ optical: opticalScene(NAME, 'optical', '2026-07-24') }));
    await lookUp();
    const state = useAppStore.getState();
    expect(state.searchContext).toBeNull();
    expect(state.searchCrops).toEqual([]);
    expect(state.sections.every((s) => s.origin === 'name')).toBe(true);
  });

  it('a dataset that failed says so in its box while another has the scene', async () => {
    vi.stubGlobal('fetch', catalogues({ optical: 502, 'optical-zarr': 400, dem: demTile(NAME) }));
    await lookUp();
    const state = useAppStore.getState();
    expect(state.openSectionId).toBe('dem');
    expect(state.sections[0].notes).toEqual(['Scene lookup failed: status 502']);
    expect(state.sections[1].notes).toEqual(['Not a valid scene name for this dataset.']);
    expect(state.error).toBeNull();
  });

  it.each([
    [{}, `No scene named "${NAME}" in the selected datasets — the catalogues name the same scene differently.`],
    [{ optical: 400, 'optical-zarr': 400, dem: 400 }, 'Not a valid scene name.'],
    [{ 'optical-zarr': 503 }, 'Scene lookup failed (Optical (Zarr)): status 503'],
  ])('when no dataset has the scene, only the error changes (%o)', async (answers, error) => {
    vi.stubGlobal('fetch', routed(byToken));
    await search();
    const before = useAppStore.getState();
    vi.stubGlobal('fetch', catalogues(answers as Record<string, number>));
    await lookUp();
    const state = useAppStore.getState();
    expect(state.error).toBe(error);
    expect(state.sections).toBe(before.sections);
    expect(state.searchContext).toBe(before.searchContext);
    expect(state.sceneLookupLoading).toBe(false);
  });

  it('a scene of a dataset without browsable preview is shown in full resolution once that dataset is chosen', async () => {
    vi.stubGlobal(
      'fetch',
      catalogues({ optical: opticalScene(NAME, 'optical', '2026-07-24'), dem: demTile(NAME) }),
    );
    await lookUp();
    expect(useAppStore.getState().openSectionId).toBe('optical');
    expect(useAppStore.getState().focusMode).toBe(false);
    useAppStore.getState().setOpenSection('dem');
    await vi.waitFor(() => expect(useAppStore.getState().focusMode).toBe(true));
    expect(useAppStore.getState().cropToAoi).toBe(false);
    expect(Object.keys(useAppStore.getState().downloaded)).toEqual([NAME]);
  });

  it('the selection cannot change while a lookup runs', () => {
    useAppStore.setState({ sceneLookupLoading: true });
    useAppStore.getState().toggleDatasetSelected('dem');
    expect(useAppStore.getState().selectedDatasetIds).toEqual(['optical', 'optical-zarr', 'dem']);
  });
});
