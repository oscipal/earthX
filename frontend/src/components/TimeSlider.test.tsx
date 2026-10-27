// @vitest-environment jsdom
//
// The time slider (UI-01g, Otto, 26.10.2026): the slider with play and the position, and nothing else: no
// "select all frames", no "add to layers", no "N images" line below it.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { useAppStore } from '../store';
import type { StacItem } from '../types';
import TimeSlider from './TimeSlider';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const item = (id: string): StacItem => ({ id, collection: 'd', bbox: [0, 0, 1, 1], properties: {}, assets: {} });

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  useAppStore.setState({
    groups: [
      { key: ['2026-07-25'], label: '2026-07-25', items: [item('a'), item('b')] },
      { key: ['2026-07-24'], label: '2026-07-24', items: [item('c')] },
    ],
    activeGroupIndex: 0,
    playing: false,
  });
  act(() => root.render(<TimeSlider />));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe('the time slider', () => {
  it('has play, the slider and the position, and no link or image count', () => {
    expect([...container.querySelectorAll('button')].map((b) => b.getAttribute('aria-label'))).toEqual(['Play']);
    expect(container.querySelector('input[type="range"]')).not.toBeNull();
    expect(container.querySelector('.time-count')?.textContent).toBe('1/2');
    expect(container.textContent).not.toMatch(/select all frames|add to layers|image/i);
  });

  it('shows no image count for a group of several scenes or of one', () => {
    for (const index of [0, 1]) {
      act(() => useAppStore.setState({ activeGroupIndex: index }));
      expect(container.textContent).not.toMatch(/\d+ images?|covering ROI/);
    }
  });
});
