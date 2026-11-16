// "Zoom to layer" (UI-09, Otto, 16.11.2026): the box the map fits to for one row of the layer manager, from the pictures the layer draws
// (scenes, a mosaic, the result of a job, a pinned view), going the shorter way round the earth. A layer as large as a pyramid of the whole
// earth (GLO-30) fits to its selection, the AOI it was pinned with, where it has one; without one it fits to its extent.

import { coordsBbox, polygonBbox, unionBboxShortest } from './geoUtils';
import type { MapLayer } from './layers';
import type { Bbox } from './types';

// From this width or height of its box (degrees) a layer counts as very large.
export const LARGE_LAYER_SPAN = { lon: 90, lat: 45 } as const;

export function layerBox(layer: MapLayer): Bbox | null {
  const extent = unionBboxShortest(layer.overlays.map((o) => (o.kind === 'raster' ? o.bounds : coordsBbox(o.coords))));
  if (!extent) return null;
  const large = extent[2] - extent[0] > LARGE_LAYER_SPAN.lon || extent[3] - extent[1] > LARGE_LAYER_SPAN.lat;
  const selection = large && layer.restore.aoi ? polygonBbox(layer.restore.aoi) : null;
  return selection ?? extent;
}
