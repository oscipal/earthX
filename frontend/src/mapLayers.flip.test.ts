// NM4-65 part 9 (Otto, 31.10.2026, "Durchblättern der Layer"): with "Flip through layers" on, the chosen layer is drawn over
// every other picture of the app — the layers, the view, the results and the live preview — and under the AOI, the drawing
// and the outlines of the results; the order of the list is not touched, and a move reloads no tile. Off, the map shows the
// real order again.

import { describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import { liveMap, lyr, pinned } from './fixtures/liveMap';
import { ensureBaseLayers, syncFocusRaster, syncLayers, syncResultsOverlay } from './mapLayers';
import type { MapLayer } from './layers';
import type { DownloadedInfo, StacItem } from './types';

type Live = ReturnType<typeof liveMap>;

const dataset = () =>
  datasetsFrom([
    {
      id: 'optical',
      title: 'Optical',
      'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
      'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'preview_tiles', quicklook_nodata_max: null, results_group_by: ['datetime'] },
      'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]] as [number, number][], colormap_name: null, expression: null, resampling: 'nearest' },
    },
  ] as never)[0];
const scene = (id: string): StacItem => ({ id, bbox: [10, 47, 11, 48], properties: { datetime: '2026-07-24T10:00:00Z' }, assets: {} });
const tile = (id: string): DownloadedInfo => ({
  datasetId: 'optical', tileUrl: `/collections/optical/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`, bounds: [10, 47, 11, 48], asset: 'visual', minZoom: 8, maxZoom: 14,
});

function freshMap(): Live {
  const live = liveMap([]);
  ensureBaseLayers(live.map as never);
  return live;
}

const at = (live: Live, id: string) => live.stack.indexOf(id);
const layer = (id: string, over: Partial<MapLayer> = {}) => pinned(id, `https://t/${id}/{z}/{x}/{y}`, over);
const list = () => ['a', 'b', 'c', 'd'].map((id) => layer(id));
const resultLayers = (live: Live) => live.stack.filter((id) => id.startsWith('res-'));
const pinnedBottomToTop = (live: Live) => live.pinnedOrder().map((id) => id.replace(/^layer-lyr-|-\d+$/gu, ''));

describe('"Flip through layers" on the map', () => {
  it('draws the chosen layer over all the others and leaves the list as it is', () => {
    const live = freshMap();
    const layers = list();
    syncLayers(live.map as never, layers, 0, null);
    // The list has "a" on top: the map draws it last.
    expect(pinnedBottomToTop(live)).toEqual(['d', 'c', 'b', 'a']);
    syncLayers(live.map as never, layers, 0, 'c');
    expect(pinnedBottomToTop(live)).toEqual(['d', 'b', 'a', 'c']);
    expect(layers.map((l) => l.id)).toEqual(['a', 'b', 'c', 'd']);
  });

  it('draws the real order again when it is off', () => {
    const live = freshMap();
    const layers = list();
    syncLayers(live.map as never, layers, 0, 'd');
    expect(pinnedBottomToTop(live)).toEqual(['c', 'b', 'a', 'd']);
    syncLayers(live.map as never, layers, 0, null);
    expect(pinnedBottomToTop(live)).toEqual(['d', 'c', 'b', 'a']);
  });

  it('moves the chosen layer from one to the next without loading a tile again', () => {
    const live = freshMap();
    const layers = list();
    syncLayers(live.map as never, layers, 0, 'a');
    const added = [...live.log.sourcesAdded];
    const removed = [...live.log.sourcesRemoved];
    for (const id of ['b', 'c', 'd', 'a', null]) syncLayers(live.map as never, layers, 0, id);
    expect(live.log.sourcesAdded).toEqual(added);
    expect(live.log.sourcesRemoved).toEqual(removed);
  });

  it('draws every picture of a layer of several images on top, in their own order', () => {
    const live = freshMap();
    const many = layer('m', { overlays: [0, 1, 2].map((n) => ({ kind: 'raster' as const, tileUrl: `https://t/m/${n}`, bounds: [10, 47, 11, 48] as [number, number, number, number], minZoom: 8, maxZoom: 14 })) });
    const layers = [layer('a'), many, layer('z')];
    syncLayers(live.map as never, layers, 0, 'm');
    const ids = live.pinnedOrder();
    expect(ids.slice(-3)).toEqual([lyr('m', 0), lyr('m', 1), lyr('m', 2)]);
    expect(ids.slice(0, 2).every((id) => !id.includes('-m-'))).toBe(true);
  });

  it('keeps the eye: a layer that is switched off is drawn nowhere, flipped or not', () => {
    const live = freshMap();
    const layers = [layer('a'), layer('b', { visible: false }), layer('c')];
    syncLayers(live.map as never, layers, 0, 'b');
    expect(live.visible(lyr('b'))).toBe(false);
    expect(live.visible(lyr('a'))).toBe(true);
    expect(pinnedBottomToTop(live)[2]).toBe('b');
  });

  it('keeps a layer whose results are gone out of the map, flipped or not', () => {
    const live = freshMap();
    const expired = layer('x', { derived: 'result', result: { jobID: 'J', expires: '2026-01-01T00:00:00Z', gsd: null, resampled: null, expired: true, dataType: null, stats: null } });
    syncLayers(live.map as never, [layer('a'), expired], 0, 'x');
    expect(live.layers.has(lyr('x'))).toBe(false);
    expect(pinnedBottomToTop(live)).toEqual(['a']);
  });

  it('draws it over the layers above "Results" too, and over the view and the results', () => {
    const live = freshMap();
    syncFocusRaster(live.map as never, { downloaded: { S1: tile('S1') }, render: {}, showDownloaded: true, items: [scene('S1')], dataset: dataset(), tilesInLayer: false });
    syncResultsOverlay(live.map as never, { items: [scene('S1'), scene('S2')], dataset: dataset() });
    const layers = [layer('a'), layer('b'), layer('c')];
    // "Results" under the first layer of the list: "a" lies over it, "b" and "c" under.
    syncLayers(live.map as never, layers, 1, null);
    expect(resultLayers(live).length).toBeGreaterThan(0);
    expect(at(live, lyr('c'))).toBeLessThan(Math.min(...resultLayers(live).map((id) => at(live, id))));
    syncLayers(live.map as never, layers, 1, 'c');
    const everything = live.stack.filter((id) => id.startsWith('layer-lyr-') || id.startsWith('res-') || /^[mn]-tiles-lyr-/u.test(id));
    expect(everything[everything.length - 1]).toBe(lyr('c'));
  });

  it('keeps the AOI, the drawing and the outlines of the results over it', () => {
    const live = freshMap();
    syncResultsOverlay(live.map as never, { items: [scene('S1')], dataset: dataset() });
    syncLayers(live.map as never, list(), 0, 'b');
    const flipped = at(live, lyr('b'));
    expect(flipped).toBeLessThan(at(live, 'mosaicsel-line'));
    expect(flipped).toBeLessThan(at(live, 'overlays-base'));
    expect(flipped).toBeLessThan(at(live, 'aoi-fill'));
    expect(resultLayers(live).length).toBeGreaterThan(0);
    expect(flipped).toBeGreaterThan(Math.max(...resultLayers(live).map((id) => at(live, id))));
  });

  it('ignores a layer that is not in the list, and changes nothing without one', () => {
    const live = freshMap();
    const layers = list();
    syncLayers(live.map as never, layers, 0, 'gone');
    expect(pinnedBottomToTop(live)).toEqual(['d', 'c', 'b', 'a']);
  });
});
