import { describe, expect, it } from 'vitest';

import { coordsBbox, MAX_INTERSECTS_POINTS, quicklookAoiPixelRings, quicklookCoords, searchArea } from './geoUtils';
import type { Coords4 } from './geoUtils';
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

  it('prefers the registry-named asset over visual (M3-12 review F-04)', () => {
    const preferredAsset: StacAsset = {
      href: 'https://example.invalid/data.tif',
      'proj:transform': [10, 0, 400000, 0, -10, 5300000],
      'proj:shape': [500, 500],
    };
    const withVisual = quicklookCoords(edgeItem());
    const withPreferred = quicklookCoords(
      edgeItem({ assets: { visual: VISUAL_ASSET, data: preferredAsset } }),
      'data',
    );
    expect(withPreferred).not.toEqual(withVisual);
    expect(withPreferred).not.toBeNull();
    expect(withPreferred).toHaveLength(4);
  });

  it('falls back to visual when the registry-named asset is missing or has no extent', () => {
    const byName = quicklookCoords(edgeItem(), 'nonexistent');
    const withoutName = quicklookCoords(edgeItem());
    expect(byName).toEqual(withoutName);

    const notGeoreferenced = quicklookCoords(
      edgeItem({ assets: { visual: VISUAL_ASSET, thumbnail: { href: 'https://example.invalid/thumb.jpg' } } }),
      'thumbnail',
    );
    expect(notGeoreferenced).toEqual(withoutName);
  });

  it('shows no quicklook for a non-UTM proj:code it cannot convert', () => {
    expect(quicklookCoords(edgeItem({ properties: { 'proj:code': 'IAU_2015:30100' } }))).toBeNull();
  });

  it('reads EPSG:4326 as the identity — a global raster in geographic coordinates (M3-02 F-03)', () => {
    const asset: StacAsset = { href: 'https://example.invalid/data.tif', 'proj:transform': [1, 0, 5, 0, -1, 50], 'proj:shape': [10, 10] };
    const coords = quicklookCoords(
      edgeItem({ properties: { 'proj:code': 'EPSG:4326' }, assets: { visual: asset } }),
    );
    expect(coords).toEqual([
      [5, 50],
      [15, 50],
      [15, 40],
      [5, 40],
    ]);
  });

  it('returns null without an item', () => {
    expect(quicklookCoords(null)).toBeNull();
    expect(quicklookCoords(undefined)).toBeNull();
  });
});

// M3-12, O5: the AOI, as pixel coordinates on the same asset `quicklookCoords`
// places above — the inverse of that conversion, so a canvas can clip the
// quicklook below `min_zoom` the way a raster tile is clipped.
describe('quicklookAoiPixelRings', () => {
  it('inverts quicklookCoords exactly: the tile corners round-trip to the pixel grid corners', () => {
    const item = edgeItem();
    const [tl, tr, br, bl] = quicklookCoords(item)!;
    const aoi: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[tl, tr, br, bl, tl]] };
    const [ring] = quicklookAoiPixelRings(item, aoi)!;
    // `proj:shape` is [10980, 10980] (VISUAL_ASSET above): (0,0) top-left,
    // (cols,0) top-right, (cols,rows) bottom-right, (0,rows) bottom-left.
    expect(ring[0][0]).toBeCloseTo(0, 3);
    expect(ring[0][1]).toBeCloseTo(0, 3);
    expect(ring[1][0]).toBeCloseTo(10980, 3);
    expect(ring[1][1]).toBeCloseTo(0, 3);
    expect(ring[2][0]).toBeCloseTo(10980, 3);
    expect(ring[2][1]).toBeCloseTo(10980, 3);
    expect(ring[3][0]).toBeCloseTo(0, 3);
    expect(ring[3][1]).toBeCloseTo(10980, 3);
  });

  it('places a smaller AOI somewhere inside the pixel grid, in proportion', () => {
    // The centre of the tile lands at the centre of the pixel grid.
    const item = edgeItem();
    const [tl, tr, br, bl] = quicklookCoords(item)!;
    const cx = (tl[0] + tr[0] + br[0] + bl[0]) / 4;
    const cy = (tl[1] + tr[1] + br[1] + bl[1]) / 4;
    const d = 0.001;
    const aoi: GeoJSON.Polygon = {
      type: 'Polygon',
      coordinates: [[[cx - d, cy - d], [cx + d, cy - d], [cx + d, cy + d], [cx - d, cy + d], [cx - d, cy - d]]],
    };
    const [ring] = quicklookAoiPixelRings(item, aoi)!;
    for (const [px, py] of ring) {
      expect(px).toBeGreaterThan(0);
      expect(px).toBeLessThan(10980);
      expect(py).toBeGreaterThan(0);
      expect(py).toBeLessThan(10980);
    }
  });

  it('carries a hole through as a second ring', () => {
    const item = edgeItem();
    const [tl, tr, br, bl] = quicklookCoords(item)!;
    const cx = (tl[0] + tr[0] + br[0] + bl[0]) / 4;
    const cy = (tl[1] + tr[1] + br[1] + bl[1]) / 4;
    const d = 0.001;
    const hole: number[][] = [[cx - d, cy - d], [cx + d, cy - d], [cx + d, cy + d], [cx - d, cy + d], [cx - d, cy - d]];
    const aoi: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[tl, tr, br, bl, tl], hole] };
    expect(quicklookAoiPixelRings(item, aoi)).toHaveLength(2);
  });

  it('is null when the item has no usable CRS, mirroring quicklookCoords', () => {
    const item = edgeItem({ properties: { datetime: '2026-09-20T10:37:40Z' } });
    expect(quicklookAoiPixelRings(item, { type: 'Polygon', coordinates: [[[0, 0]]] })).toBeNull();
  });

  it('clips onto the registry-named asset\'s pixel grid, not visual\'s (M3-12 review F-04)', () => {
    const preferredAsset: StacAsset = {
      href: 'https://example.invalid/data.tif',
      'proj:transform': [10, 0, 499980, 0, -10, 5300040],
      'proj:shape': [500, 500],
    };
    const item = edgeItem({ assets: { visual: VISUAL_ASSET, data: preferredAsset } });
    const [tl, tr, br, bl] = quicklookCoords(item, 'data')!;
    const aoi: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[tl, tr, br, bl, tl]] };
    const [ring] = quicklookAoiPixelRings(item, aoi, 'data')!;
    expect(ring[2][0]).toBeCloseTo(500, 3);
    expect(ring[2][1]).toBeCloseTo(500, 3);
  });

  it('is null without a georeferenced asset', () => {
    const item = edgeItem({ assets: { visual: { href: 'https://example.invalid/visual.tif' } } });
    expect(quicklookAoiPixelRings(item, { type: 'Polygon', coordinates: [[[0, 0]]] })).toBeNull();
  });
});

