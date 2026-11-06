// @vitest-environment jsdom
//
// The rail at the left edge and the panels beside it (UI-01 §6.9): what each symbol opens, one panel at a
// time, the keyboard, and what the symbols count.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';
import { jobEntry, NOW } from './fixtures/jobEntries';
import type { MapLayer } from './layers';
import { resetJobs, useProcessingStore } from './processingStore';
import { useAppStore } from './store';
import tokens from './tokens.css?raw';

vi.mock('./components/MapView', () => ({ default: () => null }));

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

const layer = (id: string): MapLayer => ({
  id,
  name: `Layer ${id}`,
  visible: true,
  opacity: 1,
  overlays: [{ kind: 'raster', tileUrl: 'https://t/{z}/{x}/{y}', bounds: [0, 0, 1, 1], minZoom: 0, maxZoom: 12 }],
  restore: { datasetId: null, itemIds: [] } as never,
});

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  // The jobs of the fixture are dated by `NOW`.
  vi.useFakeTimers({ toFake: ['Date'], now: NOW });
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ collections: [] }), { status: 200 })));
  useAppStore.setState({ dock: 'controls', layers: [], toolMode: 'none', aoi: null, groups: [], selectedIds: [], focusMode: false });
  useProcessingStore.setState({ open: false, detailJobID: null, jobs: [] });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  act(() => root.render(<App />));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  resetJobs();
  localStorage.clear();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const rail = () => container.querySelector<HTMLElement>('nav[aria-label="Main"]')!;
const symbol = (name: 'controls' | 'catalogue' | 'layers' | 'jobs' | 'results' | 'settings') => container.querySelector<HTMLButtonElement>(`#rail-${name}`)!;
const slot = (name: 'controls' | 'layers' | 'jobs' | 'results' | 'settings') => container.querySelector<HTMLElement>(`#dock-${name}`);
const click = (el: Element) => act(() => el.dispatchEvent(new MouseEvent('click', { bubbles: true })));
const key = (target: Element, name: string) => {
  const event = new KeyboardEvent('keydown', { key: name, bubbles: true, cancelable: true });
  act(() => target.dispatchEvent(event));
  return event;
};
const settings = () => rail().querySelector<HTMLButtonElement>('button.rail-settings')!;
const stops = () => [...rail().querySelectorAll<HTMLElement>('button')].map((b) => b.tabIndex);

describe('the symbols', () => {
  it('are six, in a navigation named "Main", each with its name for a screen reader: four panels, the Data catalogue second and "Settings" at the bottom', () => {
    expect(rail()).not.toBeNull();
    expect([...rail().querySelectorAll('button')].map((b) => b.getAttribute('aria-label'))).toEqual(['Search and area', 'Data catalogue', 'Layers', 'Jobs', 'Search results, No results yet: run a search first', 'Settings']);
  });

  it('carry their tooltip as text that shows on hover and on focus, and no second one as `title`', () => {
    expect([...rail().querySelectorAll('button')].map((b) => b.getAttribute('data-tip'))).toEqual(['Search and area', 'Data catalogue', 'Layers', 'Jobs', 'No results yet: run a search first', 'Settings']);
    expect(rail().querySelector('[title]')).toBeNull();
  });

  it('have an icon that a screen reader skips', () => {
    for (const svg of rail().querySelectorAll('svg')) expect(svg.getAttribute('aria-hidden')).toBe('true');
  });

  it('draw their icons 20 px large, the size of the token --icon-size-rail (Otto, 4.11.2026)', () => {
    const icons = [...rail().querySelectorAll('svg')];
    expect(icons).toHaveLength(6);
    for (const svg of icons) {
      expect(svg.getAttribute('width')).toBe('20');
      expect(svg.getAttribute('height')).toBe('20');
    }
    expect(tokens).toMatch(/--icon-size-rail:\s*20px/u);
  });

  it('count the layers and the jobs that run, and the count goes into the name', () => {
    act(() => {
      useAppStore.setState({ layers: [layer('a'), layer('b'), layer('c')] });
      useProcessingStore.setState({ jobs: [jobEntry(1), jobEntry(2), jobEntry(3, { phase: 'failed' }), jobEntry(4, { phase: 'successful' })] });
    });
    expect(symbol('layers').getAttribute('aria-label')).toBe('Layers, 3');
    expect(symbol('layers').querySelector('.rail-badge')?.textContent).toBe('3');
    expect(symbol('jobs').getAttribute('aria-label')).toBe('Jobs, 2');
    expect(symbol('controls').querySelector('.rail-badge')).toBeNull();
  });

  it('do not count a job whose state is not known yet as running: an archived one, one of another tab', () => {
    act(() => useProcessingStore.setState({ jobs: [jobEntry(1, { status: null }), jobEntry(2)] }));
    expect(symbol('jobs').getAttribute('aria-label')).toBe('Jobs, 1');
  });

  it('show no count where there is nothing to count, and "99+" for a great many', () => {
    expect(symbol('layers').querySelector('.rail-badge')).toBeNull();
    act(() => useAppStore.setState({ layers: Array.from({ length: 120 }, (_, i) => layer(String(i))) }));
    expect(symbol('layers').querySelector('.rail-badge')?.textContent).toBe('99+');
    expect(symbol('layers').getAttribute('aria-label')).toBe('Layers, 120');
  });
});

