import { describe, expect, it, vi } from 'vitest';

import { AOI_CLIP_PROTOCOL } from './aoiClip';
import type { DatasetOption } from './datasets';
import s2 from './fixtures/processes/sentinel-2-c1-l2a.json';
import zarr from './fixtures/processes/synthetic-zarr.json';
import { bboxToPolygon } from './geoUtils';
import { canonicalJson, type Order, type ProcessDescription } from './processing';
import { MAX_MOSAIC_OPERATOR_ASSETS, MAX_MOSAIC_REQUEST_BYTES, MAX_MOSAIC_SCENES, mosaicRequestBytes } from './mosaic';
import { RGB } from './processingBands';
import { processInfo, type BandSource, type DraftStep, type ProcessInfo } from './processingOrder';
import {
  areaMeasureOf,
  assetGsd,
  COARSE_MEASURE_HINT,
  DEFAULT_RANGE,
  finestGsd,
  furtherNote,
  MAX_PREVIEW_SCENES,
  MAX_PREVIEW_STEPS,
  probeMosaic,
  SCENE_MEASURE_HINT,
  SCENE_PREVIEW_HINT,
  type MosaicAnswer,
  previewMaxZoom,
  NO_PREVIEW,
  NO_PREVIEW_FORM,
  NO_PREVIEW_UNLISTED,
  measuredRange,
  measureHint,
  namesNeeded,
  previewRead,
  measureOf,
  planPreview,
  previewOverlays,
  previewTitle,
  previewUnit,
  probeChain,
  refusedNote,
  refusedStepOf,
  shortenPlan,
  previewSpec,
  rescaleOf,
  type PreviewPlan,
  type PreviewSpec,
} from './processingPreview';
import { tileMetres, tileSizeOf } from './tileSize';
import type { Collection, StacItem } from './types';

const S2 = processInfo(s2 as unknown as ProcessDescription);
const ZARR = processInfo(zarr as unknown as ProcessDescription);

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';

// `band_math` adds a band `name` (adr/0020 §6); the panel names the n-th step `Band_Math_<n>`.
function bandMath(expression: string, key = 1): DraftStep {
  return { key, op: 'band_math', opVersion: 2, values: { expression, name: `Band_Math_${key}` } };
}

function normalize(key = 5, values: Record<string, string | boolean> = {}): DraftStep {
  return {
    key,
    op: 'normalize',
    opVersion: 4,
    values: { method: 'linear', bands: 'red', in_min: '0', in_max: '0.5', out_min: '0', out_max: '255', clip: true, ...values },
  };
}

function mask(key = 6, values: Record<string, string | boolean> = {}): DraftStep {
  return { key, op: 'mask', opVersion: 2, values: { source: 'scl', classes: '3, 8, 9, 10', ...values } };
}

// The listed version of the fixtures; it runs only as a job (`T2`).
function reproject(): DraftStep {
  return { key: 2, op: 'reproject', opVersion: 4, values: { crs: 'EPSG:3035', resolution: '30' } };
}

