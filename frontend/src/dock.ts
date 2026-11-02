// Element ids that tie a symbol of the rail to the panel it opens (UI-01 §6.9).
import type { DockPanel } from './store';

// The symbols of the rail: the panels beside it, and the floating window of the jobs (UI-03c), which is none of them.
export type RailPanel = DockPanel | 'jobs';

export const railButtonId = (panel: RailPanel) => `rail-${panel}`;
export const dockPanelId = (panel: DockPanel) => `dock-${panel}`;
export const JOBS_WINDOW_ID = 'jobs-window';
