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
import { underlayOf } from './underlay';
import type { ImageOverlay } from './underlay';
import { passesOf, stackLikeView, viewOfPass } from './mosaic';
import type { Mosaics, PlannedRaster } from './mosaic';
import type { AppliedRender, DownloadedInfo, StacItem, TimeStepGroup } from './types';

const AOI_SRC = 'aoi-src';
const SEL_SRC = 'mosaicsel-src'; // highlighted (selected-for-download) footprints
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
// Where the layer manager's rasters end: a hidden background layer right under
// the AOI. Every pinned layer is stacked directly under it, so the active view
// (browse mosaic, full-resolution tiles: `beforeAoi`) is always above them.
const LAYERS_TOP = 'layers-top';
// Right above `LAYERS_TOP`, under the view: the quicklooks of the search results over a view go just under this marker, so
// that the full-resolution view (placed `beforeAoi`) lies over them, and the outlines of the results stay over both
// (Otto, 27.10.2026).
const RESULTS_TOP = 'results-top';
// Right under the AOI, over everything else: a search result that is ticked has its quicklook over the view, the other
// quicklooks and the pinned layers, whichever of them was drawn first (Otto, 27.10.2026, "immer der oberste Layer").
// Every other raster of the app goes under this marker (`aboveAll`), the ticked quicklooks over it (`topOfAll`).
const TICKED_TOP = 'ticked-top';
// Right over the ticked quicklooks and under the area of interest: the overlays of the "Basemap" menu (names,
// graticule) lie between this marker and the AOI, so that they stay over every picture (UI-02b, `mapStyles.ts`).
const OVERLAYS_BASE = 'overlays-base';
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
  before: string | undefined = beforeAoi(map),
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
    before,
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
  before: string | undefined = beforeAoi(map),
): void {
  if (map.getSource(srcId)) return;
  map.addSource(srcId, {
    type: 'raster',
    tiles: [tileUrl],
    tileSize: 256,
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
    before,
  );
}

// Full tile URL from a template: the template already carries the mandatory
// `asset` (api.ts `buildTileTemplate`, adr/0001 Z4); this adds the
// stretch/colormap/band params — committed via "Apply" for a full-resolution
// overlay, taken straight from the registry for a browse preview. Also used by
// the store to snapshot a layer.
export function buildTileUrl(template: string, render: AppliedRender): string {
  const params = new URLSearchParams();
  if (render.bidx) params.set('bidx', render.bidx);
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
    map.addLayer({ id: LAYERS_TOP, type: 'background', layout: { visibility: 'none' } });
    map.addLayer({ id: RESULTS_TOP, type: 'background', layout: { visibility: 'none' } });
    map.addLayer({ id: TICKED_TOP, type: 'background', layout: { visibility: 'none' } });
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
    map.addLayer({
      id: 'mosaicsel-line',
      type: 'line',
      source: SEL_SRC,
      paint: { 'line-color': '#ffd166', 'line-width': 3, 'line-blur': 1, 'line-opacity': 0.95 },
    });
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
    }
    for (const src of [`${which}-img-src-${i}`, `${which}-tiles-src-${i}`]) {
      if (map.getSource(src)) map.removeSource(src);
    }
  }
}

function finishRetired(map: MapLibreMap): void {
  if (!retiring) return;
  clearTimeout(retiring.timer);
  removeDynamic(map, retiring.bank);
  retiring = null;
}

// Start of a sync of the view: what the view drew is taken away at once where the map cannot say when the new picture is
// there, else it stays, under the new one, until `settleRetired`.
function retireDynamicMosaic(map: MapLibreMap): void {
  pendingImages = 0;
  // A style reload (a theme switch) wipes the layers a picture was waiting to be taken away from.
  if (retiring && (retiring.map !== map || !hasDynamic(map, retiring.bank))) {
    clearTimeout(retiring.timer);
    retiring = null;
  }
  // The last sync drew nothing yet (a mosaic still on its way): the picture before it waits on for this one.
  if (retiring && !drawnNew) return;
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
  retiring = { id, map, bank, timer: setTimeout(() => retiring?.id === id && finishRetired(map), RETIRE_AFTER_MS) };
  bank = bank === 'm' ? 'n' : 'm';
}

// The new picture is on the map once the quicklooks it waits for have arrived and the map has no tile left to load.
function settleRetired(map: MapLibreMap): void {
  if (!retiring || !drawnNew || pendingImages > 0) return;
  const { id } = retiring;
  map.once('idle', () => {
    if (retiring?.id === id && pendingImages === 0) finishRetired(map);
  });
}

// A sync that draws nothing new has nothing to wait for.
function dropRetired(map: MapLibreMap): void {
  finishRetired(map);
}

