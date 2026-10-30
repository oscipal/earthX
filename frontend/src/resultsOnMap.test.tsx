// @vitest-environment jsdom
//
// Otto, 27.10.2026 (zu #211): "Hide results" holds. Whatever happens next, no outline, quicklook or crop of a search
// result is on the map; and only the switch changes show/hide, with exceptions: a new search ("Search") shows the
// results, a crop ("Crop to AOI", "Crop & merge to AOI") hides them and unticks the scenes it was made of.
// Changed on 28.10.2026 (zu #221): the ticked scene is no exception any more, "Hide results" hides it too (its tick
// stays), and ticking a scene while the results are hidden shows them (the third exception; unticking changes nothing).
// `mapResults.ts` is the one function that says what is on the map, so the matrix
// asks it, after each thing a user can do, with the results hidden or shown and a scene ticked or not.
// The tests of Otto's own click path fail against the code before: "Clear" did not exist, and leaving a view, a
// crop, a new search and a cleared search all put the switch where they liked.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';
import { datasetsFrom } from './datasets';
import { bboxToPolygon } from './geoUtils';
import { resultsOnMapOf } from './mapResults';
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

function scene(id: string, day: string): StacItem {
  const bbox: [number, number, number, number] = [10, 50, 11, 51];
  return { id, collection: DATASET, bbox, geometry: bboxToPolygon(bbox), properties: { datetime: `${day}T10:00:00Z` }, assets: {} };
}
const scenes = (prefix: string, n: number, day: string) => Array.from({ length: n }, (_, i) => scene(`${prefix}${i}`, day));
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const page = (features: StacItem[], next: string | null, extra: Record<string, unknown> = {}) => ({
  features,
  numberReturned: features.length,
  links: next ? [{ rel: 'next', href: '/stac/search', method: 'POST', body: { token: next } }] : [],
  ...extra,
});
// Two days of scenes, and more behind "Load more".
const PAGES: Record<string, ReturnType<typeof page>> = {
  '': page([...scenes('a', 3, '2026-07-24'), ...scenes('b', 2, '2026-07-25')], 'p2', { numberMatched: 8 }),
  p2: page(scenes('c', 3, '2026-07-26'), null),
};

let container: HTMLDivElement;
let root: Root;

const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
  if (url === '/stac/collections') return json({ collections: [COLLECTION] });
  if (url === '/stac/search' && init?.method === 'POST') return json(PAGES[(JSON.parse(init.body as string).token as string | undefined) ?? '']);
  return json({ detail: 'not found' }, 404);
});

const state = () => useAppStore.getState();
const click = (el: Element) => act(() => el.dispatchEvent(new MouseEvent('click', { bubbles: true })));
const buttonWith = (text: string): HTMLButtonElement => {
  const found = [...container.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent?.includes(text));
  if (!found) throw new Error(`no button "${text}" in ${container.textContent?.slice(0, 200)}`);
  return found;
};
// A button of the view of scenes (the area has a "Clear" of its own in the control panel).
const viewButton = (text: string): HTMLButtonElement => {
  const found = [...container.querySelectorAll<HTMLButtonElement>('.scene-view button')].find((b) => b.textContent?.includes(text));
  if (!found) throw new Error(`no button "${text}" in the view`);
  return found;
};
const areaClear = () => [...container.querySelectorAll<HTMLButtonElement>('.toolbar button')].find((b) => b.textContent?.includes('Clear'))!;
const flush = () => act(async () => { for (let i = 0; i < 40; i++) await Promise.resolve(); });

