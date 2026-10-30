import { CRS_PATTERN, cellSizeText } from '../crsUnit';
import { useProcessingStore } from '../processingStore';
import type { FieldValue } from '../schemaForm';

// What the resolution means in a cell, for the tooltip of its label: the size of a cell, for degrees also on the ground at
// the middle latitude of the area. `null` while there is none to say.
export function useCellSizeTip(
  code: FieldValue | undefined,
  resolution: FieldValue | undefined,
  // The middle latitude of the area the order covers; `null` without one.
  latitude: number | null,
): string | null {
  const entry = useProcessingStore((s) => (typeof code === 'string' ? s.crs[code] : undefined));
  if (typeof code !== 'string' || !CRS_PATTERN.test(code) || entry?.state !== 'ready') return null;
  const typed = typeof resolution === 'string' && resolution.trim() !== '';
  return typed ? cellSizeText(entry.info, Number(resolution), latitude) : null;
}
