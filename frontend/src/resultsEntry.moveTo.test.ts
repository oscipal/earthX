// NM4-65 part 1: a row moved to a place of the list in one go, by its grip. The same list as the steps of ▲/▼ give.

import { describe, expect, it } from 'vitest';

import type { MapLayer } from './layers';
import { moveEntry, moveEntryTo } from './resultsEntry';

const layer = (id: string): MapLayer => ({ id, name: id, visible: true, opacity: 1, overlays: [], restore: {} as never });
const ABCD = ['A', 'B', 'C', 'D'].map(layer);
const ids = (r: { layers: MapLayer[] } | null) => r?.layers.map((l) => l.id).join('');

describe('moveEntryTo', () => {
  it('puts a layer at the place it is dropped on, up and down', () => {
    expect(ids(moveEntryTo(ABCD, 0, 'D', 0, false))).toBe('DABC');
    expect(ids(moveEntryTo(ABCD, 0, 'A', 3, false))).toBe('BCDA');
    expect(ids(moveEntryTo(ABCD, 0, 'B', 2, false))).toBe('ACBD');
  });

  it('is the same list as ▲/▼ step by step', () => {
    let layers = ABCD;
    let at = 2;
    const target = moveEntryTo(layers, at, 'A', 4, true)!;
    for (let step = 0; step < 4; step++) {
      const next = moveEntry(layers, at, 'A', 'down', true)!;
      layers = next.layers;
      at = next.resultsAt;
    }
    expect([layers.map((l) => l.id).join(''), at]).toEqual([ids(target), target.resultsAt]);
  });

  it('moves the row "Results" like a layer and keeps count of the layers above it', () => {
    // Rows: A B [Results] C D
    expect(moveEntryTo(ABCD, 2, null, 0, true)).toMatchObject({ resultsAt: 0 });
    expect(moveEntryTo(ABCD, 2, null, 4, true)).toMatchObject({ resultsAt: 4 });
    expect(ids(moveEntryTo(ABCD, 2, 'D', 0, true))).toBe('DABC');
    // D from the bottom to the top puts "Results" one place lower: three layers above it now.
    expect(moveEntryTo(ABCD, 2, 'D', 0, true)).toMatchObject({ resultsAt: 3 });
    // A layer dropped on the place of "Results" takes it, and "Results" gives way.
    expect(moveEntryTo(ABCD, 2, 'A', 2, true)).toMatchObject({ resultsAt: 1 });
    expect(ids(moveEntryTo(ABCD, 2, 'A', 2, true))).toBe('BACD');
  });

  it('does not move what is dropped on its own place, and no row that is not there', () => {
    expect(moveEntryTo(ABCD, 0, 'B', 1, false)).toBeNull();
    expect(moveEntryTo(ABCD, 2, null, 2, true)).toBeNull();
    expect(moveEntryTo(ABCD, 0, 'Z', 1, false)).toBeNull();
    // Without the entry "Results" in the list nothing stands for it.
    expect(moveEntryTo(ABCD, 0, null, 1, false)).toBeNull();
  });

  it('keeps a place outside the list inside it, and refuses a place that is no number', () => {
    expect(ids(moveEntryTo(ABCD, 0, 'B', -5, false))).toBe('BACD');
    expect(ids(moveEntryTo(ABCD, 0, 'B', 99, false))).toBe('ACDB');
    expect(moveEntryTo(ABCD, 0, 'B', Number.NaN, false)).toBeNull();
    expect(moveEntryTo(ABCD, 0, 'B', Number.POSITIVE_INFINITY, false)).toBeNull();
  });

  it('leaves the list it was given alone and loses no layer', () => {
    const before = [...ABCD];
    const moved = moveEntryTo(ABCD, 1, 'C', 0, true)!;
    expect(ABCD).toEqual(before);
    expect(moved.layers.map((l) => l.id).sort().join('')).toBe('ABCD');
  });

  it('holds "Results" in range when the stored place is outside the list', () => {
    expect(moveEntryTo(ABCD, 99, 'A', 4, true)).toMatchObject({ resultsAt: 3 });
  });
});
