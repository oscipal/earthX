// Imperative helpers that keep the map's custom sources/layers in sync with app
// state. All are idempotent so they can be safely re-run after map.setStyle()
// (which wipes every custom source/layer).

import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl';

import { clipTileUrl } from './aoiClip';
import { buildTileTemplate } from './api';
import type { CoverageCell } from './api';
import { cellsToFeatureCollection, coverageFillColorExpression } from './coverage';
import { preferredGeoreferencedAsset, quicklookPlan } from './datasets';
import type { DatasetOption } from './datasets';
import { asFeatureCollection, footprintOf, quicklookCoords } from './geoUtils';
import type { Coords4 } from './geoUtils';
import { groupOutlineFeatures } from './groupOutline';
import type { LayerOverlay, MapLayer } from './layers';
import { indexRasterOf, viewIndexOf } from './viewIndex';
import { underlayOf } from './underlay';
import type { ImageOverlay } from './underlay';
import { passesOf, stackLikeView, viewOfPass } from './mosaic';
import type { Mosaics, PlannedRaster, SceneEntry } from './mosaic';
import { tileSizeOf } from './tileSize';
import type { AppliedRender, DownloadedInfo, StacItem, TimeStepGroup } from './types';

const AOI_SRC = 'aoi-src';
const SEL_SRC = 'mosaicsel-src'; // highlighted (selected-for-download) footprints
const SEL_LYR = 'mosaicsel-line';
const COVERAGE_SRC = 'coverage-src'; // the density grid (M2-07c)
const COVERAGE_FOOTPRINTS_SRC = 'coverage-footprints-src'; // real footprints once footprints_advised
const COVERAGE_AREA_SRC = 'coverage-area-src'; // a one-off product's extent (M3-12, F-07)

const EMPTY_FC: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] };
export const MAX_MOSAIC_LAYERS = 40;
// Every dynamic id the focus view and the browse preview hand out is below this; a mosaic
// adds the scenes it stacks below its first level to its own layer (`mosaic.ts`).
const MAX_DYNAMIC_LAYERS = 200;
// The preview of the processing panel (M4-13c-2): above every raster the map
// draws, under the AOI outline.
const PREVIEW_SRC = 'preview-src-';
const PREVIEW_LYR = 'preview-lyr-';

// What each of the view's own rasters draws (`overlaySignature`), and which of them are out of sight
// because a pinned layer that is switched on draws the same (`settleViewTwin`).
const viewPictures = new Map<string, string>();
const viewTwinsHidden = new Set<string>();

// Bumped on each syncMosaic so slow async quicklook processing can tell whether
// it has been superseded before it touches the map.
let syncGen = 0;
const MAX_LAYER_OVERLAYS = 200;
// The one marker of the app's pictures: every raster of the app and the outlines of the results lie right under it, in
// the order `restackAll` makes; the overlays of the "Basemap" menu (names, graticule) lie between it and the AOI, so that
// they stay over every picture (UI-02b, `mapStyles.ts`).
const OVERLAYS_BASE = 'overlays-base';

// --- one order of the pictures (NM4-59, Otto, 30.10.2026) ---
//
// The layer manager holds the pinned layers and one entry "Results": the search results, the view and the live preview.
// `resultsAt` pinned layers lie above "Results", the others below it. Within "Results" the tiers below are fixed, bottom
// to top; in a tier the rank decides (the order of the ticks, the last ticked on top), and of equal rank the layer that
// was placed later. Every layer is placed at the top and given its key; `restackAll` then lays all of them out from the
// state alone, whatever was on the map when a picture arrived.
const TIERS = ['view', 'otherTicked', 'openRest', 'openTicked', 'preview', 'outline'] as const;
type Tier = (typeof TIERS)[number];
interface ResultsKey {
  tier: number;
  rank: number;
  seq: number;
}
const resultsKeys = new Map<string, ResultsKey>();
let placedSeq = 0;

function keyResults(lyrId: string, tier: Tier, rank = 0): void {
  resultsKeys.set(lyrId, { tier: TIERS.indexOf(tier), rank, seq: ++placedSeq });
}

const byKey = ([, a]: [string, ResultsKey], [, b]: [string, ResultsKey]) => a.tier - b.tier || a.rank - b.rank || a.seq - b.seq;

// Where a new picture of the app goes before `restackAll` gives it its place: under the marker, or under the AOI where
// the marker is not there (a map without it, as in the tests of the older functions).
const rastersTop = (map: MapLibreMap): string | undefined =>
  map.getLayer(OVERLAYS_BASE) ? OVERLAYS_BASE : map.getLayer('aoi-fill') ? 'aoi-fill' : undefined;

// Lays the pictures of the app out in the order the state asks for, right under `rastersTop`, bottom to top: the pinned
// layers below "Results", "Results" by tier, the pinned layers above it. Moves only what is out of place; a move reloads
// no tile. A map that cannot tell its order is left as it is.
function restackAll(map: MapLibreMap): void {
  if (typeof map.getLayersOrder !== 'function') return;
  const pinned = wantedOverlays.filter((w) => isPlaced(map, w));
  const results = [...resultsKeys].filter(([id]) => map.getLayer(id)).sort(byKey).map(([id]) => id);
  // "Flip through layers" (NM4-65 part 9): the chosen layer lies over every other picture of the app, only the outlines of the
  // results (their last tier) stay over it, as they do over every layer. The list is not touched: it is this order that changes.
  const flipped = pinned.filter((w) => w.flip).map((w) => w.lyrId);
  const outlines = new Set(flipped.length === 0 ? [] : [...resultsKeys].filter(([, key]) => key.tier >= TIERS.indexOf('outline')).map(([id]) => id));
  const want = [
    ...pinned.filter((w) => !w.above && !w.flip).map((w) => w.lyrId),
    ...results.filter((id) => !outlines.has(id)),
    ...pinned.filter((w) => w.above && !w.flip).map((w) => w.lyrId),
    ...flipped,
    ...results.filter((id) => outlines.has(id)),
  ];
  const order = map.getLayersOrder();
  const top = rastersTop(map);
  let above = top;
  for (let i = want.length - 1; i >= 0; i--) {
    const id = want[i];
    const at = above === undefined ? order.length : order.indexOf(above);
    if (order[at - 1] !== id) {
      map.moveLayer(id, above);
      order.splice(order.indexOf(id), 1);
      order.splice(above === undefined ? order.length : order.indexOf(above), 0, id);
    }
    above = id;
  }
}
// Cache of processed quicklook data URLs, keyed by URL + the parameters that
// change what gets drawn (freistellung threshold, AOI clip) so the same
// source image loaded plain (browse mode, a pinned layer) and clipped to an
// AOI (the focus-mode underlay below `min_zoom`, O5) never share an entry.
const qlDataUrlCache = new Map<string, string>();

