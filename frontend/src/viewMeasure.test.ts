// The measure of the view over the AOI (UI-03e): the order for what the view draws, the answer turned back into the values the tiles draw,
// and the fall-back to the first whole scene.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { AreaStatistics } from './api';
import type { IndexPreset } from './indexPresets';
import type { Collection, StacItem } from './types';
import { areaQuestionOf, forgetAreaAnswers, inRawValues, measureView, statisticsOfArea, type ViewMeasure } from './viewMeasure';

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
const ask = (over: Partial<Parameters<typeof areaQuestionOf>[0]> = {}) =>
  areaQuestionOf({ datasetId: 's2', collection: collection(), items: [item('b'), item('a')], aoi: AOI, index: null, asset: 'red', ...over });

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
    expect(question?.scalings).toEqual([{ scale: 0.0001, offset: -0.1 }]);
  });

  it('names the three bands of the colour picture as the item does', () => {
    const question = ask({ asset: 'visual' });
    expect(question?.order.output).toMatchObject({ bands: ['visual_1', 'visual_2', 'visual_3'] });
    expect(question?.scalings).toEqual(Array.from({ length: 3 }, () => ({ scale: 1, offset: 0 })));
  });

  it('is one band_math step of version 2 for an index, and that band as the output', () => {
    const question = ask({ index: NDVI });
    expect(question?.order.steps).toEqual([{ op: 'band_math', op_version: 2, params: { expression: NDVI.expression, name: 'NDVI' } }]);
    expect(question?.order.output).toMatchObject({ dtype: 'float32', bands: ['NDVI'] });
    // An index is physical on both sides: nothing is turned back.
    expect(question?.scalings).toEqual([{ scale: 1, offset: 0 }]);
  });

  it('carries the position of the AOI and nothing else of it', () => {
    const dressed = { ...AOI, bbox: [10, 47, 10.1, 47.1], properties: { place: 'somewhere' } } as GeoJSON.Polygon;
    expect(ask({ aoi: dressed })?.order.aoi).toEqual(AOI);
  });

  it.each([
    ['no area is cropped', { aoi: null }],
    ['a point is no area', { aoi: { type: 'Point', coordinates: [10, 47] } as GeoJSON.Point }],
    ['the scenes are not known', { items: [] }],
    ['the dataset is not a COG', { collection: collection('zarr') }],
    ['there is no dataset', { collection: undefined }],
    ['the asset is not one of the item', { asset: 'nothing' }],
    ['the item does not say how many bands the asset has', { asset: 'bare' }],
  ])('is none where %s', (_, over) => {
    expect(ask(over as Partial<Parameters<typeof areaQuestionOf>[0]>)).toBeNull();
  });

  it.each([
    ['a scale of zero', { ...SCALED, scale: 0 }],
    ['a falling scale', { ...SCALED, scale: -0.0001 }],
    ['a scale that is no number', { ...SCALED, scale: Number.NaN }],
    ['an offset that is no number', { ...SCALED, offset: Number.POSITIVE_INFINITY }],
  ])('is none for %s, which cannot be turned back', (_, red) => {
    expect(ask({ items: [item('a', red)] })).toBeNull();
  });

  it('is none for scenes whose bands are scaled differently: one raw range would be right for none of them', () => {
    expect(ask({ items: [item('a'), item('b', { ...SCALED, offset: 0 })] })).toBeNull();
    expect(ask({ items: [item('a'), item('b', SCALED)] })).not.toBeNull();
  });
});

describe('the answer in the values the tiles draw', () => {
  const physical = { minimum: 0.1, maximum: 0.3, mean: 0.2, stddev: 0.02, count: 4, valid_percent: 100, percentile_2: 0.12, percentile_98: 0.28, histogram: [[1, 3], [0.1, 0.2, 0.3]] };

  it('turns every value, percentile and edge back with raw · scale + offset, and keeps the counts', () => {
    const raw = inRawValues(physical, { scale: 0.0001, offset: -0.1 });
    expect(raw.minimum).toBeCloseTo(2000, 6);
    expect(raw.maximum).toBeCloseTo(4000, 6);
    expect(raw.mean).toBeCloseTo(3000, 6);
    expect(raw.percentile_2).toBeCloseTo(2200, 6);
    expect(raw.percentile_98).toBeCloseTo(3800, 6);
    expect(raw.stddev).toBeCloseTo(200, 6);
    const [counts, edges] = raw.histogram as [number[], number[]];
    expect(counts).toEqual([1, 3]);
    expect(edges[0]).toBeCloseTo(2000, 6);
    expect(edges[2]).toBeCloseTo(4000, 6);
    expect([raw.count, raw.valid_percent]).toEqual([4, 100]);
  });

  it('leaves a band that has no valid value as it is', () => {
    expect(inRawValues({ count: 0, valid_percent: 0 }, { scale: 0.0001, offset: -0.1 })).toEqual({ count: 0, valid_percent: 0 });
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
    const statistics = statisticsOfArea(answer, [{ scale: 1, offset: 0 }, { scale: 1, offset: 0 }]);
    expect(Object.keys(statistics)).toEqual(['visual_1', 'visual_2']);
    expect(statistics.visual_2).toMatchObject({ min: 6, max: 240, minimum: 6, maximum: 240 });
  });
});

describe('the measure', () => {
  const area = ask()!;
  const measure: ViewMeasure = { sceneUrl: '/collections/s2/items/a/statistics?asset=red', area, key: 'k' };
  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
  const physical = { bands: [{ name: 'red', unit: null, statistics: { minimum: 0.1, maximum: 0.3, count: 4, percentile_2: 0.12, percentile_98: 0.28 } }], exact: true, factor: 1 };
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

  it('asks the route for the area, with the AOI in the body and in no address', async () => {
    answers(() => json(physical));
    const { statistics, fellBack } = await measureView(measure);
    expect(fellBack).toBe(false);
    expect(statistics.red.min).toBeCloseTo(2000, 6);
    expect(statistics.red.percentile_98).toBeCloseTo(3800, 6);
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
    expect(fellBack).toBe(false);
    expect(statistics.red.max).toBe(4000);
    const url = new URL(urls()[0], 'http://x');
    expect(url.pathname).toBe('/collections/s2/items/a/statistics');
    expect(url.searchParams.getAll('p')).toEqual(['5', '95']);
    expect(url.searchParams.has('histogram_bins')).toBe(true);
  });

  it.each([413, 422])('falls back to the first whole scene on %i, and says so', async (status) => {
    answers(() => json({ detail: 'refused' }, status), () => json(scene));
    const { statistics, fellBack } = await measureView(measure, { percentiles: [5] });
    expect(fellBack).toBe(true);
    expect(statistics.red.max).toBe(4000);
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
    expect((await measureView(measure)).fellBack).toBe(true);
    expect((await measureView(measure)).fellBack).toBe(false);
  });

  it('names no area in what it writes to the console', async () => {
    answers(() => json({ detail: 'the area 10.0,47.0 is outside' }, 422), () => json(scene));
    await measureView(measure);
    expect(String(vi.mocked(console.warn).mock.calls)).not.toMatch(/47|outside|coordinates/u);
  });
});
