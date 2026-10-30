// @vitest-environment jsdom
//
// DS-02c: the search filters of each dataset are a search setting like the dates. They go to the search of the
// datasets that are ticked — each dataset its own — and on through "Load more" and the date fallback, they go to the
// coverage map of its dataset, and they stay when the results are cleared or a dataset is unticked.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { ELEVATION, OPTICAL, RADAR } from './fixtures/searchFilters';
import { searchFiltersInvalid, useAppStore } from './store';
import type { FilterInput } from './searchFilters';
import type { StacItem } from './types';

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 48], [10, 47]]] };

const range = (from: string, to: string): FilterInput => ({ kind: 'range', from, to });
const values = (...ticked: string[]): FilterInput => ({ kind: 'values', values: ticked });

const json = (body: unknown, status = 200) =>
  ({ ok: status < 300, status, statusText: '', json: async () => body }) as Response;

function scene(id: string, collection: string, day = '2026-07-10'): StacItem {
  return { id, collection, bbox: [10, 47, 11, 48], properties: { datetime: `${day}T10:00:00Z` }, assets: {} };
}

const page = (features: StacItem[], next: string | null = null) => ({
  features,
  numberReturned: features.length,
  links: next ? [{ rel: 'next', href: '/stac/search', method: 'POST', body: { token: next } }] : [],
});

// A search walks pages of 100 up to 300 scenes (`MAX_SEARCH_ITEMS`); a source with more leaves a token for "Load more".
const crowd = (prefix: string, count: number) => Array.from({ length: count }, (_, i) => scene(`${prefix}${i}`, 'optical'));
function pages(body: Record<string, unknown>) {
  const token = body.token as string | undefined;
  const n = token ? Number(token.slice(1)) : 1;
  return page(crowd(`p${n}-`, 100), `p${n + 1}`);
}

let answer: (body: Record<string, unknown>) => unknown;
let fetchMock: ReturnType<typeof vi.fn>;

const bodies = () =>
  fetchMock.mock.calls
    .filter(([url, init]) => url === '/stac/search' && init?.method === 'POST')
    .map(([, init]) => JSON.parse(init.body as string) as Record<string, unknown>);

function reset(selected: string[]) {
  useAppStore.setState({
    datasets: datasetsFrom([OPTICAL, RADAR, ELEVATION]),
    selectedDatasetIds: selected,
    datasetId: selected[0] ?? null,
    aoi: AOI,
    aoiPoint: null,
    dateFrom: '',
    dateTo: '',
    searchFilters: {},
    sections: [],
    openSectionId: null,
    items: [],
    groups: [],
    selectedIds: [],
    searchContext: null,
    searching: false,
    loadingMore: false,
    error: null,
    notice: null,
    showCoverage: false,
    coverageDatasetId: null,
  });
}

