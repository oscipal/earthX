// @vitest-environment jsdom
//
// The presets of the view of scenes (NM4-14b, review of Otto 31.10.2026), since UI-03d buttons in "Quick processing" (Otto, 2.11.2026):
// drawn at once, on or off, the tooltip with the formula, the short note where the index cannot be drawn (and its explanation).

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import CSS from '../index.css?raw';
import { datasetsFrom } from '../datasets';
import { SENTINEL_2_PRESETS } from '../fixtures/indexPresets';
import { mosaicTemplateOf } from '../mosaic';
import { SHORT_COLORMAPS } from '../colormaps';
import { useAppStore, type AppState } from '../store';
import type { Collection, DownloadedInfo, StacItem } from '../types';
import ViewerControls from './ViewerControls';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const collection = (presets: unknown[] | null, trueColor = true): Collection =>
  ({
    id: 'optical',
    title: 'Sentinel-2 L2A',
    'earthx:format': 'cog',
    'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
    'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
    'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
    ...(trueColor ? { 'earthx:true_color': ['red', 'green', 'blue'] } : {}),
    ...(presets ? { 'earthx:index_presets': presets } : {}),
  }) as unknown as Collection;

const info = (id: string): DownloadedInfo => ({ datasetId: 'optical', tileUrl: `/collections/optical/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`, bounds: [0, 0, 1, 1], asset: 'visual', minZoom: 8, maxZoom: 14 });
const item = (id: string): StacItem => ({ id, collection: 'optical', bbox: [0, 0, 1, 1], properties: { datetime: '2026-07-01T10:00:00Z' }, assets: {} });

let container: HTMLDivElement;
let root: Root;

// `null`: a collection with no field (a backend before NM4-14a).
function mount(presets: unknown[] | null = SENTINEL_2_PRESETS, over: Partial<AppState> = {}) {
  const items = [item('s0'), item('s1')];
  act(() => {
    useAppStore.setState({
      datasets: datasetsFrom([collection(presets)]),
      datasetId: 'optical',
      items,
      groups: [{ key: ['a'], label: '2026-07-01', items }],
      selectedIds: [],
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
      pendingIndex: over.appliedRender?.index ?? '',
      pendingBand: '',
      pendingChannels: [],
      pendingUnit: 'value',
      enhance: null,
      mosaics: {},
      mapZoom: 12,
      layers: [],
      focusLoading: false,
      pinLoading: false,
      dock: null,
      ...over,
    });
    root.render(<ViewerControls />);
  });
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 404 })));
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

const field = () => [...container.querySelectorAll<HTMLLabelElement>('.vc-render label')].find((l) => l.querySelector('span')?.textContent === 'Band') ?? null;
const select = () => field()?.querySelector('select') as HTMLSelectElement;
const colormapSelect = () => [...container.querySelectorAll<HTMLLabelElement>('.vc-render label')].find((l) => l.querySelector('span')?.textContent === 'Colormap')!.querySelector('select')!;
const note = () => container.querySelector<HTMLElement>('.vc-note');
const choose = (value: string) =>
  act(() => {
    Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')!.set!.call(select(), value);
    select().dispatchEvent(new Event('change', { bubbles: true }));
  });

const quick = () => [...container.querySelectorAll<HTMLButtonElement>('.vc-quick button')];
const quickButton = (name: string) => quick().find((b) => b.textContent === name)!;
const press = async (name: string) => {
  await act(async () => {
    quickButton(name).click();
  });
};
const pressed = () => quick().filter((b) => b.getAttribute('aria-pressed') === 'true').map((b) => b.textContent);

