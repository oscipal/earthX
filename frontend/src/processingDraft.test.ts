// `draftFromOrder` against `buildOrder` (M4-19d): the orders the panel writes
// (`fixtures/orders`, the same files the backend holds against its schema) come
// out of the draft they were read into, unchanged.

import { describe, expect, it } from 'vitest';

import cop from './fixtures/processes/cop-dem-glo-30.json';
import s2 from './fixtures/processes/sentinel-2-c1-l2a.json';
import zarr from './fixtures/processes/synthetic-zarr.json';
import type { Order, ProcessDescription } from './processing';
import { buildOrder, draftFromOrder, processInfo } from './processingOrder';
import { readRecipe } from './recipeFile';

const FIXTURES = import.meta.glob('./fixtures/orders/*.json', { eager: true, import: 'default' }) as Record<
  string,
  { inputs: { recipe: Order } }
>;
const INFOS: Record<string, unknown> = {
  'sentinel-2-c1-l2a': s2,
  'synthetic-zarr': zarr,
  'cop-dem-glo-30': cop,
};
const infoOf = (datasetId: string) => processInfo(INFOS[datasetId] as ProcessDescription);
const keys = () => {
  let key = 0;
  return () => ++key;
};

function roundTrip(order: Order) {
  const info = infoOf(order.inputs[0].dataset);
  const { draft, problems } = draftFromOrder(order, info, keys());
  const built = buildOrder({
    datasetId: draft.datasetId,
    itemIds: draft.groups[0],
    area: draft.aoi ? 'aoi' : 'scene',
    aoi: draft.aoi,
    steps: draft.steps,
    assets: draft.assets,
    dtype: draft.dtype ?? '',
    info,
  });
  return { problems, built };
}

