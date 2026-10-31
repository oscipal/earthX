import { describe, expect, it } from 'vitest';

import { DEFAULT_RANGE } from './processingPreview';
import { parseTileJson } from './processing';
import {
  bandTileUrl,
  defaultRange,
  isOverview,
  isResultExpired,
  MIN_REMAINING_MS,
  ownRangeOf,
  rangeOfRender,
  rangeOfTileUrl,
  renderOfRange,
  restyledTileUrl,
  resultBands,
  resultGsd,
  resultLayerName,
  resultRender,
  resultStats,
  resultTileTemplate,
  startPlaceOf,
  tilesHref,
} from './resultLayer';

const ID = 'ZyXwVuTsRqPoNmLkJiHg_-';
const HREF = `/results/${ID}/WebMercatorQuad/tilejson.json`;

describe('the link to the tiles of a result', () => {
  it('is the one path the tiler serves', () => {
    expect(tilesHref({ tiles: { href: HREF } })).toBe(HREF);
  });

  it('is the path alone for an absolute link: the tiles are read through this host, never from the one named', () => {
    expect(tilesHref({ tiles: { href: `http://localhost:8001${HREF}` } })).toBe(HREF);
    expect(tilesHref({ tiles: { href: `https://tiles.example.org${HREF}` } })).toBe(HREF);
  });

  it.each([
    ['no link', {}],
    ['a link without an address', { tiles: {} }],
    ['an address that is not text', { tiles: { href: 5 } }],
    ['an address with credentials', { tiles: { href: `https://user:pw@example.org${HREF}` } }],
    ['an absolute address with a query', { tiles: { href: `https://example.org${HREF}?x=1` } }],
    ['an absolute address with a fragment', { tiles: { href: `https://example.org${HREF}#x` } }],
    ['an address of another scheme', { tiles: { href: `javascript://example.org${HREF}` } }],
    ['an absolute address of another path', { tiles: { href: 'https://example.org/processing/x' } }],
    ['a host-relative address with two slashes', { tiles: { href: `/${HREF}` } }],
    ['an identifier of the wrong length', { tiles: { href: `/results/${ID}x/WebMercatorQuad/tilejson.json` } }],
    ['an identifier with a dot', { tiles: { href: `/results/${ID.slice(0, 20)}../WebMercatorQuad/tilejson.json` } }],
    ['a path that climbs out', { tiles: { href: `/results/../${ID}/WebMercatorQuad/tilejson.json` } }],
    ['another matrix set', { tiles: { href: `/results/${ID}/WorldCRS84Quad/tilejson.json` } }],
    ['a query', { tiles: { href: `${HREF}?x=1` } }],
    ['a line break', { tiles: { href: `${HREF}\n` } }],
    ['a file of the job API', { tiles: { href: '/processing/jobs/AbCdEfGhIjKlMnOpQrSt_-/results/result.tif' } }],
  ])('is none for %s', (_, doc) => {
    expect(tilesHref(doc as never)).toBeNull();
  });

  it('gives a tile template for 256-pixel tiles, and refuses any other address', () => {
    expect(resultTileTemplate(HREF)).toBe(`/results/${ID}/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=256`);
    expect(() => resultTileTemplate('https://example.org/x')).toThrow('not the tiles of a result');
  });
});

describe('the TileJSON of a result', () => {
  const good = { bounds: [10, 50, 11, 51], minzoom: 8, maxzoom: 14, data_type: 'float32', tiles: ['x'] };

  it('is read for its bounds, levels and data type', () => {
    expect(parseTileJson(good)).toEqual({ bounds: [10, 50, 11, 51], minZoom: 8, maxZoom: 14, dataType: 'float32' });
    expect(parseTileJson({ ...good, data_type: undefined })?.dataType).toBeNull();
  });

  it.each([
    ['nothing', null],
    ['text', 'x'],
    ['no bounds', { ...good, bounds: undefined }],
    ['three bounds', { ...good, bounds: [1, 2, 3] }],
    ['bounds that are text', { ...good, bounds: ['1', '2', '3', '4'] }],
    ['bounds that are not finite', { ...good, bounds: [1, 2, 3, null] }],
    ['no levels', { ...good, minzoom: undefined }],
    ['levels the wrong way round', { ...good, minzoom: 12, maxzoom: 4 }],
  ])('is nothing for %s', (_, value) => {
    expect(parseTileJson(value)).toBeNull();
  });
});

