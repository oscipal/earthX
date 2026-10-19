// "Preview" (M4-13c-2): shown over the map while a preview is on it — the one of
// the open processing panel, or a pinned preview layer that is switched on. A
// preview is always coarser than the data (Otto, 19.10.2026; its tiles stop short
// of the data's pixel size, `processingPreview.ts::previewMaxZoom`), so the badge
// does not depend on the zoom.

import { PREVIEW_BADGE_TITLE } from '../processingPreview';
import { useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';

export default function PreviewBadge() {
  const draft = useProcessingStore((s) => s.preview);
  const pinned = useAppStore((s) => s.layers.some((l) => l.visible && l.overlays.some((o) => o.kind === 'raster' && o.preview)));
  if (!draft && !pinned) return null;
  return (
    <div className="overlay preview-badge-dock">
      <span className="preview-badge" title={PREVIEW_BADGE_TITLE}>
        Preview
      </span>
    </div>
  );
}
