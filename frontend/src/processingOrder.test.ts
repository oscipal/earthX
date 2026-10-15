import { describe, expect, it } from 'vitest';

import cop from './fixtures/processes/cop-dem-glo-30.json';
import s2 from './fixtures/processes/sentinel-2-c1-l2a.json';
import zarr from './fixtures/processes/sentinel-2-l2a-zarr3.json';
import { bboxToPolygon, bufferPointToPolygon } from './geoUtils';
import type { ProcessDescription } from './processing';
import {
  bandSources,
  buildMosaicOrder,
  buildOrder,
  candidateItems,
  formatBytes,
  formatDuration,
  namesInExpression,
  orderAssets,
  passesOf,
  processBlockReason,
  processInfo,
  stepOfRefusal,
  type DraftStep,
} from './processingOrder';
import type { Collection, StacItem, TimeStepGroup } from './types';

const S2 = processInfo(s2 as unknown as ProcessDescription);
const ZARR = processInfo(zarr as unknown as ProcessDescription);
const DEM = processInfo(cop as unknown as ProcessDescription);

function item(id: string, assets: StacItem['assets'], bbox: [number, number, number, number] = [10, 50, 11, 51]): StacItem {
  return { id, bbox, geometry: bboxToPolygon(bbox), properties: {}, assets };
}

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';

describe('processInfo from the fixtures (K3)', () => {
  it('lists the operators with tiers and kind, and the limits of the order', () => {
    expect(S2.operators.map((o) => [o.op, o.opVersion, o.tiers, o.kind])).toEqual([
      ['band_math', 1, ['T1', 'T2'], 'pixel'],
      ['reproject', 2, ['T2'], 'grid'],
    ]);
    expect(S2).toMatchObject({ maxSteps: 16, maxAssets: 16, variableSeparator: null });
    expect(S2.dtypes).toContain('float32');
  });

  it('reads the Zarr variable separator only where the dataset has one (F9)', () => {
    expect(ZARR.variableSeparator).toBe(':');
    expect(DEM.variableSeparator).toBeNull();
  });

  it.each([
    ['sentinel-2-c1-l2a', S2],
    ['sentinel-2-l2a-zarr3', ZARR],
    ['cop-dem-glo-30', DEM],
  ])('%s: every operator has a form the panel supports', (_, info) => {
    expect(info.operators.length).toBeGreaterThan(0);
    for (const operator of info.operators) expect(operator.form, operator.op).toMatchObject({ supported: true });
  });

  it('leaves out a step variant it cannot read instead of guessing', () => {
    const broken = structuredClone(s2) as unknown as ProcessDescription;
    const schema = broken.inputs.recipe.schema as { $defs: Record<string, { properties: Record<string, unknown> }> };
    delete schema.$defs.step_reproject_v2.properties.op;
    expect(processInfo(broken).operators.map((o) => o.op)).toEqual(['band_math']);
  });
});

