// What "Quick processing" offers (M5-14): the indices, composites and steps of the registry, read entry by entry, and the steps, assets,
// bands and look each one stands for. Pure functions.

import { describe, expect, it, vi } from 'vitest';

import { buildOperatorTileTemplate } from './api';
import { SENTINEL_2_PRESETS } from './fixtures/indexPresets';
import { lookOfPreset, paramsOfPreset, presetOfLook, quickPresetsOf, shownBandsOf, tileStepsOf, withParams } from './quickPresets';
import { lookChanged, lookOfPendingFields, pendingFieldsOf } from './render';
import type { Collection } from './types';
import { indexChainOf, indexStatisticsUrl } from './viewIndex';

const FALSE_COLOUR = {
  name: 'false_colour_ir',
  title: 'False colour (IR)',
  expressions: ['nir', 'red', 'green'],
  rescale: [[0, 0.5], [0, 0.3], [0, 0.3]],
  reference: 'https://example.org/false-colour',
};
const HILLSHADE = {
  name: 'hillshade',
  title: 'Hillshade',
  op: 'terrain',
  op_version: 1,
  params: { product: 'hillshade', bands: ['data'], method: 'horn', azimuth: 315, altitude: 45, z_factor: 1, multidirectional: false, name: 'hillshade' },
  adjustable: ['azimuth', 'altitude'],
};
const ASPECT = { ...HILLSHADE, name: 'aspect', title: 'Aspect', params: { product: 'aspect', bands: ['data'], method: 'horn', name: 'aspect' }, adjustable: [] };

const collection = (fields: Record<string, unknown>) => ({ id: 'x', ...fields }) as unknown as Collection;
const S2 = collection({ 'earthx:index_presets': SENTINEL_2_PRESETS, 'earthx:composite_presets': [FALSE_COLOUR], 'earthx:step_presets': [] });
const DEM = collection({ 'earthx:index_presets': [], 'earthx:composite_presets': [], 'earthx:step_presets': [HILLSHADE, ASPECT] });

describe('the presets of a dataset', () => {
  it('are its indices, then its composites, then its steps, as the registry orders them', () => {
    const presets = quickPresetsOf(S2);
    expect(presets.map((p) => [p.kind, p.label])).toEqual([
      ...SENTINEL_2_PRESETS.map((p) => ['index', p.name]),
      ['composite', 'False colour (IR)'],
    ]);
    expect(quickPresetsOf(DEM).map((p) => [p.kind, p.name, p.label])).toEqual([
      ['step', 'hillshade', 'Hillshade'],
      ['step', 'aspect', 'Aspect'],
    ]);
  });

  it('are none for a dataset that offers none, or a backend before M5-14', () => {
    expect(quickPresetsOf(collection({}))).toEqual([]);
    expect(quickPresetsOf(undefined)).toEqual([]);
  });

  it.each([
    ['a composite of two channels', { ...FALSE_COLOUR, expressions: ['nir', 'red'] }],
    ['a composite with a range the wrong way round', { ...FALSE_COLOUR, rescale: [[0.5, 0], [0, 0.3], [0, 0.3]] }],
    ['a composite with a channel that is no expression', { ...FALSE_COLOUR, expressions: ['nir', 'red', 'import os'] }],
    ['a composite without a title', { ...FALSE_COLOUR, title: ' ' }],
  ])('leave out %s, saying so on the console', (_what, entry) => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    expect(quickPresetsOf(collection({ 'earthx:composite_presets': [entry] }))).toEqual([]);
    expect(warn).toHaveBeenCalledWith('A preset of the dataset was left out: it is not complete.');
    warn.mockRestore();
  });

  it.each([
    ['a step whose band is not the name of the preset', { ...HILLSHADE, params: { ...HILLSHADE.params, name: 'shade' } }],
    ['a step that reads no band', { ...HILLSHADE, params: { product: 'hillshade', name: 'hillshade' } }],
    ['a step without a version', { ...HILLSHADE, op_version: '1' }],
    ['a step that makes a parameter adjustable it does not set', { ...HILLSHADE, adjustable: ['slope_unit'] }],
    ['a step that makes its bands adjustable', { ...HILLSHADE, adjustable: ['bands'] }],
    ['a step named like an index of the same dataset', { ...HILLSHADE, name: 'ndvi', params: { ...HILLSHADE.params, name: 'ndvi' } }],
  ])('leave out %s', (_what, entry) => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const presets = quickPresetsOf(collection({ 'earthx:index_presets': SENTINEL_2_PRESETS, 'earthx:step_presets': [entry] }));
    expect(presets.some((p) => p.kind === 'step')).toBe(false);
    warn.mockRestore();
  });
});

