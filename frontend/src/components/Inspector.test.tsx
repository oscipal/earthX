// @vitest-environment jsdom
//
// The settings bar (UI-03a, Otto, 2.11.2026): one bar for the view of the search, the pinned view and the settings of a result layer, the same
// places for all three, the content swapped without closing the bar, the red x (and "Clear") to close it and Esc closing nothing, what
// does not apply locked with its reason, and out of the way of the processing panel without losing what was typed.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from '../App';
import { datasetsFrom } from '../datasets';
import { DRAW_AOI_TO_CROP } from '../download';
import { inspectorKindOf } from '../inspectorKind';
import type { MapLayer } from '../layers';
import { RGB } from '../processingBands';
import { resetJobs, useProcessingStore } from '../processingStore';
import { NOTHING_TO_SAVE } from '../render';
import { useAppStore } from '../store';
import type { Collection, DownloadedInfo, StacItem } from '../types';
import Inspector from './Inspector';
import LayerManager from './LayerManager';

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
  'earthx:source': { asset_hosts: ['data.test'] },
} as unknown as Collection;
const info = (id: string): DownloadedInfo => ({ datasetId: 'optical', tileUrl: `/collections/optical/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=band`, bounds: [0, 0, 1, 1], asset: 'band', minZoom: 8, maxZoom: 14 });
const scene = (id: string, day: string): StacItem => ({ id, collection: 'optical', bbox: [0, 0, 1, 1], properties: { datetime: `${day}T10:00:00Z` }, assets: { band: { href: `https://data.test/${id}.tif` } } });
const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]] };

const pinned = (): MapLayer => ({
  id: 'L1',
  name: 'Optical · crop',
  date: '2026-07-01',
  visible: true,
  opacity: 0.6,
  overlays: [],
  restore: { focusMode: true, downloaded: { s0: info('s0') }, appliedRender: { rescale: '0,3000' }, activeGroupIndex: 0, selectedIds: ['s0'], itemIds: ['s0'], groupItemIds: [['s0']], aoi: null, cropToAoi: false, datasetId: 'optical' },
});

const RESULT_BANDS = [
  { name: 'red', stats: null },
  { name: 'green', stats: null },
  { name: 'blue', stats: null },
];
const result = (id: string, patch: Partial<NonNullable<MapLayer['result']>> = {}): MapLayer => ({
  id,
  name: `Result ${id}`,
  visible: true,
  opacity: 1,
  derived: 'result',
  overlays: [{ kind: 'raster', tileUrl: '/results/AbCdEfGhIjKlMnOpQrSt_-/tiles/{z}/{x}/{y}?colormap_name=viridis&rescale=0%2C1', bounds: [10, 50, 11, 51], minZoom: 0, maxZoom: 14 }],
  result: { jobID: 'AbCdEfGhIjKlMnOpQrSt_-', expires: new Date(Date.now() + 86_400_000).toISOString(), gsd: 10, resampled: null, expired: false, dataType: 'float32', stats: null, ...patch },
  restore: { datasetId: null, itemIds: [] } as never,
});

let container: HTMLDivElement;
let root: Root;
const state = () => useAppStore.getState();
const aside = () => container.querySelector<HTMLElement>('aside.inspector');

// The view of the search: two scenes of different days, so there is a step to take; or one.
function openView(over: Partial<ReturnType<typeof state>> = {}) {
  act(() => {
    useAppStore.setState({
      datasets: datasetsFrom([collection]),
      datasetId: 'optical',
      items: [scene('s0', '2026-07-01'), scene('s1', '2026-07-02')],
      groups: [
        { key: ['a'], label: 'Day 1', items: [scene('s0', '2026-07-01')] },
        { key: ['b'], label: 'Day 2', items: [scene('s1', '2026-07-02')] },
      ],
      sections: [],
      openSectionId: null,
      selectedIds: [],
      downloaded: { s0: info('s0'), s1: info('s1') },
      shownImage: null,
      focusMode: true,
      cropToAoi: true,
      showDownloaded: true,
      viewOfLayer: false,
      viewLayerId: null,
      resultViewLayerId: null,
      layers: [],
      aoi: AOI,
      viewAoi: AOI,
      appliedRender: { rescale: '0,3000' },
      pendingColormapName: '',
      pendingVmin: '0',
      pendingVmax: '3000',
      pendingIndex: '',
      mosaics: {},
      focusLoading: false,
      pinLoading: false,
      dock: null,
      error: null,
      downloadSelection: false,
      downloadView: null,
      ...over,
    });
  });
}