function item(id: string, properties: Record<string, unknown> = {}, redGsd?: number): StacItem {
  const bbox: [number, number, number, number] = [10, 50, 11, 51];
  return {
    id,
    bbox,
    geometry: bboxToPolygon(bbox),
    properties,
    assets: {
      red: { href: 'https://example.org/red.tif', type: COG, ...(redGsd ? { gsd: redGsd } : {}), 'raster:bands': [{ data_type: 'uint16' }] },
      nir: { href: 'https://example.org/nir.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
    },
  };
}

const DATASET: DatasetOption = {
  id: 'sentinel-2-c1-l2a',
  title: 'Sentinel-2 L2A',
  viewable: true,
  groupBy: ['datetime'],
  zoom: { min: 8, max: 14 },
  browse: 'quicklook',
  quicklookNodataMax: null,
  resultsGroupBy: ['datetime'],
  hasTimeAxis: true,
  collection: { id: 'sentinel-2-c1-l2a' } as Collection,
};

function ready(steps: DraftStep[]): Extract<PreviewPlan, { state: 'ready' }> {
  const plan = planPreview(steps, S2);
  if (plan.state !== 'ready') throw new Error(`no plan: ${JSON.stringify(plan)}`);
  return plan;
}

describe('planPreview (adr/0014 §6.1)', () => {
  it('says nothing without steps or a description', () => {
    expect(planPreview([], S2)).toEqual({ state: 'off', reason: null });
    expect(planPreview([bandMath('red')], null)).toEqual({ state: 'off', reason: null });
  });

  it('previews a complete band-math step with its parameters', () => {
    const plan = ready([bandMath('(nir - red) / (nir + red)')]);
    expect(plan.steps).toHaveLength(1);
    expect(plan.steps[0].params).toEqual({ expression: '(nir - red) / (nir + red)', name: 'Band_Math_1' });
    expect(plan.steps[0].operator.op).toBe('band_math');
    expect(plan.further).toBe(false);
  });

  it('waits for a complete step instead of asking the tiler for a half one', () => {
    expect(planPreview([bandMath('')], S2)).toEqual({ state: 'off', reason: 'Complete the step to see the preview.' });
  });

  it('has no preview when the first step runs only as a job, even if a later one would tile', () => {
    expect(planPreview([reproject()], S2)).toEqual({ state: 'off', reason: NO_PREVIEW });
    expect(planPreview([reproject(), bandMath('red')], S2)).toEqual({ state: 'off', reason: NO_PREVIEW });
  });

  it('shows the longest start of tile steps, and says there are more', () => {
    const plan = ready([bandMath('red + nir'), normalize(), reproject(), bandMath('red', 3)]);
    expect(plan.steps.map((s) => s.operator.op)).toEqual(['band_math', 'normalize']);
    expect(plan.steps[1].params).toEqual({ method: 'linear', bands: ['red'], in_min: 0, in_max: 0.5, out_min: 0, out_max: 255, clip: true });
    expect(plan.further).toBe(true);
  });

  it('keeps the order of the steps', () => {
    expect(ready([normalize(), bandMath('red')]).steps.map((s) => s.operator.op)).toEqual(['normalize', 'band_math']);
    expect(ready([bandMath('red'), normalize()]).steps.map((s) => s.operator.op)).toEqual(['band_math', 'normalize']);
  });

  it('ends the start at a step that is incomplete and shows what is before it', () => {
    const plan = ready([normalize(), bandMath('', 3), bandMath('red', 4)]);
    expect(plan.steps.map((s) => s.step.key)).toEqual([5]);
    expect(plan.further).toBe(true);
  });

  it('ends the start at a step that runs only as a job', () => {
    const plan = ready([bandMath('red'), reproject(), normalize()]);
    expect(plan.steps).toHaveLength(1);
    expect(plan.further).toBe(true);
  });

  it('previews a mask as the first step: it runs as a tile (M4-18c)', () => {
    const plan = ready([mask(), bandMath('red')]);
    expect(plan.steps.map((s) => s.operator.op)).toEqual(['mask', 'band_math']);
    expect(plan.steps[0].params).toEqual({ source: 'scl', classes: [3, 8, 9, 10] });
    expect(plan.further).toBe(false);
    expect(ready([mask()]).steps).toHaveLength(1);
  });

  it('writes the classes of a mask ascending and once, whatever order they were typed in', () => {
    expect(ready([mask(6, { classes: '10, 3,3 8' })]).steps[0].params).toEqual({ source: 'scl', classes: [3, 8, 10] });
  });

  it('asks to complete a mask that has no class yet instead of calling it a job-only step', () => {
    expect(planPreview([mask(6, { classes: '' })], S2)).toEqual({
      state: 'off',
      reason: 'Complete the step to see the preview.',
    });
    expect(planPreview([mask(6, { classes: '3, x' })], S2)).toEqual({
      state: 'off',
      reason: 'Complete the step to see the preview.',
    });
  });

  it('never calls a mask a job-only step, whatever else the order holds', () => {
    for (const steps of [[mask()], [mask(), reproject()], [mask(), normalize(), bandMath('red')]]) {
      const plan = planPreview(steps, S2);
      expect(plan.state).toBe('ready');
    }
    expect(planPreview([mask(6, { classes: '' }), reproject()], S2)).not.toEqual({ state: 'off', reason: NO_PREVIEW });
  });

  it('takes no more steps than the tile route does', () => {
    const many = Array.from({ length: MAX_PREVIEW_STEPS + 2 }, (_, i) => normalize(10 + i));
    const plan = ready(many);
    expect(plan.steps).toHaveLength(MAX_PREVIEW_STEPS);
    expect(plan.further).toBe(true);
  });

  it('asks to complete the first step when it is the one that is incomplete', () => {
    expect(planPreview([normalize(5, { in_max: '' }), bandMath('red')], S2)).toEqual({
      state: 'off',
      reason: 'Complete the step to see the preview.',
    });
  });

  it('says how much of the job the map shows', () => {
    expect(furtherNote(ready([bandMath('red'), reproject()]))).toBe('The map shows the first step; the job runs all steps.');
    expect(furtherNote(ready([bandMath('red'), normalize(), reproject()]))).toBe(
      'The map shows the first 2 steps; the job runs all steps.',
    );
  });

  it('says that an operator the dataset does not list is not available, not that it is a job', () => {
    const stranger: DraftStep = { key: 9, op: 'decomp', opVersion: 1, values: {} };
    expect(planPreview([stranger], S2)).toEqual({ state: 'off', reason: NO_PREVIEW_UNLISTED });
    // Version 1 of the operators that changed is no longer listed (adr/0020 §9).
    for (const old of [mask(), bandMath('red'), normalize()]) {
      expect(planPreview([{ ...old, opVersion: 1 }], S2)).toEqual({ state: 'off', reason: NO_PREVIEW_UNLISTED });
    }
  });

  it('says that the panel has no form for a tile operator, not that it runs only as a job', () => {
    const noForm: ProcessInfo = {
      ...S2,
      operators: S2.operators.map((o) =>
        o.op === 'mask' ? { ...o, form: { supported: false, reason: 'not supported by this panel: keyword x' } } : o,
      ),
    };
    expect(planPreview([mask()], noForm)).toEqual({ state: 'off', reason: NO_PREVIEW_FORM });
    expect(NO_PREVIEW_FORM).not.toContain('only as a job');
  });
});

describe('a statistical normalize step in the chain (NM4-11b)', () => {
  const zscore = (key = 5, values: Record<string, string | boolean> = {}) => normalize(key, { method: 'zscore', ...values });
  const numbers = new Map([[5, { factor: 1, bands: { red: { mean: 2000, stddev: 500 } } }]]);

  it('is drawn with the numbers measured for it, in its parameters', () => {
    const plan = planPreview([bandMath('red + nir'), zscore()], S2, numbers);
    expect(plan.state === 'ready' && plan.steps[1].params).toEqual({
      method: 'zscore',
      bands: ['red'],
      measured: { factor: 1, bands: { red: { mean: 2000, stddev: 500 } } },
    });
  });

  it('ends the start before the step while it has no numbers, and says what is missing where it is the first', () => {
    const plan = planPreview([bandMath('red + nir'), zscore(), bandMath('red', 3)], S2);
    expect(plan.state === 'ready' && plan.steps.map((s) => s.operator.op)).toEqual(['band_math']);
    expect(plan.state === 'ready' && plan.further).toBe(true);
    expect(planPreview([zscore()], S2)).toEqual({ state: 'off', reason: 'Normalize has no measured numbers yet.' });
    expect(planPreview([normalize(5, { method: 'zscore', bands: '' })], S2)).toEqual({ state: 'off', reason: 'Complete the step to see the preview.' });
  });

  it('takes the numbers of its own step only, and none for the fixed range', () => {
    expect(planPreview([zscore(6)], S2, numbers)).toEqual({ state: 'off', reason: 'Normalize has no measured numbers yet.' });
    const fixed = planPreview([normalize()], S2, numbers);
    expect(fixed.state === 'ready' && 'measured' in fixed.steps[0].params).toBe(false);
  });

  it('takes version 4, which runs only as a job, to the tile as version 3 (NM4-71), the fixed range with the same fields', () => {
    const operator = S2.operators.find((o) => o.op === 'normalize')!;
    expect([operator.opVersion, operator.tiers]).toEqual([4, ['T2']]);
    const plan = planPreview([bandMath('red + nir'), zscore(), normalize(6)], S2, numbers);
    if (plan.state !== 'ready') throw new Error('no plan');
    expect(plan.steps.map((s) => [s.step.opVersion, s.version])).toEqual([[2, 2], [4, 3], [4, 3]]);
    expect(plan.steps[2].params).toEqual({ method: 'linear', bands: ['red'], in_min: 0, in_max: 0.5, out_min: 0, out_max: 255, clip: true });
  });

  it('ends the start before a step whose parameters are longer than the tile route takes', () => {
    const bands = Array.from({ length: 80 }, (_, i) => `band_${i}`);
    const many = { factor: 1, bands: Object.fromEntries(bands.map((name) => [name, { mean: 2000.123456, stddev: 500.654321 }])) };
    const plan = planPreview([bandMath('red'), zscore(5, { bands: bands.join(', ') })], S2, new Map([[5, many]]));
    expect(plan.state === 'ready' && plan.steps.map((s) => s.operator.op)).toEqual(['band_math']);
    expect(plan.state === 'ready' && plan.further).toBe(true);
  });

  it('makes the tile URL carry the numbers, and a new key where they change', () => {
    const base = { dataset: DATASET, items: [item('S2_A', { gsd: 10 })], assets: ['red', 'nir'], info: S2, range: DEFAULT_RANGE, area: 'scene' as const };
    const plan = planPreview([zscore()], S2, numbers);
    if (plan.state !== 'ready') throw new Error('no plan');
    const a = previewSpec({ ...base, plan })!;
    const url = new URL(a.scenes[0].url, 'http://localhost');
    expect(url.searchParams.getAll('op_version')).toEqual(['3']);
    expect(JSON.parse(url.searchParams.get('params')!)).toMatchObject({ method: 'zscore', measured: { bands: { red: { mean: 2000, stddev: 500 } } } });
    const other = planPreview([zscore()], S2, new Map([[5, { factor: 1, bands: { red: { mean: 2100, stddev: 500 } } }]]));
    if (other.state !== 'ready') throw new Error('no plan');
    expect(previewSpec({ ...base, plan: other })!.key).not.toBe(a.key);
  });
});

describe('rescaleOf', () => {
  it('writes min,max for the tile URL', () => {
    expect(rescaleOf(DEFAULT_RANGE)).toEqual({ rescale: '-1,1' });
    expect(rescaleOf({ vmin: '0.5', vmax: '2000', colormap: '' })).toEqual({ rescale: '0.5,2000' });
  });

  it.each([
    ['', '1'],
    ['0', ''],
    ['abc', '1'],
    ['1', '1'],
    ['2', '1'],
    ['0', 'Infinity'],
  ])('refuses %j to %j', (vmin, vmax) => {
    expect(rescaleOf({ vmin, vmax, colormap: '' })).toHaveProperty('problem');
  });
});

describe('previewSpec', () => {
  const items = [item('S2_A', { gsd: 10 }), item('S2_B', { gsd: 10 })];
  const base = { dataset: DATASET, items, assets: ['red', 'nir'], info: S2, range: DEFAULT_RANGE, area: 'scene' as const };

  it('gives one tile template per scene, with the operator, canonical parameters and the range', () => {
    const spec = previewSpec({ ...base, plan: ready([bandMath('(nir - red) / (nir + red)')]) })!;
    expect(spec.scenes.map((s) => s.id)).toEqual(['S2_A', 'S2_B']);
    expect(spec.scenes[0].url.split('?')[0]).toBe(
      '/collections/sentinel-2-c1-l2a/items/S2_A/tiles/WebMercatorQuad/{z}/{x}/{y}',
    );
    const url = new URL(spec.scenes[0].url, 'http://localhost');
    expect(url.searchParams.getAll('asset')).toEqual(['red', 'nir']);
    expect(url.searchParams.get('op')).toBe('band_math');
    expect(url.searchParams.get('op_version')).toBe('2');
    expect(url.searchParams.get('params')).toBe('{"expression":"(nir - red) / (nir + red)","name":"Band_Math_1"}');
    expect(url.searchParams.get('rescale')).toBe('-1,1');
    expect(url.searchParams.get('colormap_name')).toBe('rdylgn');
    expect(spec).toMatchObject({ title: 'Band math', minZoom: 8, maxZoom: 13, clipToAoi: false });
  });

  it('chains the steps in the URL: op, op_version and params once per step, in order', () => {
    const plan = ready([normalize(), bandMath('red / 2', 3)]);
    const spec = previewSpec({ ...base, plan })!;
    const url = new URL(spec.scenes[0].url, 'http://localhost');
    expect(url.searchParams.getAll('asset')).toEqual(['red', 'nir']);
    expect(url.searchParams.getAll('op')).toEqual(['normalize', 'band_math']);
    expect(url.searchParams.getAll('op_version')).toEqual(['3', '2']);
    expect(url.searchParams.getAll('params')).toEqual([
      '{"bands":["red"],"clip":true,"in_max":0.5,"in_min":0,"method":"linear","out_max":255,"out_min":0}',
      '{"expression":"red / 2","name":"Band_Math_3"}',
    ]);
    expect(spec.title).toBe('Normalize → Band math');
    const order = [...url.search.matchAll(/(?:^|&|\?)(op|op_version|params)=/g)].map((m) => m[1]);
    expect(order).toEqual(['op', 'op_version', 'params', 'op', 'op_version', 'params']);
  });

  it('names the statistics of the first scene with the same steps, whatever the range', () => {
    const plan = ready([normalize(), bandMath('red / 2', 3)]);
    const a = previewSpec({ ...base, plan })!;
    const b = previewSpec({ ...base, plan, range: { vmin: '0', vmax: '9', colormap: 'viridis' } })!;
    expect(a.key).not.toBe(b.key);
    expect(a.measure).toBe(b.measure);
    const url = new URL(a.measure, 'http://localhost');
    expect(url.pathname).toBe('/collections/sentinel-2-c1-l2a/items/S2_A/statistics');
    expect(url.searchParams.getAll('op')).toEqual(['normalize', 'band_math']);
    expect(url.searchParams.has('rescale')).toBe(false);
    expect(a.expression).toBe(true);
    expect(previewSpec({ ...base, plan: ready([normalize()]) })!.expression).toBe(false);
  });

  it('has another key for the steps in another order', () => {
    const a = previewSpec({ ...base, plan: ready([normalize(), bandMath('red', 3)]) })!;
    const b = previewSpec({ ...base, plan: ready([bandMath('red', 3), normalize()]) })!;
    expect(a.key).not.toBe(b.key);
  });

  it('keeps the placeholders of the tile grid and survives characters of a URL in the expression', () => {
    const expression = 'where(red > 100 & nir < 5, red % 3, nir) # "a+b" ?=&';
    const spec = previewSpec({ ...base, plan: ready([bandMath(expression)]) })!;
    const template = spec.scenes[0].url;
    expect(template).toContain('/{z}/{x}/{y}?');
    expect(JSON.parse(new URL(template, 'http://localhost').searchParams.get('params')!)).toEqual({ expression, name: 'Band_Math_1' });
    // Only the query carries the expression; nothing of it leaks into the path.
    expect(template.split('?')[0]).not.toContain('where');
  });

  it('asks for no colormap when none is chosen', () => {
    const spec = previewSpec({ ...base, range: { vmin: '0', vmax: '1', colormap: '' }, plan: ready([bandMath('red')]) })!;
    const params = new URL(spec.scenes[0].url, 'http://localhost').searchParams;
    expect(params.has('colormap_name')).toBe(false);
    expect(params.get('rescale')).toBe('0,1');
  });

  it('has another key for another picture and the same key for the same one', () => {
    const a = previewSpec({ ...base, plan: ready([bandMath('red')]) })!;
    expect(previewSpec({ ...base, plan: ready([bandMath('red')]) })!.key).toBe(a.key);
    expect(previewSpec({ ...base, plan: ready([bandMath('nir')]) })!.key).not.toBe(a.key);
    expect(previewSpec({ ...base, range: { ...DEFAULT_RANGE, vmax: '2' }, plan: ready([bandMath('red')]) })!.key).not.toBe(a.key);
    expect(previewSpec({ ...base, area: 'aoi', plan: ready([bandMath('red')]) })!.key).not.toBe(a.key);
  });

  it('is cut to the AOI only for "AOI only"', () => {
    const aoi = bboxToPolygon([10.2, 50.2, 10.4, 50.4]);
    const whole = previewSpec({ ...base, plan: ready([bandMath('red')]) })!;
    const cut = previewSpec({ ...base, area: 'aoi', plan: ready([bandMath('red')]) })!;
    expect(whole.clipToAoi).toBe(false);
    expect(cut.clipToAoi).toBe(true);
    expect(previewOverlays(whole, aoi).map((o) => o.kind === 'raster' && o.tileUrl.startsWith(`${AOI_CLIP_PROTOCOL}://`))).toEqual([false, false]);
    expect(previewOverlays(cut, aoi).map((o) => o.kind === 'raster' && o.tileUrl.startsWith(`${AOI_CLIP_PROTOCOL}://`))).toEqual([true, true]);
    // The unclipped template stays the same: the AOI is never part of a tile URL (Q8).
    expect(cut.scenes[0].url).toBe(whole.scenes[0].url);
    expect(JSON.stringify(cut)).not.toContain('10.2');
  });

  it('marks its overlays as a preview, held under the pixel size of the data', () => {
    const spec = previewSpec({ ...base, plan: ready([bandMath('red')]) })!;
    expect(tileMetres(51, spec.maxZoom, 256)).toBeGreaterThan(10);
    expect(previewOverlays(spec, null)[0]).toMatchObject({ kind: 'raster', bounds: [10, 50, 11, 51], preview: true });
  });

  it('shows nothing it cannot draw', () => {
    const plan = ready([bandMath('red')]);
    expect(previewSpec({ ...base, plan, assets: [] })).toBeNull();
    expect(previewSpec({ ...base, plan, assets: Array.from({ length: 17 }, (_, i) => `b${i}`) })).toBeNull();
    expect(previewSpec({ ...base, plan, range: { ...DEFAULT_RANGE, vmin: '1', vmax: '1' } })).toBeNull();
    expect(previewSpec({ ...base, plan, dataset: undefined })).toBeNull();
    expect(previewSpec({ ...base, plan, dataset: { ...DATASET, viewable: false, reason: 'x' } as DatasetOption })).toBeNull();
    expect(previewSpec({ ...base, plan, items: [{ ...items[0], bbox: null }] })).toBeNull();
  });

  it('draws as before, up to the last released level, when the data names no pixel size', () => {
    const spec = previewSpec({ ...base, plan: ready([bandMath('red')]), items: [item('S2_A'), item('S2_B')] })!;
    expect(spec).toMatchObject({ minZoom: 8, maxZoom: 14 });
    expect(spec.scenes).toHaveLength(2);
  });

  it('takes the scenes without a footprint out and no more than the full-resolution view draws', () => {
    const plan = ready([bandMath('red')]);
    const many = Array.from({ length: MAX_PREVIEW_SCENES + 5 }, (_, i) => item(`S${i}`, { gsd: 10 }));
    expect(previewSpec({ ...base, plan, items: many })!.scenes).toHaveLength(MAX_PREVIEW_SCENES);
    const spec = previewSpec({ ...base, plan, items: [{ ...items[0], bbox: null }, items[1]] })!;
    expect(spec.scenes.map((s) => s.id)).toEqual(['S2_B']);
  });
});

describe('previewSpec: the mosaic of a job (NM4-04b)', () => {
  const ids = ['S2_C', 'S2_A', 'S2_B', 'S2_D'];
  const items = ids.map((id) => item(id, { gsd: 10 }));
  const plan = ready([bandMath('(nir - red) / (nir + red)')]);
  const base = { dataset: DATASET, items, assets: ['red', 'nir'], info: S2, range: DEFAULT_RANGE, area: 'scene' as const, plan, jobs: [items] };
  // The dataset is released below the first level of a mosaic, so that single scenes can stand under it.
  const wide: DatasetOption = { ...DATASET, zoom: { min: 5, max: 14 } };
  const taken = (order: string[]): MosaicAnswer => ({ state: 'taken', order });
  const query = (url: string) => new URL(url, 'http://localhost');

  it('draws a job of several scenes as one mosaic: the scenes by id, the assets and the steps', () => {
    const spec = previewSpec(base)!;
    expect(spec.mosaics).toHaveLength(1);
    const url = query(spec.mosaics[0].url);
    expect(spec.mosaics[0].url.split('?')[0]).toBe('/collections/sentinel-2-c1-l2a/mosaic/tiles/WebMercatorQuad/{z}/{x}/{y}');
    expect(url.searchParams.getAll('item')).toEqual(['S2_A', 'S2_B', 'S2_C', 'S2_D']);
    expect(url.searchParams.getAll('asset')).toEqual(['red', 'nir']);
    expect(url.searchParams.getAll('op')).toEqual(['band_math']);
    expect(url.searchParams.getAll('op_version')).toEqual(['2']);
    expect(url.searchParams.get('params')).toBe('{"expression":"(nir - red) / (nir + red)","name":"Band_Math_1"}');
    expect(url.searchParams.get('rescale')).toBe('-1,1');
    expect(url.searchParams.get('colormap_name')).toBe('rdylgn');
    expect(spec.mosaics[0].bounds).toEqual([10, 50, 11, 51]);
    expect(spec.perScene).toBe(false);
  });

  it('is the same URL for the same pass, whatever order the scenes were picked in', () => {
    const a = previewSpec(base)!;
    const b = previewSpec({ ...base, jobs: [[...items].reverse()] })!;
    expect(b.mosaics[0].url).toBe(a.mosaics[0].url);
    expect(b.mosaics[0].probe).toBe(a.mosaics[0].probe);
  });

  it('carries no AOI, no id of a job, a recipe or a permalink and no hash, in any URL it builds', () => {
    const spec = previewSpec({ ...base, area: 'aoi', dataset: wide })!;
    const known = new Set(['item', 'asset', 'op', 'op_version', 'params', 'rescale', 'colormap_name', 'tilesize']);
    for (const url of [spec.mosaics[0].url, spec.mosaics[0].probe, spec.probe, spec.measure, ...spec.scenes.map((s) => s.url)]) {
      expect(url).not.toContain('#');
      expect([...new Set(query(url).searchParams.keys())].filter((name) => !known.has(name))).toEqual([]);
    }
    expect(spec.clipToAoi).toBe(true);
  });

  it('draws one mosaic for each job of a batch per pass, and a job of one scene alone', () => {
    const second = [item('S2_E', { gsd: 10 }), item('S2_F', { gsd: 10 })];
    const lone = item('S2_G', { gsd: 10 });
    const spec = previewSpec({ ...base, items: [...items, ...second, lone], jobs: [items, second, [lone]] })!;
    expect(spec.mosaics.map((m) => query(m.url).searchParams.getAll('item'))).toEqual([
      ['S2_A', 'S2_B', 'S2_C', 'S2_D'],
      ['S2_E', 'S2_F'],
    ]);
    expect(spec.scenes.map((s) => s.id)).toEqual(['S2_G']);
    expect(spec.perScene).toBe(false);
  });

  it('draws a job of one scene, and every job of a batch per scene, as it did before, with no hint', () => {
    expect(previewSpec({ ...base, items: [items[0]], jobs: [[items[0]]] })).toMatchObject({ mosaics: [], perScene: false });
    const spec = previewSpec({ ...base, jobs: items.map((i) => [i]) })!;
    expect(spec).toMatchObject({ mosaics: [], perScene: false });
    expect(spec.scenes).toHaveLength(4);
  });

  it('stacks the scenes below the first level of the mosaic in the order of the tiler, and measures the first', () => {
    const answers = new Map([[previewSpec({ ...base, dataset: wide })!.mosaics[0].probe, taken(['S2_D', 'S2_B', 'S2_A', 'S2_C'])]]);
    const spec = previewSpec({ ...base, dataset: wide, answers })!;
    expect(spec.mosaics[0].order).toEqual(['S2_D', 'S2_B', 'S2_A', 'S2_C']);
    expect(spec.scenes.map((s) => [s.id, s.below])).toEqual([['S2_D', 8], ['S2_B', 8], ['S2_A', 8], ['S2_C', 8]]);
    expect(query(spec.measure).pathname).toBe('/collections/sentinel-2-c1-l2a/items/S2_D/statistics');
    const overlays = previewOverlays(spec, null);
    // The mosaic's tiles are 512 px: its last level is one below the scenes' (13), and it is asked for from map zoom 7.5,
    // where the scenes step aside (NM4-29b).
    expect(spec.maxZoom).toBe(13);
    expect(overlays[0]).toMatchObject({ minZoom: 8, maxZoom: 12, preview: true });
    expect(overlays[0]).not.toHaveProperty('hideFrom');
    expect(overlays.slice(1).map((o) => o.kind === 'raster' && [o.minZoom, o.maxZoom, o.hideFrom])).toEqual(
      Array(4).fill([5, 7, 7.5]),
    );
    expect(overlays.map((o) => o.kind === 'raster' && tileSizeOf(o.tileUrl))).toEqual([512, 256, 256, 256, 256]);
    expect(overlays.slice(1).map((o) => o.kind === 'raster' && query(o.tileUrl).pathname.split('/')[4])).toEqual(['S2_D', 'S2_B', 'S2_A', 'S2_C']);
  });

  it('adds the scenes an answer leaves out, by id, and ignores the ones it makes up', () => {
    const probe = previewSpec(base)!.mosaics[0].probe;
    const answers = new Map([[probe, taken(['S2_C', 'X', 'S2_C', 'S2_B'])]]);
    expect(previewSpec({ ...base, answers })!.mosaics[0].order).toEqual(['S2_C', 'S2_B', 'S2_A', 'S2_D']);
  });

  it('draws no scene below a mosaic where the dataset starts at its first level', () => {
    const spec = previewSpec(base)!;
    expect(spec.scenes).toEqual([]);
    expect(query(spec.measure).pathname).toBe('/collections/sentinel-2-c1-l2a/items/S2_A/statistics');
  });

  describe('falls back to the scenes one by one, and says so', () => {
    const scenesOnly = (spec: ReturnType<typeof previewSpec>) => {
      expect(spec).toMatchObject({ mosaics: [], perScene: true });
      expect(spec!.scenes.map((s) => s.below)).toEqual(Array(spec!.scenes.length).fill(undefined));
    };

    it(`for more than ${MAX_MOSAIC_OPERATOR_ASSETS} assets`, () => {
      const assets = ['a', 'b', 'c', 'd', 'e'];
      const spec = previewSpec({ ...base, assets, items: items.map((i) => ({ ...i, assets: Object.fromEntries(assets.map((a) => [a, i.assets!.red])) })) });
      scenesOnly(spec);
      expect(spec!.scenes.map((s) => s.id)).toEqual(ids);
    });

    it(`keeps the mosaic for ${MAX_MOSAIC_OPERATOR_ASSETS} assets`, () => {
      expect(previewSpec({ ...base, assets: ['a', 'b', 'c', 'd'] })!.mosaics).toHaveLength(1);
    });

    it(`for more than ${MAX_MOSAIC_SCENES} scenes, and keeps the mosaic for ${MAX_MOSAIC_SCENES}`, () => {
      const many = (count: number) => Array.from({ length: count }, (_, i) => item(`S${String(i).padStart(3, '0')}`, { gsd: 10 }));
      const sixtyFive = many(MAX_MOSAIC_SCENES + 1);
      scenesOnly(previewSpec({ ...base, items: sixtyFive, jobs: [sixtyFive] }));
      const sixtyFour = many(MAX_MOSAIC_SCENES);
      expect(previewSpec({ ...base, items: sixtyFour, jobs: [sixtyFour] })!.mosaics).toHaveLength(1);
    });

    it('for a dataset released only below the first level of a mosaic', () => {
      scenesOnly(previewSpec({ ...base, dataset: { ...DATASET, zoom: { min: 2, max: 7 } } }));
    });

    it('for a request longer than the tiler takes, and keeps the mosaic at the limit', () => {
      const long = (length: number) => Array.from({ length: 40 }, (_, i) => item(`${String(i).padStart(2, '0')}${'x'.repeat(length)}`, { gsd: 10 }));
      const fits = long(60);
      expect(previewSpec({ ...base, items: fits, jobs: [fits] })!.mosaics).toHaveLength(1);
      const tooLong = long(260);
      scenesOnly(previewSpec({ ...base, items: tooLong, jobs: [tooLong] }));
    });

    it(`at ${MAX_MOSAIC_REQUEST_BYTES} bytes of request and not at ${MAX_MOSAIC_REQUEST_BYTES + 1}`, () => {
      const padded = (extra: number) => items.map((it, i) => (i === 0 ? { ...it, id: `${it.id}${'x'.repeat(extra)}` } : it));
      const first = previewSpec({ ...base })!;
      const room = MAX_MOSAIC_REQUEST_BYTES - mosaicRequestBytes(first.mosaics[0].url, first.maxZoom);
      const exact = padded(room);
      const atLimit = previewSpec({ ...base, items: exact, jobs: [exact] })!;
      expect(mosaicRequestBytes(atLimit.mosaics[0].url, atLimit.maxZoom)).toBe(MAX_MOSAIC_REQUEST_BYTES);
      const over = padded(room + 1);
      scenesOnly(previewSpec({ ...base, items: over, jobs: [over] }));
    });

    it('for a mosaic the tiler did not take', () => {
      const probe = previewSpec(base)!.mosaics[0].probe;
      scenesOnly(previewSpec({ ...base, answers: new Map([[probe, { state: 'scenes' }]]) }));
    });

    it('for the one job that is too big, and the mosaic for the other', () => {
      const big = Array.from({ length: MAX_MOSAIC_SCENES + 1 }, (_, i) => item(`B${String(i).padStart(3, '0')}`, { gsd: 10 }));
      const spec = previewSpec({ ...base, items: [...items, ...big], jobs: [items, big] })!;
      expect(spec.mosaics).toHaveLength(1);
      expect(spec.perScene).toBe(true);
      expect(spec.scenes.map((s) => s.id)).toEqual(big.map((b) => b.id).slice(0, MAX_PREVIEW_SCENES - 1));
    });

    it('keeps the scenes drawn alone when a mosaic is big, and fills the rest with the scenes below it', () => {
      const big = Array.from({ length: 45 }, (_, i) => item(`A${String(i).padStart(2, '0')}`, { gsd: 10 }));
      const lone = item('B_LONE', { gsd: 10 });
      const spec = previewSpec({ ...base, dataset: wide, items: [...big, lone], jobs: [big, [lone]] })!;
      expect(spec.mosaics).toHaveLength(1);
      expect(spec.scenes).toHaveLength(MAX_PREVIEW_SCENES - 1);
      expect(spec.scenes.filter((s) => s.below === undefined).map((s) => s.id)).toEqual(['B_LONE']);
      expect(spec.scenes.filter((s) => s.below !== undefined)).toHaveLength(MAX_PREVIEW_SCENES - 2);
    });

    it('with the hint a person can read', () => {
      expect(SCENE_PREVIEW_HINT).toBe('Preview per scene – may differ from the job where scenes overlap');
    });
  });

  it('measures the request the way the tiler counts it, at the largest tile of the last level', () => {
    const spec = previewSpec(base)!;
    const bytes = mosaicRequestBytes(spec.mosaics[0].url, spec.maxZoom);
    const url = spec.mosaics[0].url.replace('{z}', '13').replace('{x}', '8191').replace('{y}', '8191');
    expect(bytes).toBe(url.length);
    expect(bytes).toBeLessThanOrEqual(MAX_MOSAIC_REQUEST_BYTES);
  });

  it('has another key for a mosaic, another order and the scenes alone', () => {
    const mosaic = previewSpec({ ...base, dataset: wide })!;
    const probe = mosaic.mosaics[0].probe;
    const ordered = previewSpec({ ...base, dataset: wide, answers: new Map([[probe, taken(ids)]]) })!;
    const alone = previewSpec({ ...base, dataset: wide, jobs: [] })!;
    expect(new Set([mosaic.key, ordered.key, alone.key]).size).toBe(3);
    expect(previewSpec({ ...base, dataset: wide })!.key).toBe(mosaic.key);
  });
});

describe('probeMosaic (NM4-04b)', () => {
  const answer = (status: number, body: unknown) => async () =>
    new Response(typeof body === 'string' ? body : JSON.stringify(body), { status });
  const probe = (reply: () => Promise<Response>) => probeMosaic('/mosaic/tilejson.json?item=A', reply as unknown as typeof fetch);

  it('takes the mosaic and the order of its scenes', async () => {
    expect(await probe(answer(200, { tilejson: '3.0.0', 'earthx:order': ['B', 'A'] }))).toEqual({ state: 'taken', order: ['B', 'A'] });
  });

  it('asks for the TileJSON it was given', async () => {
    const reply = vi.fn(answer(200, { 'earthx:order': ['A'] }));
    await probe(reply);
    expect(reply).toHaveBeenCalledWith('/mosaic/tilejson.json?item=A', { signal: expect.any(AbortSignal) });
  });

  it('names the step a refusal names, as for one scene', async () => {
    expect(await probe(answer(422, { detail: 'step 1: expression names unknown band(s): red' }))).toEqual({
      state: 'refused',
      refused: { step: 1, reason: 'expression names unknown band(s): red' },
    });
  });

  it.each([
    ['a request that is too long', 414, { detail: 'a mosaic request takes at most 7168 bytes, not 8000' }],
    ['a mosaic of too few scenes', 400, { detail: 'a mosaic takes 2 to 64 items, not 1' }],
    ['a dataset that does not reproject', 422, { detail: "'x' does not allow reprojection, which a mosaic of scenes may need" }],
    ['scenes that scale a band differently', 422, { detail: "the scenes of the mosaic scale 'red' differently" }],
    ['a single step the tiler refuses (no step to name)', 422, { detail: 'expression: not a valid expression' }],
    ['a mosaic it does not serve', 501, { detail: 'no mosaic' }],
    ['an answer that is no JSON', 414, 'Request-URI Too Large'],
  ])('draws the scenes one by one for %s', async (_, status, body) => {
    expect(await probe(answer(status, body))).toEqual({ state: 'scenes' });
  });

  it.each([
    ['a missing scene', 404, { detail: 'item not found' }],
    ['a busy tiler', 429, { detail: 'busy' }],
    ['a failing source', 502, { detail: 'step 1: looks like a step but is no refusal' }],
    ['a tiler that is down', 503, 'unavailable'],
  ])('draws the scenes for now, and asks again later, for %s', async (_, status, body) => {
    expect(await probe(answer(status, body))).toEqual({ state: 'scenes', retry: true });
  });

  it.each([
    ['no order', { tilejson: '3.0.0' }],
    ['an empty order', { 'earthx:order': [] }],
    ['an order that is no list of ids', { 'earthx:order': ['A', 1] }],
    ['an answer that is no JSON', 'nope'],
  ])('draws the scenes one by one for %s', async (_, body) => {
    expect(await probe(answer(200, body))).toEqual({ state: 'scenes' });
  });

  it('draws the scenes for now, and asks again later, when the network fails or no answer comes in time', async () => {
    expect(await probe(async () => Promise.reject(new TypeError('failed')))).toEqual({ state: 'scenes', retry: true });
    expect(await probe(async () => Promise.reject(new DOMException('timed out', 'TimeoutError')))).toEqual({ state: 'scenes', retry: true });
  });
});

// NM4-19b: what "AOI only" measures its range on.
describe('previewSpec: what the range is measured on (NM4-19)', () => {
  const items = [item('S2_A', { gsd: 10 }), item('S2_B', { gsd: 10 })];
  const base = { dataset: DATASET, items, assets: ['red', 'nir'], info: S2, range: DEFAULT_RANGE };
  const order = {
    recipe_version: 2,
    inputs: [{ name: 'in', dataset: 'sentinel-2-c1-l2a', groups: [['S2_A', 'S2_B']] }],
    aoi: bboxToPolygon([10.4, 50.4, 10.6, 50.6]),
    steps: [{ op: 'band_math', op_version: 2, params: { expression: '(nir - red) / (nir + red)', name: 'Band_Math_1' } }],
    output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['Band_Math_1'] },
  } as unknown as Order;
  const plan = ready([bandMath('(nir - red) / (nir + red)')]);

  it('is the order of the first job, kept in memory, for "AOI only" and a complete chain', () => {
    const spec = previewSpec({ ...base, plan, area: 'aoi', order })!;
    expect(spec.areaOrder).toEqual({ datasetId: 'sentinel-2-c1-l2a', order });
    expect(spec.measure).toBe(canonicalJson(order));
    // The scene it falls back on is the first scene's as ever.
    expect(spec.sceneMeasure).toContain('/collections/sentinel-2-c1-l2a/items/S2_A/statistics?');
  });

  it('puts neither the AOI nor the order into a URL of the preview', () => {
    const spec = previewSpec({ ...base, plan, area: 'aoi', order })!;
    const urls = [spec.sceneMeasure, spec.probe, ...spec.scenes.map((scene) => scene.url), ...spec.mosaics.flatMap((m) => [m.url, m.probe])];
    for (const url of urls) {
      expect(url).not.toMatch(/10\.4|50\.6|coordinates|recipe_version|aoi/i);
      expect(url).not.toContain(encodeURIComponent(spec.measure));
    }
  });

  it.each([
    ['"Whole scene"', { area: 'scene' as const, order }],
    ['no complete order', { area: 'aoi' as const, order: null }],
    ['a start of the chain', { area: 'aoi' as const, order, plan: { ...plan, further: true } }],
  ])('is the first scene for %s', (_, args) => {
    const spec = previewSpec({ ...base, plan, ...args })!;
    expect(spec.areaOrder).toBeNull();
    expect(spec.measure).toBe(spec.sceneMeasure);
  });

  it('is the first scene without an order at all, as before', () => {
    const spec = previewSpec({ ...base, plan, area: 'aoi' })!;
    expect(spec.areaOrder).toBeNull();
  });

  it('does not change the picture: the key of the tiles ignores the order', () => {
    const a = previewSpec({ ...base, plan, area: 'aoi', order })!;
    const b = previewSpec({ ...base, plan, area: 'aoi', order: { ...order, aoi: bboxToPolygon([10.45, 50.45, 10.55, 50.55]) } })!;
    expect(a.key).toBe(b.key);
    expect(a.measure).not.toBe(b.measure);
  });
});

