import type { StacItem, TimeStepGroup } from './types';

// Values the source may still replace (M5-58 F1, Otto 19.11.2026): a warning triangle with the text on it, beside the
// time of such a result and beside the date the time slider shows; nothing at the head of a group, which carries no
// tooltip (UI-04 part 3a). The item says so in `earthx:state` (adr/0038 §3.2).
export const PROVISIONAL_TIP = 'Provisional values';

export const isProvisional = (item: StacItem): boolean => item.properties['earthx:state'] === 'provisional';

// A step of the time slider is provisional where one of its items is.
export const groupIsProvisional = (group: TimeStepGroup | undefined): boolean => !!group?.items.some(isProvisional);
