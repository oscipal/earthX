import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  type CoverageParams,
  buildCoverageUrl,
  buildMosaicTileTemplate,
  buildSearchBody,
  buildStatisticsUrl,
  buildTileTemplate,
  downloadCrop,
  errorDetail,
  fetchCoverage,
  fetchItem,
  fetchMosaicTileJson,
  HttpError,
  nextTokenFrom,
  parseAreaStatistics,
  postAreaStatistics,
  searchAllPages,
  searchItems,
  uploadAoi,
} from './api';
import { tileSizeOf } from './tileSize';

describe('buildSearchBody', () => {
  it('carries the collections, bbox, datetime range, limit and token', () => {
    const body = buildSearchBody({
      collections: ['sentinel-2-c1-l2a'],
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

  it('carries more than one collection at once (M3-13 — the backend now answers a mixed page)', () => {
    const body = buildSearchBody({ collections: ['sentinel-2-c1-l2a', 'cop-dem-glo-30'] });
    expect(body.collections).toEqual(['sentinel-2-c1-l2a', 'cop-dem-glo-30']);
  });

  it('carries intersects instead of bbox for a point or polygon AOI (M3-08)', () => {
    const point: GeoJSON.Point = { type: 'Point', coordinates: [10, 49] };
    const body = buildSearchBody({ collections: ['sentinel-2-c1-l2a'], intersects: point });
    expect(body.intersects).toBe(point);
    expect(body.bbox).toBeUndefined();
  });

  it('omits optional fields entirely rather than sending them empty', () => {
    const body = buildSearchBody({ collections: ['sentinel-2-c1-l2a'] });
    expect(Object.keys(body)).toEqual(['collections']);
  });

  it('never sends the shared query, CQL2 filter, sortby or fields extensions (M3-13 F5, DS-02c)', () => {
    // Measured against the real API (M3-13 plan §2.2): they are silently
    // dropped on a federated collection, so the backend refuses them by name
    // (`_DISALLOWED_QUERY_KEYS`) — `SearchQuery` has no field for them. The
    // filters go as `query_by_collection`, below.
    const body = buildSearchBody({
      collections: ['sentinel-2-c1-l2a'],
      queryByCollection: { 'sentinel-2-c1-l2a': { 'eo:cloud_cover': { lte: 20 } } },
    });
    for (const key of ['query', 'filter', 'sortby', 'fields']) expect(body).not.toHaveProperty(key);
  });

  it('carries the filters of each dataset as query_by_collection (DS-02c)', () => {
    const body = buildSearchBody({
      collections: ['optical', 'radar'],
      queryByCollection: {
        optical: { 'eo:cloud_cover': { gte: 5, lte: 20 }, platform: { in: ['sat-a'] } },
        radar: { 'sat:relative_orbit': { gte: 22, lte: 22 } },
      },
    });
    expect(body.query_by_collection).toEqual({
      optical: { 'eo:cloud_cover': { gte: 5, lte: 20 }, platform: { in: ['sat-a'] } },
      radar: { 'sat:relative_orbit': { gte: 22, lte: 22 } },
    });
  });

  it('leaves query_by_collection out when no dataset has a filter, so such a search keeps its body', () => {
    expect(buildSearchBody({ collections: ['optical'], queryByCollection: {} })).toEqual({ collections: ['optical'] });
    expect(buildSearchBody({ collections: ['optical'], queryByCollection: undefined })).toEqual({ collections: ['optical'] });
  });
});

describe('buildCoverageUrl', () => {
  it('carries the dataset, the level, the box and the dates', () => {
    const url = new URL(
      buildCoverageUrl({ datasetId: 'optical', zoom: 4, bbox: [10, 47, 11, 48], datetime: '2026-07-01T00:00:00Z/..' }),
      'http://localhost',
    );
    expect(url.pathname).toBe('/coverage/optical');
    expect(Object.fromEntries(url.searchParams)).toEqual({
      zoom: '4',
      bbox: '10,47,11,48',
      datetime: '2026-07-01T00:00:00Z/..',
    });
  });

  it('carries the filters of the dataset as JSON in query (DS-02b)', () => {
    const query = { 'eo:cloud_cover': { lte: 20 }, platform: { in: ['sat-a', 'sat-b'] } };
    const url = new URL(buildCoverageUrl({ datasetId: 'optical', zoom: 4, query }), 'http://localhost');
    expect(JSON.parse(url.searchParams.get('query')!)).toEqual(query);
  });

  it('omits query without filters, and has no max_cloud_cover any more', () => {
    for (const query of [undefined, {}]) {
      const url = new URL(buildCoverageUrl({ datasetId: 'optical', zoom: 4, query }), 'http://localhost');
      expect([...url.searchParams.keys()]).toEqual(['zoom']);
    }
  });
  // NM4-57 (M4 Q8): the box of an AOI is never in a URL.
  it('never carries the box of an AOI', () => {
    const url = buildCoverageUrl({ datasetId: 'optical', zoom: 4, aoiBbox: [11.31234, 47.81234, 11.51234, 47.91234] });
    expect(url).not.toContain('11.31234');
    expect(new URL(url, 'http://localhost').searchParams.has('bbox')).toBe(false);
  });
});

describe('fetchCoverage', () => {
  afterEach(() => vi.unstubAllGlobals());

  const answer = { ok: true, status: 200, json: async () => ({}) } as Response;

  it('asks an AOI by POST: the box and the filters in the body, nothing in the URL', async () => {
    const fetchMock = vi.fn(async () => answer);
    vi.stubGlobal('fetch', fetchMock);
    const query = { 'eo:cloud_cover': { lte: 20 } };

    await fetchCoverage({
      datasetId: 'optical',
      zoom: 9,
      aoiBbox: [11.31234, 47.81234, 11.51234, 47.91234],
      datetime: '2026-07-01T00:00:00Z/..',
      query,
    });

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/coverage/optical');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({
      zoom: 9,
      bbox: [11.31234, 47.81234, 11.51234, 47.91234],
      datetime: '2026-07-01T00:00:00Z/..',
      query,
    });
  });

  it('does not take a map extent and the box of an AOI together (checked by the type)', () => {
    // @ts-expect-error the extent goes in the URL, the AOI in the body: one question has one of them
    const both: CoverageParams = { datasetId: 'optical', zoom: 4, bbox: [0, 0, 1, 1], aoiBbox: [0, 0, 1, 1] };
    expect(both.zoom).toBe(4);
  });

  it('asks a map extent by GET, as before', async () => {
    const fetchMock = vi.fn(async () => answer);
    vi.stubGlobal('fetch', fetchMock);

    await fetchCoverage({ datasetId: 'optical', zoom: 6, bbox: [-180, -85, 180, 85] });

    expect(fetchMock.mock.calls[0]).toEqual(['/coverage/optical?zoom=6&bbox=-180%2C-85%2C180%2C85']);
  });

  it('leaves a body without the optional fields out', async () => {
    const fetchMock = vi.fn(async () => answer);
    vi.stubGlobal('fetch', fetchMock);

    await fetchCoverage({ datasetId: 'optical', zoom: 3, aoiBbox: [0, 0, 1, 1], query: {} });

    const init = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(JSON.parse(String(init.body))).toEqual({ zoom: 3, bbox: [0, 0, 1, 1] });
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
    await searchItems({ collections: ['sentinel-2-c1-l2a'], intersects: polygon });
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
    const url = buildTileTemplate('synthetic-zarr', 'S2B_1', key);
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

  // M4-11b-2: the dialog offers an export job from the status and the header.
  function refusal(status: number, headers: Record<string, string>): Response {
    return new Response(JSON.stringify({ detail: 'This download would be about 2 GB.' }), {
      status,
      headers: { 'Content-Type': 'application/json', ...headers },
    });
  }

  it.each([
    ['available', 'available'],
    ['too-large', 'too-large'],
    ['maybe', undefined],
    [null, undefined],
  ])('a 413 with X-Export-Job %s throws an HttpError with exportJob %s and the detail', async (header, expected) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(refusal(413, header === null ? {} : { 'X-Export-Job': header })));
    const error = await downloadCrop(request).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(HttpError);
    expect(error).toMatchObject({ status: 413, detail: 'This download would be about 2 GB.', exportJob: expected });
  });

  it('reads X-Export-Job only on a 413', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(refusal(400, { 'X-Export-Job': 'available' })));
    const error = await downloadCrop(request).catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 400, exportJob: undefined });
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

  it('POSTs the file itself as the body and its extension as a ?filename= query parameter', async () => {
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

  // NM4-57: the name of a file often names a person or a place and a URL stands in access logs.
  it.each([
    ['Haus Müller & Söhne #3.kml', 'aoi.kml'],
    ['Flurstück 12/4 Schmidt.GeoJSON', 'aoi.GeoJSON'],
    ['gebiet.zip', 'aoi.zip'],
    ['no extension', 'aoi'],
    ['ends with a dot.', 'aoi'],
    ['name.with spaces', 'aoi'],
    ['x.' + 'a'.repeat(20), 'aoi'],
  ])('sends nothing of the name %j but its extension', async (name, sent) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, { type: 'Point', coordinates: [0, 0] })));

    await uploadAoi(new File([], name), name);

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(`/aoi/upload?filename=${sent}`);
    expect(String(url)).not.toMatch(/Haus|M%C3%BCller|Schmidt|Flurst|gebiet|spaces/);
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

// M3-07b: `jsonOrThrow`'s `HttpError` carries the raw `Retry-After` header,
// which `placeSearch.ts` uses to tell a briefly-busy 503 apart from one that
// means place search is simply not enabled. Exercised through `uploadAoi`
// (any `jsonOrThrow` caller does) rather than duplicating a whole request —
// the header handling lives in `jsonOrThrow` itself, not per-route.
describe('HttpError.retryAfter', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('is set from a Retry-After response header', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        statusText: 'Service Unavailable',
        headers: new Headers({ 'Retry-After': '5' }),
        json: async () => ({ detail: 'place search is not available' }),
      } as unknown as Response),
    );
    await expect(uploadAoi(new File([], 'x.geojson'), 'x.geojson')).rejects.toMatchObject({ retryAfter: '5' });
  });

  it('is undefined when the response has no such header', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        statusText: 'Service Unavailable',
        headers: new Headers(),
        json: async () => ({ detail: 'place search is not available' }),
      } as unknown as Response),
    );
    await expect(uploadAoi(new File([], 'x.geojson'), 'x.geojson')).rejects.toMatchObject({ retryAfter: undefined });
  });

  it('is undefined when the mocked response carries no headers object at all (older test doubles)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: async () => ({}),
      } as unknown as Response),
    );
    await expect(uploadAoi(new File([], 'x.geojson'), 'x.geojson')).rejects.toMatchObject({ retryAfter: undefined });
  });
});

