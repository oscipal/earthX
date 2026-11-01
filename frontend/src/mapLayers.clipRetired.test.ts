// @vitest-environment jsdom
// NM4-25 (Otto, 25.10.2026): "Crop & merge to AOI" opens the view over the quicklook of the whole scene. That picture stays
// until the new one has loaded, so that the basemap never shows, but it must follow the AOI: outside it, it is gone as soon
// as its cut copy is on the map, inside it nothing changes until the tiles of the view are in.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { FakeImage, previewDataset, previewScene, quicklookDataset, quicklookScene, sceneInfo } from './fixtures/viewScenes';
import { liveMap } from './fixtures/liveMap';

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10.2, 47.2], [10.4, 47.2], [10.4, 47.4], [10.2, 47.4], [10.2, 47.2]]] };

// `liveMap` plus what the retiring of a picture waits for: events and sources whose tiles have come in.
function mapWithLoading() {
  const live = liveMap(['layers-top', 'aoi-fill', 'aoi-line']);
  const loaded = new Set<string>();
  const handlers = new Map<string, Set<() => void>>();
  const on = (name: string, fn: () => void) => handlers.set(name, (handlers.get(name) ?? new Set()).add(fn));
  const off = (name: string, fn: () => void) => handlers.get(name)?.delete(fn);
  const map = {
    ...live.map,
    removeSource: (id: string) => {
      loaded.delete(id);
      live.map.removeSource(id);
    },
    isSourceLoaded: (id: string) => loaded.has(id),
    on,
    off,
    once: (name: string, fn: () => void) => {
      const once = () => {
        off(name, once);
        fn();
      };
      on(name, once);
    },
  };
  return {
    ...live,
    map,
    // The tiles of these sources have come in (all sources whose id contains `part`).
    arrive: (part: string) => [...live.sources.keys()].filter((id) => id.includes(part)).forEach((id) => loaded.add(id)),
    fire: (name: string) => [...(handlers.get(name) ?? [])].forEach((fn) => fn()),
    layerIds: () => live.stack.filter((id) => /^[mn]-/.test(id)),
  };
}

let L: typeof import('./mapLayers');
beforeEach(async () => {
  vi.resetModules();
  FakeImage.all = [];
  FakeImage.instant = true;
  vi.stubGlobal('Image', FakeImage);
  L = await import('./mapLayers');
});
afterEach(() => vi.unstubAllGlobals());

const view = (dataset: ReturnType<typeof previewDataset>, item: ReturnType<typeof previewScene>, aoi: GeoJSON.Geometry | null) => ({
  downloaded: { [item.id]: sceneInfo(item, 8, 14, dataset.id) },
  render: {},
  showDownloaded: true,
  aoi,
  cropToAoi: aoi !== null,
  items: [item],
  dataset,
});

