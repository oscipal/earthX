import { useEffect } from 'react';

import { CRS_DELAY_MS, CRS_PATTERN } from '../crsUnit';
import { useProcessingStore } from '../processingStore';
import type { FieldValue } from '../schemaForm';

// Asks for the unit of the typed CRS code 300 ms after the last keystroke; typing on
// drops the question. A code the store already knows is not asked again.
export function useCrsLookup(code: FieldValue | undefined): void {
  const lookup = useProcessingStore((s) => s.lookupCrs);
  useEffect(() => {
    if (typeof code !== 'string' || !CRS_PATTERN.test(code)) return;
    const known = useProcessingStore.getState().crs[code];
    if (known && known.state !== 'error') return;
    const controller = new AbortController();
    const timer = setTimeout(() => void lookup(code, controller.signal), CRS_DELAY_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [code, lookup]);
}
