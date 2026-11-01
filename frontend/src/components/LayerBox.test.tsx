// @vitest-environment jsdom
//
// NM4-65 (Otto, 1.11.2026): "Verschiedene Layer haben verschiedene Boxen. Das darf nicht sein." A layer opened from the layer
// manager has the box of every layer — its name (with the date), the red x, the fields, "Apply" and "Apply to all" in one row,
// as before — and no second row of buttons (pin, process, change image, clear) and no further line. A view that is still open from the search keeps
// all of it, also once its image is pinned.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from '../datasets';
import type { MapLayer } from '../layers';
import { useAppStore } from '../store';
import type { Collection, DownloadedInfo, StacItem } from '../types';
import ViewerControls from './ViewerControls';

vi.mock('./MapView', () => ({ default: () => null }));

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const collection = {
  id: 'optical',
  title: 'Optical',
  'earthx:format': 'cog',
  'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
  'earthx:default_render': { title: 'Colour', assets: ['band'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
} as unknown as Collection;
const info: DownloadedInfo = { datasetId: 'optical', tileUrl: '/collections/optical/items/s0/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=band', bounds: [0, 0, 1, 1], asset: 'band', minZoom: 8, maxZoom: 14 };
const scene: StacItem = { id: 's0', collection: 'optical', bbox: [0, 0, 1, 1], properties: { datetime: '2026-07-01T10:00:00Z' }, assets: {} };

const layer = (): MapLayer => ({
  id: 'L1',
  name: 'Optical · crop',
  date: '2026-07-01',
  visible: true,
  opacity: 0.6,
  overlays: [],
  restore: {
    focusMode: true,
    downloaded: { s0: info },
    appliedRender: { rescale: '0,3000' },
    activeGroupIndex: 0,
    selectedIds: ['s0'],
    itemIds: ['s0'],
    groupItemIds: [['s0']],
    aoi: null,
    cropToAoi: false,
    datasetId: 'optical',
  },
});

let container: HTMLDivElement;
let root: Root;
const state = () => useAppStore.getState();

function mount(viewOfLayer: boolean, layers: MapLayer[] = [layer()]) {
  act(() => {
    useAppStore.setState({
      datasets: datasetsFrom([collection]),
      datasetId: 'optical',
      items: [scene],
      groups: [{ key: ['a'], label: 'a', items: [scene] }],
      selectedIds: [],
      downloaded: { s0: info },
      focusMode: true,
      cropToAoi: false,
      showDownloaded: true,
      shownImage: null,
      viewLooks: {},
      savedLooks: {},
      appliedRender: { rescale: '0,3000' },
      pendingColormapName: '',
      pendingVmin: '0',
      pendingVmax: '3000',
      pendingIndex: '',
      layers,
      viewLayerId: 'L1',
      viewOfLayer,
      mosaics: {},
      focusLoading: false,
      pinLoading: false,
      dock: null,
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

const labels = () => [...container.querySelectorAll('.vc-field > span')].map((s) => s.textContent);
const buttons = () => [...container.querySelectorAll('.vc-buttons button')].map((b) => b.textContent?.trim());

describe('a layer opened from the layer manager', () => {
  beforeEach(() => mount(true));

  it('has no row of buttons: no pinning, no processing, no "Change image", no "Clear"', () => {
    expect(container.querySelector('.vc-actions')).toBeNull();
    const text = container.textContent!;
    for (const gone of ['Add to layers', 'Add all to layers', 'Process', 'Change image', 'Clear']) expect(text, gone).not.toContain(gone);
  });

  it('has the head of every layer: its name with the date, in the style of a title, and the red x', () => {
    expect(container.querySelector('.vc-title')!.textContent).toBe('OPTICAL · CROP · 2026-07-01');
    expect(container.querySelector('.vc-title')!.getAttribute('title')).toBe('Optical · crop · 2026-07-01');
    expect(container.querySelectorAll('.vc-head .close-x')).toHaveLength(1);
    expect(container.querySelector('.vc-head .close-x')!.getAttribute('title')).toBe('Close');
    // No stepper, no dataset box, no eye of the view: the layer has its own eye in the manager.
    expect(container.querySelector('.vc-stepper, .vc-dataset, .vc-eye')).toBeNull();
  });

  // Otto, 1.11.2026 (NM4-54 part 5): the box of a layer of scenes is the box of a result: the fields and the buttons in one row, and
  // the opacity of the layer in the row under them.
  it('has the fields and the buttons of the settings of any layer in one row, and the opacity under them', () => {
    expect(labels()).toEqual(['vmin', 'vmax', 'Colormap', 'Opacity']);
    expect(buttons()).toEqual(['auto-scale', 'Apply', 'Save']);
    const box = container.querySelector('.scene-view')!;
    expect([...box.children].map((c) => c.className.split(' ')[0])).toEqual(['vc-head', 'vc-render', 'vc-opacity']);
    expect(container.querySelectorAll('.vc-opacity input[type="range"]')).toHaveLength(1);
  });

  it('changes the opacity of the layer from its box', () => {
    const slider = container.querySelector<HTMLInputElement>('.vc-opacity input[type="range"]')!;
    act(() => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!.call(slider, '0.5');
      slider.dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(state().layers[0].opacity).toBe(0.5);
  });

  it('closes with the x: the view goes, the layer stays', () => {
    act(() => container.querySelector<HTMLButtonElement>('.vc-head .close-x')!.click());
    expect(state().focusMode).toBe(false);
    expect(state().layers.map((l) => l.id)).toEqual(['L1']);
  });

  it('is the same box for a layer that is a crop and for one that is not', () => {
    const crop = layer();
    crop.restore = { ...crop.restore, cropToAoi: true, aoi: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] } };
    act(() => useAppStore.setState({ cropToAoi: true, viewAoi: crop.restore.aoi, layers: [crop] }));
    expect(container.querySelector('.vc-actions')).toBeNull();
    expect(labels()).toEqual(['vmin', 'vmax', 'Colormap', 'Opacity']);
    expect(buttons()).toEqual(['auto-scale', 'Apply', 'Save']);
  });
});

describe('a view that is still open from the search', () => {
  it('keeps all of it with no layer, and with its image pinned', () => {
    mount(false, []);
    expect(container.querySelector('.vc-actions')).not.toBeNull();
    expect(container.querySelectorAll('.vc-actions > *').length).toBeGreaterThanOrEqual(4);
    expect(container.querySelector('.vc-stepper')).not.toBeNull();
    mount(false);
    expect(container.querySelector('.vc-actions')).not.toBeNull();
    expect(container.textContent).toContain('Add to layers');
    expect(container.querySelector('.vc-head .close-x')).toBeNull();
    expect(container.textContent).toContain('Clear');
    expect(container.querySelector('.vc-title')!.textContent).not.toContain('2026-07-01 ·');
  });
});

// Otto, 1.11.2026: "es sollte auch die Box der Layer verschwinden, wenn ich wieder ein Result anklicke und die Box der Results
// erscheint".
describe('a click on a search result while a layer is open from the layer manager', () => {
  const item2: StacItem = { ...scene, id: 's9' };

  it('closes the box of the layer, so that the box of the results takes its place; the layer stays', () => {
    mount(true);
    act(() => useAppStore.setState({ items: [scene, item2], groups: [{ key: ['a'], label: 'a', items: [scene, item2] }] }));
    expect(state().focusMode).toBe(true);
    act(() => state().toggleSelected('s9'));
    expect(state().selectedIds).toEqual(['s9']);
    expect(state().focusMode).toBe(false);
    expect(state().viewOfLayer).toBe(false);
    expect(state().viewLayerId).toBeNull();
    // `App` shows the box of a view only while `focusMode` holds.
    expect(state().layers.map((l) => l.id)).toEqual(['L1']);
  });

  it('does so for "Select all" and a whole group too', () => {
    mount(true);
    act(() => useAppStore.setState({ items: [scene, item2], groups: [{ key: ['a'], label: 'a', items: [scene, item2] }], activeGroupIndex: 0 }));
    act(() => state().selectAllInActiveGroup());
    expect(state().focusMode).toBe(false);
  });

  it('does not for taking a tick off: nothing was clicked that the results show', () => {
    mount(true);
    act(() => useAppStore.setState({ items: [scene, item2], selectedIds: ['s9'] }));
    act(() => state().toggleSelected('s9'));
    expect(state().focusMode).toBe(true);
  });

  it('leaves a view that is still open from the search as it is, with the tick beside it', () => {
    mount(false);
    act(() => useAppStore.setState({ items: [scene, item2], groups: [{ key: ['a'], label: 'a', items: [scene, item2] }] }));
    act(() => state().toggleSelected('s9'));
    expect(state().focusMode).toBe(true);
    expect(container.querySelector('.scene-view .vc-actions')).not.toBeNull();
  });
});