describe('the measure over the AOI (NM4-19)', () => {
  const answer = (statistics: Record<string, unknown>, unit: string | null = null, exact = true) => ({
    bands: [{ name: 'b1', unit, statistics }],
    exact,
    factor: exact ? 1 : 2,
  });
  const ndvi = { minimum: -1.3, maximum: 1.5, mean: 0.3, stddev: 0.2, count: 900, valid_percent: 100, percentile_2: 0, percentile_98: 0.91 };

  it('reads the statistics of the results document: the numbers a colour scale is chosen from, the unit, whether it is exact', () => {
    expect(areaMeasureOf('K', answer(ndvi, 'm', false), true)).toMatchObject({
      key: 'K',
      stats: { bands: [{ minimum: -1.3, maximum: 1.5, percentile2: 0, percentile98: 0.91 }], expression: true },
      unit: 'm',
      source: 'area',
      exact: false,
    });
  });

  it('names no value of a band without a valid pixel, and one unit only where all bands share it', () => {
    const none = { count: 0, valid_percent: 0 };
    expect(areaMeasureOf('K', answer(none), true).stats).toBeNull();
    const two = { bands: [answer(ndvi, 'K').bands[0], answer(ndvi, 'm').bands[0]], exact: true, factor: 1 };
    expect(areaMeasureOf('K', two, false).unit).toBeNull();
  });

  it('gives the scale of a result of the same statistics: the NDVI with outliers is an index', () => {
    expect(measuredRange(areaMeasureOf('K', answer(ndvi), true))).toEqual({ vmin: '-1', vmax: '1', colormap: 'rdylgn' });
    expect(measuredRange(areaMeasureOf('K', answer(ndvi), false))).toEqual({ vmin: '0', vmax: '0.91', colormap: 'viridis' });
  });

  describe('the hint', () => {
    const spec = { measure: 'M', clipToAoi: true, perScene: false } as PreviewSpec;
    const measure = (source: 'area' | 'scene' | 'fallback', exact = true) => ({ key: 'M', stats: null, unit: null, source, exact });

    it('says nothing for an exact measure over the AOI', () => {
      expect(measureHint(spec, measure('area'))).toBeNull();
      expect(previewTitle(spec, measure('area'))).toBeUndefined();
    });

    it('says the read was coarser', () => {
      expect(measureHint(spec, measure('area', false))).toBe(COARSE_MEASURE_HINT);
      expect(COARSE_MEASURE_HINT).toBe('Range measured on a coarser read; the result may differ');
    });

    it.each(['scene', 'fallback'] as const)('says the range is the first whole scene\'s for a measure of the %s with "AOI only"', (source) => {
      expect(measureHint(spec, measure(source))).toBe(SCENE_MEASURE_HINT);
      expect(SCENE_MEASURE_HINT).toBe('Range measured over the first whole scene');
    });

    it('says nothing for "Whole scene", for no measure, or for the measure of another preview', () => {
      expect(measureHint({ ...spec, clipToAoi: false }, measure('scene'))).toBeNull();
      expect(measureHint(spec, null)).toBeNull();
      expect(measureHint(spec, { ...measure('fallback'), key: 'other' })).toBeNull();
      expect(measureHint(null, measure('fallback'))).toBeNull();
    });

    it('stands below the hint of a preview drawn scene by scene', () => {
      expect(previewTitle({ ...spec, perScene: true }, measure('area', false))).toBe(`${SCENE_PREVIEW_HINT}\n${COARSE_MEASURE_HINT}`);
      expect(previewTitle({ ...spec, perScene: true }, null)).toBe(SCENE_PREVIEW_HINT);
    });
  });
});

