// @vitest-environment jsdom
//
// The map below a dataset's lowest released level (M2-10). Until 10.11.2026 a standing line over the map said "Zoom in to
// level n to see imagery …"; Otto dropped it: the tooltip of the row "Search results" in the layer manager says why the
// results show nothing (`LayerManager.test.tsx`). `App` is mounted whole, so that no part of the interface says it over
// the map either.
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
  id: 'synthetic-zarr',
  title: 'Synthetic Zarr dataset',
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
      dock: null,
    });
  });
  return container;
}

describe('the map below a dataset’s lowest released level (Otto, 10.11.2026)', () => {
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

  it.each([5, 2, 8])('stands nothing over the map at zoom %i: the row of the results in the layer manager says why', (zoom) => {
    const shown = show(ZARR_LIKE, zoom);
    expect(shown.textContent).not.toContain('Zoom in');
    expect(shown.textContent).not.toContain('Nothing shown at this zoom');
    expect(shown.querySelector('.toast.hint')).toBeNull();
  });

  it('stands nothing for a dataset released from z0 either', () => {
    expect(show(COG_LIKE, 0).querySelector('.status-stack')?.textContent ?? '').toBe('');
  });
});
