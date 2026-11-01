// The methods of a Normalize step (NM4-11b): the form, the rules between its fields, the numbers taken from the answer
// of the route, and the order and the questions built from them.

import { describe, expect, it } from 'vitest';

import type { AreaStatistics } from './api';
import s2 from './fixtures/processes/sentinel-2-c1-l2a.json';
import { bboxToPolygon } from './geoUtils';
import {
  AFTER_REPROJECT,
  NO_AOI,
  bandNumbers,
  fieldsOfMethod,
  measuredFrom,
  measuredText,
  normalizeForm,
  refineNormalize,
  upgradedValues,
} from './normalizeMethods';
import type { ProcessDescription } from './processing';
import { buildOrder, processInfo, type DraftStep, type MeasureEntry } from './processingOrder';
import { paramsFrom } from './schemaForm';

const INFO = processInfo(s2 as unknown as ProcessDescription);
const OPERATOR = INFO.operators.find((o) => o.op === 'normalize')!;
const FIELDS = OPERATOR.form.supported ? OPERATOR.form.fields : [];

// The statistics of the route for a band (`processing/statistics.py`): every percentile it measures.
const STATISTICS = {
  minimum: -0.3,
  maximum: 0.9,
  mean: 0.4,
  stddev: 0.2,
  count: 1000,
  valid_percent: 100,
  percentile_1: -0.2,
  percentile_2: -0.1,
  percentile_5: 0,
  percentile_25: 0.25,
  percentile_50: 0.4,
  percentile_75: 0.55,
  percentile_95: 0.8,
  percentile_98: 0.85,
  percentile_99: 0.88,
};

const answer = (bands: Record<string, Record<string, unknown>>, factor = 1): AreaStatistics => ({
  bands: Object.entries(bands).map(([name, statistics]) => ({ name, unit: null, statistics })),
  exact: factor === 1,
  factor,
});

describe('the form of normalize version 3', () => {
  it('is read from the schema of the fixtures: the method with its four choices, the bands and the fields of the methods', () => {
    expect(OPERATOR.opVersion).toBe(3);
    expect(FIELDS.map((f) => [f.name, f.kind, f.required])).toEqual([
      ['method', 'enum', true],
      ['bands', 'names', true],
      ['in_min', 'number', false],
      ['in_max', 'number', false],
      ['low', 'integer', false],
      ['high', 'integer', false],
      ['out_min', 'number', false],
      ['out_max', 'number', false],
      ['clip', 'boolean', false],
    ]);
    expect(FIELDS[0].options).toEqual(['linear', 'percentile', 'zscore', 'robust']);
  });

  it('is not supported where the schema lacks a method or a field the panel lays out', () => {
    const properties = (s2 as unknown as { inputs: { recipe: { schema: { $defs: Record<string, { properties: { params: { properties: unknown } } }> } } } }).inputs.recipe.schema.$defs.step_normalize_v3.properties.params.properties;
    const schema = (change: (p: Record<string, unknown>) => void) => {
      const copy = structuredClone(properties) as Record<string, unknown>;
      change(copy);
      return { properties: copy };
    };
    expect(normalizeForm(schema((p) => void (p.method = { enum: ['linear', 'percentile', 'zscore'] })))).toMatchObject({ supported: false });
    expect(normalizeForm(schema((p) => void delete p.measured))).toMatchObject({ supported: false, reason: expect.stringContaining('measured') });
    expect(normalizeForm(schema((p) => void (p.method = { enum: ['linear', 'percentile', 'zscore', 'robust', 'median'] })))).toMatchObject({ supported: false });
    expect(normalizeForm(null)).toMatchObject({ supported: false });
    expect(normalizeForm({ properties: {} })).toMatchObject({ supported: false });
  });

  it('takes the fields of the method and no others', () => {
    const names = (method: string) => fieldsOfMethod(FIELDS, method).map((f) => f.name);
    expect(names('linear')).toEqual(['method', 'bands', 'in_min', 'in_max', 'out_min', 'out_max', 'clip']);
    expect(names('percentile')).toEqual(['method', 'bands', 'low', 'high', 'out_min', 'out_max', 'clip']);
    expect(names('zscore')).toEqual(['method', 'bands']);
    expect(names('robust')).toEqual(['method', 'bands']);
    expect(names('')).toEqual(['method', 'bands']);
    expect(fieldsOfMethod(FIELDS, 'linear').find((f) => f.name === 'in_min')!.required).toBe(true);
  });
});

