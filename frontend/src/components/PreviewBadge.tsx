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
// No "Zoom in" (Otto, 10.11.2026): a layer that starts at a level above the map's zoom says so in the tooltip of its row
// in the layer manager (`zoomHint.ts`), and the preview of the panel in the tooltip of "Preview".

import { useMemo } from 'react';

import { previewOverlays, previewTitle } from '../processingPreview';
import { isOverview } from '../resultLayer';
import { tileSizeOf } from '../tileSize';
import { clipAoiOf, useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import { zoomReasonOf } from '../zoomHint';
import Badge from './Badge';
import usePreviewLoading, { LOADING_TITLE } from './usePreviewLoading';

export const OVERVIEW_TITLE = 'Drawn coarser than the result: zoom in for its full resolution.';

export default function PreviewBadge() {
  const draft = useProcessingStore((s) => s.preview);
  const draftMeasure = useProcessingStore((s) => s.measure);
  const loading = usePreviewLoading();
  const mapAoi = useAppStore((s) => s.aoi);
  // What an entry fixed (a crop, a result) is cut to its own AOI, not the map's.
  const aoi = useProcessingStore((s) => clipAoiOf(s, mapAoi));
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
        (o) => o.kind === 'raster' && isOverview({ gsd: l.result?.gsd ?? null, mapZoom, viewport, maxZoom: o.maxZoom, tileSize: tileSizeOf(o.tileUrl) }),
      ),
  );
  // The preview of the panel that starts at a level above this zoom says so in the tooltip of "Preview".
  const draftReason = draft ? zoomReasonOf(draftOverlays, mapZoom, 'the preview') : null;
  if (!draft && !pinned && !overview && !loading) return null;
  return (
    <div className="overlay preview-badge-dock">
      {(draft || pinned) && <Badge tip={[draftReason, previewTitle(draft, draftMeasure)].filter(Boolean).join(' ') || undefined}>Preview</Badge>}
      {loading && (
        <Badge loading role="status" tip={LOADING_TITLE}>
          Loading…
        </Badge>
      )}
      {overview && <Badge tip={OVERVIEW_TITLE}>Overview</Badge>}
    </div>
  );
}
