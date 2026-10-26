import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import {
  buildTileUrl,
  ensureBaseLayers,
  setCoverageDisplay,
  syncFocusRaster,
  syncHighlight,
  syncLayers,
  syncMosaic,
  syncPreview,
  syncSelectionHighlight,
} from './mapLayers';
import type { LayerOverlay, MapLayer } from './layers';
import { buildMosaicTileTemplate } from './api';
import { mosaicTemplateOf } from './mosaic';
import type { Mosaics, SceneEntry } from './mosaic';
import { liveMap, lyr, pinned } from './fixtures/liveMap';
import type { AppliedRender, DownloadedInfo, StacItem, TimeStepGroup } from './types';

function info(overrides: Partial<DownloadedInfo> = {}): DownloadedInfo {
  return {
    tileUrl: '/collections/sentinel-2-c1-l2a/items/S2A_1/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual',
    bounds: [10, 47, 11, 48],
    asset: 'visual',
    minZoom: 0,
    maxZoom: 19,
    ...overrides,
  };
}

describe('buildTileUrl', () => {
  it('returns the template unchanged when nothing has been applied yet', () => {
    expect(buildTileUrl(info().tileUrl, {})).toBe(info().tileUrl);
  });

  it('adds the stretch and colormap_name (not colormap) the tiler expects', () => {
    const render: AppliedRender = { rescale: '0,3000', colormapName: 'viridis' };
    const params = new URL(buildTileUrl(info().tileUrl, render), 'http://localhost').searchParams;
    expect(params.get('rescale')).toBe('0,3000');
    expect(params.get('colormap_name')).toBe('viridis');
    expect(params.has('colormap')).toBe(false);
  });

  it('adds bidx and expression when set', () => {
    const render: AppliedRender = { bidx: '1,2,3', expression: 'b1*2' };
    const params = new URL(buildTileUrl(info().tileUrl, render), 'http://localhost').searchParams;
    expect(params.get('bidx')).toBe('1,2,3');
    expect(params.get('expression')).toBe('b1*2');
  });

  it('keeps the asset that is already baked into the template rather than adding a second one', () => {
    const url = buildTileUrl(info().tileUrl, { rescale: '0,255' });
    const params = new URL(url, 'http://localhost').searchParams.getAll('asset');
    expect(params).toEqual(['visual']);
  });
});

// --- the browse preview (M2-10) ---
//
// A fake map rather than a real MapLibre instance: everything these cases are
// about happens before WebGL — which source is added, with which tile URL and
// which zoom bounds. `syncMosaic` only touches the handful of methods below on
// the tiles path (the image path is the one that needs a canvas, and that is
// what `quicklookPlan` decides against for these datasets).
interface AddedSource {
  id: string;
  spec: Record<string, unknown>;
}

function fakeMap() {
  const sources: AddedSource[] = [];
  const layers: string[] = [];
  const layerSpecs: { id: string; source?: string; maxzoom?: number }[] = [];
  const removedSources: string[] = [];
  const removedLayers: string[] = [];
  // Data written via `source.setData(...)` on one of the fixed (non-dynamic)
  // sources, keyed by source id — this is how `setCoverageDisplay` and the
  // selection highlight (`SEL_SRC` = 'mosaicsel-src') publish their GeoJSON.
  const data: Record<string, GeoJSON.GeoJSON> = {};
  const map = {
    getSource: (id: string) =>
      id.startsWith('m-') ? undefined : { setData: (d: GeoJSON.GeoJSON) => (data[id] = d) },
    getLayer: () => undefined,
    removeLayer: (id: string) => removedLayers.push(id),
    removeSource: (id: string) => removedSources.push(id),
    addSource: (id: string, spec: Record<string, unknown>) => sources.push({ id, spec }),
    addLayer: (layer: { id: string; source?: string; maxzoom?: number }) => {
      layers.push(layer.id);
      layerSpecs.push(layer);
    },
  };
  return { map, sources, layers, layerSpecs, data, removedSources, removedLayers };
}

const CAPABILITIES = {
  roi: true,
  time_range: true,
  band_math: true,
  interpolation: true,
  ml_processing: true,
  quad_pol: false,
  single_coverage_product: false,
};

function zarrLikeDataset() {
  const [dataset] = datasetsFrom([
    {
      id: 'synthetic-zarr',
      title: 'Synthetic Zarr dataset',
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
        rescale: [[0, 0.3]] as [number, number][],
        colormap_name: null,
        expression: null,
        resampling: 'nearest',
      },
    },
  ]);
  return dataset;
}

const scene: StacItem = {
  id: 'S2B_1',
  bbox: [10, 47, 11, 48],
  properties: { datetime: '2026-07-24T10:00:00Z' },
  assets: { SR_10m: { href: 'https://data.test/x.zarr/r10m', roles: ['data'] } },
};

function browse(items: StacItem[], dataset: ReturnType<typeof zarrLikeDataset>) {
  const { map, sources } = fakeMap();
  syncMosaic(map as never, {
    items,
    dataset,
    downloaded: {},
    selectedIds: [],
    render: {},
    focusMode: false,
    showDownloaded: true,
  });
  return sources.filter((s) => s.spec.type === 'raster');
}

describe('syncMosaic: the browse preview where a source publishes no quicklook', () => {
  it('reads only the coarsest released level and overzooms above it', () => {
    const [source] = browse([scene], zarrLikeDataset());
    expect(source.spec.minzoom).toBe(8);
    expect(source.spec.maxzoom).toBe(8);
  });

  it('carries the registry stretch, or the preview would not match the focus view', () => {
    const [source] = browse([scene], zarrLikeDataset());
    const url = new URL((source.spec.tiles as string[])[0], 'http://localhost');
    expect(url.searchParams.get('asset')).toBe('SR_10m:b04,b03,b02');
    expect(url.searchParams.get('rescale')).toBe('0,0.3');
  });

  it('bounds the source by the scene, not the world', () => {
    const [source] = browse([scene], zarrLikeDataset());
    expect(source.spec.bounds).toEqual([10, 47, 11, 48]);
  });

  it('skips a scene without a bounding box rather than placing it wrongly', () => {
    expect(browse([{ ...scene, bbox: null }], zarrLikeDataset())).toHaveLength(0);
  });

  it('places nothing when no dataset is selected', () => {
    const { map, sources } = fakeMap();
    syncMosaic(map as never, {
      items: [scene],
      dataset: null,
      downloaded: {},
      selectedIds: [],
      render: {},
      focusMode: false,
      showDownloaded: true,
    });
    expect(sources.filter((s) => s.spec.type === 'raster')).toHaveLength(0);
  });
});