describe('the parameters a method writes', () => {
  const values = { bands: 'NDVI', in_min: '-1', in_max: '1', low: '2', high: '98', out_min: '0', out_max: '1', clip: true };

  it.each([
    ['linear', { method: 'linear', bands: ['NDVI'], in_min: -1, in_max: 1, out_min: 0, out_max: 1, clip: true }],
    ['percentile', { method: 'percentile', bands: ['NDVI'], low: 2, high: 98, out_min: 0, out_max: 1, clip: true }],
    ['zscore', { method: 'zscore', bands: ['NDVI'] }],
    ['robust', { method: 'robust', bands: ['NDVI'] }],
  ])('%s: only its own fields, even where the form holds the others', (method, expected) => {
    const { params, errors } = paramsFrom(FIELDS, { ...values, method }, 'normalize');
    expect(errors).toEqual({});
    expect(params).toEqual(expected);
  });

  it('asks for a method, and for the fields of the one chosen', () => {
    expect(paramsFrom(FIELDS, { bands: 'NDVI' }, 'normalize').errors).toEqual({ method: 'Required.' });
    expect(paramsFrom(FIELDS, { method: 'linear', bands: 'NDVI', clip: true }, 'normalize').errors).toEqual({
      in_min: 'Required.',
      in_max: 'Required.',
      out_min: 'Required.',
      out_max: 'Required.',
    });
    expect(paramsFrom(FIELDS, { method: 'zscore', bands: '' }, 'normalize').errors).toEqual({ bands: 'Pick at least one band.' });
  });

  it('refuses numbers the server would refuse, with a comma as a decimal mark, and a range that is not on offer', () => {
    const errors = (change: Record<string, string | boolean>) => paramsFrom(FIELDS, { ...values, method: 'linear', ...change }, 'normalize').errors;
    expect(errors({ in_min: '1', in_max: '1' })).toEqual({ in_max: '“From” must be below “to”.' });
    expect(errors({ in_min: '2', in_max: '1' })).toEqual({ in_max: '“From” must be below “to”.' });
    expect(errors({ out_min: '1', out_max: '1' })).toEqual({ out_max: 'The two ends of the target range differ.' });
    expect(errors({ in_min: '0,2' })).toEqual({ in_min: 'Enter a number.' });
    expect(errors({ in_max: 'abc' })).toEqual({ in_max: 'Enter a number.' });
    expect(errors({ in_max: 'Infinity' })).toEqual({ in_max: 'Enter a number.' });
    // A target that runs backwards is allowed (`out_max` below `out_min`).
    expect(errors({ out_min: '1', out_max: '0' })).toEqual({});
    const percentile = (low: string, high: string) => paramsFrom(FIELDS, { ...values, method: 'percentile', low, high }, 'normalize').errors;
    expect(percentile('3', '98')).toEqual({ low: 'Pick one of the ranges.' });
    expect(percentile('2', '97')).toEqual({ high: 'Pick one of the ranges.' });
    expect(percentile('', '98')).toEqual({ low: 'Required.' });
  });

  it('takes a step of version 2 as the fixed range with its numbers (KE4)', () => {
    const old = { bands: 'red', in_min: '0', in_max: '0.5', low: '', high: '', out_min: '0', out_max: '255', clip: true };
    const values = upgradedValues(old);
    expect(values).toMatchObject({ method: 'linear', low: '2', high: '98', in_min: '0', in_max: '0.5' });
    expect(paramsFrom(FIELDS, values, 'normalize').errors).toEqual({});
  });

  it('refineNormalize leaves a field the form already refused alone', () => {
    const errors = { in_max: 'Enter a number.' };
    refineNormalize({ method: 'linear', in_min: 1, in_max: 0 }, errors);
    expect(errors).toEqual({ in_max: 'Enter a number.' });
  });
});

