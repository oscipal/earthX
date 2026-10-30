// @vitest-environment jsdom
//
// NM4-26 (Otto, 26.10.2026, answer 6): every page of a search is asked exactly once, and on opening only the
// pages that are needed. The only browser call that searches is `POST /stac/search` (`api.searchItems`), so the
// requests are counted there, by body and page token. No backend: `fetch` answers by route.

import { act, StrictMode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';
import { datasetsFrom } from './datasets';
import s2 from './fixtures/processes/sentinel-2-c1-l2a.json';
import { bboxToPolygon } from './geoUtils';
import type { Order } from './processing';
import { useProcessingStore } from './processingStore';
import { useAppStore } from './store';
import type { Collection, StacItem } from './types';

vi.mock('./components/MapView', () => ({ default: () => null }));

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const DATASET = 'sentinel-2-c1-l2a';
const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const ID = 'AbCdEfGhIjKlMnOpQrSt_-';
const EXPIRES = new Date(Date.now() + 30 * 86_400_000).toISOString();
const AOI = bboxToPolygon([10.1, 50.1, 10.2, 50.2]);

const COLLECTION = {
  id: DATASET,
  title: 'Sentinel-2 L2A',
  'earthx:format': 'cog',
  'earthx:license_flags': { tier: 'processing' },
  'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
  'earthx:viewer': {
    group_by: ['datetime'],
    min_zoom: 8,
    max_zoom: 14,
    browse: 'quicklook',
    quicklook_nodata_max: null,
    results_group_by: ['datetime'],
  },
} as unknown as Collection;

const ORDER: Order = {
  recipe_version: 2,
  inputs: [{ name: 'input', dataset: DATASET, groups: [['NEW_A']] }],
  aoi: AOI as GeoJSON.Polygon,
  steps: [{ op: 'band_math', op_version: 2, params: { expression: '(nir - red) / (nir + red)', name: 'NDVI' } }],
  output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['NDVI'] },
};
const VIEW = { center: [10.15, 50.15], zoom: 11.5, range: null };

function scene(id: string, day = '2026-07-01'): StacItem {
  const bbox: [number, number, number, number] = [10, 50, 11, 51];
  return {
    id,
    collection: DATASET,
    bbox,
    geometry: bboxToPolygon(bbox),
    properties: { datetime: `${day}T10:00:00Z` },
    assets: {
      red: { href: 'https://example.org/red.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
      nir: { href: 'https://example.org/nir.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
    },
  };
}

const scenes = (prefix: string, n: number, day?: string) => Array.from({ length: n }, (_, i) => scene(`${prefix}${i}`, day));

// A page of a search: the scenes and, unless it is the last, the token of the next one.
function page(features: StacItem[], next: string | null, extra: Record<string, unknown> = {}) {
  const links = next ? [{ rel: 'next', href: '/stac/search', method: 'POST', body: { token: next } }] : [];
  return { features, numberReturned: features.length, links, ...extra };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

interface Seen {
  method: string;
  url: string;
  body: Record<string, unknown> | null;
}

let seen: Seen[];
// What the search answers to a body; the page tokens `p2`, `p3`, `p4` follow one another.
let answerSearch: (body: Record<string, unknown>) => unknown | Promise<unknown>;

const searches = () => seen.filter((r) => r.method === 'POST' && r.url === '/stac/search');
const tokens = () => searches().map((r) => (r.body?.token as string | undefined) ?? '(none)');
const gets = (url: string) => seen.filter((r) => r.method === 'GET' && r.url === url);

const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
  const method = init?.method ?? 'GET';
  const body = init?.body ? (JSON.parse(init.body as string) as Record<string, unknown>) : null;
  seen.push({ method, url, body });
  if (url === '/stac/collections') return json({ collections: [COLLECTION] });
  if (url === '/stac/search' && method === 'POST') return json(await answerSearch(body ?? {}));
  if (url === `/processing/processes/recipe?dataset=${DATASET}`) return json(s2);
  if (url === `/processing/permalinks/${ID}` && method === 'GET') return json({ order: ORDER, view: VIEW, expires_at: EXPIRES });
  if (url.startsWith(`/stac/collections/${DATASET}/items/`)) return json(scene(decodeURIComponent(url.split('/items/')[1])));
  if (url.includes('/tilejson.json')) return json({ tilejson: '3.0.0' });
  if (url.includes('/statistics?')) return json({ b1: { count: 9, min: -0.2, max: 0.9, percentile_2: -0.1, percentile_98: 0.8, unit: null } });
  return json({ detail: 'not found' }, 404);
});

const flush = () =>
  act(async () => {
    for (let i = 0; i < 40; i++) await Promise.resolve();
  });

function resetStores() {
  useProcessingStore.getState().resetDraft();
  useProcessingStore.setState({ open: false, descriptions: {}, jobs: [], batches: [], groups: [] });
  useAppStore.setState({
    datasets: [],
    selectedDatasetIds: [],
    datasetId: null,
    sections: [],
    openSectionId: null,
    items: [],
    groups: [],
    activeGroupIndex: 0,
    selectedIds: [],
    layers: [],
    aoi: null,
    aoiPoint: null,
    dateFrom: '',
    dateTo: '',
    focusMode: false,
    showCoverage: false,
    coverageDatasetId: null,
    searchContext: null,
    searching: false,
    loadingMore: false,
    loadMoreError: null,
    loadMoreUsed: false,
    fallbackDatasetIds: [],
    error: null,
    notice: null,
    viewportBbox: [10, 50, 10.3, 50.3],
    mapZoom: 11.5,
  });
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  sessionStorage.clear();
  window.history.replaceState(null, '', '/');
  seen = [];
  fetchMock.mockClear();
  answerSearch = () => page([], null);
  vi.stubGlobal('fetch', fetchMock);
  resetStores();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  window.history.replaceState(null, '', '/');
});

