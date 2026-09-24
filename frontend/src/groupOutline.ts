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
// `aoiClip.ts`/`coverage.ts::clampBboxLongitude` already use elsewhere in
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
      const unioned = union(footprintGeoms[0], ...footprintGeoms.slice(1));
      const clipped = intersection(unioned, aoiGeom);
      const geometry = fromResult(clipped);
      if (geometry) features.push({ type: 'Feature', properties: { groupKey, fallback: false }, geometry });
    } catch {
      features.push(...fallbackFeatures(visibleItems, groupKey));
    }
  }
  return features;
}
