// NM4-65 part 9: which layer "Flip through layers" goes to, and which it passes by.

import { describe, expect, it } from 'vitest';

import { flipIdOf, flipNext, flipStart, flippable } from './layerFlip';
import type { MapLayer } from './layers';

const layer = (id: string, over: Partial<MapLayer> = {}): MapLayer => ({ id, name: id, visible: true, opacity: 1, overlays: [], restore: {} as never, ...over });
const result = (over: object): MapLayer['result'] => ({ jobID: 'J', expires: '2030-01-01T00:00:00Z', gsd: null, resampled: null, expired: false, dataType: null, stats: null, ...over });
const ABCD = ['a', 'b', 'c', 'd'].map((id) => layer(id));

describe('flippable', () => {
  it('is a layer the map draws: switched on, with results that are there', () => {
    expect(flippable(layer('a'))).toBe(true);
    expect(flippable(layer('a', { visible: false }))).toBe(false);
    expect(flippable(layer('a', { result: result({ expired: true }) }))).toBe(false);
    expect(flippable(layer('a', { result: result({ deleted: true }) }))).toBe(false);
    expect(flippable(layer('a', { result: result({}) }))).toBe(true);
  });
});

describe('flipNext', () => {
  it('goes down and up the list one layer at a time', () => {
    expect(flipNext(ABCD, 'a', 1)).toBe('b');
    expect(flipNext(ABCD, 'c', -1)).toBe('b');
  });

  it('stops at the ends of the list', () => {
    expect(flipNext(ABCD, 'd', 1)).toBe('d');
    expect(flipNext(ABCD, 'a', -1)).toBe('a');
  });

  it('passes by the layers that are switched off, and those whose results are gone', () => {
    const list = [layer('a'), layer('b', { visible: false }), layer('c', { result: result({ expired: true }) }), layer('d')];
    expect(flipNext(list, 'a', 1)).toBe('d');
    expect(flipNext(list, 'd', -1)).toBe('a');
  });

  it('stays where it is when the layers beyond cannot be drawn', () => {
    const list = [layer('a'), layer('b', { visible: false })];
    expect(flipNext(list, 'a', 1)).toBe('a');
  });

  it('moves on from a layer that was switched off while it was flipped to', () => {
    const list = [layer('a'), layer('b', { visible: false }), layer('c')];
    expect(flipNext(list, 'b', 1)).toBe('c');
    expect(flipNext(list, 'b', -1)).toBe('a');
  });

  it('goes to the nearest drawable layer at an end when the one it stood on cannot be drawn there', () => {
    const list = [layer('a'), layer('b'), layer('c', { visible: false })];
    expect(flipNext(list, 'c', 1)).toBe('b');
    expect(flipNext([layer('x', { visible: false }), layer('y'), layer('z')], 'x', -1)).toBe('y');
  });

  it('starts at the first or the last drawable layer from one that is not in the list', () => {
    expect(flipNext(ABCD, 'gone', 1)).toBe('a');
    expect(flipNext(ABCD, 'gone', -1)).toBe('d');
    expect(flipNext(ABCD, null, 1)).toBe('a');
  });

  it('is nothing where no layer can be drawn', () => {
    expect(flipNext([], 'a', 1)).toBeNull();
    expect(flipNext([layer('a', { visible: false })], 'a', 1)).toBeNull();
  });
});

describe('flipStart', () => {
  it('takes the layer asked for, or the first that can be drawn', () => {
    expect(flipStart(ABCD, 'c')).toBe('c');
    expect(flipStart(ABCD, null)).toBe('a');
    expect(flipStart(ABCD, 'gone')).toBe('a');
    expect(flipStart([layer('a', { visible: false }), layer('b')], 'a')).toBe('b');
    expect(flipStart([], null)).toBeNull();
  });
});

describe('flipIdOf', () => {
  it('is the layer while flipping is on and the layer is in the list, and nothing else', () => {
    expect(flipIdOf({ flipThrough: true, flipLayerId: 'b', layers: ABCD })).toBe('b');
    expect(flipIdOf({ flipThrough: false, flipLayerId: 'b', layers: ABCD })).toBeNull();
    expect(flipIdOf({ flipThrough: true, flipLayerId: 'gone', layers: ABCD })).toBeNull();
    expect(flipIdOf({ flipThrough: true, flipLayerId: null, layers: ABCD })).toBeNull();
  });
});
