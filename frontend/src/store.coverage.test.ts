// @vitest-environment jsdom
//
// The coverage map after a search (Otto, 03.11.2026): a search needs an AOI, and with an AOI the coverage asked for the
// level of the map's zoom alone, four to five levels coarser than the map without an AOI asks at the same zoom. At the
// first zoom of the page that is level 1, four cells for the whole globe: a quarter of the world in one cell. And every
// `moveend` sent the same question again. The server is a stand-in that answers every question with one cell.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { levelForViewport } from './coverage';
import { datasetsFrom } from './datasets';
import { OPTICAL } from './fixtures/searchFilters';
import { useAppStore } from './store';
import type { Bbox } from './types';

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 48], [10, 47]]] };
const WINDOW = { width: 1280, height: 800 };
const VIEW: Bbox = [-20, 20, 40, 60];

const json = (body: unknown) => ({ ok: true, status: 200, statusText: '', json: async () => body }) as Response;

let asked: { method: string; zoom: number }[];

function answer(zoom: number) {
  return {
    dataset_id: 'optical', grid: 'geotile', level: zoom, counting: 'centroid', cells: [{ k: `${zoom}/0/0`, n: 1 }], counted: 1,
    total_count: 1, completeness: 'complete', max_count: 1, histogram: [], histogram_interval: 'month', footprints_advised: false,
    from_cache: false, extent: null, area: null, ignored_filters: [],
  };
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  asked = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), 'http://localhost');
      if (!url.pathname.startsWith('/coverage/')) return json({ type: 'FeatureCollection', features: [], links: [] });
      const zoom = init?.method === 'POST' ? (JSON.parse(String(init.body)) as { zoom: number }).zoom : Number(url.searchParams.get('zoom'));
      asked.push({ method: init?.method ?? 'GET', zoom });
      return json(answer(zoom));
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

describe('the coverage map with an AOI', () => {
  it('asks the level of the map without an AOI, not one four levels coarser', async () => {
    const level = levelForViewport(1.6, WINDOW.width, WINDOW.height);
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    expect(asked).toEqual([{ method: 'GET', zoom: level }]);

    useAppStore.getState().setAoi(AOI);
    await settle();
    expect(asked.at(-1)).toEqual({ method: 'POST', zoom: level });
    expect(useAppStore.getState().coverage?.level).toBe(level);
    expect(level).toBeGreaterThan(1);
  });

  it('follows the zoom of the map as the map without an AOI does', async () => {
    useAppStore.getState().setAoi(AOI);
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    useAppStore.getState().setMapViewport(3.2, VIEW, WINDOW);
    await settle();
    expect(asked.at(-1)).toEqual({ method: 'POST', zoom: levelForViewport(3.2, WINDOW.width, WINDOW.height) });
  });

  it('takes the size of the window while the map has not told its own', async () => {
    useAppStore.setState({ viewportSize: null, mapZoom: 1.6 });
    useAppStore.getState().setAoi(AOI);
    await settle();
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    expect(asked).toEqual([{ method: 'POST', zoom: levelForViewport(1.6, window.innerWidth, window.innerHeight) }]);
    expect(asked[0].zoom).toBeGreaterThan(1);
  });
});

describe('the same question is not asked again', () => {
  it('sends one request for many moves of the map at the same level', async () => {
    useAppStore.getState().setAoi(AOI);
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    expect(asked).toHaveLength(1);
    for (let i = 0; i < 11; i += 1) {
      useAppStore.getState().setMapViewport(1.6 + i * 0.01, [VIEW[0] + i, VIEW[1], VIEW[2] + i, VIEW[3]], WINDOW);
      await settle();
    }
    expect(asked).toHaveLength(1);
    expect(useAppStore.getState().coverageLoading).toBe(false);
  });

  it('does not ask again while the same question is on its way', async () => {
    useAppStore.getState().setAoi(AOI);
    useAppStore.getState().showCoverageFor('optical');
    useAppStore.getState().setMapViewport(1.61, VIEW, WINDOW);
    await settle();
    expect(asked).toHaveLength(1);
  });

  it('asks again when the question changes, and after the map was hidden and shown', async () => {
    useAppStore.getState().setAoi(AOI);
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    useAppStore.getState().setDateFrom('2026-01-01');
    await settle();
    expect(asked).toHaveLength(2);
    useAppStore.getState().hideCoverage();
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    expect(asked).toHaveLength(3);
  });

  it('asks again when the zoom crosses the brake of the footprints at the same level', async () => {
    const wide = { width: 1920, height: 1080 };
    expect(levelForViewport(3.99, wide.width, wide.height)).toBe(levelForViewport(4.01, wide.width, wide.height));
    useAppStore.setState({ mapZoom: 3.99, viewportSize: wide });
    useAppStore.getState().setAoi(AOI);
    useAppStore.getState().showCoverageFor('optical');
    await settle();
    useAppStore.getState().setMapViewport(4.01, VIEW, wide);
    await settle();
    expect(asked).toHaveLength(2);
  });

  it('asks again after a failed answer', async () => {
    useAppStore.getState().setAoi(AOI);
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
