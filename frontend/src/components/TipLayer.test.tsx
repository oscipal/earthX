// @vitest-environment jsdom
//
// The one tooltip (NM4-52): drawn outside any panel, in the app (where the theme tokens are), on hover and focus, closed by `Esc`.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Tip from './Tip';
import { setTipLevel } from '../tipLevel';
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
  setTipLevel('advanced');
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
    expect(layer()?.getAttribute('role')).toBe('tooltip');
  });

  // UI-04 part 3a (Otto, 3.11.2026): no `title` any more; a screen reader hears the text as the description of the element.
  it('describes the element with its text while it shows, and no longer afterwards', () => {
    const button = container.querySelector('button') as HTMLButtonElement;
    act(() => button.focus());
    expect(button.getAttribute('aria-describedby')).toBe(layer()?.id);
    act(() => button.blur());
    expect(button.hasAttribute('aria-describedby')).toBe(false);
  });

  it('keeps a description the element had, and puts it back', () => {
    const button = container.querySelector('button') as HTMLButtonElement;
    button.setAttribute('aria-describedby', 'own');
    act(() => button.focus());
    expect(button.getAttribute('aria-describedby')).toBe(`own ${layer()?.id}`);
    act(() => button.blur());
    expect(button.getAttribute('aria-describedby')).toBe('own');
  });

  it('describes the field in a label with a tip, not the label', () => {
    const label = document.createElement('label');
    label.setAttribute('data-tip', 'The range of the band');
    const field = document.createElement('input');
    label.append('Scale', field);
    container.querySelector('.panel')!.append(label);
    act(() => label.dispatchEvent(new MouseEvent('mouseover', { bubbles: true })));
    expect(field.getAttribute('aria-describedby')).toBe(layer()?.id);
    expect(label.hasAttribute('aria-describedby')).toBe(false);
    act(() => label.dispatchEvent(new MouseEvent('mouseout', { bubbles: true })));
    expect(field.hasAttribute('aria-describedby')).toBe(false);
  });

  it('does not describe an element that its own text already names (the (i) says it once)', () => {
    act(() => tip().focus());
    expect(layer()?.textContent).toBe('Resampled to a common grid');
    expect(tip().hasAttribute('aria-describedby')).toBe(false);
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

  it('stays on Esc and goes when the focus leaves (Otto, 2.11.2026: Esc closes nothing)', () => {
    act(() => tip().focus());
    expect(layer()).not.toBeNull();
    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });
    expect(layer()).not.toBeNull();
    act(() => tip().blur());
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

  // A locked button takes no pointer events (`index.css`) and has no focus: the pointer is looked for among the locked ones.
  describe('a locked control', () => {
    let locked: HTMLButtonElement;
    beforeEach(() => {
      locked = document.createElement('button');
      locked.disabled = true;
      locked.setAttribute('data-tip', 'Type a place name first');
      locked.getBoundingClientRect = () => ({ left: 10, top: 10, right: 60, bottom: 40, width: 50, height: 30, x: 10, y: 10, toJSON: () => ({}) });
      container.querySelector('.panel')!.append(locked);
    });
    // The search runs in the next frame: the frames are collected here and run by hand.
    let frames: FrameRequestCallback[] = [];
    beforeEach(() => {
      frames = [];
      vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => frames.push(callback));
      vi.stubGlobal('cancelAnimationFrame', () => undefined);
    });
    afterEach(() => vi.unstubAllGlobals());
    const move = (x: number, y: number) => {
      act(() => document.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: x, clientY: y })));
      act(() => frames.splice(0).forEach((callback) => callback(0)));
    };

    it('shows its reason where the pointer is over it, and no longer where it leaves', () => {
      move(30, 20);
      expect(layer()?.textContent).toBe('Type a place name first');
      move(300, 300);
      expect(layer()).toBeNull();
    });

    it('shows nothing where the pointer is beside it', () => {
      move(70, 20);
      expect(layer()).toBeNull();
    });

    it('leaves the tip of an enabled control alone', () => {
      act(() => tip().dispatchEvent(new MouseEvent('mouseover', { bubbles: true })));
      move(300, 300);
      expect(layer()?.textContent).toBe('Resampled to a common grid');
    });

    it('looks for the pointer once a frame, not at every move', () => {
      act(() => document.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: 30, clientY: 20 })));
      act(() => document.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: 31, clientY: 20 })));
      expect(frames).toHaveLength(1);
    });

    it('is not found when it is no longer locked', () => {
      locked.disabled = false;
      move(30, 20);
      expect(layer()).toBeNull();
    });
  });
});

