// Plan M5-30b §4.8: a layer pinned from the view of a dataset with a substitute draws the picture of the substitute under its own
// rasters, once, in the look of the layer.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { json, selectionServer } from './fixtures/selectionTiler';
import { datasetsFrom } from './datasets';
import { resetSelections } from './mosaicSelection';
import { footprintsKeyOf, mosaicsOfView } from './mosaic';
import { shownViewOf, useAppStore } from './store';
import type { Collection, StacItem } from './types';

const CAPABILITIES = { roi: true, time_range: false, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, single_coverage_product: false };
const FLAGS = {
  spdx_id: null,
  name: 'Made-up licence',
  url: 'https://licence.example/',
  commercial_use: true,
  distribution: true,
  derivatives: true,
  share_alike: false,
  attribution_required: true,
  tier: 'processing' as const,
  attribution_modified: 'Made-up attribution',
  attribution_unmodified: 'Made-up attribution',
  terms_url: null,
  terms_notice: null,
};
const viewer = (extra: Partial<NonNullable<Collection['earthx:viewer']>>) => ({
  group_by: ['earthx:state'],
  min_zoom: 13,
  max_zoom: 20,
  browse: 'full_resolution' as const,
  quicklook_nodata_max: null,
  results_group_by: ['earthx:state'],
  overview: 'substitute' as const,
  overview_resampling: null,
  overview_substitute: 'surface',
  ...extra,
});
const render = { title: 'Elevation', assets: ['dtm'], rescale: [[0, 5000]] as [number, number][], colormap_name: 'terrain', expression: null, resampling: 'nearest' };
const TERRAIN: Collection = {
  id: 'terrain',
  title: 'Terrain',
  extent: { spatial: { bbox: [[5.9, 45.7, 10.5, 47.8]] } },
  'earthx:capabilities': CAPABILITIES,
  'earthx:viewer': viewer({}),
  'earthx:default_render': render,
};
const SURFACE: Collection = {
  id: 'surface',
  title: 'Surface',
  extent: { spatial: { bbox: [[-180, -90, 180, 84]] } },
  'earthx:capabilities': CAPABILITIES,
  'earthx:license_flags': FLAGS,
  'earthx:viewer': viewer({ min_zoom: 0, max_zoom: 15, overview: 'pyramid', overview_resampling: 'average', overview_substitute: null }),
  'earthx:default_render': { ...render, assets: ['data'] },
};

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[7, 46], [8, 46], [8, 47], [7, 46]]] };
const scene = (id: string): StacItem => ({ id, collection: 'terrain', bbox: [7, 46, 8, 47], properties: { 'earthx:state': '2026' }, assets: {} });

function open(items: StacItem[]) {
  useAppStore.setState({
    datasets: datasetsFrom([TERRAIN, SURFACE]),
    selectedDatasetIds: ['terrain'],
    datasetId: 'terrain',
    items,
    groups: [{ key: ['2026'], label: '2026', items }],
    activeGroupIndex: 0,
    expandedGroupIndex: 0,
    selectedIds: [],
    focusMode: false,
    cropToAoi: false,
    downloaded: {},
    appliedRender: {},
    mosaics: {},
    pinLoading: false,
    layers: [],
    viewLayerId: null,
    resultsOnMap: true,
    aoi: AOI,
    error: null,
    notice: null,
  });
}