describe('how a result is drawn', () => {
  it('gives a float result the range and colormap of the preview', () => {
    expect(resultRender('float32', DEFAULT_RANGE)).toEqual({ rescale: '-1,1', colormapName: 'rdylgn' });
    expect(resultRender('float64', { vmin: '0', vmax: '0.5', colormap: '' })).toEqual({ rescale: '0,0.5' });
  });

  it.each(['uint16', 'int16', 'uint8', null])('draws a %s result as it is', (dataType) => {
    expect(resultRender(dataType, DEFAULT_RANGE)).toEqual({});
  });

  it('draws a float result without a range when the range is no range', () => {
    expect(resultRender('float32', { vmin: '1', vmax: '1', colormap: 'rdylgn' })).toEqual({ colormapName: 'rdylgn' });
  });
});

// The statistics of the AOI as the results document carries them (`properties.bands[].statistics`, M4-32a).
const band = (statistics: Record<string, unknown> | undefined) => ({ name: 'b', data_type: 'float32', statistics });
const dem = { minimum: 100, maximum: 2400, mean: 900, count: 1000, valid_percent: 100, percentile_2: 180, percentile_98: 1900 };
const ndvi = { minimum: -0.3, maximum: 0.9, mean: 0.4, count: 1000, valid_percent: 90, percentile_2: -0.05, percentile_98: 0.8 };
const stats = (statistics: Record<string, unknown>, expression = false) =>
  resultStats({ bands: [band(statistics)], ...(expression ? { 'processing:expression': { format: 'numexpr', expression: 'a' } } : {}) });

describe('the statistics of a result', () => {
  it('are read from the bands of the properties, with the 2nd and 98th percentile', () => {
    expect(stats(dem)).toEqual({
      bands: [{ minimum: 100, maximum: 2400, percentile2: 180, percentile98: 1900 }],
      expression: false,
    });
  });

  it('know a Band math result by its expression', () => {
    expect(stats(ndvi, true)?.expression).toBe(true);
  });

  it.each([
    ['no properties', undefined],
    ['no bands', {}],
    ['no bands in a list', { bands: [] }],
    ['bands that are not a list', { bands: 'x' }],
    ['a band without statistics (a result from before M4-32a)', { bands: [band(undefined)] }],
    ['bands that are not objects', { bands: [null, 7] }],
    ['a band without a valid pixel', { bands: [band({ count: 0, valid_percent: 0 })] }],
    ['values that are not numbers', { bands: [band({ count: 5, minimum: 'a', maximum: null })] }],
  ])('are nothing for %s', (_, properties) => {
    expect(resultStats(properties as never)).toBeNull();
  });

  it('keep the band that has values where another has none', () => {
    const read = resultStats({ bands: [band({ count: 0, valid_percent: 0 }), band(dem)] });
    expect(read?.bands).toEqual([
      { minimum: null, maximum: null, percentile2: null, percentile98: null },
      { minimum: 100, maximum: 2400, percentile2: 180, percentile98: 1900 },
    ]);
  });
});

