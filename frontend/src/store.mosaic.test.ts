// M4-17c, M5-30b part 3: a time step in the full-resolution view is one mosaic, drawn from a selection of the tiler. What the store
// does about it: it creates the selection once when the view opens, asks its TileJSON, keeps the answer under a key of its
// own (dataset, asset, scenes) and pins the picture only once it is there; where the selection expired, it creates it again.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { json, selectionIdOf, selectionServer, TILEJSON, type SelectionServerOptions } from './fixtures/selectionTiler';
import { mosaicKeyOf, orderKeyOf } from './mosaic';
import { resetSelections } from './mosaicSelection';
import { datasetsFrom } from './datasets';
import { useAppStore } from './store';
import type { Collection, DownloadedInfo, StacItem } from './types';

const ID = 'sentinel-2-c1-l2a';

const COLLECTION: Collection = {
  id: ID,
  title: 'Sentinel-2 L2A',
  'earthx:capabilities': {
    roi: true,
    time_range: true,
    band_math: true,
    interpolation: true,
    ml_processing: true,
    quad_pol: false,
    single_coverage_product: false,
  },
  'earthx:viewer': {
    group_by: ['datetime'],
    min_zoom: 0,
    max_zoom: 19,
    browse: 'preview_tiles',
    quicklook_nodata_max: null,
    results_group_by: ['datetime'],
    overview: 'own' as const,
    overview_resampling: null,
    overview_substitute: null,
  },
  'earthx:default_render': {
    title: 'True colour',
    assets: ['visual'],
    rescale: [[0, 3000]],
    colormap_name: null,
    expression: null,
    resampling: 'nearest',
  },
};

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 47]]] };

const ids = (n: number) => Array.from({ length: n }, (_, i) => `S${String(i).padStart(4, '0')}`);
const scene = (id: string): StacItem => ({
  id,
  bbox: [10, 47, 11, 48],
  properties: { datetime: '2026-07-24T10:00:00Z' },
  assets: {},
});

// A tiler that answers the statistics of the stretch, the order of a pass drawn scene by scene and the selections of the mosaics.
function tiler(mosaic?: SelectionServerOptions['tilejson'], options: Omit<SelectionServerOptions, 'tilejson'> = {}) {
  const selections = selectionServer({ ...options, tilejson: mosaic });
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const selected = await selections.answer(url, init);
    if (selected) return selected;
    // The order of a pass drawn scene by scene (NM4-24), as the tiler gives it where the scenes lie in one CRS: by id.
    if (url.includes('/scene-order')) return json({ order: (JSON.parse(String(init?.body)) as { items: string[] }).items.sort() });
    if (url.includes('/statistics')) return json({ '1': { min: 0, max: 4000, percentile_2: 0, percentile_98: 3000 } });
    throw new Error(`unexpected request: ${url}`);
  });
  vi.stubGlobal('fetch', fetchMock);
  return Object.assign(fetchMock, { selections });
}
// The mosaics of the store, without the orders of the scenes that lie beside them (NM4-24).
const mosaicsOnly = (mosaics: Record<string, unknown>) => Object.entries(mosaics).filter(([key]) => !key.startsWith('order|')).map(([, v]) => v);
const tilejsonCalls = () => vi.mocked(fetch).mock.calls.map(([url]) => url as string).filter((url) => url.endsWith('/tilejson.json'));
// The selections created, by the scenes in them.
const creations = () =>
  vi.mocked(fetch).mock.calls
    .filter(([url, init]) => /\/mosaic$/.test(url as string) && (init as RequestInit | undefined)?.method === 'POST')
    .map(([, init]) => JSON.parse(String((init as RequestInit).body)) as { items: string[]; assets: string[] });
// What a gate lets through, once the tiler has been asked: the TileJSON that is held until the test says so.
const asked = () => vi.waitFor(() => expect(tilejsonCalls().length).toBeGreaterThan(0));
const idOf = (items: string[], assets = ['visual']) => selectionIdOf(ID, assets, items);

function openGroup(groupIds: string[]) {
  const items = groupIds.map(scene);
  useAppStore.setState({
    datasets: datasetsFrom([COLLECTION]),
    selectedDatasetIds: [ID],
    datasetId: ID,
    items,
    groups: [{ key: ['2026-07-24'], label: '2026-07-24', items }],
    activeGroupIndex: 0,
    expandedGroupIndex: 0,
    selectedIds: [],
    focusMode: false,
    cropToAoi: false,
    downloaded: {},
    appliedRender: {},
    mosaics: {},
    pinLoading: false,
    layers: [],
    viewLayerId: null,
    resultsOnMap: true,
    aoi: AOI,
    error: null,
    notice: null,
  });
}