const openPinnedView = () => openView({ cropToAoi: false, viewAoi: null, viewOfLayer: true, viewLayerId: 'L1', layers: [pinned()], downloaded: { s0: info('s0') }, items: [scene('s0', '2026-07-01')], groups: [{ key: ['a'], label: 'Day 1', items: [scene('s0', '2026-07-01')] }] });
const openResult = (layers = [result('R1'), result('R2')], id = 'R1') => {
  act(() => useAppStore.setState({ focusMode: false, viewOfLayer: false, viewLayerId: null, layers, resultViewLayerId: id, dock: null, error: null }));
};

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 404 })));
  resetJobs();
  useProcessingStore.setState({ open: false, jobs: [] });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  resetJobs();
  vi.unstubAllGlobals();
  useAppStore.setState({ focusMode: false, viewOfLayer: false, viewLayerId: null, resultViewLayerId: null, layers: [], downloaded: {}, downloadView: null, downloadSelection: false });
});

const click = (el: Element | null | undefined) => {
  if (!el) throw new Error(`nothing to click in ${container.textContent}`);
  act(() => el.dispatchEvent(new MouseEvent('click', { bubbles: true })));
};
const key = (target: EventTarget, name: string) => act(() => void target.dispatchEvent(new KeyboardEvent('keydown', { key: name, bubbles: true, cancelable: true })));
const type = (input: HTMLInputElement, value: string) =>
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
const field = (name: string) => [...container.querySelectorAll<HTMLLabelElement>('.inspector label.vc-field')].find((l) => l.querySelector('span')?.textContent === name)!;
const button = (label: string) => [...container.querySelectorAll<HTMLButtonElement>('.inspector button')].find((b) => b.textContent?.trim() === label)!;
const labels = () => [...container.querySelectorAll('.inspector label.vc-field > span')].map((s) => s.textContent);
const headings = () => [...container.querySelectorAll('.inspector .insp-heading')].map((h) => h.textContent);

const KINDS: [string, () => void][] = [
  ['the view of the search', () => openView()],
  ['the pinned view', openPinnedView],
  ['the settings of a result', () => openResult()],
];

