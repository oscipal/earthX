// @vitest-environment jsdom
//
// The processing manager as a floating window (UI-03c, plan §7.9): where it opens, how it is dragged and pulled to size, what
// it keeps, how it closes (the red x; Esc does nothing), and the sheet it becomes under 900 px.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { jobEntry, NOW, status } from '../fixtures/jobEntries';
import { HEAD_HEIGHT, KEEP_WIDTH, MIN_HEIGHT, MIN_WIDTH } from '../jobsWindow';
import { resetJobs, setTrackerOptions, useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import JobsWindow from './JobsWindow';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const KEY = 'earthx.jobsWindow';
let container: HTMLDivElement;
let root: Root;

const setViewport = (width: number, height: number) => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width });
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: height });
};

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers({ toFake: ['Date'], now: NOW });
  localStorage.clear();
  setViewport(1280, 800);
  setTrackerOptions({ EventSource: null, fetchJob: async (id) => status({ jobID: id }), pollMs: 60_000 });
  resetJobs();
  useAppStore.setState({ dock: null });
  useProcessingStore.setState({ managerOpen: true, open: false, detailJobID: null });
  container = document.createElement('div');
  container.innerHTML = '<button id="rail-jobs" type="button">Jobs</button>';
  document.body.append(container);
  const host = document.createElement('div');
  container.append(host);
  root = createRoot(host);
});

afterEach(() => {
  setTrackerOptions({});
  act(() => root.unmount());
  container.remove();
  resetJobs();
  useProcessingStore.setState({ managerOpen: false });
  localStorage.clear();
  document.body.classList.remove('dragging');
  vi.restoreAllMocks();
  vi.useRealTimers();
});

const mount = () => act(() => root.render(<JobsWindow />));
const win = () => container.querySelector<HTMLElement>('#jobs-window')!;
const head = () => win().querySelector<HTMLElement>('.pm-head')!;
const box = () => ({ x: parseFloat(win().style.left), y: parseFloat(win().style.top), width: parseFloat(win().style.width), height: parseFloat(win().style.height) });
const stored = () => JSON.parse(localStorage.getItem(KEY) ?? 'null') as ReturnType<typeof box> | null;

const pointer = (target: Element, type: 'pointerdown' | 'pointermove' | 'pointerup', x: number, y: number) =>
  act(() => {
    target.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0 }));
  });
const drag = (target: Element, from: [number, number], to: [number, number]) => {
  pointer(target, 'pointerdown', ...from);
  pointer(target, 'pointermove', ...to);
  pointer(target, 'pointerup', ...to);
};
const key = (target: Element, name: string, init: KeyboardEventInit = {}) =>
  act(() => {
    target.dispatchEvent(new KeyboardEvent('keydown', { key: name, bubbles: true, cancelable: true, ...init }));
  });

describe('where it opens', () => {
  it('is a window of its own with the manager inside, at 480 px, under the buttons at the top, right of the rail', () => {
    mount();
    expect(win().querySelector('.processing-manager.windowed')).not.toBeNull();
    expect(win().querySelector('.processing-manager.dock-panel')).toBeNull();
    expect(box()).toEqual({ x: 48 + 16, y: 64, width: 480, height: 640 });
  });

  it('opens right of an open panel beside the rail', () => {
    useAppStore.setState({ dock: 'layers' });
    mount();
    expect(box().x).toBe(48 + 340 + 16);
  });

  it('is at most as high as the window minus 80 px', () => {
    setViewport(1280, 600);
    mount();
    expect(box().height).toBe(520);
  });

  it('opens where it was left, and keeps a kept place inside the window', () => {
    localStorage.setItem(KEY, JSON.stringify({ x: 300, y: 120, width: 600, height: 500 }));
    mount();
    expect(box()).toEqual({ x: 300, y: 120, width: 600, height: 500 });
    act(() => root.unmount());
    root = createRoot(container.lastElementChild as HTMLElement);
    localStorage.setItem(KEY, JSON.stringify({ x: 9000, y: 9000, width: 600, height: 500 }));
    mount();
    expect(box()).toMatchObject({ x: 1280 - KEEP_WIDTH, y: 800 - HEAD_HEIGHT });
  });

  it.each(['', 'nonsense', '[]', '{"x":1}', '{"x":-5000,"y":10,"width":500,"height":400}', '{"x":0,"y":-1,"width":500,"height":400}', '{"x":0,"y":0,"width":10,"height":10}'])(
    'takes the first place for what is kept as %j',
    (raw) => {
      localStorage.setItem(KEY, raw);
      mount();
      expect(box()).toEqual({ x: 64, y: 64, width: 480, height: 640 });
    },
  );

  it('takes the first place, and no error, where the storage cannot be read', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError');
    });
    expect(() => mount()).not.toThrow();
    expect(box()).toEqual({ x: 64, y: 64, width: 480, height: 640 });
  });
});

