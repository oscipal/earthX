// Client for the job API under `/processing` (M4-08b, M4-13a): the process
// description with the schema of an order, the estimate before a job, placing,
// following, dismissing a job and its results. Same-origin relative URLs like
// `api.ts`; the Vite dev server proxies `/processing` to the `api` process.
//
// Nothing here logs or stores an order: it carries the AOI (Q8).

import { jsonOrThrow } from './api';
import type { Bbox } from './types';

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';
const PREFIX = `${BASE}/processing`;

// A JSON Schema as the process description carries it; read field by field
// (`schemaForm.ts`, `processingOrder.ts`), never trusted as a whole.
export type JsonSchema = Record<string, unknown>;

export interface ProcessDescription {
  id: string;
  title?: string;
  inputs: { recipe: { schema: JsonSchema } } & Record<string, unknown>;
  outputs?: Record<string, unknown>;
}

export interface OrderInput {
  name: string;
  dataset: string;
  groups: string[][];
  assets: string[];
}

export interface OrderStep {
  op: string;
  op_version: number;
  params: Record<string, unknown>;
}

// The order (`RecipeRequest`, adr/0014 §4.1): what someone asks for, without
// any address. Without `aoi` a raster job covers the whole scenes it names
// (M4-12: `api` puts the union of their footprints into the recipe).
export interface Order {
  recipe_version: 1;
  inputs: OrderInput[];
  aoi?: GeoJSON.Polygon | GeoJSON.MultiPolygon;
  steps: OrderStep[];
  output: RasterOutput | CropOutput;
}

export interface RasterOutput {
  kind: 'raster';
  format: 'cog';
  dtype: string;
}

// An export (M4-11 §3.1): the crop of the download dialog, computed as a job.
export interface CropOutput {
  kind: 'crop';
  format: 'cog';
  resolution_factor: 1;
  extent: 'bbox(aoi ∩ footprints)';
  mask: 'file';
}

// Where a place-search AOI came from (M4-11 F4, M4-30): sent next to the order
// of an export or of a job with an area, never part of the recipe or its hash.
export interface AoiProvenance {
  source?: string;
  attribution?: string;
  license?: string;
}

export interface Estimate {
  size: number;
  duration: string;
  outputPixels: number;
  inputPixels: number;
  inputBytes: number;
  assets: number;
  units: number;
}

export interface EstimateDocument {
  estimate: Estimate;
  skippedItems: string[];
}

export type JobState = 'accepted' | 'running' | 'successful' | 'failed' | 'dismissed';

// The status document (OGC `statusInfo`), only the fields the panel reads.
export interface StatusInfo {
  jobID: string;
  status: JobState;
  message: string;
  progress: number;
  expires: string;
  created?: string;
  started?: string;
  finished?: string;
  skippedItems?: string[];
}

export interface ResultLink {
  href: string;
  type?: string;
  title?: string;
  // Of the link `result` (the raster): its columns, for the pixel size of a geographic CRS.
  width?: number;
  properties?: Record<string, unknown>;
}

export type ResultsDocument = Record<string, ResultLink>;

const JOB_STATES: readonly JobState[] = ['accepted', 'running', 'successful', 'failed', 'dismissed'];
export const TERMINAL_STATES: readonly JobState[] = ['successful', 'failed', 'dismissed'];

// `secrets.token_urlsafe(16)` (`jobs/submit.py`): 22 characters of the URL-safe
// alphabet. Anything else is not a job of this server and never goes into a URL.
const JOB_ID = /^[A-Za-z0-9_-]{22}$/;

export function isJobId(value: unknown): value is string {
  return typeof value === 'string' && JOB_ID.test(value);
}

