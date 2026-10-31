// @vitest-environment jsdom
//
// The dropdown "Index" of the view of scenes (NM4-14b, review of Otto 31.10.2026): the presets of the dataset under "— none —", the
// tooltip with the formula, the short note where the index cannot be drawn (and its explanation), and no dropdown for a dataset
// without presets (the DEM).

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import CSS from '../index.css?raw';
import { datasetsFrom } from '../datasets';
import { SENTINEL_2_PRESETS } from '../fixtures/indexPresets';
import { mosaicTemplateOf } from '../mosaic';
import { COLORMAPS } from '../render';
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

const field = () => [...container.querySelectorAll<HTMLLabelElement>('.vc-render label')].find((l) => l.querySelector('span')?.textContent === 'Index') ?? null;
const select = () => field()?.querySelector('select') as HTMLSelectElement;
const colormapSelect = () => [...container.querySelectorAll<HTMLLabelElement>('.vc-render label')].find((l) => l.querySelector('span')?.textContent === 'Colormap')!.querySelector('select')!;
const note = () => container.querySelector<HTMLElement>('.vc-note');
const apply = () => act(() => (container.querySelector('.vc-apply') as HTMLButtonElement).dispatchEvent(new MouseEvent('click', { bubbles: true })));
const choose = (value: string) =>
  act(() => {
    Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')!.set!.call(select(), value);
    select().dispatchEvent(new Event('change', { bubbles: true }));
  });

