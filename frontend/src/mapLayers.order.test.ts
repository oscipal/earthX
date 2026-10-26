// UI-01a (Befund Punkt 10): the order of the list is the order of the map. Each case here
// failed against the code before UI-01a: a budget of overlays that ran short at the top of
// the list, and a view that lay over a layer showing the same picture.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import type { LayerOverlay, MapLayer } from './layers';
import { syncBrowseMosaic, syncFocusRaster, syncLayers } from './mapLayers';
import { liveMap, lyr, pinned } from './fixtures/liveMap';
import type { DownloadedInfo, StacItem } from './types';

type Live = ReturnType<typeof liveMap>;

const raster = (tileUrl: string, over: Partial<Extract<LayerOverlay, { kind: 'raster' }>> = {}): LayerOverlay => ({
  kind: 'raster',
  tileUrl,
  bounds: [10, 47, 11, 48],
  minZoom: 8,
  maxZoom: 14,
  ...over,
});
const image = (url: string): LayerOverlay => ({
  kind: 'image',
  url,
  coords: [[10, 48], [11, 48], [11, 47], [10, 47]],
  nodataMax: null,
});
const layerOf = (id: string, overlays: LayerOverlay[], over: Partial<MapLayer> = {}): MapLayer =>
  pinned(id, 'unused', { overlays, ...over });

const layersOf = (live: Live, id: string) => [...live.layers.keys()].filter((k) => k.startsWith(`layer-lyr-${id}-`));

// What a map layer draws: the tile template or the image of its source.
const pictureOf = (live: Live, lyrId: string): string => {
  const source = live.sources.get(live.layers.get(lyrId)?.source ?? '') as { tiles?: string[]; url?: string } | undefined;
  return source?.tiles?.[0] ?? source?.url ?? '';
};
// The pictures the map shows, bottom to top: pinned layers and the view, whatever is switched off left out.
const shown = (live: Live): string[] =>
  live.stack.filter((id) => (id.startsWith('layer-lyr-') || id.startsWith('m-')) && live.visible(id)).map((id) => pictureOf(live, id));

describe('syncLayers: the budget of overlays counts from the top of the list', () => {
  const big = (id: string, n: number) => layerOf(id, Array.from({ length: n }, (_, i) => raster(`https://t/${id}/${i}`)));
  const four = (order = ['a', 'b', 'c', 'd']) => order.map((id) => big(id, 65));

  it('draws the layers on top whole and cuts the bottom one', () => {
    const live = liveMap();
    const notDrawn = syncLayers(live.map as never, four());
    expect([layersOf(live, 'a').length, layersOf(live, 'b').length, layersOf(live, 'c').length, layersOf(live, 'd').length]).toEqual([
      65, 65, 65, 5,
    ]);
    expect(notDrawn).toBe(60);
  });

  it('draws a layer whole once it is moved to the top, and cuts the one now at the bottom', () => {
    const live = liveMap();
    syncLayers(live.map as never, four());
    syncLayers(live.map as never, four(['d', 'a', 'b', 'c']));
    expect([layersOf(live, 'd').length, layersOf(live, 'c').length]).toEqual([65, 5]);
  });

  it('keeps the top overlays of a layer that is cut, which is the mosaic of a pinned time step', () => {
    const live = liveMap();
    const notDrawn = syncLayers(live.map as never, [big('m', 205)]);
    expect(live.layers.has(lyr('m', 204))).toBe(true);
    expect(live.layers.has(lyr('m', 5))).toBe(true);
    expect(live.layers.has(lyr('m', 4))).toBe(false);
    expect(notDrawn).toBe(5);
  });

  it('says nothing when every overlay fits', () => {
    expect(syncLayers(liveMap().map as never, four().slice(0, 3))).toBe(0);
  });
});

const CAPABILITIES = {
  roi: true,
  time_range: true,
  band_math: true,
  interpolation: true,
  ml_processing: true,
  quad_pol: false,
  single_coverage_product: false,
};
const dataset = () =>
  datasetsFrom([
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
  ])[0];
