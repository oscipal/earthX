// A finished job as a layer on the map (M4-13c-5, plan §3.4): the link the results
// document gives to the tiles of the result, the tile URL, how the result is drawn,
// when the map says "Overview", and when the layer is "Expired". Pure functions; the
// state lives in `processingStore.ts` and `store.ts`.

import { DEFAULT_RANGE, rescaleOf, type PreviewRange } from './processingPreview';
import { scaleOf, type BandStats, type ResultStats } from './render';
import type { AppliedRender, Bbox } from './types';

// The link of the output `tiles` (`api/processing_docs.py::TILES_HREF`): a path on
// this host, in the shape the tiler serves — nothing else is ever fetched or used
// for a layer. `secrets.token_urlsafe(16)`: 22 characters of the URL-safe alphabet.
const TILES_HREF = /^\/results\/[A-Za-z0-9_-]{22}\/WebMercatorQuad\/tilejson\.json$/;

// From a minute before `expires` the tiler answers `410` (`objectstore/results.py::MIN_REMAINING`).
export const MIN_REMAINING_MS = 60_000;

export function tilesHref(doc: Record<string, { href?: unknown }>): string | null {
  const href = doc.tiles?.href;
  return typeof href === 'string' && TILES_HREF.test(href) ? href : null;
}

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

// The tile URL of a result without any style: the TileJSON's address with its last
// two segments swapped for the tile route, 256-pixel tiles like every other source.
export function resultTileTemplate(href: string): string {
  if (!TILES_HREF.test(href)) throw new Error('not the tiles of a result');
  return `${BASE}${href.replace(/WebMercatorQuad\/tilejson\.json$/, 'tiles/WebMercatorQuad/{z}/{x}/{y}')}?tilesize=256`;
}

// --- how it is drawn --------------------------------------------------------

const FLOAT = /^float/;

const finite = (value: unknown): number | null => (typeof value === 'number' && Number.isFinite(value) ? value : null);

// The statistics in the `properties` of the `result` link; `null` for a result from before
// they were written, or for a document that does not carry them in this shape.
export function resultStats(properties: Record<string, unknown> | undefined): ResultStats | null {
  const bands = properties?.bands;
  if (!Array.isArray(bands) || bands.length === 0) return null;
  const read = bands.map((band): BandStats => {
    const stats = (band as { statistics?: Record<string, unknown> } | null)?.statistics;
    // `count` 0: the band has no valid pixel, and its statistics name no value.
    const usable = stats !== null && typeof stats === 'object' && (finite(stats.count) ?? 0) > 0;
    return {
      minimum: usable ? finite(stats.minimum) : null,
      maximum: usable ? finite(stats.maximum) : null,
      percentile2: usable ? finite(stats.percentile_2) : null,
      percentile98: usable ? finite(stats.percentile_98) : null,
    };
  });
  if (read.every((band) => band.minimum === null && band.maximum === null)) return null;
  return { bands: read, expression: properties?.['processing:expression'] != null };
}

const sameRange = (a: PreviewRange, b: PreviewRange) => a.vmin === b.vmin && a.vmax === b.vmax && a.colormap === b.colormap;

// The range the user set by hand in the panel, to be kept with the job started under it
// (Otto, 22.10.2026); `null` for the default, which is no choice of the user's.
export const handRange = (range: PreviewRange): PreviewRange | null => (sameRange(range, DEFAULT_RANGE) ? null : range);

function drawnWith(range: PreviewRange): AppliedRender {
  const rescale = rescaleOf(range);
  return {
    ...('rescale' in rescale ? { rescale: rescale.rescale } : {}),
    ...(range.colormap ? { colormapName: range.colormap } : {}),
  };
}

// How a result is drawn (M4-32b, plan §6.7). A floating-point result needs a range and a
// colormap to become a picture; an integer result is drawn as it is. For a float, in order:
//  1. an integer result is drawn as it is;
//  2. the range the user had set by hand when the job started holds for this result only (`own`);
//  3. an index (a Band math result whose values all lie in −1…1) is drawn at −1…1 in `rdylgn`,
//     so that jobs can be compared with one another;
//  4. otherwise the 2–98 % of the AOI from the statistics, in `viridis`;
//  5. a result without statistics is drawn with the range of the panel, as before M4-32.
export function resultRender(
  dataType: string | null,
  panel: PreviewRange,
  stats: ResultStats | null = null,
  own: PreviewRange | null = null,
): AppliedRender {
  if (dataType === null || !FLOAT.test(dataType)) return {};
  if (own) return drawnWith(own);
  const scale = scaleOf(stats);
  return scale ? { rescale: `${scale.low},${scale.high}`, colormapName: scale.colormap } : drawnWith(panel);
}

// --- the pixel size of the result -------------------------------------------

export const positive = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null;

// Metres per degree of longitude at the equator (WGS 84 sphere of `tileResolution`).
const METRES_PER_DEGREE = 111_319.49;

// The pixel size of the result in metres: the `gsd` of its properties, which the job
// writes for a projected CRS only; for a geographic one the width of the TileJSON's
// bounds over the number of columns, at the middle latitude.
export function resultGsd(stated: number | null, width: number | null, bounds: Bbox): number | null {
  if (stated !== null) return stated;
  if (width === null || width <= 0) return null;
  const [west, south, east, north] = bounds;
  const middle = (south + north) / 2;
  return positive(((east - west) / width) * METRES_PER_DEGREE * Math.cos((middle * Math.PI) / 180));
}

// Metres per pixel of a 256-pixel Web Mercator tile at `latitude` and level `zoom`.
function tileMetres(latitude: number, zoom: number): number {
  return (156543.03392 * Math.cos((latitude * Math.PI) / 180)) / 2 ** zoom;
}

// "Overview": the tile the map asks for at this zoom is coarser than the result
// (plan §3.3, F4 (1)). The level is the one MapLibre requests for 256-pixel tiles,
// held at the result's own finest level; the latitude is the one nearest the equator
// in view, where the tile is coarsest — so the badge stays as long as any part of the
// view is drawn coarser than the result.
export function isOverview(args: {
  gsd: number | null;
  mapZoom: number;
  viewport: Bbox | null;
  maxZoom: number;
}): boolean {
  const { gsd, mapZoom, viewport, maxZoom } = args;
  if (gsd === null) return false;
  const zoom = Math.min(Math.round(mapZoom + 1), maxZoom);
  let latitude = 0;
  if (viewport) {
    const [, south, , north] = viewport;
    latitude = south <= 0 && north >= 0 ? 0 : Math.min(Math.abs(south), Math.abs(north));
  }
  return tileMetres(Math.min(latitude, 89), zoom) > gsd;
}

// --- life -------------------------------------------------------------------

// The layer says "Expired" and loads no more tiles from a minute before `expires`.
export function isResultExpired(expires: string, now: number): boolean {
  const end = Date.parse(expires);
  return !Number.isFinite(end) || now >= end - MIN_REMAINING_MS;
}

// "Result · <operator>": the part of a job's title before the dataset ("Band math ·
// Sentinel-2 L2A · 3/25"). A job without a title is just "Result".
export function resultLayerName(title: string | null): string {
  const operators = title?.split(' · ')[0]?.trim();
  return operators ? `Result · ${operators}` : 'Result';
}
