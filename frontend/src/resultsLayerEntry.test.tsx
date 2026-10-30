// @vitest-environment jsdom
//
// NM4-59 (Otto, 30.10.2026): the search results are one entry "Results" in the layer manager. Its eye is the switch of
// the results on the map, ▲/▼ move it among the pinned layers. Every search puts it on top; a layer pinned while it is on
// top goes right under it, else on top. It is there while the search has results, and goes with "Clear search results".

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';
import { HIDE_RESULTS_TIP, RESULTS_ENTRY_TIP, SHOW_RESULTS_TIP } from './components/LayerManager';
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
const COLLECTION = {
  id: DATASET,
  title: 'Optical imagery',
  'earthx:format': 'cog',
  'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
  'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
} as unknown as Collection;

function scene(id: string, day: string): StacItem {
  const bbox: [number, number, number, number] = [10, 50, 11, 51];
  return { id, collection: DATASET, bbox, geometry: bboxToPolygon(bbox), properties: { datetime: `${day}T10:00:00Z` }, assets: {} };
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
  if (url === '/stac/collections') return json({ collections: [COLLECTION] });
  if (url === '/stac/search' && init?.method === 'POST') return json({ features: [scene('a0', '2026-07-24'), scene('b0', '2026-07-25')], numberReturned: 2, links: [] });
  return json({ detail: 'not found' }, 404);
});

let container: HTMLDivElement;
let root: Root;
const state = () => useAppStore.getState();
const click = (el: Element) => act(() => el.dispatchEvent(new MouseEvent('click', { bubbles: true })));
const flush = () => act(async () => { for (let i = 0; i < 40; i++) await Promise.resolve(); });

// The rows of the layer manager, top to bottom, by name.
const rowNames = () => [...container.querySelectorAll('.layer-manager .layer-row')].map((row) => row.querySelector('[data-col="name"]')?.textContent);
const resultsRow = () => container.querySelector<HTMLLIElement>('.layer-manager .results-row');
const resultsButton = (col: string) => resultsRow()!.querySelector<HTMLButtonElement>(`[data-col="${col}"]`)!;
const rowOf = (name: string) => [...container.querySelectorAll('.layer-manager .layer-row')].find((row) => row.querySelector('[data-col="name"]')?.textContent === name)!;

function pin(name: string) {
  act(() =>
    state().pinDerivedLayer({
      name,
      derived: 'result',
      overlays: [{ kind: 'raster', tileUrl: `https://t/${name}/{z}/{x}/{y}`, bounds: [10, 50, 11, 51], minZoom: 0, maxZoom: 14 }],
      itemIds: [],
      cropToAoi: false,
    }),
  );
}

