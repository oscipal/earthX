// "Preview" (M4-13c-2): shown over the map while a preview is on it — the one of
// the open processing panel, or a pinned preview layer that is switched on. A
// preview is held coarser than the data (Otto, 19.10.2026; its tiles stop short of
// the data's pixel size, `processingPreview.ts::previewMaxZoom`), or, where the
// data names no pixel size, marked at every zoom: the badge never depends on the zoom.

import { useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';

export default function PreviewBadge() {
  const draft = useProcessingStore((s) => s.preview);
  const pinned = useAppStore((s) => s.layers.some((l) => l.visible && l.overlays.some((o) => o.kind === 'raster' && o.preview)));
  if (!draft && !pinned) return null;
  return (
    <div className="overlay preview-badge-dock">
      <span className="preview-badge">
        Preview
      </span>
    </div>
  );
}
