// @vitest-environment jsdom
//
// The hint below a dataset's lowest released level (M2-10), where it has to be
// seen rather than merely rendered.
//
// The bug this covers was never in the rule: the hint sat in the control panel,
// which `runSearch` slides off screen, so it was never once visible in the
// situation it is for (found locally by Otto, 22.09.2026). A test of the rule
// could not have caught that, and neither could a test that mounts one
// component in isolation — it would pass just as well with the hint back inside
// the panel. So `App` is mounted whole and the assertion is about *where* the
// hint ends up: outside the dock that collapses.
//
// This one file asks for a DOM; the rest of the suite stays on plain node.
// Rendered as a client, not to static markup, because zustand hands a server
// render its *initial* state — a static render would see an empty store
// whatever the test set. `MapView` is replaced by nothing: it is the only part
// of the tree that wants WebGL, and it draws no part of the interface this is
// about.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from '../App';
import { datasetsFrom } from '../datasets';
import { useAppStore } from '../store';
import type { Collection } from '../types';

vi.mock('./MapView', () => ({ default: () => null }));

// React only honours `act`'s flush guarantees when a test environment says so,
// and without the flag it prints the reminder on every render.
declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

// `App` loads the dataset list on mount; the store state each case sets is what
// these assertions are about, so the request is answered with nothing rather
// than left to reach a network that is not there.
beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ collections: [] }), { status: 200 })),
  );
});

const CAPABILITIES = {
  roi: true,
  time_range: true,
  band_math: true,
  interpolation: true,
  ml_processing: true,
  quad_pol: false,
  single_coverage_product: false,
};

const ZARR_LIKE: Collection = {
  id: 'sentinel-2-l2a-zarr3',
  title: 'Sentinel-2 L2A (Zarr3)',
  'earthx:capabilities': CAPABILITIES,
  'earthx:viewer': {
    group_by: ['datetime'],
    min_zoom: 8,
    max_zoom: 14,
    browse: 'preview_tiles',
    quicklook_nodata_max: null,
    results_group_by: ['datetime'],
  },
};

const COG_LIKE: Collection = {
  id: 'sentinel-2-c1-l2a',
  title: 'Sentinel-2 L2A',
  'earthx:capabilities': CAPABILITIES,
  'earthx:viewer': {
    group_by: ['datetime'],
    min_zoom: 0,
    max_zoom: 19,
    browse: 'quicklook',
    quicklook_nodata_max: 16,
    results_group_by: ['datetime'],
  },
};

let container: HTMLDivElement;
let root: Root;

function show(collection: Collection, mapZoom: number): HTMLElement {
  act(() => {
    root.render(<App />);
  });
  act(() => {
    useAppStore.setState({
      datasets: datasetsFrom([collection]),
      datasetId: collection.id,
      mapZoom,
      groups: [],
      layers: [],
      error: null,
      notice: null,
      searching: false,
      downloading: false,
      // Exactly as `runSearch` leaves it: the panel that used to carry this hint
      // is off screen in this state, which is what the cases below are about.
      panelCollapsed: true,
    });
  });
  return container;
}

function hintOf(root_: HTMLElement): HTMLElement | null {
  return [...root_.querySelectorAll<HTMLElement>('[role="status"]')].find((el) =>
    (el.textContent ?? '').includes('Zoom in to level'),
  ) ?? null;
}

describe('the hint below a dataset’s lowest released level', () => {
  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  it('says why the map is empty, naming the level and the dataset', () => {
    const text = hintOf(show(ZARR_LIKE, 5))?.textContent ?? '';
    expect(text).toContain('Zoom in to level 8');
    expect(text).toContain('Sentinel-2 L2A (Zarr3)');
    expect(text).toContain('coverage layer');
  });

  it('does not sit inside the panel that slides away', () => {
    // The whole bug in one assertion: the hint used to live in `.panel-dock`,
    // which carries `collapsed` in this very state and is moved off screen by a
    // CSS transform — visible to neither the type check nor a test of the rule.
    const hint = hintOf(show(ZARR_LIKE, 5));
    const dock = container.querySelector('.panel-dock');

    expect(hint).not.toBeNull();
    expect(dock?.classList.contains('collapsed')).toBe(true);
    expect(dock?.contains(hint!)).toBe(false);
  });

  it('shows without a search, which is when a dataset switch explains it best', () => {
    // `setDatasetId` clears the results, so anything gated on them would be off
    // at exactly the moment someone picks the dataset with the higher floor.
    expect(hintOf(show(ZARR_LIKE, 2))).not.toBeNull();
  });

  it('is gone at the floor itself — the floor is released', () => {
    expect(hintOf(show(ZARR_LIKE, 8))).toBeNull();
  });

  it('never appears for a dataset released from z0', () => {
    expect(hintOf(show(COG_LIKE, 0))).toBeNull();
  });

  it('carries no dismiss button and takes no clicks away from the map', () => {
    const hint = hintOf(show(ZARR_LIKE, 5));
    expect(hint?.querySelector('button')).toBeNull();
    // The stack crosses the buttons at the top right on an ordinary laptop
    // width; a standing hint that took pointer events would swallow them.
    expect(hint?.className).toContain('hint');
  });
});
