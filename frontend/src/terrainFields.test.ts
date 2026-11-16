// The "Terrain" step in the panel (M5-10): its form from the process description of the elevation models, the fields of
// each product, the band it adds, and its preview as the first step only.

import { describe, expect, it } from 'vitest';

import dem from './fixtures/processes/cop-dem-glo-30.json';
import s2 from './fixtures/processes/sentinel-2-c1-l2a.json';
import { canonicalJson, type ProcessDescription } from './processing';
import { addsBand, dropFromNormalize, renameResult, resultsOf, stepName } from './processingBands';
import { processInfo, type DraftStep } from './processingOrder';
import { namesNeeded, planPreview } from './processingPreview';
import { initialValues, paramsFrom } from './schemaForm';
import { fieldsOfProduct, terrainForm } from './terrainFields';

const DEM = processInfo(dem as unknown as ProcessDescription);
const S2 = processInfo(s2 as unknown as ProcessDescription);
const TERRAIN = DEM.operators.find((o) => o.op === 'terrain')!;

const form = () => {
  if (!TERRAIN.form.supported) throw new Error(TERRAIN.form.reason);
  return TERRAIN.form.fields;
};

const terrainStep = (key: number, values: Record<string, string | boolean>): DraftStep => ({
  key,
  op: 'terrain',
  opVersion: 1,
  values: { ...initialValues(form()), bands: 'data', name: 'slope', ...values },
});

describe('the form of a terrain step', () => {
  it('is offered on an elevation model and not on Sentinel-2', () => {
    expect(TERRAIN).toBeDefined();
    expect(TERRAIN.kind).toBe('focal');
    expect(TERRAIN.form.supported).toBe(true);
    expect(S2.operators.some((o) => o.op === 'terrain')).toBe(false);
  });

  it('starts with a slope in degrees after Horn and the light of gdaldem', () => {
    const values = initialValues(form());
    expect(values).toMatchObject({ product: 'slope', method: 'horn', slope_unit: 'degrees', azimuth: '315', altitude: '45', z_factor: '1' });
    expect(values.multidirectional).toBe(false);
  });

  it('shows the fields of the chosen product and no others', () => {
    const names = (values: Record<string, string | boolean>) => fieldsOfProduct(form(), values).map((f) => f.name);
    expect(names({ product: 'slope' })).toEqual(['product', 'bands', 'name', 'method', 'slope_unit']);
    expect(names({ product: 'aspect' })).toEqual(['product', 'bands', 'name', 'method']);
    expect(names({ product: 'hillshade', multidirectional: false })).toEqual([
      'product',
      'bands',
      'name',
      'method',
      'multidirectional',
      'azimuth',
      'altitude',
      'z_factor',
    ]);
    expect(names({ product: 'hillshade', multidirectional: true })).not.toContain('azimuth');
  });

  it('sends the fields of its product only, as the server takes them', () => {
    const slope = paramsFrom(form(), terrainStep(1, {}).values, 'terrain');
    expect(slope).toEqual({
      params: { product: 'slope', bands: ['data'], name: 'slope', method: 'horn', slope_unit: 'degrees' },
      errors: {},
    });
    const shade = paramsFrom(form(), terrainStep(1, { product: 'hillshade', multidirectional: true }).values, 'terrain');
    expect(shade.params).toEqual({
      product: 'hillshade',
      bands: ['data'],
      name: 'slope',
      method: 'horn',
      multidirectional: true,
      altitude: 45,
      z_factor: 1,
    });
  });

  it('says what is wrong with a light outside its range or a band missing', () => {
    const { errors } = paramsFrom(form(), terrainStep(1, { product: 'hillshade', azimuth: '360', altitude: '91', bands: '' }).values, 'terrain');
    expect(Object.keys(errors).sort()).toEqual(['altitude', 'azimuth', 'bands']);
  });

  it('is refused by a panel that does not know its products', () => {
    expect(terrainForm({ properties: { product: { enum: ['slope'] } } })).toEqual({
      supported: false,
      reason: 'not supported by this panel: the products of terrain',
    });
    expect(terrainForm(null).supported).toBe(false);
  });
});

describe('the band a terrain step adds', () => {
  const steps = [terrainStep(1, { name: 'shade', product: 'hillshade' }), { key: 2, op: 'normalize', opVersion: 4, values: { bands: 'shade' } }];

  it('is a result of the chain, named in the title', () => {
    expect(addsBand(steps[0])).toBe(true);
    expect(resultsOf(steps)).toEqual([{ key: 1, name: 'shade' }]);
    expect(stepName(TERRAIN, steps[0].values, 0)).toBe('shade');
  });

  it('is renamed where a later step reads it, and dropped there when the step goes', () => {
    const renamed = renameResult(steps, 1, 'shade', 'relief');
    expect(renamed[1].values.bands).toBe('relief');
    const followed = [steps[0], terrainStep(3, { bands: 'shade', name: 'slope_of_shade' })];
    expect(renameResult(followed, 1, 'shade', 'relief')[1].values.bands).toBe('relief');
    expect(dropFromNormalize(followed, 'shade')[1].values.bands).toBe('');
  });

  it('needs the band of heights it reads for its preview', () => {
    expect([...namesNeeded([terrainStep(1, { name: 'shade' })], 'shade')]).toEqual(['data']);
  });
});

describe('the preview of a terrain step', () => {
  const doubled: DraftStep = { key: 9, op: 'band_math', opVersion: 2, values: { expression: 'data * 1', name: 'copy' } };

  it('is drawn as the first step', () => {
    const plan = planPreview([terrainStep(1, {})], DEM);
    expect(plan.state).toBe('ready');
    if (plan.state === 'ready') expect(plan.steps.map((s) => s.step.op)).toEqual(['terrain']);
  });

  it('ends the start of the chain the map draws when it is not the first', () => {
    const plan = planPreview([doubled, terrainStep(1, { bands: 'copy' })], DEM);
    expect(plan.state).toBe('ready');
    if (plan.state === 'ready') {
      expect(plan.steps.map((s) => s.step.op)).toEqual(['band_math']);
      expect(plan.further).toBe(true);
    }
  });

  it('carries its parameters into the tile as the server reads them', () => {
    const plan = planPreview([terrainStep(1, { product: 'aspect' })], DEM);
    if (plan.state !== 'ready') throw new Error('no plan');
    expect(canonicalJson(plan.steps[0].params)).toBe(canonicalJson({ bands: ['data'], method: 'horn', name: 'slope', product: 'aspect' }));
  });
});
