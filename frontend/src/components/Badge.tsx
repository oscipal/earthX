// The small mark beside a title or over the map: "Preview", "Temporary", "Overview", "Zoom in", "Loading…" (UI-04 part 3b). One shape for all
// of them (`.badge`); the text and what it means (the tooltip) are the caller's.

import type { ReactNode } from 'react';

export default function Badge({ children, tip, loading = false, role }: { children: ReactNode; tip?: string; loading?: boolean; role?: 'status' }) {
  return (
    <span className={loading ? 'badge loading' : 'badge'} role={role} data-tip-level="advanced" data-tip={tip}>
      {children}
    </span>
  );
}
