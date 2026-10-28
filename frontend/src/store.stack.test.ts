// UI-01a (Befund Punkt 10, §6.3): a pinned layer stacks several time steps and scenes the way
// the full-resolution view draws them, and a layer pinned from the view is the view's picture.
// Each case here failed against the code before UI-01a.

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import type { LayerOverlay } from './layers';
import { syncFocusRaster, syncPreview } from './mapLayers';
import { liveMap } from './fixtures/liveMap';
import { mosaicTemplateOf } from './mosaic';
import type { SceneEntry } from './mosaic';
import { previewOverlays } from './processingPreview';
import type { PreviewSpec } from './processingPreview';
import { useProcessingStore } from './processingStore';
import { quicklookDataset, quicklookScene, sceneInfo as tileInfo } from './fixtures/viewScenes';
import { useAppStore } from './store';
import type { Collection, DownloadedInfo, TimeStepGroup } from './types';

const ID = 'sentinel-2-c1-l2a';
const COLLECTION: Collection = {
  id: ID,
  title: 'Sentinel-2 L2A',
  'earthx:capabilities': {
    roi: true,
    time_range: true,
    band_math: true,
    interpolation: true,
    ml_processing: true,
    quad_pol: false,
    single_coverage_product: false,
  },
  'earthx:viewer': {
    group_by: ['datetime'],
    min_zoom: 0,
    max_zoom: 19,
    browse: 'preview_tiles',
    quicklook_nodata_max: null,
    results_group_by: ['datetime'],
  },
  'earthx:default_render': {
    title: 'True colour',
    assets: ['visual'],
    rescale: [[0, 3000]],
    colormap_name: null,
    expression: null,
    resampling: 'nearest',
  },
};

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 47]]] };
const group = (ids: string[]): TimeStepGroup => ({
  key: [ids[0]],
  label: ids[0],
  items: ids.map((id) => ({ id, bbox: [10, 47, 11, 48], properties: {}, assets: {} })),
});
const sceneInfo = (id: string): DownloadedInfo => ({
  tileUrl: `/collections/${ID}/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`,
  bounds: [10, 47, 11, 48],
  asset: 'visual',
  minZoom: 0,
  maxZoom: 19,
});
const downloadedOf = (...ids: string[]) => Object.fromEntries(ids.map((id) => [id, sceneInfo(id)]));

// The tiler refused the mosaics: every pass is drawn scene by scene.
const refused = (groups: TimeStepGroup[], downloaded: Record<string, DownloadedInfo>) =>
  Object.fromEntries(
    groups.map((g) => {
      const entries = g.items.map((it) => [it.id, downloaded[it.id]] as SceneEntry);
      return [mosaicTemplateOf(ID, entries) as string, null];
    }),
  );

function focusOn(ids: string[], groups: TimeStepGroup[], over: Partial<ReturnType<typeof useAppStore.getState>> = {}) {
  const downloaded = downloadedOf(...ids);
  useAppStore.setState({
    datasets: datasetsFrom([COLLECTION]),
    selectedDatasetIds: [ID],
    datasetId: ID,
    items: groups.flatMap((g) => g.items),
    groups,
    activeGroupIndex: 0,
    expandedGroupIndex: 0,
    selectedIds: [],
    focusMode: true,
    showDownloaded: true,
    cropToAoi: false,
    downloaded,
    appliedRender: {},
    mosaics: refused(groups, downloaded),
    pinLoading: false,
    layers: [],
    viewLayerId: null,
    aoi: AOI,
    error: null,
    notice: null,
    // A cropped view holds the area it was opened with.
    viewAoi: over.cropToAoi ? (over.aoi ?? AOI) : null,
    ...over,
  });
}

const tileOf = (o: LayerOverlay) => (o.kind === 'raster' ? o.tileUrl : o.url);

// The tile templates the view draws, bottom to top.
function viewOrder(): string[] {
  const s = useAppStore.getState();
  const live = liveMap();
  syncFocusRaster(live.map as never, {
    downloaded: s.downloaded,
    render: s.appliedRender,
    showDownloaded: true,
    items: s.items,
    dataset: s.datasets.find((d) => d.id === s.datasetId) ?? null,
    groups: s.groups,
    mosaics: s.mosaics,
  });
  return live.stack
    .filter((id) => id.startsWith('m-tiles-lyr-'))
    .map((id) => (live.sources.get(live.layers.get(id)!.source!) as { tiles: string[] }).tiles[0]);
}

beforeEach(() => focusOn(['A1', 'A2', 'B1', 'B2'], [group(['A1', 'A2']), group(['B1', 'B2'])]));
afterEach(() => useProcessingStore.setState({ preview: null }));

