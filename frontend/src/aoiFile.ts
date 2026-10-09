// Reads an uploaded AOI file via the backend's `POST /aoi/upload` (M3-06a/b),
// which checks and returns the geometry — GeoJSON, KML and zipped Shapefile all
// go through it. Replaces this file's former in-browser GeoJSON/KML parser
// (`prototyp-inventar.md` F3): that parser had no size, point-count or validity
// checks and took "first usable geometry wins" for a file with several — the
// route is stricter (docs/plans/m3-06a-aoi-upload-backend.md §§7–9) and is now
// the only place any of that logic lives.

import { HttpError, uploadAoi } from './api';

// = backend/earthx/access/aoi_upload.py::MAX_UPLOAD_BYTES. Kept in sync by hand
// (no config endpoint exists any more, `store.ts`'s `config` comment) — change
// both together. Checked here, before the request goes out, because a browser
// tends to report a response that lands before its own upload has finished
// sending as a network error rather than as the `413` it actually is (plan §6);
// the `413` branch below stays as the route's own, authoritative cap.
export const AOI_UPLOAD_MAX_BYTES = 1_048_576;

const USABLE_TYPES = new Set(['Point', 'Polygon', 'MultiPolygon']);

function isUsableGeometry(value: unknown): value is GeoJSON.Geometry {
  return !!value && typeof value === 'object' && USABLE_TYPES.has((value as { type?: unknown }).type as string);
}

// Ends a route-supplied detail with exactly one full stop, never two (plan §5).
function withFullStop(text: string): string {
  return text.endsWith('.') ? text : `${text}.`;
}

export interface AoiFileResult {
  geometry?: GeoJSON.Geometry;
  error?: string;
}

// Never throws — every failure comes back as `{ error }` for the caller
// (`ControlPanel.tsx`'s `AoiExtras`) to show as-is in the shared error line.
export async function readAoiFile(file: File): Promise<AoiFileResult> {
  if (file.size > AOI_UPLOAD_MAX_BYTES) {
    return { error: `"${file.name}" is too large for an AOI (max. 1 MB).` };
  }
  let geometry: GeoJSON.Geometry;
  try {
    geometry = await uploadAoi(file, file.name);
  } catch (err) {
    if (err instanceof HttpError) {
      if (err.status === 413) {
        return { error: `"${file.name}" is too large for an AOI (max. 1 MB).` };
      }
      if (err.status === 400) {
        return {
          error: err.detail
            ? `Could not use "${file.name}" as an AOI: ${withFullStop(err.detail)}`
            : `Could not use "${file.name}" as an AOI.`,
        };
      }
      return { error: `Uploading "${file.name}" failed (${err.status}). Please try again.` };
    }
    return { error: `Could not reach the server to read "${file.name}".` };
  }
  if (!isUsableGeometry(geometry)) {
    return { error: `The server returned no usable AOI for "${file.name}".` };
  }
  return { geometry };
}
