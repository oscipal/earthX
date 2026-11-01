import { beforeEach, describe, expect, it } from 'vitest';

import { liveMap, lyr } from './fixtures/liveMap';
import type { MapLayer } from './layers';
import { buildTileUrl, syncFocusRaster, syncLayers } from './mapLayers';
import { useAppStore } from './store';
import type { AppliedRender, DownloadedInfo } from './types';
import { isTemporaryImage, layersForMap, viewLayerOf, viewShown, type ViewState } from './viewLayer';

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 47]]] };

function info(itemId: string): DownloadedInfo {
  return {
    datasetId: 'sentinel-2-c1-l2a', tileUrl: `/collections/c/items/${itemId}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`,
    bounds: [10, 47, 11, 48],
    asset: 'visual',
    minZoom: 0,
    maxZoom: 14,
  };
}

// A layer pinned from the full-resolution view of the scenes `itemIds`.
function pinnedView(id: string, itemIds: string[], render: AppliedRender = { rescale: '0,3000' }, over: Partial<MapLayer> = {}): MapLayer {
  const downloaded = Object.fromEntries(itemIds.map((it) => [it, info(it)]));
  return {
    id,
    name: 'Optical · same name',
    visible: true,
    opacity: 1,
    overlays: Object.values(downloaded).map((d) => ({
      kind: 'raster' as const,
      tileUrl: buildTileUrl(d.tileUrl, render),
      bounds: d.bounds,
      minZoom: d.minZoom,
      maxZoom: d.maxZoom,
    })),
    restore: {
      focusMode: true,
      downloaded,
      appliedRender: render,
      activeGroupIndex: 0,
      selectedIds: itemIds,
      itemIds,
      groupItemIds: [itemIds],
      aoi: null,
      cropToAoi: false,
      datasetId: null,
    },
    ...over,
  };
}

function viewOf(layer: MapLayer, over: Partial<ViewState> = {}): ViewState {
  return {
    viewLayerId: layer.id,
    focusMode: true,
    downloaded: layer.restore.downloaded,
    appliedRender: layer.restore.appliedRender,
    cropToAoi: layer.restore.cropToAoi,
    aoi: layer.restore.aoi,
    showDownloaded: true,
    ...over,
  };
}

describe('viewLayerOf', () => {
  const layer = pinnedView('v', ['s1', 's2']);
  const layers = [pinnedView('other', ['s9']), layer];

  it('is the layer whose scenes the view was filled from', () => {
    expect(viewLayerOf(layers, viewOf(layer))).toBe(layer);
  });

  it('is none outside the full-resolution view, without a chosen layer and for a layer that is gone', () => {
    expect(viewLayerOf(layers, viewOf(layer, { focusMode: false }))).toBeNull();
    expect(viewLayerOf(layers, viewOf(layer, { viewLayerId: null }))).toBeNull();
    expect(viewLayerOf([layers[0]], viewOf(layer))).toBeNull();
  });

  it('is none once the view shows other scenes, more or fewer', () => {
    expect(viewLayerOf(layers, viewOf(layer, { downloaded: { s1: info('s1'), s3: info('s3') } }))).toBeNull();
    expect(viewLayerOf(layers, viewOf(layer, { downloaded: { s1: info('s1') } }))).toBeNull();
    expect(viewLayerOf(layers, viewOf(layer, { downloaded: { ...layer.restore.downloaded, s3: info('s3') } }))).toBeNull();
  });

  it('is none once the stretch or the colormap was applied anew, but not for an equal render', () => {
    expect(viewLayerOf(layers, viewOf(layer, { appliedRender: { rescale: '0,5000' } }))).toBeNull();
    expect(viewLayerOf(layers, viewOf(layer, { appliedRender: { rescale: '0,3000', colormapName: 'viridis' } }))).toBeNull();
    expect(viewLayerOf(layers, viewOf(layer, { appliedRender: { rescale: '0,3000' } }))).toBe(layer);
  });

  it('is none once the view is cropped differently, and follows the AOI only under "Crop to AOI"', () => {
    expect(viewLayerOf(layers, viewOf(layer, { cropToAoi: true, aoi: AOI }))).toBeNull();
    const cropped = pinnedView('c', ['s1']);
    cropped.restore = { ...cropped.restore, cropToAoi: true, aoi: AOI };
    expect(viewLayerOf([cropped], viewOf(cropped))).toBe(cropped);
    expect(viewLayerOf([cropped], viewOf(cropped, { aoi: { ...AOI, coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] } }))).toBeNull();
    // Not cropped: another AOI drawn on the side changes nothing.
    expect(viewLayerOf(layers, viewOf(layer, { aoi: AOI }))).toBe(layer);
  });

  it('is none for a layer that is no full-resolution view (a quicklook, a preview)', () => {
    const quicklook = pinnedView('q', ['s1']);
    quicklook.restore = { ...quicklook.restore, focusMode: false };
    expect(viewLayerOf([quicklook], viewOf(quicklook))).toBeNull();
  });
});

