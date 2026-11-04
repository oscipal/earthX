import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import { placeTip, type Side } from '../tipPlacement';

// The one tooltip of the app (UI-01 §4). Every element with `data-tip` gets it on hover and on keyboard focus;
// it is drawn in `.app` (where the theme tokens are) beside the panels, not in one, so no panel can cover or cut it off. It goes with the pointer
// or the focus; `Esc` closes nothing (Otto, 2.11.2026).
//
// It is the one tooltip (UI-04 part 3a, Otto, 3.11.2026): no element carries a `title`. A screen reader gets the text as the description of
// the element while the tip shows (`aria-describedby`), unless the element is named by the same text. A locked button (`disabled`) gets no
// mouse events in every browser, so it is found by where the pointer is.

const TIP = '[data-tip]';
const TIP_ID = 'tip-layer';
// A locked control: it takes no pointer events (`index.css`), so the pointer is looked for among them.
const LOCKED = ':is(button, input, select, textarea):disabled[data-tip]';

const lockedAt = (x: number, y: number): HTMLElement | null =>
  [...document.querySelectorAll<HTMLElement>(LOCKED)].find((el) => {
    const box = el.getBoundingClientRect();
    return box.width > 0 && x >= box.left && x <= box.right && y >= box.top && y <= box.bottom;
  }) ?? null;

const tipOf = (target: EventTarget | null): HTMLElement | null =>
  target instanceof Element ? (target.closest(TIP) as HTMLElement | null) : null;

export default function TipLayer() {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [at, setAt] = useState<{ top: number; left: number } | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const text = anchor?.getAttribute('data-tip') ?? '';

  useEffect(() => {
    const show = (event: Event) => {
      const el = tipOf(event.target);
      if (el) setAnchor(el);
    };
    const hide = (event: Event) => {
      if (tipOf(event.target)) setAnchor(null);
    };
    const move = (event: MouseEvent) => {
      if (tipOf(event.target)) return;
      const locked = lockedAt(event.clientX, event.clientY);
      setAnchor((was) => locked ?? (was?.matches(LOCKED) ? null : was));
    };
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseover', show);
    document.addEventListener('focusin', show);
    document.addEventListener('mouseout', hide);
    document.addEventListener('focusout', hide);
    return () => {
      document.removeEventListener('mousemove', move);
      document.removeEventListener('mouseover', show);
      document.removeEventListener('focusin', show);
      document.removeEventListener('mouseout', hide);
      document.removeEventListener('focusout', hide);
    };
  }, []);

  // The description of the element while its tip shows.
  useEffect(() => {
    if (!anchor || anchor.getAttribute('aria-label') === text) return undefined;
    const before = anchor.getAttribute('aria-describedby');
    anchor.setAttribute('aria-describedby', [before, TIP_ID].filter(Boolean).join(' '));
    return () => {
      if (before === null) anchor.removeAttribute('aria-describedby');
      else anchor.setAttribute('aria-describedby', before);
    };
  }, [anchor, text]);

  useLayoutEffect(() => {
    setAt(null);
    if (!anchor || !box.current) return;
    if (!anchor.isConnected) {
      setAnchor(null);
      return;
    }
    const place = () => {
      if (!box.current) return;
      const a = anchor.getBoundingClientRect();
      const size = { width: box.current.offsetWidth, height: box.current.offsetHeight };
      const prefer = (anchor.getAttribute('data-tip-side') as Side | null) ?? 'top';
      const { top, left } = placeTip(a, size, { width: window.innerWidth, height: window.innerHeight }, prefer);
      setAt({ top, left });
    };
    place();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [anchor, text]);

  if (!anchor) return null;
  return createPortal(
    <div ref={box} id={TIP_ID} role="tooltip" className="tip-layer" style={at ? { top: at.top, left: at.left } : { visibility: 'hidden' }}>
      {text}
    </div>,
    anchor.closest('.app') ?? document.body,
  );
}
