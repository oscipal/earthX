// @vitest-environment jsdom
//
// NM4-65 part 9 (Otto, 31.10.2026): a toggle in the head of the layer manager. On, the layer that was clicked is drawn over all
// the others on the map and its row is highlighted, without moving in the list; ↑/↓ or the mouse wheel over the list step to
// the next layer (the wheel over the map zooms as ever); off — the toggle or Esc — the map shows the real order. The eye is
// respected: a layer that is switched off is passed by (the proposal for the PR).

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { flipIdOf } from '../layerFlip';
import type { MapLayer } from '../layers';
import { useAppStore } from '../store';
import LayerManager, { FLIP_ROW_TIP, FLIP_TIP } from './LayerManager';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

const layer = (id: string, over: Partial<MapLayer> = {}): MapLayer => ({
  id,
  name: `Layer ${id}`,
  visible: true,
  opacity: 1,
  overlays: [{ kind: 'raster', tileUrl: `https://t/${id}/{z}/{x}/{y}`, bounds: [0, 0, 1, 1], minZoom: 0, maxZoom: 12 }],
  restore: { datasetId: null, itemIds: [] } as never,
  ...over,
});

const state = () => useAppStore.getState();
const toggle = () => container.querySelector<HTMLButtonElement>('.lm-flip');
const rows = () => [...container.querySelectorAll<HTMLElement>('.layer-row')];
const flippedRows = () => rows().flatMap((row, i) => (row.classList.contains('flip') ? [i] : []));
const order = () => state().layers.map((l) => l.id).join('');
const click = (el: Element | null | undefined) => act(() => el?.dispatchEvent(new MouseEvent('click', { bubbles: true })));
const key = (el: Element, k: string) => {
  const event = new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true });
  act(() => el.dispatchEvent(event));
  return event;
};
let clock = 1000;
const wheel = (el: Element, deltaY: number, pause = false) => {
  clock += pause ? 500 : 20;
  const event = new WheelEvent('wheel', { deltaY, bubbles: true, cancelable: true });
  Object.defineProperty(event, 'timeStamp', { value: clock });
  act(() => el.dispatchEvent(event));
  return event;
};

function mount(layers: MapLayer[], extra: Partial<ReturnType<typeof useAppStore.getState>> = {}) {
  useAppStore.setState({ layers, dock: 'layers', resultsAt: 0, sections: [], flipThrough: false, flipLayerId: null, resultViewLayerId: null, viewLayerId: null, ...extra });
  act(() => root.render(<LayerManager />));
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  useAppStore.setState({ layers: [], flipThrough: false, flipLayerId: null });
});

describe('the toggle in the head', () => {
  it('is there with two layers or more, with a tooltip that says what it does and how it ends', () => {
    mount([layer('a'), layer('b')]);
    expect(toggle()).not.toBeNull();
    expect(toggle()!.title).toBe(FLIP_TIP);
    expect(toggle()!.title).toContain('Flip through layers');
    expect(toggle()!.getAttribute('aria-pressed')).toBe('false');
  });

  it('is not there where one layer has nothing to flip through (hidden, not greyed)', () => {
    mount([layer('a')]);
    expect(toggle()).toBeNull();
    act(() => root.unmount());
    root = createRoot(container);
    mount([]);
    expect(toggle()).toBeNull();
  });

  it('switches it on and off, and shows which it is', () => {
    mount([layer('a'), layer('b')]);
    click(toggle());
    expect(state().flipThrough).toBe(true);
    expect(toggle()!.getAttribute('aria-pressed')).toBe('true');
    click(toggle());
    expect(state().flipThrough).toBe(false);
    expect(state().flipLayerId).toBeNull();
  });

  it('cannot be switched on with one layer, by the store either', () => {
    mount([layer('a')]);
    act(() => state().setFlipThrough(true));
    expect(state().flipThrough).toBe(false);
  });
});

