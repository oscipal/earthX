// @vitest-environment jsdom
//
// Otto, 27.10.2026: "Hide results" / "Show results" is kept in the browser. The store reads it when it starts, writes it
// when the switch is used (or a new search shows the results), and shows the results where nothing is stored.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const KEY = 'earthx.results';

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

describe('the switch for the results on the map, kept in the browser', () => {
  it('starts on "Show" with nothing stored', async () => {
    expect((await freshStore()).getState().resultsOnMap).toBe(true);
  });

  it('starts as it was left', async () => {
    window.localStorage.setItem(KEY, 'hide');
    expect((await freshStore()).getState().resultsOnMap).toBe(false);
    window.localStorage.setItem(KEY, 'show');
    expect((await freshStore()).getState().resultsOnMap).toBe(true);
  });

  it('starts on "Show" for a stored value that is none of the two', async () => {
    window.localStorage.setItem(KEY, 'maybe');
    expect((await freshStore()).getState().resultsOnMap).toBe(true);
  });

  it('writes what the switch sets, and a reload after that starts the same', async () => {
    const store = await freshStore();
    store.getState().toggleResultsOnMap();
    expect(window.localStorage.getItem(KEY)).toBe('hide');
    expect((await freshStore()).getState().resultsOnMap).toBe(false);
    (await freshStore()).getState().toggleResultsOnMap();
    expect(window.localStorage.getItem(KEY)).toBe('show');
  });

  it('works for the session when the browser keeps nothing', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    const store = await freshStore();
    expect(store.getState().resultsOnMap).toBe(true);
    expect(() => store.getState().toggleResultsOnMap()).not.toThrow();
    expect(store.getState().resultsOnMap).toBe(false);
  });

  it('is not written by the other buttons that touch a view or the results', async () => {
    window.localStorage.setItem(KEY, 'hide');
    const store = await freshStore();
    store.getState().exitFocus();
    store.getState().exitFocus();
    store.getState().clearSearchResults();
    store.getState().clearAll();
    expect(store.getState().resultsOnMap).toBe(false);
    expect(window.localStorage.getItem(KEY)).toBe('hide');
  });
});
