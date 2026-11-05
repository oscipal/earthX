// @vitest-environment jsdom
//
// DS-03c: "Evaluate: per pass / per scene" and the filter "AOI coverage". The search judges per pass until the user says
// otherwise, and then asks the server for it (`earthx:evaluate`), once for the whole search and only where a dataset offers it and
// has something to judge; per scene it asks nothing of the kind. The coverage goes with the filters of its dataset when there is
// an AOI it can use, needs no date range, and never to the coverage map. The server is a stand-in here.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { ELEVATION, OPTICAL, RADAR, TILES } from './fixtures/searchFilters';
import type { FilterInput } from './searchFilters';
import { useAppStore } from './store';
import type { StacItem } from './types';

// The first thing in this file, before any test touches the store: what the pop-up starts with.
const STARTED_WITH = useAppStore.getState().searchEvaluate;

const RECT: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 48], [10, 47]]] };
const COVERAGE = 'earthx:aoi_coverage';

const range = (from: string, to: string): FilterInput => ({ kind: 'range', from, to });
const values = (...ticked: string[]): FilterInput => ({ kind: 'values', values: ticked });
const json = (body: unknown, status = 200) =>
  ({ ok: status < 300, status, statusText: '', json: async () => body }) as Response;

const scene = (id: string, collection = 'optical'): StacItem => ({
  id,
  collection,
  bbox: [10, 47, 11, 48],
  properties: { datetime: '2026-07-10T10:00:00Z' },
  assets: {},
});

interface Step {
  scenes?: StacItem[];
  checked: number;
  next?: string | null;
}

let steps: Step[];
let asked: Record<string, unknown>[];
let index: number;
let fetchMock: ReturnType<typeof vi.fn>;

function answer(request: Record<string, unknown>) {
  asked.push(request);
  const step = steps[Math.min(index, steps.length - 1)];
  index += 1;
  const features = step.scenes ?? [];
  return {
    features,
    numberReturned: features.length,
    links: step.next ? [{ rel: 'next', href: '/stac/search', method: 'POST', body: { token: step.next } }] : [],
    'earthx:aoi_filter': { checked: step.checked, found: features.length, unreadable: 0, limit_reached: false },
  };
}

const state = () => useAppStore.getState();

function reset(selected = ['optical']) {
  steps = [];
  asked = [];
  index = 0;
  useAppStore.setState({
    datasets: datasetsFrom([OPTICAL, RADAR, ELEVATION, TILES]),
    selectedDatasetIds: selected,
    datasetId: selected[0],
    aoi: RECT,
    aoiPoint: null,
    dateFrom: '2026-07-01',
    dateTo: '2026-07-31',
    searchFilters: {},
    searchWithin: {},
    searchEvaluate: 'pass',
    sections: [],
    openSectionId: null,
    items: [],
    groups: [],
    selectedIds: [],
    searchContext: null,
    searching: false,
    loadingMore: false,
    aoiWalking: false,
    error: null,
    notice: null,
    showCoverage: false,
    coverageDatasetId: null,
    dock: 'controls',
  });
}

