// The one piece of the store M2-10 changed that is testable without a map:
// pinning the active time step into the layer manager. Before M2-10 a scene
// whose source publishes no quicklook produced no overlay at all, so pinning a
// time step of `sentinel-2-l2a-zarr3` yielded "Nothing to add".

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { useAppStore } from './store';
import type { Collection, StacItem } from './types';

// M3-12: a full `earthx:capabilities` block, reused by both fixtures below —
// only `time_range` matters to anything here, so one constant says so once.
const CAPABILITIES = {
  roi: true,
  time_range: true,
  band_math: true,
  interpolation: true,
  ml_processing: true,
  quad_pol: false,
  single_coverage_product: false,
};

const ZARR_LIKE: Collection = {
  id: 'sentinel-2-l2a-zarr3',
  title: 'Sentinel-2 L2A (Zarr3)',
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

const COG_LIKE: Collection = {
  id: 'sentinel-2-c1-l2a',
  title: 'Sentinel-2 L2A',
  'earthx:capabilities': CAPABILITIES,
  'earthx:viewer': {
    group_by: ['datetime'],
    min_zoom: 0,
    max_zoom: 19,
    browse: 'quicklook',
    quicklook_nodata_max: 16,
    results_group_by: ['datetime'],
  },
};

function scene(overrides: Partial<StacItem> = {}): StacItem {
  return {
    id: 'S2B_1',
    bbox: [10, 47, 11, 48],
    properties: { datetime: '2026-07-24T10:00:00Z' },
    assets: { SR_10m: { href: 'https://data.test/x.zarr/r10m', roles: ['data'] } },
    ...overrides,
  };
}

function pin(collection: Collection, items: StacItem[]) {
  useAppStore.setState({
    datasets: datasetsFrom([collection]),
    datasetId: collection.id,
    items,
    groups: [{ key: ['2026-07-24'], label: '2026-07-24', items }],
    activeGroupIndex: 0,
    selectedIds: [],
    focusMode: false,
    layers: [],
    error: null,
    notice: null,
  });
  useAppStore.getState().addCurrentToLayers();
  return useAppStore.getState();
}

describe('addCurrentToLayers while browsing', () => {
  beforeEach(() => {
    useAppStore.setState({ layers: [], error: null, notice: null });
  });

  it('pins tiles for a source that publishes no quicklook', () => {
    const state = pin(ZARR_LIKE, [scene()]);

    expect(state.error).toBeNull();
    expect(state.layers).toHaveLength(1);
    const [overlay] = state.layers[0].overlays;
    expect(overlay.kind).toBe('raster');
    if (overlay.kind !== 'raster') return;
    expect(overlay.minZoom).toBe(8);
    expect(overlay.maxZoom).toBe(8);
    expect(new URL(overlay.tileUrl, 'http://x').searchParams.get('rescale')).toBe('0,0.3');
  });

  it('a pinned preview is not downloadable — it is not a full-resolution view', () => {
    // `download.downloadRequestFor` needs `restore.focusMode`, and a browse
    // layer has none. The check lives here because pinning tiles in browse mode
    // is new, and a preview must not turn into an export path by looking like
    // one (KLAERUNGEN B11: a crop hands out the source's pixels).
    const state = pin(ZARR_LIKE, [scene()]);
    expect(state.layers[0].restore.focusMode).toBe(false);
  });

  it('a scene with no bounding box is skipped, not placed wrongly', () => {
    const state = pin(ZARR_LIKE, [scene({ bbox: null })]);
    expect(state.layers).toHaveLength(0);
    expect(state.error).toMatch(/Nothing to add/);
  });

  it('a dataset with neither quicklook nor standard visualisation still says so', () => {
    const state = pin(COG_LIKE, [scene()]);
    expect(state.layers).toHaveLength(0);
    expect(state.error).toMatch(/Nothing to add/);
  });
});

// M3-09 §10 (Otto): "Crop & merge to AOI" pins one layer per group instead
// of one for the whole selection.
describe('addCurrentToLayers while cropped in focus mode (M3-09 §10)', () => {
  const AOI: GeoJSON.Polygon = {
    type: 'Polygon',
    coordinates: [
      [
        [0, 40],
        [20, 40],
        [20, 55],
        [0, 55],
        [0, 40],
      ],
    ],
  };
  const GROUPS = [
    { key: ['a'], label: 'Overpass A', items: [scene({ id: 'S1' }), scene({ id: 'S2' })] },
    { key: ['b'], label: 'Overpass B', items: [scene({ id: 'S3' })] },
  ];

  function focusedDownload(id: string): { tileUrl: string; bounds: [number, number, number, number]; asset: string; minZoom: number; maxZoom: number } {
    return { tileUrl: `/tiles/${id}/{z}/{x}/{y}`, bounds: [1, 47, 2, 48], asset: 'visual', minZoom: 0, maxZoom: 19 };
  }

  beforeEach(() => {
    useAppStore.setState({
      datasets: datasetsFrom([COG_LIKE]),
      datasetId: COG_LIKE.id,
      groups: GROUPS,
      activeGroupIndex: 0,
      selectedIds: [],
      focusMode: true,
      aoi: AOI,
      cropToAoi: true,
      appliedRender: {},
      downloaded: { S1: focusedDownload('S1'), S2: focusedDownload('S2'), S3: focusedDownload('S3') },
      layers: [],
      error: null,
      notice: null,
    });
  });

  it('pins one layer per group, not one for the whole selection', () => {
    useAppStore.getState().addCurrentToLayers();
    const { layers } = useAppStore.getState();
    expect(layers).toHaveLength(2);
    const itemIdSets = layers.map((l) => [...l.restore.itemIds].sort());
    expect(itemIdSets).toContainEqual(['S1', 'S2']);
    expect(itemIdSets).toContainEqual(['S3']);
  });

  it('each per-group layer carries its own itemIds as its one groupItemIds group (M3-17)', () => {
    useAppStore.getState().addCurrentToLayers();
    for (const layer of useAppStore.getState().layers) {
      expect(layer.restore.groupItemIds).toEqual([layer.restore.itemIds]);
    }
  });

  it('an uncropped "View full selection" layer still splits groupItemIds by group (M3-17)', () => {
    useAppStore.setState({ cropToAoi: false });
    useAppStore.getState().addCurrentToLayers();
    const [layer] = useAppStore.getState().layers;
    expect(layer.restore.groupItemIds.map((g) => [...g].sort())).toEqual(
      expect.arrayContaining([['S1', 'S2'], ['S3']]),
    );
  });

  it('clips each group layer\'s tile URLs to the AOI and marks it cropped', () => {
    useAppStore.getState().addCurrentToLayers();
    for (const layer of useAppStore.getState().layers) {
      expect(layer.restore.cropToAoi).toBe(true);
      expect(layer.restore.aoi).toEqual(AOI);
      for (const overlay of layer.overlays) {
        if (overlay.kind === 'raster') expect(overlay.tileUrl.startsWith('earthx-clip://')).toBe(true);
      }
    }
  });

  it('only pins the groups a narrower selection actually covers', () => {
    useAppStore.setState({ selectedIds: ['S1'] });
    useAppStore.getState().addCurrentToLayers();
    const { layers } = useAppStore.getState();
    expect(layers).toHaveLength(1);
    expect(layers[0].restore.itemIds).toEqual(['S1']);
  });

  it('still pins one layer for the whole selection when the view is uncropped', () => {
    useAppStore.setState({ cropToAoi: false });
    useAppStore.getState().addCurrentToLayers();
    const { layers } = useAppStore.getState();
    expect(layers).toHaveLength(1);
    expect([...layers[0].restore.itemIds].sort()).toEqual(['S1', 'S2', 'S3']);
    expect(layers[0].restore.cropToAoi).toBe(false);
    for (const overlay of layers[0].overlays) {
      if (overlay.kind === 'raster') expect(overlay.tileUrl.startsWith('earthx-clip://')).toBe(false);
    }
  });
});

// V-2 point 3: "Zoom to selection" zooms to the AOI; failing that, to the
// pinned layer images; failing that too, it has nothing to do (App.tsx's
// `canZoom` then keeps the button disabled).
describe('zoomToView', () => {
  const AOI: GeoJSON.Geometry = {
    type: 'Polygon',
    coordinates: [
      [
        [1, 1],
        [2, 1],
        [2, 2],
        [1, 2],
        [1, 1],
      ],
    ],
  };

  beforeEach(() => {
    useAppStore.setState({ aoi: null, layers: [], flyToBbox: null });
  });

  it('prefers the AOI over pinned layers', () => {
    useAppStore.setState({
      aoi: AOI,
      layers: [
        {
          id: 'L1',
          name: 'x',
          visible: true,
          opacity: 1,
          overlays: [{ kind: 'raster', tileUrl: 'x', bounds: [40, 40, 41, 41], minZoom: 1, maxZoom: 1 }],
          restore: {
            focusMode: false,
            downloaded: {},
            appliedRender: {},
            activeGroupIndex: 0,
            selectedIds: [],
            itemIds: [],
            groupItemIds: [],
            aoi: null,
            cropToAoi: false,
            datasetId: null,
          },
        },
      ],
    });
    useAppStore.getState().zoomToView();
    expect(useAppStore.getState().flyToBbox).toEqual([1, 1, 2, 2]);
  });

  it('falls back to the pinned layer images without an AOI, raster and image overlays alike', () => {
    useAppStore.setState({
      layers: [
        {
          id: 'L1',
          name: 'x',
          visible: true,
          opacity: 1,
          overlays: [
            { kind: 'raster', tileUrl: 'x', bounds: [10, 10, 11, 11], minZoom: 1, maxZoom: 1 },
            {
              kind: 'image',
              url: 'x',
              coords: [
                [20, 21],
                [22, 21],
                [22, 20],
                [20, 20],
              ],
              nodataMax: 16,
            },
          ],
          restore: {
            focusMode: false,
            downloaded: {},
            appliedRender: {},
            activeGroupIndex: 0,
            selectedIds: [],
            itemIds: [],
            groupItemIds: [],
            aoi: null,
            cropToAoi: false,
            datasetId: null,
          },
        },
      ],
    });
    useAppStore.getState().zoomToView();
    expect(useAppStore.getState().flyToBbox).toEqual([10, 10, 22, 21]);
  });

  it('does nothing with neither an AOI nor pinned layers', () => {
    useAppStore.getState().zoomToView();
    expect(useAppStore.getState().flyToBbox).toBeNull();
  });
});

// V-11: the results list can collapse its open group without moving
// activeGroupIndex (the time step the map/time slider show) — and MapView
// hides quicklooks whenever nothing is expanded, so this has to actually
// happen, not just look right in the panel.
describe('toggleResultsGroup', () => {
  const a = { id: 'a', properties: { datetime: '2026-07-25T10:00:00Z' }, assets: {} };
  const b = { id: 'b', properties: { datetime: '2026-07-24T10:00:00Z' }, assets: {} };

  beforeEach(() => {
    useAppStore.setState({
      groups: [
        { key: ['2026-07-25'], label: '2026-07-25', items: [a] },
        { key: ['2026-07-24'], label: '2026-07-24', items: [b] },
      ],
      activeGroupIndex: 0,
      expandedGroupIndex: 0,
    });
  });

  it('collapses the open group without touching activeGroupIndex', () => {
    useAppStore.getState().toggleResultsGroup(0);
    const s = useAppStore.getState();
    expect(s.expandedGroupIndex).toBeNull();
    expect(s.activeGroupIndex).toBe(0);
  });

  it('opening a different group expands it and moves activeGroupIndex along', () => {
    useAppStore.getState().toggleResultsGroup(1);
    const s = useAppStore.getState();
    expect(s.expandedGroupIndex).toBe(1);
    expect(s.activeGroupIndex).toBe(1);
  });

  it('re-opening the collapsed group restores both', () => {
    useAppStore.getState().toggleResultsGroup(0); // collapse
    useAppStore.getState().toggleResultsGroup(0); // re-open the same one
    const s = useAppStore.getState();
    expect(s.expandedGroupIndex).toBe(0);
    expect(s.activeGroupIndex).toBe(0);
  });

  it('setActiveGroupIndex (time slider, "play") re-syncs expandedGroupIndex even after a manual collapse', () => {
    useAppStore.getState().toggleResultsGroup(0); // collapse
    useAppStore.getState().setActiveGroupIndex(1); // scrub the time slider
    const s = useAppStore.getState();
    expect(s.activeGroupIndex).toBe(1);
    expect(s.expandedGroupIndex).toBe(1);
  });
});

// M2-17: finding one scene by its exact name, without an AOI or date range.
// Only the currently selected dataset is asked (Otto, 23.09.2026); on any
// failure only `error` may change — items/groups/selection/AOI/date range
// stay exactly as they were.
describe('findSceneByName', () => {
  const AOI: GeoJSON.Geometry = {
    type: 'Polygon',
    coordinates: [
      [
        [1, 1],
        [2, 1],
        [2, 2],
        [1, 2],
        [1, 1],
      ],
    ],
  };
  const PRIOR_ITEM = scene({ id: 'prior' });

  function jsonResponse(status: number, body: unknown): Response {
    return {
      ok: status >= 200 && status < 300,
      status,
      statusText: '',
      json: async () => body,
    } as Response;
  }

  beforeEach(() => {
    useAppStore.setState({
      datasets: datasetsFrom([COG_LIKE]),
      datasetId: COG_LIKE.id,
      sceneNameQuery: '',
      sceneLookupLoading: false,
      items: [PRIOR_ITEM],
      groups: [{ key: ['2026-07-24'], label: '2026-07-24', items: [PRIOR_ITEM] }],
      activeGroupIndex: 0,
      selectedIds: ['prior'],
      aoi: AOI,
      dateFrom: '2026-01-01',
      dateTo: '2026-01-31',
      flyToBbox: null,
      error: null,
      notice: null,
    });
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('does nothing for an empty query', async () => {
    useAppStore.setState({ sceneNameQuery: '   ' });
    await useAppStore.getState().findSceneByName();
    expect(fetch).not.toHaveBeenCalled();
    expect(useAppStore.getState().items).toEqual([PRIOR_ITEM]);
  });

  it('trims the query before asking the backend', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(200, scene({ id: 'S2A_1' })));
    useAppStore.setState({ sceneNameQuery: '  S2A_1  ' });
    await useAppStore.getState().findSceneByName();
    const url = vi.mocked(fetch).mock.calls[0][0] as string;
    expect(url).toContain('/S2A_1');
    expect(url).not.toContain('%20');
  });

  it('a found scene replaces the results, is selected, and the map flies to it — AOI and dates untouched', async () => {
    const found = scene({ id: 'S2A_1', bbox: [5, 5, 6, 6] });
    vi.mocked(fetch).mockResolvedValue(jsonResponse(200, found));
    useAppStore.setState({ sceneNameQuery: 'S2A_1' });
    await useAppStore.getState().findSceneByName();
    const s = useAppStore.getState();
    expect(s.items).toEqual([found]);
    expect(s.groups).toHaveLength(1);
    expect(s.selectedIds).toEqual(['S2A_1']);
    expect(s.flyToBbox).toEqual([5, 5, 6, 6]);
    expect(s.notice).toMatch(/S2A_1/);
    expect(s.notice).toMatch(/found by name/);
    expect(s.error).toBeNull();
    expect(s.aoi).toEqual(AOI);
    expect(s.dateFrom).toBe('2026-01-01');
    expect(s.dateTo).toBe('2026-01-31');
  });

  it('an unknown name names the dataset and leaves everything else as it was', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(404, { detail: 'Not Found' }));
    useAppStore.setState({ sceneNameQuery: 'does-not-exist' });
    await useAppStore.getState().findSceneByName();
    const s = useAppStore.getState();
    expect(s.error).toContain('does-not-exist');
    expect(s.error).toContain(COG_LIKE.title);
    expect(s.items).toEqual([PRIOR_ITEM]);
    expect(s.groups).toHaveLength(1);
    expect(s.selectedIds).toEqual(['prior']);
    expect(s.aoi).toEqual(AOI);
  });

  it('a malformed name is reported as such, not as an upstream failure', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(400, { detail: 'item id contains characters …' }));
    useAppStore.setState({ sceneNameQuery: 'not valid!' });
    await useAppStore.getState().findSceneByName();
    expect(useAppStore.getState().error).toBe('Not a valid scene name.');
  });

  it('an upstream failure is reported as a lookup failure, distinct from "not found"', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(502, { detail: 'the source could not be reached' }));
    useAppStore.setState({ sceneNameQuery: 'S2A_1' });
    await useAppStore.getState().findSceneByName();
    const s = useAppStore.getState();
    expect(s.error).toMatch(/^Scene lookup failed:/);
    expect(s.items).toEqual([PRIOR_ITEM]);
  });

  it('a dataset that cannot be shown yet is refused before any request', async () => {
    const [unviewable] = datasetsFrom([{ ...COG_LIKE, 'earthx:viewer': undefined }]);
    useAppStore.setState({ datasets: [unviewable], datasetId: unviewable.id, sceneNameQuery: 'S2A_1' });
    await useAppStore.getState().findSceneByName();
    expect(fetch).not.toHaveBeenCalled();
    expect(useAppStore.getState().error).toMatch(/cannot be shown yet/);
  });
});