// V-3, finding 1: a click on a full-resolution image toggles its selection
// (MapView.tsx's map click handler already did this), but `syncMosaic` used
// to overwrite the selection source with an empty FeatureCollection
// unconditionally in focus mode — so nothing was ever drawn, and the only
// visible effect was the raster layers being torn down and rebuilt (which
// read as "the image reloads"). It must draw the same yellow outline browse
// mode draws for a selected item, from the same `selectedIds`.
describe('syncMosaic: the full-resolution selection highlight (focus mode)', () => {
  const SEL_SRC = 'mosaicsel-src';

  function focusView(selectedIds: string[]) {
    const { map, sources, data } = fakeMap();
    syncMosaic(map as never, {
      items: [scene],
      dataset: zarrLikeDataset(),
      downloaded: { [scene.id]: info() },
      selectedIds,
      render: {},
      focusMode: true,
      showDownloaded: true,
    });
    return { sources, selection: data[SEL_SRC] as GeoJSON.FeatureCollection };
  }

  it('outlines a selected full-resolution image, not an empty collection', () => {
    const { selection } = focusView([scene.id]);
    expect(selection.features).toHaveLength(1);
    expect(selection.features[0].properties?.id).toBe(scene.id);
  });

  it('carries no outline while nothing is selected', () => {
    const { selection } = focusView([]);
    expect(selection.features).toHaveLength(0);
  });

  it('keeps rendering the full-resolution raster regardless of the selection outline', () => {
    const { sources, selection } = focusView([scene.id]);
    expect(sources.filter((s) => s.spec.type === 'raster')).toHaveLength(1);
    expect(selection.features).toHaveLength(1);
  });
});

describe('syncFocusRaster', () => {
  it('renders one raster layer per downloaded scene, with the applied render in the tile URL', () => {
    const { map, sources } = fakeMap();
    syncFocusRaster(map as never, {
      downloaded: { [scene.id]: info() },
      render: { rescale: '0,3000' },
      showDownloaded: true,
      items: [scene],
      dataset: null,
    });
    const [source] = sources.filter((s) => s.spec.type === 'raster');
    expect(source.spec.bounds).toEqual(info().bounds);
    const url = new URL((source.spec.tiles as string[])[0], 'http://localhost');
    expect(url.searchParams.get('rescale')).toBe('0,3000');
  });

  it('renders nothing while the image is hidden', () => {
    const { map, sources } = fakeMap();
    syncFocusRaster(map as never, {
      downloaded: { [scene.id]: info() },
      render: {},
      showDownloaded: false,
      items: [scene],
      dataset: null,
    });
    expect(sources).toHaveLength(0);
  });

  // M3-09 finding: the map used to stack overlapping scenes in *selection*
  // order (last-selected on top), the opposite of the download's mosaic
  // (`access/download.py::crop_asset`, rio_tiler's `FirstMethod`: the
  // *first* item wins). `downloaded`'s key order is selection order (it is
  // built by `store.ts::enterFocus` iterating the selected items in that
  // order), so the fixture below relies on the same thing.
  it('draws the first-selected scene last, so it ends up on top — matching the download mosaic order', () => {
    const { map, sources, layers } = fakeMap();
    syncFocusRaster(map as never, {
      downloaded: {
        S2A_first: info({ bounds: [10, 47, 11, 48] }),
        S2A_second: info({ bounds: [20, 47, 21, 48] }),
      },
      render: {},
      showDownloaded: true,
      items: [],
      dataset: null,
    });
    const rasterSources = sources.filter((s) => s.spec.type === 'raster');
    expect(rasterSources).toHaveLength(2);
    expect(rasterSources[0].spec.bounds).toEqual([20, 47, 21, 48]); // bottom: second-selected
    expect(rasterSources[1].spec.bounds).toEqual([10, 47, 11, 48]); // top: first-selected
    // `placeRaster` always inserts right below the AOI layer, so whatever is
    // added last ends up drawn on top (see `beforeAoi`).
    expect(layers[layers.length - 1]).toBe(rasterSources[1].id.replace('src', 'lyr'));
  });

  it('routes tiles through the AOI-clip protocol when the view is cropped, with no AOI coordinate in the URL', () => {
    const { map, sources } = fakeMap();
    syncFocusRaster(map as never, {
      downloaded: { [scene.id]: info() },
      render: {},
      showDownloaded: true,
      aoi: {
        type: 'Polygon',
        coordinates: [[[10.987654, 47.123456], [11, 47], [11, 48], [10, 48], [10.987654, 47.123456]]],
      },
      cropToAoi: true,
      items: [scene],
      dataset: null,
    });
    const [source] = sources.filter((s) => s.spec.type === 'raster');
    const url = (source.spec.tiles as string[])[0];
    expect(url.startsWith('earthx-clip://')).toBe(true);
    expect(url).not.toContain('10.987654');
    expect(url).not.toContain('47.123456');
  });

  it('does not clip when the view shows the whole selection, even with an AOI drawn', () => {
    const { map, sources } = fakeMap();
    syncFocusRaster(map as never, {
      downloaded: { [scene.id]: info() },
      render: {},
      showDownloaded: true,
      aoi: { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 48], [10, 47]]] },
      cropToAoi: false,
      items: [scene],
      dataset: null,
    });
    const [source] = sources.filter((s) => s.spec.type === 'raster');
    expect((source.spec.tiles as string[])[0].startsWith('earthx-clip://')).toBe(false);
  });
});

