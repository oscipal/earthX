// The terrain products are drawn as the registry of the operator says (M5-10, Otto, 16.11.2026): in the preview of the panel, in a result
// layer and in a pinned one. Slope: RdYlGn reversed; hillshade: Greys reversed from the minimum to the maximum; aspect: hsv on 0 to 360.

import { describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import { lookOfStep } from './displayLook';
import dem from './fixtures/processes/cop-dem-glo-30.json';
import type { ProcessDescription } from './processing';
import { processInfo, type DraftStep } from './processingOrder';
import { DEFAULT_RANGE, measuredRange, planPreview, previewSpec, type PreviewMeasure } from './processingPreview';
import { presetOfResultBand, resultBands, resultRender } from './resultLayer';
import { drawnRange } from './processingStore';
import { initialValues } from './schemaForm';
import type { ResultStats } from './render';
import type { Collection, StacItem } from './types';

const INFO = processInfo(dem as unknown as ProcessDescription);
const TERRAIN = INFO.operators.find((o) => o.op === 'terrain')!;
if (!TERRAIN.form.supported) throw new Error(TERRAIN.form.reason);
const FIELDS = TERRAIN.form.fields;

const CAPABILITIES = { roi: true, time_range: false, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, single_coverage_product: false };
const COLLECTION = {
  id: 'relief',
  title: 'Relief',
  extent: { spatial: { bbox: [[5, 45, 11, 48]] } },
  'earthx:capabilities': CAPABILITIES,
  'earthx:viewer': { group_by: ['start_datetime'], min_zoom: 7, max_zoom: 15, browse: 'full_resolution', quicklook_nodata_max: null, results_group_by: ['start_datetime'], overview: 'own' },
  'earthx:default_render': { title: 'Elevation', assets: ['data'], rescale: [[0, 3000]], colormap_name: 'terrain', expression: null, resampling: 'nearest' },
} as unknown as Collection;
const [DATASET] = datasetsFrom([COLLECTION]);
const ITEM: StacItem = { id: 'r1', collection: 'relief', bbox: [7, 46, 8, 47], properties: { datetime: '2026-01-01T00:00:00Z', gsd: 30 }, assets: {} } as StacItem;

const step = (product: string, name = product): DraftStep => ({ key: 1, op: 'terrain', opVersion: 1, values: { ...initialValues(FIELDS), bands: 'data', name, product } });
const specOf = (product: string, name = product) => {
  const plan = planPreview([step(product, name)], INFO);
  if (plan.state !== 'ready') throw new Error(`no plan for ${product}`);
  return previewSpec({ dataset: DATASET, items: [ITEM], assets: ['data'], info: INFO, plan, range: DEFAULT_RANGE, area: 'scene' })!;
};
const STATS: ResultStats = { expression: false, bands: [{ minimum: 0, maximum: 88, percentile2: 1, percentile98: 40 }] };
const measure = (spec: { measure: string }): PreviewMeasure => ({ key: spec.measure, stats: STATS, unit: null, source: 'scene', exact: true });

describe('the preview of a terrain product', () => {
  it('has a colormap from the start for a slope, and its range from the measure', () => {
    const spec = specOf('slope');
    expect(spec.look).toEqual({ colormap: 'rdylgn_r', scale: 'measured' });
    expect(spec.preset).toBeNull();
    expect(measuredRange(measure(spec), spec.look)).toEqual({ vmin: '1', vmax: '40', colormap: 'rdylgn_r' });
  });

  it('is a hillshade from the minimum to the maximum in light-where-lit greys', () => {
    const spec = specOf('hillshade');
    expect(spec.look).toMatchObject({ colormap: 'greys_r', scale: 'percentiles', low: 0, high: 100 });
    expect(spec.preset).toBeNull();
    expect(measuredRange(measure(spec), spec.look)).toEqual({ vmin: '0', vmax: '88', colormap: 'greys_r' });
  });

  it('is an aspect on 0 to 360 in hsv with no measure at all: the preset is the range', () => {
    const spec = specOf('aspect');
    expect(spec.look).toMatchObject({ colormap: 'hsv', scale: 'fixed', low: 0, high: 360 });
    expect(spec.preset).toEqual({ vmin: '0', vmax: '360', colormap: 'hsv' });
  });

  it('draws the aspect with that range and colormap in the tile URL, as the store asks for it (the preset is the range)', () => {
    const plan = planPreview([step('aspect')], INFO);
    if (plan.state !== 'ready') throw new Error('no plan');
    const spec = previewSpec({ dataset: DATASET, items: [ITEM], assets: ['data'], info: INFO, plan, range: specOf('aspect').preset!, area: 'scene' })!;
    const url = new URL(spec.scenes[0].url, 'http://localhost');
    expect(url.searchParams.get('rescale')).toBe('0,360');
    expect(url.searchParams.get('colormap_name')).toBe('hsv');
  });

  it('has no look for a step of an operator that has none', () => {
    const plan = planPreview([{ key: 1, op: 'band_math', opVersion: 2, values: { expression: 'data * 2', name: 'double' } }], INFO);
    if (plan.state !== 'ready') throw new Error('no plan');
    const spec = previewSpec({ dataset: DATASET, items: [ITEM], assets: ['data'], info: INFO, plan, range: DEFAULT_RANGE, area: 'scene' })!;
    expect(spec.look).toBeNull();
  });

  it('has the look only for the band the step made, not for a band of the data the preview shows', () => {
    const plan = planPreview([step('slope', 'steep')], INFO);
    if (plan.state !== 'ready') throw new Error('no plan');
    const spec = (shown: string) => previewSpec({ dataset: DATASET, items: [ITEM], assets: ['data'], info: INFO, plan, range: DEFAULT_RANGE, area: 'scene', band: shown })!;
    expect(spec('steep').look?.colormap).toBe('rdylgn_r');
    expect(spec('data').look).toBeNull();
  });
});

const ORDER = (product: string, name = product) => ({ steps: [{ op: 'terrain', params: { product, name, bands: ['data'] } }] });
const looksOf = (step: { op: string; params: Record<string, unknown> }) => lookOfStep(TERRAIN.looks, step.params);
const properties = (name: string) => ({ bands: [{ name, data_type: 'float32', statistics: { minimum: 0, maximum: 88, mean: 20, count: 10, valid_percent: 100, percentile_2: 1, percentile_98: 40 } }] });

describe('the result layer of a terrain product', () => {
  it.each([
    ['slope', { vmin: '1', vmax: '40', colormap: 'rdylgn_r' }],
    ['hillshade', { vmin: '0', vmax: '88', colormap: 'greys_r' }],
    ['aspect', { vmin: '0', vmax: '360', colormap: 'hsv' }],
  ])('is drawn as a %s should be', (product, range) => {
    const [band] = resultBands(properties(product), ORDER(product), looksOf);
    expect(band.look).not.toBeNull();
    expect(presetOfResultBand(band, [])).toEqual(range);
    const render = resultRender('float32', DEFAULT_RANGE, band.stats, null, false, presetOfResultBand(band, []));
    expect(render).toEqual({ rescale: `${range.vmin},${range.vmax}`, colormapName: range.colormap });
  });

  it('has no look where the description of the dataset was not there to tell it', () => {
    const [band] = resultBands(properties('slope'), ORDER('slope'));
    expect(band.look).toBeNull();
    expect(presetOfResultBand(band, [])).toBeNull();
  });

  it('keeps the look to the band of the step, not to a band of the data next to it', () => {
    const listed = { bands: [...properties('slope').bands, ...properties('data').bands] };
    const [slope, data] = resultBands(listed, ORDER('slope'), looksOf);
    expect(slope.look?.colormap).toBe('rdylgn_r');
    expect(data.look).toBeNull();
  });

  it('draws an aspect on 0 to 360 even where the job measured nothing', () => {
    const [band] = resultBands({ bands: [{ name: 'aspect' }] }, ORDER('aspect'), looksOf);
    expect(presetOfResultBand(band, [])).toEqual({ vmin: '0', vmax: '360', colormap: 'hsv' });
  });

  it('draws a slope without statistics as before (the range of the panel)', () => {
    const [band] = resultBands({ bands: [{ name: 'slope' }] }, ORDER('slope'), looksOf);
    expect(presetOfResultBand(band, [])).toBeNull();
  });

  it('leaves a band of an index to the preset of the dataset, which goes first', () => {
    const band = { name: 'x', stats: STATS, expression: 'data * 2', look: { colormap: 'hsv', scale: 'fixed' as const, low: 0, high: 360 } };
    const preset = { name: 'double', title: 'Double', expression: 'data * 2', rescale: [0, 6000] as [number, number], colormapName: 'viridis', formula: 'data × 2', reference: 'https://x' };
    expect(presetOfResultBand(band, [preset])).toEqual({ vmin: '0', vmax: '6000', colormap: 'viridis' });
  });
});

describe('the range a preview of a terrain product is drawn with, before and after the measure and with Auto-scale', () => {
  const state = (over: object = {}) => ({ range: DEFAULT_RANGE, rangeByHand: false, measure: null as PreviewMeasure | null, colormapHeld: null as string | null, ...over });

  it('has the colormap of the registry before the measure is there, and the start range', () => {
    expect(drawnRange(state(), specOf('slope'))).toEqual({ vmin: '-1', vmax: '1', colormap: 'rdylgn_r' });
  });

  it('has the look over the measure once it is there', () => {
    const slope = specOf('slope');
    expect(drawnRange(state({ measure: measure(slope) }), slope)).toEqual({ vmin: '1', vmax: '40', colormap: 'rdylgn_r' });
    const shade = specOf('hillshade');
    expect(drawnRange(state({ measure: measure(shade) }), shade)).toEqual({ vmin: '0', vmax: '88', colormap: 'greys_r' });
  });

  it('does not take the measure of another preview', () => {
    const slope = specOf('slope');
    expect(drawnRange(state({ measure: { ...measure(slope), key: 'other' } }), slope)).toEqual({ vmin: '-1', vmax: '1', colormap: 'rdylgn_r' });
  });

  it('has an aspect on 0 to 360 in hsv at once, measure or not', () => {
    const aspect = specOf('aspect');
    expect(drawnRange(state(), aspect)).toEqual({ vmin: '0', vmax: '360', colormap: 'hsv' });
    expect(drawnRange(state({ measure: measure(aspect) }), aspect)).toEqual({ vmin: '0', vmax: '360', colormap: 'hsv' });
  });

  it('keeps what the user applied by hand against the look', () => {
    const hand = { vmin: '5', vmax: '9', colormap: 'magma' };
    expect(drawnRange(state({ range: hand, rangeByHand: true }), specOf('aspect'))).toEqual(hand);
  });

  it('keeps the colormap the user chose when "Auto-scale" resets the range (Otto, 16.11.2026), whatever the look says', () => {
    expect(drawnRange(state({ colormapHeld: 'magma' }), specOf('slope'))).toEqual({ vmin: '-1', vmax: '1', colormap: 'magma' });
    const shade = specOf('hillshade');
    expect(drawnRange(state({ colormapHeld: 'magma', measure: measure(shade) }), shade)).toEqual({ vmin: '0', vmax: '88', colormap: 'magma' });
    expect(drawnRange(state({ colormapHeld: 'magma' }), specOf('aspect'))).toEqual({ vmin: '0', vmax: '360', colormap: 'magma' });
  });
});