// Redraw a quicklook onto a canvas: an AOI clip if `clipRings` names one
// (`Path2D`, `evenodd` — the same pattern `aoiClip.ts::maskedBitmap` uses to
// clip a raster tile, on a different canvas API here because this one also
// keys nodata afterwards) and, where the registry names a freistellung
// threshold (M3-12, `earthx:viewer.quicklook_nodata_max`), any pixel at or
// below it in every band made fully transparent — so only the acquisition
// swath shows over the basemap, and outside an AOI clip nothing shows at all.
// Runs on the image loaded straight from the asset host (D14, not a
// same-origin proxy) with `crossOrigin = 'anonymous'` (`loadProcessed`
// below), so the canvas is not tainted (M3-02 K-23: an earlier version of
// this comment still described the pre-D14 proxy).
function processQuicklook(
  img: HTMLImageElement,
  nodataMax: number | null,
  clipRings: readonly (readonly [number, number][])[] | null,
): string {
  const w = img.naturalWidth;
  const h = img.naturalHeight;
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  if (!ctx) return img.src;
  const rings = clipRings?.filter((ring) => ring.length >= 3) ?? [];
  if (rings.length > 0) {
    const path = new Path2D();
    for (const ring of rings) {
      path.moveTo(ring[0][0], ring[0][1]);
      for (const [px, py] of ring.slice(1)) path.lineTo(px, py);
      path.closePath();
    }
    ctx.save();
    ctx.clip(path, 'evenodd');
    ctx.drawImage(img, 0, 0);
    ctx.restore();
  } else {
    ctx.drawImage(img, 0, 0);
  }
  if (nodataMax !== null) {
    const data = ctx.getImageData(0, 0, w, h);
    const px = data.data;
    for (let p = 0; p < px.length; p += 4) {
      if (px[p] <= nodataMax && px[p + 1] <= nodataMax && px[p + 2] <= nodataMax) {
        px[p + 3] = 0;
      }
    }
    ctx.putImageData(data, 0, 0);
  }
  return canvas.toDataURL('image/png');
}

function qlCacheKey(url: string, nodataMax: number | null, clipRings: unknown): string {
  return clipRings ? `${url}\u0000${nodataMax}\u0000${JSON.stringify(clipRings)}` : `${url}\u0000${nodataMax}`;
}

// Load a quicklook, process it (see `processQuicklook`), and hand back the
// data URL (cached). `nodataMax` and `clipRings` come from the registry and
// the caller's own AOI respectively — `mapLayers.ts` decides nothing about
// which dataset gets which threshold, it only applies what it is given.
function loadProcessed(
  url: string,
  nodataMax: number | null,
  clipRings: readonly (readonly [number, number][])[] | null,
  cb: (dataUrl: string) => void,
): void {
  const key = qlCacheKey(url, nodataMax, clipRings);
  const cached = qlDataUrlCache.get(key);
  if (cached) {
    cb(cached);
    return;
  }
  const img = new Image();
  // Load-bearing: the quicklook comes straight from the asset host now (D14),
  // not a same-origin proxy. Without this the browser taints the canvas the
  // moment the image isn't same-origin, and getImageData below throws — the
  // nodata keying would fail silently. The host sends
  // `Access-Control-Allow-Origin: *` (adr/0006 §3.6, gemessen); no test can
  // show that a CORS header actually arrived, so it is checked in the demo
  // instead (plan §9).
  img.crossOrigin = 'anonymous';
  img.onload = () => {
    const dataUrl = processQuicklook(img, nodataMax, clipRings);
    qlDataUrlCache.set(key, dataUrl);
    cb(dataUrl);
  };
  img.onerror = () => {
    /* unreadable quicklook — skip */
  };
  img.src = url;
}

function placeImage(
  map: MapLibreMap,
  srcId: string,
  lyrId: string,
  dataUrl: string,
  coords: Coords4,
  // A plain opacity, or a MapLibre zoom expression (O5, `addQuicklookUnderlay`
  // below needs the image to fade out exactly where the raster tiles above it
  // take over — an `ImageSource` has no `minzoom`/`maxzoom` of its own the way
  // a raster tile source does, so the boundary lives in `raster-opacity`
  // instead). `unknown` rather than maplibre-gl's own expression type: this
  // module stays loadable without the real library (see the import comment
  // in `aoiClip.ts` for why), and `paint` itself accepts one loosely already
  // (`coverage-heat`'s `fill-color` above).
  opacity: number | unknown[],
): void {
  if (map.getSource(srcId)) return;
  map.addSource(srcId, { type: 'image', url: dataUrl, coordinates: coords });
  map.addLayer(
    {
      id: lyrId,
      type: 'raster',
      source: srcId,
      paint: { 'raster-opacity': opacity as never, 'raster-fade-duration': 0 },
    },
    rastersTop(map),
  );
}

// The released levels come from the registry now (`earthx:viewer`, M2-10), not
// from a constant here: they differ per source, and the tile route refuses
// anything outside them with a 400, so a ceiling guessed in the client would
// only produce failing tiles. Below `minzoom` MapLibre requests nothing at all
// and above `maxzoom` it overzooms the last level — which is what "overzoom is
// allowed above z14" means for the second dataset (adr/0007 §12.10), and what
// keeps ordinary scroll-zoom off MapLibre's own ceiling of z22.
interface RasterZoom {
  minZoom: number;
  maxZoom: number;
  // From this zoom up the layer is not drawn at all (MapLibre's layer `maxzoom`). A source's own
  // `maxzoom` hides nothing, it overzooms — so a scene meant for the levels below a mosaic needs this.
  hideFrom?: number;
}

function placeRaster(
  map: MapLibreMap,
  srcId: string,
  lyrId: string,
  tileUrl: string,
  bounds: [number, number, number, number],
  opacity: number,
  zoom: RasterZoom,
): void {
  if (map.getSource(srcId)) return;
  map.addSource(srcId, {
    type: 'raster',
    tiles: [tileUrl],
    tileSize: tileSizeOf(tileUrl),
    bounds,
    minzoom: zoom.minZoom,
    maxzoom: zoom.maxZoom,
  });
  map.addLayer(
    {
      id: lyrId,
      type: 'raster',
      source: srcId,
      ...(zoom.hideFrom === undefined ? {} : { maxzoom: zoom.hideFrom }),
      paint: { 'raster-opacity': opacity, 'raster-fade-duration': 0 },
    },
    rastersTop(map),
  );
}

// Full tile URL from a template: the template already carries the mandatory
// `asset` (api.ts `buildTileTemplate`, adr/0001 Z4); this adds the
// stretch/colormap/band params — committed via "Apply" for a full-resolution
// overlay, taken straight from the registry for a browse preview. Also used by
// the store to snapshot a layer.
export function buildTileUrl(template: string, render: AppliedRender): string {
  const params = new URLSearchParams();
  // Several bands (`2,1,3`, a colour picture) are one `bidx` each, in this order.
  for (const place of render.bidx ? render.bidx.split(',') : []) params.append('bidx', place);
  if (render.expression) params.set('expression', render.expression);
  if (render.colormapName) params.set('colormap_name', render.colormapName);
  if (render.rescale) params.set('rescale', render.rescale);
  const q = params.toString();
  return q ? `${template}&${q}` : template;
}

// Whether the app's own layers are in the map already: they are after a change of the basemap (a style diff fires
// `style.load` as well, but leaves everything of the app in place), they are not after the first load.
export function hasOwnLayers(map: MapLibreMap): boolean {
  return !!map.getSource(AOI_SRC);
}