describe('the panels', () => {
  it('start with the control menu open, as before', () => {
    expect(useAppStore.getState().dock).toBe('controls');
    expect(slot('controls')!.hidden).toBe(false);
    expect(symbol('controls').getAttribute('aria-expanded')).toBe('true');
  });

  it('open one at a time: a second symbol takes the place of the first', () => {
    click(symbol('layers'));
    expect(useAppStore.getState().dock).toBe('layers');
    expect(slot('layers')!.hidden).toBe(false);
    expect(slot('controls')!.hidden).toBe(true);
    click(symbol('jobs'));
    expect(slot('jobs')!.hidden).toBe(false);
    expect(slot('layers')!.hidden).toBe(true);
    expect(container.querySelectorAll('.dock-slot:not([hidden])')).toHaveLength(1);
  });

  it('close with a second click on the open symbol, and the map is free', () => {
    click(symbol('controls'));
    expect(useAppStore.getState().dock).toBeNull();
    expect(container.querySelector<HTMLElement>('.dock')!.hidden).toBe(true);
    expect(symbol('controls').getAttribute('aria-expanded')).toBe('false');
  });

  it('say which panel a symbol controls only while it is open', () => {
    expect(symbol('controls').getAttribute('aria-controls')).toBe('dock-controls');
    expect(symbol('layers').hasAttribute('aria-controls')).toBe(false);
    click(symbol('layers'));
    expect(symbol('layers').getAttribute('aria-controls')).toBe('dock-layers');
    expect(container.querySelector('#dock-layers')).not.toBeNull();
  });

  it('keep the control menu and the layer manager when another panel is open, for what they hold', () => {
    const control = container.querySelector('.control-panel')!;
    click(symbol('layers'));
    click(symbol('jobs'));
    expect(container.querySelector('.control-panel')).toBe(control);
    expect(container.querySelector('.layer-manager')).not.toBeNull();
  });

  it('mount the job manager only while it is open: it follows jobs', () => {
    expect(container.querySelector('.processing-manager')).toBeNull();
    click(symbol('jobs'));
    expect(container.querySelector('.processing-manager')).not.toBeNull();
    click(symbol('jobs'));
    expect(container.querySelector('.processing-manager')).toBeNull();
  });

  it('hold the layer manager fixed beside the rail, not in a panel one can drag', () => {
    click(symbol('layers'));
    expect(container.querySelector('.layer-manager')!.closest('.draggable')).toBeNull();
    expect(container.querySelector('.layer-manager')!.closest('.dock')).not.toBeNull();
  });

  it('are not opened by a new layer, a new job or the processing window', () => {
    act(() => useAppStore.setState({ layers: [layer('a')] }));
    act(() => useProcessingStore.setState({ open: true, jobs: [jobEntry(1)] }));
    expect(useAppStore.getState().dock).toBe('controls');
  });

  it('leave only the button "Zoom to selection" at the top right: Basemap and Light/Dark are in "Settings" now (UI-04 part 4)', () => {
    const top = container.querySelector('.top-right')!;
    expect([...top.querySelectorAll('button')].map((b) => b.textContent)).toEqual(['Zoom to selection']);
  });

  it('put "Settings" last, at the bottom edge of the rail, and it opens a panel like the others, not a menu (Otto, 4.11.2026)', () => {
    const settings = rail().querySelector<HTMLButtonElement>('button.rail-settings')!;
    expect([...rail().querySelectorAll('button')].at(-1)).toBe(settings);
    expect(settings.id).toBe('rail-settings');
    expect(settings.hasAttribute('aria-haspopup')).toBe(false);
    expect(settings.getAttribute('aria-expanded')).toBe('false');
    expect(slot('settings')!.hidden).toBe(true);
    click(settings);
    expect(useAppStore.getState().dock).toBe('settings');
    expect(settings.getAttribute('aria-expanded')).toBe('true');
    expect(settings.getAttribute('aria-controls')).toBe('dock-settings');
    expect(slot('settings')!.hidden).toBe(false);
    expect(slot('controls')!.hidden).toBe(true);
    expect(container.querySelector('#dock-settings .settings-panel h2')?.textContent).toBe('Settings');
    expect(document.querySelector('[role="menu"]')).toBeNull();
    // A second click closes it, like on the other symbols: it has no red x (Otto, 4.11.2026).
    click(settings);
    expect(useAppStore.getState().dock).toBeNull();
    expect(container.querySelector('#dock-settings .close-x')).toBeNull();
  });

  it('have no red x in the head of any panel: a panel of the rail is opened and closed with its symbol only (Otto, 4.11.2026)', () => {
    for (const name of ['controls', 'layers', 'jobs', 'results', 'settings'] as const) {
      act(() => useAppStore.setState({ dock: name === 'results' ? 'controls' : name }));
      expect(container.querySelector('.dock .close-x'), name).toBeNull();
    }
  });

  it('give the panel "Settings" the width and the place of the other panels, in the same slot of the dock', () => {
    const slots = [...container.querySelectorAll('.dock > .dock-slot')].map((el) => el.id);
    expect(slots).toEqual(['dock-controls', 'dock-layers', 'dock-results', 'dock-settings']);
    expect(container.querySelector('#dock-settings .dock-panel')).not.toBeNull();
  });
});

