// Plan M5-30b §4.8: a layer pinned from the view of a dataset with a substitute draws the picture of the substitute under its own
// rasters, once, in the look of the layer.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { useAppStore } from './store';
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

function json(body: unknown): Response {
  return { ok: true, status: 200, statusText: '', json: async () => body } as Response;
}

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
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.includes('/mosaic/')) return json({ bounds: [7, 46, 8, 47], minzoom: 13, maxzoom: 20, tiles: ['http://tiler.test/tiles'], 'earthx:order': ['A', 'B'] });
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
    expect(own.at(-1)?.tileUrl).toContain('/mosaic/tiles/');
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
