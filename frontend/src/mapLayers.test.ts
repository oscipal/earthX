import { describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import {
  buildTileUrl,
  setCoverageDisplay,
  syncFocusRaster,
  syncHighlight,
  syncMosaic,
  syncSelectionHighlight,
} from './mapLayers';
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
    addLayer: (layer: { id: string }) => layers.push(layer.id),
  };
  return { map, sources, layers, data, removedSources, removedLayers };
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
