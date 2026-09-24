// M3-09: clip full-resolution raster tiles to the AOI entirely in the
// browser, so the AOI geometry itself never crosses the network — not in a
// tile URL, not in a request body, and therefore never in a server log
// either (CLAUDE.md "keine exakten AOIs in Logs"; `adr/0006` "kein Mosaik im
// Kachel-Pfad", `adr/0001` "zustandslos": nothing here is cached anywhere,
// on either side).
//
// MapLibre has no built-in way to mask a raster layer to a polygon
// (https://github.com/maplibre/maplibre-gl-js/discussions/3237); the
// maintainers' own suggestion there is to do the clipping in a custom tile
// protocol instead of the map core, which is what this module registers.
// The protocol's load function may return a decoded `ImageBitmap` directly
// (`doImageRequest` in maplibre-gl accepts one without re-encoding), so a
// clipped tile never round-trips through a re-encoded PNG.

// Only *types* come from maplibre-gl here (erased at build time, no runtime
// import): this module must stay loadable without the real library, which
// crashes outside a browser canvas/WebGL context (jsdom included) — several
// widely-imported modules (`store.ts`, `mapLayers.ts`) pull this module in
// just for `clipTileUrl`, so a real `import … from 'maplibre-gl'` here would
// drag maplibre-gl into every test that touches the store. The actual
// `addProtocol(...)` registration call lives in `MapView.tsx` instead, which
// already imports the real library and is mocked out in exactly those tests.
import type { AddProtocolAction } from 'maplibre-gl';

import { polygonBbox } from './geoUtils';
import type { Bbox } from './types';

const PROTOCOL = 'earthx-clip';
const PREFIX = `${PROTOCOL}://`;
const TILE_PX = 256;
// WGS84 semi-major axis — the sphere radius the WebMercatorQuad tile matrix
// (and every XYZ raster tile scheme) is built on.
const EARTH_RADIUS_M = 6378137;

// --- AOI registry ---------------------------------------------------------
//
// One key per AOI *object identity*, not per tile or per pinned overlay: the
// same (still-referenced) AOI object always maps to the same key, so pinning
// several overlays from one "Crop to AOI" view shares a single registry
// entry. A freshly drawn AOI is a new object (`store.ts::setAoi`), so it gets
// its own key without needing to evict the old one. Nothing here is looked
// up by geometry content — only by this identity — so content equality is
// never checked, and this is browser-tab memory, not a server-side cache.
const keysByAoi = new WeakMap<GeoJSON.Geometry, string>();
const aoiByKey = new Map<string, { geometry: GeoJSON.Geometry; bbox: Bbox }>();
let nextKey = 0;

function keyFor(aoi: GeoJSON.Geometry): string {
  const existing = keysByAoi.get(aoi);
  if (existing) return existing;
  const key = `c${nextKey++}`;
  keysByAoi.set(aoi, key);
  // A geometry `polygonBbox` cannot read (empty coordinates) never gets
  // registered — `clipTileUrl` below then leaves the tile unclipped rather
  // than clip against nothing.
  const bbox = polygonBbox(aoi);
  if (bbox) aoiByKey.set(key, { geometry: aoi, bbox });
  return key;
}

// --- URL wrapping ----------------------------------------------------------
//
// `template` still carries literal `{z}/{x}/{y}` placeholders (`api.ts`'s
// `buildTileTemplate`); MapLibre substitutes *every* occurrence of them in
// the final URL with one global replace (`TileID.url`, maplibre-gl-js), so
// the extra copy this wrapper adds right after the key is substituted the
// same way, giving `parseClipUrl` an unambiguous, un-encoded way to read the
// tile coordinate back out — no percent-encoding of the template needed
// (which would also hide its own `{z}/{x}/{y}` from that same substitution).

// Wraps a tile URL template so MapLibre routes it through the AOI-clip
// protocol instead of fetching it directly. `aoi === null` (or a geometry
// with no readable bbox) returns the template unchanged — the whole-scene
// "View full selection" case never goes through the protocol at all, and
// nothing about the requested tile changes.
export function clipTileUrl(template: string, aoi: GeoJSON.Geometry | null): string {
  if (!aoi) return template;
  const key = keyFor(aoi);
  if (!aoiByKey.has(key)) return template;
  return `${PREFIX}${key}/{z}/{x}/{y}/${template}`;
}

interface ParsedClipUrl {
  key: string;
  z: number;
  x: number;
  y: number;
  inner: string;
}

export function parseClipUrl(url: string): ParsedClipUrl | null {
  if (!url.startsWith(PREFIX)) return null;
  const parts = url.slice(PREFIX.length).split('/');
  if (parts.length < 5) return null;
  const [key, zRaw, xRaw, yRaw, ...innerParts] = parts;
  const z = Number(zRaw);
  const x = Number(xRaw);
  const y = Number(yRaw);
  if (!Number.isInteger(z) || !Number.isInteger(x) || !Number.isInteger(y)) return null;
  const inner = innerParts.join('/');
  return inner ? { key, z, x, y, inner } : null;
}

// --- projection --------------------------------------------------------
//
// lon/lat → the same spherical-mercator meters the tile matrix is built on
// (EPSG:3857-equivalent; matches what every XYZ raster tile scheme,
// including WebMercatorQuad, renders into).
export function lonLatToMerc([lon, lat]: [number, number]): [number, number] {
  const x = (lon * Math.PI * EARTH_RADIUS_M) / 180;
  const clampedLat = Math.max(Math.min(lat, 85.0511), -85.0511);
  const y = EARTH_RADIUS_M * Math.log(Math.tan(Math.PI / 4 + (clampedLat * Math.PI) / 360));
  return [x, y];
}