describe('dragging by the head', () => {
  it('moves the window, and writes the place once, at the end', () => {
    mount();
    const write = vi.spyOn(Storage.prototype, 'setItem');
    pointer(head(), 'pointerdown', 100, 100);
    pointer(head(), 'pointermove', 160, 130);
    expect(box()).toMatchObject({ x: 64 + 60, y: 64 + 30 });
    expect(document.body.classList.contains('dragging')).toBe(true);
    pointer(head(), 'pointermove', 200, 140);
    expect(write).not.toHaveBeenCalled();
    pointer(head(), 'pointerup', 200, 140);
    expect(write).toHaveBeenCalledTimes(1);
    expect(stored()).toMatchObject({ x: 164, y: 104, width: 480, height: 640 });
    expect(document.body.classList.contains('dragging')).toBe(false);
  });

  it('keeps the head in the window however far it is pulled', () => {
    mount();
    drag(head(), [100, 100], [-9000, -9000]);
    expect(box()).toMatchObject({ x: KEEP_WIDTH - 480, y: 0 });
    drag(head(), [100, 100], [9000, 9000]);
    expect(box()).toMatchObject({ x: 1280 - KEEP_WIDTH, y: 800 - HEAD_HEIGHT });
  });

  it('is not started by a press on the red x or on a tooltip symbol', () => {
    mount();
    const close = win().querySelector<HTMLElement>('.close-x')!;
    drag(close, [100, 100], [300, 300]);
    expect(box()).toMatchObject({ x: 64, y: 64 });
    expect(stored()).toBeNull();
    const tip = win().querySelector<HTMLElement>('.pm-head .tip')!;
    drag(tip, [100, 100], [300, 300]);
    expect(box()).toMatchObject({ x: 64, y: 64 });
  });

  it('moves nothing on a move without a press first', () => {
    mount();
    pointer(head(), 'pointermove', 400, 400);
    pointer(head(), 'pointerup', 400, 400);
    expect(box()).toMatchObject({ x: 64, y: 64 });
    expect(stored()).toBeNull();
  });

  it('does not stop the browser window from being full: no error where the storage cannot be written', () => {
    mount();
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError');
    });
    expect(() => drag(head(), [100, 100], [150, 150])).not.toThrow();
    expect(box()).toMatchObject({ x: 114, y: 114 });
  });
});

describe('the arrow keys on the head', () => {
  it('move the window by 16 px, and by 64 px with Shift, and keep the place', () => {
    mount();
    expect(head().tabIndex).toBe(0);
    key(head(), 'ArrowRight');
    key(head(), 'ArrowDown');
    expect(box()).toMatchObject({ x: 80, y: 80 });
    key(head(), 'ArrowLeft', { shiftKey: true });
    expect(box()).toMatchObject({ x: 16, y: 80 });
    expect(stored()).toMatchObject({ x: 16, y: 80 });
  });

  it('stop at the edge: the head stays in the window', () => {
    localStorage.setItem(KEY, JSON.stringify({ x: 0, y: 0, width: 480, height: 640 }));
    mount();
    key(head(), 'ArrowUp');
    expect(box().y).toBe(0);
  });

  it('are the head\'s own: from a button inside the window they do nothing to it, and with Ctrl or Alt neither', () => {
    mount();
    key(win().querySelector('.pm-filter button')!, 'ArrowRight');
    key(head(), 'ArrowRight', { ctrlKey: true });
    key(head(), 'ArrowRight', { altKey: true });
    key(head(), 'a');
    expect(box()).toMatchObject({ x: 64, y: 64 });
  });
});

