// NM4-55 (Otto, 30.10.2026, zu #242): what is looked at lies on top. A scene that is ticked in one group of the list does not
// hide the quicklooks of the group that is opened, or of the step that is played. From the top: the live preview, the open
// group (its ticked scenes over its other scenes, the last ticked on top), the ticked scenes of the other groups and
// datasets in the order they were ticked, then the view, the results over it and the pinned layers. A change of group, and
// each step of the playing, lays the scenes out again at once, also after a style load.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { liveMap } from './fixtures/liveMap';
import { FakeImage, quicklookScene } from './fixtures/viewScenes';
import { itemsForMap } from './grouping';
import { ensureBaseLayers, syncBrowseMosaic, syncResultsOverlay } from './mapLayers';
import { openIdsOf } from './mapResults';
import type { StacItem, TimeStepGroup } from './types';

const [DEM] = datasetsFrom([
  {
    id: 'dem',
    title: 'dem',
    'earthx:capabilities': { roi: true, time_range: false, band_math: true, interpolation: true },
    'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 14, browse: 'full_resolution', quicklook_nodata_max: null, results_group_by: ['datetime'] },
    'earthx:default_render': { title: 'Standard', assets: ['data'], rescale: [[0, 4000]] as [number, number][], colormap_name: null, expression: null, resampling: 'nearest' },
  },
] as never);

const sceneOf = (id: string): StacItem => ({ ...quicklookScene(id), collection: 'dem', assets: {} });
const group = (name: string, ids: string[]): TimeStepGroup => ({ key: [name], label: name, items: ids.map(sceneOf) });

// Three passes of two scenes each, newest first.
const GROUPS = [group('2026-07-25', ['c1', 'c2']), group('2026-07-24', ['b1', 'b2']), group('2026-07-23', ['a1', 'a2'])];

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

// Opens group `open` of the list with these ticks, as the map does: the scenes drawn are the open group's and the ticked ones.
function draw(live: ReturnType<typeof liveMap>, open: number | null, ticks: string[]) {
  const items = itemsForMap(GROUPS, open, ticks);
  syncBrowseMosaic(live.map as never, { items, dataset: DEM, datasets: [DEM], openIds: openIdsOf(GROUPS, open), selectedIds: ticks });
  FakeImage.arrive();
  return items.map((item) => item.id);
}

// The scenes on the map, bottom to top, by id.
const bottomToTop = (live: ReturnType<typeof liveMap>, ids: string[], prefix = /^[mn]-(tiles|img)-lyr-(\d+)$/u) =>
  live.stack.flatMap((layer) => {
    const match = prefix.exec(layer);
    return match ? [ids[Number(match[2])]] : [];
  });

describe('a change of group', () => {
  it('lays the opened group over a scene that is ticked in another group', () => {
    const live = freshMap();
    const ids = draw(live, 1, ['a1']);
    // a1, ticked in the oldest group, lies under both scenes of the group that is open.
    expect(bottomToTop(live, ids)).toEqual(['a1', 'b1', 'b2']);
  });

  it('keeps the ticked scenes of the open group over its other scenes, the last ticked on top, and the other group under them', () => {
    const live = freshMap();
    const ids = draw(live, 1, ['b2', 'a1', 'b1']);
    expect(bottomToTop(live, ids)).toEqual(['a1', 'b2', 'b1']);
    const again = freshMap();
    expect(bottomToTop(again, draw(again, 1, ['b1', 'b2']))).toEqual(['b1', 'b2']);
  });

  it('lays the ticked scenes of the other groups in the order they were ticked, under the open group', () => {
    const live = freshMap();
    const ids = draw(live, 0, ['a2', 'b1', 'a1']);
    const order = bottomToTop(live, ids);
    expect(order.slice(0, 3)).toEqual(['a2', 'b1', 'a1']);
    expect(order.slice(3).sort()).toEqual(['c1', 'c2']);
  });

  it('puts the group back over the ticked scene when the list returns to the group the scene is in: the ticked scene over the others', () => {
    const live = freshMap();
    draw(live, 1, ['a1']);
    const back = draw(live, 2, ['a1']);
    // a1 is in the open group again: ticked, so over a2.
    expect(bottomToTop(live, back)).toEqual(['a2', 'a1']);
  });

  it('is the same after a style load: the scenes are laid out once more on a map with only its markers', () => {
    const live = freshMap();
    const ids = draw(live, 1, ['a1']);
    const fresh = freshMap();
    expect(bottomToTop(fresh, draw(fresh, 1, ['a1']))).toEqual(bottomToTop(live, ids));
  });

  it('keeps the tiers right under the marker of the overlays: the open group over the ticked scene of another group', () => {
    const live = freshMap();
    draw(live, 1, ['a1']);
    const layer = (index: number) => live.stack.find((id) => new RegExp(`^[mn]-(tiles|img)-lyr-${index}$`, 'u').test(id))!;
    // items: b1 (0), b2 (1), a1 (2)
    const end = live.stack.indexOf('overlays-base');
    expect(live.stack.slice(end - 4, end)).toEqual([layer(2), layer(0), layer(1), 'mosaicsel-line']);
  });
});

describe('the playing of the timeline', () => {
  it('lays each step over the scene that is ticked in one of them, in whichever step the scene is', () => {
    const live = freshMap();
    for (const step of [2, 1, 0]) {
      const ids = draw(live, step, ['b1']);
      const order = bottomToTop(live, ids);
      if (step === 1) {
        // The step that holds the ticked scene: it is open, so over the other scene of its group.
        expect(order).toEqual(['b2', 'b1']);
      } else {
        // Any other step: its scenes over the ticked scene.
        expect(order[0]).toBe('b1');
        expect(order.slice(1)).toHaveLength(2);
      }
    }
  });

  it('does it for a step of a view of scenes that lie over a full-resolution view as well: the open group\'s tick over the other group\'s', () => {
    const live = freshMap();
    const ticks = ['b1', 'a1'];
    const items = [...GROUPS[1].items, ...GROUPS[2].items];
    syncResultsOverlay(live.map as never, { items, dataset: DEM, datasets: [DEM], openIds: openIdsOf(GROUPS, 1), selectedIds: ticks });
    FakeImage.arrive();
    const ids = items.map((item) => item.id);
    const order = bottomToTop(live, ids, /^res-(tiles|img)-lyr-(\d+)$/u);
    // Both are ticked, a1 after b1; b1 is in the open group and lies over a1 all the same.
    expect(order.indexOf('b1')).toBeGreaterThan(order.indexOf('a1'));
  });
});
