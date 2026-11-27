// The measure of the view over the AOI (UI-03e): the order for what the view draws, every answer in physical values (M5-68), the range
// turned into stored values for a tile, and the fall-back to the first whole scene.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { AreaStatistics } from './api';
import type { IndexPreset } from './indexPresets';
import { presetOfIndex } from './quickPresets';
import type { Collection, StacItem } from './types';
import { areaQuestionOf, fallbackReasonOf, forgetAreaAnswers, inPhysicalValues, measureView, physicalOf, rawOf, rescaleThrough, scalingOfAsset, statisticsOfArea, storedRescale, type ViewMeasure } from './viewMeasure';

const TIFF = 'image/tiff; application=geotiff; profile=cloud-optimized';
const SCALED = { data_type: 'uint16', nodata: 0, scale: 0.0001, offset: -0.1 };
const collection = (format = 'cog') => ({ id: 's2', 'earthx:format': format }) as unknown as Collection;

const item = (id: string, red: Record<string, unknown> = SCALED): StacItem => ({
  id,
  properties: {},
  assets: {
    red: { href: 'x', type: TIFF, 'raster:bands': [red] },
    visual: { href: 'x', type: TIFF, 'raster:bands': Array.from({ length: 3 }, () => ({ data_type: 'uint8', nodata: 0 })) },
    bare: { href: 'x', type: TIFF },
  } as StacItem['assets'],
});

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [10.1, 47], [10.1, 47.1], [10, 47]]] };
const NDVI: IndexPreset = { name: 'NDVI', title: 'NDVI', expression: '(nir - red) / (nir + red)', rescale: [-1, 1], colormapName: 'rdylgn', formula: '', reference: '' };
type Over = Partial<Parameters<typeof areaQuestionOf>[0]>;
const asked = (over: Over = {}) => areaQuestionOf({ datasetId: 's2', collection: collection(), items: [item('b'), item('a')], aoi: AOI, index: null, asset: 'red', ...over });
// The question itself, `null` where none is asked.
const ask = (over: Over = {}) => {
  const one = asked(over);
  return one && 'order' in one ? one : null;
};

describe('the order for what the view draws', () => {
  it('has no step for a band, and that band as the output in float32', () => {
    const question = ask();
    expect(question?.order).toEqual({
      recipe_version: 2,
      inputs: [{ name: 'input', dataset: 's2', groups: [['a', 'b']] }],
      aoi: AOI,
      steps: [],
      output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['red'] },
    });
  });

  it('names the three bands of the colour picture as the item does', () => {
    const question = ask({ asset: 'visual' });
    expect(question?.order.output).toMatchObject({ bands: ['visual_1', 'visual_2', 'visual_3'] });
  });

  it('is one band_math step of version 2 for an index, and that band as the output', () => {
    const question = ask({ index: presetOfIndex(NDVI) });
    expect(question?.order.steps).toEqual([{ op: 'band_math', op_version: 2, params: { expression: NDVI.expression, name: 'NDVI' } }]);
    expect(question?.order.output).toMatchObject({ dtype: 'float32', bands: ['NDVI'] });
  });

  it('carries the position of the AOI and nothing else of it', () => {
    const dressed = { ...AOI, bbox: [10, 47, 10.1, 47.1], properties: { place: 'somewhere' } } as GeoJSON.Polygon;
    expect(ask({ aoi: dressed })?.order.aoi).toEqual(AOI);
  });

  it('measures the one pixel of a point (M5-69)', () => {
    expect(ask({ aoi: { type: 'Point', coordinates: [10.05, 47.05] } })?.order.aoi).toEqual({ type: 'Point', coordinates: [10.05, 47.05] });
  });

  it.each([
    ['no area is cropped', { aoi: null }],
  ])('says nothing where %s: there is nothing to fall back from', (_, over) => {
    expect(asked(over as Over)).toBeNull();
  });

  it.each([
    ['the scenes are not known', { items: [] }, /not all known/u],
    ['the dataset is not a COG', { collection: collection('zarr') }, /no cloud-optimized GeoTIFF/u],
    ['there is no dataset', { collection: undefined }, /no cloud-optimized GeoTIFF/u],
    ['the asset is not one of the item', { asset: 'nothing' }, /do not describe the bands/u],
    ['the item does not say how many bands the asset has', { asset: 'bare' }, /do not describe the bands/u],
  ])('gives the reason for the first scene where %s', (_, over, reason) => {
    expect(asked(over as Over)).toEqual({ reason: expect.stringMatching(reason) });
  });

  it('asks the area of scenes scaled differently: the answer is physical, and a physical range fits each of them (M5-68)', () => {
    expect(ask({ items: [item('a'), item('b', { ...SCALED, offset: 0 })] })).not.toBeNull();
  });
});

