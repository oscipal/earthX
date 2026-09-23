// Small GeoJSON helpers used by the map + store.

import proj4 from 'proj4';

import type { Bbox, StacAsset, StacItem } from './types';

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

export type Coords4 = [[number, number], [number, number], [number, number], [number, number]];

export function coordsBbox(coords: Coords4): Bbox {
  const xs = coords.map((c) => c[0]);
  const ys = coords.map((c) => c[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

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

// EPSG code → proj4 definition, restricted to the UTM zones a Sentinel-2
// `proj:code` names (EPSG:326xx northern hemisphere, EPSG:327xx southern).
// Any other code is unsupported here — callers treat that like a missing
// `proj:code` rather than guess at a definition.
function utmProj4Def(code: string): string | null {
  const match = /^EPSG:(\d{4,5})$/i.exec(code.trim());
  if (!match) return null;
  const epsg = Number(match[1]);
  const north = epsg >= 32601 && epsg <= 32660;
  const south = epsg >= 32701 && epsg <= 32760;
  if (!north && !south) return null;
  const zone = epsg - (north ? 32600 : 32700);
  return `+proj=utm +zone=${zone} +${north ? 'north' : 'south'} +datum=WGS84 +units=m +no_defs`;
}

// The item's own CRS, in either spelling STAC has for it — mirrors the
// tiler's `_proj_code` (backend/earthx/api/tiler.py): `proj:code` is the
// projection extension v2 field, `proj:epsg` (an int) the v1 one Earth
// Search still sends.
function projCode(properties: Record<string, unknown>): string | null {
  const code = properties['proj:code'];
  if (typeof code === 'string' && code) return code;
  const epsg = properties['proj:epsg'];
  return typeof epsg === 'number' && Number.isInteger(epsg) ? `EPSG:${epsg}` : null;
}

function isFiniteNumberArray(v: unknown, length: number): v is number[] {
  return Array.isArray(v) && v.length >= length && v.every((n) => typeof n === 'number' && Number.isFinite(n));
}

// An asset's pixel-grid extent, in its own projected CRS — the STAC
// projection extension's `proj:transform` (an affine `[a, b, c, d, e, f, …]`
// mapping pixel column/row to projected x/y) and `proj:shape` (`[rows,
// cols]`). Corner order [TL, TR, BR, BL].
function assetExtent(asset: StacAsset): Coords4 | null {
  const transform = asset['proj:transform'];
  const shape = asset['proj:shape'];
  if (!isFiniteNumberArray(transform, 6)) return null;
  if (!isFiniteNumberArray(shape, 2) || shape[0] <= 0 || shape[1] <= 0) return null;
  const [a, b, c, d, e, f] = transform;
  const [rows, cols] = shape;
  const at = (col: number, row: number): [number, number] => [a * col + b * row + c, d * col + e * row + f];
  return [at(0, 0), at(cols, 0), at(cols, rows), at(0, rows)];
}

// The georeferenced asset whose pixel grid stands in for the item's own
// `proj:bbox`: Earth Search's Sentinel-2 items carry no `proj:bbox` at all
// (STAC projection extension v1.1 leaves it optional and unset here), so the
// tile's true extent — nodata border included — has to come from an asset's
// `proj:transform`/`proj:shape` instead. `visual` first, the RGB asset the
// quicklook approximates and the dataset's own default-render asset;
// otherwise the first asset that carries both fields.
function georeferencedExtent(assets: Record<string, StacAsset>): Coords4 | null {
  const visual = assets.visual && assetExtent(assets.visual);
  if (visual) return visual;
  for (const asset of Object.values(assets)) {
    const extent = assetExtent(asset);
    if (extent) return extent;
  }
  return null;
}

// Image-source corner quad for a scene's quicklook, from the *tile's* extent,
// not the item's data geometry: Earth Search's thumbnail for Sentinel-2
// renders the whole MGRS tile including its nodata border, while a
// partial/edge scene's geometry only covers the actual data and is smaller
// and irregular. Anchoring the quicklook to the geometry then misplaces it.
// `null` (no quicklook) rather than a guess when the item's CRS or a
// georeferenced asset's extent is missing, or the CRS isn't a UTM zone we
// can convert.
export function quicklookCoords(item: Pick<StacItem, 'properties' | 'assets'> | null | undefined): Coords4 | null {
  if (!item) return null;
  const code = projCode(item.properties ?? {});
  if (!code) return null;
  const def = utmProj4Def(code);
  if (!def) return null;
  const extent = georeferencedExtent(item.assets ?? {});
  if (!extent) return null;
  const toWgs84 = ([x, y]: [number, number]): [number, number] => {
    const [lon, lat] = proj4(def, 'EPSG:4326', [x, y]);
    return [lon, lat];
  };
  return [toWgs84(extent[0]), toWgs84(extent[1]), toWgs84(extent[2]), toWgs84(extent[3])];
}

function exteriorRing(geom: GeoJSON.Geometry | null | undefined): number[][] | null {
  if (!geom) return null;
  if (geom.type === 'Polygon') return geom.coordinates[0] as number[][];
  if (geom.type === 'MultiPolygon') return geom.coordinates[0]?.[0] as number[][];
  return null;
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
