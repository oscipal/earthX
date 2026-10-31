// Thin client for earthx's own STAC API (`/stac`). Same-origin relative URLs
// by default (the Vite dev server proxies /stac to the backend). Override
// with VITE_API_BASE. Never talks to the prototype's `/api/…` routes.

import type { FilterQuery, FilterQueryByCollection } from './searchFilters';
import { AOI_BODY_KEY, aoiCountsOf, type AoiCounts } from './aoiFilter';
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
  // The raw `detail` field of a JSON error body, when there was one and it was
  // a string — `undefined` for a non-JSON body, a missing `detail`, or a
  // `detail` that wasn't a string (M3-06b: lets a caller (`aoiFile.ts`) tell "the
  // route gave an actual reason" apart from `message`'s status-line fallback,
  // which `errorDetail` also uses when there is no real detail to show).
  readonly detail?: string;
  // The raw `Retry-After` response header, if the route sent one (M3-07b:
  // `placeSearch.ts` uses its presence to tell a `503` that is only briefly
  // busy — the shared rate slot, a cache/Postgres hiccup — apart from a `503`
  // that means place search is not enabled on this server at all, which never
  // carries this header). Not parsed into seconds: the value can be `5` or
  // `30` depending on which of those it is, and showing either as a promised
  // countdown would claim more than the next attempt actually holds.
  readonly retryAfter?: string;
  // The `title` of a problem document (M4-13b: a failed job's `/results` names
  // its failure there, e.g. "The source failed"), when it was a string.
  readonly title?: string;
  // The `type` of a problem document (M4-11b-2: a failed job names its kind as
  // `urn:earthx:job-failed:<kind>`, which picks the text the panel shows).
  readonly type?: string;
  // `X-Export-Job` of a crop's `413` (M4-11 K5, M4-11b K9): the same selection
  // fits an export job, or is too large for one as well; unset for every other
  // answer and for any other value of the header.
  readonly exportJob?: ExportJobHint;

  constructor(
    status: number,
    message: string,
    detail?: string,
    retryAfter?: string,
    title?: string,
    extra: { type?: string; exportJob?: ExportJobHint } = {},
  ) {
    super(message);
    this.name = 'HttpError';
    this.status = status;
    this.detail = detail;
    this.retryAfter = retryAfter;
    this.title = title;
    this.type = extra.type;
    this.exportJob = extra.exportJob;
  }
}

export type ExportJobHint = 'available' | 'too-large';

function exportJobHint(res: Response): ExportJobHint | undefined {
  const value = res.headers?.get('X-Export-Job');
  return value === 'available' || value === 'too-large' ? value : undefined;
}

async function httpErrorOf(res: Response, extra: { exportJob?: ExportJobHint } = {}): Promise<HttpError> {
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    /* non-JSON error body — errorDetail falls back to the status line */
  }
  const field = (name: 'detail' | 'title' | 'type') => {
    const value = (body as Record<string, unknown> | undefined)?.[name];
    return typeof value === 'string' ? value : undefined;
  };
  return new HttpError(
    res.status,
    errorDetail(body, res.status, res.statusText),
    field('detail'),
    res.headers?.get('Retry-After') ?? undefined,
    field('title'),
    { type: field('type'), ...extra },
  );
}

export async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) throw await httpErrorOf(res);
  return (await res.json()) as T;
}

export async function fetchCollections(): Promise<Collection[]> {
  const data = await jsonOrThrow<{ collections: Collection[] }>(
    await fetch(`${BASE}/stac/collections`),
  );
  return data.collections;
}

// M3-06b: `POST /aoi/upload` (M3-06a, `backend/earthx/api/aoi_upload_route.py`)
// checks an uploaded GeoJSON/KML/Shapefile-ZIP file and returns the geometry it
// found, in EPSG:4326. No `multipart/form-data` (the route's plan §6 measured
// that Starlette spools any file part over 1 MiB to disk regardless of a size
// cap, which the "never on disk" upload is built to avoid): the file goes as
// the raw request body, its name as a query parameter. `jsonOrThrow` turns a
// `400`/`413`/other error into an `HttpError` the caller (`aoiFile.ts`) maps to
// a message; a successful response is the bare geometry object, no envelope.
//
// NM4-57 (Otto, 30.10.2026): only the extension goes, as `aoi.<extension>`. A file name often names a person or a
// place, and a URL stands in access logs; the route reads nothing but the extension anyway.
export function uploadName(filename: string): string {
  const extension = /\.([A-Za-z0-9]{1,8})$/.exec(filename)?.[1];
  return extension ? `aoi.${extension}` : 'aoi';
}

