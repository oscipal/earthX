// The stock of bands the panel works with (adr/0020 §4, §6, §9, NM4-43e): names of results, renaming, the order of the
// output.

import { describe, expect, it } from 'vitest';

import {
  assetsCarrying,
  bandNamesOf,
  defaultName,
  dropFromNormalize,
  nameProblem,
  outputBands,
  ownersOf,
  renameInExpression,
  renameResult,
  resultsOf,
} from './processingBands';
import type { BandSource, DraftStep } from './processingOrder';

const DATA = ['coastal', 'blue', 'green', 'red', 'nir', 'scl'];

const source = (asset: string, names: string[] = []): BandSource => ({
  asset, names, units: names.map(() => null), unit: null, dataType: 'uint16', scaled: false, nodata: null,
});

const mathStep = (key: number, name: string, expression: string, applied?: string): DraftStep => ({
  key, op: 'band_math', opVersion: 2, values: { expression, name }, ...(applied ? { applied } : {}),
});
const normalizeStep = (key: number, bands: string): DraftStep => ({
  key, op: 'normalize', opVersion: 2, values: { in_min: '0', in_max: '1', out_min: '0', out_max: '1', clip: false, bands },
});

describe('the name of a band a step adds', () => {
  it('takes letters, digits and _, a letter first, up to 32 characters', () => {
    expect(nameProblem('NDVI', [], DATA)).toBeNull();
    expect(nameProblem('ndvi_2', [], DATA)).toBeNull();
    expect(nameProblem('A'.repeat(32), [], DATA)).toBeNull();
    for (const bad of ['', '1ndvi', '_ndvi', 'nd vi', 'ndvi-2', 'ndvi.', 'ndvé', 'A'.repeat(33)]) {
      expect(nameProblem(bad, [], DATA), bad).not.toBeNull();
    }
    expect(nameProblem('', [], DATA)).toBe('Enter a name.');
  });

  it('refuses a Python keyword, which an expression could not name', () => {
    for (const word of ['in', 'and', 'not', 'if', 'True', 'None', 'lambda']) {
      expect(nameProblem(word, [], DATA)).toBe(`${word} is a Python keyword, so an expression cannot use it.`);
    }
  });

  it('refuses the name of a function of an expression', () => {
    for (const word of ['where', 'abs', 'minimum', 'maximum', 'sqrt']) {
      expect(nameProblem(word, [], DATA)).toBe(`${word} is a function, so an expression cannot use it as a band.`);
    }
  });

  it('refuses a band of the data, ignoring case, the ones nobody reads included', () => {
    expect(nameProblem('red', [], DATA)).toBe('red is a band of the data.');
    expect(nameProblem('RED', [], DATA)).toBe('RED is a band of the data.');
    expect(nameProblem('Scl', [], DATA)).toBe('Scl is a band of the data.');
  });

  it('refuses a name another result has, ignoring case', () => {
    expect(nameProblem('NDVI', ['NDVI'], DATA)).toBe('NDVI is used twice.');
    expect(nameProblem('ndvi', ['NDVI'], DATA)).toBe('ndvi is used twice.');
    expect(nameProblem('NDWI', ['NDVI'], DATA)).toBeNull();
  });

  it('is Band_Math_<n> by default, the next free number from the place of the step', () => {
    expect(defaultName(1, [])).toBe('Band_Math_1');
    expect(defaultName(2, ['Band_Math_1'])).toBe('Band_Math_2');
    expect(defaultName(1, ['Band_Math_1', 'band_math_2'])).toBe('Band_Math_3');
    expect(defaultName(3, ['Band_Math_3'])).toBe('Band_Math_4');
  });
});

