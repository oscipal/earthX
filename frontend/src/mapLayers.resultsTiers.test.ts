// NM4-59 (Otto, 30.10.2026, replaces the order of 27.10.2026, zu #211): within "Results" the view is the bottom tier, the
// quicklooks of the search results lie over it and the outlines of the results over both. Whichever of the two is drawn
// first, and after a style load has laid the map's own layers again.

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
  // The results over the view, both under the outlines of the selection.
  expect(bottom(viewLayers(live))).toBeLessThan(top(resultLayers(live)));
  expect(bottom(resultLayers(live))).toBeLessThan(index(live, 'mosaicsel-line'));
}

describe('the quicklooks of the results and the view', () => {
  it('puts the results over the view when the view is drawn first', () => {
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

// Otto, 27.10.2026: "ein angeklicktes Search Result ist immer der oberste Layer", within "Results" since NM4-59: the quicklook
// of a ticked scene of the open group lies over the view and over the other quicklooks, whichever was drawn first.
describe('the quicklook of a ticked search result is the top picture of the results', () => {
  const ticked = ['S1'];
  const tickedResults = (live: Live) => syncResultsOverlay(live.map as never, { items: [scene('S1'), scene('S2')], selectedIds: ticked, dataset: dataset() });
  const rasters = (live: Live) => live.stack.filter((id) => /^(m|n|res|preview)-.*(lyr)/u.test(id) || id.startsWith('preview-lyr'));

  function expectTickedOnTop(live: Live, tickedLayer: string) {
    const others = rasters(live).filter((id) => id !== tickedLayer);
    expect(others.length).toBeGreaterThan(0);
    expect(index(live, tickedLayer)).toBeGreaterThan(Math.max(...others.map((id) => index(live, id))));
    // Under the marker of the overlays (UI-02b): names and graticule stay over the quicklook of a ticked scene.
    expect(index(live, tickedLayer)).toBeLessThan(index(live, 'overlays-base'));
    expect(index(live, 'overlays-base')).toBeLessThan(index(live, 'aoi-fill'));
    expect(index(live, tickedLayer)).toBeLessThan(index(live, 'aoi-fill'));
    expect(index(live, tickedLayer)).toBeLessThan(index(live, 'mosaicsel-line'));
  }

  it.each([
    ['the view first', (live: Live) => { view(live); tickedResults(live); }],
    ['the results first', (live: Live) => { tickedResults(live); view(live); }],
    ['the view again after the results', (live: Live) => { tickedResults(live); view(live); view(live); tickedResults(live); view(live); }],
  ])('over the view and the unticked quicklook, with %s', (_name, draw) => {
    const live = freshMap();
    draw(live);
    // S1 is ticked, S2 is not: S2 lies over the view too, under S1.
    expectTickedOnTop(live, 'res-tiles-lyr-0');
    expect(index(live, 'res-tiles-lyr-1')).toBeGreaterThan(Math.max(...viewLayers(live).map((id) => index(live, id))));
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

  it('is no different from the others when nothing is ticked: over the view', () => {
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
    expect(live.stack.filter((id) => id === 'overlays-base')).toHaveLength(1);
  });
});

// Otto, 28.10.2026 (zu #221, supplement to UI-02 8.10): from the top, the AOI and the drawing, the overlays, the live
// preview of the processing panel (while the panel is open), the quicklooks of the ticked scenes, then the other results
// and the view (NM4-59), and the pinned layers. A pinned preview is a layer of the manager and lies under the ticked
// quicklook while "Results" is on top of the list.
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

  it('lies under the overlays (their marker, and the labels between it and the AOI) and under the AOI', () => {
    const live = freshMap();
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

  it('is gone with the panel and leaves the marker', () => {
    const live = freshMap();
    live_(live);
    tickedResults(live);
    syncPreview(live.map as never, []);
    expect(previewLayers(live)).toEqual([]);
    expect(live.stack.filter((id) => id === 'overlays-base')).toHaveLength(1);
    expect(index(live, 'res-tiles-lyr-0')).toBeLessThan(index(live, 'overlays-base'));
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

// Otto, 28.10.2026 (zu #221): the ticked scenes lie over each other in the order they were ticked, the last one on
// top, whatever order the results are listed and drawn in, and after a new style.
describe('the ticked quicklooks lie in the order they were ticked', () => {
  const lists: [string, string[]][] = [
    ['listed S1, S2, S3', ['S1', 'S2', 'S3']],
    ['listed S3, S2, S1', ['S3', 'S2', 'S1']],
    ['listed S2, S3, S1', ['S2', 'S3', 'S1']],
  ];
  const ticks: [string, string[]][] = [
    ['ticked S1, S2, S3', ['S1', 'S2', 'S3']],
    ['ticked S3, S1, S2', ['S3', 'S1', 'S2']],
    ['ticked S2, S3 (S1 not ticked)', ['S2', 'S3']],
  ];
  const overlay = (live: Live, order: string[], selectedIds: string[]) =>
    syncResultsOverlay(live.map as never, { items: order.map(scene), selectedIds, dataset: dataset() });
  const browse = (live: Live, order: string[], selectedIds: string[]) =>
    syncBrowseMosaic(live.map as never, { items: order.map(scene), selectedIds, dataset: dataset() });
  // The layer of a scene: the items are drawn as `res-tiles-lyr-<position in the list>` or `m-tiles-lyr-<…>`.
  const layerOf = (prefix: string, order: string[], id: string) => `${prefix}-tiles-lyr-${order.indexOf(id)}`;

  function expectOrder(live: Live, prefix: string, order: string[], selectedIds: string[]) {
    const stackIndexes = selectedIds.map((id) => index(live, layerOf(prefix, order, id)));
    // Bottom to top in the order of the ticks.
    expect([...stackIndexes].sort((a, b) => a - b)).toEqual(stackIndexes);
    expect(new Set(stackIndexes).size).toBe(selectedIds.length);
    for (const id of order.filter((id) => !selectedIds.includes(id))) {
      expect(index(live, layerOf(prefix, order, id))).toBeLessThan(Math.min(...stackIndexes));
    }
    expect(Math.max(...stackIndexes)).toBeLessThan(index(live, 'aoi-fill'));
  }

  describe.each(lists)('%s', (_l, order) => {
    it.each(ticks)('over a view: %s', (_t, selectedIds) => {
      const live = freshMap();
      view(live);
      overlay(live, order, selectedIds);
      expectOrder(live, 'res', order, selectedIds);
      // And again, as after a new tick, and after a new style, which lays everything again.
      overlay(live, order, selectedIds);
      expectOrder(live, 'res', order, selectedIds);
      const next = freshMap();
      overlay(next, order, selectedIds);
      view(next);
      expectOrder(next, 'res', order, selectedIds);
    });

    it.each(ticks)('while browsing: %s', (_t, selectedIds) => {
      const live = freshMap();
      browse(live, order, selectedIds);
      expectOrder(live, 'm', order, selectedIds);
    });
  });

  it('puts a scene ticked again on top, and the one unticked under none of the others', () => {
    const live = freshMap();
    const order = ['S1', 'S2', 'S3'];
    overlay(live, order, ['S1', 'S2', 'S3']);
    overlay(live, order, ['S2', 'S3', 'S1']);
    expectOrder(live, 'res', order, ['S2', 'S3', 'S1']);
    overlay(live, order, ['S2', 'S1']);
    expectOrder(live, 'res', order, ['S2', 'S1']);
  });

  it('keeps the live preview over all of them', () => {
    const live = freshMap();
    syncPreview(live.map as never, [{ kind: 'raster', tileUrl: '/p/{z}/{x}/{y}', bounds: [10, 47, 11, 48], minZoom: 8, maxZoom: 14, preview: true }]);
    overlay(live, ['S1', 'S2'], ['S2', 'S1']);
    expect(index(live, 'res-tiles-lyr-0')).toBeLessThan(index(live, 'preview-lyr-0'));
    expect(index(live, 'res-tiles-lyr-1')).toBeLessThan(index(live, 'res-tiles-lyr-0'));
  });
});