beforeEach(() => {
  resetSelections();
  openGroup(['A', 'B', 'C']);
});
afterEach(() => vi.unstubAllGlobals());

describe('enterFocus with a time step of several scenes', () => {
  it('creates the selection once, with every scene and the asset in the body, and asks its TileJSON', async () => {
    tiler();
    await useAppStore.getState().enterFocus(false);
    expect(creations()).toEqual([{ items: ['A', 'B', 'C'], assets: ['visual'] }]);
    expect(tilejsonCalls()).toEqual([`/collections/sentinel-2-c1-l2a/mosaic/${idOf(['A', 'B', 'C'])}/WebMercatorQuad/tilejson.json`]);
  });

  it('puts no scene and no asset in any URL it asks for', async () => {
    tiler();
    await useAppStore.getState().enterFocus(false);
    for (const [url] of vi.mocked(fetch).mock.calls.filter(([u]) => String(u).includes('/mosaic'))) expect(String(url)).not.toMatch(/[?&](item|asset)=/);
  });

  it('keeps what the TileJSON says under the key of the mosaic, with the URL of the selection to draw', async () => {
    tiler(() => json(TILEJSON(['C', 'A', 'B'])));
    await useAppStore.getState().enterFocus(false);
    const key = mosaicKeyOf(ID, Object.entries(useAppStore.getState().downloaded)) as string;
    expect(useAppStore.getState().mosaics[key]).toEqual({
      tileUrl: `/collections/${ID}/mosaic/${idOf(['A', 'B', 'C'])}/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=512`,
      bounds: [9, 46, 12, 49],
      minZoom: 8,
      maxZoom: 19,
      order: ['C', 'A', 'B'],
    });
  });

  it('asks the TileJSON together with the stretch, not one after the other', async () => {
    let answerMosaic: (r: Response) => void = () => {};
    tiler(() => new Promise<Response>((resolve) => (answerMosaic = resolve)));
    const entering = useAppStore.getState().enterFocus(false);
    await vi.waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('/statistics'))).toBe(true));
    await asked();
    answerMosaic(json(TILEJSON(['A', 'B', 'C'])));
    await entering;
    expect(useAppStore.getState().pendingVmax).toBe('3000');
  });

  it('says it is loading until the mosaic has answered, though the stretch is there long before', async () => {
    let answerMosaic: (r: Response) => void = () => {};
    tiler(() => new Promise<Response>((resolve) => (answerMosaic = resolve)));
    const entering = useAppStore.getState().enterFocus(false);
    await vi.waitFor(() => expect(useAppStore.getState().pendingVmax).toBe('3000'));
    await vi.waitFor(() => expect(useAppStore.getState().focusLoading).toBe(true));
    await asked();
    answerMosaic(json(TILEJSON(['A', 'B', 'C'])));
    await entering;
    expect(useAppStore.getState().focusLoading).toBe(false);
  });

  it('does not create a selection for one scene', async () => {
    openGroup(['A']);
    tiler();
    await useAppStore.getState().enterFocus(false);
    expect(creations()).toEqual([]);
    expect(useAppStore.getState().mosaics).toEqual({});
  });

  it('creates the selection of each time step by itself', async () => {
    const items = ['A1', 'A2', 'B1', 'B2'].map(scene);
    useAppStore.setState({
      items,
      groups: [
        { key: ['a'], label: 'a', items: items.slice(0, 2) },
        { key: ['b'], label: 'b', items: items.slice(2) },
      ],
      selectedIds: items.map((it) => it.id), // picked across both time steps
    });
    tiler();
    await useAppStore.getState().enterFocus(false);
    expect(creations().map((c) => c.items).sort()).toEqual([['A1', 'A2'], ['B1', 'B2']]);
  });

  it('draws a time step the tiler refused scene by scene, and says why', async () => {
    tiler(() => json({ detail: 'the items are of different passes' }, 422));
    await useAppStore.getState().enterFocus(false);
    const s = useAppStore.getState();
    expect(mosaicsOnly(s.mosaics)).toEqual([null]);
    expect(s.notice).toBe('Could not load the mosaic (the items are of different passes); its scenes are drawn one by one.');
    expect(s.focusMode).toBe(true);
    expect(Object.keys(s.downloaded)).toEqual(['A', 'B', 'C']);
  });

  it('does the same when the tiler refuses to create the selection (a scale or a unit that differs between the scenes)', async () => {
    tiler(undefined, { create: () => json({ detail: 'the scenes differ in their unit' }, 422) });
    await useAppStore.getState().enterFocus(false);
    expect(mosaicsOnly(useAppStore.getState().mosaics)).toEqual([null]);
    expect(useAppStore.getState().notice).toBe('Could not load the mosaic (the scenes differ in their unit); its scenes are drawn one by one.');
    expect(tilejsonCalls()).toEqual([]);
  });

  it('does the same when the tiler cannot be reached at all', async () => {
    vi.stubGlobal('fetch', async (url: string) => {
      if (url.includes('/statistics')) return json({ '1': { percentile_2: 0, percentile_98: 1 } });
      throw new TypeError('Failed to fetch');
    });
    await useAppStore.getState().enterFocus(false);
    expect(mosaicsOnly(useAppStore.getState().mosaics)).toEqual([null]);
    expect(useAppStore.getState().notice).toMatch(/Failed to fetch/);
  });

  it('does the same for a TileJSON it cannot read', async () => {
    tiler(() => json({ bounds: [1, 2], minzoom: 8 }));
    await useAppStore.getState().enterFocus(false);
    expect(mosaicsOnly(useAppStore.getState().mosaics)).toEqual([null]);
    expect(useAppStore.getState().notice).toMatch(/cannot read/);
  });

  it('asks a second time after a refusal, not before, and does not create the selection a second time', async () => {
    const fetchMock = tiler(() => json({ detail: 'down' }, 503));
    await useAppStore.getState().enterFocus(false);
    expect(tilejsonCalls()).toHaveLength(1);
    fetchMock.selections.created.length = 0;
    vi.mocked(fetch).mockClear();
    const server = selectionServer();
    server.selections.set(idOf(['A', 'B', 'C']), { id: idOf(['A', 'B', 'C']), dataset: ID, items: ['A', 'B', 'C'], assets: ['visual'] });
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => (await server.answer(url, init)) ?? json({ '1': { percentile_2: 0, percentile_98: 1 } }));
    await useAppStore.getState().loadMosaics();
    expect(Object.values(useAppStore.getState().mosaics)[0]).not.toBeNull();
    await useAppStore.getState().loadMosaics();
    expect(tilejsonCalls()).toHaveLength(1); // an answer that is there is not asked for again
    expect(creations()).toEqual([]); // the selection of the first try is still the one
  });

  it('creates one selection for two views that want the same mosaic at the same time', async () => {
    tiler();
    useAppStore.setState({
      focusMode: true,
      downloaded: Object.fromEntries(['A', 'B', 'C'].map((id) => [id, { asset: 'visual', minZoom: 0, maxZoom: 19 } as DownloadedInfo])),
    });
    await Promise.all([useAppStore.getState().loadMosaics(), useAppStore.getState().loadMosaics()]);
    expect(creations()).toHaveLength(1);
    expect(tilejsonCalls()).toHaveLength(1);
  });

  it('does not create a selection outside the full-resolution view', async () => {
    tiler();
    await useAppStore.getState().loadMosaics();
    expect(creations()).toEqual([]);
  });

  it('draws a time step of 300 scenes as one mosaic and says nothing: the URL no longer limits it', async () => {
    openGroup(ids(300));
    tiler();
    await useAppStore.getState().enterFocus(false);
    expect(creations()).toHaveLength(1);
    expect(creations()[0].items).toHaveLength(300);
    expect(useAppStore.getState().notice).toBeNull();
    for (const [url] of vi.mocked(fetch).mock.calls) expect(String(url).length).toBeLessThan(200);
  });

  it('keeps a time step above what a selection takes (2000) out of the tiler and draws it scene by scene, with no note', async () => {
    openGroup(ids(2001));
    tiler();
    await useAppStore.getState().enterFocus(false);
    expect(creations()).toEqual([]);
    expect(useAppStore.getState().notice).toBeNull();
  });

  it('keeps a pass of scenes of different assets out of the tiler too: it can be no mosaic', async () => {
    tiler();
    useAppStore.setState({
      focusMode: true,
      downloaded: { A: { asset: 'visual', minZoom: 0, maxZoom: 19 } as DownloadedInfo, B: { asset: 'thumbnail', minZoom: 0, maxZoom: 19 } as DownloadedInfo },
    });
    await useAppStore.getState().loadMosaics();
    expect(creations()).toEqual([]);
  });
});