describe('the places', () => {
  it.each(KINDS)('is an aside "Settings" with the head, then "Display", then "Actions": %s', (_, open) => {
    act(() => root.render(<Inspector />));
    expect(aside()).toBeNull();
    open();
    expect(aside()!.getAttribute('aria-label')).toBe('Settings');
    expect(aside()!.classList.contains('panel')).toBe(true);
    // Row 1 of the head holds the title and the red x; row 2 is there whatever it holds.
    const head = aside()!.querySelector('.vc-head')!;
    expect(head.children).toHaveLength(2);
    expect(head.children[0].querySelector('.vc-title')).not.toBeNull();
    expect(head.children[0].querySelector('.close-x')).not.toBeNull();
    expect(head.children[1].classList.contains('insp-row2')).toBe(true);
    // The dataset here has neither presets nor a colour picture: "Quick processing" has nothing to offer and is not there (Otto,
    // 3.11.2026); a result never has it. With them it stands between the two (`ViewIndex.test.tsx`).
    expect(headings()).toEqual(['Display', 'Actions']);
  });

  it.each(KINDS)('has the same fields in the same order, the opacity under them and the buttons last: %s', (_, open) => {
    act(() => root.render(<Inspector />));
    open();
    expect(labels()).toEqual(['Band', 'vmin', 'vmax', 'Colormap', 'Opacity']);
    const order = [
      aside()!.querySelector('.vc-head')!,
      aside()!.querySelector('.insp-row2')!,
      ...[...container.querySelectorAll('.inspector .insp-heading')].slice(0, 1),
      field('Band'),
      field('vmin'),
      field('vmax'),
      field('Colormap'),
      field('Opacity'),
      aside()!.querySelector('.vc-buttons')!,
      ...[...container.querySelectorAll('.inspector .insp-heading')].slice(1),
    ];
    for (let i = 1; i < order.length; i += 1) {
      expect(order[i - 1].compareDocumentPosition(order[i]) & Node.DOCUMENT_POSITION_FOLLOWING, `place ${i}`).toBeTruthy();
    }
    expect([...aside()!.querySelector('.vc-buttons')!.children].map((b) => b.textContent)).toEqual(['auto-scale', 'Apply', expect.stringMatching(/^(Apply to all|Save)$/u)]);
  });

  it('puts the title, the mark, the eye and the x of the view of the search in row 1, and the dataset and the time step in row 2', () => {
    act(() => root.render(<Inspector />));
    openView();
    const [one, two] = [...aside()!.querySelector('.vc-head')!.children].map((row) => [...row.children].map((el) => el.className));
    expect(one).toEqual(['vc-title', 'pp-badge vc-temporary', 'vc-eye', 'close-x']);
    expect(two).toEqual(['vc-stepper']);
  });

  // Otto, 2.11.2026: no arrows beside the date where there is only one.
  it('puts the date of a layer in the place of the time step, without arrows, and no eye', () => {
    act(() => root.render(<Inspector />));
    openPinnedView();
    const row = aside()!.querySelector('.insp-row2')!;
    expect(row.querySelector('.vc-step-text')!.textContent).toBe('2026-07-01');
    expect(row.querySelectorAll('.vc-step')).toHaveLength(0);
    expect(aside()!.querySelector('.vc-eye, .vc-temporary')).toBeNull();
    openResult([result('R1', {}), result('R2')]);
    act(() => useAppStore.setState({ layers: [{ ...result('R1'), date: '2026-08-09' }, result('R2')] }));
    expect(aside()!.querySelector('.insp-row2 .vc-step-text')!.textContent).toBe('2026-08-09');
  });

  it('leaves the date empty for a layer without one, without arrows', () => {
    act(() => root.render(<Inspector />));
    openResult();
    expect(aside()!.querySelector('.insp-row2 .vc-step-text')!.textContent).toBe('');
    expect(aside()!.querySelectorAll('.insp-row2 .vc-step')).toHaveLength(0);
  });

  it('has "Display" with no capital letters of its own: the title is as written', () => {
    act(() => root.render(<Inspector />));
    openResult();
    expect(aside()!.querySelector('.vc-title')!.textContent).toBe('Result R1');
  });

  // Otto, 2.11.2026: in pairs, and no "Clear": the red x closes the view and drops it.
  it('has the actions of the search in pairs, the downloads of the shown image last, and no "Clear"', () => {
    act(() => root.render(<Inspector />));
    openView();
    expect([...aside()!.querySelectorAll('.vc-actions > *')].map((b) => b.textContent)).toEqual([
      '‹ Change image', '⚙ Process', '＋ Add to layers', '＋ Add all to layers', '⇩ Download crop', '⇩ Download full scene',
    ]);
    expect(aside()!.querySelector('.vc-head .close-x')!.getAttribute('title')).toBe('Close and drop this view');
  });

  // Otto, 2.11.2026: "Process", the download of the row of the layer manager, a copy as drawn now, and the bin.
  it('has the actions of a layer: process, download, a copy as it is drawn now, remove', () => {
    act(() => root.render(<Inspector />));
    openPinnedView();
    const actions = () => [...aside()!.querySelectorAll('.vc-actions > *')];
    expect(actions().map((b) => b.textContent || b.getAttribute('aria-label'))).toEqual(['⚙ Process', '⇩ Download', '＋ Add current view to layers', 'Remove layer']);
    expect(actions()[3].getAttribute('title')).toBe('Remove layer');
    openResult();
    expect(actions().map((b) => b.textContent || b.getAttribute('aria-label'))).toEqual(['⚙ Process', '⇩ Download', '＋ Add current view to layers', 'Remove layer']);
  });

  it('keeps the place of the download empty for a layer that offers none, and the other actions', () => {
    act(() => root.render(<Inspector />));
    openResult([result('R1', { expired: true })]);
    expect(headings()).toEqual(['Display', 'Actions']);
    expect([...aside()!.querySelectorAll('.vc-actions > *')].map((b) => b.textContent || b.getAttribute('aria-label'))).toEqual(['⚙ Process', null, '＋ Add current view to layers', 'Remove layer']);
  });
});

describe('the swap', () => {
  it('keeps the same element when the view gives way to a layer and a layer to another one, and swaps the content', () => {
    act(() => root.render(<Inspector />));
    openView();
    const bar = aside()!;
    expect(bar.querySelector('.vc-temporary')).not.toBeNull();
    openResult();
    expect(aside()).toBe(bar);
    expect(bar.querySelector('.result-controls')).not.toBeNull();
    expect(bar.querySelector('.vc-title')!.textContent).toBe('Result R1');
    act(() => state().selectLayer('R2'));
    expect(aside()).toBe(bar);
    expect(bar.querySelector('.vc-title')!.textContent).toBe('Result R2');
    openView();
    expect(aside()).toBe(bar);
    expect(bar.querySelector('.viewer-controls:not(.result-controls)')).not.toBeNull();
  });

  it('starts the fields of another layer over, and the old layer goes back to what was saved', () => {
    act(() => root.render(<Inspector />));
    openResult();
    act(() => state().setLayerOpacity('R1', 0.3));
    act(() => state().selectLayer('R2'));
    expect(state().layers.map((l) => l.opacity)).toEqual([1, 1]);
    expect(state().layers[0].saved).toBeUndefined();
  });
});

