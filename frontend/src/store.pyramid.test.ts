// Plan M5-30b part 9: a layer pinned from the view of a dataset with a pyramid draws the pyramid under its own rasters, once, and
// carries the one sentence the tooltip of its name says about it. A dataset with a substitute says nothing at all.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { json, selectionServer } from './fixtures/selectionTiler';
import { resetSelections } from './mosaicSelection';
import { overviewNoteOf } from './overviewSubstitute';
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
  min_zoom: 7,
  max_zoom: 15,
  browse: 'full_resolution' as const,
  quicklook_nodata_max: null,
  results_group_by: ['earthx:state'],
  overview: 'pyramid' as const,
  overview_resampling: 'average' as const,
  overview_substitute: null,
  ...extra,
});
const render = { title: 'Elevation', assets: ['data'], rescale: [[0, 5000]] as [number, number][], colormap_name: 'terrain', expression: null, resampling: 'nearest' };
const collection = (id: string, extra: Partial<NonNullable<Collection['earthx:viewer']>>): Collection => ({
  id,
  title: id,
  extent: { spatial: { bbox: [[5.9, 45.7, 10.5, 47.8]] } },
  'earthx:capabilities': CAPABILITIES,
  'earthx:license_flags': FLAGS,
  'earthx:viewer': viewer(extra),
  'earthx:default_render': render,
});
const RELIEF = collection('relief', {});
const TERRAIN = collection('terrain', { min_zoom: 13, max_zoom: 20, overview: 'substitute', overview_resampling: null, overview_substitute: 'relief' });

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[7, 46], [8, 46], [8, 47], [7, 46]]] };
const scene = (collectionId: string, id: string): StacItem => ({ id, collection: collectionId, bbox: [7, 46, 8, 47], properties: { 'earthx:state': '2026' }, assets: {} });

function open(datasetId: string, items: StacItem[]) {
  useAppStore.setState({
    datasets: datasetsFrom([RELIEF, TERRAIN]),
    selectedDatasetIds: [datasetId],
    datasetId,
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
    tilejson: () => json({ bounds: [7, 46, 8, 47], minzoom: 7, maxzoom: 15, tiles: ['http://tiler.test/tiles'], 'earthx:order': ['A', 'B'] }),
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

const pin = async (datasetId: string) => {
  open(datasetId, ['A', 'B'].map((id) => scene(datasetId, id)));
  await useAppStore.getState().enterFocus(false);
  useAppStore.getState().addCurrentToLayers();
  return useAppStore.getState().layers[0];
};

describe('a layer pinned from the view of a dataset with a pyramid', () => {
  it('has the pyramid under its mosaic, with the look of the layer and the attribution of its own licence', async () => {
    const layer = await pin('relief');
    const [overview, ...own] = layer.overlays.flatMap((o) => (o.kind === 'raster' ? [o] : []));
    expect(overview).toMatchObject({ minZoom: 0, maxZoom: 6, hideFrom: 6.5, attribution: 'Made-up attribution' });
    expect(overview.tileUrl).toContain('/collections/relief/overview/tiles/');
    expect(overview.tileUrl).toContain('colormap_name=terrain');
    expect(own.map((o) => o.tileUrl).every((url) => !url.includes('/overview/'))).toBe(true);
  });

  it('carries the sentence of the tooltip as its note, and nothing else about it', async () => {
    const layer = await pin('relief');
    expect(layer.note).toBe(overviewNoteOf(useAppStore.getState().datasets[0]));
    expect(layer.note).toMatch(/^Below zoom 7 the map shows an overview of relief, resampled from the original files/);
  });
});

describe('a layer pinned from the view of a dataset with a substitute', () => {
  it('has no note: the picture of the substitute is shown without a word about it', async () => {
    const layer = await pin('terrain');
    expect(layer.note).toBeUndefined();
    expect(layer.overlays.some((o) => o.kind === 'raster' && o.tileUrl.includes('/collections/terrain/overview/tiles/'))).toBe(true);
  });
});