beforeEach(() => {
  resetSelections();
  const selections = selectionServer({
    tilejson: () => json({ bounds: [7, 46, 8, 47], minzoom: 13, maxzoom: 20, tiles: ['http://tiler.test/tiles'], 'earthx:order': ['A', 'B'] }),
  });
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const selected = await selections.answer(url, init);
      if (selected) return selected;
      if (url.includes('/scene-order')) return json({ order: ['A', 'B'] });
      if (url.includes('/statistics')) return json({ '1': { min: 0, max: 4000, percentile_2: 0, percentile_98: 3000 } });
      throw new Error(`unexpected request: ${url}`);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const rasters = () => useAppStore.getState().layers[0].overlays.flatMap((o) => (o.kind === 'raster' ? [o] : []));

describe('a layer pinned from the view of a dataset with a substitute', () => {
  it('has the substitute under its mosaic, with the look of the layer, and the mosaic from the first level of the dataset', async () => {
    open(['A', 'B'].map(scene));
    await useAppStore.getState().enterFocus(false);
    useAppStore.getState().addCurrentToLayers();
    const [substitute, ...own] = rasters();
    expect(substitute).toMatchObject({ minZoom: 0, maxZoom: 12, hideFrom: 12.5, attribution: 'Made-up attribution' });
    expect(substitute.tileUrl).toContain('/collections/terrain/overview/tiles/');
    expect(substitute.tileUrl).toContain('colormap_name=terrain');
    expect(own.map((o) => o.tileUrl).every((url) => !url.includes('/overview/'))).toBe(true);
    expect(own.at(-1)?.tileUrl).toMatch(/\/mosaic\/[0-9a-f]{32}\/tiles\//);
  });

  it('has exactly one substitute in each layer, never two', async () => {
    const items = [scene('A'), scene('B')];
    open(items);
    useAppStore.setState({ groups: [{ key: ['2026'], label: '2026', items: [items[0]] }, { key: ['2027'], label: '2027', items: [items[1]] }], selectedIds: ['A', 'B'] });
    await useAppStore.getState().enterFocus(false);
    useAppStore.getState().addCurrentToLayers();
    const { layers } = useAppStore.getState();
    expect(layers.length).toBeGreaterThan(0);
    for (const layer of layers) expect(layer.overlays.filter((o) => o.kind === 'raster' && o.tileUrl.includes('/overview/'))).toHaveLength(1);
  });

  it('is cut to the AOI of a cropped view like everything else it draws', async () => {
    open(['A', 'B'].map(scene));
    await useAppStore.getState().enterFocus(true);
    useAppStore.getState().addCurrentToLayers();
    expect(rasters().every((o) => o.tileUrl.startsWith('earthx-clip://'))).toBe(true);
    expect(rasters()[0].tileUrl).toContain('/overview/');
  });

  it('has none for a dataset without a substitute', async () => {
    open(['A', 'B'].map(scene));
    useAppStore.setState({ datasets: datasetsFrom([{ ...TERRAIN, 'earthx:viewer': viewer({ min_zoom: 0, overview: 'own', overview_substitute: null }) }, SURFACE]) });
    await useAppStore.getState().enterFocus(false);
    useAppStore.getState().addCurrentToLayers();
    expect(rasters().some((o) => o.tileUrl.includes('/overview/'))).toBe(false);
  });
});

// M5-56: below its first level the view draws the overview of a footprint selection of its scenes; the store makes it under the key the
// map reads, and a layer pinned from the view draws the same, waiting for it rather than taking the whole area.
describe('the footprint selection of the view', () => {
  const ID = '0123456789abcdef0123456789abcdef';
  let posted: string[][] = [];
  beforeEach(() => {
    posted = [];
    const before = vi.mocked(fetch);
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.endsWith('/overview/footprints')) {
          posted.push(JSON.parse(String(init?.body)).items);
          return json({ id: ID, tiles: `/collections/terrain/overview/${ID}/tiles/WebMercatorQuad/{z}/{x}/{y}` }, 201);
        }
        return before(url, init);
      }),
    );
  });
  const settled = () => new Promise((resolve) => setTimeout(resolve, 0));

  it('is made once for the scenes of the view, under the key the map reads', async () => {
    open(['A', 'B', 'C'].map(scene));
    useAppStore.setState({ selectedIds: ['A', 'C'] });
    await useAppStore.getState().enterFocus(true);
    await settled();
    expect(posted).toEqual([['A', 'C']]);
    const s = useAppStore.getState();
    const view = shownViewOf(s);
    const picked = mosaicsOfView(s.mosaics, view.dataset?.id ?? null, Object.entries(view.downloaded), view.groups);
    expect(picked[footprintsKeyOf('terrain', ['A', 'C'])]).toEqual({ footprints: { id: ID, tiles: expect.stringContaining(`/overview/${ID}/tiles/`) } });
  });

  it('is what a layer pinned from the view draws below the first level', async () => {
    open(['A', 'B'].map(scene));
    useAppStore.setState({ selectedIds: ['A', 'B'] });
    await useAppStore.getState().enterFocus(false);
    useAppStore.getState().addCurrentToLayers();
    for (let i = 0; i < 20 && useAppStore.getState().layers.length === 0; i++) await settled();
    expect(rasters()[0].tileUrl).toContain(`/collections/terrain/overview/${ID}/tiles/`);
  });

  it('leaves the view drawing the whole area where the tiler refuses it, and is not asked again in the view', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.endsWith('/overview/footprints')) {
          posted.push(JSON.parse(String(init?.body)).items);
          return json({ detail: 'refused' }, 400);
        }
        return url.includes('/scene-order') ? json({ order: ['A', 'B'] }) : json({ detail: 'not made up' }, 404);
      }),
    );
    open(['A', 'B'].map(scene));
    useAppStore.setState({ selectedIds: ['A', 'B'] });
    await useAppStore.getState().enterFocus(false);
    await settled();
    expect(useAppStore.getState().mosaics[footprintsKeyOf('terrain', ['A', 'B'])]).toBeNull();
    await useAppStore.getState().loadMosaics();
    expect(posted).toHaveLength(1);
  });
});