const scene = (id: string): StacItem => ({
  id,
  bbox: [10, 47, 11, 48],
  properties: { datetime: '2026-07-24T10:00:00Z' },
  assets: { SR_10m: { href: 'https://data.test/x.zarr/r10m', roles: ['data'] } },
});
const downloadedOf = (id: string): DownloadedInfo => ({
  tileUrl: `/collections/synthetic-zarr/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`,
  bounds: [10, 47, 11, 48],
  asset: 'visual',
  minZoom: 8,
  maxZoom: 14,
});

// The view in browse mode (the preview tiles of a scene) or in full resolution, on a map of its own.
const browseView = (map: Live['map'], id: string) =>
  syncBrowseMosaic(map as never, { items: [scene(id)], dataset: dataset() });
const focusView = (map: Live['map'], id: string, tilesInLayer = false) =>
  syncFocusRaster(map as never, {
    downloaded: { [id]: downloadedOf(id) },
    render: {},
    showDownloaded: true,
    items: [scene(id)],
    dataset: dataset(),
    tilesInLayer,
  });
// The overlay a view draws, read off a scratch map: a layer pinned from it has the same picture.
const overlayOf = (draw: (map: Live['map']) => void): LayerOverlay => {
  const scratch = liveMap();
  draw(scratch.map);
  const spec = [...scratch.sources.values()][0] as { tiles: string[]; bounds: [number, number, number, number]; minzoom: number; maxzoom: number };
  return raster(spec.tiles[0], { bounds: spec.bounds, minZoom: spec.minzoom, maxZoom: spec.maxzoom });
};

describe('the view and a layer with the same picture', () => {
  const twin = (live: Live) => live.visible('m-tiles-lyr-0');

  it('does not lie over the layer that shows the same preview: the layer is the picture', () => {
    const live = liveMap();
    const mine = overlayOf((m) => browseView(m, 'A'));
    syncLayers(live.map as never, [layerOf('mine', [mine]), layerOf('other', [raster('https://t/other')])]);
    browseView(live.map, 'A');
    expect(twin(live)).toBe(false);
    expect(shown(live)).toEqual(['https://t/other', (mine as { tileUrl: string }).tileUrl]);
  });

  it('follows the layer when it is moved below another', () => {
    const live = liveMap();
    const mine = layerOf('mine', [overlayOf((m) => browseView(m, 'A'))]);
    const other = layerOf('other', [raster('https://t/other')]);
    browseView(live.map, 'A');
    syncLayers(live.map as never, [mine, other]);
    expect(twin(live)).toBe(false);
    syncLayers(live.map as never, [other, mine]);
    expect(shown(live).pop()).toBe('https://t/other');
  });

  it('draws the view itself again while the layer is switched off or gone', () => {
    const live = liveMap();
    const mine = layerOf('mine', [overlayOf((m) => browseView(m, 'A'))]);
    browseView(live.map, 'A');
    syncLayers(live.map as never, [mine]);
    expect(twin(live)).toBe(false);
    syncLayers(live.map as never, [{ ...mine, visible: false }]);
    expect(twin(live)).toBe(true);
    syncLayers(live.map as never, [mine]);
    expect(twin(live)).toBe(false);
    syncLayers(live.map as never, []);
    expect(twin(live)).toBe(true);
  });

  it('leaves a view that no layer shows above all the layers', () => {
    const live = liveMap();
    syncLayers(live.map as never, [layerOf('mine', [overlayOf((m) => browseView(m, 'A'))])]);
    browseView(live.map, 'B');
    expect(twin(live)).toBe(true);
    expect(live.stack.indexOf('m-tiles-lyr-0')).toBeGreaterThan(live.stack.indexOf(lyr('mine')));
  });

  it('does not count an expired result as drawing the picture', () => {
    const live = liveMap();
    const expired = layerOf('mine', [overlayOf((m) => browseView(m, 'A'))], {
      derived: 'result',
      result: { jobID: 'J', expires: '2026-10-27T10:00:00Z', gsd: 10, resampled: null, expired: true },
    });
    browseView(live.map, 'A');
    syncLayers(live.map as never, [expired]);
    expect(twin(live)).toBe(true);
  });

  it('gives a full-resolution view the same behaviour, whichever was synced first', () => {
    const live = liveMap();
    const mine = layerOf('mine', [overlayOf((m) => focusView(m, 'A'))]);
    const other = layerOf('other', [raster('https://t/other')]);
    syncLayers(live.map as never, [mine, other]);
    focusView(live.map, 'A');
    syncLayers(live.map as never, [other, mine]);
    expect(live.visible('m-tiles-lyr-0')).toBe(false);
    expect(shown(live).pop()).toBe('https://t/other');
  });
});

