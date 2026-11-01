// @vitest-environment jsdom
//
// One band of the data in the view (NM4-45, Otto, 27.10.2026): the dropdown "Band" offers the standard picture ("RGB"), the single
// bands of the dataset from its item and the registry, and after a line the presets. A band is drawn from its own asset with
// its own colormap and range; "Add to layers" keeps it; the show/hide, the choice of scenes and the places of the bars are not
// touched by it.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from '../datasets';
import { SENTINEL_2_PRESETS } from '../fixtures/indexPresets';
import { useAppStore, type AppState } from '../store';
import type { Collection, DownloadedInfo, StacAsset, StacItem } from '../types';
import { viewLayerOf } from '../viewLayer';
import ViewerControls from './ViewerControls';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const collection = (extra: object = {}): Collection =>
  ({
    id: 'optical',
    title: 'Sentinel-2 L2A',
    'earthx:format': 'cog',
    'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
    'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
    'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
    'earthx:true_color': ['red', 'green', 'blue'],
    'earthx:auxiliary_assets': ['visual', 'preview'],
    'earthx:mask': { asset: 'scl', band: 'scl', classes: [{ value: 3, label: 'Cloud shadow' }], suggested: [3] },
    'earthx:index_presets': SENTINEL_2_PRESETS,
    ...extra,
  }) as unknown as Collection;

const tiff = (bands: number): StacAsset => ({ href: 'https://data.test/x.tif', type: 'image/tiff; application=geotiff', 'raster:bands': Array.from({ length: bands }, () => ({})) }) as StacAsset;
const ASSETS = { visual: tiff(3), preview: tiff(3), B04: tiff(1), B08: tiff(1), scl: tiff(1), thumbnail: { href: 'https://data.test/t.jpg', type: 'image/jpeg', roles: ['thumbnail'] } as StacAsset };

const info = (id: string): DownloadedInfo => ({
  datasetId: 'optical',
  tileUrl: `/collections/optical/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`,
  bounds: [0, 0, 1, 1],
  asset: 'visual',
  minZoom: 8,
  maxZoom: 14,
});
const item = (id: string, assets: Record<string, StacAsset> = ASSETS): StacItem => ({ id, collection: 'optical', bbox: [0, 0, 1, 1], properties: { datetime: '2026-07-01T10:00:00Z' }, assets });

let container: HTMLDivElement;
let root: Root;
let fetchMock: ReturnType<typeof vi.fn>;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

