// UI-12 (12): the steps by which the settings bar fits without scrolling.

import { describe, expect, it } from 'vitest';

import { START, foldOrder, foldedSections, maxColumns, nextFit } from './inspectorFit';

const TITLES = ['Display', 'Quick processing', 'Actions'];

describe('the columns a window allows', () => {
  it('is one under 900 px, and as many as leave the map 240 px beside the rail and the open panel, three at most', () => {
    expect(maxColumns(360, 48)).toBe(1);
    expect(maxColumns(1280, 48)).toBe(3);
    expect(maxColumns(1280, 48 + 340)).toBe(2);
    expect(maxColumns(1000, 48 + 340)).toBe(1);
    expect(maxColumns(3000, 48)).toBe(3);
  });
});

describe('the next step of a bar that overflows', () => {
  const limits = { maxColumns: 2, quickRowsShown: 2, sections: 2 };
  it('takes a column, then fewer rows of "Quick processing", then folds, then stops', () => {
    let fit = START;
    const steps = [];
    for (let next = nextFit(fit, limits); next; next = nextFit(fit, { ...limits, quickRowsShown: Math.min(fit.quickRows, 2) })) {
      fit = next;
      steps.push({ ...fit });
    }
    expect(steps).toEqual([
      { columns: 2, quickRows: Number.POSITIVE_INFINITY, folds: 0 },
      { columns: 2, quickRows: 1, folds: 0 },
      { columns: 2, quickRows: 1, folds: 1 },
      { columns: 2, quickRows: 1, folds: 2 },
    ]);
  });

  it('has nothing left to do with one column, one row and every section that may fold folded', () => {
    expect(nextFit({ columns: 1, quickRows: 1, folds: 2 }, { maxColumns: 1, quickRowsShown: 1, sections: 2 })).toBeNull();
    expect(nextFit(START, { maxColumns: 1, quickRowsShown: 0, sections: 0 })).toBeNull();
  });
});

describe('the sections that fold', () => {
  it('fold from the bottom and never "Display" by themselves', () => {
    expect(foldOrder(TITLES, null)).toEqual(['Actions', 'Quick processing']);
    expect([...foldedSections(TITLES, 1, null)]).toEqual(['Actions']);
  });

  it('leave a section opened by hand open, and fold "Display" for it last', () => {
    expect(foldOrder(TITLES, 'Quick processing')).toEqual(['Actions', 'Display']);
    expect(foldOrder(TITLES, 'Display')).toEqual(['Actions', 'Quick processing']);
    expect([...foldedSections(TITLES, 2, 'Actions')]).toEqual(['Quick processing', 'Display']);
  });
});