// Five layers, one of each kind. After every move the map holds them in the order of the list;
// the view over them is its own picture or the picture of one of them.
describe('syncLayers: every kind of layer follows every move', () => {
  class FakeImage {
    crossOrigin = '';
    naturalWidth = 4;
    naturalHeight = 4;
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    private target = '';
    set src(v: string) {
      this.target = v;
      queueMicrotask(() => this.onload?.());
    }
    get src() {
      return this.target;
    }
  }
  beforeEach(() => {
    vi.stubGlobal('Image', FakeImage);
    vi.stubGlobal('document', { createElement: () => ({ getContext: () => null }) });
  });
  afterEach(() => vi.unstubAllGlobals());

  const view = {
    browse: { draw: (m: Live['map']) => browseView(m, 'OWN'), own: true },
    'full resolution': { draw: (m: Live['map']) => focusView(m, 'OWN'), own: true },
    'a layer': { draw: (m: Live['map']) => focusView(m, 'A'), own: false },
    none: { draw: () => {}, own: false },
  };
  const kinds = (): MapLayer[] => [
    layerOf('quicklook', [image('https://q/one.png')]),
    layerOf('full', [overlayOf((m) => focusView(m, 'A'))]),
    layerOf('preview', [raster('https://t/preview', { preview: true, maxZoom: 9 })], { derived: 'preview' }),
    layerOf('result', [raster('https://t/result')], {
      derived: 'result',
      result: { jobID: 'J', expires: '2026-12-01T10:00:00Z', gsd: 10, resampled: null, expired: false },
    }),
    layerOf('mosaic', [raster('https://t/scene', { hideFrom: 6.5, maxZoom: 7 }), raster('https://t/mosaic')]),
  ];
  const key = (o: LayerOverlay) => (o.kind === 'raster' ? o.tileUrl : o.url);
  const moves = (list: MapLayer[]) =>
    list.flatMap((l) => list.map((_, to) => ({ id: l.id, to })));

  for (const [name, { draw, own }] of Object.entries(view)) {
    it(`with ${name} as the view`, async () => {
      const live = liveMap();
      let list = kinds();
      draw(live.map);
      syncLayers(live.map as never, list);
      await Promise.resolve(); // the quicklook arrives
      for (const { id, to } of moves(list)) {
        const without = list.filter((l) => l.id !== id);
        list = [...without.slice(0, to), list.find((l) => l.id === id)!, ...without.slice(to)];
        syncLayers(live.map as never, list);
        await Promise.resolve();
        const expected = [...list].reverse().flatMap((l) => l.overlays.map(key));
        // The view of its own lies over all the layers; the picture of a layer is the layer's.
        expect(shown(live).filter((p) => !p.includes('/items/OWN/'))).toEqual(expected);
        if (own) expect(live.stack.indexOf('m-tiles-lyr-0')).toBeGreaterThan(Math.max(...live.pinnedOrder().map((x) => live.stack.indexOf(x))));
      }
    });
  }
});
