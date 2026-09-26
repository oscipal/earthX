// Thin client for earthx's own STAC API (`/stac`). Same-origin relative URLs
// by default (the Vite dev server proxies /stac to the backend). Override
// with VITE_API_BASE. Never talks to the prototype's `/api/…` routes.

import type { Bbox, Collection, StacItem } from './types';

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

interface StacLink {
  rel: string;
  href: string;
  method?: string;
  // Present on a `POST`-shaped link (M3-08, `PagingLinks.link_next` on the
  // backend): the whole next request body, our own page token under `token`.
  body?: Record<string, unknown>;
}

interface StacErrorBody {
  detail?: unknown;
  code?: string;
  description?: string;
}

// The STAC error body carries either FastAPI's `{detail}` or the OGC API
// `{code, description}` shape — both are read, neither is assumed.
export function errorDetail(body: unknown, status: number, statusText: string): string {
  const fallback = `${status} ${statusText}`;
  if (!body || typeof body !== 'object') return fallback;
  const b = body as StacErrorBody;
  if (typeof b.detail === 'string') return b.detail;
  if (b.detail !== undefined) return JSON.stringify(b.detail);
  if (typeof b.description === 'string') return b.description;
  return fallback;
}

// Carries the HTTP status alongside the message `errorDetail` already builds, so a
// caller that cares about the distinction (M2-17: a malformed name is `400`, an
// unknown one is `404`, anything else is an upstream failure) does not have to
// re-parse `.message` to get it back.
export class HttpError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'HttpError';
    this.status = status;
  }
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      /* non-JSON error body — errorDetail falls back to the status line */
    }
    throw new HttpError(res.status, errorDetail(body, res.status, res.statusText));
  }
  return (await res.json()) as T;
}

export async function fetchCollections(): Promise<Collection[]> {
  const data = await jsonOrThrow<{ collections: Collection[] }>(
    await fetch(`${BASE}/stac/collections`),
  );
  return data.collections;
}

export interface SearchQuery {
  collection: string;
  bbox?: Bbox;
  // M3-08: a polygon or point AOI searches by its true shape instead of its bbox
  // (`geoUtils.ts::searchArea` decides which of the two a caller sends — never
  // both, the backend rejects that combination). Never sent as a `GET` query
  // parameter, only in the `POST` body below.
  intersects?: GeoJSON.Geometry;
  datetime?: string;
  limit?: number;
  token?: string;
}

export interface ItemPage {
  features: StacItem[];
  numberMatched: number | null;
  numberReturned: number;
  nextToken: string | null;
}

// M3-08: every search goes over `POST` now (F7a — keeps an AOI out of the access
// log, which a `GET` query string cannot avoid), so the response's `next` link is
// always the `POST`-shaped one: the token sits in `body.token`, not in `href`'s
// query string (`PagingLinks.link_next` on the backend). The `href`-based reading
// is kept as a fallback for a link this client did not itself ask for.
export function nextTokenFrom(links: StacLink[] | undefined): string | null {
  const next = links?.find((l) => l.rel === 'next');
  if (!next) return null;
  const fromBody = next.body?.token;
  if (typeof fromBody === 'string') return fromBody;
  const url = new URL(next.href, 'http://localhost');
  return url.searchParams.get('token');
}

// The `POST /stac/search` body, in the same field names as `SearchParams`
// (`backend/earthx/adapters/federated_search.py`) — `bbox`/`intersects` are
// mutually exclusive there, so a caller sends at most one (`geoUtils.searchArea`).
export function buildSearchBody(q: SearchQuery): Record<string, unknown> {
  const body: Record<string, unknown> = { collections: [q.collection] };
  if (q.bbox) body.bbox = q.bbox;
  if (q.intersects) body.intersects = q.intersects;
  if (q.datetime) body.datetime = q.datetime;
  if (q.limit) body.limit = q.limit;
  if (q.token) body.token = q.token;
  return body;
}

