// The index presets of a dataset (NM4-14b): read from the collection entry by entry, matched by the tokens of their
// expression, and the name a second click gets.

import { afterEach, describe, expect, it, vi } from 'vitest';

import { SENTINEL_2_PRESETS } from './fixtures/indexPresets';
import { indexPresetsOf, presetFor, presetRange, presetTip } from './indexPresets';
import { numberedName } from './processingBands';
import type { Collection } from './types';

const collectionWith = (presets: unknown): Collection => ({ id: 'x', 'earthx:index_presets': presets as unknown[] }) as unknown as Collection;

afterEach(() => vi.restoreAllMocks());

describe('indexPresetsOf', () => {
  it('reads the five presets of Sentinel-2 in the order of the registry', () => {
    const presets = indexPresetsOf(collectionWith(SENTINEL_2_PRESETS));
    expect(presets.map((p) => p.name)).toEqual(['NDVI', 'NDWI', 'NDSI', 'NBR', 'EVI']);
    expect(presets[1]).toMatchObject({ expression: '(green - nir) / (green + nir)', rescale: [-1, 1], colormapName: 'rdbu' });
  });

  it('is nothing for a dataset with an empty list, without the field, or without a collection', () => {
    expect(indexPresetsOf(collectionWith([]))).toEqual([]);
    expect(indexPresetsOf({ id: 'older-backend' } as Collection)).toEqual([]);
    expect(indexPresetsOf(collectionWith(null))).toEqual([]);
    expect(indexPresetsOf(collectionWith('NDVI'))).toEqual([]);
    expect(indexPresetsOf(undefined)).toEqual([]);
  });

  it('leaves out an entry that is not complete, with one line that names no data', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const [ndvi] = SENTINEL_2_PRESETS;
    const broken = [
      null,
      'NDVI',
      [],
      { ...ndvi, name: '' },
      { ...ndvi, title: 7 },
      { ...ndvi, expression: 'red red )' },
      { ...ndvi, rescale: [] },
      { ...ndvi, rescale: [[1, -1]] },
      { ...ndvi, rescale: [[0, Number.NaN]] },
      { ...ndvi, rescale: [[0, 1], [0, 2]] },
      { ...ndvi, rescale: [['0', '1']] },
      { ...ndvi, colormap_name: null },
      { ...ndvi, formula: undefined },
      { ...ndvi, reference: ' ' },
    ];
    expect(indexPresetsOf(collectionWith([...broken, SENTINEL_2_PRESETS[3]])).map((p) => p.name)).toEqual(['NBR']);
    expect(warn).toHaveBeenCalledTimes(broken.length);
    expect(warn.mock.calls.flat().join(' ')).not.toMatch(/NDVI|nir|red/u);
  });

  it('keeps the first of two presets with one name, whatever the case', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const [ndvi] = SENTINEL_2_PRESETS;
    const presets = indexPresetsOf(collectionWith([ndvi, { ...ndvi, name: 'ndvi', expression: 'nir / red' }]));
    expect(presets.map((p) => p.expression)).toEqual([ndvi.expression]);
  });

  it('reads a collection once', () => {
    const collection = collectionWith(SENTINEL_2_PRESETS);
    expect(indexPresetsOf(collection)).toBe(indexPresetsOf(collection));
  });
});

describe('presetFor', () => {
  const presets = indexPresetsOf(collectionWith(SENTINEL_2_PRESETS));

  it('finds the preset whatever the spaces of the expression', () => {
    expect(presetFor(presets, '(nir - red) / (nir + red)')?.name).toBe('NDVI');
    expect(presetFor(presets, '(nir-red)/(nir+red)')?.name).toBe('NDVI');
    expect(presetFor(presets, '  ( nir -red )/( nir+ red )\n')?.name).toBe('NDVI');
    expect(presetFor(presets, '2.5*(nir-red)/(nir+6*red-7.5*blue+1)')?.name).toBe('EVI');
  });

  it('finds none for another expression, even one with the same bands', () => {
    expect(presetFor(presets, '(red - nir) / (red + nir)')).toBeNull();
    expect(presetFor(presets, '(nir - red) / (nir + red) + 0')).toBeNull();
    expect(presetFor(presets, '2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1.0)')).toBeNull();
    expect(presetFor(presets, 'nir - red')).toBeNull();
  });

  it('finds none where there is no expression or no preset', () => {
    expect(presetFor(presets, null)).toBeNull();
    expect(presetFor(presets, undefined)).toBeNull();
    expect(presetFor(presets, '')).toBeNull();
    expect(presetFor(presets, 'red red )')).toBeNull();
    expect(presetFor([], '(nir - red) / (nir + red)')).toBeNull();
  });
});

describe('the texts of a preset', () => {
  const [ndvi, ndwi] = indexPresetsOf(collectionWith(SENTINEL_2_PRESETS));

  it('words the tooltip as title, formula and where the formula is from (KE2), without the link', () => {
    expect(presetTip(ndvi)).toBe('Normalized Difference Vegetation Index: (N - R)/(N + R). Formula: Awesome Spectral Indices.');
    expect(presetTip(ndwi)).toContain('(McFeeters 1996)');
    expect(presetTip(ndvi)).not.toContain('http');
  });

  it('gives the range and colormap as the fields of the panel hold them', () => {
    expect(presetRange(ndwi)).toEqual({ vmin: '-1', vmax: '1', colormap: 'rdbu' });
  });
});

describe('numberedName', () => {
  it('is the name where it is free', () => {
    expect(numberedName('NDVI', ['red', 'nir'])).toBe('NDVI');
  });

  it('counts on from 2, ignoring case, over the names that are taken', () => {
    expect(numberedName('NDVI', ['ndvi'])).toBe('NDVI_2');
    expect(numberedName('NDVI', ['NDVI', 'NDVI_2'])).toBe('NDVI_3');
    expect(numberedName('NDVI', ['NDVI', 'ndvi_3'])).toBe('NDVI_2');
  });
});
