// @vitest-environment jsdom
//
// V-2 (docs/plans/m2/m2-format-und-viewer.md), five findings from Otto's review:
// 1. the theme/projection buttons (gone with UI-04 part 4: the menu of "Settings" has them, `SettingsMenu.test.tsx`);
// 2. (icons for the projection: replaced by the "Basemap" menu, UI-02a; the symbol for "Layers" moved to the
//    rail, UI-01, `AppRail.test.tsx`);
// 3. "Zoom to selection" is disabled with neither an AOI nor pinned layers;
// 5. "Add to layers" belonged next to "View full resolution" (gone from the bar with UI-01g).
// Point 4 (the date input's calendar icon in dark mode) is CSS-only and not
// checkable from jsdom, which does not render native form-control chrome.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';
import { useProcessingStore, type JobEntry } from './processingStore';
import type { ResultSection } from './sections';
import { useAppStore } from './store';
import type { StacItem } from './types';

vi.mock('./components/MapView', () => ({ default: () => null }));

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ collections: [] }), { status: 200 })),
  );
});

let container: HTMLDivElement;
let root: Root;

function mount(): HTMLElement {
  act(() => {
    root.render(<App />);
  });
  return container;
}

function btn(root_: HTMLElement, text: string): HTMLButtonElement | null {
  return (
    [...root_.querySelectorAll<HTMLButtonElement>('button')].find((b) =>
      (b.textContent ?? '').includes(text),
    ) ?? null
  );
}

describe('top-right map controls', () => {
  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
    useAppStore.setState({
      aoi: null,
      layers: [],
      groups: [],
      selectedIds: [],
      theme: 'tech',
      projection: 'mercator',
    });
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  it('has no button for the theme any more: "Light", "Dark" and "System" are in the menu of "Settings" (UI-04 part 4)', () => {
    const view = mount();
    const bar = view.querySelector<HTMLElement>('.top-right')!;
    expect(btn(bar, 'Light')).toBeNull();
    expect(btn(bar, 'Dark')).toBeNull();
    expect(view.querySelector('.app')?.getAttribute('data-theme')).toBe('tech');
    act(() => {
      view.querySelector<HTMLButtonElement>('button.rail-settings')!.click();
    });
    act(() => {
      [...document.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]')].find((e) => e.textContent === 'Light')!.click();
    });
    expect(view.querySelector('.app')?.getAttribute('data-theme')).toBe('normal');
  });

  it('has no "Basemap" button and none for the projection: the menu of "Settings" has both (UI-02a, UI-04 part 4)', () => {
    const view = mount();
    const bar = view.querySelector<HTMLElement>('.top-right')!;
    expect(btn(bar, 'Basemap')).toBeNull();
    expect(btn(bar, 'Globe')).toBeNull();
    expect(btn(bar, 'Mercator')).toBeNull();
    expect(view.querySelector('button.rail-settings')).not.toBeNull();
  });

  it('puts the projection in the menu of "Settings", and back', () => {
    const view = mount();
    const choose = (name: string) =>
      act(() => {
        [...document.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]')].find((e) => e.textContent === name)!.click();
      });
    act(() => {
      view.querySelector<HTMLButtonElement>('button.rail-settings')!.click();
    });
    choose('Globe');
    expect(useAppStore.getState().projection).toBe('globe');
    choose('Mercator');
    expect(useAppStore.getState().projection).toBe('mercator');
    expect(btn(view.querySelector<HTMLElement>('.top-right')!, 'Mercator')).toBeNull();
  });

  it('keeps "Layers" and "Jobs" off the top right: their symbols are in the rail (UI-01 §6.9)', () => {
    const view = mount();
    expect(view.querySelector('.top-right')).not.toBeNull();
    expect(btn(view.querySelector<HTMLElement>('.top-right')!, 'Layers')).toBeNull();
    expect(btn(view.querySelector<HTMLElement>('.top-right')!, 'Jobs')).toBeNull();
  });

  it('disables "Zoom to selection" with neither an AOI nor pinned layers, and enables it once one exists (point 3)', () => {
    const view = mount();
    expect(btn(view, 'Zoom to selection')?.disabled).toBe(true);
    // A locked button says why (`TipLayer` shows it in either step of the tooltips).
    expect(btn(view, 'Zoom to selection')?.getAttribute('data-tip')).toBe('Nothing to zoom to: draw an AOI, open an image or show a layer');

    act(() => {
      useAppStore.setState({
        aoi: {
          type: 'Polygon',
          coordinates: [
            [
              [1, 1],
              [2, 1],
              [2, 2],
              [1, 2],
              [1, 1],
            ],
          ],
        },
      });
    });
    expect(btn(view, 'Zoom to selection')?.disabled).toBe(false);
    expect(btn(view, 'Zoom to selection')?.getAttribute('data-tip')).toMatch(/^Zoom the map to fit/u);
  });
});