describe('physical and stored values (M5-68)', () => {
  const S2 = { scale: 0.0001, offset: -0.1 };
  const stored = { min: 1200, max: 3400, mean: 2300, stddev: 200, count: 4, valid_percent: 100, percentile_2: 1300, percentile_98: 3300, histogram: [[1, 3], [1200, 2300, 3400]] };

  it('turns the statistics of a scene into physical values, every value, percentile and edge, and keeps the counts', () => {
    const physical = inPhysicalValues(stored, S2);
    expect(physical).toMatchObject({ min: 0.02, max: 0.24, mean: 0.13, percentile_2: 0.03, percentile_98: 0.23, count: 4, valid_percent: 100 });
    expect(physical.stddev).toBeCloseTo(0.02, 12);
    expect(physical.histogram).toEqual([[1, 3], [0.02, 0.13, 0.24]]);
  });

  it('leaves a band that has no valid value as it is', () => {
    expect(inPhysicalValues({ count: 0, valid_percent: 0 }, S2)).toEqual({ count: 0, valid_percent: 0 });
  });

  it('rounds to twelve significant digits, as the registry writes a physical value', () => {
    expect(physicalOf(1200, S2)).toBe(0.02);
    expect(rawOf(0.02, S2)).toBe(1200);
    expect(rawOf(physicalOf(3456, S2), S2)).toBe(3456);
  });

  it('turns a physical range into the stored values of a tile, one pair or one for each channel', () => {
    expect(storedRescale('0.02,0.24', undefined, S2)).toBe('1200,3400');
    expect(storedRescale('0.02,0.24;0,0.1;-0.1,0', undefined, S2)).toBe('1200,3400;1000,2000;0,1000');
    expect(rescaleThrough('1200,3400', (value) => physicalOf(value, S2))).toBe('0.02,0.24');
  });

  it('keeps a range the registry gives in stored values, and one of a picture without scaling', () => {
    expect(storedRescale('1200,3400', true, S2)).toBe('1200,3400');
    expect(storedRescale('0.02,0.24', undefined, null)).toBe('0.02,0.24');
  });

  it('keeps an end that is no number', () => {
    expect(storedRescale('0.02,', undefined, S2)).toBe('1200,');
  });

  it.each([
    ['a scale of zero', { ...SCALED, scale: 0 }],
    ['a falling scale', { ...SCALED, scale: -0.0001 }],
    ['a scale that is no number', { ...SCALED, scale: Number.NaN }],
    ['an offset that is no number', { ...SCALED, offset: Number.POSITIVE_INFINITY }],
  ])('reads no scaling of an item with %s, which cannot be turned back', (_, red) => {
    expect(scalingOfAsset(item('a', red), 'red')).toBeNull();
  });

  it('reads the scaling of an asset as the item states it, and none as 1 and 0', () => {
    expect(scalingOfAsset(item('a'), 'red')).toEqual(S2);
    expect(scalingOfAsset(item('a', { data_type: 'uint16' }), 'red')).toEqual({ scale: 1, offset: 0 });
  });

  it('is by band in the order of the answer, with the names the tile route has for the ends', () => {
    const answer: AreaStatistics = {
      exact: true,
      factor: 1,
      bands: [
        { name: 'visual_1', unit: null, statistics: { minimum: 5, maximum: 250, count: 9 } },
        { name: 'visual_2', unit: null, statistics: { minimum: 6, maximum: 240, count: 9 } },
      ],
    };
    const statistics = statisticsOfArea(answer);
    expect(Object.keys(statistics)).toEqual(['visual_1', 'visual_2']);
    expect(statistics.visual_2).toMatchObject({ min: 6, max: 240, minimum: 6, maximum: 240 });
  });
});

