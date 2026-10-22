// @vitest-environment jsdom
//
// The result of a finished job as a layer (M4-13c-5): "Add to layers" in the job row,
// the layer it makes, "Overview" and "Expired". No backend: `fetch` answers the
// TileJSON of the tiler only; the tiles are never requested (the map is not here).

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { saveStoredJobs } from '../jobTracker';
import type { MapLayer } from '../layers';
import { layerProcessBlock, setTrackerOptions, useProcessingStore, type JobEntry } from '../processingStore';
import { MIN_REMAINING_MS, resultStats } from '../resultLayer';
import { useAppStore } from '../store';
import JobList, { EXPIRED_TEXT, JobRow } from './JobList';
import LayerManager, { EXPIRED_LAYER_TEXT, RESAMPLED_LAYER_TEXT } from './LayerManager';
import PreviewBadge, { OVERVIEW_TITLE } from './PreviewBadge';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const JOB = 'AbCdEfGhIjKlMnOpQrSt_-';
const RESULT = 'ZyXwVuTsRqPoNmLkJiHg_-';
const HREF = `/results/${RESULT}/WebMercatorQuad/tilejson.json`;
const TILE_JSON = { bounds: [10, 50, 11, 51], minzoom: 8, maxzoom: 14, data_type: 'float32', tiles: ['http://tiler/x'] };

function entry(over: Partial<JobEntry> = {}): JobEntry {
  return {
    jobID: JOB,
    expires: new Date(Date.now() + 86_400_000).toISOString(),
    status: null,
    phase: 'successful',
    files: [{ file: 'result.tif', label: 'Result (COG)' }],
    resampled: false,
    failure: null,
    error: null,
    cancelling: false,
    expired: false,
    title: 'Band math · Sentinel-2 L2A',
    tiles: { href: HREF, width: 1000, gsd: 10 },
    statistics: null,
    unit: null,
    range: null,
    ...over,
  };
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': status === 200 ? 'application/json' : 'application/problem+json' },
  });
}