describe('the measure of a preview (M4-19c)', () => {
  const band = { count: 900, min: -0.2, max: 0.9, percentile_2: -0.1, percentile_98: 0.8 };
  const ask = (...bands: Array<Record<string, unknown>>) =>
    measureOf('K', Object.fromEntries(bands.map((b, i) => [`b${i + 1}`, b])) as never, true);

  it('reads the numbers a colour scale is chosen from, and the unit', () => {
    expect(ask({ ...band, unit: 'm' })).toMatchObject({
      key: 'K',
      stats: { bands: [{ minimum: -0.2, maximum: 0.9, percentile2: -0.1, percentile98: 0.8 }], expression: true },
      unit: 'm',
      source: 'scene',
      exact: true,
    });
  });

  // NM4-65 part 4: the statistics are kept whole, for the percentiles typed in the fields; a band without a valid pixel has none.
  it('keeps what the statistics named of each band with a valid pixel', () => {
    expect(ask({ ...band, percentile_3: -0.15 }).raw).toEqual([expect.objectContaining({ percentile_3: -0.15 })]);
    expect(ask({ count: 0, min: null, max: null, percentile_2: null, percentile_98: null, unit: null }).raw).toEqual([]);
  });

  it('names no value of a band without a valid pixel, and no scale when no band has one', () => {
    const none = { count: 0, min: null, max: null, percentile_2: null, percentile_98: null, unit: null };
    expect(ask(none).stats).toBeNull();
    expect(measuredRange(ask(none))).toBeNull();
  });

  it('keeps the one unit all bands share, and none where they differ or are not stated', () => {
    expect(ask({ ...band, unit: 'K' }, { ...band, unit: 'K' }).unit).toBe('K');
    expect(ask({ ...band, unit: 'K' }, { ...band, unit: 'm' }).unit).toBeNull();
    expect(ask({ ...band, unit: 'K' }, { ...band, unit: null }).unit).toBeNull();
    expect(ask({ ...band }).unit).toBeNull();
    expect(ask({ ...band, unit: 4 }).unit).toBeNull();
  });

  it('turns an index into -1 to 1 in rdylgn and other values into their 2nd to 98th percentile in viridis', () => {
    expect(measuredRange(ask(band))).toEqual({ vmin: '-1', vmax: '1', colormap: 'rdylgn' });
    expect(measuredRange(ask({ ...band, min: 100, max: 2500, percentile_2: 120, percentile_98: 2400 }))).toEqual({
      vmin: '120',
      vmax: '2400',
      colormap: 'viridis',
    });
    expect(measuredRange(null)).toBeNull();
  });

  const spec = { measure: 'M' } as PreviewSpec;
  it.each([
    ['m', 'm'],
    ['1', null],
    ['', null],
    [null, null],
  ])('shows the unit %j beside the range as %j', (unit, shown) => {
    expect(previewUnit(spec, { key: 'M', stats: null, unit, source: 'scene', exact: true })).toBe(shown);
  });

  it('shows the unit of the measure of this preview and of no other', () => {
    expect(previewUnit(spec, { key: 'other', stats: null, unit: 'm', source: 'scene', exact: true })).toBeNull();
    expect(previewUnit(spec, null)).toBeNull();
    expect(previewUnit(null, { key: 'M', stats: null, unit: 'm', source: 'scene', exact: true })).toBeNull();
  });
});

