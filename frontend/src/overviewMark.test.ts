// UI-08, Otto 16.11.2026: one mark "Overview" wherever the map shows an overview instead of the originals; here the part that asks the map.

import { Evented, ImageSource } from 'maplibre-gl';
import { beforeEach, describe, expect, it } from 'vitest';

import { buildOverviewTileTemplate } from './api';
import { isOverviewTileUrl, setMapOverview, showsOverview, watchOverviewMark } from './overviewMark';
import { useAppStore } from './store';

interface FakeLayer {
  id: string;
  source: string;
  tiles: string[];
  type?: string;
  minzoom?: number;
  maxzoom?: number;
  hidden?: boolean;
  opacity?: unknown;
}

function fakeMap(layers: FakeLayer[], zoom = 4) {
  const handlers = new Map<string, () => void>();
  const map = {
    zoom,
    getZoom: () => map.zoom,
    getLayersOrder: () => layers.map((l) => l.id),
    getLayer: (id: string) => {
      const l = layers.find((x) => x.id === id);
      return l && { type: l.type ?? 'raster', source: l.source, minzoom: l.minzoom ?? 0, maxzoom: l.maxzoom ?? 24 };
    },
    getLayoutProperty: (id: string) => (layers.find((x) => x.id === id)?.hidden ? 'none' : 'visible'),
    getPaintProperty: (id: string) => layers.find((x) => x.id === id)?.opacity ?? 1,
    getSource: (id: string) => {
      const l = layers.find((x) => x.source === id);
      return l && { tiles: l.tiles };
    },
    on: (type: string, handler: () => void) => handlers.set(type, handler),
    fire: (type: string) => handlers.get(type)?.(),
  };
  return map as unknown as Parameters<typeof showsOverview>[0] & { zoom: number; fire: (type: string) => void };
}

const PYRAMID = buildOverviewTileTemplate('cop-dem-glo-30');
const SELECTION = '/collections/esa-worldcover-2021/overview/0123456789abcdef0123456789abcdef/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=512';
const COMPUTED = buildOverviewTileTemplate('cop-dem-glo-30', [{ op: 'terrain', op_version: 1, params: { product: 'slope' } }] as never);
const SCENE = '/collections/cop-dem-glo-30/items/A/tiles/WebMercatorQuad/{z}/{x}/{y}';
const MOSAIC = '/collections/cop-dem-glo-30/mosaic/0123456789abcdef0123456789abcdef/tiles/WebMercatorQuad/{z}/{x}/{y}';
const RESULT = '/results/ZyXwVuTsRqPoNmLkJiHg_-/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=256';

describe('isOverviewTileUrl', () => {
  it('knows the overview route, with and without a footprint selection and with steps', () => {
    for (const url of [PYRAMID, SELECTION, COMPUTED]) expect(isOverviewTileUrl(url)).toBe(true);
  });

  it('takes no other route for one: a scene, a mosaic, a result, the basemap, a dataset named "overview"', () => {
    for (const url of [SCENE, MOSAIC, RESULT, 'https://basemap.example/tiles/{z}/{x}/{y}.png', '/collections/overview/items/A/tiles/{z}/{x}/{y}', '/collections/a/overview/footprints']) {
      expect(isOverviewTileUrl(url)).toBe(false);
    }
  });
});

describe('showsOverview', () => {
  it('is true while a layer of the overview route is drawn at the zoom of the map (pyramid, substitute, computed)', () => {
    for (const tiles of [[PYRAMID], [SELECTION], [COMPUTED]]) expect(showsOverview(fakeMap([{ id: 'o', source: 'res-tiles-src-0', tiles, maxzoom: 7 }]))).toBe(true);
  });

  it('is false above the level where the overview steps aside, and for the originals', () => {
    expect(showsOverview(fakeMap([{ id: 'o', source: 's', tiles: [PYRAMID], maxzoom: 7 }], 7))).toBe(false);
    expect(showsOverview(fakeMap([{ id: 'o', source: 's', tiles: [PYRAMID], minzoom: 5 }], 4))).toBe(false);
    expect(showsOverview(fakeMap([{ id: 'm', source: 's', tiles: [MOSAIC] }, { id: 'r', source: 'r', tiles: [RESULT] }]))).toBe(false);
  });

  it('is false for a layer that is switched off or fully transparent, and for what is no raster', () => {
    expect(showsOverview(fakeMap([{ id: 'o', source: 's', tiles: [PYRAMID], hidden: true }]))).toBe(false);
    expect(showsOverview(fakeMap([{ id: 'o', source: 's', tiles: [PYRAMID], opacity: 0 }]))).toBe(false);
    expect(showsOverview(fakeMap([{ id: 'o', source: 's', tiles: [PYRAMID], type: 'line' }]))).toBe(false);
    expect(showsOverview(fakeMap([]))).toBe(false);
  });
});

// A quicklook as the map holds it (UI-10): MapLibre's own image source, whose `tiles` are its loaded tiles keyed by id, not URLs.
function quicklookSource(): ImageSource {
  const dispatcher = { getActor: () => ({ sendAsync: async () => ({}) }) };
  return new ImageSource('ql', { type: 'image', url: 'data:,', coordinates: [[0, 1], [1, 1], [1, 0], [0, 0]] }, dispatcher as never, new Evented());
}

describe('showsOverview with the sources MapLibre really holds (UI-10)', () => {
  function mapWith(sources: Record<string, unknown>) {
    const map = fakeMap(Object.keys(sources).map((id) => ({ id, source: id, tiles: [] })));
    (map as unknown as { getSource: (id: string) => unknown }).getSource = (id) => sources[id];
    return map;
  }

  it('skips a quicklook of a scene, an image source with its tiles as an object, without throwing', () => {
    const source = quicklookSource();
    expect(Array.isArray(source.tiles)).toBe(false);
    expect(showsOverview(mapWith({ ql: source }))).toBe(false);
    expect(showsOverview(mapWith({ ql: source, o: { type: 'raster', tiles: [PYRAMID] } }))).toBe(true);
  });

  it('skips a source that has not loaded its tiles yet, a source that is gone and tiles that are no URLs', () => {
    for (const source of [{ type: 'raster' }, undefined, null, { tiles: null }, { tiles: 'x' }, { tiles: [7, null] }]) {
      expect(showsOverview(mapWith({ s: source }))).toBe(false);
    }
  });
});

describe('watchOverviewMark', () => {
  beforeEach(() => useAppStore.setState({ mapOverview: false }));

  it('tells a change only, after a zoom', () => {
    const map = fakeMap([{ id: 'o', source: 's', tiles: [PYRAMID], maxzoom: 7 }], 4);
    const told: boolean[] = [];
    watchOverviewMark(map, (shown) => told.push(shown));
    map.fire('styledata');
    map.fire('sourcedata');
    map.zoom = 9;
    map.fire('zoomend');
    map.fire('idle');
    expect(told).toEqual([true, false]);
  });

  it('writes the store', () => {
    setMapOverview(true);
    expect(useAppStore.getState().mapOverview).toBe(true);
  });
});
