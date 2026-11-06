import { describe, expect, it } from 'vitest';

import {
  buildMosaicOperatorTileTemplate,
  buildMosaicTileTemplate,
  buildOperatorTileTemplate,
  buildTileTemplate,
  type TileStep,
} from './api';
import { clipTileUrl } from './aoiClip';
import { liveMap, lyr, pinned } from './fixtures/liveMap';
import { zoomMap } from './fixtures/zoomMap';
import type { LayerOverlay } from './layers';
import { buildTileUrl, syncLayers, syncPreview } from './mapLayers';
import { MAX_MOSAIC_REQUEST_BYTES, mosaicRequestBytes, viewOfPass } from './mosaic';
import type { MosaicInfo, SceneEntry } from './mosaic';
import { isOverview, resultTileTemplate } from './resultLayer';
import { levelAskedAt, MOSAIC_TILE_SIZE, TILE_SIZE, tileLevelAhead, tileMetres, tileSizeOf } from './tileSize';
import type { DownloadedInfo } from './types';
import { isDrawnAt, zoomInTo } from './zoomHint';

const DATASET = 'sentinel-2-c1-l2a';
const STEP: TileStep = { op: 'band_math', opVersion: 2, paramsJson: '{"expression":"(B08-B04)/(B08+B04)","name":"NDVI"}' };
const RESULT = '/results/AAAAAAAAAAAAAAAAAAAAAA/WebMercatorQuad/tilejson.json';

// What each kind of tile asks for (plan §15): 512 px for the mosaic and the mosaic with steps; 256 px for a scene, the
// scene with steps (the item preview) and a result.
const TEMPLATES = {
  scene: buildTileTemplate(DATASET, 'S2A_1', 'visual'),
  sceneWithSteps: buildOperatorTileTemplate(DATASET, 'S2A_1', ['B04', 'B08'], [STEP], 'NDVI'),
  result: resultTileTemplate(RESULT),
  mosaic: buildMosaicTileTemplate(DATASET, ['S2A_1', 'S2A_2'], 'visual'),
  mosaicWithSteps: buildMosaicOperatorTileTemplate(DATASET, ['S2A_1', 'S2A_2'], ['B04', 'B08'], [STEP], 'NDVI'),
} as const;

const SIZE_OF = {
  scene: 256,
  sceneWithSteps: 256,
  result: 256,
  mosaic: 512,
  mosaicWithSteps: 512,
} as const;

const overlay = (tileUrl: string, over: Partial<Extract<LayerOverlay, { kind: 'raster' }>> = {}): LayerOverlay => ({
  kind: 'raster',
  tileUrl,
  bounds: [10, 47, 11, 48],
  minZoom: 8,
  maxZoom: 14,
  ...over,
});

