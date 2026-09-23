import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';

// How close to the viewport edge a dragged (or auto-nudged) panel is allowed
// to get — keeps it fully reachable instead of letting it vanish behind the
// edge (V-10).
const SCREEN_MARGIN = 8;
// How long the auto-avoid nudge/restore animates (V-12: "fließend nicht
// sprunghaft" — smooth, not a jump). Never applied while the user is
// actively dragging, which must track the pointer with no lag.
const AVOID_TRANSITION = 'transform 0.28s ease';

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

// Wraps a floating panel and lets the user drag it around by grabbing any
// non-interactive part (or the grip pill at the top). The offset is a translate
// on top of the panel's normal anchored position, so layout stays responsive.
//
// Two extra, opt-in behaviors:
// - `avoidSelector` (V-10, reworked V-12): `off` is the panel's own resting
//   position — wherever the user last put it, or {0,0} at the untouched
//   anchor — and is never rewritten by avoidance itself. On top of it, an
//   auto-nudge (`avoidOffsetX`) pushes the panel right, smoothly, whenever
//   its resting position actually overlaps whatever `avoidSelector` matches;
//   the moment it no longer does (the target moved, or the panel was
//   dragged elsewhere), the nudge eases back to 0 and the panel settles
//   back at exactly that resting position — nothing else remembers or
//   restores it, because nothing else ever needed to move it.
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
  const [dragging, setDragging] = useState(false);
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
    const anchor = anchorRect();
    const el = rootRef.current;
    const avoidEl = document.querySelector(avoidSelector);
    if (!anchor || !el || !avoidEl) {
      setAvoidOffsetX(0);
      return;
    }
    // The panel's *resting* box — anchor plus whatever it was dragged to,
    // ignoring any avoid-nudge already in effect — is what has to actually
    // overlap the target. Testing the anchor alone (as the first version of
    // this did) missed a dragged-but-still-overlapping panel entirely; using
    // the currently rendered (already nudged) box would just keep re-nudging
    // an amount that includes the previous nudge.
    const { x: offX, y: offY } = offRef.current;
    const own = new DOMRect(anchor.left + offX, anchor.top + offY, el.offsetWidth, el.offsetHeight);
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
      if (!drag.current) return;
      drag.current = null;
      setDragging(false);
      document.body.classList.remove('dragging');
      // The drop point may now overlap (or no longer overlap) the avoided
      // element — nothing else triggers this recheck.
      recalcAvoid();
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
  }, [clampToScreen, recalcAvoid]);

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
    // Fold any active avoid-nudge into `off` right where it visually is —
    // grabbing the panel always means "wherever it is now", push included
    // — and zero the nudge for the duration of the drag, so the pointer is
    // the only thing moving it (no double-counting the nudge on top of the
    // drag delta). `recalcAvoid` on release decides fresh whether the
    // dropped spot needs a nudge of its own.
    const startX = off.x + avoidOffsetX;
    const startY = off.y;
    drag.current = { mx: e.clientX, my: e.clientY, ox: startX, oy: startY };
    setOff({ x: startX, y: startY });
    setAvoidOffsetX(0);
    setDragging(true);
    document.body.classList.add('dragging');
  };

  const totalX = off.x + avoidOffsetX;
  return (
    <div
      ref={rootRef}
      className={`draggable${className ? ` ${className}` : ''}`}
      style={{
        transform: totalX || off.y ? `translate(${totalX}px, ${off.y}px)` : undefined,
        transition: avoidSelector && !dragging ? AVOID_TRANSITION : undefined,
      }}
      onPointerDown={onPointerDown}
    >
      <span className="drag-grip" title="Drag to move" aria-hidden="true" />
      {children}
    </div>
  );
}
