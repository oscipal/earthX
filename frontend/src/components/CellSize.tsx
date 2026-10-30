// What the target CRS of a `reproject` step means for its resolution (M4-13c-3,
// plan §3.7): the server's refusal at the CRS field, and under the resolution the
// size of a cell with its unit — for degrees also on the ground.

import { CRS_PATTERN } from '../crsUnit';
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

// Under the resolution field: a lookup of the unit that failed says so.
export function CellSizeError({ code }: { code: FieldValue | undefined }) {
  const entry = useEntry(code);
  if (typeof code !== 'string' || !CRS_PATTERN.test(code) || entry?.state !== 'error') return null;
  return <p className="hint-text warn">The unit of {code} could not be looked up: {entry.message}</p>;
}

// The unit of the resolution, small beside its label (Otto, 30.10.2026): "in m", "in °", or the name of another unit.
// Nothing while the lookup is on its way, where the code is none or the lookup failed.
export function CellSize({ code }: { code: FieldValue | undefined }) {
  const entry = useEntry(code);
  if (typeof code !== 'string' || !CRS_PATTERN.test(code) || entry?.state !== 'ready') return null;
  const { name, kind } = entry.info.unit;
  const unit = name === 'metre' ? 'm' : kind === 'angular' && name === 'degree' ? '°' : name;
  return (
    <span className="pp-unit-line" aria-label="Unit">
      in {unit}
    </span>
  );
}
