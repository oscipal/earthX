// Plan M5-30 §8.7 (finding of 13.11.2026, 124 selected swissALTI3D tiles): over the level where its own mosaic takes over, the substitute
// of a dataset stays on the map until the mosaic's tiles have arrived, so that a mosaic that takes seconds does not leave the map empty;
// once they are there the substitute steps aside as before (`overviewSubstitute.ts`, `hideFrom`).

import { describe, expect, it } from 'vitest';

import { DOWNLOADED, GROUPS, ITEMS, LIST, MOSAICS, TERRAIN } from './fixtures/swissalti';
import { zoomMap } from './fixtures/zoomMap';
import { syncFocusRaster, watchSubstituteHold } from './mapLayers';

const view = (over: Record<string, unknown> = {}) => ({
  downloaded: DOWNLOADED,
  render: { rescale: '0,3000' },
  showDownloaded: true,
  aoi: null,
  cropToAoi: false,
  items: ITEMS,
  dataset: TERRAIN,
  datasets: LIST,
  groups: GROUPS,
  mosaics: MOSAICS,
  ...over,
});

// A map that fires what MapLibre fires and knows which sources still have tiles on their way.
function watched() {
  const live = zoomMap();
  const handlers = new Map<string, ((event: { sourceId?: string }) => void)[]>();
  const pending = new Set<string>();
  Object.assign(live.map, {
    on: (name: string, handler: (event: { sourceId?: string }) => void) => handlers.set(name, [...(handlers.get(name) ?? []), handler]),
    isSourceLoaded: (id: string) => !pending.has(id),
  });
  watchSubstituteHold(live.map as never);
  const fire = (name: string, sourceId?: string) => handlers.get(name)?.forEach((handler) => handler({ sourceId }));
  const urlOf = (id: string) => (live.sources.get(live.layers.get(id)!.source!)!.tiles as string[])[0];
  const route = (zoom: number) => live.picturesAt(zoom).map((id) => (urlOf(id).includes('/overview/') ? 'substitute' : 'mosaic'));
  return { live, fire, pending, route };
}

describe('the substitute while the mosaic of the view is on its way', () => {
  it('is drawn over the level of the mosaic until the mosaic has loaded, and then steps aside', () => {
    const { live, fire, pending, route } = watched();
    syncFocusRaster(live.map as never, view());
    pending.add('m-tiles-src-1');
    expect(route(13.5)).toEqual(['substitute', 'mosaic']);
    fire('sourcedataloading', 'm-tiles-src-1');
    fire('sourcedata', 'm-tiles-src-1');
    expect(route(13.5)).toEqual(['substitute', 'mosaic']);
    pending.delete('m-tiles-src-1');
    fire('sourcedata', 'm-tiles-src-1');
    expect(route(13.5)).toEqual(['mosaic']);
    expect(route(12.4)).toEqual(['substitute']);
  });

  it('is drawn at every level while the selection of the mosaic is not made yet, and stays until the next sync brings the mosaic', () => {
    const { live, fire, route } = watched();
    syncFocusRaster(live.map as never, view({ mosaics: {} }));
    expect(route(13.5)).toEqual(['substitute']);
    expect(route(14.5)).toEqual(['substitute']);
    fire('idle');
    expect(route(13.5)).toEqual(['substitute']);
    syncFocusRaster(live.map as never, view());
    // The picture of the sync before stays under the new one until the new one has arrived (`retireDynamicMosaic`).
    expect(route(13.5)).toContain('mosaic');
    fire('sourcedataloading', 'n-tiles-src-1');
    fire('sourcedata', 'n-tiles-src-1');
    live.idle();
    expect(route(13.5)).toEqual(['mosaic']);
  });

  it('does not take the loading of another source for the mosaic: a source that has not started does not count, the map at rest does', () => {
    const { live, fire, route } = watched();
    syncFocusRaster(live.map as never, view());
    fire('sourcedata', 'basemap');
    expect(route(13.5)).toEqual(['substitute', 'mosaic']);
    fire('idle');
    expect(route(13.5)).toEqual(['mosaic']);
  });

  it('ends where a tile of the mosaic failed: MapLibre counts a failed tile as loaded', () => {
    const { live, fire, pending, route } = watched();
    syncFocusRaster(live.map as never, view());
    pending.add('m-tiles-src-1');
    fire('sourcedataloading', 'm-tiles-src-1');
    pending.delete('m-tiles-src-1');
    fire('idle');
    expect(route(13.5)).toEqual(['mosaic']);
  });

  it('keeps the limit of the substitute in the signature of its picture and lays it below the level of the mosaic as before', () => {
    const { live, route } = watched();
    syncFocusRaster(live.map as never, view({ mosaics: {} }));
    expect(live.layers.get('m-tiles-lyr-0')!.maxzoom).toBeUndefined();
    expect(route(0)).toEqual(['substitute']);
  });

  it('draws nothing of a dataset without a substitute over its first level before the mosaic: no hold, no layer', () => {
    const { live, route } = watched();
    syncFocusRaster(live.map as never, view({ mosaics: {}, dataset: LIST[1], datasets: LIST }));
    expect(route(13.5)).toEqual([]);
  });
});