let container: HTMLDivElement;
let root: Root;
let fetchMock: ReturnType<typeof vi.fn>;
let tileJson: () => Response | Promise<Response>;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  tileJson = () => json(TILE_JSON);
  fetchMock = vi.fn(async (url: string) => {
    if (url === HREF) return tileJson();
    return json({ title: 'Not found' }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  useProcessingStore.getState().resetDraft();
  useProcessingStore.setState({ open: false, jobsOpen: true, jobs: [entry()], preview: null });
  useAppStore.setState({ layers: [], layerManagerOpen: true, mapZoom: 5, viewportBbox: null, notice: null, datasets: [] });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

async function flush() {
  await act(async () => {
    for (let i = 0; i < 5; i++) await Promise.resolve();
  });
}

function button(label: string | RegExp, within: Element = container): HTMLButtonElement | undefined {
  return [...within.querySelectorAll('button')].find((b) =>
    typeof label === 'string' ? b.textContent?.trim() === label : label.test(b.textContent ?? ''),
  ) as HTMLButtonElement | undefined;
}

function click(element: HTMLElement | undefined) {
  if (!element) throw new Error(`nothing to click in ${container.textContent}`);
  act(() => element.dispatchEvent(new MouseEvent('click', { bubbles: true })));
}

const layers = () => useAppStore.getState().layers;

async function showOnMap() {
  act(() => root.render(<JobList />));
  click(button('Add to layers'));
  await flush();
}

describe('"Add to layers" in the row of a finished job', () => {
  it('is one button, with no menu behind it', () => {
    act(() => root.render(<JobList />));
    const add = button('Add to layers');
    expect(add).toBeDefined();
    expect(add?.hasAttribute('aria-expanded')).toBe(false);
    click(add);
    expect(container.textContent).not.toContain('As a new layer');
    expect(container.textContent).not.toContain('Show on map');
    expect(container.textContent).not.toContain('Replace');
  });

  it('is not offered for a job without tiles (an export, a result from before the link)', () => {
    useProcessingStore.setState({ jobs: [entry({ tiles: null })] });
    act(() => root.render(<JobList />));
    expect(button('Add to layers')).toBeUndefined();
  });

  it.each([
    ['still running', { phase: 'active' as const }],
    ['failed', { phase: 'failed' as const }],
    ['dismissed', { phase: 'dismissed' as const }],
    ['gone', { phase: 'gone' as const }],
    ['known to be expired', { expired: true }],
  ])('is not offered for a job that is %s', (_, over) => {
    useProcessingStore.setState({ jobs: [entry(over)] });
    act(() => root.render(<JobList />));
    expect(button('Add to layers')).toBeUndefined();
  });

  it('is gone from a minute before the results go, and the row says "Expired"', () => {
    vi.useFakeTimers();
    useProcessingStore.setState({ jobs: [entry({ expires: new Date(Date.now() + MIN_REMAINING_MS + 5000).toISOString() })] });
    act(() => root.render(<JobRow job={useProcessingStore.getState().jobs[0]} />));
    expect(button('Add to layers')).toBeDefined();
    act(() => {
      vi.advanceTimersByTime(5100);
    });
    expect(button('Add to layers')).toBeUndefined();
    expect(container.textContent).toContain(EXPIRED_TEXT);
  });
});

describe('the layer a result becomes', () => {
  it('is named after the operator and holds the tiles of the result', async () => {
    await showOnMap();
    expect(fetchMock).toHaveBeenCalledWith(HREF, expect.anything());
    expect(layers()).toHaveLength(1);
    const layer = layers()[0];
    expect(layer.name).toBe('Result · Band math');
    expect(layer.derived).toBe('result');
    expect(layer.visible).toBe(true);
    expect(layer.result).toEqual({ jobID: JOB, expires: expect.any(String), gsd: 10, resampled: false, unit: null, expired: false });
    expect(layer.overlays).toEqual([
      {
        kind: 'raster',
        tileUrl: `/results/${RESULT}/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=256&colormap_name=rdylgn&rescale=-1%2C1`,
        bounds: [10, 50, 11, 51],
        minZoom: 8,
        maxZoom: 15, // one level beyond the TileJSON's 14: its `maxzoom` can be coarser than the data
      },
    ]);
  });

  it('is drawn with the range of the preview, as it stands', async () => {
    useProcessingStore.setState({ range: { vmin: '0', vmax: '0.5', colormap: 'viridis' } });
    await showOnMap();
    expect(layers()[0].overlays[0]).toMatchObject({
      tileUrl: expect.stringContaining('colormap_name=viridis&rescale=0%2C0.5'),
    });
  });

  describe('with the statistics of the result (M4-32b)', () => {
    const DEM = { minimum: 100, maximum: 2400, mean: 900, count: 1000, valid_percent: 100, percentile_2: 180, percentile_98: 1900 };
    const NDVI = { minimum: -0.3, maximum: 0.9, mean: 0.4, count: 1000, valid_percent: 90, percentile_2: -0.05, percentile_98: 0.8 };
    const properties = (statistics: object, extra: object = {}) => ({ bands: [{ name: 'b', data_type: 'float32', statistics }], ...extra });
    const EXPRESSION = { 'processing:expression': { format: 'numexpr', expression: '(a-b)/(a+b)' } };
    const urlOfLayer = () => (layers()[0].overlays[0] as { tileUrl: string }).tileUrl;

    it('is drawn with 2–98 % of the AOI in viridis for a DEM, not a single colour', async () => {
      useProcessingStore.setState({ jobs: [entry({ statistics: resultStats(properties(DEM)) })] });
      await showOnMap();
      expect(urlOfLayer()).toContain('colormap_name=viridis&rescale=180%2C1900');
    });

    it('is drawn like before for an index: −1…1 in rdylgn', async () => {
      useProcessingStore.setState({ jobs: [entry({ statistics: resultStats(properties(NDVI, EXPRESSION)) })] });
      await showOnMap();
      expect(urlOfLayer()).toContain('colormap_name=rdylgn&rescale=-1%2C1');
    });

    it('is drawn with the range the job was started with by hand, before the statistics', async () => {
      const hand = { vmin: '0', vmax: '3000', colormap: 'terrain' };
      useProcessingStore.setState({ jobs: [entry({ statistics: resultStats(properties(DEM)), range: hand })] });
      await showOnMap();
      expect(urlOfLayer()).toContain('colormap_name=terrain&rescale=0%2C3000');
    });

    it('is drawn with its own statistics when the range of the panel was set by hand for another job', async () => {
      // An NDVI preview with a range by hand; the DEM job before it was started without one.
      useProcessingStore.setState({
        range: { vmin: '0', vmax: '0.5', colormap: 'greys' },
        jobs: [entry({ statistics: resultStats(properties(DEM)), range: null })],
      });
      await showOnMap();
      expect(urlOfLayer()).toContain('colormap_name=viridis&rescale=180%2C1900');
    });

    it('keeps the range of one job from the result of another', async () => {
      const OTHER = 'QrStUvWxYzAbCdEfGhIjKl';
      const OTHER_HREF = `/results/${OTHER}/WebMercatorQuad/tilejson.json`;
      fetchMock.mockImplementation(async (url: string) => (url === HREF || url === OTHER_HREF ? tileJson() : json({}, 404)));
      useProcessingStore.setState({
        jobs: [
          entry({ statistics: resultStats(properties(DEM)), range: { vmin: '0', vmax: '3000', colormap: 'terrain' } }),
          entry({ jobID: 'ZZCdEfGhIjKlMnOpQrSt_-', tiles: { href: OTHER_HREF, width: 1000, gsd: 10 }, statistics: resultStats(properties(DEM)) }),
        ],
      });
      await useProcessingStore.getState().showResultOnMap(JOB);
      await useProcessingStore.getState().showResultOnMap('ZZCdEfGhIjKlMnOpQrSt_-');
      const urls = layers().map((l) => (l.overlays[0] as { tileUrl: string }).tileUrl);
      expect(urls.filter((u) => u.includes('terrain'))).toHaveLength(1);
      expect(urls.filter((u) => u.includes('colormap_name=viridis&rescale=180%2C1900'))).toHaveLength(1);
    });

    it('is drawn with the range of the panel for a job without statistics', async () => {
      useProcessingStore.setState({ jobs: [entry({ statistics: null })] });
      await showOnMap();
      expect(urlOfLayer()).toContain('colormap_name=rdylgn&rescale=-1%2C1');
    });

    describe('read from the results document of a job', () => {
      const STATUS = { jobID: JOB, status: 'successful', message: '', progress: 100, expires: new Date(Date.now() + 86_400_000).toISOString() };

      afterEach(() => setTrackerOptions({}));

      async function readJob(result: Record<string, unknown>) {
        const document = { result: { href: `/processing/jobs/${JOB}/results/result.tif`, properties: result }, tiles: { href: HREF } };
        fetchMock.mockImplementation(async (url: string) => {
          if (url === HREF) return tileJson();
          if (url === `/processing/jobs/${JOB}/results`) return json(document);
          return json({ title: 'Not found' }, 404);
        });
        setTrackerOptions({ EventSource: null, fetchJob: async () => STATUS as never, pollMs: 60_000 });
        useProcessingStore.setState({ jobs: [] });
        // As a reload does: the tab remembers the job, the server says it is done, the results are read.
        saveStoredJobs([{ jobID: JOB, expires: STATUS.expires, title: 'Reproject · Copernicus DEM' }]);
        act(() => useProcessingStore.getState().resumeJobs());
        await flush();
        return useProcessingStore.getState().jobs[0];
      }

      it('keeps the statistics of the AOI at the job, and draws the layer from them', async () => {
        const job = await readJob(properties(DEM));
        expect(job.statistics).toEqual({
          bands: [{ minimum: 100, maximum: 2400, percentile2: 180, percentile98: 1900 }],
          expression: false,
        });
        act(() => root.render(<JobList />));
        click(button('Add to layers'));
        await flush();
        expect(urlOfLayer()).toContain('colormap_name=viridis&rescale=180%2C1900');
      });

      it('keeps the expression, so that an index is known by its values', async () => {
        const job = await readJob(properties(NDVI, EXPRESSION));
        expect(job.statistics?.expression).toBe(true);
      });

      it('has no range of its own once taken up again: the tab does not keep it', async () => {
        const job = await readJob(properties(DEM));
        expect(job.range).toBeNull();
      });

      it('has none for a document from before they were written, and the layer is drawn as before', async () => {
        const job = await readJob({ bands: [{ name: 'b', data_type: 'float32' }], gsd: 10 });
        expect(job.statistics).toBeNull();
        expect(job.tiles).not.toBeNull();
        act(() => root.render(<JobList />));
        click(button('Add to layers'));
        await flush();
        expect(urlOfLayer()).toContain('colormap_name=rdylgn&rescale=-1%2C1');
      });
    });
  });

  it('is drawn as it is when the result is not floating point', async () => {
    tileJson = () => json({ ...TILE_JSON, data_type: 'uint16' });
    await showOnMap();
    expect(layers()[0].overlays[0]).toMatchObject({ tileUrl: `/results/${RESULT}/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=256` });
  });

  it('carries no address, no order and no AOI in its text', async () => {
    useAppStore.setState({ aoi: { type: 'Polygon', coordinates: [[[10.1, 50.1], [10.2, 50.1], [10.2, 50.2], [10.1, 50.1]]] } });
    await showOnMap();
    const text = JSON.stringify(layers()[0].overlays) + layers()[0].name;
    expect(text).not.toContain('10.1');
    expect(text).not.toContain('X-Amz');
    expect(text).not.toContain('objectstore');
    expect(layers()[0].restore.itemIds).toEqual([]);
  });

  it('is cut to the area by the tiler, not by the browser: the layer is the same with an AOI, without one, and after a reload', async () => {
    await showOnMap();
    const plain = layers()[0].overlays;
    act(() => useAppStore.setState({ layers: [], aoi: { type: 'Polygon', coordinates: [[[10.1, 50.1], [10.2, 50.1], [10.2, 50.2], [10.1, 50.1]]] }, cropToAoi: true }));
    useProcessingStore.setState({ jobs: [entry()] });
    await showOnMap();
    expect(layers()[0].overlays).toEqual(plain);
    expect(layers()[0].restore.cropToAoi).toBe(false);
    expect(JSON.stringify(layers()[0].overlays)).not.toMatch(/clip|aoi|polygon/i);
  });

  it('works out the pixel size of a geographic result from the columns', async () => {
    useProcessingStore.setState({ jobs: [entry({ tiles: { href: HREF, width: 1000, gsd: null } })] });
    tileJson = () => json({ ...TILE_JSON, bounds: [0, -0.5, 1, 0.5] });
    await showOnMap();
    expect(layers()[0].result?.gsd).toBeCloseTo(111.32, 1);
  });

  it('is one layer for a job, however often it is asked for', async () => {
    await showOnMap();
    act(() => useAppStore.getState().toggleLayerVisible(layers()[0].id));
    expect(layers()[0].visible).toBe(false);
    click(button('Add to layers'));
    await flush();
    expect(layers()).toHaveLength(1);
    expect(layers()[0].visible).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('is one layer for two clicks while the TileJSON is on its way', async () => {
    let answer: (response: Response) => void = () => {};
    const gate = new Promise<Response>((resolve) => (answer = resolve));
    tileJson = () => gate.then((response) => response.clone());
    act(() => root.render(<JobList />));
    for (let i = 0; i < 2; i++) {
      click(button('Add to layers'));
    }
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await act(async () => {
      answer(json(TILE_JSON));
    });
    await flush();
    expect(layers()).toHaveLength(1);
  });

  it('is not processed further and not downloaded as scenes', async () => {
    await showOnMap();
    expect(layerProcessBlock(layers()[0], [])).toBe('A result cannot be processed further yet.');
    act(() => root.render(<LayerManager />));
    expect(container.querySelector('.lm-btn[title="Process this layer"]')).toBeNull();
    expect(button('⚙')?.disabled).toBe(true);
    expect(button('⇩')).toBeUndefined();
  });

  it('says in its row which unit the values of the result are in', async () => {
    useProcessingStore.setState({ jobs: [entry({ unit: 'm' })] });
    await showOnMap();
    expect(layers()[0].result?.unit).toBe('m');
    act(() => root.render(<LayerManager />));
    expect(container.querySelector('.lm-note')?.textContent).toBe('Values in m');
    expect(container.querySelector('.layer-row-noted')).not.toBeNull();
  });

  it('says nothing of a unit where the result states none', async () => {
    await showOnMap();
    expect(layers()[0].result?.unit).toBeNull();
    act(() => root.render(<LayerManager />));
    expect(container.textContent).not.toContain('Values in');
    expect(container.querySelector('.layer-row-noted')).toBeNull();
  });

  it('says in its row that the result was resampled to a common grid', async () => {
    useProcessingStore.setState({ jobs: [entry({ resampled: true })] });
    await showOnMap();
    act(() => root.render(<LayerManager />));
    expect(container.textContent).toContain(RESAMPLED_LAYER_TEXT);
  });
});

describe('when the result cannot be shown', () => {
  it('says "Expired" when the tiler answers 410, and makes no layer', async () => {
    tileJson = () => json({ detail: 'the result has expired' }, 410);
    await showOnMap();
    expect(layers()).toEqual([]);
    expect(useProcessingStore.getState().jobs[0].expired).toBe(true);
    act(() => root.render(<JobList />));
    expect(container.textContent).toContain(EXPIRED_TEXT);
    expect(button('Add to layers')).toBeUndefined();
  });

  it.each([
    ['404', () => json({ detail: 'there is no such result' }, 404)],
    ['503', () => json({ detail: 'the result store is not available; try again' }, 503)],
    ['a body that is no TileJSON', () => json({ bounds: 'everywhere' })],
    ['a reply that is no JSON', () => new Response('<html>', { status: 200 })],
  ])('writes the reason in the row on %s, and makes no layer', async (_, reply) => {
    tileJson = reply;
    await showOnMap();
    expect(layers()).toEqual([]);
    expect(useProcessingStore.getState().jobs[0].expired).toBe(false);
    expect(container.querySelector('.hint-text.error')?.textContent).toContain('could not be shown on the map');
  });

  it('asks again after an error, and the error goes', async () => {
    tileJson = () => json({ detail: 'down' }, 503);
    await showOnMap();
    expect(container.querySelector('.hint-text.error')).not.toBeNull();
    tileJson = () => json(TILE_JSON);
    click(button('Add to layers'));
    await flush();
    expect(layers()).toHaveLength(1);
    expect(container.querySelector('.hint-text.error')).toBeNull();
  });

  it('asks nothing of a job that is past its minute', async () => {
    useProcessingStore.setState({ jobs: [entry({ expires: new Date(Date.now() + MIN_REMAINING_MS - 1000).toISOString() })] });
    await useProcessingStore.getState().showResultOnMap(JOB);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(layers()).toEqual([]);
    expect(useProcessingStore.getState().jobs[0].expired).toBe(true);
  });

  it.each([
    ['an unknown job', 'unknown-job-id-00000000'],
    ['a job without tiles', JOB],
  ])('does nothing for %s', async (_, jobID) => {
    useProcessingStore.setState({ jobs: [entry({ tiles: null })] });
    await useProcessingStore.getState().showResultOnMap(jobID);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(layers()).toEqual([]);
  });
});

describe('a result layer that expires', () => {
  function pinResult(expiresInMs: number): MapLayer {
    useAppStore.getState().pinDerivedLayer({
      name: 'Result · Band math',
      derived: 'result',
      result: { jobID: JOB, expires: new Date(Date.now() + expiresInMs).toISOString(), gsd: 10, resampled: null, expired: false },
      overlays: [{ kind: 'raster', tileUrl: 'https://t/{z}', bounds: [10, 50, 11, 51], minZoom: 8, maxZoom: 14 }],
      itemIds: [],
      cropToAoi: false,
    });
    return layers()[0];
  }

  it('is marked a minute before its results go, by one timer', () => {
    vi.useFakeTimers();
    pinResult(MIN_REMAINING_MS + 10_000);
    act(() => root.render(<LayerManager />));
    expect(container.textContent).not.toContain(EXPIRED_LAYER_TEXT);
    act(() => {
      vi.advanceTimersByTime(9_900);
    });
    expect(layers()[0].result?.expired).toBe(false);
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(layers()[0].result?.expired).toBe(true);
    expect(container.textContent).toContain(EXPIRED_LAYER_TEXT);
  });

  it('is marked at once when it was already inside the last minute', () => {
    pinResult(MIN_REMAINING_MS - 1000);
    act(() => root.render(<LayerManager />));
    expect(layers()[0].result?.expired).toBe(true);
  });

  it('marks only the layers that are due', () => {
    vi.useFakeTimers();
    pinResult(MIN_REMAINING_MS + 5_000);
    useAppStore.getState().pinDerivedLayer({
      name: 'Result · other',
      derived: 'result',
      result: { jobID: 'Other-job-id-0000000000', expires: new Date(Date.now() + 86_400_000).toISOString(), gsd: 10, resampled: null, expired: false },
      overlays: [],
      itemIds: [],
      cropToAoi: false,
    });
    act(() => root.render(<LayerManager />));
    act(() => {
      vi.advanceTimersByTime(5_100);
    });
    expect(layers().map((l) => l.result?.expired)).toEqual([false, true]);
  });

  it('stops its timer when the layer is taken off the list', () => {
    vi.useFakeTimers();
    pinResult(MIN_REMAINING_MS + 5_000);
    act(() => root.render(<LayerManager />));
    act(() => useAppStore.getState().removeLayer(layers()[0].id));
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe('"Overview" over the map', () => {
  function result(over: Partial<NonNullable<MapLayer['result']>> = {}, layer: Partial<MapLayer> = {}) {
    useAppStore.setState({
      layers: [
        {
          id: 'R1',
          name: 'Result · Band math',
          visible: true,
          opacity: 1,
          overlays: [{ kind: 'raster', tileUrl: 'https://t/{z}', bounds: [10, 50, 11, 51], minZoom: 8, maxZoom: 14 }],
          derived: 'result',
          result: { jobID: JOB, expires: new Date(Date.now() + 86_400_000).toISOString(), gsd: 10, resampled: null, expired: false, ...over },
          restore: {
            focusMode: false,
            downloaded: {},
            appliedRender: {},
            activeGroupIndex: 0,
            selectedIds: [],
            itemIds: [],
            groupItemIds: [],
            aoi: null,
            cropToAoi: false,
            datasetId: null,
          },
          ...layer,
        },
      ],
    });
  }
  const badge = () => container.querySelector('.preview-badge-dock')?.textContent ?? '';

  it('is on the map while the tile is coarser than the result, and goes when it is not', () => {
    result();
    act(() => root.render(<PreviewBadge />));
    expect(badge()).toBe('Overview');
    expect(container.querySelector('.preview-badge')?.getAttribute('title')).toBe(OVERVIEW_TITLE);
    act(() => useAppStore.setState({ mapZoom: 15 }));
    expect(container.querySelector('.preview-badge-dock')).toBeNull();
    act(() => useAppStore.setState({ mapZoom: 3 }));
    expect(badge()).toBe('Overview');
  });

  it.each([
    ['switched off', {}, { visible: false }],
    ['expired', { expired: true }, {}],
    ['of an unknown pixel size', { gsd: null }, {}],
  ])('is not on the map for a layer that is %s', (_, over, layer) => {
    result(over, layer);
    act(() => root.render(<PreviewBadge />));
    expect(container.querySelector('.preview-badge-dock')).toBeNull();
  });

  it('stands beside "Preview" when both are on the map', () => {
    result();
    useProcessingStore.setState({ preview: { key: 'k', title: 'Band math', stepCount: 1, probe: '', scenes: [], minZoom: 8, maxZoom: 14, clipToAoi: false } });
    act(() => root.render(<PreviewBadge />));
    expect(badge()).toBe('PreviewOverview');
  });

  it('is not the "Preview" of a preview layer', () => {
    result({}, { derived: 'preview', result: undefined });
    act(() => root.render(<PreviewBadge />));
    expect(container.querySelector('.preview-badge-dock')).toBeNull();
  });
});
