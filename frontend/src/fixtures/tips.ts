// The tooltip of an element (UI-04 part 3a): the one tooltip is `data-tip`, drawn by `TipLayer`; no element carries a `title`.
// An element without a tip has '', as the `title` of an element had.
export const tipOf = (element: Element | null | undefined): string => element?.getAttribute('data-tip') ?? '';