describe('"Quick processing" (UI-03d, Otto, 2.11.2026)', () => {
  it('has the presets of the dataset in the order of the registry and "Enhance contrast", none of them on', () => {
    mount();
    expect(quick().map((b) => b.textContent)).toEqual(['NDVI', 'NDWI', 'NDSI', 'NBR', 'EVI', 'Enhance contrast']);
    expect(pressed()).toEqual([]);
  });

  it('stands between "Display" and "Actions"', () => {
    mount();
    expect([...container.querySelectorAll('.insp-heading')].map((h) => h.textContent)).toEqual(['Display', 'Quick processing', 'Actions']);
  });

  it('has three in a row, in two rows', () => {
    expect(CSS).toMatch(/\.inspector \.vc-quick \{[^}]*grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)/u);
  });

  it('leaves the presets out of the dropdown "Band": the original and its bands only', () => {
    mount();
    expect([...select().options].map((o) => o.textContent)).toEqual(['RGB']);
    expect(select().value).toBe('');
    expect(field()!.title).toBe('This picture has one band');
  });

  it.each([
    ['an empty list (the DEM)', []],
    ['no field (a backend before NM4-14a)', null],
  ])('has "Enhance contrast" alone for a dataset with %s', (_, presets) => {
    mount(presets);
    expect(quick().map((b) => b.textContent)).toEqual(['Enhance contrast']);
  });

  it('says what an index is in the tooltip: title and formula', () => {
    mount();
    expect(quickButton('NDVI').title).toContain('Normalized Difference Vegetation Index: (N - R)/(N + R). Formula: Awesome Spectral Indices.');
    expect(quickButton('NDWI').title).toContain('(McFeeters 1996)');
    expect(quickButton('Enhance contrast').title).toContain('2nd to its 98th percentile');
  });

  it('draws an index at once, with no "Apply" and no job, and shows it on; a second click goes back to the picture of the dataset', async () => {
    mount();
    await press('NDWI');
    expect(useAppStore.getState().appliedRender).toEqual({ index: 'NDWI', colormapName: 'rdbu', rescale: '-1,1' });
    expect(pressed()).toEqual(['NDWI']);
    expect((container.querySelector('.vc-apply') as HTMLButtonElement).getAttribute('aria-disabled')).toBe('true');
    // The field "Band" says what is drawn, and the index is no band to pick there.
    expect(select().value).toBe('index:NDWI');
    expect([...select().options].find((o) => o.value === 'index:NDWI')!.disabled).toBe(true);
    // No request but the statistics: no job is placed.
    const calls = vi.mocked(fetch).mock.calls.map(([url]) => String(url));
    expect(calls.every((url) => url.includes('/statistics') || url.endsWith('/colormaps'))).toBe(true);
    await press('NDWI');
    expect(useAppStore.getState().appliedRender).toEqual({ rescale: '0,3000' });
    expect(pressed()).toEqual([]);
    expect(select().value).toBe('');
  });

  it('takes one index at a time: another one puts the first away', async () => {
    mount();
    await press('NDVI');
    await press('EVI');
    expect(pressed()).toEqual(['EVI']);
    expect(useAppStore.getState().appliedRender.index).toBe('EVI');
  });

  it('is put away by a band picked in the dropdown', async () => {
    mount(SENTINEL_2_PRESETS, { items: [{ ...item('s0'), assets: { red: { href: 'r.tif', type: 'image/tiff; application=geotiff; profile=cloud-optimized', 'eo:bands': [{ name: 'red' }] } } }, item('s1')] as StacItem[] });
    await press('NDVI');
    choose('band:red');
    expect(pressed()).toEqual([]);
  });

  it('shows the colormap and the range of the preset in the fields, and a colormap to choose where the dataset draws RGB', async () => {
    mount();
    expect([...colormapSelect().options].map((o) => o.textContent)).toEqual(['— none —']);
    await press('NDWI');
    expect(colormapSelect().value).toBe('rdbu');
    // The few of the field and "More…" (UI-03d); the whole list is the tiler's.
    expect([...colormapSelect().options].map((o) => o.textContent)).toEqual(['— none —', ...SHORT_COLORMAPS, 'More…']);
    expect(SHORT_COLORMAPS).toContain('rdbu');
    const [vmin, vmax] = container.querySelectorAll<HTMLInputElement>('.vc-num input');
    expect([vmin.value, vmax.value]).toEqual(['-1', '1']);
  });
});

