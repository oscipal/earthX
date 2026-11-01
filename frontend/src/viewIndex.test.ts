// The quick calculation of an index in the view (NM4-14b): the look an index makes, the tile of a scene or of a mosaic that
// computes it, and why the tile route cannot take it. Pure functions; the dropdown is `ViewerControls`' (`ViewIndex.test.tsx`).

import { describe, expect, it } from 'vitest';

import { SENTINEL_2_PRESETS } from './fixtures/indexPresets';
import { indexPresetsOf } from './indexPresets';
import { MAX_MOSAIC_REQUEST_BYTES, mosaicRequestBytes, mosaicTemplateOf, type Mosaics, type SceneEntry } from './mosaic';
import type { Collection, DownloadedInfo, TimeStepGroup } from './types';
import {
  assetsOfExpression,
  indexBlockOf,
  indexLookOf,
  indexNote,
  indexNoteTip,
  indexRasterOf,
  indexRastersOfPass,
  indexStatisticsUrl,
  viewIndexOf,
} from './viewIndex';

const collection = { id: 's2', 'earthx:index_presets': SENTINEL_2_PRESETS } as unknown as Collection;
const [NDVI, NDWI, , , EVI] = indexPresetsOf(collection);

const info = (id: string, minZoom = 8): DownloadedInfo => ({
  datasetId: 's2',
  tileUrl: `/collections/s2/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`,
  bounds: [10, 47, 11, 48],
  asset: 'visual',
  minZoom,
  maxZoom: 14,
});
const entries = (n: number, minZoom = 8, pad = 3): SceneEntry[] =>
  Array.from({ length: n }, (_, i) => {
    const id = `S2_${String(i).padStart(pad, '0')}`;
    return [id, info(id, minZoom)];
  });
// The scenes of the longest time step the tiler takes (64) with ids long enough that the request is above 7168 bytes.
const LONG = 110;
const group = (list: SceneEntry[]): TimeStepGroup[] => [{ label: 'a', key: ['a'], items: list.map(([id]) => ({ id, bbox: [10, 47, 11, 48], properties: {}, assets: {} })) } as unknown as TimeStepGroup];
const mosaicsOf = (list: SceneEntry[]): Mosaics => ({
  [mosaicTemplateOf('s2', list)!]: { tileUrl: '/collections/s2/mosaic/tiles/WebMercatorQuad/{z}/{x}/{y}?plain', bounds: [10, 47, 11, 48], minZoom: 8, maxZoom: 14, order: list.map(([id]) => id) },
});

describe('the look of an index', () => {
  it('is the name, the range and the colormap of the preset, and no band', () => {
    expect(indexLookOf(NDWI)).toEqual({ index: 'NDWI', colormapName: 'rdbu', rescale: '-1,1' });
  });

  it('is read back from a look by the presets of the dataset', () => {
    expect(viewIndexOf({ index: 'NDVI' }, collection)).toBe(NDVI);
  });

  it.each([
    ['a look without an index', {}],
    ['an index the dataset does not offer', { index: 'SAVI' }],
    ['a look with an empty name', { index: '' }],
  ])('finds no preset for %s', (_, look) => {
    expect(viewIndexOf(look, collection)).toBeNull();
  });

  it('finds none in a dataset without presets (the DEM) or without a collection', () => {
    expect(viewIndexOf({ index: 'NDVI' }, { id: 'dem', 'earthx:index_presets': [] } as unknown as Collection)).toBeNull();
    expect(viewIndexOf({ index: 'NDVI' }, undefined)).toBeNull();
  });
});

describe('the assets an index reads', () => {
  it('are the names of its expression in the order they first stand there, each once', () => {
    expect(assetsOfExpression(NDVI.expression)).toEqual(['nir', 'red']);
    expect(assetsOfExpression(EVI.expression)).toEqual(['nir', 'red', 'blue']);
    expect(assetsOfExpression('(red - red) / (red + 1)')).toEqual(['red']);
  });
});