// M4-11b-2: the `type` of a problem document picks the text of a failed job.
describe('HttpError.type', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function answer(body: unknown) {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(body), { status: 500, headers: { 'Content-Type': 'application/problem+json' } }),
      ),
    );
  }

  it('is the type and title of a problem document', async () => {
    answer({ type: 'urn:earthx:job-failed:runtime_exceeded', title: 'The job took longer than allowed', detail: 'x' });
    await expect(uploadAoi(new File([], 'x.geojson'), 'x.geojson')).rejects.toMatchObject({
      type: 'urn:earthx:job-failed:runtime_exceeded',
      title: 'The job took longer than allowed',
      exportJob: undefined,
    });
  });

  it('is undefined when the body has no type, or one that is not a string', async () => {
    answer({ type: 7, detail: 'x' });
    await expect(uploadAoi(new File([], 'x.geojson'), 'x.geojson')).rejects.toMatchObject({ type: undefined });
  });
});

describe('ignored_filters_by_collection and incomplete_collections (M3-10)', () => {
  function jsonResponse(body: unknown): Response {
    return { ok: true, status: 200, statusText: '', json: async () => body } as Response;
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('reads the per-collection breakdown next to the flat list', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          features: [],
          numberReturned: 0,
          ignored_filters: ['datetime'],
          ignored_filters_by_collection: { 'cop-dem-glo-30': ['datetime'] },
        }),
      ),
    );
    const page = await searchItems({ collections: ['a', 'cop-dem-glo-30'] });
    expect(page.ignoredFilters).toEqual(['datetime']);
    expect(page.ignoredFiltersByCollection).toEqual({ 'cop-dem-glo-30': ['datetime'] });
  });

  it.each([
    ['missing', undefined],
    ['null', null],
    ['a list', ['datetime']],
    ['a string', 'datetime'],
  ])('reads it as empty when it is %s', async (_case, value) => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ features: [], numberReturned: 0, ignored_filters_by_collection: value })),
    );
    expect((await searchItems({ collections: ['a'] })).ignoredFiltersByCollection).toEqual({});
  });

  it('skips entries whose value is not a list of strings', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          features: [],
          numberReturned: 0,
          ignored_filters_by_collection: { good: ['datetime', 7], bad: 'datetime', worse: { a: 1 }, none: [7] },
        }),
      ),
    );
    expect((await searchItems({ collections: ['a'] })).ignoredFiltersByCollection).toEqual({ good: ['datetime'] });
  });

  it('collects the breakdown across pages; the first page naming a collection wins', async () => {
    const pages = [
      {
        features: [{ id: 'a' }],
        numberReturned: 1,
        links: [{ rel: 'next', href: '/stac/search', body: { token: 't2' } }],
        ignored_filters_by_collection: { dem: ['datetime'] },
        incomplete_collections: [{ collection: 'zarr-source', reason: 'timeout' }],
      },
      {
        features: [{ id: 'b' }],
        numberReturned: 1,
        ignored_filters_by_collection: { dem: ['other'], later: ['datetime'] },
        incomplete_collections: [{ collection: 'zarr-source', reason: 'unreachable' }],
      },
    ];
    const fetchMock = vi.fn();
    for (const page of pages) fetchMock.mockResolvedValueOnce(jsonResponse(page));
    vi.stubGlobal('fetch', fetchMock);
    const result = await searchAllPages({ collections: ['dem', 'later', 'zarr-source'] }, 300);
    expect(result.features).toHaveLength(2);
    expect(result.ignoredFiltersByCollection).toEqual({ dem: ['datetime'], later: ['datetime'] });
    expect(result.incompleteCollections).toEqual([{ collection: 'zarr-source', reason: 'timeout' }]);
  });

  // M3-10b: "Load more" continues a walk with the token the last one left over.
  it('starts from a given token and hands back the one left once maxItems stopped it', async () => {
    const page = (ids: string[], token: string | null) => ({
      features: ids.map((id) => ({ id })),
      numberReturned: ids.length,
      links: token ? [{ rel: 'next', href: '/stac/search', body: { token } }] : [],
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(page(['a', 'b'], 't3')))
      .mockResolvedValueOnce(jsonResponse(page(['c', 'd'], 't4')));
    vi.stubGlobal('fetch', fetchMock);
    const result = await searchAllPages({ collections: ['x', 'y'], bbox: [1, 2, 3, 4] }, 3, 't2');
    const bodies = fetchMock.mock.calls.map(([, init]) => JSON.parse((init as RequestInit).body as string));
    expect(bodies.map((b) => b.token)).toEqual(['t2', 't3']);
    expect(bodies[0]).toMatchObject({ collections: ['x', 'y'], bbox: [1, 2, 3, 4] });
    expect(result.features.map((f) => f.id)).toEqual(['a', 'b', 'c', 'd']);
    expect(result.nextToken).toBe('t4');
  });

  it("hands back the last page's open collections", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({ features: [{ id: 'a' }], numberReturned: 1, links: [{ rel: 'next', href: '/stac/search', body: { token: 't2' } }], open_collections: ['x', 'y'] }),
      )
      .mockResolvedValueOnce(jsonResponse({ features: [{ id: 'b' }], numberReturned: 1, open_collections: [] }));
    vi.stubGlobal('fetch', fetchMock);
    expect((await searchAllPages({ collections: ['x', 'y'] }, 300)).openCollections).toEqual([]);
  });

  it.each([
    ['missing', undefined, null],
    ['not a list', 'x', null],
    ['a list with other things in it', ['x', 7, null], ['x']],
  ])('reads open_collections %s', async (_case, value, expected) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ features: [], numberReturned: 0, open_collections: value })));
    expect((await searchItems({ collections: ['x'] })).openCollections).toEqual(expected);
  });

  it('hands back no token once the result is complete', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ features: [{ id: 'a' }], numberReturned: 1 })));
    expect((await searchAllPages({ collections: ['x'] }, 300)).nextToken).toBeNull();
  });
});