describe('a selection that expired (adr/0032 §10.2)', () => {
  it('is created again when its TileJSON answers 410, and the TileJSON asked again', async () => {
    let answers = 0;
    const server = tiler(
      (selection) => (++answers === 1 ? json({ detail: 'no selection: it expired' }, 410) : json(TILEJSON(selection.items))),
    );
    await useAppStore.getState().enterFocus(false);
    expect(creations()).toHaveLength(2);
    expect(creations()[1]).toEqual(creations()[0]); // the same list, which makes the same id
    expect(server.selections.created.map((c) => c.id)).toEqual([idOf(['A', 'B', 'C']), idOf(['A', 'B', 'C'])]);
    expect(tilejsonCalls()).toHaveLength(2);
    const [mosaic] = mosaicsOnly(useAppStore.getState().mosaics);
    expect(mosaic).toMatchObject({ order: ['A', 'B', 'C'] });
    expect(useAppStore.getState().notice).toBeNull();
  });

  it('is created again once only: a tiler that keeps saying 410 ends in the scenes one by one', async () => {
    tiler(() => json({ detail: 'no selection: it expired' }, 410));
    await useAppStore.getState().enterFocus(false);
    expect(creations()).toHaveLength(2);
    expect(tilejsonCalls()).toHaveLength(2);
    expect(mosaicsOnly(useAppStore.getState().mosaics)).toEqual([null]);
    expect(useAppStore.getState().notice).toMatch(/^Could not load the mosaic \(no selection/);
  });

  it('is not created again for another failure of the TileJSON', async () => {
    tiler(() => json({ detail: 'down' }, 503));
    await useAppStore.getState().enterFocus(false);
    expect(creations()).toHaveLength(1);
  });
});

describe('adding a mosaic to the layers', () => {
  async function enter(cropToAoi: boolean) {
    tiler(() => json(TILEJSON(['C', 'A', 'B'])));
    await useAppStore.getState().enterFocus(cropToAoi);
  }

  it('pins the mosaic of its selection as one layer per time step, cut to the AOI, with no scene under it', async () => {
    await enter(true);
    useAppStore.getState().addCurrentToLayers();
    const { layers, error } = useAppStore.getState();
    expect(error).toBeNull();
    expect(layers).toHaveLength(1);
    const overlays = layers[0].overlays;
    expect(overlays).toHaveLength(1);
    expect(overlays.every((o) => o.kind === 'raster' && o.tileUrl.startsWith('earthx-clip://'))).toBe(true);
    const [mosaic] = overlays;
    expect(mosaic.kind === 'raster' && mosaic.tileUrl).toContain(`/mosaic/${idOf(['A', 'B', 'C'])}/tiles/`);
    expect(mosaic.kind === 'raster' && mosaic.tileUrl).not.toContain('item=');
    expect(layers[0].restore.itemIds).toEqual(['A', 'B', 'C']);
  });

  it('pins the images of an uncropped view as one layer each with "Add all to layers", one mosaic per time step', async () => {
    const items = ['A1', 'A2', 'B1', 'B2'].map(scene);
    useAppStore.setState({
      items,
      groups: [
        { key: ['a'], label: 'a', items: items.slice(0, 2) },
        { key: ['b'], label: 'b', items: items.slice(2) },
      ],
      selectedIds: items.map((it) => it.id),
    });
    await enter(false);
    useAppStore.getState().addAllToLayers();
    const { layers } = useAppStore.getState();
    expect(layers).toHaveLength(2);
    const urls = layers.flatMap((l) => l.overlays.map((o) => (o.kind === 'raster' ? o.tileUrl : '')));
    expect(urls.filter((u) => u.includes('/mosaic/'))).toHaveLength(2);
    expect(layers.every((l) => l.overlays.some((o) => o.kind === 'raster' && o.tileUrl.includes('/mosaic/')))).toBe(true);
    expect(urls.some((u) => u.startsWith('earthx-clip://'))).toBe(false);
  });

  it('pins the scenes one by one where the tiler refused the mosaic', async () => {
    tiler(() => json({ detail: 'no' }, 422));
    await useAppStore.getState().enterFocus(true);
    useAppStore.getState().addCurrentToLayers();
    const overlays = useAppStore.getState().layers[0].overlays;
    expect(overlays).toHaveLength(3);
    expect(overlays.every((o) => o.kind === 'raster' && o.hideFrom === undefined)).toBe(true);
  });

  it.each([true, false])('waits for a mosaic that is on its way and pins by itself when it is here (cropped: %s)', async (cropToAoi) => {
    let answerMosaic: (r: Response) => void = () => {};
    tiler(() => new Promise<Response>((resolve) => (answerMosaic = resolve)));
    const entering = useAppStore.getState().enterFocus(cropToAoi);
    await vi.waitFor(() => expect(useAppStore.getState().focusMode).toBe(true));

    useAppStore.getState().addCurrentToLayers();
    let s = useAppStore.getState();
    expect(s.pinLoading).toBe(true); // the button says "Loading…"
    expect(s.error).toBeNull();
    expect(s.layers).toEqual([]);
    useAppStore.getState().addCurrentToLayers(); // a second click while waiting adds nothing
    expect(creations()).toHaveLength(1);

    await asked();
    answerMosaic(json(TILEJSON(['A', 'B', 'C'])));
    await entering;
    await vi.waitFor(() => expect(useAppStore.getState().layers).toHaveLength(1));
    s = useAppStore.getState();
    expect(s.pinLoading).toBe(false);
    expect(s.error).toBeNull();
    expect(s.notice).toMatch(/^Added /);
    expect(s.layers[0].overlays.filter((o) => o.kind === 'raster' && o.tileUrl.includes('/mosaic/'))).toHaveLength(1);
  });
});

describe('the order of the scenes of a pass drawn one by one (NM4-24)', () => {
  // The tiler of `tiler()`, with the route of the order added: it answers with the ids backwards, which no sort of the page gives.
  function withOrderRoute(answer: (ids: string[]) => Response | Promise<Response>, mosaic?: SelectionServerOptions['tilejson']) {
    const base = tiler(mosaic);
    const calls: { url: string; ids: string[]; asset: string }[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.includes('/scene-order')) {
          expect(init?.method).toBe('POST');
          const body = JSON.parse(String(init?.body)) as { items: string[]; asset: string };
          calls.push({ url, ids: body.items, asset: body.asset });
          return answer(body.items);
        }
        return base(url, init);
      }),
    );
    return calls;
  }
  const backwards = (ids: string[]) => json({ order: [...ids].reverse() });
  const entriesOfView = () => Object.entries(useAppStore.getState().downloaded);
  const keyOfView = () => orderKeyOf(ID, entriesOfView()) as string;

  it('is asked for a pass too big for a selection, with the ids in the body, and kept', async () => {
    openGroup(ids(2001));
    const calls = withOrderRoute(backwards);
    await useAppStore.getState().enterFocus(false);
    expect(creations()).toEqual([]);
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toContain('/collections/sentinel-2-c1-l2a/scene-order');
    expect(calls[0].ids).toHaveLength(2001);
    expect(calls[0].asset).toBe('visual');
    expect(useAppStore.getState().mosaics[keyOfView()]).toEqual({ order: [...ids(2001)].reverse() });
  });

  it('is asked for a pass whose mosaic the tiler refused, and not asked again by the next view', async () => {
    const calls = withOrderRoute(backwards, () => json({ detail: 'the items are of different passes' }, 422));
    await useAppStore.getState().enterFocus(false);
    expect(calls).toHaveLength(1);
    expect(useAppStore.getState().mosaics[keyOfView()]).toEqual({ order: ['C', 'B', 'A'] });
    await useAppStore.getState().loadMosaics();
    expect(calls).toHaveLength(1);
  });

  it('is not asked for a pass that has its mosaic: the TileJSON names the order', async () => {
    const calls = withOrderRoute(backwards);
    await useAppStore.getState().enterFocus(false);
    expect(calls).toEqual([]);
    expect(useAppStore.getState().mosaics[keyOfView()]).toBeUndefined();
  });

  it('is not asked for a single scene', async () => {
    openGroup(['A']);
    const calls = withOrderRoute(backwards);
    await useAppStore.getState().enterFocus(false);
    expect(calls).toEqual([]);
  });

  it('is left to the selection, with a notice, when the tiler cannot give it', async () => {
    const calls = withOrderRoute(() => json({ detail: 'the catalogue database is not reachable' }, 503), () => json({ detail: 'no' }, 422));
    await useAppStore.getState().enterFocus(false);
    expect(calls).toHaveLength(1);
    const s = useAppStore.getState();
    expect(s.mosaics[keyOfView()]).toBeNull();
    expect(s.notice).toMatch(/^Could not load the mosaic/);
    // Not asked again; the answer that said no stays.
    await useAppStore.getState().loadMosaics();
    expect(calls).toHaveLength(1);
  });

  it('says that the order could not be read when the mosaic was not what failed', async () => {
    openGroup(ids(2001));
    withOrderRoute(() => json({ detail: 'the catalogue database is not reachable' }, 503));
    await useAppStore.getState().enterFocus(false);
    expect(useAppStore.getState().notice).toMatch(/^Could not read the stacking order of the scenes \(.*\); they lie in the order of the selection\.$/);
  });

  it('is refused when the answer is not a list of ids', async () => {
    openGroup(ids(2001));
    withOrderRoute(() => json({ order: [1, 2] }));
    await useAppStore.getState().enterFocus(false);
    expect(useAppStore.getState().mosaics[keyOfView()]).toBeNull();
  });
});