describe('opening the app', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it('searches nothing under StrictMode, and loads the collections once for each run of the start effect', async () => {
    vi.useFakeTimers();
    act(() => root.render(<StrictMode><App /></StrictMode>));
    await flush();
    // Nothing waits on a timer either: the coverage map is off, the shelf of jobs is empty.
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    await flush();
    expect(searches()).toHaveLength(0);
    expect(seen.filter((r) => r.url.startsWith('/coverage'))).toHaveLength(0);
    // StrictMode runs the effect of `App` twice in development, so the collections are asked twice. The list is
    // the same both times and the second answer only replaces it; it is no search and no page of one.
    expect(gets('/stac/collections')).toHaveLength(2);
    expect(useAppStore.getState().datasets.map((d) => d.id)).toEqual([DATASET]);
    expect(seen.map((r) => `${r.method} ${r.url}`)).toEqual(['GET /stac/collections', 'GET /stac/collections']);
  });

  it('loads the collections once without StrictMode', async () => {
    act(() => root.render(<App />));
    await flush();
    expect(gets('/stac/collections')).toHaveLength(1);
    expect(searches()).toHaveLength(0);
  });

  it('opens a link with no search at all: the scene of the order is fetched by name, each request once', async () => {
    vi.useFakeTimers();
    window.history.replaceState(null, '', `/?permalink=${ID}`);
    act(() => root.render(<StrictMode><App /></StrictMode>));
    await flush();
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    await flush();
    // `restoreOrder` takes the scenes of the order from the catalog one by one (`selectScenes`), the area and the
    // dates change no search, and the coverage map is off. So a link needs no page of a search: zero.
    expect(searches()).toHaveLength(0);
    expect(tokens()).toEqual([]);
    expect(seen.filter((r) => r.url.startsWith('/coverage'))).toHaveLength(0);
    expect(gets(`/processing/permalinks/${ID}`)).toHaveLength(1);
    expect(gets(`/stac/collections/${DATASET}/items/NEW_A`)).toHaveLength(1);
    expect(gets(`/processing/processes/recipe?dataset=${DATASET}`)).toHaveLength(1);
    // The link was opened: the order is in the panel, the address is clean.
    expect(useProcessingStore.getState().open).toBe(true);
    expect(useAppStore.getState().error).toBeNull();
    expect(useAppStore.getState().selectedIds).toEqual(['NEW_A']);
    expect(window.location.search).toBe('');
  });
});

