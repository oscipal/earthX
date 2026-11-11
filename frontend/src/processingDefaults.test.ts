import { describe, expect, it } from 'vitest';

import { chooseDtype, dtypeOptions, edgeNodata, effectiveDtype, integerNote, nodataMisfit } from './processingDefaults';
import type { BandSource } from './processingOrder';

const DTYPES = ['uint8', 'uint16', 'int16', 'uint32', 'int32', 'float32', 'float64'];

function band(over: Partial<BandSource> = {}): BandSource {
  return { asset: 'a', names: ['a'], units: [null], unit: null, dataType: null, scaled: false, nodata: null, ...over };
}

// A raster of integers whose item states one nodata value and no scaling.
const COUNTS = band({ dataType: 'uint16', nodata: 0 });
const NEAREST = [{ op: 'reproject', resampling: 'nearest' }];
const BILINEAR = [{ op: 'reproject', resampling: 'bilinear' }];
const UNCHOSEN = [{ op: 'reproject', resampling: '' }];

describe('chooseDtype (Otto, 12.10.2026): the type of the source data wherever the platform can write it', () => {
  const choose = (steps: { op: string; resampling?: string }[], bands: BandSource[], allowed = DTYPES) =>
    chooseDtype({ steps, bands, allowed }).value;

  it('is float32 after band math, whatever the input is', () => {
    expect(choose([{ op: 'band_math' }], [COUNTS])).toBe('float32');
    expect(choose([{ op: 'reproject', resampling: 'nearest' }, { op: 'band_math' }], [COUNTS])).toBe('float32');
  });

  it('is float32 after normalize on integer bands that state their nodata and are not scaled (Otto, 22.10.2026)', () => {
    // The run ends in float32 with NaN as nodata; the source type would be refused (`core._nodata_for`).
    expect(choose([{ op: 'normalize' }], [COUNTS])).toBe('float32');
    expect(choose([{ op: 'mask' }, { op: 'normalize' }], [COUNTS])).toBe('float32');
    expect(choose([{ op: 'normalize' }, { op: 'reproject', resampling: 'nearest' }], [COUNTS])).toBe('float32');
    expect(chooseDtype({ steps: [{ op: 'normalize' }], bands: [COUNTS], allowed: DTYPES }).reason).toBe('Normalize gives fractions.');
  });

  it('keeps the source type after a mask alone: it only hides pixels', () => {
    expect(choose([{ op: 'mask' }], [COUNTS])).toBe('uint16');
  });

  it('keeps a float source type, interpolated or not', () => {
    const float64 = band({ dataType: 'float64' });
    expect(choose(BILINEAR, [float64])).toBe('float64');
    expect(choose(NEAREST, [float64])).toBe('float64');
    expect(choose(UNCHOSEN, [band({ dataType: 'float32' })])).toBe('float32');
  });

  it('keeps the integer type for nearest when the item states one nodata value and no scaling', () => {
    expect(choose(NEAREST, [COUNTS])).toBe('uint16');
    expect(choose(NEAREST, [COUNTS, band({ asset: 'b', dataType: 'uint16', nodata: 0 })])).toBe('uint16');
  });

  it('keeps the integer type of the source for a mosaic without steps, when the item states one nodata value', () => {
    expect(choose([], [COUNTS])).toBe('uint16');
    expect(choose([], [band({ dataType: 'uint8', nodata: 0 })])).toBe('uint8');
  });

  it('is float32 for a mosaic without steps where the item states no nodata value or the values are scaled', () => {
    expect(choose([], [band({ dataType: 'uint16' })])).toBe('float32');
    expect(choose([], [band({ dataType: 'uint16', nodata: 0, scaled: true })])).toBe('float32');
    expect(choose([], [])).toBe('float32');
  });

  it('keeps the integer type for mode as for nearest: both only pick a source value (M4-24)', () => {
    expect(choose([{ op: 'reproject', resampling: 'mode' }], [COUNTS])).toBe('uint16');
    expect(choose([{ op: 'reproject', resampling: 'mode' }], [band({ dataType: 'uint16' })])).toBe('float32');
  });

  it('is float32 for integers while the resampling is interpolating or not chosen yet', () => {
    expect(choose(BILINEAR, [COUNTS])).toBe('float32');
    for (const resampling of ['cubic', 'cubicspline', 'lanczos', 'average']) {
      expect(choose([{ op: 'reproject', resampling }], [COUNTS])).toBe('float32');
    }
    expect(choose(UNCHOSEN, [COUNTS])).toBe('float32');
    expect(choose([...NEAREST, ...BILINEAR], [COUNTS])).toBe('float32');
  });

  it('is float32 where the item tells nothing about the source (the DEM)', () => {
    expect(choose(BILINEAR, [band()])).toBe('float32');
    expect(choose(NEAREST, [band()])).toBe('float32');
    expect(choose(NEAREST, [])).toBe('float32');
  });

  it.each([
    ['no nodata value', band({ dataType: 'uint16' })],
    ['a scaled raster, whose values are no longer the integers', band({ dataType: 'uint16', nodata: 0, scaled: true })],
  ])('is float32 for nearest on integers with %s', (_, source) => {
    expect(choose(NEAREST, [source])).toBe('float32');
  });

  it('is float32 for a scaled float raster too: the core works on the scaled values', () => {
    expect(choose(NEAREST, [band({ dataType: 'float64', scaled: true })])).toBe('float32');
  });

  it('is float32 when the bands differ in type or nodata', () => {
    expect(choose(NEAREST, [COUNTS, band({ dataType: 'uint8', nodata: 0 })])).toBe('float32');
    expect(choose(NEAREST, [COUNTS, band({ dataType: 'uint16', nodata: 1 })])).toBe('float32');
  });

  it('never picks a type the schema does not list', () => {
    expect(choose(NEAREST, [COUNTS], ['float32', 'float64'])).toBe('float32');
    expect(choose(BILINEAR, [band({ dataType: 'float64' })], ['float32'])).toBe('float32');
    expect(choose(BILINEAR, [], ['float64'])).toBe('float64');
  });

  it('says why', () => {
    for (const [steps, bands] of [
      [[{ op: 'band_math' }], []],
      [BILINEAR, [COUNTS]],
      [NEAREST, [COUNTS]],
      [BILINEAR, [band({ dataType: 'float32' })]],
    ] as const) {
      expect(chooseDtype({ steps, bands: [...bands], allowed: DTYPES }).reason).toMatch(/^[A-Z].*\.$/);
    }
  });
});

