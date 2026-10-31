// @vitest-environment jsdom
//
// DS-03b: "Within AOI". The search asks the clouds inside the AOI (`earthx:aoi_cloud_cover`) in place of the scene's, and
// the server answers in short steps: a few scenes checked per answer, how far it got, and a token. The store goes on by
// itself until the page is full, shows every step, ends on "Stop" or when the search it belongs to changes, and keeps
// what was found. The server is a stand-in here (`tests/fixtures`-style, nothing from a real source).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { ELEVATION, OPTICAL, RADAR } from './fixtures/searchFilters';
import type { FilterInput } from './searchFilters';
import { useAppStore } from './store';
import { hasResultsPanel } from './sections';
import type { StacItem } from './types';

const RECT: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 48], [10, 47]]] };
const TRIANGLE: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [10.5, 48], [10, 47]]] };

const AOI_CLOUD_PROPERTY = 'earthx:aoi_cloud_cover';
const AOI_NODATA_PROPERTY = 'earthx:aoi_nodata';

const range = (from: string, to: string): FilterInput => ({ kind: 'range', from, to });
const values = (...ticked: string[]): FilterInput => ({ kind: 'values', values: ticked });

const json = (body: unknown, status = 200) =>
  ({ ok: status < 300, status, statusText: '', json: async () => body }) as Response;

function scene(id: string, collection = 'optical', day = '2026-07-10', cloud = 5): StacItem {
  return {
    id,
    collection,
    bbox: [10, 47, 11, 48],
    properties: {
      datetime: `${day}T10:00:00Z`,
      [AOI_CLOUD_PROPERTY]: cloud,
      'earthx:aoi_measure': { data_percent: 100, cloud_pixels: cloud, data_pixels: 100, resolution: 80 },
    },
    assets: {},
  };
}

interface Step {
  scenes?: StacItem[];
  checked: number;
  found?: number;
  unreadable?: number;
  limit?: boolean;
  next?: string | null;
  // A mixed search names every source; one that is done is left out.
  byCollection?: Record<string, { checked: number; found: number; unreadable: number; limit_reached: boolean }>;
}

// A server that answers the steps in order, whatever is asked, and records what was asked.
let steps: Step[];
let asked: Record<string, unknown>[];
let fetchMock: ReturnType<typeof vi.fn>;

function body(step: Step) {
  const features = step.scenes ?? [];
  const counts = { checked: step.checked, found: step.found ?? features.length, unreadable: step.unreadable ?? 0, limit_reached: step.limit ?? false };
  return {
    features,
    numberReturned: features.length,
    links: step.next ? [{ rel: 'next', href: '/stac/search', method: 'POST', body: { token: step.next } }] : [],
    ...(step.byCollection ? { 'earthx:aoi_filter_by_collection': step.byCollection } : { 'earthx:aoi_filter': counts }),
  };
}

// One answer per request: the next step.
let stepIndex: number;
const respond = (request: Record<string, unknown>) => {
  asked.push(request);
  const step = steps[Math.min(stepIndex, steps.length - 1)];
  stepIndex += 1;
  return body(step);
};

const state = () => useAppStore.getState();
const sceneIds = () => state().items.map((it) => it.id);

