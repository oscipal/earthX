import { describe, expect, it } from 'vitest';

import { DATASETS_PER_ROW, pageCount, pageOf, pageSlice, rowsThatFit, START_DATASET_ROWS } from './datasetPages';

describe('rowsThatFit', () => {
  const STEP = 46;

  it('keeps the rows drawn while the free height holds no further row', () => {
    expect(rowsThatFit(2, 0, STEP)).toBe(2);
    expect(rowsThatFit(2, STEP - 1, STEP)).toBe(2);
  });

  it('adds every row the free height holds, with no upper limit (Otto, 07.11.2026)', () => {
    expect(rowsThatFit(1, STEP, STEP)).toBe(2);
    expect(rowsThatFit(3, STEP, STEP)).toBe(4);
    expect(rowsThatFit(1, 10 * STEP, STEP)).toBe(11);
    expect(rowsThatFit(2, 10 * STEP + STEP - 1, STEP)).toBe(12);
  });

  it('drops as many rows as the panel lacks, but keeps one', () => {
    expect(rowsThatFit(3, -1, STEP)).toBe(2);
    expect(rowsThatFit(3, -STEP - 1, STEP)).toBe(1);
    expect(rowsThatFit(3, -10 * STEP, STEP)).toBe(1);
  });

  it('changes nothing without a layout to measure (no row height, or a height that is no number)', () => {
    expect(rowsThatFit(3, -500, 0)).toBe(3);
    expect(rowsThatFit(5, 500, 0)).toBe(5);
    expect(rowsThatFit(2, Number.POSITIVE_INFINITY, STEP)).toBe(2);
    expect(rowsThatFit(2, Number.NaN, STEP)).toBe(2);
    expect(rowsThatFit(2, -500, Number.NaN)).toBe(2);
    expect(rowsThatFit(0, 0, 0)).toBe(1);
  });
});

describe('pages', () => {
  const SIZE = DATASETS_PER_ROW * START_DATASET_ROWS;

  it('has two to a row, six to a page of three rows, and one page also for none', () => {
    expect(SIZE).toBe(6);
    expect(pageCount(13, DATASETS_PER_ROW * 7)).toBe(1);
    expect(pageCount(0, SIZE)).toBe(1);
    expect(pageCount(6, SIZE)).toBe(1);
    expect(pageCount(7, SIZE)).toBe(2);
    expect(pageCount(13, 2)).toBe(7);
  });

  it('finds the page of an entry, the first for one that is not there', () => {
    expect(pageOf(0, SIZE)).toBe(0);
    expect(pageOf(5, SIZE)).toBe(0);
    expect(pageOf(6, SIZE)).toBe(1);
    expect(pageOf(-1, SIZE)).toBe(0);
  });

  it('cuts the entries of a page, the last one shorter', () => {
    const entries = Array.from({ length: 9 }, (_, i) => i);
    expect(pageSlice(entries, 0, SIZE)).toEqual([0, 1, 2, 3, 4, 5]);
    expect(pageSlice(entries, 1, SIZE)).toEqual([6, 7, 8]);
    expect(pageSlice(entries, 2, SIZE)).toEqual([]);
  });
});