describe('closing', () => {
  it('closes the settings of a result with the x and puts back what was not saved', () => {
    act(() => root.render(<Inspector />));
    openResult();
    act(() => state().setLayerOpacity('R1', 0.2));
    click(aside()!.querySelector('.close-x'));
    expect(aside()).toBeNull();
    expect(state().resultViewLayerId).toBeNull();
    expect(state().layers[0].opacity).toBe(1);
  });

  it('keeps what was saved: the x after "Save"', () => {
    act(() => root.render(<Inspector />));
    openResult();
    act(() => state().setLayerOpacity('R1', 0.2));
    click(button('Save'));
    click(aside()!.querySelector('.close-x'));
    expect(aside()).toBeNull();
    expect(state().layers[0].opacity).toBe(0.2);
  });

  // Otto, 2.11.2026: Esc closes nothing. The bar of each kind closes with its red x or "✕ Clear" only, and nothing typed in it is lost.
  it.each([
    ['the settings of a result layer', () => openResult()],
    ['the pinned view', () => openPinnedView()],
    ['the view of the search', () => openView()],
  ])('stays open on Escape for %s, with what was changed in it', (_, openIt) => {
    act(() => root.render(<Inspector />));
    openIt();
    const kind = inspectorKindOf(state());
    type(field('vmin').querySelector('input')!, '7');
    for (const target of [document.body, aside()!.querySelector<HTMLElement>('.vc-title')!, field('vmin').querySelector('input')!, field('Opacity').querySelector('input')!]) {
      key(target, 'Escape');
      expect(aside(), target.tagName).not.toBeNull();
    }
    expect(inspectorKindOf(state())).toBe(kind);
    expect(field('vmin').querySelector('input')!.value).toBe('7');
  });

  it('closes the pinned view with the x, and the layer stays', () => {
    act(() => root.render(<Inspector />));
    openPinnedView();
    click(aside()!.querySelector('.close-x'));
    expect(aside()).toBeNull();
    expect(state().focusMode).toBe(false);
    expect(state().layers.map((l) => l.id)).toEqual(['L1']);
  });

  it('puts a pinned layer back as saved when the view closes without "Save"', () => {
    act(() => root.render(<Inspector />));
    openPinnedView();
    act(() => state().setLayerOpacity('L1', 0.1));
    expect(state().layers[0].saved).toBeDefined();
    click(aside()!.querySelector('.close-x'));
    expect(state().layers[0].opacity).toBe(0.6);
  });

  it('closes the view of the search with the x and drops it, as "Clear" did; the tick and the switch stay', () => {
    act(() => root.render(<Inspector />));
    openView({ selectedIds: ['s1'], resultsOnMap: false });
    click(aside()!.querySelector('.close-x'));
    expect(aside()).toBeNull();
    expect(state().focusMode).toBe(false);
    expect(state().downloaded).toEqual({});
    expect(state().selectedIds).toEqual(['s1']);
    expect(state().resultsOnMap).toBe(false);
  });

  it('gives the focus back to what had it when the bar opened, if that is still there, and nowhere else', () => {
    const opener = document.createElement('button');
    document.body.append(opener);
    act(() => root.render(<Inspector />));
    opener.focus();
    openResult();
    expect(document.activeElement).toBe(opener);
    (aside()!.querySelector('.close-x') as HTMLElement).focus();
    click(aside()!.querySelector('.close-x'));
    expect(document.activeElement).toBe(opener);
    // Opened from something that is gone by the time of closing.
    const gone = document.createElement('button');
    document.body.append(gone);
    gone.focus();
    openResult();
    gone.remove();
    click(aside()!.querySelector('.close-x'));
    expect(document.activeElement).toBe(document.body);
    opener.remove();
  });

  it('leaves the focus where it is when nothing outside the bar had it at the opening', () => {
    const other = document.createElement('input');
    document.body.append(other);
    act(() => root.render(<Inspector />));
    openResult();
    other.focus();
    click(aside()!.querySelector('.close-x'));
    // The opener was the body: nothing to give back.
    expect(document.activeElement).toBe(other);
    other.remove();
  });
});