describe('a search walks its pages once each', () => {
  const PAGES: Record<string, ReturnType<typeof page>> = {
    '': page(scenes('a', 100, '2026-07-24'), 'p2', { numberMatched: 340 }),
    p2: page(scenes('b', 100, '2026-07-25'), 'p3'),
    p3: page(scenes('c', 100, '2026-07-26'), 'p4'),
    p4: page(scenes('d', 40, '2026-07-27'), null),
  };
  const byToken = (body: Record<string, unknown>) => PAGES[(body.token as string | undefined) ?? ''];

  const search = () => useAppStore.getState().runSearch();
  const loadMore = () => useAppStore.getState().loadMore();

  beforeEach(() => {
    useAppStore.setState({ datasets: datasetsFrom([COLLECTION]), selectedDatasetIds: [DATASET], datasetId: DATASET, aoi: AOI });
    answerSearch = byToken;
  });

  it('asks three pages of 100 for 300 or more matches: the tokens (none), p2, p3, each once', async () => {
    await search();
    expect(tokens()).toEqual(['(none)', 'p2', 'p3']);
    expect(searches().every((r) => r.body?.limit === 100)).toBe(true);
    expect(searches().map((r) => r.body?.collections)).toEqual([[DATASET], [DATASET], [DATASET]]);
    expect(useAppStore.getState().items).toHaveLength(300);
    expect(useAppStore.getState().searchContext?.nextToken).toBe('p4');
  });

  it('asks exactly one page for fewer than 100 matches, and for exactly 100 when the source names no next page', async () => {
    answerSearch = () => page(scenes('a', 99), null);
    await search();
    expect(tokens()).toEqual(['(none)']);
    answerSearch = () => page(scenes('a', 100), null);
    seen = [];
    await search();
    expect(tokens()).toEqual(['(none)']);
    expect(useAppStore.getState().searchContext?.nextToken).toBeNull();
  });

  it('asks the three pages and no fourth for exactly 300 matches', async () => {
    answerSearch = (body) => {
      const token = (body.token as string | undefined) ?? '';
      return { '': page(scenes('a', 100), 'p2'), p2: page(scenes('b', 100), 'p3'), p3: page(scenes('c', 100), null) }[token];
    };
    await search();
    expect(tokens()).toEqual(['(none)', 'p2', 'p3']);
    expect(useAppStore.getState().searchContext?.nextToken).toBeNull();
    await loadMore();
    expect(searches()).toHaveLength(3);
  });

  it('asks two pages for 150 matches', async () => {
    answerSearch = (body) => (body.token ? page(scenes('b', 50), null) : page(scenes('a', 100), 'p2'));
    await search();
    expect(tokens()).toEqual(['(none)', 'p2']);
  });

  it('continues with "Load more" at the next token only, once, and a second press asks nothing', async () => {
    await search();
    const before = searches().length;
    await loadMore();
    expect(tokens().slice(before)).toEqual(['p4']);
    expect(tokens()).toEqual(['(none)', 'p2', 'p3', 'p4']);
    expect(useAppStore.getState().searchContext?.nextToken).toBeNull();
    expect(useAppStore.getState().items.length).toBeGreaterThan(300);
    await loadMore();
    expect(searches()).toHaveLength(4);
  });

  it('asks the page of a double press of "Load more" once', async () => {
    await search();
    await Promise.all([loadMore(), loadMore()]);
    expect(tokens()).toEqual(['(none)', 'p2', 'p3', 'p4']);
  });

  it('asks every page once when a second search starts while the first is still walking', async () => {
    await Promise.all([search(), search()]);
    expect(tokens()).toEqual(['(none)', 'p2', 'p3']);
    expect(useAppStore.getState().items).toHaveLength(300);
  });

  it('asks the same pages again for a new search, which is a new question and no repeat', async () => {
    await search();
    await search();
    expect(tokens()).toEqual(['(none)', 'p2', 'p3', '(none)', 'p2', 'p3']);
  });
});

describe('a second press of "Search" while the first walk is still going', () => {
  let container: HTMLDivElement;
  let root: Root;

  const PAGES: Record<string, ReturnType<typeof page>> = {
    '': page(scenes('a', 100, '2026-07-24'), 'p2'),
    p2: page(scenes('b', 100, '2026-07-25'), 'p3'),
    p3: page(scenes('c', 100, '2026-07-26'), 'p4'),
  };

  beforeEach(() => {
    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  const button = (label: string) =>
    [...container.querySelectorAll('button')].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;

  it('is no second walk: the button is off while the search runs, and Enter in the name field cannot start one', async () => {
    let release!: () => void;
    const held = new Promise<void>((resolve) => (release = resolve));
    answerSearch = async (body) => {
      if (!body.token) await held;
      return PAGES[(body.token as string | undefined) ?? ''];
    };
    act(() => root.render(<App />));
    await flush();
    act(() => {
      useAppStore.getState().toggleDatasetSelected(DATASET);
      useAppStore.getState().setAoi(AOI);
    });
    act(() => button('Search')!.click());
    expect(useAppStore.getState().searching).toBe(true);
    await flush();
    expect(searches()).toHaveLength(1);
    expect(button('Searching…')!.disabled).toBe(true);
    act(() => button('Searching…')!.click());
    const field = container.querySelector<HTMLInputElement>('#scene-name-input')!;
    act(() => {
      field.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    });
    await flush();
    expect(searches()).toHaveLength(1);
    await act(async () => release());
    await flush();
    expect(tokens()).toEqual(['(none)', 'p2', 'p3']);
    expect(useAppStore.getState().searching).toBe(false);
  });
});
