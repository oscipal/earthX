// "Zoom to selection" (UI-04 part 4, Otto, 3.11.2026): the map zooms to everything that is chosen at once — the AOI, the open view and
// the layers that are shown — in the box that holds them all, going the shorter way round the earth. A layer that is switched off does not count,
// and neither does a view whose image is switched off. Without any of them the button is locked and says why.

import { coordsBbox, polygonBbox, unionBboxShortest } from './geoUtils';
import type { MapLayer } from './layers';
import type { AppliedRender, Bbox, DownloadedInfo } from './types';
import { layersForMap, viewLayerOf, viewShown } from './viewLayer';

export const NOTHING_TO_ZOOM = 'Nothing to zoom to: draw an AOI, open an image or show a layer';

export interface ZoomState {
  aoi: GeoJSON.Geometry | null;
  layers: MapLayer[];
  focusMode: boolean;
  downloaded: Record<string, DownloadedInfo>;
  appliedRender: AppliedRender;
  viewLayerId: string | null;
  cropToAoi: boolean;
  viewAoi: GeoJSON.Geometry | null;
  showDownloaded: boolean;
}

// The boxes of what is chosen: the AOI, the images of the open view, the pictures of the layers that are shown.
export function zoomBoxes(s: ZoomState): Bbox[] {
  const boxes: Bbox[] = [];
  const aoi = s.aoi && polygonBbox(s.aoi);
  if (aoi) boxes.push(aoi);
  const viewLayer = viewLayerOf(s.layers, { ...s, aoi: s.viewAoi });
  if (s.focusMode && viewShown(viewLayer, s.showDownloaded)) boxes.push(...Object.values(s.downloaded).map((image) => image.bounds));
  for (const layer of layersForMap(s.layers, viewLayer, s.showDownloaded)) {
    if (!layer.visible) continue;
    for (const overlay of layer.overlays) boxes.push(overlay.kind === 'raster' ? overlay.bounds : coordsBbox(overlay.coords));
  }
  return boxes;
}

// The box to zoom to, or `null` when nothing is chosen.
export const zoomTarget = (s: ZoomState): Bbox | null => unionBboxShortest(zoomBoxes(s));
