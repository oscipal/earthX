// Imperative helpers that keep the map's custom sources/layers in sync with app
// state. All are idempotent so they can be safely re-run after map.setStyle()
// (which wipes every custom source/layer).

import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl';

import { clipTileUrl } from './aoiClip';
import { buildTileTemplate } from './api';
import type { CoverageCell } from './api';
import { cellsToFeatureCollection, coverageFillColorExpression } from './coverage';
import { quicklookPlan } from './datasets';
import type { DatasetOption } from './datasets';
import { asFeatureCollection, footprintOf, quicklookCoords } from './geoUtils';
import type { Coords4 } from './geoUtils';
import { groupOutlineFeatures } from './groupOutline';
import type { MapLayer } from './layers';
import type { AppliedRender, DownloadedInfo, StacItem, TimeStepGroup } from './types';

const AOI_SRC = 'aoi-src';
const SEL_SRC = 'mosaicsel-src'; // highlighted (selected-for-download) footprints
const COVERAGE_SRC = 'coverage-src'; // the density grid (M2-07c)
const COVERAGE_FOOTPRINTS_SRC = 'coverage-footprints-src'; // real footprints once footprints_advised

const EMPTY_FC: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] };
const MAX_MOSAIC_LAYERS = 40;

// Dynamic per-frame overlay ids created by syncMosaic (variable count).
let dynLayerIds: string[] = [];
let dynSourceIds: string[] = [];

// Bumped on each syncMosaic so slow async quicklook processing can tell whether
// it has been superseded before it touches the map.
let syncGen = 0;
// Bumped on each syncLayers (the layer manager) for the same reason.
let layerGen = 0;
const MAX_LAYER_OVERLAYS = 200;
// Cache of processed (black-nodata → transparent) quicklook data URLs, keyed by
// the (same-origin) image URL so the mosaic and the layer renderer share it.
const qlDataUrlCache = new Map<string, string>();

// Near-black luminance threshold below which a pixel is treated as nodata and
// made fully transparent.
const NODATA_THRESHOLD = 16;

// Redraw a quicklook JPEG into a canvas, turning its near-black nodata padding
// transparent so only the acquisition swath shows over the basemap. Runs on the
// same-origin proxied image, so the canvas is not tainted.
function keyBlackToTransparent(img: HTMLImageElement): string {
  const w = img.naturalWidth;
  const h = img.naturalHeight;
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  if (!ctx) return img.src;
  ctx.drawImage(img, 0, 0);
  const data = ctx.getImageData(0, 0, w, h);
  const px = data.data;
  for (let p = 0; p < px.length; p += 4) {
    if (px[p] <= NODATA_THRESHOLD && px[p + 1] <= NODATA_THRESHOLD && px[p + 2] <= NODATA_THRESHOLD) {
      px[p + 3] = 0;
    }
  }
  ctx.putImageData(data, 0, 0);
  return canvas.toDataURL('image/png');
}

