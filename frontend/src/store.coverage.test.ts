// @vitest-environment jsdom
//
// The coverage map does not depend on the AOI (UI-04 part 4, Otto, 4.11.2026): it always shows the coverage of the visible map extent (the
// whole world at a small zoom), whether an AOI is drawn or not, and the question carries no AOI. It replaces the rule of M3-19 "with an AOI,
// over the AOI". The rule of the level of #286 (Otto, 03.11.2026) and "the same question is not asked twice" hold as before. The server is a
// stand-in that answers every question with one cell.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { levelForViewport } from './coverage';
import { datasetsFrom } from './datasets';
import { OPTICAL } from './fixtures/searchFilters';
import { useAppStore } from './store';
import type { Bbox } from './types';

// An AOI far from what is in view, so that a question over the AOI cannot be mistaken for one over the view.
const AOI_FAR: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[150, -40], [151, -40], [151, -39], [150, -39], [150, -40]]] };
const AOI_NEAR: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 48], [10, 47]]] };
const WINDOW = { width: 1280, height: 800 };
const VIEW: Bbox = [-20, 20, 40, 60];
const WORLD: Bbox = [-180, -85, 180, 85];

const json = (body: unknown) => ({ ok: true, status: 200, statusText: '', json: async () => body }) as Response;

interface Asked {
  method: string;
  zoom: number;
  bbox: Bbox | null;
  url: string;
  body: string | null;
}
let asked: Asked[];
let searched: { bbox?: Bbox }[];
let advised = false;
// The answers of the extents that were asked are kept for a while (`store.ts`), across tests too: every test asks for a date of its own.
let run = 0;
const dayOfRun = () => new Date(Date.UTC(2000, 0, 1 + run)).toISOString().slice(0, 10);

function answer(zoom: number) {
  return {
    dataset_id: 'optical', grid: 'geotile', level: zoom, counting: 'centroid', cells: [{ k: `${zoom}/0/0`, n: 1 }], counted: 1,
    total_count: 1, completeness: 'complete', max_count: 1, histogram: [], histogram_interval: 'month', footprints_advised: advised,
    from_cache: false, extent: null, area: null, ignored_filters: [],
  };
}

beforeEach(() => {
  run += 1;
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  asked = [];
  searched = [];
  advised = false;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), 'http://localhost');
      if (!url.pathname.startsWith('/coverage/')) {
        if (init?.body) searched.push(JSON.parse(String(init.body)) as { bbox?: Bbox });
        return json({ type: 'FeatureCollection', features: [], links: [] });
      }
      const box = url.searchParams.get('bbox');
      asked.push({
        method: init?.method ?? 'GET',
        zoom: Number(url.searchParams.get('zoom')),
        bbox: box ? (box.split(',').map(Number) as Bbox) : null,
        url: String(input),
        body: typeof init?.body === 'string' ? init.body : null,
      });
      return json(answer(Number(url.searchParams.get('zoom'))));
    }),
  );
  useAppStore.setState({
    datasets: datasetsFrom([OPTICAL]),
    datasetId: 'optical',
    selectedDatasetIds: ['optical'],
    aoi: null,
    showCoverage: false,
    coverage: null,
    coverageDatasetId: null,
    coverageLoading: false,
    dateFrom: dayOfRun(),
    dateTo: '',
    mapZoom: 1.6,
    viewportBbox: VIEW,
    viewportSize: WINDOW,
  });
});

