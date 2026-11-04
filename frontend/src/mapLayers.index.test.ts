// The view draws an index through the tile route with an operator (NM4-14b): one tile source per scene, or one for the
// mosaic of a pass, with the range and colormap of the look; a raster the route cannot take is not drawn (and nothing
// takes its place); a look without an index draws as before.

import { describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import { SENTINEL_2_PRESETS } from './fixtures/indexPresets';
import { liveMap } from './fixtures/liveMap';
import { ensureBaseLayers, syncFocusRaster } from './mapLayers';
import { mosaicTemplateOf, type Mosaics, type SceneEntry } from './mosaic';
import type { DownloadedInfo, StacItem } from './types';

const collection = (presets: unknown[]) =>
  ({
    id: 's2',
    title: 'Sentinel-2 L2A',
    'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
    'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
    'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
    'earthx:index_presets': presets,
  }) as never;

const [dataset] = datasetsFrom([collection(SENTINEL_2_PRESETS)]);
const WIDE = { id: 'a + b + c + d + e' };
const [wideDataset] = datasetsFrom([collection([{ ...SENTINEL_2_PRESETS[0], name: 'WIDE', expression: WIDE.id }])]);

const info = (id: string): DownloadedInfo => ({
  datasetId: 's2',
  tileUrl: `/collections/s2/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`,
  bounds: [10, 47, 11, 48],
  asset: 'visual',
  minZoom: 8,
  maxZoom: 14,
});
const ids = ['A', 'B', 'C'];
const downloaded = Object.fromEntries(ids.map((id) => [id, info(id)]));
const items: StacItem[] = ids.map((id) => ({ id, collection: 's2', bbox: [10, 47, 11, 48], properties: { datetime: '2026-07-01T10:00:00Z' }, assets: {} }));
const entries: SceneEntry[] = ids.map((id) => [id, downloaded[id]]);
const mosaics: Mosaics = { [mosaicTemplateOf('s2', entries)!]: { tileUrl: '/collections/s2/mosaic/tiles/WebMercatorQuad/{z}/{x}/{y}?plain', bounds: [10, 47, 11, 48], minZoom: 8, maxZoom: 14, order: ids } };

const freshMap = () => {
  const live = liveMap([]);
  ensureBaseLayers(live.map as never);
  return live;
};
const sources = (live: ReturnType<typeof liveMap>) => [...live.sources.entries()].filter(([id]) => id.includes('tiles-src')).map(([, source]) => source);
const urls = (live: ReturnType<typeof liveMap>) => sources(live).map((source) => (source.tiles as string[])[0]);
const draw = (live: ReturnType<typeof liveMap>, render: object, over: object = {}) =>
  syncFocusRaster(live.map as never, { downloaded, render, showDownloaded: true, aoi: null, cropToAoi: false, items, dataset, groups: undefined, mosaics: undefined, ...over });

const INDEX = { index: 'NDVI', colormapName: 'rdylgn', rescale: '-1,1' };

describe('the view with an index in its look', () => {
  it('draws a tile of each scene that computes the index, in the range and colormap of the look', () => {
    const live = freshMap();
    draw(live, INDEX);
    expect(urls(live)).toHaveLength(3);
    for (const url of urls(live)) {
      const query = new URL(url, 'http://x').searchParams;
      expect(query.getAll('op')).toEqual(['band_math']);
      expect(query.get('band')).toBe('NDVI');
      expect(query.getAll('asset')).toEqual(['nir', 'red']);
      expect(query.get('rescale')).toBe('-1,1');
      expect(query.get('colormap_name')).toBe('rdylgn');
      expect(query.has('bidx')).toBe(false);
    }
    expect(urls(live).map((url) => decodeURIComponent(new URL(url, 'http://x').pathname).split('/')[4]).sort()).toEqual(['A', 'B', 'C']);
  });

  it('draws the mosaic of a pass with the operator, one source, once the mosaic is known', () => {
    const live = freshMap();
    draw(live, INDEX, { groups: [{ label: 'a', key: ['a'], items }], mosaics });
    expect(urls(live)).toHaveLength(1);
    const url = new URL(urls(live)[0], 'http://x');
    expect(decodeURIComponent(url.pathname)).toContain('/collections/s2/mosaic/tiles/');
    expect(url.searchParams.getAll('item')).toEqual(ids);
    expect(url.searchParams.get('band')).toBe('NDVI');
    expect(url.searchParams.get('rescale')).toBe('-1,1');
    expect(sources(live)[0]).toMatchObject({ minzoom: 8, maxzoom: 14 });
  });

  it('waits for the mosaic as it does without an index: nothing is drawn meanwhile', () => {
    const live = freshMap();
    draw(live, INDEX, { groups: [{ label: 'a', key: ['a'], items }], mosaics: {} });
    expect(urls(live)).toEqual([]);
  });

  it('draws nothing for a pass the mosaic route cannot take, and no raw band in its place', () => {
    const live = freshMap();
    draw(live, { ...INDEX, index: 'WIDE' }, { dataset: wideDataset, groups: [{ label: 'a', key: ['a'], items }], mosaics });
    expect(urls(live)).toEqual([]);
  });

  it('draws a look without an index as before: the asset of the scene, the stretch of the look', () => {
    const live = freshMap();
    draw(live, { rescale: '0,3000' });
    expect(urls(live).map((url) => new URL(url, 'http://x').searchParams.get('asset'))).toEqual(['visual', 'visual', 'visual']);
    expect(urls(live).every((url) => !url.includes('op=band_math'))).toBe(true);
  });

  it('draws a look that names an index the dataset does not offer as a plain look, never as another index', () => {
    const live = freshMap();
    draw(live, { index: 'SAVI', rescale: '0,3000' });
    expect(urls(live).every((url) => new URL(url, 'http://x').searchParams.get('asset') === 'visual')).toBe(true);
  });

  it('draws nothing while the view is hidden, an index or not', () => {
    const live = freshMap();
    draw(live, INDEX, { showDownloaded: false });
    expect(urls(live)).toEqual([]);
  });
});