describe('the layer that is drawn on top', () => {
  it('is the first one to begin with, highlighted, and the list does not move', () => {
    mount([layer('a'), layer('b'), layer('c')]);
    click(toggle());
    expect(state().flipLayerId).toBe('a');
    expect(flippedRows()).toEqual([0]);
    expect(rows()[0].getAttribute('aria-current')).toBe('true');
    expect(order()).toBe('abc');
  });

  it('is the layer whose settings or view were open, where there is one', () => {
    mount([layer('a'), layer('b'), layer('c')], { resultViewLayerId: 'c' });
    click(toggle());
    expect(state().flipLayerId).toBe('c');
  });

  it('is the layer that is clicked, and the click does not open its view', () => {
    mount([layer('a'), layer('b'), layer('c')]);
    const select = vi.fn();
    act(() => useAppStore.setState({ selectLayer: select }));
    click(toggle());
    expect(rows()[2].querySelector('.lm-name')!.getAttribute('title')).toContain(FLIP_ROW_TIP);
    click(rows()[2].querySelector('.lm-name'));
    expect(state().flipLayerId).toBe('c');
    expect(flippedRows()).toEqual([2]);
    expect(select).not.toHaveBeenCalled();
    expect(order()).toBe('abc');
  });

  it('is told to the map by `flipIdOf`, and by nothing when flipping is off', () => {
    mount([layer('a'), layer('b')]);
    expect(flipIdOf(state())).toBeNull();
    click(toggle());
    click(rows()[1].querySelector('.lm-name'));
    expect(flipIdOf(state())).toBe('b');
    click(toggle());
    expect(flipIdOf(state())).toBeNull();
    // A click on a name is the layer's own again.
    const select = vi.fn();
    act(() => useAppStore.setState({ selectLayer: select }));
    click(rows()[1].querySelector('.lm-name'));
    expect(select).toHaveBeenCalledWith('b');
  });
});

describe('↑ and ↓', () => {
  it('step to the next layer, from where the focus is in the manager, and stop at the ends', () => {
    mount([layer('a'), layer('b'), layer('c')]);
    click(toggle());
    const name = rows()[0].querySelector('.lm-name')!;
    expect(key(name, 'ArrowDown').defaultPrevented).toBe(true);
    expect(state().flipLayerId).toBe('b');
    key(name, 'ArrowDown');
    key(name, 'ArrowDown');
    expect(state().flipLayerId).toBe('c');
    key(name, 'ArrowUp');
    expect(state().flipLayerId).toBe('b');
    key(name, 'ArrowUp');
    key(name, 'ArrowUp');
    expect(state().flipLayerId).toBe('a');
    expect(order()).toBe('abc');
  });

  it('pass by a layer that is switched off', () => {
    mount([layer('a'), layer('b', { visible: false }), layer('c')]);
    click(toggle());
    key(toggle()!, 'ArrowDown');
    expect(state().flipLayerId).toBe('c');
    expect(flippedRows()).toEqual([2]);
  });

  it('are the slider\'s and the dropdown\'s own: they do not step, and the page may scroll', () => {
    mount([layer('a'), layer('b')]);
    click(toggle());
    const slider = rows()[0].querySelector('input[type="range"]')!;
    const event = key(slider, 'ArrowDown');
    expect(event.defaultPrevented).toBe(false);
    expect(state().flipLayerId).toBe('a');
  });

  it('do nothing while flipping is off', () => {
    mount([layer('a'), layer('b')]);
    const event = key(rows()[0].querySelector('.lm-name')!, 'ArrowDown');
    expect(event.defaultPrevented).toBe(false);
    expect(state().flipLayerId).toBeNull();
  });

  it('are the only keys it answers to', () => {
    mount([layer('a'), layer('b')]);
    click(toggle());
    for (const k of ['ArrowLeft', 'ArrowRight', 'PageDown', 'a', ' ']) expect(key(rows()[0].querySelector('.lm-name')!, k).defaultPrevented).toBe(false);
    expect(state().flipLayerId).toBe('a');
  });
});

