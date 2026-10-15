import { describe, expect, it } from 'vitest';

import { AOI_CLIP_PROTOCOL } from './aoiClip';
import type { DatasetOption } from './datasets';
import s2 from './fixtures/processes/sentinel-2-c1-l2a.json';
import zarr from './fixtures/processes/sentinel-2-l2a-zarr3.json';
import { bboxToPolygon } from './geoUtils';
import type { ProcessDescription } from './processing';
import { processInfo, type DraftStep } from './processingOrder';
import {
  assetGsd,
  DEFAULT_RANGE,
  finestGsd,
  isCoarserThanData,
  MAX_PREVIEW_SCENES,
  NO_PREVIEW,
  planPreview,
  previewOverlays,
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

function reproject(): DraftStep {
  return { key: 2, op: 'reproject', opVersion: 2, values: { crs: 'EPSG:3035', resolution: '30' } };
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
    expect(plan.params).toEqual({ expression: '(nir - red) / (nir + red)' });
    expect(plan.operator.op).toBe('band_math');
    expect(plan.further).toBe(false);
  });

  it('waits for a complete step instead of asking the tiler for a half one', () => {
    expect(planPreview([bandMath('')], S2)).toEqual({ state: 'off', reason: 'Complete the step to see the preview.' });
  });

  it('has no preview when the first step runs only as a job, even if a later one would tile', () => {
    expect(planPreview([reproject()], S2)).toEqual({ state: 'off', reason: NO_PREVIEW });
    expect(planPreview([reproject(), bandMath('red')], S2)).toEqual({ state: 'off', reason: NO_PREVIEW });
  });

  it('shows only the first of several steps and says there are more', () => {
    const plan = ready([bandMath('red + nir'), bandMath('red', 3), reproject()]);
    expect(plan.params).toEqual({ expression: 'red + nir' });
    expect(plan.further).toBe(true);
  });

  it('has no preview for an operator the dataset does not list', () => {
    const stranger: DraftStep = { key: 9, op: 'decomp', opVersion: 1, values: {} };
    expect(planPreview([stranger], S2)).toEqual({ state: 'off', reason: NO_PREVIEW });
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
    expect(spec).toMatchObject({ title: 'Band math', minZoom: 8, maxZoom: 14, gsd: 10, clipToAoi: false });
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

  it('marks its overlays as a preview with the pixel size of the data', () => {
    const spec = previewSpec({ ...base, plan: ready([bandMath('red')]) })!;
    expect(previewOverlays(spec, null)[0]).toMatchObject({ kind: 'raster', bounds: [10, 50, 11, 51], preview: { gsd: 10 } });
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

  it('takes the scenes without a footprint out and no more than the full-resolution view draws', () => {
    const plan = ready([bandMath('red')]);
    const many = Array.from({ length: MAX_PREVIEW_SCENES + 5 }, (_, i) => item(`S${i}`));
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

describe('"Preview" while a tile is coarser than the data (F4 (1))', () => {
  const equator = [10, -1, 11, 1] as [number, number, number, number];
  const at48 = [10, 47, 11, 49] as [number, number, number, number];

  it('computes metres per pixel of a 256-pixel Web Mercator tile', () => {
    expect(tileResolution(0, 0)).toBeCloseTo(156543.03392, 4);
    expect(tileResolution(0, 14)).toBeCloseTo(9.5546, 3);
    expect(tileResolution(60, 14)).toBeCloseTo(4.7773, 3);
  });

  it('is on until the tile level reaches the data, at the equator', () => {
    // 10 m: level 13 is 19.1 m per pixel, level 14 is 9.55 m.
    expect(isCoarserThanData({ mapZoom: 12.4, viewport: equator, maxZoom: 14, gsd: 10 })).toBe(true);
    expect(isCoarserThanData({ mapZoom: 12.5, viewport: equator, maxZoom: 14, gsd: 10 })).toBe(false);
  });

  it('measures at the latitude of the view nearest to the equator, where tiles are coarsest', () => {
    // 47° N: level 13 is 13.0 m, level 14 is 6.5 m.
    expect(isCoarserThanData({ mapZoom: 12.4, viewport: at48, maxZoom: 14, gsd: 10 })).toBe(true);
    expect(isCoarserThanData({ mapZoom: 12.5, viewport: at48, maxZoom: 14, gsd: 10 })).toBe(false);
    // A view across the equator counts as the equator, however far north it reaches.
    expect(isCoarserThanData({ mapZoom: 12.5, viewport: [10, -1, 11, 60], maxZoom: 14, gsd: 10 })).toBe(false);
    expect(isCoarserThanData({ mapZoom: 12.4, viewport: [10, -1, 11, 60], maxZoom: 14, gsd: 10 })).toBe(true);
    // The southern view is as far from the equator as the northern one.
    expect(isCoarserThanData({ mapZoom: 12.5, viewport: [10, -49, 11, -47], maxZoom: 14, gsd: 10 })).toBe(false);
  });

  it('is on at 60° N where it would be off at the equator, for a finer pixel size', () => {
    // 5 m data: level 14 is 4.78 m at 60° N, 9.55 m at the equator.
    expect(isCoarserThanData({ mapZoom: 13, viewport: [10, 60, 11, 61], maxZoom: 14, gsd: 5 })).toBe(false);
    expect(isCoarserThanData({ mapZoom: 13, viewport: equator, maxZoom: 14, gsd: 5 })).toBe(true);
  });

  it('never asks for a level beyond the last released one', () => {
    expect(isCoarserThanData({ mapZoom: 20, viewport: equator, maxZoom: 12, gsd: 10 })).toBe(true);
    expect(isCoarserThanData({ mapZoom: 20, viewport: equator, maxZoom: 14, gsd: 10 })).toBe(false);
  });

  it('is always on without a pixel size, and takes the equator without a view', () => {
    expect(isCoarserThanData({ mapZoom: 22, viewport: at48, maxZoom: 22, gsd: null })).toBe(true);
    expect(isCoarserThanData({ mapZoom: 12.5, viewport: null, maxZoom: 14, gsd: 10 })).toBe(false);
  });
});