function reset(selected: string[] = ['optical']) {
  steps = [];
  asked = [];
  stepIndex = 0;
  useAppStore.setState({
    datasets: datasetsFrom([OPTICAL, RADAR, ELEVATION]),
    selectedDatasetIds: selected,
    datasetId: selected[0] ?? null,
    aoi: RECT,
    aoiPoint: null,
    dateFrom: '2026-07-01',
    dateTo: '2026-07-31',
    searchFilters: { optical: { 'test:cloud': range('', '20') } },
    searchWithin: { optical: true },
    sections: [],
    openSectionId: null,
    items: [],
    groups: [],
    selectedIds: [],
    searchContext: null,
    searching: false,
    loadingMore: false,
    loadMoreError: null,
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
    if (url === '/stac/search') return json(respond(JSON.parse(init!.body as string)));
    return json({ detail: 'not found' }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('what the search asks', () => {
  it('puts the range under the clouds inside the AOI instead of under the scene property, with the dates', async () => {
    steps = [{ scenes: [scene('a')], checked: 40 }];
    await state().runSearch();
    expect(asked).toHaveLength(1);
    expect(asked[0].query_by_collection).toEqual({ optical: { [AOI_CLOUD_PROPERTY]: { lte: 20 } } });
    expect(asked[0].datetime).toBe('2026-07-01T00:00:00Z/2026-07-31T23:59:59Z');
    expect(asked[0].bbox).toEqual([10, 47, 11, 48]);
  });

  it('keeps the scene property when the switch is off', async () => {
    useAppStore.setState({ searchWithin: {} });
    steps = [{ scenes: [], checked: 0 }];
    await state().runSearch();
    expect(asked[0].query_by_collection).toEqual({ optical: { 'test:cloud': { lte: 20 } } });
    expect(state().aoiWalking).toBe(false);
  });

  it('sends nothing for a switch that is on without a range', async () => {
    useAppStore.setState({ searchFilters: {} });
    steps = [{ scenes: [], checked: 0 }];
    await state().runSearch();
    expect(asked[0]).not.toHaveProperty('query_by_collection');
  });

  it('asks the scene when the switch cannot be used: no dates, one date, or a point', async () => {
    const cases: [string, Partial<ReturnType<typeof state>>][] = [
      ['no dates', { dateFrom: '', dateTo: '' }],
      ['no end', { dateTo: '' }],
      ['a point', { aoiPoint: { type: 'Point', coordinates: [10.5, 47.5] } }],
    ];
    for (const [, change] of cases) {
      reset();
      useAppStore.setState(change);
      steps = [{ scenes: [], checked: 0 }];
      await state().runSearch();
      expect(asked[0].query_by_collection).toEqual({ optical: { 'test:cloud': { lte: 20 } } });
      expect(state().aoiWalking).toBe(false);
    }
  });

  it('asks the scene, not the AOI, for an AOI with too many points to measure in', async () => {
    const ring = Array.from({ length: 20_001 }, (_, i) => [10.5 + 0.4 * Math.cos((i / 20_001) * 2 * Math.PI), 47.5 + 0.4 * Math.sin((i / 20_001) * 2 * Math.PI)]);
    useAppStore.setState({ aoi: { type: 'Polygon', coordinates: [[...ring, ring[0]]] } });
    steps = [{ scenes: [], checked: 0 }];
    await state().runSearch();
    expect(asked[0].query_by_collection).toEqual({ optical: { 'test:cloud': { lte: 20 } } });
    expect(asked[0]).not.toHaveProperty('earthx:aoi');
    expect(state().aoiWalking).toBe(false);
  });

  it('searches a polygon by its shape, and adds nothing', async () => {
    useAppStore.setState({ aoi: TRIANGLE });
    steps = [{ scenes: [], checked: 0 }];
    await state().runSearch();
    expect(asked[0].intersects).toEqual(TRIANGLE);
    expect(asked[0]).not.toHaveProperty('earthx:aoi');
  });

  it('sends the AOI itself beside the box when it is too long to search by its shape (KE1)', async () => {
    const ring = Array.from({ length: 1200 }, (_, i) => [10 + 0.5 + 0.4 * Math.cos((i / 1200) * 2 * Math.PI), 47.5 + 0.4 * Math.sin((i / 1200) * 2 * Math.PI)]);
    const long: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[...ring, ring[0]]] };
    useAppStore.setState({ aoi: long });
    steps = [{ scenes: [], checked: 0 }];
    await state().runSearch();
    expect(asked[0]).not.toHaveProperty('intersects');
    expect(asked[0].bbox).toBeDefined();
    expect(asked[0]['earthx:aoi']).toEqual(long);
    // The switch is not locked by it.
    expect(asked[0].query_by_collection).toEqual({ optical: { [AOI_CLOUD_PROPERTY]: { lte: 20 } } });
  });

  it('does not send the AOI beside the box of a search without the switch', async () => {
    const ring = Array.from({ length: 1200 }, (_, i) => [10 + 0.5 + 0.4 * Math.cos((i / 1200) * 2 * Math.PI), 47.5 + 0.4 * Math.sin((i / 1200) * 2 * Math.PI)]);
    useAppStore.setState({ aoi: { type: 'Polygon', coordinates: [[...ring, ring[0]]] }, searchFilters: {} });
    steps = [{ scenes: [], checked: 0 }];
    await state().runSearch();
    expect(asked[0]).not.toHaveProperty('earthx:aoi');
  });

  it('leaves the cloud filter out of the other datasets of a mixed search', async () => {
    reset(['optical', 'radar']);
    useAppStore.getState().setSearchFilter('radar', 'test:track', range('1', '5'));
    steps = [{ scenes: [], checked: 0, byCollection: { optical: { checked: 0, found: 0, unreadable: 0, limit_reached: false } } }];
    await state().runSearch();
    expect(asked[0].query_by_collection).toEqual({
      optical: { [AOI_CLOUD_PROPERTY]: { lte: 20 } },
      radar: { 'test:track': { gte: 1, lte: 5 } },
    });
  });
});

describe('the walk through the answers', () => {
  it('goes on after answers without a scene until the server has nothing more, and shows the count at the end', async () => {
    steps = [
      { checked: 100, next: 't2' },
      { checked: 200, next: 't3' },
      { scenes: [scene('a'), scene('b')], checked: 260 },
    ];
    await state().runSearch();
    expect(asked.map((a) => a.token)).toEqual([undefined, 't2', 't3']);
    expect(sceneIds()).toEqual(['a', 'b']);
    expect(state().searchContext?.answer.aoiFilter).toEqual({ optical: { checked: 260, found: 2, unreadable: 0, limitReached: false } });
    expect(state().searchContext?.nextToken).toBeNull();
    expect(state().aoiWalking).toBe(false);
    expect(state().searching).toBe(false);
  });

  it('shows each answer while it goes on, and opens the list with the first scenes', async () => {
    steps = [
      { checked: 100, found: 0, next: 't2' },
      { scenes: [scene('a')], checked: 200, next: 't3' },
      { scenes: [scene('b', 'optical', '2026-07-09')], checked: 260 },
    ];
    const seen: { items: string[]; checked: number | undefined; walking: boolean; searching: boolean; dock: string | null; notice: string | null }[] = [];
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
      // What the screen shows when the next answer is asked for.
      seen.push({
        items: sceneIds(),
        checked: state().searchContext?.answer.aoiFilter?.optical?.checked,
        walking: state().aoiWalking,
        searching: state().searching,
        dock: state().dock,
        notice: state().notice,
      });
      return json(respond(JSON.parse(init!.body as string)));
    });
    await state().runSearch();
    expect(seen.map((s) => s.items)).toEqual([[], [], ['a']]);
    expect(seen.map((s) => s.checked)).toEqual([undefined, 100, 200]);
    expect(seen.every((s) => s.walking && s.searching)).toBe(true);
    // The list opens when scenes arrive, and says nothing final before the end.
    expect(seen.map((s) => s.dock)).toEqual([null, null, 'results']);
    expect(seen.every((s) => s.notice === null)).toBe(true);
    expect(sceneIds()).toEqual(['a', 'b']);
    expect(state().dock).toBe('results');
    expect(state().notice).toContain('2 scene(s)');
  });

  it('stops at a full page and leaves the token for "Load more", which fills the next page the same way', async () => {
    const crowd = (prefix: string) => Array.from({ length: 100 }, (_, i) => scene(`${prefix}${i}`));
    steps = [
      { scenes: crowd('a'), checked: 100, next: 't2' },
      { scenes: crowd('b'), checked: 200, next: 't3' },
      { scenes: crowd('c'), checked: 300, next: 't4' },
      { checked: 400, next: 't5' },
      { scenes: [scene('late')], checked: 410 },
    ];
    await state().runSearch();
    expect(asked).toHaveLength(3);
    expect(state().items).toHaveLength(300);
    expect(state().searchContext?.nextToken).toBe('t4');
    expect(state().aoiWalking).toBe(false);

    await state().loadMore();
    expect(asked.slice(3).map((a) => a.token)).toEqual(['t4', 't5']);
    expect(state().items).toHaveLength(301);
    expect(sceneIds().filter((id) => id === 'late')).toHaveLength(1);
    expect(state().searchContext?.nextToken).toBeNull();
    expect(state().loadMoreUsed).toBe(true);
    expect(state().loadingMore).toBe(false);
    // "Load more" asks what the search asked.
    for (const request of asked) {
      expect(request.query_by_collection).toEqual({ optical: { [AOI_CLOUD_PROPERTY]: { lte: 20 } } });
    }
  });

  it('does not lay out the list again on a later answer: ticks and the open time step stay', async () => {
    steps = [
      { scenes: [scene('a')], checked: 100, next: 't2' },
      { scenes: [scene('b', 'optical', '2026-07-09')], checked: 200, next: 't3' },
      { scenes: [scene('c', 'optical', '2026-07-08')], checked: 300 },
    ];
    let ticked = false;
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
      if (asked.length === 1 && !ticked) {
        ticked = true;
        useAppStore.getState().toggleSelected('a');
      }
      return json(respond(JSON.parse(init!.body as string)));
    });
    await state().runSearch();
    expect(state().selectedIds).toEqual(['a']);
    expect(sceneIds()).toEqual(['a', 'b', 'c']);
  });

  it('reports the end of the limit, and offers no token', async () => {
    steps = [
      { scenes: [scene('a')], checked: 100, next: 't2' },
      { checked: 500, found: 1, limit: true, next: null },
    ];
    await state().runSearch();
    expect(state().searchContext?.answer.aoiFilter?.optical).toEqual({ checked: 500, found: 1, unreadable: 0, limitReached: true });
    expect(state().searchContext?.nextToken).toBeNull();
  });

  it('says in the notice that nothing is within the limit, how far it checked and what it could not read, for one dataset', async () => {
    steps = [{ checked: 500, found: 0, unreadable: 2, limit: true }];
    await state().runSearch();
    expect(state().notice).toBe(
      'No scenes within the AOI limit in this date range (500 checked). Checked 500 scenes. Narrow the date range to search further. 2 scenes could not be checked.',
    );
    expect(state().sections[0].items).toEqual([]);
  });

  it('leaves the hints to the head of the dataset when there is a list to show them in', async () => {
    steps = [{ scenes: [scene('a')], checked: 500, limit: true, unreadable: 1 }];
    await state().runSearch();
    expect(state().notice).toBe('1 scene(s) in 1 time step(s).');
  });

  it('does not look for the nearest date around a range that was searched with the limit (KE4)', async () => {
    steps = [{ checked: 120, found: 0 }];
    await state().runSearch();
    // One request: the walk. The fallback would ask again around the dates.
    expect(asked).toHaveLength(1);
    expect(state().fallbackDatasetIds).toEqual([]);
    expect(state().sections[0].origin).toBe('search');
  });

  it('keeps the last counts of a dataset that a later answer of a mixed search no longer names', async () => {
    reset(['optical', 'radar']);
    steps = [
      { scenes: [scene('a')], checked: 0, next: 't2', byCollection: { optical: { checked: 100, found: 1, unreadable: 0, limit_reached: false } } },
      { scenes: [scene('r1', 'radar')], checked: 0, byCollection: {} },
    ];
    // An answer that names no source at all carries neither of the two keys.
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
      const answered = respond(JSON.parse(init!.body as string)) as Record<string, unknown>;
      if (stepIndex === 2) {
        delete answered['earthx:aoi_filter_by_collection'];
        delete answered['earthx:aoi_filter'];
      }
      return json(answered);
    });
    await state().runSearch();
    expect(state().searchContext?.answer.aoiFilter).toEqual({ optical: { checked: 100, found: 1, unreadable: 0, limitReached: false } });
    expect(state().sections.map((s) => s.items.length)).toEqual([1, 1]);
  });
});