export async function uploadAoi(file: Blob, filename: string): Promise<GeoJSON.Geometry> {
  return jsonOrThrow<GeoJSON.Geometry>(
    await fetch(`${BASE}/aoi/upload?filename=${uploadName(filename)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: file,
    }),
  );
}

// M3-07b: `POST /geocode` (M3-07a, `backend/earthx/api/geocode_route.py`) — a
// place name resolved to an outline and a bounding box via Nominatim, over the
// backend's own gateway. `outline` is `Polygon`/`MultiPolygon` or `null` (a
// point/line hit, or an outline that stayed too large even simplified);
// `bbox` is always `[west, south, east, north]` and already sanity-checked by
// the route. `attribution`/`attribution_url`/`license` come on every answer,
// even an empty `results: []` (the plan's placeSearch.ts shows them either way).
export interface PlaceResult {
  name: string;
  display_name: string;
  kind: string;
  bbox: [number, number, number, number];
  outline: GeoJSON.Polygon | GeoJSON.MultiPolygon | null;
  outline_simplified: boolean;
}

export interface PlaceSearchResponse {
  results: PlaceResult[];
  attribution: string;
  attribution_url: string;
  license: string;
}

export async function geocodePlace(q: string): Promise<PlaceSearchResponse> {
  return jsonOrThrow<PlaceSearchResponse>(
    await fetch(`${BASE}/geocode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ q }),
    }),
  );
}

export interface SearchQuery {
  // M3-13: a list, not one dataset — the backend answers a search naming more
  // than one collection with a genuine mixed page (`api/mixed_search.py`); the
  // viewer sends every dataset ticked in the control panel (M3-10).
  collections: string[];
  bbox?: Bbox;
  // M3-08: a polygon or point AOI searches by its true shape instead of its bbox
  // (`geoUtils.ts::searchArea` decides which of the two a caller sends — never
  // both, the backend rejects that combination). Never sent as a `GET` query
  // parameter, only in the `POST` body below.
  intersects?: GeoJSON.Geometry;
  datetime?: string;
  // DS-02c: the search filters of each dataset on its own (`query_by_collection`, plan §6.4 rule 3a) — a dataset
  // gets only what its registry entry offers, so nothing is dropped on the way. Only datasets with a filter set
  // are named; every key must be one of `collections`.
  queryByCollection?: FilterQueryByCollection;
  // DS-03b: the AOI itself, sent beside the `bbox` that stands for it when it is too long to search by its shape, so that
  // the cloud share in the AOI is measured in the AOI and not in its box (plan §6.5). Only ever in the body.
  aoi?: GeoJSON.Geometry;
  limit?: number;
  token?: string;
  // Ends the request ("Stop", or a change of the search the request belongs to).
  signal?: AbortSignal;
}

// One collection a mixed search could not reach on a given page (M3-13,
// `api/mixed_search.py::IncompleteSource`) — `reason` is one of `timeout`,
// `unreachable`, `upstream_error`, `unrecognised_answer`. Not shown in the UI
// in the results list's section head (M3-10).
export interface IncompleteCollection {
  collection: string;
  reason: string;
}

