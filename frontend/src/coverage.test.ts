import { describe, expect, it } from 'vitest';

import type { CoverageCell, CoverageResponse } from './api';
import {
  bandViewportBbox,
  bboxContains,
  cellBbox,
  cellsToFeatureCollection,
  clampBboxLongitude,
  completenessNote,
  coverageFillColorExpression,
  FOOTPRINT_MIN_ZOOM,
  InvalidCellKey,
  levelForViewport,
  MIN_VIEWPORT_LEVEL,
  roundBboxToGrid,
  showFootprints,
} from './coverage';

// The 4 worked examples of backend/tests/catalog/test_coverage.py's
// TestGridArithmetic, mirrored one to one so a cell key means the same box on
// both sides of the wire.
describe('cellBbox', () => {
  it('level zero is the whole world', () => {
    const [west, south, east, north] = cellBbox('0/0/0');
    expect(west).toBe(-180);
    expect(east).toBe(180);
    expect(south).toBeCloseTo(-85.051129, 5);
    expect(north).toBeCloseTo(85.051129, 5);
  });

  it('a measured cell lands where it was measured (central Europe)', () => {
    const [west, south, east, north] = cellBbox('8/133/84');
    expect(west).toBeGreaterThanOrEqual(5);
    expect(east).toBeLessThanOrEqual(15);
    expect(west).toBeLessThan(east);
    expect(south).toBeGreaterThanOrEqual(45);
    expect(north).toBeLessThanOrEqual(55);
    expect(south).toBeLessThan(north);
  });

  it('cells of one level tile without a gap', () => {
    expect(cellBbox('4/7/5')[2]).toBeCloseTo(cellBbox('4/8/5')[0], 10);
    expect(cellBbox('4/7/5')[1]).toBeCloseTo(cellBbox('4/7/6')[3], 10);
  });

  it.each([
    ['8/133', 'too few parts'],
    ['8/133/84/2', 'too many parts'],
    ['8/x/84', 'not a number'],
    ['3/8/0', 'column outside 2**3'],
    ['3/0/8', 'row outside 2**3'],
    ['30/0/0', 'a level the source would refuse'],
    ['-1/0/0', 'a negative level'],
    ['', 'empty'],
  ])('refuses %s (%s)', (key) => {
    expect(() => cellBbox(key)).toThrow(InvalidCellKey);
  });
});

describe('clampBboxLongitude', () => {
  it('leaves an ordinary bbox unchanged', () => {
    expect(clampBboxLongitude([5, 45, 15, 55])).toEqual([5, 45, 15, 55]);
  });

  it('clamps a west/east pair from a wrapped world copy', () => {
    expect(clampBboxLongitude([-200, 10, -170, 20])).toEqual([-180, 10, -170, 20]);
    expect(clampBboxLongitude([170, 10, 210, 20])).toEqual([170, 10, 180, 20]);
  });

  it('never touches latitude', () => {
    expect(clampBboxLongitude([-190, -95, 190, 95])).toEqual([-180, -95, 180, 95]);
  });
});

describe('cellsToFeatureCollection', () => {
  it('carries the count as the `n` property the paint expression reads', () => {
    const fc = cellsToFeatureCollection([{ k: '4/7/5', n: 42 }]);
    expect(fc.features).toHaveLength(1);
    expect(fc.features[0]?.properties).toEqual({ n: 42 });
  });

  it('skips a key it cannot parse instead of throwing (zweckfremde Nutzung)', () => {
    const cells: CoverageCell[] = [
      { k: 'not-a-key', n: 1 },
      { k: '4/7/5', n: 2 },
    ];
    expect(cellsToFeatureCollection(cells).features).toHaveLength(1);
  });

  it('is empty for an empty response, not an error', () => {
    expect(cellsToFeatureCollection([]).features).toEqual([]);
  });
});