describe('what does not apply is locked, with its reason', () => {
  // Otto, 2.11.2026 (replaces the locked opacity of the same day): the view of the search has an opacity of its own.
  it('lets the opacity of the view of the search be set, 1 for every new view, and gives it to the layer it is pinned to', () => {
    act(() => root.render(<Inspector />));
    openView();
    const slider = () => field('Opacity').querySelector('input')!;
    expect(slider().disabled).toBe(false);
    expect(slider().value).toBe('1');
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(slider(), '0.4');
      slider().dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(state().viewOpacity).toBe(0.4);
    expect(slider().title).toBe('Opacity 40%');
    // The eye of the view is there and works too.
    click(aside()!.querySelector('.vc-eye'));
    expect(state().showDownloaded).toBe(false);
    click(aside()!.querySelector('.vc-head .close-x'));
    expect(state().viewOpacity).toBe(1);
  });

  it('gives its opacity to the layer "Add to layers" makes, and keeps it between 0 and 1', async () => {
    act(() => root.render(<Inspector />));
    openView();
    act(() => state().setViewOpacity(0.35));
    click(button('＋ Add to layers'));
    await act(async () => {
      for (let i = 0; i < 10; i++) await Promise.resolve();
    });
    expect(state().layers[0].opacity).toBe(0.35);
    act(() => state().setViewOpacity(3));
    expect(state().viewOpacity).toBe(1);
    act(() => state().setViewOpacity(-1));
    expect(state().viewOpacity).toBe(0);
    act(() => state().setViewOpacity(Number.NaN));
    expect(state().viewOpacity).toBe(1);
  });

  it('sets the opacity of the pinned layer that draws the view in its place, where there is one', () => {
    act(() => root.render(<Inspector />));
    openView({ cropToAoi: false, viewAoi: null, viewOfLayer: false, viewLayerId: 'L1', layers: [pinned()], appliedRender: { rescale: '0,3000' }, downloaded: { s0: info('s0') }, items: [scene('s0', '2026-07-01')], groups: [{ key: ['a'], label: 'Day 1', items: [scene('s0', '2026-07-01')] }] });
    const slider = field('Opacity').querySelector('input')!;
    expect(slider.disabled).toBe(false);
    expect(slider.value).toBe('0.6');
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(slider, '0.2');
      slider.dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(state().layers[0].opacity).toBe(0.2);
    expect(state().viewOpacity).toBe(1);
  });

  it('locks the colormap of a picture of three bands as "— none —", and says why', () => {
    act(() => root.render(<Inspector />));
    openResult([result('R1', { bands: RESULT_BANDS, band: RGB, colour: { red: 0, green: 1, blue: 2 } } as never)]);
    const select = field('Colormap').querySelector('select')!;
    expect(select.disabled).toBe(true);
    expect(select.selectedOptions[0].textContent).toBe('— none —');
    expect(field('Colormap').title).toBe('True colour: three bands, no colormap');
  });

  it('has no arrows at a layer, which holds one image (Otto, 2.11.2026)', () => {
    act(() => root.render(<Inspector />));
    for (const open of [openPinnedView, () => openResult()]) {
      open();
      expect(aside()!.querySelectorAll('.vc-step')).toHaveLength(0);
      expect(aside()!.querySelector('.vc-stepper')).not.toBeNull();
    }
  });

  it('keeps the band of a picture of one band in its place, locked: "This picture has one band"', () => {
    act(() => root.render(<Inspector />));
    for (const open of [() => openView(), () => openResult([result('R1', { bands: [RESULT_BANDS[0]] })])]) {
      open();
      expect(field('Band').querySelector('select')!.disabled).toBe(true);
      expect(field('Band').title).toBe('This picture has one band');
      expect(labels().slice(0, 2)).toEqual(['Band', 'vmin']);
    }
  });

  it('frees the band of a result of several bands', () => {
    act(() => root.render(<Inspector />));
    openResult([result('R1', { bands: RESULT_BANDS })]);
    expect(field('Band').querySelector('select')!.disabled).toBe(false);
  });

  it('locks "Add all to layers" for one image, with the reason, and frees it for several', () => {
    act(() => root.render(<Inspector />));
    openView({ downloaded: { s0: info('s0') } });
    expect(button('＋ Add all to layers').disabled).toBe(true);
    expect(button('＋ Add all to layers').title).toBe('There is only one image');
    openView();
    expect(button('＋ Add all to layers').disabled).toBe(false);
  });

  it('locks "Apply" and "Save" with the reason while there is nothing to do', () => {
    act(() => root.render(<Inspector />));
    openResult();
    expect(button('Save').getAttribute('aria-disabled')).toBe('true');
    expect(button('Save').title).toBe(NOTHING_TO_SAVE);
  });

  it('locks the downloads of the view without an AOI and without a COG dataset, with the reason', () => {
    act(() => root.render(<Inspector />));
    openView({ aoi: null });
    expect(button('⇩ Download crop').disabled).toBe(true);
    expect(button('⇩ Download crop').title).toBe(DRAW_AOI_TO_CROP);
    act(() => useAppStore.setState({ datasets: datasetsFrom([{ ...collection, 'earthx:format': 'zarr' } as Collection]) }));
    expect(button('⇩ Download full scene').disabled).toBe(true);
    expect(button('⇩ Download full scene').title).toMatch(/no single original file per scene/);
  });
});