beforeEach(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  resetJobs();
  vi.stubGlobal('fetch', fetchMock);
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  act(() => root.render(<App />));
  await flush();
  useAppStore.setState({
    dock: 'controls', datasets: datasetsFrom([COLLECTION]), selectedDatasetIds: [DATASET], datasetId: DATASET, aoi: bboxToPolygon([10.1, 50.1, 10.2, 50.2]),
    dateFrom: '', dateTo: '', sections: [], openSectionId: null, items: [], groups: [], selectedIds: [], layers: [], resultsAt: 0, searchContext: null,
    focusMode: false, error: null, notice: null, resultsOnMap: true,
  });
  useProcessingStore.setState({ open: false, jobs: [] });
  await act(() => state().runSearch());
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  resetJobs();
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe('the entry "Results" in the layer manager', () => {
  it('is there with the results, on top, with an eye and ▲/▼ and nothing else', () => {
    expect(rowNames()).toEqual(['Results']);
    expect(resultsButton('name').getAttribute('title')).toBe(RESULTS_ENTRY_TIP);
    for (const col of ['opacity', 'process', 'download', 'note', 'remove']) expect(resultsRow()!.querySelector(`button[data-col="${col}"], input[data-col="${col}"]`)).toBeNull();
    expect(resultsButton('up').disabled).toBe(true);
    expect(resultsButton('down').disabled).toBe(true);
    // The count in the head is that of the pinned layers.
    expect(container.querySelector('.layer-manager .results-head-right')?.textContent).toBe('0');
  });

  it('takes a pinned layer right under it while it is on top', () => {
    pin('Job one');
    pin('Job two');
    expect(rowNames()).toEqual(['Results', 'Job two', 'Job one']);
    expect(state().resultsAt).toBe(0);
  });

  it('moves with ▲/▼ among the layers, and a layer pinned then goes on top, over it', () => {
    pin('Job one');
    pin('Job two');
    click(resultsButton('down'));
    expect(rowNames()).toEqual(['Job two', 'Results', 'Job one']);
    click(resultsButton('down'));
    expect(rowNames()).toEqual(['Job two', 'Job one', 'Results']);
    expect(resultsButton('down').disabled).toBe(true);
    pin('Job three');
    expect(rowNames()).toEqual(['Job three', 'Job two', 'Job one', 'Results']);
    click(resultsButton('up'));
    expect(rowNames()).toEqual(['Job three', 'Job two', 'Results', 'Job one']);
  });

  it('changes places with a layer whose ▲/▼ points at it', () => {
    pin('Job one');
    click(rowOf('Job one').querySelector<HTMLButtonElement>('[data-col="up"]')!);
    expect(rowNames()).toEqual(['Job one', 'Results']);
    expect(rowOf('Job one').querySelector<HTMLButtonElement>('[data-col="up"]')!.disabled).toBe(true);
    click(rowOf('Job one').querySelector<HTMLButtonElement>('[data-col="down"]')!);
    expect(rowNames()).toEqual(['Results', 'Job one']);
  });

  it('moves up when a layer above it is removed, and stays when one below it is', () => {
    pin('Job one');
    pin('Job two');
    pin('Job three');
    click(resultsButton('down'));
    click(resultsButton('down'));
    expect(rowNames()).toEqual(['Job three', 'Job two', 'Results', 'Job one']);
    click(rowOf('Job one').querySelector('[data-col="remove"]')!);
    expect(rowNames()).toEqual(['Job three', 'Job two', 'Results']);
    click(rowOf('Job three').querySelector('[data-col="remove"]')!);
    expect(rowNames()).toEqual(['Job two', 'Results']);
    expect(state().resultsAt).toBe(1);
  });

  it('goes back on top with every search, and "Load more" leaves it', async () => {
    pin('Job one');
    click(resultsButton('down'));
    expect(state().resultsAt).toBe(1);
    await act(() => state().loadMore());
    expect(state().resultsAt).toBe(1);
    await act(() => state().runSearch());
    await flush();
    expect(rowNames()).toEqual(['Results', 'Job one']);
  });

  it('goes with "Clear search results"; the layers then move among themselves only', () => {
    pin('Job one');
    pin('Job two');
    click(resultsButton('down'));
    act(() => state().clearSearchResults());
    expect(rowNames()).toEqual(['Job two', 'Job one']);
    expect(state().resultsAt).toBe(0);
    click(rowOf('Job two').querySelector<HTMLButtonElement>('[data-col="down"]')!);
    expect(rowNames()).toEqual(['Job one', 'Job two']);
    expect(state().resultsAt).toBe(0);
    expect(rowOf('Job two').querySelector<HTMLButtonElement>('[data-col="down"]')!.disabled).toBe(true);
  });
});

describe('the eye of "Results"', () => {
  it('is the switch of the results on the map, with what a click does in its tooltip', () => {
    const eye = () => resultsButton('eye');
    expect(eye().getAttribute('aria-pressed')).toBe('true');
    expect(eye().title).toBe(HIDE_RESULTS_TIP);
    click(eye());
    expect(state().resultsOnMap).toBe(false);
    expect(eye().getAttribute('aria-pressed')).toBe('false');
    expect(eye().title).toBe(SHOW_RESULTS_TIP);
    expect(eye().classList.contains('off')).toBe(true);
    click(eye());
    expect(state().resultsOnMap).toBe(true);
  });

  it('follows the exceptions: a crop closes it, a tick opens it, a search opens it, "Play" opens it', async () => {
    const pressed = () => resultsButton('eye').getAttribute('aria-pressed');
    act(() => state().toggleSelected('a0'));
    await act(() => state().enterFocus(true));
    expect(pressed()).toBe('false');
    act(() => state().toggleSelected('b0'));
    expect(pressed()).toBe('true');
    click(resultsButton('eye'));
    await act(() => state().runSearch());
    await flush();
    expect(pressed()).toBe('true');
    click(resultsButton('eye'));
    click(container.querySelector('.time-slider .play-btn')!);
    expect(pressed()).toBe('true');
  });

  it('leaves the order alone, and moving leaves the eye alone', () => {
    pin('Job one');
    click(resultsButton('eye'));
    click(resultsButton('down'));
    expect(rowNames()).toEqual(['Job one', 'Results']);
    expect(state().resultsOnMap).toBe(false);
  });
});
