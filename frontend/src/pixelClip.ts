// M5-69: a point AOI crops the one pixel it lies on. The map cuts its tiles in the browser (`aoiClip.ts`), so a view or a
// preview at a point is cut to the outline of that pixel. Only the server knows the grid of the source
// (`POST /collections/{dataset}/pixel`); the outline it answers is kept here for the point object it belongs to, browser-tab
// memory like the registry of `aoiClip.ts`. Until it is here, a point cuts away everything.

const outlines = new WeakMap<GeoJSON.Geometry, GeoJSON.Polygon>();

// The geometry tiles and quicklooks are cut to: an area as it is, a point as the outline of its pixel, or the point itself
// while that outline is not known (which keeps nothing).
export function clipShapeOf(aoi: GeoJSON.Geometry | null): GeoJSON.Geometry | null {
  if (!aoi || aoi.type !== 'Point') return aoi;
  return outlines.get(aoi) ?? aoi;
}

export function pixelOutlineOf(point: GeoJSON.Geometry): GeoJSON.Polygon | null {
  return outlines.get(point) ?? null;
}

export function keepPixelOutline(point: GeoJSON.Point, outline: GeoJSON.Polygon): void {
  outlines.set(point, outline);
}

// The zoom at which the pixel of `outline` is about `pixels` screen pixels wide (tiles of 512 px), at most `max`.
export function zoomForPixel(outline: GeoJSON.Polygon, pixels = 96, max = 20): number {
  const xs = outline.coordinates[0].map((position) => position[0]);
  const width = Math.max(...xs) - Math.min(...xs);
  if (!(width > 0)) return max;
  return Math.min(max, Math.log2((pixels * 360) / (512 * width)));
}
