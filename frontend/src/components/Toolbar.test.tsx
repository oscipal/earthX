// @vitest-environment jsdom
//
// The button of the AOI tools that empties the AOI is "Clear AOI" in its label, its tooltip and its name (UI-04, Otto, 4.11.2026).

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { lockedWithoutReason } from '../fixtures/lockedControls';
import { useAppStore } from '../store';
import Toolbar from './Toolbar';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;
const clear = () => [...container.querySelectorAll('button')].find((b) => b.getAttribute('aria-label') === 'Clear AOI') as HTMLButtonElement | undefined;

beforeEach(() => {
  useAppStore.setState({ aoi: null, toolMode: 'rectangle' });
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root.render(<Toolbar />));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe('"Clear AOI"', () => {
  it('has the same words as label, tooltip and name, and no button is called just "Clear"', () => {
    act(() => useAppStore.setState({ aoi: { type: 'Point', coordinates: [1, 2] } }));
    expect(clear()!.textContent).toBe('Clear AOI');
    expect(clear()!.title).toBe('Clear the AOI');
    expect([...container.querySelectorAll('button')].some((b) => b.textContent === 'Clear')).toBe(false);
  });

  it('is locked without an AOI and says why', () => {
    expect(clear()!.disabled).toBe(true);
    expect(clear()!.title).toBe('No AOI to clear');
    expect(lockedWithoutReason(container)).toEqual([]);
  });

  it('empties the AOI and ends the drawing tool', () => {
    act(() => useAppStore.setState({ aoi: { type: 'Point', coordinates: [1, 2] } }));
    act(() => clear()!.click());
    expect(useAppStore.getState().aoi).toBeNull();
    expect(useAppStore.getState().toolMode).toBe('none');
  });
});
