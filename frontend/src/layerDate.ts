// The acquisition date a layer of the layer manager shows (NM4-65 part 3, Otto, 31.10.2026): the day of its scenes in UTC,
// the span of days where they differ, nothing for data without a time axis (`viewKind.ts::viewDates`). The date is looked
// up where the layer is made and kept in it, so that a layer still has it after the search has moved on.

import type { StacItem } from './types';
import { sectionsForView, type ViewSection } from './viewImages';
import { viewDates } from './viewKind';

// The date of the scenes `ids` among `items`; scenes that are not in `items` add nothing.
export function datesOfIds(ids: readonly string[], items: readonly StacItem[]): string | null {
  const wanted = new Set(ids);
  return viewDates(items.filter((item) => wanted.has(item.id)));
}

// Every scene the page knows: those of the last search and of the list as it shows them.
export function knownItems(state: Parameters<typeof sectionsForView>[0]): StacItem[] {
  const seen = new Set<string>();
  return sectionsForView(state)
    .flatMap((section: ViewSection) => section.items)
    .filter((item) => !seen.has(item.id) && seen.add(item.id));
}

// The `date` field of a layer: left out where there is none, so that a layer of data without a time axis carries nothing.
export const dateOf = (date: string | null): { date?: string } => (date ? { date } : {});