// M3-08: `aoiPoint` travels alongside `aoi` (and `lastAoi`/`lastAoiPoint`) without
// leaking into an unrelated AOI, since only `runSearch` ever reads it.
describe('AOI point tracking', () => {
  const POINT: GeoJSON.Point = { type: 'Point', coordinates: [10, 49] };
  const SQUARE: GeoJSON.Geometry = {
    type: 'Polygon',
    coordinates: [[[9.95, 48.95], [10.05, 48.95], [10.05, 49.05], [9.95, 49.05], [9.95, 48.95]]],
  };
  const RECTANGLE: GeoJSON.Geometry = {
    type: 'Polygon',
    coordinates: [[[8, 47], [12, 47], [12, 51], [8, 51], [8, 47]]],
  };

  // No jsdom in this project (Vitest runs plain Node, `preferences.test.ts`) —
  // `setAoi`/`clearAoi`/`useLastAoi` schedule a debounced coverage refresh via
  // `window.setTimeout`, which this stub only needs to not throw; the debounced
  // refresh itself (against no dataset here) is not what these tests are about.
  beforeEach(() => {
    vi.stubGlobal('window', { setTimeout: (...args: Parameters<typeof setTimeout>) => setTimeout(...args), clearTimeout });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('setAoi with a point keeps both the square and the point', () => {
    useAppStore.getState().setAoi(SQUARE, POINT);
    const s = useAppStore.getState();
    expect(s.aoi).toBe(SQUARE);
    expect(s.aoiPoint).toBe(POINT);
  });

  it('setAoi without a point clears any point a previous AOI had', () => {
    useAppStore.getState().setAoi(SQUARE, POINT);
    useAppStore.getState().setAoi(RECTANGLE);
    expect(useAppStore.getState().aoiPoint).toBeNull();
  });

  it('clearAoi clears the point along with the AOI', () => {
    useAppStore.getState().setAoi(SQUARE, POINT);
    useAppStore.getState().clearAoi();
    const s = useAppStore.getState();
    expect(s.aoi).toBeNull();
    expect(s.aoiPoint).toBeNull();
  });

  it('useLastAoi restores the point the last AOI was drawn from', () => {
    useAppStore.getState().setAoi(SQUARE, POINT);
    useAppStore.getState().clearAoi();
    useAppStore.getState().useLastAoi();
    const s = useAppStore.getState();
    expect(s.aoi).toBe(SQUARE);
    expect(s.aoiPoint).toBe(POINT);
  });
});

// M3-08: `runSearch` asks `intersects` for a point or an ordinary polygon AOI,
// `bbox` for a rectangle or a polygon over the point budget (geoUtils.searchArea).
describe('runSearch', () => {
  function jsonResponse(status: number, body: unknown): Response {
    return { ok: status >= 200 && status < 300, status, statusText: '', json: async () => body } as Response;
  }

  function requestBody(callIndex: number): Record<string, unknown> {
    const [, init] = vi.mocked(fetch).mock.calls[callIndex];
    return JSON.parse((init as RequestInit).body as string);
  }

  function baseState(overrides: Partial<ReturnType<typeof useAppStore.getState>> = {}) {
    useAppStore.setState({
      datasets: datasetsFrom([COG_LIKE]),
      datasetId: COG_LIKE.id,
      dateFrom: '',
      dateTo: '',
      items: [],
      groups: [],
      selectedIds: [],
      error: null,
      notice: null,
      ...overrides,
    });
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('a point AOI searches by the point itself, not its buffer square', async () => {
    const point: GeoJSON.Point = { type: 'Point', coordinates: [10, 49] };
    const square: GeoJSON.Geometry = {
      type: 'Polygon',
      coordinates: [[[9.95, 48.95], [10.05, 48.95], [10.05, 49.05], [9.95, 49.05], [9.95, 48.95]]],
    };
    baseState({ aoi: square, aoiPoint: point });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, { features: [], numberReturned: 0 })));

    await useAppStore.getState().runSearch();

    expect(requestBody(0).intersects).toEqual(point);
    expect(requestBody(0).bbox).toBeUndefined();
  });

  it('a rectangle AOI still searches by bbox', async () => {
    const rectangle: GeoJSON.Geometry = {
      type: 'Polygon',
      coordinates: [[[8, 47], [12, 47], [12, 51], [8, 51], [8, 47]]],
    };
    baseState({ aoi: rectangle, aoiPoint: null });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, { features: [], numberReturned: 0 })));

    await useAppStore.getState().runSearch();

    expect(requestBody(0).bbox).toEqual([8, 47, 12, 51]);
    expect(requestBody(0).intersects).toBeUndefined();
    expect(useAppStore.getState().notice).toBe('No scenes found for this area.');
  });

  it('an ordinary polygon AOI searches by intersects', async () => {
    const triangle: GeoJSON.Geometry = { type: 'Polygon', coordinates: [[[8, 47], [12, 47], [8, 51], [8, 47]]] };
    baseState({ aoi: triangle, aoiPoint: null });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, { features: [], numberReturned: 0 })));

    await useAppStore.getState().runSearch();

    expect(requestBody(0).intersects).toEqual(triangle);
  });

  it('a polygon over the point budget falls back to bbox with a notice (F2a)', async () => {
    const n = 1001;
    const ring: [number, number][] = Array.from({ length: n }, (_, i) => [
      10 + 0.01 * Math.cos((2 * Math.PI * i) / n),
      49 + 0.01 * Math.sin((2 * Math.PI * i) / n),
    ]);
    ring.push(ring[0]);
    const huge: GeoJSON.Geometry = { type: 'Polygon', coordinates: [ring] };
    baseState({ aoi: huge, aoiPoint: null });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, { features: [], numberReturned: 0 })));

    await useAppStore.getState().runSearch();

    expect(requestBody(0).intersects).toBeUndefined();
    expect(requestBody(0).bbox).toBeDefined();
    expect(useAppStore.getState().notice).toMatch(/more than 1000 points/);
  });
});

