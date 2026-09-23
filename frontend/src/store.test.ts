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

// V-2 point 3: "Zoom to selection" zooms to the AOI; failing that, to the
// pinned layer images; failing that too, it has nothing to do (App.tsx's
// `canZoom` then keeps the button disabled).
describe('zoomToView', () => {
  const AOI: GeoJSON.Geometry = {
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
  };

  beforeEach(() => {
    useAppStore.setState({ aoi: null, layers: [], flyToBbox: null });
  });

  it('prefers the AOI over pinned layers', () => {
    useAppStore.setState({
      aoi: AOI,
      layers: [
        {
          id: 'L1',
          name: 'x',
          visible: true,
          opacity: 1,
          overlays: [{ kind: 'raster', tileUrl: 'x', bounds: [40, 40, 41, 41], minZoom: 1, maxZoom: 1 }],
          restore: {
            focusMode: false,
            downloaded: {},
            appliedRender: {},
            activeGroupIndex: 0,
            selectedIds: [],
            itemIds: [],
            aoi: null,
            datasetId: null,
          },
        },
      ],
    });
    useAppStore.getState().zoomToView();
    expect(useAppStore.getState().flyToBbox).toEqual([1, 1, 2, 2]);
  });

  it('falls back to the pinned layer images without an AOI, raster and image overlays alike', () => {
    useAppStore.setState({
      layers: [
        {
          id: 'L1',
          name: 'x',
          visible: true,
          opacity: 1,
          overlays: [
            { kind: 'raster', tileUrl: 'x', bounds: [10, 10, 11, 11], minZoom: 1, maxZoom: 1 },
            {
              kind: 'image',
              url: 'x',
              coords: [
                [20, 21],
                [22, 21],
                [22, 20],
                [20, 20],
              ],
            },
          ],
          restore: {
            focusMode: false,
            downloaded: {},
            appliedRender: {},
            activeGroupIndex: 0,
            selectedIds: [],
            itemIds: [],
            aoi: null,
            datasetId: null,
          },
        },
      ],
    });
    useAppStore.getState().zoomToView();
    expect(useAppStore.getState().flyToBbox).toEqual([10, 10, 22, 21]);
  });

  it('does nothing with neither an AOI nor pinned layers', () => {
    useAppStore.getState().zoomToView();
    expect(useAppStore.getState().flyToBbox).toBeNull();
  });
});

// V-11: the results list can collapse its open group without moving
// activeGroupIndex (the time step the map/time slider show) — and MapView
// hides quicklooks whenever nothing is expanded, so this has to actually
// happen, not just look right in the panel.
describe('toggleResultsGroup', () => {
  const a = { id: 'a', properties: { datetime: '2026-07-25T10:00:00Z' }, assets: {} };
  const b = { id: 'b', properties: { datetime: '2026-07-24T10:00:00Z' }, assets: {} };

  beforeEach(() => {
    useAppStore.setState({
      groups: [
        { key: ['2026-07-25'], label: '2026-07-25', items: [a] },
        { key: ['2026-07-24'], label: '2026-07-24', items: [b] },
      ],
      activeGroupIndex: 0,
      expandedGroupIndex: 0,
    });
  });

  it('collapses the open group without touching activeGroupIndex', () => {
    useAppStore.getState().toggleResultsGroup(0);
    const s = useAppStore.getState();
    expect(s.expandedGroupIndex).toBeNull();
    expect(s.activeGroupIndex).toBe(0);
  });

  it('opening a different group expands it and moves activeGroupIndex along', () => {
    useAppStore.getState().toggleResultsGroup(1);
    const s = useAppStore.getState();
    expect(s.expandedGroupIndex).toBe(1);
    expect(s.activeGroupIndex).toBe(1);
  });

  it('re-opening the collapsed group restores both', () => {
    useAppStore.getState().toggleResultsGroup(0); // collapse
    useAppStore.getState().toggleResultsGroup(0); // re-open the same one
    const s = useAppStore.getState();
    expect(s.expandedGroupIndex).toBe(0);
    expect(s.activeGroupIndex).toBe(0);
  });

  it('setActiveGroupIndex (time slider, "play") re-syncs expandedGroupIndex even after a manual collapse', () => {
    useAppStore.getState().toggleResultsGroup(0); // collapse
    useAppStore.getState().setActiveGroupIndex(1); // scrub the time slider
    const s = useAppStore.getState();
    expect(s.activeGroupIndex).toBe(1);
    expect(s.expandedGroupIndex).toBe(1);
  });
});
