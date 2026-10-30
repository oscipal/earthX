// Placement of the tooltip layer (`components/TipLayer.tsx`).

const MARGIN = 8;
const GAP = 6;

export type Side = 'top' | 'bottom' | 'right' | 'left';

interface Box {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

// Where a tooltip of `size` goes for an anchor: on the preferred side if it fits there entirely, else on the
// opposite side, then on the other axis; if nowhere fits, on the side with the most room. Always inside the
// window with a margin on each edge.
export function placeTip(
  anchor: Box,
  size: { width: number; height: number },
  viewport: { width: number; height: number },
  prefer: Side = 'top',
): { top: number; left: number; side: Side } {
  const room: Record<Side, number> = {
    top: anchor.top - GAP - MARGIN,
    bottom: viewport.height - anchor.bottom - GAP - MARGIN,
    left: anchor.left - GAP - MARGIN,
    right: viewport.width - anchor.right - GAP - MARGIN,
  };
  const need = (side: Side) => (side === 'top' || side === 'bottom' ? size.height : size.width);
  const opposite: Record<Side, Side> = { top: 'bottom', bottom: 'top', left: 'right', right: 'left' };
  const across: Side[] = prefer === 'top' || prefer === 'bottom' ? ['right', 'left'] : ['top', 'bottom'];
  const order = [prefer, opposite[prefer], ...across];
  const fits = order.find((side) => room[side] >= need(side));
  const side = fits ?? order.reduce((best, next) => (room[next] - need(next) > room[best] - need(best) ? next : best));

  const centreX = (anchor.left + anchor.right) / 2 - size.width / 2;
  const centreY = (anchor.top + anchor.bottom) / 2 - size.height / 2;
  const clampX = (x: number) => Math.max(MARGIN, Math.min(x, viewport.width - MARGIN - size.width));
  const clampY = (y: number) => Math.max(MARGIN, Math.min(y, viewport.height - MARGIN - size.height));
  if (side === 'top') return { side, top: clampY(anchor.top - GAP - size.height), left: clampX(centreX) };
  if (side === 'bottom') return { side, top: clampY(anchor.bottom + GAP), left: clampX(centreX) };
  if (side === 'left') return { side, top: clampY(centreY), left: clampX(anchor.left - GAP - size.width) };
  return { side, top: clampY(centreY), left: clampX(anchor.right + GAP) };
}