describe('adding to the layers while the mosaic is on its way (NM4-12)', () => {
  it('drops the pin without a word when the view is closed meanwhile', async () => {
    let answerMosaic: (r: Response) => void = () => {};
    tiler(() => new Promise<Response>((resolve) => (answerMosaic = resolve)));
    const entering = useAppStore.getState().enterFocus(true);
    await vi.waitFor(() => expect(useAppStore.getState().focusMode).toBe(true));
    useAppStore.getState().addCurrentToLayers();
    expect(useAppStore.getState().pinLoading).toBe(true);

    useAppStore.getState().exitFocus();
    await asked();
    answerMosaic(json(TILEJSON(['A', 'B', 'C'])));
    await entering;
    await vi.waitFor(() => expect(useAppStore.getState().pinLoading).toBe(false));
    const s = useAppStore.getState();
    expect(s.layers).toEqual([]);
    expect([s.error, s.notice]).toEqual([null, null]);
  });

  it('clears an earlier message when the pin goes through, and a second click makes no second layer', async () => {
    let answerMosaic: (r: Response) => void = () => {};
    tiler(() => new Promise<Response>((resolve) => (answerMosaic = resolve)));
    const entering = useAppStore.getState().enterFocus(true);
    await vi.waitFor(() => expect(useAppStore.getState().focusMode).toBe(true));
    useAppStore.setState({ error: 'Nothing to add — search and pick a time step first.' });

    useAppStore.getState().addCurrentToLayers();
    expect(useAppStore.getState().error).toBeNull();
    useAppStore.getState().addCurrentToLayers();
    useAppStore.getState().addAllToLayers();
    await asked();
    answerMosaic(json(TILEJSON(['A', 'B', 'C'])));
    await entering;
    await vi.waitFor(() => expect(useAppStore.getState().layers).toHaveLength(1));
    await vi.waitFor(() => expect(useAppStore.getState().pinLoading).toBe(false));
    expect(useAppStore.getState().layers).toHaveLength(1);
    expect(useAppStore.getState().error).toBeNull();
  });
});