describe('the dropdown "Index"', () => {
  it('lists the presets of the dataset in the order of the registry, under "— none —", with "none" chosen to begin with', () => {
    mount();
    expect([...select().options].map((o) => o.textContent)).toEqual(['— none —', 'NDVI', 'NDWI', 'NDSI', 'NBR', 'EVI']);
    expect(select().value).toBe('');
  });

  it('stands first in the row of the settings, which grows a column class for it', () => {
    mount();
    expect(container.querySelector('.vc-render')!.classList.contains('has-index')).toBe(true);
    expect(container.querySelector('.vc-render')!.firstElementChild).toBe(field());
  });

  it.each([
    ['an empty list (the DEM)', []],
    ['no field (a backend before NM4-14a)', null],
  ])('is not there for a dataset with %s', (_, presets) => {
    mount(presets);
    expect(field()).toBeNull();
    expect(container.querySelector('.vc-render')!.classList.contains('has-index')).toBe(false);
    expect(container.textContent).not.toContain('Index');
  });

  it('says what an index is in the tooltip: title and formula; and what the dropdown is while none is chosen', () => {
    mount();
    expect(field()!.title).toContain('Quick calculation');
    expect(field()!.title).toContain('from zoom 8');
    expect(field()!.title).toContain('start a job in Processing');
    expect([...select().options].find((o) => o.value === 'NDVI')!.title).toBe('Normalized Difference Vegetation Index: (N - R)/(N + R). Formula: Awesome Spectral Indices.');
    choose('NDVI');
    expect(field()!.title).toBe('Normalized Difference Vegetation Index: (N - R)/(N + R). Formula: Awesome Spectral Indices.');
    expect([...select().options].find((o) => o.value === 'NDWI')!.title).toContain('(McFeeters 1996)');
  });

  it('draws the choice once "Apply" is pressed, not before (Otto, 1.11.2026): the choice is in the fields, "Apply" opens', () => {
    mount();
    const button = container.querySelector('.vc-apply') as HTMLButtonElement;
    expect(button.getAttribute('aria-disabled')).toBe('true');
    choose('NDWI');
    expect(select().value).toBe('NDWI');
    expect(useAppStore.getState().appliedRender).toEqual({ rescale: '0,3000' });
    expect(button.getAttribute('aria-disabled')).toBeNull();
    apply();
    expect(useAppStore.getState().appliedRender).toEqual({ index: 'NDWI', colormapName: 'rdbu', rescale: '-1,1' });
    expect(button.getAttribute('aria-disabled')).toBe('true');
    choose('');
    expect(useAppStore.getState().appliedRender.index).toBe('NDWI');
    apply();
    expect(useAppStore.getState().appliedRender).toEqual({ rescale: '0,3000' });
    expect(select().value).toBe('');
  });

  it('opens "Apply" for an index of the range and colormap the map shows already: NDVI after EVI', () => {
    mount(SENTINEL_2_PRESETS, { appliedRender: { index: 'EVI', colormapName: 'rdylgn', rescale: '-1,1' }, pendingColormapName: 'rdylgn', pendingVmin: '-1', pendingVmax: '1' });
    const button = container.querySelector('.vc-apply') as HTMLButtonElement;
    expect(button.getAttribute('aria-disabled')).toBe('true');
    choose('NDVI');
    expect(button.getAttribute('aria-disabled')).toBeNull();
  });

  it('shows the colormap and the range of the preset in the fields, and a colormap to choose where the dataset draws RGB', () => {
    mount();
    expect([...colormapSelect().options].map((o) => o.textContent)).toEqual(['RGB']);
    choose('NDWI');
    expect(colormapSelect().value).toBe('rdbu');
    expect([...colormapSelect().options].map((o) => o.value)).toEqual(['', ...COLORMAPS]);
    expect(COLORMAPS).toContain('rdbu');
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
    act(() => useAppStore.getState().applyRender());
    act(() => useAppStore.getState().stepImage(1));
    act(() => useAppStore.getState().chooseViewIndex('EVI'));
    act(() => useAppStore.getState().applyRender());
    expect(useAppStore.getState().appliedRender).toMatchObject({ index: 'EVI', colormapName: 'rdylgn', rescale: '-1,1' });
    expect(locked()).toBe(false);
  });

  it('is locked again once every image shows it, and for any other of the three the moment it is chosen', () => {
    twoImages();
    act(() => useAppStore.getState().chooseViewIndex('NDVI'));
    act(() => useAppStore.getState().saveViewLook());
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
    expect(select().value).toBe('NDVI'); // the choice stays
  });

  it('is gone once the map is zoomed in, and comes back when it is zoomed out again', () => {
    const render = { index: 'NDVI', colormapName: 'rdylgn', rescale: '-1,1' };
    mount(SENTINEL_2_PRESETS, { mapZoom: 5, appliedRender: render });
    act(() => useAppStore.setState({ mapZoom: 9 }));
    none();
    act(() => useAppStore.setState({ mapZoom: 4 }));
    expect(note()!.textContent).toBe('Zoom in to compute NDVI');
  });

  it('names the index being chosen, and is there the moment it is chosen out of reach', () => {
    mount(SENTINEL_2_PRESETS, { mapZoom: 5 });
    none();
    choose('NDWI');
    none(); // not drawn yet, so nothing to say
    apply();
    expect(note()!.textContent).toBe('Zoom in to compute NDWI');
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
    expect(select().value).toBe('EVI');
  });

  it('is one short line, no more than a sentence', () => {
    mount(SENTINEL_2_PRESETS, { mapZoom: 5, appliedRender: { index: 'NDVI', colormapName: 'rdylgn', rescale: '-1,1' } });
    expect(note()!.textContent!.length).toBeLessThan(40);
  });
});

describe('the layout (the CSS the view is made with)', () => {
  it('gives the dropdown, colormap, vmin and vmax two columns each and the buttons four, and the narrow window two columns for each of the four', () => {
    expect(CSS).toMatch(/\.scene-view \.vc-render\.has-index > :nth-child\(1\),[\s\S]*?:nth-child\(4\) \{\s*grid-column: span 2;/u);
    expect(CSS).toMatch(/\.scene-view \.vc-render\.has-index > :nth-child\(5\) \{\s*grid-column: span 4;/u);
    expect(CSS).toMatch(/\.app\[data-theme='normal'\] \.scene-view \.vc-note \{\s*color: #8a5a00;/u);
    expect(CSS).toMatch(/@media \(max-width: 599px\) \{[\s\S]*?\.vc-render\.has-index > :nth-child\(n \+ 1\):nth-child\(-n \+ 4\) \{\s*grid-column: span 2;/u);
  });
});