describe('ending the walk', () => {
  // The second answer is held back until the test lets it go (or the request is dropped).
  function holdSecond() {
    let release!: () => void;
    const held = new Promise<void>((resolve) => (release = resolve));
    let signal: AbortSignal | null | undefined;
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
      const request = JSON.parse(init!.body as string) as Record<string, unknown>;
      if (asked.length === 1) {
        signal = init?.signal;
        asked.push(request);
        stepIndex += 1;
        await new Promise<void>((resolve, reject) => {
          signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
          void held.then(resolve);
        });
        return json(body(steps[1]));
      }
      return json(respond(request));
    });
    return { release, signalOf: () => signal };
  }

  it('"Stop" drops the request in flight and keeps what is found and the token, so "Load more" goes on from there', async () => {
    steps = [
      { scenes: [scene('a')], checked: 100, next: 't2' },
      { scenes: [scene('b')], checked: 200, next: 't3' },
      { scenes: [scene('c')], checked: 300 },
    ];
    const hold = holdSecond();
    const run = state().runSearch();
    await vi.waitFor(() => expect(asked).toHaveLength(2));
    expect(state().aoiWalking).toBe(true);

    state().stopSearch();
    await run;

    expect(hold.signalOf()?.aborted).toBe(true);
    expect(sceneIds()).toEqual(['a']);
    expect(state().aoiWalking).toBe(false);
    expect(state().searching).toBe(false);
    expect(state().error).toBeNull();
    expect(state().searchContext?.nextToken).toBe('t2');
    expect(state().searchContext?.answer.aoiFilter?.optical?.checked).toBe(100);
    // The verdict of the notice is given now.
    expect(state().notice).toContain('1 scene(s)');

    await state().loadMore();
    // The request that was dropped is asked again from the token before it, and the walk then ends.
    expect(asked.map((a) => a.token)).toEqual([undefined, 't2', 't2']);
    expect(sceneIds()).toEqual(['a', 'c']);
    expect(state().searchContext?.nextToken).toBeNull();
  });

  it('"Stop" before the first answer leaves a search without results and no error', async () => {
    steps = [{ scenes: [scene('a')], checked: 100 }];
    fetchMock.mockImplementation(
      (_url: string, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          asked.push(JSON.parse(init!.body as string));
          init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
        }),
    );
    const run = state().runSearch();
    await vi.waitFor(() => expect(asked).toHaveLength(1));
    state().stopSearch();
    await run;
    expect(state().error).toBeNull();
    expect(state().searching).toBe(false);
    expect(state().aoiWalking).toBe(false);
    expect(sceneIds()).toEqual([]);
  });

  it('"Stop" with nothing found says so, and does not claim that nothing is within the limit', async () => {
    steps = [{ checked: 100, found: 0, next: 't2' }];
    let hold = false;
    fetchMock.mockImplementation((_url: string, init?: RequestInit) => {
      if (asked.length >= 1) {
        hold = true;
        asked.push(JSON.parse(init!.body as string));
        return new Promise<Response>((_resolve, reject) => init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError'))));
      }
      return Promise.resolve(json(respond(JSON.parse(init!.body as string))));
    });
    const run = state().runSearch();
    await vi.waitFor(() => expect(hold).toBe(true));
    state().stopSearch();
    await run;
    // No verdict in the notice: the list is there, with how far it got and "Load more" (Otto, 31.10.2026).
    expect(state().notice).toBeNull();
    expect(state().sections[0].keepList).toBe(true);
    expect(hasResultsPanel(state().sections)).toBe(true);
    expect(state().dock).toBe('results');
    expect(state().searchContext?.answer.aoiFilter?.optical).toMatchObject({ found: 0, checked: 100 });
    expect(state().searchContext?.nextToken).toBe('t2');
    expect(state().aoiWalking).toBe(false);
  });

  it('"Load more" after a "Stop" without a scene goes on from the token, and the list stays when scenes come', async () => {
    steps = [{ checked: 100, found: 0, next: 't2' }, { scenes: [scene('a')], checked: 150 }];
    let hold = true;
    fetchMock.mockImplementation((_url: string, init?: RequestInit) => {
      const request = JSON.parse(init!.body as string) as Record<string, unknown>;
      if (hold && asked.length >= 1) {
        asked.push(request);
        return new Promise<Response>((_resolve, reject) => init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError'))));
      }
      return Promise.resolve(json(respond(request)));
    });
    const run = state().runSearch();
    await vi.waitFor(() => expect(asked).toHaveLength(2));
    state().stopSearch();
    await run;
    hold = false;
    stepIndex = 1;
    await state().loadMore();
    expect(asked[asked.length - 1].token).toBe('t2');
    expect(sceneIds()).toEqual(['a']);
    expect(state().sections[0].keepList).toBeUndefined();
    expect(state().dock).toBe('results');
    expect(state().aoiWalking).toBe(false);
  });

  it('a finished search without a scene is no list: nothing is left to go on with', async () => {
    steps = [{ checked: 100, found: 0 }];
    await state().runSearch();
    expect(state().sections[0].keepList).toBeUndefined();
    expect(hasResultsPanel(state().sections)).toBe(false);
    expect(state().notice).toBe('No scenes within the AOI limit in this date range (100 checked).');
  });

  it('a failing answer while nothing is found is a failed search, not "no scenes within the limit"', async () => {
    steps = [{ checked: 100, found: 0, next: 't2' }];
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) =>
      asked.length >= 1 ? json({ detail: 'upstream broke' }, 502) : json(respond(JSON.parse(init!.body as string))),
    );
    await state().runSearch();
    expect(state().error).toContain('Search failed');
    expect(state().notice).toBeNull();
    expect(state().searchContext).toBeNull();
  });

  it('a change of the dates before the first answer ends the search with a word, not in silence', async () => {
    steps = [{ scenes: [scene('a')], checked: 100 }];
    let release!: () => void;
    const held = new Promise<void>((resolve) => (release = resolve));
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
      asked.push(JSON.parse(init!.body as string));
      await held;
      return json(body(steps[0]));
    });
    const run = state().runSearch();
    await vi.waitFor(() => expect(asked).toHaveLength(1));
    state().setDateTo('2026-08-15');
    release();
    await run;
    expect(state().notice).toBe('Search stopped.');
    expect(state().aoiWalking).toBe(false);
  });

  it('a change of the dates ends the walk and the search cannot be continued, but what was found stays', async () => {
    steps = [
      { scenes: [scene('a')], checked: 100, next: 't2' },
      { scenes: [scene('b')], checked: 200, next: 't3' },
    ];
    const hold = holdSecond();
    const run = state().runSearch();
    await vi.waitFor(() => expect(asked).toHaveLength(2));

    state().setDateTo('2026-08-15');
    await run;

    expect(hold.signalOf()?.aborted).toBe(true);
    expect(sceneIds()).toEqual(['a']);
    expect(state().searchContext?.nextToken).toBeNull();
    expect(state().aoiWalking).toBe(false);
  });

  it('a change of the filters ends the walk', async () => {
    steps = [
      { scenes: [scene('a')], checked: 100, next: 't2' },
      { scenes: [scene('b')], checked: 200 },
    ];
    const hold = holdSecond();
    const run = state().runSearch();
    await vi.waitFor(() => expect(asked).toHaveLength(2));
    state().setSearchFilter('optical', 'test:cloud', range('', '10'));
    await run;
    expect(hold.signalOf()?.aborted).toBe(true);
    expect(state().searchContext?.nextToken).toBeNull();
  });

  it('a change of the area ends the walk', async () => {
    steps = [
      { scenes: [scene('a')], checked: 100, next: 't2' },
      { scenes: [scene('b')], checked: 200 },
    ];
    const hold = holdSecond();
    const run = state().runSearch();
    await vi.waitFor(() => expect(asked).toHaveLength(2));
    useAppStore.getState().setAoi(TRIANGLE);
    await run;
    expect(hold.signalOf()?.aborted).toBe(true);
    expect(state().searchContext?.nextToken).toBeNull();
  });

  it('a new search or clearing the results drops the walk, and nothing it brings shows up afterwards', async () => {
    steps = [
      { scenes: [scene('a')], checked: 100, next: 't2' },
      { scenes: [scene('b')], checked: 200 },
    ];
    const hold = holdSecond();
    const run = state().runSearch();
    await vi.waitFor(() => expect(asked).toHaveLength(2));
    state().clearSearchResults();
    hold.release();
    await run;
    expect(hold.signalOf()?.aborted).toBe(true);
    expect(state().sections).toEqual([]);
    expect(state().searchContext).toBeNull();
    expect(state().aoiWalking).toBe(false);
  });

  it('an answer that fails after scenes were shown keeps them and says so, and offers no token', async () => {
    steps = [{ scenes: [scene('a')], checked: 100, next: 't2' }];
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
      if (asked.length >= 1) return json({ detail: 'upstream broke' }, 502);
      return json(respond(JSON.parse(init!.body as string)));
    });
    await state().runSearch();
    expect(sceneIds()).toEqual(['a']);
    expect(state().error).toBeNull();
    expect(state().loadMoreError).toBe('Could not load more results — search again.');
    expect(state().searchContext?.nextToken).toBeNull();
    expect(state().aoiWalking).toBe(false);
    expect(state().searching).toBe(false);
  });

  it('a first answer that fails is a failed search', async () => {
    fetchMock.mockImplementation(async () => json({ detail: 'the cloud share in the AOI needs a date range with a start and an end' }, 400));
    await state().runSearch();
    expect(state().error).toContain('Search failed');
    expect(state().sections).toEqual([]);
    expect(state().aoiWalking).toBe(false);
    expect(state().searching).toBe(false);
  });
});