describe('adding a part of the view to the layers', () => {
  const pickTwo = async (cropToAoi: boolean, mosaic: NonNullable<SelectionServerOptions['tilejson']>) => {
    tiler(mosaic);
    await useAppStore.getState().enterFocus(cropToAoi);
    useAppStore.setState({ selectedIds: ['A', 'B'] }); // a part of the three the view shows
  };

  it.each([true, false])('asks for the mosaic of the picked scenes and pins it when it is here (cropped: %s)', async (cropToAoi) => {
    await pickTwo(cropToAoi, () => json(TILEJSON(['A', 'B'])));
    useAppStore.getState().addCurrentToLayers();
    expect(useAppStore.getState().pinLoading).toBe(true);
    expect(useAppStore.getState().layers).toEqual([]);

    await vi.waitFor(() => expect(useAppStore.getState().layers).toHaveLength(1));
    const { layers, error, pinLoading } = useAppStore.getState();
    expect([error, pinLoading]).toEqual([null, false]);
    expect(creations().map((c) => c.items)).toContainEqual(['A', 'B']);
    expect(layers[0].restore.itemIds).toEqual(['A', 'B']);
    const urls = layers[0].overlays.map((o) => (o.kind === 'raster' ? o.tileUrl : ''));
    expect(urls.find((u) => u.includes('/mosaic/'))).toContain(`/mosaic/${idOf(['A', 'B'])}/tiles/`);
  });

  it.each([true, false])('says why and pins nothing when the tiler cannot give it (cropped: %s)', async (cropToAoi) => {
    await pickTwo(cropToAoi, (selection) =>
      selection.items.length === 2 ? json({ detail: 'the items are of different passes' }, 422) : json(TILEJSON(['A', 'B', 'C'])),
    );
    useAppStore.getState().addCurrentToLayers();
    await vi.waitFor(() => expect(useAppStore.getState().pinLoading).toBe(false));
    const s = useAppStore.getState();
    expect(s.layers).toEqual([]);
    expect(s.notice).toBe('Could not load the mosaic (the items are of different passes); its scenes are drawn one by one.');
  });

  it('does not pin another selection than the one it was asked for', async () => {
    let answerMosaic: (r: Response) => void = () => {};
    await pickTwo(false, (selection) =>
      selection.items.length === 2 ? new Promise<Response>((resolve) => (answerMosaic = resolve)) : json(TILEJSON(['A', 'B', 'C'])),
    );
    useAppStore.getState().addCurrentToLayers();
    useAppStore.setState({ selectedIds: ['C'] }); // changed its mind meanwhile
    await vi.waitFor(() => expect(tilejsonCalls().length).toBeGreaterThan(1));
    answerMosaic(json(TILEJSON(['A', 'B'])));
    await vi.waitFor(() => expect(useAppStore.getState().pinLoading).toBe(false));
    expect(useAppStore.getState().layers).toEqual([]);
  });

  it('pins scenes that no time step of the search holds one by one, never as a mosaic', async () => {
    tiler();
    useAppStore.setState({ focusMode: true, cropToAoi: true, groups: [], selectedIds: [] });
    useAppStore.setState({
      downloaded: Object.fromEntries(
        ['X', 'Y'].map((id) => [id, { datasetId: 'sentinel-2-c1-l2a', tileUrl: `/t/${id}`, bounds: [0, 0, 1, 1], asset: 'visual', minZoom: 0, maxZoom: 19 }]),
      ),
    });
    useAppStore.getState().addCurrentToLayers();
    expect(creations()).toEqual([]);
    const { layers, error } = useAppStore.getState();
    expect(error).toBeNull();
    expect(layers.flatMap((l) => l.overlays)).toHaveLength(2);
  });
});

