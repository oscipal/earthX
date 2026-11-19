import type { StacItem, TimeStepGroup } from './types';

// Values the source may still replace (M5-58 F1): no mark, only a tooltip at the date of such a day, in the results and
// on the time slider. The item says so in `earthx:state` (adr/0038 §3.2).
export const PROVISIONAL_TIP = 'Provisional values';

export const isProvisional = (item: StacItem): boolean => item.properties['earthx:state'] === 'provisional';

// The tooltip of a date that stands for `items`: one provisional item makes the date provisional.
export const provisionalTip = (items: readonly StacItem[]): { 'data-tip'?: string } =>
  items.some(isProvisional) ? { 'data-tip': PROVISIONAL_TIP } : {};

export const groupIsProvisional = (group: TimeStepGroup | undefined): boolean => !!group?.items.some(isProvisional);
