// What the target CRS of a `reproject` step means for its resolution (M4-13c-3,
// plan §3.7): the server's refusal at the CRS field, and under the resolution the
// size of a cell with its unit — for degrees also on the ground.

import { CRS_PATTERN, cellSizeText } from '../crsUnit';
import { useProcessingStore } from '../processingStore';
import type { FieldValue } from '../schemaForm';

function useEntry(code: FieldValue | undefined) {
  return useProcessingStore((s) => (typeof code === 'string' ? s.crs[code] : undefined));
}

// Under the CRS field: the reason the server gave when it turned the code away.
export function CrsRefusal({ code }: { code: FieldValue | undefined }) {
  const entry = useEntry(code);
  if (entry?.state !== 'refused') return null;
  return (
    <p className="hint-text error" role="alert">
      {entry.message}
    </p>
  );
}

// Under the resolution field, once the CRS is a valid code.
export function CellSize({
  code,
  resolution,
  latitude,
}: {
  code: FieldValue | undefined;
  resolution: FieldValue | undefined;
  // The middle latitude of the area the order covers; `null` without one.
  latitude: number | null;
}) {
  const entry = useEntry(code);
  if (typeof code !== 'string' || !CRS_PATTERN.test(code)) return null;
  if (!entry) return <p className="pp-help">Looking up the unit of {code}…</p>;
  if (entry.state === 'refused') return null;
  if (entry.state === 'error') {
    return <p className="hint-text warn">The unit of {code} could not be looked up: {entry.message}</p>;
  }
  const typed = typeof resolution === 'string' && resolution.trim() !== '';
  const text = typed ? cellSizeText(entry.info, Number(resolution), latitude) : null;
  return (
    <p className="pp-help" aria-label="Cell size">
      {text ?? `The resolution is in ${entry.info.unit.name}.`}
    </p>
  );
}
