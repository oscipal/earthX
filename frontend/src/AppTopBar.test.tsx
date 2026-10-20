// @vitest-environment jsdom
//
// V-2 (docs/plans/m2-format-und-viewer.md), five findings from Otto's review:
// 1. the theme/projection buttons label the switch's *target* (what clicking
//    gets you), e.g. "Light" while the theme is dark — confirmed with Otto
//    2026-09-23 after an initial state-first reading of the same wording;
// 2. icons: a globe for the globe, a map for the flat view (renamed
//    "Mercator"), three horizontal bars for "Layers";
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

  it('uses three horizontal bars for "Layers" (point 2)', () => {
    const view = mount();
    expect(btn(view, 'Layers')?.textContent).toContain('☰');
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

// M4-13c §3.1: the panel that builds an order is a side bar; the jobs have a
// window of their own, opened by "⚙ Jobs (n)".
describe('the processing side bar and the window of the jobs', () => {
  const JOB: JobEntry = {
    jobID: 'AbCdEfGhIjKlMnOpQrSt_-',
    expires: new Date(Date.now() + 86_400_000).toISOString(),
    status: null,
    phase: 'active',
    files: null,
    resampled: null,
    failure: null,
    error: null,
    cancelling: false,
    expired: false,
    title: null,
  };

  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
    useAppStore.setState({ groups: [], items: [], selectedIds: [], focusMode: false });
    useProcessingStore.setState({ open: false, jobsOpen: false, jobs: [JOB] });
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    useProcessingStore.setState({ open: false, jobsOpen: false, jobs: [] });
    useAppStore.setState({ sections: [] });
    vi.unstubAllGlobals();
  });

  it('opens the jobs, not the panel, from "⚙ Jobs (n)"', () => {
    const view = mount();
    act(() => btn(view, 'Jobs (1)')!.click());
    expect(useProcessingStore.getState().jobsOpen).toBe(true);
    expect(useProcessingStore.getState().open).toBe(false);
    expect(view.querySelector('.jobs-dock [aria-label="Jobs"]')).not.toBeNull();
    expect(btn(view, 'Jobs (1)')).toBeNull();
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

  it('puts the panel in the side bar and the jobs beside it', () => {
    useProcessingStore.setState({ open: true, jobsOpen: true });
    const view = mount();
    expect(view.querySelector('.processing-sheet [aria-label="Processing"]')).not.toBeNull();
    expect(view.querySelector('.jobs-dock.beside-sheet')).not.toBeNull();
  });
});
