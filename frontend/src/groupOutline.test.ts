import { union } from 'polyclip-ts';
import { describe, expect, it } from 'vitest';

import { groupOutlineFeatures, snapFootprints } from './groupOutline';
import type { StacItem, TimeStepGroup } from './types';

function item(id: string, bbox: [number, number, number, number], geometry?: GeoJSON.Geometry): StacItem {
  return { id, bbox, geometry, properties: {}, assets: {} };
}

function group(key: string, items: StacItem[]): TimeStepGroup {
  return { key: [key], label: key, items };
}

function poly(coords: number[][]): GeoJSON.Polygon {
  return { type: 'Polygon', coordinates: [coords] };
}

const BIG_AOI = poly([
  [-10, -10],
  [10, -10],
  [10, 10],
  [-10, 10],
  [-10, -10],
]);

describe('groupOutlineFeatures', () => {
  it('merges two overlapping scenes of one group into a single ring', () => {
    const g = group('a', [item('S1', [0, 0, 2, 2]), item('S2', [1, 1, 3, 3])]);
    const features = groupOutlineFeatures([g], new Set(['S1', 'S2']), BIG_AOI);
    expect(features).toHaveLength(1);
    expect(features[0].geometry.type).toBe('Polygon');
    expect(features[0].properties.fallback).toBe(false);
    expect(features[0].properties.groupKey).toBe('a');
  });

  it('gives two groups two separate rings', () => {
    const groups = [group('a', [item('S1', [0, 0, 2, 2])]), group('b', [item('S2', [5, 5, 7, 7])])];
    const features = groupOutlineFeatures(groups, new Set(['S1', 'S2']), BIG_AOI);
    expect(features).toHaveLength(2);
    expect(new Set(features.map((f) => f.properties.groupKey))).toEqual(new Set(['a', 'b']));
  });

  it('skips a group whose items are not in the visible set', () => {
    const g = group('a', [item('S1', [0, 0, 2, 2])]);
    expect(groupOutlineFeatures([g], new Set(), BIG_AOI)).toHaveLength(0);
  });

  it('draws nothing for a group entirely outside the AOI, like a single scene would', () => {
    const g = group('a', [item('S1', [100, 100, 102, 102])]);
    expect(groupOutlineFeatures([g], new Set(['S1']), BIG_AOI)).toHaveLength(0);
  });

  it('falls back to per-scene footprints when the merge computation itself fails', () => {
    // A degenerate coordinate (`NaN`) makes polyclip-ts throw rather than
    // return a shape — this is the "Schlägt sie fehl" half of Otto's F4.
    const broken = poly([
      [0, 0],
      [NaN, 0],
      [2, 2],
      [0, 2],
      [0, 0],
    ]);
    const g = group('a', [item('S1', [0, 0, 2, 2], broken), item('S2', [1, 1, 3, 3])]);
    const features = groupOutlineFeatures([g], new Set(['S1', 'S2']), BIG_AOI);
    expect(features).toHaveLength(2);
    expect(features.every((f) => f.properties.fallback)).toBe(true);
    expect(features.every((f) => f.properties.groupKey === 'a')).toBe(true);
  });

  it('falls back to per-scene footprints for a group whose footprint spans the antimeridian', () => {
    // A footprint stretching from lon 179 to -179 reads, in flat coordinates,
    // as 358° wide instead of the 2° it actually covers — the "reicht über
    // den Antimeridian" half of Otto's F4. No exception here (polyclip-ts
    // happily computes a wrong answer), so this must be caught before ever
    // calling union/intersection.
    const acrossDateline: GeoJSON.Polygon = {
      type: 'Polygon',
      coordinates: [
        [
          [179, 10],
          [-179, 10],
          [-179, 11],
          [179, 11],
          [179, 10],
        ],
      ],
    };
    const g = group('a', [item('S1', [179, 10, -179, 11], acrossDateline)]);
    const features = groupOutlineFeatures([g], new Set(['S1']), BIG_AOI);
    expect(features).toHaveLength(1);
    expect(features[0].properties.fallback).toBe(true);
  });

  it('falls every group back when the AOI itself is not a Polygon/MultiPolygon', () => {
    const g = group('a', [item('S1', [0, 0, 2, 2])]);
    const notAPolygon: GeoJSON.Point = { type: 'Point', coordinates: [0, 0] };
    const features = groupOutlineFeatures([g], new Set(['S1']), notAPolygon);
    expect(features).toHaveLength(1);
    expect(features[0].properties.fallback).toBe(true);
  });

  it('merges a MultiPolygon AOI the same way as a Polygon one', () => {
    const multiAoi: GeoJSON.MultiPolygon = { type: 'MultiPolygon', coordinates: [BIG_AOI.coordinates] };
    const g = group('a', [item('S1', [0, 0, 2, 2])]);
    const features = groupOutlineFeatures([g], new Set(['S1']), multiAoi);
    expect(features).toHaveLength(1);
    expect(features[0].properties.fallback).toBe(false);
  });
});

