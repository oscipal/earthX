import { describe, expect, it } from 'vitest';

import s2 from './fixtures/processes/sentinel-2-c1-l2a.json';
import dem from './fixtures/processes/cop-dem-glo-30.json';
import { chooseDtype, dtypeOptions, effectiveDtype, passesValues, type StepChoice } from './processingDefaults';
import type { ProcessDescription } from './processing';
import { processInfo, type BandSource } from './processingOrder';

const DTYPES = ['uint8', 'uint16', 'int16', 'uint32', 'int32', 'float32', 'float64'];
// The rule of each operator as the registry publishes it (`x-earthx-passes-values`), from the description of the backend.
const OPERATORS = [...processInfo(s2 as unknown as ProcessDescription).operators, ...processInfo(dem as unknown as ProcessDescription).operators];

function band(over: Partial<BandSource> = {}): BandSource {
  return { asset: 'a', names: ['a'], units: [null], unit: null, dataType: null, scaled: false, nodata: null, ...over };
}

const COUNTS = band({ dataType: 'uint16', nodata: 0 });
const HEIGHTS = band({ dataType: 'int16', nodata: -32768 });
const REFLECTANCE = band({ dataType: 'uint16', nodata: 0, scaled: true });
const MATH: StepChoice = { op: 'band_math', values: { expression: 'a / 2', name: 'x' } };
const reproject = (resampling: string): StepChoice => ({ op: 'reproject', values: { resampling } });
const args = (steps: StepChoice[], bands: BandSource[]) => ({ steps, bands, allowed: DTYPES, operators: OPERATORS });
const offered = (steps: StepChoice[], bands: BandSource[]) => dtypeOptions(args(steps, bands)).map((o) => o.value);

describe('the rule of the registry (x-earthx-passes-values)', () => {
  it('is in the description for every operator the panel offers', () => {
    expect(OPERATORS.length).toBeGreaterThan(3);
    expect(Object.fromEntries(OPERATORS.map((o) => [o.op, o.passesValues]))).toMatchObject({
      band_math: false,
      mask: true,
      reproject: { param: 'resampling', in: ['mode', 'nearest'] },
    });
  });

  it('passes the values where every step does, a reprojection by its resampling, nothing for a step it does not know', () => {
    expect(passesValues([], OPERATORS)).toBe(true);
    expect(passesValues([{ op: 'mask', values: {} }, reproject('mode')], OPERATORS)).toBe(true);
    expect(passesValues([reproject('bilinear')], OPERATORS)).toBe(false);
    expect(passesValues([reproject('')], OPERATORS)).toBe(false);
    expect(passesValues([{ op: 'mask', values: {} }, MATH], OPERATORS)).toBe(false);
    expect(passesValues([{ op: 'unknown' }], OPERATORS)).toBe(false);
  });
});

describe('the output types offered (Otto, 11.11.2026): only those that make sense', () => {
  it.each([
    ['no step (the mosaic of whole scenes)', []],
    ['a mask', [{ op: 'mask', values: {} }]],
    ['a mask by value', [{ op: 'mask_values', values: {} }]],
    ['nearest', [reproject('nearest')]],
    ['mode', [reproject('mode')]],
  ] as [string, StepChoice[]][])('are the type of the source and float32 after %s, the type of the source first', (_, steps) => {
    expect(offered(steps, [COUNTS])).toEqual(['uint16', 'float32']);
    expect(offered(steps, [HEIGHTS])).toEqual(['int16', 'float32']);
    expect(chooseDtype(args(steps, [COUNTS]))).toEqual({ value: 'uint16', reason: 'Same type as the source data (uint16).' });
  });

  it.each([
    ['Band math', [MATH]],
    ['Normalize', [{ op: 'normalize', values: {} }]],
    ['an interpolating reprojection', [reproject('bilinear')]],
    ['a reprojection without a resampling yet', [reproject('')]],
    ['a mask before Band math', [{ op: 'mask', values: {} }, MATH]],
  ] as [string, StepChoice[]][])('are float32 only after %s', (_, steps) => {
    expect(offered(steps, [COUNTS])).toEqual(['float32']);
    expect(chooseDtype(args(steps, [COUNTS]))).toEqual({ value: 'float32', reason: 'The steps compute new values; float32 keeps them.' });
  });

  it('are float32 only for a source whose scale the core applies (Sentinel-2): its values are computed anew', () => {
    expect(offered([], [REFLECTANCE])).toEqual(['float32']);
    expect(chooseDtype(args([], [REFLECTANCE])).reason).toMatch(/scaled/u);
  });

  it('are float32 only for bands of different types, or of no stated type', () => {
    expect(offered([], [COUNTS, band({ dataType: 'uint8' })])).toEqual(['float32']);
    expect(offered([], [band()])).toEqual(['float32']);
    expect(offered([], [])).toEqual(['float32']);
  });

  it('keep a float source as it is, and float32 beside it', () => {
    expect(offered([], [band({ dataType: 'float64' })])).toEqual(['float64', 'float32']);
    expect(offered([reproject('nearest')], [band({ dataType: 'float32' })])).toEqual(['float32']);
  });

  it('never offer a type the platform does not write, or one that is "not recommended"', () => {
    expect(dtypeOptions({ ...args([], [COUNTS]), allowed: ['float32'] }).map((o) => o.value)).toEqual(['float32']);
    for (const steps of [[], [MATH]]) for (const option of dtypeOptions(args(steps, [COUNTS]))) expect(option.label).toBe(option.value);
  });
});

describe('the type sent', () => {
  it('is the choice of the user while it makes sense, and float32 once the chain no longer allows it, without a word', () => {
    const passing = dtypeOptions(args([], [COUNTS]));
    const automatic = chooseDtype(args([], [COUNTS]));
    expect(effectiveDtype(null, passing, automatic)).toBe('uint16');
    expect(effectiveDtype('float32', passing, automatic)).toBe('float32');
    expect(effectiveDtype('uint16', dtypeOptions(args([MATH], [COUNTS])), chooseDtype(args([MATH], [COUNTS])))).toBe('float32');
    expect(effectiveDtype('uint16', dtypeOptions(args([], [band({ dataType: 'uint8' })])), chooseDtype(args([], [band({ dataType: 'uint8' })])))).toBe('float32');
  });
});