describe('the colour scale of a result (plan §6.7)', () => {
  it('is 2–98 % of the statistics in viridis for a float result of an unknown quantity (rule 4)', () => {
    expect(resultRender('float32', DEFAULT_RANGE, stats(dem))).toEqual({ rescale: '180,1900', colormapName: 'viridis' });
  });

  it('is the lowest 2nd and the highest 98th percentile over the bands', () => {
    const two = resultStats({ bands: [band(dem), band({ ...dem, percentile_2: 50, percentile_98: 1500 })] });
    expect(resultRender('float32', DEFAULT_RANGE, two)).toEqual({ rescale: '50,1900', colormapName: 'viridis' });
  });

  it('leaves an index at −1…1 in rdylgn, judged by its values (rule 3)', () => {
    expect(resultRender('float32', DEFAULT_RANGE, stats(ndvi, true))).toEqual({ rescale: '-1,1', colormapName: 'rdylgn' });
  });

  it.each([
    ['a 98th percentile above 1', { ...ndvi, percentile_98: 1.2 }],
    ['a 2nd percentile below −1', { ...ndvi, percentile_2: -1.5 }],
  ])('does not call a Band math result an index with %s', (_, statistics) => {
    const { percentile_2: low, percentile_98: high } = statistics;
    expect(resultRender('float32', DEFAULT_RANGE, stats(statistics, true))).toEqual({
      rescale: `${low},${high}`,
      colormapName: 'viridis',
    });
  });

  // NM4-19, Frage 8 (Otto, 28.10.2026): the NDVI of a real scene has single pixels beyond ±1 (exactly −1.3…1.5 here), and a
  // coarser read smooths them away. The index is judged by the 2–98 %, so that the exact and the coarse measure agree.
  it('calls a Band math result an index when only single pixels lie beyond −1…1 (the 2–98 % do not)', () => {
    const outliers = { ...ndvi, minimum: -1.3, maximum: 1.5, percentile_2: 0, percentile_98: 0.91 };
    expect(resultRender('float32', DEFAULT_RANGE, stats(outliers, true))).toEqual({ rescale: '-1,1', colormapName: 'rdylgn' });
    expect(defaultRange({ dataType: 'float32', stats: stats(outliers, true) }, DEFAULT_RANGE)).toEqual({ vmin: '-1', vmax: '1', colormap: 'rdylgn' });
  });

  it('never calls the outlier case an index without a Band math step', () => {
    const outliers = { ...ndvi, minimum: -1.3, maximum: 1.5, percentile_2: 0, percentile_98: 0.91 };
    expect(resultRender('float32', DEFAULT_RANGE, stats(outliers))).toEqual({ rescale: '0,0.91', colormapName: 'viridis' });
  });

  it('judges an index by the minimum and maximum where a band has no percentiles', () => {
    const flat = { ...ndvi, percentile_2: null, percentile_98: null };
    expect(resultRender('float32', DEFAULT_RANGE, stats(flat, true))).toEqual({ rescale: '-1,1', colormapName: 'rdylgn' });
    expect(resultRender('float32', DEFAULT_RANGE, stats({ ...flat, maximum: 1.5 }, true))).toEqual({ rescale: '-0.3,1.5', colormapName: 'viridis' });
  });

  it('does not call a result an index by its values alone: a DEM scaled into 0…1 without an expression is not one', () => {
    expect(resultRender('float32', DEFAULT_RANGE, stats({ ...ndvi, minimum: 0, maximum: 1 }))).toEqual({
      rescale: '-0.05,0.8',
      colormapName: 'viridis',
    });
  });

  it('takes an index from the bands that have values when another has none', () => {
    const mixed = resultStats({
      bands: [band({ count: 0, valid_percent: 0 }), band(ndvi)],
      'processing:expression': { format: 'numexpr', expression: 'a' },
    });
    expect(resultRender('float32', DEFAULT_RANGE, mixed)).toEqual({ rescale: '-1,1', colormapName: 'rdylgn' });
  });

  it('holds the range the job was started with by hand, before the statistics (rule 2)', () => {
    const hand = { vmin: '0', vmax: '3000', colormap: 'terrain' };
    expect(resultRender('float32', DEFAULT_RANGE, stats(dem), hand)).toEqual({ rescale: '0,3000', colormapName: 'terrain' });
    expect(resultRender('float32', DEFAULT_RANGE, stats(ndvi, true), { ...DEFAULT_RANGE, vmax: '2' })).toEqual({
      rescale: '-1,2',
      colormapName: 'rdylgn',
    });
    expect(resultRender('float32', DEFAULT_RANGE, null, hand)).toEqual({ rescale: '0,3000', colormapName: 'terrain' });
  });

  it('does not take the range of the panel for a result with statistics: it is that of another job', () => {
    const hand = { vmin: '0', vmax: '3000', colormap: 'terrain' };
    expect(resultRender('float32', hand, stats(dem))).toEqual({ rescale: '180,1900', colormapName: 'viridis' });
    expect(resultRender('float32', hand, stats(ndvi, true))).toEqual({ rescale: '-1,1', colormapName: 'rdylgn' });
    expect(resultRender('float32', hand, stats(dem), null)).toEqual({ rescale: '180,1900', colormapName: 'viridis' });
  });

  it('draws an integer result as it is, with or without statistics (rule 1)', () => {
    expect(resultRender('uint16', DEFAULT_RANGE, stats(dem))).toEqual({});
    expect(resultRender('int32', { vmin: '0', vmax: '3', colormap: 'terrain' }, stats(dem), DEFAULT_RANGE)).toEqual({});
  });

  it('is the range of the panel without statistics (rule 5)', () => {
    expect(resultRender('float32', DEFAULT_RANGE, null)).toEqual({ rescale: '-1,1', colormapName: 'rdylgn' });
    expect(resultRender('float32', DEFAULT_RANGE)).toEqual({ rescale: '-1,1', colormapName: 'rdylgn' });
  });

  it('is minimum…maximum where the percentiles meet, and the panel where those meet too', () => {
    const flat = { ...dem, percentile_2: 500, percentile_98: 500 };
    expect(resultRender('float32', DEFAULT_RANGE, stats(flat))).toEqual({ rescale: '100,2400', colormapName: 'viridis' });
    const constant = { count: 9, valid_percent: 100, minimum: 7, maximum: 7, mean: 7, percentile_2: 7, percentile_98: 7 };
    expect(resultRender('float32', DEFAULT_RANGE, stats(constant))).toEqual({ rescale: '-1,1', colormapName: 'rdylgn' });
  });

  it('is minimum…maximum where a statistics has no percentiles', () => {
    const { percentile_2: _low, percentile_98: _high, ...bare } = dem;
    expect(resultRender('float32', DEFAULT_RANGE, stats(bare))).toEqual({ rescale: '100,2400', colormapName: 'viridis' });
  });

  it('is never a range the tiler would refuse: no NaN, no infinity, low below high', () => {
    for (const statistics of [{ ...dem, percentile_2: Infinity }, { ...dem, percentile_98: NaN }, { ...dem, minimum: NaN }]) {
      const { rescale } = resultRender('float32', DEFAULT_RANGE, stats(statistics));
      const [low, high] = (rescale ?? '').split(',').map(Number);
      expect(Number.isFinite(low) && Number.isFinite(high) && low < high).toBe(true);
    }
  });

  it('draws a result of an unknown data type as it is, statistics or not', () => {
    expect(resultRender(null, DEFAULT_RANGE, stats(dem))).toEqual({});
  });
});