describe('the numbers taken from the answer of the route (plan §15, point 2)', () => {
  it('percentile: the percentile of the answer, and minimum and maximum for 0 and 100', () => {
    expect(bandNumbers('percentile', 2, 98, STATISTICS)).toEqual({ p_low: -0.1, p_high: 0.85 });
    expect(bandNumbers('percentile', 1, 99, STATISTICS)).toEqual({ p_low: -0.2, p_high: 0.88 });
    expect(bandNumbers('percentile', 5, 95, STATISTICS)).toEqual({ p_low: 0, p_high: 0.8 });
    expect(bandNumbers('percentile', 0, 100, STATISTICS)).toEqual({ p_low: -0.3, p_high: 0.9 });
    expect(bandNumbers('percentile', 0, 98, STATISTICS)).toEqual({ p_low: -0.3, p_high: 0.85 });
  });

  it('zscore: the mean and the standard deviation; robust: the quartiles and the median', () => {
    expect(bandNumbers('zscore', 2, 98, STATISTICS)).toEqual({ mean: 0.4, stddev: 0.2 });
    expect(bandNumbers('robust', 2, 98, STATISTICS)).toEqual({ p25: 0.25, median: 0.4, p75: 0.55 });
  });

  it('has no numbers for a band without a valid value, a missing or not finite number, and for the fixed range', () => {
    expect(bandNumbers('zscore', 2, 98, { count: 0, valid_percent: 0 })).toBeNull();
    const { stddev: _stddev, ...noStddev } = STATISTICS;
    expect(bandNumbers('zscore', 2, 98, noStddev)).toBeNull();
    expect(bandNumbers('zscore', 2, 98, { ...STATISTICS, stddev: Number.NaN })).toBeNull();
    expect(bandNumbers('robust', 2, 98, { ...STATISTICS, percentile_50: '0.4' })).toBeNull();
    expect(bandNumbers('percentile', 2, 98, { ...STATISTICS, percentile_98: Number.POSITIVE_INFINITY })).toBeNull();
    expect(bandNumbers('linear', 2, 98, STATISTICS)).toBeNull();
  });

  it('gives each band of the step its numbers and the factor, or names the bands without', () => {
    const both = answer({ red: STATISTICS, nir: { ...STATISTICS, mean: 0.1 } }, 3);
    expect(measuredFrom('zscore', 2, 98, ['red', 'nir'], both)).toEqual({
      measured: { factor: 3, bands: { red: { mean: 0.4, stddev: 0.2 }, nir: { mean: 0.1, stddev: 0.2 } } },
    });
    expect(measuredFrom('zscore', 2, 98, ['red', 'nir', 'scl'], both)).toEqual({ without: ['scl'] });
    expect(measuredFrom('zscore', 2, 98, ['red', 'nir'], answer({ red: STATISTICS, nir: { count: 0, valid_percent: 0 } }))).toEqual({ without: ['nir'] });
    expect(measuredFrom('zscore', 2, 98, ['red'], answer({ red: STATISTICS }, 0.4))).toMatchObject({ measured: { factor: 1 } });
  });

  it('writes the numbers of each band as the tooltip, and says a coarser read', () => {
    const measured = { factor: 3, bands: { NDVI: { p_low: -0.123456, p_high: 0.8 } } };
    expect(measuredText('percentile', measured)).toBe('NDVI: p_low -0.1235, p_high 0.8\nMeasured on a read 3 times coarser.');
    expect(measuredText('zscore', { factor: 1, bands: { a: { mean: 1, stddev: 2 } } })).toBe('a: mean 1, standard deviation 2');
    expect(measuredText('robust', { factor: 1, bands: { a: { p25: 1, median: 2, p75: 3 } } })).toBe('a: p25 1, median 2, p75 3');
  });
});

