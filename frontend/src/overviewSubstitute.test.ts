// Plan M5-30b §4.8 (F7 = 1): below its first level a dataset with `overview: substitute` draws the picture of another dataset
// (swissALTI3D: Copernicus DEM GLO-30) on a route of its own, in its own look, with nothing said about it on the map except the
// attribution line while the picture is drawn.

import { describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import { zoomMap } from './fixtures/zoomMap';
import { syncFocusRaster, syncLayers } from './mapLayers';
import { substituteRasterOf } from './overviewSubstitute';
import { substituteOverlaysOf } from './searchLayers';
import { sceneInfo } from './fixtures/viewScenes';
import type { Collection, LicenseFlags, StacItem } from './types';

const CAPABILITIES = { roi: true, time_range: false, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, single_coverage_product: false };
const SURFACE_TEXT = '© Provider made up for the test; produced using made-up data';
const FLAGS: LicenseFlags = {
  spdx_id: null,
  name: 'Made-up licence',
  url: 'https://licence.example/',
  commercial_use: true,
  distribution: true,
  derivatives: true,
  share_alike: false,
  attribution_required: true,
  tier: 'processing',
  attribution_modified: SURFACE_TEXT,
  attribution_unmodified: 'unmodified text',
  terms_url: null,
  terms_notice: null,
};

const terrain = (over: Partial<NonNullable<Collection['earthx:viewer']>> = {}): Collection => ({
  id: 'terrain',
  title: 'Terrain',
  extent: { spatial: { bbox: [[5.9, 45.7, 10.5, 47.8]] } },
  'earthx:capabilities': CAPABILITIES,
  'earthx:viewer': {
    group_by: ['earthx:state'],
    min_zoom: 13,
    max_zoom: 20,
    browse: 'full_resolution',
    quicklook_nodata_max: null,
    results_group_by: ['earthx:state'],
    overview: 'substitute',
    overview_resampling: null,
    overview_substitute: 'surface',
    ...over,
  },
  'earthx:default_render': { title: 'Elevation', assets: ['dtm'], rescale: [[0, 5000]], colormap_name: 'terrain', expression: null, resampling: 'nearest' },
});
const surface = (flags: Partial<LicenseFlags> = {}): Collection => ({
  id: 'surface',
  title: 'Surface',
  extent: { spatial: { bbox: [[-180, -90, 180, 84]] } },
  'earthx:capabilities': CAPABILITIES,
  'earthx:license_flags': { ...FLAGS, ...flags },
  'earthx:viewer': {
    group_by: ['start_datetime'],
    min_zoom: 0,
    max_zoom: 15,
    browse: 'full_resolution',
    quicklook_nodata_max: null,
    results_group_by: ['start_datetime'],
    overview: 'pyramid',
    overview_resampling: 'average',
    overview_substitute: null,
  },
  'earthx:default_render': { title: 'Elevation', assets: ['data'], rescale: [[0, 5000]], colormap_name: 'terrain', expression: null, resampling: 'nearest' },
});

const LIST = datasetsFrom([terrain(), surface()]);
const [TERRAIN, SURFACE] = LIST;
const PLAIN = datasetsFrom([terrain({ overview: 'own', overview_substitute: null, min_zoom: 0 })])[0];

describe('the raster below the first level', () => {
  it('is the substitute route of the dataset, 512 px, from z0 to the level before its first, stepping aside for the mosaic', () => {
    const raster = substituteRasterOf(TERRAIN, LIST)!;
    expect(raster.tileUrl).toMatch(/\/collections\/terrain\/overview\/tiles\/WebMercatorQuad\/\{z\}\/\{x\}\/\{y\}\?tilesize=512$/);
    expect(raster).toMatchObject({ minZoom: 0, maxZoom: 12 });
    // a 512-px mosaic of level 13 is asked for from map zoom 12.5 (`tileSize.ts`)
    expect(raster.hideFrom).toBe(12.5);
  });

  it('names the substitute in the attribution of the map, with the text of its licence for modified data', () => {
    expect(substituteRasterOf(TERRAIN, LIST)!.attribution).toBe(SURFACE_TEXT);
  });

  it('lies where the dataset does, not over the world, so that a map fitted to the layer stays on it', () => {
    expect(substituteRasterOf(TERRAIN, LIST)!.bounds).toEqual([5.9, 45.7, 10.5, 47.8]);
  });

  it('is none for a dataset without a substitute, or one that is not viewable, or none at all', () => {
    expect(substituteRasterOf(PLAIN, LIST)).toBeNull();
    expect(substituteRasterOf(SURFACE, LIST)).toBeNull();
    expect(substituteRasterOf(null, LIST)).toBeNull();
    expect(substituteRasterOf(undefined, LIST)).toBeNull();
    const unviewable = datasetsFrom([{ ...terrain(), 'earthx:viewer': undefined }])[0];
    expect(substituteRasterOf(unviewable, LIST)).toBeNull();
  });

  it('is none where there is no level below the first, or the substitute is not in the list', () => {
    expect(substituteRasterOf(datasetsFrom([terrain({ min_zoom: 0 })])[0], LIST)).toBeNull();
    expect(substituteRasterOf(TERRAIN, [TERRAIN])).toBeNull();
    expect(substituteRasterOf(TERRAIN, undefined)).toBeNull();
  });

  it('is not drawn where the licence asks for an attribution that cannot be written', () => {
    const list = datasetsFrom([terrain(), surface({ attribution_modified: null, attribution_unmodified: null })]);
    expect(substituteRasterOf(list[0], list)).toBeNull();
    const yearly = datasetsFrom([terrain(), surface({ attribution_modified: '© Provider {year}' })]);
    expect(substituteRasterOf(yearly[0], yearly)).toBeNull();
  });

  it('is drawn without a text where the licence asks for none', () => {
    const list = datasetsFrom([terrain(), surface({ attribution_required: false, attribution_modified: null, attribution_unmodified: null })]);
    expect(substituteRasterOf(list[0], list)).not.toBeNull();
    expect(substituteRasterOf(list[0], list)).not.toHaveProperty('attribution');
  });

  it('does not take a bounding box with the poles: a Web Mercator source would not load', () => {
    const poles = datasetsFrom([{ ...terrain(), extent: { spatial: { bbox: [[-180, -90, 180, 90]] } } }, surface()]);
    expect(substituteRasterOf(poles[0], poles)!.bounds).toEqual([-180, -85.0511, 180, 85.0511]);
    const nobox = datasetsFrom([{ ...terrain(), extent: undefined }, surface()]);
    expect(substituteRasterOf(nobox[0], nobox)).toBeNull();
  });
});

describe('the overlays of a layer', () => {
  const look = { rescale: '0,3000', colormapName: 'viridis' };

  it('carry the look of the layer to the substitute: its range and its colormap', () => {
    const [overlay] = substituteOverlaysOf(['terrain'], LIST, look, null);
    expect(overlay).toMatchObject({ kind: 'raster', minZoom: 0, maxZoom: 12, hideFrom: 12.5, attribution: SURFACE_TEXT });
    const url = (overlay as { tileUrl: string }).tileUrl;
    expect(url).toContain('rescale=0%2C3000');
    expect(url).toContain('colormap_name=viridis');
    expect(url).toContain('/overview/tiles/');
    expect(url).not.toContain('asset=');
  });

  it('are one for a dataset however many passes it has, and none for a dataset without a substitute', () => {
    const list = [...LIST, ...datasetsFrom([{ ...terrain({ overview: 'own', overview_substitute: null, min_zoom: 0 }), id: 'plain' }])];
    expect(substituteOverlaysOf(['terrain', 'terrain', 'plain'], list, look, null)).toHaveLength(1);
    expect(substituteOverlaysOf(['plain'], list, look, null)).toEqual([]);
    expect(substituteOverlaysOf([], list, look, null)).toEqual([]);
  });

  it('have none where the look is an index, which only a route with steps computes', () => {
    expect(substituteOverlaysOf(['terrain'], LIST, { ...look, index: 'ndvi' }, null)).toEqual([]);
  });
});

const ITEM: StacItem = { id: 't1', collection: 'terrain', bbox: [7, 46, 8, 47], properties: { datetime: '2026-01-01T00:00:00Z' }, assets: {} };
// The scene as a 512-px tile, as the mosaic of a pass is drawn (`mosaic.ts`): asked for from map zoom 12.5.
const scene512 = (datasetId: string, minZoom = 13) => ({ ...sceneInfo(ITEM, minZoom, 20, datasetId), tileUrl: '/collections/c/mosaic/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=512' });
const view = (dataset: typeof TERRAIN, over: Record<string, unknown> = {}) => ({
  downloaded: { t1: scene512(dataset.id) },
  render: { rescale: '0,3000', colormapName: 'viridis' },
  showDownloaded: true,
  aoi: null,
  cropToAoi: false,
  items: [ITEM],
  dataset,
  datasets: LIST,
  ...over,
});
const sourcesOf = (live: ReturnType<typeof zoomMap>) => [...live.sources.entries()].filter(([id]) => id.includes('tiles-src'));

describe('the view of a dataset with a substitute', () => {
  it('draws a second source on the route of the substitute, below its own scene and in its look', () => {
    const live = zoomMap();
    syncFocusRaster(live.map as never, view(TERRAIN));
    const [first, second] = sourcesOf(live);
    expect(first[1]).toMatchObject({ type: 'raster', tileSize: 512, minzoom: 0, maxzoom: 12, attribution: SURFACE_TEXT });
    const url = (first[1].tiles as string[])[0];
    expect(url).toContain('/collections/terrain/overview/tiles/WebMercatorQuad/');
    expect(url).toContain('colormap_name=viridis');
    expect(url).toContain('rescale=0%2C3000');
    expect(second[1]).toMatchObject({ minzoom: 13 });
    expect(second[1]).not.toHaveProperty('attribution');
    const layerOf = (srcId: string) => [...live.layers.values()].find((l) => l.source === srcId)!;
    expect(layerOf(first[0]).maxzoom).toBe(12.5);
    expect(live.stack.indexOf(layerOf(first[0]).id)).toBeLessThan(live.stack.indexOf(layerOf(second[0]).id));
  });

  it('draws only the scene for a dataset without a substitute', () => {
    const live = zoomMap();
    syncFocusRaster(live.map as never, view(PLAIN, { downloaded: { t1: sceneInfo(ITEM, 0, 20, PLAIN.id) }, datasets: [PLAIN] }));
    expect(sourcesOf(live)).toHaveLength(1);
    expect(sourcesOf(live)[0][1]).not.toHaveProperty('attribution');
  });

  it('draws no substitute where a pinned layer draws the view, nor where the view is off, nor with an index', () => {
    for (const over of [{ tilesInLayer: true }, { showDownloaded: false }, { render: { index: 'ndvi' } }]) {
      const live = zoomMap();
      syncFocusRaster(live.map as never, view(TERRAIN, over));
      expect(sourcesOf(live).filter(([, s]) => (s.tiles as string[])[0].includes('/overview/'))).toEqual([]);
    }
  });

  it('shows the picture of the substitute below the first level and the scene from there on, with no gap and no overlap of the two sources', () => {
    const live = zoomMap();
    syncFocusRaster(live.map as never, view(TERRAIN));
    const [[ownSub], [ownScene]] = sourcesOf(live);
    const layers = [...live.layers.values()];
    const sub = layers.find((l) => l.source === ownSub)!.id;
    const scene = layers.find((l) => l.source === ownScene)!.id;
    expect(live.picturesAt(10)).toEqual([sub]);
    expect(live.picturesAt(12.4)).toEqual([sub]);
    expect(live.picturesAt(12.5)).toEqual([scene]);
    expect(live.picturesAt(16)).toEqual([scene]);
  });

  it('names the substitute in the attribution line below the first level and not above it', () => {
    const live = zoomMap();
    syncFocusRaster(live.map as never, view(TERRAIN));
    expect(live.attributionAt(6)).toEqual([SURFACE_TEXT]);
    expect(live.attributionAt(12.4)).toEqual([SURFACE_TEXT]);
    expect(live.attributionAt(12.5)).toEqual([]);
    expect(live.attributionAt(15)).toEqual([]);
  });
});

describe('a pinned layer with a substitute', () => {
  const layer = (visible: boolean) => {
    const [overlay] = substituteOverlaysOf(['terrain'], LIST, { rescale: '0,3000' }, null);
    return {
      id: 'a',
      name: 'Terrain',
      visible,
      opacity: 0.8,
      overlays: [overlay, { kind: 'raster' as const, tileUrl: 'https://t/own/{z}/{x}/{y}?tilesize=512', bounds: [7, 46, 8, 47] as [number, number, number, number], minZoom: 13, maxZoom: 20 }],
      restore: { datasetId: 'terrain' } as never,
    };
  };

  it('draws the substitute under its own raster, with the attribution only while the layer is on and below the first level', () => {
    const live = zoomMap();
    syncLayers(live.map as never, [layer(true)]);
    expect(live.pinnedOrder()).toEqual(['layer-lyr-a-0', 'layer-lyr-a-1']);
    expect(live.attributionAt(8)).toEqual([SURFACE_TEXT]);
    expect(live.attributionAt(14)).toEqual([]);
    syncLayers(live.map as never, [layer(false)]);
    expect(live.visible('layer-lyr-a-0')).toBe(false);
    expect(live.attributionAt(8)).toEqual([]);
    syncLayers(live.map as never, [layer(true)]);
    expect(live.attributionAt(8)).toEqual([SURFACE_TEXT]);
  });

  it('is hidden with the layer, the substitute and the scene both', () => {
    const live = zoomMap();
    syncLayers(live.map as never, [layer(false)]);
    expect(live.visible('layer-lyr-a-0')).toBe(false);
    expect(live.visible('layer-lyr-a-1')).toBe(false);
    expect(live.picturesAt(8)).toEqual([]);
  });
});