// M4-17c: a time step of several scenes is one surface from z8 up, and the single scenes under it
// below that, stacked the way the mosaic reads them.
describe('syncFocusRaster with mosaics', () => {
  const DATASET = 'sentinel-2-c1-l2a';
  const group = (ids: string[]): TimeStepGroup => ({
    key: [ids[0]],
    label: ids[0],
    items: ids.map((id) => ({ id, properties: {}, assets: {} })),
  });
  const sceneInfo = (id: string, bounds: DownloadedInfo['bounds'] = [10, 47, 11, 48]) =>
    info({ tileUrl: `/collections/${DATASET}/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`, bounds });
  const downloadedOf = (...ids: string[]) => Object.fromEntries(ids.map((id) => [id, sceneInfo(id)]));
  const dataset = () => {
    const [d] = datasetsFrom([
      {
        id: DATASET,
        title: 'Sentinel-2 L2A',
        'earthx:capabilities': CAPABILITIES,
        'earthx:viewer': {
          group_by: ['datetime'],
          min_zoom: 0,
          max_zoom: 19,
          browse: 'preview_tiles',
          quicklook_nodata_max: null,
          results_group_by: ['datetime'],
        },
        'earthx:default_render': {
          title: 'True colour',
          assets: ['visual'],
          rescale: null,
          colormap_name: null,
          expression: null,
          resampling: 'nearest',
        },
      },
    ]);
    return d;
  };
  const entriesOf = (downloaded: Record<string, DownloadedInfo>) => Object.entries(downloaded) as SceneEntry[];
  const loaded = (downloaded: Record<string, DownloadedInfo>, order: string[]): Mosaics => {
    const tileUrl = mosaicTemplateOf(DATASET, entriesOf(downloaded)) as string;
    return { [tileUrl]: { tileUrl, bounds: [9, 46, 12, 49], minZoom: 8, maxZoom: 19, order } };
  };
  const draw = (state: Partial<Parameters<typeof syncFocusRaster>[1]>) => {
    const fake = fakeMap();
    syncFocusRaster(fake.map as never, {
      render: {},
      showDownloaded: true,
      items: [],
      dataset: dataset(),
      downloaded: {},
      ...state,
    });
    return { ...fake, rasters: fake.sources.filter((s) => s.spec.type === 'raster') };
  };
  const tileUrlOf = (source: AddedSource) => (source.spec.tiles as string[])[0];

  it('draws a time step as one surface above z8, under the single scenes that step aside from there', () => {
    const downloaded = downloadedOf('A', 'B', 'C');
    const { rasters, layerSpecs } = draw({
      downloaded,
      groups: [group(['A', 'B', 'C'])],
      mosaics: loaded(downloaded, ['B', 'C', 'A']),
    });
    expect(rasters).toHaveLength(4);
    const mosaic = rasters[3];
    expect(tileUrlOf(mosaic)).toBe(buildMosaicTileTemplate(DATASET, ['A', 'B', 'C'], 'visual'));
    expect([mosaic.spec.bounds, mosaic.spec.minzoom, mosaic.spec.maxzoom]).toEqual([[9, 46, 12, 49], 8, 19]);
    expect(layerSpecs.find((l) => l.source === mosaic.id)?.maxzoom).toBeUndefined();
    // bottom to top: the scene the mosaic reads last first, the one it reads first under the mosaic
    expect(rasters.slice(0, 3).map((r) => tileUrlOf(r).split('/items/')[1].split('/')[0])).toEqual(['A', 'C', 'B']);
    for (const single of rasters.slice(0, 3)) {
      expect(single.spec.maxzoom).toBe(7);
      expect(layerSpecs.find((l) => l.source === single.id)?.maxzoom).toBe(6.5);
    }
  });

  it('draws nothing for a time step while its mosaic is on its way, instead of every scene', () => {
    const downloaded = downloadedOf('A', 'B');
    expect(draw({ downloaded, groups: [group(['A', 'B'])], mosaics: {} }).sources).toHaveLength(0);
  });

  it('draws the scenes one by one once the tiler has refused the mosaic', () => {
    const downloaded = downloadedOf('A', 'B');
    const refused = { [mosaicTemplateOf(DATASET, entriesOf(downloaded)) as string]: null };
    expect(draw({ downloaded, groups: [group(['A', 'B'])], mosaics: refused }).rasters).toHaveLength(2);
  });

  it('draws the scenes one by one without mosaics, as before', () => {
    const downloaded = downloadedOf('A', 'B');
    expect(draw({ downloaded, groups: [group(['A', 'B'])] }).rasters).toHaveLength(2);
  });

  it('draws one mosaic per time step, and a scene of no known time step by itself', () => {
    const downloaded = downloadedOf('A1', 'A2', 'B1', 'B2', 'X');
    const groups = [group(['A1', 'A2']), group(['B1', 'B2'])];
    const mosaics = {
      ...loaded(downloadedOf('A1', 'A2'), ['A1', 'A2']),
      ...loaded(downloadedOf('B1', 'B2'), ['B2', 'B1']),
    };
    const { rasters } = draw({ downloaded, groups, mosaics });
    const urls = rasters.map(tileUrlOf);
    expect(urls.filter((u) => u.includes('/mosaic/'))).toHaveLength(2);
    expect(urls.filter((u) => u.includes('/items/X/'))).toHaveLength(1);
    expect(rasters).toHaveLength(2 * 3 + 1);
  });

  it('leaves the scenes below the mosaic out for a dataset released from the mosaic level on', () => {
    const zarr = Object.fromEntries(['A', 'B'].map((id) => [id, { ...sceneInfo(id), minZoom: 8, maxZoom: 14 }]));
    const tileUrl = mosaicTemplateOf(DATASET, entriesOf(zarr)) as string;
    const mosaics = { [tileUrl]: { tileUrl, bounds: [9, 46, 12, 49] as [number, number, number, number], minZoom: 8, maxZoom: 14, order: ['A', 'B'] } };
    expect(draw({ downloaded: zarr, groups: [group(['A', 'B'])], mosaics }).rasters).toHaveLength(1);
  });

  it('wraps the mosaic URL in the AOI clip like any other, with no coordinate in it', () => {
    const downloaded = downloadedOf('A', 'B');
    const { rasters } = draw({
      downloaded,
      groups: [group(['A', 'B'])],
      mosaics: loaded(downloaded, ['A', 'B']),
      aoi: { type: 'Polygon', coordinates: [[[10.987654, 47.123456], [11, 47], [11, 48], [10, 48], [10.987654, 47.123456]]] },
      cropToAoi: true,
      render: { rescale: '0,3000' },
    });
    const mosaic = tileUrlOf(rasters[rasters.length - 1]);
    expect(mosaic.startsWith('earthx-clip://')).toBe(true);
    expect(mosaic).toContain('/mosaic/tiles/');
    expect(mosaic).toContain('rescale=0%2C3000');
    expect(mosaic).not.toContain('10.987654');
    expect(mosaic).not.toContain('47.123456');
  });

  it('draws no tiles when a pinned layer draws them, as before', () => {
    const downloaded = downloadedOf('A', 'B');
    const { sources } = draw({ downloaded, groups: [group(['A', 'B'])], mosaics: loaded(downloaded, ['A', 'B']), tilesInLayer: true });
    expect(sources).toHaveLength(0);
  });

  it('draws a time step too big for a mosaic scene by scene, the first 40', () => {
    const ids = Array.from({ length: 70 }, (_, i) => `S${String(i).padStart(2, '0')}`);
    const downloaded = downloadedOf(...ids);
    const { rasters } = draw({ downloaded, groups: [group(ids)], mosaics: {} });
    expect(rasters).toHaveLength(40);
    expect(rasters.map(tileUrlOf).some((u) => u.includes('/items/S00/'))).toBe(true);
    expect(rasters.map(tileUrlOf).some((u) => u.includes('/items/S40/'))).toBe(false);
  });

  it('keeps every mosaic and leaves no layer behind when the ids run short', () => {
    const passIds = (p: number) => Array.from({ length: 64 }, (_, i) => `P${p}S${String(i).padStart(2, '0')}`);
    const all = [0, 1, 2, 3].map(passIds);
    const downloaded = downloadedOf(...all.flat(), 'X');
    const mosaics = all.reduce<Mosaics>((acc, ids) => ({ ...acc, ...loaded(downloadedOf(...ids), ids) }), {});
    const fake = fakeMap();
    const state = { downloaded, groups: all.map(group), mosaics, render: {}, showDownloaded: true, items: [], dataset: dataset() };
    syncFocusRaster(fake.map as never, state);
    const urls = fake.sources.filter((src) => src.spec.type === 'raster').map(tileUrlOf);
    expect(urls.filter((u) => u.includes('/mosaic/'))).toHaveLength(4);
    expect(urls).toHaveLength(5); // the single scenes under the mosaics were given up, X is one of its own
    // every id it handed out is one the next sync clears (`clearDynamicMosaic` goes up to 199)
    expect(fake.layers.every((id) => Number(id.split('-').pop()) < 200)).toBe(true);
  });

  it('takes a time step of 64 scenes whole, with every scene under it', () => {
    const ids = Array.from({ length: 64 }, (_, i) => `S${String(i).padStart(2, '0')}`);
    const downloaded = downloadedOf(...ids);
    const { rasters } = draw({ downloaded, groups: [group(ids)], mosaics: loaded(downloaded, ids) });
    expect(rasters).toHaveLength(65);
  });
});

