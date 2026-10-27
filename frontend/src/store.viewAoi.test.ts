// @vitest-environment jsdom
// Otto, 27.10.2026 (zu #211): a view cropped to the AOI keeps the AOI it was opened with. Drawing, changing or clearing
// the area in the control menu leaves the open view alone; the whole scene is "View whole scene".

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { bboxToPolygon } from './geoUtils';
import { useProcessingStore } from './processingStore';
import { useAppStore } from './store';
import type { Collection, StacItem } from './types';
import { viewLayerOf } from './viewLayer';

const ID = 'optical';
const COLLECTION = {
  id: ID,
  title: 'Optical',
  'earthx:format': 'cog',
  'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 19, browse: 'preview_tiles', quicklook_nodata_max: null, results_group_by: ['datetime'] },
  'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
} as unknown as Collection;

const AOI_ONE = bboxToPolygon([10.1, 47.1, 10.4, 47.4]);
const AOI_TWO = bboxToPolygon([10.6, 47.6, 10.9, 47.9]);
const scene = (id: string): StacItem => ({ id, bbox: [10, 47, 11, 48], properties: { datetime: '2026-07-24T10:00:00Z' }, assets: {} });

const state = () => useAppStore.getState();

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 404 })));
  const items = ['A', 'B'].map(scene);
  useAppStore.setState({
    datasets: datasetsFrom([COLLECTION]), selectedDatasetIds: [ID], datasetId: ID, items,
    groups: [{ key: ['2026-07-24'], label: '2026-07-24', items }], activeGroupIndex: 0, expandedGroupIndex: 0,
    selectedIds: ['A'], focusMode: false, cropToAoi: false, viewAoi: null, downloaded: {}, appliedRender: {}, mosaics: {},
    layers: [], viewLayerId: null, aoi: AOI_ONE, error: null, notice: null, pinLoading: false,
  });
});
afterEach(() => vi.unstubAllGlobals());

describe('the area of a cropped view', () => {
  it('is the area it was opened with', async () => {
    await state().enterFocus(true);
    expect(state().viewAoi).toEqual(AOI_ONE);
    expect(state().cropToAoi).toBe(true);
  });

  it('is none for a view of the whole scene', async () => {
    await state().enterFocus(false);
    expect(state().viewAoi).toBeNull();
    expect(state().cropToAoi).toBe(false);
  });

  it.each([
    ['clearing the area', () => state().clearAoi()],
    ['drawing another', () => state().setAoi(AOI_TWO)],
    ['setting it to nothing', () => state().setAoi(null)],
    ['taking the last one again', () => { state().setAoi(AOI_TWO); state().clearAoi(); state().useLastAoi(); }],
  ])('is not changed by %s in the control menu, and neither is the view', async (_name, change) => {
    await state().enterFocus(true);
    const before = { viewAoi: state().viewAoi, cropToAoi: state().cropToAoi, downloaded: state().downloaded, focusMode: state().focusMode };
    change();
    expect(state().viewAoi).toEqual(AOI_ONE);
    expect(state().cropToAoi).toBe(before.cropToAoi);
    expect(state().downloaded).toBe(before.downloaded);
    expect(state().focusMode).toBe(true);
  });

  it('goes with the view: left, cleared, or another view opened', async () => {
    await state().enterFocus(true);
    state().exitFocus();
    expect(state().viewAoi).toBeNull();
    await state().enterFocus(true);
    state().exitFocus();
    expect(state().viewAoi).toBeNull();
    await state().enterFocus(true);
    state().clearAoi();
    await state().enterFocus(false);
    expect(state().viewAoi).toBeNull();
  });

  it('a crop cannot be opened without an area, and then there is no view', async () => {
    useAppStore.setState({ aoi: null });
    await state().enterFocus(true);
    expect(state().focusMode).toBe(false);
    expect(state().viewAoi).toBeNull();
  });

  it('is cut to the new area when the view is opened again after the change', async () => {
    await state().enterFocus(true);
    state().setAoi(AOI_TWO);
    expect(state().viewAoi).toEqual(AOI_ONE);
    await state().enterFocus(true);
    expect(state().viewAoi).toEqual(AOI_TWO);
  });
});