beforeEach(() => {
  reset();
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/stac/search') return json(answer(JSON.parse(init!.body as string)));
    return json({ detail: 'not found' }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('what the pop-up starts with', () => {
  it('is per pass', () => {
    expect(STARTED_WITH).toBe('pass');
  });
});

describe('what the search asks', () => {
  it('asks the server to judge per pass when a filter is set, and the filter is the scene property', async () => {
    state().setSearchFilter('optical', 'platform', values('sat-a'));
    steps = [{ scenes: [scene('a')], checked: 3 }];
    await state().runSearch();
    expect(asked).toHaveLength(1);
    expect(asked[0]['earthx:evaluate']).toBe('pass');
    expect(asked[0].query_by_collection).toEqual({ optical: { platform: { in: ['sat-a'] } } });
  });

  it('asks nothing of the kind per scene (Gegenprobe)', async () => {
    state().setSearchFilter('optical', 'platform', values('sat-a'));
    state().setSearchEvaluate('scene');
    steps = [{ scenes: [scene('a')], checked: 0 }];
    await state().runSearch();
    expect(asked[0]).not.toHaveProperty('earthx:evaluate');
    expect(asked[0].query_by_collection).toEqual({ optical: { platform: { in: ['sat-a'] } } });
  });

  it('asks nothing of the kind while no filter is set', async () => {
    steps = [{ scenes: [scene('a')], checked: 0 }];
    await state().runSearch();
    expect(asked[0]).not.toHaveProperty('earthx:evaluate');
    expect(asked[0]).not.toHaveProperty('query_by_collection');
  });

  it('asks nothing of the kind for a dataset that does not offer it', async () => {
    reset(['radar']);
    state().setSearchFilter('radar', 'test:track', range('1', '5'));
    steps = [{ scenes: [scene('a', 'radar')], checked: 0 }];
    await state().runSearch();
    expect(asked[0]).not.toHaveProperty('earthx:evaluate');
  });

  it('asks it once for the whole search, the datasets that offer it judged and the others not named', async () => {
    reset(['optical', 'radar']);
    state().setSearchFilter('optical', 'platform', values('sat-a'));
    state().setSearchFilter('radar', 'test:track', range('1', '5'));
    steps = [{ scenes: [], checked: 0 }];
    await state().runSearch();
    expect(asked[0]['earthx:evaluate']).toBe('pass');
    expect(asked[0].query_by_collection).toEqual({
      optical: { platform: { in: ['sat-a'] } },
      radar: { 'test:track': { gte: 1, lte: 5 } },
    });
  });

  it('goes on by itself while the server judges per pass, as it does for the clouds inside the AOI', async () => {
    state().setSearchFilter('optical', 'platform', values('sat-a'));
    steps = [
      { scenes: [], checked: 100, next: 't1' },
      { scenes: [scene('a')], checked: 150, next: 't2' },
      { scenes: [scene('b')], checked: 160 },
    ];
    await state().runSearch();
    expect(asked).toHaveLength(3);
    expect(asked[1].token).toBe('t1');
    expect(state().items.map((item) => item.id)).toEqual(['a', 'b']);
    expect(state().aoiWalking).toBe(false);
  });

  it('does not walk per scene: the source judged them, so the ordinary pages are enough', async () => {
    state().setSearchFilter('optical', 'platform', values('sat-a'));
    state().setSearchEvaluate('scene');
    steps = [{ scenes: [scene('a')], checked: 0, next: 't1' }, { scenes: [scene('b')], checked: 0 }];
    const walking: boolean[] = [];
    const stop = useAppStore.subscribe((s) => walking.push(s.aoiWalking));
    await state().runSearch();
    stop();
    expect(walking).not.toContain(true);
  });

  it('walks per pass (Gegenprobe of the one before)', async () => {
    state().setSearchFilter('optical', 'platform', values('sat-a'));
    steps = [{ scenes: [scene('a')], checked: 3, next: 't1' }, { scenes: [scene('b')], checked: 6 }];
    const walking: boolean[] = [];
    const stop = useAppStore.subscribe((s) => walking.push(s.aoiWalking));
    await state().runSearch();
    stop();
    expect(walking).toContain(true);
  });

  it('does not send a long AOI beside its box for filters that read no area', async () => {
    const ring = Array.from({ length: 1200 }, (_, i) => [10.5 + 0.4 * Math.cos((i / 1200) * 2 * Math.PI), 47.5 + 0.4 * Math.sin((i / 1200) * 2 * Math.PI)]);
    useAppStore.setState({ aoi: { type: 'Polygon', coordinates: [[...ring, ring[0]]] } });
    state().setSearchFilter('optical', 'platform', values('sat-a'));
    steps = [{ scenes: [], checked: 0 }];
    await state().runSearch();
    expect(asked[0]).not.toHaveProperty('earthx:aoi');
  });

  it('keeps the way of judging when the search goes on with "Load more"', async () => {
    state().setSearchFilter('optical', 'platform', values('sat-a'));
    steps = [{ scenes: [scene('a')], checked: 500 }];
    await state().runSearch();
    expect(asked.every((body) => body['earthx:evaluate'] === 'pass')).toBe(true);
  });

  it('forgets a page token when the way of judging changes: the old one belongs to the other search', async () => {
    state().setSearchFilter('optical', 'platform', values('sat-a'));
    state().setSearchEvaluate('scene');
    steps = [{ scenes: [scene('a')], checked: 0, next: 't1' }];
    await state().runSearch();
    expect(state().searchContext?.nextToken).toBe('t1');
    state().setSearchEvaluate('pass');
    expect(state().searchContext?.nextToken).toBeNull();
  });
});

describe('a change of "Evaluate" while the first answer is on its way', () => {
  it('stops the walk and keeps no token: the search went out per pass and the fields now say per scene', async () => {
    state().setSearchFilter('optical', 'platform', values('sat-a'));
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => (release = resolve));
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url !== '/stac/search') return json({ detail: 'not found' }, 404);
      const request = JSON.parse(init!.body as string);
      asked.push(request);
      if (asked.length === 1) await gate;
      return json({ features: [], numberReturned: 0, links: [{ rel: 'next', href: '/stac/search', method: 'POST', body: { token: 't1' } }], 'earthx:aoi_filter': { checked: 100, found: 0, unreadable: 0, limit_reached: false } });
    });
    const running = state().runSearch();
    await vi.waitFor(() => expect(asked).toHaveLength(1));
    state().setSearchEvaluate('scene');
    release();
    await running;
    expect(state().searchContext?.nextToken ?? null).toBeNull();
  });

  it('keeps the token when nothing was judged per pass either way (no filter set)', async () => {
    steps = [{ scenes: [scene('a')], checked: 0, next: 't1' }, { scenes: [], checked: 0 }];
    state().setSearchEvaluate('scene');
    await state().runSearch();
    const token = state().searchContext?.nextToken;
    state().setSearchEvaluate('pass');
    expect(state().searchContext?.nextToken).toBe(token);
  });
});

