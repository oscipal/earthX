import { describe, expect, it } from 'vitest';

import { buildSearchUrl, errorDetail, nextTokenFrom } from './api';

describe('buildSearchUrl', () => {
  it('carries the collection, bbox, datetime range, limit and token', () => {
    const url = buildSearchUrl({
      collection: 'sentinel-2-c1-l2a',
      bbox: [10, 47, 11, 48],
      datetime: '2026-07-01T00:00:00Z/2026-07-31T23:59:59Z',
      limit: 100,
      token: 'next:abc',
    });
    const params = new URL(url, 'http://localhost').searchParams;
    expect(params.get('collections')).toBe('sentinel-2-c1-l2a');
    // bbox stays in the order it was given: [minx, miny, maxx, maxy].
    expect(params.get('bbox')).toBe('10,47,11,48');
    expect(params.get('datetime')).toBe('2026-07-01T00:00:00Z/2026-07-31T23:59:59Z');
    expect(params.get('limit')).toBe('100');
    expect(params.get('token')).toBe('next:abc');
  });

  it('omits optional params entirely rather than sending them empty', () => {
    const url = buildSearchUrl({ collection: 'sentinel-2-c1-l2a' });
    const params = new URL(url, 'http://localhost').searchParams;
    expect(params.has('bbox')).toBe(false);
    expect(params.has('datetime')).toBe(false);
    expect(params.has('limit')).toBe(false);
    expect(params.has('token')).toBe(false);
  });
});

describe('nextTokenFrom', () => {
  it('reads the token out of the rel=next link', () => {
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
