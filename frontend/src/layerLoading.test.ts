// Plan M5-30 §8.7, Otto 13.11.2026: which rows of the layer manager are loading, from what the map says of its sources.

import { beforeEach, describe, expect, it } from 'vitest';

import { DOWNLOADED, GROUPS, ITEMS, LIST, MOSAICS } from './fixtures/swissalti';
import { isMapLoading, isOwnerLoading, viewWaitsForMosaic, watchLayerLoading } from './layerLoading';
import { ownerOfSource, RESULTS_OWNER } from './mapLayers';
import { useAppStore } from './store';

describe('ownerOfSource', () => {
  it.each([
    ['layer-src-L12-0', 'L12'],
    ['layer-src-L12-3', 'L12'],
    ['layer-src-job-7f-2-10', 'job-7f-2'],
    ['m-tiles-src-0', RESULTS_OWNER],
    ['n-tiles-src-c4', RESULTS_OWNER],
    ['res-tiles-src-2', RESULTS_OWNER],
    ['preview-src-1', RESULTS_OWNER],
  ])('%s belongs to %s', (id, owner) => expect(ownerOfSource(id)).toBe(owner));

  it.each(['basemap', 'composite', 'aoi-src', 'coverage-src', 'mosaicsel-src', 'm-img-src-0', 'layer-src-', 'layer-src-L12', 'xm-tiles-src-0', ''])(
    'the source %j belongs to no row',
    (id) => expect(ownerOfSource(id)).toBeNull(),
  );
});

// A fake map: each source has one layer of the same name, which can be switched off or limited in zoom.
function watched() {
  const handlers = new Map<string, (event: { sourceId?: string }) => void>();
  const sources = new Set(['m-tiles-src-0', 'layer-src-A-0', 'layer-src-A-1', 'layer-src-B-0', 'basemap']);
  const pending = new Set<string>();
  const hidden = new Set<string>();
  const zooms = new Map<string, [number, number]>();
  let zoom = 13;
  const map = {
    on: (name: string, handler: (event: { sourceId?: string }) => void) => handlers.set(name, handler),
    getSource: (id: string) => (sources.has(id) ? {} : undefined),
    isSourceLoaded: (id: string) => !pending.has(id),
    getZoom: () => zoom,
    getLayersOrder: () => [...sources],
    getLayer: (id: string) => (sources.has(id) ? { source: id, minzoom: zooms.get(id)?.[0] ?? 0, maxzoom: zooms.get(id)?.[1] ?? 24 } : undefined),
    getLayoutProperty: (id: string) => (hidden.has(id) ? 'none' : 'visible'),
  };
  const told: string[][] = [];
  watchLayerLoading(map as never, (owners) => told.push([...owners]));
  const start = (id: string) => {
    pending.add(id);
    handlers.get('sourcedataloading')!({ sourceId: id });
  };
  const done = (id: string, event = 'sourcedata') => {
    pending.delete(id);
    handlers.get(event)!({ sourceId: id });
  };
  const fire = (name: string) => handlers.get(name)!({});
  return { told, start, done, fire, sources, pending, hidden, zooms, zoomTo: (next: number) => (zoom = next) };
}