export function ensureBaseLayers(map: MapLibreMap): void {
  if (!map.getSource(AOI_SRC)) {
    map.addSource(AOI_SRC, { type: 'geojson', data: EMPTY_FC });
    map.addLayer({ id: OVERLAYS_BASE, type: 'background', layout: { visibility: 'none' } });
    map.addLayer({
      id: 'aoi-fill',
      type: 'fill',
      source: AOI_SRC,
      paint: { 'fill-color': '#19e0ff', 'fill-opacity': 0.06 },
    });
    map.addLayer({
      id: 'aoi-line',
      type: 'line',
      source: AOI_SRC,
      paint: { 'line-color': '#19e0ff', 'line-width': 1.6, 'line-dasharray': [3, 2] },
    });
  }
  if (!map.getSource(COVERAGE_SRC)) {
    map.addSource(COVERAGE_SRC, { type: 'geojson', data: EMPTY_FC });
    // Acquisition-density heatmap: a `fill` choropleth over the geotile grid,
    // not MapLibre's own `heatmap` type (adr/0004 §5 — that type is
    // point-based and mixes intensity with radius and zoom, so a cell's exact
    // count would not be readable from it, and the legend has nothing to
    // anchor to). The color stops are set per response in `setCoverageDisplay`
    // (log-scaled, anchored on that response's own maximum).
    map.addLayer({
      id: 'coverage-heat',
      type: 'fill',
      source: COVERAGE_SRC,
      layout: { visibility: 'none' },
      paint: {
        // maplibre-gl doesn't export the expression-spec type this needs, so
        // `coverage.ts` returns a plain array and the cast happens once,
        // here — `setPaintProperty` below takes `value: any` and needs none.
        'fill-color': coverageFillColorExpression(1) as never,
        'fill-opacity': 0.5,
        'fill-outline-color': 'rgba(0,0,0,0)',
      },
    });
  }
  if (!map.getSource(COVERAGE_FOOTPRINTS_SRC)) {
    map.addSource(COVERAGE_FOOTPRINTS_SRC, { type: 'geojson', data: EMPTY_FC });
    // Below the switch point (`footprints_advised`), real scene footprints
    // replace the density cells — outlines only, so the imagery underneath
    // stays visible.
    map.addLayer({
      id: 'coverage-footprints-line',
      type: 'line',
      source: COVERAGE_FOOTPRINTS_SRC,
      layout: { visibility: 'none' },
      paint: { 'line-color': '#a6d96a', 'line-width': 1.4, 'line-opacity': 0.85 },
    });
  }
  if (!map.getSource(COVERAGE_AREA_SRC)) {
    map.addSource(COVERAGE_AREA_SRC, { type: 'geojson', data: EMPTY_FC });
    // A one-off product (ENTSCHEIDUNGEN §2 "bei Einmal-Produkten durch die
    // Ausdehnung allein"): one flat fill, no density legend — the density
    // heatmap's whole point (how many acquisitions per cell) does not apply
    // to a single elevation model or map with exactly one coverage.
    map.addLayer({
      id: 'coverage-area-fill',
      type: 'fill',
      source: COVERAGE_AREA_SRC,
      layout: { visibility: 'none' },
      paint: { 'fill-color': '#a6d96a', 'fill-opacity': 0.18 },
    });
    map.addLayer({
      id: 'coverage-area-line',
      type: 'line',
      source: COVERAGE_AREA_SRC,
      layout: { visibility: 'none' },
      paint: { 'line-color': '#a6d96a', 'line-width': 1.4, 'line-opacity': 0.85 },
    });
  }
  if (!map.getSource(SEL_SRC)) {
    map.addSource(SEL_SRC, { type: 'geojson', data: EMPTY_FC });
    // The outlines of the ticked scenes are the top tier of "Results" (NM4-59): under the overlays and the AOI.
    map.addLayer(
      {
        id: SEL_LYR,
        type: 'line',
        source: SEL_SRC,
        paint: { 'line-color': '#ffd166', 'line-width': 3, 'line-blur': 1, 'line-opacity': 0.95 },
      },
      rastersTop(map),
    );
    keyResults(SEL_LYR, 'outline');
  }
}

export type CoverageDisplayMode = 'off' | 'density' | 'footprints' | 'area';

export interface CoverageDisplay {
  mode: CoverageDisplayMode;
  cells: CoverageCell[];
  maxCount: number;
  footprints: GeoJSON.FeatureCollection | null;
  // M3-12, F-07: the geometry of a one-off product's answer
  // (`coverage.ts::areaGeometry`) — its own footprint union, or its plain
  // extent where there is no union to draw.
  area: GeoJSON.Geometry | null;
}

// Reconciles all three coverage layers with the current mode — only one of
// them ever carries data, so a stray re-render can't show two at once
// (`store.ts` picks the mode via `coverage.ts::showFootprints`/`isAreaAnswer`).
export function setCoverageDisplay(map: MapLibreMap, display: CoverageDisplay): void {
  const density = display.mode === 'density';
  const footprints = display.mode === 'footprints';
  const area = display.mode === 'area';
  setData(map, COVERAGE_SRC, density ? cellsToFeatureCollection(display.cells) : EMPTY_FC);
  if (density && map.getLayer('coverage-heat')) {
    map.setPaintProperty('coverage-heat', 'fill-color', coverageFillColorExpression(display.maxCount));
  }
  setVisibility(map, 'coverage-heat', density);
  setData(map, COVERAGE_FOOTPRINTS_SRC, footprints ? (display.footprints ?? EMPTY_FC) : EMPTY_FC);
  setVisibility(map, 'coverage-footprints-line', footprints);
  setData(map, COVERAGE_AREA_SRC, area ? asFeatureCollection(display.area) : EMPTY_FC);
  setVisibility(map, 'coverage-area-fill', area);
  setVisibility(map, 'coverage-area-line', area);
}

function setVisibility(map: MapLibreMap, layerId: string, visible: boolean): void {
  if (!map.getLayer(layerId)) return;
  map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none');
}

function setData(map: MapLibreMap, srcId: string, data: GeoJSON.GeoJSON): void {
  const src = map.getSource(srcId) as GeoJSONSource | undefined;
  if (src) src.setData(data);
}

export function setAoiData(map: MapLibreMap, geom: GeoJSON.Geometry | null): void {
  setData(map, AOI_SRC, asFeatureCollection(geom));
}

// The view's own rasters live in one of two id ranges, `m-…` and `n-…`. A new sync lays its layers in the range the
// last one did not use and takes the last one's away only once the new picture has loaded, so that switching
// between the quicklook and full resolution (or any redraw of the view) never shows the basemap in between.
type DynamicBank = 'm' | 'n';
const DYNAMIC_KINDS = ['img-lyr', 'img-src', 'tiles-lyr', 'tiles-src'] as const;
let bank: DynamicBank = 'm';
// How long the picture it replaces stays when the new one does not load (a tile that fails, a quicklook that does not arrive).
const RETIRE_AFTER_MS = 10_000;
let retiring: { id: number; map: MapLibreMap; bank: DynamicBank; timer: ReturnType<typeof setTimeout> } | null = null;
let retired = 0;
// Quicklooks of the current sync that are still on their way, and whether it has put a layer on the map at all.
let pendingImages = 0;
let drawnNew = false;

// A time step that is played (NM4-18) arrives over the picture it replaces without being seen: its layers are laid at
// opacity 0, `holding` says when and to whom the step is shown, and the step is shown, with the old picture taken away
// in the same breath, once it has loaded for the part of the map in view and `notBefore` has passed. Until then the old
// picture stays, never the basemap. A step that is asked for before the one before has arrived drops that one.
interface Hold {
  // The earliest time (ms since the epoch) the step may be shown: the picture before it was shown at least that long.
  notBefore: number;
  onShown: () => void;
}
let holding: Hold | null = null;
const arriving = new Set<string>();

const dynamicId = (kind: (typeof DYNAMIC_KINDS)[number], i: number): string => `${bank}-${kind}-${i}`;

