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

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      /* non-JSON error body — errorDetail falls back to the status line */
    }
    throw new Error(errorDetail(body, res.status, res.statusText));
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