beforeEach(() => {
  answer = () => page([]);
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/stac/search') return json(answer(JSON.parse(init!.body as string)));
    return json({ detail: 'not found' }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the search carries the filters of each dataset (DS-02c)', () => {
  it('sends every ticked dataset only its own filters, as query_by_collection', async () => {
    reset(['optical', 'radar']);
    const { setSearchFilter } = useAppStore.getState();
    setSearchFilter('optical', 'eo:cloud_cover', range('', '20'));
    setSearchFilter('optical', 'platform', values('sat-b', 'sat-a'));
    setSearchFilter('radar', 'sat:relative_orbit', range('22', '22'));

    await useAppStore.getState().runSearch();

    expect(bodies()).toHaveLength(1);
    expect(bodies()[0].collections).toEqual(['optical', 'radar']);
    expect(bodies()[0].query_by_collection).toEqual({
      optical: { 'eo:cloud_cover': { lte: 20 }, platform: { in: ['sat-a', 'sat-b'] } },
      radar: { 'sat:relative_orbit': { gte: 22, lte: 22 } },
    });
    // The shared `query` is never used: a filter of one dataset must not reach the other.
    expect(bodies()[0]).not.toHaveProperty('query');
  });

  it('names only the datasets with a filter set', async () => {
    reset(['optical', 'radar', 'elevation']);
    useAppStore.getState().setSearchFilter('radar', 'sat:relative_orbit', range('', '30'));
    await useAppStore.getState().runSearch();
    expect(bodies()[0].query_by_collection).toEqual({ radar: { 'sat:relative_orbit': { lte: 30 } } });
  });

  it('keeps the body of a search without filters as it was', async () => {
    reset(['optical', 'elevation']);
    await useAppStore.getState().runSearch();
    expect(Object.keys(bodies()[0]).sort()).toEqual(['bbox', 'collections', 'limit']);
  });

  it('does not send a filter of a dataset that is not ticked, and sends it again once it is', async () => {
    reset(['optical']);
    useAppStore.getState().setSearchFilter('radar', 'sat:relative_orbit', range('1', '5'));
    useAppStore.getState().setSearchFilter('optical', 'eo:cloud_cover', range('', '10'));

    await useAppStore.getState().runSearch();
    expect(bodies()[0].query_by_collection).toEqual({ optical: { 'eo:cloud_cover': { lte: 10 } } });

    useAppStore.setState({ selectedDatasetIds: ['optical', 'radar'] });
    await useAppStore.getState().runSearch();
    expect(bodies()[1].query_by_collection).toEqual({
      optical: { 'eo:cloud_cover': { lte: 10 } },
      radar: { 'sat:relative_orbit': { gte: 1, lte: 5 } },
    });
  });

  it('leaves a filter with nothing in it out, and drops the dataset once its last filter is empty', async () => {
    reset(['optical']);
    const { setSearchFilter } = useAppStore.getState();
    setSearchFilter('optical', 'eo:cloud_cover', range('', '20'));
    setSearchFilter('optical', 'eo:cloud_cover', range('', ''));
    expect(useAppStore.getState().searchFilters).toEqual({});
    await useAppStore.getState().runSearch();
    expect(bodies()[0]).not.toHaveProperty('query_by_collection');
  });

  it('holds the search back while a field is wrong, and says so', async () => {
    reset(['optical']);
    useAppStore.getState().setSearchFilter('optical', 'eo:cloud_cover', range('50', '20'));
    expect(searchFiltersInvalid(useAppStore.getState())).toBe(true);

    await useAppStore.getState().runSearch();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(useAppStore.getState().error).toBe('Correct the marked search filters first.');
    expect(useAppStore.getState().searching).toBe(false);

    useAppStore.getState().setSearchFilter('optical', 'eo:cloud_cover', range('20', '50'));
    expect(searchFiltersInvalid(useAppStore.getState())).toBe(false);
    await useAppStore.getState().runSearch();
    expect(bodies()).toHaveLength(1);
  });

  it('is not held back by a wrong field of a dataset that is not ticked', async () => {
    reset(['optical']);
    useAppStore.getState().setSearchFilter('radar', 'sat:relative_orbit', range('0', ''));
    expect(searchFiltersInvalid(useAppStore.getState())).toBe(false);
    await useAppStore.getState().runSearch();
    expect(bodies()).toHaveLength(1);
    expect(bodies()[0]).not.toHaveProperty('query_by_collection');
  });

  it('ignores a value for a property the dataset no longer offers, so the server is never asked for it', async () => {
    reset(['optical']);
    useAppStore.setState({ searchFilters: { optical: { 'made:up': range('1', '2') } } });
    await useAppStore.getState().runSearch();
    expect(bodies()[0]).not.toHaveProperty('query_by_collection');
  });

  it('says in the notice of an empty result that filters are set', async () => {
    reset(['optical']);
    await useAppStore.getState().runSearch();
    expect(useAppStore.getState().notice).toBe('No scenes found for this area.');

    useAppStore.getState().setSearchFilter('optical', 'eo:cloud_cover', range('', '1'));
    await useAppStore.getState().runSearch();
    expect(useAppStore.getState().notice).toBe('No scenes found for this area. Search filters are set.');
  });
});

describe('"Load more" and the date fallback keep the filters (DS-02c)', () => {
  it('"Load more" asks every page with the filters the search ran with', async () => {
    reset(['optical', 'radar']);
    answer = pages;
    useAppStore.getState().setSearchFilter('optical', 'eo:cloud_cover', range('', '20'));
    await useAppStore.getState().runSearch();
    expect(useAppStore.getState().searchContext?.nextToken).toBe('p4');
    const ran = bodies().length;

    await useAppStore.getState().loadMore();

    const more = bodies().slice(ran);
    expect(more.length).toBeGreaterThan(0);
    expect(more[0].token).toBe('p4');
    for (const body of more) {
      expect(body.query_by_collection).toEqual({ optical: { 'eo:cloud_cover': { lte: 20 } } });
    }
  });

  it('the fallback of a dataset asks only that dataset, with only its own filters', async () => {
    reset(['optical', 'radar']);
    useAppStore.setState({ dateFrom: '2026-07-01', dateTo: '2026-07-31' });
    const { setSearchFilter } = useAppStore.getState();
    setSearchFilter('optical', 'eo:cloud_cover', range('', '20'));
    setSearchFilter('radar', 'sat:relative_orbit', range('22', '22'));

    await useAppStore.getState().runSearch();

    const all = bodies();
    expect(all[0].collections).toEqual(['optical', 'radar']);
    const fallbacks = all.slice(1);
    expect(fallbacks.length).toBeGreaterThan(0);
    for (const body of fallbacks) {
      expect(body.collections).toEqual(['optical']);
      expect(body.query_by_collection).toEqual({ optical: { 'eo:cloud_cover': { lte: 20 } } });
    }
  });

  it('the fallback of a dataset with no filter set names none, although another dataset has one', async () => {
    reset(['optical', 'radar']);
    useAppStore.setState({ dateFrom: '2026-07-01', dateTo: '2026-07-31', datasetId: 'optical' });
    useAppStore.getState().setSearchFilter('radar', 'sat:relative_orbit', range('22', '22'));

    await useAppStore.getState().runSearch();

    const fallbacks = bodies().slice(1);
    expect(fallbacks.length).toBeGreaterThan(0);
    for (const body of fallbacks) {
      expect(body.collections).toEqual(['optical']);
      expect(body).not.toHaveProperty('query_by_collection');
    }
  });
});

describe('the filters are a search setting (DS-02c)', () => {
  it('"Clear search results" keeps them, and the next search uses them', async () => {
    reset(['optical']);
    answer = () => page([scene('a1', 'optical')]);
    useAppStore.getState().setSearchFilter('optical', 'eo:cloud_cover', range('', '20'));
    await useAppStore.getState().runSearch();

    useAppStore.getState().clearSearchResults();

    expect(useAppStore.getState().sections).toEqual([]);
    expect(useAppStore.getState().searchFilters).toEqual({ optical: { 'eo:cloud_cover': range('', '20') } });
    await useAppStore.getState().runSearch();
    expect(bodies()[1].query_by_collection).toEqual({ optical: { 'eo:cloud_cover': { lte: 20 } } });
  });

  it('"Reset filters" takes back one dataset and leaves the others', () => {
    reset(['optical', 'radar']);
    const { setSearchFilter, resetSearchFilters } = useAppStore.getState();
    setSearchFilter('optical', 'eo:cloud_cover', range('', '20'));
    setSearchFilter('radar', 'sat:relative_orbit', range('1', '5'));

    resetSearchFilters('optical');

    expect(useAppStore.getState().searchFilters).toEqual({ radar: { 'sat:relative_orbit': range('1', '5') } });
  });

  it('a change drops the page token of a search that ran with that dataset, but not of another dataset', async () => {
    reset(['optical']);
    answer = pages;
    await useAppStore.getState().runSearch();
    expect(useAppStore.getState().searchContext?.nextToken).toBe('p4');

    useAppStore.getState().setSearchFilter('radar', 'sat:relative_orbit', range('1', '5'));
    expect(useAppStore.getState().searchContext?.nextToken).toBe('p4');

    useAppStore.getState().setSearchFilter('optical', 'eo:cloud_cover', range('', '5'));
    expect(useAppStore.getState().searchContext?.nextToken).toBeNull();
    // What was found stays.
    expect(useAppStore.getState().items).toHaveLength(300);
  });
});

// The coverage map counts what the search would find (adr/0004 K1): it asks with the filters of its own dataset, and
// the answers it remembers for a pan are kept apart by them.
describe('the coverage map follows the filters of its dataset (DS-02c)', () => {
  const coverageBody = (footprints: boolean) => ({
    dataset_id: 'optical',
    grid: 'geotile',
    level: 4,
    counting: 'centroid',
    cells: [],
    counted: 0,
    total_count: 10,
    completeness: 'complete',
    max_count: 0,
    histogram: [],
    histogram_interval: 'month',
    footprints_advised: footprints,
    from_cache: false,
    extent: null,
    area: null,
    ignored_filters: [],
  });
  let footprints = false;
  const VIEWPORT = [10, 10, 60, 60] as [number, number, number, number];
  const SIZE = { width: 1920, height: 1080 };

  const coverageCalls = () =>
    fetchMock.mock.calls
      .filter(([url]) => String(url).startsWith('/coverage/'))
      .map(([url]) => new URL(String(url), 'http://x'));
  const queryOf = (url: URL) => (url.searchParams.has('query') ? JSON.parse(url.searchParams.get('query')!) : undefined);

  beforeEach(() => {
    footprints = false;
    vi.useFakeTimers();
    vi.stubGlobal('window', { setTimeout: (...args: Parameters<typeof setTimeout>) => setTimeout(...args), clearTimeout });
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (String(url).startsWith('/coverage/')) return json(coverageBody(footprints));
      if (url === '/stac/search') return json(answer(JSON.parse(init!.body as string)));
      return json({ detail: 'not found' }, 404);
    });
    reset(['optical', 'radar']);
    // The reuse cache is module-level: a viewport nobody else used.
    useAppStore.setState({
      aoi: null,
      showCoverage: true,
      coverageDatasetId: 'optical',
      mapZoom: 5,
      viewportBbox: VIEWPORT,
      viewportSize: SIZE,
      coverage: null,
      coverageFootprints: null,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const settle = () => vi.advanceTimersByTimeAsync(500);
  // A viewport of its own per test, so that no test reuses the answers of another.
  let corner = 0;
  const freshViewport = () => {
    corner += 3;
    useAppStore.setState({ viewportBbox: [10 + corner, 10, 60 + corner, 60] });
  };

  it('asks with the filters of the coverage dataset, and with none while none is set', async () => {
    freshViewport();
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    expect(coverageCalls()).toHaveLength(1);
    expect(queryOf(coverageCalls()[0])).toBeUndefined();

    useAppStore.getState().setSearchFilter('optical', 'eo:cloud_cover', range('5', '20'));
    useAppStore.getState().setSearchFilter('optical', 'platform', values('sat-a'));
    await settle();

    expect(coverageCalls()).toHaveLength(2);
    expect(queryOf(coverageCalls()[1])).toEqual({ 'eo:cloud_cover': { gte: 5, lte: 20 }, platform: { in: ['sat-a'] } });
  });

  it('follows a change after the debounce of the dates: one request for a burst of keystrokes', async () => {
    freshViewport();
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    const before = coverageCalls().length;

    for (const text of ['1', '2', '20']) {
      useAppStore.getState().setSearchFilter('optical', 'eo:cloud_cover', range('', text));
      await vi.advanceTimersByTimeAsync(100);
    }
    expect(coverageCalls()).toHaveLength(before);
    await settle();

    expect(coverageCalls()).toHaveLength(before + 1);
    expect(queryOf(coverageCalls()[before])).toEqual({ 'eo:cloud_cover': { lte: 20 } });
  });

  it('does not ask again for a change in a dataset whose coverage is not shown', async () => {
    freshViewport();
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    const before = coverageCalls().length;

    useAppStore.getState().setSearchFilter('radar', 'sat:relative_orbit', range('1', '5'));
    await settle();

    expect(coverageCalls()).toHaveLength(before);
  });

  it('never sends the filters of another dataset', async () => {
    freshViewport();
    useAppStore.getState().setSearchFilter('optical', 'eo:cloud_cover', range('', '20'));
    useAppStore.getState().setSearchFilter('radar', 'sat:relative_orbit', range('1', '5'));
    useAppStore.getState().showCoverageFor('radar');
    await settle();
    expect(coverageCalls().at(-1)!.pathname).toBe('/coverage/radar');
    expect(queryOf(coverageCalls().at(-1)!)).toEqual({ 'sat:relative_orbit': { gte: 1, lte: 5 } });
  });

  it('keeps the answers of a pan apart by their filters, and reuses each for its own', async () => {
    freshViewport();
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    expect(coverageCalls()).toHaveLength(1);

    // Another filter is another map: the answer without it is not shown for it.
    useAppStore.getState().setSearchFilter('optical', 'eo:cloud_cover', range('', '20'));
    await settle();
    expect(coverageCalls()).toHaveLength(2);

    // A pan inside the same block: both answers are there to reuse, no request.
    useAppStore.setState({ viewportBbox: [VIEWPORT[0] + corner + 2, 12, VIEWPORT[2] + corner - 2, 58] });
    useAppStore.getState().setMapViewport(5, useAppStore.getState().viewportBbox!, SIZE);
    await settle();
    expect(coverageCalls()).toHaveLength(2);

    useAppStore.getState().resetSearchFilters('optical');
    await settle();
    expect(coverageCalls()).toHaveLength(2);
    expect(useAppStore.getState().showCoverage).toBe(true);
  });

  it('goes without a filter whose field is wrong, rather than ask the server something it refuses', async () => {
    freshViewport();
    useAppStore.getState().setSearchFilter('optical', 'eo:cloud_cover', range('50', '20'));
    useAppStore.getState().setSearchFilter('optical', 'platform', values('sat-b'));
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    expect(queryOf(coverageCalls().at(-1)!)).toEqual({ platform: { in: ['sat-b'] } });
  });

  it('asks the scene footprints with the same filters, for its dataset only', async () => {
    freshViewport();
    footprints = true;
    answer = () => page([scene('f1', 'optical')]);
    useAppStore.getState().setSearchFilter('optical', 'eo:cloud_cover', range('', '20'));
    useAppStore.getState().setSearchFilter('radar', 'sat:relative_orbit', range('1', '5'));
    useAppStore.getState().showCoverageFor('optical');
    await settle();

    const search = bodies();
    expect(search).toHaveLength(1);
    expect(search[0].collections).toEqual(['optical']);
    expect(search[0].query_by_collection).toEqual({ optical: { 'eo:cloud_cover': { lte: 20 } } });
    expect(useAppStore.getState().coverageFootprints?.features).toHaveLength(1);
  });

  it('sends no filter to a dataset that has none, whatever else is set', async () => {
    freshViewport();
    useAppStore.setState({ selectedDatasetIds: ['optical', 'elevation'], coverageDatasetId: 'elevation' });
    useAppStore.getState().setSearchFilter('optical', 'eo:cloud_cover', range('', '20'));
    useAppStore.getState().showCoverageFor('elevation');
    await settle();
    expect(coverageCalls().at(-1)!.pathname).toBe('/coverage/elevation');
    expect(queryOf(coverageCalls().at(-1)!)).toBeUndefined();
  });
});
