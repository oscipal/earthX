// The two steps of the tooltips (UI-04 part 3b, Otto, 4.11.2026; the switch in "Settings" since part 4): `simple` shows only what is needed to use the
// control; `advanced` shows all.
//
// Simple (a tip without a level): (a) the reason why a control is locked, (b) the name of a button with only an icon that is not obvious
// (Flip through layers, Reverse, Process), (c) the full text of a text that is really cut off, and what stands behind an (i).
// Advanced (`data-tip-level="advanced"`): everything else — buttons with a text, obvious icons (the red x, the eye, the bin, download,
// pencil, plus, the arrow back, the grip), labels, values, datasets, groups and names of layers. Nothing is removed in either step.
//
// The full text of a cut-off text (c) shows in both steps, and only while the text is cut: `data-tip-cut` on the element (UI-04 part 4, Otto, 4.11.2026).

export type TipLevel = 'simple' | 'advanced';

export const TIP_LEVELS: readonly TipLevel[] = ['simple', 'advanced'];
export const DEFAULT_TIP_LEVEL: TipLevel = 'simple';

// The step the tooltips are in; the store sets it from the browser's storage and from the "Settings" menu.
let current: TipLevel = DEFAULT_TIP_LEVEL;

export const currentTipLevel = (): TipLevel => current;

export function setTipLevel(level: TipLevel): void {
  current = level;
}

// A locked control shows its reason in either step: the reason is case (a), whatever level its tip carries for the unlocked control.
const LOCKED = ':disabled, [aria-disabled="true"]';

// A text is cut when its box is narrower than the text (`text-overflow: ellipsis`). The attribute is empty for the element itself, or names the
// element inside it that is cut (a button holding the title in a span). Without the attribute a text is never "cut" in this sense.
export const CUT_ATTRIBUTE = 'data-tip-cut';

export function isCut(element: Element): boolean {
  const selector = element.getAttribute(CUT_ATTRIBUTE);
  const text = selector ? element.querySelector(selector) : element;
  return text !== null && text.scrollWidth > text.clientWidth;
}

export function tipShown(element: Element, level: TipLevel): boolean {
  if (element.hasAttribute(CUT_ATTRIBUTE)) return isCut(element);
  if (level === 'advanced') return true;
  return element.getAttribute('data-tip-level') !== 'advanced' || element.matches(LOCKED);
}