describe('a search over several datasets', () => {
  const NONE = { optical: { checked: 100, found: 0, unreadable: 0, limit_reached: false } };

  it('keeps the list where the user left it while answers without a scene come in', async () => {
    reset(['optical', 'radar']);
    steps = [
      { checked: 0, next: 't2', byCollection: NONE },
      { checked: 0, next: 't3', byCollection: NONE },
      { checked: 0, byCollection: NONE },
    ];
    const docks: (string | null)[] = [];
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
      docks.push(state().dock);
      if (docks.length === 2) useAppStore.setState({ dock: 'controls' });
      return json(respond(JSON.parse(init!.body as string)));
    });
    await state().runSearch();
    // The list opened with the first answer, the user went back to the controls, and the next answers left it so.
    expect(docks).toEqual([null, 'results', 'controls']);
    expect(state().dock).toBe('controls');
  });

  it('asks the nearest date for a dataset searched without the limit, with no AOI of the limit in it', async () => {
    reset(['optical', 'radar']);
    const ring = Array.from({ length: 1200 }, (_, i) => [10.5 + 0.4 * Math.cos((i / 1200) * 2 * Math.PI), 47.5 + 0.4 * Math.sin((i / 1200) * 2 * Math.PI)]);
    useAppStore.setState({ aoi: { type: 'Polygon', coordinates: [[...ring, ring[0]]] } });
    steps = [{ scenes: [scene('a')], checked: 10, byCollection: { optical: { checked: 10, found: 1, unreadable: 0, limit_reached: false } } }];
    await state().runSearch();
    asked.length = 0;
    state().setOpenSection('radar');
    await vi.waitFor(() => expect(asked.length).toBeGreaterThan(0));
    for (const request of asked) {
      expect(request.collections).toEqual(['radar']);
      expect(request).not.toHaveProperty('earthx:aoi');
      expect(request).not.toHaveProperty('query_by_collection');
    }
  });
});