describe('bandSources (K7)', () => {
  it('names a one-band COG asset like the asset', () => {
    const it1 = item('a', {
      red: { href: 'x', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
      thumbnail: { href: 'y', type: 'image/jpeg', roles: ['thumbnail'] },
    });
    expect(bandSources(it1, 'cog', null)).toEqual([
      { asset: 'red', names: ['red'], dataType: 'uint16', scaled: false, nodata: null },
    ]);
  });

  it('names the bands of a multi-band COG asset <asset>_1 … from raster:bands or bands', () => {
    const it1 = item('a', {
      visual: { href: 'x', type: COG, bands: [{}, {}, {}] },
    });
    expect(bandSources(it1, 'cog', null)[0].names).toEqual(['visual_1', 'visual_2', 'visual_3']);
  });

  it('reads bands where raster:bands is there but empty, as the backend does', () => {
    const it1 = item('a', { visual: { href: 'x', type: COG, 'raster:bands': [], bands: [{ data_type: 'uint8' }, {}] } });
    expect(bandSources(it1, 'cog', null)[0]).toMatchObject({ asset: 'visual', names: ['visual_1', 'visual_2'], dataType: 'uint8' });
  });

  it('reads what the item says about scaling and nodata', () => {
    const it1 = item('a', {
      // as the real Sentinel-2 item has it: scaled, with a nodata value
      red: { href: 'x', type: COG, 'raster:bands': [{ data_type: 'uint16', nodata: 0, scale: 0.0001, offset: -0.1 }] },
      // no scaling, a nodata value
      scl: { href: 'x', type: COG, 'raster:bands': [{ data_type: 'uint8', nodata: 0 }] },
      // a multiband asset with one nodata value in one band only
      multi: { href: 'x', type: COG, bands: [{ data_type: 'uint8', nodata: 255 }, {}] },
      // two bands that disagree on nodata
      odd: { href: 'x', type: COG, bands: [{ nodata: 0 }, { nodata: 1 }] },
      // nodata NaN is no value an integer type can hold
      flt: { href: 'x', type: COG, bands: [{ data_type: 'float32', nodata: 'nan' }] },
    });
    const by = Object.fromEntries(bandSources(it1, 'cog', null).map((b) => [b.asset, b]));
    expect(by.red).toMatchObject({ scaled: true, nodata: 0 });
    expect(by.scl).toMatchObject({ scaled: false, nodata: 0 });
    expect(by.multi.nodata).toBeNull();
    expect(by.odd.nodata).toBeNull();
    expect(by.flt.nodata).toBeNull();
  });

  it('offers a COG asset without band descriptions with no name to insert', () => {
    const dem = item('d', { data: { href: 'x', type: 'image/tiff; application=geotiff' } });
    expect(bandSources(dem, 'cog', null)).toEqual([
      { asset: 'data', names: [], dataType: null, scaled: false, nodata: null },
    ]);
  });

  it('names Zarr variables from the core field bands, one order asset per variable', () => {
    const z = item('z', {
      SR_10m: { href: 'x', type: 'application/vnd+zarr', bands: [{ name: 'b04' }, { name: 'b08' }] },
      product: { href: 'y', type: 'application/vnd+zarr' },
    });
    expect(bandSources(z, 'zarr', ':')).toEqual([
      { asset: 'SR_10m:b04', names: ['b04'], dataType: null, scaled: false, nodata: null },
      { asset: 'SR_10m:b08', names: ['b08'], dataType: null, scaled: false, nodata: null },
    ]);
  });

  it('offers nothing for Zarr without a separator', () => {
    const z = item('z', { SR_10m: { href: 'x', bands: [{ name: 'b04' }] } });
    expect(bandSources(z, 'zarr', null)).toEqual([]);
  });

  it('offers nothing for a Zarr asset that lists no band names, also if an extension field names them', () => {
    const z = item('z', {
      SR_10m: { href: 'x', 'eo:bands': [{ name: 'b04' }] } as never,
      SR_20m: { href: 'y', bands: [{}, { name: '' }] },
    });
    expect(bandSources(z, 'zarr', ':')).toEqual([]);
  });
});

describe('the assets of the order', () => {
  const plain = { dataType: null, scaled: false, nodata: null };
  const sources = [
    { asset: 'red', names: ['red'], ...plain },
    { asset: 'nir', names: ['nir'], ...plain },
    { asset: 'scl', names: ['scl'], ...plain },
    { asset: 'A:b04', names: ['b04'], ...plain },
    { asset: 'B:b04', names: ['b04'], ...plain },
  ];

  it('finds the names of an expression, not its functions', () => {
    expect([...namesInExpression('where(nir > 0.1, (nir - red) / (nir + red), 1e5)')].sort()).toEqual(['nir', 'red']);
    expect(namesInExpression('sqrt (red)').has('sqrt')).toBe(false);
  });

  it('takes what is picked and what an expression names, in the item order', () => {
    expect(orderAssets(sources, ['scl'], ['(nir - red)'])).toEqual(['red', 'nir', 'scl']);
  });

  it('leaves a name two assets carry to the user', () => {
    expect(orderAssets(sources, [], ['b04 * 2'])).toEqual([]);
  });
});

describe('candidateItems (F8)', () => {
  const aoi = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);

  it('keeps the scenes whose footprint meets the AOI', () => {
    const a = item('a', {}, [10, 50, 11, 51]);
    const b = item('b', {}, [10.5, 50.5, 11.5, 51.5]);
    const far = item('far', {}, [20, 50, 21, 51]);
    expect(candidateItems([a, b, far], aoi).map((i) => i.id)).toEqual(['a', 'b']);
  });

  it('drops a scene whose bbox meets the AOI but whose footprint does not', () => {
    const diagonal: StacItem = {
      id: 'diag',
      bbox: [10, 50, 11, 51],
      geometry: { type: 'Polygon', coordinates: [[[10, 50], [10.3, 50], [10, 50.3], [10, 50]]] },
      properties: {},
      assets: {},
    };
    expect(candidateItems([diagonal], aoi)).toEqual([]);
  });

  it('keeps a scene without a footprint: the server says what it skips', () => {
    expect(candidateItems([{ id: 'n', properties: {}, assets: {} }], aoi)).toHaveLength(1);
  });

  it('takes the buffered square of a point as the AOI, as the crop does (K11)', () => {
    const square = bufferPointToPolygon(10.5, 50.5, 0.05);
    expect(candidateItems([item('a', {})], square)).toHaveLength(1);
  });
});

