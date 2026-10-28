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
//
// "Loading…": the panel asks the tiler about the preview, or the map waits for its tiles (`usePreviewLoading`). The
// panel's heading says it too: a narrow window hides the map behind the panel.
//
// "Zoom in": a layer, or the preview of the panel, whose tiles start at a level above the map's zoom
// shows nothing there, and the badge says from which zoom it is drawn (`zoomHint.ts`).

import { useMemo } from 'react';

import { previewOverlays, SCENE_PREVIEW_HINT } from '../processingPreview';
import { isOverview } from '../resultLayer';
import { useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import { zoomInTo } from '../zoomHint';
import usePreviewLoading, { LOADING_TITLE } from './usePreviewLoading';

export const OVERVIEW_TITLE = 'Drawn coarser than the result: zoom in for its full resolution.';

const zoomInTitle = (waiting: { name: string; from: number }[]): string =>
  `${waiting[0].name} is drawn from zoom ${waiting[0].from}.${waiting.length > 1 ? ` ${waiting.length - 1} more start later.` : ''}`;

export default function PreviewBadge() {
  const draft = useProcessingStore((s) => s.preview);
  const loading = usePreviewLoading();
  const aoi = useAppStore((s) => s.aoi);
  const draftOverlays = useMemo(() => (draft ? previewOverlays(draft, draft.clipToAoi ? aoi : null) : []), [draft, aoi]);
  const layers = useAppStore((s) => s.layers);
  const mapZoom = useAppStore((s) => s.mapZoom);
  const viewport = useAppStore((s) => s.viewportBbox);
  const pinned = layers.some((l) => l.visible && l.overlays.some((o) => o.kind === 'raster' && o.preview));
  const overview = layers.some(
    (l) =>
      l.visible &&
      l.result &&
      !l.result.expired &&
      !l.result.deleted &&
      l.overlays.some(
        (o) => o.kind === 'raster' && isOverview({ gsd: l.result?.gsd ?? null, mapZoom, viewport, maxZoom: o.maxZoom }),
      ),
  );
  // A layer or the preview of the panel that starts at a level above this zoom: the map says so, instead of nothing.
  const waiting = [
    ...layers.filter((l) => l.visible && !l.result?.expired && !l.result?.deleted).map((l) => ({ name: l.name, from: zoomInTo(l.overlays, mapZoom) })),
    ...(draft ? [{ name: 'Preview', from: zoomInTo(draftOverlays, mapZoom) }] : []),
  ].filter((w): w is { name: string; from: number } => w.from !== null);
  if (!draft && !pinned && !overview && waiting.length === 0 && !loading) return null;
  return (
    <div className="overlay preview-badge-dock">
      {(draft || pinned) && (
        <span className="preview-badge" title={draft?.perScene ? SCENE_PREVIEW_HINT : undefined}>
          Preview
        </span>
      )}
      {loading && (
        <span className="preview-badge loading" role="status" title={LOADING_TITLE}>
          Loading…
        </span>
      )}
      {overview && (
        <span className="preview-badge" title={OVERVIEW_TITLE}>
          Overview
        </span>
      )}
      {waiting.length > 0 && (
        <span className="preview-badge" title={zoomInTitle(waiting)}>
          Zoom in
        </span>
      )}
    </div>
  );
}
