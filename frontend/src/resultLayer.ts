// A finished job as a layer on the map (M4-13c-5, plan §3.4): the link the results
// document gives to the tiles of the result, the tile URL, how the result is drawn,
// when the map says "Overview", and when the layer is "Expired". Pure functions; the
// state lives in `processingStore.ts` and `store.ts`.

import type { MapLayer, ResultLayerInfo } from './layers';
import { buildTileUrl } from './mapLayers';
import { RGB, RGB_LABEL, startBand } from './processingBands';
import { presetFor, presetRange, type IndexPreset } from './indexPresets';
import { rescaleOf, type PreviewRange } from './processingPreview';
import { scaleOf, statsFrom, type ResultStats } from './render';
import type { AppliedRender, Bbox } from './types';

// The path of the output `tiles` (`api/processing_docs.py::TILES_HREF`), in the shape the
// tiler serves — nothing else is ever fetched or used for a layer. The results document
// links it absolute since NM4-03 (`EARTHX_TILER_URL`); only the path is kept, so the tiles
// are read through this host's own proxy and never from a host the document names.
// `secrets.token_urlsafe(16)`: 22 characters of the URL-safe alphabet.
const TILES_HREF = /^\/results\/[A-Za-z0-9_-]{22}\/WebMercatorQuad\/tilejson\.json$/;

// The one archive a raster result has (`api/result_zip.py`): the panel and the layer link the same file.
export const RESULT_ZIP = 'result.zip';

// From a minute before `expires` the tiler answers `410` (`objectstore/results.py::MIN_REMAINING`).
export const MIN_REMAINING_MS = 60_000;

// An absolute link is reduced to its path: `http` or `https` only, no credentials, query or fragment.
function pathOf(href: string): string | null {
  if (href.startsWith('/')) return href;
  let url: URL;
  try {
    url = new URL(href);
  } catch {
    return null;
  }
  const plain = (url.protocol === 'http:' || url.protocol === 'https:') && !url.username && !url.password && !url.search && !url.hash;
  return plain && href === `${url.origin}${url.pathname}` ? url.pathname : null;
}

