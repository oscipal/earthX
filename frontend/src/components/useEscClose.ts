// Esc closes the settings of a layer (NM4-54, Otto, 1.11.2026), as the red x does: what was applied and not saved goes. Not while a field,
// a menu or a pop-over has its own use for the key, and not for the Esc of the panels at the side, which close themselves.

import { useEffect } from 'react';

export function useEscClose(close: () => void): void {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest?.('input, textarea, select, .popover, [role="menu"], [role="dialog"], .dialog-backdrop, .overlay.dock, .app-rail')) return;
      close();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [close]);
}
