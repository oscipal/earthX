// Thin client for earthx's own STAC API (`/stac`). Same-origin relative URLs
// by default (the Vite dev server proxies /stac to the backend). Override
// with VITE_API_BASE. Never talks to the prototype's `/api/…` routes.

import type { Bbox, Collection, StacItem } from './types';

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

interface StacLink {
  rel: string;
  href: string;
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

// The `token` query parameter carried by the response's `rel=next` link, not
// a guessed format — `PagingLinks` on the backend is free to change its shape.
// The base is a placeholder only, for parsing a relative `href`; it is never
// used to reach a server (no DOM/`window` in the test environment, F2 = a).
export function nextTokenFrom(links: StacLink[] | undefined): string | null {
  const next = links?.find((l) => l.rel === 'next');
  if (!next) return null;
  const url = new URL(next.href, 'http://localhost');
  return url.searchParams.get('token');
}

export function buildSearchUrl(q: SearchQuery): string {
  const params = new URLSearchParams({ collections: q.collection });
  if (q.bbox) params.set('bbox', q.bbox.join(','));
  if (q.datetime) params.set('datetime', q.datetime);
  if (q.limit) params.set('limit', String(q.limit));
  if (q.token) params.set('token', q.token);
  return `${BASE}/stac/search?${params.toString()}`;
}

export async function searchItems(q: SearchQuery): Promise<ItemPage> {
  const body = await jsonOrThrow<{
    features: StacItem[];
    numberMatched?: number;
    numberReturned: number;
    links?: StacLink[];
  }>(await fetch(buildSearchUrl(q)));
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
export interface DownloadCropRequest {
  datasetId: string;
  items: string[];
  assets: string[];
  aoi: GeoJSON.Geometry;
  language?: string;
}

export async function downloadCrop(req: DownloadCropRequest): Promise<Blob> {
  const res = await fetch(`${BASE}/collections/${encodeURIComponent(req.datasetId)}/download`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      items: req.items,
      assets: req.assets,
      aoi: req.aoi,
      language: req.language ?? 'en',
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
  return await res.blob();
}
