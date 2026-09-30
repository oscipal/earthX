// @vitest-environment jsdom
//
// M3-10: the dataset filter's ticks, one search over every ticked dataset, the
// results split into one section per dataset, the active dataset, the crops a
// search pins for a dataset with no browsable preview (F5) and pinned layers of
// several datasets side by side (F4).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
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
    coverage: null,
    coverageFootprints: null,
    error: null,
    notice: null,
    searching: false,
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
      sections: [{ datasetId: 'optical', items: [], groups: [], notes: [], groupingError: null }],
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

  it('with several datasets and a date range, an empty answer runs no ±90-day fallback yet (M3-10b)', async () => {
    useAppStore.setState({ dateFrom: '2026-07-01', dateTo: '2026-07-31' });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer([]))));
    await useAppStore.getState().runSearch();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(useAppStore.getState().notice).toBe('No scenes found for this area and date range.');
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
      sections: [{ datasetId: 'optical', items: [], groups: [], notes: [], groupingError: null }],
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

describe('the heatmap follows the active dataset only', () => {
  it('ticking another dataset leaves the active one and its heatmap', () => {
    reset(['optical']);
    useAppStore.setState({ coverage: { dataset_id: 'optical' } as never });
    useAppStore.getState().toggleDatasetSelected('dem');
    expect(useAppStore.getState().coverage).not.toBeNull();
  });

  it('a search that opens a section of another dataset drops the old heatmap', async () => {
    useAppStore.setState({ coverage: { dataset_id: 'optical' } as never });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer([opticalScene('z1', 'optical-zarr', '2026-07-24')]))));
    await useAppStore.getState().runSearch();
    expect(useAppStore.getState().datasetId).toBe('optical-zarr');
    expect(useAppStore.getState().coverage).toBeNull();
  });
});

describe('setOpenSection and setDatasetId', () => {
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

  it('setDatasetId opens the dataset\'s section where the search has one', async () => {
    await searched();
    useAppStore.getState().setDatasetId('optical-zarr');
    expect(useAppStore.getState().openSectionId).toBe('optical-zarr');
    expect(useAppStore.getState().items).toHaveLength(2);
  });

  it('setDatasetId only moves the heatmap before any search, and drops the old coverage', () => {
    useAppStore.setState({
      coverage: { dataset_id: 'optical' } as never,
      coverageFootprints: { type: 'FeatureCollection', features: [] },
    });
    useAppStore.getState().setDatasetId('dem');
    const state = useAppStore.getState();
    expect(state.datasetId).toBe('dem');
    expect(state.coverage).toBeNull();
    expect(state.coverageFootprints).toBeNull();
    expect(state.sections).toEqual([]);
  });

  it('setDatasetId ignores a dataset that is not ticked, and the one already active', () => {
    reset(['optical', 'dem']);
    useAppStore.getState().setDatasetId('optical-zarr');
    expect(useAppStore.getState().datasetId).toBe('optical');
    useAppStore.setState({ coverage: { dataset_id: 'optical' } as never });
    useAppStore.getState().setDatasetId('optical');
    expect(useAppStore.getState().coverage).not.toBeNull();
  });
});

