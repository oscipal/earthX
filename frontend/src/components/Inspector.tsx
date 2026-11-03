// The settings bar (UI-03a, Otto, 2.11.2026): one column at the right edge for the view of the search, the pinned view and the settings of
// a result layer. The content swaps when another view or layer is opened; the bar stays where it is. Under 900 px it is a sheet from the
// bottom with a grip that folds it to its head, as the processing panel is. While the processing panel is open it takes the column; the bar
// stays mounted, hidden, and comes back with what was typed in it.

import { useEffect, useRef, useState } from 'react';

import { useColormapPicker } from '../colormapPicker';
import { useProcessingStore } from '../processingStore';
import { inspectorKindOf } from '../inspectorKind';
import { useAppStore } from '../store';
import ResultControls from './ResultControls';
import ViewerControls from './ViewerControls';

// The height of the sheet under 900 px, for the bands and the map controls that stand above it.
function useSheetHeight(ref: { current: HTMLElement | null }): void {
  useEffect(() => {
    const el = ref.current;
    const app = el?.closest<HTMLElement>('.app');
    if (!el || !app) return undefined;
    const measure = () => app.style.setProperty('--inspector-sheet-height', `${el.getBoundingClientRect().height}px`);
    measure();
    // jsdom has none.
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    observer?.observe(el);
    return () => {
      observer?.disconnect();
      app.style.removeProperty('--inspector-sheet-height');
    };
  }, [ref]);
}

function Sheet({ kind, hidden }: { kind: 'view' | 'result'; hidden: boolean }) {
  const ref = useRef<HTMLElement>(null);
  const [folded, setFolded] = useState(false);
  useSheetHeight(ref);
  return (
    <aside ref={ref} className={`inspector panel${folded ? ' folded' : ''}`} aria-label={kind === 'result' ? 'Layer settings' : 'Image settings'} hidden={hidden}>
      <button
        type="button"
        className="pp-grip"
        aria-expanded={!folded}
        aria-label={folded ? 'Show the settings' : 'Fold the settings down'}
        title={folded ? 'Show the settings' : 'Fold the settings down'}
        onClick={() => setFolded(!folded)}
      >
        {folded ? '▴' : '▾'}
      </button>
      {kind === 'view' ? <ViewerControls /> : <ResultControls />}
    </aside>
  );
}

export default function Inspector() {
  const kind = useAppStore(inspectorKindOf);
  const processingOpen = useProcessingStore((s) => s.open);
  // The list of all colormaps takes the place of the bar while it is open, and gives it back as it was (UI-03d).
  const pickerOpen = useColormapPicker((s) => s.request !== null);
  const open = kind !== null;

  // Esc closes nothing here: the bar is closed with its red x only (Otto, 2.11.2026).

  // Whatever had the focus when the bar opened gets it back when it closes, if it is still there.
  const origin = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!open) return undefined;
    const active = document.activeElement;
    origin.current = active instanceof HTMLElement && active !== document.body && !active.closest('.inspector') ? active : null;
    return () => {
      const back = origin.current;
      origin.current = null;
      if (back?.isConnected) back.focus();
    };
  }, [open]);

  return kind ? <Sheet kind={kind} hidden={processingOpen || pickerOpen} /> : null;
}