describe('the tile of a scene', () => {
  it('is the tile route with Band math: the assets, the step with name and expression, and the band it shows', () => {
    const [scene] = entries(1);
    const raster = indexRasterOf(scene[1], [scene], 's2', NDVI);
    expect(typeof raster).toBe('object');
    const url = new URL((raster as { tileUrl: string }).tileUrl, 'http://x');
    expect(decodeURIComponent(url.pathname)).toBe('/collections/s2/items/S2_000/tiles/WebMercatorQuad/{z}/{x}/{y}');
    expect(url.searchParams.getAll('asset')).toEqual(['nir', 'red']);
    expect(url.searchParams.getAll('op')).toEqual(['band_math']);
    expect(url.searchParams.getAll('op_version')).toEqual(['2']);
    expect(JSON.parse(url.searchParams.get('params')!)).toEqual({ expression: '(nir - red) / (nir + red)', name: 'NDVI' });
    expect(url.searchParams.get('band')).toBe('NDVI');
    expect(url.searchParams.has('item')).toBe(false);
  });

  it('keeps the zoom levels and the bounds of the scene', () => {
    const [scene] = entries(1, 6);
    expect(indexRasterOf(scene[1], [scene], 's2', NDVI)).toMatchObject({ bounds: [10, 47, 11, 48], minZoom: 6, maxZoom: 14 });
  });
});

describe('the tile of a mosaic', () => {
  const list = entries(3);
  const mosaic = mosaicsOf(list)[mosaicTemplateOf('s2', list)!]!;

  it('is the mosaic route with the scenes as one item each, the same assets and step', () => {
    const raster = indexRasterOf(mosaic, list, 's2', NDWI);
    const url = new URL((raster as { tileUrl: string }).tileUrl, 'http://x');
    expect(decodeURIComponent(url.pathname)).toBe('/collections/s2/mosaic/tiles/WebMercatorQuad/{z}/{x}/{y}');
    expect(url.searchParams.getAll('item')).toEqual(['S2_000', 'S2_001', 'S2_002']);
    expect(url.searchParams.getAll('asset')).toEqual(['green', 'nir']);
    expect(url.searchParams.get('band')).toBe('NDWI');
    expect(raster).toMatchObject({ minZoom: 8, maxZoom: 14 });
  });

  it('is one URL for the same scenes in another order', () => {
    const reversed = [...list].reverse();
    expect((indexRasterOf(mosaic, reversed, 's2', NDWI) as { tileUrl: string }).tileUrl).toBe((indexRasterOf(mosaic, list, 's2', NDWI) as { tileUrl: string }).tileUrl);
  });

  it('is refused where the index reads more assets than a mosaic tile takes', () => {
    const wide = { ...NDVI, expression: 'a + b + c + d + e' };
    expect(indexRasterOf(mosaic, list, 's2', wide)).toBe('assets');
    // One scene is no mosaic: the same index is a tile of the scene.
    const [scene] = list;
    expect(typeof indexRasterOf(scene[1], [scene], 's2', wide)).toBe('object');
  });

  it('is refused where the request is longer than the tiler passes (414)', () => {
    const many = entries(64, 8, LONG);
    const big = mosaicsOf(many)[mosaicTemplateOf('s2', many)!]!;
    const refused = indexRasterOf(big, many, 's2', EVI);
    expect(refused).toBe('length');
    // Three scenes of the same kind fit.
    const fitting = indexRasterOf(mosaic, list, 's2', EVI) as { tileUrl: string };
    expect(mosaicRequestBytes(fitting.tileUrl, 14)).toBeLessThanOrEqual(MAX_MOSAIC_REQUEST_BYTES);
  });
});