function hasDynamic(map: MapLibreMap, which: DynamicBank): boolean {
  for (let i = 0; i < MAX_DYNAMIC_LAYERS; i++) {
    if (map.getLayer(`${which}-img-lyr-${i}`) || map.getLayer(`${which}-tiles-lyr-${i}`)) return true;
  }
  return false;
}

function removeDynamic(map: MapLibreMap, which: DynamicBank): void {
  // Remove by deterministic id across the whole index range — not just the
  // tracked ids — so an overlay placed by a slow async quicklook load that
  // finished around a re-sync can't survive as an orphan.
  for (let i = 0; i < MAX_DYNAMIC_LAYERS; i++) {
    for (const lyr of [`${which}-img-lyr-${i}`, `${which}-tiles-lyr-${i}`]) {
      if (map.getLayer(lyr)) map.removeLayer(lyr);
      viewPictures.delete(lyr);
      viewTwinsHidden.delete(lyr);
      resultsKeys.delete(lyr);
    }
    for (const src of [`${which}-img-src-${i}`, `${which}-tiles-src-${i}`]) {
      if (map.getSource(src)) map.removeSource(src);
    }
  }
}

function revealArriving(map: MapLibreMap): void {
  for (const lyr of arriving) if (map.getLayer(lyr)) map.setPaintProperty(lyr, 'raster-opacity', 1);
  arriving.clear();
}

// The step that was held back is on the map: said once, to whoever asked for it to be held.
function announceShown(): void {
  const done = holding?.onShown;
  holding = null;
  done?.();
}

function finishRetired(map: MapLibreMap): void {
  if (retiring) clearTimeout(retiring.timer);
  revealArriving(map);
  if (retiring) removeDynamic(map, retiring.bank);
  retiring = null;
  announceShown();
}

const retireTimer = (map: MapLibreMap, id: number) => setTimeout(() => retiring?.id === id && finishRetired(map), RETIRE_AFTER_MS);

// Lays a layer of the step being held at opacity 0 (`finishRetired` shows it), when there is a picture to hold.
function holdBack(map: MapLibreMap, lyrId: string): void {
  if (!holding || !retiring || !map.getLayer(lyrId)) return;
  // No fade to opacity 1 (MapLibre's 300 ms): the old picture goes at once, and the new one must be there at once.
  map.setPaintProperty(lyrId, 'raster-opacity-transition', { duration: 0, delay: 0 });
  map.setPaintProperty(lyrId, 'raster-opacity', 0);
  arriving.add(lyrId);
}

// Start of a sync of the view: what the view drew is taken away at once where the map cannot say when the new picture is
// there, else it stays, under the new one, until `settleRetired`.
function retireDynamicMosaic(map: MapLibreMap, hold = false): void {
  pendingImages = 0;
  if (!hold) holding = null;
  // A style reload (a theme switch) wipes the layers a picture was waiting to be taken away from.
  if (retiring && (retiring.map !== map || !hasDynamic(map, retiring.bank))) {
    clearTimeout(retiring.timer);
    retiring = null;
    arriving.clear();
  }
  // The last sync drew nothing yet (a mosaic still on its way): the picture before it waits on for this one. A step that
  // is asked for after a step that is still on its way gets its own time.
  if (retiring && !drawnNew) {
    if (hold) {
      clearTimeout(retiring.timer);
      retiring.timer = retireTimer(map, retiring.id);
    }
    return;
  }
  // The step before this one has not arrived: it is dropped, the picture on the map stays, and the wait starts anew.
  if (retiring && hold && arriving.size > 0) {
    removeDynamic(map, bank);
    arriving.clear();
    drawnNew = false;
    clearTimeout(retiring.timer);
    retiring.timer = retireTimer(map, retiring.id);
    return;
  }
  finishRetired(map);
  drawnNew = false;
  if (!hasDynamic(map, bank)) {
    bank = 'm';
    return;
  }
  if (typeof map.once !== 'function') {
    removeDynamic(map, bank);
    return;
  }
  const id = ++retired;
  retiring = { id, map, bank, timer: retireTimer(map, id) };
  bank = bank === 'm' ? 'n' : 'm';
}

// Calls `done` once the layers that arrive have every tile for the part of the map in view. Only those sources count,
// not `idle`, which waits for the basemap as well. Looked at after each frame: a source that has just been added has no
// tile asked for until a frame has been drawn, and only then says it is loaded.
function onceArrived(map: MapLibreMap, gen: number, done: () => void): void {
  const sources = [...arriving].flatMap((lyr) => (map.getLayer(lyr) as { source?: string } | undefined)?.source ?? []);
  const check = () => {
    // Dropped for a newer step, or its sources are gone (a style reload): nothing to wait for, and none to ask about.
    if (gen !== syncGen || !sources.every((src) => map.getSource(src))) return map.off('render', check);
    if (!sources.every((src) => map.isSourceLoaded(src))) return;
    map.off('render', check);
    done();
  };
  map.on('render', check);
}

// The new picture is on the map once the quicklooks it waits for have arrived and the map has no tile left to load.
// A step that is held waits for the tiles of its own layers and for `notBefore` instead; one with no picture to hold is
// only announced.
function settleRetired(map: MapLibreMap): void {
  if (!drawnNew || pendingImages > 0 || (!retiring && !holding)) return;
  const id = retiring?.id;
  const gen = syncGen;
  const show = () => (retiring ? finishRetired(map) : announceShown());
  const settle = () => {
    if (pendingImages !== 0 || retiring?.id !== id) return;
    // The minimum time is the picture before it's: with none, there is nothing to wait for.
    const wait = retiring ? (holding?.notBefore ?? 0) - Date.now() : 0;
    if (wait <= 0) return show();
    setTimeout(() => gen === syncGen && retiring?.id === id && show(), wait);
  };
  if (holding && retiring) onceArrived(map, gen, settle);
  else map.once('idle', settle);
}

// A held step that draws nothing (no preview, or the results are off the map) is shown, which takes the picture before it
// away, once that picture has had its time.
function finishWhenDue(map: MapLibreMap, gen: number): void {
  const wait = (holding?.notBefore ?? 0) - Date.now();
  if (wait <= 0) return finishRetired(map);
  setTimeout(() => gen === syncGen && finishRetired(map), wait);
}

// A sync that draws nothing new has nothing to wait for.
function dropRetired(map: MapLibreMap): void {
  finishRetired(map);
}

// What decides the places of the scenes of the results: the ticks in the order they were made, and which scenes belong to
// the group that is open.
interface ResultsOrder {
  ticks: readonly string[];
  isOpen: (id: string) => boolean;
}

// The tier of a scene of the results within "Results" (NM4-55, NM4-59, Otto, 30.10.2026): a ticked scene of the open group
// on top, then the other scenes of the open group, then the ticked scenes of the other groups and datasets; ticked ones in
// the order they were ticked, the last on top. In a view the same as in browsing.
function keyScene(lyrId: string, id: string, order: ResultsOrder): void {
  const rank = order.ticks.indexOf(id);
  if (rank < 0) keyResults(lyrId, 'openRest');
  else keyResults(lyrId, order.isOpen(id) ? 'openTicked' : 'otherTicked', rank);
}

function clearPreview(map: MapLibreMap): void {
  for (let i = 0; i < MAX_MOSAIC_LAYERS; i++) {
    resultsKeys.delete(`${PREVIEW_LYR}${i}`);
    if (map.getLayer(`${PREVIEW_LYR}${i}`)) map.removeLayer(`${PREVIEW_LYR}${i}`);
    if (map.getSource(`${PREVIEW_SRC}${i}`)) map.removeSource(`${PREVIEW_SRC}${i}`);
  }
}

