// NM4-59: the place of the entry "Results" among the pinned layers, kept right when layers come, go and move.

import { describe, expect, it } from 'vitest';

import { pinned } from './fixtures/liveMap';
import { clampResultsAt, moveEntry, resultsAtAfterAdding, resultsAtAfterRemoving } from './resultsEntry';

const layers = ['a', 'b', 'c'].map((id) => pinned(id, `https://t/${id}`));
// The list as the layer manager shows it, top to bottom, "Results" as R.
const rows = (moved: { layers: typeof layers; resultsAt: number } | null) => {
  if (!moved) return null;
  const ids = moved.layers.map((l) => l.id);
  return [...ids.slice(0, moved.resultsAt), 'R', ...ids.slice(moved.resultsAt)].join('');
};

describe('a new layer', () => {
  it('goes right under "Results" while "Results" is on top', () => {
    expect(resultsAtAfterAdding(0, 1)).toBe(0);
    expect(resultsAtAfterAdding(0, 3)).toBe(0);
  });

  it('goes on top, over "Results", once "Results" lies lower: "Results" keeps the layers above it', () => {
    expect(resultsAtAfterAdding(1, 1)).toBe(2);
    expect(resultsAtAfterAdding(2, 3)).toBe(5);
  });
});

describe('a layer that goes', () => {
  it('above "Results" moves it up by one', () => {
    expect(resultsAtAfterRemoving(layers, 2, (l) => l.id !== 'a')).toBe(1);
  });

  it('below "Results" leaves it where it is', () => {
    expect(resultsAtAfterRemoving(layers, 1, (l) => l.id !== 'c')).toBe(1);
  });

  it('several at once, above and below', () => {
    expect(resultsAtAfterRemoving(layers, 2, (l) => l.id === 'b')).toBe(1);
    expect(resultsAtAfterRemoving(layers, 3, () => false)).toBe(0);
  });
});

describe('clampResultsAt', () => {
  it('keeps the place inside the list', () => {
    expect(clampResultsAt(-2, layers)).toBe(0);
    expect(clampResultsAt(7, layers)).toBe(3);
    expect(clampResultsAt(2, layers)).toBe(2);
    expect(clampResultsAt(1, [])).toBe(0);
  });
});

describe('moveEntry', () => {
  it.each([
    [0, 'down', 'aRbc'],
    [1, 'down', 'abRc'],
    [2, 'down', 'abcR'],
    [3, 'up', 'abRc'],
    [1, 'up', 'Rabc'],
  ] as const)('moves "Results" from %i %s: %s', (at, dir, want) => {
    expect(rows(moveEntry(layers, at, null, dir))).toBe(want);
  });

  it('does nothing past the ends of the list', () => {
    expect(moveEntry(layers, 0, null, 'up')).toBeNull();
    expect(moveEntry(layers, 3, null, 'down')).toBeNull();
    expect(moveEntry(layers, 3, 'a', 'up')).toBeNull();
    expect(moveEntry(layers, 0, 'c', 'down')).toBeNull();
  });

  it('lets a layer next to "Results" change places with it', () => {
    expect(rows(moveEntry(layers, 1, 'b', 'up'))).toBe('abRc');
    expect(rows(moveEntry(layers, 1, 'a', 'down'))).toBe('Rabc');
    expect(rows(moveEntry(layers, 0, 'a', 'up'))).toBe('aRbc');
  });

  it('swaps two layers on the same side of "Results"', () => {
    expect(rows(moveEntry(layers, 0, 'b', 'up'))).toBe('Rbac');
    expect(rows(moveEntry(layers, 3, 'b', 'down'))).toBe('acbR');
  });

  it('without a row "Results" (no search results) only swaps layers, and "Results" does not move', () => {
    expect(rows(moveEntry(layers, 0, 'b', 'up', false))).toBe('Rbac');
    expect(moveEntry(layers, 0, 'a', 'up', false)).toBeNull();
    expect(rows(moveEntry(layers, 1, 'a', 'down', false))).toBe('bRac');
    expect(moveEntry(layers, 1, null, 'up', false)).toBeNull();
  });

  it('names no layer it does not know', () => {
    expect(moveEntry(layers, 1, 'x', 'up')).toBeNull();
  });

  it('takes a place outside the list as the nearest end', () => {
    expect(rows(moveEntry(layers, 9, null, 'up'))).toBe('abRc');
    expect(rows(moveEntry(layers, -4, null, 'down'))).toBe('aRbc');
  });
});