describe('coordsBbox', () => {
  it('wraps a quicklook quad in its bounding box (V-2, store.ts::zoomToView)', () => {
    const quad: Coords4 = [
      [9, 48],
      [10.5, 48],
      [10.5, 47],
      [9, 47],
    ];
    expect(coordsBbox(quad)).toEqual([9, 47, 10.5, 48]);
  });

  it('handles an unordered / degenerate quad the same way', () => {
    const quad: Coords4 = [
      [0, 0],
      [0, 0],
      [5, 5],
      [-2, 3],
    ];
    expect(coordsBbox(quad)).toEqual([-2, 0, 5, 5]);
  });
});

describe('searchArea', () => {
  const RECTANGLE: GeoJSON.Geometry = {
    type: 'Polygon',
    coordinates: [[[8, 47], [12, 47], [12, 51], [8, 51], [8, 47]]],
  };
  const TRIANGLE: GeoJSON.Geometry = {
    type: 'Polygon',
    coordinates: [[[8, 47], [12, 47], [8, 51], [8, 47]]],
  };
  const POINT: GeoJSON.Point = { type: 'Point', coordinates: [10, 49] };

  function convexRing(n: number): GeoJSON.Position[] {
    const ring: GeoJSON.Position[] = Array.from({ length: n }, (_, i) => [
      10 + 0.01 * Math.cos((2 * Math.PI * i) / n),
      49 + 0.01 * Math.sin((2 * Math.PI * i) / n),
    ]);
    ring.push(ring[0]);
    return ring;
  }

  it('a point searches by intersects, regardless of the AOI polygon passed alongside it', () => {
    expect(searchArea(RECTANGLE, POINT)).toEqual({ intersects: POINT });
  });

  it('no AOI and no point is an empty area', () => {
    expect(searchArea(null, null)).toEqual({});
  });

  it('a rectangle searches by bbox', () => {
    expect(searchArea(RECTANGLE, null)).toEqual({ bbox: [8, 47, 12, 51] });
  });

  it('a triangle searches by intersects', () => {
    expect(searchArea(TRIANGLE, null)).toEqual({ intersects: TRIANGLE });
  });

  it('a polygon at exactly the point budget still searches by intersects', () => {
    const polygon: GeoJSON.Geometry = { type: 'Polygon', coordinates: [convexRing(MAX_INTERSECTS_POINTS - 1)] };
    const result = searchArea(polygon, null);
    expect(result.intersects).toBe(polygon);
    expect(result.truncatedNotice).toBeUndefined();
  });

  it('a polygon over the point budget falls back to its bbox, with a notice', () => {
    const polygon: GeoJSON.Geometry = { type: 'Polygon', coordinates: [convexRing(MAX_INTERSECTS_POINTS)] };
    const result = searchArea(polygon, null);
    expect(result.intersects).toBeUndefined();
    expect(result.bbox).toBeDefined();
    expect(result.truncatedNotice).toMatch(new RegExp(`more than ${MAX_INTERSECTS_POINTS} points`));
  });

  it('a MultiPolygon (not a rectangle) still searches by intersects', () => {
    const multi: GeoJSON.Geometry = {
      type: 'MultiPolygon',
      coordinates: [
        [[[8, 47], [9, 47], [9, 48], [8, 48], [8, 47]]],
        [[[11, 50], [12, 50], [12, 51], [11, 51], [11, 50]]],
      ],
    };
    expect(searchArea(multi, null)).toEqual({ intersects: multi });
  });
});
