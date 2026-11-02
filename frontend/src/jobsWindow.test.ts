// @vitest-environment jsdom
// UI-03c §7.9: the place and size of the floating window of the jobs, and what is read back from the browser's storage.

import { afterEach, describe, expect, it, vi } from 'vitest';

import { DEFAULT_HEIGHT, DEFAULT_WIDTH, firstBox, HEAD_HEIGHT, keepReachable, KEEP_WIDTH, MIN_HEIGHT, MIN_WIDTH, parseBox, resized } from './jobsWindow';
import { loadJobsWindow, saveJobsWindow } from './preferences';

const BIG = { width: 1920, height: 1080 };
const SMALL = { width: 1280, height: 720 };
const BOX = { x: 100, y: 100, width: 500, height: 400 };

describe('parseBox', () => {
  it('takes four fitting numbers', () => {
    expect(parseBox(BOX)).toEqual(BOX);
    expect(parseBox({ ...BOX, extra: 'ignored' })).toEqual(BOX);
  });

  it.each([
    ['nothing', null],
    ['a string', 'x'],
    ['a number', 5],
    ['a list', [100, 100, 500, 400]],
    ['a missing field', { x: 1, y: 1, width: 500 }],
    ['numbers as text', { x: '100', y: '100', width: '500', height: '400' }],
    ['a place out of reach to the left', { ...BOX, x: KEEP_WIDTH - BOX.width - 1 }],
    ['a negative top', { ...BOX, y: -20 }],
    ['a negative width', { ...BOX, width: -500 }],
    ['not a number', { ...BOX, width: Number.NaN }],
    ['an absurd place', { ...BOX, x: 1e9 }],
    ['a width under the minimum', { ...BOX, width: MIN_WIDTH - 1 }],
    ['a height under the minimum', { ...BOX, height: MIN_HEIGHT - 1 }],
    ['null fields', { x: null, y: null, width: null, height: null }],
  ])('refuses %s', (_name, value) => {
    expect(parseBox(value)).toBeNull();
  });

  it('keeps the minimum itself', () => {
    expect(parseBox({ x: 0, y: 0, width: MIN_WIDTH, height: MIN_HEIGHT })).not.toBeNull();
  });

  it('keeps a window that was pushed half out at the left, as far as 120 px of it show', () => {
    expect(parseBox({ ...BOX, x: KEEP_WIDTH - BOX.width })).toEqual({ ...BOX, x: KEEP_WIDTH - BOX.width });
    expect(parseBox({ ...BOX, x: -50 })).toEqual({ ...BOX, x: -50 });
  });

  it('keeps what keepReachable makes of any box', () => {
    for (const x of [-9000, -1, 0, 5000]) for (const y of [-9000, 0, 5000]) {
      const kept = keepReachable({ x, y, width: 480, height: 640 }, { width: 1280, height: 800 });
      expect(parseBox(kept), JSON.stringify(kept)).toEqual(kept);
    }
  });
});

describe('firstBox', () => {
  it('opens at 480 × 640, under the buttons at the top and at the given left edge', () => {
    expect(firstBox(BIG, 404)).toEqual({ x: 404, y: 64, width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT });
  });

  it('is never higher than the window minus 80 px', () => {
    expect(firstBox({ width: 1280, height: 600 }, 64).height).toBe(520);
    expect(firstBox(SMALL, 64).height).toBe(640);
  });

  it('is never larger than the window, nor smaller than the minimum where the window allows it', () => {
    expect(firstBox({ width: 300, height: 400 }, 0).width).toBe(300);
    expect(firstBox({ width: 1280, height: 330 }, 0).height).toBe(MIN_HEIGHT);
    expect(firstBox({ width: 1280, height: 200 }, 0).height).toBe(200);
  });

  it('keeps itself in the window when the left edge is far right', () => {
    const box = firstBox(SMALL, 5000);
    expect(box.x).toBe(SMALL.width - KEEP_WIDTH);
  });
});

describe('keepReachable', () => {
  it('leaves a box that fits', () => {
    expect(keepReachable(BOX, BIG)).toEqual(BOX);
  });

  it('keeps the head in the window: not above the top, not below a head height from the bottom', () => {
    expect(keepReachable({ ...BOX, y: -300 }, BIG).y).toBe(0);
    expect(keepReachable({ ...BOX, y: 5000 }, BIG).y).toBe(BIG.height - HEAD_HEIGHT);
  });

  it('keeps 120 px of its width in the window, to the left and to the right', () => {
    expect(keepReachable({ ...BOX, x: -5000 }, BIG).x).toBe(KEEP_WIDTH - BOX.width);
    expect(keepReachable({ ...BOX, x: 5000 }, BIG).x).toBe(BIG.width - KEEP_WIDTH);
  });

  it('shrinks to the window, and pushes back when the window gets smaller', () => {
    const wide = { x: 1500, y: 900, width: 600, height: 700 };
    const pushed = keepReachable(wide, SMALL);
    expect(pushed.x).toBeLessThanOrEqual(SMALL.width - KEEP_WIDTH);
    expect(pushed.y).toBeLessThanOrEqual(SMALL.height - HEAD_HEIGHT);
    expect(pushed.height).toBeLessThanOrEqual(SMALL.height);
    expect(keepReachable({ ...BOX, width: 5000, height: 5000 }, SMALL)).toMatchObject({ width: SMALL.width, height: SMALL.height });
  });

  it('holds the minimum size', () => {
    expect(keepReachable({ ...BOX, width: 10, height: 10 }, BIG)).toMatchObject({ width: MIN_WIDTH, height: MIN_HEIGHT });
  });
});

describe('resized', () => {
  it('pulls the right edge, the bottom edge or the corner; the top left stays', () => {
    expect(resized(BOX, 'e', 50, 70, BIG)).toEqual({ ...BOX, width: 550 });
    expect(resized(BOX, 's', 50, 70, BIG)).toEqual({ ...BOX, height: 470 });
    expect(resized(BOX, 'se', 50, 70, BIG)).toEqual({ ...BOX, width: 550, height: 470 });
  });

  it('stops at the minimum and at the window', () => {
    expect(resized(BOX, 'se', -5000, -5000, BIG)).toMatchObject({ width: MIN_WIDTH, height: MIN_HEIGHT });
    expect(resized(BOX, 'se', 5000, 5000, BIG)).toMatchObject({ width: BIG.width, height: BIG.height });
  });
});

describe('what the browser kept (earthx.jobsWindow)', () => {
  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('reads back what was saved, rounded to whole pixels', () => {
    saveJobsWindow({ x: 10.4, y: 20.6, width: 500.2, height: 400.9 });
    expect(localStorage.getItem('earthx.jobsWindow')).toBe('{"x":10,"y":21,"width":500,"height":401}');
    expect(loadJobsWindow()).toEqual({ x: 10, y: 21, width: 500, height: 401 });
  });

  it('gives nothing for an empty, broken or foreign value', () => {
    expect(loadJobsWindow()).toBeNull();
    for (const raw of ['', 'not json', '{', '[]', '"x"', 'null', '{"x":1}', '{"x":0,"y":-1,"width":500,"height":400}', '{"x":"1","y":0,"width":500,"height":400}']) {
      localStorage.setItem('earthx.jobsWindow', raw);
      expect(loadJobsWindow(), raw).toBeNull();
    }
  });

  it('gives nothing, and does not throw, where the storage cannot be read or written', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError');
    });
    expect(loadJobsWindow()).toBeNull();
    expect(() => saveJobsWindow(BOX)).not.toThrow();
  });
});
