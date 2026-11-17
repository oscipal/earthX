// @vitest-environment jsdom
//
// The dial of an angle from north (M5-14, Otto, 17.11.2026): dragged round the circle, set with the arrows, the value beside it in degrees.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import AngleDial from './AngleDial';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;
let changed: ReturnType<typeof vi.fn<(angle: number) => void>>;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  changed = vi.fn<(angle: number) => void>();
  act(() => root.render(<AngleDial value={315} label="Azimuth" onChange={changed} />));
  const face = container.querySelector('svg')!;
  // A dial of 40 px whose centre is at (100, 100).
  face.getBoundingClientRect = () => ({ left: 80, top: 80, width: 40, height: 40, right: 120, bottom: 120, x: 80, y: 80, toJSON: () => ({}) });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const face = () => container.querySelector('svg')!;
const pointer = (type: string, x: number, y: number) =>
  act(() => {
    face().dispatchEvent(new MouseEvent(type, { clientX: x, clientY: y, bubbles: true }));
  });

describe('the dial of an angle', () => {
  it('is a slider of 0 to 359 degrees for a screen reader, with its value beside it', () => {
    expect(face().getAttribute('role')).toBe('slider');
    expect(face().getAttribute('aria-label')).toBe('Azimuth');
    expect([face().getAttribute('aria-valuemin'), face().getAttribute('aria-valuemax'), face().getAttribute('aria-valuenow')]).toEqual(['0', '359', '315']);
    expect(container.querySelector('.angle-dial-value')?.textContent).toBe('315°');
  });

  it('points its hand to the north-west for 315°', () => {
    const hand = container.querySelector('.angle-dial-hand')!;
    expect(Number(hand.getAttribute('x2'))).toBeLessThan(20);
    expect(Number(hand.getAttribute('y2'))).toBeLessThan(20);
  });

  it('follows a drag round the circle: east is 90°, south 180°', () => {
    pointer('pointerdown', 130, 100);
    expect(changed).toHaveBeenLastCalledWith(90);
    pointer('pointermove', 100, 140);
    expect(changed).toHaveBeenLastCalledWith(180);
    pointer('pointerup', 100, 140);
    pointer('pointermove', 60, 100);
    expect(changed).toHaveBeenCalledTimes(2);
  });

  it('takes the arrows, ±1° and ±15° with Shift', () => {
    const key = (name: string, shiftKey = false) =>
      act(() => {
        face().dispatchEvent(new KeyboardEvent('keydown', { key: name, shiftKey, bubbles: true }));
      });
    key('ArrowRight');
    expect(changed).toHaveBeenLastCalledWith(316);
    key('ArrowLeft', true);
    expect(changed).toHaveBeenLastCalledWith(300);
    key('Tab');
    expect(changed).toHaveBeenCalledTimes(2);
  });

  it('draws with the colours of the theme only (classes, no colour of its own)', () => {
    expect(container.innerHTML).not.toMatch(/fill="#|stroke="#|rgb\(/u);
  });
});