function mount(over: Partial<AppState> = {}, coll: Collection = collection(), assets: Record<string, StacAsset> = ASSETS) {
  const items = [item('s0', assets), item('s1', assets)];
  act(() => {
    useAppStore.setState({
      datasets: datasetsFrom([coll]),
      datasetId: 'optical',
      items,
      groups: [{ key: ['a'], label: '2026-07-01', items }],
      selectedIds: ['s0'],
      downloaded: { s0: info('s0'), s1: info('s1') },
      focusMode: true,
      cropToAoi: true,
      showDownloaded: true,
      shownImage: null,
      viewLooks: {},
      savedLooks: {},
      appliedRender: { rescale: '0,3000' },
      pendingColormapName: '',
      pendingVmin: '0',
      pendingVmax: '3000',
      pendingIndex: '',
      pendingBand: '',
      mosaics: {},
      mapZoom: 12,
      layers: [],
      viewOfLayer: false,
      viewLayerId: null,
      focusLoading: false,
      pinLoading: false,
      dock: null,
      error: null,
      notice: null,
      ...over,
    });
    root.render(<ViewerControls />);
  });
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  fetchMock = vi.fn(async (url: string) => {
    if (url.includes('/statistics')) {
      return json({ b1: { min: 100, max: 4000, percentile_2: 150, percentile_98: 2500 } });
    }
    if (url.includes('/mosaic/')) {
      return json({ bounds: [0, 0, 1, 1], minzoom: 8, maxzoom: 14, tiles: ['x'], 'earthx:order': ['s0', 's1'] });
    }
    return json({ detail: 'not found' }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

const field = (name: string) => [...container.querySelectorAll<HTMLLabelElement>('.vc-render label')].find((l) => l.querySelector('span')?.textContent === name) ?? null;
const select = () => field('Band')?.querySelector('select') as HTMLSelectElement;
const colormapSelect = () => field('Colormap')!.querySelector('select')!;
const inputs = () => [...container.querySelectorAll<HTMLInputElement>('.vc-num input')].filter((i) => i.type === 'number');
const choose = (value: string) =>
  act(() => {
    Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')!.set!.call(select(), value);
    select().dispatchEvent(new Event('change', { bubbles: true }));
  });
const apply = () => act(() => (container.querySelector('.vc-apply') as HTMLButtonElement).dispatchEvent(new MouseEvent('click', { bubbles: true })));
const settle = () => act(async () => { await vi.waitFor(() => expect(useAppStore.getState().focusLoading).toBe(false)); await new Promise((r) => setTimeout(r, 10)); });
const store = () => useAppStore.getState();

describe('the dropdown "Band" of the view', () => {
  it('lists the standard picture as "RGB", the bands of the item, a line and the presets; the standard picture is chosen to begin with', () => {
    mount();
    expect([...select().options].map((o) => o.textContent)).toEqual(['RGB', 'B04', 'B08', '──────────', 'NDVI', 'NDWI', 'NDSI', 'NBR', 'EVI']);
    expect(select().value).toBe('');
  });

  it('leaves out what is no band: the pictures made from the bands, the mask layer, a thumbnail, and "visual" as an entry of its own', () => {
    mount();
    const values = [...select().options].map((o) => o.value);
    for (const left of ['visual', 'preview', 'scl', 'thumbnail']) expect(values).not.toContain(`band:${left}`);
    expect(values).toContain('band:B04');
  });

  it('takes the bands from the item, not from a list in the page', () => {
    mount({}, collection(), { visual: tiff(3), B02: tiff(1), B03: tiff(1) });
    expect([...select().options].map((o) => o.value).filter((v) => v.startsWith('band:'))).toEqual(['band:B02', 'band:B03']);
  });

  it('is not there when it would have one entry: no band besides the standard picture and no preset', () => {
    mount({}, collection({ 'earthx:index_presets': [] }), { visual: tiff(3) });
    expect(field('Band')).toBeNull();
    expect(container.querySelector('.vc-render')!.classList.contains('has-index')).toBe(false);
  });

  it('is there for bands alone, without presets', () => {
    mount({}, collection({ 'earthx:index_presets': [] }));
    expect([...select().options].map((o) => o.textContent)).toEqual(['RGB', 'B04', 'B08']);
  });

  it('names the standard picture by its asset where the dataset has no true-colour one', () => {
    mount({}, collection({ 'earthx:true_color': null, 'earthx:default_render': { title: 'Grey', assets: ['B08'], rescale: [[0, 1]], colormap_name: null, expression: null, resampling: 'nearest' } }));
    expect([...select().options].slice(0, 2).map((o) => o.textContent)).toEqual(['B08', 'B04']);
  });

  it('is the same dropdown as the one of the presets: no field "Index" any more', () => {
    mount();
    expect(field('Index')).toBeNull();
  });
});

describe('choosing a band', () => {
  it('puts the colormap and the range of a band in the fields, measured from the scene, and draws nothing until "Apply"', async () => {
    mount();
    expect(colormapSelect().options[0].textContent).toBe('— none —'); // fixed: three bands have no colormap
    choose('band:B04');
    await settle();
    expect(select().value).toBe('band:B04');
    expect([...colormapSelect().options].map((o) => o.value)[0]).toBe(''); // a colormap to choose now
    expect(colormapSelect().options.length).toBeGreaterThan(1);
    expect(inputs().map((i) => i.value)).toEqual(['150', '2500']); // the 2nd and 98th percentile of the band
    // The statistics were asked for the asset of the band.
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/statistics') && String(url).includes('asset=B04'))).toBe(true);
    // Nothing is drawn differently yet.
    expect(store().appliedRender).toEqual({ rescale: '0,3000' });
    expect(store().downloaded.s0.asset).toBe('visual');
  });

  it('draws the scenes from the asset of the band once "Apply" is pressed, and asks for the mosaic of that asset', async () => {
    mount();
    choose('band:B04');
    await settle();
    apply();
    await settle();
    expect(store().appliedRender).toMatchObject({ band: 'B04', rescale: '150,2500' });
    for (const id of ['s0', 's1']) {
      expect(store().downloaded[id]).toMatchObject({ asset: 'B04', baseAsset: 'visual' });
      expect(store().downloaded[id].tileUrl).toContain('asset=B04');
    }
    const asked = fetchMock.mock.calls.map(([url]) => String(url)).filter((url) => url.includes('/mosaic/'));
    expect(asked.some((url) => url.includes('asset=B04'))).toBe(true);
  });

  it('goes back to the standard picture with "RGB": the scenes are drawn from the asset they were opened with', async () => {
    mount();
    choose('band:B08');
    await settle();
    apply();
    await settle();
    choose('');
    await settle();
    expect(select().value).toBe('');
    apply();
    await settle();
    expect(store().appliedRender.band).toBeUndefined();
    expect(store().downloaded.s0).toMatchObject({ asset: 'visual' });
    expect(store().downloaded.s0.tileUrl).toContain('asset=visual');
  });

  it('leaves a band for an index and an index for a band: one picture at a time', async () => {
    mount();
    choose('band:B04');
    await settle();
    choose('index:NDVI');
    expect(select().value).toBe('index:NDVI');
    expect(store().pendingBand).toBe('');
    choose('band:B08');
    await settle();
    expect(store().pendingIndex).toBe('');
    expect(store().pendingBand).toBe('B08');
  });

  it('refuses a band the item does not have', async () => {
    mount();
    act(() => store().chooseViewBand('B99'));
    expect(store().pendingBand).toBe('');
    act(() => store().chooseViewBand('visual'));
    expect(store().pendingBand).toBe('');
  });

  it('is taken by "Apply" as a change of its own, though colormap and range are the same', async () => {
    mount({ appliedRender: { colormapName: 'gray', rescale: '150,2500' }, pendingColormapName: 'gray', pendingVmin: '150', pendingVmax: '2500' });
    const button = container.querySelector('.vc-apply') as HTMLButtonElement;
    expect(button.getAttribute('aria-disabled')).toBe('true');
    act(() => useAppStore.setState({ pendingBand: 'B04' }));
    expect(button.getAttribute('aria-disabled')).toBeNull();
  });

  it('does not touch show/hide, the choice of scenes or the place of the bars', async () => {
    mount({ showDownloaded: false, selectedIds: ['s0'], dock: 'results' });
    const before = { showDownloaded: store().showDownloaded, selectedIds: store().selectedIds, dock: store().dock, resultsOnMap: store().resultsOnMap };
    choose('band:B04');
    await settle();
    apply();
    await settle();
    expect({ showDownloaded: store().showDownloaded, selectedIds: store().selectedIds, dock: store().dock, resultsOnMap: store().resultsOnMap }).toEqual(before);
  });
});

describe('a band and the layer manager', () => {
  it('"Add to layers" keeps the band: the layer draws the asset of the band and its look names it', async () => {
    mount();
    choose('band:B04');
    await settle();
    apply();
    await settle();
    // The mosaic of the band is here, so the layer can be made at once.
    act(() => store().addCurrentToLayers());
    await act(async () => {
      await vi.waitFor(() => expect(store().layers).toHaveLength(1));
    });
    const [layer] = store().layers;
    expect(layer.restore.appliedRender).toMatchObject({ band: 'B04' });
    expect(Object.values(layer.restore.downloaded).every((d) => d.asset === 'B04')).toBe(true);
    expect(layer.overlays.filter((o) => o.kind === 'raster').every((o) => o.kind === 'raster' && o.tileUrl.includes('B04'))).toBe(true);
  });

  it('"Apply to all" gives every image of the dataset the band', async () => {
    const items = [item('s0'), item('s1')];
    mount({ items, groups: [{ key: ['a'], label: 'a', items: [items[0]] }, { key: ['b'], label: 'b', items: [items[1]] }] });
    choose('band:B04');
    await settle();
    act(() => void store().saveViewLook());
    await settle();
    expect(store().downloaded.s0.asset).toBe('B04');
    expect(store().downloaded.s1.asset).toBe('B04');
  });

  it('keeps each image to its own band when stepping from one to the next', async () => {
    const items = [item('s0'), item('s1')];
    mount({ items, groups: [{ key: ['a'], label: 'a', items: [items[0]] }, { key: ['b'], label: 'b', items: [items[1]] }] });
    choose('band:B04');
    await settle();
    apply();
    await settle();
    act(() => store().stepImage(1));
    await settle();
    expect(store().downloaded.s0.asset).toBe('B04');
    expect(store().downloaded.s1.asset).toBe('visual');
    expect(select().value).toBe('');
    act(() => store().stepImage(-1));
    await settle();
    expect(select().value).toBe('band:B04');
  });
});

// Otto, 1.11.2026 (zu #272): "Add to layers" pins the whole view, not only the band: the layer keeps every band and RGB of the view, and
// only the setting stays as the view had it. The dropdown of the layer is free, "Apply to all" keeps a new choice for the layer.
describe('a layer pinned with a band', () => {
  async function pinWithBand() {
    mount();
    choose('band:B04');
    await settle();
    apply();
    await settle();
    act(() => store().addCurrentToLayers());
    await act(async () => {
      await vi.waitFor(() => expect(store().layers).toHaveLength(1));
    });
    act(() => store().exitFocus());
    act(() => store().selectLayer(store().layers[0].id));
    act(() => root.render(<ViewerControls />));
    await settle();
  }
  const layerAssets = () => Object.values(store().layers[0].restore.downloaded).map((d) => d.asset);
  const layerTiles = () => store().layers[0].overlays.flatMap((o) => (o.kind === 'raster' ? [o.tileUrl] : []));

  it('shows the picture it was pinned with in the dropdown, which is free, with every band and RGB still in it', async () => {
    await pinWithBand();
    expect(store().viewOfLayer).toBe(true);
    expect(select().disabled).toBe(false);
    expect(select().value).toBe('band:B04');
    expect([...select().options].map((o) => o.textContent)).toEqual(['RGB', 'B04', 'B08', '──────────', 'NDVI', 'NDWI', 'NDSI', 'NBR', 'EVI']);
    expect(store().layers[0].restore.appliedRender).toMatchObject({ band: 'B04' });
    // The scenes remember the asset the standard picture comes from.
    expect(Object.values(store().layers[0].restore.downloaded).every((d) => d.baseAsset === 'visual')).toBe(true);
  });

  // Otto, 1.11.2026 (Browsertest zu #272): the settings of a layer change the layer itself, at its place, and are kept with "Save" only.
  // Otto, 1.11.2026: a band chosen in the settings of a layer is seen once "Apply" is pressed, as in the view.
  it('is drawn from another band once "Apply" is pressed, as the same layer at the same place, and from RGB again', async () => {
    await pinWithBand();
    const [first] = store().layers;
    expect(layerAssets()).toEqual(['B04']);
    choose('band:B08');
    await settle();
    expect(layerAssets()).toEqual(['B04']); // chosen, not drawn
    apply();
    await settle();
    expect(store().layers.map((l) => l.id)).toEqual([first.id]); // no layer is added, none behind it
    expect(layerAssets()).toEqual(['B08']);
    expect(store().layers[0].restore.appliedRender).toMatchObject({ band: 'B08' });
    expect(layerTiles().every((url) => url.includes('B08'))).toBe(true);
    choose('');
    await settle();
    apply();
    await settle();
    expect(store().layers.map((l) => l.id)).toEqual([first.id]);
    expect(layerAssets()).toEqual(['visual']);
    expect(store().layers[0].restore.appliedRender.band).toBeUndefined();
    expect(layerTiles().every((url) => url.includes('visual'))).toBe(true);
  });

  it('is the picture of the view while it is changed: the view draws no picture of its own besides the layer', async () => {
    await pinWithBand();
    choose('band:B08');
    await settle();
    await act(async () => { await store().applyRender(); });
    const s = store();
    expect(viewLayerOf(s.layers, { ...s, aoi: s.viewAoi })?.id).toBe(s.layers[0].id);
  });

  it('is put back as saved when the settings are closed without "Save": by the x, by Esc, by another layer', async () => {
    await pinWithBand();
    choose('band:B08');
    await settle();
    apply();
    await settle();
    expect(layerAssets()).toEqual(['B08']);
    act(() => store().exitFocus());
    expect(layerAssets()).toEqual(['B04']);
    expect(store().layers[0].saved).toBeUndefined();
    expect(store().layers[0].restore.appliedRender).toMatchObject({ band: 'B04' });
    // Esc.
    act(() => store().selectLayer(store().layers[0].id));
    act(() => root.render(<ViewerControls />));
    choose('index:NDVI');
    await settle();
    apply();
    await settle();
    expect(store().layers[0].restore.appliedRender).toMatchObject({ index: 'NDVI' });
    act(() => void document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
    expect(store().viewOfLayer).toBe(false);
    expect(store().layers[0].restore.appliedRender).toMatchObject({ band: 'B04' });
    expect(layerAssets()).toEqual(['B04']);
  });

  it('is kept with "Save": the settings close with the new picture', async () => {
    await pinWithBand();
    choose('band:B08');
    await settle();
    apply();
    await settle();
    expect(container.querySelector('.vc-save')!.textContent).toBe('Save');
    expect(container.querySelector('.vc-save')!.getAttribute('aria-disabled')).toBeNull();
    act(() => void (container.querySelector('.vc-save') as HTMLButtonElement).click());
    await settle();
    expect(store().layers[0].saved).toBeUndefined();
    expect(container.querySelector('.vc-save')!.getAttribute('aria-disabled')).toBe('true');
    act(() => store().exitFocus());
    expect(layerAssets()).toEqual(['B08']);
    expect(store().layers[0].restore.appliedRender).toMatchObject({ band: 'B08' });
  });

  it('keeps the opacity apart as well: seen at once, kept with "Save", gone with the close', async () => {
    await pinWithBand();
    act(() => store().setLayerOpacity(store().layers[0].id, 0.4));
    expect(store().layers[0].opacity).toBe(0.4);
    expect(container.querySelector('.vc-save')!.getAttribute('aria-disabled')).toBeNull();
    act(() => store().exitFocus());
    expect(store().layers[0].opacity).toBe(1);
    act(() => store().selectLayer(store().layers[0].id));
    act(() => root.render(<ViewerControls />));
    act(() => store().setLayerOpacity(store().layers[0].id, 0.4));
    act(() => void (container.querySelector('.vc-save') as HTMLButtonElement).click());
    await settle();
    act(() => store().exitFocus());
    expect(store().layers[0].opacity).toBe(0.4);
  });

  it('is not touched by the opacity of a layer whose settings are not open', async () => {
    await pinWithBand();
    const id = store().layers[0].id;
    act(() => store().exitFocus());
    act(() => store().setLayerOpacity(id, 0.3));
    expect(store().layers[0].saved).toBeUndefined();
    expect(store().layers[0].opacity).toBe(0.3);
  });

  it('is drawn with an index from a band, and back, with no quicklook under the index', async () => {
    await pinWithBand();
    choose('index:NDVI');
    await settle();
    apply();
    await settle();
    expect(store().layers[0].restore.appliedRender).toMatchObject({ index: 'NDVI' });
    expect(store().layers[0].restore.appliedRender.band).toBeUndefined();
    expect(layerAssets()).toEqual(['visual']);
    expect(layerTiles().every((url) => url.includes('band_math'))).toBe(true);
    expect(store().layers[0].overlays.some((o) => o.kind === 'image')).toBe(false);
  });
});


// Otto, 1.11.2026 (zu #272): "Temporary" goes with "Add to layers" for the image pinned, and comes back with a change; "Add all to layers"
// takes it off every image, so that a step nobody changed shows none.
describe('the mark "Temporary" and the layers', () => {
  const temporary = () => container.querySelector('.vc-temporary') !== null;
  const twoImages = () => {
    const items = [item('s0'), item('s1')];
    mount({ items, groups: [{ key: ['a'], label: 'a', items: [items[0]] }, { key: ['b'], label: 'b', items: [items[1]] }], selectedIds: [] });
  };
  const pin = async (what: 'addCurrentToLayers' | 'addAllToLayers') => {
    act(() => store()[what]());
    await act(async () => {
      await vi.waitFor(() => expect(store().layers.length).toBeGreaterThan(0));
    });
    await settle();
  };

  it('is on a view that no layer holds, goes with "Add to layers" for that image, and is back with a change', async () => {
    mount({ selectedIds: [] });
    expect(temporary()).toBe(true);
    await pin('addCurrentToLayers');
    expect(temporary()).toBe(false);
    choose('band:B04');
    await settle();
    expect(temporary()).toBe(true); // chosen: something changed
    choose('');
    await settle();
    expect(temporary()).toBe(false); // back to what the layer holds
  });

  it('is on the step that was pinned no more, and on another step of the view still', async () => {
    twoImages();
    await pin('addCurrentToLayers');
    expect(temporary()).toBe(false);
    act(() => store().stepImage(1));
    await settle();
    expect(temporary()).toBe(true);
    act(() => store().stepImage(-1));
    await settle();
    expect(temporary()).toBe(false);
  });

  it('is on no step after "Add all to layers" while nothing changed, and on the one that is changed afterwards', async () => {
    twoImages();
    await pin('addAllToLayers');
    await vi.waitFor(() => expect(store().layers).toHaveLength(2));
    expect(temporary()).toBe(false);
    act(() => store().stepImage(1));
    await settle();
    expect(temporary()).toBe(false);
    choose('band:B04');
    await settle();
    expect(temporary()).toBe(true);
    act(() => store().stepImage(-1));
    await settle();
    expect(temporary()).toBe(false);
  });
});
