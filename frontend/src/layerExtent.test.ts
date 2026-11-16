import { describe, expect, it } from 'vitest';

import { layerBox, LARGE_LAYER_SPAN } from './layerExtent';
import type { LayerOverlay, MapLayer } from './layers';

const raster = (bounds: [number, number, number, number]): LayerOverlay => ({ kind: 'raster', tileUrl: 'tiles/{z}/{x}/{y}', bounds, minZoom: 0, maxZoom: 14 });
const layer = (overlays: LayerOverlay[], aoi: GeoJSON.Geometry | null = null): MapLayer =>
  ({ id: 'L', name: 'L', visible: true, opacity: 1, overlays, restore: { aoi } }) as unknown as MapLayer;
const square = (w: number, s: number, e: number, n: number): GeoJSON.Polygon => ({ type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] });

describe('layerBox', () => {
  it('is the box of one scene', () => {
    expect(layerBox(layer([raster([10, 47, 11, 48])]))).toEqual([10, 47, 11, 48]);
  });

  it('holds every scene of a mosaic or a result in one box', () => {
    expect(layerBox(layer([raster([10, 47, 11, 48]), raster([12, 46, 13, 47.5])]))).toEqual([10, 46, 13, 48]);
  });

  it('takes the corners of a quicklook image', () => {
    const image: LayerOverlay = { kind: 'image', url: 'q.png', nodataMax: null, coords: [[10, 48], [12, 48.5], [12, 47], [10, 46.5]] };
    expect(layerBox(layer([image]))).toEqual([10, 46.5, 12, 48.5]);
  });

  it('goes the shorter way round the earth', () => {
    const [west, , east] = layerBox(layer([raster([179, -18, 180, -17]), raster([-180, -18, -179, -17])]))!;
    expect(east - west).toBeLessThanOrEqual(2);
  });

  it('is null where the layer draws nothing or its box is broken', () => {
    expect(layerBox(layer([]))).toBeNull();
    expect(layerBox(layer([raster([Number.NaN, 0, 1, 1])]))).toBeNull();
  });

  it('keeps the extent of a layer that is large but has no selection', () => {
    expect(layerBox(layer([raster([-180, -85, 180, 85])]))).toEqual([-180, -85, 180, 85]);
  });

  it('fits a very large layer to its selection (the AOI it was pinned with)', () => {
    expect(layerBox(layer([raster([-180, -85, 180, 85])], square(8, 47, 9, 48)))).toEqual([8, 47, 9, 48]);
  });

  it('leaves a layer of the size of a region to its extent even where it has an AOI', () => {
    const edge = LARGE_LAYER_SPAN.lon;
    expect(layerBox(layer([raster([0, 0, edge, 10])], square(1, 1, 2, 2)))).toEqual([0, 0, edge, 10]);
  });

  it('falls back to the extent where the AOI has no box', () => {
    expect(layerBox(layer([raster([-180, -85, 180, 85])], { type: 'GeometryCollection', geometries: [] }))).toEqual([-180, -85, 180, 85]);
  });
});