// The preview of the steps on the scenes of the order: one raster source
// per overlay (`processingPreview.ts::previewOverlays`, already cut to the AOI
// for "AOI only"). Torn down and built again whenever it is called — the caller
// calls it when the overlays change, or after a style reload.
export function syncPreview(map: MapLibreMap, overlays: readonly LayerOverlay[]): void {
  clearPreview(map);
  // Drawn from the last scene to the first, so the first ends up topmost: the
  // order of the full-resolution view (`syncFocusRaster`). The lowest layer is
  // `preview-lyr-0`; the preview is the tier of "Results" under the outlines.
  [...overlays]
    .slice(0, MAX_MOSAIC_LAYERS)
    .reverse()
    .forEach((overlay, i) => {
      if (overlay.kind !== 'raster') return;
      const srcId = `${PREVIEW_SRC}${i}`;
      const lyrId = `${PREVIEW_LYR}${i}`;
      map.addSource(srcId, {
        type: 'raster',
        tiles: [overlay.tileUrl],
        tileSize: tileSizeOf(overlay.tileUrl),
        bounds: overlay.bounds,
        minzoom: overlay.minZoom,
        maxzoom: overlay.maxZoom,
      });
      map.addLayer(
        {
          id: lyrId,
          type: 'raster',
          source: srcId,
          ...(overlay.hideFrom === undefined ? {} : { maxzoom: overlay.hideFrom }),
          paint: { 'raster-opacity': 1, 'raster-fade-duration': 0 },
        },
        rastersTop(map),
      );
      keyResults(lyrId, 'preview', i);
    });
  restackAll(map);
}

// Tells whether the tiles of the preview are on their way: from the first one the map asks for until every source of
// the preview has all of its tiles. The first tile of a mosaic over cold scenes takes seconds, and the map says so
// (`PreviewBadge`). A slow basemap does not hold it up, but the map's rest (`idle`) is what ends it where tiles were
// dropped on the way (a fast pan): that waits for the basemap too.
export function watchPreviewLoading(map: MapLibreMap, onChange: (loading: boolean) => void): void {
  const isPreview = (event: { sourceId?: string }) => event.sourceId?.startsWith(PREVIEW_SRC) === true;
  const loaded = () =>
    Array.from({ length: MAX_MOSAIC_LAYERS }, (_, i) => `${PREVIEW_SRC}${i}`).every((id) => !map.getSource(id) || map.isSourceLoaded(id));
  const settle = (event: { sourceId?: string }) => {
    if (isPreview(event)) onChange(!loaded());
  };
  map.on('sourcedataloading', (event) => {
    if (isPreview(event)) onChange(true);
  });
  map.on('sourcedata', settle);
  map.on('idle', () => onChange(false));
}

// Exported for M2-07c: the same footprint-or-bbox fallback the mosaic
// selection highlight uses, reused to draw real scene footprints once the
// coverage answer's `footprints_advised` switches the map away from density.
export function footprintsFC(items: StacItem[]): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  for (const it of items) {
    const g = footprintOf(it);
    if (g) features.push({ type: 'Feature', properties: { id: it.id }, geometry: g });
  }
  return { type: 'FeatureCollection', features };
}

// One scene in the browse view. A source that publishes a quicklook gets the
// image it publishes, keyed transparent and placed on the scene's own pixel grid;
// a source that publishes none (adr/0007 §12.7) gets tiles instead, pinned to the
// coarsest level it releases and overzoomed above it — the cheap server-rendered
// preview of `adr/0007` §6 point 5, and no new endpoint for it (M2-10, F3 a).
function addPreview(
  map: MapLibreMap,
  item: StacItem,
  i: number,
  gen: number,
  dataset: DatasetOption,
  order: ResultsOrder,
): void {
  const plan = quicklookPlan(item, dataset);
  if (!plan) return;
  if (plan.kind === 'tiles') {
    // Placed by the tile grid itself, not by four corner coordinates: a tile is
    // already in the map's own projection, so there is nothing to reproject and
    // nothing to get wrong at a scene's rotated edges (the M2-16 bug).
    if (!item.bbox) return;
    const tileUrl = buildTileUrl(buildTileTemplate(dataset.id, item.id, plan.asset), plan.render);
    const zoom = { minZoom: plan.minZoom, maxZoom: plan.maxZoom };
    const lyrId = dynamicId('tiles-lyr', i);
    keyScene(lyrId, item.id, order);
    placeRaster(map, dynamicId('tiles-src', i), lyrId, tileUrl, item.bbox, 1, zoom);
    holdBack(map, lyrId);
    drawsPicture(map, lyrId, overlaySignature({ kind: 'raster', tileUrl, bounds: item.bbox, ...zoom }));
    return;
  }
  const coords = quicklookCoords(item, preferredGeoreferencedAsset(dataset));
  if (!coords) return;
  const srcId = dynamicId('img-src', i);
  const lyrId = dynamicId('img-lyr', i);
  const nodataMax = dataset.viewable ? dataset.quicklookNodataMax : null;
  // Keyed when asked for, not when the picture arrives: its place does not depend on when that is.
  keyScene(lyrId, item.id, order);
  pendingImages++;
  loadProcessed(plan.href, nodataMax, null, (dataUrl) => {
    if (gen !== syncGen) return; // a newer sync superseded this group
    pendingImages--;
    try {
      placeImage(map, srcId, lyrId, dataUrl, coords, 1);
      holdBack(map, lyrId);
      drawsPicture(map, lyrId, overlaySignature({ kind: 'image', url: plan.href, coords, nodataMax }));
      restackAll(map);
    } catch {
      /* map/style went away while loading */
    }
    settleRetired(map);
  });
}

// For a dataset with a browsable quicklook (M3-12, O5): the quicklook stands in for the raster tiles the map
// cannot show yet — below `min_zoom`, and while they load — cropped to the AOI the same way the tiles above it
// are, instead of an empty area while the AOI is still on screen (`underlay.ts` says what it is made of). It
// stays under the tiles at every zoom, so that no zoom and no jump leaves the map without a picture. Reuses the `m-img-*` id range the browse preview uses: focus mode
// and browse mode never sync at once, and `retireDynamicMosaic` already
// clears both ranges up front regardless of which mode is running.
function addQuicklookUnderlay(map: MapLibreMap, underlay: ImageOverlay, i: number, gen: number): void {
  const srcId = dynamicId('img-src', i);
  const lyrId = dynamicId('img-lyr', i);
  // Keyed before the tiles of its scene are placed, so that it lies under them whenever it arrives.
  keyResults(lyrId, 'view');
  pendingImages++;
  loadProcessed(underlay.url, underlay.nodataMax, underlay.clipRings ?? null, (dataUrl) => {
    if (gen !== syncGen) return; // a newer sync superseded this one
    pendingImages--;
    try {
      placeImage(map, srcId, lyrId, dataUrl, underlay.coords, 1);
      // The quicklook of a pinned layer of the same scene takes its place (`drawsPicture`).
      drawsPicture(map, lyrId, overlaySignature(underlay));
      restackAll(map);
    } catch {
      /* map/style went away while loading */
    }
    settleRetired(map);
  });
}