describe('the pixel size of the data (F4)', () => {
  it('reads the asset, then the first band, then the item', () => {
    expect(assetGsd(item('a', { gsd: 20 }, 10), 'red')).toBe(10);
    const band = item('b', { gsd: 20 });
    band.assets.red['raster:bands'] = [{ spatial_resolution: 15 }];
    expect(assetGsd(band, 'red')).toBe(15);
    expect(assetGsd(item('c', { gsd: 20 }), 'red')).toBe(20);
    expect(assetGsd(item('d'), 'red')).toBeNull();
  });

  it('ignores a value that is no length', () => {
    for (const bad of [0, -10, Number.NaN, Number.POSITIVE_INFINITY, '10']) {
      expect(assetGsd(item('x', { gsd: bad }), 'red')).toBeNull();
    }
  });

  it('is the finest among the assets of the order, over every scene', () => {
    expect(finestGsd([item('a', { gsd: 20 }, 10), item('b', { gsd: 20 })], ['red', 'nir'], null)).toBe(10);
    expect(finestGsd([item('a')], ['red', 'nir'], null)).toBeNull();
    expect(finestGsd([], ['red'], null)).toBeNull();
  });

  it('finds the group of a Zarr variable by the separator', () => {
    const z = item('z', {});
    z.assets = { reflectance: { href: 'x.zarr', gsd: 10, bands: [{ name: 'b04' }] } };
    expect(finestGsd([z], ['reflectance:b04'], ZARR.variableSeparator)).toBe(10);
    expect(finestGsd([z], ['reflectance:b04'], null)).toBeNull();
  });
});