describe('the pixel size of a result', () => {
  it('is the stated one for a projected CRS', () => {
    expect(resultGsd(10, 1000, [10, 50, 11, 51])).toBe(10);
  });

  it('is worked out from the columns for a geographic CRS, at the middle latitude', () => {
    // A degree of longitude is 111.3 km at the equator and half of that at 60 degrees.
    const equator = resultGsd(null, 1000, [0, -0.5, 1, 0.5])!;
    const sixty = resultGsd(null, 1000, [0, 59.5, 1, 60.5])!;
    expect(equator).toBeCloseTo(111.32, 1);
    expect(sixty).toBeCloseTo(equator / 2, 1);
  });

  it.each([null, 0, -5])('is not known with %s columns and no stated size', (width) => {
    expect(resultGsd(null, width, [0, 0, 1, 1])).toBeNull();
  });
});

describe('"Overview"', () => {
  const base = { gsd: 10, viewport: null, maxZoom: 14 };

  it('is shown where the tile of the map is coarser than the result', () => {
    // Tile level round(zoom + 1): level 6 is 2.4 km, level 14 is 9.5 m.
    expect(isOverview({ ...base, mapZoom: 5 })).toBe(true);
    expect(isOverview({ ...base, mapZoom: 11.4 })).toBe(true); // level 12: 38 m
  });

  it('is not shown once the tile is as fine as the result', () => {
    expect(isOverview({ ...base, mapZoom: 13 })).toBe(false);
    expect(isOverview({ ...base, mapZoom: 20 })).toBe(false);
  });

  it('holds the level at the finest one of the result', () => {
    // The tiler has nothing finer than level 11 here; the map stretches it, and it stays an overview.
    expect(isOverview({ gsd: 10, viewport: null, maxZoom: 11, mapZoom: 18 })).toBe(true);
  });

  it('judges by the part of the view nearest the equator, where the tile is coarsest', () => {
    // Level 13: 19 m at the equator, 12 m at 50 degrees north.
    expect(isOverview({ gsd: 15, mapZoom: 12, maxZoom: 14, viewport: [10, 50, 11, 51] })).toBe(false);
    expect(isOverview({ gsd: 15, mapZoom: 12, maxZoom: 14, viewport: [10, -1, 11, 1] })).toBe(true);
    expect(isOverview({ gsd: 15, mapZoom: 12, maxZoom: 14, viewport: [10, -1, 11, 51] })).toBe(true);
    expect(isOverview({ gsd: 15, mapZoom: 12, maxZoom: 14, viewport: [10, -51, 11, -50] })).toBe(false);
  });

  it('is not claimed for a result whose pixel size is not known', () => {
    expect(isOverview({ ...base, gsd: null, mapZoom: 2 })).toBe(false);
  });

  it('copes with the poles', () => {
    expect(() => isOverview({ ...base, mapZoom: 10, viewport: [0, 89.9, 1, 90] })).not.toThrow();
  });
});