// `clip` is the AOI to cut this scene's tiles to, or `null` for the whole
// scene ("View full selection", M3-09) — resolved by the caller from
// `cropToAoi`, never read here from anywhere else, so this stays the one
// place a raster overlay's tile URL is actually built.
function addTiles(
  map: MapLibreMap,
  info: PlannedRaster,
  i: number,
  render: AppliedRender,
  clip: GeoJSON.Geometry | null,
): void {
  const srcId = dynamicId('tiles-src', i);
  const lyrId = dynamicId('tiles-lyr', i);
  keyResults(lyrId, 'view');
  placeRaster(map, srcId, lyrId, clipTileUrl(buildTileUrl(info.tileUrl, render), clip), info.bounds, 1, info);
  drawsPicture(map, lyrId, tilesPicture(info, render, clip));
}

// What a pinned layer made of this raster would draw: its `overlaySignature`.
function tilesPicture(info: PlannedRaster, render: AppliedRender, clip: GeoJSON.Geometry | null): string {
  return overlaySignature({
    kind: 'raster',
    tileUrl: clipTileUrl(buildTileUrl(info.tileUrl, render), clip),
    bounds: info.bounds,
    minZoom: info.minZoom,
    maxZoom: info.maxZoom,
    hideFrom: info.hideFrom,
  });
}

// --- layer manager rendering (pinned overlays, independent of the active view) ---
//
// The map is brought to the list, not rebuilt from it: a source and its layer
// are added once per overlay and keep the id of the pinned layer they belong to
// (`layer-lyr-<layer id>-<n>`), so switching a layer on or off only changes its
// `visibility`, a slider only its opacity, a move only the stacking order — none
// of them reloads a tile (M4-28; before, every call removed and re-added every
// source, and the ids counted the visible overlays, not the layers).

interface WantedOverlay {
  srcId: string;
  lyrId: string;
  overlay: LayerOverlay;
  visible: boolean;
  opacity: number;
  // Everything the source is built from; a different one means a different source.
  sig: string;
  // Of a layer above "Results" in the list (NM4-59).
  above: boolean;
  // Of the layer that "Flip through layers" draws on top of all the others (NM4-65 part 9).
  flip: boolean;
}

interface PlacedOverlay {
  srcId: string;
  sig: string;
  visible: boolean;
  opacity: number;
}

const placedOverlays = new Map<string, PlacedOverlay>();
// The pinned layers' overlays, bottom to top, as of the last `syncLayers`; the
// quicklooks that arrive later read their place from here.
let wantedOverlays: WantedOverlay[] = [];

function overlaySignature(ov: LayerOverlay): string {
  return ov.kind === 'raster'
    ? JSON.stringify([ov.kind, ov.tileUrl, ov.bounds, ov.minZoom, ov.maxZoom, ov.hideFrom])
    : JSON.stringify([ov.kind, ov.url, ov.coords, ov.nodataMax, ov.clipRings]);
}

// The overlays up to the budget, bottom to top, and how many did not fit. The budget is spent from the
// top: the layers on top of the list, and of a layer its topmost overlays (the mosaic of a time step),
// are always whole; what is left out is the bottom of the stack.
function wantedOverlaysOf(layers: MapLayer[], above: number, flipId: string | null = null): { wanted: WantedOverlay[]; notDrawn: number } {
  const wanted: WantedOverlay[] = [];
  let notDrawn = 0;
  for (const [index, layer] of layers.entries()) {
    // A result whose job's results are going, or whose job is deleted: no more tiles (M4-13c-5, NM4-27).
    if (layer.result?.expired || layer.result?.deleted) continue;
    for (let n = layer.overlays.length - 1; n >= 0; n--) {
      if (wanted.length >= MAX_LAYER_OVERLAYS) {
        notDrawn++;
        continue;
      }
      const overlay = layer.overlays[n];
      wanted.push({
        srcId: `layer-src-${layer.id}-${n}`,
        lyrId: `layer-lyr-${layer.id}-${n}`,
        overlay,
        visible: layer.visible,
        opacity: layer.opacity,
        sig: overlaySignature(overlay),
        above: index < above,
        flip: layer.id === flipId,
      });
    }
  }
  return { wanted: wanted.reverse(), notDrawn };
}

export const overlayBudgetNote = (notDrawn: number): string | null =>
  notDrawn > 0
    ? `The layers hold more images than the map draws (${MAX_LAYER_OVERLAYS}); ${notDrawn} at the bottom of the list ${notDrawn === 1 ? 'is' : 'are'} left out.`
    : null;

// The view's raster `lyrId` draws the picture `sig`. A layer that is switched on and draws the same picture
// takes its place in the stack, so the view's copy stays out of sight (UI-01a): it would lie over every layer
// and a move in the list would change nothing. Switched off or gone, the layer draws nothing, and the copy
// is back. A copy out of sight loads no tiles.
function drawsPicture(map: MapLibreMap, lyrId: string, sig: string): void {
  drawnNew = true;
  viewPictures.set(lyrId, sig);
  settleViewTwin(map, lyrId);
}

function settleViewTwin(map: MapLibreMap, lyrId: string): void {
  const sig = viewPictures.get(lyrId);
  if (sig === undefined || !map.getLayer(lyrId)) return;
  const twin = wantedOverlays.some((w) => w.sig === sig && w.visible && isPlaced(map, w));
  if (twin === viewTwinsHidden.has(lyrId)) return;
  setVisibility(map, lyrId, !twin);
  if (twin) viewTwinsHidden.add(lyrId);
  else viewTwinsHidden.delete(lyrId);
}

function settleViewTwins(map: MapLibreMap): void {
  for (const lyrId of viewPictures.keys()) settleViewTwin(map, lyrId);
}

function isPlaced(map: MapLibreMap, w: WantedOverlay): boolean {
  return !!map.getLayer(w.lyrId) && placedOverlays.get(w.lyrId)?.sig === w.sig;
}

function removePlaced(map: MapLibreMap, lyrId: string, placed: PlacedOverlay): void {
  if (map.getLayer(lyrId)) map.removeLayer(lyrId);
  if (map.getSource(placed.srcId)) map.removeSource(placed.srcId);
  placedOverlays.delete(lyrId);
}

// A new layer goes on top; `restackAll` gives it its place in the list.
function placeWanted(map: MapLibreMap, w: WantedOverlay, dataUrl?: string): void {
  if (w.overlay.kind === 'raster') {
    placeRaster(map, w.srcId, w.lyrId, w.overlay.tileUrl, w.overlay.bounds, w.opacity, w.overlay);
  } else if (dataUrl !== undefined) {
    placeImage(map, w.srcId, w.lyrId, dataUrl, w.overlay.coords, w.opacity);
  } else {
    return;
  }
  if (!w.visible) setVisibility(map, w.lyrId, false);
  placedOverlays.set(w.lyrId, { srcId: w.srcId, sig: w.sig, visible: w.visible, opacity: w.opacity });
}

