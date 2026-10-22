// `draftFromOrder` against `buildOrder` (M4-19d): the orders the panel writes
// (`fixtures/orders`, the same files the backend holds against its schema) come
// out of the draft they were read into, unchanged.

import { describe, expect, it } from 'vitest';

import cop from './fixtures/processes/cop-dem-glo-30.json';
import s2 from './fixtures/processes/sentinel-2-c1-l2a.json';
import zarr from './fixtures/processes/sentinel-2-l2a-zarr3.json';
import type { Order, ProcessDescription } from './processing';
import { buildOrder, draftFromOrder, processInfo } from './processingOrder';
import { readRecipe } from './recipeFile';

const FIXTURES = import.meta.glob('./fixtures/orders/*.json', { eager: true, import: 'default' }) as Record<
  string,
  { inputs: { recipe: Order } }
>;
const INFOS: Record<string, unknown> = {
  'sentinel-2-c1-l2a': s2,
  'sentinel-2-l2a-zarr3': zarr,
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
});
