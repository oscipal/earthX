import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  buildSearchBody,
  buildStatisticsUrl,
  buildTileTemplate,
  errorDetail,
  fetchItem,
  HttpError,
  nextTokenFrom,
  searchItems,
} from './api';

describe('buildSearchBody', () => {
  it('carries the collection, bbox, datetime range, limit and token', () => {
    const body = buildSearchBody({
      collection: 'sentinel-2-c1-l2a',
      bbox: [10, 47, 11, 48],
      datetime: '2026-07-01T00:00:00Z/2026-07-31T23:59:59Z',
      limit: 100,
      token: 'next:abc',
    });
    expect(body).toEqual({
      collections: ['sentinel-2-c1-l2a'],
      bbox: [10, 47, 11, 48],
      datetime: '2026-07-01T00:00:00Z/2026-07-31T23:59:59Z',
      limit: 100,
      token: 'next:abc',
    });
  });

  it('carries intersects instead of bbox for a point or polygon AOI (M3-08)', () => {
    const point: GeoJSON.Point = { type: 'Point', coordinates: [10, 49] };
    const body = buildSearchBody({ collection: 'sentinel-2-c1-l2a', intersects: point });
    expect(body.intersects).toBe(point);
    expect(body.bbox).toBeUndefined();
  });

  it('omits optional fields entirely rather than sending them empty', () => {
    const body = buildSearchBody({ collection: 'sentinel-2-c1-l2a' });
    expect(Object.keys(body)).toEqual(['collections']);
  });
});

describe('nextTokenFrom', () => {
  it('reads the token out of a POST-shaped next links body (M3-08 — every search goes over POST now)', () => {
    const links = [
      { rel: 'self', href: 'https://example.test/stac/search' },
      { rel: 'next', href: 'https://example.test/stac/search', method: 'POST', body: { collections: ['x'], token: 'next:abc' } },
    ];
    expect(nextTokenFrom(links)).toBe('next:abc');
  });

  it('falls back to a GET-shaped hrefs query string', () => {
    const links = [
      { rel: 'self', href: 'https://example.test/stac/search?collections=x' },
      { rel: 'next', href: 'https://example.test/stac/search?collections=x&token=next%3Aabc' },
    ];
    expect(nextTokenFrom(links)).toBe('next:abc');
  });

  it('is null when there is no next link', () => {
    expect(nextTokenFrom([{ rel: 'self', href: 'https://example.test/stac/search' }])).toBeNull();
    expect(nextTokenFrom(undefined)).toBeNull();
  });
});

describe('searchItems', () => {
  function jsonResponse(status: number, body: unknown): Response {
    return { ok: status >= 200 && status < 300, status, statusText: '', json: async () => body } as Response;
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends the search as a POST body, not a GET query string (M3-08 F7a)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(200, { features: [], numberReturned: 0 })),
    );
    const polygon: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[8, 47], [12, 47], [8, 51], [8, 47]]] };
    await searchItems({ collection: 'sentinel-2-c1-l2a', intersects: polygon });
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe('/stac/search');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual({
      collections: ['sentinel-2-c1-l2a'],
      intersects: polygon,
    });
  });
});

describe('buildTileTemplate', () => {
  it('carries the mandatory asset and leaves {z}/{x}/{y} literal (adr/0001 Z4)', () => {
    const url = buildTileTemplate('sentinel-2-c1-l2a', 'S2A_1', 'visual');
    expect(url).toContain('/collections/sentinel-2-c1-l2a/items/S2A_1/tiles/WebMercatorQuad/{z}/{x}/{y}');
    const params = new URL(url, 'http://localhost').searchParams;
    expect(params.get('asset')).toBe('visual');
  });

  it('encodes dataset and item ids used as path segments', () => {
    const url = buildTileTemplate('a b', 'c/d', 'visual');
    expect(url).toContain('/collections/a%20b/items/c%2Fd/tiles/');
  });

  it("carries a Zarr group asset key back out exactly as it went in", () => {
    // `SR_10m:b04,b03,b02` is one asset key: the group the item advertises plus
    // the variables to composite (adr/0007 §12.11). The tiler splits it on the
    // registry's separator, so a key that arrives re-encoded — or decoded twice
    // — names a variable nobody has. Z4 as well: the same URL, the same image.
    const key = 'SR_10m:b04,b03,b02';
    const url = buildTileTemplate('sentinel-2-l2a-zarr3', 'S2B_1', key);
    expect(new URL(url, 'http://localhost').searchParams.get('asset')).toBe(key);
  });
});

describe('buildStatisticsUrl', () => {
  it('names the asset it asks statistics for', () => {
    const url = buildStatisticsUrl('sentinel-2-c1-l2a', 'S2A_1', 'visual');
    expect(url).toBe('/collections/sentinel-2-c1-l2a/items/S2A_1/statistics?asset=visual');
  });
});

describe('errorDetail', () => {
  it('reads FastAPI\'s {detail} shape', () => {
    expect(errorDetail({ detail: 'a search spanning more than one source is not supported yet' }, 400, 'Bad Request')).toBe(
      'a search spanning more than one source is not supported yet',
    );
  });

  it('reads the OGC API {code, description} shape', () => {
    expect(errorDetail({ code: 'NotFound', description: 'Collection x does not exist.' }, 404, 'Not Found')).toBe(
      'Collection x does not exist.',
    );
  });

  it('falls back to the status line for a body with neither shape', () => {
    expect(errorDetail({}, 502, 'Bad Gateway')).toBe('502 Bad Gateway');
    expect(errorDetail(null, 502, 'Bad Gateway')).toBe('502 Bad Gateway');
  });

  it('the multi-collection 400 arrives as a readable message', () => {
    const body = { detail: 'a search spanning more than one source is not supported yet; name exactly one collection' };
    expect(errorDetail(body, 400, 'Bad Request')).toBe(
      'a search spanning more than one source is not supported yet; name exactly one collection',
    );
  });
});

describe('fetchItem', () => {
  function jsonResponse(status: number, body: unknown): Response {
    return { ok: status >= 200 && status < 300, status, statusText: '', json: async () => body } as Response;
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('encodes dataset and item id into the STAC item route', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, { id: 'a/b' })));
    await fetchItem('a b', 'c/d');
    const url = vi.mocked(fetch).mock.calls[0][0] as string;
    expect(url).toBe('/stac/collections/a%20b/items/c%2Fd');
  });

  it('returns undefined for a 404 — an unknown name, not an error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(404, { detail: 'Not Found' })));
    expect(await fetchItem('sentinel-2-c1-l2a', 'does-not-exist')).toBeUndefined();
  });

  it('returns the item on a 200', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, { id: 'S2A_1', properties: {}, assets: {} })));
    const item = await fetchItem('sentinel-2-c1-l2a', 'S2A_1');
    expect(item?.id).toBe('S2A_1');
  });

  it('throws an HttpError carrying the status for anything else, e.g. an invalid name', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(400, { detail: 'invalid characters' })));
    await expect(fetchItem('sentinel-2-c1-l2a', 'bad name')).rejects.toMatchObject({
      status: 400,
      message: 'invalid characters',
    });
    await expect(fetchItem('sentinel-2-c1-l2a', 'bad name')).rejects.toBeInstanceOf(HttpError);
  });
});
