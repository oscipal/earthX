// @vitest-environment jsdom
//
// The tooltip's placement (NM4-52): above the element if it fits there, else below or beside, always inside
// the window with a margin of 8 px.

import { describe, expect, it } from 'vitest';

import { placeTip } from './tipPlacement';

const WINDOW = { width: 1000, height: 800 };
const SIZE = { width: 200, height: 40 };
const anchorAt = (top: number, left: number, w = 20, h = 20) => ({ top, bottom: top + h, left, right: left + w });

describe('placeTip', () => {
  it('goes above the element and is centred on it', () => {
    expect(placeTip(anchorAt(300, 400), SIZE, WINDOW)).toEqual({ side: 'top', top: 254, left: 310 });
  });

  it('flips below when there is no room above', () => {
    expect(placeTip(anchorAt(20, 400), SIZE, WINDOW)).toMatchObject({ side: 'bottom', top: 46 });
  });

  it('stays inside the window at the left and right edge', () => {
    expect(placeTip(anchorAt(300, 0), SIZE, WINDOW).left).toBe(8);
    expect(placeTip(anchorAt(300, 980), SIZE, WINDOW).left).toBe(1000 - 8 - 200);
  });

  it('honours a preferred side and flips it when it does not fit', () => {
    expect(placeTip(anchorAt(300, 50), SIZE, WINDOW, 'right')).toMatchObject({ side: 'right', left: 76 });
    expect(placeTip(anchorAt(300, 900), SIZE, WINDOW, 'right')).toMatchObject({ side: 'left' });
  });

  it('keeps a tooltip inside a window too small for it on every side', () => {
    const tiny = { width: 150, height: 60 };
    const p = placeTip(anchorAt(20, 60), SIZE, tiny);
    expect(p.left).toBeGreaterThanOrEqual(8);
    expect(p.top).toBeGreaterThanOrEqual(8);
  });
});
