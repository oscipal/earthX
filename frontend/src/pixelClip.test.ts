// M5-69: a point AOI cuts tiles and quicklooks to the outline of its one pixel, or to nothing while that is not known.
import { describe, expect, it } from 'vitest';

import { clipShapeOf, keepPixelOutline, pixelOutlineOf, zoomForPixel } from './pixelClip';
import { bboxToPolygon } from './geoUtils';

describe('clipShapeOf', () => {
  it('leaves an area and no AOI as they are', () => {
    const area = bboxToPolygon([9, 47, 9.1, 47.1]);
    expect(clipShapeOf(area)).toBe(area);
    expect(clipShapeOf(null)).toBeNull();
  });

  it('cuts a point to the outline of its pixel once it is known, and to the point itself before', () => {
    const point: GeoJSON.Point = { type: 'Point', coordinates: [9.05, 47.05] };
    expect(clipShapeOf(point)).toBe(point);
    expect(pixelOutlineOf(point)).toBeNull();
    const pixel = bboxToPolygon([9.0499, 47.0499, 9.0501, 47.0501]);
    keepPixelOutline(point, pixel);
    expect(clipShapeOf(point)).toBe(pixel);
    // Another point at the same place is another view: it asks for its own pixel.
    expect(clipShapeOf({ ...point })).not.toBe(pixel);
  });
});

describe('zoomForPixel', () => {
  it('comes close enough for a pixel of 10 m to be seen, and no closer than the map goes', () => {
    expect(zoomForPixel(bboxToPolygon([9.05, 47.05, 9.05013, 47.05009]))).toBeGreaterThan(18);
    expect(zoomForPixel(bboxToPolygon([9.05, 47.05, 9.05, 47.05]))).toBe(20);
    expect(zoomForPixel(bboxToPolygon([9, 47, 10, 48]))).toBeLessThan(7);
  });
});