describe('the switch in the store', () => {
  it('is the choice of a dataset, kept apart from the filters and from the other datasets', () => {
    useAppStore.setState({ searchFilters: {}, searchWithin: {} });
    state().setSearchWithin('optical', true);
    expect(state().searchWithin).toEqual({ optical: true });
    expect(state().searchFilters).toEqual({});
    state().setSearchWithin('radar', true);
    state().setSearchWithin('optical', false);
    expect(state().searchWithin).toEqual({ radar: true });
  });

  it('is gone with "Reset filters" of its dataset, and stays with the others', () => {
    useAppStore.setState({ searchWithin: { optical: true, radar: true } });
    state().resetSearchFilters('optical');
    expect(state().searchWithin).toEqual({ radar: true });
    expect(state().searchFilters.optical).toBeUndefined();
  });

  it('is kept when "Clear search results" is pressed, like the filters', () => {
    state().clearSearchResults();
    expect(state().searchWithin).toEqual({ optical: true });
  });

  it('moves every filter that depends on the area and no other, each under the property the registry names', async () => {
    useAppStore.setState({
      searchFilters: { optical: { 'test:cloud': range('', '20'), 'test:nodata': range('', '5'), platform: values('sat-a') } },
    });
    steps = [{ scenes: [], checked: 0 }];
    await state().runSearch();
    expect(asked[0].query_by_collection).toEqual({
      optical: { [AOI_CLOUD_PROPERTY]: { lte: 20 }, [AOI_NODATA_PROPERTY]: { lte: 5 }, platform: { in: ['sat-a'] } },
    });
  });

  it('moves nothing while it is off: the scene filters stay what they were', async () => {
    useAppStore.setState({
      searchWithin: {},
      searchFilters: { optical: { 'test:cloud': range('', '20'), 'test:nodata': range('', '5') } },
    });
    steps = [{ scenes: [], checked: 0 }];
    await state().runSearch();
    expect(asked[0].query_by_collection).toEqual({ optical: { 'test:cloud': { lte: 20 }, 'test:nodata': { lte: 5 } } });
    expect(state().aoiWalking).toBe(false);
  });

  it('measures a search with the share of no data alone, and walks it like any other', async () => {
    useAppStore.setState({ searchFilters: { optical: { 'test:nodata': range('', '5') } } });
    steps = [{ checked: 100, next: 't2' }, { scenes: [scene('a')], checked: 150 }];
    await state().runSearch();
    expect(asked.map((a) => a.query_by_collection)).toEqual([
      { optical: { [AOI_NODATA_PROPERTY]: { lte: 5 } } },
      { optical: { [AOI_NODATA_PROPERTY]: { lte: 5 } } },
    ]);
    expect(sceneIds()).toEqual(['a']);
  });

  it('is changed on the page token of a search on screen, like a filter: it cannot be continued', async () => {
    steps = [{ scenes: [scene('a')], checked: 100, next: 't2' }];
    await state().runSearch();
    expect(state().searchContext?.nextToken).toBe('t2');
    state().setSearchWithin('optical', false);
    expect(state().searchContext?.nextToken).toBeNull();
  });
});

