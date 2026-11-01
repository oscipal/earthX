// The layer-manager model. A layer is a pinned snapshot of whatever was on
// screen (a quicklook, a full-res crop, a stitch, a decomposition …) plus the
// state needed to re-select it and keep working.

import type { Coords4 } from './geoUtils';
import type { RGB } from './processingBands';
import type { Percent } from './percentRange';
import type { PreviewRange } from './processingPreview';
import type { ResultStats } from './render';
import type { ResultBand } from './resultLayer';
import type { AppliedRender, Bbox, DownloadedInfo } from './types';

export type LayerOverlay =
  // A (transparent-nodata) quicklook. `nodataMax` is the registry's
  // freistellung threshold at the time this was pinned (M3-12) — captured
  // here for the same reason `minZoom`/`maxZoom` are captured on the raster
  // variant below: the live dataset selection can move on while the layer
  // stays pinned.
  | {
      kind: 'image';
      url: string;
      coords: Coords4;
      nodataMax: number | null;
      // The AOI the image is cut to, in its own pixels (`geoUtils.ts::quicklookAoiPixelRings`).
      clipRings?: [number, number][][];
    }
  // Tiles: full resolution, a stitch, a decomposition — or the browse preview of a
  // source that publishes no quicklook, which is the same thing pinned to a single
  // level (M2-10). The range travels with the overlay so a pinned layer still knows
  // it after `setStyle()` wipes every source.
  // `preview` marks a tile preview of an operator (M4-13c-2): always coarser than
  // the data, and the map says "Preview" while one is switched on.
  | {
      kind: 'raster';
      tileUrl: string;
      bounds: Bbox;
      minZoom: number;
      maxZoom: number;
      // From this zoom up the layer is not drawn (MapLibre's layer `maxzoom`): a scene stacked
      // below the first level of a mosaic (`mosaic.ts`) steps aside for it.
      hideFrom?: number;
      preview?: true;
    };

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
  // `itemIds`, split back into the groups the results list drew them from
  // (M3-17, `grouping.ts::groupItemIdsFor`) — one merged file per group on
  // download (P19), reusing PR #84's own per-overpass grouping rather than a
  // second, download-specific one. Empty for a layer pinned before M3-17;
  // `download.ts::downloadRequestFor` then falls back to one group of
  // everything, the flat shape every download had before.
  groupItemIds: string[][];
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
  // Set for a layer that shows a derived picture, not scenes of a dataset: a
  // preview of the processing panel, or the result of a job. It cannot be
  // processed or downloaded as scenes (the buttons of the layer manager skip it).
  derived?: 'preview' | 'result';
  // The acquisition day of the scenes the layer shows (UTC, YYYY-MM-DD), or the span "first – last" of several; absent for
  // data without a time axis such as the elevation model (NM4-65 part 3). Set where the layer is made: it does not follow
  // the search, which moves on.
  date?: string;
  // What the layer was saved with while its settings are open and something else is applied or its opacity is changed (NM4-54, Otto,
  // 1.11.2026): "Save" makes the layer as it is drawn its own, closing the settings without it puts this back. Only the parts that changed
  // are here.
  saved?: { opacity: number; overlays?: LayerOverlay[]; downloaded?: LayerRestore['downloaded']; appliedRender?: LayerRestore['appliedRender'] };
  // A hint for the tooltip of the layer's name, never a line of text in its row: a preview drawn scene by scene where
  // the job is a mosaic says it may differ from the job (`processingPreview.ts::SCENE_PREVIEW_HINT`).
  note?: string;
  // Of a `result` layer (M4-13c-5).
  result?: ResultLayerInfo;
}

// What a layer made of a job's result knows about it. Not the tile URL (that is
// the overlay's) and not the order: the AOI never goes into a layer's text.
export interface ResultLayerInfo {
  jobID: string;
  // When the job's results are dropped; the layer is "Expired" from a minute before.
  expires: string;
  // Metres per pixel of the result, for "Overview"; `null` if it is not known.
  gsd: number | null;
  // `earthx:resampled` (Prinzip 2.9); `null` if the results said nothing.
  resampled: boolean | null;
  // Set when `expires` has passed: the map loads no more tiles of it.
  expired: boolean;
  // Set while the job is deleted and can still be restored (NM4-27): the server answers `404` for it, so the layer
  // stays in the list, locked, and the map asks for no tiles. It goes from the list when the day is over.
  deleted?: boolean;
  // The tile URL the layer is saved with while "Apply" draws another one that is not saved yet (NM4-50): the unsaved
  // look goes when the settings are closed (`revertResultLayer`), "Save" makes it the layer's own.
  savedTileUrl?: string;
  // What the tiler named for the result (`float32`, `uint16` …); `null` if it did not say. A float result
  // needs a range and a colormap to become a picture, any other is drawn as it is.
  dataType: string | null;
  // The statistics of the AOI the default range comes from (M4-32); `null` for a result without them. Of a result of
  // several bands: those of the band the layer draws.
  stats: ResultStats | null;
  // The range and colormap of the index preset the band the layer draws is (its expression is the preset's, NM4-14);
  // `null` for any other band. Left out in a layer made before this was written.
  preset?: PreviewRange | null;
  // The bands of a result of more than one, in the order of the file, and the place of the one the layer draws
  // (`bidx` is the place + 1); left out for a result of one band (NM4-43e PR 2).
  bands?: ResultBand[];
  // The place of the band the layer draws, or `RGB` for the colour picture of the three bands in `colour` (NM4-64).
  band?: number | typeof RGB;
  // The places in the file of red, green and blue where the result has all three and the dataset a colour picture:
  // then "RGB" is one of the choices of the layer.
  colour?: [number, number, number];
  // Set on a layer made from one band of another ("Add band as layer", NM4-65 part 2): it draws that band and no other, is
  // named after it, and its look is its own — "Save" keeps it for this layer and leaves the layer it came from and the job alone.
  own?: true;
  // What the range the layer draws was typed as, where it was typed in percentiles (NM4-65 part 4); the tile URL holds the
  // values they gave. While a look is applied and not saved, `savedPercent` is what the saved look was typed as.
  percent?: Percent;
  savedPercent?: Percent | null;
}
