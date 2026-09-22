// The one piece of the store M2-10 changed that is testable without a map:
// pinning the active time step into the layer manager. Before M2-10 a scene
// whose source publishes no quicklook produced no overlay at all, so pinning a
// time step of `sentinel-2-l2a-zarr3` yielded "Nothing to add".

import { beforeEach, describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import { useAppStore } from './store';
import type { Collection, StacItem } from './types';

const ZARR_LIKE: Collection = {
  id: 'sentinel-2-l2a-zarr3',
  title: 'Sentinel-2 L2A (Zarr3)',
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14 },
  'earthx:default_render': {
    title: 'True colour',
    assets: ['SR_10m:b04,b03,b02'],
    rescale: [[0, 0.3]],
    colormap_name: null,
    expression: null,
    resampling: 'nearest',
  },
};

const COG_LIKE: Collection = {
  id: 'sentinel-2-c1-l2a',
  title: 'Sentinel-2 L2A',
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 19 },
};

function scene(overrides: Partial<StacItem> = {}): StacItem {
  return {
    id: 'S2B_1',
    bbox: [10, 47, 11, 48],
    properties: { datetime: '2026-07-24T10:00:00Z' },
    assets: { SR_10m: { href: 'https://data.test/x.zarr/r10m', roles: ['data'] } },
    ...overrides,
  };
}

function pin(collection: Collection, items: StacItem[]) {
  useAppStore.setState({
    datasets: datasetsFrom([collection]),
    datasetId: collection.id,
    items,
    groups: [{ key: ['2026-07-24'], label: '2026-07-24', items }],
    activeGroupIndex: 0,
    selectedIds: [],
    focusMode: false,
    layers: [],
    error: null,
    notice: null,
  });
  useAppStore.getState().addCurrentToLayers();
  return useAppStore.getState();
}

describe('addCurrentToLayers while browsing', () => {
  beforeEach(() => {
    useAppStore.setState({ layers: [], error: null, notice: null });
  });

  it('pins tiles for a source that publishes no quicklook', () => {
    const state = pin(ZARR_LIKE, [scene()]);

    expect(state.error).toBeNull();
    expect(state.layers).toHaveLength(1);
    const [overlay] = state.layers[0].overlays;
    expect(overlay.kind).toBe('raster');
    if (overlay.kind !== 'raster') return;
    expect(overlay.minZoom).toBe(8);
    expect(overlay.maxZoom).toBe(8);
    expect(new URL(overlay.tileUrl, 'http://x').searchParams.get('rescale')).toBe('0,0.3');
  });

  it('a pinned preview is not downloadable — it is not a full-resolution view', () => {
    // `download.downloadRequestFor` needs `restore.focusMode`, and a browse
    // layer has none. The check lives here because pinning tiles in browse mode
    // is new, and a preview must not turn into an export path by looking like
    // one (KLAERUNGEN B11: a crop hands out the source's pixels).
    const state = pin(ZARR_LIKE, [scene()]);
    expect(state.layers[0].restore.focusMode).toBe(false);
  });

  it('a scene with no bounding box is skipped, not placed wrongly', () => {
    const state = pin(ZARR_LIKE, [scene({ bbox: null })]);
    expect(state.layers).toHaveLength(0);
    expect(state.error).toMatch(/Nothing to add/);
  });

  it('a dataset with neither quicklook nor standard visualisation still says so', () => {
    const state = pin(COG_LIKE, [scene()]);
    expect(state.layers).toHaveLength(0);
    expect(state.error).toMatch(/Nothing to add/);
  });
});
