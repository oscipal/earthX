// Client-side view preferences (V-1): dark/light HUD theme and flat/globe
// projection. Both are saved per browser (`localStorage`), never sent to the
// backend — the tile URLs and the base map are unaffected either way (D27).

export type Theme = 'tech' | 'normal';
export type Projection = 'mercator' | 'globe';

const THEME_KEY = 'earthx.theme';
const PROJECTION_KEY = 'earthx.projection';

const THEMES: readonly Theme[] = ['tech', 'normal'];
const PROJECTIONS: readonly Projection[] = ['mercator', 'globe'];

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