describe('the downloads of the view', () => {
  it('open the dialog for the scenes of the shown image, not for the ticks', () => {
    act(() => root.render(<Inspector />));
    openView({ selectedIds: ['s1'] });
    click(button('⇩ Download crop'));
    expect(state().downloadSelection).toBe(true);
    expect(state().downloadView?.items.map((it) => it.id)).toEqual(['s0']);
    act(() => state().closeDownloadDialog());
    click(button('⇩ Download full scene'));
    expect(state().downloadPasses?.map((pass) => pass.items.map((it) => it.id))).toEqual([['s0']]);
  });

  it('follow the step: the next image is the one downloaded', () => {
    act(() => root.render(<Inspector />));
    openView();
    click(aside()!.querySelector('[aria-label="Next image"]'));
    click(button('⇩ Download crop'));
    expect(state().downloadView?.items.map((it) => it.id)).toEqual(['s1']);
  });
});

describe('the download of a layer', () => {
  it('is the block of the row of the layer manager: the same link, the same tooltip', () => {
    act(() => root.render(<><LayerManager /><Inspector /></>));
    openResult();
    const row = container.querySelector<HTMLAnchorElement>('.layer-row [data-col="download"]')!;
    const own = aside()!.querySelector<HTMLAnchorElement>('.vc-actions a')!;
    expect(own.getAttribute('href')).toBe(row.getAttribute('href'));
    expect(own.title).toBe(row.title);
    expect(own.getAttribute('aria-label')).toBe(row.getAttribute('aria-label'));
    expect(row.className).toBe('lm-btn');
    expect(row.textContent).toBe('⇩');
    expect(own.className).toBe('ghost-btn');
  });

  it('answers like its row: the originals of a COG layer, and locked where a source with no file needs an AOI', () => {
    act(() => root.render(<><LayerManager /><Inspector /></>));
    openPinnedView();
    const row = () => container.querySelector<HTMLButtonElement>('.layer-row [data-col="download"]')!;
    expect(button('⇩ Download').title).toBe(row().title);
    expect(button('⇩ Download').title).toBe('Download the original files, straight from the source');
    expect(button('⇩ Download').disabled).toBe(false);
    act(() => useAppStore.setState({ datasets: datasetsFrom([{ ...collection, 'earthx:format': 'zarr' } as Collection]) }));
    expect(button('⇩ Download').disabled).toBe(true);
    expect(row().disabled).toBe(true);
    expect(button('⇩ Download').title).toBe('Draw an AOI to download this layer');
    expect(button('⇩ Download').title).toBe(row().title);
  });
});

describe('the processing panel in the same column', () => {
  it('hides the bar and keeps it mounted: what was typed is still there when the panel closes', () => {
    act(() => root.render(<Inspector />));
    openResult();
    const bar = aside()!;
    type(field('vmax').querySelector('input')!, '0.5');
    act(() => useProcessingStore.setState({ open: true }));
    expect(aside()).toBe(bar);
    expect(bar.hidden).toBe(true);
    act(() => useProcessingStore.setState({ open: false }));
    expect(aside()).toBe(bar);
    expect(bar.hidden).toBe(false);
    expect(field('vmax').querySelector('input')!.value).toBe('0.5');
  });

  it('is hidden at once when the panel is already open as the bar opens, and shows when it closes', () => {
    act(() => root.render(<Inspector />));
    act(() => useProcessingStore.setState({ open: true }));
    openView();
    expect(aside()!.hidden).toBe(true);
    act(() => useProcessingStore.setState({ open: false }));
    expect(aside()!.hidden).toBe(false);
  });
});

describe('a layer that goes while its bar is open', () => {
  it('closes the bar of a result without an error', () => {
    act(() => root.render(<><LayerManager /><Inspector /></>));
    openResult();
    act(() => state().removeLayer('R1'));
    expect(aside()).toBeNull();
    expect(state().resultViewLayerId).toBeNull();
  });

  it('closes the bar of a result whose layer is gone by another way, also when the id stays set', () => {
    act(() => root.render(<Inspector />));
    openResult();
    act(() => useAppStore.setState({ layers: [] }));
    expect(aside()).toBeNull();
  });

  it('keeps the view of a pinned layer that is removed, as a temporary picture', () => {
    act(() => root.render(<><LayerManager /><Inspector /></>));
    openPinnedView();
    act(() => state().removeLayer('L1'));
    expect(aside()).not.toBeNull();
    expect(aside()!.querySelector('.vc-temporary')).not.toBeNull();
  });
});

describe('a view without an image', () => {
  it('shows the bar with the fields and no step', () => {
    act(() => root.render(<Inspector />));
    openView({ downloaded: {}, items: [], groups: [] });
    expect(aside()).not.toBeNull();
    expect(aside()!.querySelector('.vc-stepper')).toBeNull();
    expect(button('＋ Add all to layers').disabled).toBe(true);
  });
});