// Two slices of one pass in the shape Earth Search gives Sentinel-1 (synthetic numbers): the top edge of the southern
// slice and the bottom edge of the northern one should be one line, but lie a few thousandths of a degree apart, now
// overlapping, now leaving a gap, and the northern one has a corner on that edge the southern one lacks.
const SOUTH = poly([
  [0, 0],
  [3, 0.3],
  [2.9, 1.5],
  [1.5, 1.35],
  [-0.1, 1.2],
  [0, 0],
]);
const NORTH = poly([
  [-0.096, 1.197],
  [0.7, 1.2785],
  [1.497, 1.354],
  [2.904, 1.498],
  [2.8, 2.7],
  [-0.2, 2.4],
  [-0.096, 1.197],
]);
// An AOI across the seam, inside both slices left and right.
const ACROSS_SEAM = poly([
  [0.5, 0.8],
  [2.5, 0.8],
  [2.5, 2],
  [0.5, 2],
  [0.5, 0.8],
]);
const ringCount = (features: ReturnType<typeof groupOutlineFeatures>) =>
  features.reduce((sum, f) => sum + (f.geometry.type === 'Polygon' ? f.geometry.coordinates.length : f.geometry.coordinates.flat().length), 0);

describe('the outline of a merged pass draws no scene boundary (Otto, 9.11.2026)', () => {
  it('is what fell apart before: the plain union of the two slices is not one ring', () => {
    const plain = union(SOUTH.coordinates as never, NORTH.coordinates as never);
    expect(plain.length + plain.reduce((sum, polygon) => sum + polygon.length - 1, 0)).toBeGreaterThan(1);
  });

  it('draws one ring for two slices of one pass whose edges almost meet', () => {
    const g = group('pass', [item('SOUTH', [-0.1, 0, 3, 1.5], SOUTH), item('NORTH', [-0.2, 1.197, 2.904, 2.7], NORTH)]);
    for (const aoi of [BIG_AOI, ACROSS_SEAM]) {
      const features = groupOutlineFeatures([g], new Set(['SOUTH', 'NORTH']), aoi);
      expect(features).toHaveLength(1);
      expect(features[0].properties.fallback).toBe(false);
      expect(ringCount(features)).toBe(1);
    }
  });

  it('cuts no slit into the ring: across the AOI the outline is the edge of the AOI alone', () => {
    // Both slices cover the AOI whole; the plain union leaves a gap that ends just short of its edge, one ring with a
    // narrow cut in it, drawn as the same double line.
    const g = group('pass', [item('SOUTH', [-0.1, 0, 3, 1.5], SOUTH), item('NORTH', [-0.2, 1.197, 2.904, 2.7], NORTH)]);
    for (const right of [2.5, 2.2]) {
      const aoi = poly([
        [0.5, 0.8],
        [right, 0.8],
        [right, 2],
        [0.5, 2],
        [0.5, 0.8],
      ]);
      const features = groupOutlineFeatures([g], new Set(['SOUTH', 'NORTH']), aoi);
      const corners = features.flatMap((f) => (f.geometry.type === 'Polygon' ? f.geometry.coordinates : f.geometry.coordinates.flat()).flat());
      expect(corners.filter(([x, y]) => x > 0.5 && x < right && y > 0.8 && y < 2)).toEqual([]);
    }
  });

  it('draws one ring whichever slice comes first', () => {
    const g = group('pass', [item('NORTH', [-0.2, 1.197, 2.904, 2.7], NORTH), item('SOUTH', [-0.1, 0, 3, 1.5], SOUTH)]);
    expect(ringCount(groupOutlineFeatures([g], new Set(['SOUTH', 'NORTH']), ACROSS_SEAM))).toBe(1);
  });

  it('keeps a real gap between two scenes: 0.05° is more than the tolerance', () => {
    const lifted = poly(NORTH.coordinates[0].map(([x, y]) => [x, y + 0.05]));
    const g = group('pass', [item('SOUTH', [-0.1, 0, 3, 1.5], SOUTH), item('NORTH', [-0.2, 1.247, 2.904, 2.75], lifted)]);
    expect(ringCount(groupOutlineFeatures([g], new Set(['SOUTH', 'NORTH']), ACROSS_SEAM))).toBe(2);
  });

  it('leaves two tiles of an optical pass that overlap widely as their plain union (Sentinel-2)', () => {
    const g = group('pass', [item('T1', [0, 0, 1, 1]), item('T2', [0.9, 0, 1.9, 1])]);
    const features = groupOutlineFeatures([g], new Set(['T1', 'T2']), BIG_AOI);
    expect(features).toHaveLength(1);
    const ring = (features[0].geometry as GeoJSON.Polygon).coordinates[0];
    expect(new Set(ring.map(([x, y]) => `${x},${y}`))).toEqual(new Set(['0,0', '1.9,0', '1.9,1', '0,1']));
  });
});