describe('the quicklook that stays while the cropped view loads', () => {
  it('is a copy cut to the AOI before the tiles of the view are in, and the whole one goes (preview tiles)', () => {
    const fake = mapWithLoading();
    const [dataset, item] = [previewDataset(), previewScene('H1')];
    L.syncBrowseMosaic(fake.map as never, { items: [item], dataset });
    fake.arrive('tiles-src');
    fake.fire('idle');
    expect(fake.layerIds()).toEqual(['m-tiles-lyr-0']);

    L.syncFocusRaster(fake.map as never, view(dataset, item, AOI));
    // The whole scene is still the picture, with the cut copy right under the cropped view, whose tiles are not in.
    expect(fake.layerIds()).toContain('m-tiles-lyr-0');
    expect(fake.layerIds()).toContain('m-tiles-lyr-c0');
    const cut = (fake.sources.get('m-tiles-src-c0')!.tiles as string[])[0];
    expect(cut).toMatch(/^earthx-clip:\/\//);
    expect(cut).toContain('/collections/preview-source/items/H1/tiles/');
    // The cut copy has not loaded: the whole scene must stay, there is a picture at every moment.
    fake.fire('render');
    expect(fake.layerIds()).toContain('m-tiles-lyr-0');

    // It has loaded; the tiles of the view have not: the whole scene is gone, the cut copy stands.
    fake.arrive('m-tiles-src-c0');
    fake.fire('render');
    expect(fake.layerIds()).not.toContain('m-tiles-lyr-0');
    expect(fake.layerIds()).toContain('m-tiles-lyr-c0');
    expect(fake.layerIds()).toContain('n-tiles-lyr-0');

    // The tiles of the view are in: the cut copy goes, and so does nothing else.
    fake.arrive('n-tiles-src');
    fake.fire('idle');
    expect(fake.layerIds()).toEqual(['n-tiles-lyr-0']);
  });

  it('is a copy of the image cut to the AOI on its pixels, and the whole one goes (quicklook image)', () => {
    const fake = mapWithLoading();
    const [dataset, item] = [quicklookDataset(8), quicklookScene('Q1')];
    L.syncBrowseMosaic(fake.map as never, { items: [item], dataset });
    fake.arrive('img-src');
    fake.fire('idle');
    expect(fake.layerIds()).toEqual(['m-img-lyr-0']);

    L.syncFocusRaster(fake.map as never, view(dataset, item, AOI));
    expect(fake.layerIds()).toContain('m-img-lyr-c0');
    expect(fake.layerIds()).toContain('m-img-lyr-0');
    fake.arrive('m-img-src-c0');
    fake.fire('render');
    expect(fake.layerIds()).not.toContain('m-img-lyr-0');
    expect(fake.layerIds()).toContain('m-img-lyr-c0');
  });

  it('keeps the whole picture where the AOI cannot be placed on it', () => {
    const fake = mapWithLoading();
    const [dataset, item] = [quicklookDataset(8), { ...quicklookScene('Q2'), assets: { thumbnail: quicklookScene('Q2').assets.thumbnail } }];
    L.syncBrowseMosaic(fake.map as never, { items: [item], dataset });
    fake.arrive('img-src');
    fake.fire('idle');
    L.syncFocusRaster(fake.map as never, view(dataset, item, AOI));
    // No georeferenced asset: the AOI cannot be placed on its pixels, so it stays whole (as the underlay of the view does).
    expect(fake.layerIds().filter((id) => id.includes('-c'))).toEqual([]);
  });

  it('is not cut for the view of the whole scene', () => {
    const fake = mapWithLoading();
    const [dataset, item] = [previewDataset(), previewScene('H1')];
    L.syncBrowseMosaic(fake.map as never, { items: [item], dataset });
    fake.arrive('tiles-src');
    fake.fire('idle');
    L.syncFocusRaster(fake.map as never, view(dataset, item, null));
    expect(fake.layerIds().filter((id) => id.includes('-c'))).toEqual([]);
    expect(fake.layerIds()).toContain('m-tiles-lyr-0');
  });

  it('is not cut a second time by the next sync of the same view, and a cut copy that is not wanted any more is taken away', () => {
    const fake = mapWithLoading();
    const [dataset, item] = [previewDataset(), previewScene('H1')];
    L.syncBrowseMosaic(fake.map as never, { items: [item], dataset });
    fake.arrive('tiles-src');
    fake.fire('idle');
    L.syncFocusRaster(fake.map as never, view(dataset, item, AOI));
    const added = fake.log.sourcesAdded.filter((id) => id.includes('-c')).length;
    L.syncFocusRaster(fake.map as never, view(dataset, item, AOI));
    expect(fake.log.sourcesAdded.filter((id) => id.includes('-c')).length).toBe(added);
    // The view is left (nothing to show): no layer of either bank is left behind.
    L.syncFocusRaster(fake.map as never, { ...view(dataset, item, AOI), showDownloaded: false });
    fake.fire('idle');
    expect(fake.layerIds()).toEqual([]);
  });
});
