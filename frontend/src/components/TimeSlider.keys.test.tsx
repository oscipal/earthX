// @vitest-environment jsdom
//
// The arrow keys browse the passes (Otto, 05.11.2026): left to the one before, right to the one after, like the arrows beside the date.
// Not in a field, a list or a dialog, not with a modifier, not past an end; by hand they end the playing. The date row keeps its
// places: four text columns of one width round the date and its arrows, so that the first and the last step do not move them.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import CSS from '../index.css?raw';
import { useAppStore } from '../store';
import type { StacItem } from '../types';
import TimeSlider from './TimeSlider';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const item = (id: string): StacItem => ({ id, collection: 'd', bbox: [0, 0, 1, 1], properties: {}, assets: {} });
const DAYS = ['2026-07-25', '2026-07-24', '2026-07-23', '2026-07-22']; // newest first

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  useAppStore.setState({
    groups: DAYS.map((day) => ({ key: [day], label: day, items: [item(day)] })),
    activeGroupIndex: 1,
    playing: false,
    shownGroupIndex: null,
  });
  act(() => root.render(<TimeSlider />));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const press = (key: string, target: EventTarget = document.body, init: KeyboardEventInit = {}) => {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init });
  act(() => {
    target.dispatchEvent(event);
  });
  return event;
};
const index = () => useAppStore.getState().activeGroupIndex;
const shown = () => container.querySelector('.time-dates strong')!.textContent;

describe('browsing the passes with the arrow keys', () => {
  it('goes to the pass before with the left arrow and to the one after with the right, as the arrows beside the date do', () => {
    press('ArrowLeft');
    expect(index()).toBe(2);
    expect(shown()).toBe('2026-07-23');
    press('ArrowRight');
    press('ArrowRight');
    expect(index()).toBe(0);
    expect(shown()).toBe('2026-07-25');
  });

  it('does the same as the buttons beside the date', () => {
    const before = container.querySelector<HTMLButtonElement>('button[aria-label="Previous time step"]')!;
    act(() => before.click());
    const byButton = index();
    act(() => useAppStore.setState({ activeGroupIndex: 1 }));
    press('ArrowLeft');
    expect(index()).toBe(byButton);
  });

  it('stays at the ends, and says it took the key, so that the map does not pan', () => {
    act(() => useAppStore.setState({ activeGroupIndex: 0 }));
    const newest = press('ArrowRight');
    expect(index()).toBe(0);
    expect(newest.defaultPrevented).toBe(true);
    act(() => useAppStore.setState({ activeGroupIndex: 3 }));
    press('ArrowLeft');
    expect(index()).toBe(3);
  });

  it('ends the playing, as every step by hand does', () => {
    act(() => useAppStore.setState({ playing: true, shownGroupIndex: 1 }));
    press('ArrowLeft');
    expect(useAppStore.getState().playing).toBe(false);
    expect(index()).toBe(2);
  });

  it('is taken before the map: the key does not reach a listener below it', () => {
    let reached = false;
    const map = document.createElement('div');
    map.tabIndex = 0;
    map.addEventListener('keydown', () => (reached = true));
    document.body.append(map);
    press('ArrowLeft', map);
    map.remove();
    expect(index()).toBe(2);
    expect(reached).toBe(false);
  });

  it.each([
    ['a text field', () => Object.assign(document.createElement('input'), { type: 'text' })],
    ['a number field', () => Object.assign(document.createElement('input'), { type: 'number' })],
    ['a text area', () => document.createElement('textarea')],
    ['a list', () => Object.assign(document.createElement('div'), { role: 'listbox' })],
    ['a dialog', () => Object.assign(document.createElement('div'), { role: 'dialog' })],
    ['the slider', () => Object.assign(document.createElement('input'), { type: 'range' })],
  ])('leaves the arrows to %s', (_name, make) => {
    const element = make() as HTMLElement;
    document.body.append(element);
    const event = press('ArrowLeft', element);
    element.remove();
    expect(index()).toBe(1);
    expect(event.defaultPrevented).toBe(false);
  });

  it.each([['ctrlKey'], ['altKey'], ['metaKey'], ['shiftKey']])('does nothing with %s held', (modifier) => {
    press('ArrowLeft', document.body, { [modifier]: true });
    expect(index()).toBe(1);
  });

  it('does nothing for other keys, and nothing with fewer than two passes', () => {
    press('ArrowUp');
    press('a');
    expect(index()).toBe(1);
    act(() => useAppStore.setState({ groups: [{ key: ['2026-07-25'], label: '2026-07-25', items: [item('x')] }], activeGroupIndex: 0 }));
    const event = press('ArrowLeft');
    expect(index()).toBe(0);
    expect(event.defaultPrevented).toBe(false);
  });

  it('stops listening when the slider goes (no passes, or unmounted)', () => {
    act(() => root.unmount());
    press('ArrowLeft');
    expect(index()).toBe(1);
    root = createRoot(container);
    act(() => root.render(<TimeSlider />));
  });
});

describe('the date row keeps its places (first, middle and last step)', () => {
  const ROW = CSS.slice(CSS.indexOf('.time-dates {'), CSS.indexOf('}', CSS.indexOf('.time-dates {')));

  it('has four text columns of one width round the date and its two arrows', () => {
    expect(ROW).toMatch(/grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\) auto auto auto repeat\(2, minmax\(0, 1fr\)\)/);
  });

  it('holds the place of a date it does not name, at every step', () => {
    for (let at = 0; at < DAYS.length; at += 1) {
      act(() => useAppStore.setState({ activeGroupIndex: at }));
      const cells = [...container.querySelectorAll('.time-dates > *')];
      expect(cells).toHaveLength(7); // first, before, arrow, date, arrow, after, last: always seven
      expect(cells[3].tagName).toBe('STRONG');
    }
  });
});
