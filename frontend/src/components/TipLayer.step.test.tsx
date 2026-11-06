// @vitest-environment jsdom
//
// A tip that was drawn stayed on the screen when the step of the tooltips went to "simple" while the pointer was on its control (Otto, 4.11.2026).
// Its own file: every test here has one `TipLayer`, as the app has.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { useAppStore } from '../store';
import { setTipLevel } from '../tipLevel';
import TipLayer from './TipLayer';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

describe('TipLayer when the step changes', () => {
  let host: HTMLDivElement;
  let hostRoot: Root;

  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    host = document.createElement('div');
    document.body.append(host);
    hostRoot = createRoot(host);
    act(() => {
      hostRoot.render(
        <div className="app">
          <button type="button" id="advanced" data-tip-level="advanced" data-tip="What it does">Do it</button>
          <button type="button" id="other" data-tip-level="advanced" data-tip="Another one">Other</button>
          <TipLayer />
        </div>,
      );
    });
    setTipLevel('advanced');
  });

  afterEach(() => {
    setTipLevel('advanced');
    act(() => useAppStore.setState({ tipLevel: 'simple' }));
    act(() => hostRoot.unmount());
    host.remove();
  });

  const over = (el: Element) => act(() => el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true })));
  const out = (el: Element) => act(() => el.dispatchEvent(new MouseEvent('mouseout', { bubbles: true })));
  const shown = () => host.querySelectorAll('.tip-layer').length;

  it('goes when the pointer leaves, though the step is "simple" by then and the tip is one the step holds back', () => {
    const button = host.querySelector('#advanced')!;
    over(button);
    expect(shown()).toBe(1);
    setTipLevel('simple');
    out(button);
    expect(shown()).toBe(0);
  });

  it('goes when the step changes to "simple" with the pointer still on the control (the store step is the one that moves)', () => {
    const button = host.querySelector('#advanced')!;
    act(() => useAppStore.setState({ tipLevel: 'advanced' }));
    over(button);
    expect(shown()).toBe(1);
    setTipLevel('simple');
    act(() => useAppStore.setState({ tipLevel: 'simple' }));
    expect(shown()).toBe(0);
  });

  it('goes when the focus leaves it, too', () => {
    const button = host.querySelector('#advanced') as HTMLButtonElement;
    act(() => button.focus());
    expect(shown()).toBe(1);
    setTipLevel('simple');
    act(() => button.blur());
    expect(shown()).toBe(0);
  });

  it('still follows the pointer from one control to the next in the advanced step', () => {
    over(host.querySelector('#advanced')!);
    out(host.querySelector('#advanced')!);
    over(host.querySelector('#other')!);
    expect(host.querySelector('.tip-layer')?.textContent).toBe('Another one');
  });
});
