// Where a layer is on the map and where it is not (UI-01a). A layer whose tiles start at a level above the map's zoom
// shows nothing there; the tooltip of its row in the layer manager says from which zoom it is drawn (Otto, 10.11.2026:
// nothing over the map says it any more), instead of the layer staying empty without a word.

import type { LayerOverlay } from './layers';
import { firstZoomOf } from './tileSize';

// MapLibre asks a tile source for level L from map zoom L - 1.5 (256-px tiles) or L - 0.5 (512-px ones, `tileSize.ts`);
// a layer's `maxzoom` is a map zoom. An image is drawn at every zoom.
export function isDrawnAt(overlay: LayerOverlay, zoom: number): boolean {
  if (overlay.kind === 'image') return true;
  return zoom >= firstZoomOf(overlay.minZoom, overlay.tileUrl) && (overlay.hideFrom === undefined || zoom < overlay.hideFrom);
}

// The map zoom from which these overlays are drawn, if they are not drawn at `zoom` and would be zoomed in; else `null`.
export function zoomInTo(overlays: readonly LayerOverlay[], zoom: number): number | null {
  if (overlays.length === 0 || overlays.some((ov) => isDrawnAt(ov, zoom))) return null;
  const starts = overlays.flatMap((ov) => (ov.kind === 'raster' && firstZoomOf(ov.minZoom, ov.tileUrl) > zoom ? [firstZoomOf(ov.minZoom, ov.tileUrl)] : []));
  return starts.length > 0 ? Math.ceil(Math.min(...starts)) : null;
}

// What the row of a layer says while the layer shows nothing at this zoom, or `null` while it shows something.
export function zoomReasonOf(overlays: readonly LayerOverlay[], zoom: number, subject = 'this layer'): string | null {
  const from = Number.isFinite(zoom) ? zoomInTo(overlays, zoom) : null;
  return from === null ? null : `Nothing shown at this zoom: ${subject} is drawn from zoom ${from}.`;
}
