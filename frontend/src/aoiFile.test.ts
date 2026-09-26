// readAoiFile (M3-06b): never parses in the browser any more, only calls
// POST /aoi/upload (M3-06a) and maps the answer. `fetch` is stubbed directly
// (same pattern as api.test.ts) rather than mocking './api', so a change to
// uploadAoi's own request shape is still exercised here too.

import { afterEach, describe, expect, it, vi } from 'vitest';

import { AOI_UPLOAD_MAX_BYTES, readAoiFile } from './aoiFile';

function jsonResponse(status: number, body: unknown): Response {
  return { ok: status >= 200 && status < 300, status, statusText: 'Error', json: async () => body } as Response;
}

function nonJsonErrorResponse(status: number, statusText: string): Response {
  return {
    ok: false,
    status,
    statusText,
    json: async () => {
      throw new Error('not json');
    },
  } as unknown as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('readAoiFile — success', () => {
  it('returns a Polygon unchanged', async () => {
    const square: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]] };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, square)));
    expect(await readAoiFile(new File(['{}'], 'a.geojson'))).toEqual({ geometry: square });
  });

  it('returns a MultiPolygon unchanged', async () => {
    const multi: GeoJSON.MultiPolygon = {
      type: 'MultiPolygon',
      coordinates: [[[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]],
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, multi)));
    expect(await readAoiFile(new File(['{}'], 'a.geojson'))).toEqual({ geometry: multi });
  });

  it('returns a Point unchanged (buffering into a square is the caller’s job)', async () => {
    const point: GeoJSON.Point = { type: 'Point', coordinates: [8, 49] };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, point)));
    expect(await readAoiFile(new File(['{}'], 'a.geojson'))).toEqual({ geometry: point });
  });
});

describe('readAoiFile — error mapping', () => {
  it('maps a 400 with a detail to "Could not use … as an AOI: <detail>."', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(400, { detail: 'not a valid ZIP file' })));
    const result = await readAoiFile(new File(['{}'], 'parcels.zip'));
    expect(result.error).toBe('Could not use "parcels.zip" as an AOI: not a valid ZIP file.');
  });

  it('does not double the full stop when the detail already ends with one', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(400, { detail: 'geometry has no coordinates.' })));
    const result = await readAoiFile(new File(['{}'], 'a.geojson'));
    expect(result.error).toBe('Could not use "a.geojson" as an AOI: geometry has no coordinates.');
  });

  it('maps a 400 with a non-JSON body to the short form, without a colon', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(nonJsonErrorResponse(400, 'Bad Request')));
    const result = await readAoiFile(new File(['{}'], 'a.geojson'));
    expect(result.error).toBe('Could not use "a.geojson" as an AOI.');
  });

  it('maps a 413 from the route the same way as an oversized file caught locally', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(413, { detail: 'too big' })));
    const result = await readAoiFile(new File(['{}'], 'huge.zip'));
    expect(result.error).toBe('"huge.zip" is too large for an AOI (max. 1 MB).');
  });

  it('maps a 500 to a generic retry message naming the status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(nonJsonErrorResponse(500, 'Internal Server Error')));
    const result = await readAoiFile(new File(['{}'], 'a.geojson'));
    expect(result.error).toBe('Uploading "a.geojson" failed (500). Please try again.');
  });

  it('maps a 502 the same way as any other non-400/413 status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(nonJsonErrorResponse(502, 'Bad Gateway')));
    const result = await readAoiFile(new File(['{}'], 'a.geojson'));
    expect(result.error).toBe('Uploading "a.geojson" failed (502). Please try again.');
  });

  it('maps a 422 (e.g. a missing filename query parameter) the same way as any other status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(422, { detail: [{ msg: 'field required' }] })));
    const result = await readAoiFile(new File(['{}'], 'a.geojson'));
    expect(result.error).toBe('Uploading "a.geojson" failed (422). Please try again.');
  });

  it('maps a fetch/network failure without touching the status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    const result = await readAoiFile(new File(['{}'], 'a.geojson'));
    expect(result.error).toBe('Could not reach the server to read "a.geojson".');
  });

  it('rejects an unexpected 200 answer (missing type)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, {})));
    const result = await readAoiFile(new File(['{}'], 'a.geojson'));
    expect(result.error).toBe('The server returned no usable AOI for "a.geojson".');
  });

  it('rejects an unexpected 200 answer (a LineString, which the route itself never returns)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(200, { type: 'LineString', coordinates: [[0, 0], [1, 1]] })),
    );
    const result = await readAoiFile(new File(['{}'], 'a.geojson'));
    expect(result.error).toBe('The server returned no usable AOI for "a.geojson".');
  });

  it('rejects a null 200 answer', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, null)));
    const result = await readAoiFile(new File(['{}'], 'a.geojson'));
    expect(result.error).toBe('The server returned no usable AOI for "a.geojson".');
  });
});

describe('readAoiFile — client-side size cap', () => {
  it('rejects a file over the cap without ever calling fetch', async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    const oversized = new File([new Uint8Array(AOI_UPLOAD_MAX_BYTES + 1)], 'huge.geojson');

    const result = await readAoiFile(oversized);

    expect(result.error).toBe('"huge.geojson" is too large for an AOI (max. 1 MB).');
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('sends a file exactly at the cap', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(200, { type: 'Point', coordinates: [0, 0] })),
    );
    const atCap = new File([new Uint8Array(AOI_UPLOAD_MAX_BYTES)], 'a.geojson');

    const result = await readAoiFile(atCap);

    expect(result.geometry).toEqual({ type: 'Point', coordinates: [0, 0] });
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});

describe('readAoiFile — misuse and edge cases', () => {
  it('sends an empty (0-byte) file and lets the route reject it', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(400, { detail: 'not valid JSON' })));
    const result = await readAoiFile(new File([], 'empty.geojson'));
    expect(result.error).toBe('Could not use "empty.geojson" as an AOI: not valid JSON.');
  });

  it('sends a file name with no extension as-is; the route decides it is unsupported', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(400, { detail: "unsupported file type: 'noext' (expected .geojson, .kml or .zip)" })),
    );
    const result = await readAoiFile(new File(['x'], 'noext'));
    expect(result.error).toContain('Could not use "noext" as an AOI:');
    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe('/aoi/upload?filename=noext');
  });

  it('percent-encodes a very long file name without truncating it', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(400, { detail: 'not valid JSON' })));
    const longName = `${'a'.repeat(300)}.geojson`;
    await readAoiFile(new File(['x'], longName));
    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe(`/aoi/upload?filename=${encodeURIComponent(longName)}`);
  });
});