describe('pulling to size', () => {
  const handle = (edge: 'e' | 's' | 'se') => win().querySelector<HTMLElement>(`.jw-handle.${edge}`)!;

  it('the right edge, the bottom edge and the corner change the size and leave the place', () => {
    mount();
    drag(handle('e'), [500, 300], [560, 300]);
    expect(box()).toMatchObject({ x: 64, y: 64, width: 540, height: 640 });
    drag(handle('s'), [300, 700], [300, 640]);
    expect(box()).toMatchObject({ width: 540, height: 580 });
    drag(handle('se'), [500, 600], [530, 640]);
    expect(box()).toEqual({ x: 64, y: 64, width: 570, height: 620 });
    expect(stored()).toEqual({ x: 64, y: 64, width: 570, height: 620 });
  });

  it('stops at 420 × 320 and at the size of the browser window', () => {
    mount();
    drag(handle('se'), [500, 600], [-9000, -9000]);
    expect(box()).toMatchObject({ width: MIN_WIDTH, height: MIN_HEIGHT });
    drag(handle('se'), [500, 600], [9000, 9000]);
    expect(box()).toMatchObject({ width: 1280, height: 800 });
  });
});

describe('a smaller browser window', () => {
  it('pushes the window back so that its head and 120 px of its width stay in, and keeps what was stored', () => {
    localStorage.setItem(KEY, JSON.stringify({ x: 1000, y: 700, width: 480, height: 500 }));
    mount();
    const before = localStorage.getItem(KEY);
    setViewport(1000, 600);
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    expect(box().x).toBeLessThanOrEqual(1000 - KEEP_WIDTH);
    expect(box().y).toBeLessThanOrEqual(600 - HEAD_HEIGHT);
    expect(box().height).toBeLessThanOrEqual(600);
    expect(localStorage.getItem(KEY)).toBe(before);
  });
});

describe('closing', () => {
  it('closes with the red x and puts the focus back on the symbol of the jobs in the rail', () => {
    mount();
    act(() => win().querySelector<HTMLButtonElement>('.close-x')!.click());
    expect(useProcessingStore.getState().managerOpen).toBe(false);
    expect(document.activeElement).toBe(container.querySelector('#rail-jobs'));
  });

  it('is not closed by Esc, from the head, from inside, or from the page', () => {
    mount();
    for (const target of [head(), win().querySelector('.pm-filter button')!, document.body, document.documentElement]) key(target, 'Escape');
    expect(useProcessingStore.getState().managerOpen).toBe(true);
    expect(win()).not.toBeNull();
  });

  it('stays open when a job opens its details in the processing panel, and is not moved by it', () => {
    useProcessingStore.setState({ jobs: [jobEntry(1)] });
    mount();
    const before = { ...box() };
    act(() => win().querySelector<HTMLButtonElement>('button.pm-open')!.click());
    expect(useProcessingStore.getState().open).toBe(true);
    expect(useProcessingStore.getState().managerOpen).toBe(true);
    expect(box()).toEqual(before);
  });
});

describe('under 900 px', () => {
  beforeEach(() => setViewport(600, 800));

  it('is a sheet: no place of its own, no handles, nothing to drag, and the kept size does not apply', () => {
    localStorage.setItem(KEY, JSON.stringify({ x: 300, y: 120, width: 600, height: 500 }));
    mount();
    expect(win().classList.contains('sheet')).toBe(true);
    expect(win().getAttribute('style')).toBeNull();
    expect(win().querySelector('.jw-handle')).toBeNull();
    expect(head().hasAttribute('tabindex')).toBe(false);
    drag(head(), [100, 100], [300, 300]);
    key(head(), 'ArrowRight');
    expect(win().getAttribute('style')).toBeNull();
    expect(localStorage.getItem(KEY)).toBe(JSON.stringify({ x: 300, y: 120, width: 600, height: 500 }));
  });

  it('folds to its head with the grip, and unfolds', () => {
    mount();
    const grip = win().querySelector<HTMLButtonElement>('.pp-grip')!;
    expect(grip.getAttribute('aria-expanded')).toBe('true');
    act(() => grip.click());
    expect(win().classList.contains('folded')).toBe(true);
    expect(grip.getAttribute('aria-expanded')).toBe('false');
    expect(win().querySelector('.close-x')).not.toBeNull();
    act(() => grip.click());
    expect(win().classList.contains('folded')).toBe(false);
  });

  it('turns into a window again when the browser window grows, at the kept place', () => {
    localStorage.setItem(KEY, JSON.stringify({ x: 300, y: 120, width: 600, height: 500 }));
    mount();
    setViewport(1280, 800);
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    expect(win().classList.contains('sheet')).toBe(false);
    expect(box()).toEqual({ x: 300, y: 120, width: 600, height: 500 });
  });
});
