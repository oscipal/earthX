// M4-17c: a time step in the full-resolution view is one mosaic. What the store does about it:
// it asks the tiler for the mosaic's TileJSON once when the view opens (that also warms the
// tiler's item cache), keeps the answer, and pins the picture only once it is there.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { buildMosaicTileTemplate } from './api';
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

const ids = (n: number) => Array.from({ length: n }, (_, i) => `S${String(i).padStart(2, '0')}`);
const scene = (id: string): StacItem => ({
  id,
  bbox: [10, 47, 11, 48],
  properties: { datetime: '2026-07-24T10:00:00Z' },
  assets: {},
});

function json(body: unknown, status = 200): Response {
  return { ok: status < 300, status, statusText: '', json: async () => body } as Response;
}

const TILEJSON = (order: string[]) => ({
  bounds: [9, 46, 12, 49],
  minzoom: 8,
  maxzoom: 19,
  tiles: ['http://tiler.test/tiles'],
  'earthx:order': order,
});

// A tiler that answers the statistics of the stretch and the TileJSON of a mosaic.
function tiler(mosaic: (url: string) => Response | Promise<Response> = (url) => json(TILEJSON(itemsOf(url)))) {
  const fetchMock = vi.fn(async (url: string) => {
    if (url.includes('/mosaic/')) return mosaic(url);
    if (url.includes('/statistics')) return json({ '1': { min: 0, max: 4000, percentile_2: 0, percentile_98: 3000 } });
    throw new Error(`unexpected request: ${url}`);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}
const itemsOf = (url: string) => new URL(url, 'http://localhost').searchParams.getAll('item');
const mosaicCalls = () =>
  vi.mocked(fetch).mock.calls.map(([url]) => url as string).filter((url) => url.includes('/mosaic/'));

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

beforeEach(() => openGroup(['A', 'B', 'C']));
afterEach(() => vi.unstubAllGlobals());

describe('enterFocus with a time step of several scenes', () => {
  it('asks the tiler for the mosaic once, with every scene and the asset', async () => {
    tiler();
    await useAppStore.getState().enterFocus(false);
    expect(mosaicCalls()).toHaveLength(1);
    const params = new URL(mosaicCalls()[0], 'http://localhost').searchParams;
    expect(params.getAll('item')).toEqual(['A', 'B', 'C']);
    expect(params.get('asset')).toBe('visual');
    expect(mosaicCalls()[0]).toContain('/collections/sentinel-2-c1-l2a/mosaic/WebMercatorQuad/tilejson.json');
  });

  it('keeps what the TileJSON says, by the mosaic\'s tile template', async () => {
    tiler(() => json(TILEJSON(['C', 'A', 'B'])));
    await useAppStore.getState().enterFocus(false);
    const template = buildMosaicTileTemplate(ID, ['A', 'B', 'C'], 'visual');
    expect(useAppStore.getState().mosaics[template]).toEqual({
      tileUrl: template,
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
    answerMosaic(json(TILEJSON(['A', 'B', 'C'])));
    await entering;
    expect(useAppStore.getState().focusLoading).toBe(false);
  });

  it('does not ask for a mosaic of one scene', async () => {
    openGroup(['A']);
    tiler();
    await useAppStore.getState().enterFocus(false);
    expect(mosaicCalls()).toEqual([]);
    expect(useAppStore.getState().mosaics).toEqual({});
  });

  it('asks for the mosaic of each time step by itself', async () => {
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
    expect(mosaicCalls().map(itemsOf).sort()).toEqual([['A1', 'A2'], ['B1', 'B2']]);
  });

  it('draws a time step the tiler refused scene by scene, and says why', async () => {
    tiler(() => json({ detail: 'the items are of different passes' }, 422));
    await useAppStore.getState().enterFocus(false);
    const s = useAppStore.getState();
    expect(Object.values(s.mosaics)).toEqual([null]);
    expect(s.notice).toBe('Could not load the mosaic (the items are of different passes); its scenes are drawn one by one.');
    expect(s.focusMode).toBe(true);
    expect(Object.keys(s.downloaded)).toEqual(['A', 'B', 'C']);
  });

  it('does the same when the tiler cannot be reached at all', async () => {
    tiler(() => {
      throw new TypeError('Failed to fetch');
    });
    await useAppStore.getState().enterFocus(false);
    expect(Object.values(useAppStore.getState().mosaics)).toEqual([null]);
    expect(useAppStore.getState().notice).toMatch(/Failed to fetch/);
  });

  it('does the same for a TileJSON it cannot read', async () => {
    tiler(() => json({ bounds: [1, 2], minzoom: 8 }));
    await useAppStore.getState().enterFocus(false);
    expect(Object.values(useAppStore.getState().mosaics)).toEqual([null]);
    expect(useAppStore.getState().notice).toMatch(/cannot read/);
  });

  it('asks a second time after a refusal, not before', async () => {
    const fetchMock = tiler(() => json({ detail: 'down' }, 503));
    await useAppStore.getState().enterFocus(false);
    expect(mosaicCalls()).toHaveLength(1);
    fetchMock.mockImplementation(async (url: string) =>
      url.includes('/mosaic/') ? json(TILEJSON(['A', 'B', 'C'])) : json({ '1': { percentile_2: 0, percentile_98: 1 } }),
    );
    await useAppStore.getState().loadMosaics();
    expect(Object.values(useAppStore.getState().mosaics)[0]).not.toBeNull();
    await useAppStore.getState().loadMosaics();
    expect(mosaicCalls()).toHaveLength(2); // an answer that is there is not asked for again
  });

  it('asks once for two views that want the same mosaic at the same time', async () => {
    tiler();
    useAppStore.setState({
      focusMode: true,
      downloaded: Object.fromEntries(['A', 'B', 'C'].map((id) => [id, { asset: 'visual', minZoom: 0, maxZoom: 19 } as DownloadedInfo])),
    });
    await Promise.all([useAppStore.getState().loadMosaics(), useAppStore.getState().loadMosaics()]);
    expect(mosaicCalls()).toHaveLength(1);
  });

  it('does not ask for a mosaic outside the full-resolution view', async () => {
    tiler();
    await useAppStore.getState().loadMosaics();
    expect(mosaicCalls()).toEqual([]);
  });

  it('draws a time step of 64 scenes as a mosaic and says nothing', async () => {
    openGroup(ids(64));
    tiler();
    await useAppStore.getState().enterFocus(false);
    expect(mosaicCalls()).toHaveLength(1);
    expect(useAppStore.getState().notice).toBeNull();
  });

  it('keeps a time step of 65 scenes out of the tiler, and says it is drawn one by one, 40 of them', async () => {
    openGroup(ids(65));
    tiler();
    await useAppStore.getState().enterFocus(false);
    expect(mosaicCalls()).toEqual([]);
    expect(useAppStore.getState().notice).toBe(
      'A time step of 65 scenes is more than one mosaic takes (64); its scenes are drawn one by one, 25 of them not at all.',
    );
  });
});

describe('adding a mosaic to the layers', () => {
  async function enter(cropToAoi: boolean) {
    tiler(() => json(TILEJSON(['C', 'A', 'B'])));
    await useAppStore.getState().enterFocus(cropToAoi);
  }

  it('pins the mosaic and the scenes under it as one layer per time step, cut to the AOI', async () => {
    await enter(true);
    useAppStore.getState().addCurrentToLayers();
    const { layers, error } = useAppStore.getState();
    expect(error).toBeNull();
    expect(layers).toHaveLength(1);
    const overlays = layers[0].overlays;
    expect(overlays).toHaveLength(4);
    expect(overlays.every((o) => o.kind === 'raster' && o.tileUrl.startsWith('earthx-clip://'))).toBe(true);
    const mosaic = overlays[3];
    expect(mosaic.kind === 'raster' && mosaic.tileUrl).toContain('/mosaic/tiles/');
    expect(overlays.slice(0, 3).map((o) => o.kind === 'raster' && o.hideFrom)).toEqual([6.5, 6.5, 6.5]);
    expect(layers[0].restore.itemIds).toEqual(['A', 'B', 'C']);
  });

  it('pins the whole selection of an uncropped view as one layer, one mosaic per time step', async () => {
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
    useAppStore.getState().addCurrentToLayers();
    const { layers } = useAppStore.getState();
    expect(layers).toHaveLength(1);
    const urls = layers[0].overlays.map((o) => (o.kind === 'raster' ? o.tileUrl : ''));
    expect(urls.filter((u) => u.includes('/mosaic/'))).toHaveLength(2);
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
    expect(mosaicCalls()).toHaveLength(1);

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

describe('adding a part of the view to the layers', () => {
  const pickTwo = async (cropToAoi: boolean, mosaic: (url: string) => Response | Promise<Response>) => {
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
    expect(mosaicCalls().map(itemsOf)).toContainEqual(['A', 'B']);
    expect(layers[0].restore.itemIds).toEqual(['A', 'B']);
    const urls = layers[0].overlays.map((o) => (o.kind === 'raster' ? o.tileUrl : ''));
    expect(itemsOf(urls.find((u) => u.includes('/mosaic/')) as string)).toEqual(['A', 'B']);
  });

  it.each([true, false])('says why and pins nothing when the tiler cannot give it (cropped: %s)', async (cropToAoi) => {
    await pickTwo(cropToAoi, (url) =>
      itemsOf(url).length === 2 ? json({ detail: 'the items are of different passes' }, 422) : json(TILEJSON(['A', 'B', 'C'])),
    );
    useAppStore.getState().addCurrentToLayers();
    await vi.waitFor(() => expect(useAppStore.getState().pinLoading).toBe(false));
    const s = useAppStore.getState();
    expect(s.layers).toEqual([]);
    expect(s.notice).toBe('Could not load the mosaic (the items are of different passes); its scenes are drawn one by one.');
  });

  it('does not pin another selection than the one it was asked for', async () => {
    let answerMosaic: (r: Response) => void = () => {};
    await pickTwo(false, (url) =>
      itemsOf(url).length === 2 ? new Promise<Response>((resolve) => (answerMosaic = resolve)) : json(TILEJSON(['A', 'B', 'C'])),
    );
    useAppStore.getState().addCurrentToLayers();
    useAppStore.setState({ selectedIds: ['C'] }); // changed its mind meanwhile
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
    expect(mosaicCalls()).toEqual([]);
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
    await vi.waitFor(() => expect(mosaicCalls()).toHaveLength(1));
    expect(itemsOf(mosaicCalls()[0])).toEqual(['A', 'B']);
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

  it('"Change image" leaves the view and opens the results, and leaves the switch and the tick', async () => {
    tiler();
    useAppStore.setState({ resultsOnMap: false, selectedIds: ['A'], dock: null, sections: [{ datasetId: ID, items: useAppStore.getState().items, groups: useAppStore.getState().groups, notes: [] }] as never });
    await useAppStore.getState().enterFocus(false);
    useAppStore.getState().changeImage();
    expect(useAppStore.getState().focusMode).toBe(false);
    expect(useAppStore.getState().dock).toBe('results');
    expect(useAppStore.getState().resultsOnMap).toBe(false);
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