describe('the preview is never as fine as the data (Otto, 19.10.2026)', () => {
  const at51 = [[10, 50, 11, 51]] as [number, number, number, number][];

  it('computes metres per pixel of a Web Mercator tile of its size', () => {
    expect(tileMetres(0, 0, 256)).toBeCloseTo(156543.03392, 4);
    expect(tileMetres(0, 14, 256)).toBeCloseTo(9.5546, 3);
    expect(tileMetres(60, 14, 256)).toBeCloseTo(4.7773, 3);
    // A 512-px tile of level L has the pixels of a 256-px tile of level L + 1.
    expect(tileMetres(51, 13, 512)).toBeCloseTo(tileMetres(51, 14, 256), 6);
  });

  it('ends a 512-px preview one level lower than a 256-px one of the same data (NM4-29b)', () => {
    // 10 m at 51° N: 256-px tiles are held at level 13, and a 512-px tile of level 12 is as coarse as one of level 13.
    expect(previewMaxZoom(at51, 10, { min: 8, max: 22 }, 256)).toBe(13);
    expect(previewMaxZoom(at51, 10, { min: 8, max: 22 }, 512)).toBe(12);
    expect(tileMetres(51, 12, 512)).toBeGreaterThan(10);
    expect(tileMetres(51, 13, 512)).toBeLessThanOrEqual(10);
    // The default is the 256-px tile.
    expect(previewMaxZoom(at51, 10, { min: 8, max: 22 })).toBe(13);
  });

  it('stops at the last level whose tiles are coarser than the data, where the scene is farthest from the equator', () => {
    // 10 m at 51° N: level 13 is 12.0 m per pixel, level 14 is 6.0 m.
    expect(previewMaxZoom(at51, 10, { min: 8, max: 22 })).toBe(13);
    expect(tileMetres(51, 13, 256)).toBeGreaterThan(10);
    expect(tileMetres(51, 14, 256)).toBeLessThan(10);
    // At the equator level 13 is 19.1 m, level 14 is 9.55 m: the same level, as 9.55 < 10.
    expect(previewMaxZoom([[10, -1, 11, 1]], 10, { min: 8, max: 22 })).toBe(13);
    // 30 m (a DEM): level 12 is 38 m at the equator, level 13 is 19 m.
    expect(previewMaxZoom([[10, -1, 11, 1]], 30, { min: 0, max: 22 })).toBe(12);
  });

  it('uses a level while it is coarser than the data and not once it is as fine', () => {
    const level13 = tileMetres(0, 13, 256);
    const equator = [[10, -1, 11, 1]] as [number, number, number, number][];
    expect(previewMaxZoom(equator, level13 * 0.999, { min: 0, max: 22 })).toBe(13);
    expect(previewMaxZoom(equator, level13 * 1.001, { min: 0, max: 22 })).toBe(12);
  });

  it.each([
    ['10 m', 10, [10, 50, 11, 51]],
    ['1 m', 1, [10, 50, 11, 51]],
    ['300 m', 300, [10, 50, 11, 51]],
    ['10 m in the south', 10, [10, -52, 11, -51]],
    ['5 m near the pole', 5, [10, 78, 11, 80]],
  ] as const)('holds every tile under the pixel size at its farthest latitude (%s)', (_, gsd, bbox) => {
    const level = previewMaxZoom([bbox as unknown as [number, number, number, number]], gsd, { min: 0, max: 22 });
    const farthest = Math.max(Math.abs(bbox[1]), Math.abs(bbox[3]));
    expect(tileMetres(farthest, level, 256)).toBeGreaterThan(gsd);
    expect(tileMetres(farthest, level + 1, 256)).toBeLessThanOrEqual(gsd);
  });

  it('takes the scene farthest from the equator when there are several', () => {
    expect(previewMaxZoom([[10, 0, 11, 1], [10, 70, 11, 71]], 10, { min: 0, max: 22 })).toBe(
      previewMaxZoom([[10, 70, 11, 71]], 10, { min: 0, max: 22 }),
    );
  });

  it('keeps within the released levels', () => {
    expect(previewMaxZoom(at51, 10, { min: 8, max: 11 })).toBe(11);
    expect(previewMaxZoom(at51, 10000, { min: 8, max: 22 })).toBe(8); // coarser data than the lowest level
  });

  it('is never above the data at the pole either', () => {
    expect(previewMaxZoom([[10, 89, 11, 90]], 10, { min: 0, max: 22 })).toBeLessThanOrEqual(22);
  });
});

describe('a chain the tiler refuses', () => {
  const answer = (status: number, body: unknown) => async () =>
    new Response(typeof body === 'string' ? body : JSON.stringify(body), { status });

  it('reads the step and the reason off the detail of the tiler', () => {
    expect(refusedStepOf('step 1: expression names unknown band(s): red; the input has: band_math')).toEqual({
      step: 1,
      reason: 'expression names unknown band(s): red; the input has: band_math',
    });
    expect(refusedStepOf("step 12: 'mask' cannot run here: x\ny")).toEqual({ step: 12, reason: "'mask' cannot run here: x\ny" });
  });

  it.each([['params: expression: required'], ['step : x'], ['step 2:'], ['Step 2: x'], [' step 2: x'], [undefined], [422], [['step 2: x']], [null]])(
    'names no step in %j',
    (detail) => {
      expect(refusedStepOf(detail)).toBeNull();
    },
  );

  it('asks the TileJSON and returns what a refusal names', async () => {
    const fetchImpl = vi.fn(answer(422, { detail: 'step 1: no band red' }));
    expect(await probeChain('/tj?x=1', 2, fetchImpl as unknown as typeof fetch)).toEqual({
      state: 'refused',
      refused: { step: 1, reason: 'no band red' },
    });
    expect(fetchImpl).toHaveBeenCalledWith('/tj?x=1');
  });

  it('takes a chain the tiler takes as taken', async () => {
    expect(await probeChain('/tj', 2, answer(200, { tilejson: '3.0.0' }) as unknown as typeof fetch)).toEqual({ state: 'taken' });
  });

  it.each([
    ['a refusal of several steps without a step', 2, answer(400, { detail: 'params: x' })],
    ['a refusal of several steps whose detail is no text', 2, answer(422, { detail: [{ msg: 'x' }] })],
    ['a refusal of a single step whose detail is no text', 1, answer(422, { detail: [{ msg: 'x' }] })],
    ['a refusal of a single step without a detail', 1, answer(400, {})],
    ['a failure of the source', 2, answer(502, { detail: 'step 1: the asset could not be read' })],
    ['a failure of the source for a single step', 1, answer(502, { detail: 'the asset could not be read' })],
    ['an answer that is not JSON', 1, answer(422, 'not json')],
    ['a network that fails', 1, async () => Promise.reject(new TypeError('offline'))],
    ['a scene the source does not have', 1, answer(404, { detail: "no item 'S2B_A' in 'sentinel-2-c1-l2a'" })],
    ['a busy tiler', 1, answer(429, { detail: 'too many requests' })],
  ])('has no answer to go by for %s', async (_, steps, fetchImpl) => {
    expect(await probeChain('/tj', steps, fetchImpl as unknown as typeof fetch)).toEqual({ state: 'none' });
  });

  it('takes the text of a refusal of a single step as the reason for step 0', async () => {
    const detail = 'params: expression: Value error, expression: not a valid expression';
    expect(await probeChain('/tj', 1, answer(400, { detail }) as unknown as typeof fetch)).toEqual({
      state: 'refused',
      refused: { step: 0, reason: detail },
    });
    expect(await probeChain('/tj', 1, answer(422, { detail: 'step 0: no band red' }) as unknown as typeof fetch)).toEqual({
      state: 'refused',
      refused: { step: 0, reason: 'no band red' },
    });
  });

  it('cuts the plan to the steps before the refused one, and to none for the first', () => {
    const plan = ready([normalize(), bandMath('red', 3), normalize(7)]);
    expect(shortenPlan(plan, 2)!.steps.map((s) => s.step.key)).toEqual([5, 3]);
    expect(shortenPlan(plan, 2)!.further).toBe(true);
    expect(shortenPlan(plan, 0)).toBeNull();
  });

  it('writes the note the way the panel shows it', () => {
    const refused = { step: 1, reason: 'band red is not available after step 1' };
    expect(refusedNote(1, 2, refused)).toBe('Preview shows step 1 of 2. Step 2: band red is not available after step 1.');
    expect(refusedNote(2, 4, { step: 2, reason: 'no band.' })).toBe('Preview shows steps 1 to 2 of 4. Step 3: no band.');
    expect(refusedNote(0, 2, { step: 0, reason: 'no band' })).toBe('No preview. Step 1: no band.');
    expect(refusedNote(0, 1, { step: 0, reason: 'expression: not a valid expression' })).toBe(
      'No preview: expression: not a valid expression.',
    );
  });

  it('puts the chain into the TileJSON URL of the first scene', () => {
    const items = [item('S2_A', { gsd: 10 }), item('S2_B', { gsd: 10 })];
    const spec = previewSpec({
      dataset: DATASET,
      items,
      assets: ['red', 'nir'],
      info: S2,
      range: DEFAULT_RANGE,
      area: 'scene',
      plan: ready([normalize(), bandMath('red', 3)]),
    })!;
    expect(spec.stepCount).toBe(2);
    const url = new URL(spec.probe, 'http://localhost');
    expect(url.pathname).toBe('/collections/sentinel-2-c1-l2a/items/S2_A/WebMercatorQuad/tilejson.json');
    expect(url.searchParams.getAll('op')).toEqual(['normalize', 'band_math']);
    expect(url.searchParams.has('rescale')).toBe(false);
  });
});

