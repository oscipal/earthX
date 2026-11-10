// M3-09 §10 (Otto): in the "Crop & merge to AOI" view, the yellow selection
// outline represents each *group* (Überflug) as one object — a single ring
// per group, AOI ∩ union of that group's own scene footprints — instead of
// one ring per scene. Everything here is pure geometry, run in the browser;
// the AOI never leaves it, same as the tile clip itself (`aoiClip.ts`).
//
// Uses `polyclip-ts` directly rather than the `@turf/union`/`@turf/intersect`
// wrapper around it (measured ~5 kB gzip lighter; Otto, 24.09.2026): it takes
// and returns exactly the ring-array shape GeoJSON's own
// `Polygon`/`MultiPolygon.coordinates` already use, so there is barely an
// adapter to write.

import { intersection, union } from 'polyclip-ts';
import type { Geom } from 'polyclip-ts';

import { footprintOf, polygonBbox } from './geoUtils';
import type { StacItem, TimeStepGroup } from './types';

// polyclip-ts's `Geom` is a plain-array ring/polygon/multi-polygon nest —
// structurally identical to GeoJSON's own `Polygon`/`MultiPolygon.coordinates`
// (only its `Ring` element type is a `[number, number]` tuple rather than a
// plain `number[]`, which TypeScript won't unify on its own); the library
// itself tells a lone polygon from a multi-polygon apart by nesting depth,
// not by anything the type carries, so a cast at this one boundary is exact,
// not a widening.
function toGeom(geometry: GeoJSON.Geometry): Geom | null {
  if (geometry.type === 'Polygon') return geometry.coordinates as unknown as Geom;
  if (geometry.type === 'MultiPolygon') return geometry.coordinates as unknown as Geom;
  return null;
}

function fromResult(result: ReturnType<typeof union>): GeoJSON.Polygon | GeoJSON.MultiPolygon | null {
  const multi = result as unknown as number[][][][];
  if (multi.length === 0) return null;
  return multi.length === 1 ? { type: 'Polygon', coordinates: multi[0] } : { type: 'MultiPolygon', coordinates: multi };
}

// None of these clipping libraries understand spherical geometry — they all
// compute in lon/lat as if it were flat x/y. A footprint or an AOI that
// really spans the antimeridian (rare MGRS zones near it) would silently
// produce a wildly wrong shape (measured: a ring from lon 179 to -179 comes
// back stretched the wrong way around, 358° wide instead of 2°) rather than
// an error to catch. The cheap defence is the same kind of bbox check
// `aoiClip.ts` already uses elsewhere in
// this codebase: if the combined longitude span of a group's footprints and
// the AOI exceeds half the globe, treat it as at risk and skip the merge for
// *that* group, rather than trust geometry that could be silently wrong
// (Prinzip 9 — never show something we can't vouch for).
const ANTIMERIDIAN_RISK_SPAN_DEG = 180;

function combinedLonSpan(geometries: readonly GeoJSON.Geometry[]): number {
  let minLon = Infinity;
  let maxLon = -Infinity;
  for (const geometry of geometries) {
    const bbox = polygonBbox(geometry);
    if (!bbox) continue;
    minLon = Math.min(minLon, bbox[0]);
    maxLon = Math.max(maxLon, bbox[2]);
  }
  return Number.isFinite(minLon) ? maxLon - minLon : 0;
}

// The scenes of one pass do not share their edges exactly: two slices of a Sentinel-1 datatake meet with their footprints
// a few thousandths of a degree apart, now overlapping, now leaving a gap (measured on 9.11.2026: 282 of 689 pairs of
// slices fell apart into two rings, or a ring with a hole, when united). The union then draws both edges, a double line
// across the merged picture (Otto's browser check, 9.11.2026). Before the union the footprints of a group are snapped to
// each other: a corner near a corner of an earlier footprint takes its place, and an edge that passes near a corner of
// another footprint gets that corner, so the two share the same points along their common edge. 0.01° closes every
// seam of those pairs and of 232 more in the polar seas, where 0.008° was the least that did; it moves an outline by at
// most about a kilometre where scenes really meet, and nowhere else. A footprint smaller than ten times that (a tile of
// swissALTI3D, 1 km) snaps within a tenth of its shorter side (`SNAP_SHARE_OF_SIDE`). Generic: any dataset's group goes
// through it.
const SNAP_TOLERANCE_DEG = 0.01;

