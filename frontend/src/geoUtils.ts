// Small GeoJSON helpers used by the map + store.

import type { Bbox } from './types';

export function bboxToPolygon(bbox: Bbox): GeoJSON.Polygon {
  const [minx, miny, maxx, maxy] = bbox;
  return {
    type: 'Polygon',
    coordinates: [
      [
        [minx, miny],
        [maxx, miny],
        [maxx, maxy],
        [minx, maxy],
        [minx, miny],
      ],
    ],
  };
}

// Union of several bounding boxes (nulls skipped). Returns null if none valid.
export function unionBbox(boxes: (Bbox | null | undefined)[]): Bbox | null {
  let minx = Infinity;
  let miny = Infinity;
  let maxx = -Infinity;
  let maxy = -Infinity;
  for (const b of boxes) {
    if (!b) continue;
    minx = Math.min(minx, b[0]);
    miny = Math.min(miny, b[1]);
    maxx = Math.max(maxx, b[2]);
    maxy = Math.max(maxy, b[3]);
  }
  return Number.isFinite(minx) ? [minx, miny, maxx, maxy] : null;
}

// A clicked point becomes a small square AOI polygon (matches the backend
// POINT_BUFFER_DEG behaviour, kept on the client so display == what we search).
export function bufferPointToPolygon(lon: number, lat: number, deg: number): GeoJSON.Polygon {
  return bboxToPolygon([lon - deg, lat - deg, lon + deg, lat + deg]);
}

export function polygonBbox(geom: GeoJSON.Geometry): Bbox | null {
  let minx = Infinity;
  let miny = Infinity;
  let maxx = -Infinity;
  let maxy = -Infinity;
  const visit = (coords: unknown): void => {
    if (typeof coords === 'number') return;
    if (Array.isArray(coords) && typeof coords[0] === 'number') {
      const [x, y] = coords as number[];
      minx = Math.min(minx, x);
      miny = Math.min(miny, y);
      maxx = Math.max(maxx, x);
      maxy = Math.max(maxy, y);
      return;
    }
    if (Array.isArray(coords)) coords.forEach(visit);
  };
  if ('coordinates' in geom) visit((geom as { coordinates: unknown }).coordinates);
  if (!Number.isFinite(minx)) return null;
  return [minx, miny, maxx, maxy];
}

// Corner order MapLibre image sources expect: top-left, top-right, bottom-right, bottom-left.
export function bboxToImageCoords(
  bbox: Bbox,
): [[number, number], [number, number], [number, number], [number, number]] {
  const [minx, miny, maxx, maxy] = bbox;
  return [
    [minx, maxy],
    [maxx, maxy],
    [maxx, miny],
    [minx, miny],
  ];
}

export type Coords4 = [[number, number], [number, number], [number, number], [number, number]];

// Corner-quad transforms for image sources whose pixels are stored in a
// different orientation than north-up. Quad order is [TL, TR, BR, BL].
export function mirrorX(c: Coords4): Coords4 {
  // left↔right (flip the range/east–west axis)
  return [c[1], c[0], c[3], c[2]];
}
export function mirrorY(c: Coords4): Coords4 {
  // top↔bottom (flip the azimuth/north–south axis)
  return [c[3], c[2], c[1], c[0]];
}

// Image-source corner quad for a scene's quicklook, from its true footprint.
// Shared by the mosaic and the layer renderer so a pinned quicklook lands
// exactly where it was shown.
export function quicklookCoords(
  geometry: GeoJSON.Geometry | null | undefined,
  bbox: Bbox | null | undefined,
): Coords4 | null {
  if (!bbox) return null;
  return footprintCorners(geometry, bbox) ?? bboxToImageCoords(bbox);
}

function exteriorRing(geom: GeoJSON.Geometry | null | undefined): number[][] | null {
  if (!geom) return null;
  if (geom.type === 'Polygon') return geom.coordinates[0] as number[][];
  if (geom.type === 'MultiPolygon') return geom.coordinates[0]?.[0] as number[][];
  return null;
}

// Order a frame's 4 footprint corners into image-source order [TL,TR,BR,BL]
// using a north-up heuristic, so a rectangular quicklook warps onto the true
// (possibly rotated) footprint quad and adjacent frames tile edge-to-edge.
export function footprintCorners(
  geom: GeoJSON.Geometry | null | undefined,
  bbox: Bbox | null | undefined,
): Coords4 | null {
  const ring = exteriorRing(geom);
  if (ring && ring.length >= 4) {
    let pts = ring.slice();
    const first = pts[0];
    const last = pts[pts.length - 1];
    if (first[0] === last[0] && first[1] === last[1]) pts = pts.slice(0, -1);
    if (pts.length === 4) {
      const byLat = [...pts].sort((p, q) => q[1] - p[1]); // north first
      const top = byLat.slice(0, 2).sort((p, q) => p[0] - q[0]); // west first
      const bot = byLat.slice(2, 4).sort((p, q) => p[0] - q[0]);
      const [tl, tr] = top;
      const [bl, br] = bot;
      return [
        [tl[0], tl[1]],
        [tr[0], tr[1]],
        [br[0], br[1]],
        [bl[0], bl[1]],
      ];
    }
  }
  return bbox ? bboxToImageCoords(bbox) : null;
}

// Ray-casting point-in-polygon (falls back to bbox containment).
export function pointInFootprint(
  lng: number,
  lat: number,
  geom: GeoJSON.Geometry | null | undefined,
  bbox: Bbox | null | undefined,
): boolean {
  const ring = exteriorRing(geom);
  if (ring && ring.length >= 4) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = ring[i][0];
      const yi = ring[i][1];
      const xj = ring[j][0];
      const yj = ring[j][1];
      const intersect =
        yi > lat !== yj > lat && lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi;
      if (intersect) inside = !inside;
    }
    return inside;
  }
  if (bbox) return lng >= bbox[0] && lng <= bbox[2] && lat >= bbox[1] && lat <= bbox[3];
  return false;
}

export function asFeatureCollection(geom: GeoJSON.Geometry | null): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: geom ? [{ type: 'Feature', geometry: geom, properties: {} }] : [],
  };
}
