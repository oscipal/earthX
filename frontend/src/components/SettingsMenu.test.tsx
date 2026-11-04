// @vitest-environment jsdom
//
// UI-02a, UI-04 part 4: the symbol "Settings" at the bottom of the rail and its menu. Every basemap, overlay, projection, appearance and step of
// the tooltips can be chosen, the choice reaches the store and the browser's storage (and works when the storage is locked), and each entry says
// what it is or where its tiles come from.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { BASEMAP_IDS, BASEMAPS } from '../basemaps';
import { NO_OVERLAYS, OVERLAYS } from '../overlays';
import { useAppStore } from '../store';
import { currentTipLevel, setTipLevel } from '../tipLevel';
import SettingsMenu from './SettingsMenu';
import { tipOf } from '../fixtures/tips';

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
  useAppStore.setState({ basemap: 'satellite', projection: 'mercator', overlays: { ...NO_OVERLAYS }, appearance: 'dark', theme: 'tech', tipLevel: 'simple' });
  setTipLevel('simple');
  act(() => root.render(<SettingsMenu buttonRef={() => undefined} tabIndex={0} onFocus={() => undefined} />));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const trigger = (): HTMLButtonElement => container.querySelector('button.rail-settings') as HTMLButtonElement;
const menu = (): HTMLElement | null => document.querySelector('[role="menu"]');
const entries = (): HTMLButtonElement[] => [...document.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]')];
const entry = (name: string): HTMLButtonElement => {
  const found = [...entries(), ...checkboxes()].find((e) => e.textContent === name);
  if (!found) throw new Error(`no entry ${name}`);
  return found;
};
const checkboxes = (): HTMLButtonElement[] => [...document.querySelectorAll<HTMLButtonElement>('[role="menuitemcheckbox"]')];
const overlayEntry = (name: string): HTMLButtonElement => {
  const found = checkboxes().find((e) => e.textContent === name);
  if (!found) throw new Error(`no overlay ${name}`);
  return found;
};
const open = () => act(() => trigger().click());
const choose = (name: string) => act(() => entry(name).click());
const chooseOverlay = (name: string) => act(() => overlayEntry(name).click());

describe('the Settings symbol', () => {
  it('is named "Settings", with the icon and nothing else in it, and opens nothing before it is clicked', () => {
    expect(trigger().getAttribute('aria-label')).toBe('Settings');
    expect(trigger().textContent).toBe('');
    expect(trigger().querySelector('svg')).not.toBeNull();
    expect(trigger().getAttribute('aria-haspopup')).toBe('menu');
    expect(trigger().getAttribute('aria-expanded')).toBe('false');
    expect(menu()).toBeNull();
  });

  it('says "Settings" in its tooltip, to the right of the rail, in the simple step too (the name of an icon that is not clear)', () => {
    expect(tipOf(trigger())).toBe('Settings');
    expect(trigger().getAttribute('data-tip-side')).toBe('right');
    expect(trigger().getAttribute('data-tip-level')).toBeNull();
  });

  it('opens a menu named "Settings" with the groups Basemap, Overlays, Projection, Appearance and Tooltips', () => {
    open();
    expect(trigger().getAttribute('aria-expanded')).toBe('true');
    expect(menu()?.getAttribute('aria-label')).toBe('Settings');
    const groups = [...document.querySelectorAll('[role="menu"] [role="group"]')];
    expect(groups.map((g) => g.getAttribute('aria-label'))).toEqual(['Basemap', 'Overlays', 'Projection', 'Appearance', 'Tooltips']);
    expect(entries().map((e) => e.textContent)).toEqual(['Satellite', 'Streets', 'Grey', 'Outlines', 'Mercator', 'Globe', 'Light', 'Dark', 'System', 'Simple', 'Advanced']);
    expect(checkboxes().map((e) => e.textContent)).toEqual(['Labels', 'Graticule', 'Relief']);
  });

  it('has no "Relief" among the basemaps: Relief is an overlay only (Otto, 3.11.2026)', () => {
    open();
    expect(entries().map((e) => e.textContent)).not.toContain('Relief');
    expect(checkboxes().map((e) => e.textContent)).toContain('Relief');
  });

  it('closes on the second click on the symbol', () => {
    open();
    open();
    expect(menu()).toBeNull();
  });

  it('takes the place of the buttons "Basemap" and "Light/Dark": the menu is the one place for them', () => {
    open();
    expect(document.querySelector('button.basemap-btn')).toBeNull();
    expect(menu()?.textContent).not.toMatch(/Basemap, overlays and projection/u);
  });
});

