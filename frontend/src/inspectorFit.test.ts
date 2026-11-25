// UI-12 (4): a page of "Quick processing" loses a row while the settings bar overflows, down to one; the bar itself may scroll (F3 new).

import { describe, expect, it } from 'vitest';

import { QUICK_PER_ROW, fewerQuickRows } from './inspectorFit';

describe('the rows of a page of "Quick processing"', () => {
  it('lose one while the bar overflows', () => {
    expect(fewerQuickRows(3)).toBe(2);
    expect(fewerQuickRows(2)).toBe(1);
  });

  it('keep one at least: then the bar scrolls', () => {
    expect(fewerQuickRows(1)).toBeNull();
    expect(fewerQuickRows(0)).toBeNull();
  });

  it('hold three buttons each', () => {
    expect(QUICK_PER_ROW).toBe(3);
  });
});
