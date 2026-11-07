// The pages of dataset buttons in "Search and area" (UI-05 §3.1): two buttons a row, and as many rows as the panel holds
// without scrolling, at least one; the rest goes to the next page. No upper limit (Otto, 07.11.2026, replacing the six of
// 06.11.2026).

export const DATASETS_PER_ROW = 2;
// The rows before the first measurement, and where there is no layout to measure (jsdom).
export const START_DATASET_ROWS = 3;

// The rows that fit: those drawn now, plus as many as the free height (`slack`, negative while the panel scrolls) holds or
// minus as many as it lacks. `rowStep` is the height of one row with its gap; without one (no layout) nothing changes.
export function rowsThatFit(drawn: number, slack: number, rowStep: number): number {
  if (!(rowStep > 0) || !Number.isFinite(slack)) return Math.max(1, drawn);
  return Math.max(1, drawn + Math.floor(slack / rowStep));
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
