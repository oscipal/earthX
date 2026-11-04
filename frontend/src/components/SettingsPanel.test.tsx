// @vitest-environment jsdom
//
// UI-02a, UI-04 part 4: the panel "Settings" beside the rail. A choice of one is a row of segment buttons, an overlay is a button that is pressed
// while it is on, the tooltips are a switch. The choice reaches the store and the browser's storage (and works when the storage is locked), and
// each button says what it is or where its tiles come from. Opened and closed with its symbol or the red x; Esc closes nothing.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { BASEMAP_IDS, BASEMAPS } from '../basemaps';
import { tipOf } from '../fixtures/tips';
import { NO_OVERLAYS, OVERLAYS } from '../overlays';
import { useAppStore } from '../store';
import { currentTipLevel, setTipLevel } from '../tipLevel';
import SettingsPanel from './SettingsPanel';

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
  container.className = 'app';
  document.body.append(container);
  root = createRoot(container);
  useAppStore.setState({ dock: 'settings', basemap: 'satellite', projection: 'mercator', overlays: { ...NO_OVERLAYS }, appearance: 'dark', theme: 'tech', tipLevel: 'simple' });
  setTipLevel('simple');
  act(() => root.render(<SettingsPanel />));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const group = (name: string): HTMLElement => container.querySelector(`[role="group"][aria-label="${name}"]`) as HTMLElement;
const buttons = (name: string): HTMLButtonElement[] => [...group(name).querySelectorAll<HTMLButtonElement>('button')];
const button = (groupName: string, name: string): HTMLButtonElement => {
  const found = buttons(groupName).find((b) => b.textContent === name);
  if (!found) throw new Error(`no button ${name} in ${groupName}`);
  return found;
};
const pressed = (groupName: string): string[] => buttons(groupName).filter((b) => b.getAttribute('aria-pressed') === 'true').map((b) => b.textContent ?? '');
const click = (el: Element) => act(() => (el as HTMLElement).click());
const tipSwitch = (): HTMLButtonElement => container.querySelector('button[role="switch"]') as HTMLButtonElement;

