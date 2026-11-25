// The pages of `/stac/collections` (M5-40): every full entry over its pages, one page of a group of the catalogue, and the
// helpers of listed entries. Synthetic answers only; nothing leaves the test.

import { afterEach, describe, expect, it, vi } from 'vitest';

import { catalogueDatetime, fetchCatalogueCategories, fetchCatalogueRegions, fetchCataloguePage, fetchCatalogueSearch, fetchCollections } from './api';
import { activeFilters, isListed, listedSourceOf, sourceRow } from './catalogue';
import type { Collection } from './types';

const page = (ids: string[], next: string | null, extra: object = {}) =>
  new Response(
    JSON.stringify({
      collections: ids.map((id) => ({ id })),
      links: next ? [{ rel: 'next', href: `https://api.example.org/stac/collections?entry=full&token=${next}` }] : [],
      ...extra,
    }),
    { status: 200 },
  );

afterEach(() => vi.unstubAllGlobals());

describe('fetchCollections', () => {
  it('loads the full entries page by page with the token of each next link, from its own base', async () => {
    const fetchStub = vi.fn().mockResolvedValueOnce(page(['a', 'b'], 'T1')).mockResolvedValueOnce(page(['c'], null));
    vi.stubGlobal('fetch', fetchStub);
    expect((await fetchCollections()).map((c) => c.id)).toEqual(['a', 'b', 'c']);
    expect(fetchStub.mock.calls.map((call) => call[0])).toEqual([
      '/stac/collections?entry=full&limit=1000',
      '/stac/collections?entry=full&limit=1000&token=T1',
    ]);
  });

  it('stops after twenty pages instead of loading without end', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => page(['x'], 'again')));
    await expect(fetchCollections()).rejects.toThrow(/more than 20 pages/u);
  });

  it('fails with the status of an answer that is no page', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{"detail":"bad"}', { status: 400 })));
    await expect(fetchCollections()).rejects.toThrow();
  });
});

describe('fetchCataloguePage', () => {
  it('asks by POST for one category with the filters, and passes the token on', async () => {
    const answer = { collections: [{ id: 'a' }], links: [{ rel: 'next', method: 'POST', body: { token: 'T2' } }], numberMatched: 120 };
    const fetchStub = vi.fn(async (_url: string, _init: RequestInit) => new Response(JSON.stringify(answer), { status: 200 }));
    vi.stubGlobal('fetch', fetchStub);
    const area = { type: 'Point', coordinates: [7, 46] } as GeoJSON.Geometry;
    const filter = { area, region: 'DE-BY', from: '2020-01-01', to: null };
    expect(await fetchCataloguePage('water', 'T1', 50, filter)).toEqual({ collections: [{ id: 'a' }], next: 'T2', matched: 120 });
    const [url, init] = fetchStub.mock.calls[0];
    expect(url).toBe('/stac/collections');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({
      category: 'water', limit: 50, token: 'T1', intersects: area, region: ['DE-BY'], datetime: '2020-01-01T00:00:00Z/..',
    });
  });

  it('puts no area, region or period into the body that the filter does not have', async () => {
    const fetchStub = vi.fn(async (_url: string, _init: RequestInit) => page([], null));
    vi.stubGlobal('fetch', fetchStub);
    await fetchCataloguePage('water', null);
    expect(JSON.parse(String(fetchStub.mock.calls[0][1].body))).toEqual({ category: 'water', limit: 50 });
  });

  it('has no count where the API gives none, and no next page without a next link', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => page(['a'], null)));
    expect(await fetchCataloguePage('water', null)).toEqual({ collections: [{ id: 'a' }], next: null, matched: null });
  });

  it('reads no token from a next link that is no address', async () => {
    const body = { collections: [], links: [{ rel: 'next', href: 'http://[broken' }] };
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
    expect((await fetchCataloguePage('water', null)).next).toBeNull();
  });
});