describe('layersForMap and viewShown', () => {
  const a = pinnedView('a', ['s1']);
  const b = pinnedView('b', ['s2']);

  it('leave the list alone while the view is not a layer, or is shown', () => {
    expect(layersForMap([a, b], null, false)).toEqual([a, b]);
    expect(layersForMap([a, b], b, true)).toEqual([a, b]);
  });

  it('switch the layer that is the view off with the view\'s own "Hide image", and only that one', () => {
    const drawn = layersForMap([a, b], b, false);
    expect(drawn.map((l) => l.visible)).toEqual([true, false]);
    expect(drawn.map((l) => l.id)).toEqual(['a', 'b']);
    expect(b.visible).toBe(true);
  });

  it('draw the view itself only when it is shown and its layer, if any, is on', () => {
    expect(viewShown(null, true)).toBe(true);
    expect(viewShown(null, false)).toBe(false);
    expect(viewShown(a, true)).toBe(true);
    expect(viewShown({ ...a, visible: false }, true)).toBe(false);
    expect(viewShown(a, false)).toBe(false);
  });
});

// The full-resolution view of a pinned layer on a map, wired as `MapView` does.
describe('the view of a pinned layer on the map', () => {
  const top = pinnedView('top', ['s1']);
  const middle = pinnedView('middle', ['s2']);
  const bottom = pinnedView('bottom', ['s3']);
  let live: ReturnType<typeof liveMap>;

  function draw() {
    const st = useAppStore.getState();
    const viewLayer = viewLayerOf(st.layers, st);
    syncLayers(live.map as never, layersForMap(st.layers, viewLayer, st.showDownloaded));
    if (st.focusMode) {
      syncFocusRaster(live.map as never, {
        downloaded: st.downloaded,
        render: st.appliedRender,
        showDownloaded: viewShown(viewLayer, st.showDownloaded),
        tilesInLayer: viewLayer !== null,
        aoi: st.aoi,
        cropToAoi: st.cropToAoi,
        items: [],
        dataset: null,
      });
    }
  }
  const viewTiles = () => live.stack.filter((id) => id.startsWith('m-tiles-lyr-'));

  beforeEach(() => {
    live = liveMap();
    useAppStore.setState({
      layers: [top, middle, bottom],
      viewLayerId: null,
      focusMode: false,
      downloaded: {},
      appliedRender: {},
      showDownloaded: true,
      cropToAoi: false,
      aoi: null,
      datasets: [],
    });
    draw();
  });

  it('keeps the list and the stacking order when a layer is chosen by its name', () => {
    const before = live.pinnedOrder();
    useAppStore.getState().selectLayer('middle');
    draw();
    expect(useAppStore.getState().layers.map((l) => l.id)).toEqual(['top', 'middle', 'bottom']);
    expect(live.pinnedOrder()).toEqual(before);
    expect(before).toEqual([lyr('bottom'), lyr('middle'), lyr('top')]);
  });

  it('draws the chosen layer at its place, not above all: no tiles of the view on top', () => {
    useAppStore.getState().selectLayer('middle');
    draw();
    expect(viewTiles()).toEqual([]);
    expect(live.visible(lyr('middle'))).toBe(true);
  });

  it('follows the eye of the layer, also after another layer was chosen in between', () => {
    useAppStore.getState().selectLayer('middle');
    draw();
    useAppStore.getState().toggleLayerVisible('middle');
    draw();
    expect(live.visible(lyr('middle'))).toBe(false);
    expect(viewTiles()).toEqual([]);
    useAppStore.getState().selectLayer('bottom');
    draw();
    expect(live.visible(lyr('middle'))).toBe(false); // its own eye still decides
    useAppStore.getState().toggleLayerVisible('middle');
    draw();
    expect(live.visible(lyr('middle'))).toBe(true);
  });

  it('follows the eye of the view too: "Hide image" hides the layer that is the view, nothing else', () => {
    useAppStore.getState().selectLayer('middle');
    useAppStore.getState().toggleDownloaded();
    draw();
    expect([lyr('top'), lyr('middle'), lyr('bottom')].map(live.visible)).toEqual([true, false, true]);
    useAppStore.getState().toggleDownloaded();
    draw();
    expect(live.visible(lyr('middle'))).toBe(true);
  });

  it('follows the order when the layer is moved while it is the view', () => {
    useAppStore.getState().selectLayer('middle');
    useAppStore.getState().moveLayer('middle', 'up');
    draw();
    expect(live.pinnedOrder()).toEqual([lyr('bottom'), lyr('top'), lyr('middle')]);
    expect(viewTiles()).toEqual([]);
  });

  it('is its own picture above the layers once the view is changed', () => {
    useAppStore.getState().selectLayer('middle');
    draw();
    useAppStore.setState({ appliedRender: { rescale: '0,9000' } });
    draw();
    expect(viewTiles()).toEqual(['m-tiles-lyr-0']);
    const top = Math.max(...live.pinnedOrder().map((id) => live.stack.indexOf(id)));
    expect(live.stack.indexOf('m-tiles-lyr-0')).toBeGreaterThan(top);
    expect(live.visible(lyr('middle'))).toBe(true); // the pinned copy stays as it was
  });

  it('is not a layer any more after the full-resolution view is left', () => {
    useAppStore.getState().selectLayer('middle');
    useAppStore.getState().exitFocus();
    expect(useAppStore.getState().viewLayerId).toBeNull();
  });
});


