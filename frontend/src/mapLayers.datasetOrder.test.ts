// NM4-50 (Otto, 30.10.2026): the dataset the results list shows lies on top of the map. From the top: the live preview, the
// open dataset (its ticked scenes in the order they were ticked, the last on top, and under them its other quicklooks), the
// ticked scenes of the other datasets (in the order they were ticked), then the view, the results over it and the pinned
// layers. A change of the dataset lays the scenes out again at once, also after a style load.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { liveMap, pinned } from './fixtures/liveMap';
import { FakeImage, quicklookDataset, quicklookScene } from './fixtures/viewScenes';
import { ensureBaseLayers, syncBrowseMosaic, syncLayers, syncPreview, syncResultsOverlay } from './mapLayers';
import type { DatasetOption } from './datasets';
import type { StacItem } from './types';

const tiles = (id: string, browse: 'full_resolution' | 'preview_tiles', minZoom: number): DatasetOption =>
  datasetsFrom([
    {
      id,
      title: id,
      'earthx:capabilities': { roi: true, time_range: browse !== 'full_resolution', band_math: true, interpolation: true },
      'earthx:viewer': { group_by: ['datetime'], min_zoom: minZoom, max_zoom: 14, browse, quicklook_nodata_max: null, results_group_by: ['datetime'] },
      'earthx:default_render': { title: 'Standard', assets: ['data'], rescale: [[0, 4000]] as [number, number][], colormap_name: null, expression: null, resampling: 'nearest' },
    },
  ] as never)[0];

const DEM = tiles('dem', 'full_resolution', 0);
const COARSE = tiles('coarse', 'preview_tiles', 8);
const S2 = quicklookDataset();

const sceneOf = (id: string, dataset: DatasetOption): StacItem => ({
  ...quicklookScene(id),
  collection: dataset.id,
  assets: dataset.id === S2.id ? quicklookScene(id).assets : {},
});

const arrive = () => FakeImage.arrive();

beforeEach(() => {
  FakeImage.all = [];
  vi.stubGlobal('Image', FakeImage);
  vi.stubGlobal('document', { createElement: () => ({ getContext: () => null }) });
});
afterEach(() => vi.unstubAllGlobals());

const freshMap = () => {
  const live = liveMap([]);
  ensureBaseLayers(live.map as never);
  return live;
};

// The scenes on the map, bottom to top, by the index their item has in the list handed over.
const resultLayers = (live: ReturnType<typeof liveMap>, prefix = /^[mn]-(tiles|img)-lyr-(\d+)$/u) =>
  live.stack.flatMap((id) => {
    const match = prefix.exec(id);
    return match ? [Number(match[2])] : [];
  });
const below = (live: ReturnType<typeof liveMap>, id: string, marker: string) => live.stack.indexOf(id) < live.stack.indexOf(marker);