// Returns how many overlays the budget left out (`overlayBudgetNote`). `resultsAt`: how many layers of the list lie
// above "Results" (`store.ts`); none where it is left out, as before NM4-59. `flipId`: the layer "Flip through layers" draws
// over all the others (NM4-65 part 9); none, the order of the list.
export function syncLayers(map: MapLibreMap, layers: MapLayer[], resultsAt = 0, flipId: string | null = null): number {
  const { wanted, notDrawn } = wantedOverlaysOf(layers, resultsAt, flipId);
  wantedOverlays = wanted;
  const known = new Map(wanted.map((w) => [w.lyrId, w]));
  // Gone from the list, or built from something else now: out.
  for (const [lyrId, placed] of [...placedOverlays]) {
    if (known.get(lyrId)?.sig === placed.sig) continue;
    removePlaced(map, lyrId, placed);
  }
  for (const w of wanted) {
    if (isPlaced(map, w)) continue;
    if (w.overlay.kind === 'raster') {
      placeWanted(map, w);
    } else if (w.visible) {
      // A hidden quicklook is not even fetched; it is the next sync that finds it missing.
      const ov = w.overlay;
      loadProcessed(ov.url, ov.nodataMax, ov.clipRings ?? null, (dataUrl) => {
        const now = wantedOverlays.find((x) => x.lyrId === w.lyrId && x.sig === w.sig);
        if (!now) return; // gone from the list, or a newer one took its place
        try {
          if (!isPlaced(map, now)) placeWanted(map, now, dataUrl);
          restackAll(map);
          settleViewTwins(map);
        } catch {
          /* map/style went away while loading */
        }
      });
    }
  }
  for (const w of wanted) {
    const placed = placedOverlays.get(w.lyrId);
    if (!placed || !map.getLayer(w.lyrId)) continue;
    if (placed.visible !== w.visible) setVisibility(map, w.lyrId, w.visible);
    if (placed.opacity !== w.opacity) map.setPaintProperty(w.lyrId, 'raster-opacity', w.opacity);
    placed.visible = w.visible;
    placed.opacity = w.opacity;
  }
  restackAll(map);
  settleViewTwins(map);
  return notDrawn;
}

export interface MosaicState {
  items: StacItem[]; // items of the active time step
  // The ids of the scenes of the group that is open in the list, which lies on top of the other results (`mapResults.ts::openIdsOf`,
  // Otto, 30.10.2026). Left out, every scene of the open dataset counts as open.
  openIds?: ReadonlySet<string>;
  // The scenes outlined as ticked, where that is not the same list as `items` (`mapResults.ts`).
  highlight?: StacItem[];
  // The dataset those items belong to: the browse preview reads its released
  // levels and its standard visualisation from here rather than from a branch
  // on the dataset id (M2-10).
  dataset: DatasetOption | null;
  // Every dataset of the search, for the ticked scenes of the ones the list does not show (`datasetOfItem`).
  datasets?: readonly DatasetOption[];
  downloaded: Record<string, DownloadedInfo>;
  selectedIds: string[];
  render: AppliedRender;
  focusMode: boolean; // full-res tiles are only drawn while focused on a download
  showDownloaded: boolean; // when false, downloaded full-res overlays are hidden
  // The AOI to clip the full-resolution tiles to, and whether the current
  // view actually is cropped to it (M3-09: "Crop to AOI" vs. "View full
  // selection") — both optional so every existing call site that never draws
  // a cropped view (the browse preview, most tests) can leave them out.
  aoi?: GeoJSON.Geometry | null;
  cropToAoi?: boolean;
  // The full grouping of the current results (M3-09 §10) — needed only to
  // resolve which group each shown scene belongs to when cropped, where the
  // selection outline becomes one ring per group instead of one per scene
  // (`syncHighlight`). Optional like `aoi`/`cropToAoi` above, for the same
  // reason: most call sites never draw a cropped view.
  groups?: TimeStepGroup[];
  // What the mosaics of the passes in `downloaded` look like (`mosaic.ts`). Left out, every scene
  // is drawn by itself, as before M4-17.
  mosaics?: Mosaics;
  // A pinned layer draws the view's tiles (`viewLayer.ts`): at its place in the
  // list, with its eye. The view then adds only what the layer does not have.
  tilesInLayer?: boolean;
}

// Full-resolution raster tiles (M2-07b). Tearing the existing layers down and
// re-adding them is visible as the image disappearing and reappearing, so
// this must only run when what should be drawn actually changes — which
// scenes, the applied render, or the visibility toggle — never for a plain
// selection toggle, which is `syncSelectionHighlight`'s job instead. Before
// V-3 this and the highlight were one function always called together, so a
// click that only (de)selected a full-resolution image still tore the tiles
// down and reloaded them for no visual gain — the actual cause behind "a
// click on a full-resolution image reloads it".
export function syncFocusRaster(
  map: MapLibreMap,
  s: Pick<
    MosaicState,
    'downloaded' | 'render' | 'showDownloaded' | 'aoi' | 'cropToAoi' | 'items' | 'dataset' | 'tilesInLayer' | 'groups' | 'mosaics'
  >,
): void {
  // A quicklook that arrives after this sync belongs to the one before it.
  const gen = ++syncGen;
  retireDynamicMosaic(map);
  if (!s.showDownloaded) return dropRetired(map);
  const clip = s.cropToAoi ? (s.aoi ?? null) : null;
  const dataset = s.dataset;
  // Each pass is a mosaic, scene by scene, or not yet known (`mosaic.ts`). The scenes drawn one by
  // one are capped, first come first served, as they always were.
  let single = 0;
  const drawn = passesOf(Object.entries(s.downloaded), s.groups).map((entries) => {
    const view = viewOfPass(dataset?.id ?? null, entries, s.mosaics);
    if (view.kind === 'scenes') {
      const own = entries.slice(0, Math.max(0, MAX_MOSAIC_LAYERS - single));
      single += own.length;
      return { entries: own, view };
    }
    return { entries, view };
  });
  // Drawn in reverse selection order, so the *first*-selected scene ends up
  // topmost — the same "first valid pixel wins" rule the download's mosaic
  // uses (rio_tiler's `FirstMethod`, `adr/0006` §3.5), so overlapping scenes
  // agree between the view and the downloaded file. This used to draw in
  // selection order, putting the *last*-selected scene on top instead
  // (M3-09 finding). A mosaic applies that rule on the server.
  // Short of ids, a mosaic gives up the single scenes under it before any mosaic is lost.
  const wanted = drawn.reduce(
    (sum, { entries, view }) => sum + (view.kind === 'mosaic' ? view.rasters.length : view.kind === 'scenes' ? entries.length : 0),
    0,
  );
  let tiles = 0;
  let underlays = 0;
  // An index in the look (NM4-14b) is computed by the tile route with an operator, with no quicklook under it: that would
  // be the true-colour picture, which an index is not. A raster the route cannot take is not drawn; the view says why.
  const index = dataset ? viewIndexOf(s.render, dataset.collection) : null;
  const place = (raster: PlannedRaster, pass: SceneEntry[]) => {
    if (tiles >= MAX_DYNAMIC_LAYERS) return;
    const drawing = index && dataset ? indexRasterOf(raster, pass, dataset.id, index) : raster;
    if (typeof drawing !== 'string') addTiles(map, drawing, tiles++, s.render, clip);
  };
  for (const { entries, view } of stackLikeView(drawn)) {
    if (view.kind === 'pending' && !s.tilesInLayer) continue;
    stackLikeView(entries).forEach(([itemId, info]) => {
      // O5: the underlay is keyed first, so `addTiles` right after it ends up
      // on top (of equal tier and rank, the later key lies higher), whenever
      // the underlay's image arrives.
      const item = underlays < MAX_DYNAMIC_LAYERS ? s.items.find((it) => it.id === itemId) : undefined;
      const underlay = item && underlayOf(item, dataset, clip);
      if (underlay && !index) addQuicklookUnderlay(map, underlay, underlays++, gen);
      if (view.kind === 'scenes' && !s.tilesInLayer) place(info, entries);
    });
    if (view.kind === 'mosaic' && !s.tilesInLayer) {
      (wanted > MAX_DYNAMIC_LAYERS ? view.rasters.slice(-1) : view.rasters).forEach((raster) => place(raster, entries));
    }
  }
  restackAll(map);
  settleRetired(map);
}