describe('renaming a result', () => {
  it('replaces the name token by token, not inside a longer name or a number', () => {
    expect(renameInExpression('NDVI * 2 + NDVI2 + xNDVI + NDVI_b + 1e5', 'NDVI', 'Index')).toBe(
      'Index * 2 + NDVI2 + xNDVI + NDVI_b + 1e5',
    );
    expect(renameInExpression('where(NDVI > 0.3, NDVI, 0)', 'NDVI', 'V')).toBe('where(V > 0.3, V, 0)');
  });

  it('follows into the expressions and the normalize steps after the step, and into nothing before it', () => {
    const steps = [
      mathStep(1, 'Band_Math_1', '(nir - red) / (nir + red)'),
      mathStep(2, 'Band_Math_2', 'Band_Math_1 * 2'),
      normalizeStep(3, 'Band_Math_1, red'),
      mathStep(4, 'Other', 'Band_Math_1 + Band_Math_2'),
    ];
    const renamed = renameResult(steps, 1, 'Band_Math_1', 'NDVI');
    expect(renamed[0]).toBe(steps[0]);
    expect(renamed[1].values.expression).toBe('NDVI * 2');
    expect(renamed[2].values.bands).toBe('NDVI, red');
    expect(renamed[3].values.expression).toBe('NDVI + Band_Math_2');
    expect(steps[1].values.expression).toBe('Band_Math_1 * 2');
  });

  it('leaves a step before the step that adds the band alone', () => {
    const steps = [mathStep(1, 'A', 'Band_Math_2 + 1'), mathStep(2, 'Band_Math_2', 'red')];
    expect(renameResult(steps, 2, 'Band_Math_2', 'B')[0].values.expression).toBe('Band_Math_2 + 1');
  });

  it('takes a removed result out of the bands of a normalize step', () => {
    const steps = [normalizeStep(3, 'NDVI, red'), normalizeStep(4, 'NDVI')];
    expect(dropFromNormalize(steps, 'NDVI').map((s) => s.values.bands)).toEqual(['red', '']);
  });

  it('lists the name the references follow, the typed one where none was applied yet', () => {
    const steps = [mathStep(1, 'ND', 'nir', 'NDVI'), mathStep(2, 'B', 'nir')];
    expect(resultsOf(steps)).toEqual([{ key: 1, name: 'NDVI' }, { key: 2, name: 'B' }]);
  });
});

describe('the bands of the output', () => {
  it('are the results in step order, then the bands of the data in the order of the item', () => {
    expect(outputBands(['red', 'NDWI', 'coastal', 'NDVI'], ['NDVI', 'NDWI'], DATA)).toEqual(['NDVI', 'NDWI', 'coastal', 'red']);
  });

  it('is one order for one choice, whichever way it was clicked', () => {
    const results = ['A', 'B'];
    expect(outputBands(['nir', 'B', 'red', 'A'], results, DATA)).toEqual(outputBands(['A', 'red', 'B', 'nir'], results, DATA));
  });

  it('keeps a name the selection does not know at the end, so that the server can say so', () => {
    expect(outputBands(['red', 'B99', 'NDVI'], ['NDVI'], DATA)).toEqual(['NDVI', 'red', 'B99']);
  });

  it('names a band that is both a result and a band of the data once', () => {
    expect(outputBands(['red'], ['red'], DATA)).toEqual(['red']);
  });

  it('is empty for no choice', () => {
    expect(outputBands([], ['NDVI'], DATA)).toEqual([]);
  });
});

describe('which asset carries a name', () => {
  const sources = [source('red', ['red']), source('visual', ['visual_1', 'visual_2']), source('dem'), source('a:b04', ['b04']), source('c:b04', ['b04'])];

  it('names an asset the item does not describe like its key', () => {
    expect(bandNamesOf(sources[2])).toEqual(['dem']);
    expect(bandNamesOf(sources[1])).toEqual(['visual_1', 'visual_2']);
  });

  it('gives a name no owner where two assets carry it', () => {
    const owners = ownersOf(sources);
    expect(owners.get('red')).toBe('red');
    expect(owners.get('visual_2')).toBe('visual');
    expect(owners.get('dem')).toBe('dem');
    expect(owners.has('b04')).toBe(false);
  });

  it('lists the assets that carry the names, in the order of the item, and none for a result or a typo', () => {
    expect(assetsCarrying(sources, ['visual_2', 'red', 'NDVI', 'b04'])).toEqual(['red', 'visual']);
    expect(assetsCarrying(sources, [])).toEqual([]);
  });
});
