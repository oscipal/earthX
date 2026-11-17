// The order a composite or a step of "Quick processing" is a job with (M5-14 PR B): the steps of the preset as the panel's form takes them,
// the band or the three bands they add as the output. What "Download crop" and "Process" of a layer of such a preset run.

import { describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import dem from './fixtures/processes/cop-dem-glo-30.json';
import s2 from './fixtures/processes/sentinel-2-c1-l2a.json';
import { indexOrdersOfScenes, presetDetail } from './indexDownload';
import { processInfo as infoOf } from './processingOrder';
import { quickPresetsOf, withParams } from './quickPresets';
import type { Collection } from './types';

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[7.4, 46.4], [7.6, 46.4], [7.6, 46.6], [7.4, 46.6], [7.4, 46.4]]] };
const VIEWER = { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'], overview: 'pyramid', overview_resampling: 'average', overview_substitute: null };
const RENDER = { title: 'Image', assets: ['data'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' };

const FALSE_COLOUR = { name: 'false_colour_ir', title: 'False colour (IR)', expressions: ['nir', 'red', 'green'], rescale: [[0, 0.5], [0, 0.3], [0, 0.3]], reference: 'https://example.org/fc' };
const HILLSHADE = {
  name: 'hillshade',
  title: 'Hillshade',
  op: 'terrain',
  op_version: 1,
  params: { product: 'hillshade', bands: ['data'], method: 'horn', azimuth: 315, altitude: 45, z_factor: 1, multidirectional: false, name: 'hillshade' },
  adjustable: ['azimuth', 'altitude'],
};

const collectionOf = (id: string, units: Record<string, string | null>, presets: Record<string, unknown[]>) =>
  ({
    id,
    title: id,
    'earthx:format': 'cog',
    'earthx:license_flags': { tier: 'processing' },
    'earthx:viewer': VIEWER,
    'earthx:default_render': RENDER,
    'earthx:band_units': units,
    'earthx:index_presets': [],
    'earthx:composite_presets': [],
    'earthx:step_presets': [],
    ...presets,
  }) as unknown as Collection;

const optical = datasetsFrom([collectionOf('sentinel-2-c1-l2a', { red: 'reflectance', green: 'reflectance', blue: 'reflectance', nir: 'reflectance' }, { 'earthx:composite_presets': [FALSE_COLOUR] })])[0];
const heights = datasetsFrom([collectionOf('cop-dem-glo-30', { data: 'm' }, { 'earthx:step_presets': [HILLSHADE] })])[0];

const ordersOf = (dataset: typeof optical, preset = quickPresetsOf(dataset.collection)[0], info = dataset.id === heights.id ? dem : s2) =>
  indexOrdersOfScenes({ datasetId: dataset.id, groups: [['A', 'B'], ['C']], aoi: AOI, preset, dataset, info: infoOf(info as never) });

describe('the order of a composite', () => {
  it('is a Band math step for each channel, the three bands as the output, one order for each group', () => {
    const made = ordersOf(optical);
    if (!('orders' in made)) throw new Error(made.problem);
    expect(made.orders.map((order) => order.inputs[0].groups)).toEqual([[['A', 'B']], [['C']]]);
    const [order] = made.orders;
    expect(order.steps).toEqual([
      { op: 'band_math', op_version: 2, params: { expression: 'nir', name: 'false_colour_ir_r' } },
      { op: 'band_math', op_version: 2, params: { expression: 'red', name: 'false_colour_ir_g' } },
      { op: 'band_math', op_version: 2, params: { expression: 'green', name: 'false_colour_ir_b' } },
    ]);
    expect(order.output).toMatchObject({ kind: 'raster', bands: ['false_colour_ir_r', 'false_colour_ir_g', 'false_colour_ir_b'], dtype: 'float32' });
    expect(order.aoi).toEqual(AOI);
  });

  it('is told in the dialog by its three channels', () => {
    expect(presetDetail(quickPresetsOf(optical.collection)[0])).toBe('nir, red, green');
  });
});

describe('the order of a step', () => {
  it('is the step of the registry, its band as the output', () => {
    const made = ordersOf(heights);
    if (!('orders' in made)) throw new Error(made.problem);
    expect(made.orders[0].steps).toEqual([{ op: 'terrain', op_version: 1, params: HILLSHADE.params }]);
    expect(made.orders[0].output).toMatchObject({ kind: 'raster', bands: ['hillshade'] });
    expect(presetDetail(quickPresetsOf(heights.collection)[0])).toBeNull();
  });

  it('takes the values chosen for its parameters', () => {
    const preset = withParams(quickPresetsOf(heights.collection)[0], { azimuth: 90, altitude: 30 });
    const made = ordersOf(heights, preset);
    if (!('orders' in made)) throw new Error(made.problem);
    expect(made.orders[0].steps[0].params).toMatchObject({ azimuth: 90, altitude: 30, product: 'hillshade' });
  });

  it('cannot be built where the dataset lacks the operator, and says why', () => {
    // The description of Sentinel-2 has no `terrain`: the registry would never offer it there, an old layer could still name it.
    const made = ordersOf(heights, quickPresetsOf(heights.collection)[0], s2);
    expect(made).toEqual({ problem: 'Step 1 (terrain): this operator is not available for this dataset.' });
  });

  it('cannot be built where a parameter is of no use to the operator', () => {
    const [preset] = quickPresetsOf(heights.collection);
    const odd = { ...preset, steps: [{ ...preset.steps[0], params: { ...preset.steps[0].params, shadow: true } }] };
    expect(ordersOf(heights, odd)).toEqual({ problem: 'Step 1 (terrain): unknown parameter shadow.' });
  });

  it('cannot be built without scenes', () => {
    const made = indexOrdersOfScenes({ datasetId: heights.id, groups: [[]], aoi: null, preset: quickPresetsOf(heights.collection)[0], dataset: heights, info: infoOf(dem as never) });
    expect(made).toEqual({ problem: 'The layer has no scenes left.' });
  });
});
