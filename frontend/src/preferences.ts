// Client-side view preferences (V-1, UI-02a): dark/light HUD theme, flat/globe
// projection and the basemap. All are saved per browser (`localStorage`), never
// sent to the backend — the tile URLs are unaffected by any of them (D27).

import { BASEMAP_IDS, DEFAULT_BASEMAP, type BasemapId } from './basemaps';

export type Theme = 'tech' | 'normal';
export type Projection = 'mercator' | 'globe';
// The jobs the processing manager lists: those that are neither archived nor expired, the expired ones, or
// all of them (UI-01 §6.10).
export type JobFilter = 'active' | 'expired' | 'all';

const THEME_KEY = 'earthx.theme';
const PROJECTION_KEY = 'earthx.projection';
const BASEMAP_KEY = 'earthx.basemap';
const RESULTS_KEY = 'earthx.results';
const JOB_FILTER_KEY = 'earthx.jobfilter';

const THEMES: readonly Theme[] = ['tech', 'normal'];
const PROJECTIONS: readonly Projection[] = ['mercator', 'globe'];
const JOB_FILTERS: readonly JobFilter[] = ['active', 'expired', 'all'];
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

export function loadTheme(): Theme {
  return readStored(THEME_KEY, THEMES, 'tech');
}

export function saveTheme(theme: Theme): void {
  writeStored(THEME_KEY, theme);
}

export function loadProjection(): Projection {
  return readStored(PROJECTION_KEY, PROJECTIONS, 'mercator');
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