beforeEach(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  sessionStorage.clear();
  resetJobs();
  vi.stubGlobal('fetch', fetchMock);
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  act(() => root.render(<App />));
  await flush();
  useAppStore.setState({
    dock: 'controls', datasets: datasetsFrom([COLLECTION]), selectedDatasetIds: [DATASET], datasetId: DATASET, aoi: AOI, dateFrom: '', dateTo: '',
    sections: [], openSectionId: null, items: [], groups: [], selectedIds: [], layers: [], searchContext: null, searching: false, loadingMore: false,
    loadMoreError: null, loadMoreUsed: false, focusMode: false, resultViewLayerId: null, error: null, notice: null, resultsOnMap: true,
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

const idsOf = (items: StacItem[]) => items.map((it) => it.id);
// What may be on the map with the results hidden: nothing of the search, the ticked scenes included. The view's own
// scenes are no result.
function expectNothingOnMap() {
  const shown = resultsOnMapOf(state());
  expect(shown.quicklooks).toEqual([]);
  expect(shown.overlay).toEqual([]);
  expect(shown.highlight).toEqual([]);
  for (const id of idsOf(shown.clickable)) expect(state().focusMode && Object.hasOwn(state().downloaded, id)).toBe(true);
}

// A view of the scenes open (the ticked ones, or the open time step), as the bar of the selection opens it.
async function openView(crop = false) {
  await act(() => state().enterFocus(crop));
  expect(state().focusMode).toBe(true);
}

// What each thing a user can do does to the switch and the tick: `switchTo` is what show/hide is afterwards (null: as
// before), `unticks` whether the tick is gone.
interface Effect {
  switchTo?: boolean;
  unticks?: boolean;
  startsOver?: boolean;
}
const OPERATIONS: [string, () => Promise<void> | void, Effect][] = [
  ['"Clear" in the view', async () => { await openView(); click(viewButton('Clear')); }, {}],
  ['"Change image" in the view', async () => { await openView(); click(viewButton('Change image')); }, {}],
  ['"Crop to AOI"', () => openView(true), { switchTo: false, unticks: true }],
  ['"View whole scene"', () => openView(false), {}],
  ['"Clear" of the area in the control panel, in a view', async () => { await openView(); act(() => state().setToolMode('none')); act(() => state().reopenControls()); act(() => useAppStore.setState({ dock: 'controls' })); click(areaClear()); }, {}],
  ['"Clear" of the area in the control panel, in a crop', async () => { await openView(true); act(() => state().setToolMode('none')); act(() => state().reopenControls()); act(() => useAppStore.setState({ dock: 'controls' })); click(areaClear()); }, { switchTo: false, unticks: true }],
  ['a layer removed', async () => { await openView(); act(() => state().removeLayer('none')); }, {}],
  ['a change of the basemap', () => void act(() => state().setBasemap('streets')), {}],
  ['a change of the projection', () => void act(() => state().setProjection('globe')), {}],
  ['"Load more"', async () => { await act(() => state().loadMore()); }, { startsOver: true }],
  ['a new search', () => act(() => state().runSearch()), { switchTo: true, startsOver: true }],
];

describe.each([false, true])('with the results on the map: %s', (onMap) => {
  describe.each([false, true])('and a scene ticked: %s', (hasTick) => {
    beforeEach(() => {
      // Ticked first: ticking a scene while the results are hidden would show them.
      act(() => {
        if (hasTick) state().toggleSelected('a0');
        useAppStore.setState({ resultsOnMap: onMap });
      });
    });

    it.each(OPERATIONS)('%s leaves the switch alone but for its exceptions, and with the results hidden nothing is on the map, a ticked scene included', async (_name, run, effect) => {
      const tickBefore = [...state().selectedIds];
      await run();
      await flush();
      const expected = effect.switchTo ?? onMap;
      expect(state().resultsOnMap).toBe(expected);
      if (!expected) expectNothingOnMap();
      // The choice of scenes survives everything but a crop (and a new search, which starts over).
      if (effect.unticks) expect(state().selectedIds).toEqual([]);
      else if (!effect.startsOver) expect(state().selectedIds).toEqual(tickBefore);
    });
  });
});

describe('a new search shows the results (Otto, 27.10.2026)', () => {
  const searchButton = () => buttonWith('Search');
  beforeEach(() => {
    act(() => useAppStore.setState({ resultsOnMap: false, dock: 'controls' }));
    window.localStorage.setItem('earthx.results', 'hide');
  });

  it('"Search" in the control menu puts "Show results" back, in the store and in the browser', async () => {
    click(searchButton());
    await flush();
    expect(state().resultsOnMap).toBe(true);
    expect(window.localStorage.getItem('earthx.results')).toBe('show');
  });

  it('so does a search for a scene by its name', async () => {
    act(() => useAppStore.setState({ sceneNameQuery: 'S2B_MSIL2A_X' }));
    await act(() => state().findSceneByName());
    expect(state().resultsOnMap).toBe(true);
  });

  it('a search that does not start (no area) leaves the switch alone', async () => {
    act(() => useAppStore.setState({ aoi: null }));
    await act(() => state().runSearch());
    expect(state().resultsOnMap).toBe(false);
  });

  it('"Load more", "Clear search results" and "Clear all" do not', async () => {
    await act(() => state().loadMore());
    expect(state().resultsOnMap).toBe(false);
    act(() => state().clearSearchResults());
    expect(state().resultsOnMap).toBe(false);
    act(() => state().clearAll());
    expect(state().resultsOnMap).toBe(false);
  });
});

describe('"Hide results" hides a ticked scene too, and ticking while hidden shows the results (Otto, 28.10.2026)', () => {
  it('hiding takes the ticked scenes off the map, and their ticks stay', () => {
    act(() => { state().toggleSelected('a0'); state().toggleSelected('b0'); });
    expect(idsOf(resultsOnMapOf(state()).highlight)).toEqual(['a0', 'b0']);
    act(() => state().toggleResultsOnMap());
    expect(state().resultsOnMap).toBe(false);
    expect(state().selectedIds).toEqual(['a0', 'b0']);
    expectNothingOnMap();
  });

  it('hiding takes them off over a view as well, and a crop with them keeps working on the ticks', async () => {
    act(() => { state().toggleSelected('a0'); state().toggleSelected('b0'); });
    await act(() => state().enterFocus(false));
    expect(idsOf(resultsOnMapOf(state()).overlay)).toEqual(expect.arrayContaining(['a0', 'b0']));
    act(() => state().toggleResultsOnMap());
    expectNothingOnMap();
    expect(state().selectedIds).toEqual(['a0', 'b0']);
  });

  describe('ticking a scene while the results are hidden', () => {
    beforeEach(() => {
      act(() => { state().toggleSelected('a1'); state().toggleResultsOnMap(); });
      expect(state().resultsOnMap).toBe(false);
    });

    it('switches to "Show results", in the button too and in the browser', () => {
      act(() => useAppStore.setState({ dock: 'results' }));
      expect(buttonWith('Show results').textContent).toBe('Show results');
      act(() => state().toggleSelected('a0'));
      expect(state().resultsOnMap).toBe(true);
      expect(buttonWith('Hide results').textContent).toBe('Hide results');
      expect(window.localStorage.getItem('earthx.results')).toBe('show');
      expect(idsOf(resultsOnMapOf(state()).highlight)).toEqual(['a1', 'a0']);
    });

    it('does so for a click on a row of the list, for the time step and for "Select all"', () => {
      act(() => useAppStore.setState({ dock: 'results' }));
      click(container.querySelector('.result-row input')!);
      expect(state().resultsOnMap).toBe(true);
      act(() => state().toggleResultsOnMap());
      act(() => state().toggleGroupSelected(1));
      expect(state().resultsOnMap).toBe(true);
      act(() => state().toggleResultsOnMap());
      act(() => state().selectAllInActiveGroup());
      expect(state().resultsOnMap).toBe(true);
      act(() => state().toggleResultsOnMap());
      act(() => state().selectAllLoaded());
      expect(state().resultsOnMap).toBe(true);
    });

    it('is left alone by unticking: the results stay hidden', () => {
      act(() => state().toggleSelected('a1'));
      expect(state().selectedIds).toEqual([]);
      expect(state().resultsOnMap).toBe(false);
      act(() => state().toggleSelected('a1'));
      act(() => state().toggleResultsOnMap());
      act(() => state().clearSelection());
      expect(state().resultsOnMap).toBe(false);
    });

    it('is left alone by ticking a scene that is ticked already (the time step again)', () => {
      act(() => state().selectAllInActiveGroup());
      act(() => state().toggleResultsOnMap());
      act(() => state().selectAllInActiveGroup());
      expect(state().resultsOnMap).toBe(false);
    });
  });
});

describe('the order of the ticked scenes (Otto, 28.10.2026)', () => {
  it('is the order they were ticked in, the last one on top, and a scene ticked again goes to the top', () => {
    act(() => { state().toggleSelected('b0'); state().toggleSelected('a0'); state().toggleSelected('a2'); });
    expect(idsOf(resultsOnMapOf(state()).highlight)).toEqual(['b0', 'a0', 'a2']);
    act(() => state().toggleSelected('a0'));
    expect(idsOf(resultsOnMapOf(state()).highlight)).toEqual(['b0', 'a2']);
    act(() => state().toggleSelected('a0'));
    expect(idsOf(resultsOnMapOf(state()).highlight)).toEqual(['b0', 'a2', 'a0']);
  });

  it('is kept in memory only: nothing of it goes into the browser', () => {
    act(() => { state().toggleSelected('b0'); state().toggleSelected('a0'); });
    expect(JSON.stringify({ ...localStorage })).not.toContain('b0');
  });
});

describe('Otto\'s click path (27.10.2026)', () => {
  it('shown, a scene ticked, "Crop to AOI": the results are hidden and the scene unticked, so its quicklook does not lie on the crop', async () => {
    act(() => { state().toggleSelected('a0'); useAppStore.setState({ dock: 'results' }); });
    expect(state().resultsOnMap).toBe(true);
    click(buttonWith('Crop to AOI'));
    await flush();
    expect(state().focusMode).toBe(true);
    expect(state().resultsOnMap).toBe(false);
    expect(buttonWith('Show results').textContent).toBe('Show results');
    expect(state().selectedIds).toEqual([]);
    const shown = resultsOnMapOf(state());
    expect(shown.quicklooks).toEqual([]);
    expect(shown.overlay).toEqual([]);
    expect(shown.highlight).toEqual([]);
    // The view stays, and does not hang on the tick.
    expect(Object.keys(state().downloaded)).toEqual(['a0']);
  });

  it('the scene ticked again shows the results with its quicklook and leaves the view alone', async () => {
    act(() => { state().toggleSelected('a0'); useAppStore.setState({ dock: 'results' }); });
    click(buttonWith('Crop to AOI'));
    await flush();
    const view = state().downloaded;
    act(() => state().toggleSelected('a0'));
    // The tick shows the results (the third exception): the quicklook of the scene lies over the view with the others.
    expect(state().resultsOnMap).toBe(true);
    expect(idsOf(resultsOnMapOf(state()).overlay)).toContain('a0');
    expect(idsOf(resultsOnMapOf(state()).highlight)).toEqual(['a0']);
    expect(state().focusMode).toBe(true);
    expect(state().downloaded).toBe(view);
    act(() => state().toggleResultsOnMap());
    expect(resultsOnMapOf(state()).overlay).toEqual([]);
  });

  it('"Show results" with the view open lays the results over the quicklooks of browsing, under the view', async () => {
    act(() => { state().toggleSelected('a0'); useAppStore.setState({ dock: 'results' }); });
    click(buttonWith('Crop to AOI'));
    await flush();
    click(buttonWith('Show results'));
    expect(state().resultsOnMap).toBe(true);
    expect(state().focusMode).toBe(true);
    expect(resultsOnMapOf(state()).overlay.length).toBeGreaterThan(0);
  });

  it('"Clear" of the area, then the view\'s own "Clear"', async () => {
    act(() => { state().toggleSelected('a0'); useAppStore.setState({ dock: 'results' }); });
    click(buttonWith('Crop to AOI'));
    await flush();
    act(() => state().reopenControls());
    act(() => useAppStore.setState({ dock: 'controls' }));
    click(areaClear());
    expect(state().aoi).toBeNull();
    expect(state().focusMode).toBe(true);
    click(viewButton('Clear'));
    expect(state().focusMode).toBe(false);
    expect(state().downloaded).toEqual({});
  });

  it('the switch says what a click does, and hiding takes everything off the map, a ticked scene included', async () => {
    act(() => useAppStore.setState({ dock: 'results' }));
    expect(buttonWith('Hide results').textContent).toBe('Hide results');
    act(() => state().toggleSelected('a0'));
    click(buttonWith('Hide results'));
    expect(buttonWith('Show results').textContent).toBe('Show results');
    expectNothingOnMap();
    // Leaving a view brings nothing back, and the tick stays.
    await openView();
    click(viewButton('Change image'));
    expect(state().resultsOnMap).toBe(false);
    expect(state().selectedIds).toEqual(['a0']);
    expectNothingOnMap();
    // Unticking changes nothing.
    act(() => state().toggleSelected('a0'));
    expect(state().resultsOnMap).toBe(false);
    expectNothingOnMap();
  });
});

describe('"Clear" and "Change image" in the view', () => {
  it('"Clear" takes the view off the map and nothing else: the tick, what was pinned, the switch and the panel stay', async () => {
    const layer = { id: 'pinned', name: 'Pinned', visible: true, opacity: 1, overlays: [], restore: { datasetId: DATASET, itemIds: [], groupItemIds: [], downloaded: {}, appliedRender: {}, selectedIds: [] } } as never;
    act(() => state().toggleSelected('a0'));
    act(() => useAppStore.setState({ layers: [layer], resultsOnMap: false, dock: 'controls' }));
    await openView();
    const pinned = state().layers;
    click(viewButton('Clear'));
    const s = state();
    expect(s.focusMode).toBe(false);
    expect(s.downloaded).toEqual({});
    expect(s.selectedIds).toEqual(['a0']);
    expect(s.layers).toBe(pinned);
    expect(s.resultsOnMap).toBe(false);
    expect(s.dock).toBe('controls');
    // The results list is still there.
    expect(s.sections.length).toBe(1);
  });

  it('"Change image" takes the view off the map and opens the results, and leaves the tick and the switch', async () => {
    act(() => state().toggleSelected('a0'));
    act(() => useAppStore.setState({ dock: 'controls', resultsOnMap: false }));
    await openView();
    click(viewButton('Change image'));
    expect(state().focusMode).toBe(false);
    expect(state().dock).toBe('results');
    expect(state().selectedIds).toEqual(['a0']);
    expect(state().resultsOnMap).toBe(false);
  });

  it('have the tooltips of what they do', async () => {
    await openView();
    expect(viewButton('Clear').title).toBe('Remove this view from the map');
    expect(viewButton('Change image').title).toBe('Remove this view and choose another scene from the results');
  });
});