// V-3, finding 1's actual root cause: before this, MapView had one effect
// covering both the raster tiles *and* the selection outline, keyed (among
// other things) on `selectedIds` — so a click that only (de)selected a
// full-resolution image still went through the whole reconcile, tearing the
// raster layers down and rebuilding them. `syncSelectionHighlight` is the
// only thing a selection toggle should ever have to run; it must never touch
// a source or layer that `syncFocusRaster`/`syncBrowseMosaic` own.
describe('syncSelectionHighlight: no layer churn', () => {
  it('never adds or removes a raster/quicklook source or layer', () => {
    const { map, sources, layers, data } = fakeMap();
    syncFocusRaster(map as never, {
      downloaded: { [scene.id]: info() },
      render: {},
      showDownloaded: true,
      items: [scene],
      dataset: null,
    });
    const sourcesAfterRaster = sources.length;
    const layersAfterRaster = layers.length;
    expect(sourcesAfterRaster).toBeGreaterThan(0);

    syncSelectionHighlight(map as never, [scene], [scene.id]);

    expect(sources).toHaveLength(sourcesAfterRaster);
    expect(layers).toHaveLength(layersAfterRaster);
    expect((data['mosaicsel-src'] as GeoJSON.FeatureCollection).features).toHaveLength(1);
  });
});