describe('passesOf (M4-12b)', () => {
  const group = (label: string, items: StacItem[]): TimeStepGroup => ({ key: [label], label, items });
  const a = item('a', {});
  const b = item('b', {});
  const c = item('c', {});

  it('splits the scenes by the group of the results list, in the order of the list', () => {
    const groups = [group('2026-07-02', [c]), group('2026-07-01', [a, b])];
    const passes = passesOf([b, c, a], groups);
    expect(passes.map((p) => [p.label, p.items.map((i) => i.id)])).toEqual([
      ['2026-07-02', ['c']],
      ['2026-07-01', ['b', 'a']],
    ]);
  });

  it('gives each pass its own key', () => {
    const groups = [group('x', [a]), group('y', [b])];
    const keys = passesOf([a, b], groups).map((p) => p.key);
    expect(new Set(keys).size).toBe(2);
  });

  it('puts a scene the list does not know into a pass of its own, last', () => {
    const passes = passesOf([c, a], [group('2026-07-01', [a])]);
    expect(passes.map((p) => [p.label, p.items.map((i) => i.id)])).toEqual([
      ['2026-07-01', ['a']],
      ['Other scenes', ['c']],
    ]);
  });

  it('is empty without scenes', () => {
    expect(passesOf([], [group('x', [a])])).toEqual([]);
  });
});

describe('buildOrder', () => {
  const step = (op: string, opVersion: number, values: DraftStep['values']): DraftStep => ({ key: 1, op, opVersion, values });
  const aoi = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);
  const base = {
    datasetId: 'sentinel-2-c1-l2a',
    itemIds: ['S2B_X'],
    area: 'aoi' as const,
    aoi,
    steps: [step('band_math', 1, { expression: '(nir - red) / (nir + red)' })],
    assets: ['red', 'nir'],
    dtype: 'float32',
    info: S2,
  };

  it('builds the envelope with one input named "input", one item and the AOI', () => {
    expect(buildOrder(base).order).toEqual({
      recipe_version: 1,
      inputs: [{ name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['S2B_X']], assets: ['red', 'nir'] }],
      aoi,
      steps: [{ op: 'band_math', op_version: 1, params: { expression: '(nir - red) / (nir + red)' } }],
      output: { kind: 'raster', format: 'cog', dtype: 'float32' },
    });
  });

  it('sends no AOI for "Whole scene", and needs none (M4-13c §3.2)', () => {
    const order = buildOrder({ ...base, area: 'scene', aoi: null }).order;
    expect(order).not.toBeNull();
    expect(order).not.toHaveProperty('aoi');
    expect(buildOrder({ ...base, area: 'scene' }).order).toEqual(order);
  });

  it('needs an area for "AOI only"', () => {
    const built = buildOrder({ ...base, aoi: null });
    expect(built.order).toBeNull();
    expect(built.problems).toContain('Draw an area as AOI.');
  });

  it('puts all scenes of the pass into one group, sorted, so the same scenes are the same order', () => {
    const forward = buildOrder({ ...base, itemIds: ['S2B_B', 'S2B_A', 'S2B_C'] }).order;
    const backward = buildOrder({ ...base, itemIds: ['S2B_C', 'S2B_A', 'S2B_B'] }).order;
    expect(forward?.inputs[0].groups).toEqual([['S2B_A', 'S2B_B', 'S2B_C']]);
    expect(backward).toEqual(forward);
  });

  it('turns reprojection numbers into numbers and keeps the boolean', () => {
    const order = buildOrder({
      ...base,
      steps: [step('reproject', 2, { crs: 'EPSG:3035', resolution: '30', resampling: 'bilinear', align: false })],
    }).order;
    expect(order?.steps[0].params).toEqual({ crs: 'EPSG:3035', resolution: 30, resampling: 'bilinear', align: false });
  });

  it.each([
    ['no scene', { itemIds: [] }, 'Pick a pass.'],
    ['a line as AOI', { aoi: { type: 'LineString', coordinates: [[0, 0], [1, 1]] } }, 'Draw an area as AOI.'],
    ['no step', { steps: [] }, 'Add a step.'],
    ['17 steps', { steps: Array.from({ length: 17 }, () => base.steps[0]) }, 'At most 16 steps.'],
    ['no band', { assets: [] }, 'Pick at least one band.'],
    ['17 bands', { assets: Array.from({ length: 17 }, (_, i) => `b${i}`) }, 'At most 16 bands.'],
    ['no data type', { dtype: '' }, 'Pick an output data type.'],
  ])('blocks %s', (_, change, problem) => {
    const built = buildOrder({ ...base, ...change } as Parameters<typeof buildOrder>[0]);
    expect(built.order).toBeNull();
    expect(built.problems).toContain(problem);
  });

  it('blocks a step whose form does not fit and says where', () => {
    const built = buildOrder({ ...base, steps: [step('band_math', 1, { expression: '' })] });
    expect(built.order).toBeNull();
    expect(built.stepProblems[0].errors).toEqual({ expression: 'Required.' });
  });

  it('blocks an operator the dataset does not offer', () => {
    const built = buildOrder({ ...base, steps: [step('decomp', 1, {})] });
    expect(built.order).toBeNull();
    expect(built.stepProblems[0].unsupported).toMatch(/not available/);
  });
});

