// @vitest-environment jsdom
//
// V-2 (docs/plans/m2-format-und-viewer.md), five findings from Otto's review:
// 1. the theme button must label the current state, not the switch's effect;
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

  it('labels the theme button by the active theme, not by the switch target (point 1)', () => {
    const view = mount();
    expect(btn(view, 'Dark')?.textContent).toContain('☾');

    act(() => {
      btn(view, 'Dark')!.click();
    });
    expect(btn(view, 'Light')?.textContent).toContain('☀');
    expect(btn(view, 'Dark')).toBeNull();
  });

  it('uses a globe icon for the globe and a map icon for the (renamed) Mercator view (point 2)', () => {
    const view = mount();
    expect(btn(view, 'Mercator')?.textContent).toMatch(/🗺/u);
    expect(btn(view, 'Flat')).toBeNull();

    act(() => {
      btn(view, 'Mercator')!.click();
    });
    expect(btn(view, 'Globe')?.textContent).toMatch(/🌐/u);
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

  it('offers "Add to layers" next to "View full resolution" (point 5)', () => {
    const view = mount();
    const bar = view.querySelector('.download-bar');
    expect(bar).not.toBeNull();
    expect(btn(bar as HTMLElement, 'View full resolution')).not.toBeNull();
    expect(btn(bar as HTMLElement, 'Add to layers')).not.toBeNull();
  });
});