describe('when a result layer expires', () => {
  const now = Date.parse('2026-10-20T12:00:00Z');
  const at = (ms: number) => new Date(now + ms).toISOString();

  it('is a minute before the results go', () => {
    expect(isResultExpired(at(MIN_REMAINING_MS + 1), now)).toBe(false);
    expect(isResultExpired(at(MIN_REMAINING_MS), now)).toBe(true);
    expect(isResultExpired(at(-1000), now)).toBe(true);
  });

  it('is expired when the time is not a time', () => {
    expect(isResultExpired('soon', now)).toBe(true);
  });
});

describe('the name of the layer', () => {
  it.each([
    ['Band math · Sentinel-2 L2A', 'Result · Band math'],
    ['Band math · Sentinel-2 L2A · 3/25', 'Result · Band math'],
    ['Reproject and resample, Band math · Copernicus DEM', 'Result · Reproject and resample, Band math'],
    ['', 'Result'],
    [null, 'Result'],
  ])('is made from the title %j', (title, name) => {
    expect(resultLayerName(title)).toBe(name);
  });
});

describe('the range of a result layer in its view', () => {
  const TEMPLATE = resultTileTemplate(HREF);
  const DEM = resultStats({ bands: [{ statistics: { count: 9, minimum: 100, maximum: 2400, percentile_2: 180, percentile_98: 1900 } }] });

  it('is read from the tile URL the layer draws with, or empty where it asks for none', () => {
    expect(rangeOfTileUrl(`${TEMPLATE}&colormap_name=terrain&rescale=0%2C3000`)).toEqual({ vmin: '0', vmax: '3000', colormap: 'terrain' });
    expect(rangeOfTileUrl(`${TEMPLATE}&rescale=-1%2C1`)).toEqual({ vmin: '-1', vmax: '1', colormap: '' });
    expect(rangeOfTileUrl(TEMPLATE)).toEqual({ vmin: '', vmax: '', colormap: '' });
    expect(rangeOfTileUrl('no query at all')).toEqual({ vmin: '', vmax: '', colormap: '' });
  });

  it('comes back to the same render and URL, and a bad range makes none', () => {
    const range = { vmin: '0', vmax: '3000', colormap: 'terrain' };
    expect(renderOfRange(range)).toEqual({ rescale: '0,3000', colormapName: 'terrain' });
    expect(rangeOfRender({ rescale: '0,3000', colormapName: 'terrain' })).toEqual(range);
    expect(renderOfRange({ vmin: '', vmax: '1', colormap: '' })).toBeNull();
    expect(renderOfRange({ vmin: '2', vmax: '1', colormap: '' })).toBeNull();
    expect(renderOfRange({ vmin: '1', vmax: '1', colormap: '' })).toBeNull();
  });

  it('restyles the URL from its template: the style is replaced, never added to', () => {
    const once = restyledTileUrl(`${TEMPLATE}&colormap_name=viridis&rescale=180%2C1900`, { rescale: '0,3000', colormapName: 'terrain' });
    expect(once).toBe(`${TEMPLATE}&colormap_name=terrain&rescale=0%2C3000`);
    expect(restyledTileUrl(once, { rescale: '1,2' })).toBe(`${TEMPLATE}&rescale=1%2C2`);
    expect(restyledTileUrl(once, {})).toBe(TEMPLATE);
    expect(restyledTileUrl(TEMPLATE, { rescale: '1,2' })).toBe(`${TEMPLATE}&rescale=1%2C2`);
  });

  it('keeps the band (`bidx`) of a result when the style is replaced, and sets it from the place in the file', () => {
    const second = bandTileUrl(TEMPLATE, 1, { rescale: '0,1', colormapName: 'greys' });
    expect(second).toBe(`${TEMPLATE}&bidx=2&colormap_name=greys&rescale=0%2C1`);
    expect(restyledTileUrl(second, { rescale: '1,2' })).toBe(`${TEMPLATE}&bidx=2&rescale=1%2C2`);
    expect(restyledTileUrl(second, {})).toBe(`${TEMPLATE}&bidx=2`);
    expect(bandTileUrl(second, 0, {})).toBe(`${TEMPLATE}&bidx=1`);
    expect(rangeOfTileUrl(second)).toEqual({ vmin: '0', vmax: '1', colormap: 'greys' });
  });

  it('has the default of the statistics for "auto", the range of the panel without them, none for whole numbers', () => {
    expect(defaultRange({ dataType: 'float32', stats: DEM }, DEFAULT_RANGE)).toEqual({ vmin: '180', vmax: '1900', colormap: 'viridis' });
    expect(defaultRange({ dataType: 'float32', stats: null }, { vmin: '0', vmax: '2', colormap: 'plasma' })).toEqual({ vmin: '0', vmax: '2', colormap: 'plasma' });
    expect(defaultRange({ dataType: 'uint16', stats: DEM }, DEFAULT_RANGE)).toBeNull();
    expect(defaultRange({ dataType: null, stats: DEM }, DEFAULT_RANGE)).toBeNull();
  });
});

