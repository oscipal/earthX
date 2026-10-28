// NM4-50 (Otto, 28.10.2026): a dataset with no quicklook (browse: full_resolution, the DEM) is previewed by the whole scene
// in full resolution, at every released level and not cut to the AOI — through the one function the quicklooks of the other
// datasets go through, so that the results, the ticks and "Hide results" govern it the same way. And a layer that is hidden
// stays off the map: a redraw of the map or a sync of other layers does not draw it again.

import { describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import { liveMap, lyr, pinned } from './fixtures/liveMap';
import { ensureBaseLayers, syncBrowseMosaic, syncLayers, syncResultsOverlay } from './mapLayers';
import type { StacItem } from './types';

const collection = (id: string, browse: 'full_resolution' | 'preview_tiles', minZoom: number, maxZoom: number) => ({
  id,
  title: id,
  'earthx:capabilities': { roi: true, time_range: browse !== 'full_resolution', band_math: true, interpolation: true },
  'earthx:viewer': { group_by: ['datetime'], min_zoom: minZoom, max_zoom: maxZoom, browse, quicklook_nodata_max: null, results_group_by: ['datetime'] },
  'earthx:default_render': { title: 'Standard', assets: ['data'], rescale: [[0, 4000]] as [number, number][], colormap_name: 'terrain', expression: null, resampling: 'nearest' },
});

const [dem, other] = datasetsFrom([collection('dem', 'full_resolution', 0, 15), collection('other', 'preview_tiles', 8, 14)] as never);
const scene = (id: string, collectionId: string): StacItem => ({ id, collection: collectionId, bbox: [10, 47, 11, 48], properties: { datetime: '2026-07-24T10:00:00Z' }, assets: {} });

const freshMap = () => {
  const live = liveMap([]);
  ensureBaseLayers(live.map as never);
  return live;
};
const tileSources = (live: ReturnType<typeof liveMap>) => [...live.sources.entries()].filter(([id]) => id.includes('tiles-src'));

describe('the preview of a dataset with no quicklook', () => {
  it('is the tiles of the whole scene, over every released level, with the standard visualisation and no cut to the AOI', () => {
    const live = freshMap();
    syncBrowseMosaic(live.map as never, { items: [scene('d1', 'dem')], dataset: dem, selectedIds: [] });
    const [[, source]] = tileSources(live);
    expect(source).toMatchObject({ type: 'raster', minzoom: 0, maxzoom: 15, bounds: [10, 47, 11, 48] });
    const url = (source.tiles as string[])[0];
    expect(url).toContain('/collections/dem/items/d1/tiles/');
    expect(url).toContain('colormap_name=terrain');
    expect(url).not.toContain('earthx-clip://');
  });

  it('is drawn the way the coarse-tile preview of another dataset is: one level there, all levels here', () => {
    const live = freshMap();
    syncBrowseMosaic(live.map as never, { items: [scene('o1', 'other')], dataset: other, selectedIds: [] });
    const [[, source]] = tileSources(live);
    expect(source).toMatchObject({ minzoom: 8, maxzoom: 8 });
  });

  it('is drawn under a view as well, by the results over the view', () => {
    const live = freshMap();
    syncResultsOverlay(live.map as never, { items: [scene('d1', 'dem')], dataset: dem, selectedIds: [] });
    const [[, source]] = tileSources(live);
    expect(source).toMatchObject({ minzoom: 0, maxzoom: 15 });
  });

  it('is gone with no scene to show, which is how "Hide results" takes it off', () => {
    const live = freshMap();
    syncBrowseMosaic(live.map as never, { items: [scene('d1', 'dem')], dataset: dem, selectedIds: [] });
    syncBrowseMosaic(live.map as never, { items: [], dataset: dem, selectedIds: [] });
    expect(live.stack.filter((id) => id.includes('tiles-lyr'))).toEqual([]);
  });
});

describe('a hidden layer', () => {
  const layers = (visible: boolean) => [pinned('a', 'https://t/a/{z}/{x}/{y}', { visible }), pinned('b', 'https://t/b/{z}/{x}/{y}')];

  it('stays off the map through a sync of the same list, of another list and a layer added', () => {
    const live = freshMap();
    syncLayers(live.map as never, layers(true));
    expect(live.visible(lyr('a'))).toBe(true);
    syncLayers(live.map as never, layers(false));
    expect(live.visible(lyr('a'))).toBe(false);
    syncLayers(live.map as never, layers(false));
    syncLayers(live.map as never, [pinned('c', 'https://t/c/{z}/{x}/{y}'), ...layers(false)]);
    expect(live.visible(lyr('a'))).toBe(false);
    expect(live.visible(lyr('b'))).toBe(true);
  });

  it('is not shown by a layer that is first synced hidden, and is shown once it is switched on', () => {
    const live = freshMap();
    syncLayers(live.map as never, layers(false));
    expect(live.visible(lyr('a'))).toBe(false);
    syncLayers(live.map as never, layers(true));
    expect(live.visible(lyr('a'))).toBe(true);
  });
});
