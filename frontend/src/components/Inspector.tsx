// The settings bar (UI-03a, Otto, 2.11.2026): one column at the right edge for the view of the search, the pinned view and the settings of
// a result layer. The content swaps when another view or layer is opened; the bar stays where it is. Under 900 px it is a sheet from the
// bottom with a grip that folds it to its head, as the processing panel is. While the processing panel is open it takes the column; the bar
// stays mounted, hidden, and comes back with what was typed in it.

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react';

import { useColormapPicker } from '../colormapPicker';
import { useProcessingStore } from '../processingStore';
import { COLUMN_WIDTH, START, foldOrder, foldedSections, maxColumns, nextFit, type Fit } from '../inspectorFit';
import { inspectorKindOf } from '../inspectorKind';
import { useAppStore } from '../store';
import { ChevronDownIcon, ChevronUpIcon } from './icons';
import { InspectorFitContext, type InspectorFitState } from '../inspectorFitContext';
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

// The window as the bar sees it: its size and whether the panel of the rail takes room beside it.
function useWindowSize(): { width: number; height: number } {
  const [size, setSize] = useState(() => ({ width: window.innerWidth, height: window.innerHeight }));
  useEffect(() => {
    const resize = () => setSize({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);
  return size;
}

// The bar never scrolls (UI-12 (12), `inspectorFit.ts`): it measures its body after each change of its content and takes the next step while
// the body overflows; a change of the window, of the kind or of a fold by hand starts again from the first.
function useFit(ref: { current: HTMLElement | null }, kind: string): InspectorFitState & { columns: number } {
  const size = useWindowSize();
  const dockOpen = useAppStore((s) => s.dock !== null);
  const [handFolded, setHandFolded] = useState<ReadonlySet<string>>(new Set());
  const [openedLast, setOpenedLast] = useState<string | null>(null);
  const signature = [size.width, size.height, dockOpen, kind, Array.from(handFolded).join(','), openedLast].join('|');
  const [state, setState] = useState<{ signature: string; fit: Fit }>({ signature, fit: START });
  const fit = state.signature === signature ? state.fit : START;
  const [titles, setTitles] = useState<string[]>([]);
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
    if (!body) return;
    const found = [...body.querySelectorAll<HTMLElement>(':scope > .insp-section')].map((el) => el.dataset.title ?? '');
    if (found.join('|') !== titles.join('|')) setTitles(found);
    const overflows = body.scrollHeight > body.clientHeight + 1 || body.scrollWidth > body.clientWidth + 1;
    if (!overflows) return;
    const quick = body.querySelector<HTMLElement>('.vc-quick');
    const quickRowsShown = quick ? Math.min(fit.quickRows, Number(quick.dataset.rows ?? 0)) : 0;
    const taken = Number.parseFloat(getComputedStyle(body).getPropertyValue('--rail-width')) + (dockOpen ? Number.parseFloat(getComputedStyle(body).getPropertyValue('--dock-width')) : 0);
    const next = nextFit(fit, { maxColumns: maxColumns(size.width, taken || 0), quickRowsShown, sections: foldOrder(found, openedLast).length });
    if (next) setState({ signature, fit: next });
  }, [ref, tick, fit, signature, size.width, dockOpen, titles, openedLast]);

  const folded = useMemo(() => {
    const auto = foldedSections(titles, fit.folds, openedLast);
    return new Set([...auto, ...handFolded].filter((t) => t !== openedLast || handFolded.has(t)));
  }, [titles, fit.folds, openedLast, handFolded]);
  const toggle = useCallback(
    (title: string) => {
      if (folded.has(title)) {
        setHandFolded((set) => new Set([...set].filter((t) => t !== title)));
        setOpenedLast(title);
      } else {
        setHandFolded((set) => new Set([...set, title]));
        if (openedLast === title) setOpenedLast(null);
      }
    },
    [folded, openedLast],
  );
  return { folded, toggle, quickRows: fit.quickRows, columns: fit.columns };
}

function Sheet({ kind, hidden }: { kind: 'view' | 'result'; hidden: boolean }) {
  const ref = useRef<HTMLElement>(null);
  const [folded, setFolded] = useState(false);
  const { columns, ...fit } = useFit(ref, kind);
  useSheetHeight(ref);
  // A bar of more columns is wider, and the map, its buttons and its legend move left of it (`--inspector-width` of `.app`).
  useLayoutEffect(() => {
    const app = ref.current?.closest<HTMLElement>('.app');
    if (!app) return undefined;
    if (columns > 1) app.style.setProperty('--inspector-width', `${columns * COLUMN_WIDTH}px`);
    else app.style.removeProperty('--inspector-width');
    return () => {
      app.style.removeProperty('--inspector-width');
    };
  }, [columns]);
  const { folded: foldedSet, toggle, quickRows } = fit;
  const context = useMemo(() => ({ folded: foldedSet, toggle, quickRows }), [foldedSet, toggle, quickRows]);
  return (
    <aside
      ref={ref}
      className={`inspector panel${folded ? ' folded' : ''}`}
      aria-label={kind === 'result' ? 'Layer settings' : 'Image settings'}
      hidden={hidden}
      data-columns={columns > 1 ? columns : undefined}
      style={columns > 1 ? ({ '--columns': columns, width: `${columns * COLUMN_WIDTH}px` } as CSSProperties) : undefined}
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
      <InspectorFitContext.Provider value={context}>{kind === 'view' ? <ViewerControls /> : <ResultControls />}</InspectorFitContext.Provider>
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
