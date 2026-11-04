// The two steps of the tooltips (UI-04 part 3b, Otto, 4.11.2026): `simple` shows only what is needed to use the control; `advanced` shows all.
//
// Simple (a tip without a level): (a) the reason why a control is locked, (b) the name of a button with only an icon that is not obvious
// (Flip through layers, Reverse, Process), (c) the full text of a text that is really cut off, and what stands behind an (i).
// Advanced (`data-tip-level="advanced"`): everything else — buttons with a text, obvious icons (the red x, the eye, the bin, download,
// pencil, plus, the arrow back, the grip), labels, values, datasets, groups and names of layers. Nothing is removed in either step.

export type TipLevel = 'simple' | 'advanced';

export const TIP_LEVELS: readonly TipLevel[] = ['simple', 'advanced'];

// Until the setting is there (part 4), every tip shows: the behaviour before the steps.
let current: TipLevel = 'advanced';

export const currentTipLevel = (): TipLevel => current;

export function setTipLevel(level: TipLevel): void {
  current = level;
}

// A locked control shows its reason in either step: the reason is case (a), whatever level its tip carries for the unlocked control.
const LOCKED = ':disabled, [aria-disabled="true"]';

export function tipShown(element: Element, level: TipLevel): boolean {
  if (level === 'advanced') return true;
  return element.getAttribute('data-tip-level') !== 'advanced' || element.matches(LOCKED);
}
