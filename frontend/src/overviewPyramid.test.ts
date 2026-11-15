// Plan M5-30b part 9: below its first level a dataset with `overview: pyramid` (GLO-30, WorldCover) draws its own pyramid on the
// route of the overview, in its own look, under its own attribution for modified data. The picture has no mark; the tooltip of the
// layer says what it is (Otto, 11.11.2026, `adr/0032` §14 F12). Synthetic collections only.

import { describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import { sceneInfo } from './fixtures/viewScenes';
import { zoomMap } from './fixtures/zoomMap';
import { syncFocusRaster, syncLayers } from './mapLayers';
import { noteOfOverview, overviewNoteOf, overviewRasterOf } from './overviewSubstitute';
import { overviewOverlaysOf } from './searchLayers';
import type { Collection, LicenseFlags, StacItem } from './types';

const CAPABILITIES = { roi: true, time_range: false, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, single_coverage_product: false };
const TEXT = '© Provider made up for the test; produced using made-up data';
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
  attribution_modified: TEXT,
  attribution_unmodified: 'unmodified text',
  terms_url: null,
  terms_notice: null,
};

const relief = (over: Partial<NonNullable<Collection['earthx:viewer']>> = {}, flags: Partial<LicenseFlags> = {}): Collection => ({
  id: 'relief',
  title: 'Relief',
  extent: { spatial: { bbox: [[-180, -90, 180, 90]] } },
  'earthx:capabilities': CAPABILITIES,
  'earthx:license_flags': { ...FLAGS, ...flags },
  'earthx:viewer': {
    group_by: ['start_datetime'],
    min_zoom: 7,
    max_zoom: 15,
    browse: 'full_resolution',
    quicklook_nodata_max: null,
    results_group_by: ['start_datetime'],
    overview: 'pyramid',
    overview_resampling: 'average',
    overview_substitute: null,
    ...over,
  },
  'earthx:default_render': { title: 'Elevation', assets: ['data'], rescale: [[0, 5000]], colormap_name: 'terrain', expression: null, resampling: 'nearest' },
});

const LIST = datasetsFrom([relief()]);
const [RELIEF] = LIST;
const ITEM: StacItem = { id: 'r1', collection: 'relief', bbox: [7, 46, 8, 47], properties: { datetime: '2026-01-01T00:00:00Z' }, assets: {} };
const scene512 = (minZoom = 7) => ({ ...sceneInfo(ITEM, minZoom, 15, 'relief'), tileUrl: '/collections/relief/mosaic/s/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=512' });
const view = (over: Record<string, unknown> = {}) => ({
  downloaded: { r1: scene512() },
  render: { rescale: '0,3000', colormapName: 'viridis' },
  showDownloaded: true,
  aoi: null,
  cropToAoi: false,
  items: [ITEM],
  dataset: RELIEF,
  datasets: LIST,
  ...over,
});
const sourcesOf = (live: ReturnType<typeof zoomMap>) => [...live.sources.entries()].filter(([id]) => id.includes('tiles-src'));

describe('the raster below the first level of a dataset with a pyramid', () => {
  it('is the route of the overview of the dataset itself, 512 px, from z0 to the level before its first', () => {
    const raster = overviewRasterOf(RELIEF, LIST)!;
    expect(raster.tileUrl).toMatch(/\/collections\/relief\/overview\/tiles\/WebMercatorQuad\/\{z\}\/\{x\}\/\{y\}\?tilesize=512$/);
    expect(raster).toMatchObject({ minZoom: 0, maxZoom: 6, hideFrom: 6.5 });
  });

  it('names the dataset in the attribution line, with the text of its own licence for modified data', () => {
    expect(overviewRasterOf(RELIEF, LIST)!.attribution).toBe(TEXT);
  });

  it('does not need the list of datasets: the picture is the dataset itself', () => {
    expect(overviewRasterOf(RELIEF, undefined)).not.toBeNull();
    expect(overviewRasterOf(RELIEF, [])).not.toBeNull();
  });

  it('lies where the dataset does, without the poles', () => {
    expect(overviewRasterOf(RELIEF, LIST)!.bounds).toEqual([-180, -85.0511, 180, 85.0511]);
  });

  it('is none where there is no level below the first, and not drawn where the licence asks for an attribution that cannot be written', () => {
    expect(overviewRasterOf(datasetsFrom([relief({ min_zoom: 0 })])[0], LIST)).toBeNull();
    const none = datasetsFrom([relief({}, { attribution_modified: null, attribution_unmodified: null })]);
    expect(overviewRasterOf(none[0], none)).toBeNull();
    const yearly = datasetsFrom([relief({}, { attribution_modified: '© Provider {year}' })]);
    expect(overviewRasterOf(yearly[0], yearly)).toBeNull();
  });

  it('is none for the other ways below the first level: scenes and own files have nothing below it', () => {
    expect(overviewRasterOf(datasetsFrom([relief({ overview: 'scenes', overview_resampling: null, min_zoom: 0 })])[0], LIST)).toBeNull();
    expect(overviewRasterOf(datasetsFrom([relief({ overview: 'own', overview_resampling: null, min_zoom: 0 })])[0], LIST)).toBeNull();
  });
});

