// "Copy original scene name" (Otto, 3.11.2026, zu #282): the names as they are copied, and where they come from.

import { describe, expect, it, vi } from 'vitest';

import type { Order } from './processing';
import { copyNames, copyTip, sceneNamesOfOrder, textOfNames } from './sceneNames';

const order = (groups: string[][]): Order =>
  ({ recipe_version: 2, inputs: [{ name: 'input', dataset: 'd', groups }], steps: [], output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['red'] } }) as unknown as Order;

describe('the text', () => {
  it('is one name to a line, each once, in the order given', () => {
    expect(textOfNames(['S2B_2', 'S2A_1', 'S2B_2'])).toBe('S2B_2\nS2A_1');
    expect(textOfNames(['S2A_1'])).toBe('S2A_1');
    expect(textOfNames([])).toBe('');
  });

  it('says "n scenes" in the tooltip for several, and what it copies for one', () => {
    expect(copyTip(3)).toBe('3 scenes');
    expect(copyTip(2)).toBe('2 scenes');
    expect(copyTip(1)).toBe('Copy the name of the original scene');
  });
});

describe('the scenes of an order', () => {
  it('are those of all its groups, each once, in the order of the order', () => {
    expect(sceneNamesOfOrder(order([['S2A_1', 'S2A_2'], ['S2B_1', 'S2A_1']]))).toEqual(['S2A_1', 'S2A_2', 'S2B_1']);
  });

  it.each([
    ['no copy of the order', null],
    ['an order that was never there', undefined],
    ['an order without scenes', order([])],
    ['an order of empty groups', order([[], []])],
  ])('are none for %s', (_, given) => {
    expect(sceneNamesOfOrder(given as Order | null | undefined)).toEqual([]);
  });

  it('leave out what is no name: an empty string, a number', () => {
    expect(sceneNamesOfOrder(order([['S2A_1', '', 7 as unknown as string]]))).toEqual(['S2A_1']);
  });
});

describe('the copy', () => {
  it('writes the text to the clipboard and says it was done', async () => {
    const write = vi.fn(async () => undefined);
    expect(await copyNames(['a', 'b'], write)).toBe(true);
    expect(write).toHaveBeenCalledWith('a\nb');
  });

  it('says it was not where the browser does not let the page', async () => {
    expect(await copyNames(['a'], async () => Promise.reject(new Error('denied')))).toBe(false);
    expect(await copyNames(['a'], () => { throw new Error('no clipboard'); })).toBe(false);
  });
});
