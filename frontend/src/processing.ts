// Client for the job API under `/processing` (M4-08b, M4-13a): the process
// description with the schema of an order, the estimate before a job, placing,
// following, dismissing a job and its results. Same-origin relative URLs like
// `api.ts`; the Vite dev server proxies `/processing` to the `api` process.
//
// Nothing here logs or stores an order: it carries the AOI (Q8).

import { jsonOrThrow } from './api';

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
// any address.
export interface Order {
  recipe_version: 1;
  inputs: OrderInput[];
  aoi: GeoJSON.Polygon | GeoJSON.MultiPolygon;
  steps: OrderStep[];
  output: { kind: 'raster'; format: 'cog'; dtype: string };
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
// (`plans/m4-09-band-math.md` §6).
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

function orderBody(order: Order): string {
  return JSON.stringify({ inputs: { recipe: order } });
}

const JSON_HEADERS = { 'Content-Type': 'application/json' };

export async function fetchProcess(datasetId: string, signal?: AbortSignal): Promise<ProcessDescription> {
  return jsonOrThrow<ProcessDescription>(
    await fetch(`${PREFIX}/processes/recipe?dataset=${encodeURIComponent(datasetId)}`, { signal }),
  );
}

export async function estimateOrder(order: Order, signal?: AbortSignal): Promise<EstimateDocument> {
  const doc = await jsonOrThrow<EstimateDocument>(
    await fetch(`${PREFIX}/processes/recipe/estimate`, {
      method: 'POST',
      headers: JSON_HEADERS,
      body: orderBody(order),
      signal,
    }),
  );
  return { estimate: doc.estimate, skippedItems: doc.skippedItems ?? [] };
}

export async function placeJob(order: Order): Promise<StatusInfo> {
  const status = parseStatusInfo(
    await jsonOrThrow<unknown>(
      await fetch(`${PREFIX}/processes/recipe/execution`, {
        method: 'POST',
        headers: { ...JSON_HEADERS, Prefer: 'respond-async' },
        body: orderBody(order),
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

export function eventsUrl(jobId: string): string {
  return `${jobUrl(jobId)}/events`;
}

// A result file (`result.tif`, `mask.tif`, `recipe.json`): the route answers
// with a `303` to a signed URL, which a plain link follows (K6).
export function resultUrl(jobId: string, name: string): string {
  return `${jobUrl(jobId)}/results/${encodeURIComponent(name)}`;
}