export interface ItemPage {
  features: StacItem[];
  numberMatched: number | null;
  numberReturned: number;
  nextToken: string | null;
  // M3-12: filters the backend could not honour for at least one searched
  // collection and dropped rather than silently applying — `datetime` for a
  // dataset with `capabilities.time_range=False`. Empty when nothing was
  // dropped. Mirrors the coverage route's own `ignored_filters`
  // (`api/coverage_route.py`).
  ignoredFilters: string[];
  // M3-13 F4: the same, broken down per collection — what a mixed search's
  // results list needs to say which dataset a note belongs to (M3-10). Empty
  // where the backend names none (a search over a single source may not).
  ignoredFiltersByCollection: Record<string, string[]>;
  // M3-13: collections a mixed search could not reach on this page. Empty for
  // a single-collection search, which never partially fails this way.
  incompleteCollections: IncompleteCollection[];
  // M3-10b: the collections whose source still has pages after this one
  // (collections sharing a source are open together). `null` where the answer
  // does not say — the caller then cannot rule out more for any of them.
  openCollections: string[] | null;
  // DS-03b: how far the server has got with the cloud share in the AOI, by dataset, over the whole search up to this
  // page. Empty without that filter, and for a source that is done and is not named any more.
  aoiFilter: Record<string, AoiCounts>;
}

function openCollectionsFrom(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  return value.filter((c): c is string => typeof c === 'string');
}