describe('"AOI coverage"', () => {
  it('goes with the filters of its dataset, with no date range', async () => {
    useAppStore.setState({ dateFrom: '', dateTo: '' });
    state().setSearchFilter('optical', COVERAGE, range('60', ''));
    steps = [{ scenes: [], checked: 0 }];
    await state().runSearch();
    expect(asked[0].query_by_collection).toEqual({ optical: { [COVERAGE]: { gte: 60 } } });
    expect(asked[0]).not.toHaveProperty('datetime');
  });

  it('goes to a dataset that has no filter of its own and nothing to judge per pass', async () => {
    reset(['tiles']);
    state().setSearchFilter('tiles', COVERAGE, range('90', ''));
    steps = [{ scenes: [], checked: 0 }];
    await state().runSearch();
    expect(asked[0].query_by_collection).toEqual({ tiles: { [COVERAGE]: { gte: 90 } } });
    expect(asked[0]).not.toHaveProperty('earthx:evaluate');
  });

  it('is not sent for a point, which has no area, and the search is the one without it', async () => {
    useAppStore.setState({ aoiPoint: { type: 'Point', coordinates: [10.5, 47.5] } });
    state().setSearchFilter('optical', COVERAGE, range('60', ''));
    steps = [{ scenes: [], checked: 0 }];
    await state().runSearch();
    expect(asked[0]).not.toHaveProperty('query_by_collection');
    expect(asked[0]).not.toHaveProperty('earthx:evaluate');
  });

  it('is sent beside the other filters, with and without "Filter within AOI only"', async () => {
    state().setSearchFilter('optical', COVERAGE, range('60', ''));
    state().setSearchFilter('optical', 'test:cloud', range('', '20'));
    steps = [{ scenes: [], checked: 0 }];
    await state().runSearch();
    expect(asked[0].query_by_collection).toEqual({ optical: { [COVERAGE]: { gte: 60 }, 'test:cloud': { lte: 20 } } });
    reset();
    state().setSearchFilter('optical', COVERAGE, range('60', ''));
    state().setSearchFilter('optical', 'test:cloud', range('', '20'));
    state().setSearchWithin('optical', true);
    steps = [{ scenes: [], checked: 0 }];
    await state().runSearch();
    expect(asked[0].query_by_collection).toEqual({
      optical: { [COVERAGE]: { gte: 60 }, 'earthx:aoi_cloud_cover': { lte: 20 } },
    });
  });

  it('sends the AOI itself beside the box when it is long, because the coverage reads outlines against it', async () => {
    const ring = Array.from({ length: 1200 }, (_, i) => [10.5 + 0.4 * Math.cos((i / 1200) * 2 * Math.PI), 47.5 + 0.4 * Math.sin((i / 1200) * 2 * Math.PI)]);
    const long: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[...ring, ring[0]]] };
    useAppStore.setState({ aoi: long });
    state().setSearchFilter('optical', COVERAGE, range('60', ''));
    steps = [{ scenes: [], checked: 0 }];
    await state().runSearch();
    expect(asked[0]['earthx:aoi']).toEqual(long);
  });

  it('is judged per pass or per scene by the way chosen: the server is told, and nothing else changes in the request', async () => {
    state().setSearchFilter('optical', COVERAGE, range('60', ''));
    steps = [{ scenes: [], checked: 0 }];
    await state().runSearch();
    const perPass = asked[0];
    reset();
    state().setSearchFilter('optical', COVERAGE, range('60', ''));
    state().setSearchEvaluate('scene');
    steps = [{ scenes: [], checked: 0 }];
    await state().runSearch();
    const perScene = asked[0];
    expect({ ...perPass, 'earthx:evaluate': undefined }).toEqual({ ...perScene, 'earthx:evaluate': undefined });
    expect(perPass['earthx:evaluate']).toBe('pass');
    expect(perScene).not.toHaveProperty('earthx:evaluate');
  });

  it('is not asked of the coverage map, which counts at the source and cannot judge an outline', async () => {
    vi.useFakeTimers();
    try {
      fetchMock.mockImplementation(async (url: string) => {
        if (String(url).startsWith('/coverage/')) {
          return json({
            dataset_id: 'optical', grid: 'geotile', level: 4, counting: 'centroid', cells: [], counted: 0, total_count: 0,
            completeness: 'complete', max_count: 0, histogram: [], histogram_interval: 'month', footprints_advised: false,
            from_cache: false, extent: null, area: null, ignored_filters: [],
          });
        }
        return json({ detail: 'not found' }, 404);
      });
      state().setSearchFilter('optical', COVERAGE, range('60', ''));
      state().setSearchFilter('optical', 'test:cloud', range('', '20'));
      useAppStore.setState({
        aoi: null, showCoverage: true, coverageDatasetId: 'optical', mapZoom: 5, viewportBbox: [71, 10, 121, 60],
        viewportSize: { width: 1920, height: 1080 }, coverage: null, coverageFootprints: null,
      });
      state().showCoverageFor('optical');
      await vi.advanceTimersByTimeAsync(500);
      const calls = fetchMock.mock.calls.filter(([url]) => String(url).startsWith('/coverage/'));
      expect(calls.length).toBeGreaterThan(0);
      for (const [url] of calls) {
        const query = new URL(String(url), 'http://x').searchParams.get('query');
        expect(query ? JSON.parse(query) : {}).toEqual({ 'test:cloud': { lte: 20 } });
      }
    } finally {
      vi.useRealTimers();
    }
  });
});