describe('the size of a tile (NM4-29b)', () => {
  it.each(Object.entries(SIZE_OF))('is %s px for the template of a %s tile', (kind, size) => {
    const template = TEMPLATES[kind as keyof typeof TEMPLATES];
    expect(tileSizeOf(template)).toBe(size);
    expect(tileSizeOf(buildTileUrl(template, { rescale: '0,1', colormapName: 'viridis' }))).toBe(size);
    expect(tileSizeOf(clipTileUrl(template, { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 47]]] }))).toBe(size);
  });

  it('is named in the query of the template for the mosaics, as the tiler takes it, and in none for a scene', () => {
    for (const kind of ['mosaic', 'mosaicWithSteps'] as const) {
      expect(new URL(TEMPLATES[kind], 'http://localhost').searchParams.getAll('tilesize')).toEqual(['512']);
    }
    for (const kind of ['scene', 'sceneWithSteps'] as const) {
      expect(new URL(TEMPLATES[kind], 'http://localhost').searchParams.has('tilesize')).toBe(false);
    }
    expect(new URL(TEMPLATES.result, 'http://localhost').searchParams.getAll('tilesize')).toEqual(['256']);
  });

  it('is the tiler\'s own 256 for a template that names none, or a size the tiler would refuse', () => {
    expect(tileSizeOf('/collections/d/items/a/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual')).toBe(TILE_SIZE);
    expect(tileSizeOf('/x?tilesize=4096')).toBe(TILE_SIZE);
    expect(tileSizeOf('/x?tilesize=')).toBe(TILE_SIZE);
    expect(tileSizeOf('/x?other_tilesize=512')).toBe(TILE_SIZE);
    expect(tileSizeOf('/x?tilesize=5120')).toBe(TILE_SIZE);
    expect(tileSizeOf('')).toBe(TILE_SIZE);
  });

  describe('of the source the map holds', () => {
    it.each(Object.entries(SIZE_OF))('is the one of the template, for a %s in the preview', (kind, size) => {
      const live = liveMap();
      syncPreview(live.map as never, [overlay(TEMPLATES[kind as keyof typeof TEMPLATES], { preview: true })]);
      const sources = [...live.sources.values()].filter((s) => s.type === 'raster');
      expect(sources).toHaveLength(1);
      expect(sources[0].tileSize).toBe(size);
    });

    it('is the one of the template, in every source of a pinned layer: a mosaic 512, a scene and a result 256', () => {
      const live = liveMap();
      const layers = Object.entries(TEMPLATES).map(([kind, template], i) => pinned(`l${i}`, template, { name: kind }));
      syncLayers(live.map as never, layers);
      for (const [i, [kind]] of Object.entries(TEMPLATES).entries()) {
        const source = live.sources.get(live.layers.get(lyr(`l${i}`))!.source!)!;
        expect(source.tileSize, kind).toBe(SIZE_OF[kind as keyof typeof SIZE_OF]);
        expect((source.tiles as string[])[0], kind).toBe(TEMPLATES[kind as keyof typeof TEMPLATES]);
      }
    });

    it('is the one of the template when the tile is cut to the AOI in the browser', () => {
      const live = liveMap();
      const aoi: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 47]]] };
      syncPreview(live.map as never, [overlay(clipTileUrl(TEMPLATES.mosaicWithSteps, aoi)), overlay(clipTileUrl(TEMPLATES.sceneWithSteps, aoi))]);
      expect([...live.sources.values()].map((s) => s.tileSize)).toEqual([256, 512]);
    });
  });
});

describe('the level the map asks for (NM4-29b)', () => {
  it('is, for a level L, asked from map zoom L - 0.5 for 512-px tiles and from L - 1.5 for 256-px tiles', () => {
    expect(tileLevelAhead(MOSAIC_TILE_SIZE)).toBe(0.5);
    expect(tileLevelAhead(TILE_SIZE)).toBe(1.5);
  });

  it.each([256, 512])('agrees with the level MapLibre rounds the map zoom to, for %i-px tiles', (size) => {
    for (let zoom = 0; zoom <= 20; zoom += 0.125) {
      for (const level of [8, 14]) {
        expect(levelAskedAt(zoom, size) >= level, `${size} px, level ${level}, zoom ${zoom}`).toBe(zoom >= level - tileLevelAhead(size));
      }
    }
  });

  it('puts a 512-px tile of the same pixel size one map zoom above a 256-px one', () => {
    expect(tileMetres(47, 13, 512)).toBeCloseTo(tileMetres(47, 14, 256), 9);
    expect(tileMetres(47, 13, 256)).toBeCloseTo(2 * tileMetres(47, 13, 512), 9);
  });

  describe('under a mosaic that starts at level 8', () => {
    const info = (id: string): DownloadedInfo => ({
      datasetId: DATASET,
      tileUrl: buildTileUrl(buildTileTemplate(DATASET, id, 'visual'), {}),
      bounds: [10, 47, 11, 48],
      asset: 'visual',
      minZoom: 0,
      maxZoom: 19,
    });
    const entries: SceneEntry[] = [['A', info('A')], ['B', info('B')]];
    const mosaic: MosaicInfo = {
      tileUrl: buildMosaicTileTemplate(DATASET, ['A', 'B'], 'visual'),
      bounds: [9, 46, 12, 49],
      minZoom: 8,
      maxZoom: 19,
      order: ['A', 'B'],
    };

    it('is the mosaic seen from map zoom 7.5 and the scenes up to it, and never both or neither', () => {
      const view = viewOfPass(DATASET, entries, { [mosaic.tileUrl]: mosaic });
      if (view.kind !== 'mosaic') throw new Error('expected a mosaic');
      const live = zoomMap();
      syncPreview(live.map as never, view.rasters.map((raster) => ({ kind: 'raster', ...raster })));
      const mosaicLayer = [...live.layers.values()].find((l) => l.maxzoom === undefined)!.id;
      for (const zoom of live.sweep()) {
        const drawn = live.picturesAt(zoom);
        if (zoom < 7.5) expect(drawn, `at ${zoom}`).not.toContain(mosaicLayer);
        else expect(drawn, `at ${zoom}`).toEqual([mosaicLayer]);
        if (zoom < 7.5 && zoom >= 5.5) expect(drawn, `at ${zoom}`).toHaveLength(2); // the two scenes, level 7 from 5.5 on
      }
    });

    it('is told by the zoom hint with the level the mosaic starts at, and with the scene\'s for a scene', () => {
      const mosaicOverlay = overlay(mosaic.tileUrl);
      const sceneOverlay = overlay(info('A').tileUrl);
      expect(isDrawnAt(mosaicOverlay, 7.4)).toBe(false);
      expect(isDrawnAt(mosaicOverlay, 7.5)).toBe(true);
      expect(isDrawnAt(sceneOverlay, 6.4)).toBe(false);
      expect(isDrawnAt(sceneOverlay, 6.5)).toBe(true);
      expect(zoomInTo([mosaicOverlay], 3)).toBe(8);
      expect(zoomInTo([sceneOverlay], 3)).toBe(7);
      expect(zoomInTo([mosaicOverlay, sceneOverlay], 3)).toBe(7);
    });
  });
});

