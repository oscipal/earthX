// Resolves a place name to an AOI via the backend's `POST /geocode` (M3-07a/b).
// `searchPlaces` never throws — every failure comes back as `{ error }` for the
// caller (`ControlPanel.tsx`'s `PlaceSearchField`) to show as-is in the shared
// error line, the same convention as `aoiFile.ts::readAoiFile`.

import { geocodePlace, HttpError, type PlaceResult } from './api';
import { bboxToPolygon } from './geoUtils';

// The source Otto approved carrying on an AOI's own GeoJSON properties (F3,
// 26.09.2026): every AOI the place search hands out gets these, so a
// download's `aoi.geojson` can later say where the shape came from. Drawn and
// uploaded AOIs never get this key — only `placeAoi` below attaches it.
export const PLACE_SEARCH_PROVENANCE = {
  source: 'OpenStreetMap / Nominatim',
  attribution: '© OpenStreetMap contributors',
  license: 'ODbL-1.0',
} as const;

// A `GeoJSON.Geometry` that also carries `properties` — not a `Feature` (the
// AOI travels through `store.aoi`/`searchArea`/the download request as a bare
// geometry everywhere else, and turning it into a `Feature` there would touch
// every one of those call sites for a label the backend never reads out of
// its shape, only writes back verbatim into `aoi.geojson`).
export type AoiGeometryWithProvenance = GeoJSON.Geometry & {
  properties?: typeof PLACE_SEARCH_PROVENANCE;
};

export interface PlaceSearchResult {
  results?: PlaceResult[];
  attribution?: string;
  attributionUrl?: string;
  error?: string;
}

function isFiniteBbox(bbox: unknown): bbox is [number, number, number, number] {
  return Array.isArray(bbox) && bbox.length === 4 && bbox.every((n) => typeof n === 'number' && Number.isFinite(n));
}

function isUsableOutline(outline: unknown): outline is GeoJSON.Polygon | GeoJSON.MultiPolygon {
  if (!outline || typeof outline !== 'object') return false;
  const type = (outline as { type?: unknown }).type;
  return type === 'Polygon' || type === 'MultiPolygon';
}

// Defends only against an unexpected answer (a `bbox` that is not four finite
// numbers, an `outline` that is not a Polygon/MultiPolygon) — never a second
// validation of a geometry the route already checked (plan §3).
function sanitizeResult(hit: unknown): PlaceResult | null {
  if (!hit || typeof hit !== 'object') return null;
  const h = hit as Partial<PlaceResult> & Record<string, unknown>;
  if (typeof h.display_name !== 'string' || !h.display_name) return null;
  if (!isFiniteBbox(h.bbox)) return null;
  return {
    name: typeof h.name === 'string' && h.name ? h.name : h.display_name,
    display_name: h.display_name,
    kind: typeof h.kind === 'string' && h.kind ? h.kind : 'unknown',
    bbox: h.bbox,
    outline: isUsableOutline(h.outline) ? h.outline : null,
    outline_simplified: h.outline_simplified === true,
  };
}

// Never throws. Every failure — a rejected request, an answer that could not
// be read — comes back as `{ error }`, matching M3-06b's `readAoiFile`.
export async function searchPlaces(q: string): Promise<PlaceSearchResult> {
  let response;
  try {
    response = await geocodePlace(q);
  } catch (err) {
    if (err instanceof HttpError) {
      if (err.status === 422) {
        return {
          error: err.detail ? `Could not search for this place: ${err.detail}.` : 'Could not search for this place.',
        };
      }
      if (err.status === 503) {
        return {
          error: err.retryAfter
            ? 'Place search is busy. Please try again in a few seconds.'
            : 'Place search is not enabled on this server.',
        };
      }
      if (err.status === 502 || err.status === 504) {
        return { error: 'The place search service did not answer. Please try again.' };
      }
      return { error: `Place search failed (${err.status}). Please try again.` };
    }
    return { error: 'Could not reach the server for place search.' };
  }
  if (!Array.isArray(response.results)) {
    return { error: 'Place search returned an answer that could not be read.' };
  }
  const results = response.results.map(sanitizeResult).filter((r): r is PlaceResult => r !== null);
  return {
    results,
    attribution: typeof response.attribution === 'string' ? response.attribution : undefined,
    attributionUrl: typeof response.attribution_url === 'string' ? response.attribution_url : undefined,
  };
}

// F1 (Otto, 26.09.2026): the outline as the AOI whenever there is one, the
// bounding box otherwise — never a choice between the two. Every AOI this
// returns carries `PLACE_SEARCH_PROVENANCE` in its `properties` (F3).
export function placeAoi(result: PlaceResult): AoiGeometryWithProvenance {
  const geometry: GeoJSON.Geometry = result.outline ?? bboxToPolygon(result.bbox);
  return { ...geometry, properties: PLACE_SEARCH_PROVENANCE };
}
