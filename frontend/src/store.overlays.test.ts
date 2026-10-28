// @vitest-environment jsdom
//
// UI-02b: the overlays of the "Basemap" menu are kept in the browser. The store reads them when it starts and writes
// them when one is switched; where nothing valid is stored, both are off.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const KEY = 'earthx.overlays';

async function freshStore() {
  vi.resetModules();
  return (await import('./store')).useAppStore;
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('the overlays in the store', () => {
  it('start off with nothing stored', async () => {
    expect((await freshStore()).getState().overlays).toEqual({ labels: false, graticule: false });
  });

  it('start as they were left', async () => {
    window.localStorage.setItem(KEY, '{"labels":true,"graticule":true}');
    expect((await freshStore()).getState().overlays).toEqual({ labels: true, graticule: true });
  });

  it('start off for a stored value that is not an object of booleans', async () => {
    window.localStorage.setItem(KEY, 'labels');
    expect((await freshStore()).getState().overlays).toEqual({ labels: false, graticule: false });
  });

  it('write what is switched, one at a time, and a reload after that starts the same', async () => {
    const store = await freshStore();
    store.getState().setOverlay('graticule', true);
    expect(JSON.parse(window.localStorage.getItem(KEY) ?? '{}')).toEqual({ labels: false, graticule: true });
    store.getState().setOverlay('labels', true);
    store.getState().setOverlay('graticule', false);
    expect(store.getState().overlays).toEqual({ labels: true, graticule: false });
    expect((await freshStore()).getState().overlays).toEqual({ labels: true, graticule: false });
  });

  it('leave the basemap, the projection and the theme alone', async () => {
    const store = await freshStore();
    const before = store.getState();
    store.getState().setOverlay('labels', true);
    expect([store.getState().basemap, store.getState().projection, store.getState().theme]).toEqual([before.basemap, before.projection, before.theme]);
  });

  it('are switched on the page even when the browser keeps nothing', async () => {
    const store = await freshStore();
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() => store.getState().setOverlay('labels', true)).not.toThrow();
    expect(store.getState().overlays.labels).toBe(true);
  });
});