describe('a listed entry', () => {
  const listed = (extra: Partial<Collection> = {}): Collection =>
    ({ id: 'x', 'earthx:entry': 'listed', ...extra }) as Collection;

  it('is told by earthx:entry, and nothing else', () => {
    expect(isListed(listed())).toBe(true);
    expect(isListed({ id: 'x', 'earthx:entry': 'full' } as Collection)).toBe(false);
    expect(isListed({ id: 'x' } as Collection)).toBe(false);
  });

  it('links to its page at the source, the link "via" where the listing names none, https only', () => {
    expect(listedSourceOf(listed({ 'earthx:listing': { source_url: 'https://a.example.org/1' } }))).toBe('https://a.example.org/1');
    const via = { links: [{ rel: 'via', href: 'https://b.example.org/2' }] } as Partial<Collection>;
    expect(listedSourceOf(listed(via))).toBe('https://b.example.org/2');
    expect(listedSourceOf(listed({ 'earthx:listing': { source_url: 'http://a.example.org/1' } }))).toBeNull();
    expect(listedSourceOf(listed({ links: [{ rel: 'via', href: 'javascript:alert(1)' }] } as Partial<Collection>))).toBeNull();
  });

  it('shows the host of its page as the row "Source"', () => {
    expect(sourceRow(listed({ 'earthx:listing': { source_url: 'https://a.example.org/1' } }))).toEqual([
      { text: 'a.example.org', href: 'https://a.example.org/1' },
    ]);
    expect(sourceRow(listed())).toEqual([{ text: '—', href: null }]);
  });
});

describe('the period of the catalogue', () => {
  it('runs from the first instant of the first day to the last of the last, open where a day is missing', () => {
    expect(catalogueDatetime('2020-01-01', '2020-12-31')).toBe('2020-01-01T00:00:00Z/2020-12-31T23:59:59Z');
    expect(catalogueDatetime(null, '2020-12-31')).toBe('../2020-12-31T23:59:59Z');
    expect(catalogueDatetime('2020-01-01', null)).toBe('2020-01-01T00:00:00Z/..');
    expect(catalogueDatetime(null, null)).toBeNull();
  });
});

describe('the lists of /catalogue', () => {
  it('read the categories and the regions', async () => {
    const answers: Record<string, object> = {
      '/catalogue/categories': { categories: [{ id: 'other', title: 'Other' }] },
      '/catalogue/regions': { regions: [{ code: 'DE', name: 'Germany', level: 'state' }] },
    };
    vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(answers[url]), { status: 200 })));
    expect(await fetchCatalogueCategories()).toEqual([{ id: 'other', title: 'Other' }]);
    expect(await fetchCatalogueRegions()).toEqual([{ code: 'DE', name: 'Germany', level: 'state' }]);
  });
});


describe('fetchCatalogueSearch (Otto, 16.11.2026)', () => {
  it('asks by POST with q, the offset, the category and the filters, and reads the offset of the next page', async () => {
    const answer = { collections: [{ id: 'a' }], links: [{ rel: 'next', method: 'POST', body: { q: 'dem', offset: 40 } }] };
    const fetchStub = vi.fn(async (_url: string, _init: RequestInit) => new Response(JSON.stringify(answer), { status: 200 }));
    vi.stubGlobal('fetch', fetchStub);
    const filter = { area: null, region: 'CH', from: null, to: '2020-12-31' };
    expect(await fetchCatalogueSearch('dem', 20, filter, 'elevation')).toEqual({ collections: [{ id: 'a' }], next: 40 });
    expect(JSON.parse(String(fetchStub.mock.calls[0][1].body))).toEqual({
      q: 'dem', offset: 20, category: 'elevation', region: ['CH'], datetime: '../2020-12-31T23:59:59Z',
    });
  });

  it('sends no offset on the first page, and has no next page without a next link', async () => {
    const fetchStub = vi.fn(async (_url: string, _init: RequestInit) => new Response(JSON.stringify({ collections: [], links: [] }), { status: 200 }));
    vi.stubGlobal('fetch', fetchStub);
    expect(await fetchCatalogueSearch('dem', 0)).toEqual({ collections: [], next: null });
    expect(JSON.parse(String(fetchStub.mock.calls[0][1].body))).toEqual({ q: 'dem' });
  });
});

describe('activeFilters', () => {
  const none = { bySearchPanel: false, region: '', from: '', to: '', category: '' };
  it('counts the fields that are set, the search panel as one with the category beside it', () => {
    expect(activeFilters(none, false)).toBe(0);
    expect(activeFilters({ ...none, region: 'DE', from: '2020-01-01', category: 'water' }, false)).toBe(3);
    expect(activeFilters({ ...none, bySearchPanel: true, region: 'DE', category: 'water' }, true)).toBe(2);
  });
});
