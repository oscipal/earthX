// @vitest-environment jsdom
//
// M3-12, O5: below a dataset's smallest released zoom, the full-resolution
// view shows the quicklook (cropped to the AOI) instead of an empty area.
// Split into its own jsdom file for the same reason `store.confirmDownload.
// test.ts` is: the rest of `mapLayers.test.ts` runs faster without a DOM.
//
// No `canvas` package is installed, so `HTMLCanvasElement.getContext('2d')`
// is `null` here (jsdom's own limitation, not this code's) — `processQuicklook`
// then falls back to the plain image `src` unprocessed (its own documented
// behaviour for a context it cannot get). That is exactly the branch this
// file can exercise; the pixel-level clip/nodata math is unit-tested on its
// own in `geoUtils.test.ts` (`quicklookAoiPixelRings`) and needs no canvas at
// all. `Image` is stubbed to "load" synchronously, since jsdom does not
// actually fetch a fake test URL.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { syncFocusRaster, syncLayers } from './mapLayers';
import { liveMap, pinned } from './fixtures/liveMap';
import { underlayOf } from './underlay';
import type { DownloadedInfo, StacAsset, StacItem } from './types';

class FakeImage {
  crossOrigin = '';
  naturalWidth = 4;
  naturalHeight = 4;
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private _src = '';
  set src(value: string) {
    this._src = value;
    this.onload?.();
  }
  get src(): string {
    return this._src;
  }
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

function quicklookDataset(minZoom = 8) {
  const [dataset] = datasetsFrom([
    {
      id: 'sentinel-2-c1-l2a',
      title: 'Sentinel-2 L2A',
      'earthx:capabilities': CAPABILITIES,
      'earthx:viewer': {
        group_by: ['datetime'],
        min_zoom: minZoom,
        max_zoom: 19,
        browse: 'quicklook',
        quicklook_nodata_max: 16,
        results_group_by: ['datetime'],
      },
    },
  ]);
  return dataset;
}

const VISUAL_ASSET: StacAsset = {
  href: 'https://example.invalid/visual.tif',
  'proj:transform': [10, 0, 499980, 0, -10, 5300040],
  'proj:shape': [10980, 10980],
};

function georeferencedScene(overrides: Partial<StacItem> = {}): StacItem {
  return {
    id: 'S2A_1',
    bbox: [8.999746, 46.866609, 9.668828, 47.853693],
    properties: { datetime: '2026-07-24T10:00:00Z', 'proj:epsg': 32632 },
    assets: {
      thumbnail: { href: 'https://example.invalid/thumb.jpg', roles: ['thumbnail'] },
      visual: VISUAL_ASSET,
    },
    ...overrides,
  };
}

function info(overrides: Partial<DownloadedInfo> = {}): DownloadedInfo {
  return {
    tileUrl: '/collections/sentinel-2-c1-l2a/items/S2A_1/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual',
    bounds: [8.999746, 46.866609, 9.668828, 47.853693],
    asset: 'visual',
    minZoom: 8,
    maxZoom: 19,
    ...overrides,
  };
}

interface AddedSource {
  id: string;
  spec: Record<string, unknown>;
}

interface AddedLayer {
  id: string;
  spec: Record<string, unknown>;
}

function fakeMap() {
  const sources: AddedSource[] = [];
  const layers: AddedLayer[] = [];
  const map = {
    getSource: () => undefined,
    getLayer: () => undefined,
    removeLayer: () => {},
    removeSource: () => {},
    addSource: (id: string, spec: Record<string, unknown>) => sources.push({ id, spec }),
    addLayer: (layer: { id: string } & Record<string, unknown>) => layers.push({ id: layer.id, spec: layer }),
  };
  return { map, sources, layers };
}

describe('syncFocusRaster: the quicklook underlay below min_zoom (M3-12, O5)', () => {
  beforeEach(() => {
    vi.stubGlobal('Image', FakeImage);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('adds an image source below the raster tile source, for a browse: quicklook dataset', () => {
    const { map, sources, layers } = fakeMap();
    const scene = georeferencedScene();
    syncFocusRaster(map as never, {
      downloaded: { [scene.id]: info() },
      render: {},
      showDownloaded: true,
      items: [scene],
      dataset: quicklookDataset(),
    });
    const imageSources = sources.filter((s) => s.spec.type === 'image');
    const rasterSources = sources.filter((s) => s.spec.type === 'raster');
    expect(imageSources).toHaveLength(1);
    expect(rasterSources).toHaveLength(1);
    // The tile layer is added after the underlay, so it ends up on top
    // (`beforeAoi` puts each newly added layer just below the AOI layer).
    const imageLayerIdx = layers.findIndex((l) => l.id.startsWith('m-img-lyr'));
    const tileLayerIdx = layers.findIndex((l) => l.id.startsWith('m-tiles-lyr'));
    expect(imageLayerIdx).toBeGreaterThanOrEqual(0);
    expect(imageLayerIdx).toBeLessThan(tileLayerIdx);
  });

  it('keeps the underlay under the raster tiles at every zoom, so no zoom and no late tile leaves the map empty', () => {
    const { map, layers } = fakeMap();
    const scene = georeferencedScene();
    syncFocusRaster(map as never, {
      downloaded: { [scene.id]: info() },
      render: {},
      showDownloaded: true,
      items: [scene],
      dataset: quicklookDataset(8),
    });
    const imageLayer = layers.find((l) => l.id.startsWith('m-img-lyr'));
    expect(imageLayer?.spec.paint).toMatchObject({ 'raster-opacity': 1 });
  });

  it('adds no underlay for a dataset that is not browse: quicklook', () => {
    const { map, sources } = fakeMap();
    const scene = georeferencedScene();
    const [previewTiles] = datasetsFrom([
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
      },
    ]);
    syncFocusRaster(map as never, {
      downloaded: { [scene.id]: info() },
      render: {},
      showDownloaded: true,
      items: [scene],
      dataset: previewTiles,
    });
    expect(sources.filter((s) => s.spec.type === 'image')).toHaveLength(0);
    expect(sources.filter((s) => s.spec.type === 'raster')).toHaveLength(1);
  });

  it('adds no underlay for a scene with no quicklook asset of its own', () => {
    const { map, sources } = fakeMap();
    const scene = georeferencedScene({ assets: { visual: VISUAL_ASSET } });
    syncFocusRaster(map as never, {
      downloaded: { [scene.id]: info() },
      render: {},
      showDownloaded: true,
      items: [scene],
      dataset: quicklookDataset(),
    });
    expect(sources.filter((s) => s.spec.type === 'image')).toHaveLength(0);
    expect(sources.filter((s) => s.spec.type === 'raster')).toHaveLength(1);
  });

  it('never lets the AOI reach the placed image source as a coordinate', () => {
    const { map, sources } = fakeMap();
    const scene = georeferencedScene();
    syncFocusRaster(map as never, {
      downloaded: { [scene.id]: info() },
      render: {},
      showDownloaded: true,
      aoi: {
        type: 'Polygon',
        coordinates: [[[9.1, 47.1], [9.2, 47.1], [9.2, 47.2], [9.1, 47.2], [9.1, 47.1]]],
      },
      cropToAoi: true,
      items: [scene],
      dataset: quicklookDataset(),
    });
    const [imageSource] = sources.filter((s) => s.spec.type === 'image');
    // The clip happens on the canvas the (mocked) image data goes through,
    // never in the source spec itself — `coordinates` is always the scene's
    // own full extent, exactly as the plain browse-mode quicklook places it.
    expect(imageSource.spec.url).not.toContain('9.1');
    expect(JSON.stringify(imageSource.spec.coordinates)).not.toContain('9.15');
  });
});

// UI-01a (Otto, 24.10.2026): a pinned layer draws tiles only from the dataset's smallest zoom and
// has no quicklook of its own, so the underlay is not redundant with it. It stays when a layer
// draws the scene's tiles, or the map would be empty when zooming out.
describe('syncFocusRaster: the underlay when a layer draws the scene', () => {
  beforeEach(() => {
    vi.stubGlobal('Image', FakeImage);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const view = (live: ReturnType<typeof liveMap>, tilesInLayer = false) => {
    const scene = georeferencedScene();
    syncFocusRaster(live.map as never, {
      downloaded: { [scene.id]: info() },
      render: {},
      showDownloaded: true,
      items: [scene],
      dataset: quicklookDataset(),
      tilesInLayer,
    });
  };
  // As "Add to layers" pins the scene: tiles from the smallest zoom, no image overlay.
  const layerOfView = (id: string) =>
    pinned(id, 'unused', {
      overlays: [{ kind: 'raster', tileUrl: info().tileUrl, bounds: info().bounds, minZoom: 8, maxZoom: 19 }],
    });
  // The quicklook is on the map once, opaque at every zoom.
  const expectQuicklookOnce = (live: ReturnType<typeof liveMap>) => {
    const images = [...live.layers.values()].filter((l) => l.id.startsWith('m-img-lyr-'));
    expect(images).toHaveLength(1);
    expect(live.visible(images[0].id)).toBe(true);
    expect(images[0].paint['raster-opacity']).toBe(1);
  };

  it('keeps the quicklook once, where the layer draws nothing yet', () => {
    const live = liveMap();
    view(live);
    syncLayers(live.map as never, [layerOfView('mine'), pinned('other', 'https://t/other')]);
    expectQuicklookOnce(live);
    // The layer's tiles start at the zoom where the quicklook is gone, so they never meet.
    expect(live.layers.get('layer-lyr-mine-0')?.maxzoom).toBeUndefined();
    expect((live.sources.get('layer-src-mine-0') as { minzoom: number }).minzoom).toBe(8);
  });

  it('keeps it once when the layer is the view and the view draws no tiles of its own', () => {
    const live = liveMap();
    syncLayers(live.map as never, [layerOfView('mine')]);
    view(live, true);
    expectQuicklookOnce(live);
    expect([...live.layers.keys()].some((id) => id.startsWith('m-tiles-lyr-'))).toBe(false);
  });

  it('keeps it once while the layer is switched off', () => {
    const live = liveMap();
    view(live);
    syncLayers(live.map as never, [{ ...layerOfView('mine'), visible: false }]);
    expectQuicklookOnce(live);
  });

  it('steps aside for a layer that holds the quicklook itself, which is then on the map once, at its place', () => {
    const live = liveMap();
    const scene = georeferencedScene();
    const quicklook = underlayOf(scene, quicklookDataset(), null);
    expect(quicklook).not.toBeNull();
    view(live);
    syncLayers(live.map as never, [
      pinned('mine', 'unused', {
        overlays: [quicklook!, { kind: 'raster', tileUrl: info().tileUrl, bounds: info().bounds, minZoom: 8, maxZoom: 19 }],
      }),
      pinned('other', 'https://t/other'),
    ]);
    expect(live.visible('m-img-lyr-0')).toBe(false);
    expect(live.visible('m-tiles-lyr-0')).toBe(false);
    expect(live.visible('layer-lyr-mine-0')).toBe(true);
    const images = [...live.layers.values()].filter((l) => (live.sources.get(l.source ?? '') as { type?: string })?.type === 'image');
    expect(images.filter((l) => live.visible(l.id)).map((l) => l.id)).toEqual(['layer-lyr-mine-0']);
    // The layer's quicklook is at the layer's place in the list: under the layer above it, over the one below.
    expect(live.stack.indexOf('layer-lyr-other-0')).toBeLessThan(live.stack.indexOf('layer-lyr-mine-0'));
  });
});
