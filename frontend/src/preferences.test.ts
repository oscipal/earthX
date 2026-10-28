import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { BASEMAP_IDS } from './basemaps';
import { loadBasemap, loadOverlays, loadProjection, loadResultsOnMap, loadTheme, saveBasemap, saveOverlays, saveProjection, saveResultsOnMap, saveTheme } from './preferences';

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

  it.each(['', 'Streets', 'Relief', 'hillshade', 'osm', 'satellite ', '__proto__', 'constructor', '["streets"]'])('falls back to the default on the foreign value %j', (value) => {
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

describe('loadOverlays (UI-02b)', () => {
  it('has all overlays off when nothing is stored', () => {
    expect(loadOverlays()).toEqual({ labels: false, graticule: false, relief: false });
  });

  it.each([
    { labels: true, graticule: false, relief: false },
    { labels: false, graticule: true, relief: false },
    { labels: true, graticule: true, relief: false },
    { labels: false, graticule: false, relief: true },
    { labels: true, graticule: true, relief: true },
  ])('round-trips %j', (overlays) => {
    saveOverlays(overlays);
    expect(loadOverlays()).toEqual(overlays);
  });

  it.each(['', 'null', 'true', '42', '"labels"', '[true, true]', '{', '<html>', '{"labels": 1, "graticule": "true"}', '{"labels": null}'])(
    'has all off for the foreign value %j',
    (value) => {
      storage.setItem('earthx.overlays', value);
      expect(loadOverlays()).toEqual({ labels: false, graticule: false, relief: false });
    },
  );

  it('keeps the one that is valid and drops the one that is not, and ignores unknown keys', () => {
    storage.setItem('earthx.overlays', '{"labels": true, "graticule": "yes", "mgrs": true, "__proto__": {"labels": true}}');
    expect(loadOverlays()).toEqual({ labels: true, graticule: false, relief: false });
  });

  it('reads a value kept before the relief existed as "relief off" and keeps the others (NM4-35)', () => {
    storage.setItem('earthx.overlays', '{"labels":true,"graticule":true}');
    expect(loadOverlays()).toEqual({ labels: true, graticule: true, relief: false });
    storage.setItem('earthx.overlays', '{"relief": "on"}');
    expect(loadOverlays().relief).toBe(false);
  });

  it('has all off when localStorage cannot be read', () => {
    vi.stubGlobal('window', {
      localStorage: {
        getItem: () => {
          throw new Error('blocked');
        },
      },
    });
    expect(loadOverlays()).toEqual({ labels: false, graticule: false, relief: false });
  });

  it('does not throw when localStorage.setItem fails (storage full/disabled)', () => {
    vi.stubGlobal('window', {
      localStorage: {
        setItem: () => {
          throw new Error('quota exceeded');
        },
      },
    });
    expect(() => saveOverlays({ labels: true, graticule: true, relief: false })).not.toThrow();
  });

  it('is kept apart from the basemap and the projection', () => {
    saveOverlays({ labels: true, graticule: true, relief: false });
    expect([loadBasemap(), loadProjection(), loadTheme()]).toEqual(['satellite', 'mercator', 'tech']);
  });
});

describe('loadResultsOnMap (Otto, 27.10.2026)', () => {
  it('is "Show" when nothing is stored', () => {
    expect(loadResultsOnMap()).toBe(true);
  });

  it.each([true, false])('round-trips %s, under the key earthx.results', (on) => {
    saveResultsOnMap(on);
    expect(storage.getItem('earthx.results')).toBe(on ? 'show' : 'hide');
    expect(loadResultsOnMap()).toBe(on);
  });

  it.each(['', 'Hide', 'true', 'false', '0', 'hide ', '__proto__', '["hide"]'])('is "Show" for the foreign value %j', (value) => {
    storage.setItem('earthx.results', value);
    expect(loadResultsOnMap()).toBe(true);
  });

  it('is "Show" when localStorage cannot be read', () => {
    vi.stubGlobal('window', {
      localStorage: {
        getItem: () => {
          throw new Error('blocked');
        },
      },
    });
    expect(loadResultsOnMap()).toBe(true);
  });

  it('does not throw when localStorage.setItem fails (storage full/disabled)', () => {
    vi.stubGlobal('window', {
      localStorage: {
        setItem: () => {
          throw new Error('quota exceeded');
        },
      },
    });
    expect(() => saveResultsOnMap(false)).not.toThrow();
  });

  it('is kept apart from the other preferences', () => {
    saveResultsOnMap(false);
    expect(loadBasemap()).toBe('satellite');
    expect(loadTheme()).toBe('tech');
    expect(loadProjection()).toBe('mercator');
  });
});