describe('the rasters of a pass', () => {
  it('are all made into the index, or none: a refused raster blocks the pass', () => {
    const many = entries(64, 8, LONG);
    const big = mosaicsOf(many)[mosaicTemplateOf('s2', many)!]!;
    expect(indexRastersOfPass([big], many, 's2', EVI)).toEqual({ rasters: [], block: 'length' });
    const [scene] = entries(1);
    const one = indexRastersOfPass([scene[1]], [scene], 's2', EVI);
    expect(one.block).toBeNull();
    expect(one.rasters).toHaveLength(1);
  });
});

describe('why an index is not drawn (indexBlockOf)', () => {
  const list = entries(3);
  const args = { datasetId: 's2', entries: list, groups: group(list), mosaics: mosaicsOf(list), preset: NDVI, mapZoom: 12 };

  it('is nothing where it can be drawn', () => {
    expect(indexBlockOf(args)).toBeNull();
  });

  it('is the zoom below the level the tiles start at, less the lead MapLibre has: half a level for the 512-px mosaic', () => {
    expect(indexBlockOf({ ...args, mapZoom: 5 })).toBe('zoom');
    expect(indexBlockOf({ ...args, mapZoom: 7.4 })).toBe('zoom');
    expect(indexBlockOf({ ...args, mapZoom: 7.5 })).toBeNull();
    expect(indexBlockOf({ ...args, mapZoom: 8 })).toBeNull();
  });

  it('is the same for scenes drawn one by one: the level of the scenes, a level and a half ahead (256-px tiles)', () => {
    const one = entries(1, 8);
    expect(indexBlockOf({ ...args, entries: one, groups: group(one), mosaics: {}, mapZoom: 4 })).toBe('zoom');
    expect(indexBlockOf({ ...args, entries: one, groups: group(one), mosaics: {}, mapZoom: 6.4 })).toBe('zoom');
    expect(indexBlockOf({ ...args, entries: one, groups: group(one), mosaics: {}, mapZoom: 6.5 })).toBeNull();
    expect(indexBlockOf({ ...args, entries: one, groups: group(one), mosaics: {}, mapZoom: 9 })).toBeNull();
  });

  it('is the request first, which zooming does not mend', () => {
    const many = entries(64, 8, LONG);
    expect(indexBlockOf({ ...args, entries: many, groups: group(many), mosaics: mosaicsOf(many), preset: EVI, mapZoom: 3 })).toBe('length');
    const wide = { ...NDVI, expression: 'a + b + c + d + e' };
    expect(indexBlockOf({ ...args, preset: wide, mapZoom: 3 })).toBe('assets');
  });

  it('is nothing while the mosaic of the pass is not known, as long as the map is zoomed in: the view waits as without an index', () => {
    expect(indexBlockOf({ ...args, mosaics: {}, mapZoom: 12 })).toBeNull();
  });

  it('is the zoom of the scenes where the mosaic is not known yet', () => {
    expect(indexBlockOf({ ...args, mosaics: {}, mapZoom: 5 })).toBe('zoom');
  });
});

describe('the words of the note', () => {
  it('says what to do about the zoom, and that the rest cannot be computed here; the tooltip says why and what to do', () => {
    expect(indexNote('zoom', 'NDVI')).toBe('Zoom in to compute NDVI');
    expect(indexNote('length', 'NDVI')).toBe('NDVI cannot be computed here');
    expect(indexNote('assets', 'EVI')).toBe('EVI cannot be computed here');
    expect(indexNoteTip('zoom')).toBe('The quick calculation works from zoom 8. For whole scenes start a job in Processing.');
    expect(indexNoteTip('length')).toContain('start a job in Processing');
    expect(indexNoteTip('assets')).toBe(indexNoteTip('length'));
  });
});

describe('the statistics of an index', () => {
  it('are the same route and step as the tiles, over one scene', () => {
    const url = new URL(indexStatisticsUrl('s2', 'S2_000', NDWI), 'http://x');
    expect(url.pathname).toBe('/collections/s2/items/S2_000/statistics');
    expect(url.searchParams.getAll('asset')).toEqual(['green', 'nir']);
    expect(url.searchParams.get('band')).toBe('NDWI');
  });
});