describe('the sheet under 900 px', () => {
  it('has a grip that folds the bar to its head and back, with aria-expanded', () => {
    act(() => root.render(<Inspector />));
    openResult();
    const grip = aside()!.querySelector<HTMLButtonElement>('.pp-grip')!;
    expect(grip.getAttribute('aria-expanded')).toBe('true');
    click(grip);
    expect(grip.getAttribute('aria-expanded')).toBe('false');
    expect(aside()!.classList.contains('folded')).toBe(true);
    // The title and the x stay in the DOM and in the head.
    expect(aside()!.querySelector('.vc-head .vc-title')).not.toBeNull();
    expect(aside()!.querySelector('.vc-head .close-x')).not.toBeNull();
    click(grip);
    expect(aside()!.classList.contains('folded')).toBe(false);
  });

  it('opens unfolded again after it was closed folded', () => {
    act(() => root.render(<Inspector />));
    openResult();
    click(aside()!.querySelector('.pp-grip'));
    click(aside()!.querySelector('.close-x'));
    openResult();
    expect(aside()!.classList.contains('folded')).toBe(false);
  });

  it('tells the page how high it is where ResizeObserver exists, and works without it', () => {
    class Observer {
      static last: Observer | null = null;
      callback: () => void;
      constructor(callback: () => void) {
        this.callback = callback;
        Observer.last = this;
      }
      observe = vi.fn();
      disconnect = vi.fn();
    }
    vi.stubGlobal('ResizeObserver', Observer);
    act(() => root.render(<App />));
    openResult();
    const app = container.querySelector<HTMLElement>('.app')!;
    expect(app.style.getPropertyValue('--inspector-sheet-height')).toBe('0px');
    vi.spyOn(aside()!, 'getBoundingClientRect').mockReturnValue({ height: 321 } as DOMRect);
    act(() => Observer.last!.callback());
    expect(app.style.getPropertyValue('--inspector-sheet-height')).toBe('321px');
    act(() => state().closeResultView());
    expect(app.style.getPropertyValue('--inspector-sheet-height')).toBe('');
  });
});

describe('in the page', () => {
  it('deletes the stored place of the old floating window of the jobs when it starts', () => {
    localStorage.setItem('earthx.jobsWindow', '{"x":1,"y":1,"width":480,"height":400}');
    act(() => root.render(<App />));
    expect(localStorage.getItem('earthx.jobsWindow')).toBeNull();
  });

  it('marks the app while the bar shows, so that the bands and the map controls make room, and not while the processing panel has the column', () => {
    act(() => root.render(<App />));
    const app = () => container.querySelector('.app')!;
    expect(app().classList.contains('has-inspector')).toBe(false);
    openView();
    expect(app().classList.contains('has-inspector')).toBe(true);
    act(() => useProcessingStore.setState({ open: true }));
    expect(app().classList.contains('has-inspector')).toBe(false);
    // The wide sheet has its own mark, for the map controls and the status line (UI-03b).
    expect(app().classList.contains('has-sheet')).toBe(true);
    expect(container.querySelector('.processing-sheet')).not.toBeNull();
    expect(container.querySelector('.overlay.bottom')!.classList.contains('beside-sheet')).toBe(true);
    // The buttons at the top stand left of the panel, which reaches the top (Otto, 2.11.2026).
    expect(container.querySelector('.overlay.top-right')!.classList.contains('beside-sheet')).toBe(true);
    act(() => useProcessingStore.setState({ open: false }));
    expect(app().classList.contains('has-inspector')).toBe(true);
    expect(app().classList.contains('has-sheet')).toBe(false);
    act(() => state().exitFocus());
    expect(app().classList.contains('has-inspector')).toBe(false);
  });

  it('keeps the bar out of the stack at the bottom and of the bands that can be moved', () => {
    act(() => root.render(<App />));
    openView();
    expect(container.querySelector('.overlay.bottom .inspector')).toBeNull();
    expect(aside()!.closest('.draggable')).toBeNull();
  });
});