// M3-09 §10: in a cropped focus view, the yellow outline switches from one
// ring per scene to one per group.
describe('syncHighlight', () => {
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
  const groupA: TimeStepGroup = {
    key: ['a'],
    label: 'a',
    items: [
      { id: 'S1', bbox: [1, 47, 2, 48], properties: {}, assets: {} },
      { id: 'S2', bbox: [1.5, 47, 2.5, 48], properties: {}, assets: {} },
    ],
  };
  const groupB: TimeStepGroup = {
    key: ['b'],
    label: 'b',
    items: [{ id: 'S3', bbox: [10, 47, 11, 48], properties: {}, assets: {} }],
  };

  it('draws one ring per group when the view is cropped', () => {
    const { map, data } = fakeMap();
    syncHighlight(map as never, {
      items: [],
      selectedIds: [],
      focusMode: true,
      cropToAoi: true,
      aoi: AOI,
      downloaded: { S1: info(), S2: info(), S3: info() },
      groups: [groupA, groupB],
    });
    const fc = data['mosaicsel-src'] as GeoJSON.FeatureCollection;
    expect(fc.features).toHaveLength(2);
  });

  it('falls back to the per-scene highlight when the view is not cropped', () => {
    const { map, data } = fakeMap();
    syncHighlight(map as never, {
      items: [groupA.items[0]],
      selectedIds: ['S1'],
      focusMode: true,
      cropToAoi: false,
      aoi: AOI,
      downloaded: { S1: info() },
      groups: [groupA, groupB],
    });
    const fc = data['mosaicsel-src'] as GeoJSON.FeatureCollection;
    expect(fc.features).toHaveLength(1);
    expect(fc.features[0].properties?.id).toBe('S1');
  });

  it('falls back to the per-scene highlight while browsing (not in focus mode)', () => {
    const { map, data } = fakeMap();
    syncHighlight(map as never, {
      items: [groupA.items[0]],
      selectedIds: ['S1'],
      focusMode: false,
      cropToAoi: false,
      aoi: null,
      downloaded: {},
      groups: [groupA, groupB],
    });
    const fc = data['mosaicsel-src'] as GeoJSON.FeatureCollection;
    expect(fc.features).toHaveLength(1);
  });
});

// M3-12, F-07: a one-off product's coverage answer draws its extent, not a
// density (ENTSCHEIDUNGEN §2) — only one of the three coverage sources ever
// carries data at once.
describe('setCoverageDisplay: area mode', () => {
  const AREA: GeoJSON.Polygon = {
    type: 'Polygon',
    coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
  };

  it('publishes the area geometry on its own source', () => {
    const { map, data } = fakeMap();
    setCoverageDisplay(map as never, { mode: 'area', cells: [], maxCount: 0, footprints: null, area: AREA });
    const fc = data['coverage-area-src'] as GeoJSON.FeatureCollection;
    expect(fc.features).toHaveLength(1);
    expect(fc.features[0].geometry).toEqual(AREA);
  });

  it('clears the area source in every other mode', () => {
    const { map, data } = fakeMap();
    setCoverageDisplay(map as never, { mode: 'density', cells: [], maxCount: 0, footprints: null, area: AREA });
    const fc = data['coverage-area-src'] as GeoJSON.FeatureCollection;
    expect(fc.features).toHaveLength(0);
  });

  it('clears the density and footprints sources while showing an area', () => {
    const { map, data } = fakeMap();
    setCoverageDisplay(map as never, {
      mode: 'area',
      cells: [{ k: '4/1/1', n: 3 }],
      maxCount: 3,
      footprints: { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: AREA }] },
      area: AREA,
    });
    expect((data['coverage-src'] as GeoJSON.FeatureCollection).features).toHaveLength(0);
    expect((data['coverage-footprints-src'] as GeoJSON.FeatureCollection).features).toHaveLength(0);
  });
});

// M3-10 F4 (Otto, 30.09.2026): pinned layers of different datasets are drawn
// together — the map keeps no notion of "the open dataset" for them.
describe('syncLayers: pinned layers of several datasets', () => {
  it('draws a layer of each dataset, bottom of the list first', () => {
    const { map, sources, pinnedOrder } = liveMap();
    syncLayers(map as never, [
      pinned('top', 'https://t/dem/{z}/{x}/{y}'),
      pinned('bottom', 'https://t/optical/{z}/{x}/{y}'),
    ]);
    expect(pinnedOrder()).toEqual([lyr('bottom'), lyr('top')]);
    expect(sources.size).toBe(2);
  });

  it('leaves a layer that is switched off out of sight, and only that one', () => {
    const { map, visible } = liveMap();
    syncLayers(map as never, [pinned('a', 'https://t/a', { visible: false }), pinned('b', 'https://t/b')]);
    expect(visible(lyr('a'))).toBe(false);
    expect(visible(lyr('b'))).toBe(true);
  });
});

// M4-17c: a pinned time step is a mosaic and the scenes under it, which step aside from its first level.
describe('syncLayers: a pinned mosaic', () => {
  const scene = (hideFrom?: number): LayerOverlay => ({
    kind: 'raster',
    tileUrl: 'https://t/scene',
    bounds: [0, 0, 1, 1],
    minZoom: 0,
    maxZoom: 7,
    ...(hideFrom === undefined ? {} : { hideFrom }),
  });
  const mosaic: LayerOverlay = { kind: 'raster', tileUrl: 'https://t/mosaic', bounds: [0, 0, 1, 1], minZoom: 8, maxZoom: 19 };

  it('hides the scenes from the mosaic level up and leaves the mosaic itself shown at every level', () => {
    const { map, layers } = liveMap();
    syncLayers(map as never, [pinned('m', 'unused', { overlays: [scene(6.5), mosaic] })]);
    expect(layers.get(lyr('m', 0))?.maxzoom).toBe(6.5);
    expect(layers.get(lyr('m', 1))?.maxzoom).toBeUndefined();
  });

  it('is another picture than the same scene without the step aside, and replaces it', () => {
    const { map, layers, log } = liveMap();
    syncLayers(map as never, [pinned('m', 'unused', { overlays: [scene()] })]);
    syncLayers(map as never, [pinned('m', 'unused', { overlays: [scene(6.5)] })]);
    expect(log.sourcesAdded).toHaveLength(2);
    expect(layers.get(lyr('m', 0))?.maxzoom).toBe(6.5);
  });
});

