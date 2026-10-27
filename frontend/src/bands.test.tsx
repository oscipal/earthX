// @vitest-environment jsdom
//
// Otto, 27.10.2026 (zu #211): a band that was moved stays at its place on the screen, whether other bands appear,
// disappear or change their height, and no other band takes over its shift; bands that were not moved stack from the
// bottom edge as before, and every band stays completely inside the window.
//
// jsdom has no layout. The tests give the bottom stack (`.overlay.bottom`) the one the style sheet describes: a column
// that grows upwards from 20 px above the bottom edge of the window, a gap of 10 px, items centred, a left edge that
// moves when the dock opens, and the heights of the three kinds of band. The place of a band on the screen is then
// where this layout puts it, shifted by the `transform` and the `margin-top` the band sets on itself, so the tests ask
// for the position, not for how a band gets there. They run against the earlier ways of keeping a band's shift
// (per component, per band) and fail on the position.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';
import { useBandPositions } from './bandPositions';
import { datasetsFrom } from './datasets';
import { bboxToPolygon } from './geoUtils';
import { resetJobs, useProcessingStore } from './processingStore';
import { useAppStore } from './store';
import type { Collection, StacItem } from './types';

vi.mock('./components/MapView', () => ({ default: () => null }));

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const DATASET = 'optical';
const AOI = bboxToPolygon([10.1, 50.1, 10.2, 50.2]);
const COLLECTION = {
  id: DATASET,
  title: 'Optical imagery',
  'earthx:format': 'cog',
  'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
  'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
} as unknown as Collection;

const scene = (id: string, day: string): StacItem => {
  const bbox: [number, number, number, number] = [10, 50, 11, 51];
  return { id, collection: DATASET, bbox, geometry: bboxToPolygon(bbox), properties: { datetime: `${day}T10:00:00Z` }, assets: {} };
};
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
  if (url === '/stac/collections') return json({ collections: [COLLECTION] });
  if (url === '/stac/search' && init?.method === 'POST') {
    const features = [scene('a0', '2026-07-24'), scene('a1', '2026-07-24'), scene('b0', '2026-07-25')];
    return json({ features, numberReturned: features.length, links: [], numberMatched: 3 });
  }
  return json({ detail: 'not found' }, 404);
});

// --- the layout of the bottom stack ---------------------------------------------------------------------------------
const WINDOW = { width: 1280, height: 800 };
const BOTTOM_EDGE = 20;
const GAP = 10;
const STACK_WIDTH = 760;
const STACK_LEFT = { closed: 260, open: 430 }; // `left: calc((100% + var(--dock-offset)) / 2)` less half the width

let container: HTMLDivElement;
let root: Root;

const heightOf = (band: HTMLElement) => (band.querySelector('.scene-view') ? 168 : band.querySelector('.time-slider') ? 61 : 66);
const widthOf = (band: HTMLElement) => (band.classList.contains('fill') ? STACK_WIDTH : 300);
const number = (value: string) => parseFloat(value) || 0;

// Where the stack puts each band on its own (no transform), the margin of the band taken into account.
function flowPlaces(): Map<Element, { left: number; top: number }> {
  const stack = container.querySelector('.overlay.bottom');
  const bands = [...(stack?.children ?? [])] as HTMLElement[];
  const total = bands.reduce((sum, band) => sum + number(band.style.marginTop) + heightOf(band), 0) + GAP * Math.max(0, bands.length - 1);
  const left = container.querySelector('.app.dock-open') ? STACK_LEFT.open : STACK_LEFT.closed;
  const places = new Map<Element, { left: number; top: number }>();
  let top = WINDOW.height - BOTTOM_EDGE - total;
  for (const band of bands) {
    places.set(band, { left: left + (STACK_WIDTH - widthOf(band)) / 2, top: top + number(band.style.marginTop) });
    top += number(band.style.marginTop) + heightOf(band) + GAP;
  }
  return places;
}

function screenPlace(band: HTMLElement) {
  const flow = flowPlaces().get(band);
  const shift = /translate\((-?[\d.]+)px, (-?[\d.]+)px\)/u.exec(band.style.transform);
  return { left: (flow?.left ?? 0) + number(shift?.[1] ?? '0'), top: (flow?.top ?? 0) + number(shift?.[2] ?? '0') };
}

const originals = {
  rect: Element.prototype.getBoundingClientRect,
  height: Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight'),
  width: Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth'),
  style: window.getComputedStyle,
};