// Browse-mode preview overlays: one per scene of `items` (the active time
// step, plus any scene pinned onto the map by a cross-group selection — see
// `itemsForMap`, V-3 finding 2). Without a dataset there is nothing to
// preview *from* — the registry decides both the image and the level.
// The dataset of a scene: its own where the search has several (the ticks stay over a change of the dataset), else the one
// the list shows.
const datasetOfItem = (item: StacItem, s: { dataset: DatasetOption | null; datasets?: readonly DatasetOption[] }): DatasetOption | null =>
  s.datasets?.find((d) => d.id === item.collection) ?? s.dataset;

type PreviewState = Pick<MosaicState, 'items' | 'dataset' | 'datasets' | 'openIds'> & {
  selectedIds?: readonly string[];
  // Draw the step hidden over the picture on the map and show it once it has loaded (NM4-18).
  hold?: Hold;
};

// The order of the scenes of the results on the map: the ticks, and which scenes are of the dataset the list shows (a scene
// that names no dataset is).
const resultsOrderOf = (s: PreviewState, items: readonly StacItem[]): ResultsOrder => {
  // The scenes of the group that is open (the step that is played), where the caller says which; else all of the dataset.
  const open = new Map(items.map((it) => [it.id, s.openIds ? s.openIds.has(it.id) : !it.collection || it.collection === s.dataset?.id]));
  return { ticks: s.selectedIds ?? [], isOpen: (id) => open.get(id) ?? true };
};

export function syncBrowseMosaic(map: MapLibreMap, s: PreviewState): void {
  const gen = ++syncGen;
  retireDynamicMosaic(map, s.hold !== undefined);
  holding = s.hold ?? null;
  const items = s.items.slice(0, MAX_MOSAIC_LAYERS);
  const { dataset } = s;
  // Nothing to draw (no dataset, or the results are off the map, UI-01g): the picture before it has nothing to
  // wait for and goes at once.
  if (!dataset || items.length === 0) return s.hold ? finishWhenDue(map, gen) : dropRetired(map);
  const order = resultsOrderOf(s, items);
  items.forEach((it, i) => {
    const own = datasetOfItem(it, s);
    if (own) addPreview(map, it, i, gen, own, order);
  });
  restackAll(map);
  // A held step none of whose scenes has a preview has nothing to arrive.
  if (s.hold && !drawnNew && pendingImages === 0) return finishWhenDue(map, gen);
  settleRetired(map);
}

// The quicklooks of the search results while a full-resolution view is open, with the eye of "Results" on: over the
// view, which is the bottom tier of "Results" (NM4-59, Otto, 30.10.2026; replaces the view over them of 27.10.2026). Their
// own id range (`res-…`), apart from the view's two banks, so that neither sync takes the other's layers away.
const RESULTS_KINDS = ['img-lyr', 'img-src', 'tiles-lyr', 'tiles-src'] as const;
let resultsGen = 0;

function removeResultsOverlay(map: MapLibreMap): void {
  for (let i = 0; i < MAX_MOSAIC_LAYERS; i++) {
    for (const lyr of [`res-img-lyr-${i}`, `res-tiles-lyr-${i}`]) {
      resultsKeys.delete(lyr);
      if (map.getLayer(lyr)) map.removeLayer(lyr);
    }
    for (const src of [`res-img-src-${i}`, `res-tiles-src-${i}`]) if (map.getSource(src)) map.removeSource(src);
  }
}

export function syncResultsOverlay(map: MapLibreMap, s: PreviewState): void {
  const gen = ++resultsGen;
  removeResultsOverlay(map);
  const { dataset } = s;
  if (!dataset) return;
  const shown = s.items.slice(0, MAX_MOSAIC_LAYERS);
  const order = resultsOrderOf(s, shown);
  shown.forEach((item, i) => {
    const own = datasetOfItem(item, s);
    const plan = own && quicklookPlan(item, own);
    if (!own || !plan) return;
    // Over the view, in the tiers of browsing (NM4-59): the open group over the ticked scenes of the other groups.
    const [lyr, src] = [`res-${RESULTS_KINDS[plan.kind === 'tiles' ? 2 : 0]}-${i}`, `res-${RESULTS_KINDS[plan.kind === 'tiles' ? 3 : 1]}-${i}`];
    if (plan.kind === 'tiles') {
      if (!item.bbox) return;
      const tileUrl = buildTileUrl(buildTileTemplate(own.id, item.id, plan.asset), plan.render);
      keyScene(lyr, item.id, order);
      placeRaster(map, src, lyr, tileUrl, item.bbox, 1, { minZoom: plan.minZoom, maxZoom: plan.maxZoom });
      return;
    }
    const coords = quicklookCoords(item, preferredGeoreferencedAsset(own));
    if (!coords) return;
    const nodataMax = own.viewable ? own.quicklookNodataMax : null;
    keyScene(lyr, item.id, order);
    loadProcessed(plan.href, nodataMax, null, (dataUrl) => {
      if (gen !== resultsGen) return; // a newer sync superseded this one
      try {
        placeImage(map, src, lyr, dataUrl, coords, 1);
        restackAll(map);
      } catch {
        /* map/style went away while loading */
      }
    });
  });
  restackAll(map);
}

// The yellow outline around selected scenes, in either mode. A plain GeoJSON
// source update with no layer churn, so it is safe and cheap to run on every
// selection change without going through `syncFocusRaster`/`syncBrowseMosaic`.
export function syncSelectionHighlight(map: MapLibreMap, items: StacItem[], selectedIds: string[]): void {
  const limited = items.slice(0, MAX_MOSAIC_LAYERS);
  setData(map, SEL_SRC, footprintsFC(limited.filter((it) => selectedIds.includes(it.id))));
}

// M3-09 §10: in the cropped focus view ("Crop & merge to AOI"), the same
// yellow outline source shows one ring per group instead of one per scene —
// `groupOutlineFeatures` (pure geometry, `groupOutline.ts`) does the actual
// union/intersection; this just publishes its result.
function syncGroupOutlines(
  map: MapLibreMap,
  groups: TimeStepGroup[],
  visibleIds: ReadonlySet<string>,
  aoi: GeoJSON.Geometry,
): void {
  setData(map, SEL_SRC, { type: 'FeatureCollection', features: groupOutlineFeatures(groups, visibleIds, aoi) });
}

// Picks between the two: per-group outlines only in a cropped focus view (the
// one case with something to merge), the plain per-scene highlight
// otherwise — browsing, "View full selection", or without a usable AOI.
export function syncHighlight(
  map: MapLibreMap,
  s: Pick<MosaicState, 'items' | 'selectedIds' | 'focusMode' | 'cropToAoi' | 'aoi' | 'downloaded' | 'groups'>,
): void {
  if (s.focusMode && s.cropToAoi && s.aoi && s.groups) {
    syncGroupOutlines(map, s.groups, new Set(Object.keys(s.downloaded)), s.aoi);
    return;
  }
  syncSelectionHighlight(map, s.items, s.selectedIds);
}

/** Reconcile everything in one call — used for a full rebuild (initial load,
 *  after a style reload wipes every custom source/layer). Everyday updates
 *  go through the finer-grained functions above instead, so a selection
 *  toggle alone never forces a raster reload (V-3, finding 1). */
export function syncMosaic(map: MapLibreMap, s: MosaicState): void {
  if (s.focusMode) {
    syncFocusRaster(map, s);
  } else {
    syncBrowseMosaic(map, s);
  }
  syncHighlight(map, s.highlight ? { ...s, items: s.highlight } : s);
}
