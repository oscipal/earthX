import { describe, expect, it, vi } from 'vitest';

import { AOI_CLIP_PROTOCOL } from './aoiClip';
import type { DatasetOption } from './datasets';
import s2 from './fixtures/processes/sentinel-2-c1-l2a.json';
import zarr from './fixtures/processes/sentinel-2-l2a-zarr3.json';
import { bboxToPolygon } from './geoUtils';
import type { ProcessDescription } from './processing';
import { processInfo, type DraftStep, type ProcessInfo } from './processingOrder';
import {
  assetGsd,
  DEFAULT_RANGE,
  finestGsd,
  furtherNote,
  MAX_PREVIEW_SCENES,
  MAX_PREVIEW_STEPS,
  previewMaxZoom,
  NO_PREVIEW,
  NO_PREVIEW_FORM,
  NO_PREVIEW_UNLISTED,
  planPreview,
  previewOverlays,
  probeChain,
  refusedNote,
  refusedStepOf,
  shortenPlan,
  previewSpec,
  rescaleOf,
  tileResolution,
  type PreviewPlan,
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
  return { key: 2, op: 'reproject', opVersion: 3, values: { crs: 'EPSG:3035', resolution: '30' } };
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
    expect(await probeChain('/tj?x=1', fetchImpl as unknown as typeof fetch)).toEqual({ step: 1, reason: 'no band red' });
    expect(fetchImpl).toHaveBeenCalledWith('/tj?x=1');
  });

  it.each([
    ['a chain the tiler takes', answer(200, { tilejson: '3.0.0' })],
    ['a refusal without a step', answer(400, { detail: 'params: x' })],
    ['a failure of the source', answer(502, { detail: 'step 1: the asset could not be read' })],
    ['an answer that is not JSON', answer(422, 'not json')],
    ['a network that fails', async () => Promise.reject(new TypeError('offline'))],
  ])('names no step for %s', async (_, fetchImpl) => {
    expect(await probeChain('/tj', fetchImpl as unknown as typeof fetch)).toBeNull();
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