describe('opening a pinned layer again', () => {
  it('loads the mosaics of the layer\'s time steps, so the view can draw them when it differs from the layer', async () => {
    tiler();
    const layer = {
      id: 'L',
      name: 'n',
      visible: true,
      opacity: 1,
      overlays: [],
      restore: {
        focusMode: true,
        downloaded: Object.fromEntries(
          ['A', 'B'].map((id) => [id, { tileUrl: `/t/${id}`, bounds: [0, 0, 1, 1], asset: 'visual', minZoom: 0, maxZoom: 19 }]),
        ),
        appliedRender: {},
        activeGroupIndex: 0,
        selectedIds: ['A', 'B'],
        itemIds: ['A', 'B'],
        groupItemIds: [['A', 'B']],
        aoi: AOI,
        cropToAoi: false,
        datasetId: ID,
      },
    };
    useAppStore.setState({ layers: [layer as never] });
    useAppStore.getState().selectLayer('L');
    expect(useAppStore.getState().focusLoading).toBe(true); // until the mosaic has answered
    await vi.waitFor(() => expect(creations()).toHaveLength(1));
    expect(creations()[0].items).toEqual(['A', 'B']);
    await vi.waitFor(() => expect(useAppStore.getState().focusLoading).toBe(false));
  });
});

