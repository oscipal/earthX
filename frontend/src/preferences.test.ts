import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { BASEMAP_IDS } from './basemaps';
import { forgetJobsWindow, loadAddedDatasets, loadAppearance, loadBasemap, loadOverlays, loadProjection, loadResultsOnMap, loadTerrain, loadTipLevel, migrateReliefBasemap, saveAddedDatasets, saveAppearance, saveBasemap, saveOverlays, saveProjection, saveResultsOnMap, saveTerrain, saveTipLevel, themeOf } from './preferences';

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

const BLOCKED = {
  localStorage: {
    getItem: () => {
      throw new Error('blocked');
    },
    setItem: () => {
      throw new Error('blocked');
    },
  },
};

describe('loadAppearance (UI-04 part 4)', () => {
  it('defaults to dark when nothing is stored', () => {
    expect(loadAppearance()).toBe('dark');
  });

  it.each(['light', 'dark', 'system'] as const)('round-trips %s', (appearance) => {
    saveAppearance(appearance);
    expect(loadAppearance()).toBe(appearance);
  });

  it('keeps the words of the time before "System", so that an old choice holds: tech is dark, normal is light', () => {
    storage.setItem('earthx.theme', 'tech');
    expect(loadAppearance()).toBe('dark');
    storage.setItem('earthx.theme', 'normal');
    expect(loadAppearance()).toBe('light');
    saveAppearance('light');
    expect(storage.getItem('earthx.theme')).toBe('normal');
    saveAppearance('system');
    expect(storage.getItem('earthx.theme')).toBe('system');
  });

  it.each(['', 'not-a-theme', 'light', 'dark', 'SYSTEM', '__proto__'])('falls back to the default on the foreign value %j', (value) => {
    storage.setItem('earthx.theme', value);
    expect(loadAppearance()).toBe('dark');
  });

  it('falls back to the default when localStorage throws (private browsing), and saving does not throw', () => {
    vi.stubGlobal('window', BLOCKED);
    expect(loadAppearance()).toBe('dark');
    expect(() => saveAppearance('light')).not.toThrow();
  });
});

describe('themeOf', () => {
  it('draws the theme that was chosen, whatever the system says', () => {
    expect(themeOf('light', true)).toBe('normal');
    expect(themeOf('dark', false)).toBe('tech');
  });

  it('follows the system for "system"', () => {
    expect(themeOf('system', true)).toBe('tech');
    expect(themeOf('system', false)).toBe('normal');
  });

  it('asks the browser when it is not told, and takes dark where the browser cannot tell', () => {
    expect(themeOf('system')).toBe('tech');
    vi.stubGlobal('window', { localStorage: storage, matchMedia: (query: string) => ({ matches: query.includes('light') }) });
    expect(themeOf('system')).toBe('normal');
    vi.stubGlobal('window', {
      localStorage: storage,
      matchMedia: () => {
        throw new Error('no');
      },
    });
    expect(themeOf('system')).toBe('tech');
  });
});

describe('loadTipLevel (UI-04 part 4)', () => {
  it('is "simple" when nothing is stored', () => {
    expect(loadTipLevel()).toBe('simple');
  });

  it.each(['simple', 'advanced'] as const)('round-trips %s, under the key earthx.tooltips', (level) => {
    saveTipLevel(level);
    expect(storage.getItem('earthx.tooltips')).toBe(level);
    expect(loadTipLevel()).toBe(level);
  });

  it.each(['', 'Advanced', 'all', 'true', '["advanced"]'])('is "simple" for the foreign value %j', (value) => {
    storage.setItem('earthx.tooltips', value);
    expect(loadTipLevel()).toBe('simple');
  });

  it('is "simple" with a storage that is locked, and saving does not throw', () => {
    vi.stubGlobal('window', BLOCKED);
    expect(loadTipLevel()).toBe('simple');
    expect(() => saveTipLevel('advanced')).not.toThrow();
  });
});