// M4-13c-5: a result layer whose job's results are about to go loads no more tiles.
describe('syncLayers: a result layer that expired', () => {
  const result = (id: string, expired: boolean) =>
    pinned(id, `https://t/${id}`, {
      derived: 'result',
      result: { jobID: 'J', expires: '2026-10-27T10:00:00Z', gsd: 10, resampled: null, expired, dataType: 'float32', stats: null },
    });

  it('has no source on the map, and the other layers keep theirs', () => {
    const { map, sources } = liveMap();
    syncLayers(map as never, [result('gone', true), pinned('kept', 'https://t/kept'), result('live', false)]);
    expect(sources.size).toBe(2);
    expect([...sources.keys()].some((id) => id.includes('gone'))).toBe(false);
  });

  it('is taken off the map when it expires, source and layer together', () => {
    const { map, sources, visible } = liveMap();
    syncLayers(map as never, [result('r', false)]);
    expect(sources.size).toBe(1);
    expect(visible(lyr('r'))).toBe(true);
    syncLayers(map as never, [result('r', true)]);
    expect(sources.size).toBe(0);
  });
});

// M4-28: the layer manager is quick and truthful. Each case here failed against
// the code that removed and re-added every source on every call and named the map
// layers after their position among the visible ones.
describe('syncLayers: switching, opacity and order change the map, not its sources', () => {
  const list = () => [pinned('a', 'https://t/a'), pinned('b', 'https://t/b'), pinned('c', 'https://t/c')];

  it('switches a layer by its visibility, without adding or removing a source', () => {
    const { map, log, visible } = liveMap();
    syncLayers(map as never, list());
    const added = log.sourcesAdded.length;
    syncLayers(map as never, list().map((l) => (l.id === 'b' ? { ...l, visible: false } : l)));
    expect(visible(lyr('b'))).toBe(false);
    syncLayers(map as never, list());
    expect(visible(lyr('b'))).toBe(true);
    expect(log.sourcesAdded).toHaveLength(added);
    expect(log.sourcesRemoved).toEqual([]);
  });

  it('keeps the source of every other layer when one is switched', () => {
    const { map, sources } = liveMap();
    syncLayers(map as never, list());
    const before = new Map(sources);
    syncLayers(map as never, list().map((l) => (l.id === 'a' ? { ...l, visible: false } : l)));
    for (const [id, spec] of before) expect(sources.get(id)).toBe(spec);
  });

  it('changes the opacity of a layer in place', () => {
    const { map, layers, log } = liveMap();
    syncLayers(map as never, list());
    syncLayers(map as never, list().map((l) => (l.id === 'c' ? { ...l, opacity: 0.2 } : l)));
    expect(layers.get(lyr('c'))!.paint['raster-opacity']).toBe(0.2);
    expect(layers.get(lyr('a'))!.paint['raster-opacity']).toBe(0.8);
    expect(log.sourcesRemoved).toEqual([]);
  });

  it('draws a layer switched off from the start only once it is switched on', () => {
    const { map, visible } = liveMap();
    syncLayers(map as never, [pinned('a', 'https://t/a', { visible: false })]);
    expect(visible(lyr('a'))).toBe(false);
    syncLayers(map as never, [pinned('a', 'https://t/a')]);
    expect(visible(lyr('a'))).toBe(true);
  });

  it('names the map layers after the pinned layer, whatever else is on or off', () => {
    const { map, pinnedOrder } = liveMap();
    syncLayers(map as never, list());
    syncLayers(map as never, list().map((l) => (l.id === 'a' ? { ...l, visible: false } : l)));
    expect(pinnedOrder()).toEqual([lyr('c'), lyr('b'), lyr('a')]);
  });

  it('switches exactly the layer asked for among layers of one name and one picture', () => {
    const { map, visible } = liveMap();
    const twins = ['x', 'y', 'z'].map((id) => pinned(id, 'https://t/same'));
    syncLayers(map as never, twins);
    syncLayers(map as never, twins.map((l) => (l.id === 'y' ? { ...l, visible: false } : l)));
    expect([visible(lyr('x')), visible(lyr('y')), visible(lyr('z'))]).toEqual([true, false, true]);
  });

  it('adds a source for a layer that is new, and drops that of one that is gone', () => {
    const { map, sources, log } = liveMap();
    syncLayers(map as never, list());
    syncLayers(map as never, [pinned('d', 'https://t/d'), ...list().filter((l) => l.id !== 'b')]);
    expect(sources.has('layer-src-d-0')).toBe(true);
    expect(sources.has('layer-src-b-0')).toBe(false);
    expect(log.sourcesAdded.filter((id) => id !== 'layer-src-d-0' && !'abc'.includes(id.split('-')[2]))).toEqual([]);
    expect(log.sourcesRemoved).toEqual(['layer-src-b-0']);
  });

  it('builds a layer anew when what it shows changes', () => {
    const { map, sources } = liveMap();
    syncLayers(map as never, [pinned('a', 'https://t/a/v1')]);
    syncLayers(map as never, [pinned('a', 'https://t/a/v2')]);
    expect((sources.get('layer-src-a-0') as { tiles: string[] }).tiles).toEqual(['https://t/a/v2']);
  });
});

