import { describe, expect, it, vi } from 'vitest';

import { AOI_CLIP_PROTOCOL } from './aoiClip';
import type { DatasetOption } from './datasets';
import s2 from './fixtures/processes/sentinel-2-c1-l2a.json';
import zarr from './fixtures/processes/synthetic-zarr.json';
import { bboxToPolygon } from './geoUtils';
import type { ProcessDescription } from './processing';
import { MAX_MOSAIC_OPERATOR_ASSETS, MAX_MOSAIC_REQUEST_BYTES, MAX_MOSAIC_SCENES, mosaicRequestBytes } from './mosaic';
import { processInfo, type DraftStep, type ProcessInfo } from './processingOrder';
import {
  assetGsd,
  DEFAULT_RANGE,
  finestGsd,
  furtherNote,
  MAX_PREVIEW_SCENES,
  MAX_PREVIEW_STEPS,
  probeMosaic,
  SCENE_PREVIEW_HINT,
  type MosaicAnswer,
  previewMaxZoom,
  NO_PREVIEW,
  NO_PREVIEW_FORM,
  NO_PREVIEW_UNLISTED,
  measuredRange,
  measureOf,
  planPreview,
  previewOverlays,
  previewUnit,
  probeChain,
  refusedNote,
  refusedStepOf,
  shortenPlan,
  previewSpec,
  rescaleOf,
  tileResolution,
  type PreviewPlan,
  type PreviewSpec,
} from './processingPreview';
import type { Collection, StacItem } from './types';

const S2 = processInfo(s2 as unknown as ProcessDescription);
const ZARR = processInfo(zarr as unknown as ProcessDescription);

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';

function bandMath(expression: string, key = 1): DraftStep {
  return { key, op: 'band_math', opVersion: 1, values: { expression } };
}

function normalize(key = 5, values: Record<string, string | boolean> = {}): DraftStep {
  return {
    key,
    op: 'normalize',
    opVersion: 1,
    values: { in_min: '0', in_max: '0.5', out_min: '0', out_max: '255', clip: true, ...values },
  };
}

function mask(key = 6, values: Record<string, string | boolean> = {}): DraftStep {
  return { key, op: 'mask', opVersion: 1, values: { source: 'scl', classes: '3, 8, 9, 10', ...values } };
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
    expect(plan.steps[0].params).toEqual({ expression: '(nir - red) / (nir + red)' });
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
    expect(plan.steps[1].params).toEqual({ in_min: 0, in_max: 0.5, out_min: 0, out_max: 255, clip: true });
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
    expect(planPreview([{ ...mask(), opVersion: 2 }], S2)).toEqual({ state: 'off', reason: NO_PREVIEW_UNLISTED });
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
    expect(url.searchParams.get('op_version')).toBe('1');
    expect(url.searchParams.get('params')).toBe('{"expression":"(nir - red) / (nir + red)"}');
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
    expect(url.searchParams.getAll('op_version')).toEqual(['1', '1']);
    expect(url.searchParams.getAll('params')).toEqual([
      '{"clip":true,"in_max":0.5,"in_min":0,"out_max":255,"out_min":0}',
      '{"expression":"red / 2"}',
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
    expect(JSON.parse(new URL(template, 'http://localhost').searchParams.get('params')!)).toEqual({ expression });
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
    expect(tileResolution(51, spec.maxZoom)).toBeGreaterThan(10);
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
    expect(url.searchParams.getAll('op_version')).toEqual(['1']);
    expect(url.searchParams.get('params')).toBe('{"expression":"(nir - red) / (nir + red)"}');
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
    const known = new Set(['item', 'asset', 'op', 'op_version', 'params', 'rescale', 'colormap_name']);
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
    expect(overlays[0]).toMatchObject({ minZoom: 8, maxZoom: 13, preview: true });
    expect(overlays[0]).not.toHaveProperty('hideFrom');
    expect(overlays.slice(1).map((o) => o.kind === 'raster' && [o.minZoom, o.maxZoom, o.hideFrom])).toEqual(
      Array(4).fill([5, 7, 6.5]),
    );
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

describe('the measure of a preview (M4-19c)', () => {
  const band = { count: 900, min: -0.2, max: 0.9, percentile_2: -0.1, percentile_98: 0.8 };
  const ask = (...bands: Array<Record<string, unknown>>) =>
    measureOf('K', Object.fromEntries(bands.map((b, i) => [`b${i + 1}`, b])) as never, true);

  it('reads the numbers a colour scale is chosen from, and the unit', () => {
    expect(ask({ ...band, unit: 'm' })).toEqual({
      key: 'K',
      stats: { bands: [{ minimum: -0.2, maximum: 0.9, percentile2: -0.1, percentile98: 0.8 }], expression: true },
      unit: 'm',
    });
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
    expect(previewUnit(spec, { key: 'M', stats: null, unit })).toBe(shown);
  });

  it('shows the unit of the measure of this preview and of no other', () => {
    expect(previewUnit(spec, { key: 'other', stats: null, unit: 'm' })).toBeNull();
    expect(previewUnit(spec, null)).toBeNull();
    expect(previewUnit(null, { key: 'M', stats: null, unit: 'm' })).toBeNull();
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

  it('computes metres per pixel of a 256-pixel Web Mercator tile', () => {
    expect(tileResolution(0, 0)).toBeCloseTo(156543.03392, 4);
    expect(tileResolution(0, 14)).toBeCloseTo(9.5546, 3);
    expect(tileResolution(60, 14)).toBeCloseTo(4.7773, 3);
  });

  it('stops at the last level whose tiles are coarser than the data, where the scene is farthest from the equator', () => {
    // 10 m at 51° N: level 13 is 12.0 m per pixel, level 14 is 6.0 m.
    expect(previewMaxZoom(at51, 10, { min: 8, max: 22 })).toBe(13);
    expect(tileResolution(51, 13)).toBeGreaterThan(10);
    expect(tileResolution(51, 14)).toBeLessThan(10);
    // At the equator level 13 is 19.1 m, level 14 is 9.55 m: the same level, as 9.55 < 10.
    expect(previewMaxZoom([[10, -1, 11, 1]], 10, { min: 8, max: 22 })).toBe(13);
    // 30 m (a DEM): level 12 is 38 m at the equator, level 13 is 19 m.
    expect(previewMaxZoom([[10, -1, 11, 1]], 30, { min: 0, max: 22 })).toBe(12);
  });

  it('uses a level while it is coarser than the data and not once it is as fine', () => {
    const level13 = tileResolution(0, 13);
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
    expect(tileResolution(farthest, level)).toBeGreaterThan(gsd);
    expect(tileResolution(farthest, level + 1)).toBeLessThanOrEqual(gsd);
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