describe('choosing a basemap', () => {
  it('marks the chosen ones of each group, satellite, mercator, dark and simple at the start', () => {
    open();
    expect(entries().filter((e) => e.getAttribute('aria-checked') === 'true').map((e) => e.textContent)).toEqual(['Satellite', 'Mercator', 'Dark', 'Simple']);
  });

  it.each(BASEMAP_IDS)('%s: the choice reaches the store, the storage and the mark', (id) => {
    open();
    // From another basemap than the one asked for, so that the click has something to change.
    useAppStore.setState({ basemap: id === 'outlines' ? 'grey' : 'outlines' });
    choose(BASEMAPS[id].name);
    expect(useAppStore.getState().basemap).toBe(id);
    expect(window.localStorage.getItem('earthx.basemap')).toBe(id);
    expect(entry(BASEMAPS[id].name).getAttribute('aria-checked')).toBe('true');
    expect(entries().filter((e) => e.getAttribute('aria-checked') === 'true')).toHaveLength(4);
  });

  it.each(BASEMAP_IDS)('%s: the tooltip says where its tiles come from', (id) => {
    open();
    expect(tipOf(entry(BASEMAPS[id].name))).toBe(BASEMAPS[id].tip);
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
    expect(entries().filter((e) => e.getAttribute('aria-checked') === 'true')).toHaveLength(4);
  });
});

