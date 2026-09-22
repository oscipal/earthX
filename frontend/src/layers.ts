// The layer-manager model. A layer is a pinned snapshot of whatever was on
// screen (a quicklook, a full-res crop, a stitch, a decomposition …) plus the
// state needed to re-select it and keep working.

import type { Coords4 } from './geoUtils';
import type { AppliedRender, Bbox, DownloadedInfo } from './types';

export type LayerOverlay =
  | { kind: 'image'; url: string; coords: Coords4 } // a (transparent-nodata) quicklook
  | { kind: 'raster'; tileUrl: string; bounds: Bbox }; // full-res / stitch / decomposition tiles

// Enough of the working state to bring a layer back into the active view.
export interface LayerRestore {
  focusMode: boolean;
  downloaded: Record<string, DownloadedInfo>;
  appliedRender: AppliedRender;
  activeGroupIndex: number;
  selectedIds: string[];
  aoi: GeoJSON.Geometry | null;
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
