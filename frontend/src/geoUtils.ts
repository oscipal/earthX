// Small GeoJSON helpers used by the map + store.

import proj4 from 'proj4';

import type { Bbox, StacAsset, StacItem } from './types';

// A scene's own footprint, or its bbox as a rectangle when the item carries
// no `geometry` — the same fallback the mosaic selection highlight
// (`mapLayers.ts`) and the coverage footprints (M2-07c) both need, so it
// lives here once rather than twice.
export function footprintOf(item: Pick<StacItem, 'geometry' | 'bbox'>): GeoJSON.Geometry | null {
  if (item.geometry) return item.geometry;
  return item.bbox ? bboxToPolygon(item.bbox) : null;
}

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

function isEpsg4326(code: string): boolean {
  return code.trim().toUpperCase() === 'EPSG:4326';
}

// A quicklook placement conversion for the item's CRS, in whichever direction
// the caller needs — `null` for a CRS neither of the two forms below covers
// (M3-02 F-03: before this, only a UTM zone worked; a global raster in
// EPSG:4326, like the DEM, showed no quicklook at all). EPSG:4326 is the
// identity: an asset's `proj:transform` already maps pixels straight to
// lon/lat, no proj4 conversion needed.
function toWgs84Converter(code: string): ((xy: [number, number]) => [number, number]) | null {
  if (isEpsg4326(code)) return (xy) => xy;
  const def = utmProj4Def(code);
  return def ? (xy) => proj4(def, 'EPSG:4326', xy) as [number, number] : null;
}

