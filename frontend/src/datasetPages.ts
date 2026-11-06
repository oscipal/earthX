// The pages of dataset buttons in "Search and area" (UI-05 §3.1, Otto 06.11.2026): two buttons a row, at most three rows,
// and only as many rows as the panel holds without scrolling, at least one.

export const DATASETS_PER_ROW = 2;
export const MAX_DATASET_ROWS = 3;

// The rows that fit: those drawn now, plus as many as the free height (`slack`, negative while the panel scrolls) holds or
// minus as many as it lacks. `rowStep` is the height of one row with its gap; without one (no layout) nothing changes.
export function rowsThatFit(drawn: number, slack: number, rowStep: number): number {
  if (!(rowStep > 0) || !Number.isFinite(slack)) return Math.min(MAX_DATASET_ROWS, Math.max(1, drawn));
  const rows = drawn + Math.floor(slack / rowStep);
  return Math.min(MAX_DATASET_ROWS, Math.max(1, rows));
}

export function pageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize));
}

// The page that shows the entry at `index`; the first page for one that is not there.
export function pageOf(index: number, pageSize: number): number {
  return index < 0 ? 0 : Math.floor(index / pageSize);
}

export function pageSlice<T>(entries: readonly T[], page: number, pageSize: number): T[] {
  return entries.slice(page * pageSize, (page + 1) * pageSize);
}
