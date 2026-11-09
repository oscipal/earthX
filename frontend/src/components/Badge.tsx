// The small mark beside a title or over the map: "Preview", "Temporary", "Overview", "Zoom in", "Loading…" (UI-04 part 3b). One shape for all
// of them (`.badge`); the text and what it means (the tooltip) are the caller's. A tooltip that explains what the mark means, like the
// notices of a dataset, shows in both steps of the tooltips (`tipLevel.ts`): `simple`.

import type { ReactNode } from 'react';

import type { TipLevel } from '../tipLevel';

export default function Badge({
  children,
  tip,
  loading = false,
  role,
  tipLevel = 'advanced',
}: {
  children: ReactNode;
  tip?: string;
  loading?: boolean;
  role?: 'status';
  tipLevel?: TipLevel;
}) {
  return (
    <span className={loading ? 'badge loading' : 'badge'} role={role} data-tip-level={tipLevel === 'advanced' ? 'advanced' : undefined} data-tip={tip}>
      {children}
    </span>
  );
}