describe('watchLayerLoading', () => {
  it('says a row is loading from the first tile its source asks for to the last one it gets', () => {
    const { told, start, done } = watched();
    start('layer-src-A-0');
    start('layer-src-A-1');
    expect(told).toEqual([['A']]);
    done('layer-src-A-0');
    expect(told).toEqual([['A']]);
    done('layer-src-A-1');
    expect(told).toEqual([['A'], []]);
  });

  it('keeps the rows apart, a pinned layer from "Results" and one layer from another', () => {
    const { told, start, done } = watched();
    start('layer-src-B-0');
    start('m-tiles-src-0');
    expect(told.at(-1)).toEqual(['B', RESULTS_OWNER]);
    done('layer-src-B-0');
    expect(told.at(-1)).toEqual([RESULTS_OWNER]);
  });

  it('tells a change once, not at every tile', () => {
    const { told, start } = watched();
    start('layer-src-A-0');
    start('layer-src-A-0');
    start('layer-src-A-1');
    expect(told).toEqual([['A']]);
  });

  it('does not take the basemap, or a source of no row, for a layer, however slow it is', () => {
    const { told, start, fire } = watched();
    start('basemap');
    start('coverage-src');
    fire('sourcedata');
    expect(told).toEqual([]);
  });

  it('ends where the last tile of a source failed: that fires no `sourcedata`, but the map comes to rest', () => {
    const { told, start, fire, pending } = watched();
    start('layer-src-A-0');
    pending.delete('layer-src-A-0');
    fire('idle');
    expect(told).toEqual([['A'], []]);
  });

  it('ends where the source was removed while it was loading', () => {
    const { told, start, fire, sources } = watched();
    start('layer-src-A-0');
    sources.delete('layer-src-A-0');
    fire('styledata');
    expect(told).toEqual([['A'], []]);
  });

  it('settles on an error of the map that names a source whose tiles are all in or failed', () => {
    const { told, start, done } = watched();
    start('layer-src-A-0');
    done('layer-src-A-0', 'error');
    expect(told).toEqual([['A'], []]);
  });
  it('says loading again for the tiles a zoom or a pan asks for, after the first load is done', () => {
    const { told, start, done } = watched();
    start('layer-src-A-0');
    done('layer-src-A-0');
    start('layer-src-A-0'); // zoom in: the tiles of the new level
    done('layer-src-A-0');
    start('layer-src-A-0'); // pan: the tiles of the new edge
    done('layer-src-A-0');
    expect(told).toEqual([['A'], [], ['A'], [], ['A'], []]);
  });

  it('stays loading while a pan asks for more tiles before the first ones are in', () => {
    const { told, start, done } = watched();
    start('layer-src-A-0');
    start('layer-src-A-0');
    start('layer-src-B-0');
    done('layer-src-A-0');
    expect(told).toEqual([['A'], ['A', 'B'], ['B']]);
  });

  it('ends a load whose tiles a zoom dropped (they ask for nothing more and fire no `sourcedata`) when the zoom ends', () => {
    const { told, start, pending, fire } = watched();
    start('layer-src-A-0');
    pending.delete('layer-src-A-0');
    fire('zoomend');
    expect(told).toEqual([['A'], []]);
  });

  it('ends a load whose tiles a pan dropped when the move ends, and on an abort of the source', () => {
    const { told, start, pending, fire } = watched();
    start('layer-src-A-0');
    pending.delete('layer-src-A-0');
    fire('moveend');
    start('layer-src-B-0');
    pending.delete('layer-src-B-0');
    fire('sourcedataabort');
    expect(told).toEqual([['A'], [], ['B'], []]);
  });

  it('keeps loading through a move that leaves a tile in flight', () => {
    const { told, start, fire } = watched();
    start('layer-src-A-0');
    fire('moveend');
    fire('zoomend');
    expect(told).toEqual([['A']]);
  });

  it('does not say a hidden layer is loading, and stops saying it when the layer is hidden while it loads', () => {
    const { told, start, hidden, fire } = watched();
    hidden.add('layer-src-B-0');
    start('layer-src-B-0');
    expect(told).toEqual([]);
    start('layer-src-A-0');
    expect(told).toEqual([['A']]);
    hidden.add('layer-src-A-0');
    fire('styledata');
    expect(told).toEqual([['A'], []]);
  });

  it('does not say a layer is loading outside its zoom range, and does again when the zoom comes back into it', () => {
    const { told, start, zooms, zoomTo, fire } = watched();
    zooms.set('layer-src-A-0', [0, 12.5]);
    start('layer-src-A-0');
    expect(told).toEqual([]);
    zooms.set('layer-src-A-0', [0, 24]);
    zoomTo(12);
    fire('zoomend');
    expect(told).toEqual([['A']]);
  });

});