afterEach(() => {
  useAppStore.getState().hideCoverage();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const settle = () => vi.advanceTimersByTimeAsync(1000);
const contains = (outer: Bbox, inner: Bbox) => outer[0] <= inner[0] && outer[1] <= inner[1] && outer[2] >= inner[2] && outer[3] >= inner[3];

describe('the coverage map is the one of the visible extent, whether an AOI is drawn or not', () => {
  it('asks the extent of the map by GET, the level of the map, and nothing of an AOI that is drawn', async () => {
    useAppStore.getState().setAoi(AOI_FAR);
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    const level = levelForViewport(1.6, WINDOW.width, WINDOW.height);
    expect(asked).toHaveLength(1);
    expect(asked[0]).toMatchObject({ method: 'GET', zoom: level, body: null });
    expect(contains(asked[0].bbox!, VIEW)).toBe(true);
    expect(contains(asked[0].bbox!, [150, -40, 151, -39])).toBe(false);
    expect(asked[0].url).not.toMatch(/150|151|-40|-39/u);
  });

  it('answers a map that was hidden and shown again from what it has, whatever the AOI became meanwhile', async () => {
    useAppStore.getState().setAoi(AOI_NEAR);
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    useAppStore.getState().hideCoverage();
    useAppStore.getState().clearAoi();
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    expect(asked).toHaveLength(1);
    expect(useAppStore.getState().coverage).not.toBeNull();
  });

  it('shows the whole world at a small zoom, with an AOI drawn', async () => {
    useAppStore.setState({ mapZoom: 0.8, viewportBbox: WORLD });
    useAppStore.getState().setAoi(AOI_NEAR);
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    expect(contains(asked[0].bbox!, [-180, -80, 180, 80])).toBe(true);
  });

  it('never sends an AOI: no POST, no body, whatever is drawn, changed, loaded as the last one or cleared', async () => {
    useAppStore.getState().showCoverageFor('optical');
    useAppStore.getState().setAoi(AOI_NEAR);
    await settle();
    useAppStore.getState().setAoi(AOI_FAR);
    await settle();
    useAppStore.getState().clearAoi();
    useAppStore.getState().useLastAoi();
    await settle();
    expect(asked.every((q) => q.method === 'GET' && q.body === null)).toBe(true);
    expect(asked.map((q) => q.url).join('\n')).not.toMatch(/intersects|aoi/iu);
  });

  it('does not ask again when an AOI is drawn, changed or cleared: it is the same question', async () => {
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    expect(asked).toHaveLength(1);
    useAppStore.getState().setAoi(AOI_NEAR);
    await settle();
    useAppStore.getState().setAoi(AOI_FAR);
    await settle();
    useAppStore.getState().clearAoi();
    await settle();
    expect(asked).toHaveLength(1);
    expect(useAppStore.getState().coverage).not.toBeNull();
  });

  it('follows the zoom of the map, with an AOI as without', async () => {
    useAppStore.getState().setAoi(AOI_NEAR);
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    useAppStore.getState().setMapViewport(3.2, VIEW, WINDOW);
    await settle();
    expect(asked.at(-1)).toMatchObject({ method: 'GET', zoom: levelForViewport(3.2, WINDOW.width, WINDOW.height) });
  });

  it('follows a pan out of the extent that was asked, whatever the AOI is', async () => {
    useAppStore.getState().setAoi(AOI_NEAR);
    useAppStore.setState({ mapZoom: 5, viewportBbox: [8, 46, 12, 49] });
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    const first = asked[0].bbox!;
    useAppStore.getState().setMapViewport(5, [100, -10, 104, -7], WINDOW);
    await settle();
    expect(asked).toHaveLength(2);
    expect(contains(asked[1].bbox!, [100, -10, 104, -7])).toBe(true);
    expect(contains(asked[1].bbox!, first)).toBe(false);
  });

  it('waits for the map to tell its extent and its size: nothing is asked before, even with an AOI', async () => {
    useAppStore.setState({ viewportSize: null, viewportBbox: null });
    useAppStore.getState().setAoi(AOI_NEAR);
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    expect(asked).toEqual([]);
    useAppStore.getState().setMapViewport(1.6, VIEW, WINDOW);
    await settle();
    expect(asked).toHaveLength(1);
  });

  it('draws the footprints of the extent that is in view, not of the AOI', async () => {
    advised = true;
    useAppStore.setState({ mapZoom: 6, viewportBbox: [8, 46, 12, 49] });
    useAppStore.getState().setAoi(AOI_FAR);
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    expect(searched.length).toBeGreaterThan(0);
    for (const request of searched) {
      expect(contains(request.bbox!, [8, 46, 12, 49])).toBe(true);
      expect(contains(request.bbox!, [150, -40, 151, -39])).toBe(false);
    }
  });
});

describe('the same question is not asked again', () => {
  it('sends one request for many moves of the map at the same level', async () => {
    useAppStore.getState().setAoi(AOI_NEAR);
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    expect(asked).toHaveLength(1);
    for (let i = 0; i < 11; i += 1) {
      useAppStore.getState().setMapViewport(1.6 + i * 0.01, [VIEW[0] + i * 0.02, VIEW[1], VIEW[2] + i * 0.02, VIEW[3]], WINDOW);
      await settle();
    }
    expect(asked).toHaveLength(1);
    expect(useAppStore.getState().coverageLoading).toBe(false);
  });

  it('does not ask again while the same question is on its way', async () => {
    useAppStore.getState().setAoi(AOI_NEAR);
    useAppStore.getState().showCoverageFor('optical');
    useAppStore.getState().setMapViewport(1.61, VIEW, WINDOW);
    await settle();
    expect(asked).toHaveLength(1);
  });

  it('asks again when the question changes, and not after the map was hidden and shown (the extent was asked)', async () => {
    useAppStore.getState().setAoi(AOI_NEAR);
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    useAppStore.getState().setDateFrom('2026-01-01');
    await settle();
    expect(asked).toHaveLength(2);
    useAppStore.getState().hideCoverage();
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    expect(asked).toHaveLength(2);
  });

  it('asks again when the zoom crosses the brake of the footprints at the same level, and the source advises them', async () => {
    advised = true;
    const wide = { width: 1920, height: 1080 };
    expect(levelForViewport(3.99, wide.width, wide.height)).toBe(levelForViewport(4.01, wide.width, wide.height));
    useAppStore.setState({ mapZoom: 3.99, viewportSize: wide });
    useAppStore.getState().setAoi(AOI_NEAR);
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    useAppStore.getState().setMapViewport(4.01, VIEW, wide);
    await settle();
    expect(asked).toHaveLength(2);
  });

  it('asks again after a failed answer', async () => {
    useAppStore.getState().setAoi(AOI_NEAR);
    await settle();
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 502, statusText: 'Bad Gateway', json: async () => ({ detail: 'x' }) } as Response);
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    expect(useAppStore.getState().coverageError).not.toBeNull();
    useAppStore.getState().setMapViewport(1.62, VIEW, WINDOW);
    await settle();
    expect(asked).toHaveLength(1);
    expect(useAppStore.getState().coverage?.level).toBe(levelForViewport(1.6, WINDOW.width, WINDOW.height));
  });
});
