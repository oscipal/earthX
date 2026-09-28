// searchPlaces/placeAoi (M3-07b): `fetch` stubbed directly (same pattern as
// aoiFile.test.ts) so a change to geocodePlace's own request shape is still
// exercised here too. Every place name and coordinate below is invented.

import { afterEach, describe, expect, it, vi } from 'vitest';

import type { PlaceResult } from './api';
import { PLACE_SEARCH_PROVENANCE, placeAoi, searchPlaces } from './placeSearch';

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: 'Error',
    headers: new Headers(headers),
    json: async () => body,
  } as Response;
}

function nonJsonErrorResponse(status: number, statusText: string, headers: Record<string, string> = {}): Response {
  return {
    ok: false,
    status,
    statusText,
    headers: new Headers(headers),
    json: async () => {
      throw new Error('not json');
    },
  } as unknown as Response;
}

const BERLIN_POLYGON: GeoJSON.Polygon = {
  type: 'Polygon',
  coordinates: [[[13.0, 52.3], [13.8, 52.3], [13.8, 52.7], [13.0, 52.7], [13.0, 52.3]]],
};

function hit(overrides: Partial<PlaceResult> = {}): PlaceResult {
  return {
    name: 'Neuland',
    display_name: 'Neuland, Testland',
    kind: 'boundary/administrative',
    bbox: [13.0, 52.3, 13.8, 52.7],
    outline: BERLIN_POLYGON,
    outline_simplified: false,
    ...overrides,
  };
}

function fullResponse(results: PlaceResult[]): unknown {
  return {
    results,
    attribution: '© OpenStreetMap contributors',
    attribution_url: 'https://www.openstreetmap.org/copyright',
    license: 'ODbL-1.0',
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('searchPlaces — request', () => {
  it('POSTs to /geocode with exactly {"q": …} as JSON, the text in no URL', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, fullResponse([]))));
    await searchPlaces('Neuland');
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe('/geocode');
    expect(init?.method).toBe('POST');
    expect(init?.body).toBe(JSON.stringify({ q: 'Neuland' }));
  });
});

describe('searchPlaces — success', () => {
  it('returns the hits, attribution and attribution URL unchanged', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, fullResponse([hit()]))));
    const result = await searchPlaces('Neuland');
    expect(result.error).toBeUndefined();
    expect(result.results).toEqual([hit()]);
    expect(result.attribution).toBe('© OpenStreetMap contributors');
    expect(result.attributionUrl).toBe('https://www.openstreetmap.org/copyright');
  });

  it('returns an empty list with attribution still present for "no hit"', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, fullResponse([]))));
    const result = await searchPlaces('bxlxrghqz');
    expect(result.results).toEqual([]);
    expect(result.attribution).toBe('© OpenStreetMap contributors');
  });

  it('keeps several hits in the order the route sent them', async () => {
    const hits = [hit({ name: 'A' }), hit({ name: 'B' }), hit({ name: 'C' })];
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, fullResponse(hits))));
    const result = await searchPlaces('a');
    expect(result.results?.map((r) => r.name)).toEqual(['A', 'B', 'C']);
  });
});