describe('the rows that are loading now', () => {
  beforeEach(() => {
    useAppStore.setState({ mapLoading: [], focusMode: false, downloaded: {}, mosaics: {} });
  });

  const viewOpen = (mosaics: typeof MOSAICS) =>
    useAppStore.setState({
      focusMode: true,
      showDownloaded: true,
      downloaded: DOWNLOADED,
      datasets: LIST,
      datasetId: 'terrain',
      items: ITEMS,
      groups: GROUPS,
      sections: [{ datasetId: 'terrain', items: ITEMS, groups: GROUPS, notes: [], groupingError: null, origin: 'search' as const, incomplete: false }],
      openSectionId: 'terrain',
      shownImage: null,
      mosaics,
    });

  it('names the rows the map says are loading', () => {
    useAppStore.setState({ mapLoading: ['L1'] });
    expect(isOwnerLoading(useAppStore.getState(), 'L1')).toBe(true);
    expect(isOwnerLoading(useAppStore.getState(), 'L2')).toBe(false);
    expect(isOwnerLoading(useAppStore.getState(), RESULTS_OWNER)).toBe(false);
  });

  it('has the view wait for a mosaic until the selection of its scenes is made, then not any more', () => {
    viewOpen({});
    expect(viewWaitsForMosaic(useAppStore.getState())).toBe(true);
    expect(isOwnerLoading(useAppStore.getState(), RESULTS_OWNER)).toBe(true);
    viewOpen(MOSAICS);
    expect(viewWaitsForMosaic(useAppStore.getState())).toBe(false);
  });

  it('does not wait for a mosaic the tiler refused: the scenes are drawn one by one', () => {
    viewOpen(Object.fromEntries(Object.keys(MOSAICS).map((key) => [key, null])));
    expect(viewWaitsForMosaic(useAppStore.getState())).toBe(false);
  });

  it('does not wait where no view is open, or its picture is hidden', () => {
    viewOpen({});
    useAppStore.setState({ focusMode: false });
    expect(viewWaitsForMosaic(useAppStore.getState())).toBe(false);
    useAppStore.setState({ focusMode: true, showDownloaded: false });
    expect(viewWaitsForMosaic(useAppStore.getState())).toBe(false);
  });
});

describe('whether anything on the map is loading', () => {
  beforeEach(() => {
    useAppStore.setState({ mapLoading: [], focusMode: false, downloaded: {}, mosaics: {} });
  });

  it('is so while any row is loading, whichever one', () => {
    expect(isMapLoading(useAppStore.getState())).toBe(false);
    useAppStore.setState({ mapLoading: ['L1'] });
    expect(isMapLoading(useAppStore.getState())).toBe(true);
    useAppStore.setState({ mapLoading: [RESULTS_OWNER] });
    expect(isMapLoading(useAppStore.getState())).toBe(true);
    useAppStore.setState({ mapLoading: [] });
    expect(isMapLoading(useAppStore.getState())).toBe(false);
  });

  it('is so while the view waits for its mosaic, and not once it has it', () => {
    const open = (mosaics: typeof MOSAICS) =>
      useAppStore.setState({
        focusMode: true, showDownloaded: true, downloaded: DOWNLOADED, datasets: LIST, datasetId: 'terrain', items: ITEMS, groups: GROUPS,
        sections: [{ datasetId: 'terrain', items: ITEMS, groups: GROUPS, notes: [], groupingError: null, origin: 'search' as const, incomplete: false }],
        openSectionId: 'terrain', shownImage: null, mosaics,
      });
    open({});
    expect(isMapLoading(useAppStore.getState())).toBe(true);
    open(MOSAICS);
    expect(isMapLoading(useAppStore.getState())).toBe(false);
  });
});