describe('a composite', () => {
  const [composite] = quickPresetsOf(S2).filter((p) => p.kind === 'composite');

  it('is three band_math steps that add a band each, shown as red, green and blue', () => {
    expect(composite.steps).toEqual([
      { op: 'band_math', opVersion: 2, params: { expression: 'nir', name: 'false_colour_ir_r' } },
      { op: 'band_math', opVersion: 2, params: { expression: 'red', name: 'false_colour_ir_g' } },
      { op: 'band_math', opVersion: 2, params: { expression: 'green', name: 'false_colour_ir_b' } },
    ]);
    expect(composite.assets).toEqual(['nir', 'red', 'green']);
    expect(shownBandsOf(composite)).toEqual(['false_colour_ir_r', 'false_colour_ir_g', 'false_colour_ir_b']);
  });

  it('asks the tile route for its three bands', () => {
    const url = new URL(buildOperatorTileTemplate('x', 'S2_1', composite.assets, tileStepsOf(composite), shownBandsOf(composite)), 'http://localhost');
    expect(url.searchParams.getAll('op')).toEqual(['band_math', 'band_math', 'band_math']);
    expect(url.searchParams.getAll('band')).toEqual(['false_colour_ir_r', 'false_colour_ir_g', 'false_colour_ir_b']);
    expect(url.searchParams.getAll('asset')).toEqual(['nir', 'red', 'green']);
  });

  it('is drawn with a fixed range for each channel and no colormap', () => {
    expect(lookOfPreset(composite)).toEqual({ index: 'false_colour_ir', rescale: '0,0.5;0,0.3;0,0.3' });
  });

  it('is computed below the first level with the same steps (never an empty map)', () => {
    expect(indexChainOf(composite)).toEqual({ steps: tileStepsOf(composite), band: shownBandsOf(composite) });
  });
});

describe('a step', () => {
  const [hillshade, aspect] = quickPresetsOf(DEM);

  it('is the step of its operator with the parameters of the registry, reading the band it names', () => {
    expect(hillshade.steps).toEqual([{ op: 'terrain', opVersion: 1, params: HILLSHADE.params }]);
    expect(hillshade.assets).toEqual(['data']);
    expect(hillshade.bands).toEqual(['hillshade']);
    expect(hillshade.index).toBeNull();
  });

  it('is measured as it is drawn: the statistics route with the same step', () => {
    const url = new URL(indexStatisticsUrl('cop-dem-glo-30', 'T1', hillshade), 'http://localhost');
    expect(url.searchParams.getAll('op')).toEqual(['terrain']);
    expect(JSON.parse(url.searchParams.get('params')!)).toEqual(HILLSHADE.params);
    expect(url.searchParams.get('band')).toBe('hillshade');
  });

  it('is drawn with the look of its operator: a fixed range at once, a measured one from the measure (adr/0035)', () => {
    expect(lookOfPreset(aspect, { colormap: 'hsv', scale: 'fixed', low: 0, high: 360 })).toEqual({ index: 'aspect', colormapName: 'hsv', rescale: '0,360' });
    const shade = { colormap: 'greys_r', scale: 'percentiles' as const, low: 0, high: 100 };
    expect(lookOfPreset(hillshade, shade)).toBeNull();
    const stats = { expression: false, bands: [{ minimum: 3, maximum: 251, percentile2: 40, percentile98: 220 }] };
    expect(lookOfPreset(hillshade, shade, stats)).toEqual({ index: 'hillshade', colormapName: 'greys_r', rescale: '3,251' });
  });

  it('has no look before the description of the dataset tells it', () => {
    expect(lookOfPreset(hillshade)).toBeNull();
  });

  it('is what a look names, and nothing is what the dataset lacks', () => {
    expect(presetOfLook({ index: 'aspect' }, DEM)).toBe(aspect);
    expect(presetOfLook({ index: 'slope' }, DEM)).toBeNull();
    expect(presetOfLook({}, DEM)).toBeNull();
  });

  it('names the parameters a person may change, with the values of the registry', () => {
    expect(hillshade.adjustable).toEqual(['azimuth', 'altitude']);
    expect(paramsOfPreset(hillshade)).toEqual({ azimuth: 315, altitude: 45 });
    expect(aspect.adjustable).toEqual([]);
  });
});

