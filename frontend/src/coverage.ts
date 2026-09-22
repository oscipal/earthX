// Pure logic for the coverage heatmap (M2-07c): the geotile arithmetic that
// turns a cell key into a box, the log-scale color ramp, and the two rules
// that decide what the legend says. No map/DOM access here — `mapLayers.ts`
// and the components call these and do the drawing.

import type { CoverageCell, CoverageCompleteness, CoverageResponse } from './api';
import type { Bbox } from './types';

export class InvalidCellKey extends Error {}

// The same bound as `catalog.coverage.MAX_GEOTILE_LEVEL`: geotile runs out
// here (below a metre a cell is past any imagery), and Earth Search happens
// to draw the same line (a precision outside 0..29 comes back as a `400`).
const MAX_GEOTILE_LEVEL = 29;

// Geotile `z/x/y` → WGS84 `[west, south, east, north]`. The same arithmetic
// as `backend/earthx/catalog/coverage.py::cell_bbox` (kept in lockstep by the
// worked examples in coverage.test.ts) — columns run east from the
// antimeridian, rows run south from the top of the Web-Mercator square.
export function cellBbox(key: string): Bbox {
  const parts = key.split('/');
  if (parts.length !== 3) throw new InvalidCellKey(`grid key "${key}" is not z/x/y`);
  const [z, x, y] = parts.map(Number);
  if (![z, x, y].every(Number.isInteger)) {
    throw new InvalidCellKey(`grid key "${key}" has a part that is not a number`);
  }
  if (z < 0 || z > MAX_GEOTILE_LEVEL) {
    throw new InvalidCellKey(`grid key "${key}" names a level outside 0..${MAX_GEOTILE_LEVEL}`);
  }
  const side = 2 ** z;
  if (x < 0 || x >= side || y < 0 || y >= side) {
    throw new InvalidCellKey(`grid key "${key}" lies outside the grid of its own level`);
  }
  const west = (x / side) * 360 - 180;
  const east = ((x + 1) / side) * 360 - 180;
  const north = mercatorLatitude(y / side);
  const south = mercatorLatitude((y + 1) / side);
  return [west, south, east, north];
}

function mercatorLatitude(fraction: number): number {
  return (Math.atan(Math.sinh(Math.PI * (1 - 2 * fraction))) * 180) / Math.PI;
}

function bboxPolygon([west, south, east, north]: Bbox): GeoJSON.Polygon {
  return {
    type: 'Polygon',
    coordinates: [
      [
        [west, south],
        [east, south],
        [east, north],
        [west, north],
        [west, south],
      ],
    ],
  };
}

// Cells as a GeoJSON `FeatureCollection` for the `fill` layer, `n` carried as
// the property the paint expression reads. A key the arithmetic above cannot
// parse is skipped rather than thrown — one bad cell must not blank the whole
// map (the source is our own backend, but a response is still outside input).
export function cellsToFeatureCollection(cells: CoverageCell[]): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  for (const cell of cells) {
    let bbox: Bbox;
    try {
      bbox = cellBbox(cell.k);
    } catch {
      continue;
    }
    features.push({ type: 'Feature', properties: { n: cell.n }, geometry: bboxPolygon(bbox) });
  }
  return { type: 'FeatureCollection', features };
}

// A MapLibre `fill-color` expression, log-scaled, its stops derived from this
// response's own maximum rather than a fixed density (adr/0004 §5: "die
// Stützstellen werden aus dem Maximum der Antwort abgeleitet", replacing the
// prototype's scale that was only ever calibrated to BIOMASS, F12). `n >= 1`
// always holds — a cell only exists because it counted something — so log10
// is always defined and the bottom stop is fixed at 0.
const PALETTE = ['#2c7bb6', '#00a6ca', '#a6d96a', '#fdae61', '#d7191c'];

export function coverageFillColorExpression(maxCount: number): unknown[] {
  const logTop = Math.log10(Math.max(1, maxCount));
  const stops: unknown[] = [];
  // MapLibre refuses an `interpolate` expression whose stops are not
  // *strictly* ascending (found by loading the layer in a real browser, not
  // by a type check: `addLayer` throws at runtime, silently, since its
  // `paint` type is untyped `any`). `maxCount <= 1` collapses every step to
  // the same `logTop * t == 0`, so each stop is nudged past the previous one
  // rather than left equal to it — the color at 0 is what every cell shows
  // either way, since `n === 1` for all of them in that case.
  let previous = -Infinity;
  PALETTE.forEach((color, i) => {
    const t = PALETTE.length === 1 ? 0 : i / (PALETTE.length - 1);
    const value = Math.max(logTop * t, previous + Number.EPSILON);
    stops.push(value, color);
    previous = value;
  });
  return ['interpolate', ['linear'], ['log10', ['get', 'n']], ...stops];
}

// A drawn/uploaded AOI can carry longitudes outside ±180: MapLibre pans
// across repeated world copies at low zoom, so a rectangle dragged over a
// wrapped copy ends up with corners like -200 or 210. The coverage route
// checks ±180 and refuses anything past it (`InvalidCoverageQuery` → `400`),
// which made the heatmap vanish rather than just clamp to the same area a
// non-wrapped view would show. A hard clamp, not an antimeridian split —
// the smallest fix for the reported bug, not a general AOI-longitude fix.
export function clampBboxLongitude([west, south, east, north]: Bbox): Bbox {
  return [Math.max(-180, Math.min(180, west)), south, Math.max(-180, Math.min(180, east)), north];
}

// The zoom brake of `plans/m2-05-coverage.md` §6.8: `footprints_advised`
// alone answers "is the checked total small enough", but a strict filter
// (e.g. a narrow date range) can keep a *world* view under 500 hits, and
// drawing five hundred tiny footprints across the whole globe reads as noise,
// not as scenes. This constant is chosen, not measured — "roughly a country
// is in view" — and kept in one place so a later measurement can move it.
export const FOOTPRINT_MIN_ZOOM = 4;

// The cap on how many footprints M2-07c will actually fetch and draw. Equal
// to the backend's own `FOOTPRINT_THRESHOLD` (`catalog/coverage.py`): once
// `footprints_advised` is true, `total_count` is already known to be below
// it, so this is a ceiling that is never expected to bite, only a guard
// against fetching an unbounded number of pages if it ever is.
export const FOOTPRINT_FETCH_LIMIT = 500;

export function showFootprints(result: CoverageResponse | null, zoom: number): boolean {
  return !!result && result.footprints_advised && zoom >= FOOTPRINT_MIN_ZOOM;
}

// The legend's completeness line (`plans/m2-05-coverage.md` §3.5 table).
// `null` means the legend needs no addition. English here, like the rest of
// the interface (CLAUDE.md: Code auf Englisch) — `adr/0004` §5.3 still asks
// for the German terms ("bleiben die Sprache ... der Oberfläche"), which is
// now stale against the app's own English UI and needs Otto's decision plus
// an ADR update, not a silent override in one component (see the PR note).
export function completenessNote(result: CoverageResponse): string | null {
  const { counted, total_count: total } = result;
  const table: Record<CoverageCompleteness, () => string | null> = {
    complete: () => null,
    truncated: () => (total === null ? 'truncated' : `showing ${counted} of ${total} scenes`),
    sample: () => (total === null ? 'sample' : `sample: ${counted} of ${total} scenes`),
  };
  return table[result.completeness]();
}
