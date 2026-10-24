// Permalinks (M4-19e, plan §3.5): "Share" keeps the order and a small view on the server
// under an identifier of its own, 30 days from its creation. The address carries the
// identifier and nothing else: never the area, never the order (Q8, §1.2). The key that
// deletes a link is shown once by the server and kept in this browser only
// (`localStorage`, `earthx.permalinks`); it is worth nothing without the identifier.

import { HttpError, jsonOrThrow } from './api';
import type { Order } from './processing';
import type { Bbox } from './types';
import { useProcessingStore } from './processingStore';
import { readRecipe } from './recipeFile';
import { useAppStore } from './store';

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';
const PREFIX = `${BASE}/processing/permalinks`;

export const PERMALINK_PARAM = 'permalink';
export const KEYS_STORAGE = 'earthx.permalinks';
export const GONE_TEXT = 'This link has expired or never existed.';

// What is restored besides the order: the map's centre and zoom, the range and colormap of
// the preview if the user set them by hand.
export interface PermalinkView {
  center: [number, number];
  zoom: number;
  range: { vmin: number; vmax: number; colormap: string } | null;
}

export interface PermalinkDocument {
  order: Order;
  view: PermalinkView;
  expiresAt: string;
}

export interface Created {
  id: string;
  expiresAt: string;
  deleteKey: string;
}

const isId = (value: unknown): value is string => typeof value === 'string' && /^[A-Za-z0-9_-]{22}$/.test(value);
const isObject = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && !Array.isArray(value);
const isNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);

export function permalinkAddress(id: string, location: Pick<Location, 'origin' | 'pathname'> = window.location): string {
  return `${location.origin}${location.pathname}?${PERMALINK_PARAM}=${id}`;
}

// The identifier in `?permalink=…`, or `null` when there is none or it cannot be one.
export function permalinkIdIn(search: string): string | null {
  const value = new URLSearchParams(search).get(PERMALINK_PARAM);
  return isId(value) ? value : null;
}

export async function createPermalink(order: Order, view: PermalinkView): Promise<Created> {
  const body = await jsonOrThrow<Record<string, unknown>>(
    await fetch(PREFIX, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ order, view }),
    }),
  );
  if (!isId(body.id) || typeof body.expires_at !== 'string' || typeof body.delete_key !== 'string') {
    throw new Error('the server answered with a link the panel cannot read');
  }
  return { id: body.id, expiresAt: body.expires_at, deleteKey: body.delete_key };
}

// The view as the panel keeps it now: the centre of the map's viewport (across the antimeridian too),
// the zoom, and the preview's range only where the user set it by hand (`null` for the default).
export function viewOf(
  bbox: Bbox,
  zoom: number,
  range: { vmin: string; vmax: string; colormap: string } | null,
): PermalinkView {
  const [west, south, east, north] = bbox;
  const lon = (west + (east < west ? east + 360 : east)) / 2;
  const hand = range && isNumber(Number(range.vmin)) && isNumber(Number(range.vmax)) && range.vmin.trim() !== '' && range.vmax.trim() !== '';
  return {
    center: [lon > 180 ? lon - 360 : lon, (south + north) / 2],
    zoom: Math.min(Math.max(zoom, 0), 24),
    range: hand ? { vmin: Number(range.vmin), vmax: Number(range.vmax), colormap: range.colormap } : null,
  };
}

export function parseView(value: unknown): PermalinkView | null {
  if (!isObject(value) || !Array.isArray(value.center) || value.center.length !== 2) return null;
  const [lon, lat] = value.center;
  if (!isNumber(lon) || !isNumber(lat) || !isNumber(value.zoom)) return null;
  const { range } = value;
  let parsed: PermalinkView['range'] = null;
  if (range !== null && range !== undefined) {
    if (!isObject(range) || !isNumber(range.vmin) || !isNumber(range.vmax) || typeof range.colormap !== 'string') return null;
    parsed = { vmin: range.vmin, vmax: range.vmax, colormap: range.colormap };
  }
  return { center: [lon, lat], zoom: value.zoom, range: parsed };
}