describe('snapFootprints', () => {
  it('moves no corner farther than the tolerance and keeps corners far from another footprint', () => {
    const [south, north] = snapFootprints([SOUTH.coordinates as never, NORTH.coordinates as never]);
    const moved = (before: number[][], after: number[][]) => before.every(([x, y]) => after.some(([u, v]) => Math.hypot(x - u, y - v) <= 0.01));
    expect(moved(SOUTH.coordinates[0], (south as number[][][])[0])).toBe(true);
    expect(moved(NORTH.coordinates[0], (north as number[][][])[0])).toBe(true);
    expect((north as number[][][])[0]).toContainEqual([2.8, 2.7]);
    expect((south as number[][][])[0]).toContainEqual([0, 0]);
  });

  it('gives the two slices the same points along their common edge', () => {
    const [south, north] = snapFootprints([SOUTH.coordinates as never, NORTH.coordinates as never]);
    const key = ([x, y]: number[]) => `${x},${y}`;
    const southPoints = new Set((south as number[][][])[0].map(key));
    const shared = (north as number[][][])[0].filter((point) => southPoints.has(key(point)));
    expect(new Set(shared.map(key))).toEqual(new Set(['-0.1,1.2', '0.7,1.2785', '1.5,1.35', '2.9,1.5']));
  });

  it('changes nothing for a single footprint, an empty list or a tolerance of 0', () => {
    expect(snapFootprints([SOUTH.coordinates as never])).toEqual([SOUTH.coordinates]);
    expect(snapFootprints([])).toEqual([]);
    expect(snapFootprints([SOUTH.coordinates as never, NORTH.coordinates as never], 0)).toEqual([SOUTH.coordinates, NORTH.coordinates]);
  });

  it('snaps the parts of a MultiPolygon footprint like a Polygon', () => {
    const [, north] = snapFootprints([SOUTH.coordinates as never, [NORTH.coordinates] as never]);
    expect((north as number[][][][])[0][0][0]).toEqual([-0.1, 1.2]);
  });
});
