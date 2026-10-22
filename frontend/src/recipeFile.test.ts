import { describe, expect, it } from 'vitest';

import { MAX_RECIPE_BYTES, readRecipe } from './recipeFile';

const AOI = { type: 'Polygon', coordinates: [[[9, 47], [9.05, 47], [9.05, 47.05], [9, 47]]] };
const recipe = (patch: Record<string, unknown> = {}) => ({
  recipe_version: 1,
  inputs: [{ name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['A', 'B']], assets: ['red', 'nir'] }],
  aoi: AOI,
  steps: [{ op: 'band_math', op_version: 1, params: { expression: '(nir - red) / (nir + red)' } }],
  output: { kind: 'raster', format: 'cog', dtype: 'float32' },
  ...patch,
});
const read = (value: unknown) => readRecipe(JSON.stringify(value));
const reason = (value: unknown) => {
  const result = read(value);
  if (result.ok) throw new Error('read');
  return result.reason;
};

describe('readRecipe', () => {
  it('takes a recipe and leaves out what the panel has no use for', () => {
    const result = read({ ...recipe(), resolved: [{ x: 1 }], provenance: { execution: 'cloud' }, recipe_id: 'secret' });
    expect(result).toEqual({ ok: true, order: recipe() });
  });

  it('takes the recipe of a crop, with no steps', () => {
    const output = { kind: 'crop', format: 'cog', resolution_factor: 1, extent: 'bbox(aoi ∩ footprints)', mask: 'file' };
    const result = read(recipe({ steps: [], output }));
    expect(result.ok && result.order.output).toEqual(output);
  });

  it('strips what an AOI carries beyond its type and coordinates', () => {
    const result = read(recipe({ aoi: { ...AOI, bbox: [9, 47, 9.05, 47.05], properties: { source: 'x' } } }));
    expect(result.ok && result.order.aoi).toEqual(AOI);
  });

  it('refuses a file that is not JSON, or larger than the job route takes', () => {
    expect(readRecipe('{"recipe_version": ')).toEqual({ ok: false, reason: 'The file is not valid JSON.' });
    const big = JSON.stringify(recipe({ note: 'x'.repeat(MAX_RECIPE_BYTES) }));
    expect(readRecipe(big)).toEqual({ ok: false, reason: 'The file is larger than 1 MB.' });
  });

  it('refuses something that is no recipe', () => {
    expect(reason({ type: 'FeatureCollection', features: [] })).toMatch(/not a recipe/u);
    expect(reason([1, 2])).toMatch(/not a recipe/u);
    expect(reason(null)).toMatch(/not a recipe/u);
  });

  it('refuses an unknown recipe version', () => {
    expect(reason(recipe({ recipe_version: 2 }))).toBe('Recipe version 2 is not supported.');
  });

  it('refuses a recipe without inputs or without a steps list', () => {
    expect(reason(recipe({ inputs: [] }))).toMatch(/no inputs/u);
    const { steps: _steps, ...rest } = recipe();
    expect(reason(rest)).toMatch(/no steps list/u);
  });

  it('refuses incomplete inputs and steps', () => {
    expect(reason(recipe({ inputs: [{ dataset: 'x', groups: [], assets: [] }] }))).toMatch(/no scenes/u);
    expect(reason(recipe({ inputs: [{ dataset: 'x', groups: [[1]], assets: [] }] }))).toMatch(/no scenes/u);
    expect(reason(recipe({ steps: [{ op: 'band_math' }] }))).toMatch(/step 1 names no operator/u);
    expect(reason(recipe({ steps: [{ op: 'band_math', op_version: 1, params: [] }] }))).toMatch(/no parameters object/u);
  });

  it('refuses more than one dataset, and more than one input', () => {
    const input = recipe().inputs[0];
    expect(reason(recipe({ inputs: [input, { ...input, dataset: 'cop-dem-glo-30' }] }))).toMatch(/more than one dataset/u);
    expect(reason(recipe({ inputs: [input, input] }))).toMatch(/more than one input/u);
  });

  it('refuses an AOI that is no polygon, and an output it does not know', () => {
    expect(reason(recipe({ aoi: { type: 'Point', coordinates: [9, 47] } }))).toMatch(/not a polygon/u);
    expect(reason(recipe({ aoi: { type: 'Polygon', coordinates: [[[9, 'x']]] } }))).toMatch(/not a polygon/u);
    expect(reason(recipe({ output: { kind: 'vector' } }))).toMatch(/no known output/u);
    expect(reason(recipe({ output: { kind: 'raster' } }))).toMatch(/no output data type/u);
  });
});
