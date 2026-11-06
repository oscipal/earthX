// @vitest-environment jsdom
//
// NM4-50 (Otto, 28.10.2026): a layer keeps the colormap and the range it was made with. Choosing it in the layer manager
// shows them in the controls of its view, the same for a dataset with quicklooks (Sentinel-2) and for one without (the DEM).

import { beforeEach, describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import type { MapLayer } from './layers';
import { pendingFieldsOf } from './render';
import { useAppStore } from './store';
import { viewLayerOf } from './viewLayer';
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
    downloaded: { a: { datasetId, tileUrl: `/collections/${datasetId}/items/a/tiles/{z}/{x}/{y}`, bounds: [0, 0, 1, 1], asset: 'visual', minZoom: 8, maxZoom: 14 } },
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
    expect(pendingFieldsOf({ colormapName: 'viridis', rescale: '10,2900' })).toMatchObject({ pendingColormapName: 'viridis', pendingVmin: '10', pendingVmax: '2900', pendingIndex: '', pendingUnit: 'value' });
  });

  it('leaves the fields empty for a look without colormap or range, or a range that is not a pair', () => {
    expect(pendingFieldsOf({})).toMatchObject({ pendingColormapName: '', pendingVmin: '', pendingVmax: '', pendingIndex: '', pendingUnit: 'value' });
    expect(pendingFieldsOf({ rescale: '5' })).toMatchObject({ pendingColormapName: '', pendingVmin: '5', pendingVmax: '', pendingIndex: '', pendingUnit: 'value' });
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


// Otto, 29.10.2026 (zu #234): "Apply" in the view does not change a pinned layer; "Add to layers" takes the look the view was
// given with "Apply" and nothing that was only typed.
describe.each([
  ['the DEM', 'dem', 'full_resolution'],
  ['Sentinel-2', 's2', 'quicklook'],
] as const)('the view of %s and its layers', (_name, id, browse) => {
  const overlayUrl = (layer: MapLayer) => (layer.overlays.find((o) => o.kind === 'raster') as { tileUrl: string } | undefined)?.tileUrl ?? '';

  beforeEach(() => {
    const layer = layerOf(id, { colormapName: 'viridis', rescale: '10,2900' });
    layer.overlays = [{ kind: 'raster', tileUrl: `/collections/${id}/items/a/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual&colormap_name=viridis&rescale=10%2C2900`, bounds: [0, 0, 1, 1], minZoom: 8, maxZoom: 14 }];
    useAppStore.setState({
      datasets: datasetsFrom([collection(id, browse)]),
      selectedDatasetIds: [id],
      datasetId: id,
      layers: [layer],
      items: [],
      groups: [],
      mosaics: {},
      focusMode: false,
      downloaded: {},
      appliedRender: {},
      viewLayerId: null,
      aoi: null,
    });
    useAppStore.getState().selectLayer(`L-${id}`);
  });

  // Otto, 1.11.2026 (Browsertest zu #272): "Apply" in the settings of a layer changes the layer itself (the old rule of M4-28, that it
  // leaves the layer as it was, is gone), at its place; it is kept with "Save" and put back when the settings close without it.
  it('is the picture of the layer, and "Apply" changes this layer at once, with the saved look kept apart', () => {
    const before = useAppStore.getState().layers[0];
    expect(useAppStore.getState().viewLayerId).toBe(`L-${id}`);
    useAppStore.getState().setPendingColormapName('magma');
    useAppStore.getState().applyRender();
    const s = useAppStore.getState();
    expect(s.appliedRender.colormapName).toBe('magma');
    expect(s.layers.map((l) => l.id)).toEqual([before.id]);
    expect(s.layers[0].restore.appliedRender).toMatchObject({ colormapName: 'magma' });
    expect(overlayUrl(s.layers[0])).toContain('colormap_name=magma');
    expect(s.layers[0].saved?.appliedRender).toEqual({ colormapName: 'viridis', rescale: '10,2900' });
    useAppStore.getState().exitFocus();
    expect(useAppStore.getState().layers[0].restore.appliedRender).toEqual({ colormapName: 'viridis', rescale: '10,2900' });
    expect(overlayUrl(useAppStore.getState().layers[0])).toContain('colormap_name=viridis');
  });

  it('takes into "Add to layers" the look that was applied, not what was only typed', () => {
    useAppStore.getState().setPendingColormapName('magma');
    useAppStore.getState().setPendingVmin('1');
    useAppStore.getState().setPendingVmax('50');
    useAppStore.getState().applyRender();
    useAppStore.getState().setPendingColormapName('plasma');
    useAppStore.getState().setPendingVmax('99');
    useAppStore.getState().addCurrentToLayers();
    const [added, original] = useAppStore.getState().layers;
    expect(added.restore.appliedRender).toMatchObject({ colormapName: 'magma', rescale: '1,50' });
    expect(overlayUrl(added)).toContain('colormap_name=magma');
    expect(overlayUrl(added)).toContain('rescale=1%2C50');
    expect(overlayUrl(added)).not.toContain('plasma');
    expect(original.restore.appliedRender).toEqual({ colormapName: 'viridis', rescale: '10,2900' });
  });
});

// Otto, 30.10.2026 (zu #234): a pinned scene layer has the settings of a result layer. Its settings are the controls of its
// view: "Apply" draws the view with the look and leaves the layer as it was, "Save" makes the look the layer's own, and
// what was applied and not saved goes when the settings are closed.
describe.each([
  ['the DEM', 'dem', 'full_resolution', false],
  ['the DEM cropped to the AOI', 'dem', 'full_resolution', true],
  ['Sentinel-2', 's2', 'quicklook', false],
  ['Sentinel-2 cropped to the AOI', 's2', 'quicklook', true],
] as const)('the settings of a pinned layer of %s', (_name, id, browse, cropped) => {
  const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.2]]] };
  const urlOf = (layer: MapLayer) => layer.overlays.filter((o) => o.kind === 'raster').map((o) => (o as { tileUrl: string }).tileUrl).join('|');
  const store = () => useAppStore.getState();
  const layer = () => store().layers.find((l) => l.id === `L-${id}`)!;
  const OTHER = `L-other`;

  beforeEach(() => {
    const own = layerOfView(id, cropped, AOI);
    useAppStore.setState({
      datasets: datasetsFrom([collection(id, browse)]),
      selectedDatasetIds: [id],
      datasetId: id,
      layers: [own, { ...layerOf('other', {}), id: OTHER }],
      items: [],
      groups: [],
      sections: [],
      mosaics: {},
      focusMode: false,
      downloaded: {},
      appliedRender: {},
      viewLayerId: null,
      viewAoi: null,
      aoi: null,
      error: null,
    });
    store().selectLayer(`L-${id}`);
  });

  function layerOfView(datasetId: string, crop: boolean, aoi: GeoJSON.Geometry): MapLayer {
    const made = layerOf(datasetId, { colormapName: 'viridis', rescale: '10,2900' });
    made.restore = { ...made.restore, cropToAoi: crop, aoi: crop ? aoi : null };
    const url = `/collections/${datasetId}/items/a/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual&colormap_name=viridis&rescale=10%2C2900`;
    made.overlays = [{ kind: 'raster', tileUrl: crop ? `earthx-clip://k/${url}` : url, bounds: [0, 0, 1, 1], minZoom: 8, maxZoom: 14 }];
    return made;
  }

  it('are the view of the layer, with its saved look in the fields', () => {
    expect(store().viewLayerId).toBe(`L-${id}`);
    expect([store().pendingColormapName, store().pendingVmin, store().pendingVmax]).toEqual(['viridis', '10', '2900']);
    expect(store().viewAoi).toEqual(cropped ? AOI : null);
  });

  it('"Apply" changes the layer itself, at once, and keeps the saved look apart (Otto, 1.11.2026)', () => {
    store().setPendingColormapName('magma');
    store().applyRender();
    expect(store().appliedRender.colormapName).toBe('magma');
    expect(layer().restore.appliedRender.colormapName).toBe('magma');
    expect(urlOf(layer())).toContain('colormap_name=magma');
    expect(layer().saved?.appliedRender?.colormapName).toBe('viridis');
    expect(store().layers.filter((l) => l.id === `L-${id}`)).toHaveLength(1);
  });

  it('"Save" makes the applied look the layer\'s own: its restore and its tiles, cut the way they were', () => {
    store().setPendingColormapName('magma');
    store().setPendingVmin('1');
    store().setPendingVmax('50');
    store().applyRender();
    store().saveViewLook();
    expect(layer().restore.appliedRender).toMatchObject({ colormapName: 'magma', rescale: '1,50' });
    expect(urlOf(layer())).toContain('colormap_name=magma');
    expect(urlOf(layer())).toContain('rescale=1%2C50');
    expect(urlOf(layer())).not.toContain('viridis');
    expect(urlOf(layer()).startsWith('earthx-clip://')).toBe(cropped);
    expect(layer().restore.cropToAoi).toBe(cropped);
    // The layer is the picture of the view again, at its own place with its own eye.
    expect(viewLayerOf(store().layers, { ...store(), aoi: store().viewAoi })?.id).toBe(`L-${id}`);
  });

  it('"Save" also draws what is typed and not applied', () => {
    store().setPendingVmax('77');
    store().saveViewLook();
    expect(store().appliedRender.rescale).toBe('10,77');
    expect(layer().restore.appliedRender.rescale).toBe('10,77');
  });

  it('loses what was applied and not saved, without asking, when the settings are closed', () => {
    store().setPendingColormapName('magma');
    store().applyRender();
    store().exitFocus();
    expect(layer().restore.appliedRender).toEqual({ colormapName: 'viridis', rescale: '10,2900' });
    store().selectLayer(`L-${id}`);
    expect(store().appliedRender).toEqual({ colormapName: 'viridis', rescale: '10,2900' });
    expect(store().pendingColormapName).toBe('viridis');
  });

  it('loses it as well when another layer is chosen', () => {
    store().setPendingColormapName('magma');
    store().applyRender();
    store().selectLayer(OTHER);
    store().selectLayer(`L-${id}`);
    expect(store().pendingColormapName).toBe('viridis');
    expect(urlOf(layer())).toContain('viridis');
  });

  it('keeps what was saved when the settings are closed and opened again', () => {
    store().setPendingColormapName('magma');
    store().saveViewLook();
    store().exitFocus();
    store().selectLayer(`L-${id}`);
    expect(store().appliedRender.colormapName).toBe('magma');
    expect(store().pendingColormapName).toBe('magma');
  });

  it('does nothing for a view that is no layer\'s', () => {
    store().exitFocus();
    useAppStore.setState({ focusMode: true, downloaded: layer().restore.downloaded, appliedRender: {}, viewLayerId: null });
    const before = store().layers;
    store().setPendingColormapName('plasma');
    store().saveViewLook();
    expect(store().layers).toBe(before);
  });
});