describe('the basemap "Relief" of the time before UI-04 part 4', () => {
  it('is no basemap any more: it reads as the default one', () => {
    storage.setItem('earthx.basemap', 'relief');
    expect(loadBasemap()).toBe('satellite');
  });

  it('becomes the default basemap and the overlay Relief, once, in the storage', () => {
    storage.setItem('earthx.basemap', 'relief');
    saveOverlays({ labels: true, graticule: false, relief: false });
    migrateReliefBasemap();
    expect(storage.getItem('earthx.basemap')).toBe('satellite');
    expect(loadOverlays()).toEqual({ labels: true, graticule: false, relief: true });
  });

  it('does not bring the overlay back when it is switched off afterwards', () => {
    storage.setItem('earthx.basemap', 'relief');
    migrateReliefBasemap();
    saveOverlays({ labels: false, graticule: false, relief: false });
    migrateReliefBasemap();
    expect(loadOverlays().relief).toBe(false);
  });

  it('leaves a browser alone that never chose Relief, or chose another basemap', () => {
    migrateReliefBasemap();
    expect(storage.length).toBe(0);
    saveBasemap('grey');
    migrateReliefBasemap();
    expect(loadBasemap()).toBe('grey');
    expect(loadOverlays().relief).toBe(false);
  });

  it('does not throw with a storage that is locked', () => {
    vi.stubGlobal('window', BLOCKED);
    expect(() => migrateReliefBasemap()).not.toThrow();
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
    expect(loadAppearance()).toBe('dark');
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
    expect([loadBasemap(), loadProjection(), loadAppearance()]).toEqual(['satellite', 'mercator', 'dark']);
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
    expect(loadAppearance()).toBe('dark');
    expect(loadProjection()).toBe('mercator');
  });
});

describe('the old place of the window of the jobs (UI-03c, gone with #283)', () => {
  it('is deleted once, and nothing else with it', () => {
    storage.setItem('earthx.jobsWindow', '{"x":10,"y":10,"width":480,"height":400}');
    saveAppearance('light');
    forgetJobsWindow();
    expect(storage.getItem('earthx.jobsWindow')).toBeNull();
    expect(loadAppearance()).toBe('light');
  });

  it('does nothing for a storage that holds no entry', () => {
    expect(() => forgetJobsWindow()).not.toThrow();
    expect(storage.length).toBe(0);
  });

  it('does not throw when the storage is locked or throws', () => {
    vi.stubGlobal('window', {
      localStorage: {
        removeItem: () => {
          throw new Error('blocked');
        },
      },
    });
    expect(() => forgetJobsWindow()).not.toThrow();
    vi.stubGlobal('window', {
      get localStorage(): Storage {
        throw new DOMException('denied', 'SecurityError');
      },
    });
    expect(() => forgetJobsWindow()).not.toThrow();
  });
});

describe('the datasets of "Search and area" (UI-05 F4)', () => {
  it('are none saved on a first visit', () => {
    expect(loadAddedDatasets()).toBeNull();
  });

  it('round-trip in their order, an empty list included', () => {
    saveAddedDatasets(['b', 'a']);
    expect(storage.getItem('earthx.datasets')).toBe('["b","a"]');
    expect(loadAddedDatasets()).toEqual(['b', 'a']);
    saveAddedDatasets([]);
    expect(loadAddedDatasets()).toEqual([]);
  });

  it.each(['not json', '{"a":1}', '"a"', 'null', '3'])('read %j as nothing saved', (raw) => {
    storage.setItem('earthx.datasets', raw);
    expect(loadAddedDatasets()).toBeNull();
  });

  it('leave out what is no id', () => {
    storage.setItem('earthx.datasets', '["a", 3, null, {"id":"b"}, "c"]');
    expect(loadAddedDatasets()).toEqual(['a', 'c']);
  });

  it('read nothing and write nothing from a storage that is locked, without an error', () => {
    vi.stubGlobal('window', BLOCKED);
    expect(loadAddedDatasets()).toBeNull();
    expect(() => saveAddedDatasets(['a'])).not.toThrow();
  });
});

describe('loadTerrain (UI-06 F12)', () => {
  it('is off when nothing is stored', () => {
    expect(loadTerrain()).toBe(false);
  });

  it.each([true, false])('round-trips %s, under the key earthx.terrain', (on) => {
    saveTerrain(on);
    expect(storage.getItem('earthx.terrain')).toBe(on ? 'on' : 'off');
    expect(loadTerrain()).toBe(on);
  });

  it.each(['', 'On', 'true', '1', 'on ', '3d', '__proto__', '["on"]', '{"on":true}'])('is off for the foreign value %j', (value) => {
    storage.setItem('earthx.terrain', value);
    expect(loadTerrain()).toBe(false);
  });

  it('is off when localStorage cannot be read, and saving into a locked storage does not throw', () => {
    vi.stubGlobal('window', BLOCKED);
    expect(loadTerrain()).toBe(false);
    expect(() => saveTerrain(true)).not.toThrow();
  });

  it('keeps only the switch, apart from the projection and the basemap', () => {
    saveTerrain(true);
    expect(loadProjection()).toBe('mercator');
    expect(loadBasemap()).toBe('satellite');
    expect([...Array(storage.length).keys()].map((i) => storage.key(i))).toEqual(['earthx.terrain']);
  });
});
