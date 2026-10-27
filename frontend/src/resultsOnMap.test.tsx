// @vitest-environment jsdom
//
// Otto, 27.10.2026 (zu #211): "Hide results" holds. Whatever happens next, no outline, quicklook or crop of a search
// result is on the map, except for a ticked scene, which shows with its usual controls and goes with its tick; and
// only the switch changes show/hide, with two exceptions: a new search ("Search") shows the results, and a crop
// ("Crop to AOI", "Crop & merge to AOI") hides them and unticks the scenes it was made of.
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
    loadMoreError: null, loadMoreUsed: false, focusMode: false, resultViewLayerId: null, searchCrops: [], error: null, notice: null, resultsOnMap: true,
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
const ticked = () => new Set(state().selectedIds);

// What may be on the map with the results hidden: the ticked scenes, and nothing else.
function expectOnlyTickedOnMap() {
  const shown = resultsOnMapOf(state());
  const allowed = ticked();
  for (const id of [...idsOf(shown.quicklooks), ...idsOf(shown.overlay), ...idsOf(shown.highlight), ...idsOf(shown.clickable)]) expect(allowed.has(id) || (state().focusMode && Object.hasOwn(state().downloaded, id))).toBe(true);
  expect(shown.cropsOf).toEqual(state().selectedIds);
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
      act(() => {
        useAppStore.setState({ resultsOnMap: onMap });
        if (hasTick) state().toggleSelected('a0');
      });
    });

    it.each(OPERATIONS)('%s leaves the switch alone but for the two exceptions, and with the results hidden only a ticked scene is on the map', async (_name, run, effect) => {
      const tickBefore = [...state().selectedIds];
      await run();
      await flush();
      const expected = effect.switchTo ?? onMap;
      expect(state().resultsOnMap).toBe(expected);
      if (!expected) expectOnlyTickedOnMap();
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

describe('a scene that is ticked shows although the results are hidden, and goes with its tick', () => {
  beforeEach(() => act(() => useAppStore.setState({ resultsOnMap: false })));

  it('nothing is on the map with nothing ticked', () => {
    const shown = resultsOnMapOf(state());
    expect(shown.quicklooks).toEqual([]);
    expect(shown.overlay).toEqual([]);
    expect(shown.highlight).toEqual([]);
    expect(shown.cropsOf).toEqual([]);
  });

  it('the ticked scene shows, in browsing and over a view, and is gone when its tick is', async () => {
    act(() => state().toggleSelected('a0'));
    expect(idsOf(resultsOnMapOf(state()).quicklooks)).toEqual(['a0']);
    expect(idsOf(resultsOnMapOf(state()).highlight)).toEqual(['a0']);
    await act(() => state().enterFocus(true));
    // The view draws the scene itself; a second ticked scene lies over it.
    act(() => state().toggleSelected('a1'));
    expect(idsOf(resultsOnMapOf(state()).overlay)).toEqual(['a1']);
    act(() => state().toggleSelected('a1'));
    expect(resultsOnMapOf(state()).overlay).toEqual([]);
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

  it('the scene ticked again shows its quicklook like any other and leaves the view alone', async () => {
    act(() => { state().toggleSelected('a0'); useAppStore.setState({ dock: 'results' }); });
    click(buttonWith('Crop to AOI'));
    await flush();
    const view = state().downloaded;
    act(() => state().toggleSelected('a0'));
    expect(idsOf(resultsOnMapOf(state()).overlay)).toEqual(['a0']);
    expect(idsOf(resultsOnMapOf(state()).highlight)).toEqual(['a0']);
    expect(state().focusMode).toBe(true);
    expect(state().downloaded).toBe(view);
    act(() => state().toggleSelected('a0'));
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

  it('the switch says what a click does, and hiding takes everything but a ticked scene off the map', async () => {
    act(() => useAppStore.setState({ dock: 'results' }));
    expect(buttonWith('Hide results').textContent).toBe('Hide results');
    click(buttonWith('Hide results'));
    expect(buttonWith('Show results').textContent).toBe('Show results');
    expectOnlyTickedOnMap();
    // Leaving a view brings nothing back.
    act(() => state().toggleSelected('a0'));
    await openView();
    click(viewButton('Change image'));
    expect(state().resultsOnMap).toBe(false);
    expect(idsOf(resultsOnMapOf(state()).quicklooks)).toEqual(['a0']);
    act(() => state().toggleSelected('a0'));
    expectOnlyTickedOnMap();
    expect(resultsOnMapOf(state()).quicklooks).toEqual([]);
  });
});

describe('"Clear" and "Change image" in the view', () => {
  it('"Clear" takes the view off the map and nothing else: the tick, what was pinned, the switch and the panel stay', async () => {
    const layer = { id: 'pinned', name: 'Pinned', visible: true, opacity: 1, overlays: [], restore: { datasetId: DATASET, itemIds: [], groupItemIds: [], downloaded: {}, appliedRender: {}, selectedIds: [] } } as never;
    act(() => useAppStore.setState({ layers: [layer], resultsOnMap: false, dock: 'controls' }));
    act(() => state().toggleSelected('a0'));
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
    act(() => useAppStore.setState({ dock: 'controls', resultsOnMap: false }));
    act(() => state().toggleSelected('a0'));
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