describe('buildMosaicOrder (M4-12 §3.1)', () => {
  it('names the whole scenes of one pass: one group, no AOI, no steps', () => {
    expect(
      buildMosaicOrder({ datasetId: 'sentinel-2-c1-l2a', itemIds: ['B', 'A'], assets: ['visual'], dtype: 'uint8' }),
    ).toEqual({
      recipe_version: 1,
      inputs: [{ name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['A', 'B']], assets: ['visual'] }],
      steps: [],
      output: { kind: 'raster', format: 'cog', dtype: 'uint8' },
    });
  });

  it('carries no aoi member at all', () => {
    const order = buildMosaicOrder({ datasetId: 'd', itemIds: ['A'], assets: ['visual'], dtype: 'uint8' });
    expect('aoi' in order).toBe(false);
  });
});

describe('small rules', () => {
  it('finds the step a refusal names', () => {
    expect(stepOfRefusal('the order is not valid: parameters of step 1 (reproject): crs')).toBe(1);
    expect(stepOfRefusal("step 0: 'band_math' cannot run here")).toBe(0);
    expect(stepOfRefusal('invalid order: steps.2.params.expression: string_too_long')).toBe(2);
    expect(stepOfRefusal('the AOI does not touch any of the given items')).toBeNull();
    const bm = [{ op: 'reproject' }, { op: 'band_math' }];
    expect(stepOfRefusal('expression names unknown band(s): nir_2; the input has: red, nir', bm)).toBe(1);
    expect(stepOfRefusal('expression names unknown band(s): x', [...bm, { op: 'band_math' }])).toBeNull();
  });

  it('formats the estimate', () => {
    expect(formatBytes(4_200_000)).toBe('4.2 MB');
    expect(formatDuration('PT12.3S')).toBe('about 12 s');
    expect(formatDuration('PT0.4S')).toBe('under 1 s');
    expect(formatDuration('PT600.0S')).toBe('about 10 min');
    expect(formatDuration('P1D')).toBe('P1D');
  });

  it('says why Process cannot open; no AOI needed (M4-13c K1)', () => {
    const collection = (tier: string) => ({ id: 'x', 'earthx:license_flags': { tier } }) as unknown as Collection;
    expect(processBlockReason({ viewable: true, collection: collection('processing') }, 1)).toBeNull();
    expect(processBlockReason({ viewable: true, collection: collection('display') }, 1)).toMatch(/tier: display/);
    expect(processBlockReason({ viewable: true, collection: collection('processing') }, 0)).toMatch(/scene/);
    expect(processBlockReason(undefined, 1)).toMatch(/dataset/);
  });
});