describe('the overlays of a layer of a dataset with a pyramid', () => {
  it('carry the look of the layer to the overview route and name no asset', () => {
    const [overlay] = overviewOverlaysOf(['relief'], LIST, { rescale: '0,3000', colormapName: 'viridis' }, null);
    expect(overlay).toMatchObject({ kind: 'raster', minZoom: 0, maxZoom: 6, hideFrom: 6.5, attribution: TEXT });
    const url = (overlay as { tileUrl: string }).tileUrl;
    expect(url).toContain('/overview/tiles/');
    expect(url).toContain('rescale=0%2C3000');
    expect(url).toContain('colormap_name=viridis');
    expect(url).not.toContain('asset=');
  });

  it('are none where the look is an index, which the route of the overview does not compute', () => {
    expect(overviewOverlaysOf(['relief'], LIST, { rescale: '0,3000', index: 'ndvi' }, null)).toEqual([]);
  });
});

describe('the view of a dataset with a pyramid', () => {
  it('draws the pyramid below the first level and the scene from there on', () => {
    const live = zoomMap();
    syncFocusRaster(live.map as never, view());
    live.idle();
    const [[overviewSource], [sceneSource]] = sourcesOf(live);
    const layers = [...live.layers.values()];
    const overview = layers.find((l) => l.source === overviewSource)!.id;
    const scene = layers.find((l) => l.source === sceneSource)!.id;
    expect((live.sources.get(overviewSource)!.tiles as string[])[0]).toContain('/collections/relief/overview/tiles/');
    expect(live.picturesAt(0)).toEqual([overview]);
    expect(live.picturesAt(5)).toEqual([overview]);
    expect(live.picturesAt(6.4)).toEqual([overview]);
    expect(live.picturesAt(6.5)).toEqual([scene]);
    expect(live.picturesAt(12)).toEqual([scene]);
  });

  it('names the dataset in the attribution line below the first level and not above it', () => {
    const live = zoomMap();
    syncFocusRaster(live.map as never, view());
    live.idle();
    expect(live.attributionAt(3)).toEqual([TEXT]);
    expect(live.attributionAt(6.4)).toEqual([TEXT]);
    expect(live.attributionAt(6.5)).toEqual([]);
  });

  it('draws no pyramid where a pinned layer draws the view, nor where the view is off, nor with an index', () => {
    for (const over of [{ tilesInLayer: true }, { showDownloaded: false }, { render: { index: 'ndvi' } }]) {
      const live = zoomMap();
      syncFocusRaster(live.map as never, view(over));
      expect(sourcesOf(live).filter(([, s]) => (s.tiles as string[])[0].includes('/overview/'))).toEqual([]);
    }
  });
});

describe('a pinned layer of a dataset with a pyramid', () => {
  const layer = (visible: boolean) => {
    const [overlay] = overviewOverlaysOf(['relief'], LIST, { rescale: '0,3000' }, null);
    return {
      id: 'a',
      name: 'Relief',
      visible,
      opacity: 0.8,
      overlays: [overlay, { kind: 'raster' as const, tileUrl: 'https://t/own/{z}/{x}/{y}?tilesize=512', bounds: [7, 46, 8, 47] as [number, number, number, number], minZoom: 7, maxZoom: 15 }],
      restore: { datasetId: 'relief' } as never,
    };
  };

  it('draws the pyramid under its own raster, with the attribution only while the layer is on and below the first level', () => {
    const live = zoomMap();
    syncLayers(live.map as never, [layer(true)]);
    expect(live.pinnedOrder()).toEqual(['layer-lyr-a-0', 'layer-lyr-a-1']);
    expect(live.attributionAt(4)).toEqual([TEXT]);
    expect(live.attributionAt(9)).toEqual([]);
    syncLayers(live.map as never, [layer(false)]);
    expect(live.attributionAt(4)).toEqual([]);
  });
});

describe('what the layer says of its pyramid', () => {
  it('is one sentence for the tooltip: where the overview ends and that it is resampled from the original files', () => {
    expect(overviewNoteOf(RELIEF)).toBe('Below zoom 7 the map shows an overview of Relief, resampled from the original files; zoom in to 7 for the originals.');
  });

  it('is nothing for a dataset without a pyramid, one that cannot be viewed, or none', () => {
    expect(overviewNoteOf(datasetsFrom([relief({ overview: 'scenes', overview_resampling: null, min_zoom: 0 })])[0])).toBeNull();
    expect(overviewNoteOf(datasetsFrom([relief({ overview: 'substitute', overview_resampling: null, overview_substitute: 'x' })])[0])).toBeNull();
    expect(overviewNoteOf(datasetsFrom([relief({ min_zoom: 0 })])[0])).toBeNull();
    expect(overviewNoteOf(datasetsFrom([{ ...relief(), 'earthx:viewer': undefined }])[0])).toBeNull();
    expect(overviewNoteOf(null)).toBeNull();
    expect(overviewNoteOf(undefined)).toBeNull();
  });

  it('is the field a layer is made with, and none where there is no note', () => {
    expect(noteOfOverview(RELIEF)).toEqual({ note: overviewNoteOf(RELIEF) });
    expect(noteOfOverview(null)).toEqual({});
  });
});
