// @vitest-environment jsdom
//
// The eye (UI-04 part 3a, Otto, 4.11.2026): one component; hidden is the eye crossed out, never another colour.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import EyeButton from './EyeButton';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;
const onToggle = vi.fn();
const button = () => container.querySelector('button') as HTMLButtonElement;
const mount = (props: Partial<Parameters<typeof EyeButton>[0]> = {}) => act(() => root.render(<EyeButton shown tip="Hide layer" onToggle={onToggle} {...props} />));

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  onToggle.mockClear();
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe('EyeButton', () => {
  it('is the open eye when shown and the crossed eye when hidden, and has the same classes in both', () => {
    mount();
    expect(button().querySelector('svg.lucide-eye')).not.toBeNull();
    const shownClasses = button().className;
    mount({ shown: false, tip: 'Show layer' });
    expect(button().querySelector('svg.lucide-eye-off')).not.toBeNull();
    expect(button().className).toBe(shownClasses);
    expect(button().classList.contains('off')).toBe(false);
  });

  it('says what a click does, by its tooltip and its name, and is pressed while shown', () => {
    mount();
    expect([button().getAttribute('data-tip'), button().getAttribute('aria-label'), button().getAttribute('aria-pressed')]).toEqual(['Hide layer', 'Hide layer', 'true']);
    mount({ shown: false, tip: 'Show layer' });
    expect(button().getAttribute('aria-pressed')).toBe('false');
  });

  it('switches on a click', () => {
    mount();
    act(() => button().click());
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it('is 22 px with a 14 px icon in a row, 28 px with a 16 px icon otherwise', () => {
    mount({ row: true });
    expect(button().classList.contains('sm')).toBe(true);
    expect(button().querySelector('svg')?.getAttribute('width')).toBe('14');
    mount({ row: false });
    expect(button().classList.contains('sm')).toBe(false);
    expect(button().querySelector('svg')?.getAttribute('width')).toBe('16');
  });

  it('keeps its place when locked: crossed out, not pressed, aria-disabled, and a click does nothing', () => {
    mount({ locked: true, tip: 'Job deleted: restore it first' });
    expect(button().querySelector('svg.lucide-eye-off')).not.toBeNull();
    expect(button().getAttribute('aria-disabled')).toBe('true');
    expect(button().hasAttribute('aria-pressed')).toBe(false);
    act(() => button().click());
    expect(onToggle).not.toHaveBeenCalled();
  });

  it('carries the place of the row it stands in', () => {
    mount({ col: 'eye' });
    expect(button().getAttribute('data-col')).toBe('eye');
  });
});
