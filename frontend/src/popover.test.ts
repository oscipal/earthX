// @vitest-environment jsdom
//
// The dropdowns' placement (Otto, 30.09.2026): below the anchor when it fits,
// above when there is more room there, never outside the window.

import { describe, expect, it } from 'vitest';

import { focusFirstItem, placePopover } from './popover';

const WINDOW = { width: 1000, height: 800 };
const anchorAt = (top: number, left = 100, width = 300) => ({ top, bottom: top + 30, left, width });

describe('placePopover', () => {
  it('opens below the anchor when the content fits there', () => {
    const p = placePopover(anchorAt(100), 200, WINDOW);
    expect(p).toMatchObject({ above: false, top: 134, left: 100, width: 300 });
    expect(p.maxHeight).toBe(800 - 130 - 4 - 8);
  });

  it('opens above when it does not fit below and there is more room above', () => {
    const p = placePopover(anchorAt(700), 200, WINDOW);
    expect(p.above).toBe(true);
    expect(p.top).toBe(700 - 4 - 200);
    expect(p.top + 200).toBeLessThanOrEqual(700);
  });

  it('stays below, scrolling, when there is more room below than above', () => {
    const p = placePopover(anchorAt(300), 900, WINDOW);
    expect(p.above).toBe(false);
    expect(p.maxHeight).toBe(800 - 330 - 4 - 8);
    expect(p.top + p.maxHeight).toBeLessThanOrEqual(800 - 8);
  });

  it('above, a too tall content is capped to the room there and stays inside the window', () => {
    const p = placePopover(anchorAt(700), 2000, WINDOW);
    expect(p.above).toBe(true);
    expect(p.top).toBe(8);
    expect(p.maxHeight).toBe(700 - 4 - 8);
  });

  it('never runs past the left or right edge, nor wider than the window', () => {
    expect(placePopover(anchorAt(100, 900, 300), 100, WINDOW).left).toBe(1000 - 8 - 300);
    expect(placePopover(anchorAt(100, -50, 300), 100, WINDOW).left).toBe(8);
    expect(placePopover(anchorAt(100, 0, 2000), 100, WINDOW).width).toBe(1000 - 16);
  });

  it('a window too small for anything gives no negative height', () => {
    expect(placePopover(anchorAt(0), 100, { width: 200, height: 20 }).maxHeight).toBe(0);
  });
});

describe('focusFirstItem', () => {
  it('focuses the chosen entry, else the first; nothing to focus is no error', () => {
    const root = document.createElement('div');
    root.innerHTML = '<button role="option">a</button><button role="option" aria-selected="true">b</button>';
    document.body.append(root);
    focusFirstItem(root);
    expect(document.activeElement?.textContent).toBe('b');
    root.innerHTML = '<button role="option">a</button><button role="option">b</button>';
    focusFirstItem(root);
    expect(document.activeElement?.textContent).toBe('a');
    expect(() => focusFirstItem(null)).not.toThrow();
    root.remove();
  });
});
