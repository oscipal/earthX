// @vitest-environment jsdom
//
// UI-06: the switch "3D" in the store. It is kept per browser; a permalink opens flat for its view only (F11), and a lost
// graphics context switches it off without forgetting the choice.

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { useAppStore } from './store';

beforeEach(() => {
  localStorage.clear();
  useAppStore.setState({ terrain: false });
});

afterEach(() => {
  localStorage.clear();
});

describe('setTerrain (UI-06 F12)', () => {
  it('keeps the switch in the browser', () => {
    useAppStore.getState().setTerrain(true);
    expect(useAppStore.getState().terrain).toBe(true);
    expect(localStorage.getItem('earthx.terrain')).toBe('on');
    useAppStore.getState().setTerrain(false);
    expect(localStorage.getItem('earthx.terrain')).toBe('off');
  });

  it('switches off for this visit only when asked not to keep it (a lost graphics context)', () => {
    useAppStore.getState().setTerrain(true);
    useAppStore.getState().setTerrain(false, false);
    expect(useAppStore.getState().terrain).toBe(false);
    expect(localStorage.getItem('earthx.terrain')).toBe('on');
  });
});

describe('showSharedLook (UI-06 F11)', () => {
  it('opens a permalink flat and leaves the kept choice alone', () => {
    useAppStore.getState().setTerrain(true);
    useAppStore.getState().showSharedLook({ basemap: 'streets', projection: 'globe' });
    expect(useAppStore.getState().terrain).toBe(false);
    expect(localStorage.getItem('earthx.terrain')).toBe('on');
  });
});
