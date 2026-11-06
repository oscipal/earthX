// "Zoom to selection" (UI-04 part 4, Otto, 3.11.2026): AOI, open view and the layers that are shown, together, the shorter way round the earth.

import { describe, expect, it } from 'vitest';

import type { MapLayer } from './layers';
import type { Bbox, DownloadedInfo } from './types';
import { NOTHING_TO_ZOOM, zoomBoxes, zoomTarget, type ZoomState } from './zoomSelection';

const square = (box: Bbox): GeoJSON.Polygon => ({
  type: 'Polygon',
  coordinates: [[[box[0], box[1]], [box[2], box[1]], [box[2], box[3]], [box[0], box[3]], [box[0], box[1]]]],
});

const layer = (id: string, bounds: Bbox, extra: Partial<MapLayer> = {}): MapLayer => ({
  id,
  name: id,
  visible: true,
  opacity: 1,
  overlays: [{ kind: 'raster', tileUrl: 'https://t/{z}/{x}/{y}', bounds, minZoom: 0, maxZoom: 12 }],
  restore: { focusMode: false, downloaded: {}, appliedRender: {}, activeGroupIndex: 0, selectedIds: [], itemIds: [], groupItemIds: [], aoi: null, cropToAoi: false, datasetId: null },
  ...extra,
});

const image = (bounds: Bbox): DownloadedInfo => ({ datasetId: 'd', tileUrl: 'https://t/{z}/{x}/{y}', bounds, asset: 'visual', minZoom: 0, maxZoom: 12 });

const state = (extra: Partial<ZoomState> = {}): ZoomState => ({
  aoi: null,
  layers: [],
  focusMode: false,
  downloaded: {},
  appliedRender: {},
  viewLayerId: null,
  cropToAoi: false,
  viewAoi: null,
  showDownloaded: true,
  ...extra,
});

const SWITZERLAND: Bbox = [6, 45.8, 10.5, 47.8];
const TENERIFE: Bbox = [-16.9, 28, -16.1, 28.6];

describe('what "Zoom to selection" zooms to', () => {
  it('is nothing, and the button is locked with a reason, where there is no AOI, no view and no layer', () => {
    expect(zoomBoxes(state())).toEqual([]);
    expect(zoomTarget(state())).toBeNull();
    expect(NOTHING_TO_ZOOM).toBe('Nothing to zoom to: draw an AOI, open an image or show a layer');
  });

  it('is the AOI alone', () => {
    expect(zoomTarget(state({ aoi: square(SWITZERLAND) }))).toEqual(SWITZERLAND);
  });

  it('is the open view alone: the images it draws', () => {
    expect(zoomTarget(state({ focusMode: true, downloaded: { a: image(TENERIFE) } }))).toEqual(TENERIFE);
  });

  it('is the layers that are shown alone', () => {
    expect(zoomTarget(state({ layers: [layer('L', TENERIFE)] }))).toEqual(TENERIFE);
  });

  it('is all three together: an AOI in Switzerland and a view on Tenerife are both in the box (Otto\'s example)', () => {
    const target = zoomTarget(state({ aoi: square(SWITZERLAND), focusMode: true, downloaded: { a: image(TENERIFE) } }));
    expect(target).toEqual([-16.9, 28, 10.5, 47.8]);
  });

  it('adds the layers to the AOI, and the AOI no longer wins (it did until part 4)', () => {
    expect(zoomTarget(state({ aoi: square(SWITZERLAND), layers: [layer('L', TENERIFE)] }))).toEqual([-16.9, 28, 10.5, 47.8]);
  });

  it('counts an image of the view only while the view is open', () => {
    expect(zoomBoxes(state({ focusMode: false, downloaded: { a: image(TENERIFE) } }))).toEqual([]);
  });

  it('leaves out the view whose image is switched off ("Hide image"), and a layer that is switched off', () => {
    expect(zoomBoxes(state({ focusMode: true, showDownloaded: false, downloaded: { a: image(TENERIFE) } }))).toEqual([]);
    expect(zoomBoxes(state({ layers: [layer('hidden', TENERIFE, { visible: false })] }))).toEqual([]);
    expect(zoomTarget(state({ aoi: square(SWITZERLAND), layers: [layer('hidden', TENERIFE, { visible: false })] }))).toEqual(SWITZERLAND);
  });

  it('counts the pinned layer that is the open view once, by its eye, and not through the view\'s own switch', () => {
    const pinned = layer('P', TENERIFE, { restore: { ...layer('P', TENERIFE).restore, focusMode: true, downloaded: { a: image(TENERIFE) } } });
    const open = state({ layers: [pinned], viewLayerId: 'P', focusMode: true, downloaded: { a: image(TENERIFE) } });
    expect(zoomTarget(open)).toEqual(TENERIFE);
    // The view's image is switched off: the layer that is the view goes with it.
    expect(zoomBoxes({ ...open, showDownloaded: false })).toEqual([]);
    // The layer is switched off: neither draws.
    expect(zoomBoxes({ ...open, layers: [{ ...pinned, visible: false }] })).toEqual([]);
  });

  it('reads the corners of an image overlay as well as the bounds of a raster one', () => {
    const picture = layer('I', [0, 0, 0, 0], {
      overlays: [{ kind: 'image', url: 'x', coords: [[20, 21], [22, 21], [22, 20], [20, 20]], nodataMax: 16 }],
    });
    expect(zoomTarget(state({ layers: [picture] }))).toEqual([20, 20, 22, 21]);
  });

  it('ignores an AOI without a box (an empty geometry)', () => {
    expect(zoomBoxes(state({ aoi: { type: 'GeometryCollection', geometries: [] } }))).toEqual([]);
  });

  it('takes the shorter way over the antimeridian: Fiji on both sides gives one box past 180, not the world', () => {
    const east: Bbox = [177, -19, 179.9, -16];
    const west: Bbox = [-179.5, -18, -178, -16];
    expect(zoomTarget(state({ aoi: square(east), layers: [layer('W', west)] }))).toEqual([177, -19, 182, -16]);
  });

  it('is not the world for a view across the line and an AOI beside it', () => {
    const target = zoomTarget(state({ aoi: square([178, -18, 179, -17]), focusMode: true, downloaded: { a: image([-179, -18, -178, -17]) } }));
    expect(target).toEqual([178, -18, 182, -17]);
  });
});
