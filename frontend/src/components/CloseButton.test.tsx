// @vitest-environment jsdom
//
// NM4-65 part 8 (Otto, 31.10.2026: "consistency!!"): everything that is closed is closed with the same small red "x" and
// the tooltip "Close" — the settings of a layer (it was "‹ Close"), the processing panel, the details of a job, the windows
// of the download and the pop-up "Advanced search". What removes or empties something keeps its own button.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import CSS from '../index.css?raw';
import { focusFirstItem } from '../popover';
import CloseButton from './CloseButton';

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
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe('CloseButton', () => {
  it('is a button "Close" with the tooltip "Close", and no text of its own to read', () => {
    const onClick = vi.fn();
    act(() => root.render(<CloseButton onClick={onClick} />));
    const button = container.querySelector('button')!;
    expect(button.type).toBe('button');
    expect(button.className).toBe('close-x');
    expect(button.title).toBe('Close');
    expect(button.getAttribute('aria-label')).toBe('Close');
    expect(button.textContent).toBe('');
    act(() => button.dispatchEvent(new MouseEvent('click', { bubbles: true })));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('may say more in its tooltip where closing has a consequence, and keeps its name', () => {
    act(() => root.render(<CloseButton title="Close. This stops a download that is still running." onClick={() => undefined} />));
    const button = container.querySelector('button')!;
    expect(button.title).toContain('stops a download');
    expect(button.getAttribute('aria-label')).toBe('Close');
  });

  it('is small and red in both themes, with a focus ring', () => {
    const rule = (selector: string) => CSS.slice(CSS.indexOf(`\n${selector} {`), CSS.indexOf('}', CSS.indexOf(`\n${selector} {`)));
    expect(rule('.close-x')).toContain('color: #ff5a6e');
    expect(rule('.close-x')).toMatch(/width: 20px/u);
    expect(rule(".app[data-theme='normal'] .close-x")).toContain('color: #c62840');
    expect(rule('.close-x:focus-visible')).toContain('outline');
  });
});

// The pop-up opens with the focus on the first thing to work with; the "x" is one Tab away, not the first stop.
describe('the focus of a pop-up that has a close "x"', () => {
  it('starts at the first thing to work with, not at the "x"', () => {
    act(() =>
      root.render(
        <div>
          <CloseButton onClick={() => undefined} />
          <button type="button" className="first">
            first
          </button>
        </div>,
      ),
    );
    focusFirstItem(container);
    expect(document.activeElement?.className).toBe('first');
  });

  it('falls back to the "x" where it is the only thing', () => {
    act(() => root.render(<CloseButton onClick={() => undefined} />));
    focusFirstItem(container);
    expect(document.activeElement?.className).toBe('close-x');
  });
});
