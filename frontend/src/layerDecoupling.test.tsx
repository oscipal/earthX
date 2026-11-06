// @vitest-environment jsdom
//
// UI-01g (Otto, 26.10.2026): layers and search results are apart. A click on a pinned layer in the layer manager
// (a crop, a result of a job, a mosaic, a pinned preview) shows the controls or the picture of that layer and
// leaves the search results alone: it ticks no scene, changes no tick, opens no other section and changes no
// choice of datasets. These tests fail on the code before: `selectLayer` put the scenes the layer was pinned
// from into the list's selection, opened its section and ticked its dataset.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import type { MapLayer } from './layers';
import { resetJobs } from './processingStore';
import { buildSections } from './sections';
import { useAppStore } from './store';
import type { Collection, DownloadedInfo, StacItem } from './types';
import LayerManager from './components/LayerManager';

vi.mock('./components/MapView', () => ({ default: () => null }));

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const collection = (id: string): Collection =>
  ({
    id,
    title: id,
    'earthx:format': 'cog',
    'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
    'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
    'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
  }) as unknown as Collection;

const scene = (id: string, day: string, dataset = 'optical'): StacItem => ({
  id,
  collection: dataset,
  bbox: [10, 50, 11, 51],
  properties: { datetime: `${day}T10:00:00Z` },
  assets: {},
});

const SEARCH_AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 50], [10.5, 50], [10.5, 50.5], [10, 50.5], [10, 50]]] };
const LAYER_AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10.6, 50.6], [10.9, 50.6], [10.9, 50.9], [10.6, 50.9], [10.6, 50.6]]] };

const info = (id: string): DownloadedInfo => ({
  datasetId: 'sentinel-2-c1-l2a', tileUrl: `/collections/optical/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`,
  bounds: [10, 50, 11, 51],
  asset: 'visual',
  minZoom: 0,
  maxZoom: 14,
});

// A layer pinned from earlier scenes, with a different selection, group and area than the search holds now.
function layer(id: string, over: Partial<MapLayer> = {}, restore: Partial<MapLayer['restore']> = {}): MapLayer {
  const ids = ['old1', 'old2'];
  return {
    id,
    name: `Layer ${id}`,
    visible: true,
    opacity: 1,
    overlays: [{ kind: 'raster', tileUrl: `https://t/${id}/{z}/{x}/{y}`, bounds: [10, 50, 11, 51], minZoom: 0, maxZoom: 12 }],
    restore: {
      focusMode: true,
      downloaded: Object.fromEntries(ids.map((i) => [i, info(i)])),
      appliedRender: { rescale: '0,3000' },
      activeGroupIndex: 1,
      selectedIds: ids,
      itemIds: ids,
      groupItemIds: [ids],
      aoi: LAYER_AOI,
      cropToAoi: true,
      datasetId: 'optical',
      ...restore,
    },
    ...over,
  };
}

let container: HTMLDivElement;
let root: Root;

const items = [scene('s1', '2026-07-24'), scene('s2', '2026-07-24'), scene('s3', '2026-07-25')];

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 404 })));
  resetJobs();
  const datasets = datasetsFrom([collection('optical'), collection('dem')]);
  const viewable = datasets.filter((d): d is Extract<typeof d, { viewable: true }> => d.viewable);
  const { sections } = buildSections(items, viewable, { ignoredFilters: [], ignoredFiltersByCollection: {}, incompleteCollections: [] });
  const open = sections[0];
  useAppStore.setState({
    datasets,
    sections,
    openSectionId: open.datasetId,
    datasetId: open.datasetId,
    selectedDatasetIds: ['optical'],
    items: open.items,
    groups: open.groups,
    activeGroupIndex: 0,
    expandedGroupIndex: 0,
    selectedIds: ['s1'],
    aoi: SEARCH_AOI,
    focusMode: false,
    resultViewLayerId: null,
    viewLayerId: null,
    downloaded: {},
    dock: 'layers',
    layers: [
      layer('crop'),
      layer('mosaic', { name: 'Mosaic' }, { itemIds: ['old1', 'old2', 'old3'], groupItemIds: [['old1', 'old2', 'old3']] }),
      layer('preview', { name: 'Preview' }, { focusMode: false, downloaded: {}, cropToAoi: false, aoi: null, selectedIds: ['old9'], itemIds: ['old9'] }),
      layer('result', { name: 'Result', derived: 'result' } as Partial<MapLayer>),
    ],
  });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  act(() => root.render(<LayerManager />));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  resetJobs();
  localStorage.clear();
  vi.unstubAllGlobals();
});

