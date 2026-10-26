// Element ids that tie a symbol of the rail to the panel it opens (UI-01 §6.9).
import type { DockPanel } from './store';

export const railButtonId = (panel: DockPanel) => `rail-${panel}`;
export const dockPanelId = (panel: DockPanel) => `dock-${panel}`;