describe.each([
  ['the DEM open, Sentinel-2 (coarse tiles) ticked beside it', DEM, COARSE],
  ['Sentinel-2 (coarse tiles) open, the DEM ticked beside it', COARSE, DEM],
  ['Sentinel-2 (quicklooks) open, the DEM ticked beside it', S2, DEM],
  ['the DEM open, Sentinel-2 (quicklooks) ticked beside it', DEM, S2],
] as const)('with %s', (_name, open, other) => {
  // x1, x2, x3 of the open dataset, y1, y2 of the other one.
  const items = [sceneOf('x1', open), sceneOf('x2', open), sceneOf('x3', open), sceneOf('y1', other), sceneOf('y2', other)];
  const datasets = [open, other];
  const draw = (live: ReturnType<typeof liveMap>, ticks: string[], openDataset: DatasetOption = open) => {
    syncBrowseMosaic(live.map as never, { items, dataset: openDataset, datasets, selectedIds: ticks });
    arrive();
  };

  it('lays the other dataset\'s ticked scenes lowest, the open dataset\'s other scenes over them and its ticked ones on top', () => {
    const live = freshMap();
    draw(live, ['y1', 'x2', 'y2', 'x1']);
    // y1 (3), y2 (4): the other dataset in the order ticked; x3 (2): the rest of the open one; x2 (1), x1 (0): its ticks.
    expect(resultLayers(live)).toEqual([3, 4, 2, 1, 0]);
  });

  it('keeps the tiers apart by the markers: all over the end of the layers, the preview over all', () => {
    const live = freshMap();
    draw(live, ['y1', 'x2', 'y2', 'x1']);
    const ids = (index: number) => live.stack.filter((id) => new RegExp(`^[mn]-(tiles|img)-lyr-${index}$`, 'u').test(id));
    const [y1] = ids(3);
    const [x3] = ids(2);
    const [x1] = ids(0);
    expect(live.stack.indexOf(y1)).toBeGreaterThan(live.stack.indexOf('ticked-top'));
    expect(below(live, y1, 'open-base')).toBe(true);
    expect(live.stack.indexOf(x3)).toBeGreaterThan(live.stack.indexOf('open-base'));
    expect(below(live, x3, 'open-ticked-base')).toBe(true);
    expect(live.stack.indexOf(x1)).toBeGreaterThan(live.stack.indexOf('open-ticked-base'));
    expect(below(live, x1, 'preview-base')).toBe(true);
  });

  it('puts the last ticked on top, whichever order the ticks were made in', () => {
    const live = freshMap();
    draw(live, ['x1', 'x2', 'y2', 'y1']);
    expect(resultLayers(live)).toEqual([4, 3, 2, 0, 1]);
  });

  it('lays the scenes out again at once when the other dataset is the open one', () => {
    const live = freshMap();
    draw(live, ['y1', 'x2', 'y2', 'x1']);
    // The list shows the other dataset now: its ticks go on top, the scenes of the first one under them.
    syncBrowseMosaic(live.map as never, { items: [items[3], items[4], items[0], items[1]], dataset: other, datasets, selectedIds: ['y1', 'x2', 'y2', 'x1'] });
    arrive();
    // Indexes follow the list handed over now: y1 (0), y2 (1), x1 (2), x2 (3). Ticked elsewhere: x2, x1 in the order ticked.
    expect(resultLayers(live)).toEqual([3, 2, 0, 1]);
  });

  it('lays the scenes out the same again after a style load', () => {
    const live = freshMap();
    draw(live, ['y1', 'x2', 'y2', 'x1']);
    const fresh = freshMap();
    draw(fresh, ['y1', 'x2', 'y2', 'x1']);
    expect(resultLayers(fresh)).toEqual(resultLayers(live));
  });

  it('draws nothing of it while the results are hidden', () => {
    const live = freshMap();
    draw(live, ['y1', 'x2', 'y2', 'x1']);
    syncBrowseMosaic(live.map as never, { items: [], dataset: open, datasets, selectedIds: ['y1', 'x2', 'y2', 'x1'] });
    expect(resultLayers(live)).toEqual([]);
  });

  it('keeps the pinned layers and the view under all of them, the live preview over all', () => {
    const live = freshMap();
    syncLayers(live.map as never, [pinned('p', 'https://t/p/{z}/{x}/{y}')]);
    syncPreview(live.map as never, [{ kind: 'raster', tileUrl: 'https://t/preview/{z}/{x}/{y}', bounds: [0, 0, 1, 1], minZoom: 0, maxZoom: 14 }]);
    draw(live, ['y1', 'x2', 'y2', 'x1']);
    const pin = live.stack.indexOf('layer-lyr-p-0');
    const preview = live.stack.findIndex((id) => id.startsWith('preview-lyr-'));
    for (const index of resultLayers(live)) {
      const at = live.stack.findIndex((id) => new RegExp(`^[mn]-(tiles|img)-lyr-${index}$`, 'u').test(id));
      expect(at).toBeGreaterThan(pin);
      expect(at).toBeLessThan(preview);
    }
  });

  it('orders the ticked scenes over a view the same way, and leaves the other results under it', () => {
    const live = freshMap();
    syncResultsOverlay(live.map as never, { items, dataset: open, datasets, selectedIds: ['y1', 'x2', 'y2', 'x1'] });
    arrive();
    const res = live.stack.flatMap((id) => {
      const match = /^res-(tiles|img)-lyr-(\d+)$/u.exec(id);
      return match ? [Number(match[2])] : [];
    });
    // Only the ticked ones lie over the view's marker, in tiers; x3 (2) is the open dataset's other scene, under the view.
    expect(res.indexOf(3)).toBeLessThan(res.indexOf(4));
    expect(res.indexOf(4)).toBeLessThan(res.indexOf(1));
    expect(res.indexOf(1)).toBeLessThan(res.indexOf(0));
    const x3 = live.stack.findIndex((id) => /^res-(tiles|img)-lyr-2$/u.test(id));
    expect(x3).toBeLessThan(live.stack.indexOf('results-top'));
    expect(live.stack.findIndex((id) => /^res-(tiles|img)-lyr-3$/u.test(id))).toBeGreaterThan(live.stack.indexOf('ticked-top'));
  });
});
