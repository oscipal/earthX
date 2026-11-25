// The settings bar (UI-03a, Otto, 2.11.2026): one column at the right edge for the view of the search, the pinned view and the settings of
// a result layer. The content swaps when another view or layer is opened; the bar stays where it is. Under 900 px it is a sheet from the
// bottom with a grip that folds it to its head, as the processing panel is. While the processing panel is open it takes the column; the bar
// stays mounted, hidden, and comes back with what was typed in it.

import { useEffect, useLayoutEffect, useRef, useState } from 'react';

import { useColormapPicker } from '../colormapPicker';
import { useProcessingStore } from '../processingStore';
import { fewerQuickRows } from '../inspectorFit';
import { inspectorKindOf } from '../inspectorKind';
import { useAppStore } from '../store';
import { ChevronDownIcon, ChevronUpIcon } from './icons';
import { QuickRowsContext } from '../inspectorFitContext';
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

// The rows a page of "Quick processing" has (UI-12 (4)): all at first, one fewer while the body of the bar overflows, down to one. A change
// of the window, of the kind or of the image starts again with all.
function useQuickRows(ref: { current: HTMLElement | null }, kind: string): number {
  const [size, setSize] = useState(() => `${window.innerWidth}x${window.innerHeight}`);
  useEffect(() => {
    const resize = () => setSize(`${window.innerWidth}x${window.innerHeight}`);
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);
  const target = useAppStore((s) => (s.focusMode ? `view|${s.viewLayerId ?? ''}|${s.datasetId ?? ''}` : `result|${s.resultViewLayerId ?? ''}`));
  const signature = [size, kind, target].join('|');
  const [state, setState] = useState<{ signature: string; rows: number }>({ signature, rows: Number.POSITIVE_INFINITY });
  const rows = state.signature === signature ? state.rows : Number.POSITIVE_INFINITY;
  const [tick, setTick] = useState(0);

  // Any change of size inside the body (a histogram that arrives, an RGB band with its three rows) asks for a new measurement.
  useEffect(() => {
    const body = ref.current?.querySelector('.insp-body');
    if (!body || typeof ResizeObserver === 'undefined') return undefined;
    const sizes = new ResizeObserver(() => setTick((t) => t + 1));
    const watch = () => {
      sizes.disconnect();
      for (const child of body.children) sizes.observe(child);
    };
    watch();
    const children = new MutationObserver(watch);
    children.observe(body, { childList: true });
    return () => {
      sizes.disconnect();
      children.disconnect();
    };
  }, [ref, kind]);

  useLayoutEffect(() => {
    const body = ref.current?.querySelector<HTMLElement>('.insp-body');
    const quick = body?.querySelector<HTMLElement>('.vc-quick');
    if (!body || !quick || body.scrollHeight <= body.clientHeight + 1) return;
    const next = fewerQuickRows(Math.min(rows, Number(quick.dataset.rows ?? 0)));
    if (next !== null) setState({ signature, rows: next });
  }, [ref, tick, rows, signature]);
  return rows;
}

function Sheet({ kind, hidden }: { kind: 'view' | 'result'; hidden: boolean }) {
  const ref = useRef<HTMLElement>(null);
  const [folded, setFolded] = useState(false);
  const quickRows = useQuickRows(ref, kind);
  useSheetHeight(ref);
  return (
    <aside
      ref={ref}
      className={`inspector panel${folded ? ' folded' : ''}`}
      aria-label={kind === 'result' ? 'Layer settings' : 'Image settings'}
      hidden={hidden}
    >
      <button
        type="button"
        className="pp-grip"
        aria-expanded={!folded}
        aria-label={folded ? 'Show the settings' : 'Fold the settings down'}
        data-tip-level="advanced" data-tip={folded ? 'Show the settings' : 'Fold the settings down'}
        onClick={() => setFolded(!folded)}
      >
        {folded ? <ChevronUpIcon /> : <ChevronDownIcon />}
      </button>
      <QuickRowsContext.Provider value={quickRows}>{kind === 'view' ? <ViewerControls /> : <ResultControls />}</QuickRowsContext.Provider>
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