// NM4-43e PR 2: the band the map shows, and what it reads for it (adr/0020 §4, §10).
describe('namesNeeded', () => {
  const named = (key: number, name: string, expression: string): DraftStep => ({
    key,
    op: 'band_math',
    opVersion: 2,
    values: { expression, name },
  });

  it('is the band itself for a band of the data', () => {
    expect([...namesNeeded([named(1, 'ndvi', '(nir - red) / (nir + red)')], 'blue')]).toEqual(['blue']);
  });

  it('is what the expression reads for a result, and not the result itself', () => {
    expect([...namesNeeded([named(1, 'ndvi', '(nir - red) / (nir + red)')], 'ndvi')].sort()).toEqual(['nir', 'red']);
  });

  it('follows a result through the results it reads, back to the data', () => {
    const steps = [named(1, 'ndvi', '(nir - red) / (nir + red)'), named(2, 'twice', 'ndvi * 2'), named(3, 'ndwi', '(green - nir) / (green + nir)')];
    expect([...namesNeeded(steps, 'twice')].sort()).toEqual(['nir', 'red']);
    expect([...namesNeeded(steps, 'ndwi')].sort()).toEqual(['green', 'nir']);
  });

  it('does not read what a step after the band reads, and knows no band of a step that comes later', () => {
    const steps = [named(1, 'a', 'red + 1'), named(2, 'b', 'a + green')];
    expect([...namesNeeded(steps, 'a')]).toEqual(['red']);
  });

  it('reads the band a mask by value looks at, whichever band is shown', () => {
    const mask = (key: number, band: string): DraftStep => ({ key, op: 'mask_values', opVersion: 1, values: { band, condition: 'lt', values: '0.2' } });
    expect([...namesNeeded([mask(1, 'red')], 'blue')].sort()).toEqual(['blue', 'red']);
    // A result it looks at is read through its expression; one that comes after the mask is no concern of it.
    const steps = [named(1, 'ndvi', '(nir - red) / (nir + red)'), mask(2, 'ndvi')];
    expect([...namesNeeded(steps, 'blue')].sort()).toEqual(['blue', 'nir', 'red']);
    expect([...namesNeeded([mask(1, 'scl'), named(2, 'a', 'red + 1')], 'a')].sort()).toEqual(['red', 'scl']);
    expect([...namesNeeded([mask(1, '')], 'blue')]).toEqual(['blue']);
  });

  it('keeps the bands a normalize or a reproject is given', () => {
    const steps = [named(1, 'ndvi', 'nir - red'), normalize(2, { bands: 'ndvi' }), reproject()];
    expect([...namesNeeded(steps, 'ndvi')].sort()).toEqual(['nir', 'red']);
  });
});

describe('previewRead', () => {
  const source = (asset: string, names = [asset]): BandSource => ({
    asset,
    names,
    units: names.map(() => null),
    unit: null,
    dataType: 'uint16',
    scaled: false,
    nodata: null,
  });
  const sources = ['blue', 'green', 'red', 'nir', 'scl'].map((asset) => source(asset));
  const dataNames = sources.map((s) => s.asset);
  const first = (key: number, name: string, expression: string): DraftStep => ({ key, op: 'band_math', opVersion: 2, values: { expression, name } });
  const read = (over: Partial<Parameters<typeof previewRead>[0]>) =>
    previewRead({
      output: ['ndvi'],
      dataNames,
      sources,
      maskAsset: null,
      all: ['everything'],
      steps: [first(1, 'ndvi', '(nir - red) / (nir + red)')],
      pick: null,
      trueColor: null,
      ...over,
    });

  it('shows the result of the only step and reads its two assets, in the order of the item', () => {
    expect(read({})).toEqual({ choices: ['ndvi'], band: 'ndvi', bands: ['ndvi'], assets: ['red', 'nir'] });
  });

  it('lists the results above the bands of the data, as the output holds them', () => {
    const steps = [first(1, 'ndvi', '(nir - red) / (nir + red)'), first(2, 'ndwi', '(green - nir) / (green + nir)')];
    expect(read({ output: ['ndvi', 'ndwi', 'blue', 'red'], steps }).choices).toEqual(['ndvi', 'ndwi', 'blue', 'red']);
  });

  it('shows the result created last, not the last of the chain', () => {
    // The step with key 2 was created after the step with key 1, then moved in front of it.
    const steps = [first(2, 'ndwi', '(green - nir) / (green + nir)'), first(1, 'ndvi', '(nir - red) / (nir + red)')];
    const output = ['ndwi', 'ndvi', 'blue'];
    expect(read({ output, steps }).band).toBe('ndwi');
  });

  it('shows the first band of the output where no result is in it', () => {
    expect(read({ output: ['green', 'red'], steps: [first(1, 'ndvi', 'nir - red')] })).toMatchObject({
      choices: ['green', 'red'],
      band: 'green',
      assets: ['green'],
    });
  });

  it('shows a result of a step in the output only', () => {
    const steps = [first(1, 'ndvi', 'nir - red'), first(2, 'ndwi', 'green - nir')];
    expect(read({ output: ['ndvi', 'blue'], steps })).toMatchObject({ choices: ['ndvi', 'blue'], band: 'ndvi' });
  });

  it('shows the pick while it is a choice, and the default when it is not', () => {
    const steps = [first(1, 'ndvi', 'nir - red')];
    expect(read({ output: ['ndvi', 'blue'], steps, pick: 'blue' })).toMatchObject({ band: 'blue', assets: ['blue'] });
    expect(read({ output: ['ndvi', 'blue'], steps, pick: 'green' })).toMatchObject({ band: 'ndvi' });
    expect(read({ output: ['ndvi'], steps, pick: 'blue' })).toMatchObject({ band: 'ndvi' });
  });

  it('does not offer a result of a step the map does not draw, nor a band the data does not have', () => {
    const steps = [first(1, 'ndvi', 'nir - red')];
    expect(read({ output: ['ndvi', 'later', 'blue', 'ghost'], steps }).choices).toEqual(['ndvi', 'blue']);
  });

  it('adds the layer of a mask step to what is read, for any band, and leaves it out without one', () => {
    const steps = [{ key: 1, op: 'mask', opVersion: 2, values: { source: 'scl', classes: '3' } }, first(2, 'ndvi', 'nir - red')];
    expect(read({ steps, maskAsset: 'scl' }).assets).toEqual(['red', 'nir', 'scl']);
    expect(read({ steps, output: ['blue'], maskAsset: 'scl' }).assets).toEqual(['blue', 'scl']);
    expect(read({ steps: [first(2, 'ndvi', 'nir - red')], maskAsset: null }).assets).toEqual(['red', 'nir']);
  });

  it('reads the assets of the order where the output is empty, and shows no band', () => {
    expect(read({ output: [] })).toEqual({ choices: [], band: null, bands: [], assets: ['everything'] });
  });

  it('reads only the assets of the band from a wide output', () => {
    const wide = Array.from({ length: 20 }, (_, i) => `b${i}`);
    const many = [...sources, ...wide.map((asset) => source(asset))];
    const steps = [first(1, 'ndvi', '(nir - red) / (nir + red)')];
    const found = read({ output: ['ndvi', ...wide], dataNames: many.map((s) => s.asset), sources: many, steps });
    expect(found.choices).toHaveLength(21);
    expect(found.assets).toEqual(['red', 'nir']);
  });

  it('reads an asset that carries several bands once', () => {
    const visual = source('visual', ['visual_1', 'visual_2', 'visual_3']);
    expect(read({ output: ['visual_2'], dataNames: ['visual_1', 'visual_2', 'visual_3'], sources: [visual], steps: [] })).toMatchObject({
      band: 'visual_2',
      assets: ['visual'],
    });
  });
});

