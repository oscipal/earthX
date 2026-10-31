// @vitest-environment jsdom
//
// UI-01g (Otto, 26.10.2026): the search results are the fourth panel beside the rail. The symbol counts the
// scenes, the panel opens by itself after a search, one panel at a time, and everything the list could do
// before is still there: groups, "Select all", "Load more", the dataset box, and the bar of the selection
// (view, download) at the bottom. "Clear all" is gone from the head (Otto, 26.10.2026), where the switch
// for the map is now: since NM4-59 the eye of the results, the same as in the entry "Results" of the layer manager.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';
import { datasetsFrom } from './datasets';
import { jobEntry, NOW } from './fixtures/jobEntries';
import { bboxToPolygon } from './geoUtils';
import { resetJobs, useProcessingStore } from './processingStore';
import { HIDE_RESULTS_TIP, SHOW_RESULTS_TIP } from './components/ResultsEye';
import { RESULTS_ON_TOP_TIP } from './components/ResultsToTop';
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
  'earthx:viewer': {
    group_by: ['datetime'],
    min_zoom: 8,
    max_zoom: 14,
    browse: 'quicklook',
    quicklook_nodata_max: null,
    results_group_by: ['datetime'],
  },
} as unknown as Collection;

function scene(id: string, day: string): StacItem {
  const bbox: [number, number, number, number] = [10, 50, 11, 51];
  return { id, collection: DATASET, bbox, geometry: bboxToPolygon(bbox), properties: { datetime: `${day}T10:00:00Z` }, assets: {} };
}

const scenes = (prefix: string, n: number, day: string) => Array.from({ length: n }, (_, i) => scene(`${prefix}${i}`, day));

function page(features: StacItem[], next: string | null, extra: Record<string, unknown> = {}) {
  const links = next ? [{ rel: 'next', href: '/stac/search', method: 'POST', body: { token: next } }] : [];
  return { features, numberReturned: features.length, links, ...extra };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

let answer: (init?: RequestInit) => Response | Promise<Response>;
let container: HTMLDivElement;
let root: Root;

const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
  if (url === '/stac/collections') return json({ collections: [COLLECTION] });
  if (url === '/stac/search' && init?.method === 'POST') return answer(init);
  return json({ detail: 'not found' }, 404);
});

const search = () => act(() => useAppStore.getState().runSearch());
const symbol = (name: 'controls' | 'layers' | 'jobs' | 'results') => container.querySelector<HTMLButtonElement>(`#rail-${name}`)!;
const slot = (name: 'controls' | 'layers' | 'jobs' | 'results') => container.querySelector<HTMLElement>(`#dock-${name}`)!;
const click = (el: Element) => act(() => el.dispatchEvent(new MouseEvent('click', { bubbles: true })));
const visible = () => [...container.querySelectorAll<HTMLElement>('.dock-slot:not([hidden])')].map((el) => el.id);

// A search walks pages of 100 up to 300 scenes; 340 matched, so "Load more" and "(of 340)" show.
const PAGES: Record<string, ReturnType<typeof page>> = {
  '': page(scenes('a', 100, '2026-07-24'), 'p2', { numberMatched: 340 }),
  p2: page(scenes('b', 100, '2026-07-25'), 'p3'),
  p3: page(scenes('c', 100, '2026-07-26'), 'p4'),
  p4: page(scenes('d', 40, '2026-07-27'), null),
};
const MANY = (init?: RequestInit) => json(PAGES[(JSON.parse(init!.body as string).token as string | undefined) ?? '']);
const FEW = page(scenes('f', 2, '2026-07-24'), null, { numberMatched: 2 });