describe('the coverage map', () => {
  const coverageBody = {
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
    footprints_advised: false,
    from_cache: false,
    extent: null,
    area: null,
    ignored_filters: [],
  };
  const coverageQueries = () =>
    fetchMock.mock.calls
      .filter(([url]) => String(url).startsWith('/coverage/'))
      .map(([url, init]) => {
        const parsed = init?.body ? (JSON.parse(init.body as string) as { query?: unknown }) : null;
        if (parsed) return parsed.query;
        const q = new URL(String(url), 'http://x').searchParams.get('query');
        return q ? JSON.parse(q) : undefined;
      });

  beforeEach(() => {
    fetchMock.mockImplementation(async (url: string) => (String(url).startsWith('/coverage/') ? json(coverageBody) : json({ detail: 'x' }, 404)));
  });

  it('gets the filters that do not depend on the area and none of those the switch moves (KE6)', async () => {
    useAppStore.setState({
      searchFilters: { optical: { 'test:cloud': range('', '20'), 'test:nodata': range('', '30'), platform: values('sat-a') } },
      showCoverage: true,
      coverageDatasetId: 'optical',
      mapZoom: 5,
    });
    state().showCoverageFor('optical');
    await vi.waitFor(() => expect(coverageQueries().length).toBeGreaterThan(0));
    expect(coverageQueries()[0]).toEqual({ platform: { in: ['sat-a'] } });
  });

  it('gets the cloud range of the scene when the switch cannot be used and so counts for nothing', async () => {
    useAppStore.setState({
      searchFilters: { optical: { 'test:cloud': range('', '20') } },
      dateFrom: '',
      showCoverage: true,
      coverageDatasetId: 'optical',
      mapZoom: 5,
    });
    state().showCoverageFor('optical');
    await vi.waitFor(() => expect(coverageQueries().length).toBeGreaterThan(0));
    expect(coverageQueries()[0]).toEqual({ 'test:cloud': { lte: 20 } });
  });
});
