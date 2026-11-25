// The pages of "Quick processing" in the settings bar (UI-12 (4), Otto 17.11.2026): as many rows a page as the bar holds without scrolling.
// The bar itself may scroll (Otto, 25.11.2026, F3 new): where it overflows, the page loses a row, down to one; it never gets columns or
// folds a section.

export const QUICK_PER_ROW = 3;

// The rows a page of "Quick processing" has next while the bar overflows with `shown` rows, or `null` when one is left.
export const fewerQuickRows = (shown: number): number | null => (shown > 1 ? shown - 1 : null);