describe('buildOrder with a statistical Normalize step', () => {
  const aoi = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);
  const step = (op: string, opVersion: number, values: DraftStep['values'], key: number): DraftStep => ({ key, op, opVersion, values });
  const ndvi = (key = 1) => step('band_math', 2, { expression: '(nir - red) / (nir + red)', name: 'NDVI' }, key);
  const normalize = (method: string, key = 2, bands = 'NDVI') =>
    step('normalize', 3, { method, bands, low: '2', high: '98', in_min: '', in_max: '', out_min: '0', out_max: '1', clip: true }, key);
  const base = {
    datasetId: 'sentinel-2-c1-l2a',
    itemIds: ['S2B_X'],
    area: 'aoi' as const,
    aoi,
    steps: [ndvi(), normalize('percentile')],
    bands: ['NDVI'],
    data: ['blue', 'green', 'red', 'nir', 'scl'],
    dtype: 'float32',
    info: INFO,
  };
  const build = (change: Partial<Parameters<typeof buildOrder>[0]> = {}) => buildOrder({ ...base, ...change });
  const ready = (built: ReturnType<typeof buildOrder>, statistics: Record<string, unknown> = STATISTICS, factor = 1) =>
    new Map<string, MeasureEntry>(built.needs.map((need) => [need.key, { state: 'ready', answer: answer({ NDVI: statistics }, factor) }]));

  it('asks for the steps before the step, its bands and float64, over the AOI, and waits for the answer', () => {
    const built = build();
    expect(built.order).toBeNull();
    expect(built.waiting).toBe('Normalize: measuring the bands…');
    expect(built.stepProblems[1]).toEqual({ errors: {}, measure: { state: 'measuring', text: 'Measuring…' } });
    expect(built.needs).toHaveLength(1);
    const { body, datasetId } = built.needs[0];
    expect(datasetId).toBe('sentinel-2-c1-l2a');
    expect(body.steps.map((s) => s.op)).toEqual(['band_math']);
    expect(body.output).toEqual({ kind: 'raster', format: 'cog', dtype: 'float64', bands: ['NDVI'] });
    expect(body.aoi).toEqual(aoi);
    expect(body.inputs).toEqual([{ name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['S2B_X']] }]);
    // The key is the text of the question; the question is the same for a change of the method that is not a change of the steps before.
    expect(JSON.parse(built.needs[0].key)).toEqual(body);
    expect(build({ steps: [ndvi(), normalize('zscore')] }).needs[0].key).toBe(built.needs[0].key);
  });

  it('asks without any step before it, for the bands of the data', () => {
    const built = build({ steps: [normalize('zscore', 1, 'red')], bands: ['red'] });
    expect(built.needs[0].body.steps).toEqual([]);
    expect(built.needs[0].body.output).toMatchObject({ bands: ['red'], dtype: 'float64' });
  });

  it('asks again where the AOI, the scene, the bands or a step before changes', () => {
    const keys = [
      build().needs[0].key,
      build({ aoi: bboxToPolygon([10.4, 50.4, 10.5, 50.5]) }).needs[0].key,
      build({ itemIds: ['S2B_Y'] }).needs[0].key,
      build({ steps: [step('band_math', 2, { expression: 'nir / red', name: 'NDVI' }, 1), normalize('percentile')] }).needs[0].key,
      build({ steps: [ndvi(), step('mask', 2, { source: 'scl', classes: '3' }, 5), normalize('percentile')] }).needs[0].key,
    ];
    expect(new Set(keys).size).toBe(keys.length);
  });

  it.each([
    ['percentile', { method: 'percentile', bands: ['NDVI'], low: 2, high: 98, out_min: 0, out_max: 1, clip: true, measured: { factor: 1, bands: { NDVI: { p_low: -0.1, p_high: 0.85 } } } }],
    ['zscore', { method: 'zscore', bands: ['NDVI'], measured: { factor: 1, bands: { NDVI: { mean: 0.4, stddev: 0.2 } } } }],
    ['robust', { method: 'robust', bands: ['NDVI'], measured: { factor: 1, bands: { NDVI: { p25: 0.25, median: 0.4, p75: 0.55 } } } }],
  ])('%s: the order holds the method, its fields and the numbers measured, version 3', (method, params) => {
    const waiting = build({ steps: [ndvi(), normalize(method)] });
    const built = build({ steps: [ndvi(), normalize(method)], measures: ready(waiting) });
    expect(built.waiting).toBeNull();
    expect(built.order?.steps[1]).toEqual({ op: 'normalize', op_version: 3, params });
    expect(built.stepProblems[1].measure?.state).toBe('ready');
    expect(built.stepProblems[1].measure?.text).toContain('NDVI');
  });

  it('writes the fixed range without a measure and asks nothing', () => {
    const built = build({ steps: [ndvi(), step('normalize', 3, { method: 'linear', bands: 'NDVI', in_min: '-1', in_max: '1', out_min: '0', out_max: '1', clip: true, low: '2', high: '98' }, 2)] });
    expect(built.needs).toEqual([]);
    expect(built.waiting).toBeNull();
    expect(built.order?.steps[1].params).toEqual({ method: 'linear', bands: ['NDVI'], in_min: -1, in_max: 1, out_min: 0, out_max: 1, clip: true });
  });

  it('holds the order back while the measurement runs or has failed, and says why', () => {
    const failed = new Map<string, MeasureEntry>([[build().needs[0].key, { state: 'failed', reason: 'The area is too large' }]]);
    const built = build({ measures: failed });
    expect(built.order).toBeNull();
    expect(built.waiting).toBe('Normalize: the measurement failed: The area is too large');
    expect(built.stepProblems[1].measure).toEqual({ state: 'failed', text: 'The measurement failed: The area is too large' });
  });

  it('measures a band that has no valid value over the AOI as an error of the bands, and the step does not wait', () => {
    const built = build({ measures: ready(build(), { count: 0, valid_percent: 0 }) });
    expect(built.order).toBeNull();
    expect(built.stepProblems[1].errors).toEqual({ bands: 'No valid values over the AOI in NDVI.' });
    expect(built.waiting).toBeNull();
  });

  it('carries a coarser read into the recipe as the factor', () => {
    const built = build({ steps: [ndvi(), normalize('zscore')], measures: ready(build({ steps: [ndvi(), normalize('zscore')] }), STATISTICS, 3) });
    expect(built.order?.steps[1].params).toMatchObject({ measured: { factor: 3 } });
    expect(built.stepProblems[1].measure?.text).toContain('3 times coarser');
  });

  it('is locked without an AOI and after a reprojection, with the reason at the method, and asks nothing', () => {
    const whole = build({ area: 'scene', aoi: null });
    expect(whole.needs).toEqual([]);
    expect(whole.order).toBeNull();
    expect(whole.stepProblems[1].errors).toEqual({ method: NO_AOI });
    const reproject = step('reproject', 4, { crs: 'EPSG:3035', resolution: '30', resampling: 'bilinear', align: false }, 3);
    const after = build({ steps: [ndvi(), reproject, normalize('zscore', 4)] });
    expect(after.needs).toEqual([]);
    expect(after.stepProblems[2].errors).toEqual({ method: AFTER_REPROJECT });
    // Above the reprojection it is measured.
    expect(build({ steps: [ndvi(), normalize('zscore'), reproject] }).needs).toHaveLength(1);
  });

  it('asks nothing while a step has an error before it or at itself', () => {
    expect(build({ steps: [step('band_math', 2, { expression: '', name: 'NDVI' }, 1), normalize('zscore')] }).needs).toEqual([]);
    expect(build({ steps: [ndvi(), normalize('zscore', 2, '')] }).needs).toEqual([]);
    expect(build({ itemIds: [] }).needs).toEqual([]);
  });

  it('measures the second step on the first one with its numbers, and the second waits for the first', () => {
    const steps = [ndvi(), normalize('zscore', 2), normalize('robust', 3)];
    const first = build({ steps });
    expect(first.needs).toHaveLength(1);
    expect(first.stepProblems[2].measure?.state).toBe('measuring');
    const second = build({ steps, measures: ready(first) });
    expect(second.needs).toHaveLength(2);
    const [, later] = second.needs;
    expect(later.body.steps.map((s) => s.op)).toEqual(['band_math', 'normalize']);
    expect(later.body.steps[1].params).toMatchObject({ method: 'zscore', measured: { factor: 1 } });
    expect(second.order).toBeNull();
    const done = build({ steps, measures: new Map([...ready(first), ...ready(second)]) });
    expect(done.order?.steps.map((s) => (s.params as { method: string }).method)).toEqual([undefined, 'zscore', 'robust']);
  });
});