describe('the keyboard', () => {
  it('gives the Tab key one stop in the rail: the open panel\'s symbol', () => {
    expect(stops()).toEqual([0, -1, -1, -1, -1, -1]);
    click(symbol('jobs'));
    expect(stops()).toEqual([-1, -1, -1, 0, -1, -1]);
  });

  it('keeps the stop on the last symbol focused where no panel is open', () => {
    click(symbol('controls'));
    act(() => symbol('layers').focus());
    expect(stops()).toEqual([-1, -1, 0, -1, -1, -1]);
  });

  it('moves between the symbols with the arrow keys and wraps at the ends', () => {
    act(() => symbol('controls').focus());
    expect(key(symbol('controls'), 'ArrowDown').defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(symbol('catalogue'));
    key(symbol('catalogue'), 'ArrowDown');
    expect(document.activeElement).toBe(symbol('layers'));
    key(symbol('layers'), 'ArrowDown');
    key(symbol('jobs'), 'ArrowDown');
    key(symbol('results'), 'ArrowDown');
    expect(document.activeElement).toBe(settings());
    key(settings(), 'ArrowDown');
    expect(document.activeElement).toBe(symbol('controls'));
    key(symbol('controls'), 'ArrowUp');
    expect(document.activeElement).toBe(settings());
    key(settings(), 'Home');
    expect(document.activeElement).toBe(symbol('controls'));
    key(symbol('controls'), 'End');
    expect(document.activeElement).toBe(settings());
  });

  it('does not take other keys', () => {
    act(() => symbol('controls').focus());
    expect(key(symbol('controls'), 'a').defaultPrevented).toBe(false);
    expect(document.activeElement).toBe(symbol('controls'));
  });

  it('opens a panel with a click, which is what Enter and Space make on a button', () => {
    click(symbol('controls'));
    act(() => symbol('layers').focus());
    click(symbol('layers'));
    expect(useAppStore.getState().dock).toBe('layers');
  });

  // Otto, 2.11.2026: Esc closes nothing; a panel closes with its symbol. Esc ends "Flip through layers" (NM4-65 part 9), the one thing it does here.
  it('leaves the open panel open on Escape, from inside it and from its symbol; its symbol closes it', () => {
    click(symbol('layers'));
    key(container.querySelector<HTMLElement>('.layer-manager h2')!, 'Escape');
    expect(useAppStore.getState().dock).toBe('layers');
    act(() => symbol('layers').focus());
    key(symbol('layers'), 'Escape');
    expect(useAppStore.getState().dock).toBe('layers');
    expect(document.activeElement).toBe(symbol('layers'));
    click(symbol('layers'));
    expect(useAppStore.getState().dock).toBeNull();
  });

  it('ends "Flip through layers" with Escape from inside the layer manager, and the panel stays after the next Escape too', () => {
    act(() => useAppStore.setState({ layers: [layer('a'), layer('b')], flipThrough: false, flipLayerId: null }));
    click(symbol('layers'));
    act(() => useAppStore.getState().setFlipThrough(true));
    key(container.querySelector<HTMLElement>('.layer-manager h2')!, 'Escape');
    expect(useAppStore.getState().flipThrough).toBe(false);
    expect(useAppStore.getState().dock).toBe('layers');
    key(container.querySelector<HTMLElement>('.layer-manager h2')!, 'Escape');
    expect(useAppStore.getState().dock).toBe('layers');
  });

  it('ends "Flip through layers" with Escape from the symbol of the layers, and the panel stays after the next Escape too', () => {
    act(() => useAppStore.setState({ layers: [layer('a'), layer('b')], flipThrough: false, flipLayerId: null }));
    click(symbol('layers'));
    act(() => useAppStore.getState().setFlipThrough(true));
    act(() => symbol('layers').focus());
    key(symbol('layers'), 'Escape');
    expect(useAppStore.getState().flipThrough).toBe(false);
    expect(useAppStore.getState().dock).toBe('layers');
    key(symbol('layers'), 'Escape');
    expect(useAppStore.getState().dock).toBe('layers');
  });

  it('leaves the menu of a job row and the panel open on Escape (Otto, 2.11.2026: Esc closes no menu either)', () => {
    act(() => useProcessingStore.setState({ jobs: [jobEntry(1)] }));
    click(symbol('jobs'));
    click(container.querySelector('button[aria-haspopup="menu"]')!);
    const first = document.querySelector('[role="menu"] button')!;
    key(first, 'Escape');
    expect(document.querySelector('[role="menu"]')).not.toBeNull();
    expect(useAppStore.getState().dock).toBe('jobs');
    key(container.querySelector('.processing-manager h2')!, 'Escape');
    expect(useAppStore.getState().dock).toBe('jobs');
  });
});

describe('the control menu slides away for a draw or a search, and comes back', () => {
  it('slides away when a draw tool is chosen, and comes back when the draw is over', () => {
    act(() => useAppStore.getState().setToolMode('polygon'));
    expect(useAppStore.getState().dock).toBeNull();
    act(() => useAppStore.getState().reopenControls());
    expect(useAppStore.getState().dock).toBe('controls');
  });

  it('does not take the place of a panel the user opened meanwhile', () => {
    act(() => useAppStore.getState().setToolMode('polygon'));
    click(symbol('layers'));
    act(() => useAppStore.getState().reopenControls());
    expect(useAppStore.getState().dock).toBe('layers');
  });

  it('does not close another panel when a draw tool is chosen', () => {
    click(symbol('layers'));
    act(() => useAppStore.getState().setToolMode('polygon'));
    expect(useAppStore.getState().dock).toBe('layers');
  });

  it('slides away again, without effect, for a second draw tool', () => {
    act(() => useAppStore.getState().setToolMode('polygon'));
    act(() => useAppStore.getState().setToolMode('rectangle'));
    expect(useAppStore.getState().dock).toBeNull();
  });

  it('is back for "Clear all"', () => {
    click(symbol('controls'));
    act(() => useAppStore.getState().clearAll());
    expect(useAppStore.getState().dock).toBe('controls');
  });
});
