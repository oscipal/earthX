// The pages of `/stac/collections` (M5-40): every full entry over its pages, one page of a group of the catalogue, and the
// helpers of listed entries. Synthetic answers only; nothing leaves the test.

import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchCataloguePage, fetchCollections } from './api';
import { isListed, keywordsOf, listedSourceOf, sourceRow } from './catalogue';
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
  it('asks for one category and passes the token on', async () => {
    const fetchStub = vi.fn(async (_url: string) => page(['a'], 'T2', { numberMatched: 120 }));
    vi.stubGlobal('fetch', fetchStub);
    expect(await fetchCataloguePage('water', 'T1', 50)).toEqual({ collections: [{ id: 'a' }], next: 'T2', matched: 120 });
    expect(fetchStub.mock.calls[0][0]).toBe('/stac/collections?category=water&limit=50&token=T1');
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

  it('has its keywords each once, without empty ones and what is no text', () => {
    expect(keywordsOf({ id: 'x', keywords: ['flood', 'flood', ' ', 3, 'gauges'] } as unknown as Collection)).toEqual(['flood', 'gauges']);
    expect(keywordsOf({ id: 'x' } as Collection)).toEqual([]);
  });
});
