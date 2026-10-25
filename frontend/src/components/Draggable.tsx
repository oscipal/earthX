import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';

// How close to the viewport edge a dragged panel is allowed to get — keeps it
// fully reachable instead of letting it vanish behind the edge (V-10).
const SCREEN_MARGIN = 8;

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

// Wraps a floating panel and lets the user drag it around by grabbing any
// non-interactive part (or the grip pill at the top). The offset is a translate
// on top of the panel's normal anchored position, so layout stays responsive.
// The clamp below applies to manual dragging and to a resize: the panel can
// never end up (partially) past the viewport edge.
export default function Draggable({ children, className }: { children: ReactNode; className?: string }) {
  const [off, setOff] = useState({ x: 0, y: 0 });
  const drag = useRef<{ mx: number; my: number; ox: number; oy: number } | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  // The anchor position with no offset applied at all: the parent overlay
  // (`.overlay.right`, `.bottom`, …) carries the actual `position:
  // absolute; top/left`, and the transform below lives only on this
  // component's own root, so the parent's rect is unaffected by the offset.
  const anchorRect = useCallback((): DOMRect | null => rootRef.current?.parentElement?.getBoundingClientRect() ?? null, []);

  // Keeps a candidate (dragX, dragY) — on top of the anchor — from putting the
  // panel's box (partially) outside the viewport.
  const clampToScreen = useCallback(
    (dragX: number, dragY: number): { x: number; y: number } => {
      const own = anchorRect();
      const el = rootRef.current;
      if (!own || !el) return { x: dragX, y: dragY };
      const width = el.offsetWidth;
      const height = el.offsetHeight;
      const minLeft = SCREEN_MARGIN;
      const maxLeft = Math.max(minLeft, window.innerWidth - width - SCREEN_MARGIN);
      const minTop = SCREEN_MARGIN;
      const maxTop = Math.max(minTop, window.innerHeight - height - SCREEN_MARGIN);
      const left = clamp(own.left + dragX, minLeft, maxLeft);
      const top = clamp(own.top + dragY, minTop, maxTop);
      return { x: left - own.left, y: top - own.top };
    },
    [anchorRect],
  );

  useEffect(() => {
    const move = (e: PointerEvent) => {
      if (!drag.current) return;
      const x = drag.current.ox + (e.clientX - drag.current.mx);
      const y = drag.current.oy + (e.clientY - drag.current.my);
      setOff(clampToScreen(x, y));
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
  }, [clampToScreen]);

  // A resize can leave a previously in-bounds manual position off-screen
  // (window shrunk) — re-clamp whatever offset is already set.
  useEffect(() => {
    const onResize = () => setOff((current) => clampToScreen(current.x, current.y));
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [clampToScreen]);

  const onPointerDown = (e: React.PointerEvent) => {
    // Don't hijack clicks on controls — only drag from panel chrome / empty space.
    if (
      (e.target as HTMLElement).closest(
        'button, input, select, textarea, a, [type="range"], .searchbox-results, .result-thumb',
      )
    ) {
      return;
    }
    drag.current = { mx: e.clientX, my: e.clientY, ox: off.x, oy: off.y };
    document.body.classList.add('dragging');
  };

  return (
    <div
      ref={rootRef}
      className={`draggable${className ? ` ${className}` : ''}`}
      style={{ transform: off.x || off.y ? `translate(${off.x}px, ${off.y}px)` : undefined }}
      onPointerDown={onPointerDown}
    >
      <span className="drag-grip" title="Drag to move" aria-hidden="true" />
      {children}
    </div>
  );
}
