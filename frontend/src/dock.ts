// Element ids that tie a symbol of the rail to the panel it opens (UI-01 §6.9).
import type { DockPanel } from './store';

export const railButtonId = (panel: DockPanel) => `rail-${panel}`;
export const dockPanelId = (panel: DockPanel) => `dock-${panel}`;
// The Data catalogue is a window, not a panel of the dock (UI-05 §4.1); its symbol and the window share these.
export const CATALOGUE_ID = 'data-catalogue';
export const CATALOGUE_RAIL_ID = 'rail-catalogue';
