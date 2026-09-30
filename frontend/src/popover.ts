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

const ITEMS = '[role="option"], [role^="menuitem"], button:not(:disabled), a[href]';

export function popoverItems(root: HTMLElement | null): HTMLElement[] {
  return root ? ([...root.querySelectorAll(ITEMS)] as HTMLElement[]) : [];
}

// Focus the chosen entry of an open dropdown, else its first one.
export function focusFirstItem(root: HTMLElement | null): void {
  const all = popoverItems(root);
  (all.find((el) => el.getAttribute('aria-selected') === 'true' || el.getAttribute('aria-checked') === 'true') ?? all[0])?.focus();
}