// F5 (Otto, 30.09.2026): a dataset with browse=full_resolution shows up as the
// AOI crop after every search, whichever section is open.
describe('full-resolution datasets after a search (F5)', () => {
  const MIXED = [opticalScene('o1', 'optical', '2026-07-24'), demTile('d1'), demTile('d2', '2012-06-01T00:00:00Z')];

  it('pins the DEM crop even though an optical section is the open one', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer(MIXED))));
    await useAppStore.getState().runSearch();
    const state = useAppStore.getState();
    expect(state.openSectionId).toBe('optical');
    expect(state.focusMode).toBe(false);
    expect(state.layers.filter((l) => l.fromSearch && l.restore.datasetId === 'dem')).toHaveLength(2);
    expect(state.layers.every((l) => l.restore.cropToAoi && l.restore.focusMode && l.visible)).toBe(true);
    // Only the DEM is pinned: the datasets with a preview show it in the list first.
    expect(state.layers.every((l) => l.restore.datasetId === 'dem')).toBe(true);
  });

  it('pins it for a search over the DEM alone too, without entering the single full-resolution view', async () => {
    reset(['dem']);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer([demTile('d1')]))));
    await useAppStore.getState().runSearch();
    const state = useAppStore.getState();
    expect(state.layers).toHaveLength(1);
    expect(state.layers[0].fromSearch).toBe(true);
    expect(state.openSectionId).toBe('dem');
    expect(state.focusMode).toBe(false);
  });

  it('does not depend on which section is opened afterwards', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer(MIXED))));
    await useAppStore.getState().runSearch();
    const before = useAppStore.getState().layers;
    useAppStore.getState().setOpenSection('dem');
    useAppStore.getState().setOpenSection('optical');
    expect(useAppStore.getState().layers).toBe(before);
  });

  it('a repeat search replaces the earlier crops instead of stacking a second set', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer(MIXED))));
    await useAppStore.getState().runSearch();
    await useAppStore.getState().runSearch();
    expect(useAppStore.getState().layers.filter((l) => l.restore.datasetId === 'dem')).toHaveLength(2);
  });

  it('a repeat search that finds no DEM tiles takes the old crops away', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer(MIXED))));
    await useAppStore.getState().runSearch();
    vi.mocked(fetch).mockResolvedValue(jsonResponse(searchAnswer([opticalScene('o1', 'optical', '2026-07-24')])));
    await useAppStore.getState().runSearch();
    expect(useAppStore.getState().layers).toEqual([]);
  });

  it('leaves the layers the user pinned, and search crops of datasets this search did not ask', async () => {
    const userLayer = { id: 'U', name: 'mine', visible: true, opacity: 1, overlays: [], restore: { datasetId: 'dem' } } as never;
    const otherCrop = {
      id: 'S',
      name: 'earlier',
      visible: true,
      opacity: 1,
      overlays: [],
      fromSearch: true,
      restore: { datasetId: 'some-other-full-resolution-dataset' },
    } as never;
    useAppStore.setState({ layers: [userLayer, otherCrop] });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer(MIXED))));
    await useAppStore.getState().runSearch();
    const ids = useAppStore.getState().layers.map((l) => l.id);
    expect(ids).toContain('U');
    expect(ids).toContain('S');
    expect(useAppStore.getState().layers.filter((l) => l.fromSearch && l.restore.datasetId === 'dem')).toHaveLength(2);
  });

  it('says something else when the visualisation exists but no scene has a bounding box', async () => {
    reset(['dem']);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer([{ ...demTile('d1'), bbox: null }]))));
    await useAppStore.getState().runSearch();
    const state = useAppStore.getState();
    expect(state.layers).toEqual([]);
    expect(state.notice).toContain('none of its scenes carries a bounding box');
  });

  it('says so when the dataset has no standard visualisation to draw', async () => {
    reset(['dem']);
    useAppStore.setState({ datasets: datasetsFrom([{ ...DEM, 'earthx:default_render': null }]) });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer([demTile('d1')]))));
    await useAppStore.getState().runSearch();
    const state = useAppStore.getState();
    expect(state.layers).toEqual([]);
    expect(state.notice).toContain('has no default visualisation yet');
  });

  it('"Clear all" removes what a search pinned and keeps what the user pinned', async () => {
    const userLayer = { id: 'U', name: 'mine', visible: true, opacity: 1, overlays: [], restore: { datasetId: 'dem' } } as never;
    useAppStore.setState({ layers: [userLayer] });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchAnswer(MIXED))));
    await useAppStore.getState().runSearch();
    useAppStore.getState().clearAll();
    const state = useAppStore.getState();
    expect(state.layers.map((l) => l.id)).toEqual(['U']);
    expect(state.sections).toEqual([]);
    expect(state.openSectionId).toBeNull();
  });
});