// A status document as the server sends it, or `null` for anything else — an
// unknown state, a missing field, another job's id (K5: dropped, not shown).
export function parseStatusInfo(value: unknown, jobId?: string): StatusInfo | null {
  if (!value || typeof value !== 'object') return null;
  const v = value as Record<string, unknown>;
  if (!isJobId(v.jobID) || (jobId !== undefined && v.jobID !== jobId)) return null;
  if (!JOB_STATES.includes(v.status as JobState)) return null;
  if (typeof v.progress !== 'number' || !Number.isFinite(v.progress)) return null;
  if (typeof v.expires !== 'string' || Number.isNaN(Date.parse(v.expires))) return null;
  return {
    jobID: v.jobID,
    status: v.status as JobState,
    message: typeof v.message === 'string' ? v.message : '',
    progress: Math.min(100, Math.max(0, v.progress)),
    expires: v.expires,
    ...(typeof v.created === 'string' ? { created: v.created } : {}),
    ...(typeof v.started === 'string' ? { started: v.started } : {}),
    ...(typeof v.finished === 'string' ? { finished: v.finished } : {}),
    ...(Array.isArray(v.skippedItems) ? { skippedItems: v.skippedItems.filter((x) => typeof x === 'string') } : {}),
  };
}

// JSON with sorted keys and no whitespace: one order, one text. The panel
// compares orders by it (an estimate belongs to exactly one order, K4), and
// the preview's `params` must be built the same way to hit the tile cache
// (`plans/m4/m4-09-band-math.md` §6).
export function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value && typeof value === 'object') {
    const entries = Object.keys(value as Record<string, unknown>)
      .filter((key) => (value as Record<string, unknown>)[key] !== undefined)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson((value as Record<string, unknown>)[key])}`);
    return `{${entries.join(',')}}`;
  }
  return JSON.stringify(value);
}

function orderBody(order: Order, aoiProvenance?: AoiProvenance): string {
  return JSON.stringify({ inputs: aoiProvenance ? { recipe: order, aoiProvenance } : { recipe: order } });
}

const JSON_HEADERS = { 'Content-Type': 'application/json' };

export async function fetchProcess(datasetId: string, signal?: AbortSignal): Promise<ProcessDescription> {
  return jsonOrThrow<ProcessDescription>(
    await fetch(`${PREFIX}/processes/recipe?dataset=${encodeURIComponent(datasetId)}`, { signal }),
  );
}

// The unit of a target CRS (`GET /processing/crs/{code}`, M4-13c-3): what the
// resolution of `reproject` is measured in. `toBase` is the factor to metres for
// a linear unit and to degrees for an angular one.
export interface CrsUnit {
  name: string;
  kind: 'linear' | 'angular';
  toBase: number;
}

export interface CrsInfo {
  code: string;
  name: string;
  kind: 'projected' | 'geographic' | 'other';
  unit: CrsUnit;
}

// The answer of the route, or `null` for anything else (a proxy's page).
export function parseCrsInfo(value: unknown): CrsInfo | null {
  if (!value || typeof value !== 'object') return null;
  const { code, name, kind, unit } = value as Record<string, unknown>;
  if (typeof code !== 'string' || typeof name !== 'string') return null;
  if (kind !== 'projected' && kind !== 'geographic' && kind !== 'other') return null;
  if (!unit || typeof unit !== 'object') return null;
  const u = unit as Record<string, unknown>;
  if (typeof u.name !== 'string' || (u.kind !== 'linear' && u.kind !== 'angular') || typeof u.toBase !== 'number') {
    return null;
  }
  return { code, name, kind, unit: { name: u.name, kind: u.kind, toBase: u.toBase } };
}

// A `422` carries the reason in `detail`: not a code, unknown, or no unit.
export async function fetchCrs(code: string, signal?: AbortSignal): Promise<CrsInfo> {
  const body = await jsonOrThrow<unknown>(await fetch(`${PREFIX}/crs/${encodeURIComponent(code)}`, { signal }));
  const info = parseCrsInfo(body);
  if (!info) throw new Error('The answer about the CRS could not be read.');
  return info;
}

const ESTIMATE_NUMBERS = ['size', 'outputPixels', 'inputPixels', 'inputBytes', 'assets', 'units'] as const;

// An estimate as the route writes it, or `null` for anything else (a proxy's
// page, a body of another shape): the panel shows an error then, not numbers.
export function parseEstimate(value: unknown): EstimateDocument | null {
  if (!value || typeof value !== 'object') return null;
  const { estimate, skippedItems } = value as Record<string, unknown>;
  if (!estimate || typeof estimate !== 'object') return null;
  const e = estimate as Record<string, unknown>;
  if (typeof e.duration !== 'string') return null;
  if (!ESTIMATE_NUMBERS.every((key) => typeof e[key] === 'number' && Number.isFinite(e[key]))) return null;
  return {
    estimate: e as unknown as Estimate,
    skippedItems: Array.isArray(skippedItems) ? skippedItems.filter((x) => typeof x === 'string') : [],
  };
}

export async function estimateOrder(order: Order, signal?: AbortSignal): Promise<EstimateDocument> {
  const doc = parseEstimate(
    await jsonOrThrow<unknown>(
      await fetch(`${PREFIX}/processes/recipe/estimate`, {
        method: 'POST',
        headers: JSON_HEADERS,
        body: orderBody(order),
        signal,
      }),
    ),
  );
  if (!doc) throw new Error('the server answered with an estimate the panel cannot read');
  return doc;
}

export async function placeJob(order: Order, options: { aoiProvenance?: AoiProvenance } = {}): Promise<StatusInfo> {
  const status = parseStatusInfo(
    await jsonOrThrow<unknown>(
      await fetch(`${PREFIX}/processes/recipe/execution`, {
        method: 'POST',
        headers: { ...JSON_HEADERS, Prefer: 'respond-async' },
        body: orderBody(order, options.aoiProvenance),
      }),
    ),
  );
  if (!status) throw new Error('the server answered with a status the panel cannot read');
  return status;
}

function jobUrl(jobId: string): string {
  if (!isJobId(jobId)) throw new Error('not a job id');
  return `${PREFIX}/jobs/${jobId}`;
}

export async function fetchJob(jobId: string): Promise<StatusInfo> {
  const status = parseStatusInfo(await jsonOrThrow<unknown>(await fetch(jobUrl(jobId))), jobId);
  if (!status) throw new Error('the server answered with a status the panel cannot read');
  return status;
}

export async function dismissJob(jobId: string): Promise<void> {
  await jsonOrThrow<unknown>(await fetch(jobUrl(jobId), { method: 'DELETE' }));
}

export async function fetchResults(jobId: string): Promise<ResultsDocument> {
  return jsonOrThrow<ResultsDocument>(await fetch(`${jobUrl(jobId)}/results`));
}

// What `GET …/tilejson.json` says that the layer needs.
export interface ResultTileJson {
  bounds: Bbox;
  minZoom: number;
  maxZoom: number;
  // `float32`, `uint16` …; `null` if the tiler did not say.
  dataType: string | null;
}

const isNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);

export function parseTileJson(value: unknown): ResultTileJson | null {
  if (!value || typeof value !== 'object') return null;
  const { bounds, minzoom, maxzoom, data_type: dataType } = value as Record<string, unknown>;
  if (!Array.isArray(bounds) || bounds.length !== 4 || !bounds.every(isNumber)) return null;
  if (!isNumber(minzoom) || !isNumber(maxzoom) || minzoom > maxzoom) return null;
  return {
    bounds: bounds as Bbox,
    minZoom: minzoom,
    maxZoom: maxzoom,
    dataType: typeof dataType === 'string' ? dataType : null,
  };
}

// The TileJSON of a result (`GET /results/{result_id}/WebMercatorQuad/tilejson.json`,
// served by the tiler, M4-13c-5): where it lies and which levels it has. `410` once
// the result is gone, `404` if it never was.
export async function fetchResultTileJson(href: string, signal?: AbortSignal): Promise<ResultTileJson> {
  const tileJson = parseTileJson(await jsonOrThrow<unknown>(await fetch(`${BASE}${href}`, { signal })));
  if (!tileJson) throw new Error('the tiler answered with a TileJSON the map cannot read');
  return tileJson;
}

// The methods text of a finished job (`methods.txt`, M4-19a), as text to paste.
export async function fetchMethodsText(jobId: string, signal?: AbortSignal): Promise<string> {
  const response = await fetch(resultUrl(jobId, 'methods.txt'), { signal });
  if (!response.ok) throw new Error(`the methods text could not be read (${response.status})`);
  return response.text();
}

export function eventsUrl(jobId: string): string {
  return `${jobUrl(jobId)}/events`;
}

// A result file (`result.tif`, `mask.tif`, `recipe.json`, `export.zip`): the
// route answers with a `303` to a signed URL, which a plain link follows (K6);
// `result.zip` it serves itself (M4-11b-1).
export function resultUrl(jobId: string, name: string): string {
  return `${jobUrl(jobId)}/results/${encodeURIComponent(name)}`;
}
