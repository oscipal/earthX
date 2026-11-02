// What the settings bar shows (UI-03a): a view (`focusMode`, also a pinned one), the settings of a result layer, or nothing.

import type { AppState } from './store';

export function inspectorKindOf(s: Pick<AppState, 'focusMode' | 'resultViewLayerId' | 'layers'>): 'view' | 'result' | null {
  if (s.focusMode) return 'view';
  return s.layers.some((l) => l.id === s.resultViewLayerId && l.derived === 'result') ? 'result' : null;
}