describe('the mosaic of a time step (M4-17)', () => {
  it('names the scenes in the URL, sorted, with the asset and the tile placeholders', () => {
    const template = buildMosaicTileTemplate('sentinel-2-c1-l2a', ['S2B_2', 'S2A_1', 'S2A_3'], 'visual');
    expect(template.startsWith('/collections/sentinel-2-c1-l2a/mosaic/tiles/WebMercatorQuad/{z}/{x}/{y}?')).toBe(true);
    const params = new URL(template, 'http://localhost').searchParams;
    expect(params.getAll('item')).toEqual(['S2A_1', 'S2A_3', 'S2B_2']);
    expect(params.getAll('asset')).toEqual(['visual']);
  });

  it('is one URL for one selection, whatever order it was made in', () => {
    expect(buildMosaicTileTemplate('d', ['b', 'a'], 'x')).toBe(buildMosaicTileTemplate('d', ['a', 'b'], 'x'));
  });

  it('carries no area, and escapes what it is given', () => {
    const template = buildMosaicTileTemplate('a b', ['x&y=1', 'z/../w'], 'SR_10m:b04,b03');
    expect(template).toContain('/collections/a%20b/mosaic/');
    const params = new URL(template, 'http://localhost').searchParams;
    expect(params.getAll('item')).toEqual(['x&y=1', 'z/../w']);
    expect([...params.keys()].sort()).toEqual(['asset', 'item', 'item', 'tilesize']);
  });

  it('asks for 512-px tiles, which the tiler takes as 256 or 512 (NM4-29b)', () => {
    expect(new URL(buildMosaicTileTemplate('d', ['a', 'b'], 'x'), 'http://localhost').searchParams.get('tilesize')).toBe('512');
    expect(tileSizeOf(buildMosaicTileTemplate('d', ['a', 'b'], 'x'))).toBe(512);
  });

  it('leaves the TileJSON of the same pass without a size', async () => {
    const urls: string[] = [];
    vi.stubGlobal('fetch', async (url: string) => {
      urls.push(url);
      return { ok: true, status: 200, statusText: '', json: async () => ({ bounds: [0, 0, 1, 1], minzoom: 8, maxzoom: 19, 'earthx:order': ['a'] }) } as Response;
    });
    await fetchMosaicTileJson('d', ['a', 'b'], 'x');
    vi.unstubAllGlobals();
    expect(urls[0]).not.toContain('tilesize');
  });
});

