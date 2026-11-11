// The opacity of the view of the search (Otto, 2.11.2026): every picture of the view takes it, at once and without loading a tile
// again, and a picture laid later is laid with it. A pinned layer keeps its own.

import { afterEach, describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import { liveMap, pinned } from './fixtures/liveMap';
import { ensureBaseLayers, setViewOpacity, syncFocusRaster, syncLayers } from './mapLayers';
import type { DownloadedInfo, StacItem } from './types';

const dataset = () =>
  datasetsFrom([
    {
      id: 'optical',
      title: 'Optical',
      'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
      'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'preview_tiles', quicklook_nodata_max: null, results_group_by: ['datetime'], overview: 'pyramid' as const, overview_resampling: 'average' as const },
      'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]] as [number, number][], colormap_name: null, expression: null, resampling: 'nearest' },
    },
  ] as never)[0];
const scene = (id: string): StacItem => ({ id, bbox: [10, 47, 11, 48], properties: { datetime: '2026-07-24T10:00:00Z' }, assets: {} });
const tile = (id: string): DownloadedInfo => ({
  datasetId: 'optical',
  tileUrl: `/collections/optical/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`,
  bounds: [10, 47, 11, 48],
  asset: 'visual',
  minZoom: 8,
  maxZoom: 14,
});

type Live = ReturnType<typeof liveMap>;
const view = (live: Live, ids = ['S1']) =>
  syncFocusRaster(live.map as never, {
    downloaded: Object.fromEntries(ids.map((id) => [id, tile(id)])),
    render: {},
    showDownloaded: true,
    items: ids.map(scene),
    dataset: dataset(),
    tilesInLayer: false,
  });
const viewTiles = (live: Live) => live.stack.filter((id) => /^[mn]-tiles-lyr-/u.test(id));
const opacityOf = (live: Live, id: string) => (live.map.getLayer(id) as { paint: Record<string, unknown> }).paint['raster-opacity'];

function freshMap(): Live {
  const live = liveMap([]);
  ensureBaseLayers(live.map as never);
  return live;
}

afterEach(() => setViewOpacity(freshMap().map as never, 1));

describe('the opacity of the view', () => {
  it('is 1 to begin with', () => {
    const live = freshMap();
    view(live);
    expect(viewTiles(live).length).toBeGreaterThan(0);
    for (const id of viewTiles(live)) expect(opacityOf(live, id)).toBe(1);
  });

  it('changes the paint of every picture of the view at once, and loads no tile again', () => {
    const live = freshMap();
    view(live, ['S1', 'S2']);
    const sources = live.log.sourcesAdded.length;
    setViewOpacity(live.map as never, 0.3);
    expect(viewTiles(live)).toHaveLength(2);
    for (const id of viewTiles(live)) expect(opacityOf(live, id)).toBe(0.3);
    expect(live.log.sourcesAdded).toHaveLength(sources);
  });

  it('is the opacity a picture laid later is laid with', () => {
    const live = freshMap();
    setViewOpacity(live.map as never, 0.5);
    view(live, ['S3']);
    for (const id of viewTiles(live)) expect(opacityOf(live, id)).toBe(0.5);
  });

  it('stays between 0 and 1', () => {
    const live = freshMap();
    view(live);
    setViewOpacity(live.map as never, 7);
    for (const id of viewTiles(live)) expect(opacityOf(live, id)).toBe(1);
    setViewOpacity(live.map as never, -2);
    for (const id of viewTiles(live)) expect(opacityOf(live, id)).toBe(0);
  });

  it('leaves a pinned layer at its own opacity', () => {
    const live = freshMap();
    const layer = pinned('P1', '/collections/optical/items/P1/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual');
    syncLayers(live.map as never, [layer]);
    const own = live.stack.filter((id) => id.startsWith('layer-lyr-'));
    expect(own.length).toBeGreaterThan(0);
    setViewOpacity(live.map as never, 0.2);
    for (const id of own) expect(opacityOf(live, id)).toBe(0.8);
  });
});