describe('the bands of a result (NM4-43e PR 2)', () => {
  const band = (name: unknown, minimum: number, maximum: number) => ({ name, statistics: { count: 9, minimum, maximum } });
  const steps = [{ op: 'band_math', params: { expression: 'a', name: 'ndvi' } }, { op: 'mask', params: { source: 'scl' } }];

  it('keeps the order of the file and the name of each band', () => {
    expect(resultBands({ bands: [band('ndvi', -1, 1), band('red', 0, 1)] }, { steps }).map((b) => b.name)).toEqual(['ndvi', 'red']);
  });

  it('gives a band with no name an empty one, and a result without bands none', () => {
    expect(resultBands({ bands: [band(7, 0, 1)] }, null)[0].name).toBe('');
    expect(resultBands({}, null)).toEqual([]);
    expect(resultBands(undefined, null)).toEqual([]);
    expect(resultBands({ bands: 'x' }, null)).toEqual([]);
  });

  it('leaves the statistics of a band without a valid pixel empty', () => {
    expect(resultBands({ bands: [{ name: 'a', statistics: { count: 0, minimum: 1, maximum: 2 } }] }, null)[0].stats).toBeNull();
  });

  it('judges the band by the steps of the order when it is known, else by the property of the job', () => {
    const bands = { bands: [band('ndvi', -1, 1), band('red', 0, 1)], 'processing:expression': {} };
    expect(resultBands(bands, { steps }).map((b) => b.stats?.expression)).toEqual([true, false]);
    expect(resultBands(bands, null).map((b) => b.stats?.expression)).toEqual([true, true]);
  });

  it('draws a band with the range saved for it, a result of one band with the range of the job', () => {
    const own = { vmin: '0', vmax: '1', colormap: 'greys' };
    const job = { range: own, bandRanges: { red: { vmin: '2', vmax: '3', colormap: '' } } };
    const two = resultBands({ bands: [band('ndvi', 0, 1), band('red', 0, 1)] }, null);
    expect(ownRangeOf(job, two, 0)).toBeNull(); // the range of the job is for a result of one band
    expect(ownRangeOf(job, two, 1)).toEqual({ vmin: '2', vmax: '3', colormap: '' });
    expect(ownRangeOf(job, two, 5)).toBeNull();
    expect(ownRangeOf(job, two.slice(0, 1), 0)).toEqual(own);
    expect(ownRangeOf(job, [], 0)).toEqual(own);
  });
});

describe('the band a result layer starts with (Otto, 31.10.2026)', () => {
  const bands = ['red', 'ndvi', 'ndwi', 'green'].map((name) => ({ name, stats: null }));
  const order = (...names: string[]) => ({ steps: names.map((name) => ({ op: 'band_math', params: { expression: 'a', name } })) });

  it('is the band the preview showed when the job was started, if the result has it', () => {
    expect(startPlaceOf(bands, order('ndvi', 'ndwi'), 'green')).toBe(3);
    expect(startPlaceOf(bands, null, 'ndvi')).toBe(1);
  });

  it('is the last result of the order where that band is unknown or not in the result', () => {
    expect(startPlaceOf(bands, order('ndvi', 'ndwi'), null)).toBe(2);
    expect(startPlaceOf(bands, order('ndvi', 'ndwi'), 'blue')).toBe(2);
    expect(startPlaceOf(bands, order('ndvi', 'gone'), null)).toBe(1);
  });

  it('is the first band without a result of Band math, or without the order', () => {
    expect(startPlaceOf(bands, { steps: [{ op: 'mask', params: { source: 'scl' } }] }, null)).toBe(0);
    expect(startPlaceOf(bands, null, null)).toBe(0);
    expect(startPlaceOf([], null, 'x')).toBe(0);
  });
});
