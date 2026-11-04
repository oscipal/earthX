// Client-side view preferences (V-1, UI-02a, UI-04 part 4): the appearance (light, dark, or the system's), flat/globe
// projection, the basemap, the overlays and the step of the tooltips — the content of the "Settings" menu. All are saved per
// browser (`localStorage`), never sent to the backend — the tile URLs are unaffected by any of them (D27). A storage that is
// locked or throws leaves the default and never breaks the viewer.

import { BASEMAP_IDS, DEFAULT_BASEMAP, type BasemapId } from './basemaps';
import { NO_OVERLAYS, OVERLAY_IDS, type Overlays } from './overlays';
import { TIP_LEVELS, type TipLevel } from './tipLevel';

// What is drawn: `tech` is the dark theme, `normal` the light one (the names of `data-theme` in `tokens.css`).
export type Theme = 'tech' | 'normal';
// What the user chose in "Settings": the system's choice follows `prefers-color-scheme`.
export type Appearance = 'light' | 'dark' | 'system';
export const APPEARANCES: readonly Appearance[] = ['light', 'dark', 'system'];
export const DEFAULT_APPEARANCE: Appearance = 'dark';
export type Projection = 'mercator' | 'globe';
export const DEFAULT_PROJECTION: Projection = 'mercator';
// The jobs the processing manager lists: those that are neither archived, expired nor deleted, the expired ones,
// the deleted ones, or all of them (UI-01 §6.10, NM4-27).
export type JobFilter = 'active' | 'expired' | 'deleted' | 'all';

const THEME_KEY = 'earthx.theme';
const PROJECTION_KEY = 'earthx.projection';
const BASEMAP_KEY = 'earthx.basemap';
const OVERLAYS_KEY = 'earthx.overlays';
const RESULTS_KEY = 'earthx.results';
const TIP_LEVEL_KEY = 'earthx.tooltips';
const JOB_FILTER_KEY = 'earthx.jobfilter';

// What `earthx.theme` holds: the two themes keep the words they had before "System" came (so that a choice made then holds),
// and `system` is the new one.
const STORED_APPEARANCE: Record<Appearance, string> = { light: 'normal', dark: 'tech', system: 'system' };
export const PROJECTIONS: readonly Projection[] = ['mercator', 'globe'];
const JOB_FILTERS: readonly JobFilter[] = ['active', 'expired', 'deleted', 'all'];
const COLLAPSED_GROUPS_KEY = 'earthx.jobgroups.collapsed';

function readStored<T extends string>(key: string, valid: readonly T[], fallback: T): T {
  let raw: string | null;
  try {
    raw = window.localStorage.getItem(key);
  } catch {
    // Private browsing / storage disabled: fall back silently (E5-style — a
    // missing preference only means the default, never a broken viewer).
    return fallback;
  }
  return (valid as readonly string[]).includes(raw ?? '') ? (raw as T) : fallback;
}

function writeStored(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* private browsing / storage disabled — the choice just won't persist */
  }
}

export function loadAppearance(): Appearance {
  const stored = readStored(THEME_KEY, Object.values(STORED_APPEARANCE), STORED_APPEARANCE[DEFAULT_APPEARANCE]);
  return APPEARANCES.find((appearance) => STORED_APPEARANCE[appearance] === stored) ?? DEFAULT_APPEARANCE;
}

export function saveAppearance(appearance: Appearance): void {
  writeStored(THEME_KEY, STORED_APPEARANCE[appearance]);
}

// Whether the system asks for a dark page (`prefers-color-scheme`); a browser that cannot tell is taken as dark, the default look.
export function systemPrefersDark(): boolean {
  try {
    return typeof window.matchMedia !== 'function' || !window.matchMedia('(prefers-color-scheme: light)').matches;
  } catch {
    return true;
  }
}

export const themeOf = (appearance: Appearance, systemDark: boolean = systemPrefersDark()): Theme =>
  appearance === 'light' || (appearance === 'system' && !systemDark) ? 'normal' : 'tech';

