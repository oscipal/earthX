import { describe, expect, it } from 'vitest';

import { quicklookCoords } from './geoUtils';
import type { StacAsset, StacItem } from './types';

// A real edge scene (S2C_T32TNT_20260920T103025_L2A, 2026-09-20, MGRS 32TNT):
// its data geometry is clipped by the swath edge and is markedly smaller than
// the full MGRS tile the thumbnail actually depicts, so the corners must come
// from the tile (the `visual` asset's pixel grid), not the geometry.
const EDGE_GEOMETRY: GeoJSON.Geometry = {
  type: 'Polygon',
  coordinates: [
    [
      [8.999746010269405, 47.85369284462768],
      [8.999750703868813, 46.86660885273466],
      [9.227707690485033, 46.86745689891034],
      [9.668828320072095, 47.851744724546236],
      [8.999746010269405, 47.85369284462768],
    ],
  ],
};
const EDGE_BBOX: [number, number, number, number] = [8.999746, 46.866609, 9.668828, 47.853693];

const VISUAL_ASSET: StacAsset = {
  href: 'https://example.invalid/visual.tif',
  'proj:transform': [10, 0, 499980, 0, -10, 5300040],
  'proj:shape': [10980, 10980],
};

function edgeItem(overrides: Partial<StacItem> = {}): StacItem {
  return {
    id: 'S2C_T32TNT_20260920T103025_L2A',
    bbox: EDGE_BBOX,
    geometry: EDGE_GEOMETRY,
    properties: { datetime: '2026-09-20T10:37:40.886000Z', 'proj:epsg': 32632 },
    assets: { visual: VISUAL_ASSET },
    ...overrides,
  };
}

describe('quicklookCoords', () => {
  it('takes the corners from the tile (visual asset extent), not the smaller data geometry', () => {
    const coords = quicklookCoords(edgeItem());
    expect(coords).not.toBeNull();
    const [tl, tr, br, bl] = coords!;

    // The full MGRS tile reaches noticeably further east/north than the
    // clipped geometry (max lon 9.6688) — this is the whole point of the fix.
    expect(tr[0]).toBeGreaterThan(EDGE_BBOX[2] + 0.3);

    expect(tl[0]).toBeCloseTo(8.999733, 4);
    expect(tl[1]).toBeCloseTo(47.853702, 4);
    expect(tr[0]).toBeCloseTo(10.467277, 4);
    expect(tr[1]).toBeCloseTo(47.844325, 4);
    expect(br[0]).toBeCloseTo(10.44015, 4);
    expect(br[1]).toBeCloseTo(46.85664, 4);
    expect(bl[0]).toBeCloseTo(8.999738, 4);
    expect(bl[1]).toBeCloseTo(46.8657, 4);
  });

  it('reads a string proj:code the same way as a numeric proj:epsg', () => {
    const byCode = quicklookCoords(
      edgeItem({ properties: { 'proj:code': 'EPSG:32632' } }),
    );
    const byEpsg = quicklookCoords(edgeItem());
    expect(byCode).toEqual(byEpsg);
  });

  it('shows no quicklook when the item has neither proj:code nor proj:epsg', () => {
    expect(quicklookCoords(edgeItem({ properties: { datetime: '2026-09-20T10:37:40Z' } }))).toBeNull();
  });

  it('shows no quicklook when no asset carries proj:transform/proj:shape', () => {
    expect(quicklookCoords(edgeItem({ assets: { visual: { href: 'https://example.invalid/visual.tif' } } }))).toBeNull();
  });

  it('falls back to another georeferenced asset when visual is missing', () => {
    const coords = quicklookCoords(
      edgeItem({ assets: { red: { ...VISUAL_ASSET, href: 'https://example.invalid/red.tif' } } }),
    );
    expect(coords).not.toBeNull();
  });

  it('shows no quicklook for a non-UTM proj:code it cannot convert', () => {
    expect(quicklookCoords(edgeItem({ properties: { 'proj:code': 'IAU_2015:30100' } }))).toBeNull();
  });

  it('returns null without an item', () => {
    expect(quicklookCoords(null)).toBeNull();
    expect(quicklookCoords(undefined)).toBeNull();
  });
});