describe('the results on the map around a full-resolution view (Otto, 26.10.2026; the switch alone, 27.10.2026)', () => {
  // Show or hide is the results switch's alone, with two exceptions: a new search shows the results, and a crop of the
  // scenes ("Crop to AOI") hides them. A view of the whole scene, leaving a view and clearing it leave the switch.
  it.each([true, false])('a view of the whole scene, loaded and left, leaves the switch and the tick as they were (results on map: %s)', async (before) => {
    tiler();
    useAppStore.setState({ resultsOnMap: before, selectedIds: ['A'] });
    await useAppStore.getState().enterFocus(false);
    expect(useAppStore.getState().focusMode).toBe(true);
    expect(useAppStore.getState().resultsOnMap).toBe(before);
    expect(useAppStore.getState().selectedIds).toEqual(['A']);
    useAppStore.getState().exitFocus();
    expect(useAppStore.getState().focusMode).toBe(false);
    expect(useAppStore.getState().resultsOnMap).toBe(before);
    expect(useAppStore.getState().selectedIds).toEqual(['A']);
  });

  it.each([true, false])('a crop hides the results and drops the tick of its scenes, whatever the switch was (results on map: %s)', async (before) => {
    tiler();
    useAppStore.setState({ resultsOnMap: before, selectedIds: ['A', 'B'] });
    await useAppStore.getState().enterFocus(true);
    expect(useAppStore.getState().focusMode).toBe(true);
    expect(useAppStore.getState().resultsOnMap).toBe(false);
    expect(useAppStore.getState().selectedIds).toEqual([]);
    // The view is made of the scenes that were ticked, and stays open without the tick.
    expect(Object.keys(useAppStore.getState().downloaded).sort()).toEqual(['A', 'B']);
  });

  it('a crop of the time step (nothing ticked) hides the results too', async () => {
    tiler();
    useAppStore.setState({ resultsOnMap: true, selectedIds: [] });
    await useAppStore.getState().enterFocus(true);
    expect(useAppStore.getState().resultsOnMap).toBe(false);
    expect(Object.keys(useAppStore.getState().downloaded).sort()).toEqual(['A', 'B', 'C']);
  });

  it('a scene ticked again after a crop leaves the view alone', async () => {
    tiler();
    useAppStore.setState({ selectedIds: ['A'] });
    await useAppStore.getState().enterFocus(true);
    const view = useAppStore.getState().downloaded;
    useAppStore.getState().toggleSelected('A');
    expect(useAppStore.getState().selectedIds).toEqual(['A']);
    expect(useAppStore.getState().focusMode).toBe(true);
    expect(useAppStore.getState().downloaded).toBe(view);
    expect(useAppStore.getState().cropToAoi).toBe(true);
  });

  it('"Add to layers" right after a crop takes all scenes of the view, as nothing is ticked any more', async () => {
    tiler();
    useAppStore.setState({ selectedIds: ['A', 'B'] });
    await useAppStore.getState().enterFocus(true);
    useAppStore.getState().addCurrentToLayers();
    await vi.waitFor(() => expect(useAppStore.getState().layers.length).toBeGreaterThan(0));
    const layers = useAppStore.getState().layers;
    expect(layers.flatMap((l) => l.restore.itemIds).sort()).toEqual(['A', 'B']);
  });

  it('the switch alone changes it, in a view as well', async () => {
    tiler();
    await useAppStore.getState().enterFocus(false);
    const was = useAppStore.getState().resultsOnMap;
    useAppStore.getState().toggleResultsOnMap();
    expect(useAppStore.getState().resultsOnMap).toBe(!was);
    expect(useAppStore.getState().focusMode).toBe(true);
  });

  it('are not touched by a view that cannot be entered', async () => {
    tiler();
    useAppStore.setState({ aoi: null, resultsOnMap: false, selectedIds: ['A'] });
    await useAppStore.getState().enterFocus(true);
    expect(useAppStore.getState().focusMode).toBe(false);
    expect(useAppStore.getState().resultsOnMap).toBe(false);
    expect(useAppStore.getState().selectedIds).toEqual(['A']);
  });

  it('"Change image" leaves the view, opens the results and shows them (Otto, 2.11.2026), and leaves the tick', async () => {
    tiler();
    useAppStore.setState({ resultsOnMap: false, selectedIds: ['A'], dock: null, resultsAt: 1, sections: [{ datasetId: ID, items: useAppStore.getState().items, groups: useAppStore.getState().groups, notes: [] }] as never });
    await useAppStore.getState().enterFocus(false);
    useAppStore.getState().changeImage();
    expect(useAppStore.getState().focusMode).toBe(false);
    expect(useAppStore.getState().dock).toBe('results');
    expect(useAppStore.getState().resultsOnMap).toBe(true);
    expect(useAppStore.getState().resultsAt).toBe(0);
    expect(useAppStore.getState().selectedIds).toEqual(['A']);
  });

  it('"Change image" without results opens nothing', async () => {
    tiler();
    useAppStore.setState({ sections: [], dock: 'controls' });
    await useAppStore.getState().enterFocus(false);
    useAppStore.getState().changeImage();
    expect(useAppStore.getState().focusMode).toBe(false);
    expect(useAppStore.getState().dock).toBe('controls');
  });
});
