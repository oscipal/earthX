import { useCallback, useEffect, useLayoutEffect, useRef, type ReactNode } from 'react';

import { useBandPositions, type BandId, type Place } from '../bandPositions';

// How close to the viewport edge a dragged panel is allowed to get — keeps it
// fully reachable instead of letting it vanish behind the edge (V-10).
const SCREEN_MARGIN = 8;

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

// Keeps a band of this size, at this place, completely inside the window.
function keepInWindow(place: Place, width: number, height: number): Place {
  return {
    x: clamp(place.x, SCREEN_MARGIN, Math.max(SCREEN_MARGIN, window.innerWidth - width - SCREEN_MARGIN)),
    y: clamp(place.y, SCREEN_MARGIN, Math.max(SCREEN_MARGIN, window.innerHeight - height - SCREEN_MARGIN)),
  };
}

function setStyle(el: HTMLElement, property: 'transform' | 'marginTop', value: string) {
  if (el.style[property] !== value) el.style[property] = value;
}

// Wraps a floating panel and lets the user drag it around by grabbing any non-interactive part (or the grip pill at
// the top).
//
// A band that was never moved stands where the stack of bands (`.overlay.bottom`) puts it. A band that was moved
// stands at the place on the screen where it was put (`bandPositions.ts`), whatever the other bands do: it takes no
// room in the stack (a negative margin of its own height and the gap), and a translate brings it from where the stack
// would put it to its place, worked out again after every render, every resize of the band or of the stack, and
// every resize of the window. In the same step it is kept completely inside the window.
export default function Draggable({ id, children, className }: { id: BandId; children: ReactNode; className?: string }) {
  // Subscribes to the place: a move renders the band, and `settle` runs after the render.
  useBandPositions((s) => s.places[id]);
  const drag = useRef<{ mx: number; my: number; ox: number; oy: number } | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  const settle = useCallback(() => {
    const el = rootRef.current;
    const stack = el?.parentElement;
    if (!el || !stack) return;
    const wanted = useBandPositions.getState().places[id];
    if (!wanted) {
      setStyle(el, 'transform', '');
      setStyle(el, 'marginTop', '');
      return;
    }
    const gap = parseFloat(getComputedStyle(stack).rowGap) || 0;
    setStyle(el, 'marginTop', `${-(el.offsetHeight + gap)}px`);
    el.style.transform = '';
    const from = el.getBoundingClientRect();
    const kept = keepInWindow(wanted, el.offsetWidth, el.offsetHeight);
    if (kept.x !== wanted.x || kept.y !== wanted.y) useBandPositions.getState().move(id, kept);
    setStyle(el, 'transform', `translate(${kept.x - from.left}px, ${kept.y - from.top}px)`);
  }, [id]);

  useLayoutEffect(() => {
    settle();
  });

  useEffect(() => {
    const el = rootRef.current;
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => settle());
    if (el) observer?.observe(el);
    if (el?.parentElement) observer?.observe(el.parentElement);
    window.addEventListener('resize', settle);
    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', settle);
    };
  }, [settle]);

  useEffect(() => {
    const move = (e: PointerEvent) => {
      const el = rootRef.current;
      if (!drag.current || !el) return;
      const wanted = { x: drag.current.ox + (e.clientX - drag.current.mx), y: drag.current.oy + (e.clientY - drag.current.my) };
      useBandPositions.getState().move(id, keepInWindow(wanted, el.offsetWidth, el.offsetHeight));
    };
    const up = () => {
      if (!drag.current) return;
      drag.current = null;
      document.body.classList.remove('dragging');
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
  }, [id]);

  const onPointerDown = (e: React.PointerEvent) => {
    // Don't hijack clicks on controls — only drag from panel chrome / empty space.
    if (
      (e.target as HTMLElement).closest(
        'button, input, select, textarea, a, [type="range"], .searchbox-results, .result-thumb',
      )
    ) {
      return;
    }
    const at = rootRef.current?.getBoundingClientRect();
    drag.current = { mx: e.clientX, my: e.clientY, ox: at?.left ?? 0, oy: at?.top ?? 0 };
    document.body.classList.add('dragging');
  };

  return (
    <div
      ref={rootRef}
      data-band={id}
      className={`draggable${className ? ` ${className}` : ''}`}
      onPointerDown={onPointerDown}
    >
      <span className="drag-grip" title="Drag to move" aria-hidden="true" />
      {children}
    </div>
  );
}
