// Otto, 27.10.2026 (zu #211): the view of the chosen scenes lies over the quicklooks of the search results, and the
// outlines of the results stay over both. Whichever of the two is drawn first, and after a style load has laid the
// map's own layers again.

import { describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import { ensureBaseLayers, syncBrowseMosaic, syncFocusRaster, syncResultsOverlay } from './mapLayers';
import { liveMap } from './fixtures/liveMap';
import type { DownloadedInfo, StacItem } from './types';

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
  tileUrl: `/collections/optical/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`,
  bounds: [10, 47, 11, 48],
  asset: 'visual',
  minZoom: 8,
  maxZoom: 14,
});

type Live = ReturnType<typeof liveMap>;

const view = (live: Live) =>
  syncFocusRaster(live.map as never, { downloaded: { S1: tile('S1') }, render: {}, showDownloaded: true, items: [scene('S1')], dataset: dataset(), tilesInLayer: false });
const results = (live: Live, items = [scene('S1'), scene('S2')]) => syncResultsOverlay(live.map as never, { items, dataset: dataset() });

const index = (live: Live, id: string) => live.stack.indexOf(id);
const viewLayers = (live: Live) => live.stack.filter((id) => /^[mn]-tiles-lyr-/u.test(id));
const resultLayers = (live: Live) => live.stack.filter((id) => id.startsWith('res-'));

// The map as a style load leaves it: the app's own layers, laid by `ensureBaseLayers`, nothing of the search yet.
function freshMap(): Live {
  const live = liveMap([]);
  ensureBaseLayers(live.map as never);
  return live;
}

function expectOrder(live: Live) {
  expect(viewLayers(live).length).toBeGreaterThan(0);
  expect(resultLayers(live)).toHaveLength(2);
  const top = (ids: string[]) => Math.min(...ids.map((id) => index(live, id)));
  const bottom = (ids: string[]) => Math.max(...ids.map((id) => index(live, id)));
  // The results under the view, both over the layers of the manager and under the outlines of the selection.
  expect(bottom(resultLayers(live))).toBeLessThan(top(viewLayers(live)));
  expect(index(live, 'layers-top')).toBeLessThan(top(resultLayers(live)));
  expect(bottom(viewLayers(live))).toBeLessThan(index(live, 'mosaicsel-line'));
}

describe('the quicklooks of the results and the view', () => {
  it('puts the results under the view when the view is drawn first', () => {
    const live = freshMap();
    view(live);
    results(live);
    expectOrder(live);
  });

  it('and when the results are drawn first', () => {
    const live = freshMap();
    results(live);
    view(live);
    expectOrder(live);
  });

  it('and every time either is drawn again', () => {
    const live = freshMap();
    results(live);
    view(live);
    for (let i = 0; i < 3; i++) {
      results(live);
      view(live);
    }
    results(live);
    expectOrder(live);
  });

  it('and after a style load, which lays the map\'s layers again and draws the view and the results as `onStyleLoad` does', () => {
    const live = freshMap();
    view(live);
    results(live);
    // The next map: nothing but what `ensureBaseLayers` lays.
    const next = freshMap();
    view(next);
    results(next);
    expectOrder(next);
  });

  it('keeps the outlines of the selection over the quicklooks too', () => {
    const live = freshMap();
    results(live);
    expect(Math.max(...resultLayers(live).map((id) => index(live, id)))).toBeLessThan(index(live, 'mosaicsel-line'));
  });

  it('leaves no result layer behind when the results are gone', () => {
    const live = freshMap();
    view(live);
    results(live);
    results(live, []);
    expect(resultLayers(live)).toEqual([]);
    expect(viewLayers(live).length).toBeGreaterThan(0);
  });

  it('browsing is not touched: the quicklooks of browsing lie where they did, under the outlines', () => {
    const live = freshMap();
    syncBrowseMosaic(live.map as never, { items: [scene('S1')], dataset: dataset() });
    expect(live.stack.filter((id) => id.startsWith('m-tiles-lyr-')).length).toBe(1);
    expect(index(live, 'm-tiles-lyr-0')).toBeLessThan(index(live, 'mosaicsel-line'));
  });
});