describe('fetchMosaicTileJson', () => {
  function jsonResponse(status: number, body: unknown): Response {
    return { ok: status >= 200 && status < 300, status, statusText: '', json: async () => body } as Response;
  }

  const TILEJSON = {
    bounds: [10, 47, 12, 48],
    minzoom: 8,
    maxzoom: 19,
    tiles: ['http://internal-host/tiles'],
    'earthx:order': ['B', 'A'],
  };

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('asks the TileJSON route with the same query as the tiles, and reads surface, levels and order', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, TILEJSON)));
    const json = await fetchMosaicTileJson('sentinel-2-c1-l2a', ['B', 'A'], 'visual');
    const url = vi.mocked(fetch).mock.calls[0][0] as string;
    expect(url).toBe('/collections/sentinel-2-c1-l2a/mosaic/WebMercatorQuad/tilejson.json?item=A&item=B&asset=visual');
    const init = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    expect(init.signal).toBeInstanceOf(AbortSignal); // it ends on its own if the tiler never answers
    expect(json).toEqual({ bounds: [10, 47, 12, 48], minzoom: 8, maxzoom: 19, order: ['B', 'A'] });
  });

  it.each([
    ['a refused mosaic', 422, { detail: 'the items are of different passes' }, 'the items are of different passes'],
    ['a missing item cache', 503, { detail: 'mosaic tiles need the item cache' }, 'mosaic tiles need the item cache'],
  ])('throws the tiler\'s reason for %s', async (_name, status, body, message) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(status, body)));
    await expect(fetchMosaicTileJson('d', ['A', 'B'], 'visual')).rejects.toMatchObject({ status, message });
  });

  it.each([
    ['no order', { ...TILEJSON, 'earthx:order': undefined }],
    ['an order of numbers', { ...TILEJSON, 'earthx:order': [1, 2] }],
    ['a short surface', { ...TILEJSON, bounds: [10, 47] }],
    ['a surface of text', { ...TILEJSON, bounds: ['a', 'b', 'c', 'd'] }],
    ['no first level', { ...TILEJSON, minzoom: undefined }],
    ['an infinite last level', { ...TILEJSON, maxzoom: Number.POSITIVE_INFINITY }],
  ])('refuses an answer with %s rather than drawing from it', async (_name, body) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, body)));
    await expect(fetchMosaicTileJson('d', ['A', 'B'], 'visual')).rejects.toThrow(/cannot read/);
  });
});