describe('coverageFillColorExpression', () => {
  it('anchors the log scale on the response maximum, not a fixed density', () => {
    const low = coverageFillColorExpression(10);
    const high = coverageFillColorExpression(10_000);
    // Same shape (interpolate/log10/get n), different stop values.
    expect(low[0]).toBe('interpolate');
    expect(low[2]).toEqual(['log10', ['get', 'n']]);
    expect(low).not.toEqual(high);
  });

  it('never divides by zero for an all-empty response', () => {
    expect(() => coverageFillColorExpression(0)).not.toThrow();
  });

  // MapLibre rejects an `interpolate` expression whose stops are not
  // strictly ascending — found by loading the layer in a real browser
  // (`addLayer`'s paint type is untyped `any`, so tsc never catches it).
  // `maxCount <= 1` is the case that used to collapse every stop to 0.
  it.each([0, 1])('keeps every stop strictly ascending for maxCount=%d', (maxCount) => {
    const expr = coverageFillColorExpression(maxCount);
    const values = expr.slice(3).filter((_, i) => i % 2 === 0) as number[];
    for (let i = 1; i < values.length; i++) {
      expect(values[i]).toBeGreaterThan(values[i - 1]);
    }
  });
});

function response(overrides: Partial<CoverageResponse> = {}): CoverageResponse {
  return {
    dataset_id: 'sentinel-2-c1-l2a',
    grid: 'geotile',
    level: 6,
    counting: 'centroid',
    cells: [],
    counted: 0,
    total_count: null,
    completeness: 'complete',
    max_count: 0,
    histogram: [],
    histogram_interval: 'month',
    footprints_advised: false,
    from_cache: false,
    extent: null,
    area: null,
    ignored_filters: [],
    ...overrides,
  };
}

describe('showFootprints', () => {
  it('is false without a result', () => {
    expect(showFootprints(null, 10)).toBe(false);
  });

  it('is false below the zoom brake even when the backend advises it', () => {
    expect(showFootprints(response({ footprints_advised: true }), FOOTPRINT_MIN_ZOOM - 1)).toBe(false);
  });

  it('is true once both the backend advice and the zoom brake agree', () => {
    expect(showFootprints(response({ footprints_advised: true }), FOOTPRINT_MIN_ZOOM)).toBe(true);
  });

  // adr/0007's sample case (M2-09b): a source with no checked total leaves
  // `footprints_advised=false` however few cells are counted — the
  // "Ersatzregel" of m2-format-und-viewer.md's M2-07c is already satisfied by
  // trusting that field rather than re-deriving it from `total_count` here.
  it('stays false for a declared sample with no checked total, whatever the zoom', () => {
    const sample = response({ completeness: 'sample', total_count: null, footprints_advised: false });
    expect(showFootprints(sample, 20)).toBe(false);
  });
});

// M3-19: without an AOI the world overview always asks for z6, whatever the
// map's own zoom is (adr/0010 Option B). With an AOI it still follows the
// map's zoom, as before.
// M3-19 (Otto, 23.09.2026): without an AOI, the level follows the map zoom
// and the viewport size so roughly TARGET_CELL_COUNT cells cover the screen.
// Expected values from plans/m3-19-weltueberblick-ausschnitt.md §1 (1920×1080:
// L ≈ Z + 4; 2560×1440: L ≈ Z + 3.6).
describe('levelForViewport', () => {
  it('is roughly zoom + 4 on a 1920×1080 viewport', () => {
    expect(levelForViewport(1.6, 1920, 1080)).toBe(6);
    expect(levelForViewport(3, 1920, 1080)).toBe(7);
    expect(levelForViewport(3.5, 1920, 1080)).toBe(7);
  });

  it('needs a slightly finer step on a smaller (2560×1440) viewport', () => {
    expect(levelForViewport(1.6, 2560, 1440)).toBe(5);
  });

  it('never falls below MIN_VIEWPORT_LEVEL, however far zoomed out', () => {
    expect(levelForViewport(0, 1920, 1080)).toBe(MIN_VIEWPORT_LEVEL);
    expect(levelForViewport(-5, 1920, 1080)).toBe(MIN_VIEWPORT_LEVEL);
  });

  it('is capped at the grid maximum (29), however far zoomed in', () => {
    expect(levelForViewport(40, 1920, 1080)).toBe(29);
  });

  it('falls back to the floor rather than NaN/Infinity on a bad viewport size', () => {
    expect(levelForViewport(8, 0, 0)).toBe(MIN_VIEWPORT_LEVEL);
    expect(levelForViewport(8, -100, 1080)).toBe(MIN_VIEWPORT_LEVEL);
    expect(levelForViewport(Number.NaN, 1920, 1080)).toBe(MIN_VIEWPORT_LEVEL);
  });
});

