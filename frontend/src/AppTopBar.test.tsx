// @vitest-environment jsdom
//
// V-2 (docs/plans/m2/m2-format-und-viewer.md), five findings from Otto's review:
// 1. the theme/projection buttons label the switch's *target* (what clicking
//    gets you), e.g. "Light" while the theme is dark — confirmed with Otto
//    2026-09-23 after an initial state-first reading of the same wording;
// 2. icons: a globe for the globe, a map for the flat view (renamed
//    "Mercator"); the symbol for "Layers" moved to the rail (UI-01, `AppRail.test.tsx`);
// 3. "Zoom to selection" is disabled with neither an AOI nor pinned layers;
// 5. "Add to layers" belongs next to "View full resolution".
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

  it('labels the theme button by the switch target: "Light" while dark, "Dark" while light (point 1)', () => {
    const view = mount();
    expect(btn(view, 'Light')?.textContent).toContain('☀');
    expect(btn(view, 'Dark')).toBeNull();

    act(() => {
      btn(view, 'Light')!.click();
    });
    expect(btn(view, 'Dark')?.textContent).toContain('☾');
    expect(btn(view, 'Light')).toBeNull();
  });

  it('labels the projection button by the switch target: "Globe" while flat, "Mercator" while globe (point 2)', () => {
    const view = mount();
    expect(btn(view, 'Globe')?.textContent).toMatch(/🌐/u);
    expect(btn(view, 'Flat')).toBeNull();
    expect(btn(view, 'Mercator')).toBeNull();

    act(() => {
      btn(view, 'Globe')!.click();
    });
    expect(btn(view, 'Mercator')?.textContent).toMatch(/🗺/u);
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

  it('offers "Add to layers" next to the full-resolution buttons (point 5)', () => {
    const view = mount();
    const bar = view.querySelector('.download-bar');
    expect(bar).not.toBeNull();
    // M3-09: one "View full resolution" button became two ("Crop & merge to
    // AOI" / "View full selection"), grouped under a shared "Full resolution"
    // label so it stays clear both lead to the same full-resolution view.
    expect(bar!.querySelector('[aria-label="View full resolution"]')).not.toBeNull();
    expect(btn(bar as HTMLElement, 'Crop & merge to AOI')).not.toBeNull();
    expect(btn(bar as HTMLElement, 'View full selection')).not.toBeNull();
    expect(btn(bar as HTMLElement, 'Add to layers')).not.toBeNull();
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
    error: null,
    cancelling: false,
    expired: false,
    tiles: null,
    statistics: null,
    range: null,
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

  it('folds the results list away under the side bar, without its toggle, and centres the bottom bar beside it', () => {
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
    useAppStore.setState({ sections: [section], resultsPanelCollapsed: false });
    const view = mount();
    expect(view.querySelector('.results-dock.collapsed')).toBeNull();
    expect(view.querySelector('.results-toggle')).not.toBeNull();
    act(() => useProcessingStore.setState({ open: true }));
    expect(view.querySelector('.results-dock.collapsed')).not.toBeNull();
    expect(view.querySelector('.results-toggle')).toBeNull();
    expect(view.querySelector('.overlay.bottom.beside-sheet')).not.toBeNull();
    expect(useAppStore.getState().resultsPanelCollapsed).toBe(false);
  });

  it('puts the panel in the side bar and the manager beside the rail', () => {
    useProcessingStore.setState({ open: true });
    useAppStore.setState({ dock: 'jobs' });
    const view = mount();
    expect(view.querySelector('.processing-sheet [aria-label="Processing"]')).not.toBeNull();
    expect(view.querySelector('.dock .processing-manager')).not.toBeNull();
  });
});