describe('what follows the area of the view, not the one in the control menu', () => {
  it('"Add to layers" pins the crop of the area the view has', async () => {
    await state().enterFocus(true);
    state().clearAoi();
    state().addCurrentToLayers();
    const { layers } = state();
    expect(layers).toHaveLength(1);
    expect(layers[0].restore.cropToAoi).toBe(true);
    expect(layers[0].restore.aoi).toEqual(AOI_ONE);
  });

  it('the layer pinned from the view is the picture of the view, still', async () => {
    await state().enterFocus(true);
    state().addCurrentToLayers();
    const s = state();
    expect(viewLayerOf(s.layers, { viewLayerId: s.viewLayerId, focusMode: s.focusMode, downloaded: s.downloaded, appliedRender: s.appliedRender, cropToAoi: s.cropToAoi, aoi: s.viewAoi, showDownloaded: s.showDownloaded })?.id).toBe(s.layers[0]?.id);
    // The area in the control menu is not what decides it.
    state().setAoi(AOI_TWO);
    expect(viewLayerOf(state().layers, { viewLayerId: state().viewLayerId, focusMode: true, downloaded: state().downloaded, appliedRender: state().appliedRender, cropToAoi: true, aoi: state().viewAoi, showDownloaded: true })).not.toBeNull();
  });

  it('"Process" of the view takes the area of the view as the order\'s area', async () => {
    await state().enterFocus(true);
    state().setAoi(AOI_TWO);
    await useProcessingStore.getState().processFocusView();
    expect(useProcessingStore.getState().area).toBe('aoi');
    expect(state().aoi).toEqual(AOI_ONE);
  });

  it('"Process" of the view, with the area cleared, still takes the area of the view', async () => {
    await state().enterFocus(true);
    state().clearAoi();
    await useProcessingStore.getState().processFocusView();
    expect(useProcessingStore.getState().area).toBe('aoi');
    expect(state().aoi).toEqual(AOI_ONE);
  });

  it('"Process" of a whole-scene view leaves the area alone and takes the scene', async () => {
    await state().enterFocus(false);
    state().setAoi(AOI_TWO);
    await useProcessingStore.getState().processFocusView();
    expect(useProcessingStore.getState().area).toBe('scene');
    expect(state().aoi).toEqual(AOI_TWO);
  });
});

describe('a view of a pinned layer', () => {
  it('has the area of the layer, and the area in the control menu does not move it', async () => {
    const layer = {
      id: 'L1', name: 'Layer', visible: true, opacity: 1, overlays: [],
      restore: { focusMode: true, downloaded: {}, appliedRender: {}, activeGroupIndex: 0, selectedIds: ['A'], itemIds: ['A'], groupItemIds: [['A']], aoi: AOI_TWO, cropToAoi: true, datasetId: ID },
    } as never;
    useAppStore.setState({ layers: [layer] });
    state().selectLayer('L1');
    expect(state().viewAoi).toEqual(AOI_TWO);
    state().clearAoi();
    expect(state().viewAoi).toEqual(AOI_TWO);
  });

  it('has none for a layer that is not cropped', () => {
    const layer = {
      id: 'L2', name: 'Layer', visible: true, opacity: 1, overlays: [],
      restore: { focusMode: true, downloaded: {}, appliedRender: {}, activeGroupIndex: 0, selectedIds: ['A'], itemIds: ['A'], groupItemIds: [['A']], aoi: AOI_TWO, cropToAoi: false, datasetId: ID },
    } as never;
    useAppStore.setState({ layers: [layer] });
    state().selectLayer('L2');
    expect(state().viewAoi).toBeNull();
  });
});
