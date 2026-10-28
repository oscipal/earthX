// @vitest-environment jsdom
//
// UI-02a: the "Basemap" button and its menu. Every basemap and every projection can be chosen, the choice reaches
// the store and the browser's storage, and each entry says where its tiles come from.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { BASEMAP_IDS, BASEMAPS } from '../basemaps';
import { NO_OVERLAYS, OVERLAYS } from '../overlays';
import { useAppStore } from '../store';
import BasemapMenu from './BasemapMenu';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  window.localStorage.clear();
  container = document.createElement('div');
  // The menu opens in `.app` (`Popover`).
  container.className = 'app';
  document.body.append(container);
  root = createRoot(container);
  useAppStore.setState({ basemap: 'satellite', projection: 'mercator', overlays: { ...NO_OVERLAYS } });
  act(() => root.render(<BasemapMenu />));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const trigger = (): HTMLButtonElement => container.querySelector('button.basemap-btn') as HTMLButtonElement;
const menu = (): HTMLElement | null => document.querySelector('[role="menu"]');
const entries = (): HTMLButtonElement[] => [...document.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]')];
const entry = (name: string): HTMLButtonElement => {
  const found = [...entries(), ...checkboxes()].find((e) => e.textContent === name);
  if (!found) throw new Error(`no entry ${name}`);
  return found;
};
const checkboxes = (): HTMLButtonElement[] => [...document.querySelectorAll<HTMLButtonElement>('[role="menuitemcheckbox"]')];
const open = () => act(() => trigger().click());
const choose = (name: string) => act(() => entry(name).click());

describe('the Basemap button', () => {
  it('is called "Basemap" and opens nothing before it is clicked', () => {
    expect(trigger().textContent).toBe('Basemap');
    expect(trigger().getAttribute('aria-expanded')).toBe('false');
    expect(menu()).toBeNull();
  });

  it('opens a menu with a group of basemaps, one of overlays and one of projections', () => {
    open();
    expect(trigger().getAttribute('aria-expanded')).toBe('true');
    const groups = [...document.querySelectorAll('[role="menu"] [role="group"]')];
    expect(groups.map((g) => g.getAttribute('aria-label'))).toEqual(['Basemap', 'Overlays', 'Projection']);
    expect(entries().map((e) => e.textContent)).toEqual(['Satellite', 'Streets', 'Grey', 'Outlines', 'Mercator', 'Globe']);
    expect(checkboxes().map((e) => e.textContent)).toEqual(['Labels', 'Graticule']);
  });

  it('closes on the second click on the button', () => {
    open();
    open();
    expect(menu()).toBeNull();
  });

  it('has no theme entry (Light/Dark is a button of its own)', () => {
    open();
    expect(menu()?.textContent ?? '').not.toMatch(/Light|Dark/u);
  });

  it('is called "Basemap, overlays and projection" in its tooltip', () => {
    expect(trigger().title).toBe('Basemap, overlays and projection');
  });
});

describe('choosing a basemap', () => {
  it('marks the chosen one, satellite at the start', () => {
    open();
    expect(entries().filter((e) => e.getAttribute('aria-checked') === 'true').map((e) => e.textContent)).toEqual(['Satellite', 'Mercator']);
  });

  it.each(BASEMAP_IDS)('%s: the choice reaches the store, the storage and the mark', (id) => {
    open();
    // From another basemap than the one asked for, so that the click has something to change.
    useAppStore.setState({ basemap: id === 'outlines' ? 'grey' : 'outlines' });
    choose(BASEMAPS[id].name);
    expect(useAppStore.getState().basemap).toBe(id);
    expect(window.localStorage.getItem('earthx.basemap')).toBe(id);
    expect(entry(BASEMAPS[id].name).getAttribute('aria-checked')).toBe('true');
    expect(entries().filter((e) => e.getAttribute('aria-checked') === 'true')).toHaveLength(2);
  });

  it.each(BASEMAP_IDS)('%s: the tooltip says where its tiles come from', (id) => {
    open();
    expect(entry(BASEMAPS[id].name).title).toBe(BASEMAPS[id].tip);
  });

  it('leaves the projection alone, and the menu open for the next choice', () => {
    open();
    choose('Streets');
    expect(useAppStore.getState().projection).toBe('mercator');
    expect(menu()).not.toBeNull();
  });

  it('chooses the same basemap twice without harm', () => {
    open();
    choose('Grey');
    choose('Grey');
    expect(useAppStore.getState().basemap).toBe('grey');
    expect(entries().filter((e) => e.getAttribute('aria-checked') === 'true')).toHaveLength(2);
  });
});