const names = () => [...container.querySelectorAll<HTMLButtonElement>('.lm-name')];
const clickLayer = (id: string) => {
  const label = ({ mosaic: 'Mosaic', preview: 'Preview', result: 'Result' } as Record<string, string>)[id] ?? `Layer ${id}`;
  const button = names().find((b) => b.textContent === label);
  expect(button).toBeDefined();
  act(() => button!.dispatchEvent(new MouseEvent('click', { bubbles: true })));
};

// Everything the list of results holds, and the choices of the search.
const searchState = () => {
  const s = useAppStore.getState();
  return {
    selectedIds: s.selectedIds,
    items: s.items,
    groups: s.groups,
    sections: s.sections,
    openSectionId: s.openSectionId,
    activeGroupIndex: s.activeGroupIndex,
    expandedGroupIndex: s.expandedGroupIndex,
    selectedDatasetIds: s.selectedDatasetIds,
  };
};

describe.each([
  ['a crop', 'crop'],
  ['a mosaic', 'mosaic'],
  ['a pinned preview', 'preview'],
  ['the result of a job', 'result'],
])('a click on %s in the layer manager', (_, id) => {
  it('ticks no scene and changes no tick of the search results, nor anything else the list holds', () => {
    const before = searchState();
    clickLayer(id);
    const after = searchState();
    expect(after.selectedIds).toBe(before.selectedIds);
    expect(after.selectedIds).toEqual(['s1']);
    expect(after).toEqual(before);
    expect(after.items).toBe(before.items);
    expect(after.groups).toBe(before.groups);
  });

  it('leaves the ticks in the rows of the results panel as they were', () => {
    clickLayer(id);
    expect(useAppStore.getState().selectedIds).toEqual(['s1']);
    expect(useAppStore.getState().selectedIds).not.toContain('old1');
    expect(useAppStore.getState().selectedIds).not.toContain('old9');
  });
});

describe('what a click on a layer does show', () => {
  it('a crop: the view of that layer, with its picture, stretch and the area it was cut to', () => {
    const crop = useAppStore.getState().layers.find((l) => l.id === 'crop')!;
    clickLayer('crop');
    const s = useAppStore.getState();
    expect(s.viewLayerId).toBe('crop');
    expect(s.focusMode).toBe(true);
    expect(s.downloaded).toBe(crop.restore.downloaded);
    expect(s.appliedRender).toBe(crop.restore.appliedRender);
    expect(s.cropToAoi).toBe(true);
    expect(s.aoi).toEqual(LAYER_AOI);
    expect(s.datasetId).toBe('optical');
  });

  it('a pinned preview: the layer is the view, the search area stays', () => {
    clickLayer('preview');
    const s = useAppStore.getState();
    expect(s.viewLayerId).toBe('preview');
    expect(s.focusMode).toBe(false);
    expect(s.aoi).toEqual(SEARCH_AOI);
  });

  it('the result of a job: its own view of how it is drawn, and no view of scenes', () => {
    act(() => useAppStore.setState({ focusMode: true, viewLayerId: 'crop' }));
    clickLayer('result');
    const s = useAppStore.getState();
    expect(s.resultViewLayerId).toBe('result');
    expect(s.focusMode).toBe(false);
    expect(s.selectedIds).toEqual(['s1']);
  });

  it('a layer of another dataset than the open section: its dataset drives its controls, the list keeps its section', () => {
    act(() => useAppStore.setState({ layers: [layer('dem', { name: 'Layer dem' }, { datasetId: 'dem' })] }));
    clickLayer('dem');
    const s = useAppStore.getState();
    expect(s.datasetId).toBe('dem');
    expect(s.openSectionId).toBe('optical');
    expect(s.selectedDatasetIds).toEqual(['optical']);
  });
});

describe('the other way round', () => {
  it('a tick in the results does not move a layer: the layers stay as they are', () => {
    const before = useAppStore.getState().layers;
    act(() => useAppStore.getState().toggleSelected('s2'));
    expect(useAppStore.getState().layers).toBe(before);
    expect(useAppStore.getState().viewLayerId).toBeNull();
  });
});
