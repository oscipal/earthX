// @vitest-environment jsdom
//
// NM4-50 (Otto, 28.10.2026): a layer keeps the colormap and the range it was made with. Choosing it in the layer manager
// shows them in the controls of its view, the same for a dataset with quicklooks (Sentinel-2) and for one without (the DEM).

import { beforeEach, describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import type { MapLayer } from './layers';
import { pendingFieldsOf } from './render';
import { useAppStore } from './store';
import type { Collection } from './types';

const CAPABILITIES = { roi: true, time_range: true, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, single_coverage_product: false };

const collection = (id: string, browse: 'quicklook' | 'full_resolution'): Collection => ({
  id,
  title: id,
  'earthx:capabilities': CAPABILITIES,
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse, quicklook_nodata_max: browse === 'quicklook' ? 16 : null, results_group_by: ['datetime'] },
  'earthx:default_render': { title: 'Standard', assets: ['visual'], rescale: [[0, 255]], colormap_name: null, expression: null, resampling: 'nearest' },
});

const layerOf = (datasetId: string, render: { colormapName?: string; rescale?: string }): MapLayer => ({
  id: `L-${datasetId}`,
  name: datasetId,
  visible: true,
  opacity: 1,
  overlays: [],
  restore: {
    focusMode: true,
    downloaded: { a: { tileUrl: `/collections/${datasetId}/items/a/tiles/{z}/{x}/{y}`, bounds: [0, 0, 1, 1], asset: 'visual', minZoom: 8, maxZoom: 14 } },
    appliedRender: render,
    activeGroupIndex: 0,
    selectedIds: ['a'],
    itemIds: ['a'],
    groupItemIds: [['a']],
    aoi: null,
    cropToAoi: false,
    datasetId,
  },
});

describe('pendingFieldsOf', () => {
  it('splits a look into the fields of the controls', () => {
    expect(pendingFieldsOf({ colormapName: 'viridis', rescale: '10,2900' })).toEqual({ pendingColormapName: 'viridis', pendingVmin: '10', pendingVmax: '2900' });
  });

  it('leaves the fields empty for a look without colormap or range, or a range that is not a pair', () => {
    expect(pendingFieldsOf({})).toEqual({ pendingColormapName: '', pendingVmin: '', pendingVmax: '' });
    expect(pendingFieldsOf({ rescale: '5' })).toEqual({ pendingColormapName: '', pendingVmin: '5', pendingVmax: '' });
  });
});

describe.each([
  ['the DEM', 'dem', 'full_resolution'],
  ['Sentinel-2', 's2', 'quicklook'],
] as const)('choosing a layer of %s', (_name, id, browse) => {
  beforeEach(() => {
    useAppStore.setState({
      datasets: datasetsFrom([collection(id, browse)]),
      selectedDatasetIds: [id],
      datasetId: id,
      layers: [layerOf(id, { colormapName: 'viridis', rescale: '10,2900' })],
      focusMode: false,
      downloaded: {},
      appliedRender: {},
      pendingColormapName: 'magma',
      pendingVmin: '5',
      pendingVmax: '9',
      viewLayerId: null,
    });
  });

  it('shows what the layer was made with in the controls, not what the last view had in them', () => {
    useAppStore.getState().selectLayer(`L-${id}`);
    const s = useAppStore.getState();
    expect(s.appliedRender).toEqual({ colormapName: 'viridis', rescale: '10,2900' });
    expect([s.pendingColormapName, s.pendingVmin, s.pendingVmax]).toEqual(['viridis', '10', '2900']);
  });

  it('keeps them over hiding and showing the layer, and over a move in the list', () => {
    const layer = () => useAppStore.getState().layers.find((l) => l.id === `L-${id}`)!;
    useAppStore.getState().toggleLayerVisible(`L-${id}`);
    useAppStore.getState().toggleLayerVisible(`L-${id}`);
    useAppStore.getState().moveLayer(`L-${id}`, 'down');
    expect(layer().restore.appliedRender).toEqual({ colormapName: 'viridis', rescale: '10,2900' });
    useAppStore.getState().selectLayer(`L-${id}`);
    expect(useAppStore.getState().pendingColormapName).toBe('viridis');
  });

  it('is the view of the layer while nothing differs, so that the eye of the layer is the eye of the picture', () => {
    useAppStore.getState().selectLayer(`L-${id}`);
    expect(useAppStore.getState().viewLayerId).toBe(`L-${id}`);
  });
});
