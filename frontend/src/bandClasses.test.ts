// The classes of a band (M5-62): read from `earthx:bands` of a collection and from the answer of the bands, each class on its own.
// Synthetic collections only.

import { describe, expect, it } from 'vitest';

import { classBandsOf, classesOfBand, parseClasses } from './bandClasses';
import type { Collection } from './types';

const MAP = [
  { value: 10, name: 'tree_cover', title: 'Tree cover', color_hint: '006400' },
  { value: 60, name: 'bare_sparse_vegetation', title: 'Bare / sparse vegetation', color_hint: 'B4B4B4' },
];
const collection = (bands: unknown): Collection => ({ id: 'x', 'earthx:bands': bands } as Collection);

describe('classesOfBand', () => {
  it('reads the title people read and the colour hint as #rrggbb in lower case', () => {
    const c = collection([{ name: 'map', description: 'Land cover class', 'classification:classes': MAP }]);
    expect(classesOfBand(c, 'map')).toEqual([
      { value: 10, name: 'Tree cover', colour: '#006400' },
      { value: 60, name: 'Bare / sparse vegetation', colour: '#b4b4b4' },
    ]);
  });

  it('has none for a band without classes, an unknown band and a collection without bands', () => {
    const c = collection([{ name: 'red', description: 'Red' }]);
    expect(classesOfBand(c, 'red')).toBeNull();
    expect(classesOfBand(c, 'map')).toBeNull();
    expect(classesOfBand(c, undefined)).toBeNull();
    expect(classesOfBand(collection(undefined), 'map')).toBeNull();
    expect(classesOfBand(collection('map'), 'map')).toBeNull();
  });

  it('leaves out a class that does not read, and has none where no class reads', () => {
    const odd = [
      { value: 1.5, title: 'Half', color_hint: '000000' },
      { value: '20', title: 'Text', color_hint: '000000' },
      { value: 30, title: '', color_hint: '000000' },
      { value: 40, color_hint: '000000' },
      { value: 50, title: 'Short hex', color_hint: 'fff' },
      { value: 70, title: 'Not hex', color_hint: 'gggggg' },
      { value: 80, title: 'With alpha', color_hint: '00000000' },
      { value: 90, title: 'No colour' },
      null,
      'class',
    ];
    const c = collection([{ name: 'map', 'classification:classes': [...odd, MAP[0]] }, { name: 'bad', 'classification:classes': odd }]);
    expect(classesOfBand(c, 'map')).toEqual([{ value: 10, name: 'Tree cover', colour: '#006400' }]);
    expect(classesOfBand(c, 'bad')).toBeNull();
  });
});

describe('parseClasses', () => {
  it('reads value, name and colour of the answer of the bands', () => {
    expect(parseClasses([{ value: 4, name: 'Vegetation', colour: '#2CA02C' }])).toEqual([{ value: 4, name: 'Vegetation', colour: '#2ca02c' }]);
  });

  it('has none for null, an empty list or something else', () => {
    expect(parseClasses(null)).toBeNull();
    expect(parseClasses(undefined)).toBeNull();
    expect(parseClasses([])).toBeNull();
    expect(parseClasses({ value: 4, name: 'Vegetation', colour: '#2ca02c' })).toBeNull();
    expect(parseClasses([{ value: 4, name: 'Vegetation', colour: 'green' }])).toBeNull();
  });
});

describe('classBandsOf', () => {
  it('lists every band with classes in the order of the entry, and nothing else', () => {
    const c = collection([
      { name: 'scl', 'classification:classes': [{ value: 4, title: 'Vegetation', color_hint: '2CA02C' }] },
      { name: 'red', description: 'Red' },
      { name: 'map', 'classification:classes': MAP },
      { name: 7, 'classification:classes': MAP },
    ]);
    expect(classBandsOf(c).map((entry) => entry.band)).toEqual(['scl', 'map']);
    expect(classBandsOf(collection(null))).toEqual([]);
  });
});
