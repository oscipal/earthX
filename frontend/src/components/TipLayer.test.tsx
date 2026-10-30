// @vitest-environment jsdom
//
// The one tooltip (NM4-52): drawn outside any panel, in the app (where the theme tokens are), on hover and focus, closed by `Esc`.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import Tip from './Tip';
import TipLayer from './TipLayer';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  act(() => {
    root.render(
      <div className="app">
        <div className="panel" style={{ overflow: 'hidden' }}>
          <Tip text="Resampled to a common grid" />
          <button type="button" data-tip="Not empty" aria-label="Remove">x</button>
        </div>
        <TipLayer />
      </div>,
    );
  });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const layer = () => document.body.querySelector('.tip-layer');
const app = () => container.querySelector('.app');
const tip = () => container.querySelector('.tip') as HTMLElement;

describe('TipLayer', () => {
  it('shows nothing until the pointer or focus is on a tip', () => {
    expect(layer()).toBeNull();
  });

  it('draws the text in the app, outside the panel, on hover', () => {
    act(() => tip().dispatchEvent(new MouseEvent('mouseover', { bubbles: true })));
    expect(layer()?.textContent).toBe('Resampled to a common grid');
    expect(layer()?.parentElement).toBe(app());
    expect(container.querySelector('.panel')?.contains(layer())).toBe(false);
    expect(layer()?.getAttribute('aria-hidden')).toBe('true');
  });

  it('hides when the pointer leaves', () => {
    act(() => tip().dispatchEvent(new MouseEvent('mouseover', { bubbles: true })));
    act(() => tip().dispatchEvent(new MouseEvent('mouseout', { bubbles: true })));
    expect(layer()).toBeNull();
  });

  it('shows on keyboard focus, also for a button, and hides on blur', () => {
    const button = container.querySelector('button') as HTMLButtonElement;
    act(() => button.focus());
    expect(layer()?.textContent).toBe('Not empty');
    act(() => button.blur());
    expect(layer()).toBeNull();
  });

  it('closes on Esc', () => {
    act(() => tip().focus());
    expect(layer()).not.toBeNull();
    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });
    expect(layer()).toBeNull();
  });

  it('ignores other keys and elements without a tip', () => {
    act(() => tip().focus());
    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', bubbles: true }));
    });
    expect(layer()).not.toBeNull();
    act(() => container.querySelector('.panel')!.dispatchEvent(new MouseEvent('mouseover', { bubbles: true })));
    expect(layer()).not.toBeNull();
  });

  it('the element keeps its accessible name', () => {
    expect(tip().getAttribute('aria-label')).toBe('Resampled to a common grid');
  });
});

describe('TipLayer without an app around it', () => {
  it('falls back to body', () => {
    const bare = document.createElement('div');
    bare.innerHTML = '<span id="t" data-tip="Alone" tabindex="0">i</span>';
    document.body.append(bare);
    act(() => (bare.querySelector('#t') as HTMLElement).dispatchEvent(new MouseEvent('mouseover', { bubbles: true })));
    expect(layer()?.parentElement).toBe(document.body);
    act(() => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
    bare.remove();
  });
});
