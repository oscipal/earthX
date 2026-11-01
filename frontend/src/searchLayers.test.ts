import { describe, expect, it } from 'vitest';

import { buildTileTemplate } from './api';
import { mosaicTemplateOf } from './mosaic';
import type { Mosaics, SceneEntry } from './mosaic';
import { overlaysOfPass } from './searchLayers';
import type { AppliedRender } from './types';

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 47]]] };
const RENDER: AppliedRender = { colormapName: 'terrain', rescale: '0,4000' };

const entry = (id: string): SceneEntry => [
  id,
  { datasetId: 'sentinel-2-c1-l2a', tileUrl: buildTileTemplate('dem', id, 'data'), bounds: [10, 47, 11, 48], asset: 'data', minZoom: 0, maxZoom: 15 },
];

// The overlays a pinned layer draws for a pass of scenes: its mosaic under the scenes that step aside, else the scenes.
describe('overlaysOfPass', () => {
  const entries = [entry('a'), entry('b')];
  const mosaicOf = (order = ['a', 'b']): Mosaics => {
    const tileUrl = mosaicTemplateOf('dem', entries) as string;
    return { [tileUrl]: { tileUrl, bounds: [9, 46, 12, 49], minZoom: 8, maxZoom: 15, order } };
  };
  const rasters = (overlays: ReturnType<typeof overlaysOfPass>) =>
    (overlays ?? []).map((o) => {
      if (o.kind !== 'raster') throw new Error('expected a raster overlay');
      return o;
    });

  it('is one mosaic overlay under the two scenes that step aside from z8, all clipped', () => {
    const overlays = rasters(overlaysOfPass('dem', entries, mosaicOf(), RENDER, AOI));
    expect(overlays).toHaveLength(3);
    expect(overlays.every((o) => o.tileUrl.startsWith('earthx-clip://'))).toBe(true);
    expect(overlays.slice(0, 2).map((o) => [o.maxZoom, o.hideFrom])).toEqual([[7, 7.5], [7, 7.5]]);
    expect(overlays[2].tileUrl).toContain('/collections/dem/mosaic/tiles/');
    expect(overlays[2].tileUrl).toContain('colormap_name=terrain');
    expect([overlays[2].minZoom, overlays[2].maxZoom, overlays[2].hideFrom]).toEqual([8, 15, undefined]);
  });

  it('stacks the scenes in the order the mosaic reads them, the first on top', () => {
    const [bottom, top] = rasters(overlaysOfPass('dem', entries, mosaicOf(['b', 'a']), RENDER, AOI));
    expect(bottom.tileUrl).toContain('/items/a/');
    expect(top.tileUrl).toContain('/items/b/');
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