// A float raster whose item states a nodata no unsigned type holds, as swissALTI3D (−9999).
const HEIGHTS = band({ dataType: 'float32', nodata: -9999 });
// An integer raster whose nodata no unsigned type holds.
const SIGNED = band({ dataType: 'int16', nodata: -32768 });

describe('dtypeOptions (M5-28)', () => {
  it('lists all types of the schema as they are', () => {
    const options = dtypeOptions({ dtypes: DTYPES, steps: NEAREST, bands: [COUNTS] });
    expect(options.map((o) => o.label)).toEqual(DTYPES);
    expect(options.every((o) => o.disabledReason === null)).toBe(true);
  });

  it('offers integer types after band math and normalize: the result carries NaN, not the source nodata', () => {
    for (const op of ['band_math', 'normalize']) {
      const options = dtypeOptions({ dtypes: DTYPES, steps: [{ op }], bands: [HEIGHTS] });
      expect(options.every((o) => o.disabledReason === null)).toBe(true);
    }
  });

  it('does not offer a type that cannot hold a source nodata the result would keep (Otto, 11.11.2026, F7)', () => {
    const options = dtypeOptions({ dtypes: DTYPES, steps: NEAREST, bands: [SIGNED] });
    const refused = options.filter((o) => o.disabledReason);
    expect(refused.map((o) => o.value)).toEqual(['uint8', 'uint16', 'uint32']);
    expect(refused[1].label).toBe('uint16 (nodata does not fit)');
    expect(refused[1].disabledReason).toBe('The source marks missing pixels with -32768, which uint16 cannot hold.');
  });

  it('offers every type where the steps change the values: a float source, interpolation, band math', () => {
    for (const [steps, bands] of [
      [NEAREST, [HEIGHTS]],
      [BILINEAR, [SIGNED]],
      [[{ op: 'band_math' }], [SIGNED]],
    ] as const) {
      expect(dtypeOptions({ dtypes: DTYPES, steps: [...steps], bands: [...bands] }).every((o) => o.disabledReason === null)).toBe(true);
    }
  });
});

describe('nodataMisfit', () => {
  it('names a kept nodata out of range, and nothing where it fits, is not kept, or for float types', () => {
    expect(nodataMisfit('uint8', NEAREST, [band({ dataType: 'uint16', nodata: 256 })])).toMatch(/256, which uint8/);
    expect(nodataMisfit('uint16', [], [SIGNED])).toMatch(/-32768, which uint16/);
    expect(nodataMisfit('int16', NEAREST, [SIGNED])).toBeNull();
    expect(nodataMisfit('uint16', NEAREST, [HEIGHTS])).toBeNull();
    expect(nodataMisfit('uint16', [{ op: 'normalize' }], [SIGNED])).toBeNull();
    expect(nodataMisfit('float32', NEAREST, [SIGNED])).toBeNull();
  });
});

describe('edgeNodata', () => {
  it('is the top of an unsigned type and the bottom of a signed one, so 0 stays a value', () => {
    expect(['uint8', 'uint16', 'uint32', 'int16', 'int32'].map(edgeNodata)).toEqual([255, 65535, 4294967295, -32768, -2147483648]);
  });
});

describe('effectiveDtype', () => {
  const automatic = { value: 'float32', reason: 'x.' };
  const options = dtypeOptions({ dtypes: DTYPES, steps: NEAREST, bands: [SIGNED] });

  it('is the automatic type until the user chooses', () => {
    expect(effectiveDtype(null, options, automatic)).toBe('float32');
  });

  it('is the user choice while it is allowed', () => {
    expect(effectiveDtype('float64', options, automatic)).toBe('float64');
  });

  it('falls back to the automatic type when the choice became one a run refuses for sure', () => {
    expect(effectiveDtype('uint16', options, automatic)).toBe('float32');
    expect(effectiveDtype('complex64', options, automatic)).toBe('float32');
  });
});

describe('integerNote', () => {
  it('names the edge of the type where the source nodata is not kept', () => {
    expect(integerNote('uint16', NEAREST, [band({ dataType: 'uint16' })])).toMatch(/marks missing pixels with 65535/);
    expect(integerNote('int16', [{ op: 'band_math' }], [COUNTS])).toMatch(/with -32768/);
    expect(integerNote('uint16', BILINEAR, [COUNTS])).toMatch(/float32 keeps every value/);
    expect(integerNote('uint16', NEAREST, [band({ dataType: 'uint16', nodata: 0, scaled: true })])).toMatch(/65535/);
    expect(integerNote('uint16', NEAREST, [])).toMatch(/65535/);
  });

  it('stays quiet where the source nodata is kept, and for float types', () => {
    expect(integerNote('uint16', NEAREST, [COUNTS])).toBeNull();
    expect(integerNote('uint8', [{ op: 'mask' }], [COUNTS])).toBeNull();
    expect(integerNote('float32', NEAREST, [band()])).toBeNull();
  });
});
