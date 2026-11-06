// UI-01a (Otto, 25.10.2026): a picture never leaves the map while the user zooms or switches the view. Each kind of
// layer is swept over every half zoom level in and out, and the view's redraws keep the picture they replace until the
// new one has loaded. The tiles that load late are the ones the map has not called idle for (`fixtures/zoomMap.ts`).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { LayerOverlay } from './layers';
import { syncBrowseMosaic, syncFocusRaster, syncLayers } from './mapLayers';
import { pinned } from './fixtures/liveMap';
import { FakeImage, previewDataset, previewScene, quicklookDataset, quicklookScene, sceneInfo } from './fixtures/viewScenes';
import { zoomMap } from './fixtures/zoomMap';
import type { Mosaics, SceneEntry } from './mosaic';
import { overlaysOfPass, underlaysOf } from './searchLayers';
import type { TimeStepGroup } from './types';
import { zoomInTo } from './zoomHint';

beforeEach(() => {
  FakeImage.all = [];
  FakeImage.instant = true;
  vi.stubGlobal('Image', FakeImage);
  vi.stubGlobal('document', { createElement: () => ({ getContext: () => null }) });
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const raster = (minZoom: number, maxZoom: number, over: Partial<Extract<LayerOverlay, { kind: 'raster' }>> = {}): LayerOverlay => ({
  kind: 'raster',
  tileUrl: `https://t/${minZoom}-${maxZoom}/{z}/{x}/{y}`,
  bounds: [10, 47, 11, 48],
  minZoom,
  maxZoom,
  ...over,
});

function expectEveryZoom(overlays: LayerOverlay[], id = 'layer') {
  const map = zoomMap();
  syncLayers(map.map as never, [pinned(id, 'unused', { overlays })]);
  for (const zoom of map.sweep()) expect(map.picturesAt(zoom), `zoom ${zoom}`).not.toHaveLength(0);
  return map;
}

describe('a layer pinned from a scene with a quicklook, whose tiles start at z8', () => {
  const item = quicklookScene('Z1');
  const entries: SceneEntry[] = [[item.id, sceneInfo(item, 8, 19)]];
  const overlays = () =>
    overlaysOfPass('quicklook-source', entries, undefined, {}, null, underlaysOf(entries, [item], quicklookDataset(8), null)) ?? [];

  it('holds the quicklook under its tiles', () => {
    expect(overlays().map((o) => o.kind)).toEqual(['image', 'raster']);
    expect(overlays()[0]).toMatchObject({ kind: 'image', url: 'https://example.invalid/Z1.jpg' });
  });

  it('is on the map at every zoom, in and out', () => {
    expectEveryZoom(overlays());
  });

  it('shows its quicklook exactly once where the tiles are not asked for yet, and under them from there on', () => {
    const map = expectEveryZoom(overlays(), 'scene');
    expect(map.picturesAt(3)).toEqual(['layer-lyr-scene-0']);
    // From level 8 minus 1.5 the tiles are asked for; the quicklook stays under them while they load, whatever the zoom.
    expect(map.picturesAt(7)).toEqual(['layer-lyr-scene-0', 'layer-lyr-scene-1']);
    expect(map.picturesAt(10)).toEqual(['layer-lyr-scene-0', 'layer-lyr-scene-1']);
  });

  it('keeps the opacity of the layer in the quicklook', () => {
    const map = zoomMap();
    syncLayers(map.map as never, [pinned('scene', 'unused', { overlays: overlays(), opacity: 0.4 })]);
    expect(map.layers.get('layer-lyr-scene-0')?.paint['raster-opacity']).toBe(0.4);
    syncLayers(map.map as never, [pinned('scene', 'unused', { overlays: overlays(), opacity: 0.9 })]);
    expect(map.layers.get('layer-lyr-scene-0')?.paint['raster-opacity']).toBe(0.9);
  });

  it('has no quicklook where the tiles start at z0, or the dataset shows none', () => {
    expect(underlaysOf(entries, [item], quicklookDataset(0), null)).toEqual([]);
    expect(underlaysOf(entries, [item], previewDataset(), null)).toEqual([]);
    expect(underlaysOf(entries, [{ ...item, assets: {} }], quicklookDataset(8), null)).toEqual([]);
  });
});

describe('a layer pinned from a time step of several scenes (mosaic)', () => {
  it('is on the map at every zoom where single scenes stand under the mosaic, released below z8', () => {
    // The mosaic is 512 px (asked for from zoom 7.5), the scenes under it 256 px.
    expectEveryZoom([raster(0, 7, { hideFrom: 7.5 }), raster(8, 19, { tileUrl: 'https://t/8-19/{z}/{x}/{y}?tilesize=512' })]);
  });

  it('says from which zoom it is drawn where the dataset is released from z8 only', () => {
    const overlays = [raster(8, 14)];
    const map = zoomMap();
    syncLayers(map.map as never, [pinned('zarr', 'unused', { overlays })]);
    expect(map.picturesAt(3)).toEqual([]);
    expect(zoomInTo(overlays, 3)).toBe(7);
    expect(map.picturesAt(7)).not.toEqual([]);
    expect(zoomInTo(overlays, 7)).toBeNull();
  });
});

describe('a pinned preview and the result of a job', () => {
  it('a preview of a dataset released from z0 is on the map at every zoom', () => {
    expectEveryZoom([raster(0, 13, { preview: true })]);
  });

  it('a preview of a dataset released from z8 says where it is drawn from', () => {
    expect(zoomInTo([raster(8, 13, { preview: true })], 4)).toBe(7);
  });

  it('the result, as the tiler names its levels, is on the map at every zoom', () => {
    expectEveryZoom([raster(0, 19)]);
  });
});

describe('the view hands over to its next picture', () => {
  const item = previewScene('H1');
  const dataset = previewDataset();
  const downloaded = { H1: sceneInfo(item, 8, 14) };
  const browse = (map: ReturnType<typeof zoomMap>) => syncBrowseMosaic(map.map as never, { items: [item], dataset });
  const full = (map: ReturnType<typeof zoomMap>, over: Partial<Parameters<typeof syncFocusRaster>[1]> = {}) =>
    syncFocusRaster(map.map as never, { downloaded, render: {}, showDownloaded: true, items: [item], dataset, ...over });
  const dynamic = (map: ReturnType<typeof zoomMap>) => [...map.layers.keys()].filter((id) => /^[mn]-/.test(id)).sort();

  it('keeps the quicklook on the map, under the full resolution, until the tiles have loaded', () => {
    const map = zoomMap();
    browse(map);
    map.idle();
    full(map);
    expect(dynamic(map)).toEqual(['m-tiles-lyr-0', 'n-tiles-lyr-0']);
    expect(map.picturesAt(9)).toContain('m-tiles-lyr-0');
    map.idle();
    expect(dynamic(map)).toEqual(['n-tiles-lyr-0']);
  });

  it('keeps the full resolution under the quicklook it goes back to', () => {
    const map = zoomMap();
    full(map);
    map.idle();
    browse(map);
    expect(dynamic(map)).toEqual(['m-tiles-lyr-0', 'n-tiles-lyr-0']);
    map.idle();
    expect(dynamic(map)).toEqual(['n-tiles-lyr-0']);
    full(map);
    map.idle();
    expect(dynamic(map)).toEqual(['m-tiles-lyr-0']);
  });

  it('waits for a quicklook that is still on its way, not only for the tiles', () => {
    FakeImage.instant = false;
    const ql = quicklookDataset(8);
    const scene = quicklookScene('H3');
    const aoi: GeoJSON.Geometry = { type: 'Polygon', coordinates: [[[9.1, 47.1], [9.4, 47.1], [9.4, 47.5], [9.1, 47.5], [9.1, 47.1]]] };
    const map = zoomMap();
    syncBrowseMosaic(map.map as never, { items: [scene], dataset: ql });
    FakeImage.arrive();
    map.idle();
    expect(dynamic(map)).toEqual(['m-img-lyr-0']);
    // The view cut to the AOI: another image than the browse preview, which arrives late.
    syncFocusRaster(map.map as never, {
      downloaded: { H3: sceneInfo(scene, 8, 19) },
      render: {},
      showDownloaded: true,
      items: [scene],
      dataset: ql,
      aoi,
      cropToAoi: true,
    });
    map.idle();
    expect(dynamic(map)).toContain('m-img-lyr-0');
    FakeImage.arrive();
    map.idle();
    expect(dynamic(map).some((id) => id.startsWith('m-'))).toBe(false);
    expect(dynamic(map)).toContain('n-img-lyr-0');
  });

  it('keeps the old picture while the next one draws nothing yet, such as a mosaic on its way', () => {
    const items = [previewScene('P1'), previewScene('P2')];
    const group: TimeStepGroup = { key: ['p'], label: 'p', items };
    const both = { P1: sceneInfo(items[0], 8, 14), P2: sceneInfo(items[1], 8, 14) };
    const map = zoomMap();
    browse(map);
    map.idle();
    full(map, { downloaded: both, items, groups: [group], mosaics: {} }); // pending: nothing drawn
    map.idle();
    expect(dynamic(map)).toEqual(['m-tiles-lyr-0']);
    const refused: Mosaics = {};
    full(map, { downloaded: both, items, groups: [group], mosaics: refused, dataset: { ...dataset } });
    map.idle();
    expect(dynamic(map)).toEqual(['m-tiles-lyr-0']); // the tiler's answer is not here yet
  });

  it('lets go of the old picture after ten seconds if the new one never loads', () => {
    vi.useFakeTimers();
    const map = zoomMap();
    browse(map);
    full(map);
    expect(dynamic(map)).toHaveLength(2);
    vi.advanceTimersByTime(9_999);
    expect(dynamic(map)).toHaveLength(2);
    vi.advanceTimersByTime(2);
    expect(dynamic(map)).toEqual(['n-tiles-lyr-0']);
  });

  it('takes the picture away at once when the image is switched off', () => {
    const map = zoomMap();
    browse(map);
    map.idle();
    full(map, { showDownloaded: false });
    expect(dynamic(map)).toEqual([]);
  });

  it('never keeps more than one older picture, however fast it is redrawn', () => {
    const map = zoomMap();
    browse(map);
    for (let i = 0; i < 5; i++) full(map);
    expect(dynamic(map).length).toBeLessThanOrEqual(2);
    map.idle();
    expect(dynamic(map)).toHaveLength(1);
  });

  it('forgets the picture it waited to take away when a style reload wipes the map', () => {
    vi.useFakeTimers();
    const first = zoomMap();
    browse(first);
    full(first); // the quicklook waits on `first`
    const reloaded = zoomMap(); // setStyle(): every custom layer is gone
    full(reloaded);
    expect(dynamic(reloaded)).toEqual(['m-tiles-lyr-0']);
    vi.advanceTimersByTime(20_000);
    expect(dynamic(reloaded)).toEqual(['m-tiles-lyr-0']);
  });

  it('draws at once on a map that cannot say when it is idle, as before', () => {
    const map = zoomMap();
    delete (map.map as { once?: unknown }).once;
    browse(map);
    full(map);
    expect(dynamic(map)).toEqual(['m-tiles-lyr-0']);
  });
});
