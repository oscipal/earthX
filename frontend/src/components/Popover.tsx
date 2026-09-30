// Every dropdown of the viewer (Otto, 30.09.2026): it lies over what is below it
// instead of pushing it down, stays inside the window — opening upwards when
// there is more room there — closes on Escape and on a click beside it, and is
// worked with the keyboard (arrow keys, Home/End, Enter, Escape, Tab).
//
// Rendered through a portal into `.app`: the panels are moved with `transform`,
// which would make them the containing block of a `position: fixed` child and
// clip it; `.app` carries the theme tokens the dropdown's colours come from.

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';

import { focusFirstItem, placePopover, popoverItems, type Placement } from '../popover';

export default function Popover({
  anchorRef,
  triggerRef = anchorRef,
  open,
  onClose,
  className,
  role,
  ariaLabel,
  focusOnOpen = false,
  children,
}: {
  anchorRef: RefObject<HTMLElement | null>;
  // Where the focus returns on Escape, if not the anchor itself.
  triggerRef?: RefObject<HTMLElement | null>;
  open: boolean;
  onClose: () => void;
  className: string;
  role?: string;
  ariaLabel?: string;
  // Move the focus into the dropdown when it opens (a button opened it); a text
  // field that opens one keeps the focus until the user presses the down arrow.
  focusOnOpen?: boolean;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [placement, setPlacement] = useState<Placement | null>(null);

  useLayoutEffect(() => {
    if (!open) {
      setPlacement(null);
      return;
    }
    let frame = 0;
    const place = () => {
      const anchor = anchorRef.current;
      const content = ref.current;
      if (anchor && content) {
        const rect = anchor.getBoundingClientRect();
        // The panel slid away (a draw tool, the collapse toggle): nothing to hang on.
        if (rect.bottom < 0 || rect.top > window.innerHeight || rect.right < 0 || rect.left > window.innerWidth) {
          onClose();
          return;
        }
        const next = placePopover(rect, content.scrollHeight, { width: window.innerWidth, height: window.innerHeight });
        setPlacement((prev) => (prev && JSON.stringify(prev) === JSON.stringify(next) ? prev : next));
      }
    };
    // The panels scroll and slide and the window resizes: the dropdown follows
    // every frame while it is open.
    const loop = () => {
      place();
      frame = window.requestAnimationFrame(loop);
    };
    place();
    frame = window.requestAnimationFrame(loop);
    return () => window.cancelAnimationFrame(frame);
  }, [open, anchorRef, onClose]);

  // Once per opening, as soon as it is placed (a hidden entry takes no focus).
  const focused = useRef(false);
  useEffect(() => {
    if (!open) {
      focused.current = false;
      return;
    }
    if (focusOnOpen && placement && !focused.current) {
      focused.current = true;
      focusFirstItem(ref.current);
    }
  }, [open, focusOnOpen, placement]);

  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => {
      const target = e.target as Node;
      if (ref.current?.contains(target) || anchorRef.current?.contains(target)) return;
      onClose();
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      onClose();
      if (ref.current?.contains(document.activeElement)) triggerRef.current?.focus();
    };
    document.addEventListener('pointerdown', away);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', away);
      document.removeEventListener('keydown', escape);
    };
  }, [open, onClose, anchorRef, triggerRef]);

  if (!open) return null;
  const host = anchorRef.current?.closest('.app') ?? document.body;

  const onKeyDown = (e: React.KeyboardEvent) => {
    const all = popoverItems(ref.current);
    const at = all.indexOf(document.activeElement as HTMLElement);
    const go = (index: number) => {
      e.preventDefault();
      all[(index + all.length) % all.length]?.focus();
    };
    if (e.key === 'ArrowDown') go(at + 1);
    else if (e.key === 'ArrowUp') go(at < 0 ? all.length - 1 : at - 1);
    else if (e.key === 'Home') go(0);
    else if (e.key === 'End') go(all.length - 1);
    else if (e.key === 'Tab') onClose();
  };

  return createPortal(
    <div
      ref={ref}
      className={`popover ${className}${placement?.above ? ' above' : ''}`}
      role={role}
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
      style={{
        position: 'fixed',
        top: placement?.top ?? 0,
        left: placement?.left ?? 0,
        width: placement?.width,
        maxHeight: placement?.maxHeight,
        visibility: placement ? 'visible' : 'hidden',
      }}
    >
      {children}
    </div>,
    host,
  );
}