function installLayout() {
  Element.prototype.getBoundingClientRect = function (this: Element) {
    if (!this.classList.contains('draggable')) return originals.rect.call(this);
    const band = this as HTMLElement;
    const { left, top } = screenPlace(band);
    const [width, height] = [widthOf(band), heightOf(band)];
    return { left, top, x: left, y: top, width, height, right: left + width, bottom: top + height, toJSON: () => ({}) } as DOMRect;
  };
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, get(this: HTMLElement) { return this.classList.contains('draggable') ? heightOf(this) : 0; } });
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, get(this: HTMLElement) { return this.classList.contains('draggable') ? widthOf(this) : 0; } });
  window.getComputedStyle = ((el: Element, pseudo?: string | null) =>
    el.classList.contains('bottom') ? ({ rowGap: `${GAP}px` } as CSSStyleDeclaration) : originals.style(el, pseudo)) as typeof window.getComputedStyle;
  Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: WINDOW.width });
  Object.defineProperty(window, 'innerHeight', { configurable: true, writable: true, value: WINDOW.height });
}

function removeLayout() {
  Element.prototype.getBoundingClientRect = originals.rect;
  if (originals.height) Object.defineProperty(HTMLElement.prototype, 'offsetHeight', originals.height);
  if (originals.width) Object.defineProperty(HTMLElement.prototype, 'offsetWidth', originals.width);
  window.getComputedStyle = originals.style;
}

// --- the bands -------------------------------------------------------------------------------------------------------
const state = () => useAppStore.getState();
const flush = () => act(async () => { for (let i = 0; i < 40; i++) await Promise.resolve(); });
const click = (el: Element) => act(() => el.dispatchEvent(new MouseEvent('click', { bubbles: true })));

// The three bands by what is in them, not by an attribute of the band.
const selectionBar = () => container.querySelector('.download-bar')?.closest<HTMLElement>('.draggable') ?? null;
const view = () => container.querySelector('.scene-view')?.closest<HTMLElement>('.draggable') ?? null;
const timeline = () => container.querySelector('.time-slider')?.closest<HTMLElement>('.draggable') ?? null;
const placeOf = (find: () => HTMLElement | null) => {
  const band = find();
  if (!band) throw new Error('the band is not there');
  return screenPlace(band);
};

// What a user does: presses on the grip of the band, moves the pointer, lets go.
function dragBy(band: HTMLElement, dx: number, dy: number) {
  const { left, top } = screenPlace(band);
  const [x, y] = [left + 40, top + 3];
  act(() => band.querySelector('.drag-grip')?.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, clientX: x, clientY: y })));
  act(() => void window.dispatchEvent(new MouseEvent('pointermove', { clientX: x + dx, clientY: y + dy })));
  act(() => void window.dispatchEvent(new MouseEvent('pointerup')));
}

const changeImage = () => click([...container.querySelectorAll<HTMLButtonElement>('.scene-view button')].find((b) => b.textContent?.includes('Change image'))!);

beforeEach(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  resetJobs();
  useBandPositions.setState({ places: {} });
  installLayout();
  vi.stubGlobal('fetch', fetchMock);
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  act(() => root.render(<App />));
  await flush();
  useAppStore.setState({
    dock: null, datasets: datasetsFrom([COLLECTION]), selectedDatasetIds: [DATASET], datasetId: DATASET, aoi: AOI, dateFrom: '', dateTo: '',
    sections: [], openSectionId: null, items: [], groups: [], selectedIds: [], layers: [], searchContext: null, searching: false, loadingMore: false,
    focusMode: false, resultViewLayerId: null, searchCrops: [], error: null, notice: null, resultsOnMap: true,
  });
  useProcessingStore.setState({ open: false, jobs: [] });
  await act(() => state().runSearch());
  act(() => useAppStore.setState({ dock: null }));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  removeLayout();
  resetJobs();
  vi.unstubAllGlobals();
});

// A crop of a0 is open, a1 is ticked beside it (the bar of the selection shows), the dock is closed.
async function cropWithBarBeside() {
  act(() => state().toggleSelected('a0'));
  await act(() => state().enterFocus(true));
  act(() => state().toggleSelected('a1'));
  act(() => useAppStore.setState({ dock: null }));
  expect(selectionBar()).not.toBeNull();
  expect(view()).not.toBeNull();
}