describe('the pixel size of a result stays at 256 px (NM4-29b)', () => {
  const base = { gsd: 10, viewport: null, maxZoom: 22 };

  it('says "Overview" while the tile asked for is coarser than the result, as it did', () => {
    expect(isOverview({ ...base, mapZoom: 12 })).toBe(true); // level 13: 19 m at the equator
    expect(isOverview({ ...base, mapZoom: 13 })).toBe(false); // level 14: 9.5 m
    expect(isOverview({ ...base, mapZoom: 13, tileSize: TILE_SIZE })).toBe(false);
  });

  it('judges a 512-px source by its own level and its own pixels', () => {
    // A 512-px tile is asked for the level `round(zoom)`, and has the pixel size of 256-px tiles one level up.
    expect(isOverview({ ...base, mapZoom: 12.4, tileSize: MOSAIC_TILE_SIZE })).toBe(true); // level 12: 19 m
    expect(isOverview({ ...base, mapZoom: 13.4, tileSize: MOSAIC_TILE_SIZE })).toBe(false); // level 13: 9.5 m
    // Held at its last level 13, a 512-px source is 9.5 m per pixel; a 256-px one is 19 m.
    expect(isOverview({ ...base, mapZoom: 20, maxZoom: 13, tileSize: MOSAIC_TILE_SIZE })).toBe(false);
    expect(isOverview({ ...base, mapZoom: 20, maxZoom: 13, tileSize: TILE_SIZE })).toBe(true);
  });
});

describe('the request of a mosaic tile counts its size (NM4-29b)', () => {
  const ids = (n: number) => Array.from({ length: n }, (_, i) => `S2B_MSIL2A_20260${(i % 9) + 1}01T101559_N0511_R022_T32TQT_${String(i).padStart(4, '0')}`);

  it('is the template of the tile with `&tilesize=512`, 13 bytes longer than it was', () => {
    const bytes = (template: string) => mosaicRequestBytes(template, 14);
    const without = buildMosaicTileTemplate(DATASET, ids(8), 'visual').replace('&tilesize=512', '');
    expect(bytes(buildMosaicTileTemplate(DATASET, ids(8), 'visual')) - bytes(without)).toBe('&tilesize=512'.length);
    expect('&tilesize=512'.length).toBe(13);
  });

  it('is over the limit the tiler passes for a request that stayed under it without the size', () => {
    // Two scenes with ids as long as it takes: the request grows by two bytes with each character of an id.
    const request = (length: number) => buildMosaicTileTemplate(DATASET, ['a'.repeat(length), 'b'.repeat(length)], 'visual');
    let length = 1;
    while (mosaicRequestBytes(request(length), 14) <= MAX_MOSAIC_REQUEST_BYTES) length++;
    const bare = request(length).replace('&tilesize=512', '');
    expect(mosaicRequestBytes(request(length), 14)).toBeGreaterThan(MAX_MOSAIC_REQUEST_BYTES);
    expect(mosaicRequestBytes(bare, 14)).toBeLessThanOrEqual(MAX_MOSAIC_REQUEST_BYTES);
  });

  it('is counted for a mosaic with steps as well', () => {
    const template = buildMosaicOperatorTileTemplate(DATASET, ids(40), ['B04', 'B08'], [STEP], 'NDVI');
    const bare = template.replace('&tilesize=512', '');
    expect(mosaicRequestBytes(template, 19) - mosaicRequestBytes(bare, 19)).toBe(13);
  });
});