describe('the panel', () => {
  it('has the head of a panel: the title "Settings" and the red x, and is a region of that name', () => {
    const panel = container.querySelector('.settings-panel')!;
    expect(panel.getAttribute('role')).toBe('region');
    expect(panel.getAttribute('aria-label')).toBe('Settings');
    expect(panel.querySelector('.results-head h2')?.textContent).toBe('Settings');
    const x = panel.querySelector('.results-head button.close-x') as HTMLButtonElement;
    expect(x.getAttribute('aria-label')).toBe('Close');
    expect(panel.classList.contains('dock-panel')).toBe(true);
  });

  it('closes with the red x, and with nothing else: Escape leaves it open (Otto, 2.11.2026)', () => {
    act(() => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
    act(() => container.querySelector('.settings-panel')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
    expect(useAppStore.getState().dock).toBe('settings');
    click(container.querySelector('button.close-x')!);
    expect(useAppStore.getState().dock).toBeNull();
  });

  it('has the five sections Basemap, Overlays, Projection, Appearance and Tooltips', () => {
    expect([...container.querySelectorAll('.settings-heading')].map((h) => h.textContent)).toEqual(['Basemap', 'Overlays', 'Projection', 'Appearance', 'Tooltips']);
    expect(buttons('Basemap').map((b) => b.textContent)).toEqual(['Satellite', 'Streets', 'Grey', 'Outlines']);
    expect(buttons('Overlays').map((b) => b.textContent)).toEqual(['Labels', 'Graticule', 'Relief']);
    expect(buttons('Projection').map((b) => b.textContent)).toEqual(['Mercator', 'Globe']);
    expect(buttons('Appearance').map((b) => b.textContent)).toEqual(['Light', 'Dark', 'System']);
  });

  it('has no list of ticks and no menu: every choice is a button (Otto, 4.11.2026)', () => {
    expect(container.querySelector('[role="menu"], [role^="menuitem"], .menu-tick, [role="radio"], input[type="checkbox"], input[type="radio"]')).toBeNull();
    for (const b of container.querySelectorAll('.settings-row button')) {
      expect(b.classList.contains('btn') && b.classList.contains('seg')).toBe(true);
      expect(b.hasAttribute('aria-pressed')).toBe(true);
    }
  });

  it('has no Relief among the basemaps: Relief is an overlay only (Otto, 3.11.2026)', () => {
    expect(buttons('Basemap').map((b) => b.textContent)).not.toContain('Relief');
    expect(buttons('Overlays').map((b) => b.textContent)).toContain('Relief');
  });

  it('marks the chosen ones at the start: satellite, mercator, dark, no overlay, and the switch left (simple)', () => {
    expect(pressed('Basemap')).toEqual(['Satellite']);
    expect(pressed('Projection')).toEqual(['Mercator']);
    expect(pressed('Appearance')).toEqual(['Dark']);
    expect(pressed('Overlays')).toEqual([]);
    expect(tipSwitch().getAttribute('aria-checked')).toBe('false');
  });
});

describe('choosing a basemap', () => {
  it.each(BASEMAP_IDS)('%s: the choice reaches the store, the storage and the mark', (id) => {
    useAppStore.setState({ basemap: id === 'outlines' ? 'grey' : 'outlines' });
    click(button('Basemap', BASEMAPS[id].name));
    expect(useAppStore.getState().basemap).toBe(id);
    expect(window.localStorage.getItem('earthx.basemap')).toBe(id);
    expect(pressed('Basemap')).toEqual([BASEMAPS[id].name]);
  });

  it.each(BASEMAP_IDS)('%s: the tooltip says where its tiles come from', (id) => {
    expect(tipOf(button('Basemap', BASEMAPS[id].name))).toBe(BASEMAPS[id].tip);
  });

  it('chooses the same basemap twice without harm, and leaves projection and overlays alone', () => {
    click(button('Basemap', 'Grey'));
    click(button('Basemap', 'Grey'));
    expect(useAppStore.getState()).toMatchObject({ basemap: 'grey', projection: 'mercator' });
    expect(pressed('Basemap')).toEqual(['Grey']);
    expect(useAppStore.getState().overlays).toEqual(NO_OVERLAYS);
  });
});

describe('switching an overlay on and off (a button that is pressed while it is on)', () => {
  it.each([
    ['Labels', 'labels'],
    ['Graticule', 'graticule'],
    ['Relief', 'relief'],
  ] as const)('%s: a click switches it on, the next one off, in the store, the storage and the mark', (name, id) => {
    click(button('Overlays', name));
    expect(useAppStore.getState().overlays[id]).toBe(true);
    expect(JSON.parse(window.localStorage.getItem('earthx.overlays') ?? '{}')[id]).toBe(true);
    expect(pressed('Overlays')).toEqual([name]);
    click(button('Overlays', name));
    expect(useAppStore.getState().overlays[id]).toBe(false);
    expect(pressed('Overlays')).toEqual([]);
  });

  it.each(['labels', 'graticule', 'relief'] as const)('%s: the tooltip says what it shows', (id) => {
    expect(tipOf(button('Overlays', OVERLAYS[id].name))).toBe(OVERLAYS[id].tip);
  });

  it('switches one overlay without the other, and leaves basemap and projection alone', () => {
    click(button('Overlays', 'Graticule'));
    click(button('Overlays', 'Labels'));
    expect(pressed('Overlays')).toEqual(['Labels', 'Graticule']);
    expect(useAppStore.getState().overlays).toEqual({ labels: true, graticule: true, relief: false });
    expect([useAppStore.getState().basemap, useAppStore.getState().projection]).toEqual(['satellite', 'mercator']);
  });

  it('is an overlay for every basemap: the marks of the basemaps do not move it', () => {
    click(button('Overlays', 'Labels'));
    click(button('Overlays', 'Relief'));
    for (const id of BASEMAP_IDS) {
      click(button('Basemap', BASEMAPS[id].name));
      expect(pressed('Overlays')).toEqual(['Labels', 'Relief']);
    }
  });
});

describe('choosing a projection', () => {
  it.each([
    ['Mercator', 'mercator'],
    ['Globe', 'globe'],
  ] as const)('%s: the choice reaches the store, the storage and the mark', (name, id) => {
    useAppStore.setState({ projection: id === 'globe' ? 'mercator' : 'globe' });
    click(button('Projection', name));
    expect(useAppStore.getState().projection).toBe(id);
    expect(window.localStorage.getItem('earthx.projection')).toBe(id);
    expect(pressed('Projection')).toEqual([name]);
  });

  it('leaves the basemap alone', () => {
    click(button('Projection', 'Globe'));
    expect(useAppStore.getState().basemap).toBe('satellite');
  });
});

describe('choosing the appearance (Otto, 3.11.2026)', () => {
  it.each([
    ['Light', 'light', 'normal', 'normal'],
    ['Dark', 'dark', 'tech', 'tech'],
    ['System', 'system', 'system', 'tech'],
  ] as const)('%s: reaches the store (the theme that is drawn as well) and the storage under earthx.theme', (name, appearance, stored, theme) => {
    useAppStore.setState({ appearance: name === 'Dark' ? 'light' : 'dark', theme: name === 'Dark' ? 'normal' : 'tech' });
    click(button('Appearance', name));
    expect(useAppStore.getState()).toMatchObject({ appearance, theme });
    expect(window.localStorage.getItem('earthx.theme')).toBe(stored);
    expect(pressed('Appearance')).toEqual([name]);
  });

  it('has its own icon on each: sun, moon and monitor', () => {
    const icon = (name: string) => button('Appearance', name).querySelector('svg')?.getAttribute('class') ?? '';
    expect(icon('Light')).toContain('lucide-sun');
    expect(icon('Dark')).toContain('lucide-moon');
    expect(icon('System')).toContain('lucide-monitor');
  });

  it('"System" follows the colour scheme of the system while the page is open, and the others do not', () => {
    click(button('Appearance', 'System'));
    act(() => useAppStore.getState().followSystemTheme(false));
    expect(useAppStore.getState().theme).toBe('normal');
    act(() => useAppStore.getState().followSystemTheme(true));
    expect(useAppStore.getState().theme).toBe('tech');
    click(button('Appearance', 'Dark'));
    act(() => useAppStore.getState().followSystemTheme(false));
    expect(useAppStore.getState().theme).toBe('tech');
    click(button('Appearance', 'Light'));
    act(() => useAppStore.getState().followSystemTheme(true));
    expect(useAppStore.getState().theme).toBe('normal');
  });
});

describe('the switch of the tooltips (Otto, 4.11.2026)', () => {
  const sides = () => [...container.querySelectorAll('.settings-switch-row > *')].map((e) => e.textContent || e.getAttribute('role'));

  it('has "Simple" at the left, the switch between, "Advanced" at the right, and is left at the start', () => {
    expect(sides()).toEqual(['Simple', 'switch', 'Advanced']);
    expect(tipSwitch().getAttribute('aria-label')).toBe('Advanced tooltips');
    expect(tipSwitch().getAttribute('aria-checked')).toBe('false');
    expect(container.querySelector('.settings-switch-side.on')?.textContent).toBe('Simple');
  });

  it('is not a list of buttons: no segment button, no tick, for something that is on or off', () => {
    expect(container.querySelector('.settings-switch-row .btn')).toBeNull();
  });

  it('a click puts it right ("Advanced") — the store, the step the tooltips are in, the storage — and the next one left again', () => {
    click(tipSwitch());
    expect(tipSwitch().getAttribute('aria-checked')).toBe('true');
    expect(useAppStore.getState().tipLevel).toBe('advanced');
    expect(currentTipLevel()).toBe('advanced');
    expect(window.localStorage.getItem('earthx.tooltips')).toBe('advanced');
    expect(container.querySelector('.settings-switch-side.on')?.textContent).toBe('Advanced');
    click(tipSwitch());
    expect(useAppStore.getState().tipLevel).toBe('simple');
    expect(currentTipLevel()).toBe('simple');
    expect(window.localStorage.getItem('earthx.tooltips')).toBe('simple');
    expect(tipSwitch().getAttribute('aria-checked')).toBe('false');
  });

  it('shows the step that is kept: a browser that kept "advanced" opens with the switch right', () => {
    act(() => useAppStore.setState({ tipLevel: 'advanced' }));
    expect(tipSwitch().getAttribute('aria-checked')).toBe('true');
  });

  it('says in its tooltip what the two steps are', () => {
    expect(tipOf(tipSwitch())).toMatch(/Simple: tooltips only where they are needed.*Advanced: a tooltip on every control/u);
  });
});

describe('a browser that keeps nothing (storage blocked)', () => {
  it('still takes every choice for this visit', () => {
    const setItem = Storage.prototype.setItem;
    Storage.prototype.setItem = () => {
      throw new Error('blocked');
    };
    try {
      click(button('Projection', 'Globe'));
      click(button('Basemap', 'Outlines'));
      click(button('Appearance', 'Light'));
      click(tipSwitch());
      click(button('Overlays', 'Labels'));
    } finally {
      Storage.prototype.setItem = setItem;
    }
    expect(useAppStore.getState()).toMatchObject({ projection: 'globe', basemap: 'outlines', appearance: 'light', theme: 'normal', tipLevel: 'advanced' });
    expect(useAppStore.getState().overlays.labels).toBe(true);
    expect(currentTipLevel()).toBe('advanced');
  });
});