describe('searchPlaces — malformed answers (defence, not a second geometry check)', () => {
  it('rejects an answer whose "results" is missing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, { attribution: 'x' })));
    const result = await searchPlaces('a');
    expect(result.error).toBe('Place search returned an answer that could not be read.');
  });

  it('rejects an answer whose "results" is not an array', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, { results: null })));
    const result = await searchPlaces('a');
    expect(result.error).toBe('Place search returned an answer that could not be read.');
  });

  it('drops a hit with a bbox of only three values', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(200, fullResponse([hit({ bbox: [1, 2, 3] as never })]))),
    );
    const result = await searchPlaces('a');
    expect(result.results).toEqual([]);
  });

  it('drops a hit whose bbox is a string, not numbers', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(200, fullResponse([hit({ bbox: '1,2,3,4' as never })]))),
    );
    const result = await searchPlaces('a');
    expect(result.results).toEqual([]);
  });

  it('drops a hit whose bbox carries a NaN', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(200, fullResponse([hit({ bbox: [1, Number.NaN, 3, 4] })])),
      ),
    );
    const result = await searchPlaces('a');
    expect(result.results).toEqual([]);
  });

  it('turns an outline that is a LineString into null, keeping the rest of the hit', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          200,
          fullResponse([hit({ outline: { type: 'LineString', coordinates: [[0, 0], [1, 1]] } as never })]),
        ),
      ),
    );
    const result = await searchPlaces('a');
    expect(result.results).toEqual([hit({ outline: null })]);
  });

  it('turns an outline with no "type" into null', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(200, fullResponse([hit({ outline: {} as never })]))),
    );
    const result = await searchPlaces('a');
    expect(result.results).toEqual([hit({ outline: null })]);
  });
});

describe('searchPlaces — error mapping', () => {
  it('maps a 422 with a detail string', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(422, { detail: 'search text is empty' })));
    const result = await searchPlaces('');
    expect(result.error).toBe('Could not search for this place: search text is empty.');
  });

  it('maps a 422 with an unreadable detail (FastAPI validation list)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(422, { detail: [{ msg: 'field required' }] })));
    const result = await searchPlaces('a');
    expect(result.error).toBe('Could not search for this place.');
  });

  it('maps a 503 with Retry-After as "busy, try again shortly"', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(503, { detail: 'place search is rate-limited, try again shortly' }, { 'Retry-After': '2' })),
    );
    const result = await searchPlaces('a');
    expect(result.error).toBe('Place search is busy. Please try again in a few seconds.');
  });

  it('maps a 503 without Retry-After as "not enabled"', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(503, { detail: 'place search is not available' })),
    );
    const result = await searchPlaces('a');
    expect(result.error).toBe('Place search is not enabled on this server.');
  });

  it('maps a 502 as "did not answer"', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(nonJsonErrorResponse(502, 'Bad Gateway')));
    const result = await searchPlaces('a');
    expect(result.error).toBe('The place search service did not answer. Please try again.');
  });

  it('maps a 504 the same way as a 502', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(nonJsonErrorResponse(504, 'Gateway Timeout')));
    const result = await searchPlaces('a');
    expect(result.error).toBe('The place search service did not answer. Please try again.');
  });

  it('maps any other status generically, naming it', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(nonJsonErrorResponse(500, 'Internal Server Error')));
    const result = await searchPlaces('a');
    expect(result.error).toBe('Place search failed (500). Please try again.');
  });

  it('maps a network failure without touching the status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    const result = await searchPlaces('a');
    expect(result.error).toBe('Could not reach the server for place search.');
  });
});

describe('placeAoi — F1: outline where there is one, else the bbox; always with provenance', () => {
  it('takes the outline as-is when there is one, carrying provenance in its properties', () => {
    const geom = placeAoi(hit());
    expect(geom).toEqual({ ...BERLIN_POLYGON, properties: PLACE_SEARCH_PROVENANCE });
  });

  it('takes a MultiPolygon outline as-is', () => {
    const multi: GeoJSON.MultiPolygon = { type: 'MultiPolygon', coordinates: [BERLIN_POLYGON.coordinates] };
    const geom = placeAoi(hit({ outline: multi }));
    expect(geom).toEqual({ ...multi, properties: PLACE_SEARCH_PROVENANCE });
  });

  it('falls back to a rectangle from the bbox when there is no outline (a point or line hit)', () => {
    const geom = placeAoi(hit({ outline: null, bbox: [10, 50, 10.001, 50.001] }));
    expect(geom).toEqual({
      type: 'Polygon',
      coordinates: [[[10, 50], [10.001, 50], [10.001, 50.001], [10, 50.001], [10, 50]]],
      properties: PLACE_SEARCH_PROVENANCE,
    });
  });
});
