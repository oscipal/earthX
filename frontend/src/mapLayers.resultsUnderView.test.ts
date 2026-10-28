// Otto, 27.10.2026 (zu #211): the view of the chosen scenes lies over the quicklooks of the search results, and the
// outlines of the results stay over both. Whichever of the two is drawn first, and after a style load has laid the
// map's own layers again.

import { describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import type { LayerOverlay } from './layers';
import { ensureBaseLayers, syncBrowseMosaic, syncFocusRaster, syncLayers, syncPreview, syncResultsOverlay } from './mapLayers';
import { liveMap, lyr, pinned } from './fixtures/liveMap';
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

// Otto, 27.10.2026: "ein angeklicktes Search Result ist immer der oberste Layer". The quicklook of a ticked scene lies
// over the view, over the other quicklooks and over the pinned layers, whichever was drawn first.
describe('the quicklook of a ticked search result is the top layer', () => {
  const ticked = ['S1'];
  const tickedResults = (live: Live) => syncResultsOverlay(live.map as never, { items: [scene('S1'), scene('S2')], selectedIds: ticked, dataset: dataset() });
  const rasters = (live: Live) => live.stack.filter((id) => /^(m|n|res|preview)-.*(lyr)/u.test(id) || id.startsWith('preview-lyr'));

  function expectTickedOnTop(live: Live, tickedLayer: string) {
    const others = rasters(live).filter((id) => id !== tickedLayer);
    expect(others.length).toBeGreaterThan(0);
    expect(index(live, tickedLayer)).toBeGreaterThan(Math.max(...others.map((id) => index(live, id))));
    expect(index(live, tickedLayer)).toBeLessThan(index(live, 'aoi-fill'));
    expect(index(live, tickedLayer)).toBeLessThan(index(live, 'mosaicsel-line'));
    expect(index(live, tickedLayer)).toBeGreaterThan(index(live, 'layers-top'));
  }

  it.each([
    ['the view first', (live: Live) => { view(live); tickedResults(live); }],
    ['the results first', (live: Live) => { tickedResults(live); view(live); }],
    ['the view again after the results', (live: Live) => { tickedResults(live); view(live); view(live); tickedResults(live); view(live); }],
  ])('over the view and the unticked quicklook, with %s', (_name, draw) => {
    const live = freshMap();
    draw(live);
    // S1 is ticked, S2 is not: S2 stays under the view.
    expectTickedOnTop(live, 'res-tiles-lyr-0');
    expect(index(live, 'res-tiles-lyr-1')).toBeLessThan(Math.min(...viewLayers(live).map((id) => index(live, id))));
  });

  it('after a style load, which lays everything again', () => {
    const next = freshMap();
    view(next);
    tickedResults(next);
    expectTickedOnTop(next, 'res-tiles-lyr-0');
  });

  it('over the other quicklooks while browsing, whichever of them is drawn first', () => {
    const live = freshMap();
    // The ticked scene comes second, so it is drawn after S1's quicklook: it must still end up over it.
    syncBrowseMosaic(live.map as never, { items: [scene('S2'), scene('S1')], selectedIds: ticked, dataset: dataset() });
    expect(live.stack.filter((id) => id.startsWith('m-tiles-lyr-'))).toHaveLength(2);
    expectTickedOnTop(live, 'm-tiles-lyr-1');
  });

  it('over the other quicklooks while browsing when the ticked scene is the first of the list', () => {
    const live = freshMap();
    syncBrowseMosaic(live.map as never, { items: [scene('S1'), scene('S2')], selectedIds: ticked, dataset: dataset() });
    expectTickedOnTop(live, 'm-tiles-lyr-0');
  });

  it('is no different from the others when nothing is ticked: under the view', () => {
    const live = freshMap();
    view(live);
    syncResultsOverlay(live.map as never, { items: [scene('S1'), scene('S2')], selectedIds: [], dataset: dataset() });
    expectOrder(live);
  });

  it('is gone with the results, and leaves the marker for the next', () => {
    const live = freshMap();
    tickedResults(live);
    syncResultsOverlay(live.map as never, { items: [], selectedIds: [], dataset: dataset() });
    expect(resultLayers(live)).toEqual([]);
    expect(live.stack.filter((id) => id === 'ticked-top')).toHaveLength(1);
  });
});

// Otto, 28.10.2026 (zu #221, supplement to UI-02 8.10): from the top, the AOI and the drawing, the overlays, the live
// preview of the processing panel (while the panel is open), the quicklooks of the ticked scenes, then the view, the
// results and the pinned layers. A pinned preview is a layer of the manager and lies under the ticked quicklook.
describe('the live preview of the processing panel', () => {
  const ticked = ['S1'];
  const tickedResults = (live: Live) => syncResultsOverlay(live.map as never, { items: [scene('S1'), scene('S2')], selectedIds: ticked, dataset: dataset() });
  const previewOverlays = (n = 2): LayerOverlay[] =>
    Array.from({ length: n }, (_, i) => ({
      kind: 'raster' as const,
      tileUrl: `/collections/optical/items/S${i}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual&op=band_math`,
      bounds: [10, 47, 11, 48] as [number, number, number, number],
      minZoom: 8,
      maxZoom: 14,
      preview: true as const,
    }));
  const live_ = (live: Live) => syncPreview(live.map as never, previewOverlays());
  const previewLayers = (live: Live) => live.stack.filter((id) => id.startsWith('preview-lyr-'));

  function expectOrder(live: Live) {
    const previews = previewLayers(live);
    expect(previews.length).toBeGreaterThan(0);
    const lowest = Math.min(...previews.map((id) => index(live, id)));
    const highest = Math.max(...previews.map((id) => index(live, id)));
    // Over the ticked quicklook, over the view and the unticked quicklook, under the AOI and the outlines.
    expect(index(live, 'res-tiles-lyr-0')).toBeLessThan(lowest);
    expect(index(live, 'ticked-top')).toBeLessThan(index(live, 'res-tiles-lyr-0'));
    expect(index(live, 'preview-base')).toBeGreaterThan(index(live, 'res-tiles-lyr-0'));
    expect(index(live, 'preview-base')).toBeLessThan(lowest);
    expect(Math.max(...viewLayers(live).map((id) => index(live, id)))).toBeLessThan(lowest);
    expect(index(live, 'res-tiles-lyr-1')).toBeLessThan(lowest);
    expect(highest).toBeLessThan(index(live, 'aoi-fill'));
    expect(highest).toBeLessThan(index(live, 'mosaicsel-line'));
  }

  it.each([
    ['the preview first', (live: Live) => { live_(live); view(live); tickedResults(live); }],
    ['the preview last', (live: Live) => { view(live); tickedResults(live); live_(live); }],
    ['the preview between', (live: Live) => { tickedResults(live); live_(live); view(live); }],
    ['everything drawn again, the ticked quicklook after the preview', (live: Live) => {
      live_(live);
      view(live);
      tickedResults(live);
      live_(live);
      view(live);
      tickedResults(live);
    }],
  ])('lies over the quicklook of a ticked scene, with %s', (_name, draw) => {
    const live = freshMap();
    draw(live);
    expectOrder(live);
  });

  it('after a style load, which lays the map\'s layers again and draws everything as `onStyleLoad` does', () => {
    const live = freshMap();
    live_(live);
    view(live);
    tickedResults(live);
    const next = freshMap();
    view(next);
    tickedResults(next);
    live_(next);
    expectOrder(next);
  });

  it('lies over the quicklook of a ticked scene that is browsed, which arrives after the preview', () => {
    const live = freshMap();
    live_(live);
    syncBrowseMosaic(live.map as never, { items: [scene('S2'), scene('S1')], selectedIds: ticked, dataset: dataset() });
    const tickedLayer = index(live, 'm-tiles-lyr-1');
    expect(tickedLayer).toBeLessThan(Math.min(...previewLayers(live).map((id) => index(live, id))));
    expect(index(live, 'm-tiles-lyr-0')).toBeLessThan(tickedLayer);
    expect(Math.max(...previewLayers(live).map((id) => index(live, id)))).toBeLessThan(index(live, 'aoi-fill'));
  });

  it('lies under the overlays, once their marker is on the map, and under the AOI', () => {
    const live = freshMap();
    live.map.addLayer({ id: 'overlays-base' }, 'aoi-fill');
    live.map.addLayer({ id: 'labels' }, 'aoi-fill');
    live_(live);
    tickedResults(live);
    const highest = Math.max(...previewLayers(live).map((id) => index(live, id)));
    expect(highest).toBeLessThan(index(live, 'overlays-base'));
    expect(index(live, 'overlays-base')).toBeLessThan(index(live, 'labels'));
    expect(index(live, 'labels')).toBeLessThan(index(live, 'aoi-fill'));
    expect(index(live, 'res-tiles-lyr-0')).toBeLessThan(Math.min(...previewLayers(live).map((id) => index(live, id))));
  });

  it('keeps its two layers in the order of the scenes: the first on top', () => {
    const live = freshMap();
    live_(live);
    const urls = previewLayers(live).map((id) => (live.sources.get(live.layers.get(id)!.source!) as { tiles: string[] }).tiles[0]);
    expect(urls[0]).toContain('/items/S1/');
    expect(urls[1]).toContain('/items/S0/');
  });

  it('is gone with the panel and leaves the markers', () => {
    const live = freshMap();
    live_(live);
    tickedResults(live);
    syncPreview(live.map as never, []);
    expect(previewLayers(live)).toEqual([]);
    expect(live.stack.filter((id) => id === 'preview-base' || id === 'ticked-top')).toHaveLength(2);
    expect(index(live, 'res-tiles-lyr-0')).toBeLessThan(index(live, 'preview-base'));
  });

  it('does not push the view, the results or a new quicklook over a preview that is on the map', () => {
    const live = freshMap();
    live_(live);
    view(live);
    results(live);
    syncBrowseMosaic(live.map as never, { items: [scene('S3')], dataset: dataset() });
    const lowest = Math.min(...previewLayers(live).map((id) => index(live, id)));
    for (const id of [...viewLayers(live), ...resultLayers(live), ...live.stack.filter((layer) => layer.startsWith('m-tiles-lyr-'))]) {
      expect(index(live, id)).toBeLessThan(lowest);
    }
  });

  describe('a preview pinned to the layer manager', () => {
    const pin = (live: Live) =>
      syncLayers(live.map as never, [pinned('P', '/collections/optical/items/S1/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual&op=band_math', { derived: 'preview' })]);

    it.each([
      ['pinned first', (live: Live) => { pin(live); tickedResults(live); }],
      ['pinned last', (live: Live) => { tickedResults(live); pin(live); }],
    ])('lies under the quicklook of a ticked scene, %s', (_name, draw) => {
      const live = freshMap();
      draw(live);
      expect(index(live, lyr('P'))).toBeLessThan(index(live, 'ticked-top'));
      expect(index(live, lyr('P'))).toBeLessThan(index(live, 'res-tiles-lyr-0'));
    });

    it('lies under the live preview and under the view too', () => {
      const live = freshMap();
      live_(live);
      view(live);
      pin(live);
      expect(index(live, lyr('P'))).toBeLessThan(Math.min(...viewLayers(live).map((id) => index(live, id))));
      expect(index(live, lyr('P'))).toBeLessThan(Math.min(...previewLayers(live).map((id) => index(live, id))));
    });
  });
});
