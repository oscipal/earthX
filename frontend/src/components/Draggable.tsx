import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';

// How close to the viewport edge a dragged (or auto-nudged) panel is allowed
// to get — keeps it fully reachable instead of letting it vanish behind the
// edge (V-10).
const SCREEN_MARGIN = 8;

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

// Wraps a floating panel and lets the user drag it around by grabbing any
// non-interactive part (or the grip pill at the top). The offset is a translate
// on top of the panel's normal anchored position, so layout stays responsive.
//
// Two extra, opt-in behaviors (V-10):
// - `avoidSelector`: while the panel is still at its untouched anchor
//   position (never dragged), nudge it right just far enough to clear
//   whatever element `avoidSelector` matches, if and only if they actually
//   overlap — not "whenever that element is open", which would move the
//   panel even when there was nothing in its way. A manual drag always wins
//   over this; it only applies at the default position.
// - The clamp below applies unconditionally to both that nudge and manual
//   dragging: the panel can never end up (partially) past the viewport
//   edge, on open, on drag, or after a resize.
export default function Draggable({
  children,
  className,
  avoidSelector,
  avoidGap = 16,
  recalcTrigger,
}: {
  children: ReactNode;
  className?: string;
  avoidSelector?: string;
  avoidGap?: number;
  // Anything the caller knows changes the avoidance geometry beyond what
  // `avoidSelector`'s own transitions already cover — e.g. this panel going
  // from hidden to shown, which changes its own (auto-sized) anchor rect
  // from empty to its real size. Compared by `Object.is`, like any other
  // effect dependency.
  recalcTrigger?: unknown;
}) {
  const [off, setOff] = useState({ x: 0, y: 0 });
  const [avoidOffsetX, setAvoidOffsetX] = useState(0);
  const drag = useRef<{ mx: number; my: number; ox: number; oy: number } | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  // Read inside callbacks without making them (and the effects that use
  // them) re-run on every drag-move frame.
  const offRef = useRef(off);
  offRef.current = off;

  // The anchor position with no offset applied at all: the parent overlay
  // (`.overlay.right`, `.layermgr`, …) carries the actual `position:
  // absolute; top/left`, and the transform below lives only on this
  // component's own root, so the parent's rect is unaffected by either kind
  // of offset — safe to measure at any time, including while this panel is
  // itself hidden via `display: none` (V-6 keeps it mounted, and hiding
  // that way never touches the parent).
  const anchorRect = useCallback((): DOMRect | null => rootRef.current?.parentElement?.getBoundingClientRect() ?? null, []);

  const recalcAvoid = useCallback(() => {
    if (!avoidSelector) return;
    if (offRef.current.x !== 0 || offRef.current.y !== 0) return; // a manual drag always wins
    const own = anchorRect();
    const avoidEl = document.querySelector(avoidSelector);
    if (!own || !avoidEl) {
      setAvoidOffsetX(0);
      return;
    }
    const avoid = avoidEl.getBoundingClientRect();
    const overlaps = own.left < avoid.right && own.right > avoid.left && own.top < avoid.bottom && own.bottom > avoid.top;
    if (!overlaps) {
      setAvoidOffsetX(0);
      return;
    }
    const nudge = Math.max(0, avoid.right + avoidGap - own.left);
    const maxNudge = Math.max(0, window.innerWidth - SCREEN_MARGIN - own.right);
    setAvoidOffsetX(Math.min(nudge, maxNudge));
  }, [avoidSelector, avoidGap, anchorRect]);

  // Re-check whenever: `recalcTrigger` changes (the caller's own signal —
  // needed because this panel's *own* anchor rect is only correct once it is
  // actually shown: while hidden behind `display: none`, the auto-sized
  // parent it's measured from collapses to nothing, so opening it has to
  // force a fresh measurement); the element to avoid finishes an animated
  // move (its `transitionend`, e.g. the control dock's collapse/expand,
  // which is a `transform`, not a size change no observer would catch on its
  // own); or the viewport changed size.
  useEffect(() => {
    if (!avoidSelector) return;
    recalcAvoid();
    const onTransitionEnd = (e: TransitionEvent) => {
      if (e.propertyName === 'transform') recalcAvoid();
    };
    window.addEventListener('transitionend', onTransitionEnd);
    window.addEventListener('resize', recalcAvoid);
    return () => {
      window.removeEventListener('transitionend', onTransitionEnd);
      window.removeEventListener('resize', recalcAvoid);
    };
  }, [avoidSelector, recalcAvoid, recalcTrigger]);

  // Keeps a candidate (dragX, dragY) — on top of the anchor and any avoid
  // nudge — from putting the panel's box (partially) outside the viewport.
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
      const left = clamp(own.left + avoidOffsetX + dragX, minLeft, maxLeft);
      const top = clamp(own.top + dragY, minTop, maxTop);
      return { x: left - own.left - avoidOffsetX, y: top - own.top };
    },
    [anchorRect, avoidOffsetX],
  );

  useEffect(() => {
    const move = (e: PointerEvent) => {
      if (!drag.current) return;
      const x = drag.current.ox + (e.clientX - drag.current.mx);
      const y = drag.current.oy + (e.clientY - drag.current.my);
      setOff(clampToScreen(x, y));
    };
    const up = () => {
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
  // (window shrunk) — re-clamp whatever offset is already set, auto-nudge
  // included.
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

  const totalX = off.x + avoidOffsetX;
  return (
    <div
      ref={rootRef}
      className={`draggable${className ? ` ${className}` : ''}`}
      style={{ transform: totalX || off.y ? `translate(${totalX}px, ${off.y}px)` : undefined }}
      onPointerDown={onPointerDown}
    >
      <span className="drag-grip" title="Drag to move" aria-hidden="true" />
      {children}
    </div>
  );
}
