import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { BASEMAP_IDS } from './basemaps';
import { loadBasemap, loadProjection, loadTheme, saveBasemap, saveProjection, saveTheme } from './preferences';

// No jsdom in this project (Vitest runs plain Node) — a minimal
// localStorage stand-in is enough to exercise the module under test.
function fakeLocalStorage(): Storage {
  const data = new Map<string, string>();
  return {
    getItem: (key: string) => (data.has(key) ? data.get(key)! : null),
    setItem: (key: string, value: string) => {
      data.set(key, value);
    },
    removeItem: (key: string) => {
      data.delete(key);
    },
    clear: () => data.clear(),
    key: (i: number) => [...data.keys()][i] ?? null,
    get length() {
      return data.size;
    },
  };
}

let storage: Storage;

beforeEach(() => {
  storage = fakeLocalStorage();
  vi.stubGlobal('window', { localStorage: storage });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('loadTheme', () => {
  it('defaults to the dark theme when nothing is stored', () => {
    expect(loadTheme()).toBe('tech');
  });

  it('round-trips a saved theme', () => {
    saveTheme('normal');
    expect(loadTheme()).toBe('normal');
  });

  it('falls back to the default on a garbled or foreign value', () => {
    storage.setItem('earthx.theme', 'not-a-theme');
    expect(loadTheme()).toBe('tech');
  });

  it('falls back to the default when localStorage throws (private browsing)', () => {
    vi.stubGlobal('window', {
      localStorage: {
        getItem: () => {
          throw new Error('blocked');
        },
      },
    });
    expect(loadTheme()).toBe('tech');
  });
});

describe('loadProjection', () => {
  it('defaults to the flat map when nothing is stored', () => {
    expect(loadProjection()).toBe('mercator');
  });

  it('round-trips a saved projection', () => {
    saveProjection('globe');
    expect(loadProjection()).toBe('globe');
  });

  it('falls back to the default on a garbled or foreign value', () => {
    storage.setItem('earthx.projection', 'flat-earth');
    expect(loadProjection()).toBe('mercator');
  });

  it('does not throw when localStorage.setItem fails (storage full/disabled)', () => {
    vi.stubGlobal('window', {
      localStorage: {
        setItem: () => {
          throw new Error('quota exceeded');
        },
      },
    });
    expect(() => saveProjection('globe')).not.toThrow();
  });
});

describe('loadBasemap', () => {
  it('defaults to the satellite imagery when nothing is stored', () => {
    expect(loadBasemap()).toBe('satellite');
  });

  it.each(BASEMAP_IDS)('round-trips %s', (id) => {
    saveBasemap(id);
    expect(storage.getItem('earthx.basemap')).toBe(id);
    expect(loadBasemap()).toBe(id);
  });

  it.each(['', 'Streets', 'osm', 'satellite ', '__proto__', 'constructor', '["streets"]'])('falls back to the default on the foreign value %j', (value) => {
    storage.setItem('earthx.basemap', value);
    expect(loadBasemap()).toBe('satellite');
  });

  it('falls back to the default when localStorage cannot be read', () => {
    vi.stubGlobal('window', {
      localStorage: {
        getItem: () => {
          throw new Error('blocked');
        },
      },
    });
    expect(loadBasemap()).toBe('satellite');
  });

  it('does not throw when localStorage.setItem fails (storage full/disabled)', () => {
    vi.stubGlobal('window', {
      localStorage: {
        setItem: () => {
          throw new Error('quota exceeded');
        },
      },
    });
    expect(() => saveBasemap('grey')).not.toThrow();
  });

  it('keeps the basemap apart from the theme and the projection', () => {
    saveBasemap('outlines');
    expect(loadTheme()).toBe('tech');
    expect(loadProjection()).toBe('mercator');
  });
});