function fromWgs84Converter(code: string): ((lonLat: [number, number]) => [number, number]) | null {
  if (isEpsg4326(code)) return (lonLat) => lonLat;
  const def = utmProj4Def(code);
  return def ? (lonLat) => proj4('EPSG:4326', def, lonLat) as [number, number] : null;
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
function georeferencedAsset(assets: Record<string, StacAsset>): StacAsset | null {
  if (assets.visual && assetExtent(assets.visual)) return assets.visual;
  return Object.values(assets).find((asset) => assetExtent(asset)) ?? null;
}

function georeferencedExtent(assets: Record<string, StacAsset>): Coords4 | null {
  const asset = georeferencedAsset(assets);
  return asset ? assetExtent(asset) : null;
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
  const toWgs84 = toWgs84Converter(code);
  if (!toWgs84) return null;
  const extent = georeferencedExtent(item.assets ?? {});
  if (!extent) return null;
  return [toWgs84(extent[0]), toWgs84(extent[1]), toWgs84(extent[2]), toWgs84(extent[3])];
}

// The inverse of a `proj:transform` affine (pixel col/row → projected x/y):
// given a projected (x, y), the pixel (col, row) it came from. `null` for a
// degenerate transform (zero determinant) — not a real pixel grid.
function invertAffine(transform: number[]): ((x: number, y: number) => [number, number]) | null {
  const [a, b, c, d, e, f] = transform;
  const det = a * e - b * d;
  if (!Number.isFinite(det) || det === 0) return null;
  return (x, y) => {
    const dx = x - c;
    const dy = y - f;
    return [(dx * e - b * dy) / det, (a * dy - d * dx) / det];
  };
}

// Every ring of an AOI polygon/multipolygon (exterior and holes), as pixel
// coordinates on the item's own georeferenced asset (M3-12, O5) — the inverse
// of the corner conversion `quicklookCoords` above does, so a canvas can clip
// a quicklook to the AOI the way `aoiClip.ts::ringsToTilePixels` clips a
// raster tile to it in that tile's own Web-Mercator pixel space. `null` for
// the same reasons `quicklookCoords` is: a CRS this cannot convert, or no
// georeferenced asset to place the ring on — the caller then shows the
// quicklook unclipped rather than blocking it on a geometry it cannot place.
export function quicklookAoiPixelRings(
  item: Pick<StacItem, 'properties' | 'assets'>,
  aoi: GeoJSON.Geometry,
): [number, number][][] | null {
  const code = projCode(item.properties ?? {});
  if (!code) return null;
  const fromWgs84 = fromWgs84Converter(code);
  if (!fromWgs84) return null;
  const asset = georeferencedAsset(item.assets ?? {});
  const transform = asset?.['proj:transform'];
  if (!asset || !isFiniteNumberArray(transform, 6)) return null;
  const invert = invertAffine(transform);
  if (!invert) return null;
  const toPixel = ([lon, lat]: number[]): [number, number] => {
    const [x, y] = fromWgs84([lon, lat]);
    return invert(x, y);
  };
  return exteriorAndHoles(aoi).map((ring) => ring.map(toPixel));
}

// Mirrors `aoiClip.ts`'s private helper of the same name — kept separate
// rather than shared, since the two modules solve the same GeoJSON-shape
// problem for two different pixel grids and neither should depend on the
// other's internals for it.
function exteriorAndHoles(geom: GeoJSON.Geometry): number[][][] {
  if (geom.type === 'Polygon') return geom.coordinates as number[][][];
  if (geom.type === 'MultiPolygon') return (geom.coordinates as number[][][][]).flat();
  return [];
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

// M3-08 F1a: kept in lockstep with the backend's own cap
// (`MAX_INTERSECTS_POINTS`, `backend/earthx/adapters/federated_search.py`) — a
// polygon over this many positions is rejected there, so `searchArea` falls back
// to the bounding box on this side rather than let the search fail.
export const MAX_INTERSECTS_POINTS = 1000;

// Counts the positions in a geometry, the same way the backend's own
// `_check_positions` does: walks the (possibly nested) coordinates array down to
// its leaves, one leaf per position.
function countPositions(coords: unknown): number {
  if (Array.isArray(coords) && typeof coords[0] === 'number') return 1;
  if (!Array.isArray(coords)) return 0;
  return coords.reduce((total: number, item) => total + countPositions(item), 0);
}

// A rectangle drawn with the "Rectangle" tool: a single ring of exactly five
// points (closed) whose corners take only two distinct x- and two distinct y-
// values. Sent as `bbox` rather than `intersects` — the same question, asked the
// cheaper way and without spending any of the point budget above.
function isAxisAlignedRectangle(geom: GeoJSON.Geometry): boolean {
  if (geom.type !== 'Polygon' || geom.coordinates.length !== 1) return false;
  const ring = geom.coordinates[0];
  if (ring.length !== 5) return false;
  const xs = new Set(ring.map(([x]) => x));
  const ys = new Set(ring.map(([, y]) => y));
  return xs.size === 2 && ys.size === 2;
}

export interface SearchArea {
  bbox?: Bbox;
  intersects?: GeoJSON.Geometry;
  // Set only when a polygon went over MAX_INTERSECTS_POINTS and was searched by
  // its bounding box instead (M3-08 F2a) — the caller folds this into its own
  // search notice; unset otherwise, including for a plain rectangle.
  truncatedNotice?: string;
}

// M3-08 F2a/F5a: what one search request asks for, given the drawn/uploaded AOI
// and, separately, the point it was drawn or uploaded from (`store.ts` tracks the
// two apart — the AOI square stays what the map shows and the download crops,
// the point is only ever used here). A rectangle AOI still asks by `bbox`; a
// point or any other polygon asks by `intersects`, except a polygon so large it
// would be rejected upstream, which falls back to `bbox` with a notice instead.
export function searchArea(aoi: GeoJSON.Geometry | null, point: GeoJSON.Point | null): SearchArea {
  if (point) return { intersects: point };
  if (!aoi) return {};
  const bbox = polygonBbox(aoi);
  if (!bbox) return {};
  if (isAxisAlignedRectangle(aoi)) return { bbox };
  if (countPositions((aoi as { coordinates?: unknown }).coordinates) > MAX_INTERSECTS_POINTS) {
    return {
      bbox,
      truncatedNotice: `Area has more than ${MAX_INTERSECTS_POINTS} points; searched its bounding box instead.`,
    };
  }
  return { intersects: aoi };
}
