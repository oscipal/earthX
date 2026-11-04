import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import { placeTip, type Side } from '../tipPlacement';

// The one tooltip of the app (UI-01 §4). Every element with `data-tip` gets it on hover and on keyboard focus;
// it is drawn in `.app` (where the theme tokens are) beside the panels, not in one, so no panel can cover or cut it off. It goes with the pointer
// or the focus; `Esc` closes nothing (Otto, 2.11.2026). It is hidden from screen
// readers: the element carries the same text as its `aria-label`.

const TIP = '[data-tip]';

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
    document.addEventListener('mouseover', show);
    document.addEventListener('focusin', show);
    document.addEventListener('mouseout', hide);
    document.addEventListener('focusout', hide);
    return () => {
      document.removeEventListener('mouseover', show);
      document.removeEventListener('focusin', show);
      document.removeEventListener('mouseout', hide);
      document.removeEventListener('focusout', hide);
    };
  }, []);

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
    <div ref={box} className="tip-layer" aria-hidden="true" style={at ? { top: at.top, left: at.left } : { visibility: 'hidden' }}>
      {text}
    </div>,
    anchor.closest('.app') ?? document.body,
  );
}