beforeEach(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  sessionStorage.clear();
  // The jobs of the fixture are dated by `NOW`.
  vi.useFakeTimers({ toFake: ['Date'], now: NOW });
  vi.stubGlobal('fetch', fetchMock);
  answer = () => json(FEW);
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  act(() => root.render(<App />));
  // Loading the collections on start resets the selection: set the state after it.
  await act(async () => {
    for (let i = 0; i < 40; i++) await Promise.resolve();
  });
  useAppStore.setState({
    dock: 'controls',
    datasets: datasetsFrom([COLLECTION]),
    selectedDatasetIds: [DATASET],
    datasetId: DATASET,
    aoi: AOI,
    dateFrom: '',
    dateTo: '',
    sections: [],
    openSectionId: null,
    items: [],
    groups: [],
    selectedIds: [],
    layers: [],
    searchContext: null,
    searching: false,
    loadingMore: false,
    loadMoreError: null,
    loadMoreUsed: false,
    focusMode: false,
    resultViewLayerId: null,
    error: null,
    notice: null,
  });
  useProcessingStore.setState({ open: false, jobs: [] });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  resetJobs();
  localStorage.clear();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('the symbol', () => {
  it('is the fourth in the rail, named "Results"', () => {
    expect([...container.querySelectorAll('.app-rail button')].map((b) => b.id)).toEqual([
      'rail-controls',
      'rail-layers',
      'rail-jobs',
      'rail-results',
    ]);
  });

  it('stays in its place without results, says why in its tooltip, and opens nothing', () => {
    const button = symbol('results');
    expect(button.getAttribute('aria-disabled')).toBe('true');
    expect(button.getAttribute('data-tip')).toBe('No results yet: run a search first');
    expect(button.querySelector('.rail-badge')).toBeNull();
    click(button);
    expect(useAppStore.getState().dock).toBe('controls');
  });

  it('counts the scenes the search found, in the badge and in the name', async () => {
    await search();
    expect(symbol('results').getAttribute('aria-disabled')).toBeNull();
    expect(symbol('results').getAttribute('aria-label')).toBe('Results, 2');
    expect(symbol('results').querySelector('.rail-badge')?.textContent).toBe('2');
  });
});

describe('after a search', () => {
  it('the panel opens by itself, instead of the control menu', async () => {
    await search();
    expect(useAppStore.getState().dock).toBe('results');
    expect(visible()).toEqual(['dock-results']);
    expect(symbol('results').getAttribute('aria-expanded')).toBe('true');
    expect(symbol('results').getAttribute('aria-controls')).toBe('dock-results');
    expect(symbol('controls').getAttribute('aria-expanded')).toBe('false');
    expect(container.querySelector('.app')!.classList.contains('dock-open')).toBe(true);
  });

  it('lies beside the rail with the other panels, and no list is left at the right edge', async () => {
    await search();
    expect(slot('results').closest('.dock')).not.toBeNull();
    expect(slot('results').querySelector('.results-panel')).not.toBeNull();
    expect(container.querySelector('.results-dock, .results-toggle')).toBeNull();
  });

  it('leaves the panel closed, and the others as they are, for a search that found nothing', async () => {
    answer = () => json(page([], null));
    await search();
    expect(useAppStore.getState().dock).toBeNull();
    expect(symbol('results').getAttribute('aria-disabled')).toBe('true');
  });

  it('goes back to the control menu when the search fails', async () => {
    await search();
    expect(useAppStore.getState().dock).toBe('results');
    answer = () => json({ detail: 'down' }, 500);
    await search();
    expect(useAppStore.getState().error).toMatch(/Search failed/);
    expect(useAppStore.getState().dock).toBe('controls');
    expect(visible()).toEqual(['dock-controls']);
  });

  it('keeps the settings of the search in the control menu, one click away', async () => {
    await search();
    click(symbol('controls'));
    expect(visible()).toEqual(['dock-controls']);
    expect(useAppStore.getState().aoi).toEqual(AOI);
    expect(useAppStore.getState().selectedDatasetIds).toEqual([DATASET]);
  });
});

describe('one panel at a time', () => {
  it('shows only the panel of the symbol last clicked, and a second click closes the results', async () => {
    await search();
    click(symbol('layers'));
    expect(visible()).toEqual(['dock-layers']);
    click(symbol('results'));
    expect(visible()).toEqual(['dock-results']);
    click(symbol('results'));
    expect(useAppStore.getState().dock).toBeNull();
    expect(visible()).toEqual([]);
  });

  it('keeps what was open in the list when another panel comes and goes', async () => {
    answer = MANY;
    await search();
    click(slot('results').querySelectorAll('.result-group-head')[1]);
    const expandedBefore = useAppStore.getState().expandedGroupIndex;
    click(symbol('jobs'));
    click(symbol('results'));
    expect(useAppStore.getState().expandedGroupIndex).toBe(expandedBefore);
    expect(slot('results').querySelectorAll('.rg-items')).toHaveLength(1);
  });

  it('is not pushed away by "Load more", which leaves a panel the user opened meanwhile', async () => {
    answer = MANY;
    await search();
    click(symbol('layers'));
    await act(() => useAppStore.getState().loadMore());
    expect(useAppStore.getState().dock).toBe('layers');
  });

  it('refuses to open without results, from the store as from the symbol', () => {
    act(() => useAppStore.getState().toggleDock('results'));
    expect(useAppStore.getState().dock).toBe('controls');
  });

  it('closes with Escape from inside, and hands the focus back to its symbol', async () => {
    await search();
    const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
    act(() => slot('results').querySelector('.results-head h2')!.dispatchEvent(event));
    expect(useAppStore.getState().dock).toBeNull();
    expect(document.activeElement).toBe(symbol('results'));
  });
});

describe('everything the list could do is in the panel', () => {
  beforeEach(async () => {
    answer = MANY;
    await search();
  });

  it('lists the scenes in groups by pass, with their counts', () => {
    const heads = [...slot('results').querySelectorAll('.result-group-head')];
    expect(heads.map((h) => h.querySelector('.rg-count')?.textContent)).toEqual(['100', '100', '100']);
    expect(slot('results').querySelector('.results-head h2')?.textContent).toBe('Results (0/300)');
  });

  it('opens and closes a group', () => {
    const head = slot('results').querySelector('.result-group-head')!;
    const open = () => slot('results').querySelectorAll('.result-row').length;
    const before = open();
    click(head);
    expect(open()).not.toBe(before);
  });

  it('selects a scene, or all of them, and says "of N" while the source has more', () => {
    const label = slot('results').querySelector('.select-all-box')!.textContent;
    expect(label).toBe('Select all 300 loaded (of 340)');
    click(slot('results').querySelector('.select-all-box input')!);
    expect(useAppStore.getState().selectedIds).toHaveLength(300);
    click(slot('results').querySelector('.select-all-box input')!);
    expect(useAppStore.getState().selectedIds).toEqual([]);
  });

  it('selects a whole group from its check box', () => {
    click(slot('results').querySelector('.rg-select')!);
    expect(useAppStore.getState().selectedIds).toHaveLength(100);
  });

  it('loads more, and the new scenes arrive in the panel', async () => {
    const button = [...slot('results').querySelectorAll('button')].find((b) => b.textContent === 'Load more')!;
    await act(async () => button.click());
    expect(symbol('results').getAttribute('aria-label')).toBe('Results, 340');
    expect([...slot('results').querySelectorAll('button')].some((b) => b.textContent === 'Load more')).toBe(false);
  });

  it('names the dataset in the box', () => {
    expect(slot('results').querySelector('.dataset-select-box')?.textContent).toContain('Optical imagery');
  });

  it('leaves the bar of the selection (view, download) at the bottom, next to the panel', () => {
    expect(container.querySelector('.download-bar')).toBeNull();
    click(slot('results').querySelector('.select-all-box input')!);
    const bar = container.querySelector('.download-bar')!;
    expect(bar).not.toBeNull();
    expect(bar.closest('.dock')).toBeNull();
    expect(bar.textContent).toContain('Crop & merge to AOI');
    expect(bar.textContent).toContain('Download merged crop');
  });

  it('has no "Clear all" in its head', () => {
    expect([...slot('results').querySelectorAll('.results-head button')].map((b) => (b as HTMLButtonElement).title)).toEqual([RESULTS_ON_TOP_TIP, HIDE_RESULTS_TIP]);
  });

  it('goes back to the control menu when the search is cleared', () => {
    act(() => useAppStore.getState().clearAll());
    expect(useAppStore.getState().dock).toBe('controls');
    expect(visible()).toEqual(['dock-controls']);
    expect(slot('results').querySelector('.results-panel')).toBeNull();
    expect(symbol('results').getAttribute('aria-disabled')).toBe('true');
  });

  it('goes back to the control menu when another choice of datasets drops the results', () => {
    act(() => useAppStore.getState().toggleDatasetSelected(DATASET));
    expect(useAppStore.getState().sections).toEqual([]);
    expect(useAppStore.getState().dock).toBe('controls');
  });
});

describe('with a view open (Otto, 26.10.2026: the results never disappear, they are only switched off on the map)', () => {
  it('keeps the list, the title and the switch, in the full-resolution view and after "Crop to AOI"', async () => {
    answer = MANY;
    await search();
    click(slot('results').querySelector('.result-row input')!);
    act(() => useAppStore.setState({ focusMode: true, cropToAoi: true }));
    expect(slot('results').querySelector('.results-list')).not.toBeNull();
    expect(slot('results').querySelectorAll('.result-group-head')).toHaveLength(3);
    expect(slot('results').querySelector('.results-head h2')?.textContent).toBe('Results (1/300)');
    expect([...slot('results').querySelectorAll('.results-head button')].map((b) => (b as HTMLButtonElement).title)).toEqual([RESULTS_ON_TOP_TIP, HIDE_RESULTS_TIP]);
    expect(useAppStore.getState().sections).toHaveLength(1);
    expect(symbol('results').getAttribute('aria-label')).toBe('Results, 300');
    act(() => useAppStore.setState({ focusMode: false, cropToAoi: false }));
    expect(slot('results').querySelector('.results-list')).not.toBeNull();
  });

  it('shows the bar of the selection above the controls of the view once a scene is ticked that the view does not draw', async () => {
    answer = MANY;
    await search();
    act(() => useAppStore.setState({ focusMode: true, downloaded: { c0: {} as never }, selectedIds: ['c0'] }));
    expect(container.querySelector('.download-bar')).toBeNull();
    expect(container.querySelector('.viewer-controls')).not.toBeNull();
    click([...slot('results').querySelectorAll('.result-row input')].find((el) => el.getAttribute('aria-label') === 'Select c1')!);
    expect(useAppStore.getState().selectedIds).toEqual(['c0', 'c1']);
    expect(container.querySelector('.download-bar')?.textContent).toContain('2');
    expect(container.querySelector('.viewer-controls')).not.toBeNull();
    const bottom = container.querySelector('.overlay.bottom')!;
    expect(bottom.querySelector('.download-bar')!.compareDocumentPosition(bottom.querySelector('.viewer-controls')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('shows the bar of the selection above the controls of a result view once a scene is ticked', async () => {
    await search();
    act(() => useAppStore.setState({ resultViewLayerId: 'some-layer', selectedIds: [] }));
    expect(container.querySelector('.download-bar')).toBeNull();
    click(slot('results').querySelector('.result-row input')!);
    expect(container.querySelector('.download-bar')).not.toBeNull();
  });

  it('keeps the list when the view is a result layer', async () => {
    await search();
    act(() => useAppStore.setState({ resultViewLayerId: 'some-layer' }));
    expect(slot('results').querySelector('.results-list')).not.toBeNull();
  });

  it('keeps the results in the store when a view is entered from the bar of the selection', async () => {
    answer = MANY;
    await search();
    click(slot('results').querySelector('.select-all-box input')!);
    const before = useAppStore.getState().sections;
    const crop = [...container.querySelectorAll('.download-bar button')].find((b) => b.textContent === 'Crop & merge to AOI')!;
    await act(async () => crop.dispatchEvent(new MouseEvent('click', { bubbles: true })));
    expect(useAppStore.getState().sections).toBe(before);
    expect(slot('results').querySelector('.results-list')).not.toBeNull();
  });
});

describe('the results on the map (Otto, 26.10.2026)', () => {
  const toggle = () => slot('results').querySelector('.results-head button[aria-pressed]') as HTMLButtonElement;

  beforeEach(async () => {
    // A search no longer puts the switch back, so each test starts from "on".
    useAppStore.setState({ resultsOnMap: true });
    answer = MANY;
    await search();
  });

  it('are on after a search, and the eye offers to hide them', () => {
    expect(useAppStore.getState().resultsOnMap).toBe(true);
    expect(toggle().title).toBe(HIDE_RESULTS_TIP);
  });

  it('go off and on with the eye, whose tooltip names the next step; the list does not change', () => {
    click(toggle());
    expect(useAppStore.getState().resultsOnMap).toBe(false);
    expect(toggle().title).toBe(SHOW_RESULTS_TIP);
    expect(slot('results').querySelectorAll('.result-group-head')).toHaveLength(3);
    expect(slot('results').querySelector('.results-head h2')?.textContent).toBe('Results (0/300)');
    click(toggle());
    expect(useAppStore.getState().resultsOnMap).toBe(true);
    expect(toggle().title).toBe(HIDE_RESULTS_TIP);
  });

  it('a scene ticked while they are off is ticked as usual, with the bar of the selection, and shows them (Otto, 28.10.2026)', () => {
    click(toggle());
    click(slot('results').querySelector('.result-row input')!);
    expect(useAppStore.getState().selectedIds).toHaveLength(1);
    expect(useAppStore.getState().resultsOnMap).toBe(true);
    expect(toggle().title).toBe(HIDE_RESULTS_TIP);
    expect(container.querySelector('.download-count strong')?.textContent).toBe('1');
    expect(container.querySelector('.download-count span')?.textContent).toBe('scene selected');
  });

  it('stay as the switch left them after the search was cleared, and a new search shows them (Otto, 27.10.2026)', async () => {
    click(toggle());
    expect(useAppStore.getState().resultsOnMap).toBe(false);
    act(() => useAppStore.getState().clearAll());
    expect(useAppStore.getState().resultsOnMap).toBe(false);
    act(() => useAppStore.getState().clearSearchResults());
    expect(useAppStore.getState().resultsOnMap).toBe(false);
    // Only the switch, or a new search, brings them back ("Clear all" took the area away: draw it again).
    act(() => useAppStore.setState({ aoi: AOI }));
    await search();
    expect(useAppStore.getState().resultsOnMap).toBe(true);
    click(toggle());
    expect(useAppStore.getState().resultsOnMap).toBe(false);
    act(() => useAppStore.getState().toggleResultsOnMap());
    expect(useAppStore.getState().resultsOnMap).toBe(true);
  });
});

describe('"Clear search results" under "Load more" (Otto, 26.10.2026)', () => {
  const clearButton = () => [...slot('results').querySelectorAll('button')].find((b) => b.textContent?.includes('Clear search results'))!;

  beforeEach(async () => {
    answer = MANY;
    await search();
  });

  it('is the last thing in the panel, after "Load more", with a small red cross', () => {
    const buttons = [...slot('results').querySelectorAll('button')];
    const load = buttons.findIndex((b) => b.textContent === 'Load more');
    expect(load).toBeGreaterThan(-1);
    expect(buttons.indexOf(clearButton())).toBeGreaterThan(load);
    expect(clearButton().querySelector('.clear-results-x')?.textContent).toBe('✕');
    expect(clearButton().querySelector('.clear-results-x')?.getAttribute('aria-hidden')).toBe('true');
  });

  it('takes the list away, and what it drew on the map, and opens the control menu', () => {
    click(slot('results').querySelector('.result-row input')!);
    useAppStore.setState({ resultsOnMap: false });
    click(clearButton());
    const s = useAppStore.getState();
    expect(s.sections).toEqual([]);
    expect(s.items).toEqual([]);
    expect(s.groups).toEqual([]);
    expect(s.selectedIds).toEqual([]);
    // Clearing the results is not the switch: hidden stays hidden.
    expect(s.resultsOnMap).toBe(false);
    expect(s.dock).toBe('controls');
    expect(visible()).toEqual(['dock-controls']);
    expect(symbol('results').getAttribute('aria-disabled')).toBe('true');
  });

  it('leaves the area, dates, choice of datasets and filters', () => {
    act(() => useAppStore.setState({ dateFrom: '2026-07-01', dateTo: '2026-07-31' }));
    click(clearButton());
    const s = useAppStore.getState();
    expect(s.aoi).toEqual(AOI);
    expect(s.dateFrom).toBe('2026-07-01');
    expect(s.dateTo).toBe('2026-07-31');
    expect(s.selectedDatasetIds).toEqual([DATASET]);
    expect(s.datasetId).toBe(DATASET);
  });

  it('leaves the pinned layers and the jobs', () => {
    const layer = { id: 'pinned', name: 'Pinned', visible: true, opacity: 1, overlays: [], restore: { datasetId: DATASET, itemIds: [], groupItemIds: [], downloaded: {}, appliedRender: {}, selectedIds: [] } } as never;
    act(() => {
      useAppStore.setState({ layers: [layer] });
      useProcessingStore.setState({ jobs: [jobEntry(1)] });
    });
    click(clearButton());
    expect(useAppStore.getState().layers).toEqual([layer]);
    expect(useProcessingStore.getState().jobs).toHaveLength(1);
  });

  it('next "Search" asks with the same settings and fills the panel again', async () => {
    click(clearButton());
    await search();
    expect(useAppStore.getState().sections).toHaveLength(1);
    expect(useAppStore.getState().dock).toBe('results');
  });

  it('is there with a view open too, and closes the view with the list', () => {
    act(() => useAppStore.setState({ focusMode: true }));
    expect(clearButton()).toBeDefined();
    click(clearButton());
    expect(useAppStore.getState().focusMode).toBe(false);
  });

  it('drops the answer of a search that was still on its way', async () => {
    let release!: () => void;
    let first = true;
    answer = (init) => {
      if (!first) return MANY(init);
      first = false;
      return new Promise((resolve) => (release = () => resolve(MANY(init))));
    };
    const running = useAppStore.getState().runSearch();
    await act(async () => {
      for (let i = 0; i < 20; i++) await Promise.resolve();
    });
    click(clearButton());
    release();
    await act(async () => {
      await running;
    });
    expect(useAppStore.getState().sections).toEqual([]);
  });

  it('is also a store action that clears more than the list only when asked to: "clearAll" still clears the AOI', () => {
    act(() => useAppStore.getState().clearAll());
    expect(useAppStore.getState().aoi).toBeNull();
  });
});