describe('the measure', () => {
  const area = ask()!;
  const measure: ViewMeasure = { sceneUrl: '/collections/s2/items/a/statistics?asset=red', scaling: { scale: 0.0001, offset: -0.1 }, area, skipped: null, key: 'k' };
  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
  const physical = { bands: [{ name: 'red', unit: null, statistics: { minimum: 0.1, maximum: 0.3, count: 4, percentile_2: 0.12, percentile_98: 0.28 } }], exact: true, factor: 1 };
  // The scene route answers in the stored numbers of the file: 2000 … 4000 is 0.1 … 0.3.
  const scene = { red: { min: 2000, max: 4000, percentile_2: 2200, percentile_98: 3800, count: 4 } };
  let fetchMock: ReturnType<typeof vi.fn>;
  const answers = (...replies: (() => Response)[]) => {
    fetchMock = vi.fn(async () => (replies.shift() ?? (() => json(scene)))());
    vi.stubGlobal('fetch', fetchMock);
  };
  const urls = () => fetchMock.mock.calls.map((call) => String((call as unknown[])[0]));

  beforeEach(() => {
    forgetAreaAnswers();
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('asks the route for the area, with the AOI in the body and in no address, and keeps its physical answer', async () => {
    answers(() => json(physical));
    const { statistics, fellBack } = await measureView(measure);
    expect(fellBack).toBeNull();
    expect(statistics.red).toMatchObject({ min: 0.1, percentile_98: 0.28 });
    expect(urls()).toEqual(['/collections/s2/statistics']);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual(area.order);
  });

  it('asks once for one order, however many times the picture is measured', async () => {
    answers(() => json(physical));
    await Promise.all([measureView(measure), measureView(measure, { histogram: true }), measureView(measure, { percentiles: [5, 95] })]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('asks the first scene where the view is not cropped, with the percentiles and the histogram it is asked for', async () => {
    answers(() => json(scene));
    const { statistics, fellBack } = await measureView({ ...measure, area: null }, { percentiles: [5, 95], histogram: true });
    expect(fellBack).toBeNull();
    expect(statistics.red).toMatchObject({ min: 0.1, max: 0.3, percentile_2: 0.12, percentile_98: 0.28 });
    const url = new URL(urls()[0], 'http://x');
    expect(url.pathname).toBe('/collections/s2/items/a/statistics');
    expect(url.searchParams.getAll('p')).toEqual(['5', '95']);
    expect(url.searchParams.has('histogram_bins')).toBe(true);
  });

  it.each([413, 422])('falls back to the first whole scene on %i, and says so', async (status) => {
    answers(() => json({ detail: 'refused' }, status), () => json(scene));
    const { statistics, fellBack } = await measureView(measure, { percentiles: [5] });
    expect(fellBack).toBe(fallbackReasonOf(measure));
    expect(fellBack).toMatch(status === 413 ? /at most 16 files/u : /does not take the area/u);
    // The first scene in the same physical values as the area would have been.
    expect(statistics.red.max).toBe(0.3);
    expect(urls()).toHaveLength(2);
    expect(new URL(urls()[1], 'http://x').searchParams.getAll('p')).toEqual(['5']);
  });

  it.each([500, 502, 503])('does not hide a failure of %i behind the first scene', async (status) => {
    answers(() => json({ detail: 'broken' }, status));
    await expect(measureView(measure)).rejects.toMatchObject({ status });
    expect(urls()).toHaveLength(1);
  });

  it('does not keep a refusal: the same order is asked again next time', async () => {
    answers(() => json({ detail: 'refused' }, 422), () => json(scene), () => json(physical));
    expect((await measureView(measure)).fellBack).not.toBeNull();
    expect(fallbackReasonOf(measure)).not.toBeNull();
    expect((await measureView(measure)).fellBack).toBeNull();
    // A measure that works again takes the hint with it.
    expect(fallbackReasonOf(measure)).toBeNull();
  });

  it('names no area in what it writes to the console', async () => {
    answers(() => json({ detail: 'the area 10.0,47.0 is outside' }, 422), () => json(scene));
    await measureView(measure);
    expect(String(vi.mocked(console.warn).mock.calls)).not.toMatch(/47|outside|coordinates/u);
  });

  it('says why the first scene stands in where the area was never asked, for the range and for the histograms alike', async () => {
    const skipped: ViewMeasure = { ...measure, area: null, skipped: 'The items do not describe the bands of this image.' };
    answers(() => json(scene), () => json(scene));
    expect((await measureView(skipped, { percentiles: [5] })).fellBack).toBe(skipped.skipped);
    expect((await measureView(skipped, { histogram: true })).fellBack).toBe(skipped.skipped);
    expect(fallbackReasonOf(skipped)).toBe(skipped.skipped);
    expect(urls().every((url) => url.startsWith('/collections/s2/items/a/statistics'))).toBe(true);
  });

  it('keeps the answer of a scene without scaling (an index, a step, an unscaled band) as it is', async () => {
    answers(() => json(scene));
    expect((await measureView({ ...measure, area: null, scaling: null })).statistics.red.max).toBe(4000);
  });

  it('says nothing where the view is not cropped, the first scene being the question there', async () => {
    const plain: ViewMeasure = { ...measure, area: null, skipped: null };
    answers(() => json(scene));
    expect((await measureView(plain)).fellBack).toBeNull();
    expect(fallbackReasonOf(plain)).toBeNull();
  });

  it('keeps the hint of one picture to that picture', async () => {
    answers(() => json({ detail: 'refused' }, 413), () => json(scene), () => json(physical));
    await measureView(measure);
    const other: ViewMeasure = { ...measure, key: 'other' };
    expect(fallbackReasonOf(other)).toBeNull();
    expect(fallbackReasonOf(measure)).not.toBeNull();
  });
});
