// Whether the preview is loading and the badge should say so: the panel asks the tiler about it, or the map waits for
// its tiles (`processingStore.ts`: `previewSettling`, `previewTilesLoading`). Only once the wait has lasted a moment, so
// that a warm tile (0.2 s) does not make the badge blink; a cold mosaic takes seconds (NM4-04b, Otto, 28.10.2026:
// 6.0 s cold, 0.16 s warm).

import { useEffect, useState } from 'react';

import { useProcessingStore } from '../processingStore';

export const LOADING_AFTER_MS = 600;
export const LOADING_TITLE = 'Reading the scenes. The first tile of a mosaic can take several seconds.';

export default function usePreviewLoading(): boolean {
  const settling = useProcessingStore((s) => s.previewSettling);
  const tilesLoading = useProcessingStore((s) => s.previewTilesLoading && s.preview !== null);
  const loading = settling || tilesLoading;
  const [held, setHeld] = useState(false);
  useEffect(() => {
    if (!loading) {
      setHeld(false);
      return;
    }
    const timer = setTimeout(() => setHeld(true), LOADING_AFTER_MS);
    return () => clearTimeout(timer);
  }, [loading]);
  return loading && held;
}