type Point = [number, number];

const squaredDistance = (a: Point, b: Point): number => (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2;

// Where `p` lies along the segment a→b (0 to 1, ends excluded) and how far from it, squared; `null` beyond the ends.
function alongSegment(p: Point, a: Point, b: Point): { t: number; distance: number } | null {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const length = dx * dx + dy * dy;
  if (length === 0) return null;
  const t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length;
  if (t <= 0 || t >= 1) return null;
  return { t, distance: squaredDistance(p, [a[0] + t * dx, a[1] + t * dy]) };
}

// The rings of a polygon or of every part of a multipolygon.
const ringsOf = (geom: Geom): Point[][] => (typeof geom[0]?.[0]?.[0] === 'number' ? (geom as Point[][]) : (geom as Point[][][]).flat());

function mapRings(geom: Geom, fn: (ring: Point[]) => Point[]): Geom {
  return typeof geom[0]?.[0]?.[0] === 'number'
    ? (geom as Point[][]).map(fn)
    : (geom as Point[][][]).map((polygon) => polygon.map(fn));
}

type Box = [number, number, number, number];

function boxOf(geom: Geom): Box {
  const box: Box = [Infinity, Infinity, -Infinity, -Infinity];
  for (const [x, y] of ringsOf(geom).flat()) {
    box[0] = Math.min(box[0], x);
    box[1] = Math.min(box[1], y);
    box[2] = Math.max(box[2], x);
    box[3] = Math.max(box[3], y);
  }
  return box;
}

const near = (a: Box, b: Box, tolerance: number): boolean =>
  a[0] - tolerance <= b[2] && b[0] - tolerance <= a[2] && a[1] - tolerance <= b[3] && b[1] - tolerance <= a[3];

// A ring this can snap: closed, with at least three corners. Anything else is left as it is, for the union to judge.
const closedRing = (ring: Point[]): boolean => ring.length >= 4 && squaredDistance(ring[0], ring[ring.length - 1]) === 0;

// The share of the shorter side of a footprint it may move by at most: a small tile (swissALTI3D, 1 km) snaps within its
// own size, never onto the next corner of its neighbour, and a narrow strip cannot have its two long edges pulled across.
const SNAP_SHARE_OF_SIDE = 0.1;

export function snapFootprints(footprints: readonly Geom[], tolerance = SNAP_TOLERANCE_DEG): Geom[] {
  const boxes = footprints.map(boxOf);
  // The tolerance of each footprint, and of a pair the smaller of the two: 0.01° for scenes of a pass, a tenth of the
  // shorter side for footprints that small.
  const own = boxes.map((box) => Math.min(tolerance, SNAP_SHARE_OF_SIDE * Math.min(box[2] - box[0], box[3] - box[1])));
  const limitOf = (i: number, j: number) => Math.min(own[i], own[j]) ** 2;
  // Only the footprints that come within the tolerance of each other are compared, so a group of many scenes costs what
  // their neighbours cost.
  const neighbours = (index: number, before: number) =>
    boxes.slice(0, before).flatMap((box, j) => (j !== index && near(box, boxes[index], tolerance) ? [j] : []));
  // Corners first, each footprint onto those before it, so that two near corners become one point and not two that swapped.
  // A corner that lies exactly on an earlier corner keeps it.
  const snapped: Geom[] = [];
  footprints.forEach((footprint, index) => {
    const earlier = neighbours(index, index).map((j) => ({ corners: ringsOf(snapped[j]).flat(), limit: limitOf(index, j) }));
    snapped.push(
      mapRings(footprint, (ring) =>
        !closedRing(ring)
          ? ring
          : ring.map((corner) => {
              let best = corner;
              let bestDistance = Infinity;
              for (const { corners, limit } of earlier) {
                for (const other of corners) {
                  const distance = squaredDistance(corner, other);
                  if (distance === 0) return corner;
                  if (distance <= limit && distance <= bestDistance) {
                    best = other;
                    bestDistance = distance;
                  }
                }
              }
              return best;
            }),
      ),
    );
  });
  // Then every edge takes the corners of the other footprints that lie near it, in their order along the edge.
  return snapped.map((footprint, index) => {
    const others = neighbours(index, snapped.length).flatMap((j) =>
      ringsOf(snapped[j]).flatMap((ring) => ring.slice(0, -1).map((corner) => ({ corner, limit: limitOf(index, j) }))),
    );
    if (others.length === 0) return footprint;
    return mapRings(footprint, (ring) => {
      if (!closedRing(ring)) return ring;
      const out: Point[] = [];
      for (let k = 0; k < ring.length - 1; k++) {
        const [a, b] = [ring[k], ring[k + 1]];
        // Two corners snapped onto one point leave it once; a corner that is no number stays, for the union to refuse.
        if (out.length === 0 || squaredDistance(a, out[out.length - 1]) !== 0) out.push(a);
        const [x0, x1] = [Math.min(a[0], b[0]) - tolerance, Math.max(a[0], b[0]) + tolerance];
        const [y0, y1] = [Math.min(a[1], b[1]) - tolerance, Math.max(a[1], b[1]) + tolerance];
        const inserted: { corner: Point; t: number }[] = [];
        for (const { corner, limit } of others) {
          if (corner[0] < x0 || corner[0] > x1 || corner[1] < y0 || corner[1] > y1) continue;
          if (squaredDistance(corner, a) <= limit || squaredDistance(corner, b) <= limit) continue;
          const at = alongSegment(corner, a, b);
          if (at && at.distance <= limit) inserted.push({ corner, t: at.t });
        }
        inserted.sort((x, y) => x.t - y.t);
        for (const { corner } of inserted) if (squaredDistance(corner, out[out.length - 1]) !== 0) out.push(corner);
      }
      out.push(out[0]);
      return out;
    });
  });
}

export interface GroupOutlineProperties {
  groupKey: string;
  // Set on a feature that could not be merged (an antimeridian risk, or the
  // union/intersection computation itself failed) — such a group falls back
  // to its individual scene footprints instead of one merged ring, so a
  // single group can contribute several `fallback: true` features.
  fallback: boolean;
}

type GroupOutlineFeature = GeoJSON.Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon, GroupOutlineProperties>;

function fallbackFeatures(items: readonly StacItem[], groupKey: string): GroupOutlineFeature[] {
  const features: GroupOutlineFeature[] = [];
  for (const item of items) {
    const footprint = footprintOf(item);
    if (footprint && (footprint.type === 'Polygon' || footprint.type === 'MultiPolygon')) {
      features.push({ type: 'Feature', properties: { groupKey, fallback: true }, geometry: footprint });
    }
  }
  return features;
}

// One feature per group whose visible items overlap the AOI at all — a
// group entirely outside the AOI contributes nothing, same as an outlined
// scene entirely outside it would draw nothing today.
export function groupOutlineFeatures(
  groups: readonly TimeStepGroup[],
  visibleIds: ReadonlySet<string>,
  aoi: GeoJSON.Geometry,
): GroupOutlineFeature[] {
  const aoiGeom = toGeom(aoi);
  const features: GroupOutlineFeature[] = [];

  for (const group of groups) {
    const visibleItems = group.items.filter((it) => visibleIds.has(it.id));
    if (visibleItems.length === 0) continue;
    const groupKey = group.key.join('\u0000');

    const footprints = visibleItems
      .map((it) => footprintOf(it))
      .filter((g): g is GeoJSON.Geometry => g !== null);
    if (footprints.length === 0) continue;

    if (!aoiGeom || combinedLonSpan([...footprints, aoi]) > ANTIMERIDIAN_RISK_SPAN_DEG) {
      features.push(...fallbackFeatures(visibleItems, groupKey));
      continue;
    }

    const footprintGeoms = footprints.map(toGeom).filter((g): g is Geom => g !== null);
    if (footprintGeoms.length === 0) {
      features.push(...fallbackFeatures(visibleItems, groupKey));
      continue;
    }

    try {
      const [first, ...rest] = snapFootprints(footprintGeoms);
      const unioned = union(first, ...rest);
      const clipped = intersection(unioned, aoiGeom);
      const geometry = fromResult(clipped);
      if (geometry) features.push({ type: 'Feature', properties: { groupKey, fallback: false }, geometry });
    } catch {
      features.push(...fallbackFeatures(visibleItems, groupKey));
    }
  }
  return features;
}
