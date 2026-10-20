import { describe, expect, it } from 'vitest';

import { DEFAULT_RANGE } from './processingPreview';
import { parseTileJson } from './processing';
import {
  isOverview,
  isResultExpired,
  MIN_REMAINING_MS,
  resultGsd,
  resultLayerName,
  resultRender,
  resultTileTemplate,
  tilesHref,
} from './resultLayer';

const ID = 'ZyXwVuTsRqPoNmLkJiHg_-';
const HREF = `/results/${ID}/WebMercatorQuad/tilejson.json`;

describe('the link to the tiles of a result', () => {
  it('is the one path the tiler serves', () => {
    expect(tilesHref({ tiles: { href: HREF } })).toBe(HREF);
  });

  it.each([
    ['no link', {}],
    ['a link without an address', { tiles: {} }],
    ['an address that is not text', { tiles: { href: 5 } }],
    ['another host', { tiles: { href: `https://example.org${HREF}` } }],
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