// A tile's own bounds from the standard slippy-map lon/lat corner formulas —
// used both as the cheap reject test (in lon/lat, `bboxesOverlap` below) and,
// reprojected through `lonLatToMerc`, as the frame the AOI is placed into for
// masking (`ringsToTilePixels`). One projection used consistently for both
// the tile and the AOI, rather than a second, independently derived
// meters-per-tile formula that could disagree with it at the edges.
export function tileLonLatBounds(z: number, x: number, y: number): Bbox {
  const n = 2 ** z;
  const lonAt = (tx: number): number => (tx / n) * 360 - 180;
  const latAt = (ty: number): number => (Math.atan(Math.sinh(Math.PI * (1 - (2 * ty) / n))) * 180) / Math.PI;
  return [lonAt(x), latAt(y + 1), lonAt(x + 1), latAt(y)];
}

export function tileMercBounds(z: number, x: number, y: number): Bbox {
  const [lonMin, latMin, lonMax, latMax] = tileLonLatBounds(z, x, y);
  const [minX, minY] = lonLatToMerc([lonMin, latMin]);
  const [maxX, maxY] = lonLatToMerc([lonMax, latMax]);
  return [minX, minY, maxX, maxY];
}

export function bboxesOverlap(a: Bbox, b: Bbox): boolean {
  return a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];
}

function exteriorAndHoles(geom: GeoJSON.Geometry): number[][][] {
  if (geom.type === 'Polygon') return geom.coordinates as number[][][];
  if (geom.type === 'MultiPolygon') return (geom.coordinates as number[][][][]).flat();
  return [];
}

// Every ring (exterior and holes, of every polygon of a MultiPolygon) of the
// AOI, each projected into this tile's own 256x256 pixel space. One shared
// `evenodd`-filled path from all of them masks holes and disjoint polygons
// correctly regardless of a ring's winding direction (the GeoJSON right-hand
// rule is meant to hold, but real-world data does not always comply, and
// `evenodd` never has to care).
export function ringsToTilePixels(geom: GeoJSON.Geometry, z: number, x: number, y: number): [number, number][][] {
  const [minX, minY, maxX, maxY] = tileMercBounds(z, x, y);
  const w = maxX - minX;
  const h = maxY - minY;
  const project = ([lon, lat]: number[]): [number, number] => {
    const [mx, my] = lonLatToMerc([lon, lat]);
    return [((mx - minX) / w) * TILE_PX, ((maxY - my) / h) * TILE_PX];
  };
  return exteriorAndHoles(geom).map((ring) => ring.map(project));
}

// --- the protocol itself ---------------------------------------------------

// A fully transparent 1x1 bitmap — the same "outside the footprint" answer
// F10's server-side tiles already give (`prototyp-inventar.md` F10), reused
// here for a tile the AOI's own bbox never reaches: no fetch is made at all.
async function transparentPixel(): Promise<ImageBitmap> {
  const canvas = new OffscreenCanvas(1, 1);
  canvas.getContext('2d'); // leaves the pixel at its default, transparent black
  return canvas.transferToImageBitmap();
}

async function maskedBitmap(bitmap: ImageBitmap, rings: [number, number][][]): Promise<ImageBitmap> {
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const ctx = canvas.getContext('2d');
  if (!ctx) return bitmap;
  const path = new Path2D();
  for (const ring of rings) {
    if (ring.length < 3) continue;
    path.moveTo(ring[0][0], ring[0][1]);
    for (const [px, py] of ring.slice(1)) path.lineTo(px, py);
    path.closePath();
  }
  ctx.save();
  ctx.clip(path, 'evenodd');
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  ctx.restore();
  return canvas.transferToImageBitmap();
}

// The protocol name to register `aoiClipProtocol` under
// (`maplibregl.addProtocol(AOI_CLIP_PROTOCOL, aoiClipProtocol)`, in
// `MapView.tsx` — the one place in the app allowed to import the real
// maplibre-gl runtime at the top level).
export const AOI_CLIP_PROTOCOL = PROTOCOL;

// The `earthx-clip` protocol's load function. Registering it is `MapView`'s
// job (idempotent either way: `addProtocol` simply overwrites any previous
// registration under the same name).
export const aoiClipProtocol: AddProtocolAction = async (params, abortController) => {
  const parsed = parseClipUrl(params.url);
  if (!parsed) throw new Error(`earthx-clip: malformed tile URL "${params.url}"`);
  const { key, z, x, y, inner } = parsed;
  const entry = aoiByKey.get(key);
  if (!entry) throw new Error('earthx-clip: the AOI for this view is no longer available');
  if (!bboxesOverlap(entry.bbox, tileLonLatBounds(z, x, y))) {
    return { data: await transparentPixel() };
  }
  const res = await fetch(inner, { signal: abortController.signal });
  if (!res.ok) throw new Error(`earthx-clip: ${res.status} ${res.statusText} fetching the tile`);
  const bitmap = await createImageBitmap(await res.blob());
  const rings = ringsToTilePixels(entry.geometry, z, x, y);
  return { data: await maskedBitmap(bitmap, rings) };
};
