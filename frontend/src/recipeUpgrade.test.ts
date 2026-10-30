// The rewrite of version 1 as version 2 (adr/0020 §11, NM4-43e). The cases are those of
// `backend/tests/earthx/processing/test_upgrade.py`, which holds the same rule for `api`, the worker and the runner.

import { describe, expect, it } from 'vitest';

import { isVersion1, keyNames, upgradeOrder } from './recipeUpgrade';

const NORMALIZE = { in_min: 0, in_max: 1, out_min: 0, out_max: 255, clip: true };

const step = (op: string, version: number, params: Record<string, unknown>) => ({ op, op_version: version, params });

function order(steps: unknown[], assets: string[] = ['red', 'nir', 'scl']): Record<string, unknown> {
  return {
    recipe_version: 1,
    inputs: [{ name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['ITEM_A']], assets }],
    steps,
    output: { kind: 'raster', format: 'cog', dtype: 'float32' },
  };
}

const bandsOf = (upgraded: Record<string, unknown> | null) => (upgraded!.output as { bands: string[] }).bands;
const stepsOf = (upgraded: Record<string, unknown> | null) => upgraded!.steps as Array<ReturnType<typeof step>>;

describe('an order of version 1 written as version 2', () => {
  it('has no steps: the output is every asset, and the order names no assets', () => {
    const upgraded = upgradeOrder(order([]));
    expect(upgraded?.recipe_version).toBe(2);
    expect(bandsOf(upgraded)).toEqual(['red', 'nir', 'scl']);
    expect((upgraded!.inputs as Array<Record<string, unknown>>)[0]).not.toHaveProperty('assets');
  });

  it('calls the last expression band_math as before and the earlier ones band_math_<n>', () => {
    const upgraded = upgradeOrder(
      order([step('band_math', 1, { expression: 'nir - red' }), step('band_math', 1, { expression: 'band_math * 2' })]),
    );
    expect(stepsOf(upgraded).map((s) => s.params.name)).toEqual(['band_math_1', 'band_math']);
    expect(stepsOf(upgraded)[1].params.expression).toBe('band_math_1 * 2');
    expect(stepsOf(upgraded).map((s) => s.op_version)).toEqual([2, 2]);
    expect(bandsOf(upgraded)).toEqual(['band_math']);
  });

  it('calls a single expression band_math', () => {
    const upgraded = upgradeOrder(order([step('band_math', 1, { expression: 'nir - red' })]));
    expect(stepsOf(upgraded)[0].params).toEqual({ expression: 'nir - red', name: 'band_math' });
  });

  it('gives normalize the bands it saw, the layer gone after a mask', () => {
    const upgraded = upgradeOrder(order([step('mask', 1, { source: 'scl', classes: [3] }), step('normalize', 1, NORMALIZE)]));
    expect(stepsOf(upgraded)[1].params.bands).toEqual(['red', 'nir']);
    expect(stepsOf(upgraded)[1].op_version).toBe(2);
  });

  it('lets a normalize before the mask see the layer too, and leaves the layer out of the output', () => {
    const upgraded = upgradeOrder(order([step('normalize', 1, NORMALIZE), step('mask', 1, { source: 'scl', classes: [3] })]));
    expect(stepsOf(upgraded)[0].params.bands).toEqual(['red', 'nir', 'scl']);
    expect(bandsOf(upgraded)).toEqual(['red', 'nir']);
  });

  it('lets a normalize after an expression see the result alone', () => {
    const upgraded = upgradeOrder(order([step('band_math', 1, { expression: 'nir - red' }), step('normalize', 1, NORMALIZE)]));
    expect(stepsOf(upgraded)[1].params.bands).toEqual(['band_math']);
  });

  it('keeps the parameters of a mask and drops its layer from the output', () => {
    const upgraded = upgradeOrder(order([step('mask', 1, { source: 'scl', classes: [3, 8] })]));
    expect(bandsOf(upgraded)).toEqual(['red', 'nir']);
    expect(stepsOf(upgraded)[0]).toEqual(step('mask', 2, { source: 'scl', classes: [3, 8] }));
  });

  it('keeps reproject as it is, in its place', () => {
    const reproject = step('reproject', 3, { crs: 'EPSG:3035', resolution: 20, resampling: 'nearest', align: false });
    const upgraded = upgradeOrder(order([reproject, step('band_math', 1, { expression: 'nir - red' })]));
    expect(stepsOf(upgraded)[0]).toEqual(reproject);
    expect(stepsOf(upgraded)[1].op_version).toBe(2);
  });

  it('leaves a word that only looks like the old name alone', () => {
    const upgraded = upgradeOrder(
      order([step('band_math', 1, { expression: 'nir - red' }), step('band_math', 1, { expression: 'band_math2 + band_math + 1e5' })]),
    );
    expect(stepsOf(upgraded)[1].params.expression).toBe('band_math2 + band_math_1 + 1e5');
  });

  it('does not change what it was given', () => {
    const given = order([step('band_math', 1, { expression: 'nir - red' })]);
    const before = structuredClone(given);
    upgradeOrder(given);
    expect(given).toEqual(before);
  });

  it('names a Zarr key by its variables, and takes the names of the caller where he knows more', () => {
    expect(bandsOf(upgradeOrder(order([], ['SR_10m:b04', 'SR_20m:b05,b06']), keyNames(':')))).toEqual(['b04', 'b05', 'b06']);
    expect(bandsOf(upgradeOrder(order([], ['visual']), (key) => [`${key}_1`, `${key}_2`, `${key}_3`]))).toEqual([
      'visual_1',
      'visual_2',
      'visual_3',
    ]);
  });

  it('only changes the version of a crop, which has no stock', () => {
    const crop: Record<string, unknown> = {
      ...order([], ['visual']),
      output: { kind: 'crop', format: 'cog', resolution_factor: 1, extent: 'bbox(aoi ∩ footprints)', mask: 'file' },
    };
    const upgraded = upgradeOrder(crop);
    expect(upgraded?.recipe_version).toBe(2);
    expect(upgraded?.inputs).toEqual(crop.inputs);
    expect(upgraded?.output).toEqual(crop.output);
  });

  it.each([
    ['version 2', (o: Record<string, unknown>) => (o.recipe_version = 2)],
    ['a boolean version', (o: Record<string, unknown>) => (o.recipe_version = true)],
    ['no inputs', (o: Record<string, unknown>) => (o.inputs = [])],
    ['inputs that are no list', (o: Record<string, unknown>) => (o.inputs = 'x')],
    ['assets that are no list', (o: Record<string, unknown>) => ((o.inputs as Array<Record<string, unknown>>)[0].assets = 'red')],
    ['assets that are no texts', (o: Record<string, unknown>) => ((o.inputs as Array<Record<string, unknown>>)[0].assets = [1])],
    ['steps that are no list', (o: Record<string, unknown>) => (o.steps = 'x')],
    ['a step that is no object', (o: Record<string, unknown>) => (o.steps = ['x'])],
    ['no output', (o: Record<string, unknown>) => (o.output = null)],
  ])('refuses a document with %s, and says nothing of its values', (_name, break_) => {
    const broken = order([]);
    break_(broken);
    expect(upgradeOrder(broken)).toBeNull();
  });

  it.each(['band_math', 'mask', 'normalize'])('refuses a step of version 2 in a document of version 1 (%s)', (op) => {
    expect(upgradeOrder(order([step(op, 2, { expression: 'red', name: 'Red' })]))).toBeNull();
  });
});

describe('which documents are version 1', () => {
  it('is a number 1, nothing that merely looks like it', () => {
    expect(isVersion1({ recipe_version: 1 })).toBe(true);
    expect(isVersion1({ recipe_version: '1' })).toBe(false);
    expect(isVersion1({ recipe_version: true })).toBe(false);
    expect(isVersion1({ recipe_version: 2 })).toBe(false);
    expect(isVersion1(null)).toBe(false);
    expect(isVersion1([1])).toBe(false);
  });
});