// M3-19 (Otto, 23.09.2026): without an AOI, `refreshCoverage` asks for the
// visible map extent and reuses an already-loaded answer for a viewport that
// stays inside it, instead of firing a request on every `moveend`. With an
// AOI nothing changes — every call still asks fresh.
describe('refreshCoverage without an AOI (M3-19)', () => {
  // A fresh id per test: the reuse cache is module-level (store.ts), so two
  // tests sharing a dataset id would see each other's cached answers.
  let testCounter = 0;
  let DATASET_ID = '';

  function jsonResponse(status: number, body: unknown): Response {
    return { ok: status >= 200 && status < 300, status, statusText: '', json: async () => body } as Response;
  }

  function coverageResponse(datasetId: string, level: number): unknown {
    return {
      dataset_id: datasetId,
      grid: 'geotile',
      level,
      counting: 'centroid',
      cells: [],
      counted: 0,
      total_count: 100_000,
      completeness: 'complete',
      max_count: 0,
      histogram: [],
      histogram_interval: 'month',
      footprints_advised: false,
      from_cache: false,
      extent: null,
    };
  }

  beforeEach(() => {
    DATASET_ID = `coverage-reuse-m3-19-${testCounter++}`;
    vi.useFakeTimers();
    vi.stubGlobal('window', { setTimeout: (...args: Parameters<typeof setTimeout>) => setTimeout(...args), clearTimeout });
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        const zoom = Number(new URL(url, 'http://x').searchParams.get('zoom'));
        return jsonResponse(200, coverageResponse(DATASET_ID, zoom));
      }),
    );
    useAppStore.setState({
      datasetId: DATASET_ID,
      showCoverage: true,
      aoi: null,
      aoiPoint: null,
      dateFrom: '',
      dateTo: '',
      coverage: null,
      coverageFootprints: null,
      coverageError: null,
      coverageLoading: false,
      viewportBbox: null,
      viewportSize: null,
      mapZoom: 1.6,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  // Both viewports lie inside 0°–180° / 0°–85° (levelForViewport(0, 1920,
  // 1080) === 4, coverage.test.ts), so both round to the very same block.
  it('does not repeat a request for a small pan that stays inside the same block', async () => {
    const { setMapViewport } = useAppStore.getState();

    setMapViewport(0, [10, 10, 60, 60], { width: 1920, height: 1080 });
    await vi.advanceTimersByTimeAsync(500);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(useAppStore.getState().coverage?.level).toBe(4);

    setMapViewport(0, [15, 15, 55, 55], { width: 1920, height: 1080 });
    await vi.advanceTimersByTimeAsync(500);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(useAppStore.getState().coverage?.level).toBe(4);
  });

  it('asks again once the zoom changes the level, even at the same spot', async () => {
    const { setMapViewport } = useAppStore.getState();

    setMapViewport(0, [10, 10, 60, 60], { width: 1920, height: 1080 });
    await vi.advanceTimersByTimeAsync(500);
    expect(fetch).toHaveBeenCalledTimes(1);

    // levelForViewport(3, 1920, 1080) === 7 (coverage.test.ts) — a different
    // level, so the cache entry at level 4 does not cover this request.
    setMapViewport(3, [10, 10, 60, 60], { width: 1920, height: 1080 });
    await vi.advanceTimersByTimeAsync(500);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(useAppStore.getState().coverage?.level).toBe(7);
  });

  it('with an AOI, every viewport report still asks fresh — no reuse', async () => {
    const aoi: GeoJSON.Geometry = {
      type: 'Polygon',
      coordinates: [[[10, 49], [11, 49], [11, 50], [10, 50], [10, 49]]],
    };
    useAppStore.setState({ aoi });
    const { setMapViewport } = useAppStore.getState();

    setMapViewport(8, [10, 49, 11, 50], { width: 1920, height: 1080 });
    await vi.advanceTimersByTimeAsync(500);
    expect(fetch).toHaveBeenCalledTimes(1);

    // The very same report a second time (e.g. a resize firing `moveend`
    // without the map actually moving) is not treated as reuse either.
    setMapViewport(8, [10, 49, 11, 50], { width: 1920, height: 1080 });
    await vi.advanceTimersByTimeAsync(500);
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});

// M3-17: download follows the view — the crop/originals/disabled decision
// (`download.ts::decideDownloadOutcome`) as the store wires it up for the
// current selection (`openDownloadForSelection`) and a pinned layer
// (`openDownloadDialog`, which alone needs a fetch: a layer's `restore`
// carries tile info, not the STAC items' own asset `href`s).
describe('download outcome (M3-17 plan §4)', () => {
  const AOI: GeoJSON.Polygon = {
    type: 'Polygon',
    coordinates: [
      [
        [0, 40],
        [20, 40],
        [20, 55],
        [0, 55],
        [0, 40],
      ],
    ],
  };

  const COG_DATASET: Collection = {
    id: 'sentinel-2-c1-l2a',
    title: 'Sentinel-2 L2A',
    'earthx:capabilities': CAPABILITIES,
    'earthx:viewer': {
      group_by: ['datetime'],
      min_zoom: 0,
      max_zoom: 19,
      browse: 'quicklook',
      quicklook_nodata_max: 16,
      results_group_by: ['datetime'],
    },
    'earthx:format': 'cog',
    'earthx:source': { asset_hosts: ['data.test'] },
    'earthx:default_render': {
      title: 'True colour',
      assets: ['visual'],
      rescale: null,
      colormap_name: null,
      expression: null,
      resampling: 'nearest',
    },
  };

  const ZARR_DATASET: Collection = {
    id: 'sentinel-2-l2a-zarr3',
    title: 'Sentinel-2 L2A (Zarr3)',
    'earthx:capabilities': CAPABILITIES,
    'earthx:viewer': {
      group_by: ['datetime'],
      min_zoom: 8,
      max_zoom: 14,
      browse: 'preview_tiles',
      quicklook_nodata_max: null,
      results_group_by: ['datetime'],
    },
    'earthx:format': 'zarr',
  };

  function cogScene(id: string): StacItem {
    return scene({ id, assets: { visual: { href: `https://data.test/${id}.tif` } } });
  }

  function jsonResponse(status: number, body: unknown): Response {
    return { ok: status >= 200 && status < 300, status, statusText: '', json: async () => body } as Response;
  }

  beforeEach(() => {
    useAppStore.setState({
      layers: [],
      items: [],
      groups: [],
      selectedIds: [],
      activeGroupIndex: 0,
      focusMode: false,
      cropToAoi: false,
      aoi: null,
      error: null,
      notice: null,
      downloadDialogLayerId: null,
      downloadSelection: false,
      downloadOutcome: null,
      downloadOriginalLinks: null,
    });
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('openDownloadForSelection', () => {
    it('an AOI drawn: the crop outcome, no fetch needed', () => {
      const items = [cogScene('S1'), cogScene('S2')];
      useAppStore.setState({
        datasets: datasetsFrom([COG_DATASET]),
        datasetId: COG_DATASET.id,
        items,
        groups: [{ key: ['a'], label: 'Overpass A', items }],
        aoi: AOI,
      });
      useAppStore.getState().openDownloadForSelection();
      const s = useAppStore.getState();
      expect(s.downloadSelection).toBe(true);
      expect(s.downloadOutcome).toBe('crop');
      expect(s.error).toBeNull();
      expect(fetch).not.toHaveBeenCalled();
    });

    it('no AOI, a COG dataset: the originals outcome, links built straight from store.items', () => {
      const items = [cogScene('S1')];
      useAppStore.setState({
        datasets: datasetsFrom([COG_DATASET]),
        datasetId: COG_DATASET.id,
        items,
        groups: [{ key: ['a'], label: 'Overpass A', items }],
        aoi: null,
      });
      useAppStore.getState().openDownloadForSelection();
      const s = useAppStore.getState();
      expect(s.downloadSelection).toBe(true);
      expect(s.downloadOutcome).toBe('originals');
      expect(s.downloadOriginalLinks).toEqual([
        { itemId: 'S1', groupLabel: 'Overpass A', asset: 'visual', href: 'https://data.test/S1.tif' },
      ]);
      expect(fetch).not.toHaveBeenCalled();
    });

    it('no AOI, a Zarr dataset: disabled, an error naming the reason, dialog not opened', () => {
      const items = [scene({ id: 'S1' })];
      useAppStore.setState({
        datasets: datasetsFrom([ZARR_DATASET]),
        datasetId: ZARR_DATASET.id,
        items,
        groups: [{ key: ['a'], label: 'Overpass A', items }],
        aoi: null,
      });
      useAppStore.getState().openDownloadForSelection();
      const s = useAppStore.getState();
      expect(s.downloadSelection).toBe(false);
      expect(s.error).toMatch(/Draw an AOI/);
    });

    it('nothing picked and no active time step: a defined error, not a crash', () => {
      useAppStore.setState({
        datasets: datasetsFrom([COG_DATASET]),
        datasetId: COG_DATASET.id,
        items: [],
        groups: [],
        aoi: AOI,
      });
      useAppStore.getState().openDownloadForSelection();
      expect(useAppStore.getState().error).toMatch(/Nothing to download/);
    });

    it("an asset href on a host the dataset does not name is left out of the originals", () => {
      const items = [scene({ id: 'S1', assets: { visual: { href: 'https://elsewhere.invalid/x.tif' } } })];
      useAppStore.setState({
        datasets: datasetsFrom([COG_DATASET]),
        datasetId: COG_DATASET.id,
        items,
        groups: [{ key: ['a'], label: 'Overpass A', items }],
        aoi: null,
      });
      useAppStore.getState().openDownloadForSelection();
      expect(useAppStore.getState().downloadOriginalLinks).toEqual([]);
    });
  });

  describe('openDownloadDialog (a pinned layer)', () => {
    function layerFixture(restoreOverrides: Record<string, unknown> = {}) {
      return {
        id: 'L1',
        name: 'test layer',
        visible: true,
        opacity: 1,
        overlays: [],
        restore: {
          focusMode: true,
          downloaded: {},
          appliedRender: {},
          activeGroupIndex: 0,
          selectedIds: [],
          itemIds: ['S1', 'S2'],
          groupItemIds: [['S1'], ['S2']],
          aoi: null,
          cropToAoi: false,
          datasetId: COG_DATASET.id,
          ...restoreOverrides,
        },
      };
    }

    it('a cropped layer: the crop outcome, known without any fetch', async () => {
      useAppStore.setState({
        datasets: datasetsFrom([COG_DATASET]),
        layers: [layerFixture({ cropToAoi: true, aoi: AOI })],
      });
      await useAppStore.getState().openDownloadDialog('L1');
      expect(useAppStore.getState().downloadOutcome).toBe('crop');
      expect(fetch).not.toHaveBeenCalled();
    });

    it('a "View full selection" Zarr layer without an AOI: disabled, known without any fetch', async () => {
      useAppStore.setState({
        datasets: datasetsFrom([ZARR_DATASET]),
        layers: [layerFixture({ datasetId: ZARR_DATASET.id })],
      });
      await useAppStore.getState().openDownloadDialog('L1');
      expect(useAppStore.getState().downloadOutcome).toBe('disabled');
      expect(fetch).not.toHaveBeenCalled();
    });

    it('a "View full selection" COG layer without an AOI: fetches each pinned item once, builds links', async () => {
      useAppStore.setState({
        datasets: datasetsFrom([COG_DATASET]),
        layers: [layerFixture()],
      });
      vi.mocked(fetch).mockImplementation(async (url) => {
        const id = String(url).split('/').pop() ?? '';
        return jsonResponse(200, cogScene(id));
      });

      await useAppStore.getState().openDownloadDialog('L1');

      const s = useAppStore.getState();
      expect(s.downloadOutcome).toBe('originals');
      expect(fetch).toHaveBeenCalledTimes(2);
      expect(s.downloadOriginalLinks).toEqual([
        { itemId: 'S1', groupLabel: 'Group 1', asset: 'visual', href: 'https://data.test/S1.tif' },
        { itemId: 'S2', groupLabel: 'Group 2', asset: 'visual', href: 'https://data.test/S2.tif' },
      ]);
    });

    it('a layer pinned before M3-17 (no groupItemIds) falls back to one group', async () => {
      useAppStore.setState({
        datasets: datasetsFrom([COG_DATASET]),
        layers: [layerFixture({ groupItemIds: [] })],
      });
      vi.mocked(fetch).mockImplementation(async (url) => {
        const id = String(url).split('/').pop() ?? '';
        return jsonResponse(200, cogScene(id));
      });

      await useAppStore.getState().openDownloadDialog('L1');

      expect(useAppStore.getState().downloadOriginalLinks?.map((l) => l.groupLabel)).toEqual([
        'Group 1',
        'Group 1',
      ]);
    });

    it('a fetch failure reports a defined error, and an empty link list rather than staying stuck loading', async () => {
      useAppStore.setState({
        datasets: datasetsFrom([COG_DATASET]),
        layers: [layerFixture()],
      });
      vi.mocked(fetch).mockRejectedValue(new TypeError('network error'));

      await useAppStore.getState().openDownloadDialog('L1');

      const s = useAppStore.getState();
      expect(s.error).toMatch(/Could not load the original files/);
      expect(s.downloadOriginalLinks).toEqual([]);
    });

    it('an unknown layer id is a no-op, not a crash', async () => {
      useAppStore.setState({ datasets: datasetsFrom([COG_DATASET]), layers: [] });
      await useAppStore.getState().openDownloadDialog('nope');
      expect(useAppStore.getState().downloadOutcome).toBeNull();
    });
  });
});
