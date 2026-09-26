import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  buildSearchBody,
  buildStatisticsUrl,
  buildTileTemplate,
  downloadCrop,
  errorDetail,
  fetchItem,
  HttpError,
  nextTokenFrom,
  searchItems,
  uploadAoi,
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

// M3-18 F8: the backend formulates the download's error text (size cap, item
// cap); this client only has to pass it through unchanged, the same way it
// already does for every other route.
describe('downloadCrop', () => {
  function jsonResponse(status: number, body: unknown): Response {
    return { ok: status >= 200 && status < 300, status, statusText: 'x', json: async () => body } as Response;
  }

  function noJsonResponse(status: number, statusText: string): Response {
    return {
      ok: false,
      status,
      statusText,
      json: async () => {
        throw new SyntaxError('Unexpected end of JSON input');
      },
    } as unknown as Response;
  }

  function blobResponse(headers: Record<string, string> = {}): Response {
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      headers: new Headers(headers),
      blob: async () => new Blob(['x']),
    } as unknown as Response;
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const request = {
    datasetId: 'sentinel-2-c1-l2a',
    groups: [['ITEM1']],
    assets: ['visual'],
    aoi: { type: 'Polygon' as const, coordinates: [] },
  };

  it('a 413 over the output size cap surfaces the backend detail unchanged', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(413, {
          detail: 'This download would be about 403 MB, more than the 200 MB limit. Draw a smaller area or download fewer layers.',
        }),
      ),
    );
    await expect(downloadCrop(request)).rejects.toThrow(
      'This download would be about 403 MB, more than the 200 MB limit. Draw a smaller area or download fewer layers.',
    );
  });

  it('a 413 over the item cap surfaces the backend detail unchanged', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(413, { detail: 'This download covers 26 scenes; at most 25 fit in one download.' }),
      ),
    );
    await expect(downloadCrop(request)).rejects.toThrow('This download covers 26 scenes; at most 25 fit in one download.');
  });

  it('an error response with no JSON body still reads as a plain, English message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(noJsonResponse(503, 'Service Unavailable')));
    await expect(downloadCrop(request)).rejects.toThrow('503 Service Unavailable');
  });

  // Review finding 1: a dropped group has to be visible before the file is
  // even opened — these two headers are how `store.confirmDownload` finds out.
  it('reads X-Total-Groups/X-Skipped-Groups off a successful response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(blobResponse({ 'X-Total-Groups': '3', 'X-Skipped-Groups': '1' })),
    );
    const result = await downloadCrop(request);
    expect(result.totalGroups).toBe(3);
    expect(result.skippedGroups).toBe(1);
    expect(result.blob).toBeInstanceOf(Blob);
  });

  it('treats a missing or malformed count header as 0, never NaN', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(blobResponse()));
    expect(await downloadCrop(request)).toMatchObject({ totalGroups: 0, skippedGroups: 0 });

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(blobResponse({ 'X-Total-Groups': 'not-a-number', 'X-Skipped-Groups': '-1' })),
    );
    expect(await downloadCrop(request)).toMatchObject({ totalGroups: 0, skippedGroups: 0 });
  });
});

// M3-06b: `POST /aoi/upload` (M3-06a) is called with the file's own bytes as the
// raw request body — never `FormData` (plan §6: Starlette's multipart parser
// spools any file part over 1 MiB to disk, `max_part_size` or not).
describe('uploadAoi', () => {
  function jsonResponse(status: number, body: unknown): Response {
    return { ok: status >= 200 && status < 300, status, statusText: '', json: async () => body } as Response;
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('POSTs the file itself as the body and the name as a ?filename= query parameter', async () => {
    const square: GeoJSON.Polygon = {
      type: 'Polygon',
      coordinates: [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, square)));
    const file = new File(['{}'], 'aoi.geojson');

    const geometry = await uploadAoi(file, file.name);

    expect(geometry).toEqual(square);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe('/aoi/upload?filename=aoi.geojson');
    expect(init?.method).toBe('POST');
    expect(init?.body).toBe(file); // the Blob itself, not a FormData wrapper
    expect(new Headers(init?.headers).get('Content-Type')).toBe('application/octet-stream');
  });

  it('percent-encodes spaces and reserved characters in the filename', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, { type: 'Point', coordinates: [0, 0] })));
    const name = 'a b&c#d.kml';

    await uploadAoi(new File([], name), name);

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(`/aoi/upload?filename=${encodeURIComponent(name)}`);
  });

  it('rejects with an HttpError carrying the route detail on a 400', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(400, { detail: 'not valid JSON' })));

    await expect(uploadAoi(new File([], 'x.geojson'), 'x.geojson')).rejects.toMatchObject({
      status: 400,
      detail: 'not valid JSON',
    });
  });

  it('leaves detail undefined for a non-JSON error body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => {
          throw new Error('not json');
        },
      } as unknown as Response),
    );

    await expect(uploadAoi(new File([], 'x.geojson'), 'x.geojson')).rejects.toMatchObject({
      status: 400,
      detail: undefined,
    });
  });
});