// Otto, 2.11.2026: the actions of a layer in the settings bar, and its name renamed in the head.
describe('the actions of a layer', () => {
  const actionButton = (label: string) => [...container.querySelectorAll<HTMLButtonElement>('.inspector .vc-actions button')].find((b) => (b.textContent || b.getAttribute('aria-label')) === label)!;
  const nameField = () => container.querySelector<HTMLInputElement>('.inspector .vc-head input[aria-label="Layer name"]');
  const rename = (text: string) => {
    type(nameField()!, text);
    key(nameField()!, 'Enter');
  };

  it('renames the layer from the head, by its title or by the pencil, and the layer manager says the new name', () => {
    act(() => root.render(<><LayerManager /><Inspector /></>));
    openPinnedView();
    expect(nameField()).toBeNull();
    click(container.querySelector('.inspector .vc-title-btn'));
    expect(nameField()!.value).toBe('Optical · crop');
    rename('River bend');
    expect(state().layers[0].name).toBe('River bend');
    expect(container.querySelector('.inspector .vc-title')!.textContent).toBe('River bend · 2026-07-01');
    expect(container.querySelector('.layer-row .lm-name')!.textContent).toBe('River bend · 2026-07-01');
    click(container.querySelector('.inspector .vc-pencil'));
    expect(nameField()).not.toBeNull();
  });

  it('refuses an empty name: the layer keeps the one it had', () => {
    act(() => root.render(<Inspector />));
    openResult();
    click(container.querySelector('.inspector .vc-pencil'));
    rename('   ');
    expect(state().layers[0].name).toBe('Result R1');
    expect(state().renameLayer('R1', '')).toBe(false);
    // Counter-check: a name with text is taken, trimmed.
    expect(state().renameLayer('R1', '  Floods  ')).toBe(true);
    expect(state().layers[0].name).toBe('Floods');
  });

  it('has no rename in the view of the search, which is no layer', () => {
    act(() => root.render(<Inspector />));
    openView();
    expect(container.querySelector('.inspector .vc-pencil, .inspector .vc-title-btn')).toBeNull();
  });

  it('removes the layer by the bin, as the layer manager does: the view of a pinned layer stays as a temporary picture', () => {
    act(() => root.render(<Inspector />));
    openPinnedView();
    click(actionButton('Remove layer'));
    expect(state().layers).toEqual([]);
    expect(aside()!.querySelector('.vc-temporary')).not.toBeNull();
  });

  it('removes a result layer by the bin, and its settings close with it', () => {
    act(() => root.render(<Inspector />));
    openResult();
    click(actionButton('Remove layer'));
    expect(state().layers.map((l) => l.id)).toEqual(['R2']);
    expect(state().resultViewLayerId).toBeNull();
    expect(aside()).toBeNull();
  });

  it('adds a copy as it is drawn now, above the layer, which goes back to what it was saved with; the settings are the copy\'s', async () => {
    act(() => root.render(<Inspector />));
    openPinnedView();
    act(() => state().setPendingVmax('1000'));
    await act(async () => {
      actionButton('＋ Add current view to layers').click();
      await vi.waitFor(() => expect(state().layers).toHaveLength(2));
    });
    const [copy, original] = state().layers;
    expect(copy.name).toBe('Optical · crop (copy)');
    expect(copy.restore.appliedRender.rescale).toBe('0,1000');
    expect(copy.saved).toBeUndefined();
    // Counter-check: the layer it was made from is as it was saved.
    expect(original.id).toBe('L1');
    expect(original.restore.appliedRender.rescale).toBe('0,3000');
    expect(state().viewLayerId).toBe(copy.id);
  });

  it('adds a copy of a result layer drawn as it is now, and leaves the result layer as saved', async () => {
    act(() => root.render(<Inspector />));
    openResult([{ ...result('R1', { savedTileUrl: '/results/AbCdEfGhIjKlMnOpQrSt_-/tiles/{z}/{x}/{y}?colormap_name=viridis&rescale=0%2C5' }) }]);
    await act(async () => {
      actionButton('＋ Add current view to layers').click();
      await vi.waitFor(() => expect(state().layers).toHaveLength(2));
    });
    const [copy, original] = state().layers;
    expect(copy.result!.savedTileUrl).toBeUndefined();
    expect((copy.overlays[0] as { tileUrl: string }).tileUrl).toContain('rescale=0%2C1');
    expect((original.overlays[0] as { tileUrl: string }).tileUrl).toContain('rescale=0%2C5');
    expect(state().resultViewLayerId).toBe(copy.id);
  });

  it('has "Process" as the row of the layer manager has it: free or locked alike, with the same reason', () => {
    act(() => root.render(<><LayerManager /><Inspector /></>));
    const row = () => container.querySelector<HTMLButtonElement>('.layer-row [data-col="process"]')!;
    openPinnedView();
    expect([actionButton('⚙ Process').disabled, actionButton('⚙ Process').title]).toEqual([row().disabled, row().title]);
    expect(actionButton('⚙ Process').disabled).toBe(true);
    // A dataset that allows processing: both free.
    act(() => useAppStore.setState({ datasets: datasetsFrom([{ ...collection, 'earthx:license_flags': { tier: 'processing' } } as unknown as Collection]) }));
    expect([actionButton('⚙ Process').disabled, actionButton('⚙ Process').title]).toEqual([false, 'Process this layer']);
    expect([row().disabled, row().title]).toEqual([false, 'Process this layer']);
  });
});
