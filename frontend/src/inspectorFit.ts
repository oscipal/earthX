// The settings bar never scrolls (UI-12 (12), F3, Otto: "Panels scrollen nie"). What does not fit is made to, step by step, each step only
// while the content still overflows:
//   1. in a wide window the bar takes another column (up to `MAX_COLUMNS`, while the map keeps `MIN_MAP` beside it and the panel of the rail);
//   2. "Quick processing" shows fewer rows a page (UI-12 (4)), down to one;
//   3. the sections fold from the bottom; their head opens them again. The first ("Display") is what the bar is for and folds only for a
//      section opened by hand, which never folds by itself.
// A change of the window or of the content starts again from one column, all rows and nothing folded.

export const COLUMN_WIDTH = 320;
export const MAX_COLUMNS = 3;
// What a wider bar leaves of the map at least.
export const MIN_MAP = 240;

export interface Fit {
  columns: number;
  // Rows of "Quick processing" a page; `Infinity` for all.
  quickRows: number;
  // How many sections are folded, from the bottom.
  folds: number;
}

export const START: Fit = { columns: 1, quickRows: Number.POSITIVE_INFINITY, folds: 0 };

// The columns a window allows: the bar beside the rail, the panel of the rail when it is open, and the least map.
export function maxColumns(windowWidth: number, taken: number): number {
  if (windowWidth < 900) return 1;
  return Math.max(1, Math.min(MAX_COLUMNS, Math.floor((windowWidth - taken - MIN_MAP) / COLUMN_WIDTH)));
}

// The next step for a bar that overflows, or `null` when nothing is left to do. `quickRowsShown` is the rows "Quick processing" has now
// (0 without it), `sections` the number of sections that may fold (`foldOrder`).
export function nextFit(fit: Fit, limits: { maxColumns: number; quickRowsShown: number; sections: number }): Fit | null {
  if (fit.columns < limits.maxColumns) return { ...fit, columns: fit.columns + 1 };
  if (limits.quickRowsShown > 1) return { ...fit, quickRows: limits.quickRowsShown - 1 };
  if (fit.folds < limits.sections) return { ...fit, folds: fit.folds + 1 };
  return null;
}

// The order in which the sections fold: from the bottom, the one opened by hand never, the first only for one opened by hand.
export function foldOrder(titles: readonly string[], openedLast: string | null): string[] {
  const [first, ...rest] = titles;
  const order = rest.reverse().filter((title) => title !== openedLast);
  if (openedLast !== null && first !== undefined && first !== openedLast) order.push(first);
  return order;
}

export const foldedSections = (titles: readonly string[], folds: number, openedLast: string | null): Set<string> =>
  new Set(foldOrder(titles, openedLast).slice(0, folds));