export async function searchItems(q: SearchQuery): Promise<ItemPage> {
  const body = await jsonOrThrow<{
    features: StacItem[];
    numberMatched?: number;
    numberReturned: number;
    links?: StacLink[];
  }>(
    await fetch(`${BASE}/stac/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildSearchBody(q)),
    }),
  );
  return {
    features: body.features,
    numberMatched: body.numberMatched ?? null,
    numberReturned: body.numberReturned,
    nextToken: nextTokenFrom(body.links),
  };
}

// One scene by its exact name, no search in front of it (M2-17, adr/0001 Z1).
// `undefined` — not a thrown error — means the collection does not have a scene
// by that name (the source's own `404`, adr/0005 rule I): a real answer for a
// well-formed name, not the exceptional case `jsonOrThrow` is for. A malformed
// name or an upstream failure still throws, same as `searchItems`.
export async function fetchItem(datasetId: string, itemId: string): Promise<StacItem | undefined> {
  const url = `${BASE}/stac/collections/${encodeURIComponent(datasetId)}/items/${encodeURIComponent(itemId)}`;
  const res = await fetch(url);
  if (res.status === 404) return undefined;
  return jsonOrThrow<StacItem>(res);
}

// The tiler process (adr/0006), a separate service from `/stac` — same-origin
// relative URLs here too, dev-proxied under `/collections` (vite.config.ts).
const TILE_MATRIX_SET = 'WebMercatorQuad';

function itemBase(datasetId: string, itemId: string): string {
  return `${BASE}/collections/${encodeURIComponent(datasetId)}/items/${encodeURIComponent(itemId)}`;
}

// A MapLibre-ready tile template: literal `{z}/{x}/{y}` placeholders, `asset`
// already baked in (adr/0001 Z4 — the URL alone determines the image). Stretch
// and colormap are added on top of this by `buildTileUrl` (mapLayers.ts) once
// they are known/applied.
export function buildTileTemplate(datasetId: string, itemId: string, asset: string): string {
  const params = new URLSearchParams({ asset });
  return `${itemBase(datasetId, itemId)}/tiles/${TILE_MATRIX_SET}/{z}/{x}/{y}?${params.toString()}`;
}

export function buildStatisticsUrl(datasetId: string, itemId: string, asset: string): string {
  const params = new URLSearchParams({ asset });
  return `${itemBase(datasetId, itemId)}/statistics?${params.toString()}`;
}

// rio-tiler's `BandStatistics`, plain JSON (backend/earthx/access/tiles.py) —
// only the fields the stretch calculation reads are named, the rest passes
// through untyped.
export interface BandStatistics {
  min: number;
  max: number;
  percentile_2: number;
  percentile_98: number;
  [key: string]: unknown;
}

export async function fetchStatistics(
  datasetId: string,
  itemId: string,
  asset: string,
): Promise<Record<string, BandStatistics>> {
  return jsonOrThrow(await fetch(buildStatisticsUrl(datasetId, itemId, asset)));
}

// Pages through `nextToken` until the result is complete or `maxItems` is
// reached — the API never sorts (D8, `earthx.api.main`), so both "the nearest
// date" (runSearch) and "the footprints for a coverage cell" (M2-07c) have to
// walk every page rather than trust the first one.
export async function searchAllPages(
  q: Omit<SearchQuery, 'limit' | 'token'>,
  maxItems: number,
): Promise<{ features: StacItem[]; numberMatched: number | null }> {
  let token: string | undefined;
  const features: StacItem[] = [];
  let numberMatched: number | null = null;
  do {
    const page: ItemPage = await searchItems({ ...q, limit: 100, token });
    features.push(...page.features);
    if (numberMatched === null) numberMatched = page.numberMatched;
    token = page.nextToken ?? undefined;
  } while (token && features.length < maxItems);
  return { features, numberMatched };
}

// The coverage route (`GET /coverage/{dataset_id}`, M2-05b) lives on the
// `api` process's base app, outside `/stac` — a different namespace, same
// same-origin dev-proxy pattern (vite.config.ts).
export type CoverageCompleteness = 'complete' | 'truncated' | 'sample';

export interface CoverageCell {
  k: string; // geotile key "z/x/y"
  n: number;
}

export interface CoverageHistogramPoint {
  t: string; // ISO instant, start of the bucket
  n: number;
}

// Mirrors `earthx.api.coverage_route._serialise` field for field.
export interface CoverageResponse {
  dataset_id: string;
  grid: string;
  level: number;
  counting: string;
  cells: CoverageCell[];
  counted: number;
  total_count: number | null;
  completeness: CoverageCompleteness;
  max_count: number;
  histogram: CoverageHistogramPoint[];
  histogram_interval: string;
  footprints_advised: boolean;
  from_cache: boolean;
  extent: Bbox | null;
}

export interface CoverageParams {
  datasetId: string;
  zoom: number;
  bbox?: Bbox;
  datetime?: string;
  maxCloudCover?: number;
}

export function buildCoverageUrl(p: CoverageParams): string {
  const params = new URLSearchParams({ zoom: String(p.zoom) });
  if (p.bbox) params.set('bbox', p.bbox.join(','));
  if (p.datetime) params.set('datetime', p.datetime);
  if (p.maxCloudCover !== undefined) params.set('max_cloud_cover', String(p.maxCloudCover));
  return `${BASE}/coverage/${encodeURIComponent(p.datasetId)}?${params.toString()}`;
}

export async function fetchCoverage(p: CoverageParams): Promise<CoverageResponse> {
  return jsonOrThrow(await fetch(buildCoverageUrl(p)));
}

// POST /collections/{dataset}/download (M2-06): the AOI crop as a ZIP, streamed
// synchronously and never cached (D3, D11). The body mirrors `DownloadRequest`
// in `api/tiler.py`; `language` picks the notice file's text (M2-07d requests
// `en`, matching the rest of the — English since 2026-09-20 — interface).
// One of `RESOLUTION_FACTORS` in `access/download.py` (F10c, M3-18 §10):
// how many times coarser than native to read. Native (`1`) is the default and
// is never chosen automatically — the dialog always shows the choice.
export const RESOLUTION_FACTORS = [1, 2, 4, 10] as const;
export type ResolutionFactor = (typeof RESOLUTION_FACTORS)[number];

// `groups` (M3-17, replacing the flat `items` list): item ids per group,
// mirroring `DownloadRequest.groups` in `api/tiler.py` — one merged file per
// group, separate groups as separate files in the same ZIP (P19). A single
// group is simply a list of one, the shape every download had before M3-17.
export interface DownloadCropRequest {
  datasetId: string;
  groups: string[][];
  assets: string[];
  aoi: GeoJSON.Geometry;
  language?: string;
  resolution?: ResolutionFactor;
}

// `totalGroups`/`skippedGroups` (M3-17, review finding 1): `X-Total-Groups`/
// `X-Skipped-Groups` off the response — a group dropped for never touching
// the AOI is otherwise only named inside the ZIP's ATTRIBUTION.txt, which the
// user only sees after the file is already saved. Counts only, read here
// before the dialog's own notice ever mentions them (`store.confirmDownload`).
export interface DownloadCropResult {
  blob: Blob;
  totalGroups: number;
  skippedGroups: number;
}

// A missing/non-numeric header is `0`, never `NaN` propagating into a user
// message — an older or misconfigured backend that does not send the header
// at all just means "nothing to report", not "something is wrong here".
function headerCount(res: Response, name: string): number {
  const value = Number(res.headers.get(name));
  return Number.isFinite(value) && value >= 0 ? value : 0;
}

export async function downloadCrop(req: DownloadCropRequest): Promise<DownloadCropResult> {
  const res = await fetch(`${BASE}/collections/${encodeURIComponent(req.datasetId)}/download`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      groups: req.groups,
      assets: req.assets,
      aoi: req.aoi,
      language: req.language ?? 'en',
      resolution: req.resolution ?? 1,
    }),
  });
  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      /* non-JSON error body — errorDetail falls back to the status line */
    }
    throw new Error(errorDetail(body, res.status, res.statusText));
  }
  const totalGroups = headerCount(res, 'X-Total-Groups');
  const skippedGroups = headerCount(res, 'X-Skipped-Groups');
  return { blob: await res.blob(), totalGroups, skippedGroups };
}