// Where the quicklooks of the results go while a view is open: under the marker above the layer manager's stack.
const underTheView = (map: MapLibreMap): string | undefined => (map.getLayer(RESULTS_TOP) ? RESULTS_TOP : beforeAoi(map));

// What a new raster of the app goes under: the marker of the ticked quicklooks, or the AOI where the marker is not
// there (a map without it, as in the tests of the older functions).
const aboveAll = (map: MapLibreMap): string | undefined =>
  map.getLayer(TICKED_TOP) ? TICKED_TOP : map.getLayer('aoi-fill') ? 'aoi-fill' : undefined;

// Where the quicklook of a ticked search result goes: over the marker, under the overlays and the AOI.
const topOfAll = (map: MapLibreMap): string | undefined =>
  map.getLayer(OVERLAYS_BASE) ? OVERLAYS_BASE : map.getLayer('aoi-fill') ? 'aoi-fill' : undefined;

// Where a new raster goes: below the preview, which stays on top of whatever
// loads after it (a quicklook is placed when its image has arrived).
const beforeAoi = (map: MapLibreMap): string | undefined =>
  map.getLayer(`${PREVIEW_LYR}0`) ? `${PREVIEW_LYR}0` : aboveAll(map);

function clearPreview(map: MapLibreMap): void {
  for (let i = 0; i < MAX_MOSAIC_LAYERS; i++) {
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
  // `preview-lyr-0`, which `beforeAoi` keeps later rasters under.
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
        tileSize: 256,
        bounds: overlay.bounds,
        minzoom: overlay.minZoom,
        maxzoom: overlay.maxZoom,
      });
      map.addLayer(
        { id: lyrId, type: 'raster', source: srcId, paint: { 'raster-opacity': 1, 'raster-fade-duration': 0 } },
        aboveAll(map),
      );
    });
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
  ticked: boolean,
): void {
  const plan = quicklookPlan(item, dataset);
  if (!plan) return;
  // A ticked scene is the top layer; the others go where later rasters go (`undefined`: the default place).
  const before = (): string | undefined => (ticked ? topOfAll(map) : undefined);
  if (plan.kind === 'tiles') {
    // Placed by the tile grid itself, not by four corner coordinates: a tile is
    // already in the map's own projection, so there is nothing to reproject and
    // nothing to get wrong at a scene's rotated edges (the M2-16 bug).
    if (!item.bbox) return;
    const tileUrl = buildTileUrl(buildTileTemplate(dataset.id, item.id, plan.asset), plan.render);
    const zoom = { minZoom: plan.zoom, maxZoom: plan.zoom };
    const lyrId = dynamicId('tiles-lyr', i);
    placeRaster(map, dynamicId('tiles-src', i), lyrId, tileUrl, item.bbox, 1, zoom, before());
    drawsPicture(map, lyrId, overlaySignature({ kind: 'raster', tileUrl, bounds: item.bbox, ...zoom }));
    return;
  }
  const coords = quicklookCoords(item, preferredGeoreferencedAsset(dataset));
  if (!coords) return;
  const srcId = dynamicId('img-src', i);
  const lyrId = dynamicId('img-lyr', i);
  const nodataMax = dataset.viewable ? dataset.quicklookNodataMax : null;
  pendingImages++;
  loadProcessed(plan.href, nodataMax, null, (dataUrl) => {
    if (gen !== syncGen) return; // a newer sync superseded this group
    pendingImages--;
    try {
      placeImage(map, srcId, lyrId, dataUrl, coords, 1, before());
      drawsPicture(map, lyrId, overlaySignature({ kind: 'image', url: plan.href, coords, nodataMax }));
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
  pendingImages++;
  loadProcessed(underlay.url, underlay.nodataMax, underlay.clipRings ?? null, (dataUrl) => {
    if (gen !== syncGen) return; // a newer sync superseded this one
    pendingImages--;
    try {
      placeImage(map, srcId, lyrId, dataUrl, underlay.coords, 1);
      // The quicklook of a pinned layer of the same scene takes its place (`drawsPicture`).
      drawsPicture(map, lyrId, overlaySignature(underlay));
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
// The order the map holds them in, to move layers only where the list changed.
let stackedOrder: string[] = [];

function overlaySignature(ov: LayerOverlay): string {
  return ov.kind === 'raster'
    ? JSON.stringify([ov.kind, ov.tileUrl, ov.bounds, ov.minZoom, ov.maxZoom, ov.hideFrom])
    : JSON.stringify([ov.kind, ov.url, ov.coords, ov.nodataMax, ov.clipRings]);
}

// The overlays up to the budget, bottom to top, and how many did not fit. The budget is spent from the
// top: the layers on top of the list, and of a layer its topmost overlays (the mosaic of a time step),
// are always whole; what is left out is the bottom of the stack.
function wantedOverlaysOf(layers: MapLayer[]): { wanted: WantedOverlay[]; notDrawn: number } {
  const wanted: WantedOverlay[] = [];
  let notDrawn = 0;
  for (const layer of layers) {
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

// The layer right above `index` that is on the map, or the top of the manager's
// stack: what a new layer goes under.
function layerAbove(map: MapLibreMap, wanted: readonly WantedOverlay[], index: number): string | undefined {
  for (let j = index + 1; j < wanted.length; j++) {
    if (isPlaced(map, wanted[j])) return wanted[j].lyrId;
  }
  return map.getLayer(LAYERS_TOP) ? LAYERS_TOP : aboveAll(map);
}

function placeWanted(map: MapLibreMap, wanted: readonly WantedOverlay[], index: number, dataUrl?: string): void {
  const w = wanted[index];
  const before = layerAbove(map, wanted, index);
  if (w.overlay.kind === 'raster') {
    placeRaster(map, w.srcId, w.lyrId, w.overlay.tileUrl, w.overlay.bounds, w.opacity, w.overlay, before);
  } else if (dataUrl !== undefined) {
    placeImage(map, w.srcId, w.lyrId, dataUrl, w.overlay.coords, w.opacity, before);
  } else {
    return;
  }
  if (!w.visible) setVisibility(map, w.lyrId, false);
  placedOverlays.set(w.lyrId, { srcId: w.srcId, sig: w.sig, visible: w.visible, opacity: w.opacity });
}

function placedOrder(map: MapLibreMap, wanted: readonly WantedOverlay[]): string[] {
  return wanted.filter((w) => isPlaced(map, w)).map((w) => w.lyrId);
}

// After a move in the list: lay the layers out again in the list's order, each
// right under the one above it. Nothing is reloaded by that.
function restack(map: MapLibreMap, wanted: readonly WantedOverlay[]): void {
  const order = placedOrder(map, wanted);
  const kept = new Set(order);
  const before = stackedOrder.filter((id) => kept.has(id));
  const known = new Set(before);
  const now = order.filter((id) => known.has(id));
  if (before.length !== now.length || before.some((id, i) => id !== now[i])) {
    let above = map.getLayer(LAYERS_TOP) ? LAYERS_TOP : aboveAll(map);
    for (let i = order.length - 1; i >= 0; i--) {
      map.moveLayer(order[i], above);
      above = order[i];
    }
  }
  stackedOrder = order;
}

// Returns how many overlays the budget left out (`overlayBudgetNote`).
export function syncLayers(map: MapLibreMap, layers: MapLayer[]): number {
  const { wanted, notDrawn } = wantedOverlaysOf(layers);
  wantedOverlays = wanted;
  const known = new Map(wanted.map((w) => [w.lyrId, w]));
  // Gone from the list, or built from something else now: out.
  for (const [lyrId, placed] of [...placedOverlays]) {
    if (known.get(lyrId)?.sig === placed.sig) continue;
    removePlaced(map, lyrId, placed);
  }
  // Top to bottom, so every new layer finds the one above it on the map already.
  for (let i = wanted.length - 1; i >= 0; i--) {
    const w = wanted[i];
    if (isPlaced(map, w)) continue;
    if (w.overlay.kind === 'raster') {
      placeWanted(map, wanted, i);
    } else if (w.visible) {
      // A hidden quicklook is not even fetched; it is the next sync that finds it missing.
      const ov = w.overlay;
      loadProcessed(ov.url, ov.nodataMax, ov.clipRings ?? null, (dataUrl) => {
        const index = wantedOverlays.findIndex((x) => x.lyrId === w.lyrId && x.sig === w.sig);
        if (index < 0) return; // gone from the list, or a newer one took its place
        try {
          if (!isPlaced(map, wantedOverlays[index])) placeWanted(map, wantedOverlays, index, dataUrl);
          restack(map, wantedOverlays);
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
  restack(map, wanted);
  settleViewTwins(map);
  return notDrawn;
}

export interface MosaicState {
  items: StacItem[]; // items of the active time step
  // The scenes outlined as ticked, where that is not the same list as `items` (`mapResults.ts`).
  highlight?: StacItem[];
  // The dataset those items belong to: the browse preview reads its released
  // levels and its standard visualisation from here rather than from a branch
  // on the dataset id (M2-10).
  dataset: DatasetOption | null;
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
  const place = (raster: PlannedRaster) => {
    if (tiles < MAX_DYNAMIC_LAYERS) addTiles(map, raster, tiles++, s.render, clip);
  };
  for (const { entries, view } of stackLikeView(drawn)) {
    if (view.kind === 'pending' && !s.tilesInLayer) continue;
    stackLikeView(entries).forEach(([itemId, info]) => {
      // O5: the underlay goes down first, so `addTiles` right after it ends up
      // on top (`beforeAoi` puts each newly added layer just below the AOI
      // layer, so whichever is added later of the two is the more on top).
      const item = underlays < MAX_DYNAMIC_LAYERS ? s.items.find((it) => it.id === itemId) : undefined;
      const underlay = item && underlayOf(item, dataset, clip);
      if (underlay) addQuicklookUnderlay(map, underlay, underlays++, gen);
      if (view.kind === 'scenes' && !s.tilesInLayer) place(info);
    });
    if (view.kind === 'mosaic' && !s.tilesInLayer) {
      (wanted > MAX_DYNAMIC_LAYERS ? view.rasters.slice(-1) : view.rasters).forEach(place);
    }
  }
  settleRetired(map);
}

// Browse-mode preview overlays: one per scene of `items` (the active time
// step, plus any scene pinned onto the map by a cross-group selection — see
// `itemsForMap`, V-3 finding 2). Without a dataset there is nothing to
// preview *from* — the registry decides both the image and the level.
export function syncBrowseMosaic(map: MapLibreMap, s: Pick<MosaicState, 'items' | 'dataset'> & { selectedIds?: readonly string[] }): void {
  const gen = ++syncGen;
  retireDynamicMosaic(map);
  const items = s.items.slice(0, MAX_MOSAIC_LAYERS);
  const { dataset } = s;
  // Nothing to draw (no dataset, or the results are off the map, UI-01g): the picture before it has nothing to
  // wait for and goes at once.
  if (!dataset || items.length === 0) return dropRetired(map);
  items.forEach((it, i) => addPreview(map, it, i, gen, dataset, s.selectedIds?.includes(it.id) ?? false));
  settleRetired(map);
}

// The quicklooks of the search results under the full-resolution view (Otto, 26.10.2026, turned over on 27.10.2026):
// "Show results" in the results panel draws them while a view is open, and the view lies over them. Their own id range
// (`res-…`), apart from the view's two banks, so that neither sync takes the other's layers away; placed under
// `RESULTS_TOP`, which is under every layer the view adds, whichever sync came first.
const RESULTS_KINDS = ['img-lyr', 'img-src', 'tiles-lyr', 'tiles-src'] as const;
let resultsGen = 0;

function removeResultsOverlay(map: MapLibreMap): void {
  for (let i = 0; i < MAX_MOSAIC_LAYERS; i++) {
    for (const lyr of [`res-img-lyr-${i}`, `res-tiles-lyr-${i}`]) if (map.getLayer(lyr)) map.removeLayer(lyr);
    for (const src of [`res-img-src-${i}`, `res-tiles-src-${i}`]) if (map.getSource(src)) map.removeSource(src);
  }
}

export function syncResultsOverlay(map: MapLibreMap, s: Pick<MosaicState, 'items' | 'dataset'> & { selectedIds?: readonly string[] }): void {
  const gen = ++resultsGen;
  removeResultsOverlay(map);
  const { dataset } = s;
  if (!dataset) return;
  s.items.slice(0, MAX_MOSAIC_LAYERS).forEach((item, i) => {
    const plan = quicklookPlan(item, dataset);
    if (!plan) return;
    // A ticked scene lies over the view as well; the others under the view.
    const place = (): string | undefined => (s.selectedIds?.includes(item.id) ? topOfAll(map) : underTheView(map));
    const [lyr, src] = [`res-${RESULTS_KINDS[plan.kind === 'tiles' ? 2 : 0]}-${i}`, `res-${RESULTS_KINDS[plan.kind === 'tiles' ? 3 : 1]}-${i}`];
    if (plan.kind === 'tiles') {
      if (!item.bbox) return;
      const tileUrl = buildTileUrl(buildTileTemplate(dataset.id, item.id, plan.asset), plan.render);
      placeRaster(map, src, lyr, tileUrl, item.bbox, 1, { minZoom: plan.zoom, maxZoom: plan.zoom }, place());
      return;
    }
    const coords = quicklookCoords(item, preferredGeoreferencedAsset(dataset));
    if (!coords) return;
    const nodataMax = dataset.viewable ? dataset.quicklookNodataMax : null;
    loadProcessed(plan.href, nodataMax, null, (dataUrl) => {
      if (gen !== resultsGen) return; // a newer sync superseded this one
      try {
        placeImage(map, src, lyr, dataUrl, coords, 1, place());
      } catch {
        /* map/style went away while loading */
      }
    });
  });
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
