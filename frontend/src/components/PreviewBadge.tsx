// "Preview" (M4-13c-2, F4 (1)): shown over the map, and in the processing panel,
// while a tile of a preview is coarser than the data it is made from. A careful
// rule from the pixel size and the zoom, not a measurement
// (`processingPreview.ts::isCoarserThanData`).

import { isCoarserThanData, PREVIEW_BADGE_TITLE } from '../processingPreview';
import { useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';

// Whether any preview on the map — the one of the open panel, or a pinned preview
// layer that is switched on — is coarser than its data at the current view.
function usePreviewBadge(): boolean {
  const mapZoom = useAppStore((s) => s.mapZoom);
  const viewport = useAppStore((s) => s.viewportBbox);
  const layers = useAppStore((s) => s.layers);
  const draft = useProcessingStore((s) => s.preview);
  const coarse = (maxZoom: number, gsd: number | null) => isCoarserThanData({ mapZoom, viewport, maxZoom, gsd });
  if (draft && coarse(draft.maxZoom, draft.gsd)) return true;
  return layers.some(
    (layer) =>
      layer.visible &&
      layer.overlays.some((overlay) => overlay.kind === 'raster' && overlay.preview && coarse(overlay.maxZoom, overlay.preview.gsd)),
  );
}

export default function PreviewBadge() {
  if (!usePreviewBadge()) return null;
  return (
    <div className="overlay preview-badge-dock">
      <span className="preview-badge" title={PREVIEW_BADGE_TITLE}>
        Preview
      </span>
    </div>
  );
}
