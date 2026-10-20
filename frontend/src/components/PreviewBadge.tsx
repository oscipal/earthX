// "Preview" and "Overview" over the map (M4-13c-2, M4-13c-5).
//
// "Preview": shown while a preview is on the map — the one of the open processing
// panel, or a pinned preview layer that is switched on. A preview is held coarser
// than the data (Otto, 19.10.2026; its tiles stop short of the data's pixel size,
// `processingPreview.ts::previewMaxZoom`), or, where the data names no pixel size,
// marked at every zoom: the badge never depends on the zoom.
//
// "Overview": the layer of a job's result is real data, drawn from the result's
// own file; at a zoom where the tile is coarser than the result's pixel size, the
// tiler reads its overviews, and the badge says so (`resultLayer.ts::isOverview`).

import { isOverview } from '../resultLayer';
import { useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';

export const OVERVIEW_TITLE = 'Drawn coarser than the result: zoom in for its full resolution.';

export default function PreviewBadge() {
  const draft = useProcessingStore((s) => s.preview);
  const layers = useAppStore((s) => s.layers);
  const mapZoom = useAppStore((s) => s.mapZoom);
  const viewport = useAppStore((s) => s.viewportBbox);
  const pinned = layers.some((l) => l.visible && l.overlays.some((o) => o.kind === 'raster' && o.preview));
  const overview = layers.some(
    (l) =>
      l.visible &&
      l.result &&
      !l.result.expired &&
      l.overlays.some(
        (o) => o.kind === 'raster' && isOverview({ gsd: l.result?.gsd ?? null, mapZoom, viewport, maxZoom: o.maxZoom }),
      ),
  );
  if (!draft && !pinned && !overview) return null;
  return (
    <div className="overlay preview-badge-dock">
      {(draft || pinned) && <span className="preview-badge">Preview</span>}
      {overview && (
        <span className="preview-badge" title={OVERVIEW_TITLE}>
          Overview
        </span>
      )}
    </div>
  );
}
