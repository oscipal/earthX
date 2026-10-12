import { describe, expect, it } from 'vitest';

import {
  AFTER_BAND_MATH,
  dtypeOptions,
  effectiveDtype,
  integerNote,
  recommendDtype,
  recommendResampling,
} from './processingDefaults';
import type { BandSource } from './processingOrder';

const DTYPES = ['uint8', 'uint16', 'int16', 'uint32', 'int32', 'float32', 'float64'];

function band(over: Partial<BandSource> = {}): BandSource {
  return { asset: 'a', names: ['a'], dataType: null, classified: false, scaled: false, nodata: null, ...over };
}

// A raster of integers whose item states one nodata value and no scaling.
const COUNTS = band({ dataType: 'uint16', nodata: 0 });
const NEAREST = [{ op: 'reproject', resampling: 'nearest' }];
const BILINEAR = [{ op: 'reproject', resampling: 'bilinear' }];

describe('recommendResampling (Otto, 12.10.2026)', () => {
  it('is nearest for a dataset without the capability interpolation, whatever the bands', () => {
    expect(recommendResampling({ interpolation: false, bands: [band()] }).value).toBe('nearest');
    expect(recommendResampling({ interpolation: undefined, bands: [] }).value).toBe('nearest');
  });

  it('is nearest when a band in the order holds classes or bit fields', () => {
    const rec = recommendResampling({ interpolation: true, bands: [band(), band({ classified: true })] });
    expect(rec.value).toBe('nearest');
    expect(rec.reason).toContain('classes or bit fields');
  });

  it('is bilinear for continuous values, also when the item says nothing about the bands', () => {
    expect(recommendResampling({ interpolation: true, bands: [band(), band({ dataType: 'uint16' })] }).value).toBe('bilinear');
    expect(recommendResampling({ interpolation: true, bands: [] }).value).toBe('bilinear');
  });

  it('says why', () => {
    for (const args of [
      { interpolation: false, bands: [] },
      { interpolation: true, bands: [band({ classified: true })] },
      { interpolation: true, bands: [] },
    ]) {
      expect(recommendResampling(args).reason).toMatch(/^[A-Z].*\.$/);
    }
  });
});

describe('recommendDtype (Otto, 12.10.2026)', () => {
  const rec = (steps: { op: string; resampling?: string }[], bands: BandSource[]) =>
    recommendDtype({ steps, bands, allowed: DTYPES }).value;

  it('is float32 for band math, whatever the input is', () => {
    expect(rec([{ op: 'band_math' }], [COUNTS])).toBe('float32');
    expect(rec([{ op: 'reproject', resampling: 'nearest' }, { op: 'band_math' }], [COUNTS])).toBe('float32');
  });

  it('is float32 for a reprojection of a source that tells nothing (the DEM)', () => {
    expect(rec(BILINEAR, [band()])).toBe('float32');
    expect(rec(NEAREST, [band()])).toBe('float32');
    expect(rec(NEAREST, [])).toBe('float32');
  });

  it('is float32 for an interpolating reprojection of integers', () => {
    expect(rec(BILINEAR, [COUNTS])).toBe('float32');
    expect(rec([{ op: 'reproject', resampling: 'cubic' }], [COUNTS])).toBe('float32');
    expect(rec([...NEAREST, ...BILINEAR], [COUNTS])).toBe('float32');
  });

  it('is the input type for nearest on integers when the item states their nodata', () => {
    expect(rec(NEAREST, [COUNTS])).toBe('uint16');
    expect(rec(NEAREST, [COUNTS, band({ asset: 'b', dataType: 'uint16', nodata: 0 })])).toBe('uint16');
  });

  it.each([
    ['no nodata value', band({ dataType: 'uint16' })],
    ['a scaled raster, whose values are no longer the integers', band({ dataType: 'uint16', nodata: 0, scaled: true })],
    ['a float input', band({ dataType: 'float32', nodata: 0 })],
  ])('stays float32 for nearest on %s', (_, source) => {
    expect(rec(NEAREST, [source])).toBe('float32');
  });

  it('stays float32 when the bands differ in type or nodata', () => {
    expect(rec(NEAREST, [COUNTS, band({ dataType: 'uint8', nodata: 0 })])).toBe('float32');
    expect(rec(NEAREST, [COUNTS, band({ dataType: 'uint16', nodata: 1 })])).toBe('float32');
  });

  it('never recommends a type the schema does not list', () => {
    expect(recommendDtype({ steps: NEAREST, bands: [COUNTS], allowed: ['float32', 'float64'] }).value).toBe('float32');
    expect(recommendDtype({ steps: BILINEAR, bands: [], allowed: ['float64'] }).value).toBe('float64');
  });

  it('says why', () => {
    expect(recommendDtype({ steps: [{ op: 'band_math' }], bands: [], allowed: DTYPES }).reason).toMatch(/^[A-Z].*\.$/);
  });
});

describe('dtypeOptions', () => {
  const recommended = { value: 'float32', reason: 'x.' };

  it('marks the recommended type', () => {
    const options = dtypeOptions({ dtypes: DTYPES, steps: NEAREST, recommended });
    expect(options.find((o) => o.recommended)).toMatchObject({ value: 'float32', label: 'float32 (recommended)' });
    expect(options.filter((o) => o.recommended)).toHaveLength(1);
    expect(options.every((o) => o.disabledReason === null)).toBe(true);
  });

  it('does not offer an integer type after band math, with the reason', () => {
    const options = dtypeOptions({ dtypes: DTYPES, steps: [{ op: 'band_math' }], recommended });
    const integers = options.filter((o) => o.disabledReason);
    expect(integers.map((o) => o.value)).toEqual(['uint8', 'uint16', 'int16', 'uint32', 'int32']);
    expect(integers.every((o) => o.disabledReason === AFTER_BAND_MATH)).toBe(true);
    expect(options.filter((o) => !o.disabledReason).map((o) => o.value)).toEqual(['float32', 'float64']);
  });
});

describe('effectiveDtype', () => {
  const recommended = { value: 'float32', reason: 'x.' };
  const options = dtypeOptions({ dtypes: DTYPES, steps: [{ op: 'band_math' }], recommended });

  it('is the recommendation until the user chooses', () => {
    expect(effectiveDtype(null, options, recommended)).toBe('float32');
  });

  it('is the user choice while it is allowed', () => {
    expect(effectiveDtype('float64', options, recommended)).toBe('float64');
  });

  it('falls back to the recommendation when the choice became one a run refuses for sure', () => {
    expect(effectiveDtype('uint16', options, recommended)).toBe('float32');
    expect(effectiveDtype('complex64', options, recommended)).toBe('float32');
  });
});

describe('integerNote', () => {
  it('warns for an integer type whose nodata the item does not state', () => {
    expect(integerNote('uint16', NEAREST, [band({ dataType: 'uint16' })])).toMatch(/needs a nodata value/);
    expect(integerNote('uint16', NEAREST, [])).toMatch(/float32 always works/);
  });

  it('stays quiet where the item states one nodata value, for float types and after band math', () => {
    expect(integerNote('uint16', NEAREST, [COUNTS])).toBeNull();
    expect(integerNote('float32', NEAREST, [band()])).toBeNull();
    expect(integerNote('uint16', [{ op: 'band_math' }], [band()])).toBeNull();
  });
});