describe('switching an overlay on and off', () => {
  it('starts with both off', () => {
    open();
    expect(checkboxes().map((e) => e.getAttribute('aria-checked'))).toEqual(['false', 'false']);
  });

  it.each([
    ['Labels', 'labels'],
    ['Graticule', 'graticule'],
  ] as const)('%s: a click switches it on, the next one off, in the store, the storage and the mark', (name, id) => {
    open();
    choose(name);
    expect(useAppStore.getState().overlays[id]).toBe(true);
    expect(JSON.parse(window.localStorage.getItem('earthx.overlays') ?? '{}')[id]).toBe(true);
    expect(entry(name).getAttribute('aria-checked')).toBe('true');
    choose(name);
    expect(useAppStore.getState().overlays[id]).toBe(false);
    expect(entry(name).getAttribute('aria-checked')).toBe('false');
  });

  it.each(['labels', 'graticule'] as const)('%s: the tooltip says what it shows', (id) => {
    open();
    expect(entry(OVERLAYS[id].name).title).toBe(OVERLAYS[id].tip);
  });

  it('switches one overlay without the other, and leaves basemap and projection alone', () => {
    open();
    choose('Graticule');
    expect(useAppStore.getState().overlays).toEqual({ labels: false, graticule: true });
    expect([useAppStore.getState().basemap, useAppStore.getState().projection]).toEqual(['satellite', 'mercator']);
    expect(menu()).not.toBeNull();
  });

  it('is an overlay for every basemap: the marks of the basemaps do not move it', () => {
    open();
    choose('Labels');
    for (const id of BASEMAP_IDS) {
      choose(BASEMAPS[id].name);
      expect(entry('Labels').getAttribute('aria-checked')).toBe('true');
    }
  });

  it('works when the browser keeps nothing (storage blocked)', () => {
    const setItem = Storage.prototype.setItem;
    Storage.prototype.setItem = () => {
      throw new Error('blocked');
    };
    try {
      open();
      choose('Labels');
    } finally {
      Storage.prototype.setItem = setItem;
    }
    expect(useAppStore.getState().overlays.labels).toBe(true);
  });
});

describe('choosing a projection', () => {
  it.each([
    ['Mercator', 'mercator'],
    ['Globe', 'globe'],
  ] as const)('%s: the choice reaches the store, the storage and the mark', (name, id) => {
    open();
    useAppStore.setState({ projection: id === 'globe' ? 'mercator' : 'globe' });
    choose(name);
    expect(useAppStore.getState().projection).toBe(id);
    expect(window.localStorage.getItem('earthx.projection')).toBe(id);
    expect(entry(name).getAttribute('aria-checked')).toBe('true');
  });

  it('leaves the basemap alone', () => {
    open();
    choose('Globe');
    expect(useAppStore.getState().basemap).toBe('satellite');
  });

  it('works when the browser keeps nothing (storage blocked)', () => {
    const setItem = Storage.prototype.setItem;
    Storage.prototype.setItem = () => {
      throw new Error('blocked');
    };
    try {
      open();
      choose('Globe');
      choose('Outlines');
    } finally {
      Storage.prototype.setItem = setItem;
    }
    expect(useAppStore.getState().projection).toBe('globe');
    expect(useAppStore.getState().basemap).toBe('outlines');
  });
});

describe('the keyboard and the mouse', () => {
  it('opens with the focus on the chosen basemap', () => {
    useAppStore.setState({ basemap: 'grey' });
    open();
    expect(document.activeElement?.textContent).toBe('Grey');
  });

  it('moves between the entries with the arrow keys, across all three groups', () => {
    open();
    act(() => entry('Outlines').focus());
    const down = () => act(() => document.activeElement!.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true })));
    down();
    expect(document.activeElement?.textContent).toBe('Labels');
    down();
    down();
    expect(document.activeElement?.textContent).toBe('Mercator');
  });

  it('closes on Escape and gives the focus back to the button', () => {
    open();
    act(() => document.activeElement!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
    expect(menu()).toBeNull();
    expect(document.activeElement).toBe(trigger());
  });

  it('closes on a click beside it', () => {
    open();
    act(() => document.body.dispatchEvent(new Event('pointerdown', { bubbles: true })));
    expect(menu()).toBeNull();
  });
});