describe('syncLayers: the map follows the order of the list', () => {
  const ids = ['a', 'b', 'c', 'd'];
  const list = (order: string[] = ids) => order.map((id) => pinned(id, `https://t/${id}`));
  // The list's top is the map's top: the reverse of the list.
  const expectedOrder = (order: string[]) => [...order].reverse().map((id) => lyr(id));

  it('stacks the first of the list on top', () => {
    const { map, pinnedOrder } = liveMap();
    syncLayers(map as never, list());
    expect(pinnedOrder()).toEqual(expectedOrder(ids));
  });

  it('follows a move up and a move down, with no source touched', () => {
    const { map, pinnedOrder, log } = liveMap();
    syncLayers(map as never, list());
    for (const order of [['a', 'c', 'b', 'd'], ['c', 'a', 'b', 'd'], ['c', 'a', 'd', 'b'], ['b', 'd', 'a', 'c']]) {
      syncLayers(map as never, list(order));
      expect(pinnedOrder()).toEqual(expectedOrder(order));
    }
    expect(log.sourcesRemoved).toEqual([]);
    expect(log.sourcesAdded).toHaveLength(4);
  });

  it('puts a layer added at the top, in the middle or at the bottom where the list has it', () => {
    const { map, pinnedOrder } = liveMap();
    syncLayers(map as never, [pinned('b', 'https://t/b'), pinned('c', 'https://t/c')]);
    for (const order of [['a', 'b', 'c'], ['a', 'b', 'x', 'c'], ['a', 'b', 'x', 'c', 'y']]) {
      syncLayers(map as never, list(order));
      expect(pinnedOrder()).toEqual(expectedOrder(order));
    }
  });

  it('keeps the order when a layer is removed, replaced or switched off', () => {
    const { map, pinnedOrder } = liveMap();
    syncLayers(map as never, list());
    syncLayers(map as never, list(['a', 'c', 'd']));
    expect(pinnedOrder()).toEqual(expectedOrder(['a', 'c', 'd']));
    syncLayers(map as never, [pinned('n', 'https://t/n'), ...list(['a', 'c', 'd']).slice(1)]);
    expect(pinnedOrder()).toEqual(expectedOrder(['n', 'c', 'd']));
    syncLayers(map as never, [{ ...pinned('n', 'https://t/n'), visible: false }, ...list(['c', 'd'])]);
    expect(pinnedOrder()).toEqual(expectedOrder(['n', 'c', 'd']));
  });

  it('orders a layer with several overlays as one block', () => {
    const { map, pinnedOrder } = liveMap();
    const two = pinned('two', 'https://t/two/0', {
      overlays: [0, 1].map((n) => ({ kind: 'raster' as const, tileUrl: `https://t/two/${n}`, bounds: [0, 0, 1, 1] as [number, number, number, number], minZoom: 0, maxZoom: 12 })),
    });
    syncLayers(map as never, [pinned('a', 'https://t/a'), two, pinned('c', 'https://t/c')]);
    expect(pinnedOrder()).toEqual([lyr('c'), lyr('two', 0), lyr('two', 1), lyr('a')]);
    syncLayers(map as never, [two, pinned('a', 'https://t/a'), pinned('c', 'https://t/c')]);
    expect(pinnedOrder()).toEqual([lyr('c'), lyr('a'), lyr('two', 0), lyr('two', 1)]);
  });

  it('draws them again, in order, on a map whose style was reloaded', () => {
    const first = liveMap();
    syncLayers(first.map as never, list());
    const second = liveMap(); // setStyle() wiped everything
    syncLayers(second.map as never, list(['b', 'a', 'c', 'd']));
    expect(second.pinnedOrder()).toEqual(expectedOrder(['b', 'a', 'c', 'd']));
    expect(second.sources.size).toBe(4);
  });

  it('keeps the active view above the pinned layers whichever was synced last', () => {
    const { map, stack, pinnedOrder } = liveMap();
    const dataset = zarrLikeDataset();
    const view = () =>
      syncMosaic(map as never, { items: [scene], dataset, downloaded: {}, selectedIds: [], render: {}, focusMode: false, showDownloaded: true });
    const viewAbovePinned = () => {
      expect(pinnedOrder()).toHaveLength(2);
      const top = Math.max(...pinnedOrder().map((id) => stack.indexOf(id)));
      expect(stack.indexOf('m-tiles-lyr-0')).toBeGreaterThan(top);
      expect(stack.indexOf('m-tiles-lyr-0')).toBeLessThan(stack.indexOf('aoi-fill'));
    };
    view();
    syncLayers(map as never, [pinned('a', 'https://t/a'), pinned('b', 'https://t/b')]);
    viewAbovePinned();
    syncLayers(map as never, [pinned('b', 'https://t/b'), pinned('a', 'https://t/a')]);
    viewAbovePinned();
    view();
    syncLayers(map as never, [pinned('b', 'https://t/b', { visible: false }), pinned('a', 'https://t/a')]);
    viewAbovePinned();
  });
});

describe('ensureBaseLayers', () => {
  it('lays the end of the layer manager right under the AOI, once', () => {
    const { map, stack } = liveMap(['bg']);
    ensureBaseLayers(map as never);
    ensureBaseLayers(map as never);
    expect(stack.slice(0, 3)).toEqual(['bg', 'layers-top', 'aoi-fill']);
    expect(stack.filter((id) => id === 'layers-top')).toHaveLength(1);
  });
});