// Load a quicklook, key its black nodata transparent, and hand back the data
// URL (cached).
function loadTransparent(url: string, cb: (dataUrl: string) => void): void {
  const cached = qlDataUrlCache.get(url);
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
    const dataUrl = keyBlackToTransparent(img);
    qlDataUrlCache.set(url, dataUrl);
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
  opacity: number,
): void {
  if (map.getSource(srcId)) return;
  map.addSource(srcId, { type: 'image', url: dataUrl, coordinates: coords });
  map.addLayer(
    { id: lyrId, type: 'raster', source: srcId, paint: { 'raster-opacity': opacity, 'raster-fade-duration': 0 } },
    beforeAoi(map),
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
    tileSize: 256,
    bounds,
    minzoom: zoom.minZoom,
    maxzoom: zoom.maxZoom,
  });
  map.addLayer(
    { id: lyrId, type: 'raster', source: srcId, paint: { 'raster-opacity': opacity, 'raster-fade-duration': 0 } },
    beforeAoi(map),
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

export function ensureBaseLayers(map: MapLibreMap): void {
  if (!map.getSource(AOI_SRC)) {
    map.addSource(AOI_SRC, { type: 'geojson', data: EMPTY_FC });
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

export type CoverageDisplayMode = 'off' | 'density' | 'footprints';

export interface CoverageDisplay {
  mode: CoverageDisplayMode;
  cells: CoverageCell[];
  maxCount: number;
  footprints: GeoJSON.FeatureCollection | null;
}

// Reconciles both coverage layers with the current mode — only one of the
// two ever carries data, so a stray re-render can't show density and
// footprints at once (`store.ts` picks the mode via `coverage.ts::showFootprints`).
export function setCoverageDisplay(map: MapLibreMap, display: CoverageDisplay): void {
  const density = display.mode === 'density';
  const footprints = display.mode === 'footprints';
  setData(map, COVERAGE_SRC, density ? cellsToFeatureCollection(display.cells) : EMPTY_FC);
  if (density && map.getLayer('coverage-heat')) {
    map.setPaintProperty('coverage-heat', 'fill-color', coverageFillColorExpression(display.maxCount));
  }
  setVisibility(map, 'coverage-heat', density);
  setData(map, COVERAGE_FOOTPRINTS_SRC, footprints ? (display.footprints ?? EMPTY_FC) : EMPTY_FC);
  setVisibility(map, 'coverage-footprints-line', footprints);
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

function clearDynamicMosaic(map: MapLibreMap): void {
  // Remove by deterministic id across the whole index range — not just the
  // tracked ids — so an overlay placed by a slow async quicklook load that
  // finished around a re-sync can't survive as an orphan.
  for (let i = 0; i < MAX_MOSAIC_LAYERS; i++) {
    for (const lyr of [`m-img-lyr-${i}`, `m-tiles-lyr-${i}`]) {
      if (map.getLayer(lyr)) map.removeLayer(lyr);
    }
    for (const src of [`m-img-src-${i}`, `m-tiles-src-${i}`]) {
      if (map.getSource(src)) map.removeSource(src);
    }
  }
  dynLayerIds = [];
  dynSourceIds = [];
}

const beforeAoi = (map: MapLibreMap): string | undefined =>
  map.getLayer('aoi-fill') ? 'aoi-fill' : undefined;

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
): void {
  const plan = quicklookPlan(item, dataset);
  if (!plan) return;
  if (plan.kind === 'tiles') {
    // Placed by the tile grid itself, not by four corner coordinates: a tile is
    // already in the map's own projection, so there is nothing to reproject and
    // nothing to get wrong at a scene's rotated edges (the M2-16 bug).
    if (!item.bbox) return;
    placeRaster(
      map,
      `m-tiles-src-${i}`,
      `m-tiles-lyr-${i}`,
      buildTileUrl(buildTileTemplate(dataset.id, item.id, plan.asset), plan.render),
      item.bbox,
      1,
      { minZoom: plan.zoom, maxZoom: plan.zoom },
    );
    dynSourceIds.push(`m-tiles-src-${i}`);
    dynLayerIds.push(`m-tiles-lyr-${i}`);
    return;
  }
  const coords = quicklookCoords(item);
  if (!coords) return;
  const srcId = `m-img-src-${i}`;
  const lyrId = `m-img-lyr-${i}`;
  loadTransparent(plan.href, (dataUrl) => {
    if (gen !== syncGen) return; // a newer sync superseded this group
    try {
      placeImage(map, srcId, lyrId, dataUrl, coords, 1);
      dynSourceIds.push(srcId);
      dynLayerIds.push(lyrId);
    } catch {
      /* map/style went away while loading */
    }
  });
}

// `clip` is the AOI to cut this scene's tiles to, or `null` for the whole
// scene ("View full selection", M3-09) — resolved by the caller from
// `cropToAoi`, never read here from anywhere else, so this stays the one
// place a raster overlay's tile URL is actually built.
function addTiles(
  map: MapLibreMap,
  info: DownloadedInfo,
  i: number,
  render: AppliedRender,
  clip: GeoJSON.Geometry | null,
): void {
  const srcId = `m-tiles-src-${i}`;
  const lyrId = `m-tiles-lyr-${i}`;
  placeRaster(map, srcId, lyrId, clipTileUrl(buildTileUrl(info.tileUrl, render), clip), info.bounds, 1, info);
  dynSourceIds.push(srcId);
  dynLayerIds.push(lyrId);
}

// --- layer manager rendering (pinned overlays, independent of the active view) ---
function clearLayerOverlays(map: MapLibreMap): void {
  for (let i = 0; i < MAX_LAYER_OVERLAYS; i++) {
    if (map.getLayer(`layer-lyr-${i}`)) map.removeLayer(`layer-lyr-${i}`);
    if (map.getSource(`layer-src-${i}`)) map.removeSource(`layer-src-${i}`);
  }
}

export function syncLayers(map: MapLibreMap, layers: MapLayer[]): void {
  const gen = ++layerGen;
  clearLayerOverlays(map);
  // Render bottom-to-top: layers[0] is the top of the list, so draw it last.
  let idx = 0;
  for (const layer of [...layers].reverse()) {
    if (!layer.visible) continue;
    for (const ov of layer.overlays) {
      if (idx >= MAX_LAYER_OVERLAYS) break;
      const srcId = `layer-src-${idx}`;
      const lyrId = `layer-lyr-${idx}`;
      idx += 1;
      if (ov.kind === 'raster') {
        placeRaster(map, srcId, lyrId, ov.tileUrl, ov.bounds, layer.opacity, ov);
      } else {
        loadTransparent(ov.url, (dataUrl) => {
          if (gen !== layerGen) return;
          try {
            placeImage(map, srcId, lyrId, dataUrl, ov.coords, layer.opacity);
          } catch {
            /* superseded / map gone */
          }
        });
      }
    }
  }
}

export interface MosaicState {
  items: StacItem[]; // items of the active time step
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
  s: Pick<MosaicState, 'downloaded' | 'render' | 'showDownloaded' | 'aoi' | 'cropToAoi'>,
): void {
  clearDynamicMosaic(map);
  if (!s.showDownloaded) return;
  const clip = s.cropToAoi ? (s.aoi ?? null) : null;
  const entries = Object.entries(s.downloaded).slice(0, MAX_MOSAIC_LAYERS);
  // Drawn in reverse selection order, so the *first*-selected scene ends up
  // topmost — the same "first valid pixel wins" rule the download's mosaic
  // uses (rio_tiler's `FirstMethod`, `adr/0006` §3.5), so overlapping scenes
  // agree between the view and the downloaded file. This used to draw in
  // selection order, putting the *last*-selected scene on top instead
  // (M3-09 finding).
  [...entries].reverse().forEach(([, info], i) => addTiles(map, info, i, s.render, clip));
}

// Browse-mode preview overlays: one per scene of `items` (the active time
// step, plus any scene pinned onto the map by a cross-group selection — see
// `itemsForMap`, V-3 finding 2). Without a dataset there is nothing to
// preview *from* — the registry decides both the image and the level.
export function syncBrowseMosaic(map: MapLibreMap, s: Pick<MosaicState, 'items' | 'dataset'>): void {
  const gen = ++syncGen;
  clearDynamicMosaic(map);
  const items = s.items.slice(0, MAX_MOSAIC_LAYERS);
  const { dataset } = s;
  if (dataset) items.forEach((it, i) => addPreview(map, it, i, gen, dataset));
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
  syncHighlight(map, s);
}