// NM4-19: the statistics over the AOI of an order, the AOI in the body and nowhere else.
describe('postAreaStatistics', () => {
  const answer = { bands: [{ name: 'b1', unit: 'm', statistics: { minimum: 1, maximum: 2, count: 3 } }, { name: 'b2', statistics: {} }], exact: false, factor: 2 };
  const reply = (status: number, body: unknown) =>
    ({ ok: status < 300, status, statusText: 'x', headers: new Headers(), json: async () => body }) as unknown as Response;
  const order = { recipe_version: 1, aoi: { type: 'Polygon', coordinates: [[[10.4, 50.4], [10.6, 50.4], [10.6, 50.6], [10.4, 50.4]]] }, steps: [] };

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('posts the order as the JSON body to the path of the dataset, with no query', async () => {
    const fetchMock = vi.fn(async () => reply(200, answer));
    vi.stubGlobal('fetch', fetchMock);
    const read = await postAreaStatistics('sentinel-2-c1-l2a', order);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/collections/sentinel-2-c1-l2a/statistics');
    expect(init).toMatchObject({ method: 'POST', headers: { 'Content-Type': 'application/json' } });
    expect(JSON.parse(String(init.body))).toEqual(order);
    expect(read).toEqual({
      bands: [
        { name: 'b1', unit: 'm', statistics: { minimum: 1, maximum: 2, count: 3 } },
        { name: 'b2', unit: null, statistics: {} },
      ],
      exact: false,
      factor: 2,
    });
  });

  it('writes the dataset into the path as one segment, whatever it is called', async () => {
    const fetchMock = vi.fn(async () => reply(200, answer));
    vi.stubGlobal('fetch', fetchMock);
    await postAreaStatistics('a/b?c', order);
    expect(String((fetchMock.mock.calls[0] as unknown[])[0])).toBe('/collections/a%2Fb%3Fc/statistics');
  });

  it.each([
    [413, { detail: 'too many positions' }],
    [422, { detail: 'step 1: expression names unknown band(s)' }],
    [502, {}],
  ])('throws an HttpError for status %s', async (status, body) => {
    vi.stubGlobal('fetch', vi.fn(async () => reply(status, body)));
    await expect(postAreaStatistics('d', order)).rejects.toMatchObject({ status });
  });

  it.each([
    ['no object', null],
    ['no bands', { bands: [], exact: true, factor: 1 }],
    ['bands that are no list', { bands: 'x', exact: true, factor: 1 }],
    ['no statement whether it is exact', { bands: answer.bands, factor: 1 }],
  ])('refuses an answer with %s', (_, body) => {
    expect(() => parseAreaStatistics(body)).toThrow('cannot read');
  });

  it('takes a factor that is no number as 1, and a band that is no object as an empty one', () => {
    expect(parseAreaStatistics({ bands: [null], exact: true, factor: 'x' })).toEqual({
      bands: [{ name: '', unit: null, statistics: {} }],
      exact: true,
      factor: 1,
    });
  });
});