// F4 (Otto, 30.09.2026): pinned layers of different datasets stay in the layer
// manager and on the map together, whichever section is open.
describe('pinned layers of several datasets (F4)', () => {
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
  }

  it('keeps layers of two datasets visible together, whichever section is open', async () => {
    await searchedAndPinned();
    const datasetsPinned = () =>
      new Set(useAppStore.getState().layers.filter((l) => l.visible).map((l) => l.restore.datasetId));
    expect(datasetsPinned()).toEqual(new Set(['optical', 'optical-zarr', 'dem']));
    for (const open of ['optical', 'dem', 'optical-zarr'] as const) {
      useAppStore.getState().setOpenSection(open);
      expect(datasetsPinned()).toEqual(new Set(['optical', 'optical-zarr', 'dem']));
    }
  });

  it('gives every pinned layer its own id, also when two are pinned within one millisecond', async () => {
    await searchedAndPinned();
    const ids = useAppStore.getState().layers.map((l) => l.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('keeps them when the tick boxes change and when the next search runs', async () => {
    await searchedAndPinned();
    const manual = useAppStore.getState().layers.filter((l) => !l.fromSearch).map((l) => l.id);
    expect(manual).toHaveLength(2);
    useAppStore.getState().toggleDatasetSelected('optical');
    expect(useAppStore.getState().layers.filter((l) => !l.fromSearch).map((l) => l.id)).toEqual(manual);
    vi.mocked(fetch).mockResolvedValue(jsonResponse(searchAnswer([demTile('d1')])));
    await useAppStore.getState().runSearch();
    expect(useAppStore.getState().layers.filter((l) => !l.fromSearch).map((l) => l.id)).toEqual(manual);
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
    const opticalLayer = useAppStore.getState().layers.find((l) => l.restore.datasetId === 'optical' && !l.fromSearch);
    expect(opticalLayer).toBeDefined();
    useAppStore.setState({ coverage: { dataset_id: 'optical-zarr' } as never });
    useAppStore.getState().selectLayer(opticalLayer!.id);
    const state = useAppStore.getState();
    expect(state.datasetId).toBe('optical');
    expect(state.openSectionId).toBe('optical');
    expect(state.items.map((i) => i.id)).toEqual(['o1']);
    expect(state.coverage).toBeNull();
    expect(state.layers.filter((l) => l.visible)).toHaveLength(3);
  });

  it('choosing a layer of a dataset that is no longer ticked ticks it again, keeping the results', async () => {
    await searchedAndPinned();
    useAppStore.getState().toggleDatasetSelected('optical'); // wipes sections, unticks it
    const layer = useAppStore.getState().layers.find((l) => l.restore.datasetId === 'optical')!;
    useAppStore.getState().selectLayer(layer.id);
    const state = useAppStore.getState();
    expect(state.selectedDatasetIds).toContain('optical');
    expect(state.datasetId).toBe('optical');
    // No section for it any more: the list shows nothing of another dataset.
    expect(state.items).toEqual([]);
    expect(state.openSectionId).toBeNull();
  });

  it('never leaves the list holding another dataset\'s scenes when a dataset without a section becomes active', async () => {
    await searchedAndPinned();
    useAppStore.setState({
      selectedIds: ['z1'],
      focusMode: true,
      downloaded: { z1: { tileUrl: 't', bounds: [0, 0, 1, 1], asset: 'a', minZoom: 0, maxZoom: 1 } },
    });
    // A scene-name lookup keeps a single section; the other ticked dataset has none.
    useAppStore.setState({
      sections: useAppStore.getState().sections.filter((s) => s.datasetId === 'optical-zarr'),
      openSectionId: 'optical-zarr',
      datasetId: 'optical-zarr',
    });
    useAppStore.getState().setDatasetId('dem');
    const state = useAppStore.getState();
    expect(state.datasetId).toBe('dem');
    expect(state.items).toEqual([]);
    expect(state.groups).toEqual([]);
    expect(state.selectedIds).toEqual([]);
    expect(state.focusMode).toBe(false);
    expect(state.downloaded).toEqual({});
  });
});
