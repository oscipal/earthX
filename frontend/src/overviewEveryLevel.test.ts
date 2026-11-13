// Plan M5-30b §8.8 (finding of 13.11.2026): no dataset loses its picture when the map zooms out, at no level and not between
// two parts. swissALTI3D draws its own mosaic from level 13 and the picture of GLO-30 below it; in "Crop and merge to AOI",
// and in the layer pinned from that view, at every map zoom from 0 to 13.9 at least one raster of the layer is drawn, and
// every one of them goes through the AOI clip.

import { describe, expect, it } from 'vitest';

import { AOI, DOWNLOADED, ENTRIES, GROUPS, ITEMS, LIST, MOSAICS, TERRAIN } from './fixtures/swissalti';
import { zoomMap } from './fixtures/zoomMap';
import { syncFocusRaster, syncLayers } from './mapLayers';
import { overlaysOfPass, substituteOverlaysOf } from './searchLayers';

// Every map zoom from 0 to 13.9 in tenths: below 13 the substitute, from 12.5 the mosaic (512 px tiles of level 13).
const ZOOMS = Array.from({ length: 140 }, (_, i) => i / 10);
const view = (over: Record<string, unknown> = {}) => ({
  downloaded: DOWNLOADED,
  render: { rescale: '0,3000' },
  showDownloaded: true,
  aoi: AOI,
  cropToAoi: true,
  items: ITEMS,
  dataset: TERRAIN,
  datasets: LIST,
  groups: GROUPS,
  mosaics: MOSAICS,
  ...over,
});
const hole = (live: ReturnType<typeof zoomMap>) => ZOOMS.filter((zoom) => live.picturesAt(zoom).length === 0);
const urlOf = (live: ReturnType<typeof zoomMap>, layerId: string) => {
  const source = live.layers.get(layerId)!.source!;
  return (live.sources.get(source)!.tiles as string[])[0];
};

describe('swissALTI3D in "Crop and merge to AOI"', () => {
  it('draws an image at every map zoom from 0 to 13.9: the substitute below level 13, the mosaic from there on', () => {
    const live = zoomMap();
    syncFocusRaster(live.map as never, view());
    expect(hole(live)).toEqual([]);
    expect(live.picturesAt(0)).toHaveLength(1);
    expect(urlOf(live, live.picturesAt(0)[0])).toContain('/collections/terrain/overview/tiles/');
    expect(urlOf(live, live.picturesAt(13.5)[0])).toContain('/mosaic/');
    expect(live.picturesAt(12.4)).toHaveLength(1);
    expect(live.picturesAt(12.5)).toHaveLength(1);
  });

  it('clips every one of them to the AOI in the browser, the substitute as the mosaic', () => {
    const live = zoomMap();
    syncFocusRaster(live.map as never, view());
    for (const zoom of ZOOMS) {
      for (const id of live.picturesAt(zoom)) expect(urlOf(live, id), `z${zoom}`).toMatch(/^earthx-clip:\/\//);
    }
  });

  it('has the substitute at every level below 13 while the selection of the mosaic is still on its way', () => {
    const live = zoomMap();
    syncFocusRaster(live.map as never, view({ mosaics: {} }));
    expect(ZOOMS.filter((zoom) => zoom < 12.5 && live.picturesAt(zoom).length === 0)).toEqual([]);
  });

  it('has it with one scene and with the scenes drawn one by one, too', () => {
    for (const only of [['A'], ['A', 'B']]) {
      const live = zoomMap();
      const own = Object.fromEntries(only.map((id) => [id, { ...DOWNLOADED[id], tileUrl: '/collections/terrain/items/x/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=512' }]));
      syncFocusRaster(live.map as never, view({ downloaded: own, mosaics: {}, groups: [] }));
      expect(ZOOMS.filter((zoom) => zoom < 12.5 && live.picturesAt(zoom).length === 0), only.join()).toEqual([]);
    }
  });

  it('draws the substitute without the clip where the view is not cropped, and still at every level', () => {
    const live = zoomMap();
    syncFocusRaster(live.map as never, view({ cropToAoi: false }));
    expect(hole(live)).toEqual([]);
    expect(urlOf(live, live.picturesAt(3)[0])).not.toMatch(/^earthx-clip:/);
  });
});

describe('the layer pinned from that view', () => {
  const overlays = () => {
    const own = overlaysOfPass('terrain', ENTRIES, MOSAICS, { rescale: '0,3000' }, AOI);
    return [...substituteOverlaysOf(['terrain'], LIST, { rescale: '0,3000' }, AOI), ...(own ?? [])];
  };

  it('has an image at every map zoom from 0 to 13.9', () => {
    const live = zoomMap();
    syncLayers(live.map as never, [{ id: 'a', name: 'Terrain', visible: true, opacity: 1, overlays: overlays(), restore: { datasetId: 'terrain' } as never }]);
    expect(overlays()).toHaveLength(2);
    expect(hole(live)).toEqual([]);
    for (const zoom of ZOOMS) {
      for (const id of live.picturesAt(zoom)) expect(urlOf(live, id), `z${zoom}`).toMatch(/^earthx-clip:\/\//);
    }
  });
});
