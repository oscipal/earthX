// Where a layer is on the map and where it is not (UI-01a). A layer whose tiles start at a level above the map's zoom
// shows nothing there; the map then says from which zoom it is drawn instead of staying empty without a word.

import type { LayerOverlay } from './layers';
import { TILE_LEVEL_AHEAD } from './mosaic';

// MapLibre asks a 256-pixel tile source for level L from map zoom L - 1.5 (`mosaic.ts`); a layer's `maxzoom` is a map
// zoom. An image is drawn at every zoom.
export function isDrawnAt(overlay: LayerOverlay, zoom: number): boolean {
  if (overlay.kind === 'image') return true;
  return zoom >= overlay.minZoom - TILE_LEVEL_AHEAD && (overlay.hideFrom === undefined || zoom < overlay.hideFrom);
}

// The map zoom from which these overlays are drawn, if they are not drawn at `zoom` and would be zoomed in; else `null`.
export function zoomInTo(overlays: readonly LayerOverlay[], zoom: number): number | null {
  if (overlays.length === 0 || overlays.some((ov) => isDrawnAt(ov, zoom))) return null;
  const starts = overlays.flatMap((ov) => (ov.kind === 'raster' && ov.minZoom - TILE_LEVEL_AHEAD > zoom ? [ov.minZoom - TILE_LEVEL_AHEAD] : []));
  return starts.length > 0 ? Math.ceil(Math.min(...starts)) : null;
}