describe('previewSpec: the band shown (NM4-43e PR 2)', () => {
  const items = [item('S2_A', { gsd: 10 }), item('S2_B', { gsd: 10 })];
  const base = { dataset: DATASET, items, assets: ['red', 'nir'], info: S2, range: DEFAULT_RANGE, area: 'scene' as const };
  const plan = ready([bandMath('(nir - red) / (nir + red)')]);

  it('puts the band in every address of the picture: tiles, TileJSON and statistics', () => {
    const spec = previewSpec({ ...base, plan, band: 'Band_Math_1' })!;
    for (const url of [spec.scenes[0].url, spec.probe, spec.sceneMeasure]) {
      expect(new URL(url, 'http://localhost').searchParams.getAll('band')).toEqual(['Band_Math_1']);
    }
    expect(spec.band).toBe('Band_Math_1');
  });

  it('puts it in the address of a mosaic as well', () => {
    const jobs = [items];
    const spec = previewSpec({ ...base, plan, band: 'Band_Math_1', jobs })!;
    expect(spec.mosaics).toHaveLength(1);
    for (const url of [spec.mosaics[0].url, spec.mosaics[0].probe]) {
      expect(new URL(url, 'http://localhost').searchParams.getAll('band')).toEqual(['Band_Math_1']);
    }
  });

  it('writes a name with signs that mean something in an address so that it arrives whole', () => {
    const spec = previewSpec({ ...base, plan, band: 'SR_10m:b04&x=1 #' })!;
    const url = new URL(spec.scenes[0].url, 'http://localhost');
    expect(url.searchParams.getAll('band')).toEqual(['SR_10m:b04&x=1 #']);
    expect(url.searchParams.has('x')).toBe(false);
    expect(spec.scenes[0].url).not.toContain(' #');
  });

  it('names no band where none is chosen', () => {
    const spec = previewSpec({ ...base, plan })!;
    expect(spec.band).toBeNull();
    expect(spec.scenes[0].url).not.toContain('band=');
  });

  it('judges the values as an index only for a result of Band math', () => {
    expect(previewSpec({ ...base, plan, band: 'Band_Math_1' })!.expression).toBe(true);
    expect(previewSpec({ ...base, plan, band: 'red' })!.expression).toBe(false);
    expect(previewSpec({ ...base, plan })!.expression).toBe(true);
  });

  it('has a measure of its own per band, also over the AOI, and one text for the same band', () => {
    const order = { recipe_version: 2, steps: [], output: { bands: ['x'] } } as unknown as Order;
    const over = { ...base, plan, area: 'aoi' as const, order };
    const a = previewSpec({ ...over, band: 'Band_Math_1' })!;
    const b = previewSpec({ ...over, band: 'red' })!;
    expect(a.measure).not.toBe(b.measure);
    expect(a.sceneMeasure).not.toBe(b.sceneMeasure);
    expect(previewSpec({ ...over, band: 'red' })!.measure).toBe(b.measure);
  });

  it('names the picture after the band where the output has several', () => {
    expect(previewSpec({ ...base, plan, band: 'Band_Math_1' })!.title).toBe('Band math');
    expect(previewSpec({ ...base, plan, band: 'Band_Math_1', named: true })!.title).toBe('Band math · Band_Math_1');
  });

  it('reads no more than the limit of the tile in the assets it is given', () => {
    const wide = Array.from({ length: 17 }, (_, i) => `b${i}`);
    expect(previewSpec({ ...base, plan, assets: wide })).toBeNull();
    expect(previewSpec({ ...base, plan, assets: ['red', 'nir'], band: 'Band_Math_1' })).not.toBeNull();
  });
});

describe('previewRead: the colour picture (NM4-64)', () => {
  const source = (asset: string): BandSource => ({
    asset,
    names: [asset],
    units: [null],
    unit: null,
    dataType: 'uint16',
    scaled: false,
    nodata: null,
  });
  const sources = ['blue', 'green', 'red', 'nir', 'scl'].map(source);
  const dataNames = sources.map((s) => s.asset);
  const ndvi: DraftStep = { key: 1, op: 'band_math', opVersion: 2, values: { expression: '(nir - red) / (nir + red)', name: 'ndvi' } };
  const read = (over: Partial<Parameters<typeof previewRead>[0]>) =>
    previewRead({
      output: ['blue', 'green', 'red', 'nir'],
      dataNames,
      sources,
      maskAsset: null,
      all: ['everything'],
      steps: [ndvi],
      pick: null,
      trueColor: ['red', 'green', 'blue'],
      ...over,
    });

  it('puts RGB on top and shows it where the output has no result of a step', () => {
    expect(read({})).toEqual({
      choices: [RGB, 'blue', 'green', 'red', 'nir'],
      band: RGB,
      bands: ['red', 'green', 'blue'],
      assets: ['blue', 'green', 'red'],
    });
  });

  it('shows the result created last, not RGB, where the output has one', () => {
    const found = read({ output: ['ndvi', 'blue', 'green', 'red'] });
    expect(found.choices).toEqual([RGB, 'ndvi', 'blue', 'green', 'red']);
    expect(found).toMatchObject({ band: 'ndvi', bands: ['ndvi'], assets: ['red', 'nir'] });
  });

  it('shows RGB where a result of a step is not in the output', () => {
    expect(read({ output: ['blue', 'green', 'red'] }).band).toBe(RGB);
  });

  it('offers RGB only where all three bands are in the output', () => {
    for (const output of [['red', 'green'], ['red', 'green', 'nir'], ['blue']]) {
      const found = read({ output });
      expect(found.choices).not.toContain(RGB);
      expect(found.band).not.toBe(RGB);
    }
  });

  it('offers RGB only where the dataset has a colour picture', () => {
    const found = read({ trueColor: null });
    expect(found.choices).toEqual(['blue', 'green', 'red', 'nir']);
    expect(found.band).toBe('blue');
  });

  it('does not offer RGB for a registry that names bands the data does not have', () => {
    expect(read({ trueColor: ['red', 'green', 'ghost'] }).choices).not.toContain(RGB);
    expect(read({ trueColor: ['red', 'green'] }).choices).not.toContain(RGB);
  });

  it('keeps the pick while it is RGB, and the default when RGB is no choice any more', () => {
    expect(read({ output: ['ndvi', 'blue', 'green', 'red'], pick: RGB })).toMatchObject({ band: RGB, assets: ['blue', 'green', 'red'] });
    expect(read({ output: ['ndvi', 'blue', 'green'], pick: RGB })).toMatchObject({ band: 'ndvi' });
  });

  it('reads the assets the three bands need, and the layer of a mask step, in the order of the item', () => {
    const mask = { key: 2, op: 'mask', opVersion: 2, values: { source: 'scl', classes: '3' } };
    expect(read({ steps: [mask, ndvi], maskAsset: 'scl' }).assets).toEqual(['blue', 'green', 'red', 'scl']);
  });

  it('shows the first band of an empty output as before: none', () => {
    expect(read({ output: [] })).toMatchObject({ choices: [], band: null, bands: [] });
  });
});

describe('previewSpec: the colour picture (NM4-64)', () => {
  const items = [item('S2_A', { gsd: 10 }), item('S2_B', { gsd: 10 })];
  const base = {
    dataset: DATASET,
    items,
    assets: ['blue', 'green', 'red'],
    info: S2,
    range: { vmin: '0', vmax: '0.3', colormap: 'viridis' },
    area: 'scene' as const,
    plan: ready([bandMath('(nir - red) / (nir + red)')]),
    band: RGB,
    bands: ['red', 'green', 'blue'],
    named: true,
  };
  const query = (url: string) => new URL(url, 'http://localhost').searchParams;

  it('asks the tile for the three bands in order, with one range and no colormap', () => {
    const spec = previewSpec(base)!;
    const params = query(spec.scenes[0].url);
    expect(params.getAll('band')).toEqual(['red', 'green', 'blue']);
    expect(params.getAll('rescale')).toEqual(['0,0.3']);
    expect(params.has('colormap_name')).toBe(false);
    expect(spec).toMatchObject({ band: RGB, bands: ['red', 'green', 'blue'], expression: false });
  });

  it('names the preview RGB where the output has more bands', () => {
    expect(previewSpec(base)!.title).toBe('Band math · RGB');
  });

  it('asks the TileJSON and the statistics for the same three bands', () => {
    const spec = previewSpec(base)!;
    expect(query(spec.probe).getAll('band')).toEqual(['red', 'green', 'blue']);
    expect(query(spec.sceneMeasure).getAll('band')).toEqual(['red', 'green', 'blue']);
    expect(query(spec.sceneMeasure).has('colormap_name')).toBe(false);
  });

  it('has a key and a measure of its own, apart from the band that is called red', () => {
    const rgb = previewSpec(base)!;
    const red = previewSpec({ ...base, band: 'red', bands: ['red'], assets: ['red'] })!;
    expect(rgb.key).not.toBe(red.key);
    expect(rgb.measure).not.toBe(red.measure);
  });

  it('asks the mosaic for the three bands as well', () => {
    const spec = previewSpec({ ...base, jobs: [items] })!;
    expect(spec.mosaics).toHaveLength(1);
    expect(query(spec.mosaics[0].url).getAll('band')).toEqual(['red', 'green', 'blue']);
    expect(query(spec.mosaics[0].url).has('colormap_name')).toBe(false);
    expect(query(spec.mosaics[0].probe).getAll('band')).toEqual(['red', 'green', 'blue']);
  });

  it('draws no picture for RGB without its three bands', () => {
    expect(previewSpec({ ...base, bands: ['red', 'green'] })).toBeNull();
    expect(previewSpec({ ...base, bands: undefined })).toBeNull();
  });

  it('still draws one band with its colormap', () => {
    const params = query(previewSpec({ ...base, band: 'red', bands: ['red'], assets: ['red'] })!.scenes[0].url);
    expect(params.getAll('band')).toEqual(['red']);
    expect(params.get('colormap_name')).toBe('viridis');
  });
});