describe('the selection bar', () => {
  const ITEM: StacItem = {
    id: 'S2B_1',
    bbox: [10, 47, 11, 48],
    properties: { datetime: '2026-07-24T10:00:00Z' },
    assets: { SR_10m: { href: 'https://data.test/x.zarr/r10m', roles: ['data'] } },
  };

  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
    useAppStore.setState({
      groups: [{ key: ['2026-07-24'], label: '2026-07-24', items: [ITEM] }],
      items: [ITEM],
      activeGroupIndex: 0,
      selectedIds: [ITEM.id],
      focusMode: false,
    });
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  it('offers the two full-resolution views, and no "Add to layers" (UI-01g)', () => {
    const view = mount();
    const bar = view.querySelector('.download-bar');
    expect(bar).not.toBeNull();
    // UI-01g: the two views are full resolution without saying so; one scene is selected here.
    expect(btn(bar as HTMLElement, 'Crop to AOI')).not.toBeNull();
    expect(btn(bar as HTMLElement, 'View whole scene')).not.toBeNull();
    expect(btn(bar as HTMLElement, 'Add to layers')).toBeNull();
  });
});

// M4-13c §3.1: the panel that builds an order is a side bar; the jobs are listed in the manager beside the
// rail (UI-01 §6.9).
describe('the processing side bar and the manager of the jobs', () => {
  const JOB: JobEntry = {
    jobID: 'AbCdEfGhIjKlMnOpQrSt_-',
    expires: new Date(Date.now() + 86_400_000).toISOString(),
    status: null,
    phase: 'active',
    archive: null,
    bytes: null,
    resampled: null,
    failure: null,
    failureKind: null,
    normalize: null,
    error: null,
    cancelling: false,
    retrying: false,
    retryRefused: false,
    retryError: null,
    deleting: false,
    deletedUntil: null,
    serverDeleted: false,
    lost: false,
    superseded: false,
    expired: false,
    tiles: null,
    statistics: null,
    bands: [],
    range: null,
    bandRanges: {},
    shownBand: null,
    dates: null,
    archived: false,
    groupId: null,
    batchId: null,
    part: null,
    order: null,
    createdAt: '2026-10-10T12:00:00Z',
    title: null,
    titleDefault: null,
  };

  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
    useAppStore.setState({ groups: [], items: [], selectedIds: [], focusMode: false });
    useProcessingStore.setState({ open: false, jobs: [JOB] });
    useAppStore.setState({ dock: 'controls' });
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    useProcessingStore.setState({ open: false, jobs: [] });
    useAppStore.setState({ sections: [] });
    vi.unstubAllGlobals();
  });

  it('opens the manager, not the panel, from the symbol of the jobs in the rail', () => {
    const view = mount();
    act(() => view.querySelector<HTMLButtonElement>('#rail-jobs')!.click());
    expect(useAppStore.getState().dock).toBe('jobs');
    expect(useProcessingStore.getState().open).toBe(false);
    expect(view.querySelector('.dock .processing-manager')).not.toBeNull();
  });

  it('leaves the results in their panel beside the rail when the side bar opens, and centres the bottom bar beside it', () => {
    const item = { id: 'S2B_1', bbox: [10, 47, 11, 48], properties: {}, assets: {} } as unknown as StacItem;
    const section: ResultSection = {
      datasetId: 'x',
      items: [item],
      groups: [{ key: ['2026-07-24'], label: '2026-07-24', items: [item] }],
      notes: [],
      groupingError: null,
      origin: 'search',
      incomplete: false,
    };
    useAppStore.setState({ sections: [section], dock: 'results' });
    const view = mount();
    expect(view.querySelector('#dock-results')!.hasAttribute('hidden')).toBe(false);
    act(() => useProcessingStore.setState({ open: true }));
    expect(view.querySelector('#dock-results')!.hasAttribute('hidden')).toBe(false);
    expect(view.querySelector('.results-dock, .results-toggle')).toBeNull();
    expect(view.querySelector('.overlay.bottom.beside-sheet')).not.toBeNull();
  });

  it('puts the panel in the side bar and the manager beside the rail', () => {
    useProcessingStore.setState({ open: true });
    useAppStore.setState({ dock: 'jobs' });
    const view = mount();
    expect(view.querySelector('.processing-sheet [aria-label="Processing"]')).not.toBeNull();
    expect(view.querySelector('.dock .processing-manager')).not.toBeNull();
  });
});