describe('the values a person chose for the parameters of a step (Otto, 17.11.2026)', () => {
  const [hillshade] = quickPresetsOf(DEM);

  it('go into the step of the tile, and the rest stays as the registry has it', () => {
    const turned = withParams(hillshade, { azimuth: 90, altitude: 30 });
    const url = new URL(buildOperatorTileTemplate('x', 'T1', turned.assets, tileStepsOf(turned), shownBandsOf(turned)), 'http://localhost');
    expect(JSON.parse(url.searchParams.get('params')!)).toEqual({ ...HILLSHADE.params, azimuth: 90, altitude: 30 });
    expect(paramsOfPreset(turned)).toEqual({ azimuth: 90, altitude: 30 });
  });

  it('come with the look: the same preset for the same values, that of the registry for none', () => {
    expect(presetOfLook({ index: 'hillshade', presetParams: { azimuth: 90 } }, DEM)).toBe(presetOfLook({ index: 'hillshade', presetParams: { azimuth: 90 } }, DEM));
    expect(presetOfLook({ index: 'hillshade' }, DEM)).toBe(hillshade);
    expect(presetOfLook({ index: 'hillshade', presetParams: { azimuth: 315 } }, DEM)).toBe(hillshade);
  });

  it('leave out a parameter that is not adjustable or a value of another type', () => {
    expect(withParams(hillshade, { z_factor: 5, method: 'zevenbergen_thorne' })).toBe(hillshade);
    expect(withParams(hillshade, { azimuth: '90' })).toBe(hillshade);
    expect(withParams(hillshade, { bands: 'red' } as never)).toBe(hillshade);
  });
});

describe('a change of a parameter is a change of the look', () => {
  const fields = (presetParams: Record<string, string | number | boolean>) => ({ pendingColormapName: 'greys_r', pendingVmin: '3', pendingVmax: '251', pendingIndex: 'hillshade', pendingPresetParams: presetParams });

  it('is what "Apply" would draw, and the look carries it', () => {
    const applied = { index: 'hillshade', colormapName: 'greys_r', rescale: '3,251' };
    expect(lookChanged(applied, fields({}))).toBe(false);
    expect(lookChanged(applied, fields({ azimuth: 90 }))).toBe(true);
    expect(lookOfPendingFields(fields({ azimuth: 90 }))).toMatchObject({ index: 'hillshade', presetParams: { azimuth: 90 } });
    expect(pendingFieldsOf({ ...applied, presetParams: { azimuth: 90 } }).pendingPresetParams).toEqual({ azimuth: 90 });
  });

  it('is nothing without a preset', () => {
    expect(lookOfPendingFields({ ...fields({ azimuth: 90 }), pendingIndex: '' }).presetParams).toBeUndefined();
  });
});
