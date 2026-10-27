// @vitest-environment jsdom
//
// UI-02a: the "Basemap" button and its menu. Every basemap and every projection can be chosen, the choice reaches
// the store and the browser's storage, and each entry says where its tiles come from.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { BASEMAP_IDS, BASEMAPS } from '../basemaps';
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
  useAppStore.setState({ basemap: 'satellite', projection: 'mercator' });
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
  const found = entries().find((e) => e.textContent === name);
  if (!found) throw new Error(`no entry ${name}`);
  return found;
};
const open = () => act(() => trigger().click());
const choose = (name: string) => act(() => entry(name).click());

describe('the Basemap button', () => {
  it('is called "Basemap" and opens nothing before it is clicked', () => {
    expect(trigger().textContent).toBe('Basemap');
    expect(trigger().getAttribute('aria-expanded')).toBe('false');
    expect(menu()).toBeNull();
  });

  it('opens a menu with a group of basemaps and a group of projections', () => {
    open();
    expect(trigger().getAttribute('aria-expanded')).toBe('true');
    const groups = [...document.querySelectorAll('[role="menu"] [role="group"]')];
    expect(groups.map((g) => g.getAttribute('aria-label'))).toEqual(['Basemap', 'Projection']);
    expect(entries().map((e) => e.textContent)).toEqual(['Satellite', 'Streets', 'Grey', 'Outlines', 'Mercator', 'Globe']);
  });

  it('closes on the second click on the button', () => {
    open();
    open();
    expect(menu()).toBeNull();
  });

  it('has no "Overlays" group yet and no theme entry (Light/Dark is a button of its own)', () => {
    open();
    const text = menu()?.textContent ?? '';
    expect(text).not.toMatch(/Overlays|Labels|Graticule|Light|Dark/u);
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

  it('moves between the entries with the arrow keys, across both groups', () => {
    open();
    act(() => entry('Outlines').focus());
    act(() => document.activeElement!.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true })));
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
