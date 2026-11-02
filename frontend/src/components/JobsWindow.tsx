// The processing manager as a window of its own (UI-03c, plan §7.9, Otto, 2.11.2026): it floats over the map, is dragged by
// its head and pulled to size at the right and bottom edge, and keeps place and size per browser. Under 900 px it is a sheet
// from the bottom like the settings bar. It closes with the red x and with the symbol in the rail, never with Esc.

import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';

import { JOBS_WINDOW_ID, railButtonId } from '../dock';
import {
  firstBox,
  keepReachable,
  resized,
  SHEET_BELOW,
  STEP,
  STEP_BIG,
  type Box,
  type Edge,
  type View,
} from '../jobsWindow';
import { loadJobsWindow, saveJobsWindow } from '../preferences';
import { useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import ProcessingManager from './ProcessingManager';

const RAIL = 48;
const DOCK = 340;
const GAP = 16;
// What a press on these does by itself: it starts no drag.
const OWN_CLICKS = 'button, a, input, select, textarea, .tip';

const viewOf = (): View => ({ width: window.innerWidth, height: window.innerHeight });

function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(() => window.innerWidth < SHEET_BELOW);
  useEffect(() => {
    const on = () => setNarrow(window.innerWidth < SHEET_BELOW);
    window.addEventListener('resize', on);
    return () => window.removeEventListener('resize', on);
  }, []);
  return narrow;
}

// Where it opens: what was kept, else beside the rail and an open panel. The stored value is kept in the window as well.
function openingBox(): Box {
  const view = viewOf();
  const kept = loadJobsWindow();
  if (kept) return keepReachable(kept, view);
  return firstBox(view, RAIL + (useAppStore.getState().dock ? DOCK : 0) + GAP);
}

export default function JobsWindow() {
  const closeManager = useProcessingStore((s) => s.closeManager);
  const narrow = useNarrow();
  const [box, setBox] = useState<Box>(openingBox);
  const [folded, setFolded] = useState(false);
  // What is being pulled: the head moves the box, a handle changes its size; both from where the press began.
  const pull = useRef<{ edge: Edge | 'move'; x: number; y: number; from: Box; now: Box } | null>(null);

  // A smaller browser window pushes it back inside; what is kept stays as the person left it.
  useEffect(() => {
    const on = () => setBox((b) => keepReachable(b, viewOf()));
    window.addEventListener('resize', on);
    return () => window.removeEventListener('resize', on);
  }, []);

  const start = (edge: Edge | 'move') => (event: PointerEvent<HTMLElement>) => {
    if (narrow || event.button !== 0 || (edge === 'move' && (event.target as HTMLElement).closest(OWN_CLICKS))) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    pull.current = { edge, x: event.clientX, y: event.clientY, from: box, now: box };
    document.body.classList.add('dragging');
  };
  const move = (event: PointerEvent<HTMLElement>) => {
    const p = pull.current;
    if (!p) return;
    const dx = event.clientX - p.x;
    const dy = event.clientY - p.y;
    p.now = p.edge === 'move' ? keepReachable({ ...p.from, x: p.from.x + dx, y: p.from.y + dy }, viewOf()) : resized(p.from, p.edge, dx, dy, viewOf());
    setBox(p.now);
  };
  // Written once, at the end of the drag or of the pull.
  const end = () => {
    const p = pull.current;
    if (!p) return;
    pull.current = null;
    document.body.classList.remove('dragging');
    saveJobsWindow(p.now);
  };

  // The head is a tab stop of its own: the arrow keys move the window, as a drag would.
  const onHeadKey = (event: KeyboardEvent<HTMLElement>) => {
    if (narrow || event.target !== event.currentTarget || event.ctrlKey || event.altKey || event.metaKey) return;
    const step = event.shiftKey ? STEP_BIG : STEP;
    const by = ({ ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] } as Record<string, [number, number] | undefined>)[event.key];
    if (!by) return;
    event.preventDefault();
    const next = keepReachable({ ...box, x: box.x + by[0], y: box.y + by[1] }, viewOf());
    setBox(next);
    saveJobsWindow(next);
  };

  const close = () => {
    closeManager();
    document.getElementById(railButtonId('jobs'))?.focus();
  };

  const handle = (edge: Edge) => (
    <div className={`jw-handle ${edge}`} aria-hidden="true" onPointerDown={start(edge)} onPointerMove={move} onPointerUp={end} onPointerCancel={end} />
  );

  return (
    <div
      id={JOBS_WINDOW_ID}
      className={`jobs-window${narrow ? ' sheet' : ''}${narrow && folded ? ' folded' : ''}`}
      style={narrow ? undefined : { left: box.x, top: box.y, width: box.width, height: box.height }}
    >
      {narrow && (
        <button
          type="button"
          className="pp-grip"
          aria-expanded={!folded}
          aria-label={folded ? 'Show the jobs' : 'Fold the jobs down'}
          title={folded ? 'Show the jobs' : 'Fold the jobs down'}
          onClick={() => setFolded(!folded)}
        >
          {folded ? '▴' : '▾'}
        </button>
      )}
      <ProcessingManager
        chrome={{
          onClose: close,
          headProps: narrow
            ? {}
            : {
                tabIndex: 0,
                title: 'Drag to move; the arrow keys move it too',
                'aria-keyshortcuts': 'ArrowUp ArrowDown ArrowLeft ArrowRight',
                onPointerDown: start('move'),
                onPointerMove: move,
                onPointerUp: end,
                onPointerCancel: end,
                onKeyDown: onHeadKey,
              },
        }}
      />
      {!narrow && (
        <>
          {handle('e')}
          {handle('s')}
          {handle('se')}
        </>
      )}
    </div>
  );
}