describe('addCurrentToLayers: the layer stacks the way the view does', () => {
  it('lays the first time step on top, and the first scene of a time step on top of the others', () => {
    useAppStore.getState().addCurrentToLayers();
    const [layer] = useAppStore.getState().layers;
    expect(layer.overlays.map(tileOf)).toEqual(viewOrder());
    expect(layer.overlays.map(tileOf).pop()).toContain('/items/A1/');
  });

  it('does the same for scenes that belong to no time step', () => {
    focusOn(['A', 'B', 'C'], []);
    useAppStore.getState().addCurrentToLayers();
    expect(useAppStore.getState().layers[0].overlays.map(tileOf)).toEqual(viewOrder());
  });
});

describe('addCurrentToLayers from the full-resolution view: the layer is the view', () => {
  it('makes the one layer it adds the picture of the view', () => {
    focusOn(['A1', 'A2'], [group(['A1', 'A2'])]);
    useAppStore.getState().addCurrentToLayers();
    const { layers, viewLayerId } = useAppStore.getState();
    expect(viewLayerId).toBe(layers[0].id);
  });

  it('also when the one layer is a time step cut to the AOI', () => {
    focusOn(['A1', 'A2'], [group(['A1', 'A2'])], { cropToAoi: true });
    useAppStore.getState().addCurrentToLayers();
    expect(useAppStore.getState().viewLayerId).toBe(useAppStore.getState().layers[0].id);
  });

  it('does not when it adds one layer per time step: no layer is the whole view', () => {
    useAppStore.setState({ cropToAoi: true, viewAoi: AOI });
    useAppStore.getState().addCurrentToLayers();
    expect(useAppStore.getState().layers).toHaveLength(2);
    expect(useAppStore.getState().viewLayerId).toBeNull();
  });

  it('does not when the layer holds only some of the view\'s scenes', () => {
    focusOn(['A1', 'A2'], [group(['A1', 'A2'])], { selectedIds: ['A1'] });
    useAppStore.getState().addCurrentToLayers();
    expect(useAppStore.getState().viewLayerId).toBeNull();
  });
});

describe('pinPreview: the layer stacks the scenes the way the preview does', () => {
  it('lays the first scene on top', () => {
    const scenes = ['A', 'B', 'C'].map((id) => ({
      id,
      bbox: [10, 47, 11, 48] as [number, number, number, number],
      url: `/collections/${ID}/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual&op=band_math`,
    }));
    const preview = { key: 'k', title: 'Band math', mosaics: [], scenes, minZoom: 8, maxZoom: 14, clipToAoi: false } as unknown as PreviewSpec;
    useProcessingStore.setState({ preview });
    useAppStore.setState({ layers: [], aoi: AOI });
    useProcessingStore.getState().pinPreview();

    const onMap = liveMap();
    syncPreview(onMap.map as never, previewOverlays(preview, null));
    const previewOrder = onMap.stack
      .filter((id) => id.startsWith('preview-lyr-'))
      .map((id) => (onMap.sources.get(onMap.layers.get(id)!.source!) as { tiles: string[] }).tiles[0]);
    expect(useAppStore.getState().layers[0].overlays.map(tileOf)).toEqual(previewOrder);
  });
});

describe('addCurrentToLayers for a dataset with a quicklook whose tiles start at z8 (UI-01a)', () => {
  const pinFrom = (over: Partial<ReturnType<typeof useAppStore.getState>> = {}) => {
    const item = quicklookScene('Q1');
    focusOn(['Q1'], [], {
      datasets: [quicklookDataset(8)],
      datasetId: quicklookDataset(8).id,
      items: [item],
      downloaded: { Q1: tileInfo(item, 8, 19) },
      ...over,
    });
    useAppStore.getState().addCurrentToLayers();
    return useAppStore.getState().layers[0];
  };

  it('puts the quicklook under the tiles of the layer, so the layer is not empty when zoomed out of them', () => {
    const layer = pinFrom();
    expect(layer.overlays.map((o) => o.kind)).toEqual(['image', 'raster']);
    expect(layer.overlays[0]).toMatchObject({ kind: 'image', url: 'https://example.invalid/Q1.jpg' });
  });

  it('cuts the quicklook to the AOI like the tiles, in its own pixels and with no coordinate in the layer\'s text', () => {
    const layer = pinFrom({
      cropToAoi: true,
      aoi: { type: 'Polygon', coordinates: [[[9.1, 47.1], [9.4, 47.1], [9.4, 47.5], [9.1, 47.5], [9.1, 47.1]]] },
    });
    const image = layer.overlays[0];
    expect(image.kind === 'image' && image.clipRings?.length).toBeGreaterThan(0);
    expect(layer.name).not.toContain('9.1');
  });

  it('adds none for a dataset released from z0, where the tiles are the picture at every zoom', () => {
    const layer = pinFrom({ datasets: [quicklookDataset(0)] });
    expect(layer.overlays.map((o) => o.kind)).toEqual(['raster']);
  });
});