describe('roundBboxToGrid', () => {
  it('rounds outward to the block grid, not to the nearest cell', () => {
    expect(roundBboxToGrid([1, 1, 5, 5], 2)).toEqual([0, 0, 90, 66.51326044311186]);
  });

  it('gives two nearby viewports the same rounded block', () => {
    const a = roundBboxToGrid([10, 10, 60, 60], 1);
    const b = roundBboxToGrid([15, 15, 55, 55], 1);
    expect(a).toEqual(b);
    expect(a[0]).toBe(0);
    expect(a[1]).toBe(0);
    expect(a[2]).toBe(180);
    expect(a[3]).toBeCloseTo(85.0511287798, 9);
  });

  it('gives a viewport in a different block a different rounded bbox', () => {
    const a = roundBboxToGrid([10, 10, 60, 60], 1);
    const b = roundBboxToGrid([-5, 10, 60, 60], 1);
    expect(a).not.toEqual(b);
  });
});

describe('bandViewportBbox', () => {
  it('leaves an ordinary viewport unchanged', () => {
    expect(bandViewportBbox([5, 45, 15, 55])).toEqual([5, 45, 15, 55]);
  });

  it('replaces a viewport crossing ±180° with the full-width band', () => {
    expect(bandViewportBbox([-200, 10, -170, 20])).toEqual([-180, 10, 180, 20]);
    expect(bandViewportBbox([170, 10, 210, 20])).toEqual([-180, 10, 180, 20]);
  });
});

describe('bboxContains', () => {
  it('is true when the inner bbox lies within the outer one', () => {
    expect(bboxContains([0, 0, 180, 85], [10, 10, 60, 60])).toBe(true);
  });

  it('is true for an identical bbox', () => {
    expect(bboxContains([0, 0, 180, 85], [0, 0, 180, 85])).toBe(true);
  });

  it('is false once the inner bbox reaches past any one edge', () => {
    expect(bboxContains([0, 0, 180, 85], [-1, 10, 60, 60])).toBe(false);
    expect(bboxContains([0, 0, 180, 85], [10, 10, 181, 60])).toBe(false);
    expect(bboxContains([0, 0, 180, 85], [10, -1, 60, 60])).toBe(false);
    expect(bboxContains([0, 0, 180, 85], [10, 10, 60, 86])).toBe(false);
  });
});

describe('completenessNote', () => {
  it('adds nothing when the map is complete', () => {
    expect(completenessNote(response({ completeness: 'complete' }))).toBeNull();
  });

  it('names both counts when a truncated answer knows its total', () => {
    const note = completenessNote(
      response({ completeness: 'truncated', counted: 480, total_count: 512 }),
    );
    expect(note).toBe('showing 480 of 512 scenes');
  });

  it('falls back to a bare label when a truncated answer has no total', () => {
    expect(completenessNote(response({ completeness: 'truncated', total_count: null }))).toBe('truncated');
  });

  it('names both counts for a sample that knows its total', () => {
    const note = completenessNote(response({ completeness: 'sample', counted: 40, total_count: 4000 }));
    expect(note).toBe('sample: 40 of 4000 scenes');
  });

  it('is a bare "sample" for a sample with no checked total', () => {
    expect(completenessNote(response({ completeness: 'sample', total_count: null }))).toBe('sample');
  });
});