describe('"Apply to all" with indices of one range (Otto, 1.11.2026)', () => {
  const applyAll = () => [...container.querySelectorAll<HTMLButtonElement>('.vc-buttons button')].find((b) => b.textContent?.trim() === 'Apply to all')!;
  const locked = () => applyAll().getAttribute('aria-disabled') === 'true';
  // Two images (two time steps), each of one scene.
  const twoImages = () => {
    const items = [item('s0'), item('s1')];
    mount(SENTINEL_2_PRESETS, { items, groups: [{ key: ['a'], label: 'a', items: [items[0]] }, { key: ['b'], label: 'b', items: [items[1]] }] });
  };

  it('is open when the image shown has another index than the other image, though NDVI and EVI are drawn alike', () => {
    twoImages();
    act(() => useAppStore.getState().chooseViewIndex('NDVI'));
    act(() => void useAppStore.getState().applyRender());
    act(() => useAppStore.getState().stepImage(1));
    act(() => useAppStore.getState().chooseViewIndex('EVI'));
    act(() => void useAppStore.getState().applyRender());
    expect(useAppStore.getState().appliedRender).toMatchObject({ index: 'EVI', colormapName: 'rdylgn', rescale: '-1,1' });
    expect(locked()).toBe(false);
  });

  it('is locked again once every image shows it, and for any other of the three the moment it is chosen', () => {
    twoImages();
    act(() => useAppStore.getState().chooseViewIndex('NDVI'));
    act(() => void useAppStore.getState().saveViewLook());
    expect(locked()).toBe(true);
    // Chosen but not applied: "Apply to all" takes what the fields hold, so it has something to do.
    act(() => useAppStore.getState().chooseViewIndex('NBR'));
    expect(locked()).toBe(false);
    expect(applyAll().title).toContain('Draw every image of this dataset with these values');
  });
});

describe('the note under the settings', () => {
  const none = () => expect(note()).toBeNull();

  it('is not there without an index, wherever the map is', () => {
    mount(SENTINEL_2_PRESETS, { mapZoom: 2 });
    none();
    mount(null, { mapZoom: 2 });
    none();
  });

  it('asks to zoom in where the map is too far out, and says why in its tooltip', () => {
    mount(SENTINEL_2_PRESETS, { mapZoom: 5, appliedRender: { index: 'NDVI', colormapName: 'rdylgn', rescale: '-1,1' } });
    expect(note()!.textContent).toBe('Zoom in to compute NDVI');
    expect(note()!.title).toBe('The quick calculation works from zoom 8. For whole scenes start a job in Processing.');
    expect(select().value).toBe('index:NDVI'); // the choice stays
  });

  it('is gone once the map is zoomed in, and comes back when it is zoomed out again', () => {
    const render = { index: 'NDVI', colormapName: 'rdylgn', rescale: '-1,1' };
    mount(SENTINEL_2_PRESETS, { mapZoom: 5, appliedRender: render });
    act(() => useAppStore.setState({ mapZoom: 9 }));
    none();
    act(() => useAppStore.setState({ mapZoom: 4 }));
    expect(note()!.textContent).toBe('Zoom in to compute NDVI');
  });

  it('names the index drawn, and is there the moment it is drawn out of reach', async () => {
    mount(SENTINEL_2_PRESETS, { mapZoom: 5 });
    none();
    await press('NDWI');
    expect(note()!.textContent).toBe('Zoom in to compute NDWI');
    expect(note()!.closest('.insp-section')!.querySelector('.insp-heading')!.textContent).toBe('Quick processing');
  });

  it('says it cannot be computed where the tile route cannot take the scenes (the request is too long), at any zoom', () => {
    const ids = Array.from({ length: 64 }, (_, i) => `S2_${'x'.repeat(110)}${i}`);
    const items = ids.map(item);
    const downloaded = Object.fromEntries(ids.map((id) => [id, info(id)]));
    const entries = ids.map((id) => [id, downloaded[id]] as [string, DownloadedInfo]);
    mount(SENTINEL_2_PRESETS, {
      items,
      groups: [{ key: ['a'], label: 'a', items }],
      downloaded,
      mosaics: { [mosaicTemplateOf('optical', entries)!]: { tileUrl: '/m/{z}/{x}/{y}', bounds: [0, 0, 1, 1], minZoom: 8, maxZoom: 14, order: ids } },
      mapZoom: 14,
      appliedRender: { index: 'EVI', colormapName: 'rdylgn', rescale: '-1,1' },
    });
    expect(note()!.textContent).toBe('EVI cannot be computed here');
    expect(note()!.title).toContain('start a job in Processing');
    expect(select().value).toBe('index:EVI');
  });

  it('is one short line, no more than a sentence', () => {
    mount(SENTINEL_2_PRESETS, { mapZoom: 5, appliedRender: { index: 'NDVI', colormapName: 'rdylgn', rescale: '-1,1' } });
    expect(note()!.textContent!.length).toBeLessThan(40);
  });
});

describe('the layout (the CSS the view is made with)', () => {
  it('has the yellow note in a darker yellow on the light theme, where the pale one does not read', () => {
    expect(CSS).toMatch(/\.app\[data-theme='normal'\] \.inspector \.vc-note \{\s*color: #8a5a00;/u);
  });
});
