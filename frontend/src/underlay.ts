// The quicklook a scene keeps under its tiles (M3-12, O5; UI-01a). A dataset that publishes a quicklook and
// releases its tiles from a zoom above 0 would otherwise leave the map empty when zooming out of them, and for as
// long as tiles load late when zooming in: the quicklook is there at every zoom and the tiles lie over it. The view
// lays it under its tiles and so does a layer pinned from the view, at its own place in the list, so that a move in
// the list moves the quicklook with the tiles.

import { preferredGeoreferencedAsset, quicklookAsset } from './datasets';
import type { DatasetOption } from './datasets';
import { quicklookAoiPixelRings, quicklookCoords } from './geoUtils';
import type { LayerOverlay } from './layers';
import type { StacItem } from './types';

export type ImageOverlay = Extract<LayerOverlay, { kind: 'image' }>;

// `clip` is the AOI the tiles are cut to, or `null`: the image is cut the same way, on its own pixel grid.
// `null` for a dataset that shows no quicklook first, or from zoom 0 up, and for a scene without one.
export function underlayOf(
  item: StacItem,
  dataset: DatasetOption | null | undefined,
  clip: GeoJSON.Geometry | null,
): ImageOverlay | null {
  if (!dataset?.viewable || dataset.browse !== 'quicklook' || dataset.zoom.min <= 0) return null;
  const href = quicklookAsset(item)?.href;
  if (!href) return null;
  const preferred = preferredGeoreferencedAsset(dataset);
  const coords = quicklookCoords(item, preferred);
  if (!coords) return null;
  const rings = clip ? quicklookAoiPixelRings(item, clip, preferred) : null;
  return {
    kind: 'image',
    url: href,
    coords,
    nodataMax: dataset.quicklookNodataMax,
    ...(rings ? { clipRings: rings } : {}),
  };
}
