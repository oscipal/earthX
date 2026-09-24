import { describe, expect, it } from 'vitest';

import { groupOutlineFeatures } from './groupOutline';
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
