// Drags a row of a list with the mouse or a finger by its grip (NM4-65 part 1): pointer events, so that one piece of logic
// serves both, and no library. While a row is dragged the row under the pointer is the place it will take; letting go moves
// it there, Escape and a cancelled pointer drop nothing. The list stays as it is until then. ▲/▼ remain for the keyboard.

import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type RefObject } from 'react';

export interface RowDrag {
  // The row that is dragged and the row under the pointer, both as places of the list.
  from: number;
  over: number;
}

// How near the edge of the list (px) it scrolls along, and by how much per move of the pointer.
const EDGE = 28;
const STEP = 12;

// The place of the row under `y` among `rows`; above the first row is the first, below the last the last.
export function rowAt(rows: readonly { top: number; bottom: number }[], y: number): number {
  if (rows.length === 0) return -1;
  const found = rows.findIndex((row) => y >= row.top && y < row.bottom);
  if (found >= 0) return found;
  return y < rows[0].top ? 0 : rows.length - 1;
}

export function useRowDrag(list: RefObject<HTMLElement | null>, onDrop: (from: number, to: number) => void) {
  const [drag, setDrag] = useState<RowDrag | null>(null);
  const active = useRef<{ from: number; over: number } | null>(null);

  const finish = useCallback(
    (commit: boolean) => {
      const done = active.current;
      active.current = null;
      setDrag(null);
      if (commit && done && done.over !== done.from) onDrop(done.from, done.over);
    },
    [onDrop],
  );

  // Escape while a row is held drops nothing.
  useEffect(() => {
    if (!drag) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') finish(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [drag, finish]);

  const place = useCallback(
    (clientY: number) => {
      const element = list.current;
      if (!element || !active.current) return;
      const box = element.getBoundingClientRect();
      if (clientY < box.top + EDGE) element.scrollTop -= STEP;
      else if (clientY > box.bottom - EDGE) element.scrollTop += STEP;
      const rows = [...element.children].map((child) => child.getBoundingClientRect());
      const over = rowAt(rows, clientY);
      if (over >= 0 && over !== active.current.over) {
        active.current = { ...active.current, over };
        setDrag({ ...active.current });
      }
    },
    [list],
  );

  // What the grip of the row at `index` takes: the pointer is captured, so that the moves arrive wherever it goes.
  const grip = (index: number) => ({
    onPointerDown: (event: ReactPointerEvent<HTMLElement>) => {
      if (event.button !== 0 && event.pointerType === 'mouse') return;
      event.preventDefault();
      event.currentTarget.setPointerCapture?.(event.pointerId);
      active.current = { from: index, over: index };
      setDrag({ from: index, over: index });
    },
    onPointerMove: (event: ReactPointerEvent<HTMLElement>) => {
      if (active.current) place(event.clientY);
    },
    onPointerUp: () => finish(true),
    onPointerCancel: () => finish(false),
  });

  return { drag, grip };
}