// The step of the tooltips (`tipLevel.ts`): `simple` unless the user chose `advanced`.
export function loadTipLevel(): TipLevel {
  return readStored(TIP_LEVEL_KEY, TIP_LEVELS, 'simple');
}

export function saveTipLevel(level: TipLevel): void {
  writeStored(TIP_LEVEL_KEY, level);
}

// "Relief" was a basemap until UI-04 part 4; it is an overlay only. A browser that kept it as its basemap opens with the default basemap and
// the overlay on, and the entry is rewritten once, so that switching the overlay off later is not undone by the old entry.
export function migrateReliefBasemap(): void {
  try {
    if (window.localStorage.getItem(BASEMAP_KEY) !== 'relief') return;
    writeStored(BASEMAP_KEY, DEFAULT_BASEMAP);
    saveOverlays({ ...loadOverlays(), relief: true });
  } catch {
    /* storage disabled or locked: the old entry stays and reads as the default basemap */
  }
}

export function loadProjection(): Projection {
  return readStored(PROJECTION_KEY, PROJECTIONS, DEFAULT_PROJECTION);
}

export function saveProjection(projection: Projection): void {
  writeStored(PROJECTION_KEY, projection);
}

export function loadBasemap(): BasemapId {
  return readStored(BASEMAP_KEY, BASEMAP_IDS, DEFAULT_BASEMAP);
}

export function saveBasemap(basemap: BasemapId): void {
  writeStored(BASEMAP_KEY, basemap);
}

// The overlays that are switched on, stored as JSON like {"labels":true,"graticule":false}. A value that is not
// `true`, an unknown key, anything that is not an object and a storage that cannot be read leave the overlay off.
export function loadOverlays(): Overlays {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(OVERLAYS_KEY) ?? 'null');
    if (!parsed || typeof parsed !== 'object') return { ...NO_OVERLAYS };
    return Object.fromEntries(OVERLAY_IDS.map((id) => [id, (parsed as Record<string, unknown>)[id] === true])) as Overlays;
  } catch {
    return { ...NO_OVERLAYS };
  }
}

export function saveOverlays(overlays: Overlays): void {
  writeStored(OVERLAYS_KEY, JSON.stringify(overlays));
}

// Whether the search results are on the map: the switch "Hide results" / "Show results" (Otto, 27.10.2026). Stored as
// "show" or "hide"; anything else, and a storage that cannot be read, is "show".
export function loadResultsOnMap(): boolean {
  return readStored(RESULTS_KEY, ['show', 'hide'] as const, 'show') === 'show';
}

export function saveResultsOnMap(onMap: boolean): void {
  writeStored(RESULTS_KEY, onMap ? 'show' : 'hide');
}

export function loadJobFilter(): JobFilter {
  return readStored(JOB_FILTER_KEY, JOB_FILTERS, 'active');
}

export function saveJobFilter(filter: JobFilter): void {
  writeStored(JOB_FILTER_KEY, filter);
}

// The place and size the floating window of the jobs kept (UI-03c, gone again with #283): the old entry is deleted once at the start. A
// storage that is locked or throws leaves it where it is, without a message.
const JOBS_WINDOW_KEY = 'earthx.jobsWindow';
export function forgetJobsWindow(): void {
  try {
    window.localStorage.removeItem(JOBS_WINDOW_KEY);
  } catch {
    /* storage disabled or locked: the entry stays, nothing reads it */
  }
}

// The groups of the job manager that are folded up: their ids, and `ungrouped` for the jobs without a group.
export function loadCollapsedGroups(): string[] {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(COLLAPSED_GROUPS_KEY) ?? '[]');
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string').slice(0, 500) : [];
  } catch {
    return [];
  }
}

export function saveCollapsedGroups(ids: readonly string[]): void {
  writeStored(COLLAPSED_GROUPS_KEY, JSON.stringify(ids));
}
