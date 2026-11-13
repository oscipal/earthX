import { describe, expect, it } from 'vitest';

import { buildTileTemplate } from './api';
import { mosaicKeyOf, orderKeyOf } from './mosaic';
import type { Mosaics, SceneEntry } from './mosaic';
import { overlaysOfPass } from './searchLayers';
import type { AppliedRender } from './types';

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 47]]] };
const RENDER: AppliedRender = { colormapName: 'terrain', rescale: '0,4000' };

const entry = (id: string): SceneEntry => [
  id,
  { datasetId: 'sentinel-2-c1-l2a', tileUrl: buildTileTemplate('dem', id, 'data'), bounds: [10, 47, 11, 48], asset: 'data', minZoom: 0, maxZoom: 15 },
];

// The overlays a pinned layer draws for a pass of scenes: its mosaic, else the scenes.
describe('overlaysOfPass', () => {
  const entries = [entry('a'), entry('b')];
  const mosaicOf = (order = ['a', 'b']): Mosaics => {
    const tileUrl = '/collections/dem/mosaic/0123456789abcdef0123456789abcdef/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=512';
    return { [mosaicKeyOf('dem', entries) as string]: { tileUrl, bounds: [9, 46, 12, 49], minZoom: 8, maxZoom: 15, order } };
  };
  const rasters = (overlays: ReturnType<typeof overlaysOfPass>) =>
    (overlays ?? []).map((o) => {
      if (o.kind !== 'raster') throw new Error('expected a raster overlay');
      return o;
    });

  it('is one mosaic overlay of the selection, clipped, with no scene under it', () => {
    const overlays = rasters(overlaysOfPass('dem', entries, mosaicOf(), RENDER, AOI));
    expect(overlays).toHaveLength(1);
    expect(overlays[0].tileUrl.startsWith('earthx-clip://')).toBe(true);
    expect(overlays[0].tileUrl).toContain('/collections/dem/mosaic/0123456789abcdef0123456789abcdef/tiles/');
    expect(overlays[0].tileUrl).not.toContain('item=');
    expect(overlays[0].tileUrl).toContain('colormap_name=terrain');
    expect([overlays[0].minZoom, overlays[0].maxZoom, overlays[0].hideFrom]).toEqual([8, 15, undefined]);
  });

  it('stacks the scenes drawn one by one in the order the tiler gave, not in the order they were ticked (NM4-24)', () => {
    const refused = { [mosaicKeyOf('dem', entries) as string]: null, [orderKeyOf('dem', entries) as string]: { order: ['b', 'a'] } };
    const [bottom, top] = rasters(overlaysOfPass('dem', entries, refused, RENDER, AOI));
    expect(bottom.tileUrl).toContain('/items/a/');
    expect(top.tileUrl).toContain('/items/b/');
    // The other way round: ticked b, then a.
    const [low, high] = rasters(overlaysOfPass('dem', [...entries].reverse(), refused, RENDER, AOI));
    expect([low.tileUrl, high.tileUrl].map((u) => /items\/(\w)\//.exec(u)![1])).toEqual(['a', 'b']);
  });

  it('is drawn scene by scene when the mosaic was refused, or there is none', () => {
    for (const mosaics of [undefined, Object.fromEntries(Object.keys(mosaicOf()).map((k) => [k, null]))]) {
      const overlays = rasters(overlaysOfPass('dem', entries, mosaics, RENDER, AOI));
      expect(overlays).toHaveLength(2);
      expect(overlays.every((o) => o.hideFrom === undefined && o.tileUrl.includes('/items/'))).toBe(true);
    }
  });

  it('is nothing yet while the mosaic is on its way: a layer is not made from half of one', () => {
    expect(overlaysOfPass('dem', entries, {}, RENDER, AOI)).toBeNull();
  });

  it('leaves a pass of one scene a scene, and does not cut it where there is no AOI', () => {
    const [overlay] = rasters(overlaysOfPass('dem', [entry('a')], {}, RENDER, null));
    expect(overlay.tileUrl.startsWith('earthx-clip://')).toBe(false);
    expect(overlay.tileUrl).toContain('/items/a/');
  });
});
