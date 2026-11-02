// The floating window of the processing manager (UI-03c, plan §7.9): where it stands, how large it is, and how
// both are kept inside the browser window and read back from what was stored.

export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface View {
  width: number;
  height: number;
}

export const DEFAULT_WIDTH = 480;
export const DEFAULT_HEIGHT = 640;
export const MIN_WIDTH = 420;
export const MIN_HEIGHT = 320;
// What is kept in the window, wherever the rest goes: the head, and this much of its width.
export const HEAD_HEIGHT = 44;
export const KEEP_WIDTH = 120;
// The first place: under the row of buttons at the top, as the settings bar's column starts (`top: 64px` in the plan).
export const FIRST_TOP = 64;
// The window never gets higher than the browser window minus this much, when it opens for the first time.
export const FIRST_MARGIN = 80;
// Under this width the window is a sheet from the bottom, as the settings bar is.
export const SHEET_BELOW = 900;
export const STEP = 16;
export const STEP_BIG = 64;

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), Math.max(min, max));

const SANE = 100_000;

// What a stored value may be: four plain numbers, a size not under the minimum, a place from which the window can be reached. A window
// pushed half out at the left has a negative `x` (down to `KEEP_WIDTH - width`, see `keepReachable`), and that is what it is kept as; a
// negative top or a place beyond that is broken. Anything else (no JSON, other types, too small values, `NaN`) is no box.
export function parseBox(raw: unknown): Box | null {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return null;
  const { x, y, width, height } = raw as Record<string, unknown>;
  const numbers = [x, y, width, height];
  if (!numbers.every((n) => typeof n === 'number' && Number.isFinite(n) && Math.abs(n) <= SANE)) return null;
  const [px, py, w, h] = numbers as number[];
  if (w < MIN_WIDTH || h < MIN_HEIGHT || py < 0 || px < KEEP_WIDTH - w) return null;
  return { x: px, y: py, width: w, height: h };
}

// The place of the first opening: right of the rail and of an open panel, under the buttons at the top.
export function firstBox(view: View, left: number): Box {
  const width = clamp(DEFAULT_WIDTH, Math.min(MIN_WIDTH, view.width), view.width);
  const height = clamp(Math.min(DEFAULT_HEIGHT, view.height - FIRST_MARGIN), Math.min(MIN_HEIGHT, view.height), view.height);
  return keepReachable({ x: left, y: FIRST_TOP, width, height }, view);
}

// Size within the minimum and the browser window; the head and `KEEP_WIDTH` of the width stay in the window.
export function keepReachable(box: Box, view: View): Box {
  const width = clamp(box.width, Math.min(MIN_WIDTH, view.width), view.width);
  const height = clamp(box.height, Math.min(MIN_HEIGHT, view.height), view.height);
  return {
    width,
    height,
    x: clamp(box.x, KEEP_WIDTH - width, view.width - KEEP_WIDTH),
    y: clamp(box.y, 0, view.height - HEAD_HEIGHT),
  };
}

export type Edge = 'e' | 's' | 'se';

// The box after a handle was pulled by (dx, dy): the right edge, the bottom edge or the corner; the top left stays.
export function resized(box: Box, edge: Edge, dx: number, dy: number, view: View): Box {
  const width = edge === 's' ? box.width : box.width + dx;
  const height = edge === 'e' ? box.height : box.height + dy;
  return keepReachable({ ...box, width, height }, view);
}