// A body field that should be `{collection: [filter, …]}`; anything else —
// including entries of the wrong type — reads as "nothing named", never as a
// crash: a note is only ever a hint, it must not take the results list down.
function ignoredByCollectionFrom(value: unknown): Record<string, string[]> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const result: Record<string, string[]> = Object.create(null);
  for (const [collection, filters] of Object.entries(value)) {
    if (!Array.isArray(filters)) continue;
    const names = filters.filter((f): f is string => typeof f === 'string');
    if (names.length > 0) result[collection] = names;
  }
  return result;
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
  const body: Record<string, unknown> = { collections: q.collections };
  if (q.bbox) body.bbox = q.bbox;
  if (q.intersects) body.intersects = q.intersects;
  if (q.datetime) body.datetime = q.datetime;
  if (q.queryByCollection && Object.keys(q.queryByCollection).length > 0) body.query_by_collection = q.queryByCollection;
  if (q.aoi) body[AOI_BODY_KEY] = q.aoi;
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
    ignored_filters?: string[];
    ignored_filters_by_collection?: unknown;
    incomplete_collections?: IncompleteCollection[];
    open_collections?: unknown;
  }>(
    await fetch(`${BASE}/stac/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildSearchBody(q)),
      signal: q.signal,
    }),
  );
  return {
    features: body.features,
    numberMatched: body.numberMatched ?? null,
    numberReturned: body.numberReturned,
    nextToken: nextTokenFrom(body.links),
    ignoredFilters: body.ignored_filters ?? [],
    ignoredFiltersByCollection: ignoredByCollectionFrom(body.ignored_filters_by_collection),
    incompleteCollections: body.incomplete_collections ?? [],
    openCollections: openCollectionsFrom(body.open_collections),
    aoiFilter: aoiCountsOf(body as Record<string, unknown>, q.queryByCollection),
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

// One pass as a single surface (M4-17, `adr/0006` §5 "Zu Frage 4"): the scenes
// stand in the URL, one `item` each and sorted by id, so the same selection is the
// same URL (plan KE5). The order the tiler reads them in is its own (`mosaic_order`,
// S5) and the URL's order does not count. Never a search id and never an AOI.
function mosaicQuery(itemIds: readonly string[], asset: string): string {
  const params = new URLSearchParams();
  for (const id of [...itemIds].sort()) params.append('item', id);
  params.set('asset', asset);
  return params.toString();
}

const mosaicBase = (datasetId: string) => `${BASE}/collections/${encodeURIComponent(datasetId)}/mosaic`;

export function buildMosaicTileTemplate(datasetId: string, itemIds: readonly string[], asset: string): string {
  return `${mosaicBase(datasetId)}/tiles/${TILE_MATRIX_SET}/{z}/{x}/{y}?${mosaicQuery(itemIds, asset)}`;
}

// What the client reads of a mosaic's TileJSON: the surface (`bounds`), the levels it
// serves, and `earthx:order` — the scene ids in the order a tile reads them, which the
// map below the first level stacks single scenes by.
export interface MosaicTileJson {
  bounds: Bbox;
  minzoom: number;
  maxzoom: number;
  order: string[];
}

const isNumber = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

// A cold mosaic of 64 scenes is about 5 s (plan §2.8); a time step waits for its TileJSON and draws
// nothing meanwhile, so an answer that never comes must end in an error, not in a map that stays empty.
export const MOSAIC_TILEJSON_TIMEOUT_MS = 60_000;

// Loading it also fills the tiler's item cache with every scene of the mosaic once,
// so the tiles that follow find them there (plan §4.3) — which is why the map asks
// for it before it asks for a single tile.
export async function fetchMosaicTileJson(
  datasetId: string,
  itemIds: readonly string[],
  asset: string,
): Promise<MosaicTileJson> {
  const url = `${mosaicBase(datasetId)}/${TILE_MATRIX_SET}/tilejson.json?${mosaicQuery(itemIds, asset)}`;
  const body = await jsonOrThrow<Record<string, unknown>>(
    await fetch(url, { signal: AbortSignal.timeout(MOSAIC_TILEJSON_TIMEOUT_MS) }),
  );
  const { bounds, minzoom, maxzoom } = body;
  const order = body['earthx:order'];
  if (
    !Array.isArray(bounds) ||
    bounds.length !== 4 ||
    !bounds.every(isNumber) ||
    !isNumber(minzoom) ||
    !isNumber(maxzoom) ||
    !Array.isArray(order) ||
    !order.every((id) => typeof id === 'string')
  ) {
    throw new Error('The tile server sent a mosaic description this page cannot read.');
  }
  return { bounds: bounds as Bbox, minzoom, maxzoom, order };
}

// The band an operator tile shows: one, or three in the order red, green, blue for a colour picture (NM4-64); `null`: the
// tiler chooses (the last Band math result, else the first band).
export type ShownBands = string | readonly string[] | null;

// One step of an operator tile: the operator, its version and its parameters as
// canonical JSON (`processing.ts::canonicalJson`), so equal parameters are one URL,
// one cache entry.
export interface TileStep {
  op: string;
  opVersion: number;
  paramsJson: string;
}

// The tile template of an operator or a chain of them (T1, adr/0014 §6.1, §6.2): the
// assets the steps read — one `asset` each, in the order of the order — and `op`,
// `op_version` and `params` once per step, in the order of the steps, as the tiler
// takes them (`api/tiler.py`, at most four). `band` is the one band of what the steps leave that the tile shows, or
// three for a colour picture (NM4-43d, NM4-64); left out, the tiler shows the last one a Band math step added, else the first.
export function buildOperatorTileTemplate(
  datasetId: string,
  itemId: string,
  assets: readonly string[],
  steps: readonly TileStep[],
  band: ShownBands = null,
): string {
  return `${itemBase(datasetId, itemId)}/tiles/${TILE_MATRIX_SET}/{z}/{x}/{y}?${operatorQuery(assets, steps, band)}`;
}

// The TileJSON of the same chain. The tiler opens the inputs and judges every step on
// the bands the one before leaves, so a `422` of it says which step it refuses and why
// (`api/tiler.py`, `processing/tile.py`) — the panel asks it instead of judging bands itself.
export function buildOperatorTileJsonUrl(
  datasetId: string,
  itemId: string,
  assets: readonly string[],
  steps: readonly TileStep[],
  band: ShownBands = null,
): string {
  return `${itemBase(datasetId, itemId)}/${TILE_MATRIX_SET}/tilejson.json?${operatorQuery(assets, steps, band)}`;
}

// The statistics of the same chain (M4-19c): one measure of what the steps make of the scene, for the colour
// scale and the unit of the preview. At most 1024 pixels on the long side (`processing/tile.py`).
export function buildOperatorStatisticsUrl(
  datasetId: string,
  itemId: string,
  assets: readonly string[],
  steps: readonly TileStep[],
  band: ShownBands = null,
): string {
  return `${itemBase(datasetId, itemId)}/statistics?${operatorQuery(assets, steps, band)}`;
}

// The mosaic of a pass with the steps over it (NM4-04, `api/mosaic_tiles.py`): the scenes as one `item` each,
// sorted by id like the mosaic without steps, and the assets and steps as the tile of one scene takes them.
// The order of the scenes in the URL does not count, so the same pass is the same URL. Never an AOI, never an id
// of a job or a recipe.
export function buildMosaicOperatorTileTemplate(
  datasetId: string,
  itemIds: readonly string[],
  assets: readonly string[],
  steps: readonly TileStep[],
  band: ShownBands = null,
): string {
  return `${mosaicBase(datasetId)}/tiles/${TILE_MATRIX_SET}/{z}/{x}/{y}?${mosaicOperatorQuery(itemIds, assets, steps, band)}`;
}

// Its TileJSON: the cheap question, with the refusals of the tiles and `earthx:order`, the scenes in the order a
// tile reads them.
export function buildMosaicOperatorTileJsonUrl(
  datasetId: string,
  itemIds: readonly string[],
  assets: readonly string[],
  steps: readonly TileStep[],
  band: ShownBands = null,
): string {
  return `${mosaicBase(datasetId)}/${TILE_MATRIX_SET}/tilejson.json?${mosaicOperatorQuery(itemIds, assets, steps, band)}`;
}

function mosaicOperatorQuery(
  itemIds: readonly string[],
  assets: readonly string[],
  steps: readonly TileStep[],
  band: ShownBands,
): string {
  const items = new URLSearchParams();
  for (const id of [...itemIds].sort()) items.append('item', id);
  return `${items.toString()}&${operatorQuery(assets, steps, band)}`;
}

function operatorQuery(assets: readonly string[], steps: readonly TileStep[], band: ShownBands): string {
  const params = new URLSearchParams();
  for (const asset of assets) params.append('asset', asset);
  for (const step of steps) {
    params.append('op', step.op);
    params.append('op_version', String(step.opVersion));
    params.append('params', step.paramsJson);
  }
  for (const name of band === null ? [] : typeof band === 'string' ? [band] : band) params.append('band', name);
  return params.toString();
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
  // Of an operator's statistics: the unit of this band of the result, `null` where it is not known.
  unit?: string | null;
  [key: string]: unknown;
}

export async function fetchStatistics(
  datasetId: string,
  itemId: string,
  asset: string,
): Promise<Record<string, BandStatistics>> {
  return jsonOrThrow(await fetch(buildStatisticsUrl(datasetId, itemId, asset)));
}

// The statistics at an address the panel built (`buildOperatorStatisticsUrl`).
export async function fetchStatisticsAt(url: string): Promise<Record<string, BandStatistics>> {
  return jsonOrThrow(await fetch(url));
}

// The statistics over the AOI of an order (NM4-19, `api/area_statistics.py`): the tiler counts them as the job does,
// so that the colour scale of the preview is the one of the result. The AOI goes in the body and nowhere else: the
// path names the dataset alone, and no error text of the answer is kept.
export interface AreaStatistics {
  bands: { name: string; unit: string | null; statistics: Record<string, unknown> }[];
  // `false`: read on a coarser raster (a window above 2048² pixels), the values can differ from the result's.
  exact: boolean;
  factor: number;
}

export function parseAreaStatistics(body: unknown): AreaStatistics {
  const { bands, exact, factor } = (body ?? {}) as Record<string, unknown>;
  if (!Array.isArray(bands) || bands.length === 0 || typeof exact !== 'boolean') {
    throw new Error('the server answered with statistics the panel cannot read');
  }
  return {
    bands: bands.map((band) => {
      const { name, unit, statistics } = (band ?? {}) as Record<string, unknown>;
      return {
        name: typeof name === 'string' ? name : '',
        unit: typeof unit === 'string' ? unit : null,
        statistics: statistics !== null && typeof statistics === 'object' ? (statistics as Record<string, unknown>) : {},
      };
    }),
    exact,
    factor: typeof factor === 'number' && Number.isFinite(factor) ? factor : 1,
  };
}

// `order`: the order of the job (`processing.ts::Order`), without the envelope of the job route.
export async function postAreaStatistics(datasetId: string, order: unknown): Promise<AreaStatistics> {
  const res = await fetch(`${BASE}/collections/${encodeURIComponent(datasetId)}/statistics`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(order),
  });
  return parseAreaStatistics(await jsonOrThrow<unknown>(res));
}

// What a walk through the pages has up to a page, or all of it once it is done.
export interface PagesSoFar {
  features: StacItem[];
  numberMatched: number | null;
  ignoredFilters: string[];
  ignoredFiltersByCollection: Record<string, string[]>;
  incompleteCollections: IncompleteCollection[];
  nextToken: string | null;
  openCollections: string[] | null;
  // By dataset, the last the walk was told (a source that is done is not named on later pages).
  aoiFilter: Record<string, AoiCounts>;
}

export interface WalkOptions {
  // Called after every page with what the walk has so far (DS-03b: the cloud share in the AOI answers in short steps,
  // and the list shows each step). Not called for a page that arrives after `signal` ended the walk.
  onPage?: (soFar: PagesSoFar) => void;
  // Ends the walk: the request in flight is dropped, and `nextToken` of the last `onPage` is where it can go on.
  signal?: AbortSignal;
}

// Pages through `nextToken` until the result is complete or `maxItems` is
// reached — the API never sorts (D8, `earthx.api.main`), so both "the nearest
// date" (runSearch) and "the footprints for a coverage cell" (M2-07c) have to
// walk every page rather than trust the first one. `startToken` continues an
// earlier walk ("Load more", M3-10b); `nextToken` is what is left once
// `maxItems` stopped it, `null` when the result is complete. A page may hold
// no scene at all (the cloud share in the AOI is measured scene by scene and an
// answer ends after a few seconds), and the walk goes on while the token does.
export async function searchAllPages(
  q: Omit<SearchQuery, 'limit' | 'token'>,
  maxItems: number,
  startToken?: string,
  options: WalkOptions = {},
): Promise<PagesSoFar> {
  let token = startToken;
  // The last page's: it says where the walk stopped.
  let openCollections: string[] | null = null;
  const features: StacItem[] = [];
  let numberMatched: number | null = null;
  // Every page of one search drops the same filter for the same reason, so
  // the first page's answer already speaks for the whole set.
  let ignoredFilters: string[] = [];
  const ignoredFiltersByCollection: Record<string, string[]> = {};
  // Unlike `ignoredFilters`, a mixed search's own failing source can change
  // from page to page (M3-13: it stops being asked again once it fails, but a
  // *different* source could still fail later) — collected across every page,
  // deduplicated by collection so a repeated notice does not pile up.
  const incompleteByCollection = new Map<string, IncompleteCollection>();
  const aoiFilter: Record<string, AoiCounts> = {};
  const soFar = (): PagesSoFar => ({
    features: [...features],
    numberMatched,
    ignoredFilters,
    ignoredFiltersByCollection: { ...ignoredFiltersByCollection },
    incompleteCollections: [...incompleteByCollection.values()],
    nextToken: token ?? null,
    openCollections,
    aoiFilter: { ...aoiFilter },
  });
  do {
    const page: ItemPage = await searchItems({ ...q, limit: 100, token, signal: options.signal });
    if (options.signal?.aborted) throw new DOMException('The search was stopped.', 'AbortError');
    features.push(...page.features);
    if (numberMatched === null) numberMatched = page.numberMatched;
    if (ignoredFilters.length === 0) ignoredFilters = page.ignoredFilters;
    // Kept per collection like the flat list: the first page that names a
    // collection speaks for the whole search.
    for (const [collection, filters] of Object.entries(page.ignoredFiltersByCollection)) {
      if (!Object.hasOwn(ignoredFiltersByCollection, collection)) ignoredFiltersByCollection[collection] = filters;
    }
    for (const entry of page.incompleteCollections) {
      if (!incompleteByCollection.has(entry.collection)) incompleteByCollection.set(entry.collection, entry);
    }
    Object.assign(aoiFilter, page.aoiFilter);
    token = page.nextToken ?? undefined;
    openCollections = page.openCollections;
    options.onPage?.(soFar());
  } while (token && features.length < maxItems);
  return soFar();
}

// The coverage route (`/coverage/{dataset_id}`, M2-05b: GET for the map extent, POST for an AOI since NM4-57)
// lives on the `api` process's base app, outside `/stac` — a different namespace, same same-origin dev-proxy
// pattern (vite.config.ts).
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
  // Set only by the `local-sql` area way (M3-11c): the union of a materialized
  // one-off product's own item footprints, as a GeoJSON MultiPolygon. `null`
  // everywhere else. Drawing it is M3-12 (M3-02 F-07); not read yet.
  area: GeoJSON.MultiPolygon | null;
  // Filters the request carried that this dataset could not honour and this
  // answer silently dropped rather than reject, e.g. `["datetime"]` for a
  // dataset without a time axis. Not surfaced in the UI yet (M3-12).
  ignored_filters: string[];
}

interface CoverageQuestion {
  datasetId: string;
  zoom: number;
  datetime?: string;
  // DS-02c: the search filters of the dataset, as JSON in the form of the STAC query extension (`query` of
  // `GET /coverage/{id}`, DS-02b). Replaces `max_cloud_cover`.
  query?: FilterQuery;
}

// Either the visible map extent or the box of an AOI, never both (NM4-57).
export type CoverageParams = CoverageQuestion &
  (
    | {
        // The visible map extent, rounded to the block grid of `coverage.ts` (`roundBboxToGrid`): no AOI, so it may
        // stand in the URL of a GET. The route refuses a box that is off that grid.
        bbox?: Bbox;
        aoiBbox?: never;
      }
    | {
        // The box of the AOI (M4 Q8): never in a URL, always in the body of a POST.
        aoiBbox: Bbox;
        bbox?: never;
      }
  );

const hasFilters = (query?: FilterQuery): query is FilterQuery => !!query && Object.keys(query).length > 0;

// The URL of a coverage question without an AOI. It never carries `aoiBbox`.
export function buildCoverageUrl(p: CoverageParams): string {
  const params = new URLSearchParams({ zoom: String(p.zoom) });
  if (p.bbox) params.set('bbox', p.bbox.join(','));
  if (p.datetime) params.set('datetime', p.datetime);
  if (hasFilters(p.query)) params.set('query', JSON.stringify(p.query));
  return `${BASE}/coverage/${encodeURIComponent(p.datasetId)}?${params.toString()}`;
}

// The body of `POST /coverage/{id}` (`CoverageBody` in `api/coverage_route.py`): the AOI, and what the GET
// carries in its query string, with the filters as an object.
export function buildCoverageBody(p: CoverageParams): Record<string, unknown> {
  const body: Record<string, unknown> = { zoom: p.zoom };
  if (p.aoiBbox) body.bbox = p.aoiBbox;
  if (p.datetime) body.datetime = p.datetime;
  if (hasFilters(p.query)) body.query = p.query;
  return body;
}

export async function fetchCoverage(p: CoverageParams): Promise<CoverageResponse> {
  if (!p.aoiBbox) return jsonOrThrow(await fetch(buildCoverageUrl(p)));
  return jsonOrThrow(
    await fetch(`${BASE}/coverage/${encodeURIComponent(p.datasetId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildCoverageBody(p)),
    }),
  );
}

// POST /collections/{dataset}/download (M2-06): the AOI crop as a ZIP, streamed
// synchronously and never cached (D3, D11). The body mirrors `DownloadRequest`
// in `api/tiler.py`.
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

// A refusal throws an `HttpError`; a `413` carries `exportJob` (M4-11b-2).
export async function downloadCrop(req: DownloadCropRequest): Promise<DownloadCropResult> {
  const res = await fetch(`${BASE}/collections/${encodeURIComponent(req.datasetId)}/download`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      groups: req.groups,
      assets: req.assets,
      aoi: req.aoi,
      resolution: req.resolution ?? 1,
    }),
  });
  if (!res.ok) throw await httpErrorOf(res, { exportJob: res.status === 413 ? exportJobHint(res) : undefined });
  const totalGroups = headerCount(res, 'X-Total-Groups');
  const skippedGroups = headerCount(res, 'X-Skipped-Groups');
  return { blob: await res.blob(), totalGroups, skippedGroups };
}