// Quicklooks arrive when their image has loaded, in any order — the place in the
// stack is the list's, not that of the arrival.
describe('syncLayers: quicklooks that arrive late', () => {
  class FakeImage {
    static all: FakeImage[] = [];
    crossOrigin = '';
    naturalWidth = 4;
    naturalHeight = 4;
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    private target = '';
    constructor() {
      FakeImage.all.push(this);
    }
    set src(v: string) {
      this.target = v;
    }
    get src() {
      return this.target;
    }
    arrive() {
      this.onload?.();
    }
  }
  const image = (id: string, url: string, over: Partial<MapLayer> = {}): MapLayer => ({
    ...pinned(id, ''),
    overlays: [{ kind: 'image', url, coords: [[0, 1], [1, 1], [1, 0], [0, 0]], nodataMax: null }],
    ...over,
  });
  const loading = (url: string) => FakeImage.all.filter((i) => i.src === url);

  beforeEach(() => {
    FakeImage.all = [];
    vi.stubGlobal('Image', FakeImage);
    // No 2D context: the quicklook is handed on as it is (`processQuicklook`).
    vi.stubGlobal('document', { createElement: () => ({ getContext: () => null }) });
  });
  afterEach(() => vi.unstubAllGlobals());

  it('places a quicklook that arrives last under the tiles above it in the list', () => {
    const { map, pinnedOrder } = liveMap();
    syncLayers(map as never, [pinned('top', 'https://t/top'), image('low', 'https://q/late-1.png'), pinned('bottom', 'https://t/bottom')]);
    expect(pinnedOrder()).toEqual([lyr('bottom'), lyr('top')]);
    loading('https://q/late-1.png').forEach((i) => i.arrive());
    expect(pinnedOrder()).toEqual([lyr('bottom'), lyr('low'), lyr('top')]);
  });

  it('places quicklooks in the list order whichever arrives first', () => {
    const { map, pinnedOrder } = liveMap();
    syncLayers(map as never, [image('one', 'https://q/late-2a.png'), image('two', 'https://q/late-2b.png'), image('three', 'https://q/late-2c.png')]);
    for (const url of ['late-2b', 'late-2c', 'late-2a']) loading(`https://q/${url}.png`).forEach((i) => i.arrive());
    expect(pinnedOrder()).toEqual([lyr('three', 0), lyr('two', 0), lyr('one', 0)]);
  });

  it('does not place a quicklook whose layer was removed while it loaded', () => {
    const { map, pinnedOrder } = liveMap();
    syncLayers(map as never, [image('gone', 'https://q/late-3.png'), pinned('a', 'https://t/a')]);
    syncLayers(map as never, [pinned('a', 'https://t/a')]);
    loading('https://q/late-3.png').forEach((i) => i.arrive());
    expect(pinnedOrder()).toEqual([lyr('a')]);
  });

  it('places a quicklook hidden while it loaded as hidden, with the opacity it has now', () => {
    const { map, visible, layers } = liveMap();
    syncLayers(map as never, [image('q', 'https://q/late-4.png')]);
    syncLayers(map as never, [image('q', 'https://q/late-4.png', { visible: false, opacity: 0.3 })]);
    loading('https://q/late-4.png').forEach((i) => i.arrive());
    expect(visible(lyr('q'))).toBe(false);
    expect(layers.get(lyr('q'))!.paint['raster-opacity']).toBe(0.3);
  });

  it('does not fetch the quicklook of a layer that is switched off', () => {
    const { map } = liveMap();
    syncLayers(map as never, [image('q', 'https://q/late-5.png', { visible: false })]);
    expect(loading('https://q/late-5.png')).toHaveLength(0);
    syncLayers(map as never, [image('q', 'https://q/late-5.png')]);
    expect(loading('https://q/late-5.png')).toHaveLength(1);
  });

  it('places it once, however often the layers were synced while it loaded', () => {
    const { map, log } = liveMap();
    const layers = [image('q', 'https://q/late-6.png')];
    syncLayers(map as never, layers);
    syncLayers(map as never, layers);
    loading('https://q/late-6.png').forEach((i) => i.arrive());
    expect(log.sourcesAdded).toEqual(['layer-src-q-0']);
  });
});

// --- the preview of the processing panel (M4-13c-2) ---

// A map that remembers its layers in order, as MapLibre stacks them: a layer
// added `before` another goes right under it.
function stackedMap(initial: string[]) {
  const stack = [...initial];
  const sources = new Map<string, Record<string, unknown>>();
  const map = {
    getLayer: (id: string) => (stack.includes(id) ? { id } : undefined),
    getSource: (id: string) => sources.get(id),
    removeLayer: (id: string) => stack.splice(stack.indexOf(id), 1),
    removeSource: (id: string) => sources.delete(id),
    addSource: (id: string, spec: Record<string, unknown>) => sources.set(id, spec),
    addLayer: (layer: { id: string }, before?: string) => {
      stack.splice(before ? stack.indexOf(before) : stack.length, 0, layer.id);
    },
  };
  return { map, stack, sources };
}

const previewTiles = (n: number): LayerOverlay[] =>
  Array.from({ length: n }, (_, i) => ({
    kind: 'raster' as const,
    tileUrl: `/collections/c/items/S${i}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=red&op=band_math`,
    bounds: [10, 47, 11, 48] as [number, number, number, number],
    minZoom: 8,
    maxZoom: 14,
    preview: true as const,
  }));

describe('syncPreview', () => {
  it('adds one raster source per scene, within the released levels, under the AOI outline', () => {
    const { map, stack, sources } = stackedMap(['m-tiles-lyr-0', 'aoi-fill', 'aoi-line']);
    const tiles = previewTiles(2);
    syncPreview(map as never, tiles);
    expect(stack).toEqual(['m-tiles-lyr-0', 'preview-lyr-0', 'preview-lyr-1', 'aoi-fill', 'aoi-line']);
    // The first scene is on top, as in the full-resolution view: it is drawn last.
    expect((sources.get('preview-src-1') as { tiles: string[] }).tiles).toEqual([(tiles[0] as { tileUrl: string }).tileUrl]);
    expect(sources.get('preview-src-0')).toMatchObject({
      type: 'raster',
      tiles: [(tiles[1] as { tileUrl: string }).tileUrl],
      tileSize: 256,
      bounds: [10, 47, 11, 48],
      minzoom: 8,
      maxzoom: 14,
    });
  });

  it('builds the picture anew each time, and leaves nothing behind for none', () => {
    const { map, stack, sources } = stackedMap(['aoi-fill']);
    syncPreview(map as never, previewTiles(3));
    syncPreview(map as never, previewTiles(1));
    expect(stack).toEqual(['preview-lyr-0', 'aoi-fill']);
    expect([...sources.keys()]).toEqual(['preview-src-0']);
    syncPreview(map as never, []);
    expect(stack).toEqual(['aoi-fill']);
    expect(sources.size).toBe(0);
  });

  it('keeps the preview on top of a quicklook that arrives after it', () => {
    const { map, stack } = stackedMap(['aoi-fill']);
    syncPreview(map as never, previewTiles(1));
    // The browse view places its tiles as it is synced: below the preview, not above.
    syncMosaic(map as never, {
      items: [scene],
      dataset: zarrLikeDataset(),
      downloaded: {},
      selectedIds: [],
      render: {},
      focusMode: false,
      showDownloaded: true,
    });
    expect(stack.indexOf('m-tiles-lyr-0')).toBeLessThan(stack.indexOf('preview-lyr-0'));
    expect(stack.indexOf('preview-lyr-0')).toBeLessThan(stack.indexOf('aoi-fill'));
  });
});