describe('switching an overlay on and off', () => {
  it('starts with all off', () => {
    open();
    expect(checkboxes().map((e) => e.getAttribute('aria-checked'))).toEqual(['false', 'false', 'false']);
  });

  it.each([
    ['Labels', 'labels'],
    ['Graticule', 'graticule'],
    ['Relief', 'relief'],
  ] as const)('%s: a click switches it on, the next one off, in the store, the storage and the mark', (name, id) => {
    open();
    chooseOverlay(name);
    expect(useAppStore.getState().overlays[id]).toBe(true);
    expect(JSON.parse(window.localStorage.getItem('earthx.overlays') ?? '{}')[id]).toBe(true);
    expect(overlayEntry(name).getAttribute('aria-checked')).toBe('true');
    chooseOverlay(name);
    expect(useAppStore.getState().overlays[id]).toBe(false);
    expect(overlayEntry(name).getAttribute('aria-checked')).toBe('false');
  });

  it.each(['labels', 'graticule', 'relief'] as const)('%s: the tooltip says what it shows', (id) => {
    open();
    expect(tipOf(overlayEntry(OVERLAYS[id].name))).toBe(OVERLAYS[id].tip);
  });

  it('switches one overlay without the other, and leaves basemap and projection alone', () => {
    open();
    chooseOverlay('Graticule');
    expect(useAppStore.getState().overlays).toEqual({ labels: false, graticule: true, relief: false });
    expect([useAppStore.getState().basemap, useAppStore.getState().projection]).toEqual(['satellite', 'mercator']);
    expect(menu()).not.toBeNull();
  });

  it('is an overlay for every basemap: the marks of the basemaps do not move it', () => {
    open();
    chooseOverlay('Labels');
    chooseOverlay('Relief');
    for (const id of BASEMAP_IDS) {
      choose(BASEMAPS[id].name);
      expect(overlayEntry('Labels').getAttribute('aria-checked')).toBe('true');
      expect(overlayEntry('Relief').getAttribute('aria-checked')).toBe('true');
    }
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
});

describe('choosing the appearance (Otto, 3.11.2026)', () => {
  it.each([
    ['Light', 'light', 'normal', 'normal'],
    ['Dark', 'dark', 'tech', 'tech'],
    ['System', 'system', 'system', 'tech'],
  ] as const)('%s: reaches the store (the theme that is drawn as well) and the storage under earthx.theme', (name, appearance, stored, theme) => {
    open();
    useAppStore.setState({ appearance: name === 'Dark' ? 'light' : 'dark', theme: name === 'Dark' ? 'normal' : 'tech' });
    choose(name);
    expect(useAppStore.getState()).toMatchObject({ appearance, theme });
    expect(window.localStorage.getItem('earthx.theme')).toBe(stored);
    expect(entry(name).getAttribute('aria-checked')).toBe('true');
  });

  it('offers each with its own icon: sun, moon and monitor', () => {
    open();
    const iconOf = (name: string) => [...entry(name).querySelectorAll('svg')].map((svg) => svg.getAttribute('class') ?? '').find((c) => !c.includes('lucide-check')) ?? '';
    expect(iconOf('Light')).toContain('lucide-sun');
    expect(iconOf('Dark')).toContain('lucide-moon');
    expect(iconOf('System')).toContain('lucide-monitor');
  });

  it('"System" follows the colour scheme of the system while the page is open, and the others do not', () => {
    open();
    choose('System');
    act(() => useAppStore.getState().followSystemTheme(false));
    expect(useAppStore.getState().theme).toBe('normal');
    act(() => useAppStore.getState().followSystemTheme(true));
    expect(useAppStore.getState().theme).toBe('tech');
    choose('Dark');
    act(() => useAppStore.getState().followSystemTheme(false));
    expect(useAppStore.getState().theme).toBe('tech');
    choose('Light');
    act(() => useAppStore.getState().followSystemTheme(true));
    expect(useAppStore.getState().theme).toBe('normal');
  });
});

describe('choosing the tooltips (Otto, 4.11.2026)', () => {
  it('"Advanced" reaches the store, the step the tooltips are in and the storage under earthx.tooltips; "Simple" takes it back', () => {
    open();
    choose('Advanced');
    expect(useAppStore.getState().tipLevel).toBe('advanced');
    expect(currentTipLevel()).toBe('advanced');
    expect(window.localStorage.getItem('earthx.tooltips')).toBe('advanced');
    expect(entry('Advanced').getAttribute('aria-checked')).toBe('true');
    choose('Simple');
    expect(useAppStore.getState().tipLevel).toBe('simple');
    expect(currentTipLevel()).toBe('simple');
    expect(window.localStorage.getItem('earthx.tooltips')).toBe('simple');
  });

  it('says in the tooltip of each what it does', () => {
    open();
    expect(tipOf(entry('Simple'))).toMatch(/where they are needed/u);
    expect(tipOf(entry('Advanced'))).toBe('A tooltip on every control');
  });
});

describe('a browser that keeps nothing (storage blocked)', () => {
  it('still takes every choice for this visit', () => {
    const setItem = Storage.prototype.setItem;
    Storage.prototype.setItem = () => {
      throw new Error('blocked');
    };
    try {
      open();
      choose('Globe');
      choose('Outlines');
      choose('Light');
      choose('Advanced');
      chooseOverlay('Labels');
    } finally {
      Storage.prototype.setItem = setItem;
    }
    expect(useAppStore.getState()).toMatchObject({ projection: 'globe', basemap: 'outlines', appearance: 'light', theme: 'normal', tipLevel: 'advanced' });
    expect(useAppStore.getState().overlays.labels).toBe(true);
    expect(currentTipLevel()).toBe('advanced');
  });
});

describe('the keyboard and the mouse', () => {
  it('opens with the focus on the chosen basemap', () => {
    useAppStore.setState({ basemap: 'grey' });
    open();
    expect(document.activeElement?.textContent).toBe('Grey');
  });

  it('moves between the entries with the arrow keys, across the groups', () => {
    open();
    act(() => entry('Outlines').focus());
    const down = () => act(() => document.activeElement!.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true })));
    down();
    expect(document.activeElement?.textContent).toBe('Labels');
    down();
    down();
    expect(document.activeElement?.textContent).toBe('Relief');
    expect(document.activeElement?.getAttribute('role')).toBe('menuitemcheckbox');
    down();
    expect(document.activeElement?.textContent).toBe('Mercator');
  });

  it('stays open on Escape (Otto, 2.11.2026: Esc closes nothing)', () => {
    open();
    act(() => document.activeElement!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
    expect(menu()).not.toBeNull();
  });

  it('closes on a click beside it', () => {
    open();
    act(() => document.body.dispatchEvent(new Event('pointerdown', { bubbles: true })));
    expect(menu()).toBeNull();
  });
});
