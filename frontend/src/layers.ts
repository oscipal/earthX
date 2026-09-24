// The layer-manager model. A layer is a pinned snapshot of whatever was on
// screen (a quicklook, a full-res crop, a stitch, a decomposition …) plus the
// state needed to re-select it and keep working.

import type { Coords4 } from './geoUtils';
import type { AppliedRender, Bbox, DownloadedInfo } from './types';

export type LayerOverlay =
  | { kind: 'image'; url: string; coords: Coords4 } // a (transparent-nodata) quicklook
  // Tiles: full resolution, a stitch, a decomposition — or the browse preview of a
  // source that publishes no quicklook, which is the same thing pinned to a single
  // level (M2-10). The range travels with the overlay so a pinned layer still knows
  // it after `setStyle()` wipes every source.
  | { kind: 'raster'; tileUrl: string; bounds: Bbox; minZoom: number; maxZoom: number };

// Enough of the working state to bring a layer back into the active view.
export interface LayerRestore {
  focusMode: boolean;
  downloaded: Record<string, DownloadedInfo>;
  appliedRender: AppliedRender;
  activeGroupIndex: number;
  selectedIds: string[];
  // The scenes this layer represents, captured when it was pinned (V-6) —
  // independent of `store.items`/`groups`, which may have moved on to a
  // different search by the time the layer is downloaded. For a
  // full-resolution layer this is `Object.keys(downloaded)`; for a
  // quicklook-only one, the pinned scenes themselves (`addCurrentToLayers`
  // may have skipped a few of those as map overlays for missing geometry,
  // but a crop only needs the item id, the dataset and the AOI).
  itemIds: string[];
  aoi: GeoJSON.Geometry | null;
  // Whether the full-resolution view this layer was pinned from was cropped
  // to `aoi` ("Crop to AOI") or showed the whole selection uncropped ("View
  // full selection", M3-09) — meaningless while `focusMode` is false, where a
  // quicklook-only layer's download always needs `aoi` regardless of it.
  // Drives both the map (was the pinned overlay's tile URL clipped) and the
  // download (`download.ts::downloadRequestFor`: what "download follows the
  // view" means for this layer, P19).
  cropToAoi: boolean;
  // The dataset the layer was pinned from (M2-07d): the current selection
  // (`store.datasetId`) can move on to a different dataset while the layer
  // stays pinned, and a download has to name the dataset the pinned items
  // actually belong to, not whatever is picked in the panel right now.
  datasetId: string | null;
}

export interface MapLayer {
  id: string;
  name: string;
  visible: boolean;
  opacity: number;
  overlays: LayerOverlay[];
  restore: LayerRestore;
}