// What the server keeps is checked again: it is a file of someone else's, as far as this tab knows.
export async function fetchPermalink(id: string): Promise<PermalinkDocument> {
  if (!isId(id)) throw new HttpError(404, GONE_TEXT);
  const body = await jsonOrThrow<Record<string, unknown>>(await fetch(`${PREFIX}/${id}`));
  const read = readRecipe(JSON.stringify(body.order));
  const view = parseView(body.view);
  if (!read.ok || !view || typeof body.expires_at !== 'string') throw new Error('the server answered with a link the panel cannot read');
  return { order: read.order, view, expiresAt: body.expires_at };
}

export async function deletePermalink(id: string, key: string): Promise<void> {
  const res = await fetch(`${PREFIX}/${id}`, { method: 'DELETE', headers: { 'X-Delete-Key': key } });
  // `404`: unknown, expired or already gone; nothing is left to delete.
  if (!res.ok && res.status !== 404) await jsonOrThrow<unknown>(res);
}

// --- the keys of this browser ------------------------------------------------------

export type Keys = Record<string, { key: string; expiresAt: string }>;

export function loadKeys(now = Date.now()): Keys {
  try {
    const stored: unknown = JSON.parse(globalThis.localStorage?.getItem(KEYS_STORAGE) ?? '{}');
    if (!isObject(stored)) return {};
    const kept: Keys = {};
    for (const [id, entry] of Object.entries(stored)) {
      if (isId(id) && isObject(entry) && typeof entry.key === 'string' && typeof entry.expiresAt === 'string' && Date.parse(entry.expiresAt) > now) {
        kept[id] = { key: entry.key, expiresAt: entry.expiresAt };
      }
    }
    return kept;
  } catch {
    // Private browsing, storage off, a value that is no JSON: no keys, the link just cannot be deleted from here.
    return {};
  }
}

function saveKeys(keys: Keys): void {
  try {
    globalThis.localStorage?.setItem(KEYS_STORAGE, JSON.stringify(keys));
  } catch {
    /* the link still works; it only cannot be deleted from this browser */
  }
}

export function rememberKey(created: Created): void {
  saveKeys({ ...loadKeys(), [created.id]: { key: created.deleteKey, expiresAt: created.expiresAt } });
}

export function forgetKey(id: string): void {
  const { [id]: _gone, ...rest } = loadKeys();
  saveKeys(rest);
}

// "Delete link": the server first, the key after; a link that fails to delete keeps its key.
export async function removePermalink(id: string): Promise<boolean> {
  const entry = loadKeys()[id];
  if (!entry) return false;
  await deletePermalink(id, entry.key);
  forgetKey(id);
  return true;
}

// --- opening a link ----------------------------------------------------------------

let opening = false;

// At the start: `?permalink=<id>` restores the order and the view. The parameter goes from the
// address once the link has been tried, so a reload does not restore it again and the address
// that is copied from the bar is the app's, not the link's.
export async function openPermalinkInAddress(): Promise<void> {
  const id = permalinkIdIn(window.location.search);
  if (!id || opening) return;
  opening = true;
  const app = useAppStore.getState();
  try {
    const document = await fetchPermalink(id);
    const result = await useProcessingStore.getState().restoreOrder(document.order, document.view);
    if (!result.ok) app.setError(result.reason);
    else if (result.notes.length > 0) app.setNotice(result.notes.join(' '));
  } catch (error) {
    app.setError(error instanceof HttpError && error.status === 404 ? GONE_TEXT : `The link could not be opened: ${error instanceof Error ? error.message : String(error)}`);
  } finally {
    opening = false;
    const url = new URL(window.location.href);
    url.searchParams.delete(PERMALINK_PARAM);
    window.history.replaceState(window.history.state, '', url);
  }
}