export function tilesHref(doc: Record<string, { href?: unknown }>): string | null {
  const href = doc.tiles?.href;
  const path = typeof href === 'string' ? pathOf(href) : null;
  return path !== null && TILES_HREF.test(path) ? path : null;
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

// The statistics in the `properties` of the `result` link; `null` for a result from before
// they were written, or for a document that does not carry them in this shape.
export function resultStats(properties: Record<string, unknown> | undefined): ResultStats | null {
  return statsFrom(properties?.bands, properties?.['processing:expression'] != null);
}

// One band of a result and what the job measured of it: the colour scale of the layer comes from these (M4-32).
export interface ResultBand {
  name: string;
  stats: ResultStats | null;
  // The expression of the Band math step that made the band, where the order or the results say it (NM4-14): what the
  // presets of the dataset are matched by. `null` for a band of the data.
  expression?: string | null;
}

// The bands of `properties.bands` in the order of the file, so that the place of a band + 1 is its `bidx`. A band is judged
// as an index (`render.ts::scaleOf`) if a Band math step of the order made it; without the order, as the job is judged: if
// any step did.
export function resultBands(properties: Record<string, unknown> | undefined, order: { steps: { op: string; params: Record<string, unknown> }[] } | null): ResultBand[] {
  const listed = properties?.bands;
  if (!Array.isArray(listed)) return [];
  const steps = order?.steps.flatMap((step) =>
    step.op === 'band_math' && typeof step.params.name === 'string' ? [[step.params.name, step.params.expression] as const] : [],
  );
  const made = new Set(steps?.map(([name]) => name));
  const any = properties?.['processing:expression'] != null;
  // The results name the expression of the last Band math step and the band it made; the order says it for every one.
  const last = properties?.['processing:expression'] as { name?: unknown; expression?: unknown } | undefined;
  const expressions = new Map<string, string>(
    steps?.flatMap(([name, expression]) => (typeof expression === 'string' ? [[name, expression] as [string, string]] : [])) ??
      (typeof last?.name === 'string' && typeof last.expression === 'string' ? [[last.name, last.expression] as [string, string]] : []),
  );
  return listed.map((band): ResultBand => {
    const name = typeof (band as { name?: unknown } | null)?.name === 'string' ? (band as { name: string }).name : '';
    return { name, stats: statsFrom([band], order === null ? any : made.has(name)), expression: expressions.get(name) ?? null };
  });
}

// The range and colormap of the preset that `band` is (its expression is the preset's), or `null`. The colour picture and a
// band of the data are none.
export function presetOfResultBand(band: ResultBand | undefined, presets: readonly IndexPreset[]): PreviewRange | null {
  const preset = presetFor(presets, band?.expression);
  return preset ? presetRange(preset) : null;
}

// The places in the file of the three bands of the colour picture (`earthx:true_color`: red, green, blue), or `null` where the
// dataset has none or the file lacks one of them (NM4-64).
export function colourPlacesOf(bands: readonly ResultBand[], trueColor: readonly string[] | null): [number, number, number] | null {
  if (trueColor === null || trueColor.length !== 3) return null;
  const places = trueColor.map((name) => bands.findIndex((band) => band.name === name));
  return places.every((place) => place >= 0) ? [places[0], places[1], places[2]] : null;
}

// What the job measured of the three bands of the colour picture, as one measure: the scale is chosen from all three
// (`render.ts::scaleOf`), so that no channel is stretched by a range of its own. `null` where none has statistics.
export function colourStats(bands: readonly ResultBand[], colour: readonly number[]): ResultStats | null {
  const measured = colour.flatMap((place) => bands[place]?.stats?.bands ?? []);
  return measured.length > 0 ? { bands: measured, expression: false } : null;
}

// The place (0 is the first of the file) of the band a result layer starts with, the one the preview started with
// (Otto, 31.10.2026), or `RGB` for the colour picture (NM4-64): the band the preview showed when the job was started, if the
// result has it; else the result of a Band math step of the order, the last of the chain (which was created last is not
// kept); else RGB where the result has the three bands of a colour picture; else the first band.
export function startPlaceOf(
  bands: readonly ResultBand[],
  order: { steps: { op: string; params: Record<string, unknown> }[] } | null,
  shown: string | null,
  colour: readonly number[] | null = null,
): number | typeof RGB {
  const names = bands.map((band) => band.name);
  if (shown === RGB && colour !== null) return RGB;
  if (shown !== null && names.includes(shown)) return names.indexOf(shown);
  const made = (order?.steps ?? []).flatMap((step) => (step.op === 'band_math' && typeof step.params.name === 'string' ? [step.params.name] : []));
  const results = made.filter((name) => names.includes(name)).map((name, created) => ({ name, created }));
  const start = startBand([...(colour === null ? [] : [RGB]), ...names], results);
  return start === RGB ? RGB : Math.max(0, names.indexOf(start ?? ''));
}

// The range a band is drawn with by choice of the person: saved for the band, or — a result of one band — saved for the job;
// the range set in the panel when the job started belongs to the job and so to a result of one band.
export function ownRangeOf(
  job: { range: PreviewRange | null; bandRanges: Readonly<Record<string, PreviewRange>> },
  bands: readonly ResultBand[],
  place: number | typeof RGB,
): PreviewRange | null {
  if (bands.length <= 1) return job.range;
  return job.bandRanges[place === RGB ? RGB : (bands[place]?.name ?? '')] ?? null;
}

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
//  3. an index the dataset offers as a preset (a band whose expression is the preset's, NM4-14) is drawn with the
//     range and colormap of the preset, so that the same index looks the same wherever it is made;
//  4. an index (a Band math result whose 2–98 % lie in −1…1, `render.ts::scaleOf`) is drawn at −1…1 in `rdylgn`,
//     so that jobs can be compared with one another;
//  5. otherwise the 2–98 % of the AOI from the statistics, in `viridis`;
//  6. a result without statistics is drawn with the range of the panel, as before M4-32.
// The colour picture (`colour`, NM4-64) takes one range for its three bands and no colormap, whatever the rule says.
export function resultRender(
  dataType: string | null,
  panel: PreviewRange,
  stats: ResultStats | null = null,
  own: PreviewRange | null = null,
  colour = false,
  preset: PreviewRange | null = null,
): AppliedRender {
  if (dataType === null || !FLOAT.test(dataType)) return {};
  const scale = scaleOf(stats);
  const render = own ? drawnWith(own) : preset ? drawnWith(preset) : scale ? { rescale: `${scale.low},${scale.high}`, colormapName: scale.colormap } : drawnWith(panel);
  if (!colour) return render;
  const { colormapName: _none, ...plain } = render;
  return plain;
}

// The range and colormap a render stands for, as the fields of the result view show them.
export function rangeOfRender(render: AppliedRender): PreviewRange {
  const [vmin = '', vmax = ''] = render.rescale?.split(',') ?? [];
  return { vmin, vmax, colormap: render.colormapName ?? '' };
}

// The range and colormap a tile URL asks for: what a result layer draws now.
export function rangeOfTileUrl(tileUrl: string): PreviewRange {
  const query = new URLSearchParams(tileUrl.slice(tileUrl.indexOf('?') + 1));
  return rangeOfRender({ rescale: query.get('rescale') ?? undefined, colormapName: query.get('colormap_name') ?? undefined });
}

// The same range and colormap in the shape of a request.
export function renderOfRange(range: PreviewRange): AppliedRender | null {
  const rescale = rescaleOf(range);
  return 'rescale' in rescale ? drawnWith(range) : null;
}

// The tile URL of a result drawn another way: its style is the part after the first `&`
// (`resultTileTemplate` ends in `?tilesize=256`), and only that part changes. The band (`bidx`) stays unless `render` names one.
// The three bands of a colour picture take no colormap: the tiler refuses it.
export function restyledTileUrl(tileUrl: string, render: AppliedRender): string {
  const amp = tileUrl.indexOf('&');
  const kept = amp < 0 ? [] : new URLSearchParams(tileUrl.slice(amp + 1)).getAll('bidx');
  const bidx = render.bidx ?? (kept.length > 0 ? kept.join(',') : undefined);
  const { colormapName: _colormap, ...withoutColormap } = render;
  const style = bidx && bidx.includes(',') ? withoutColormap : render;
  return buildTileUrl(amp < 0 ? tileUrl : tileUrl.slice(0, amp), bidx ? { ...style, bidx } : style);
}

// The same result drawn from the band at `place` (0 is the first of the file): `bidx` counts from 1.
export function bandTileUrl(tileUrl: string, place: number, render: AppliedRender): string {
  return restyledTileUrl(tileUrl, { ...render, bidx: String(place + 1) });
}

// The same result drawn as a colour picture: the places of red, green and blue as `bidx`, in this order (NM4-64).
export function colourTileUrl(tileUrl: string, colour: readonly number[], render: AppliedRender): string {
  return restyledTileUrl(tileUrl, { ...render, bidx: colour.map((place) => place + 1).join(',') });
}

// How a layer of a result is drawn when no range was set by hand for its job (M4-32): the default of
// "Auto". `null` for a result that is drawn as it is.
export function defaultRange(info: Pick<ResultLayerInfo, 'dataType' | 'stats' | 'band' | 'preset'>, panel: PreviewRange): PreviewRange | null {
  const render = resultRender(info.dataType, panel, info.stats, null, info.band === RGB, info.preset ?? null);
  return 'rescale' in render || render.colormapName ? rangeOfRender(render) : null;
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

// "Add band as layer" (NM4-65 part 2, Otto, 31.10.2026): the band a result layer draws as a layer of its own. It is named after
// the band, drawn as the band is drawn now (the look that is applied and not yet saved comes along as its saved look), has
// the date, the opacity and the visibility of the layer it comes from, and carries no list of bands: it draws that one. Its
// settings and "Save" are its own from then on (`ResultLayerInfo.own`). `null` for a layer that is no result of several bands,
// one whose results are gone, or one whose band is not one of its bands.
export function bandLayerOf(layer: MapLayer, id: string): MapLayer | null {
  const info = layer.result;
  if (!info || layer.derived !== 'result' || !info.bands || info.bands.length < 2 || info.expired || info.deleted) return null;
  const band = info.band ?? 0;
  const colour = band === RGB;
  const named = colour ? (info.colour ? RGB_LABEL : null) : (info.bands[band]?.name || `Band ${band + 1}`);
  if (named === null || (!colour && !info.bands[band])) return null;
  const { bands: _bands, band: _band, colour: _colour, savedTileUrl: _unsaved, ...rest } = info;
  return {
    ...layer,
    id,
    name: named,
    overlays: layer.overlays.map((overlay) => ({ ...overlay })),
    result: { ...rest, ...(colour && info.colour ? { band: RGB, colour: info.colour } : {}), own: true },
  };
}