// Otto, 1.11.2026 (zu #272): the mark "Temporary" of the view of the search.
describe('an image that is temporary', () => {
  const image = (ids: string[]) => ({ ids, datasetId: 'sentinel-2-c1-l2a' });
  const RENDER: AppliedRender = { rescale: '0,3000' };
  const view = { cropToAoi: false, aoi: null as GeoJSON.Geometry | null };
  // A layer pinned from the view of the dataset (`datasetId` is what ties it to its images).
  const pinned = (id: string, ids: string[], render: AppliedRender) => {
    const layer = pinnedView(id, ids, render);
    return { ...layer, restore: { ...layer.restore, datasetId: 'sentinel-2-c1-l2a' } };
  };

  it('is so while no layer holds it', () => {
    expect(isTemporaryImage([], image(['a']), RENDER, view)).toBe(true);
  });

  it('is not once "Add to layers" pinned it as it looks, and is again as soon as its look changes', () => {
    const layers = [pinned('L1', ['a'], RENDER)];
    expect(isTemporaryImage(layers, image(['a']), RENDER, view)).toBe(false);
    expect(isTemporaryImage(layers, image(['a']), { rescale: '0,2000' }, view)).toBe(true);
    expect(isTemporaryImage(layers, image(['a']), { ...RENDER, colormapName: 'magma' }, view)).toBe(true);
    expect(isTemporaryImage(layers, image(['a']), { ...RENDER, band: 'B04' }, view)).toBe(true);
  });

  it('is so again for other scenes, another dataset or another crop of the same image', () => {
    const layers = [pinned('L1', ['a', 'b'], RENDER)];
    expect(isTemporaryImage(layers, image(['a', 'b']), RENDER, view)).toBe(false);
    expect(isTemporaryImage(layers, image(['a']), RENDER, view)).toBe(true);
    expect(isTemporaryImage(layers, image(['a', 'b', 'c']), RENDER, view)).toBe(true);
    expect(isTemporaryImage(layers, { ids: ['a', 'b'], datasetId: 'dem' }, RENDER, view)).toBe(true);
    expect(isTemporaryImage(layers, image(['a', 'b']), RENDER, { cropToAoi: true, aoi: AOI })).toBe(true);
  });

  it('is not for any image "Add all to layers" pinned, so that a step that was not changed shows no mark, and is for one it did not pin', () => {
    const layers = [pinned('L2', ['b'], RENDER), pinned('L1', ['a'], RENDER)];
    expect(isTemporaryImage(layers, image(['a']), RENDER, view)).toBe(false);
    expect(isTemporaryImage(layers, image(['b']), RENDER, view)).toBe(false);
    expect(isTemporaryImage(layers, image(['c']), RENDER, view)).toBe(true);
    // The step changed after it was pinned: the mark is back on that step only.
    expect(isTemporaryImage(layers, image(['b']), { rescale: '0,100' }, view)).toBe(true);
    expect(isTemporaryImage(layers, image(['a']), RENDER, view)).toBe(false);
  });

  it('does not count a layer that is no view of scenes (a result, a preview)', () => {
    const result = { ...pinned('R', ['a'], RENDER), derived: 'result' as const };
    expect(isTemporaryImage([result], image(['a']), RENDER, view)).toBe(true);
  });
});