describe('draftFromOrder', () => {
  const withSteps = Object.entries(FIXTURES).filter(([, f]) => f.inputs.recipe.steps.length > 0);

  it('has the fixtures to go through', () => {
    expect(withSteps.length).toBeGreaterThanOrEqual(7);
  });

  it.each(withSteps)('builds %s again from its draft', (_name, fixture) => {
    const { problems, built } = roundTrip(fixture.inputs.recipe);
    expect(problems).toEqual([]);
    expect(built.order).toEqual(fixture.inputs.recipe);
  });

  it('survives the file the user would save', () => {
    const order = Object.values(FIXTURES)[0].inputs.recipe;
    const read = readRecipe(JSON.stringify({ ...order, provenance: { execution: 'cloud' } }));
    expect(read.ok && roundTrip(read.order).built.order).toEqual(order);
  });

  // M4-19b: the unit sits in `resolved`, which the file carries and the order does not. A file from before units
  // loads as it did, and one with units gives the very same order: nothing of `resolved` goes back to the server.
  const served = (order: Order, resolved: unknown) => ({
    ...order,
    recipe_id: 'AbCdEfGhIjKlMnOpQrSt_-',
    inputs: order.inputs.map((input) => ({ ...input, resolved })),
    provenance: { execution: 'cloud' },
  });
  const OLD_BANDS = [{ asset: { asset: 'red' }, bands: [{ data_type: 'uint16', nodata: 0, scale: 0.0001, offset: -0.1 }], scaling: 'item' }];
  const NEW_BANDS = [
    { asset: { asset: 'red' }, bands: [{ data_type: 'uint16', nodata: 0, scale: 0.0001, offset: -0.1, unit: '1' }], scaling: 'item', unit: null },
    { asset: { asset: 'data' }, bands: [], scaling: 'none', unit: 'm' },
  ];

  it.each([
    ['from before units', OLD_BANDS],
    ['with units', NEW_BANDS],
  ])('loads a recipe.json %s into the order it was made from', (_label, resolved) => {
    for (const [, fixture] of withSteps) {
      const order = fixture.inputs.recipe;
      const read = readRecipe(JSON.stringify(served(order, resolved)));
      expect(read.ok).toBe(true);
      const { problems, built } = roundTrip((read as { order: Order }).order);
      expect(problems).toEqual([]);
      expect(built.order).toEqual(order);
      expect(JSON.stringify(built.order)).not.toMatch(/"unit"|"resolved"/u);
    }
  });

  it('takes a recipe without steps as a draft without steps (a crop or a mosaic)', () => {
    const order = Object.values(FIXTURES).find((f) => f.inputs.recipe.steps.length === 0)!.inputs.recipe;
    const { draft, problems } = draftFromOrder(order, infoOf(order.inputs[0].dataset), keys());
    expect(problems).toEqual([]);
    expect(draft.steps).toEqual([]);
    expect(draft.groups).toEqual(order.inputs[0].groups);
  });

  it('has no data type for a crop', () => {
    const order = {
      ...Object.values(FIXTURES)[0].inputs.recipe,
      steps: [],
      output: { kind: 'crop', format: 'cog', resolution_factor: 1, extent: 'bbox(aoi ∩ footprints)', mask: 'file' },
    } as Order;
    expect(draftFromOrder(order, infoOf(order.inputs[0].dataset), keys()).draft.dtype).toBeNull();
  });

  it('names an operator the dataset does not list', () => {
    const order = structuredClone(Object.values(FIXTURES)[0].inputs.recipe);
    order.steps[0] = { op: 'warp_drive', op_version: 1, params: {} };
    const { problems, draft } = draftFromOrder(order, infoOf(order.inputs[0].dataset), keys());
    expect(problems).toEqual(['Step 1 (warp_drive): this operator is not available for this dataset.']);
    expect(draft.steps).toEqual([]);
  });

  it('names parameters the form does not know, refuses, or gets in the wrong type', () => {
    const order = structuredClone(Object.values(FIXTURES).find((f) => f.inputs.recipe.steps[0].op === 'band_math')!.inputs.recipe);
    const info = infoOf(order.inputs[0].dataset);
    const check = (params: Record<string, unknown>) => {
      order.steps[0] = { ...order.steps[0], params };
      return draftFromOrder(order, info, keys()).problems;
    };
    expect(check({ expression: 'nir', extra: 1 })).toEqual(['Step 1 (band_math): unknown parameter extra.']);
    expect(check({ expression: '' })).toEqual(['Step 1 (band_math): expression: Required.']);
    expect(check({ expression: { not: 'text' } })).toEqual([
      'Step 1 (band_math): expression has the wrong type.',
      'Step 1 (band_math): expression: Required.',
    ]);
  });

  describe('an older version the server still takes (reproject v2)', () => {
    const reproject = () => structuredClone(FIXTURES['./fixtures/orders/reproject-dem-with-drawn-aoi.json'].inputs.recipe);
    const asV2 = (version: number) => {
      const order = reproject();
      order.steps[0] = { ...order.steps[0], op_version: version, params: { crs: 'EPSG:3035', resolution: 30, resampling: 'cubic' } };
      return order;
    };

    it('is taken as the listed version, with a note', () => {
      const order = asV2(2);
      const { draft, problems, notes } = draftFromOrder(order, infoOf(order.inputs[0].dataset), keys());
      expect(problems).toEqual([]);
      expect(notes).toEqual(['Step 1 (reproject): version 2 is taken as version 3.']);
      expect(draft.steps.map((s) => [s.op, s.opVersion, s.values.resampling])).toEqual([['reproject', 3, 'cubic']]);
      const rebuilt = roundTrip(order).built.order;
      expect(rebuilt?.steps).toEqual([{ op: 'reproject', op_version: 3, params: { crs: 'EPSG:3035', resolution: 30, resampling: 'cubic', align: false } }]);
    });

    it('has no note for the listed version, and refuses a version the server does not list or take', () => {
      expect(draftFromOrder(asV2(3), infoOf('cop-dem-glo-30'), keys()).notes).toEqual([]);
      expect(draftFromOrder(asV2(4), infoOf('cop-dem-glo-30'), keys()).problems).toEqual([
        'Step 1 (reproject): this operator is not available for this dataset.',
      ]);
    });

    it('still checks the parameters against the form', () => {
      const order = asV2(2);
      order.steps[0].params = { crs: 'EPSG:3035', resolution: 'x' };
      expect(draftFromOrder(order, infoOf('cop-dem-glo-30'), keys()).problems.join(' ')).toMatch(/resolution/u);
    });
  });
});