describe('the mouse wheel over the list', () => {
  const list = () => container.querySelector('.layer-list')!;

  it('steps down for a turn forward and up for a turn back, one layer for a notch, and the list does not scroll along', () => {
    mount([layer('a'), layer('b'), layer('c')]);
    click(toggle());
    expect(wheel(list(), 100, true).defaultPrevented).toBe(true);
    expect(state().flipLayerId).toBe('b');
    wheel(list(), 100, true);
    expect(state().flipLayerId).toBe('c');
    wheel(list(), -100, true);
    expect(state().flipLayerId).toBe('b');
  });

  it('takes a quick run of small turns for one step, not for one each', () => {
    mount([layer('a'), layer('b'), layer('c'), layer('d')]);
    click(toggle());
    wheel(list(), 15, true);
    wheel(list(), 15);
    expect(state().flipLayerId).toBe('a');
    wheel(list(), 15);
    expect(state().flipLayerId).toBe('b');
  });

  it('forgets a half turn after a pause', () => {
    mount([layer('a'), layer('b'), layer('c')]);
    click(toggle());
    wheel(list(), 30, true);
    wheel(list(), 30, true);
    expect(state().flipLayerId).toBe('a');
  });

  it('is not taken from the page elsewhere: over the map it zooms, and without flipping the list scrolls', () => {
    mount([layer('a'), layer('b')]);
    const before = wheel(list(), 100, true);
    expect(before.defaultPrevented).toBe(false);
    click(toggle());
    expect(wheel(document.body, 100, true).defaultPrevented).toBe(false);
    expect(state().flipLayerId).toBe('a');
  });

  it('stops at the end of the list', () => {
    mount([layer('a'), layer('b')]);
    click(toggle());
    wheel(list(), 100, true);
    wheel(list(), 100, true);
    expect(state().flipLayerId).toBe('b');
  });
});

describe('ending it', () => {
  it('Esc ends it, and the map shows the real order again', () => {
    mount([layer('a'), layer('b')]);
    click(toggle());
    act(() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', cancelable: true })));
    expect(state().flipThrough).toBe(false);
    expect(flipIdOf(state())).toBeNull();
    expect(flippedRows()).toEqual([]);
  });

  // The panel closes on Esc as well (`App.tsx`): while flipping, the key ends the flipping and the panel stays open.
  it('Esc in the manager ends it and does not close the panel as well', () => {
    mount([layer('a'), layer('b')]);
    click(toggle());
    const event = key(rows()[0].querySelector('.lm-name')!, 'Escape');
    expect(event.defaultPrevented).toBe(true);
    expect(state().flipThrough).toBe(false);
    expect(state().dock).toBe('layers');
  });

  it('Esc is the field\'s own in a dropdown or a field of the manager', () => {
    mount([layer('a'), layer('b')]);
    click(toggle());
    expect(key(rows()[0].querySelector('input[type="range"]')!, 'Escape').defaultPrevented).toBe(false);
  });

  it('Esc that another part of the page has taken (a pop-up, a tooltip) does not end it', () => {
    mount([layer('a'), layer('b')]);
    click(toggle());
    const event = new KeyboardEvent('keydown', { key: 'Escape', cancelable: true });
    event.preventDefault();
    act(() => window.dispatchEvent(event));
    expect(state().flipThrough).toBe(true);
  });

  it('ends of itself when fewer than two layers are left', () => {
    mount([layer('a'), layer('b')]);
    click(toggle());
    act(() => state().removeLayer('b'));
    expect(state().flipThrough).toBe(false);
    expect(toggle()).toBeNull();
  });

  it('does not keep a layer that is removed: nothing is drawn on top, and stepping goes on from the list', () => {
    mount([layer('a'), layer('b'), layer('c')]);
    click(toggle());
    click(rows()[1].querySelector('.lm-name'));
    act(() => state().removeLayer('b'));
    expect(flipIdOf(state())).toBeNull();
    act(() => state().flipStep(1));
    expect(state().flipLayerId).toBe('a');
  });
});