describe('a band that was moved stays where it was put (Otto, 27.10.2026)', () => {
  it('"Change image" in the view, which makes room for the time line and opens the dock, leaves the bar of the selection where it was put', async () => {
    await cropWithBarBeside();
    dragBy(selectionBar()!, -80, -30);
    const put = placeOf(selectionBar as () => HTMLElement);
    expect(put).not.toEqual(flowPlaces().get(selectionBar()!));

    changeImage();
    await flush();
    expect(view()).toBeNull();
    expect(timeline()).not.toBeNull();
    expect(state().dock).toBe('results'); // the dock opened: the stack moved to the right
    expect(placeOf(selectionBar as () => HTMLElement)).toEqual(put);
  });

  it('a band moved in the view is not where the time line stands after "Change image": no band takes over its shift', async () => {
    act(() => state().toggleSelected('a0'));
    await act(() => state().enterFocus(true));
    act(() => useAppStore.setState({ dock: null }));
    dragBy(view()!, 120, -90);

    changeImage();
    await flush();
    expect(view()).toBeNull();
    // Not moved, the time line stands where the stack puts it: on the bottom edge of the window, nothing above.
    const bottom = placeOf(timeline as () => HTMLElement);
    expect(bottom.top).toBe(WINDOW.height - BOTTOM_EDGE - 61);
    expect(bottom.left).toBe(STACK_LEFT.open + (STACK_WIDTH - 300) / 2);
  });

  it('the band, back after it went, stands where it was left', async () => {
    act(() => state().toggleSelected('a0'));
    await flush();
    dragBy(selectionBar()!, -150, -200);
    const put = placeOf(selectionBar as () => HTMLElement);
    act(() => state().toggleSelected('a0')); // nothing ticked: the bar goes
    expect(selectionBar()).toBeNull();
    act(() => state().toggleSelected('b0'));
    expect(placeOf(selectionBar as () => HTMLElement)).toEqual(put);
  });

  it('stays when the band under it changes its height: a view (168 px) instead of the time line (61 px)', async () => {
    act(() => state().toggleSelected('a0'));
    await flush();
    dragBy(selectionBar()!, 0, -120);
    const put = placeOf(selectionBar as () => HTMLElement);
    expect(timeline()).not.toBeNull();
    await act(() => state().enterFocus(false)); // the view of a0: no tick beside it, the bar goes
    act(() => state().toggleSelected('a1')); // and comes back, over the view
    expect(view()).not.toBeNull();
    expect(placeOf(selectionBar as () => HTMLElement)).toEqual(put);
  });
});

describe('the other bands stack from the bottom as before', () => {
  it('a band that is not moved ignores the room of a band that was moved', async () => {
    act(() => state().toggleSelected('a0'));
    await flush();
    const before = placeOf(timeline as () => HTMLElement);
    expect(before.top).toBe(WINDOW.height - BOTTOM_EDGE - 61);
    dragBy(selectionBar()!, -100, -100);
    // The bar is no part of the stack any more: the time line stays on the bottom edge, the stack is not higher.
    expect(placeOf(timeline as () => HTMLElement)).toEqual(before);
  });

  it('without a moved band, the bar stands above the band under it, as before', async () => {
    act(() => state().toggleSelected('a0'));
    await flush();
    expect(placeOf(selectionBar as () => HTMLElement).top).toBe(WINDOW.height - BOTTOM_EDGE - 61 - GAP - 66);
  });
});

describe('a band stays completely inside the window', () => {
  it('is kept there while it is dragged', async () => {
    act(() => state().toggleSelected('a0'));
    await flush();
    dragBy(timeline()!, 5000, 5000);
    const place = placeOf(timeline as () => HTMLElement);
    expect(place.left).toBe(WINDOW.width - 300 - 8);
    expect(place.top).toBe(WINDOW.height - 61 - 8);
    dragBy(timeline()!, -9000, -9000);
    expect(placeOf(timeline as () => HTMLElement)).toEqual({ left: 8, top: 8 });
  });

  it('is brought back into the visible area when the window gets smaller', async () => {
    act(() => state().toggleSelected('a0'));
    await flush();
    dragBy(timeline()!, 400, 0);
    expect(placeOf(timeline as () => HTMLElement).left).toBeGreaterThan(700);
    Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: 800 });
    Object.defineProperty(window, 'innerHeight', { configurable: true, writable: true, value: 500 });
    act(() => void window.dispatchEvent(new Event('resize')));
    const place = placeOf(timeline as () => HTMLElement);
    expect(place.left).toBeLessThanOrEqual(800 - 300 - 8);
    expect(place.top).toBeLessThanOrEqual(500 - 61 - 8);
    expect(place.left).toBeGreaterThanOrEqual(8);
    expect(place.top).toBeGreaterThanOrEqual(8);
  });
});