// UI-04 part 3b (Otto, 4.11.2026): two steps. The simple one holds back the tips marked advanced, but never the reason of a locked control.
describe('TipLayer in the simple step', () => {
  const over = (el: Element) => act(() => el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true })));
  const out = (el: Element) => act(() => el.dispatchEvent(new MouseEvent('mouseout', { bubbles: true })));

  function mount(): void {
    act(() => {
      root.render(
        <div className="app">
          <button type="button" id="plain" aria-label="Flip through layers" data-tip="Flip through layers" />
          <button type="button" id="text" data-tip-level="advanced" data-tip="Draw the result on the map">Show</button>
          <button type="button" id="locked" aria-disabled="true" data-tip-level="advanced" data-tip="Draw an AOI first">Download</button>
          <label id="label" data-tip-level="advanced" data-tip="The label explains">
            <input id="inside" data-tip-level="advanced" data-tip="The field explains" />
          </label>
          <TipLayer />
        </div>,
      );
    });
  }

  it('shows a tip without a step', () => {
    setTipLevel('simple');
    mount();
    over(container.querySelector('#plain')!);
    expect(layer()?.textContent).toBe('Flip through layers');
  });

  it('shows no advanced tip, and shows it in the advanced step', () => {
    setTipLevel('simple');
    mount();
    over(container.querySelector('#text')!);
    expect(layer()).toBeNull();
    setTipLevel('advanced');
    over(container.querySelector('#text')!);
    expect(layer()?.textContent).toBe('Draw the result on the map');
  });

  it('shows the reason of a locked control although the tip of the control is advanced', () => {
    setTipLevel('simple');
    mount();
    over(container.querySelector('#locked')!);
    expect(layer()?.textContent).toBe('Draw an AOI first');
  });

  it('shows nothing for a field whose label and itself are advanced, and leaves no stale tip when the pointer goes', () => {
    setTipLevel('simple');
    mount();
    over(container.querySelector('#inside')!);
    expect(layer()).toBeNull();
    over(container.querySelector('#plain')!);
    expect(layer()).not.toBeNull();
    out(container.querySelector('#plain')!);
    expect(layer()).toBeNull();
  });
});

// UI-04 part 4 (Otto, 4.11.2026): the full text of a cut-off text shows only while it is really cut, in both steps. jsdom lays nothing out, so
// the widths are set by hand, as a browser would measure them.
describe('TipLayer with the full text of a cut-off text', () => {
  let host: HTMLDivElement;
  let hostRoot: Root;

  const sizes = (el: Element, scrollWidth: number, clientWidth: number) => Object.defineProperties(el, { scrollWidth: { value: scrollWidth, configurable: true }, clientWidth: { value: clientWidth, configurable: true } });
  const hover = (el: Element) => act(() => el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true })));
  const leave = (el: Element) => act(() => el.dispatchEvent(new MouseEvent('mouseout', { bubbles: true })));

  beforeEach(() => {
    host = document.createElement('div');
    document.body.append(host);
    hostRoot = createRoot(host);
    act(() => {
      hostRoot.render(
        <div className="app">
          <span id="own" data-tip="A long name that is cut" data-tip-cut="">A long name that is cut</span>
          <button type="button" id="around" data-tip="A long job title" data-tip-cut=".title">
            <span className="title">A long job title</span>
          </button>
          <TipLayer />
        </div>,
      );
    });
  });

  afterEach(() => {
    setTipLevel('advanced');
    act(() => hostRoot.unmount());
    host.remove();
  });

  const shown = () => document.body.querySelectorAll('.tip-layer')[0]?.textContent ?? null;

  it.each(['simple', 'advanced'] as const)('%s: shows the full text while the text is cut', (level) => {
    setTipLevel(level);
    const own = host.querySelector('#own')!;
    sizes(own, 180, 120);
    hover(own);
    expect(shown()).toBe('A long name that is cut');
  });

  it.each(['simple', 'advanced'] as const)('%s: shows nothing while the text fits, however wide the box is', (level) => {
    setTipLevel(level);
    const own = host.querySelector('#own')!;
    sizes(own, 120, 120);
    hover(own);
    expect(shown()).toBeNull();
    leave(own);
    sizes(own, 60, 300);
    hover(own);
    expect(shown()).toBeNull();
  });

  it('measures the text inside a button, not the button', () => {
    const around = host.querySelector('#around')!;
    sizes(around, 100, 100);
    sizes(around.querySelector('.title')!, 200, 100);
    hover(around);
    expect(shown()).toBe('A long job title');
    leave(around);
    sizes(around, 400, 100);
    sizes(around.querySelector('.title')!, 100, 100);
    hover(around);
    expect(shown()).toBeNull();
  });

  it('follows the text: the same name shows once it is cut by a narrower box, and goes again when the box is wide', () => {
    const own = host.querySelector('#own')!;
    sizes(own, 150, 200);
    hover(own);
    expect(shown()).toBeNull();
    leave(own);
    sizes(own, 150, 90);
    hover(own);
    expect(shown()).toBe('A long name that is cut');
  });
});
