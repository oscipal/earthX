// The tooltip of an element (UI-04 part 3a): the one tooltip is `data-tip`, drawn by `TipLayer`; no element carries a `title`.
// An element without a tip has '', as the `title` of an element had.
export const tipOf = (element: Element | null | undefined): string => element?.getAttribute('data-tip') ?? '';

// Every tooltip below `root`, one text: what "behind the (i)" is read from (NM4-22).
export const tipsOf = (root: Element | null | undefined): string => [...(root?.querySelectorAll('[data-tip]') ?? [])].map((el) => el.getAttribute('data-tip')).join('\n');
