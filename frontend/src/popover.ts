// Placement and keyboard helpers of the viewer's dropdowns (`components/Popover.tsx`).

const MARGIN = 8;
const GAP = 4;

export interface Placement {
  top: number;
  left: number;
  width: number;
  maxHeight: number;
  above: boolean;
}

// Where the dropdown goes for an anchor at `anchor` in a window of `viewport`:
// below it if the content fits there or there is at least as much room as above,
// otherwise above; never wider than the window, and scrolling rather than
// running past its edge.
export function placePopover(
  anchor: { top: number; bottom: number; left: number; width: number },
  contentHeight: number,
  viewport: { width: number; height: number },
): Placement {
  const below = viewport.height - anchor.bottom - GAP - MARGIN;
  const aboveRoom = anchor.top - GAP - MARGIN;
  const above = contentHeight > below && aboveRoom > below;
  const maxHeight = Math.max(0, above ? aboveRoom : below);
  const height = Math.min(contentHeight, maxHeight);
  const width = Math.min(anchor.width, viewport.width - 2 * MARGIN);
  const left = Math.min(Math.max(MARGIN, anchor.left), viewport.width - MARGIN - width);
  return { top: above ? anchor.top - GAP - height : anchor.bottom + GAP, left, width, maxHeight, above };
}

// Where a dropdown goes that stands beside its anchor, for an anchor at the edge of the window (the "Settings" symbol at the bottom of the
// rail): to the right of it, its bottom edge on the bottom of the anchor, and moved up as far as it must to stay inside the window.
export function placePopoverBeside(
  anchor: { top: number; bottom: number; right: number },
  contentHeight: number,
  viewport: { width: number; height: number },
  wanted: number,
): Placement {
  const width = Math.min(wanted, viewport.width - 2 * MARGIN);
  const maxHeight = Math.max(0, viewport.height - 2 * MARGIN);
  const height = Math.min(contentHeight, maxHeight);
  const left = Math.min(anchor.right + GAP, viewport.width - MARGIN - width);
  const top = Math.max(MARGIN, Math.min(anchor.bottom - height, viewport.height - MARGIN - height));
  return { top, left, width, maxHeight, above: false };
}

const ITEMS = '[role="option"], [role^="menuitem"], button:not(:disabled), a[href]';

export function popoverItems(root: HTMLElement | null): HTMLElement[] {
  return root ? ([...root.querySelectorAll(ITEMS)] as HTMLElement[]) : [];
}

// Focus the chosen entry of an open dropdown, else its first one. The close "x" of a pop-up is no entry to start with: the
// focus goes to the first thing to work with, and the "x" stays one Tab away (NM4-65).
export function focusFirstItem(root: HTMLElement | null): void {
  const all = popoverItems(root);
  const chosen = all.find((el) => el.getAttribute('aria-selected') === 'true' || el.getAttribute('aria-checked') === 'true');
  (chosen ?? all.find((el) => !el.classList.contains('close-x')) ?? all[0])?.focus();
}
