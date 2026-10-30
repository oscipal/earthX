// NM4-59 (Otto, 30.10.2026): the search results, the view and the live preview are one entry "Results" among the pinned
// layers. Where it lies in the list decides where all of it lies on the map, whatever order the pictures arrive in; a
// move reloads no tile. Otto's click path: a group open, nothing ticked, a job's result pinned, the results hidden and
// shown again: the open group lies over the job's result every time.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { liveMap, lyr, pinned } from './fixtures/liveMap';
import { FakeImage, quicklookDataset, quicklookScene, sceneInfo } from './fixtures/viewScenes';
import { ensureBaseLayers, syncBrowseMosaic, syncFocusRaster, syncLayers, syncPreview } from './mapLayers';
import type { MapLayer } from './layers';
import type { StacItem } from './types';

type Live = ReturnType<typeof liveMap>;

beforeEach(() => {
  FakeImage.all = [];
  vi.stubGlobal('Image', FakeImage);
  vi.stubGlobal('document', { createElement: () => ({ getContext: () => null }) });
});
afterEach(() => vi.unstubAllGlobals());

const dataset = quicklookDataset();

function freshMap(): Live {
  const live = liveMap([]);
  ensureBaseLayers(live.map as never);
  return live;
}

// Every test its own scenes: a quicklook that has arrived once is cached, and would not arrive late again.
let made = 0;
const scenes = (n: number): StacItem[] => Array.from({ length: n }, () => quicklookScene(`R${++made}`));

// The images asked for so far arrive, the last asked for first.
function arriveBackwards() {
  for (const image of [...FakeImage.all].reverse()) image.onload?.();
  FakeImage.all = [];
}

const job = pinned('job', 'https://t/job/{z}/{x}/{y}', { derived: 'result', opacity: 1 });
const quicklooks = (live: Live) => live.stack.filter((id) => /^[mn]-img-lyr-\d+$/u.test(id));
const at = (live: Live, id: string) => live.stack.indexOf(id);
const lowest = (live: Live, ids: string[]) => Math.min(...ids.map((id) => at(live, id)));
const highest = (live: Live, ids: string[]) => Math.max(...ids.map((id) => at(live, id)));

describe("Otto's click path: a group open, a job's result pinned, the results hidden and shown again", () => {
  const browse = (live: Live, items: StacItem[]) => syncBrowseMosaic(live.map as never, { items, dataset, selectedIds: [] });

  it('lays the open group over the job every time, the pictures arriving in either order', () => {
    const live = freshMap();
    const group = scenes(3);
    browse(live, group);
    arriveBackwards();
    syncLayers(live.map as never, [job]);
    for (let round = 0; round < 4; round++) {
      browse(live, []);
      expect(quicklooks(live)).toEqual([]);
      browse(live, group);
      if (round % 2 === 0) arriveBackwards();
      else FakeImage.arrive();
      expect(quicklooks(live)).toHaveLength(3);
      expect(lowest(live, quicklooks(live))).toBeGreaterThan(at(live, lyr('job')));
    }
  });

  it('and when the job is pinned while the pictures of the group are still on their way', () => {
    const live = freshMap();
    browse(live, scenes(2));
    syncLayers(live.map as never, [job]);
    arriveBackwards();
    expect(lowest(live, quicklooks(live))).toBeGreaterThan(at(live, lyr('job')));
  });

  it('the other way round once "Results" lies under the job (the counter-check)', () => {
    const live = freshMap();
    syncLayers(live.map as never, [job], 1);
    const group = scenes(2);
    browse(live, []);
    browse(live, group);
    arriveBackwards();
    expect(highest(live, quicklooks(live))).toBeLessThan(at(live, lyr('job')));
  });
});

describe('the place of "Results" among the pinned layers', () => {
  const layers: MapLayer[] = ['a', 'b', 'c'].map((id) => pinned(id, `https://t/${id}/{z}/{x}/{y}`));
  const pinnedOrder = (live: Live) => live.stack.filter((id) => id.startsWith('layer-lyr-') || /^[mn]-img-lyr-0$/u.test(id));

  it.each([
    [0, ['c', 'b', 'a', 'R']],
    [1, ['c', 'b', 'R', 'a']],
    [2, ['c', 'R', 'b', 'a']],
    [3, ['R', 'c', 'b', 'a']],
  ])('with %i layers above it, lies there (bottom to top: %j)', (resultsAt, bottomToTop) => {
    const live = freshMap();
    syncBrowseMosaic(live.map as never, { items: scenes(1), dataset, selectedIds: [] });
    FakeImage.arrive();
    syncLayers(live.map as never, layers, resultsAt);
    expect(pinnedOrder(live).map((id) => (id.startsWith('layer-lyr-') ? id.slice(10, 11) : 'R'))).toEqual(bottomToTop);
  });

  it('moves without loading a tile again', () => {
    const live = freshMap();
    syncBrowseMosaic(live.map as never, { items: scenes(1), dataset, selectedIds: [] });
    FakeImage.arrive();
    syncLayers(live.map as never, layers, 0);
    const added = live.log.sourcesAdded.length;
    for (const resultsAt of [1, 2, 3, 2, 0]) syncLayers(live.map as never, layers, resultsAt);
    expect(live.log.sourcesAdded).toHaveLength(added);
    expect(live.log.sourcesRemoved).toEqual([]);
  });

  it.each([
    [99, 'under all of them'],
    [-1, 'over all of them'],
  ])('takes a place outside the list as the nearest end: %i is %s', (resultsAt) => {
    const live = freshMap();
    syncLayers(live.map as never, layers, resultsAt);
    syncPreview(live.map as never, [{ kind: 'raster', tileUrl: 'https://t/p/{z}/{x}/{y}', bounds: [0, 0, 1, 1], minZoom: 0, maxZoom: 14 }]);
    if (resultsAt > 0) expect(at(live, 'preview-lyr-0')).toBeLessThan(at(live, lyr('c')));
    else expect(at(live, 'preview-lyr-0')).toBeGreaterThan(at(live, lyr('a')));
  });

  it('carries the view, the live preview and the outlines with it, under the AOI', () => {
    const live = freshMap();
    const [item] = scenes(1);
    syncFocusRaster(live.map as never, { downloaded: { [item.id]: sceneInfo(item, 8, 14) }, render: {}, showDownloaded: true, items: [], dataset, tilesInLayer: false });
    syncPreview(live.map as never, [{ kind: 'raster', tileUrl: 'https://t/p/{z}/{x}/{y}', bounds: [0, 0, 1, 1], minZoom: 0, maxZoom: 14 }]);
    syncLayers(live.map as never, layers, 1);
    const view = live.stack.filter((id) => /^[mn]-tiles-lyr-/u.test(id));
    const results = [...view, 'preview-lyr-0', 'mosaicsel-line'];
    // a above all of "Results", b and c under it.
    expect(at(live, lyr('a'))).toBeGreaterThan(highest(live, results));
    expect(at(live, lyr('b'))).toBeLessThan(lowest(live, results));
    // Within "Results": the view at the bottom, the preview over it, the outlines on top.
    expect(highest(live, view)).toBeLessThan(at(live, 'preview-lyr-0'));
    expect(at(live, 'preview-lyr-0')).toBeLessThan(at(live, 'mosaicsel-line'));
    // The marker of the overlays and the AOI over all of it.
    expect(at(live, lyr('a'))).toBeLessThan(at(live, 'overlays-base'));
    expect(at(live, 'overlays-base')).toBeLessThan(at(live, 'aoi-fill'));
  });
});
