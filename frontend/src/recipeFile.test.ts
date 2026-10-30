import { describe, expect, it } from 'vitest';

import { MAX_RECIPE_BYTES, readRecipe } from './recipeFile';

const AOI = { type: 'Polygon', coordinates: [[[9, 47], [9.05, 47], [9.05, 47.05], [9, 47]]] };
const recipe = (patch: Record<string, unknown> = {}) => ({
  recipe_version: 2,
  inputs: [{ name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['A', 'B']] }],
  aoi: AOI,
  steps: [{ op: 'band_math', op_version: 2, params: { expression: '(nir - red) / (nir + red)', name: 'NDVI' } }],
  output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['NDVI'] },
  ...patch,
});
const CROP = { kind: 'crop', format: 'cog', resolution_factor: 1, extent: 'bbox(aoi ∩ footprints)', mask: 'file' };
const recipe1 = (patch: Record<string, unknown> = {}) => ({
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
    expect(result).toEqual({ ok: true, order: recipe(), converted: false });
  });

  it('takes version 2 as it is: no assets in the input, the bands in the output', () => {
    const result = read(recipe());
    expect(result.ok && result.order.inputs[0]).toEqual({ name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['A', 'B']] });
    expect(result.ok && result.order.output).toEqual({ kind: 'raster', format: 'cog', dtype: 'float32', bands: ['NDVI'] });
  });

  it('takes the recipe of a crop of version 2, with its assets and no steps', () => {
    const inputs = [{ name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['A']], assets: ['red', 'nir'] }];
    const result = read(recipe({ inputs, steps: [], output: CROP }));
    expect(result).toMatchObject({ ok: true, converted: false, order: { recipe_version: 2, inputs, steps: [], output: CROP } });
  });

  it('refuses a crop of version 2 that names no assets', () => {
    expect(reason(recipe({ steps: [], output: CROP }))).toMatch(/no list of assets/u);
  });

  it('reads version 1 as version 2 and says so: assets leave the input, the names go into the output', () => {
    const result = read(recipe1());
    expect(result).toEqual({
      ok: true,
      converted: true,
      order: {
        recipe_version: 2,
        inputs: [{ name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['A', 'B']] }],
        aoi: AOI,
        steps: [{ op: 'band_math', op_version: 2, params: { expression: '(nir - red) / (nir + red)', name: 'band_math' } }],
        output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['band_math'] },
      },
    });
  });

  it('reads version 1 without steps as the bands of its assets', () => {
    const result = read(recipe1({ steps: [] }));
    expect(result.ok && result.order.output).toMatchObject({ bands: ['red', 'nir'] });
    expect(result.ok && result.converted).toBe(true);
  });

  it('reads version 1 onto the bands of the layout it is given', () => {
    const namesOf = (key: string) => (key === 'red' ? ['red_1', 'red_2'] : [key]);
    const result = readRecipe(JSON.stringify(recipe1({ steps: [] })), namesOf);
    expect(result.ok && result.order.output).toMatchObject({ bands: ['red_1', 'red_2', 'nir'] });
  });

  it('writes the crop of version 1 as version 2 and keeps its assets', () => {
    const result = read(recipe1({ steps: [], output: CROP }));
    expect(result).toMatchObject({ ok: true, converted: true, order: { recipe_version: 2, output: CROP } });
    expect(result.ok && result.order.inputs[0].assets).toEqual(['red', 'nir']);
  });

  it('refuses version 1 without a list of assets', () => {
    const { assets: _assets, ...input } = recipe1().inputs[0];
    expect(reason(recipe1({ inputs: [input] }))).toMatch(/no list of assets/u);
    expect(reason(recipe1({ inputs: [{ ...input, assets: [1] }] }))).toMatch(/no list of assets/u);
  });

  it('refuses version 1 that cannot be rewritten, without naming anything of the file', () => {
    const bad = recipe1({ steps: [{ op: 'band_math', op_version: 1, params: [] }] });
    expect(reason(bad)).toMatch(/no parameters object/u);
    const result = read(recipe1({ steps: [{ op: 'normalize', op_version: 7, params: {} }] }));
    expect(result).toEqual({ ok: false, reason: 'The recipe is incomplete: it cannot be read as version 2.' });
  });

  it('refuses version 2 without output bands, or with bands that are no names', () => {
    const output = { kind: 'raster', format: 'cog', dtype: 'float32' };
    expect(reason(recipe({ output }))).toBe('The recipe names no output bands.');
    expect(reason(recipe({ output: { ...output, bands: 'NDVI' } }))).toBe('The recipe names no output bands.');
    expect(reason(recipe({ output: { ...output, bands: ['NDVI', 3] } }))).toBe('The recipe names no output bands.');
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

  it('refuses a recipe version it does not know', () => {
    expect(reason(recipe({ recipe_version: 3 }))).toBe('Recipe version 3 is not supported.');
    expect(reason(recipe({ recipe_version: 0 }))).toBe('Recipe version 0 is not supported.');
    expect(reason(recipe({ recipe_version: '2' }))).toBe('Recipe version 2 is not supported.');
  });

  it('refuses a recipe without inputs or without a steps list', () => {
    expect(reason(recipe({ inputs: [] }))).toMatch(/no inputs/u);
    const { steps: _steps, ...rest } = recipe();
    expect(reason(rest)).toMatch(/no steps list/u);
  });

  it('refuses incomplete inputs and steps', () => {
    expect(reason(recipe({ inputs: [{ dataset: 'x', groups: [] }] }))).toMatch(/no scenes/u);
    expect(reason(recipe({ inputs: [{ dataset: 'x', groups: [[1]] }] }))).toMatch(/no scenes/u);
    expect(reason(recipe({ steps: [{ op: 'band_math' }] }))).toMatch(/step 1 names no operator/u);
    expect(reason(recipe({ steps: [{ op: 'band_math', op_version: 2, params: [] }] }))).toMatch(/no parameters object/u);
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
